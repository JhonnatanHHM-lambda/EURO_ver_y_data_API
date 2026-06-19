import io
import re
from datetime import datetime

import pandas as pd
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import parsers

from EURO_ver_y_data.decoradores import require_permission
from Trazabilidad.models import EmpleadoTrazabilidad, Sede, HistorialCambioRegistro


def _norm_doc(val):
    if not val or str(val).strip() in ('', 'nan', 'None'):
        return None
    return re.sub(r'[\.\-\s]', '', str(val).strip()) or None


def _clasificar(registros):
    """Dado los registros de una persona, retorna su clasificación para PandaPé."""
    estados = [r.estado_candidato for r in registros]
    if any(e in ('INHABILITADO', 'REVISION_MANUAL_RECHAZADA') for e in estados):
        return 'CON_ANTECEDENTES'
    return 'CON_HISTORIAL'


def _reg_dict(reg):
    return {
        'id': reg.id,
        'origen_datos': reg.origen_datos,
        'tipo_proceso': reg.tipo_proceso,
        'estado_candidato': reg.estado_candidato,
        'cargo': reg.cargo or '',
        'sede': reg.sede.nombre if reg.sede else None,
        'fecha_ingreso': str(reg.fecha_ingreso) if reg.fecha_ingreso else None,
        'fecha_retiro': str(reg.fecha_retiro) if reg.fecha_retiro else None,
        'motivo_retiro': reg.motivo_retiro or '',
    }


def _parse_fecha(val):
    if not val or str(val).strip() in ('', 'nan', 'None'):
        return None
    v = str(val).strip().split(' ')[0]
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y'):
        try:
            return datetime.strptime(v, fmt).date()
        except ValueError:
            pass
    return None


class PandapeProcesarView(APIView):
    parser_classes = [parsers.MultiPartParser]

    @require_permission(['can_upload_excel'], app_label='Usuarios')
    def post(self, request):
        archivo = request.FILES.get('archivo')
        if not archivo:
            return Response({'error': 'Adjunta el reporte de PandaPé.'}, status=400)

        try:
            df = pd.read_excel(io.BytesIO(archivo.read()), dtype=str)
            df.columns = [str(c).strip() for c in df.columns]
            df = df.where(pd.notnull(df), '')
        except Exception as e:
            return Response({'error': f'No se pudo leer el archivo: {e}'}, status=400)

        if 'CPF' not in df.columns:
            return Response({
                'error': 'El archivo no tiene columna CPF. Verifica que sea el reporte correcto de PandaPé.'
            }, status=400)

        candidatos = []
        for _, row in df.iterrows():
            doc = _norm_doc(row.get('CPF', ''))
            if not doc:
                continue
            nombre = str(row.get('Nombre', '') or '').strip()
            apellido = str(row.get('Apellido', '') or '').strip()
            tel_raw = str(row.get('Móvil', '') or row.get('Teléfono', '') or '').strip()
            tel = re.sub(r'^57[\-\s]?', '', tel_raw).strip()
            experiencia = str(row.get('Experiencia profesional', '') or '').strip()
            origen_app  = str(row.get('Origen de la aplicación', '') or '').strip()
            obs_parts   = [p for p in [
                f'Experiencia: {experiencia}' if experiencia else '',
                f'Origen aplicación: {origen_app}' if origen_app else '',
            ] if p]
            candidatos.append({
                'documento_id': doc,
                'nombre_completo': f'{nombre} {apellido}'.strip(),
                'email': str(row.get('Correo electrónico', '') or '').strip(),
                'celular': tel,
                'fecha_nacimiento': str(row.get('Fecha de nacimiento', '') or '').strip(),
                'fecha_aplicacion': str(row.get('Fecha de aplicación', '') or '').strip(),
                'provincia': str(row.get('Provincia', '') or '').strip(),
                'direccion': str(row.get('Dirección', '') or '').strip(),
                'estudios': str(row.get('Estudios', '') or '').strip(),
                'genero': str(row.get('Género', '') or '').strip(),
                'observaciones': ' | '.join(obs_parts),
                'historial_empresa': str(row.get('Historial de aplicación en la empresa', '') or '').strip(),
            })

        if not candidatos:
            return Response({'error': 'No se encontraron registros con CPF válido en el archivo.'}, status=400)

        docs = list({c['documento_id'] for c in candidatos})
        registros_bd = (
            EmpleadoTrazabilidad.objects
            .filter(documento_id__in=docs, estado=True)
            .select_related('sede')
        )
        por_doc = {}
        for reg in registros_bd:
            por_doc.setdefault(reg.documento_id, []).append(reg)

        habilitados = []
        con_antecedentes = []
        con_historial = []

        for cand in candidatos:
            regs = por_doc.get(cand['documento_id'], [])
            if not regs:
                habilitados.append({**cand, 'resultado': 'SIN_ANTECEDENTES', 'antecedentes': []})
            else:
                clase = _clasificar(regs)
                datos = {**cand, 'resultado': clase, 'antecedentes': [_reg_dict(r) for r in regs]}
                if clase == 'CON_ANTECEDENTES':
                    con_antecedentes.append(datos)
                else:
                    con_historial.append(datos)

        return Response({
            'habilitados': habilitados,
            'con_antecedentes': con_antecedentes,
            'con_historial': con_historial,
            'resumen': {
                'total': len(candidatos),
                'habilitados': len(habilitados),
                'con_antecedentes': len(con_antecedentes),
                'con_historial': len(con_historial),
            },
        })


