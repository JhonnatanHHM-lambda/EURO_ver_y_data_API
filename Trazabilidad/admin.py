from django.contrib import admin
from .models import Sede, EmpleadoTrazabilidad, CargaExcel


@admin.register(Sede)
class SedeAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'ciudad', 'codigo', 'estado')
    list_filter = ('estado', 'ciudad')
    search_fields = ('nombre', 'codigo', 'ciudad')


@admin.register(EmpleadoTrazabilidad)
class EmpleadoAdmin(admin.ModelAdmin):
    list_display = ('nombre_completo', 'documento_id', 'sede', 'origen_datos', 'tipo_proceso', 'estado_candidato')
    list_filter = ('origen_datos', 'estado_candidato', 'tipo_proceso', 'sede')
    search_fields = ('nombre_completo', 'documento_id', 'cargo')
    raw_id_fields = ('sede', 'cargado_por')


@admin.register(CargaExcel)
class CargaExcelAdmin(admin.ModelAdmin):
    list_display = ('nombre_archivo', 'sede', 'origen_datos', 'exitosos', 'fallidos', 'creado')
    list_filter = ('sede', 'origen_datos')
    readonly_fields = ('errores',)
