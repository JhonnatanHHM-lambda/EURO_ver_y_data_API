from django.db import models
from Base.models import BaseModel


class EstadoEjecucion(models.TextChoices):
    PENDIENTE = 'PENDIENTE', 'Pendiente'
    EN_PROCESO = 'EN_PROCESO', 'En proceso'
    COMPLETADA = 'COMPLETADA', 'Completada'
    ERROR = 'ERROR', 'Error'


class EstadoConciliacion(models.TextChoices):
    CONCILIADA = 'CONCILIADA', 'Conciliada'
    REVISION_MANUAL = 'REVISION_MANUAL', 'Revisión manual'
    SOLO_RADIAN = 'SOLO_RADIAN', 'Solo RADIAN'
    SOLO_CORREO = 'SOLO_CORREO', 'Solo correo'


class EjecucionConsolidacion(BaseModel):
    fecha_desde = models.DateField()
    fecha_hasta = models.DateField()
    estado = models.CharField(
        max_length=20, choices=EstadoEjecucion.choices, default=EstadoEjecucion.PENDIENTE
    )
    iniciada_en = models.DateTimeField(null=True, blank=True)
    completada_en = models.DateTimeField(null=True, blank=True)
    total_radian = models.IntegerField(default=0)
    total_correo = models.IntegerField(default=0)
    total_conciliadas = models.IntegerField(default=0)
    total_solo_radian = models.IntegerField(default=0)
    total_solo_correo = models.IntegerField(default=0)
    total_revision = models.IntegerField(default=0)
    error_mensaje = models.TextField(blank=True)
    iniciada_por = models.ForeignKey(
        'Usuarios.Usuario', on_delete=models.SET_NULL, null=True, blank=True
    )

    class Meta:
        db_table = 'oc_ejecucion'
        ordering = ['-creado']
        verbose_name = 'Ejecución de consolidación'
        verbose_name_plural = 'Ejecuciones de consolidación'

    def __str__(self):
        return f'Ejecución {self.fecha_desde} — {self.fecha_hasta} [{self.estado}]'


class FacturaRadian(BaseModel):
    ejecucion = models.ForeignKey(
        EjecucionConsolidacion, on_delete=models.CASCADE, related_name='facturas_radian'
    )
    cufe = models.CharField(max_length=300, db_index=True)
    numero = models.CharField(max_length=100)
    nit_proveedor = models.CharField(max_length=50)
    nombre_proveedor = models.CharField(max_length=255)
    total = models.DecimalField(max_digits=18, decimal_places=2)
    fecha_emision = models.DateField()
    tipo_documento = models.CharField(max_length=10, blank=True)
    track_id = models.CharField(max_length=300)

    class Meta:
        db_table = 'oc_factura_radian'
        verbose_name = 'Factura RADIAN'
        verbose_name_plural = 'Facturas RADIAN'

    def __str__(self):
        return f'RADIAN {self.numero} — {self.nit_proveedor}'


class FacturaCorreo(BaseModel):
    ejecucion = models.ForeignKey(
        EjecucionConsolidacion, on_delete=models.CASCADE, related_name='facturas_correo'
    )
    cufe = models.CharField(max_length=300, blank=True, db_index=True)
    numero = models.CharField(max_length=100, blank=True)
    nit_proveedor = models.CharField(max_length=50, blank=True)
    nombre_proveedor = models.CharField(max_length=255, blank=True)
    total = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    fecha_emision = models.DateField(null=True, blank=True)
    asunto_correo = models.CharField(max_length=500)
    fecha_correo = models.DateTimeField()
    remitente = models.CharField(max_length=255)
    nombre_remitente = models.CharField(max_length=255, blank=True)
    carpeta = models.CharField(max_length=255, blank=True)

    class Meta:
        db_table = 'oc_factura_correo'
        verbose_name = 'Factura correo'
        verbose_name_plural = 'Facturas correo'

    def __str__(self):
        return f'Correo: {self.asunto_correo[:60]}'


class ResultadoConciliacion(BaseModel):
    ejecucion = models.ForeignKey(
        EjecucionConsolidacion, on_delete=models.CASCADE, related_name='resultados'
    )
    factura_radian = models.ForeignKey(
        FacturaRadian, on_delete=models.SET_NULL, null=True, blank=True
    )
    factura_correo = models.ForeignKey(
        FacturaCorreo, on_delete=models.SET_NULL, null=True, blank=True
    )
    cufe = models.CharField(max_length=300, db_index=True, blank=True)
    numero = models.CharField(max_length=100, blank=True)
    nit_proveedor = models.CharField(max_length=50, blank=True)
    nombre_proveedor = models.CharField(max_length=255, blank=True)
    monto_radian = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    monto_correo = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    delta_monto = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    fecha_radian = models.DateField(null=True, blank=True)
    fecha_correo = models.DateTimeField(null=True, blank=True)
    asunto_correo = models.CharField(max_length=500, blank=True)
    estado = models.CharField(max_length=30, choices=EstadoConciliacion.choices)
    nivel_match = models.CharField(max_length=5, blank=True)

    class Meta:
        db_table = 'oc_resultado'
        verbose_name = 'Resultado de conciliación'
        verbose_name_plural = 'Resultados de conciliación'

    def __str__(self):
        return f'Resultado {self.estado} — {self.numero or self.cufe[:20]}'
