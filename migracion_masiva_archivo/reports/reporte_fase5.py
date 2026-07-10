"""
Reporte final Fase 5: cargados, fallidos y pendientes de revision.

Genera un Excel con 4 hojas:
  - RESUMEN         : contadores globales de la ejecucion
  - CARGADOS        : documentos subidos exitosamente a SAIA
  - FALLIDOS        : documentos con ERROR_SAIA y su mensaje de error
  - PENDIENTES_REV  : documentos con metadata incompleta o requiere_revision=True
"""

import io

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from migracion_masiva_archivo.models import DocumentoDigitalizado, EjecucionCargaMasiva, IntentoCargaSAIA


_FILL_AZUL = PatternFill(start_color='27348B', end_color='27348B', fill_type='solid')
_FILL_ROJO = PatternFill(start_color='C0392B', end_color='C0392B', fill_type='solid')
_FILL_NARANJA = PatternFill(start_color='E67E22', end_color='E67E22', fill_type='solid')
_FILL_VERDE = PatternFill(start_color='1E8449', end_color='1E8449', fill_type='solid')
_FONT_HEADER = Font(color='FFFFFF', bold=True, size=10)
_ALIGN_C = Alignment(horizontal='center', vertical='center', wrap_text=True)
_ALIGN_L = Alignment(horizontal='left', vertical='center', wrap_text=True)
_THIN = Side(style='thin')
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)


# ---------------------------------------------------------------------------
# Consultas
# ---------------------------------------------------------------------------

def get_datos_reporte(ejecucion):
    lote = ejecucion.lote

    cargados = list(
        IntentoCargaSAIA.objects
        .filter(exitoso=True, documento__lote=lote)
        .select_related('documento', 'documento__metadata')
        .order_by('documento__nombre_archivo')
    )

    fallidos = list(
        DocumentoDigitalizado.objects
        .select_related('metadata')
        .prefetch_related('intentos_saia')
        .filter(lote=lote, estado_proceso='ERROR_SAIA')
        .order_by('nombre_archivo')
    )

    pendientes_revision = list(
        DocumentoDigitalizado.objects
        .select_related('metadata')
        .filter(lote=lote, metadata__requiere_revision=True)
        .exclude(estado_proceso='CARGADO_SAIA')
        .order_by('nombre_archivo')
    )

    return cargados, fallidos, pendientes_revision


# ---------------------------------------------------------------------------
# Excel
# ---------------------------------------------------------------------------

def build_reporte_fase5_xlsx(ejecucion):
    cargados, fallidos, pendientes_revision = get_datos_reporte(ejecucion)

    wb = Workbook()
    _build_resumen(wb.active, ejecucion, cargados, fallidos, pendientes_revision)
    _build_cargados(wb.create_sheet('CARGADOS'), cargados)
    _build_fallidos(wb.create_sheet('FALLIDOS'), fallidos)
    _build_pendientes_revision(wb.create_sheet('PENDIENTES_REV'), pendientes_revision)

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output.getvalue()


def _build_resumen(ws, ejecucion, cargados, fallidos, pendientes_revision):
    ws.title = 'RESUMEN'
    filas = [
        ('Lote ID', ejecucion.lote_id),
        ('Lote nombre', ejecucion.lote.nombre),
        ('Ejecucion ID', ejecucion.id),
        ('Estado', ejecucion.estado_proceso),
        ('Fecha inicio', str(ejecucion.fecha_inicio or '')),
        ('Fecha fin', str(ejecucion.fecha_fin or '')),
        ('Total documentos evaluados', ejecucion.total_documentos),
        ('Procesados en esta ejecucion', ejecucion.procesados),
        ('Cargados exitosamente', len(cargados)),
        ('Fallidos (ERROR_SAIA)', len(fallidos)),
        ('Pendientes de revision', len(pendientes_revision)),
        ('Dry-run', 'Si' if ejecucion.dry_run else 'No'),
        ('Tamano sub-lote', ejecucion.tamano_sublote),
        ('Max reintentos', ejecucion.max_reintentos),
        ('Task Celery ID', ejecucion.celery_task_id or 'N/A'),
        ('Error critico', ejecucion.error or 'Ninguno'),
    ]

    ws.column_dimensions['A'].width = 32
    ws.column_dimensions['B'].width = 52

    for i, (etiqueta, valor) in enumerate(filas, start=1):
        celda_a = ws.cell(row=i, column=1, value=etiqueta)
        celda_b = ws.cell(row=i, column=2, value=valor)
        celda_a.border = _BORDER
        celda_b.border = _BORDER
        celda_a.alignment = _ALIGN_L
        celda_b.alignment = _ALIGN_L
        celda_a.font = Font(bold=True)


