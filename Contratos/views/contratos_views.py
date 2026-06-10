import uuid
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.utils import timezone
from datetime import timedelta
from ..models import Contrato, DocumentoAdicional, EventoContrato
from ..serializers import ContratoSerializer
from ..utils.pdf_generator import generar_carta_prorroga, generar_carta_terminacion
from ..utils.minio_client import upload_to_minio


class ContratosListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = Contrato.objects.select_related('sede').all()
        try:
            asignacion = request.user.asignacion_centro
            if asignacion.rol == 'DIRECTOR':
                qs = qs.filter(sede=asignacion.sede)
        except Exception:
            pass
        return Response(ContratoSerializer(qs, many=True).data)


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


class ProrrogarContratoView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        try:
            contrato = Contrato.objects.get(pk=pk)
        except Contrato.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        duracion = request.data.get('duracion_prorroga')
        if duracion not in ['3_MESES', '6_MESES', '12_MESES']:
            return Response({'error': 'Duración inválida.'}, status=status.HTTP_400_BAD_REQUEST)

        meses = {'3_MESES': 3, '6_MESES': 6, '12_MESES': 12}[duracion]
        from dateutil.relativedelta import relativedelta
        fecha_fin_prorroga = contrato.fecha_finalizacion + relativedelta(months=meses)

        contrato.tipo_carta = 'PRORROGA'
        contrato.duracion_prorroga = duracion
        contrato.mantener_condiciones = request.data.get('mantener_condiciones', True)
        contrato.nuevo_sueldo = request.data.get('nuevo_sueldo') if not contrato.mantener_condiciones else None
        contrato.fecha_fin_prorroga = fecha_fin_prorroga
        contrato.estado = 'PENDIENTE_FIRMA_PRORROGA'
        contrato.token_usado = False
        contrato.token_firma = uuid.uuid4()
        contrato.token_expira_en = timezone.now() + timedelta(days=7)
        contrato.fecha_primer_envio = timezone.now()
        contrato.save()

        pdf_key = generar_carta_prorroga(contrato)
        contrato.pdf_carta_key = pdf_key
        contrato.save(update_fields=['pdf_carta_key'])

        from ..tasks import enviar_notificacion_empleado_task
        enviar_notificacion_empleado_task.delay(contrato.id)

        EventoContrato.objects.create(
            contrato=contrato, tipo_evento='DECISION_DIRECTOR',
            usuario=request.user,
            detalle={'accion': 'PRORROGA', 'duracion': duracion},
        )
        return Response({'mensaje': 'Prórroga generada y enviada al empleado.'})


class TerminarContratoView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        try:
            contrato = Contrato.objects.get(pk=pk)
        except Contrato.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        if not contrato.documentos_adicionales.exists():
            return Response(
                {'error': 'Adjunta al menos un documento antes de confirmar la terminación.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        contrato.tipo_carta = 'TERMINACION'
        contrato.estado = 'PENDIENTE_FIRMA_TERMINACION'
        contrato.token_usado = False
        contrato.token_firma = uuid.uuid4()
        contrato.token_expira_en = timezone.now() + timedelta(days=7)
        contrato.fecha_primer_envio = timezone.now()
        contrato.save()

        pdf_key = generar_carta_terminacion(contrato)
        contrato.pdf_carta_key = pdf_key
        contrato.save(update_fields=['pdf_carta_key'])

        from ..tasks import enviar_notificacion_empleado_task
        enviar_notificacion_empleado_task.delay(contrato.id)

        EventoContrato.objects.create(
            contrato=contrato, tipo_evento='DECISION_DIRECTOR',
            usuario=request.user,
            detalle={'accion': 'TERMINACION'},
        )
        return Response({'mensaje': 'Terminación generada y enviada al empleado.'})


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
