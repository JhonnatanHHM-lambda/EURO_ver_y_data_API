from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework import status
from django.utils import timezone
from ..models import Contrato, EventoContrato
from ..utils.minio_client import generate_presigned_url
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

        pdf_url = None
        if contrato.pdf_carta_key:
            try:
                pdf_url = generate_presigned_url(contrato.pdf_carta_key)
            except Exception:
                pass

        docs_adicionales = []
        for doc in contrato.documentos_adicionales.all():
            try:
                url = generate_presigned_url(doc.minio_key)
                docs_adicionales.append({'nombre': doc.nombre_archivo, 'url': url})
            except Exception:
                pass

        return Response({
            'nombre_completo': contrato.nombre_completo,
            'cargo': contrato.cargo,
            'tipo_carta': contrato.tipo_carta,
            'tipo_carta_display': contrato.get_tipo_carta_display(),
            'fecha_finalizacion': str(contrato.fecha_finalizacion),
            'pdf_url': pdf_url,
            'documentos_adicionales': docs_adicionales,
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

        firma_data = request.data.get('firma_data', '')
        if not firma_data:
            return Response({'error': 'Firma requerida.'}, status=status.HTTP_400_BAD_REQUEST)

        ip = _get_client_ip(request)
        logger.info(f'Confirmación firma token={token} ip={ip}')

        contrato.firma_canvas_data = firma_data
        contrato.ip_confirmacion = ip
        contrato.token_usado = True
        contrato.estado = 'FIRMADO'
        contrato.fecha_firma = timezone.now()
        contrato.save()

        from ..tasks import generar_y_guardar_pdf_firmado
        generar_y_guardar_pdf_firmado.delay(contrato.id)

        EventoContrato.objects.create(
            contrato=contrato, tipo_evento='FIRMADO', ip=ip,
            detalle={'mensaje': 'Firma completada'},
        )

        return Response({'mensaje': 'Firma registrada correctamente.'})
