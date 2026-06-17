from django.contrib.auth import authenticate
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

from EURO_ver_y_data.decoradores import require_permission
from Usuarios.models import Usuario, OTPVerificacion, SolicitudRecuperacionPassword, NotificacionAdmin
from Usuarios.serializers import UsuarioListSerializer
from Notificaciones.tasks import enviar_otp_email


class LoginIniciarView(APIView):
    """Paso 1: correo + contraseña → valida credenciales → envía OTP."""
    authentication_classes = []
    permission_classes = [AllowAny]

    @swagger_auto_schema(
        operation_summary='Iniciar login — valida credenciales y envía OTP',
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['correo', 'password'],
            properties={
                'correo':   openapi.Schema(type=openapi.TYPE_STRING, format='email'),
                'password': openapi.Schema(type=openapi.TYPE_STRING),
            },
        ),
        tags=['Autenticación'],
    )
    def post(self, request):
        correo   = request.data.get('correo',   '').strip().lower()
        password = request.data.get('password', '').strip()

        if not correo or not password:
            return Response({'error': 'Correo y contraseña son obligatorios.'}, status=400)

        # Verificar que el usuario existe y está activo
        try:
            usuario = Usuario.objects.get(correo=correo, is_active=True, estado=True)
        except Usuario.DoesNotExist:
            return Response({'error': 'No existe una cuenta activa con ese correo.'}, status=404)

        # Validar contraseña
        if not usuario.check_password(password):
            return Response({'error': 'Contraseña incorrecta.'}, status=401)

        otp = OTPVerificacion.generar(usuario)
        enviar_otp_email.delay(usuario.id, otp.codigo)

        return Response({
            'mensaje': f'Código OTP enviado a {correo}',
            'correo':  correo,
        }, status=200)


class LoginVerificarOTPView(APIView):
    """Paso 2: El usuario ingresa el OTP → se retornan tokens JWT."""
    authentication_classes = []
    permission_classes = [AllowAny]

    @swagger_auto_schema(
        operation_summary='Verificar OTP y obtener tokens JWT',
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['correo', 'codigo'],
            properties={
                'correo': openapi.Schema(type=openapi.TYPE_STRING, format='email'),
                'codigo': openapi.Schema(type=openapi.TYPE_STRING, description='Código OTP de 6 dígitos'),
            },
        ),
        tags=['Autenticación'],
    )
    def post(self, request):
        correo = request.data.get('correo', '').strip().lower()
        codigo = request.data.get('codigo', '').strip()

        if not correo or not codigo:
            return Response({'error': 'Correo y código son obligatorios.'}, status=400)

        try:
            usuario = Usuario.objects.get(correo=correo, is_active=True, estado=True)
        except Usuario.DoesNotExist:
            return Response({'error': 'Usuario no encontrado.'}, status=404)

        otp = OTPVerificacion.objects.filter(
            usuario=usuario, codigo=codigo, usado=False
        ).order_by('-creado').first()

        if not otp:
            return Response({'error': 'Código inválido.'}, status=400)

        if not otp.es_valido:
            return Response({'error': 'El código ha expirado. Solicita uno nuevo.'}, status=400)

        otp.usado = True
        otp.save(update_fields=['usado'])

        refresh = RefreshToken.for_user(usuario)

        return Response({
            'user': UsuarioListSerializer(usuario).data,
            'access': str(refresh.access_token),
            'refresh': str(refresh),
        }, status=200)


class TokenRefreshView(APIView):
    """Renueva el access token usando el refresh token."""
    authentication_classes = []
    permission_classes = [AllowAny]

    @swagger_auto_schema(
        operation_summary='Renovar access token',
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['refresh'],
            properties={'refresh': openapi.Schema(type=openapi.TYPE_STRING)},
        ),
        tags=['Autenticación'],
    )
    def post(self, request):
        refresh_token = request.data.get('refresh')
        if not refresh_token:
            return Response({'error': 'Refresh token requerido.'}, status=400)
        try:
            token = RefreshToken(refresh_token)
            return Response({'access': str(token.access_token)}, status=200)
        except Exception:
            return Response({'error': 'Token inválido o expirado.'}, status=401)


class LogoutView(APIView):
    """Invalida el refresh token (logout)."""
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary='Cerrar sesión',
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['refresh'],
            properties={'refresh': openapi.Schema(type=openapi.TYPE_STRING)},
        ),
        tags=['Autenticación'],
    )
    def post(self, request):
        refresh_token = request.data.get('refresh')
        if not refresh_token:
            return Response({'error': 'Refresh token requerido.'}, status=400)
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except Exception:
            pass
        return Response({'mensaje': 'Sesión cerrada correctamente.'}, status=200)


class MeView(APIView):
    """Devuelve los datos del usuario autenticado."""
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(operation_summary='Datos del usuario autenticado', tags=['Autenticación'])
    def get(self, request):
        return Response(UsuarioListSerializer(request.user).data)


# ── Recuperación de contraseña ────────────────────────────────────────────────

class RecuperacionIniciarView(APIView):
    """Paso 1 recuperación: usuario ingresa correo → se envía OTP."""
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        correo = request.data.get('correo', '').strip().lower()
        if not correo:
            return Response({'error': 'El correo es obligatorio.'}, status=400)

        try:
            usuario = Usuario.objects.get(correo=correo, is_active=True, estado=True)
        except Usuario.DoesNotExist:
            return Response({'error': 'No existe una cuenta activa con ese correo.'}, status=404)

        otp = OTPVerificacion.generar(usuario)
        enviar_otp_email.delay(usuario.id, otp.codigo)

        return Response({'mensaje': 'Código enviado.', 'correo': correo}, status=200)