class PandapeConfirmarView(APIView):

    @require_permission(['can_upload_excel'], app_label='Usuarios')
    def post(self, request):
        candidatos = request.data.get('candidatos', [])
        sede_id    = request.data.get('sede_id')
        nombre_archivo = request.data.get('nombre_archivo', 'Reporte PandaPé')

        if not candidatos:
            return Response({'error': 'No hay candidatos para incorporar.'}, status=400)

        sede = None
        if sede_id:
            try:
                sede = Sede.objects.get(id=sede_id, estado=True)
            except Sede.DoesNotExist:
                return Response({'error': 'Sede no encontrada.'}, status=404)

        from Trazabilidad.models import CargaExcel
        carga = CargaExcel.objects.create(
            sede=sede,
            nombre_archivo=nombre_archivo,
            origen_datos='PANDAPE',
            cargado_por=request.user,
        )

        creados = omitidos = 0
        errores = []

        for cand in candidatos:
            doc = _norm_doc(cand.get('documento_id', ''))
            if not doc:
                continue
            if EmpleadoTrazabilidad.objects.filter(
                documento_id=doc, origen_datos='PANDAPE',
                tipo_proceso='CANDIDATO', estado=True,
            ).exists():
                omitidos += 1
                continue
            try:
                EmpleadoTrazabilidad.objects.create(
                    documento_id=doc,
                    nombre_completo=cand.get('nombre_completo', ''),
                    email=cand.get('email', ''),
                    celular=cand.get('celular', ''),
                    fecha_nacimiento=_parse_fecha(cand.get('fecha_nacimiento', '')),
                    direccion=cand.get('direccion', ''),
                    barrio_municipio=cand.get('provincia', ''),
                    nivel_escolaridad=cand.get('estudios', ''),
                    sexo=cand.get('genero', ''),
                    observaciones=cand.get('observaciones', ''),
                    sede=sede,
                    origen_datos='PANDAPE',
                    tipo_proceso='CANDIDATO',
                    estado_candidato='HABILITADO',
                    fuente_carga='PANDAPE',
                    cargado_por=request.user,
                    carga_excel=carga,
                )
                creados += 1
            except Exception as e:
                errores.append({'documento_id': doc, 'error': str(e)})

        carga.total_registros = creados + omitidos + len(errores)
        carga.exitosos        = creados
        carga.fallidos        = len(errores)
        carga.errores         = errores
        carga.save(update_fields=['total_registros', 'exitosos', 'fallidos', 'errores'])

        partes = [f'{creados} candidato(s) incorporado(s) a la BD centralizada.']
        if omitidos:
            partes.append(f'{omitidos} ya existían y se omitieron.')
        return Response({
            'mensaje': ' '.join(partes),
            'creados': creados,
            'omitidos': omitidos,
            'errores': errores,
            'carga_id': carga.id,
        })


class PandapeAutorizarView(APIView):

    @require_permission(['can_edit_registros'], app_label='Usuarios')
    def post(self, request, documento_id):
        justificacion = str(request.data.get('justificacion', '')).strip()
        if len(justificacion) < 10:
            return Response({'error': 'La justificación debe tener al menos 10 caracteres.'}, status=400)

        bloqueados = list(EmpleadoTrazabilidad.objects.filter(
            documento_id=documento_id,
            estado=True,
            estado_candidato__in=['INHABILITADO', 'REVISION_MANUAL_RECHAZADA'],
        ))
        if not bloqueados:
            return Response({
                'error': 'No se encontraron registros bloqueados para este documento.'
            }, status=404)

        for reg in bloqueados:
            HistorialCambioRegistro.objects.create(
                registro=reg,
                campo='estado_candidato',
                valor_anterior=reg.estado_candidato,
                valor_nuevo='REVISION_MANUAL_AUTORIZADA',
                justificacion=f'[PandaPé] {justificacion}',
                modificado_por=request.user,
            )
            reg.estado_candidato = 'REVISION_MANUAL_AUTORIZADA'
            reg.save(update_fields=['estado_candidato'])

        return Response({
            'mensaje': f'Candidato autorizado. {len(bloqueados)} registro(s) actualizado(s).',
            'actualizados': len(bloqueados),
        })
