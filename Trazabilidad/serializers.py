from rest_framework import serializers
from .models import Sede, Origen, EmpleadoTrazabilidad, CargaExcel


class SedeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Sede
        fields = ['id', 'nombre', 'ciudad', 'codigo', 'estado']


class SedeAdminSerializer(serializers.ModelSerializer):
    total_cargas = serializers.SerializerMethodField()

    def get_total_cargas(self, obj):
        return CargaExcel.objects.filter(sede=obj).count()

    class Meta:
        model = Sede
        fields = ['id', 'nombre', 'ciudad', 'codigo', 'estado', 'total_cargas']


class OrigenSerializer(serializers.ModelSerializer):
    total_cargas = serializers.SerializerMethodField()

    def get_total_cargas(self, obj):
        return CargaExcel.objects.filter(origen_datos__iexact=obj.nombre).count()

    class Meta:
        model = Origen
        fields = ['id', 'nombre', 'descripcion', 'estado', 'total_cargas']


class EmpleadoListSerializer(serializers.ModelSerializer):
    sede_nombre = serializers.CharField(source='sede.nombre', read_only=True, allow_null=True)
    sede_ciudad = serializers.CharField(source='sede.ciudad', read_only=True, allow_null=True)

    class Meta:
        model = EmpleadoTrazabilidad
        fields = [
            'id', 'documento_id', 'tipo_documento', 'nombre_completo',
            'origen_datos', 'estado_candidato', 'tipo_proceso',
            'sede', 'sede_nombre', 'sede_ciudad',
            'cargo', 'fecha_ingreso', 'fecha_retiro', 'motivo_retiro',
            'celular', 'email', 'observaciones', 'psicologa',
            'fecha_entrevista', 'fuente_carga', 'creado',
            'tipo_sangre', 'nivel_escolaridad', 'fecha_nacimiento', 'sexo',
            'expedida_en', 'barrio_municipio', 'direccion', 'centro_costos',
            'eps', 'pensiones', 'arl',
        ]


class EmpleadoDetalleSerializer(serializers.ModelSerializer):
    sede_nombre = serializers.CharField(source='sede.nombre', read_only=True, allow_null=True)
    cargado_por_nombre = serializers.CharField(
        source='cargado_por.obtener_nombre_completo', read_only=True, allow_null=True
    )

    class Meta:
        model = EmpleadoTrazabilidad
        fields = '__all__'


class CargaExcelSerializer(serializers.ModelSerializer):
    sede_nombre = serializers.CharField(source='sede.nombre', read_only=True, allow_null=True)
    cargado_por_nombre = serializers.CharField(
        source='cargado_por.obtener_nombre_completo', read_only=True, allow_null=True
    )

    class Meta:
        model = CargaExcel
        fields = [
            'id', 'sede', 'sede_nombre', 'nombre_archivo', 'hoja', 'origen_datos',
            'total_registros', 'exitosos', 'fallidos', 'errores',
            'cargado_por', 'cargado_por_nombre', 'creado', 'estado',
            'firma_gh_nombre', 'firma_gh_cargo', 'firma_gh_fecha',
        ]
