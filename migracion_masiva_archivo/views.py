import uuid
from datetime import date
from pathlib import Path

from celery import current_app
from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.text import get_valid_filename
from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from EURO_ver_y_data.decoradores import require_permission

from .models import (
    ConfiguracionMigracionMasivaArchivo,
    DocumentoDigitalizado,
    LogProcesoDocumental,
    LoteDocumental,
)
from .reports.reporte_saia import (
    build_reporte_saia_xlsx,
    get_asuntos_exitosos_por_fecha,
    send_reporte_saia_email,
)
from .reports.reporte_service import build_exploration_xlsx
from .serializers import (
    ArchivoMigracionSerializer,
    CargaMasivaArchivoCreateSerializer,
    CargaMasivaArchivoDetailSerializer,
    CargaMasivaArchivoListSerializer,
    LogMigracionMasivaArchivoSerializer,
)
from .services.lote_service import crear_lote_desde_carpeta
from .services.saia.exceptions import SAIALocalFileError
from .services.saia.local_file_service import mark_document_file_ok
from .tasks import enviar_reporte_email_lote, procesar_lote_migracion_masiva_archivo


class CargaMasivaArchivoListCreateView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    @require_permission(['can_view_migracion_masiva_archivo'], app_label='Usuarios')
    def get(self, request):
        cargas = LoteDocumental.objects.all()
        serializer = CargaMasivaArchivoListSerializer(cargas, many=True)
        return Response(serializer.data)

    @require_permission(['can_manage_migracion_masiva_archivo'], app_label='Usuarios')
    def post(self, request):
        serializer = CargaMasivaArchivoCreateSerializer(
            data=request.data,
            context={'max_upload_mb': getattr(settings, 'MIGRACION_ARCHIVOS_MAX_UPLOAD_MB', 100)},
        )
        serializer.is_valid(raise_exception=True)

        carpeta = _guardar_archivos_temporales(serializer.validated_data['archivos'])
        archivos_secundarios = serializer.validated_data.get('archivos_secundarios')
        carpeta_secundaria = (
            _guardar_archivos_temporales(archivos_secundarios) if archivos_secundarios else None
        )
        lote, _documentos = crear_lote_desde_carpeta(
            carpeta_origen=str(carpeta),
            nombre=serializer.validated_data['nombre'],
            usuario=request.user,
            carpeta_secundaria=str(carpeta_secundaria) if carpeta_secundaria else None,
        )
        descripcion = serializer.validated_data.get('descripcion', '')
        if descripcion:
            lote.observaciones = descripcion
            lote.save(update_fields=['observaciones', 'modificado'])

        LogProcesoDocumental.objects.create(
            lote=lote,
            nivel='INFO',
            evento='carga_creada_api',
            mensaje=f'Carga creada desde API con {lote.total_archivos} documento(s).',
            detalle={'carpeta_origen': lote.carpeta_origen},
        )
        response = CargaMasivaArchivoDetailSerializer(lote, context={'request': request})
        return Response(response.data, status=status.HTTP_201_CREATED)


class CargaMasivaArchivoDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @require_permission(['can_view_migracion_masiva_archivo'], app_label='Usuarios')
    def get(self, request, pk):
        carga = get_object_or_404(LoteDocumental, pk=pk)
        serializer = CargaMasivaArchivoDetailSerializer(carga, context={'request': request})
        return Response(serializer.data)

    @require_permission(['can_manage_migracion_masiva_archivo'], app_label='Usuarios')
    def delete(self, request, pk):
        carga = get_object_or_404(LoteDocumental, pk=pk)
        carga.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProcesarCargaView(APIView):
    permission_classes = [IsAuthenticated]

    @require_permission(['can_manage_migracion_masiva_archivo'], app_label='Usuarios')
    def post(self, request, pk):
        carga = get_object_or_404(LoteDocumental, pk=pk)
        if carga.estado_proceso == 'EN_PROCESO':
            return Response({'detail': 'La carga ya está en proceso.'}, status=status.HTTP_400_BAD_REQUEST)

        cargar_saia = _bool_request(request.data.get('cargar_saia'), default=False)
        if cargar_saia and not request.user.has_perm('Usuarios.can_upload_migracion_masiva_archivo_saia'):
            return Response(
                {
                    'error': 'Permiso denegado',
                    'required': ['Usuarios.can_upload_migracion_masiva_archivo_saia'],
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        dry_run = _bool_request(request.data.get('dry_run'), default=not cargar_saia)
        headful = _bool_request(request.data.get('headful'), default=False)
        incluir_errores = _bool_request(request.data.get('incluir_errores'), default=False)
        enviar_correo = _bool_request(request.data.get('enviar_correo'), default=False)
        sin_ocr = _bool_request(request.data.get('sin_ocr'), default=False)
        con_detalle = _bool_request(request.data.get('con_detalle'), default=False)
        max_pages = int(request.data.get('max_pages') or 1)
        limite = int(request.data.get('limite') or getattr(settings, 'MIGRACION_ARCHIVOS_SAIA_LIMITE', 70))

        destinatarios = _parse_destinatarios(request)
        if enviar_correo and not destinatarios:
            default = _correo_destino_usuario(request.user)
            if default:
                destinatarios = [default]

        task = procesar_lote_migracion_masiva_archivo.delay(
            carga.id,
            {
                'cargar_saia': cargar_saia,
                'dry_run': dry_run,
                'headful': headful,
                'limite': limite,
                'incluir_errores': incluir_errores,
                'sin_ocr': sin_ocr,
                'max_pages': max_pages,
                'enviar_correo': enviar_correo,
                'con_detalle': con_detalle,
                'destinatarios': destinatarios,
                'usuario': str(request.user),
            },
        )
        carga.estado_proceso = 'PENDIENTE'
        carga.save(update_fields=['estado_proceso', 'modificado'])
        return Response({
            'carga_id': carga.id,
            'task_id': task.id,
            'estado': carga.estado_proceso,
            'cargar_saia': cargar_saia,
            'dry_run': dry_run,
        })


class EstadoCargaView(APIView):
    permission_classes = [IsAuthenticated]

    @require_permission(['can_view_migracion_masiva_archivo'], app_label='Usuarios')
    def get(self, request, pk):
        carga = get_object_or_404(LoteDocumental, pk=pk)
        return Response(CargaMasivaArchivoListSerializer(carga).data)


class ResultadosCargaView(APIView):
    permission_classes = [IsAuthenticated]

    @require_permission(['can_view_migracion_masiva_archivo'], app_label='Usuarios')
    def get(self, request, pk):
        carga = get_object_or_404(LoteDocumental, pk=pk)
        archivos = carga.documentos.all()
        return Response({
            'carga': CargaMasivaArchivoListSerializer(carga).data,
            'archivos': ArchivoMigracionSerializer(archivos, many=True, context={'request': request}).data,
        })


class LogsCargaView(APIView):
    permission_classes = [IsAuthenticated]

    @require_permission(['can_view_migracion_masiva_archivo'], app_label='Usuarios')
    def get(self, request, pk):
        carga = get_object_or_404(LoteDocumental, pk=pk)
        logs = carga.logs.all()
        return Response(LogMigracionMasivaArchivoSerializer(logs, many=True).data)


class DescargarReporteCargaView(APIView):
    """
    Reporte de diagnostico completo (145 columnas: continuidad, OCR, duplicados
    historicos, relaciones, mensajes de error por fase) via
    reports.reporte_service.build_exploration_xlsx — el mismo generador que ya
    usan los comandos manuales de F1-F3, antes solo disponible por esa via. Sin
    continuity_context (requeriria re-escanear la carpeta de origen), asi que
    la hoja "Resumen" y las alertas de continuidad no aparecen aqui; el resto
    del reporte (duplicados, relaciones, errores por fase) si queda completo.
    """
    permission_classes = [IsAuthenticated]

    @require_permission(['can_view_migracion_masiva_archivo'], app_label='Usuarios')
    def get(self, request, pk):
        carga = get_object_or_404(LoteDocumental, pk=pk)
        documentos = DocumentoDigitalizado.objects.filter(lote=carga).select_related('metadata')
        xlsx_bytes = build_exploration_xlsx(documentos, carpeta_origen=carga.carpeta_origen)
        response = HttpResponse(
            xlsx_bytes,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        response['Content-Disposition'] = f'attachment; filename="migracion_masiva_archivo_{carga.id}.xlsx"'
        return response


class ReenviarReporteCargaView(APIView):
    """Regenera y reenvia el reporte SAIA de un lote ya procesado, sin volver
    a correr el pipeline F2-F5."""
    permission_classes = [IsAuthenticated]

    @require_permission(['can_manage_migracion_masiva_archivo'], app_label='Usuarios')
    def post(self, request, pk):
        carga = get_object_or_404(LoteDocumental, pk=pk)
        destinatarios = _parse_destinatarios(request)
        if not destinatarios:
            default = _correo_destino_usuario(request.user)
            if default:
                destinatarios = [default]
        if not destinatarios:
            return Response({'detail': 'No hay destinatario configurado.'}, status=status.HTTP_400_BAD_REQUEST)

        con_detalle = _bool_request(request.data.get('con_detalle'), default=False)
        ejecucion = carga.ejecuciones.order_by('-creado').first()
        enviar_reporte_email_lote(carga, ejecucion, destinatarios, con_detalle=con_detalle)
        return Response({'ok': True, 'destinatarios': destinatarios})


class ReporteDiarioSAIAView(APIView):
    """Reporte consolidado de todos los lotes cargados exitosamente en una
    fecha (equivalente web de generar_reporte_saia.py --fecha)."""
    permission_classes = [IsAuthenticated]

    @require_permission(['can_view_migracion_masiva_archivo'], app_label='Usuarios')
    def get(self, request):
        fecha = _parse_fecha(request.query_params.get('fecha'))
        con_detalle = _bool_request(request.query_params.get('con_detalle'), default=False)
        items = get_asuntos_exitosos_por_fecha(fecha)
        workbook_bytes = build_reporte_saia_xlsx(items, fecha, con_detalle=con_detalle)
        response = HttpResponse(
            workbook_bytes,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        response['Content-Disposition'] = f'attachment; filename="reporte_saia_{fecha.isoformat()}.xlsx"'
        return response

    @require_permission(['can_manage_migracion_masiva_archivo'], app_label='Usuarios')
    def post(self, request):
        fecha = _parse_fecha(request.data.get('fecha'))
        con_detalle = _bool_request(request.data.get('con_detalle'), default=False)
        destinatarios = _parse_destinatarios(request)
        if not destinatarios:
            default = _correo_destino_usuario(request.user)
            if default:
                destinatarios = [default]
        if not destinatarios:
            return Response({'detail': 'No hay destinatario configurado.'}, status=status.HTTP_400_BAD_REQUEST)

        items = get_asuntos_exitosos_por_fecha(fecha)
        if not items:
            return Response({'detail': f'No hay cargas exitosas para {fecha.isoformat()}.'}, status=status.HTTP_404_NOT_FOUND)
        xlsx_bytes = build_reporte_saia_xlsx(items, fecha, con_detalle=con_detalle)
        send_reporte_saia_email(xlsx_bytes, fecha, destinatarios)
        return Response({'ok': True, 'destinatarios': destinatarios, 'total': len(items)})


def _parse_fecha(valor):
    if not valor:
        return timezone.localdate()
    try:
        return date.fromisoformat(str(valor))
    except ValueError:
        return timezone.localdate()


class PararCargaView(APIView):
    permission_classes = [IsAuthenticated]

    @require_permission(['can_manage_migracion_masiva_archivo'], app_label='Usuarios')
    def post(self, request, pk):
        carga = get_object_or_404(LoteDocumental, pk=pk)
        ejecucion = carga.ejecuciones.filter(estado_proceso='EN_PROCESO').order_by('-creado').first()
        if not ejecucion:
            return Response({'detail': 'No hay un proceso activo para esta carga.'}, status=status.HTTP_409_CONFLICT)

        ejecucion.cancelacion_solicitada = True
        ejecucion.save(update_fields=['cancelacion_solicitada', 'modificado'])

        if ejecucion.celery_task_id:
            try:
                current_app.control.revoke(ejecucion.celery_task_id)
            except Exception:
                pass

        LogProcesoDocumental.objects.create(
            lote=carga,
            nivel='WARNING',
            evento='cancelacion_solicitada',
            mensaje=f'El usuario {request.user} solicitó detener el proceso.',
        )
        return Response({
            'ok': True,
            'mensaje': 'Cancelación solicitada. El proceso se detendrá al terminar el documento actual.',
        })


class DocumentoRevisadoView(APIView):
    """Marcar un documento como revisado siempre reencola un ciclo de carga SAIA
    vía _reanudar_saia_si_idle, por lo que además de gestionar el documento exige
    el permiso de carga a SAIA (no solo de gestión)."""
    permission_classes = [IsAuthenticated]

    @require_permission(
        ['can_manage_migracion_masiva_archivo', 'can_upload_migracion_masiva_archivo_saia'],
        app_label='Usuarios',
    )
    def post(self, request, pk, doc_id):
        carga = get_object_or_404(LoteDocumental, pk=pk)
        documento = get_object_or_404(DocumentoDigitalizado, pk=doc_id, lote=carga)

        if documento.estado_proceso not in _ESTADOS_RETROCEDIBLES:
            return Response({'detail': 'El documento no requiere revisión.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            metadata = documento.metadata
        except Exception:
            metadata = None
        if metadata:
            metadata.requiere_revision = False
            metadata.confianza = 100
            metadata.save(update_fields=['requiere_revision', 'confianza', 'modificado'])

        documento.estado_proceso = 'VALIDADO'
        documento.error = ''
        documento.save(update_fields=['estado_proceso', 'error', 'modificado'])

        LogProcesoDocumental.objects.create(
            lote=carga,
            documento=documento,
            nivel='INFO',
            evento='marcado_revisado_manualmente',
            mensaje=f'Documento aprobado manualmente por {request.user}. Queda en cola para el siguiente ciclo de carga SAIA.',
            detalle={'analista': str(request.user)},
        )

        reanudo = _reanudar_saia_si_idle(carga, request.user)
        return Response({'ok': True, 'reanudo_saia': reanudo})


class DocumentoMarcarOkView(APIView):
    """Igual que DocumentoRevisadoView: marcar OK reencola un ciclo de carga SAIA
    vía _reanudar_saia_si_idle, por lo que exige también el permiso de carga a SAIA."""
    permission_classes = [IsAuthenticated]

    @require_permission(
        ['can_manage_migracion_masiva_archivo', 'can_upload_migracion_masiva_archivo_saia'],
        app_label='Usuarios',
    )
    def post(self, request, pk, doc_id):
        carga = get_object_or_404(LoteDocumental, pk=pk)
        documento = get_object_or_404(DocumentoDigitalizado, pk=doc_id, lote=carga)

        try:
            mark_document_file_ok(documento)
        except SAIALocalFileError as exc:
            documento.error = 'PENDIENTE_OK: El archivo sigue abierto en otro programa. Cierre el archivo y vuelva a intentarlo.'
            documento.save(update_fields=['error', 'modificado'])
            return Response({'ok': True, 'advertencia': str(exc)})

        if documento.estado_proceso in _ESTADOS_RETROCEDIBLES:
            documento.estado_proceso = 'VALIDADO'
        documento.error = ''
        documento.save(update_fields=['estado_proceso', 'error', 'modificado'])
        try:
            metadata = documento.metadata
            metadata.requiere_revision = False
            metadata.save(update_fields=['requiere_revision', 'modificado'])
        except Exception:
            pass

        LogProcesoDocumental.objects.create(
            lote=carga,
            documento=documento,
            nivel='INFO',
            evento='marcado_ok_reintento',
            mensaje='Archivo renombrado con OK en reintento del analista.',
        )
        reanudo = _reanudar_saia_si_idle(carga, request.user)
        return Response({'ok': True, 'reanudo_saia': reanudo})


class ConfiguracionCorreoView(APIView):
    permission_classes = [IsAuthenticated]

    @require_permission(['can_view_migracion_masiva_archivo'], app_label='Usuarios')
    def get(self, request):
        return Response({'correo_destino': _correo_destino_usuario(request.user)})

    @require_permission(['can_manage_migracion_masiva_archivo'], app_label='Usuarios')
    def post(self, request):
        correo = (request.data.get('correo_destino') or '').strip()
        if not correo:
            return Response({'detail': 'El correo no puede estar vacío.'}, status=status.HTTP_400_BAD_REQUEST)
        ConfiguracionMigracionMasivaArchivo.objects.update_or_create(
            usuario=request.user,
            defaults={'correo_destino': correo},
        )
        return Response({'ok': True, 'correo_destino': correo})


_ESTADOS_RETROCEDIBLES = {'REQUIERE_REVISION', 'ERROR_SAIA'}


def _parse_destinatarios(request):
    """Acepta 'destinatarios' como lista (JSON) o string separado por comas,
    o el nombre singular 'destinatario' por compatibilidad."""
    raw = request.data.get('destinatarios')
    if raw is None:
        raw = request.data.get('destinatario')
    if raw is None:
        return []
    items = raw if isinstance(raw, (list, tuple)) else str(raw).split(',')
    return [item.strip() for item in items if item and item.strip()]


def _correo_destino_usuario(user):
    config = ConfiguracionMigracionMasivaArchivo.objects.filter(usuario=user).first()
    if config and config.correo_destino:
        return config.correo_destino
    return getattr(user, 'email', '') or ''


def _reanudar_saia_si_idle(carga, user):
    """
    Si no hay una ejecución EN_PROCESO para este lote, encola una nueva pasada
    de carga SAIA (incluyendo ERROR_SAIA) para igualar el comportamiento de la
    app de escritorio: aprobar un documento lo deja listo para el siguiente
    ciclo automáticamente en vez de requerir que el analista pulse "procesar".
    """
    if carga.ejecuciones.filter(estado_proceso='EN_PROCESO').exists():
        return False
    procesar_lote_migracion_masiva_archivo.delay(
        carga.id,
        {
            'cargar_saia': True,
            'incluir_errores': True,
            'dry_run': False,
            'usuario': str(user),
        },
    )
    carga.estado_proceso = 'PENDIENTE'
    carga.save(update_fields=['estado_proceso', 'modificado'])
    return True


def _guardar_archivos_temporales(archivos):
    base = Path(getattr(settings, 'MIGRACION_ARCHIVOS_MEDIA_ROOT', settings.MEDIA_ROOT))
    carpeta = base / 'uploads' / uuid.uuid4().hex
    carpeta.mkdir(parents=True, exist_ok=True)
    for archivo in archivos:
        nombre = get_valid_filename(Path(archivo.name).name) or f'archivo_{uuid.uuid4().hex}'
        destino = carpeta / nombre
        with destino.open('wb') as fh:
            for chunk in archivo.chunks():
                fh.write(chunk)
    return carpeta


def _bool_request(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {'1', 'true', 'yes', 'si', 'sí', 'on'}


