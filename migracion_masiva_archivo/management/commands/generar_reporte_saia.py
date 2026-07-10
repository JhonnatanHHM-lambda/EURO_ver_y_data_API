"""
Fase 5: genera el reporte Excel de PEL cargados exitosamente a SAIA
y lo envia por correo a lviana@eurosupermercados.com (o destinatario indicado).

Uso:
  # Por fecha (default: hoy)
  python manage.py generar_reporte_saia

  # Fecha especifica
  python manage.py generar_reporte_saia --fecha 2026-06-11

  # Por lote
  python manage.py generar_reporte_saia --lote 5

  # Guardar y enviar
  python manage.py generar_reporte_saia --fecha 2026-06-11 --salida reporte.xlsx --enviar-correo

  # Destinatario adicional
  python manage.py generar_reporte_saia --enviar-correo --destinatario otro@empresa.com

  # Con hoja de detalle tecnico
  python manage.py generar_reporte_saia --con-detalle --salida reporte.xlsx
"""

import os
from datetime import datetime
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from migracion_masiva_archivo.models import LoteDocumental
from migracion_masiva_archivo.reports.reporte_saia import (
    build_reporte_saia_xlsx,
    get_asuntos_exitosos_por_fecha,
    get_asuntos_exitosos_por_lote,
    send_reporte_saia_email,
)


DESTINATARIO_DEFAULT = os.getenv('EMAIL_DESTINATARIO_DEFAULT', 'lviana@eurosupermercados.com')


class Command(BaseCommand):
    help = (
        'Fase 5: genera el Excel de PEL cargados a SAIA y lo envia por correo.'
    )

    def add_arguments(self, parser):
        grupo = parser.add_mutually_exclusive_group()
        grupo.add_argument(
            '--fecha', type=str,
            help='Fecha del reporte en formato YYYY-MM-DD (default: hoy en hora Bogota).',
        )
        grupo.add_argument(
            '--lote', type=int,
            help='ID del lote documental (alternativa a --fecha).',
        )
        parser.add_argument(
            '--salida', type=str,
            help='Ruta donde guardar el archivo Excel generado.',
        )
        parser.add_argument(
            '--enviar-correo', action='store_true',
            help='Envia el reporte por correo despues de generarlo.',
        )
        parser.add_argument(
            '--destinatario', type=str, action='append', dest='destinatarios',
            metavar='EMAIL',
            help=(
                f'Correo destinatario (puede repetirse). '
                f'Default: {DESTINATARIO_DEFAULT}'
            ),
        )
        parser.add_argument(
            '--con-detalle', action='store_true',
            help='Incluye una hoja DETALLE con campos tecnicos por intento.',
        )

    def handle(self, *args, **options):
        fecha_reporte, items, lote = self._resolver_items(options)

        self.stdout.write(
            f'Reporte SAIA | fecha={fecha_reporte} | lote={lote.id if lote else "-"} '
            f'| documentos={len(items)}'
        )

        if not items:
            self.stdout.write(self.style.WARNING(
                'No hay documentos cargados exitosamente en SAIA para el periodo indicado.'
            ))
            return

        xlsx_bytes = build_reporte_saia_xlsx(
            items, fecha_reporte, con_detalle=options['con_detalle']
        )

        salida = options.get('salida')
        if salida:
            ruta = Path(salida)
            ruta.parent.mkdir(parents=True, exist_ok=True)
            ruta.write_bytes(xlsx_bytes)
            self.stdout.write(self.style.SUCCESS(f'Excel guardado en: {ruta.resolve()}'))

        if options['enviar_correo']:
            self._enviar(xlsx_bytes, fecha_reporte, options['destinatarios'], lote)

        if not salida and not options['enviar_correo']:
            self.stdout.write(
                'Usa --salida <ruta.xlsx> para guardar el archivo '
                'o --enviar-correo para enviarlo.'
            )

        self.stdout.write(self.style.SUCCESS(
            f'Reporte generado: {len(items)} PEL del {fecha_reporte.strftime("%d/%m/%Y")}.'
        ))
        self._imprimir_listado(items)

    def _resolver_items(self, options):
        lote = None
        if options.get('lote'):
            lote = self._get_lote(options['lote'])
            items = get_asuntos_exitosos_por_lote(lote.id)
            fecha_reporte = timezone.localdate()
        else:
            fecha_str = options.get('fecha')
            fecha_reporte = self._parsear_fecha(fecha_str) if fecha_str else timezone.localdate()
            items = get_asuntos_exitosos_por_fecha(fecha_reporte)
        return fecha_reporte, items, lote

    def _enviar(self, xlsx_bytes, fecha_reporte, destinatarios_cli, lote):
        destinatarios = destinatarios_cli or [DESTINATARIO_DEFAULT]
        try:
            resultado = send_reporte_saia_email(
                xlsx_bytes, fecha_reporte, destinatarios, lote=lote
            )
            self.stdout.write(self.style.SUCCESS(
                f'Correo enviado a: {", ".join(resultado["destinatarios"])}'
            ))
        except Exception as exc:
            raise CommandError(f'Error al enviar correo: {exc}') from exc

    def _imprimir_listado(self, items):
        self.stdout.write('Consecutivos incluidos en el reporte:')
        for item in items:
            self.stdout.write(f'  {item["asunto_saia"]}')

    def _parsear_fecha(self, fecha_str):
        try:
            return datetime.strptime(fecha_str, '%Y-%m-%d').date()
        except ValueError as exc:
            raise CommandError(
                f'Fecha invalida: "{fecha_str}". Use formato YYYY-MM-DD.'
            ) from exc

    def _get_lote(self, lote_id):
        try:
            return LoteDocumental.objects.get(pk=lote_id)
        except LoteDocumental.DoesNotExist as exc:
            raise CommandError(f'No existe el lote {lote_id}.') from exc


