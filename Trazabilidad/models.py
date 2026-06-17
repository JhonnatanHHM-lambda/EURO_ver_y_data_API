from django.db import models
from django.core.validators import MinValueValidator
from Base.models import BaseModel


class Origen(BaseModel):
    nombre      = models.CharField(max_length=100, unique=True, verbose_name='Nombre')
    descripcion = models.CharField(max_length=250, blank=True, verbose_name='Descripción')

    class Meta:
        verbose_name = 'Origen de datos'
        verbose_name_plural = 'Orígenes de datos'
        db_table = 'origenes_datos'
        ordering = ['nombre']

    def __str__(self):
        return self.nombre


class Sede(BaseModel):
    nombre = models.CharField(max_length=120, verbose_name='Nombre')
    ciudad = models.CharField(max_length=100, verbose_name='Ciudad')
    codigo = models.CharField(max_length=20, unique=True, verbose_name='Código')
    dias_alerta_director = models.PositiveIntegerField(
        default=5,
        validators=[MinValueValidator(5)],
        verbose_name='Días alerta director',
        help_text='Días antes del vencimiento del contrato para notificar al director de esta sede. Mínimo 5.'
    )

    class Meta:
        verbose_name = 'Sede'
        verbose_name_plural = 'Sedes'
        db_table = 'sedes'
        ordering = ['ciudad', 'nombre']

    def __str__(self):
        return f'{self.nombre} ({self.ciudad})'


ESTADOS_CANDIDATO = [
    ('REGISTRADO', 'Registrado'),
    ('HABILITADO', 'Habilitado'),
    ('INHABILITADO', 'Inhabilitado'),
    ('VERIFICACION_PARCIAL', 'Verificación parcial'),
    ('REVISION_MANUAL_AUTORIZADA', 'Revisión manual autorizada'),
    ('REVISION_MANUAL_RECHAZADA', 'Revisión manual rechazada'),
]

TIPOS_PROCESO = [
    ('SELECCIONADO', 'Seleccionado'),
    ('EMPLEADO', 'Empleado'),
    ('APRENDIZ', 'Aprendiz'),
    ('PASANTE', 'Pasante'),
    ('RETIRADO', 'Retirado'),
    ('CANDIDATO', 'Candidato'),
    ('ENTREVISTADO', 'Entrevistado'),
]


class EmpleadoTrazabilidad(BaseModel):
    documento_id   = models.CharField(max_length=20, verbose_name='Número de documento', db_index=True)
    tipo_documento = models.CharField(max_length=60, default='CC', verbose_name='Tipo documento')
    nombre_completo = models.CharField(max_length=200, verbose_name='Nombre completo')
    origen_datos   = models.CharField(max_length=100, verbose_name='Origen de datos')
    estado_candidato = models.CharField(max_length=40, choices=ESTADOS_CANDIDATO, default='REGISTRADO')
    tipo_proceso   = models.CharField(max_length=30, choices=TIPOS_PROCESO, blank=True)
    motivo_inhabilitacion = models.TextField(blank=True)
    sede           = models.ForeignKey(Sede, on_delete=models.SET_NULL, null=True, blank=True, related_name='empleados')
    cargo          = models.CharField(max_length=120, blank=True)
    fecha_ingreso  = models.DateField(null=True, blank=True)
    fecha_retiro   = models.DateField(null=True, blank=True)
    motivo_retiro  = models.CharField(max_length=500, blank=True)
    celular        = models.CharField(max_length=60, blank=True)
    email          = models.EmailField(max_length=120, blank=True)
    direccion      = models.CharField(max_length=250, blank=True)
    barrio_municipio = models.CharField(max_length=120, blank=True)
    centro_costos  = models.CharField(max_length=30, blank=True)
    eps            = models.CharField(max_length=100, blank=True)
    pensiones      = models.CharField(max_length=100, blank=True)
    arl            = models.CharField(max_length=100, blank=True)
    tipo_sangre    = models.CharField(max_length=20, blank=True)
    fecha_nacimiento = models.DateField(null=True, blank=True)
    nivel_escolaridad = models.CharField(max_length=60, blank=True)
    expedida_en    = models.CharField(max_length=100, blank=True)
    sexo           = models.CharField(max_length=30, blank=True)
    observaciones  = models.TextField(blank=True)
    fecha_entrevista = models.DateField(null=True, blank=True)
    psicologa      = models.CharField(max_length=100, blank=True)
    fuente_carga   = models.CharField(max_length=250, blank=True)
    cargado_por    = models.ForeignKey(
        'Usuarios.Usuario', on_delete=models.SET_NULL, null=True, blank=True, related_name='cargas'
    )
    carga          = models.ForeignKey(
        'CargaExcel', on_delete=models.SET_NULL, null=True, blank=True, related_name='empleados'
    )

    class Meta:
        verbose_name = 'Empleado / Candidato'
        verbose_name_plural = 'Empleados / Candidatos'
        db_table = 'empleados_trazabilidad'
        ordering = ['nombre_completo']
        indexes = [
            models.Index(fields=['documento_id']),
            models.Index(fields=['origen_datos']),
            models.Index(fields=['estado_candidato']),
        ]

    def __str__(self):
        return f'{self.nombre_completo} ({self.documento_id})'


