from rest_framework import serializers
from .models import Contrato, DocumentoAdicional, EventoContrato, AsignacionCentro


class ContratoListSerializer(serializers.ModelSerializer):
    """Serializer ligero para la vista de lista: sin URLs presignadas, sin sub-serializadores."""
    sede_nombre           = serializers.CharField(source='sede.nombre', read_only=True)
    sede_codigo           = serializers.CharField(source='sede.codigo', read_only=True)
    dias_alerta_director  = serializers.IntegerField(source='sede.dias_alerta_director', read_only=True, allow_null=True)

    class Meta:
        model = Contrato
        fields = [
            'id', 'tipo_documento', 'documento_id', 'nombre_completo', 'cargo', 'email',
            'fecha_finalizacion', 'tipo_carta', 'estado',
            'sede_nombre', 'sede_codigo', 'dias_alerta_director',
            'fecha_primer_envio', 'contador_escalamientos', 'no_prorroga_firmada',
        ]


class DocumentoAdicionalSerializer(serializers.ModelSerializer):
    url               = serializers.SerializerMethodField()
    es_carta_firmada  = serializers.SerializerMethodField()

    def get_url(self, obj):
        if not obj.minio_key:
            return None
        try:
            from .utils.minio_client import generate_presigned_url
            return generate_presigned_url(obj.minio_key, expires_seconds=300)
        except Exception:
            return None

    def get_es_carta_firmada(self, obj):
        """True si fue generado automáticamente por el sistema (carta firmada de ciclo anterior)."""
        return obj.subido_por_id is None

    class Meta:
        model = DocumentoAdicional
        fields = ['id', 'nombre_archivo', 'creado', 'url', 'es_carta_firmada']


class EventoContratoSerializer(serializers.ModelSerializer):
    class Meta:
        model = EventoContrato
        fields = ['id', 'tipo_evento', 'timestamp', 'ip', 'detalle']


class ContratoSerializer(serializers.ModelSerializer):
    documentos_adicionales = DocumentoAdicionalSerializer(many=True, read_only=True)
    eventos = EventoContratoSerializer(many=True, read_only=True)
    sede_nombre          = serializers.CharField(source='sede.nombre', read_only=True)
    sede_codigo          = serializers.CharField(source='sede.codigo', read_only=True)
    dias_alerta_director = serializers.IntegerField(source='sede.dias_alerta_director', read_only=True, allow_null=True)
    pdf_firmado_url       = serializers.SerializerMethodField()
    pdf_carta_url         = serializers.SerializerMethodField()
    pdf_no_prorroga_url   = serializers.SerializerMethodField()
    documentos_historicos = serializers.SerializerMethodField()

    def get_pdf_firmado_url(self, obj):
        if not obj.pdf_firmado_key:
            return None
        try:
            from .utils.minio_client import generate_presigned_url
            return generate_presigned_url(obj.pdf_firmado_key, expires_seconds=300)
        except Exception:
            return None

    def get_pdf_carta_url(self, obj):
        """URL de la carta sin firma. Visible mientras el empleado no haya firmado,
        independientemente del estado (incluyendo PENDIENTE_DECISION_DIRECTOR cuando
        el director fue alertado antes de que el empleado firmara)."""
        if not obj.pdf_carta_key:
            return None
        if obj.pdf_firmado_key:
            return None
        try:
            from .utils.minio_client import generate_presigned_url
            return generate_presigned_url(obj.pdf_carta_key, expires_seconds=300)
        except Exception:
            return None

    def get_pdf_no_prorroga_url(self, obj):
        """URL de la carta de no prórroga original, visible solo cuando hay firma secuencial pendiente."""
        if obj.no_prorroga_firmada or not obj.pdf_no_prorroga_key:
            return None
        try:
            from .utils.minio_client import generate_presigned_url
            return generate_presigned_url(obj.pdf_no_prorroga_key, expires_seconds=300)
        except Exception:
            return None

    def get_documentos_historicos(self, obj):
        from .utils.minio_client import generate_presigned_url
        TIPOS = {'NO_PRORROGA': 'No prórroga', 'PRORROGA': 'Prórroga', 'TERMINACION': 'Terminación'}
        qs = Contrato.objects.filter(
            documento_id=obj.documento_id,
            estado='FIRMADO',
        ).exclude(pk=obj.pk).order_by('-fecha_firma')
        result = []
        for c in qs:
            # Preferir PDF con firma incrustada; si no existe, usar la carta original
            key = c.pdf_firmado_key or c.pdf_carta_key
            if not key:
                continue
            try:
                url = generate_presigned_url(key, expires_seconds=300)
                result.append({
                    'id':                c.id,
                    'tipo_carta':        c.tipo_carta,
                    'tipo_carta_label':  TIPOS.get(c.tipo_carta, c.tipo_carta),
                    'fecha_finalizacion': str(c.fecha_finalizacion),
                    'fecha_firma':       c.fecha_firma.isoformat() if c.fecha_firma else None,
                    'url':               url,
                    'con_firma':         bool(c.pdf_firmado_key),
                })
            except Exception:
                pass
        return result

    class Meta:
        model = Contrato
        fields = [
            'id', 'tipo_documento', 'documento_id', 'nombre_completo', 'cargo',
            'fecha_finalizacion', 'tipo_carta', 'estado', 'celular', 'email',
            'fecha_primer_envio', 'fecha_firma', 'contador_escalamientos',
            'duracion_prorroga', 'mantener_condiciones', 'nuevo_sueldo', 'fecha_fin_prorroga',
            'sede', 'sede_nombre', 'sede_codigo',
            'token_usado', 'creado', 'ip_confirmacion',
            'no_prorroga_firmada', 'dias_alerta_director',
            'documentos_adicionales', 'eventos',
            'pdf_firmado_url', 'pdf_carta_url', 'pdf_no_prorroga_url', 'documentos_historicos',
        ]


class AsignacionCentroSerializer(serializers.ModelSerializer):
    usuario_nombre = serializers.CharField(source='usuario.nombre_completo_display', read_only=True)
    usuario_correo = serializers.CharField(source='usuario.correo', read_only=True)
    sede_nombre = serializers.CharField(source='sede.nombre', read_only=True)
    sede_codigo = serializers.CharField(source='sede.codigo', read_only=True)

    class Meta:
        model = AsignacionCentro
        fields = ['id', 'usuario', 'usuario_nombre', 'usuario_correo', 'sede', 'sede_nombre', 'sede_codigo', 'rol', 'activo']
