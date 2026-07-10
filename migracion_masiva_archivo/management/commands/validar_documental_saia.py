from django.core.management.base import BaseCommand, CommandError

from migracion_masiva_archivo.models import DocumentoDigitalizado, LoteDocumental
from migracion_masiva_archivo.services.saia.validation_service import (
    validate_document_for_saia,
    validate_lote_for_saia,
)


class Command(BaseCommand):
    help = 'Valida localmente documentos antes de abrir SAIA o intentar cargarlos.'

    def add_arguments(self, parser):
        target = parser.add_mutually_exclusive_group(required=True)
        target.add_argument('--lote', type=int)
        target.add_argument('--documento', type=int)
        parser.add_argument('--solo-listos', action='store_true')
        parser.add_argument('--limite', type=int, default=50)

    def handle(self, *args, **options):
        if options.get('documento'):
            result = validate_document_for_saia(self._get_documento(options['documento']))
            self._print_result(result)
            if not result['listo_para_saia']:
                raise CommandError('Documento no esta listo para SAIA.')
            return

        lote = self._get_lote(options['lote'])
        results = validate_lote_for_saia(lote, solo_listos=options['solo_listos'])
        ready = sum(1 for result in results if result['listo_para_saia'])
        blocked = len(results) - ready

        self.stdout.write(self.style.SUCCESS(f'Lote validado localmente: {lote.id} - {lote.nombre}'))
        self.stdout.write(f'Documentos evaluados: {len(results)}')
        self.stdout.write(f'Listos para SAIA: {ready}')
        self.stdout.write(f'Bloqueados: {blocked}')

        for result in results[: options['limite']]:
            self._print_result(result)

    def _print_result(self, result):
        status = 'LISTO' if result['listo_para_saia'] else 'BLOQUEADO'
        self.stdout.write(
            f'[{status}] {result["documento_id"]} | {result["nombre_archivo"]} | '
            f'{result["asunto_saia"] or "Sin asunto SAIA"}'
        )
        for error in result['errores']:
            self.stdout.write(f'  ERROR: {error}')
        for warning in result['advertencias']:
            self.stdout.write(f'  ADVERTENCIA: {warning}')

    def _get_lote(self, lote_id):
        try:
            return LoteDocumental.objects.get(pk=lote_id)
        except LoteDocumental.DoesNotExist as exc:
            raise CommandError(f'No existe el lote {lote_id}') from exc

    def _get_documento(self, documento_id):
        try:
            return DocumentoDigitalizado.objects.select_related('metadata').get(pk=documento_id)
        except DocumentoDigitalizado.DoesNotExist as exc:
            raise CommandError(f'No existe el documento {documento_id}') from exc