class RecuperacionValidarOTPView(APIView):
    """Paso 2 recuperación: valida OTP → crea ticket + notificación para admin."""
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        correo = request.data.get('correo', '').strip().lower()
        codigo = request.data.get('codigo', '').strip()

        if not correo or not codigo:
            return Response({'error': 'Correo y código son obligatorios.'}, status=400)

        try:
            usuario = Usuario.objects.get(correo=correo, is_active=True, estado=True)
        except Usuario.DoesNotExist:
            return Response({'error': 'Usuario no encontrado.'}, status=404)

        otp = OTPVerificacion.objects.filter(
            usuario=usuario, codigo=codigo, usado=False
        ).order_by('-creado').first()

        if not otp:
            return Response({'error': 'Código inválido.'}, status=400)

        if not otp.es_valido:
            return Response({'error': 'El código ha expirado. Solicita uno nuevo.'}, status=400)

        otp.usado = True
        otp.save(update_fields=['usado'])

        # Crear solicitud y notificación para el admin
        solicitud = SolicitudRecuperacionPassword.objects.create(
            usuario=usuario,
            estado='PENDIENTE_ADMIN',
        )
        NotificacionAdmin.objects.create(
            tipo='recuperacion_password',
            titulo=f'Solicitud de cambio de contraseña — {usuario.nombre_completo_display}',
            cuerpo=(
                f'El usuario {usuario.nombre_completo_display} ({usuario.correo}) '
                f'validó un código OTP y solicita el cambio de su contraseña. '
                f'Por favor asigna una nueva contraseña y comunícasela por un medio seguro.'
            ),
            solicitud=solicitud,
        )

        return Response({
            'mensaje': 'Solicitud enviada. El administrador recibirá una notificación.',
        }, status=200)


# ── Notificaciones de administrador ──────────────────────────────────────────

class NotificacionesAdminView(APIView):

    def get(self, request):
        from django.db.models import Q
        es_admin = request.user.is_superuser or request.user.has_perm('Usuarios.can_manage_users')

        if es_admin:
            # Admins ven notifs globales (usuario=null) + las suyas propias
            qs = NotificacionAdmin.objects.filter(
                Q(usuario__isnull=True) | Q(usuario=request.user)
            ).select_related('solicitud__usuario', 'usuario', 'contrato')
        else:
            # Directores y otros roles solo ven sus notifs personales
            qs = NotificacionAdmin.objects.filter(
                usuario=request.user
            ).select_related('solicitud__usuario', 'contrato')

        notifs = qs.order_by('-creado')[:50]
        data = []
        for n in notifs:
            sol = n.solicitud
            data.append({
                'id':          n.id,
                'tipo':        n.tipo,
                'titulo':      n.titulo,
                'cuerpo':      n.cuerpo,
                'leida':       n.leida,
                'creado':      n.creado,
                'contrato_id': n.contrato_id,
                'solicitud': {
                    'id':      sol.id,
                    'estado':  sol.estado,
                    'usuario': {
                        'id':     sol.usuario.id,
                        'correo': sol.usuario.correo,
                        'nombre': sol.usuario.nombre_completo_display,
                    },
                } if sol else None,
            })
        no_leidas = qs.filter(leida=False).count()
        return Response({'notificaciones': data, 'no_leidas': no_leidas})

    def put(self, request, pk):
        """Marca notificación como leída — cualquier usuario puede marcar las suyas."""
        from django.db.models import Q
        es_admin = request.user.is_superuser or request.user.has_perm('Usuarios.can_manage_users')
        try:
            if es_admin:
                notif = NotificacionAdmin.objects.get(pk=pk)
            else:
                notif = NotificacionAdmin.objects.get(pk=pk, usuario=request.user)
        except NotificacionAdmin.DoesNotExist:
            return Response({'error': 'No encontrada.'}, status=404)
        notif.leida = True
        notif.save(update_fields=['leida'])
        return Response({'ok': True})


class ResolverRecuperacionView(APIView):
    """Admin resuelve la solicitud asignando nueva contraseña al usuario."""

    @require_permission(['can_manage_users'], app_label='Usuarios')
    def post(self, request, pk):
        try:
            solicitud = SolicitudRecuperacionPassword.objects.get(pk=pk, estado='PENDIENTE_ADMIN')
        except SolicitudRecuperacionPassword.DoesNotExist:
            return Response({'error': 'Solicitud no encontrada o ya resuelta.'}, status=404)

        nueva_password = request.data.get('nueva_password', '').strip()
        if not nueva_password or len(nueva_password) < 8:
            return Response({'error': 'La contraseña debe tener al menos 8 caracteres.'}, status=400)

        usuario = solicitud.usuario
        usuario.set_password(nueva_password)
        usuario.save(update_fields=['password'])

        solicitud.estado       = 'RESUELTO'
        solicitud.resuelto_por = request.user
        solicitud.save(update_fields=['estado', 'resuelto_por'])

        # Marcar notificaciones relacionadas como leídas
        NotificacionAdmin.objects.filter(solicitud=solicitud).update(leida=True)

        return Response({
            'mensaje': (
                f'Contraseña actualizada para {usuario.nombre_completo_display}. '
                f'Recuerda compartirla con el usuario por un medio seguro '
                f'(llamada, mensaje directo o correo cifrado).'
            ),
            'usuario': usuario.correo,
        })
