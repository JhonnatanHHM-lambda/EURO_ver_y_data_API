from django.contrib.auth.models import Group, Permission
from rest_framework import serializers
from .models import Usuario


class PermisosSerializer(serializers.ModelSerializer):
    class Meta:
        model = Permission
        fields = ['id', 'codename', 'name', 'content_type']


class GrupoListSerializer(serializers.ModelSerializer):
    total_usuarios = serializers.SerializerMethodField()
    permisos = serializers.SerializerMethodField()

    class Meta:
        model = Group
        fields = ['id', 'name', 'total_usuarios', 'permisos']

    def get_total_usuarios(self, obj):
        return obj.user_set.filter(estado=True).count()

    def get_permisos(self, obj):
        return list(obj.permissions.values_list('codename', flat=True))


class GrupoCreateSerializer(serializers.ModelSerializer):
    permisos = serializers.ListField(
        child=serializers.CharField(), required=False, write_only=True
    )

    class Meta:
        model = Group
        fields = ['name', 'permisos']

    def validate_name(self, value):
        if Group.objects.filter(name=value).exists():
            raise serializers.ValidationError('Ya existe un rol con ese nombre.')
        return value

    def create(self, validated_data):
        permisos_codenames = validated_data.pop('permisos', [])
        grupo = Group.objects.create(**validated_data)
        if permisos_codenames:
            perms = Permission.objects.filter(codename__in=permisos_codenames)
            grupo.permissions.set(perms)
        return grupo


class GrupoUpdateSerializer(serializers.ModelSerializer):
    permisos = serializers.ListField(
        child=serializers.CharField(), required=False, write_only=True
    )

    class Meta:
        model = Group
        fields = ['name', 'permisos']

    def update(self, instance, validated_data):
        permisos_codenames = validated_data.pop('permisos', None)
        instance.name = validated_data.get('name', instance.name)
        instance.save()
        if permisos_codenames is not None:
            perms = Permission.objects.filter(codename__in=permisos_codenames)
            instance.permissions.set(perms)
        return instance


class UsuarioListSerializer(serializers.ModelSerializer):
    rol = serializers.CharField(source='rol_principal', read_only=True)
    nombre_completo = serializers.CharField(source='obtener_nombre_completo', read_only=True)
    permisos_rol = serializers.SerializerMethodField()
    grupos = serializers.SerializerMethodField()

    class Meta:
        model = Usuario
        fields = [
            'id', 'cedula', 'correo', 'nombres', 'apellidos', 'nombre_completo',
            'genero', 'codigo', 'telefono', 'fecha_nacimiento',
            'rol', 'grupos', 'permisos_rol', 'estado', 'is_active', 'is_superuser',
            'creado', 'modificado',
        ]
        read_only_fields = ['codigo', 'creado', 'modificado']

    TODOS_LOS_PERMISOS = [
        'add_group', 'change_group', 'delete_group', 'view_group',
        'can_manage_users', 'can_manage_roles',
        'can_view_dashboard', 'can_upload_excel', 'can_view_trazabilidad',
        'can_manage_sedes',
        'can_manage_cargas',
    ]

    def get_permisos_rol(self, obj):
        if obj.is_superuser:
            return self.TODOS_LOS_PERMISOS
        perms = set()
        for group in obj.groups.all():
            for perm in group.permissions.all():
                perms.add(perm.codename)
        return list(perms)

    def get_grupos(self, obj):
        return list(obj.groups.values_list('name', flat=True))


class UsuarioCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    grupos = serializers.SlugRelatedField(
        many=True, slug_field='name',
        queryset=Group.objects.all(), required=False
    )

    class Meta:
        model = Usuario
        fields = ['cedula', 'correo', 'nombres', 'apellidos', 'genero',
                  'telefono', 'fecha_nacimiento', 'password', 'grupos']

    def validate_correo(self, value):
        if Usuario.objects.filter(correo=value).exists():
            raise serializers.ValidationError('Ya existe un usuario con ese correo.')
        return value

    def validate_cedula(self, value):
        if Usuario.objects.filter(cedula=value).exists():
            raise serializers.ValidationError('Ya existe un usuario con esa cédula.')
        return value

    def create(self, validated_data):
        grupos = validated_data.pop('grupos', [])
        password = validated_data.pop('password')
        user = Usuario(**validated_data)
        user.set_password(password)
        user.save()
        if grupos:
            user.groups.set(grupos)
        return user


class UsuarioUpdateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8, required=False, allow_blank=True)
    grupos   = serializers.SlugRelatedField(
        many=True, slug_field='name',
        queryset=Group.objects.all(), required=False
    )

    class Meta:
        model = Usuario
        fields = ['cedula', 'correo', 'nombres', 'apellidos', 'genero',
                  'telefono', 'fecha_nacimiento', 'estado', 'is_active',
                  'password', 'grupos']

    def validate_correo(self, value):
        qs = Usuario.objects.filter(correo=value).exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError('Ya existe un usuario con ese correo.')
        return value

    def validate_cedula(self, value):
        qs = Usuario.objects.filter(cedula=value).exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError('Ya existe un usuario con esa cédula.')
        return value

    def update(self, instance, validated_data):
        grupos   = validated_data.pop('grupos', None)
        password = validated_data.pop('password', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        instance.save()
        if grupos is not None:
            instance.groups.set(grupos)
        return instance


class CambiarPasswordSerializer(serializers.Serializer):
    password_actual = serializers.CharField(write_only=True)
    password_nuevo = serializers.CharField(write_only=True, min_length=8)

    def validate_password_actual(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError('La contraseña actual es incorrecta.')
        return value
