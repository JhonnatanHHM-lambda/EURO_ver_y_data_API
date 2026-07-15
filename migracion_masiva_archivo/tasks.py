import logging
import os
import shutil
from datetime import timedelta
from pathlib import Path

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from .execution_control import control
from .models import EjecucionCargaMasiva, LogProcesoDocumental, LoteDocumental
from .reports.reporte_fase5 import build_reporte_fase5_xlsx
from .reports.reporte_saia import (
    build_reporte_saia_xlsx,
    get_asuntos_exitosos_por_lote,
    send_reporte_saia_email,
)
from .services.metadata_service import procesar_lote_metadata
from .services.relaciones_service import relacionar_documentos_lote
from .services.saia.batch_service import cargar_lote_saia
from .services.saia.exceptions import SAIAError, SAIALoginError
from .services.saia.validation_service import validate_lote_for_saia


@shared_task(bind=True, max_retries=3, default_retry_delay=120)
def procesar_lote_migracion_masiva_archivo(self, lote_id, opciones=None):
    """
    Ejecuta el flujo real de Migración Masiva de Archivo sobre un lote ya inventariado.

    El POST de creación ya ejecuta F1/inventario al guardar los archivos en MEDIA_ROOT.
    Esta tarea ejecuta:
      F2 OCR / metadata
      F3 relaciones
      F4 validación previa a SAIA
      F5 carga SAIA, solo si opciones.cargar_saia=True
    """
    opciones = opciones or {}
    lote = LoteDocumental.objects.get(pk=lote_id)
    ejecucion = EjecucionCargaMasiva.objects.create(
        lote=lote,
        celery_task_id=self.request.id or '',
        estado_proceso='EN_PROCESO',
        total_documentos=lote.documentos.count(),
        dry_run=bool(opciones.get('dry_run', True)),
        headful=bool(opciones.get('headful', False)),
        tamano_sublote=int(opciones.get('limite') or 70),
        iniciado_por=opciones.get('usuario', ''),
        fecha_inicio=timezone.now(),
    )

    control.lote_id_activo = lote.id
    control.running = True
    control.estado = 'EN_EJECUCION'

    lote.estado_proceso = 'EN_PROCESO'
    lote.fecha_inicio = lote.fecha_inicio or timezone.now()
    lote.fecha_fin = None
    lote.save(update_fields=['estado_proceso', 'fecha_inicio', 'fecha_fin', 'modificado'])
    _log(lote, 'INFO', 'flujo_inicio', 'Inicia procesamiento real de Migración Masiva de Archivo.', opciones)

    try:
        _fase_metadata(lote, opciones)
        _fase_relaciones(lote)
        listos = _fase_validacion_saia(lote)

        if opciones.get('cargar_saia'):
            _fase_carga_saia(lote, ejecucion, opciones)
        else:
            _log(
                lote,
                'INFO',
                'fase5_omitida',
                'Validación SAIA finalizada. La carga real a SAIA no se ejecutó porque cargar_saia=false.',
                {'documentos_listos': listos},
            )

        _sincronizar_contadores(lote, ejecucion)

        if opciones.get('cargar_saia') and opciones.get('enviar_correo') and opciones.get('destinatarios'):
            enviar_reporte_email_lote(
                lote, ejecucion, opciones['destinatarios'],
                con_detalle=bool(opciones.get('con_detalle', False)),
            )

        estado_final = 'FINALIZADO_CON_ERRORES' if lote.total_fallidos or lote.total_revision else 'FINALIZADO'
        _finalizar(lote, ejecucion, estado_final)

    except SAIALoginError as exc:
        _log(lote, 'ERROR', 'saia_login_error', str(exc), {})
        try:
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            _finalizar(lote, ejecucion, 'FINALIZADO_CON_ERRORES', str(exc))
            return {'error': str(exc), 'lote_id': lote.id}

    except SAIAError as exc:
        _log(lote, 'ERROR', 'saia_error', str(exc), {})
        _finalizar(lote, ejecucion, 'FINALIZADO_CON_ERRORES', str(exc))
        return {'error': str(exc), 'lote_id': lote.id}

    except Exception as exc:
        _log(lote, 'ERROR', 'flujo_error', str(exc), {})
        _finalizar(lote, ejecucion, 'FINALIZADO_CON_ERRORES', str(exc))
        raise

    finally:
        control.marcar_finalizado()

    return {
        'lote_id': lote.id,
        'estado': lote.estado_proceso,
        'procesados': lote.total_procesados,
        'exitosos': lote.total_exitosos,
        'fallidos': lote.total_fallidos,
        'pendientes_revision': lote.total_revision,
    }


