"""
Flujo completo del modulo Documental en un solo comando.

Pasos:
  1. Explorar carpeta y crear lote  (solo con --carpeta)
  2. Extraer metadata y OCR
  3. Relacionar documentos
  4. Validar documentos para SAIA
  5. Cargar documentos en SAIA
  6. Generar reporte Excel y enviar por correo

Uso tipico (dia a dia):
  python manage.py procesar_lote_completo
      --carpeta "C:\\...\\PEL 2019"
      --limite 30 --headful --enviar-correo

Retomar lote ya explorado:
  python manage.py procesar_lote_completo
      --lote 12 --limite 30 --headful --enviar-correo

Solo reporte de un lote ya cargado:
  python manage.py procesar_lote_completo
      --lote 12 --solo-reporte --enviar-correo
"""

import os
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from migracion_masiva_archivo.execution_control import control
from migracion_masiva_archivo.models import LoteDocumental, LogProcesoDocumental
from migracion_masiva_archivo.reports.reporte_saia import (
    build_reporte_saia_xlsx,
    get_asuntos_exitosos_por_lote,
    send_reporte_saia_email,
)
from migracion_masiva_archivo.services.lote_service import crear_lote_desde_carpeta
from migracion_masiva_archivo.services.metadata_service import procesar_lote_metadata
from migracion_masiva_archivo.services.relaciones_service import relacionar_documentos_lote
from migracion_masiva_archivo.services.saia.batch_service import cargar_lote_saia
from migracion_masiva_archivo.services.saia.exceptions import SAIAError
from migracion_masiva_archivo.services.saia.validation_service import validate_lote_for_saia
from migracion_masiva_archivo.services.scanner_service import FolderValidationError, validate_selected_folder_for_inventory


DESTINATARIO_DEFAULT = os.getenv('EMAIL_DESTINATARIO_DEFAULT', 'lviana@eurosupermercados.com')
SEPARADOR = '-' * 60


