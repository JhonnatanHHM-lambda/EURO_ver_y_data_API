from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from migracion_masiva_archivo.models import DocumentoDigitalizado
from migracion_masiva_archivo.reports.reporte_service import write_exploration_report
from migracion_masiva_archivo.services.lote_service import crear_lote_desde_carpeta


class Command(BaseCommand):
    help = 'Explora una carpeta documental, crea un lote y opcionalmente genera reporte CSV/XLSX.'

    def add_arguments(self, parser):
        parser.add_argument('carpeta_origen', type=str)
        parser.add_argument('--nombre', type=str, default='')
        parser.add_argument('--reporte', type=str, default='')
        parser.add_argument('--carpeta-secundaria', type=str, default='')
        parser.add_argument('--inventariar-secundaria-completa', action='store_true')

    def handle(self, *args, **options):
        carpeta_origen = options['carpeta_origen']
        nombre = options.get('nombre') or None
        reporte = options.get('reporte') or ''
        carpeta_secundaria = options.get('carpeta_secundaria') or ''
        inventariar_secundaria_completa = options['inventariar_secundaria_completa']

        try:
            lote, documents, continuity_context = crear_lote_desde_carpeta(
                carpeta_origen=carpeta_origen,
                nombre=nombre,
                carpeta_secundaria=carpeta_secundaria,
                inventariar_secundaria_completa=inventariar_secundaria_completa,
                retornar_contexto=True,
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(self.style.SUCCESS(f'Lote creado: {lote.id} - {lote.nombre}'))
        self.stdout.write(f'Documentos detectados: {len(documents)}')
        self.stdout.write(f'Exitosos: {lote.total_exitosos}')
        self.stdout.write(f'Requieren revision: {lote.total_revision}')
        self.stdout.write(f'Fallidos: {lote.total_fallidos}')
        resumen_continuidad = continuity_context.get('resumen', {})
        self.stdout.write(f'Faltantes detectados: {resumen_continuidad.get("total_faltantes_detectados", 0)}')
        self.stdout.write(
            'Recuperados en secundaria: '
            f'{resumen_continuidad.get("total_documentos_recuperados_secundaria", 0)}'
        )
        self.stdout.write(
            'Faltantes no encontrados: '
            f'{resumen_continuidad.get("total_faltantes_no_encontrados", 0)}'
        )
        self.stdout.write(
            'Documentos secundaria inventariados: '
            f'{resumen_continuidad.get("total_documentos_secundaria", 0)}'
        )
        self.stdout.write(
            'Duplicados entre carpetas: '
            f'{resumen_continuidad.get("total_duplicados_entre_carpetas", 0)}'
        )

        if reporte:
            output_path = Path(reporte)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            queryset = DocumentoDigitalizado.objects.filter(lote=lote).select_related('metadata')
            report_type = write_exploration_report(
                output_path,
                queryset,
                continuity_context=continuity_context,
                carpeta_origen=carpeta_origen,
                carpeta_secundaria=carpeta_secundaria,
            )
            self.stdout.write(self.style.SUCCESS(f'Reporte generado: {output_path}'))
            self.stdout.write(f'Formato: {report_type}')


