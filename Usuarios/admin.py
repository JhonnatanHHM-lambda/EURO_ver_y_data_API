from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Usuario, OTPVerificacion


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    list_display = ('correo', 'nombres', 'apellidos', 'rol_principal', 'is_active', 'creado')
    list_filter = ('is_active', 'groups')
    search_fields = ('correo', 'nombres', 'apellidos', 'cedula')
    ordering = ('correo',)
    fieldsets = (
        (None, {'fields': ('correo', 'password')}),
        ('Información personal', {'fields': ('cedula', 'nombres', 'apellidos', 'genero', 'telefono', 'fecha_nacimiento')}),
        ('Permisos', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('correo', 'cedula', 'nombres', 'apellidos', 'password1', 'password2'),
        }),
    )


@admin.register(OTPVerificacion)
class OTPVerificacionAdmin(admin.ModelAdmin):
    list_display = ('usuario', 'codigo', 'expira_en', 'usado', 'creado')
    list_filter = ('usado',)
    readonly_fields = ('codigo', 'expira_en', 'creado')