def _fase_metadata(lote, opciones):
    control.fase_actual = 'Fase 2 — OCR / Metadata'
    _log(lote, 'INFO', 'fase2_inicio', 'Inicia extracción de metadata y OCR.', {})
    resultados = procesar_lote_metadata(
        lote,
        usar_ocr=not bool(opciones.get('sin_ocr', False)),
        max_pages=int(opciones.get('max_pages') or 1),
        incluir_duplicados=False,
    )
    _log(lote, 'INFO', 'fase2_fin', 'Finaliza extracción de metadata y OCR.', {
        'procesados': len(resultados),
        'validados': sum(1 for r in resultados if r.get('estado') == 'VALIDADO'),
        'revision': sum(1 for r in resultados if r.get('estado') == 'REQUIERE_REVISION'),
        'errores': sum(1 for r in resultados if r.get('estado') == 'ERROR' or r.get('error')),
    })


def _fase_relaciones(lote):
    control.fase_actual = 'Fase 3 — Relaciones'
    _log(lote, 'INFO', 'fase3_inicio', 'Inicia relación de documentos.', {})
    resultado = relacionar_documentos_lote(lote)
    _log(lote, 'INFO', 'fase3_fin', 'Finaliza relación de documentos.', {
        'relaciones': len(resultado.get('relaciones', [])),
        'grupos_ambiguos': len(resultado.get('grupos_ambiguos', [])),
    })


def _fase_validacion_saia(lote):
    control.fase_actual = 'Fase 4 — Validación SAIA'
    _log(lote, 'INFO', 'fase4_inicio', 'Inicia validación previa a SAIA.', {})
    resultados = validate_lote_for_saia(lote, solo_listos=False)
    listos = sum(1 for r in resultados if r.get('listo_para_saia'))
    _log(lote, 'INFO', 'fase4_fin', 'Finaliza validación previa a SAIA.', {
        'listos': listos,
        'bloqueados': len(resultados) - listos,
    })
    return listos


def _fase_carga_saia(lote, ejecucion, opciones):
    control.fase_actual = 'Fase 5 — Carga SAIA'
    _log(lote, 'INFO', 'fase5_inicio', 'Inicia carga en SAIA.', {
        'dry_run': ejecucion.dry_run,
        'headful': ejecucion.headful,
        'limite': ejecucion.tamano_sublote,
    })
    resumen = cargar_lote_saia(
        lote_id=lote.id,
        limite=ejecucion.tamano_sublote,
        dry_run=ejecucion.dry_run,
        headful=ejecucion.headful,
        pausa_entre=int(opciones.get('pausa') or 3),
        max_reintentos=ejecucion.max_reintentos,
        include_errors=bool(opciones.get('incluir_errores', False)),
        ejecucion_id=ejecucion.id,
    )
    ejecucion.procesados += resumen.get('exitosos', 0) + resumen.get('fallidos', 0)
    ejecucion.exitosos += resumen.get('exitosos', 0)
    ejecucion.fallidos += resumen.get('fallidos', 0)
    ejecucion.save(update_fields=['procesados', 'exitosos', 'fallidos', 'modificado'])
    _log(lote, 'INFO', 'fase5_fin', 'Finaliza carga en SAIA.', resumen)
    if resumen.get('error_critico'):
        raise SAIAError(resumen['error_critico'])


def enviar_reporte_email_lote(lote, ejecucion, destinatarios, con_detalle=False):
    """
    Envia el reporte de PEL cargados a SAIA a los destinatarios indicados,
    adjuntando tambien el Excel de detalle de la ejecucion (Fase 5: cargados,
    fallidos, pendientes de revision). Un fallo aqui no debe tumbar el estado
    final del lote: send_reporte_saia_email ya registra exito/error en
    LogProcesoDocumental. Reutilizable tanto desde la tarea Celery como desde
    un endpoint de "reenviar reporte" sin re-ejecutar el pipeline.
    """
    try:
        items = get_asuntos_exitosos_por_lote(lote.id)
        if not items:
            _log(lote, 'INFO', 'reporte_saia_correo_omitido',
                 'No se envio correo: no hay documentos cargados exitosamente en este lote.', {})
            return
        xlsx_bytes = build_reporte_saia_xlsx(items, timezone.localdate(), con_detalle=con_detalle)
        xlsx_fase5_bytes = build_reporte_fase5_xlsx(ejecucion) if ejecucion else None
        send_reporte_saia_email(
            xlsx_bytes,
            timezone.localdate(),
            destinatarios,
            lote=lote,
            xlsx_fase5_bytes=xlsx_fase5_bytes,
            pendientes=ejecucion.pendientes_revision if ejecucion else 0,
        )
    except Exception as exc:
        _log(lote, 'ERROR', 'reporte_saia_correo_error', str(exc), {})


