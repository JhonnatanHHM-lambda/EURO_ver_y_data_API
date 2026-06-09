from django.db import models


class BaseModel(models.Model):
    creado = models.DateTimeField(auto_now_add=True, verbose_name='Fecha de creación')
    modificado = models.DateTimeField(auto_now=True, verbose_name='Fecha de modificación')
    estado = models.BooleanField(default=True, verbose_name='Estado')

    class Meta:
        abstract = True

    @property
    def get_estado(self):
        return 'Activo' if self.estado else 'Inactivo'
