from django.core.management.base import BaseCommand, CommandError

from migracion_masiva_archivo.services.saia.exceptions import SAIAError
from migracion_masiva_archivo.services.saia.upload_service import probar_carga_documento_saia


class Command(BaseCommand):
    help = 'Ejecuta Fase 4: prueba controlada de carga de un documento en SAIA.'

    def add_arguments(self, parser):
        parser.add_argument('--documento-id', type=int, required=True)
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--confirmar-carga', action='store_true')
        parser.add_argument('--headful', action='store_true')
        parser.add_argument(
            '--adjuntar-en-dry-run',
            action='store_true',
            help='Adjunta el archivo en dry-run, pero no confirma la carga final.',
        )

    def handle(self, *args, **options):
        confirmar_carga = options['confirmar_carga']
        dry_run = not confirmar_carga or options['dry_run']

        if confirmar_carga and options['dry_run']:
            raise CommandError('No combines --dry-run con --confirmar-carga.')

        try:
            intento = probar_carga_documento_saia(
                documento_id=options['documento_id'],
                dry_run=dry_run,
                headful=options['headful'],
                confirmar_carga=confirmar_carga,
                adjuntar_en_dry_run=options['adjuntar_en_dry_run'],
            )
        except SAIAError as exc:
            raise CommandError(str(exc)) from exc

        estado = 'exitoso' if intento.exitoso else 'registrado sin carga exitosa'
        self.stdout.write(self.style.SUCCESS(f'Intento SAIA {intento.id} {estado}.'))
        self.stdout.write(f'Documento: {intento.documento_id}')
        self.stdout.write(f'URL final: {intento.endpoint or "No disponible"}')


