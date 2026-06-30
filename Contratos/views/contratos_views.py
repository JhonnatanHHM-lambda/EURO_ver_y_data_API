import uuid
import logging
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from rest_framework import status
from django.db.models import Q
from django.utils import timezone
from datetime import timedelta
from ..models import Contrato, DocumentoAdicional, EventoContrato
from ..serializers import ContratoSerializer, ContratoListSerializer
from ..utils.pdf_generator import generar_carta_prorroga, generar_carta_terminacion, generar_carta_no_prorroga
from ..utils.minio_client import upload_to_minio, delete_from_minio

logger = logging.getLogger(__name__)

class ContratoPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


def _get_gh_users(sede):
    """Retorna los usuarios con rol GH asignados a la sede dada."""
    if not sede:
        return []
    from ..models import AsignacionCentro
    return [
        a.usuario for a in
        AsignacionCentro.objects.filter(sede=sede, rol='GH', activo=True).select_related('usuario')
    ]


def _get_director(sede):
    """Retorna el primer director asignado a la sede dada."""
    if not sede:
        return None
    from ..models import AsignacionCentro
    asig = AsignacionCentro.objects.filter(
        sede=sede, rol='DIRECTOR', activo=True
    ).select_related('usuario').first()
    return asig.usuario if asig else None


class ContratosListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from ..models import AsignacionCentro
        qs = Contrato.objects.select_related('sede').order_by('fecha_finalizacion', 'id')
        sedes_asignadas = AsignacionCentro.objects.filter(
            usuario=request.user, activo=True
        ).values_list('sede', flat=True)
        if sedes_asignadas.exists():
            qs = qs.filter(sede__in=sedes_asignadas)
        if request.query_params.get('activos') == 'true':
            qs = qs.exclude(estado__in=['FIRMADO', 'CANCELADO'])
        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(
                Q(nombre_completo__icontains=search) |
                Q(documento_id__icontains=search) |
                Q(cargo__icontains=search)
            )
        estado = request.query_params.get('estado', '').strip()
        if estado:
            qs = qs.filter(estado=estado)
        paginator = ContratoPagination()
        page_qs = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response(ContratoListSerializer(page_qs, many=True).data)


class ContratoDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        try:
            contrato = Contrato.objects.select_related('sede').prefetch_related(
                'documentos_adicionales', 'eventos'
            ).get(pk=pk)
        except Contrato.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(ContratoSerializer(contrato).data)


class ActualizarContactoView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        try:
            contrato = Contrato.objects.get(pk=pk)
        except Contrato.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        update_fields = []
        if 'email' in request.data:
            contrato.email = (request.data['email'] or '').strip()
            update_fields.append('email')
        if 'celular' in request.data:
            contrato.celular = (request.data['celular'] or '').strip()
            update_fields.append('celular')

        if not update_fields:
            return Response({'error': 'Nada que actualizar.'}, status=status.HTTP_400_BAD_REQUEST)

        contrato.save(update_fields=update_fields)
        return Response({'email': contrato.email, 'celular': contrato.celular})


