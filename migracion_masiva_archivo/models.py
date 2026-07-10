from django.conf import settings
from django.db import models


class BaseModel(models.Model):
    creado = models.DateTimeField(auto_now_add=True)
    modificado = models.DateTimeField(auto_now=True)
    estado = models.BooleanField(default=True)

    class Meta:
        abstract = True


ESTADOS_LOTE = [
    ('PENDIENTE', 'Pendiente'),
    ('EN_PROCESO', 'En proceso'),
    ('FINALIZADO', 'Finalizado'),
    ('FINALIZADO_CON_ERRORES', 'Finalizado con errores'),
    ('CANCELADO', 'Cancelado'),
]


ESTADOS_DOCUMENTO = [
    ('PENDIENTE', 'Pendiente'),
    ('LEIDO', 'Leido'),
    ('OCR_PROCESADO', 'OCR procesado'),
    ('METADATA_EXTRAIDA', 'Metadata extraida'),
    ('VALIDADO', 'Validado'),
    ('REQUIERE_REVISION', 'Requiere revision'),
    ('RELACIONADO', 'Relacionado'),
    ('CARGADO_SAIA', 'Cargado en SAIA'),
    ('ERROR_SAIA', 'Error SAIA'),
]


TIPOS_RELACION = [
    ('FACTURA_PRINCIPAL', 'Factura principal'),
    ('SOPORTE_PAGO', 'Soporte de pago'),
    ('EGRESO', 'Egreso'),
    ('EXTRACTO_BANCARIO', 'Extracto bancario'),
    ('CONCILIACION', 'Conciliacion'),
    ('CRUCE', 'Cruce'),
    ('OTRO_SOPORTE', 'Otro soporte'),
]


NIVELES_LOG = [
    ('INFO', 'Informacion'),
    ('WARNING', 'Advertencia'),
    ('ERROR', 'Error'),
]


class LoteDocumental(BaseModel):
    nombre = models.CharField(max_length=160)
    carpeta_origen = models.CharField(max_length=500)
    estado_proceso = models.CharField(max_length=30, choices=ESTADOS_LOTE, default='PENDIENTE')
    total_archivos = models.PositiveIntegerField(default=0)
    total_procesados = models.PositiveIntegerField(default=0)
    total_exitosos = models.PositiveIntegerField(default=0)
    total_fallidos = models.PositiveIntegerField(default=0)
    total_revision = models.PositiveIntegerField(default=0)
    iniciado_por = models.CharField(max_length=150, blank=True, null=True, default='sistema')
    fecha_inicio = models.DateTimeField(null=True, blank=True)
    fecha_fin = models.DateTimeField(null=True, blank=True)
    observaciones = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Lote documental'
        verbose_name_plural = 'Lotes documentales'
        db_table = 'migracion_masiva_archivo_lotes'
        ordering = ['-creado']
        permissions = [
            ('can_view_migracion_masiva_archivo', 'Puede ver Migración Masiva de Archivo'),
            ('can_manage_migracion_masiva_archivo', 'Puede gestionar Migración Masiva de Archivo'),
            ('can_upload_migracion_masiva_archivo_saia', 'Puede cargar documentos en SAIA desde Migración Masiva de Archivo'),
        ]

    def __str__(self):
        return self.nombre


