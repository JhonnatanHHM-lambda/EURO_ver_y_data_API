from django.db import models


class AusentismoDato(models.Model):
    """
    Registro individual de ausentismo/tiempo-no-laborado sincronizado desde SIESA.
    Cada fila corresponde a un registro en w0610_tiempo_no_laborado.
    rowid_tnl es el surrogate key de SIESA — garantiza idempotencia en upserts.
    """
    rowid_tnl     = models.BigIntegerField(unique=True, db_index=True)
    cedula        = models.CharField(max_length=20, db_index=True)
    nombre        = models.CharField(max_length=200)
    concepto_id   = models.CharField(max_length=20, db_index=True)
    concepto_desc = models.CharField(max_length=200)
    tipo_concepto = models.CharField(max_length=20, blank=True)
    horas         = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    valor         = models.DecimalField(max_digits=16, decimal_places=2, null=True, blank=True)
    dias          = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    cargo         = models.CharField(max_length=200, blank=True)
    co_codigo     = models.CharField(max_length=10, blank=True, db_index=True)
    mes           = models.SmallIntegerField(db_index=True)
    ano           = models.SmallIntegerField(db_index=True)
    fecha_inicio  = models.DateField()
    fecha_fin     = models.DateField(null=True, blank=True)
    # M = masculino, F = femenino
    sexo          = models.CharField(max_length=1, blank=True)
    # I = indefinido, F = fijo
    tipo_contrato = models.CharField(max_length=1, blank=True)
    fecha_ingreso = models.DateField(null=True, blank=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'dashboard_ausentismo_dato'
        indexes = [
            models.Index(fields=['ano', 'mes']),
            models.Index(fields=['co_codigo', 'ano', 'mes']),
            models.Index(fields=['cedula', 'ano', 'mes']),
        ]

    def __str__(self):
        return f"{self.cedula} | {self.concepto_id} | {self.fecha_inicio}"


class NominaDato(models.Model):
    """
    Registro individual de nómina (TODOS los conceptos) sincronizado desde SIESA.
    Fuente: w0602_movto_nomina. rowid_mv = c0602_rowid, surrogate key de SIESA.
    """
    rowid_mv       = models.BigIntegerField(unique=True, db_index=True)
    cedula         = models.CharField(max_length=20, db_index=True)
    nombre         = models.CharField(max_length=200)
    concepto_id    = models.CharField(max_length=20, db_index=True)
    concepto_desc  = models.CharField(max_length=200)
    naturaleza     = models.SmallIntegerField(default=1)   # 1=devengado, 2=deducción
    horas          = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    valor          = models.DecimalField(max_digits=16, decimal_places=2, null=True, blank=True)
    dias_tnl       = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    cargo          = models.CharField(max_length=200, blank=True)
    co_codigo      = models.CharField(max_length=10, blank=True, db_index=True)
    co_nombre      = models.CharField(max_length=100, blank=True)
    mes            = models.SmallIntegerField(db_index=True)
    ano            = models.SmallIntegerField(db_index=True)
    es_tnl         = models.BooleanField(default=False, db_index=True)
    sexo           = models.CharField(max_length=1, blank=True)
    tipo_contrato  = models.CharField(max_length=1, blank=True)
    fecha_ingreso  = models.DateField(null=True, blank=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'dashboard_nomina_dato'
        indexes = [
            models.Index(fields=['ano', 'mes']),
            models.Index(fields=['ano', 'mes', 'co_codigo']),
            models.Index(fields=['cedula', 'ano', 'mes']),
            models.Index(fields=['concepto_id', 'ano', 'mes']),
        ]

    def __str__(self):
        return f"{self.cedula} | {self.concepto_id} | {self.ano}/{self.mes:02d}"


class RotacionDato(models.Model):
    """
    Registro de rotación de personal sincronizado desde SIESA.
    Cubre activos (es_activo=True) y retirados (es_activo=False).
    Fuente: w0550_contratos. rowid_contrato = c0550_rowid (PK única SIESA).
    La misma fila es activo hoy y retirado mañana — el upsert actualiza el estado.
    """
    rowid_contrato     = models.BigIntegerField(unique=True, db_index=True)
    cedula             = models.CharField(max_length=20, db_index=True)
    nombre             = models.CharField(max_length=200)
    cargo              = models.CharField(max_length=200, blank=True)
    co_codigo          = models.CharField(max_length=10, blank=True, db_index=True)
    co_nombre          = models.CharField(max_length=100, blank=True)
    fecha_ingreso      = models.DateField(null=True, blank=True)
    fecha_retiro       = models.DateField(null=True, blank=True, db_index=True)
    id_motivo_retiro   = models.CharField(max_length=10, blank=True)
    motivo_retiro      = models.CharField(max_length=200, blank=True)
    salario            = models.DecimalField(max_digits=16, decimal_places=4, null=True, blank=True)
    salario_anterior   = models.DecimalField(max_digits=16, decimal_places=4, null=True, blank=True)
    fecha_contrato_hasta = models.DateField(null=True, blank=True)
    # F = término fijo, I = indefinido
    tipo_contrato      = models.CharField(max_length=1, blank=True)
    # M = masculino, F = femenino
    sexo               = models.CharField(max_length=1, blank=True)
    es_activo          = models.BooleanField(default=True, db_index=True)
    actualizado_en     = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'dashboard_rotacion_dato'
        indexes = [
            models.Index(fields=['es_activo', 'co_codigo']),
            models.Index(fields=['fecha_retiro', 'co_codigo']),
            models.Index(fields=['cedula', 'es_activo']),
        ]

    def __str__(self):
        estado = 'Activo' if self.es_activo else f'Retirado {self.fecha_retiro}'
        return f"{self.cedula} | {self.cargo} | {estado}"
