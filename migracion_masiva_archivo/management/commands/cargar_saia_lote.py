import os

from django.core.management.base import BaseCommand, CommandError

from migracion_masiva_archivo.services.saia.batch_service import cargar_lote_saia
from migracion_masiva_archivo.services.saia.exceptions import SAIAError


class Command(BaseCommand):
    help = (
        'Fase 4: carga masiva controlada de documentos en SAIA. '
        'Requiere carga individual validada previamente.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--lote', type=int, required=True,
                            help='ID del lote documental a procesar.')
        parser.add_argument('--limite', type=int, default=10,
                            help='Maximo de documentos a procesar en este ciclo (default: 10).')
        parser.add_argument('--dry-run', action='store_true',
                            help='Navega y llena el formulario pero no confirma la carga.')
        parser.add_argument('--headful', action='store_true',
                            help='Muestra el navegador durante el proceso.')
        parser.add_argument('--pausa', type=int, default=3,
                            help='Segundos de espera entre cargas (default: 3).')

    def handle(self, *args, **options):
        os.environ.setdefault('DJANGO_ALLOW_ASYNC_UNSAFE', 'true')

        lote_id = options['lote']
        dry_run = options['dry_run']
        limite = options['limite']

        self.stdout.write(
            f'Iniciando carga masiva SAIA | lote={lote_id} | limite={limite} '
            f'| dry_run={dry_run} | headful={options["headful"]}'
        )

        try:
            resumen = cargar_lote_saia(
                lote_id=lote_id,
                limite=limite,
                dry_run=dry_run,
                headful=options['headful'],
                pausa_entre=options['pausa'],
            )
        except SAIAError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(self.style.SUCCESS(
            f'\nResumen lote {lote_id}:'
            f'\n  Total evaluados : {resumen["total"]}'
            f'\n  Exitosos        : {resumen["exitosos"]}'
            f'\n  Fallidos        : {resumen["fallidos"]}'
            f'\n  Omitidos        : {resumen["omitidos"]}'
        ))

        if resumen.get('error_critico'):
            self.stdout.write(self.style.ERROR(
                f'Error critico detuvo el lote: {resumen["error_critico"]}'
            ))

        for detalle in resumen['detalles']:
            estado = 'OK' if detalle['exitoso'] else ('OMITIDO' if detalle.get('omitido') else 'FALLO')
            linea = (
                f'  [{estado}] doc={detalle["documento_id"]} '
                f'asunto={detalle.get("asunto_saia", "?")} '
                f'intento={detalle.get("intento_id", "-")}'
            )
            if detalle.get('id_documento_saia'):
                linea += f' saia_id={detalle["id_documento_saia"]}'
            if detalle.get('error'):
                linea += f' error={detalle["error"][:120]}'
            self.stdout.write(linea)


