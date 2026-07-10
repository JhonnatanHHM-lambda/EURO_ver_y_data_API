from django.contrib import admin

from .models import (
    DocumentoDigitalizado,
    IntentoCargaSAIA,
    LogProcesoDocumental,
    LoteDocumental,
    MetadataDocumento,
    RelacionDocumento,
)


@admin.register(LoteDocumental)
class LoteDocumentalAdmin(admin.ModelAdmin):
    list_display = ('id', 'nombre', 'estado_proceso', 'total_archivos', 'total_revision', 'creado')
    list_filter = ('estado_proceso', 'creado')
    search_fields = ('nombre', 'carpeta_origen')
    readonly_fields = ('creado', 'modificado')


@admin.register(DocumentoDigitalizado)
class DocumentoDigitalizadoAdmin(admin.ModelAdmin):
    list_display = ('id', 'nombre_archivo', 'extension', 'estado_proceso', 'es_pdf', 'requiere_ocr')
    list_filter = ('estado_proceso', 'extension', 'es_pdf', 'requiere_ocr')
    search_fields = ('nombre_archivo', 'ruta_archivo', 'hash_archivo')
    readonly_fields = ('creado', 'modificado')


@admin.register(MetadataDocumento)
class MetadataDocumentoAdmin(admin.ModelAdmin):
    list_display = ('id', 'documento', 'nit', 'consecutivo', 'tipo_documento', 'requiere_revision')
    list_filter = ('tipo_documento', 'requiere_revision', 'normalizado')
    search_fields = ('documento__nombre_archivo', 'nit', 'proveedor', 'consecutivo')
    readonly_fields = ('creado', 'modificado', 'datos_pel')


@admin.register(RelacionDocumento)
class RelacionDocumentoAdmin(admin.ModelAdmin):
    list_display = ('id', 'documento_principal', 'documento_relacionado', 'tipo_relacion', 'confianza')
    list_filter = ('tipo_relacion', 'validado_manualmente')
    search_fields = ('documento_principal__nombre_archivo', 'documento_relacionado__nombre_archivo')


@admin.register(IntentoCargaSAIA)
class IntentoCargaSAIAAdmin(admin.ModelAdmin):
    list_display = ('id', 'documento', 'numero_intento', 'status_code', 'exitoso', 'creado')
    list_filter = ('exitoso', 'status_code', 'creado')
    search_fields = ('documento__nombre_archivo', 'id_documento_saia', 'usuario_saia')


@admin.register(LogProcesoDocumental)
class LogProcesoDocumentalAdmin(admin.ModelAdmin):
    list_display = ('id', 'nivel', 'evento', 'lote', 'documento', 'creado')
    list_filter = ('nivel', 'evento', 'creado')
    search_fields = ('evento', 'mensaje', 'documento__nombre_archivo', 'lote__nombre')


