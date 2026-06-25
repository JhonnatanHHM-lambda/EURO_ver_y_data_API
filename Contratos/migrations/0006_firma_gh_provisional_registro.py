from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('Contratos', '0005_firma_secuencial_no_prorroga'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='FirmaGH',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('firma_imagen', models.TextField(verbose_name='Imagen firma (base64)')),
                ('habilitada', models.BooleanField(default=True, verbose_name='Habilitada para uso')),
                ('creado', models.DateTimeField(auto_now_add=True)),
                ('actualizado', models.DateTimeField(auto_now=True)),
                ('usuario', models.OneToOneField(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='firma_gh',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Usuario GH',
                )),
            ],
            options={'db_table': 'contratos_firma_gh', 'verbose_name': 'Firma GH'},
        ),
        migrations.CreateModel(
            name='FirmaProvisional',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('firma_imagen', models.TextField(verbose_name='Imagen firma (base64)')),
                ('creado', models.DateTimeField(auto_now_add=True)),
                ('actualizado', models.DateTimeField(auto_now=True)),
                ('usuario', models.OneToOneField(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='firma_provisional',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Usuario provisional',
                )),
                ('autorizado_por', models.ForeignKey(
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='firmas_provisionales_autorizadas',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Autorizado por',
                )),
            ],
            options={'db_table': 'contratos_firma_provisional', 'verbose_name': 'Firma provisional'},
        ),
        migrations.CreateModel(
            name='RegistroFirmaEmpleador',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('tipo_carta', models.CharField(max_length=20)),
                ('nombre_empleador', models.CharField(max_length=200)),
                ('cedula_empleador', models.CharField(max_length=30)),
                ('firma_imagen_snapshot', models.TextField()),
                ('es_provisional', models.BooleanField(default=False)),
                ('fecha_generacion', models.DateTimeField(auto_now_add=True)),
                ('contrato', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='registros_firma_empleador',
                    to='Contratos.contrato',
                )),
                ('usuario_empleador', models.ForeignKey(
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='documentos_como_empleador',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'db_table': 'contratos_registro_firma_empleador',
                'verbose_name': 'Registro firma empleador',
                'ordering': ['-fecha_generacion'],
            },
        ),
    ]