def _sincronizar_contadores(lote, ejecucion):
    documentos = lote.documentos.all()
    total = documentos.count()
    cargados = documentos.filter(estado_proceso='CARGADO_SAIA').count()
    revision = documentos.filter(estado_proceso='REQUIERE_REVISION').count()
    errores = documentos.filter(estado_proceso='ERROR_SAIA').count()
    procesados = documentos.exclude(estado_proceso='PENDIENTE').count()

    lote.total_archivos = total
    lote.total_procesados = procesados
    lote.total_exitosos = cargados
    lote.total_revision = revision
    lote.total_fallidos = errores
    lote.save(update_fields=[
        'total_archivos', 'total_procesados', 'total_exitosos',
        'total_revision', 'total_fallidos', 'modificado',
    ])

    ejecucion.total_documentos = total
    ejecucion.pendientes_revision = revision
    ejecucion.fallidos = max(ejecucion.fallidos, errores)
    ejecucion.exitosos = max(ejecucion.exitosos, cargados)
    ejecucion.procesados = max(ejecucion.procesados, procesados)
    ejecucion.save(update_fields=[
        'total_documentos', 'pendientes_revision', 'fallidos',
        'exitosos', 'procesados', 'modificado',
    ])


def _finalizar(lote, ejecucion, estado, error=''):
    lote.estado_proceso = estado
    lote.fecha_fin = timezone.now()
    lote.save(update_fields=['estado_proceso', 'fecha_fin', 'modificado'])

    ejecucion.estado_proceso = estado
    ejecucion.fecha_fin = timezone.now()
    ejecucion.error = error
    ejecucion.save(update_fields=['estado_proceso', 'fecha_fin', 'error', 'modificado'])

    _log(lote, 'INFO' if 'FINALIZADO' in estado else 'ERROR', 'flujo_fin', f'Flujo terminado: {estado}', {
        'estado': estado,
        'error': error,
        'total_archivos': lote.total_archivos,
        'procesados': lote.total_procesados,
        'exitosos': lote.total_exitosos,
        'fallidos': lote.total_fallidos,
        'revision': lote.total_revision,
    })


def _log(lote, nivel, evento, mensaje, detalle):
    LogProcesoDocumental.objects.create(
        lote=lote,
        nivel=nivel,
        evento=evento,
        mensaje=mensaje,
        detalle=detalle or {},
    )


# Compatibilidad con el nombre anterior usado durante el MVP.
procesar_carga_migracion_masiva_archivo = procesar_lote_migracion_masiva_archivo


@shared_task(name='migracion_masiva_archivo.tasks.purgar_logs_antiguos', queue='migracion_masiva_archivo')
def purgar_logs_antiguos_migracion_masiva_archivo():
    """
    Purga LogProcesoDocumental con mas de 90 dias de antiguedad para controlar el
    crecimiento de la tabla.

    Reemplaza el hilo de purga de un solo disparo por proceso del app de
    escritorio (threading.Timer con 5s de delay al arrancar): un servidor Django
    de larga duracion (Gunicorn) no se reinicia a diario como el app de
    escritorio, asi que ese patron casi nunca volveria a ejecutarse. Programada
    en CELERY_BEAT_SCHEDULE (settings.py) para correr diariamente.
    """
    cutoff = timezone.now() - timedelta(days=90)
    eliminados, _ = LogProcesoDocumental.objects.filter(creado__lt=cutoff).delete()
    if eliminados:
        logging.getLogger('migracion_masiva_archivo').info(
            'Limpieza automatica: %d logs eliminados (> 90 dias).', eliminados,
        )
    return {'eliminados': eliminados}