class DocumentoDigitalizado(BaseModel):
    lote = models.ForeignKey(LoteDocumental, on_delete=models.CASCADE, related_name='documentos')
    ruta_archivo = models.CharField(max_length=700)
    nombre_archivo = models.CharField(max_length=260)
    extension = models.CharField(max_length=20, blank=True)
    peso_bytes = models.BigIntegerField(default=0)
    hash_archivo = models.CharField(max_length=64, blank=True, db_index=True)
    es_soportado = models.BooleanField(default=True)
    es_duplicado = models.BooleanField(default=False)
    documento_duplicado_de = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='duplicados',
    )
    numero_paginas = models.PositiveIntegerField(default=0)
    es_pdf = models.BooleanField(default=False)
    es_digital = models.BooleanField(default=False)
    requiere_ocr = models.BooleanField(default=False)
    ocr_agotado = models.BooleanField(default=False)
    texto_extraido = models.TextField(blank=True)
    estado_proceso = models.CharField(max_length=30, choices=ESTADOS_DOCUMENTO, default='PENDIENTE')
    marcado_ok = models.BooleanField(default=False)
    error = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Documento digitalizado'
        verbose_name_plural = 'Documentos digitalizados'
        db_table = 'migracion_masiva_archivo_documentos'
        ordering = ['nombre_archivo']
        indexes = [
            models.Index(fields=['nombre_archivo']),
            models.Index(fields=['extension']),
            models.Index(fields=['estado_proceso']),
            models.Index(fields=['hash_archivo']),
            models.Index(fields=['es_soportado']),
            models.Index(fields=['es_duplicado']),
            models.Index(fields=['lote', 'estado_proceso'], name='doc_lote_estado_idx'),
        ]

    def __str__(self):
        return self.nombre_archivo


class MetadataDocumento(BaseModel):
    documento = models.OneToOneField(
        DocumentoDigitalizado,
        on_delete=models.CASCADE,
        related_name='metadata',
    )
    nit = models.CharField(max_length=30, blank=True, db_index=True)
    proveedor = models.CharField(max_length=220, blank=True)
    consecutivo = models.CharField(max_length=80, blank=True, db_index=True)
    fecha_documento = models.DateField(null=True, blank=True)
    tipo_documento = models.CharField(max_length=80, blank=True)
    valor = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    medio_pago = models.CharField(max_length=120, blank=True)
    cruce = models.CharField(max_length=120, blank=True)
    cruces_m_pago = models.JSONField(default=list, blank=True)
    referencia_pago = models.CharField(max_length=120, blank=True)
    pagina_detectada = models.PositiveIntegerField(null=True, blank=True)
    confianza = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    normalizado = models.BooleanField(default=False)
    requiere_revision = models.BooleanField(default=False)
    datos_pel = models.JSONField(default=dict, blank=True)
    observaciones = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Metadata documental'
        verbose_name_plural = 'Metadata documental'
        db_table = 'migracion_masiva_archivo_metadata'
        ordering = ['documento__nombre_archivo']
        indexes = [
            models.Index(fields=['nit']),
            models.Index(fields=['consecutivo']),
            models.Index(fields=['tipo_documento']),
        ]

    def __str__(self):
        return f'{self.documento.nombre_archivo} | {self.consecutivo or "Sin consecutivo"}'


class RelacionDocumento(BaseModel):
    documento_principal = models.ForeignKey(
        DocumentoDigitalizado,
        on_delete=models.CASCADE,
        related_name='relaciones_principales',
    )
    documento_relacionado = models.ForeignKey(
        DocumentoDigitalizado,
        on_delete=models.CASCADE,
        related_name='relaciones_secundarias',
    )
    tipo_relacion = models.CharField(max_length=40, choices=TIPOS_RELACION)
    criterio_relacion = models.CharField(max_length=250, blank=True)
    confianza = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    validado_manualmente = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'Relacion documental'
        verbose_name_plural = 'Relaciones documentales'
        db_table = 'migracion_masiva_archivo_relaciones'
        unique_together = ('documento_principal', 'documento_relacionado', 'tipo_relacion')

    def __str__(self):
        return f'{self.documento_principal} -> {self.documento_relacionado}'


class IntentoCargaSAIA(BaseModel):
    documento = models.ForeignKey(DocumentoDigitalizado, on_delete=models.CASCADE, related_name='intentos_saia')
    numero_intento = models.PositiveIntegerField(default=1)
    endpoint = models.CharField(max_length=500, blank=True)
    status_code = models.PositiveIntegerField(null=True, blank=True)
    exitoso = models.BooleanField(default=False)
    id_documento_saia = models.CharField(max_length=120, blank=True)
    usuario_saia = models.CharField(max_length=120, blank=True)
    request_metadata = models.JSONField(default=dict, blank=True)
    respuesta = models.JSONField(default=dict, blank=True)
    mensaje_error = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Intento de carga SAIA'
        verbose_name_plural = 'Intentos de carga SAIA'
        db_table = 'migracion_masiva_archivo_intentos_saia'
        ordering = ['-creado']
        indexes = [
            models.Index(fields=['exitoso']),
            models.Index(fields=['status_code']),
        ]

    def __str__(self):
        return f'{self.documento.nombre_archivo} | intento {self.numero_intento}'


