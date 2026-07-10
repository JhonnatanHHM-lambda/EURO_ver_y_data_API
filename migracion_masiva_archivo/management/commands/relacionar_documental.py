from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from migracion_masiva_archivo.models import DocumentoDigitalizado, LoteDocumental, RelacionDocumento
from migracion_masiva_archivo.reports.reporte_service import write_exploration_report
from migracion_masiva_archivo.services.relaciones_service import relacionar_documentos_lote


class Command(BaseCommand):
    help = 'Ejecuta Fase 3: relaciona documentos por familias PEL.'

    def add_arguments(self, parser):
        parser.add_argument('--lote', type=int, required=True)
        parser.add_argument('--min-confidence', type=int, default=80)
        parser.add_argument('--recrear', action='store_true')
        parser.add_argument('--reporte', type=str, default='')

    def handle(self, *args, **options):
        lote = self._get_lote(options['lote'])
        result = relacionar_documentos_lote(
            lote,
            min_confidence=options['min_confidence'],
            recrear=options['recrear'],
        )

        self.stdout.write(self.style.SUCCESS(f'Lote relacionado: {lote.id} - {lote.nombre}'))
        self.stdout.write(f'Relaciones creadas/actualizadas: {len(result["relaciones"])}')
        self.stdout.write(f'Grupos ambiguos: {len(result["grupos_ambiguos"])}')
        self.stdout.write(f'Relaciones descartadas: {len(result["relaciones_descartadas"])}')
        self.stdout.write(f'Documentos omitidos: {len(result.get("documentos_omitidos", []))}')

        revision_items = []
        revision_items.extend(result.get('grupos_ambiguos', []))
        revision_items.extend(result.get('relaciones_descartadas', []))
        revision_items.extend(result.get('documentos_omitidos', []))
        revision_items.extend(result.get('advertencias_orden', []))

        if revision_items:
            self.stdout.write('Revision requerida:')
            for item in revision_items:
                label = item.get('grupo') or item.get('nombre_archivo') or item.get('criterio') or item.get('tipo') or 'Elemento'
                message = item.get('mensaje_usuario') or item.get('motivo') or 'Requiere revision documental'
                action = item.get('accion_recomendada') or 'Revise el detalle tecnico del resultado.'
                self.stdout.write(f'  - {label}: {message}')
                self.stdout.write(f'    Accion: {action}')

        relaciones = RelacionDocumento.objects.filter(documento_principal__lote=lote).select_related(
            'documento_principal',
            'documento_relacionado',
        )
        for relacion in relaciones:
            self.stdout.write(
                f'{relacion.documento_principal.nombre_archivo} -> '
                f'{relacion.documento_relacionado.nombre_archivo} | '
                f'{relacion.criterio_relacion} | confianza {relacion.confianza}'
            )

        if options['reporte']:
            output_path = Path(options['reporte'])
            output_path.parent.mkdir(parents=True, exist_ok=True)
            queryset = DocumentoDigitalizado.objects.filter(lote=lote).select_related('metadata')
            report_type = write_exploration_report(output_path, queryset)
            self.stdout.write(self.style.SUCCESS(f'Reporte generado: {output_path}'))
            self.stdout.write(f'Formato: {report_type}')

    def _get_lote(self, lote_id):
        try:
            return LoteDocumental.objects.get(pk=lote_id)
        except LoteDocumental.DoesNotExist as exc:
            raise CommandError(f'No existe el lote {lote_id}') from exc


