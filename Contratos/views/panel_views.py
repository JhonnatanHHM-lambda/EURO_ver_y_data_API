from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from ..models import Contrato, AsignacionCentro
from ..serializers import AsignacionCentroSerializer
from datetime import date


class EscanearSiesaView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from ..tasks import revisar_contratos_60_dias
        try:
            antes = Contrato.objects.count()
            revisar_contratos_60_dias()
            despues = Contrato.objects.count()
            nuevos = despues - antes
            return Response({
                'mensaje': f'Escaneo completado. {nuevos} contrato(s) nuevo(s) generado(s).',
                'nuevos': nuevos,
                'total': despues,
            })
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class PanelResumenView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = Contrato.objects.all()
        try:
            asignacion = request.user.asignacion_centro
            if asignacion.rol == 'DIRECTOR':
                qs = qs.filter(sede=asignacion.sede)
        except Exception:
            pass

        return Response({
            'total': qs.count(),
            'pendiente_firma': qs.filter(estado__startswith='PENDIENTE_FIRMA').count(),
            'pendiente_decision': qs.filter(estado='PENDIENTE_DECISION_DIRECTOR').count(),
            'firmados': qs.filter(estado='FIRMADO').count(),
            'sin_canal': qs.filter(estado='SIN_CANAL_CONTACTO').count(),
        })


class AsignacionesSedView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = AsignacionCentro.objects.select_related('usuario', 'sede').filter(activo=True)
        return Response(AsignacionCentroSerializer(qs, many=True).data)

    def post(self, request):
        serializer = AsignacionCentroSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk=None):
        try:
            asignacion = AsignacionCentro.objects.get(pk=pk)
        except AsignacionCentro.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        asignacion.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
