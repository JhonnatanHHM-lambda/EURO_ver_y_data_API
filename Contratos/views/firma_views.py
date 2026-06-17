from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework import status
from django.utils import timezone
from django.http import HttpResponse
from django.utils.decorators import method_decorator
from django.views.decorators.clickjacking import xframe_options_exempt
from ..models import Contrato, EventoContrato
from ..utils.minio_client import generate_presigned_url, download_from_minio
import logging

logger = logging.getLogger(__name__)


def _get_client_ip(request):
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


class ValidarTokenView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, token):
        try:
            contrato = Contrato.objects.get(token_firma=token)
        except Contrato.DoesNotExist:
            return Response({'error': 'Enlace inválido.'}, status=status.HTTP_404_NOT_FOUND)

        if contrato.token_usado:
            return Response({'error': 'Este enlace ya fue utilizado.'}, status=status.HTTP_410_GONE)

        if contrato.token_expira_en and timezone.now() > contrato.token_expira_en:
            return Response({'error': 'Este enlace ha expirado.'}, status=status.HTTP_410_GONE)

        ip = _get_client_ip(request)
        contrato.ip_acceso = ip
        contrato.save(update_fields=['ip_acceso'])
        logger.info(f'Acceso a firma token={token} ip={ip}')

        EventoContrato.objects.create(contrato=contrato, tipo_evento='ACCESO_FIRMA', ip=ip)

        # URL del proxy — Django sirve el PDF inline, evitando problemas de CORS/headers de MinIO
        pdf_proxy_url = None
        if contrato.pdf_carta_key:
            pdf_proxy_url = request.build_absolute_uri(f'/api/contratos/firma/{token}/pdf/')

        # Firma secuencial: el empleado debe firmar primero la NO_PRORROGA
        pdf_no_prorroga_url = None
        if not contrato.no_prorroga_firmada and contrato.pdf_no_prorroga_key:
            pdf_no_prorroga_url = request.build_absolute_uri(f'/api/contratos/firma/{token}/pdf-no-prorroga/')

        # Solo documentos adjuntos por el director para este proceso —
        # excluir cartas auto-preservadas de ciclos anteriores (subido_por=None).
        docs_adicionales = []
        for doc in contrato.documentos_adicionales.filter(subido_por__isnull=False):
            try:
                url = generate_presigned_url(doc.minio_key)
                docs_adicionales.append({'nombre': doc.nombre_archivo, 'url': url})
            except Exception:
                pass

        return Response({
            'nombre_completo':  contrato.nombre_completo,
            'tipo_documento':   contrato.tipo_documento,
            'documento_id':     contrato.documento_id,
            'cargo':            contrato.cargo,
            'tipo_carta':       contrato.tipo_carta,
            'tipo_carta_display': contrato.get_tipo_carta_display(),
            'fecha_finalizacion': str(contrato.fecha_finalizacion),
            'pdf_carta_url':    pdf_proxy_url,
            'documentos_adicionales': docs_adicionales,
            # Firma secuencial
            'firma_previa_requerida': not contrato.no_prorroga_firmada,
            'pdf_no_prorroga_url':   pdf_no_prorroga_url,
        })