class ReenviarNotificacionView(APIView):
    permission_classes = [IsAuthenticated]

    _TIPO_A_ESTADO_PENDIENTE = {
        'NO_PRORROGA': 'PENDIENTE_FIRMA_NO_PRORROGA',
        'PRORROGA':    'PENDIENTE_FIRMA_PRORROGA',
        'TERMINACION': 'PENDIENTE_FIRMA_TERMINACION',
    }

    def post(self, request, pk):
        # Siempre recarga desde BD para tener email/celular actualizados
        try:
            contrato = Contrato.objects.get(pk=pk)
        except Contrato.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        if not contrato.email and not contrato.celular:
            return Response(
                {'error': 'El empleado no tiene email ni celular registrado.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        update_fields = ['token_firma', 'token_usado', 'token_expira_en']

        # Si el proceso estaba bloqueado, resetear a PENDIENTE_FIRMA_* para que el link funcione
        if contrato.estado in ('SIN_CANAL_CONTACTO', 'ERROR_NOTIFICACION'):
            nuevo_estado = self._TIPO_A_ESTADO_PENDIENTE.get(contrato.tipo_carta)
            if nuevo_estado:
                contrato.estado = nuevo_estado
                update_fields.append('estado')

        contrato.token_firma = uuid.uuid4()
        contrato.token_usado = False
        contrato.token_expira_en = timezone.now() + timedelta(days=7)
        contrato.save(update_fields=update_fields)

        from ..tasks import enviar_notificacion_empleado_task
        enviar_notificacion_empleado_task.delay(contrato.id)

        return Response({'mensaje': 'Notificación reenviada al empleado.'})


_TIPO_LABELS = {'NO_PRORROGA': 'No Prorroga', 'PRORROGA': 'Prorroga', 'TERMINACION': 'Terminacion'}


def _preservar_carta_firmada(contrato):
    """Guarda la carta del ciclo actual como DocumentoAdicional antes de sobreescribir.
    Prioriza pdf_firmado_key (con firma); si no existe, usa pdf_carta_key como respaldo."""
    key = contrato.pdf_firmado_key or contrato.pdf_carta_key
    if not key:
        return
    ya_existe = DocumentoAdicional.objects.filter(
        contrato=contrato, minio_key=key
    ).exists()
    if ya_existe:
        return
    tipo_label = _TIPO_LABELS.get(contrato.tipo_carta, contrato.tipo_carta)
    sufijo = 'firmada' if contrato.pdf_firmado_key else 'carta original'
    DocumentoAdicional.objects.create(
        contrato=contrato,
        nombre_archivo=f'Carta {tipo_label} {sufijo}.pdf',
        minio_key=key,
        subido_por=None,
    )


class ProrrogarContratoView(APIView):
    """GH decide prorrogar — registra la decisión y pasa a definir condiciones."""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        try:
            contrato = Contrato.objects.select_related('sede').get(pk=pk)
        except Contrato.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        # firma_secuencial: GH decide sobre un contrato NO_PRORROGA que el empleado
        # aún no ha firmado (pdf_firmado_key vacío).
        firma_secuencial = (
            contrato.tipo_carta == 'NO_PRORROGA' and
            not contrato.pdf_firmado_key
        )
        if firma_secuencial:
            if contrato.pdf_carta_key:
                contrato.pdf_no_prorroga_key = contrato.pdf_carta_key
            contrato.no_prorroga_firmada = False
        else:
            # Solo preservar si el empleado ya firmó algo — ciclo cerrado
            _preservar_carta_firmada(contrato)

        contrato.tipo_carta = 'PRORROGA'
        contrato.estado = 'PENDIENTE_CONDICIONES_GH'
        contrato.pdf_firmado_key = ''
        if firma_secuencial:
            contrato.pdf_carta_key = ''  # la carta de prórroga aún no se ha generado
        contrato.save()

        EventoContrato.objects.create(
            contrato=contrato, tipo_evento='DECISION_DIRECTOR',
            usuario=request.user,
            detalle={'accion': 'PRORROGA'},
        )

        return Response({'mensaje': 'Decisión registrada. Define las condiciones para notificar al empleado.'})


class TerminarContratoView(APIView):
    """GH decide terminar — registra la decisión y pasa a definir condiciones."""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        try:
            contrato = Contrato.objects.select_related('sede').get(pk=pk)
        except Contrato.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        # firma_secuencial: igual que en ProrrogarContratoView — detectar por tipo_carta y
        # ausencia de firma, no por estado.
        firma_secuencial = (
            contrato.tipo_carta == 'NO_PRORROGA' and
            not contrato.pdf_firmado_key
        )
        if firma_secuencial:
            if contrato.pdf_carta_key:
                contrato.pdf_no_prorroga_key = contrato.pdf_carta_key
            contrato.no_prorroga_firmada = False
        else:
            _preservar_carta_firmada(contrato)

        contrato.tipo_carta = 'TERMINACION'
        contrato.estado = 'PENDIENTE_CONDICIONES_GH'
        contrato.pdf_firmado_key = ''
        if firma_secuencial:
            contrato.pdf_carta_key = ''  # la carta de terminación aún no se ha generado
        contrato.save()

        EventoContrato.objects.create(
            contrato=contrato, tipo_evento='DECISION_DIRECTOR',
            usuario=request.user,
            detalle={'accion': 'TERMINACION'},
        )

        return Response({'mensaje': 'Decisión registrada. Define las condiciones para notificar al empleado.'})


class CondicionesGHView(APIView):
    """GH define las condiciones de prórroga (duración/sueldo) o sube documentos de terminación."""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        try:
            contrato = Contrato.objects.select_related('sede').get(pk=pk)
        except Contrato.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        if contrato.estado != 'PENDIENTE_CONDICIONES_GH':
            return Response(
                {'error': 'El contrato no está en estado de espera de condiciones GH.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if contrato.tipo_carta == 'PRORROGA':
            try:
                meses = int(request.data.get('meses_prorroga', 0))
            except (TypeError, ValueError):
                meses = 0
            if not 1 <= meses <= 12:
                return Response({'error': 'Duración inválida. Elige entre 1 y 12 meses.'}, status=status.HTTP_400_BAD_REQUEST)
            from dateutil.relativedelta import relativedelta
            contrato.duracion_prorroga = '1_MES' if meses == 1 else f'{meses}_MESES'
            contrato.mantener_condiciones = True
            contrato.nuevo_sueldo = None
            contrato.fecha_fin_prorroga = contrato.fecha_finalizacion + relativedelta(months=meses)

        elif contrato.tipo_carta == 'TERMINACION':
            archivos = request.FILES.getlist('documentos')
            if not archivos:
                return Response(
                    {'error': 'Adjunta al menos un documento antes de confirmar la terminación.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            for archivo in archivos:
                key = f'contratos/{contrato.documento_id}/adicional_{uuid.uuid4()}_{archivo.name}'
                upload_to_minio(archivo, key, content_type=archivo.content_type)
                DocumentoAdicional.objects.create(
                    contrato=contrato,
                    nombre_archivo=archivo.name,
                    minio_key=key,
                    subido_por=request.user,
                )
            # Generar carta de terminación inmediatamente para que sea visible en el drawer
            try:
                pdf_key = generar_carta_terminacion(contrato)
                contrato.pdf_carta_key = pdf_key
            except Exception as e:
                logger.warning(f'No se pudo pre-generar carta terminación contrato {contrato.id}: {e}')

        contrato.estado = 'PENDIENTE_NOTIFICACION_EMPLEADO'
        contrato.save()

        EventoContrato.objects.create(
            contrato=contrato, tipo_evento='CONDICIONES_GH',
            usuario=request.user,
            detalle={'tipo_carta': contrato.tipo_carta},
        )

        director = _get_director(contrato.sede)
        if director:
            from Usuarios.models import NotificacionAdmin
            from ..utils.notificaciones import enviar_email_director_condiciones_listas
            cuerpo_notif = (
                'GH ha definido las condiciones de prórroga. GH notificará directamente al empleado.'
                if contrato.tipo_carta == 'PRORROGA'
                else 'GH ha definido las condiciones. Ya puedes notificar al empleado.'
            )
            NotificacionAdmin.objects.create(
                tipo='condiciones_gh_listas',
                titulo=f'Condiciones listas — {contrato.nombre_completo}',
                cuerpo=cuerpo_notif,
                contrato=contrato,
                usuario=director,
            )
            try:
                enviar_email_director_condiciones_listas(director, contrato)
            except Exception:
                pass

        return Response({'mensaje': 'Condiciones registradas. Se notificó al director.'})


class NotificarEmpleadoView(APIView):
    """Director dispara la notificación al empleado — genera la carta PDF y la envía."""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        try:
            contrato = Contrato.objects.get(pk=pk)
        except Contrato.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        if contrato.estado != 'PENDIENTE_NOTIFICACION_EMPLEADO':
            return Response(
                {'error': 'El contrato no está listo para notificar al empleado.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        contrato.token_usado = False
        contrato.token_firma = uuid.uuid4()
        contrato.token_expira_en = timezone.now() + timedelta(days=7)
        contrato.fecha_primer_envio = timezone.now()
        contrato.pdf_firmado_key = ''

        if contrato.tipo_carta == 'PRORROGA':
            contrato.estado = 'PENDIENTE_FIRMA_PRORROGA'
            contrato.save()
            pdf_key = generar_carta_prorroga(contrato)
        else:
            contrato.estado = 'PENDIENTE_FIRMA_TERMINACION'
            contrato.save()
            pdf_key = generar_carta_terminacion(contrato)

        contrato.pdf_carta_key = pdf_key
        contrato.save(update_fields=['pdf_carta_key'])

        from ..tasks import enviar_notificacion_empleado_task
        enviar_notificacion_empleado_task.delay(contrato.id)

        EventoContrato.objects.create(
            contrato=contrato, tipo_evento='NOTIFICACION_EMPLEADO',
            usuario=request.user,
            detalle={'tipo_carta': contrato.tipo_carta},
        )

        return Response({'mensaje': 'Carta generada y enviada al empleado.'})


class SubirDocumentoAdicionalView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        try:
            contrato = Contrato.objects.get(pk=pk)
        except Contrato.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        archivo = request.FILES.get('archivo')
        if not archivo:
            return Response({'error': 'Archivo requerido.'}, status=status.HTTP_400_BAD_REQUEST)

        key = f'contratos/{contrato.documento_id}/adicional_{uuid.uuid4()}_{archivo.name}'
        upload_to_minio(archivo, key, content_type=archivo.content_type)

        doc = DocumentoAdicional.objects.create(
            contrato=contrato,
            nombre_archivo=archivo.name,
            minio_key=key,
            subido_por=request.user,
        )
        return Response({'mensaje': 'Documento subido.', 'id': doc.id, 'nombre': doc.nombre_archivo})


class CrearContratoDemoView(APIView):
    """Crea un contrato ficticio para demostrar el flujo completo de vencimientos.
    Solo disponible para superusuarios. El link de firma del empleado llega al
    correo del usuario que crea el demo."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        puede = request.user.is_superuser or request.user.has_perm('Usuarios.can_manage_users')
        if not puede:
            return Response(
                {'error': 'Solo administradores pueden crear contratos demo.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        from Trazabilidad.models import Sede
        import uuid as _uuid

        sede_id = request.data.get('sede_id')
        sede = None
        if sede_id:
            try:
                sede = Sede.objects.get(id=sede_id)
            except Sede.DoesNotExist:
                return Response({'error': 'Sede no encontrada.'}, status=status.HTTP_400_BAD_REQUEST)
        else:
            sede = Sede.objects.filter(estado=True).first()

        hoy = timezone.now().date()
        fecha_fin = hoy + timedelta(days=2)
        sufijo = _uuid.uuid4().hex[:6].upper()

        nombre_completo = (request.data.get('nombre_completo') or f'Demo Empleado {sufijo}').strip()
        _doc_raw        = (request.data.get('documento_id')    or sufijo).strip()
        # Forzar prefijo DEMO- para identificar y limpiar fácilmente
        documento_id    = _doc_raw if _doc_raw.upper().startswith('DEMO') else f'DEMO-{_doc_raw}'
        cargo           = (request.data.get('cargo')           or 'Cargo de Demostración').strip()
        email_emp       = (request.data.get('email')           or getattr(request.user, 'correo', '') or '').strip()
        celular_emp     = (request.data.get('celular')         or '').strip()

        contrato = Contrato.objects.create(
            tipo_documento='CC',
            documento_id=documento_id,
            nombre_completo=nombre_completo,
            cargo=cargo,
            fecha_inicio_contrato=hoy - timedelta(days=363),
            fecha_finalizacion=fecha_fin,
            email=email_emp,
            celular=celular_emp,
            tipo_carta='NO_PRORROGA',
            estado='PENDIENTE_FIRMA_NO_PRORROGA',
            sede=sede,
            token_expira_en=timezone.now() + timedelta(days=7),
            fecha_primer_envio=timezone.now(),
        )

        try:
            pdf_key = generar_carta_no_prorroga(contrato)
            contrato.pdf_carta_key = pdf_key
            contrato.save(update_fields=['pdf_carta_key'])
        except Exception as e:
            logger.warning(f'Demo: no se pudo generar carta para contrato {contrato.id}: {e}')

        # Paso 1 — notificar al empleado (igual que revisar_contratos_60_dias)
        EventoContrato.objects.create(
            contrato=contrato, tipo_evento='GENERADO',
            detalle={'demo': True},
        )
        from ..tasks import enviar_notificacion_empleado_task
        try:
            enviar_notificacion_empleado_task.delay(contrato.id)
        except Exception as e:
            logger.warning(f'Demo: no se pudo encolar notificación empleado: {e}')

        # Paso 2 — escalar a GH (flujo vigente: GH toma la decisión)
        contrato.estado = 'PENDIENTE_DECISION_GH'
        contrato.save(update_fields=['estado'])

        EventoContrato.objects.create(
            contrato=contrato, tipo_evento='ESCALADO',
            detalle={'motivo': 'revision_proximos_vencer', 'dias': 2, 'demo': True},
        )

        ghs = _get_gh_users(sede) if sede else []
        for gh in ghs:
            from ..utils.notificaciones import enviar_alerta_gh
            from Usuarios.models import NotificacionAdmin
            try:
                enviar_alerta_gh(gh, contrato, 2)
            except Exception as e:
                logger.warning(f'Demo: no se pudo notificar GH: {e}')
            NotificacionAdmin.objects.create(
                tipo='alerta_contrato',
                titulo=f'[DEMO] Contrato próximo a vencer — {contrato.nombre_completo}',
                cuerpo=(
                    f'Contrato de demostración. {contrato.nombre_completo} '
                    f'(CC {contrato.documento_id}) vence el '
                    f'{contrato.fecha_finalizacion.strftime("%d/%m/%Y")}. '
                    f'Quedan 2 día(s). Ingresa al panel y toma una decisión.'
                ),
                usuario=gh,
                contrato=contrato,
            )

        destino = email_emp or '(sin correo)'
        return Response({
            'id': contrato.id,
            'nombre': contrato.nombre_completo,
            'fecha_fin': str(fecha_fin),
            'mensaje': (
                f'Contrato demo creado — {contrato.nombre_completo} '
                f'vence el {fecha_fin.strftime("%d/%m/%Y")}. '
                f'Link de firma enviado a {destino}.'
            ),
        })

    def delete(self, request):
        """Elimina todos los contratos demo (documento_id empieza con 'DEMO')
        junto con sus archivos en MinIO."""
        puede = request.user.is_superuser or request.user.has_perm('Usuarios.can_manage_users')
        if not puede:
            return Response(
                {'error': 'Solo administradores pueden eliminar contratos demo.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        demos = Contrato.objects.filter(documento_id__istartswith='DEMO')
        total = demos.count()

        if total == 0:
            return Response({'mensaje': 'No hay contratos demo para eliminar.', 'eliminados': 0})

        # Eliminar notificaciones antes del delete (FK usa SET_NULL, no CASCADE)
        from Usuarios.models import NotificacionAdmin
        NotificacionAdmin.objects.filter(contrato__in=demos).delete()

        keys_a_borrar = []
        for c in demos:
            for key in [c.pdf_carta_key, c.pdf_firmado_key, c.pdf_no_prorroga_key]:
                if key:
                    keys_a_borrar.append(key)
            for doc in c.documentos_adicionales.all():
                if doc.minio_key:
                    keys_a_borrar.append(doc.minio_key)

        demos.delete()

        errores = 0
        for key in keys_a_borrar:
            try:
                delete_from_minio(key)
            except Exception as e:
                logger.warning(f'Demo cleanup: no se pudo borrar MinIO key {key}: {e}')
                errores += 1

        msg = f'{total} contrato(s) demo eliminado(s).'
        if errores:
            msg += f' {errores} archivo(s) de MinIO no pudieron borrarse (ver logs).'
        return Response({'mensaje': msg, 'eliminados': total})
