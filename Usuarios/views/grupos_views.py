from django.contrib.auth.models import Group, Permission
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from drf_yasg.utils import swagger_auto_schema

from EURO_ver_y_data.decoradores import require_permission
from Usuarios.serializers import (
    GrupoListSerializer, GrupoCreateSerializer,
    GrupoUpdateSerializer, PermisosSerializer,
)


class GruposCRUDView(APIView):

    @require_permission(['can_manage_roles'], app_label='Usuarios')
    @swagger_auto_schema(operation_summary='Listar roles/grupos', tags=['Roles'])
    def get(self, request, pk=None):
        if pk:
            obj = get_object_or_404(Group, pk=pk)
            return Response(GrupoListSerializer(obj).data)
        grupos = Group.objects.prefetch_related('permissions').all()
        return Response(GrupoListSerializer(grupos, many=True).data)

    @require_permission(['can_manage_roles'], app_label='Usuarios')
    @swagger_auto_schema(
        operation_summary='Crear rol/grupo',
        request_body=GrupoCreateSerializer,
        tags=['Roles'],
    )
    def post(self, request):
        serializer = GrupoCreateSerializer(data=request.data)
        if serializer.is_valid():
            grupo = serializer.save()
            return Response(GrupoListSerializer(grupo).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @require_permission(['can_manage_roles'], app_label='Usuarios')
    @swagger_auto_schema(
        operation_summary='Actualizar rol/grupo',
        request_body=GrupoUpdateSerializer,
        tags=['Roles'],
    )
    def put(self, request, pk):
        grupo = get_object_or_404(Group, pk=pk)
        serializer = GrupoUpdateSerializer(grupo, data=request.data, partial=True)
        if serializer.is_valid():
            actualizado = serializer.save()
            return Response(GrupoListSerializer(actualizado).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @require_permission(['can_manage_roles'], app_label='Usuarios')
    @swagger_auto_schema(operation_summary='Eliminar rol/grupo', tags=['Roles'])
    def delete(self, request, pk):
        grupo = get_object_or_404(Group, pk=pk)
        grupo.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class PermisosListView(APIView):

    PERMISOS_PLATAFORMA = [
        'can_manage_users',
        'can_manage_roles',
        'can_view_dashboard',
        'can_upload_excel',
        'can_view_trazabilidad',
        'can_manage_sedes',
        'can_manage_cargas',
    ]

    @require_permission(['can_manage_roles'], app_label='Usuarios')
    @swagger_auto_schema(
        operation_summary='Listar permisos disponibles de la plataforma',
        tags=['Roles'],
    )
    def get(self, request):
        permisos = Permission.objects.select_related('content_type').filter(
            codename__in=self.PERMISOS_PLATAFORMA
        ).order_by('codename')
        return Response(PermisosSerializer(permisos, many=True).data)