class Command(BaseCommand):
    help = 'Flujo completo: explorar -> metadata -> relacionar -> validar -> cargar SAIA -> reporte.'

    def add_arguments(self, parser):
        target = parser.add_mutually_exclusive_group(required=True)
        target.add_argument(
            '--carpeta', type=str,
            help='Ruta de la carpeta con documentos PEL. Crea un lote nuevo.',
        )
        target.add_argument(
            '--lote', type=int,
            help='ID de un lote ya explorado. Continua desde metadata.',
        )
        parser.add_argument('--nombre', type=str,
                            help='Nombre del lote (solo con --carpeta).')
        parser.add_argument('--sin-ocr', action='store_true',
                            help='No aplica OCR durante la extraccion de metadata.')
        parser.add_argument('--max-pages', type=int, default=1,
                            help='Paginas maximas por documento para OCR (default: 1).')
        parser.add_argument('--limite', type=int, default=70,
                            help='Maximo de documentos a cargar en SAIA en este ciclo (default: 70).')
        parser.add_argument('--dry-run', action='store_true',
                            help='Navega SAIA pero no confirma ninguna carga.')
        parser.add_argument('--headful', action='store_true',
                            help='Muestra el navegador durante la carga SAIA.')
        parser.add_argument('--pausa', type=int, default=3,
                            help='Segundos entre cargas SAIA (default: 3).')
        parser.add_argument('--enviar-correo', action='store_true',
                            help='Envia el reporte Excel por correo al finalizar.')
        parser.add_argument(
            '--destinatario', type=str, action='append', dest='destinatarios',
            metavar='EMAIL',
            help=f'Correo destinatario (puede repetirse). Default: {DESTINATARIO_DEFAULT}',
        )
        parser.add_argument('--carpeta-secundaria', type=str, dest='carpeta_secundaria',
                            help='Carpeta complemento (ej: 192.168.1.245). '
                                 'Sus documentos unicos se agregan al lote deduplicando por PEL.')
        parser.add_argument('--salida', type=str,
                            help='Ruta donde guardar el Excel generado.')
        parser.add_argument('--con-detalle', action='store_true',
                            help='Incluye hoja DETALLE en el Excel.')
        parser.add_argument('--solo-reporte', action='store_true',
                            help='Salta los pasos 1-5 y solo genera/envia el reporte.')

    # ------------------------------------------------------------------
    # Coordinador principal
    # ------------------------------------------------------------------

    def handle(self, *args, **options):
        os.environ.setdefault('DJANGO_ALLOW_ASYNC_UNSAFE', 'true')
        self._sep('FLUJO COMPLETO PEL -> SAIA')

        lote = self._resolver_lote(options)
        # Registrar lote activo en el singleton de control (usado por el dashboard)
        control.lote_id_activo = lote.id
        control.running = True
        if control.estado not in ('EN_EJECUCION', 'DETENIENDO'):
            control.estado = 'EN_EJECUCION'

        if not options['solo_reporte']:
            self._chk_cancel(lote)
            self._paso_metadata(lote, options)

            self._chk_cancel(lote)
            self._paso_relacionar(lote)

            self._chk_cancel(lote)
            listos = self._paso_validar(lote)
            if listos == 0:
                self.stdout.write(self.style.WARNING(
                    'Ningun documento listo para SAIA. Flujo completado sin carga.'
                ))
                control.fase_actual = 'Sin documentos listos para SAIA'
                control.marcar_finalizado()
                return

            self._chk_cancel(lote)
            exitosos = self._paso_cargar(lote, options)
            if exitosos == 0 and not options['dry_run']:
                self.stdout.write(self.style.WARNING(
                    'No se cargo ningun documento exitosamente en SAIA.'
                ))

        self._paso_reporte(lote, options)
        self._sep('FLUJO COMPLETADO')
        control.marcar_finalizado()

    def _chk_cancel(self, lote):
        """Verifica si el usuario solicitó cancelar. Lanza SystemExit si es así."""
        if not control.cancel_requested:
            return
        msg = 'Proceso cancelado por el usuario desde el dashboard.'
        self.stdout.write(self.style.WARNING(msg))
        LogProcesoDocumental.objects.create(
            lote=lote,
            nivel='WARNING',
            evento='PROCESO_CANCELADO',
            mensaje=msg,
        )
        control.marcar_cancelado()
        raise SystemExit(0)

    # ------------------------------------------------------------------
    # Paso 0: resolver lote
    # ------------------------------------------------------------------

    def _resolver_lote(self, options):
        if options.get('lote'):
            return self._get_lote(options['lote'])
        return self._paso_explorar(options)

    def _paso_explorar(self, options):
        control.fase_actual = 'Fase 1 — Explorando carpeta'
        self._sep('PASO 1 | Explorar carpeta')
        try:
            carpeta = str(validate_selected_folder_for_inventory(options['carpeta']))
        except FolderValidationError as exc:
            raise CommandError(str(exc)) from exc

        nombre = options.get('nombre') or f'PEL - {timezone.localdate()}'
        carpeta_secundaria = options.get('carpeta_secundaria') or None
        if carpeta_secundaria:
            try:
                carpeta_secundaria = str(validate_selected_folder_for_inventory(carpeta_secundaria))
            except FolderValidationError as exc:
                raise CommandError(str(exc)) from exc
        self.stdout.write(f'Carpeta : {carpeta}')
        if carpeta_secundaria:
            self.stdout.write(f'Complemento: {carpeta_secundaria}')
        self.stdout.write(f'Nombre  : {nombre}')

        lote, documentos = crear_lote_desde_carpeta(
            carpeta_origen=carpeta,
            nombre=nombre,
            usuario=None,
            carpeta_secundaria=carpeta_secundaria,
            inventariar_secundaria_completa=bool(carpeta_secundaria),
        )
        control.lote_id_activo = lote.id  # actualizar ahora que el lote existe
        self.stdout.write(self.style.SUCCESS(
            f'Lote creado: ID={lote.id} | {len(documentos)} documentos encontrados.'
        ))
        return lote

    # ------------------------------------------------------------------
    # Paso 2: metadata
    # ------------------------------------------------------------------

    def _paso_metadata(self, lote, options):
        control.fase_actual = 'Fase 2 — Extrayendo metadata y OCR'
        self._sep('PASO 2 | Extraer metadata y OCR')
        resultados = procesar_lote_metadata(
            lote,
            usar_ocr=not options['sin_ocr'],
            max_pages=options['max_pages'],
            incluir_duplicados=False,
        )
        validados = sum(1 for r in resultados if r.get('estado') == 'VALIDADO')
        revision = sum(1 for r in resultados if r.get('estado') == 'REQUIERE_REVISION')
        errores = sum(1 for r in resultados if r.get('estado') == 'ERROR' or r.get('error'))
        self.stdout.write(self.style.SUCCESS(
            f'Metadata: {len(resultados)} procesados | '
            f'{validados} validados | {revision} revision | {errores} errores.'
        ))

    # ------------------------------------------------------------------
    # Paso 3: relaciones
    # ------------------------------------------------------------------

    def _paso_relacionar(self, lote):
        control.fase_actual = 'Fase 3 — Relacionando documentos'
        self._sep('PASO 3 | Relacionar documentos')
        resultado = relacionar_documentos_lote(lote)
        creadas = len(resultado.get('relaciones', []))
        ambiguos = len(resultado.get('grupos_ambiguos', []))
        self.stdout.write(self.style.SUCCESS(
            f'Relaciones: {creadas} creadas | {ambiguos} grupos ambiguos.'
        ))

    # ------------------------------------------------------------------
    # Paso 4: validar
    # ------------------------------------------------------------------

    def _paso_validar(self, lote):
        control.fase_actual = 'Fase 4 — Validando para SAIA'
        self._sep('PASO 4 | Validar para SAIA')
        resultados = validate_lote_for_saia(lote, solo_listos=False)
        listos = sum(1 for r in resultados if r['listo_para_saia'])
        bloqueados = len(resultados) - listos
        self.stdout.write(self.style.SUCCESS(
            f'Validacion: {listos} listos para SAIA | {bloqueados} bloqueados.'
        ))
        for r in resultados:
            if not r['listo_para_saia']:
                self.stdout.write(
                    f'  [BLOQUEADO] {r["nombre_archivo"]}: {"; ".join(r["errores"])}'
                )
        return listos

    # ------------------------------------------------------------------
    # Paso 5: cargar SAIA
    # ------------------------------------------------------------------

    def _paso_cargar(self, lote, options):
        control.fase_actual = 'Fase 5 — Cargando en SAIA'
        sufijo = '  [DRY-RUN]' if options['dry_run'] else ''
        self._sep(f'PASO 5 | Cargar en SAIA{sufijo}')
        try:
            resumen = cargar_lote_saia(
                lote_id=lote.id,
                limite=options['limite'],
                dry_run=options['dry_run'],
                headful=options['headful'],
                pausa_entre=options['pausa'],
            )
        except SAIAError as exc:
            raise CommandError(f'Error critico SAIA: {exc}') from exc

        self.stdout.write(self.style.SUCCESS(
            f'SAIA: {resumen["exitosos"]} exitosos | '
            f'{resumen["fallidos"]} fallidos | '
            f'{resumen["omitidos"]} omitidos de {resumen["total"]}.'
        ))
        if resumen.get('error_critico'):
            self.stdout.write(self.style.ERROR(
                f'Error critico detuvo el lote: {resumen["error_critico"]}'
            ))
        pendientes = resumen.get('pendientes', 0)
        control.pendientes_saia = pendientes
        if pendientes:
            self.stdout.write(self.style.WARNING(
                f'Atencion: {pendientes} documentos listos quedaron sin cargar '
                f'por el limite de {options["limite"]} docs por ciclo.'
            ))
        return resumen['exitosos']

    # ------------------------------------------------------------------
    # Paso 6: reporte
    # ------------------------------------------------------------------

    def _paso_reporte(self, lote, options):
        control.fase_actual = 'Fase 6 — Generando reporte'
        self._sep('PASO 6 | Reporte Excel')
        fecha = timezone.localdate()
        items = get_asuntos_exitosos_por_lote(lote.id)

        if not items:
            self.stdout.write(self.style.WARNING(
                'No hay cargas exitosas en este lote para incluir en el reporte.'
            ))
            return

        xlsx_bytes = build_reporte_saia_xlsx(
            items, fecha, con_detalle=options['con_detalle']
        )

        salida = options.get('salida')
        if salida:
            ruta = Path(salida)
            ruta.parent.mkdir(parents=True, exist_ok=True)
            ruta.write_bytes(xlsx_bytes)
            self.stdout.write(self.style.SUCCESS(f'Excel guardado: {ruta.resolve()}'))

        if options['enviar_correo']:
            destinatarios = options['destinatarios'] or [DESTINATARIO_DEFAULT]
            xlsx_fase5 = None
            try:
                from migracion_masiva_archivo.models import EjecucionCargaMasiva
                from migracion_masiva_archivo.reports.reporte_fase5 import build_reporte_fase5_xlsx
                ejecucion = EjecucionCargaMasiva.objects.filter(
                    lote=lote
                ).order_by('-creado').first()
                if ejecucion:
                    xlsx_fase5 = build_reporte_fase5_xlsx(ejecucion)
            except Exception:
                pass
            try:
                resultado = send_reporte_saia_email(
                    xlsx_bytes, fecha, destinatarios, lote=lote,
                    xlsx_fase5_bytes=xlsx_fase5,
                    pendientes=control.pendientes_saia,
                )
                control.email_status = True
                self.stdout.write(self.style.SUCCESS(
                    f'Correo enviado a: {", ".join(resultado["destinatarios"])}'
                ))
            except Exception as exc:
                control.email_status = str(exc)
                self.stdout.write(self.style.ERROR(f'Error al enviar correo: {exc}'))

        self.stdout.write(f'Reporte: {len(items)} PEL del {fecha.strftime("%d/%m/%Y")}.')
        for item in items:
            self.stdout.write(f'  {item["asunto_saia"]}')

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_lote(self, lote_id):
        try:
            return LoteDocumental.objects.get(pk=lote_id)
        except LoteDocumental.DoesNotExist as exc:
            raise CommandError(f'No existe el lote {lote_id}.') from exc

    def _sep(self, titulo):
        self.stdout.write(f'\n{SEPARADOR}')
        self.stdout.write(f'  {titulo}')
        self.stdout.write(SEPARADOR)


