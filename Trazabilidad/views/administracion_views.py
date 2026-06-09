from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from drf_yasg.utils import swagger_auto_schema

from EURO_ver_y_data.decoradores import require_permission
from Trazabilidad.models import Sede, Origen, CargaExcel
from Trazabilidad.serializers import SedeAdminSerializer, OrigenSerializer


# ── Sedes ─────────────────────────────────────────────────────────────────────

class SedesAdminView(APIView):

    @require_permission(['can_manage_sedes'], app_label='Usuarios')
    @swagger_auto_schema(operation_summary='Listar sedes con conteo de cargas', tags=['Admin'])
    def get(self, request):
        sedes = Sede.objects.all().order_by('ciudad', 'nombre')
        return Response(SedeAdminSerializer(sedes, many=True).data)

    @require_permission(['can_manage_sedes'], app_label='Usuarios')
    @swagger_auto_schema(operation_summary='Crear sede', tags=['Admin'])
    def post(self, request):
        ser = SedeAdminSerializer(data=request.data)
        if ser.is_valid():
            ser.save()
            return Response(ser.data, status=201)
        return Response(ser.errors, status=400)


class SedeAdminDetalleView(APIView):

    def _get_sede(self, pk):
        try:
            return Sede.objects.get(id=pk)
        except Sede.DoesNotExist:
            return None

    @require_permission(['can_manage_sedes'], app_label='Usuarios')
    @swagger_auto_schema(operation_summary='Actualizar sede', tags=['Admin'])
    def put(self, request, pk):
        sede = self._get_sede(pk)
        if not sede:
            return Response({'error': 'Sede no encontrada.'}, status=404)

        ser = SedeAdminSerializer(sede, data=request.data, partial=True)
        if ser.is_valid():
            ser.save()
            return Response(ser.data)
        return Response(ser.errors, status=400)

    @require_permission(['can_manage_sedes'], app_label='Usuarios')
    @swagger_auto_schema(operation_summary='Eliminar sede', tags=['Admin'])
    def delete(self, request, pk):
        sede = self._get_sede(pk)
        if not sede:
            return Response({'error': 'Sede no encontrada.'}, status=404)

        total = CargaExcel.objects.filter(sede=sede).count()
        if total > 0:
            return Response({
                'error': (
                    f'No se puede eliminar "{sede.nombre}": '
                    f'está asociada a {total} carga{"s" if total != 1 else ""} de Excel. '
                    f'Revierte esas cargas primero si deseas eliminar la sede.'
                ),
                'total_cargas': total,
                'protegido': True,
            }, status=400)

        sede.delete()
        return Response(status=204)


# ── Orígenes ──────────────────────────────────────────────────────────────────

class OrigenesAdminView(APIView):

    @swagger_auto_schema(operation_summary='Listar orígenes', tags=['Admin'])
    def get(self, request):
        origenes = Origen.objects.filter(estado=True)
        return Response(OrigenSerializer(origenes, many=True).data)

    @require_permission(['can_manage_sedes'], app_label='Usuarios')
    @swagger_auto_schema(operation_summary='Crear origen', tags=['Admin'])
    def post(self, request):
        ser = OrigenSerializer(data=request.data)
        if ser.is_valid():
            ser.save()
            return Response(ser.data, status=201)
        return Response(ser.errors, status=400)


class OrigenAdminDetalleView(APIView):

    def _get_origen(self, pk):
        try:
            return Origen.objects.get(id=pk, estado=True)
        except Origen.DoesNotExist:
            return None

    @require_permission(['can_manage_sedes'], app_label='Usuarios')
    @swagger_auto_schema(operation_summary='Actualizar origen', tags=['Admin'])
    def put(self, request, pk):
        origen = self._get_origen(pk)
        if not origen:
            return Response({'error': 'Origen no encontrado.'}, status=404)

        ser = OrigenSerializer(origen, data=request.data, partial=True)
        if ser.is_valid():
            ser.save()
            return Response(ser.data)
        return Response(ser.errors, status=400)

    @require_permission(['can_manage_sedes'], app_label='Usuarios')
    @swagger_auto_schema(operation_summary='Eliminar origen', tags=['Admin'])
    def delete(self, request, pk):
        origen = self._get_origen(pk)
        if not origen:
            return Response({'error': 'Origen no encontrado.'}, status=404)

        total = CargaExcel.objects.filter(origen_datos__iexact=origen.nombre).count()
        if total > 0:
            return Response({
                'error': (
                    f'No se puede eliminar "{origen.nombre}": '
                    f'está asociado a {total} carga{"s" if total != 1 else ""} de Excel. '
                    f'Revierte esas cargas primero si deseas eliminarlo.'
                ),
                'total_cargas': total,
                'protegido': True,
            }, status=400)

        origen.delete()
        return Response(status=204)