@shared_task(name='migracion_masiva_archivo.tasks.purgar_screenshots_saia', queue='migracion_masiva_archivo')
def purgar_screenshots_saia_antiguos():
    """
    Purga capturas de pantalla de SAIA_SCREENSHOT_DIR con mas de
    SAIA_SCREENSHOT_RETENTION_DIAS dias (default 30). Son evidencia de auditoria de
    cada intento de carga a SAIA (services/saia/browser_client.py:capture_screenshot),
    pero se acumulan indefinidamente sin este job — ver INFRA_MIGRACION_MASIVA_ARCHIVO.md.

    Usa la fecha de modificacion del archivo (no el timestamp en el nombre), asi que
    es robusto ante cualquier cambio futuro en el formato de nombre de archivo.
    """
    from .services.saia.config import get_saia_config

    retencion_dias = int(os.getenv('SAIA_SCREENSHOT_RETENTION_DIAS', '30'))
    cutoff_ts = (timezone.now() - timedelta(days=retencion_dias)).timestamp()
    screenshot_dir = get_saia_config().screenshot_dir

    eliminados = 0
    bytes_liberados = 0
    if screenshot_dir.is_dir():
        for archivo in screenshot_dir.glob('*.png'):
            try:
                stat = archivo.stat()
                if stat.st_mtime < cutoff_ts:
                    bytes_liberados += stat.st_size
                    archivo.unlink()
                    eliminados += 1
            except OSError:
                continue

    if eliminados:
        logging.getLogger('migracion_masiva_archivo').info(
            'Limpieza automatica: %d capturas de pantalla SAIA eliminadas (> %d dias, %.1f MB liberados).',
            eliminados, retencion_dias, bytes_liberados / (1024 * 1024),
        )
    return {'eliminados': eliminados, 'bytes_liberados': bytes_liberados}


_ESTADOS_LOTE_TERMINALES = {'FINALIZADO', 'FINALIZADO_CON_ERRORES', 'CANCELADO'}


@shared_task(name='migracion_masiva_archivo.tasks.purgar_uploads_antiguos', queue='migracion_masiva_archivo')
def purgar_uploads_antiguos_migracion_masiva_archivo():
    """
    Purga las carpetas de archivos subidos vía API (MIGRACION_ARCHIVOS_MEDIA_ROOT/uploads/<uuid>,
    creadas por views._guardar_archivos_temporales) para lotes en estado terminal con mas de
    MIGRACION_ARCHIVOS_UPLOADS_RETENTION_DIAS dias (default 90) desde su ultima modificacion.

    Solo toca carpeta_origen que esta DENTRO de MIGRACION_ARCHIVOS_MEDIA_ROOT/uploads: los lotes
    creados apuntando directamente a una carpeta de red (ej. el share montado en /mnt/...) nunca
    se tocan aqui -- esos archivos son el repositorio vivo de la oficina, no un upload desechable
    de este sistema. Ver INFRA_MIGRACION_MASIVA_ARCHIVO.md.
    """
    retencion_dias = int(os.getenv('MIGRACION_ARCHIVOS_UPLOADS_RETENTION_DIAS', '90'))
    cutoff = timezone.now() - timedelta(days=retencion_dias)
    uploads_root = Path(getattr(settings, 'MIGRACION_ARCHIVOS_MEDIA_ROOT', settings.MEDIA_ROOT)) / 'uploads'
    uploads_root_resolved = str(uploads_root.resolve())

    candidatos = LoteDocumental.objects.filter(
        estado_proceso__in=_ESTADOS_LOTE_TERMINALES,
        modificado__lt=cutoff,
    )

    eliminados = 0
    for lote in candidatos:
        carpeta = Path(lote.carpeta_origen)
        try:
            carpeta_resuelta = str(carpeta.resolve())
        except OSError:
            continue
        # Guard de seguridad: solo se borra si la ruta realmente esta dentro de la
        # carpeta de uploads de este modulo, nunca una ruta de red arbitraria.
        if not carpeta_resuelta.startswith(uploads_root_resolved + os.sep):
            continue
        if not carpeta.is_dir():
            continue

        shutil.rmtree(carpeta, ignore_errors=True)
        eliminados += 1
        LogProcesoDocumental.objects.create(
            lote=lote,
            nivel='INFO',
            evento='purga_uploads_antiguos',
            mensaje=(
                f'Carpeta de archivos subidos eliminada tras {retencion_dias} dias '
                f'en estado terminal ({lote.estado_proceso}).'
            ),
            detalle={'carpeta_origen': str(carpeta)},
        )

    if eliminados:
        logging.getLogger('migracion_masiva_archivo').info(
            'Limpieza automatica: %d carpeta(s) de uploads de lotes terminados eliminadas (> %d dias).',
            eliminados, retencion_dias,
        )
    return {'eliminados': eliminados}
