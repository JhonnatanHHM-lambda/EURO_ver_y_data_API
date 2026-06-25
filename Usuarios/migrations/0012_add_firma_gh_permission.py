from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('Usuarios', '0011_alter_usuario_options_alter_notificacionadmin_tipo'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='usuario',
            options={
                'verbose_name': 'Usuario',
                'verbose_name_plural': 'Usuarios',
                'permissions': [
                    ('can_manage_users', 'Puede gestionar usuarios'),
                    ('can_manage_roles', 'Puede gestionar roles y permisos'),
                    ('can_view_dashboard', 'Puede ver el dashboard'),
                    ('can_upload_excel', 'Puede subir archivos Excel'),
                    ('can_view_trazabilidad', 'Puede ver trazabilidad de empleados'),
                    ('can_manage_sedes', 'Puede gestionar sedes y orígenes de datos'),
                    ('can_edit_registros', 'Puede editar estado y proceso de registros de trazabilidad'),
                    ('can_manage_cargas', 'Puede ver historial de cargas y revertirlas'),
                    ('can_view_contratos', 'Puede ver el panel de vencimientos'),
                    ('can_decide_contratos', 'Puede tomar decisiones sobre vencimientos: prorrogar o terminar'),
                    ('can_set_condiciones_contratos', 'Puede definir condiciones de prórroga/terminación (rol GH)'),
                    ('can_escanear_siesa', 'Puede ejecutar consulta manual de contratos desde SIESA'),
                    ('can_manage_asignaciones', 'Puede gestionar asignaciones de director/GH a sedes'),
                    ('can_view_contrataciones', 'Puede ver el historial de contrataciones y documentos firmados'),
                    ('can_manage_firma_gh', 'Puede gestionar la firma digital del empleador'),
                ],
            },
        ),
    ]
