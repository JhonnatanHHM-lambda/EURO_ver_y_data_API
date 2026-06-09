import random
import string
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.utils import timezone
from django.utils.crypto import get_random_string
from datetime import timedelta
import shortuuid

from Base.models import BaseModel


def generar_codigo_unico():
    return shortuuid.ShortUUID().random(length=8)


class UserManager(BaseUserManager):
    def create_user(self, correo, nombres, apellidos, password=None, **extra_fields):
        if not correo:
            raise ValueError('El correo es obligatorio')
        correo = self.normalize_email(correo)
        user = self.model(correo=correo, nombres=nombres, apellidos=apellidos, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, correo, nombres, apellidos, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        return self.create_user(correo, nombres, apellidos, password, **extra_fields)


class Usuario(BaseModel, AbstractBaseUser, PermissionsMixin):
    cedula = models.CharField(max_length=20, unique=True, verbose_name='Cédula')
    correo = models.EmailField(unique=True, verbose_name='Correo electrónico')
    nombres = models.CharField(max_length=80, verbose_name='Nombres')
    apellidos = models.CharField(max_length=80, verbose_name='Apellidos')
    genero = models.CharField(
        max_length=10,
        choices=[('M', 'Masculino'), ('F', 'Femenino'), ('O', 'Otro')],
        blank=True, null=True
    )
    codigo = models.CharField(max_length=8, unique=True, default=generar_codigo_unico, editable=False)
    fecha_nacimiento = models.DateField(blank=True, null=True)
    telefono = models.CharField(max_length=15, blank=True, null=True)

    reset_password_token = models.CharField(max_length=200, blank=True, null=True)
    reset_password_token_expires_at = models.DateTimeField(blank=True, null=True)

    is_staff = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    objects = UserManager()

    USERNAME_FIELD = 'correo'
    REQUIRED_FIELDS = ['nombres', 'apellidos', 'cedula']

    class Meta:
        verbose_name = 'Usuario'
        verbose_name_plural = 'Usuarios'
        db_table = 'usuarios'
        permissions = [
            ('can_manage_users', 'Puede gestionar usuarios'),
            ('can_manage_roles', 'Puede gestionar roles y permisos'),
            ('can_view_dashboard', 'Puede ver el dashboard'),
            ('can_upload_excel', 'Puede subir archivos Excel'),
            ('can_view_trazabilidad', 'Puede ver trazabilidad de empleados'),
            ('can_manage_sedes', 'Puede gestionar sedes y orígenes de datos'),
            ('can_edit_registros', 'Puede editar estado y proceso de registros de trazabilidad'),
            ('can_manage_cargas', 'Puede ver historial de cargas y revertirlas'),
        ]
        indexes = [
            models.Index(fields=['correo']),
            models.Index(fields=['cedula']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return f'{self.nombres} {self.apellidos}'.title()

    def obtener_nombre_completo(self):
        return f'{self.nombres} {self.apellidos}'.title()

    @property
    def nombre_completo_display(self):
        return f'{self.nombres} {self.apellidos}'.title()

    @property
    def rol_principal(self):
        if self.groups.exists():
            return self.groups.first().name
        return 'Sin rol'

    def crear_token_recuperacion(self):
        self.reset_password_token = get_random_string(50)
        self.reset_password_token_expires_at = timezone.now() + timedelta(hours=1)
        self.save(update_fields=['reset_password_token', 'reset_password_token_expires_at'])
        return self.reset_password_token


class SolicitudRecuperacionPassword(BaseModel):
    """Ticket de recuperación de contraseña iniciado por el usuario."""
    ESTADOS = [
        ('PENDIENTE_OTP',   'Pendiente validación OTP'),
        ('PENDIENTE_ADMIN', 'Esperando resolución del administrador'),
        ('RESUELTO',        'Resuelto'),
    ]
    usuario       = models.ForeignKey(Usuario, on_delete=models.CASCADE, related_name='solicitudes_recuperacion')
    estado        = models.CharField(max_length=20, choices=ESTADOS, default='PENDIENTE_OTP')
    resuelto_por  = models.ForeignKey(
        Usuario, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='recuperaciones_resueltas'
    )

    class Meta:
        verbose_name = 'Solicitud de recuperación'
        verbose_name_plural = 'Solicitudes de recuperación'
        db_table = 'solicitudes_recuperacion'
        ordering = ['-creado']

    def __str__(self):
        return f'Recuperación {self.usuario.correo} — {self.estado}'


class NotificacionAdmin(BaseModel):
    """Notificación generada para los administradores."""
    TIPOS = [('recuperacion_password', 'Recuperación de contraseña')]
    tipo       = models.CharField(max_length=50, choices=TIPOS)
    titulo     = models.CharField(max_length=200)
    cuerpo     = models.TextField()
    leida      = models.BooleanField(default=False)
    solicitud  = models.ForeignKey(
        SolicitudRecuperacionPassword, on_delete=models.CASCADE,
        null=True, blank=True, related_name='notificaciones'
    )

    class Meta:
        verbose_name = 'Notificación admin'
        verbose_name_plural = 'Notificaciones admin'
        db_table = 'notificaciones_admin'
        ordering = ['-creado']

    def __str__(self):
        return self.titulo


class OTPVerificacion(BaseModel):
    usuario = models.ForeignKey(
        Usuario, on_delete=models.CASCADE,
        related_name='otps', verbose_name='Usuario'
    )
    codigo = models.CharField(max_length=6, verbose_name='Código OTP')
    expira_en = models.DateTimeField(verbose_name='Expira en')
    usado = models.BooleanField(default=False, verbose_name='Usado')

    class Meta:
        verbose_name = 'Verificación OTP'
        verbose_name_plural = 'Verificaciones OTP'
        db_table = 'otp_verificaciones'
        ordering = ['-creado']

    def __str__(self):
        return f'OTP {self.codigo} - {self.usuario.correo}'

    @property
    def es_valido(self):
        return not self.usado and timezone.now() < self.expira_en

    @classmethod
    def generar(cls, usuario):
        from django.conf import settings as django_settings
        cls.objects.filter(usuario=usuario, usado=False).update(usado=True)
        codigo = ''.join(random.choices(string.digits, k=6))
        expira = timezone.now() + timedelta(minutes=django_settings.OTP_EXPIRY_MINUTES)
        return cls.objects.create(usuario=usuario, codigo=codigo, expira_en=expira)
