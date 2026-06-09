from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from drf_yasg.utils import swagger_auto_schema

from EURO_ver_y_data.decoradores import require_permission
from Trazabilidad.models import Sede
from Trazabilidad.serializers import SedeSerializer


class SedesView(APIView):

    @swagger_auto_schema(operation_summary='Listar sedes activas', tags=['Sedes'])
    def get(self, request):
        sedes = Sede.objects.filter(estado=True).order_by('ciudad', 'nombre')
        return Response(SedeSerializer(sedes, many=True).data)

    @require_permission(['can_manage_sedes'], app_label='Usuarios')
    @swagger_auto_schema(operation_summary='Crear sede', request_body=SedeSerializer, tags=['Sedes'])
    def post(self, request):
        serializer = SedeSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
