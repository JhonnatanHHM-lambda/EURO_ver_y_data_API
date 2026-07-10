"""
Fase 5: Carga masiva controlada con Celery.

Iniciar nueva ejecucion:
  python manage.py carga_masiva_fase5 --lote 3

Con opciones:
  python manage.py carga_masiva_fase5 --lote 3 --tamano-sublote 15 --pausa 5 --headful

Dry-run (sin confirmar carga en SAIA):
  python manage.py carga_masiva_fase5 --lote 3 --dry-run --tamano-sublote 5

Modo sincrono (sin worker Celery externo):
  python manage.py carga_masiva_fase5 --lote 3 --sync

Consultar estado de ejecuciones del lote:
  python manage.py carga_masiva_fase5 --estado --lote 3

Reanudar ejecucion interrumpida:
  python manage.py carga_masiva_fase5 --reanudar --ejecucion 7

Generar reporte final:
  python manage.py carga_masiva_fase5 --reporte --ejecucion 7
  python manage.py carga_masiva_fase5 --reporte --ejecucion 7 --salida reporte_fase5.xlsx
"""

import os
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from migracion_masiva_archivo.models import EjecucionCargaMasiva, LogProcesoDocumental, LoteDocumental
from migracion_masiva_archivo.services.saia.batch_service import get_documentos_listos
from migracion_masiva_archivo.tasks import ejecutar_carga_masiva_lote, ejecutar_logica_carga_masiva