class HistorialCambioRegistro(BaseModel):
    """Auditoría de cambios manuales a estado_candidato o tipo_proceso."""
    CAMPOS = [
        ('estado_candidato', 'Estado candidato'),
        ('tipo_proceso',     'Tipo de proceso'),
    ]
    registro       = models.ForeignKey(
        'EmpleadoTrazabilidad', on_delete=models.CASCADE,
        related_name='historial_cambios'
    )
    campo          = models.CharField(max_length=30, choices=CAMPOS)
    valor_anterior = models.CharField(max_length=50)
    valor_nuevo    = models.CharField(max_length=50)
    justificacion  = models.TextField()
    modificado_por = models.ForeignKey(
        'Usuarios.Usuario', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='cambios_realizados'
    )

    class Meta:
        verbose_name        = 'Historial de cambio'
        verbose_name_plural = 'Historial de cambios'
        db_table            = 'historial_cambios_registros'
        ordering            = ['-creado']

    def __str__(self):
        return f'{self.registro.nombre_completo} | {self.campo}: {self.valor_anterior} → {self.valor_nuevo}'


class CargaExcel(BaseModel):
    sede            = models.ForeignKey(Sede, on_delete=models.SET_NULL, null=True, related_name='cargas')
    nombre_archivo  = models.CharField(max_length=250)
    hoja            = models.CharField(max_length=100, blank=True)
    origen_datos    = models.CharField(max_length=100)
    total_registros = models.IntegerField(default=0)
    exitosos        = models.IntegerField(default=0)
    fallidos        = models.IntegerField(default=0)
    errores         = models.JSONField(default=list)
    cargado_por     = models.ForeignKey(
        'Usuarios.Usuario', on_delete=models.SET_NULL, null=True, blank=True, related_name='historial_cargas'
    )
    # ── Firma GH para el acta de carga ────────────────────────────────────────
    firma_gh_nombre = models.CharField(max_length=120, blank=True, verbose_name='Nombre firmante GH')
    firma_gh_cargo  = models.CharField(max_length=120, blank=True, verbose_name='Cargo firmante GH')
    firma_gh_fecha  = models.DateTimeField(null=True, blank=True,  verbose_name='Fecha firma GH')
    firma_gh_imagen = models.TextField(blank=True, verbose_name='Firma GH (base64 PNG)')

    class Meta:
        verbose_name = 'Carga de Excel'
        verbose_name_plural = 'Historial de cargas'
        db_table = 'cargas_excel'
        ordering = ['-creado']

    def __str__(self):
        return f'{self.nombre_archivo} — {self.sede} ({self.creado})'
