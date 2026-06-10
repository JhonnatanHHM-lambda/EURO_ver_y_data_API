from django.contrib import admin
from .models import Contrato, EventoContrato, DocumentoAdicional, PlantillaCarta, AsignacionCentro


@admin.register(Contrato)
class ContratoAdmin(admin.ModelAdmin):
    list_display = ['nombre_completo', 'documento_id', 'tipo_carta', 'estado', 'fecha_finalizacion', 'sede']
    list_filter = ['estado', 'tipo_carta', 'sede']
    search_fields = ['nombre_completo', 'documento_id']
    readonly_fields = ['token_firma', 'token_usado', 'creado', 'actualizado']


@admin.register(EventoContrato)
class EventoContratoAdmin(admin.ModelAdmin):
    list_display = ['contrato', 'tipo_evento', 'timestamp', 'ip']
    list_filter = ['tipo_evento']
    readonly_fields = ['timestamp']


@admin.register(AsignacionCentro)
class AsignacionCentroAdmin(admin.ModelAdmin):
    list_display = ['usuario', 'sede', 'rol', 'activo']
    list_filter = ['rol', 'activo', 'sede']
    search_fields = ['usuario__correo', 'usuario__nombres', 'sede__codigo', 'sede__nombre']


admin.site.register(DocumentoAdicional)
admin.site.register(PlantillaCarta)
