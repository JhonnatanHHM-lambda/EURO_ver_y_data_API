from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from drf_yasg.utils import swagger_auto_schema

from EURO_ver_y_data.decoradores import require_permission
from Trazabilidad.models import CargaExcel, EmpleadoTrazabilidad
from Trazabilidad.serializers import CargaExcelSerializer


class HistorialCargasView(APIView):

    @require_permission(['can_manage_cargas'], app_label='Usuarios')
    @swagger_auto_schema(operation_summary='Historial de cargas Excel', tags=['BD Centralizada'])
    def get(self, request):
        cargas = (
            CargaExcel.objects
            .select_related('sede', 'cargado_por')
            .order_by('-creado')[:100]
        )
        data = []
        for c in cargas:
            item = CargaExcelSerializer(c).data
            item['puede_revertir'] = True
            data.append(item)
        return Response(data)


class RevertirCargaView(APIView):

    @require_permission(['can_manage_cargas'], app_label='Usuarios')
    @swagger_auto_schema(
        operation_summary='Revertir carga — elimina todos sus registros',
        tags=['BD Centralizada']
    )
    def delete(self, request, pk):
        try:
            carga = CargaExcel.objects.get(pk=pk)
        except CargaExcel.DoesNotExist:
            return Response({'error': 'Carga no encontrada.'}, status=404)

        # Eliminar todos los empleados vinculados a esta carga
        eliminados, _ = EmpleadoTrazabilidad.objects.filter(carga=carga).delete()

        # Marcar la carga como revertida (no la borramos para mantener el historial)
        carga.estado = False
        carga.save(update_fields=['estado'])

        return Response({
            'mensaje': f'Carga revertida. Se eliminaron {eliminados} registros.',
            'eliminados': eliminados,
            'carga_id': pk,
        })