class Command(BaseCommand):
    help = 'Fase 5: carga masiva controlada con Celery, reintentos y reporte.'

    def add_arguments(self, parser):
        accion = parser.add_mutually_exclusive_group(required=True)
        accion.add_argument('--lote', type=int,
                            help='ID del lote. Inicia nueva ejecucion masiva.')
        accion.add_argument('--estado', action='store_true',
                            help='Muestra estado de las ultimas ejecuciones.')
        accion.add_argument('--reanudar', action='store_true',
                            help='Reanuda ejecucion fallida o interrumpida.')
        accion.add_argument('--reporte', action='store_true',
                            help='Genera reporte final de una ejecucion.')

        parser.add_argument('--ejecucion', type=int,
                            help='ID de EjecucionCargaMasiva (para --estado/--reanudar/--reporte).')
        parser.add_argument('--tamano-sublote', type=int, default=10,
                            help='Documentos por sub-lote (default: 10).')
        parser.add_argument('--max-reintentos', type=int, default=3,
                            help='Reintentos Celery ante error de SAIA (default: 3).')
        parser.add_argument('--dry-run', action='store_true',
                            help='Navega SAIA pero no confirma ninguna carga.')
        parser.add_argument('--headful', action='store_true',
                            help='Muestra el navegador durante la carga.')
        parser.add_argument('--pausa', type=int, default=3,
                            help='Segundos entre cargas individuales (default: 3).')
        parser.add_argument('--sync', action='store_true',
                            help='Ejecutar en el mismo proceso, sin worker Celery.')
        parser.add_argument('--salida', type=str,
                            help='Ruta Excel para guardar el reporte (con --reporte).')

    # ------------------------------------------------------------------ #
    # Coordinador
    # ------------------------------------------------------------------ #

    def handle(self, *args, **options):
        # Playwright's sync API runs an event loop in the main thread.
        # Django 4.1+ raises SynchronousOnlyOperation when it detects a running
        # loop. This env var disables that guard for the duration of this command.
        os.environ.setdefault('DJANGO_ALLOW_ASYNC_UNSAFE', 'true')

        if options.get('lote'):
            self._lanzar(options)
        elif options.get('estado'):
            self._mostrar_estado(options)
        elif options.get('reanudar'):
            self._reanudar(options)
        elif options.get('reporte'):
            self._generar_reporte(options)

    # ------------------------------------------------------------------ #
    # Lanzar nueva ejecucion
    # ------------------------------------------------------------------ #

    def _lanzar(self, options):
        lote = self._get_lote(options['lote'])
        pendientes = len(get_documentos_listos(lote, limite=None))

        if pendientes == 0:
            self.stdout.write(self.style.WARNING(
                'No hay documentos validados y relacionados pendientes de carga.'
            ))
            return

        ejecucion = EjecucionCargaMasiva.objects.create(
            lote=lote,
            tamano_sublote=options['tamano_sublote'],
            max_reintentos=options['max_reintentos'],
            dry_run=options['dry_run'],
            headful=options['headful'],
            pausa_entre=options['pausa'],
            total_documentos=pendientes,
        )
        self.stdout.write(
            f'Ejecucion creada | ID={ejecucion.id} | Lote={lote.id} | '
            f'Pendientes={pendientes} | Sub-lote={options["tamano_sublote"]} docs'
        )

        if options.get('sync'):
            self.stdout.write('Ejecutando en modo sincrono... (Ctrl+C para cancelar con reporte parcial)')
            try:
                result = ejecutar_logica_carga_masiva(ejecucion.id)
                self._imprimir_resultado(result)
            except KeyboardInterrupt:
                self._handle_interrupcion(ejecucion)
        else:
            task = ejecutar_carga_masiva_lote.delay(ejecucion.id)
            ejecucion.celery_task_id = task.id
            ejecucion.save(update_fields=['celery_task_id', 'modificado'])
            self.stdout.write(self.style.SUCCESS(
                f'Tarea enviada al worker Celery.\n'
                f'  task_id  : {task.id}\n'
                f'  Consultar: python manage.py carga_masiva_fase5 --estado --ejecucion {ejecucion.id}\n'
                f'  Reporte  : python manage.py carga_masiva_fase5 --reporte --ejecucion {ejecucion.id}'
            ))

    # ------------------------------------------------------------------ #
    # Estado
    # ------------------------------------------------------------------ #

    def _mostrar_estado(self, options):
        qs = EjecucionCargaMasiva.objects.select_related('lote').order_by('-creado')
        if options.get('ejecucion'):
            qs = qs.filter(pk=options['ejecucion'])
        else:
            qs = qs[:10]

        if not qs.exists():
            self.stdout.write('No se encontraron ejecuciones.')
            return

        for ej in qs:
            pendientes = ej.total_documentos - ej.procesados
            linea = (
                f'Ejecucion {ej.id:>4} | Lote={ej.lote_id} | {ej.estado_proceso:<26} | '
                f'Exitosos={ej.exitosos:>4} | Fallidos={ej.fallidos:>3} | '
                f'Revision={ej.pendientes_revision:>3} | Pendientes={pendientes:>4}'
            )
            if ej.celery_task_id:
                linea += f'\n               task_id={ej.celery_task_id}'
            if ej.error:
                linea += f'\n               error={ej.error[:100]}'
            self.stdout.write(linea)

    # ------------------------------------------------------------------ #
    # Reanudar
    # ------------------------------------------------------------------ #

    def _reanudar(self, options):
        if not options.get('ejecucion'):
            raise CommandError('--reanudar requiere --ejecucion ID')

        ejecucion = self._get_ejecucion(options['ejecucion'])
        if ejecucion.estado_proceso in ('FINALIZADO', 'CANCELADO'):
            raise CommandError(
                f'La ejecucion {ejecucion.id} esta en estado {ejecucion.estado_proceso}. '
                f'Usa --lote para iniciar una nueva.'
            )

        ejecucion.estado_proceso = 'PENDIENTE'
        ejecucion.error = ''
        ejecucion.save(update_fields=['estado_proceso', 'error', 'modificado'])
        self.stdout.write(f'Ejecucion {ejecucion.id} reiniciada. '
                          f'Documentos ya cargados seran omitidos automaticamente.')

        if options.get('sync'):
            try:
                result = ejecutar_logica_carga_masiva(ejecucion.id)
                self._imprimir_resultado(result)
            except KeyboardInterrupt:
                self._handle_interrupcion(ejecucion)
        else:
            task = ejecutar_carga_masiva_lote.delay(ejecucion.id)
            ejecucion.celery_task_id = task.id
            ejecucion.save(update_fields=['celery_task_id', 'modificado'])
            self.stdout.write(self.style.SUCCESS(f'Reanudada | task_id={task.id}'))

    # ------------------------------------------------------------------ #
    # Reporte
    # ------------------------------------------------------------------ #

    def _generar_reporte(self, options):
        if not options.get('ejecucion'):
            raise CommandError('--reporte requiere --ejecucion ID')

        from migracion_masiva_archivo.reports.reporte_fase5 import build_reporte_fase5_xlsx, imprimir_reporte_consola
        ejecucion = self._get_ejecucion(options['ejecucion'])
        imprimir_reporte_consola(ejecucion, self.stdout)

        salida = options.get('salida')
        if salida:
            xlsx = build_reporte_fase5_xlsx(ejecucion)
            ruta = Path(salida)
            ruta.parent.mkdir(parents=True, exist_ok=True)
            ruta.write_bytes(xlsx)
            self.stdout.write(self.style.SUCCESS(f'Reporte Excel guardado: {ruta.resolve()}'))

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _handle_interrupcion(self, ejecucion):
        """Llamado cuando el usuario cierra el script (Ctrl+C) en modo --sync."""
        from migracion_masiva_archivo.reports.reporte_fase5 import imprimir_reporte_consola
        ejecucion.refresh_from_db()
        if ejecucion.estado_proceso not in ('CANCELADO', 'FINALIZADO', 'FINALIZADO_CON_ERRORES'):
            ejecucion.estado_proceso = 'CANCELADO'
            ejecucion.fecha_fin = timezone.now()
            ejecucion.error = 'Interrumpido por el usuario.'
            ejecucion.save(update_fields=['estado_proceso', 'fecha_fin', 'error', 'modificado'])
            LogProcesoDocumental.objects.create(
                lote=ejecucion.lote,
                nivel='WARNING',
                evento='carga_masiva_cancelada_comando',
                mensaje='Script cerrado por el usuario. Reporte parcial generado.',
                detalle={'exitosos': ejecucion.exitosos, 'fallidos': ejecucion.fallidos},
            )
        self.stdout.write(self.style.WARNING(
            '\n[CANCELADO] Script interrumpido. Reporte parcial:'
        ))
        imprimir_reporte_consola(ejecucion, self.stdout)
        self.stdout.write(
            f'Para reanudar: python manage.py carga_masiva_fase5 '
            f'--reanudar --ejecucion {ejecucion.id} --sync'
        )

    def _imprimir_resultado(self, result):
        if not result:
            return
        if result.get('error'):
            self.stdout.write(self.style.ERROR(f'Error: {result["error"]}'))
        else:
            self.stdout.write(self.style.SUCCESS(
                f'Completado | Exitosos={result.get("exitosos", 0)} | '
                f'Fallidos={result.get("fallidos", 0)} | '
                f'Procesados={result.get("procesados", 0)} | '
                f'En revision={result.get("pendientes_revision", 0)}'
            ))

    def _get_lote(self, lote_id):
        try:
            return LoteDocumental.objects.get(pk=lote_id)
        except LoteDocumental.DoesNotExist as exc:
            raise CommandError(f'No existe el lote {lote_id}') from exc

    def _get_ejecucion(self, ejecucion_id):
        try:
            return EjecucionCargaMasiva.objects.select_related('lote').get(pk=ejecucion_id)
        except EjecucionCargaMasiva.DoesNotExist as exc:
            raise CommandError(f'No existe la ejecucion {ejecucion_id}') from exc


