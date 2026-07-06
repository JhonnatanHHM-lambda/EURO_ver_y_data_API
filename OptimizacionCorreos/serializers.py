from rest_framework import serializers
from .models import EjecucionConsolidacion, ResultadoConciliacion


class EjecucionConsolidacionListSerializer(serializers.ModelSerializer):
    iniciada_por_nombre = serializers.SerializerMethodField()

    class Meta:
        model = EjecucionConsolidacion
        fields = [
            'id', 'fecha_desde', 'fecha_hasta', 'estado',
            'iniciada_en', 'completada_en',
            'total_radian', 'total_correo', 'total_conciliadas',
            'total_solo_radian', 'total_solo_correo', 'total_revision',
            'iniciada_por_nombre', 'creado',
        ]

    def get_iniciada_por_nombre(self, obj):
        if obj.iniciada_por:
            return obj.iniciada_por.obtener_nombre_completo()
        return None


class EjecucionConsolidacionDetalleSerializer(serializers.ModelSerializer):
    iniciada_por_nombre = serializers.SerializerMethodField()

    class Meta:
        model = EjecucionConsolidacion
        fields = [
            'id', 'fecha_desde', 'fecha_hasta', 'estado',
            'iniciada_en', 'completada_en',
            'total_radian', 'total_correo', 'total_conciliadas',
            'total_solo_radian', 'total_solo_correo', 'total_revision',
            'error_mensaje', 'iniciada_por_nombre', 'creado',
        ]

    def get_iniciada_por_nombre(self, obj):
        if obj.iniciada_por:
            return obj.iniciada_por.obtener_nombre_completo()
        return None


class ResultadoConciliacionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ResultadoConciliacion
        fields = [
            'id', 'cufe', 'numero', 'nit_proveedor', 'nombre_proveedor',
            'monto_radian', 'monto_correo', 'delta_monto',
            'fecha_radian', 'fecha_correo', 'asunto_correo',
            'estado', 'nivel_match',
        ]