class ConfirmarFirmaView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, token):
        try:
            contrato = Contrato.objects.get(token_firma=token)
        except Contrato.DoesNotExist:
            return Response({'error': 'Enlace inválido.'}, status=status.HTTP_404_NOT_FOUND)

        if contrato.token_usado:
            return Response({'error': 'Este enlace ya fue utilizado.'}, status=status.HTTP_410_GONE)

        if not contrato.no_prorroga_firmada:
            return Response(
                {
                    'error': 'Debes firmar primero la carta de no prórroga antes de firmar este documento.',
                    'firma_previa_requerida': True,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        firma_data = request.data.get('firma_data', '')
        if not firma_data:
            return Response({'error': 'Firma requerida.'}, status=status.HTTP_400_BAD_REQUEST)

        ip = _get_client_ip(request)
        logger.info(f'Confirmación firma token={token} ip={ip}')

        contrato.firma_canvas_data = firma_data
        contrato.ip_confirmacion = ip
        contrato.token_usado = True
        # NO_PRORROGA firmada = empleado reconoce el vencimiento, pero el director
        # aún debe decidir prórroga o terminación → sigue pendiente de decisión.
        # PRORROGA / TERMINACION firmadas = ciclo completo → FIRMADO.
        if contrato.tipo_carta == 'NO_PRORROGA':
            contrato.estado = 'PENDIENTE_DECISION_DIRECTOR'
        else:
            contrato.estado = 'FIRMADO'
        contrato.fecha_firma = timezone.now()
        contrato.save()

        from ..tasks import generar_y_guardar_pdf_firmado
        generar_y_guardar_pdf_firmado.delay(contrato.id)

        EventoContrato.objects.create(
            contrato=contrato, tipo_evento='FIRMADO', ip=ip,
            detalle={'mensaje': 'Firma completada'},
        )

        # Notificar a GH cuando se firma una carta de prórroga o terminación
        if contrato.tipo_carta != 'NO_PRORROGA':
            from ..views.contratos_views import _get_gh_users
            contrato_reloaded = Contrato.objects.select_related('sede').get(pk=contrato.pk)
            gh_users = _get_gh_users(contrato_reloaded.sede)
            from Usuarios.models import NotificacionAdmin
            from ..utils.notificaciones import enviar_email_gh_contrato_firmado
            for gh in gh_users:
                NotificacionAdmin.objects.create(
                    tipo='contrato_firmado_gh',
                    titulo=f'Contrato firmado: {contrato.nombre_completo}',
                    cuerpo=f'{contrato.nombre_completo} ha firmado su carta de {contrato.get_tipo_carta_display()}.',
                    contrato=contrato,
                    usuario=gh,
                )
                try:
                    enviar_email_gh_contrato_firmado(gh, contrato_reloaded)
                except Exception:
                    pass

        return Response({'mensaje': 'Firma registrada correctamente.'})


@method_decorator(xframe_options_exempt, name='dispatch')
class FirmaPDFProxyView(APIView):
    """Proxy que descarga el PDF de MinIO y lo sirve inline. Sin X-Frame-Options para permitir iframe."""
    permission_classes = [AllowAny]

    def get(self, request, token):
        try:
            contrato = Contrato.objects.get(token_firma=token)
        except Contrato.DoesNotExist:
            return Response({'error': 'Enlace inválido.'}, status=status.HTTP_404_NOT_FOUND)

        if not contrato.pdf_carta_key:
            return Response({'error': 'Sin documento.'}, status=status.HTTP_404_NOT_FOUND)

        try:
            pdf_bytes = download_from_minio(contrato.pdf_carta_key)
        except Exception as e:
            logger.error(f'Error descargando PDF para firma token={token}: {e}')
            return Response({'error': 'No se pudo cargar el documento.'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = 'inline; filename="carta.pdf"'
        response['Cache-Control'] = 'no-store'
        return response


@method_decorator(xframe_options_exempt, name='dispatch')
class FirmaNoProrrogaPDFProxyView(APIView):
    """Sirve inline el PDF de la NO_PRORROGA original en el flujo de firma secuencial."""
    permission_classes = [AllowAny]

    def get(self, request, token):
        try:
            contrato = Contrato.objects.get(token_firma=token)
        except Contrato.DoesNotExist:
            return Response({'error': 'Enlace inválido.'}, status=status.HTTP_404_NOT_FOUND)

        if not contrato.pdf_no_prorroga_key:
            return Response({'error': 'Sin documento.'}, status=status.HTTP_404_NOT_FOUND)

        try:
            pdf_bytes = download_from_minio(contrato.pdf_no_prorroga_key)
        except Exception as e:
            logger.error(f'Error descargando PDF no-prorroga token={token}: {e}')
            return Response({'error': 'No se pudo cargar el documento.'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = 'inline; filename="carta_no_prorroga.pdf"'
        response['Cache-Control'] = 'no-store'
        return response


class ConfirmarFirmaNoProrrogaView(APIView):
    """Empleado firma la NO_PRORROGA previa en el flujo de firma secuencial."""
    permission_classes = [AllowAny]

    def post(self, request, token):
        try:
            contrato = Contrato.objects.get(token_firma=token)
        except Contrato.DoesNotExist:
            return Response({'error': 'Enlace inválido.'}, status=status.HTTP_404_NOT_FOUND)

        if contrato.token_usado:
            return Response({'error': 'Este enlace ya fue utilizado.'}, status=status.HTTP_410_GONE)

        if contrato.token_expira_en and timezone.now() > contrato.token_expira_en:
            return Response({'error': 'Este enlace ha expirado.'}, status=status.HTTP_410_GONE)

        if contrato.no_prorroga_firmada:
            return Response({'error': 'La carta de no prórroga ya fue firmada.'}, status=status.HTTP_400_BAD_REQUEST)

        firma_data = request.data.get('firma_data', '')
        if not firma_data:
            return Response({'error': 'Firma requerida.'}, status=status.HTTP_400_BAD_REQUEST)

        ip = _get_client_ip(request)
        logger.info(f'Firma NO_PRORROGA secuencial token={token} ip={ip}')

        # Generar PDF firmado de la NO_PRORROGA y guardarlo como documento adicional
        try:
            from ..utils.pdf_generator import generar_pdf_no_prorroga_firmada
            from ..models import DocumentoAdicional
            pdf_key = generar_pdf_no_prorroga_firmada(contrato, firma_data)
            DocumentoAdicional.objects.create(
                contrato=contrato,
                nombre_archivo='Carta No Prórroga firmada.pdf',
                minio_key=pdf_key,
                subido_por=None,
            )
        except Exception as e:
            logger.error(f'Error generando PDF no_prorroga firmada token={token}: {e}')

        contrato.no_prorroga_firmada = True
        contrato.save(update_fields=['no_prorroga_firmada'])

        EventoContrato.objects.create(
            contrato=contrato, tipo_evento='FIRMADO', ip=ip,
            detalle={'tipo': 'NO_PRORROGA_SECUENCIAL', 'mensaje': 'Carta no prórroga firmada en flujo secuencial'},
        )

        return Response({'mensaje': 'Carta de no prórroga firmada. Ahora puedes firmar el documento principal.'})
