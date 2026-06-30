from django.shortcuts import get_object_or_404
from django.db.models import Q
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

from EURO_ver_y_data.decoradores import require_permission
from Usuarios.models import Usuario
from Usuarios.serializers import (
    UsuarioListSerializer, UsuarioCreateSerializer,
    UsuarioUpdateSerializer, CambiarPasswordSerializer,
)


def _tiene_relaciones_criticas(usuario):
    """
    Retorna True si el usuario tiene registros de auditoría que no deben
    perderse (eventos de contrato, firmas, autorizaciones).
    En ese caso solo se permite desactivar, no eliminar permanentemente.
    """
    from Contratos.models import EventoContrato, RegistroFirmaEmpleador, FirmaProvisional
    return (
        EventoContrato.objects.filter(usuario=usuario).exists()
        or RegistroFirmaEmpleador.objects.filter(usuario_empleador=usuario).exists()
        or FirmaProvisional.objects.filter(autorizado_por=usuario).exists()
    )


class UsuariosCRUDView(APIView):

    @require_permission(['can_manage_users'], app_label='Usuarios')
    @swagger_auto_schema(
        operation_summary='Listar usuarios',
        manual_parameters=[
            openapi.Parameter('search', openapi.IN_QUERY, type=openapi.TYPE_STRING),
            openapi.Parameter('rol', openapi.IN_QUERY, type=openapi.TYPE_STRING),
        ],
        tags=['Usuarios'],
    )
    def get(self, request, pk=None):
        if pk:
            obj = get_object_or_404(Usuario, pk=pk)
            return Response(UsuarioListSerializer(obj).data)

        include_inactivos = request.query_params.get('include_inactivos') == 'true'
        if include_inactivos:
            # Retorna solo los archivados (soft-deleted) para el panel de gestión
            queryset = Usuario.objects.filter(estado=False).prefetch_related('groups__permissions')
        else:
            queryset = Usuario.objects.filter(estado=True).prefetch_related('groups__permissions')
        search = request.query_params.get('search')
        rol = request.query_params.get('rol')

        if search:
            queryset = queryset.filter(
                Q(nombres__icontains=search) |
                Q(apellidos__icontains=search) |
                Q(correo__icontains=search) |
                Q(cedula__icontains=search)
            )
        if rol:
            queryset = queryset.filter(groups__name=rol)

        return Response(UsuarioListSerializer(queryset, many=True).data)

    @require_permission(['can_manage_users'], app_label='Usuarios')
    @swagger_auto_schema(
        operation_summary='Crear usuario',
        request_body=UsuarioCreateSerializer,
        tags=['Usuarios'],
    )
    def post(self, request):
        serializer = UsuarioCreateSerializer(data=request.data)
        if serializer.is_valid():
            usuario = serializer.save()
            return Response(UsuarioListSerializer(usuario).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @require_permission(['can_manage_users'], app_label='Usuarios')
    @swagger_auto_schema(
        operation_summary='Actualizar usuario',
        request_body=UsuarioUpdateSerializer,
        tags=['Usuarios'],
    )
    def put(self, request, pk):
        obj = get_object_or_404(Usuario, pk=pk)
        serializer = UsuarioUpdateSerializer(obj, data=request.data, partial=True)
        if serializer.is_valid():
            actualizado = serializer.save()
            return Response(UsuarioListSerializer(actualizado).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @require_permission(['can_manage_users'], app_label='Usuarios')
    @swagger_auto_schema(
        operation_summary='Actualizar parcialmente usuario',
        request_body=UsuarioUpdateSerializer,
        tags=['Usuarios'],
    )
    def patch(self, request, pk):
        obj = get_object_or_404(Usuario, pk=pk)
        serializer = UsuarioUpdateSerializer(obj, data=request.data, partial=True)
        if serializer.is_valid():
            actualizado = serializer.save()
            return Response(UsuarioListSerializer(actualizado).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @require_permission(['can_manage_users'], app_label='Usuarios')
    @swagger_auto_schema(operation_summary='Eliminar usuario permanentemente', tags=['Usuarios'])
    def delete(self, request, pk):
        try:
            obj = Usuario.objects.get(pk=pk)
        except Usuario.DoesNotExist:
            return Response({'error': 'Usuario no encontrado.'}, status=404)

        if obj == request.user:
            return Response({'error': 'No puedes eliminarte a ti mismo.'}, status=400)

        # Usuario ya archivado (soft-delete previo): purgar directamente
        if not obj.estado:
            obj.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)

        # Usuario activo: verificar relaciones críticas de auditoría
        if _tiene_relaciones_criticas(obj):
            return Response({
                'error': (
                    f'"{obj.nombres} {obj.apellidos}" tiene registros de auditoría asociados '
                    '(eventos de contrato, firmas o autorizaciones). '
                    'No es posible eliminarlo para preservar la trazabilidad. '
                    'Puedes desactivarlo para que no pueda iniciar sesión.'
                ),
                'solo_desactivar': True,
            }, status=status.HTTP_409_CONFLICT)

        # Sin relaciones críticas: eliminar permanentemente
        obj.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class CambiarPasswordView(APIView):

    @swagger_auto_schema(
        operation_summary='Cambiar contraseña del usuario autenticado',
        request_body=CambiarPasswordSerializer,
        tags=['Usuarios'],
    )
    def post(self, request):
        serializer = CambiarPasswordSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            request.user.set_password(serializer.validated_data['password_nuevo'])
            request.user.save(update_fields=['password'])
            return Response({'mensaje': 'Contraseña actualizada correctamente.'})
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
