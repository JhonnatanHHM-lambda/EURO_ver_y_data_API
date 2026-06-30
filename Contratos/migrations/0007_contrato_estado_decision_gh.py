from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('Contratos', '0006_firma_gh_provisional_registro'),
    ]

    operations = [
        migrations.AlterField(
            model_name='contrato',
            name='estado',
            field=models.CharField(
                max_length=40,
                default='PENDIENTE_FIRMA_NO_PRORROGA',
                choices=[
                    ('PENDIENTE_FIRMA_NO_PRORROGA', 'Pendiente firma — no prórroga'),
                    ('PENDIENTE_DECISION_DIRECTOR', 'Pendiente decisión director'),
                    ('PENDIENTE_DECISION_GH', 'Pendiente decisión GH'),
                    ('PENDIENTE_CONDICIONES_GH', 'Pendiente condiciones GH'),
                    ('PENDIENTE_NOTIFICACION_EMPLEADO', 'Pendiente notificación empleado'),
                    ('PENDIENTE_FIRMA_PRORROGA', 'Pendiente firma — prórroga'),
                    ('PENDIENTE_FIRMA_TERMINACION', 'Pendiente firma — terminación'),
                    ('FIRMADO', 'Firmado'),
                    ('SIN_CANAL_CONTACTO', 'Sin canal de contacto'),
                    ('ERROR_NOTIFICACION', 'Error de notificación'),
                    ('CANCELADO', 'Cancelado'),
                ],
            ),
        ),
    ]