def _build_cargados(ws, cargados):
    headers = ['documento_id', 'nombre_archivo', 'consecutivo', 'asunto_saia',
               'intento_id', 'id_documento_saia', 'fecha_carga']
    _write_header_row(ws, headers, _FILL_VERDE)
    ws.column_dimensions['B'].width = 40
    ws.column_dimensions['D'].width = 30

    for intento in cargados:
        doc = intento.documento
        meta = getattr(doc, 'metadata', None)
        meta_req = intento.request_metadata or {}
        ws.append([
            doc.id,
            doc.nombre_archivo,
            meta.consecutivo if meta else '',
            meta_req.get('asunto_saia', ''),
            intento.id,
            intento.id_documento_saia or '',
            str(intento.creado),
        ])
        _border_last_row(ws, len(headers))


def _build_fallidos(ws, fallidos):
    headers = ['documento_id', 'nombre_archivo', 'consecutivo', 'estado_proceso',
               'ultimo_error', 'intentos_realizados']
    _write_header_row(ws, headers, _FILL_ROJO)
    ws.column_dimensions['B'].width = 40
    ws.column_dimensions['E'].width = 60

    for doc in fallidos:
        meta = getattr(doc, 'metadata', None)
        ultimo_error = ''
        intentos_count = 0
        ultimo_intento = doc.intentos_saia.order_by('-creado').first()
        if ultimo_intento:
            ultimo_error = ultimo_intento.mensaje_error or ''
            intentos_count = doc.intentos_saia.count()
        ws.append([
            doc.id,
            doc.nombre_archivo,
            meta.consecutivo if meta else '',
            doc.estado_proceso,
            ultimo_error[:200],
            intentos_count,
        ])
        _border_last_row(ws, len(headers))


def _build_pendientes_revision(ws, pendientes_revision):
    headers = ['documento_id', 'nombre_archivo', 'consecutivo', 'nit',
               'confianza', 'observaciones', 'estado_proceso']
    _write_header_row(ws, headers, _FILL_NARANJA)
    ws.column_dimensions['B'].width = 40
    ws.column_dimensions['F'].width = 50

    for doc in pendientes_revision:
        meta = getattr(doc, 'metadata', None)
        ws.append([
            doc.id,
            doc.nombre_archivo,
            meta.consecutivo if meta else '',
            meta.nit if meta else '',
            float(meta.confianza) if meta else 0,
            meta.observaciones[:200] if meta else '',
            doc.estado_proceso,
        ])
        _border_last_row(ws, len(headers))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_header_row(ws, headers, fill):
    ws.append(headers)
    for cell in ws[1]:
        cell.fill = fill
        cell.font = _FONT_HEADER
        cell.alignment = _ALIGN_C
        cell.border = _BORDER
    for col_idx, _ in enumerate(headers, start=1):
        letter = get_column_letter(col_idx)
        if ws.column_dimensions[letter].width < 14:
            ws.column_dimensions[letter].width = 14


def _border_last_row(ws, num_cols):
    row_idx = ws.max_row
    for col_idx in range(1, num_cols + 1):
        cell = ws.cell(row=row_idx, column=col_idx)
        cell.border = _BORDER
        cell.alignment = _ALIGN_L


# ---------------------------------------------------------------------------
# Consola
# ---------------------------------------------------------------------------

def imprimir_reporte_consola(ejecucion, stdout):
    cargados, fallidos, pendientes_revision = get_datos_reporte(ejecucion)

    stdout.write('\n' + '=' * 60)
    stdout.write(f'  REPORTE FASE 5 | Ejecucion {ejecucion.id}')
    stdout.write('=' * 60)
    stdout.write(f'Lote        : {ejecucion.lote_id} - {ejecucion.lote.nombre}')
    stdout.write(f'Estado      : {ejecucion.estado_proceso}')
    stdout.write(f'Dry-run     : {"Si" if ejecucion.dry_run else "No"}')
    stdout.write(f'Procesados  : {ejecucion.procesados}')
    stdout.write(f'Cargados    : {len(cargados)}')
    stdout.write(f'Fallidos    : {len(fallidos)}')
    stdout.write(f'En revision : {len(pendientes_revision)}')

    if fallidos:
        stdout.write('\n--- FALLIDOS ---')
        for doc in fallidos[:20]:
            ultimo = doc.intentos_saia.order_by('-creado').first()
            error = (ultimo.mensaje_error[:100] if ultimo and ultimo.mensaje_error else doc.error[:100])
            stdout.write(f'  [FALLO] {doc.nombre_archivo} | {error}')
        if len(fallidos) > 20:
            stdout.write(f'  ... y {len(fallidos) - 20} mas. Ver Excel para detalle completo.')

    if pendientes_revision:
        stdout.write('\n--- PENDIENTES DE REVISION ---')
        for doc in pendientes_revision[:20]:
            meta = getattr(doc, 'metadata', None)
            obs = (meta.observaciones[:80] if meta and meta.observaciones else 'sin observacion')
            stdout.write(f'  [REVISION] {doc.nombre_archivo} | {obs}')
        if len(pendientes_revision) > 20:
            stdout.write(f'  ... y {len(pendientes_revision) - 20} mas. Ver Excel para detalle completo.')

    stdout.write('=' * 60)


