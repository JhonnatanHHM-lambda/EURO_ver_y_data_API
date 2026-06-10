from rest_framework import serializers
from .models import Contrato, DocumentoAdicional, EventoContrato, AsignacionCentro


class DocumentoAdicionalSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentoAdicional
        fields = ['id', 'nombre_archivo', 'creado']


class EventoContratoSerializer(serializers.ModelSerializer):
    class Meta:
        model = EventoContrato
        fields = ['id', 'tipo_evento', 'timestamp', 'ip', 'detalle']


class ContratoSerializer(serializers.ModelSerializer):
    documentos_adicionales = DocumentoAdicionalSerializer(many=True, read_only=True)
    eventos = EventoContratoSerializer(many=True, read_only=True)
    sede_nombre = serializers.CharField(source='sede.nombre', read_only=True)
    sede_codigo = serializers.CharField(source='sede.codigo', read_only=True)

    class Meta:
        model = Contrato
        fields = [
            'id', 'tipo_documento', 'documento_id', 'nombre_completo', 'cargo',
            'fecha_finalizacion', 'tipo_carta', 'estado', 'celular', 'email',
            'fecha_primer_envio', 'fecha_firma', 'contador_escalamientos',
            'duracion_prorroga', 'fecha_fin_prorroga', 'sede', 'sede_nombre', 'sede_codigo',
            'token_usado', 'creado',
            'documentos_adicionales', 'eventos',
        ]


class AsignacionCentroSerializer(serializers.ModelSerializer):
    usuario_nombre = serializers.CharField(source='usuario.nombre_completo_display', read_only=True)
    usuario_correo = serializers.CharField(source='usuario.correo', read_only=True)
    sede_nombre = serializers.CharField(source='sede.nombre', read_only=True)
    sede_codigo = serializers.CharField(source='sede.codigo', read_only=True)

    class Meta:
        model = AsignacionCentro
        fields = ['id', 'usuario', 'usuario_nombre', 'usuario_correo', 'sede', 'sede_nombre', 'sede_codigo', 'rol', 'activo']
