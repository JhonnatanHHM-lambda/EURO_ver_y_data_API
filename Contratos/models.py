import uuid
from django.db import models
from django.conf import settings


class PlantillaCarta(models.Model):
    TIPO_CHOICES = [
        ('NO_PRORROGA', 'No prórroga'),
        ('PRORROGA', 'Prórroga'),
        ('TERMINACION', 'Terminación'),
    ]
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, unique=True)
    activa = models.BooleanField(default=True)
    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Plantilla de carta'
        verbose_name_plural = 'Plantillas de carta'
        db_table = 'contratos_plantillas'

    def __str__(self):
        return self.get_tipo_display()


class Contrato(models.Model):
    ESTADO_CHOICES = [
        ('PENDIENTE_FIRMA_NO_PRORROGA', 'Pendiente firma — no prórroga'),
        ('PENDIENTE_DECISION_DIRECTOR', 'Pendiente decisión director'),
        ('PENDIENTE_CONDICIONES_GH', 'Pendiente condiciones GH'),
        ('PENDIENTE_NOTIFICACION_EMPLEADO', 'Pendiente notificación empleado'),
        ('PENDIENTE_FIRMA_PRORROGA', 'Pendiente firma — prórroga'),
        ('PENDIENTE_FIRMA_TERMINACION', 'Pendiente firma — terminación'),
        ('FIRMADO', 'Firmado'),
        ('SIN_CANAL_CONTACTO', 'Sin canal de contacto'),
        ('ERROR_NOTIFICACION', 'Error de notificación'),
        ('CANCELADO', 'Cancelado'),
    ]
    TIPO_CHOICES = [
        ('NO_PRORROGA', 'No prórroga'),
        ('PRORROGA', 'Prórroga'),
        ('TERMINACION', 'Terminación'),
    ]
    DURACION_PRORROGA_CHOICES = [
        ('1_MES',    '1 mes'),
        ('2_MESES',  '2 meses'),
        ('3_MESES',  '3 meses'),
        ('4_MESES',  '4 meses'),
        ('5_MESES',  '5 meses'),
        ('6_MESES',  '6 meses'),
        ('7_MESES',  '7 meses'),
        ('8_MESES',  '8 meses'),
        ('9_MESES',  '9 meses'),
        ('10_MESES', '10 meses'),
        ('11_MESES', '11 meses'),
        ('12_MESES', '12 meses'),
    ]

    # Datos del empleado (snapshot de Siesa)
    tipo_documento = models.CharField(max_length=10)
    documento_id = models.CharField(max_length=30)
    nombre_completo = models.CharField(max_length=200)
    cargo = models.CharField(max_length=100)
    fecha_inicio_contrato = models.DateField(null=True, blank=True)
    fecha_finalizacion = models.DateField()
    celular = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    sede = models.ForeignKey(
        'Trazabilidad.Sede',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='contratos'
    )

    # Tipo y estado
    tipo_carta = models.CharField(max_length=20, choices=TIPO_CHOICES)
    estado = models.CharField(max_length=40, choices=ESTADO_CHOICES, default='PENDIENTE_FIRMA_NO_PRORROGA')

    # Firma
    token_firma = models.UUIDField(default=uuid.uuid4, unique=True)
    token_usado = models.BooleanField(default=False)
    token_expira_en = models.DateTimeField(null=True, blank=True)
    ip_acceso = models.GenericIPAddressField(null=True, blank=True)
    ip_confirmacion = models.GenericIPAddressField(null=True, blank=True)
    firma_canvas_data = models.TextField(blank=True)

    # PDFs en MinIO
    pdf_carta_key = models.CharField(max_length=500, blank=True)
    pdf_firmado_key = models.CharField(max_length=500, blank=True)

    # Firma secuencial: cuando el director decide sobre un contrato cuya NO_PRORROGA
    # aún no fue firmada, el empleado debe firmar primero la NO_PRORROGA y luego la
    # PRORROGA/TERMINACION dentro del mismo enlace.
    no_prorroga_firmada = models.BooleanField(default=True)
    pdf_no_prorroga_key = models.CharField(max_length=500, blank=True, default='')

    # Prórroga
    duracion_prorroga = models.CharField(max_length=10, choices=DURACION_PRORROGA_CHOICES, blank=True)
    nuevo_sueldo = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    mantener_condiciones = models.BooleanField(default=True)
    fecha_fin_prorroga = models.DateField(null=True, blank=True)

    # Escalamiento
    fecha_primer_envio = models.DateTimeField(null=True, blank=True)
    fecha_firma = models.DateTimeField(null=True, blank=True)
    contador_escalamientos = models.PositiveIntegerField(default=0)
    fecha_ultimo_escalamiento = models.DateTimeField(null=True, blank=True)

    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['fecha_finalizacion']
        verbose_name = 'Contrato'
        verbose_name_plural = 'Contratos'
        db_table = 'contratos_contrato'

    def __str__(self):
        return f'{self.nombre_completo} — {self.tipo_carta} ({self.estado})'


class DocumentoAdicional(models.Model):
    contrato = models.ForeignKey(Contrato, on_delete=models.CASCADE, related_name='documentos_adicionales')
    nombre_archivo = models.CharField(max_length=255)
    minio_key = models.CharField(max_length=500)
    subido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'contratos_documentos_adicionales'

    def __str__(self):
        return f'{self.nombre_archivo} — {self.contrato}'


class EventoContrato(models.Model):
    TIPO_CHOICES = [
        ('GENERADO', 'Carta generada'),
        ('ENVIADO_EMAIL', 'Email enviado'),
        ('ENVIADO_WA', 'WhatsApp enviado'),
        ('ACCESO_FIRMA', 'Acceso a firma'),
        ('FIRMADO', 'Firmado'),
        ('ESCALADO', 'Escalado a director'),
        ('DECISION_DIRECTOR', 'Decisión de director'),
        ('CONDICIONES_GH', 'Condiciones definidas por GH'),
        ('NOTIFICACION_EMPLEADO', 'Director notificó al empleado'),
        ('ERROR', 'Error'),
    ]
    contrato = models.ForeignKey(Contrato, on_delete=models.CASCADE, related_name='eventos')
    tipo_evento = models.CharField(max_length=30, choices=TIPO_CHOICES)
    timestamp = models.DateTimeField(auto_now_add=True)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    ip = models.GenericIPAddressField(null=True, blank=True)
    detalle = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-timestamp']
        db_table = 'contratos_eventos'

    def __str__(self):
        return f'{self.tipo_evento} — {self.contrato}'


class AsignacionCentro(models.Model):
    """Asocia un Usuario a una Sede con rol Director o GH para el módulo de contratos."""
    ROL_CHOICES = [
        ('GH', 'Gestión Humana'),
        ('DIRECTOR', 'Director'),
    ]
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='asignaciones_centro',
        verbose_name='Usuario'
    )
    sede = models.ForeignKey(
        'Trazabilidad.Sede',
        on_delete=models.CASCADE,
        related_name='asignaciones_contratos',
        verbose_name='Sede'
    )
    rol = models.CharField(max_length=20, choices=ROL_CHOICES, verbose_name='Rol en contratos')
    activo = models.BooleanField(default=True)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Asignación de sede'
        verbose_name_plural = 'Asignaciones de sede'
        db_table = 'contratos_asignaciones_sede'
        unique_together = [('usuario', 'sede')]

    def __str__(self):
        return f'{self.usuario} → {self.sede.codigo} ({self.rol})'
