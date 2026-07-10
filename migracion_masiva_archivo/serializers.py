from pathlib import Path

from django.conf import settings
from rest_framework import serializers

from .models import DocumentoDigitalizado, LogProcesoDocumental, LoteDocumental
from .services.error_message_service import get_blocking_phase_error


class DocumentoDigitalizadoSerializer(serializers.ModelSerializer):
    nombre_original = serializers.CharField(source='nombre_archivo', read_only=True)
    resultado = serializers.SerializerMethodField()
    url = serializers.SerializerMethodField()

    class Meta:
        model = DocumentoDigitalizado
        fields = [
            'id', 'nombre_original', 'extension', 'peso_bytes', 'hash_archivo',
            'estado_proceso', 'resultado', 'error', 'url', 'creado', 'modificado',
        ]
        read_only_fields = fields

    def get_resultado(self, obj):
        metadata = {}
        try:
            meta = obj.metadata
            metadata = {
                'nit': meta.nit,
                'proveedor': meta.proveedor,
                'consecutivo': meta.consecutivo,
                'fecha_documento': meta.fecha_documento,
                'tipo_documento': meta.tipo_documento,
                'valor': meta.valor,
                'medio_pago': meta.medio_pago,
                'cruce': meta.cruce,
                'referencia_pago': meta.referencia_pago,
                'confianza': meta.confianza,
                'requiere_revision': meta.requiere_revision,
                'observaciones': meta.observaciones,
                'datos_pel': meta.datos_pel,
            }
        except Exception:
            pass

        mensaje_analista, accion_sugerida, fase_error, codigo_error_usuario = '', '', '', ''
        if obj.error or obj.estado_proceso in {'REQUIERE_REVISION', 'ERROR_SAIA'}:
            payload = get_blocking_phase_error(obj)
            if payload:
                mensaje_analista = payload.get('mensaje_usuario', '')
                accion_sugerida = payload.get('accion_recomendada', '')
                fase_error = payload.get('fase_error', '')
                codigo_error_usuario = payload.get('codigo_error_usuario', '')
            elif obj.error:
                mensaje_analista = obj.error

        intentos_saia = [
            {
                'numero_intento': intento.numero_intento,
                'exitoso': intento.exitoso,
                'mensaje_error': intento.mensaje_error,
                'creado': intento.creado,
                'id_documento_saia': intento.id_documento_saia,
                'usuario_saia': intento.usuario_saia,
            }
            for intento in obj.intentos_saia.order_by('-creado')[:5]
        ]

        return {
            'es_pdf': obj.es_pdf,
            'es_digital': obj.es_digital,
            'requiere_ocr': obj.requiere_ocr,
            'ocr_agotado': obj.ocr_agotado,
            'es_soportado': obj.es_soportado,
            'es_duplicado': obj.es_duplicado,
            'marcado_ok': obj.marcado_ok,
            'metadata': metadata,
            'mensaje_analista': mensaje_analista,
            'accion_sugerida': accion_sugerida,
            'fase_error': fase_error,
            'codigo_error_usuario': codigo_error_usuario,
            'intentos_saia': intentos_saia,
        }

    def get_url(self, obj):
        ruta = Path(obj.ruta_archivo or '')
        media_root = Path(settings.MEDIA_ROOT).resolve()
        try:
            relative = ruta.resolve().relative_to(media_root)
        except Exception:
            return ''
        url = f'{settings.MEDIA_URL}{relative.as_posix()}'
        request = self.context.get('request')
        return request.build_absolute_uri(url) if request else url


class LogProcesoDocumentalSerializer(serializers.ModelSerializer):
    archivo = serializers.IntegerField(source='documento_id', read_only=True)
    archivo_nombre = serializers.CharField(source='documento.nombre_archivo', read_only=True)

    class Meta:
        model = LogProcesoDocumental
        fields = [
            'id', 'nivel', 'evento', 'mensaje', 'detalle',
            'archivo', 'archivo_nombre', 'creado',
        ]
        read_only_fields = fields


class LoteDocumentalListSerializer(serializers.ModelSerializer):
    descripcion = serializers.CharField(source='observaciones', read_only=True)
    iniciado_por_nombre = serializers.CharField(source='iniciado_por', read_only=True)
    celery_task_id = serializers.SerializerMethodField()
    procesados = serializers.IntegerField(source='total_procesados', read_only=True)
    exitosos = serializers.IntegerField(source='total_exitosos', read_only=True)
    fallidos = serializers.IntegerField(source='total_fallidos', read_only=True)
    pendientes_revision = serializers.IntegerField(source='total_revision', read_only=True)
    error = serializers.SerializerMethodField()

    class Meta:
        model = LoteDocumental
        fields = [
            'id', 'nombre', 'descripcion', 'estado_proceso', 'iniciado_por',
            'iniciado_por_nombre', 'celery_task_id', 'total_archivos', 'procesados',
            'exitosos', 'fallidos', 'pendientes_revision', 'fecha_inicio',
            'fecha_fin', 'error', 'creado', 'modificado',
        ]
        read_only_fields = fields

    def get_celery_task_id(self, obj):
        ejecucion = obj.ejecuciones.order_by('-creado').first()
        return ejecucion.celery_task_id if ejecucion else ''

    def get_error(self, obj):
        ejecucion = obj.ejecuciones.order_by('-creado').first()
        return ejecucion.error if ejecucion else ''


class LoteDocumentalDetailSerializer(LoteDocumentalListSerializer):
    archivos = DocumentoDigitalizadoSerializer(source='documentos', many=True, read_only=True)
    logs = LogProcesoDocumentalSerializer(many=True, read_only=True)

    class Meta(LoteDocumentalListSerializer.Meta):
        fields = LoteDocumentalListSerializer.Meta.fields + ['archivos', 'logs']


class CargaMasivaArchivoCreateSerializer(serializers.Serializer):
    nombre = serializers.CharField(max_length=180)
    descripcion = serializers.CharField(required=False, allow_blank=True)
    archivos = serializers.ListField(
        child=serializers.FileField(),
        allow_empty=False,
        write_only=True,
    )
    archivos_secundarios = serializers.ListField(
        child=serializers.FileField(),
        required=False,
        write_only=True,
    )

    def validate_archivos(self, archivos):
        return self._validar_tamano(archivos)

    def validate_archivos_secundarios(self, archivos):
        return self._validar_tamano(archivos)

    def _validar_tamano(self, archivos):
        max_mb = self.context.get('max_upload_mb')
        if max_mb:
            max_bytes = max_mb * 1024 * 1024
            for archivo in archivos:
                if archivo.size > max_bytes:
                    raise serializers.ValidationError(
                        f'El archivo {archivo.name} supera el límite de {max_mb} MB.'
                    )
        return archivos


# Aliases para no cambiar el contrato interno de las vistas existentes.
ArchivoMigracionSerializer = DocumentoDigitalizadoSerializer
LogMigracionMasivaArchivoSerializer = LogProcesoDocumentalSerializer
CargaMasivaArchivoListSerializer = LoteDocumentalListSerializer
CargaMasivaArchivoDetailSerializer = LoteDocumentalDetailSerializer
