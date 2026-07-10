from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from migracion_masiva_archivo.models import DocumentoDigitalizado, LoteDocumental
from migracion_masiva_archivo.reports.reporte_service import write_exploration_report
from migracion_masiva_archivo.services.metadata_service import procesar_documento_metadata, procesar_lote_metadata


class Command(BaseCommand):
    help = 'Ejecuta Fase 2: OCR opcional, extraccion, normalizacion y validacion de metadata.'

    def add_arguments(self, parser):
        target = parser.add_mutually_exclusive_group(required=True)
        target.add_argument('--lote', type=int)
        target.add_argument('--documento', type=int)
        parser.add_argument('--sin-ocr', action='store_true')
        parser.add_argument('--max-pages', type=int, default=2)
        parser.add_argument('--incluir-duplicados', action='store_true')
        parser.add_argument('--reporte', type=str, default='')

    def handle(self, *args, **options):
        usar_ocr = not options['sin_ocr']
        max_pages = options['max_pages']

        if options.get('lote'):
            lote = self._get_lote(options['lote'])
            resultados = procesar_lote_metadata(
                lote,
                usar_ocr=usar_ocr,
                max_pages=max_pages,
                incluir_duplicados=options['incluir_duplicados'],
            )
            self.stdout.write(self.style.SUCCESS(f'Lote procesado: {lote.id} - {lote.nombre}'))
            self.stdout.write(f'Documentos procesados: {len(resultados)}')
            self.stdout.write(f'Validados: {sum(1 for item in resultados if item["ok"])}')
            self.stdout.write(f'Requieren revision: {sum(1 for item in resultados if not item["ok"])}')

            if options['reporte']:
                output_path = Path(options['reporte'])
                output_path.parent.mkdir(parents=True, exist_ok=True)
                queryset = DocumentoDigitalizado.objects.filter(lote=lote).select_related('metadata')
                report_type = write_exploration_report(output_path, queryset)
                self.stdout.write(self.style.SUCCESS(f'Reporte generado: {output_path}'))
                self.stdout.write(f'Formato: {report_type}')
            return

        documento = self._get_documento(options['documento'])
        resultado = procesar_documento_metadata(documento, usar_ocr=usar_ocr, max_pages=max_pages)
        self.stdout.write(self.style.SUCCESS(f'Documento procesado: {documento.id} - {documento.nombre_archivo}'))
        self.stdout.write(f'Estado: {resultado["estado"]}')
        self.stdout.write(f'OK: {resultado["ok"]}')
        if resultado['errores']:
            self.stdout.write(f'Errores: {"; ".join(resultado["errores"])}')

    def _get_lote(self, lote_id):
        try:
            return LoteDocumental.objects.get(pk=lote_id)
        except LoteDocumental.DoesNotExist as exc:
            raise CommandError(f'No existe el lote {lote_id}') from exc

    def _get_documento(self, documento_id):
        try:
            return DocumentoDigitalizado.objects.get(pk=documento_id)
        except DocumentoDigitalizado.DoesNotExist as exc:
            raise CommandError(f'No existe el documento {documento_id}') from exc