ESTADOS_EJECUCION = [
    ('PENDIENTE', 'Pendiente'),
    ('EN_PROCESO', 'En proceso'),
    ('FINALIZADO', 'Finalizado'),
    ('FINALIZADO_CON_ERRORES', 'Finalizado con errores'),
    ('FALLIDO', 'Fallido'),
    ('CANCELADO', 'Cancelado'),
]


class EjecucionCargaMasiva(BaseModel):
    lote = models.ForeignKey(LoteDocumental, on_delete=models.CASCADE, related_name='ejecuciones')
    celery_task_id = models.CharField(max_length=200, blank=True, db_index=True)
    estado_proceso = models.CharField(max_length=30, choices=ESTADOS_EJECUCION, default='PENDIENTE')
    tamano_sublote = models.PositiveIntegerField(default=10)
    max_reintentos = models.PositiveIntegerField(default=3)
    total_documentos = models.PositiveIntegerField(default=0)
    procesados = models.PositiveIntegerField(default=0)
    exitosos = models.PositiveIntegerField(default=0)
    fallidos = models.PositiveIntegerField(default=0)
    pendientes_revision = models.PositiveIntegerField(default=0)
    dry_run = models.BooleanField(default=False)
    headful = models.BooleanField(default=False)
    pausa_entre = models.PositiveIntegerField(default=3)
    iniciado_por = models.CharField(max_length=150, blank=True)
    fecha_inicio = models.DateTimeField(null=True, blank=True)
    fecha_fin = models.DateTimeField(null=True, blank=True)
    error = models.TextField(blank=True)
    cancelacion_solicitada = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'Ejecucion carga masiva'
        verbose_name_plural = 'Ejecuciones de carga masiva'
        db_table = 'migracion_masiva_archivo_ejecuciones_masivas'
        ordering = ['-creado']

    def __str__(self):
        return f'Ejecucion {self.id} | Lote {self.lote_id} | {self.estado}'


class LogProcesoDocumental(BaseModel):
    lote = models.ForeignKey(
        LoteDocumental,
        on_delete=models.CASCADE,
        related_name='logs',
        null=True,
        blank=True,
    )
    documento = models.ForeignKey(
        DocumentoDigitalizado,
        on_delete=models.CASCADE,
        related_name='logs',
        null=True,
        blank=True,
    )
    nivel = models.CharField(max_length=20, choices=NIVELES_LOG, default='INFO')
    evento = models.CharField(max_length=120)
    mensaje = models.TextField(blank=True)
    detalle = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = 'Log documental'
        verbose_name_plural = 'Logs documentales'
        db_table = 'migracion_masiva_archivo_proceso_logs'
        ordering = ['-creado']
        indexes = [
            models.Index(fields=['evento'], name='migracion_m_evento_6232ea_idx'),
            models.Index(fields=['nivel'], name='migracion_m_nivel_a66dd8_idx'),
            models.Index(fields=['lote', 'creado'], name='logs_lote_creado_idx'),
        ]

    def __str__(self):
        return f'{self.nivel} | {self.evento}'


class ConfiguracionMigracionMasivaArchivo(BaseModel):
    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='configuracion_migracion_masiva_archivo',
    )
    correo_destino = models.EmailField(blank=True)

    class Meta:
        verbose_name = 'Configuracion Migracion Masiva de Archivo'
        verbose_name_plural = 'Configuraciones Migracion Masiva de Archivo'
        db_table = 'migracion_masiva_archivo_configuracion'

    def __str__(self):
        return f'Config {self.usuario_id} | {self.correo_destino or "sin correo"}'

