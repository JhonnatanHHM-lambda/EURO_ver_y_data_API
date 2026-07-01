"""
Tarea Celery principal del módulo OptimizacionCorreos.

Flujo:
  1. Marcar ejecución EN_PROCESO
  2. Autenticar en RADIAN (Playwright + CapSolver + Graph OTP)
  3. Listar documentos del rango de fechas
  4. Descargar ZIPs y parsear con xml_parser → guardar FacturaRadian
  5. Obtener correos Zimbra del rango → parsear XML adjunto → guardar FacturaCorreo
  6. Ejecutar conciliación N1/N2/N3 → guardar ResultadoConciliacion
  7. Actualizar conteos en EjecucionConsolidacion → COMPLETADA
"""
from __future__ import annotations

import datetime as dt
import tempfile
from decimal import Decimal
from pathlib import Path

from celery import shared_task
from django.utils import timezone


@shared_task(
    name='OptimizacionCorreos.tasks.ejecutar_consolidacion',
    queue='optimizacion_correos',
    bind=True,
    max_retries=0,
)
def ejecutar_consolidacion(self, ejecucion_id: int):
    from .models import (
        EjecucionConsolidacion, FacturaRadian, FacturaCorreo, ResultadoConciliacion,
    )
    from .utils.crypto_utils import decrypt_credential
    from .utils.dian_client import DianClient
    from .utils.xml_parser import parse_zip, parse_invoice_element, _extraer_invoice_de_attached
    from .utils.zimbra_client import ZimbraHttpClient
    from .utils.conciliacion import conciliar

    ejecucion = EjecucionConsolidacion.objects.get(pk=ejecucion_id)

    try:
        # ── 1. Marcar EN_PROCESO ─────────────────────────────────────────────
        ejecucion.estado = 'EN_PROCESO'
        ejecucion.iniciada_en = timezone.now()
        ejecucion.completada_en = None
        ejecucion.error_mensaje = ''
        ejecucion.total_radian = 0
        ejecucion.total_correo = 0
        ejecucion.total_conciliadas = 0
        ejecucion.total_solo_radian = 0
        ejecucion.total_solo_correo = 0
        ejecucion.total_revision = 0
        ejecucion.save(update_fields=[
            'estado', 'iniciada_en', 'completada_en', 'error_mensaje',
            'total_radian', 'total_correo', 'total_conciliadas',
            'total_solo_radian', 'total_solo_correo', 'total_revision',
        ])
        ResultadoConciliacion.objects.filter(ejecucion=ejecucion).delete()
        FacturaRadian.objects.filter(ejecucion=ejecucion).delete()
        FacturaCorreo.objects.filter(ejecucion=ejecucion).delete()

        fecha_desde = ejecucion.fecha_desde
        fecha_hasta = ejecucion.fecha_hasta

        # ── 2 & 3. Autenticar RADIAN y listar documentos ─────────────────────
        cc_rep = decrypt_credential('OC_DIAN_CC_REP_ENC')
        cli = DianClient(cc_rep=cc_rep)
        auth_result = cli.autenticar()
        if not auth_result.get('autenticado'):
            raise RuntimeError('RADIAN no quedo autenticado; no se listan documentos.')

        resultado_dian = cli.listar_documentos(
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
            length=500,
        )
        documentos = resultado_dian.get('data', [])

        # ── 4. Descargar ZIPs y guardar FacturaRadian ─────────────────────────
        facturas_radian_bulk = []
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            for doc in documentos:
                # Probar candidatos de ID en orden sin resolver captcha por documento.
                # descargar_zip_documento resuelve un captcha por doc (lento en bulk);
                # en sesión autenticada el endpoint acepta la descarga sin captcha.
                zip_path = None
                track_id = ''
                for _, candidate_id in cli._download_id_candidates(doc):
                    try:
                        zip_path = cli.descargar_zip(candidate_id, tmp_path)
                        track_id = candidate_id
                        break
                    except Exception:
                        continue
                if zip_path is None:
                    continue
                try:
                    fx = parse_zip(zip_path)
                except Exception:
                    continue

                if not fx.cufe and not fx.numero:
                    continue

                total_val = Decimal(str(fx.total)) if fx.total is not None else Decimal('0')
                fecha_em = None
                if fx.fecha_emision:
                    try:
                        fecha_em = dt.date.fromisoformat(fx.fecha_emision)
                    except (ValueError, TypeError):
                        pass

                facturas_radian_bulk.append(FacturaRadian(
                    ejecucion=ejecucion,
                    cufe=fx.cufe or '',
                    numero=fx.numero or '',
                    nit_proveedor=fx.emisor_nit or '',
                    nombre_proveedor=fx.emisor_nombre or '',
                    total=total_val,
                    fecha_emision=fecha_em or fecha_desde,
                    tipo_documento='01',
                    track_id=track_id,
                ))

        if facturas_radian_bulk:
            FacturaRadian.objects.bulk_create(facturas_radian_bulk, batch_size=200)

        # ── 5. Obtener correos Zimbra y guardar FacturaCorreo ─────────────────
        zimbra = ZimbraHttpClient()
        correos = zimbra.obtener_correos(
            fecha_desde=fecha_desde.isoformat(),
            fecha_hasta=fecha_hasta.isoformat(),
        )

        facturas_correo_bulk = []
        for correo in correos:
            asunto = correo.get('subject') or correo.get('asunto') or ''
            fecha_correo_raw = (
                correo.get('date') or correo.get('fecha') or
                correo.get('receivedDateTime') or correo.get('received_at') or ''
            )
            remitente = (
                correo.get('from') or correo.get('remitente') or
                correo.get('sender') or ''
            )
            nombre_remitente = correo.get('from_name') or correo.get('nombre_remitente') or ''
            carpeta = correo.get('folder') or correo.get('carpeta') or ''

            # Parsear fecha del correo
            fecha_correo_dt = None
            if fecha_correo_raw:
                for fmt in ('%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%dT%H:%M:%S',
                            '%Y-%m-%d %H:%M:%S', '%Y-%m-%d'):
                    try:
                        parsed = dt.datetime.strptime(str(fecha_correo_raw)[:19], fmt)
                        fecha_correo_dt = timezone.make_aware(parsed)
                        break
                    except (ValueError, TypeError):
                        continue
            if not fecha_correo_dt:
                fecha_correo_dt = timezone.now()

            # Intentar extraer XML del adjunto
            xml_bytes = zimbra.descargar_adjunto_xml(correo)
            fx = None
            if xml_bytes:
                try:
                    inv_el = _extraer_invoice_de_attached(xml_bytes)
                    if inv_el is not None:
                        fx = parse_invoice_element(inv_el)
                except Exception:
                    pass

            total_val = None
            fecha_em = None
            if fx:
                if fx.total is not None:
                    total_val = Decimal(str(fx.total))
                if fx.fecha_emision:
                    try:
                        fecha_em = dt.date.fromisoformat(fx.fecha_emision)
                    except (ValueError, TypeError):
                        pass

            facturas_correo_bulk.append(FacturaCorreo(
                ejecucion=ejecucion,
                cufe=(fx.cufe or '') if fx else '',
                numero=(fx.numero or '') if fx else '',
                nit_proveedor=(fx.emisor_nit or '') if fx else '',
                nombre_proveedor=(fx.emisor_nombre or '') if fx else '',
                total=total_val,
                fecha_emision=fecha_em,
                asunto_correo=asunto[:500],
                fecha_correo=fecha_correo_dt,
                remitente=str(remitente)[:255],
                nombre_remitente=str(nombre_remitente)[:255],
                carpeta=str(carpeta)[:255],
            ))

        if facturas_correo_bulk:
            FacturaCorreo.objects.bulk_create(facturas_correo_bulk, batch_size=200)

        # ── 6. Conciliación ───────────────────────────────────────────────────
        facturas_radian_qs = list(ejecucion.facturas_radian.all())
        facturas_correo_qs = list(ejecucion.facturas_correo.all())

        pares = conciliar(ejecucion, facturas_radian_qs, facturas_correo_qs)

        resultados_bulk = [ResultadoConciliacion(**p) for p in pares]
        if resultados_bulk:
            ResultadoConciliacion.objects.bulk_create(resultados_bulk, batch_size=200)

        # ── 7. Actualizar conteos y COMPLETADA ────────────────────────────────
        total_conciliadas = sum(1 for p in pares if p['estado'] == 'CONCILIADA')
        total_solo_radian = sum(1 for p in pares if p['estado'] == 'SOLO_RADIAN')
        total_solo_correo = sum(1 for p in pares if p['estado'] == 'SOLO_CORREO')
        total_revision = sum(1 for p in pares if p['estado'] == 'REVISION_MANUAL')

        ejecucion.estado = 'COMPLETADA'
        ejecucion.completada_en = timezone.now()
        ejecucion.total_radian = len(facturas_radian_qs)
        ejecucion.total_correo = len(facturas_correo_qs)
        ejecucion.total_conciliadas = total_conciliadas
        ejecucion.total_solo_radian = total_solo_radian
        ejecucion.total_solo_correo = total_solo_correo
        ejecucion.total_revision = total_revision
        ejecucion.save(update_fields=[
            'estado', 'completada_en', 'total_radian', 'total_correo',
            'total_conciliadas', 'total_solo_radian', 'total_solo_correo',
            'total_revision',
        ])

    except Exception as exc:
        ejecucion.estado = 'ERROR'
        ejecucion.error_mensaje = str(exc)
        ejecucion.completada_en = timezone.now()
        ejecucion.save(update_fields=['estado', 'error_mensaje', 'completada_en'])
        raise
