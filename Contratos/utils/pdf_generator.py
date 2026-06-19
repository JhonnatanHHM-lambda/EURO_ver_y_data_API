"""Generador de PDFs de contratos usando ReportLab + plantilla corporativa."""

import io
import os
import base64
from datetime import date
from django.utils import timezone

from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph
from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT, TA_CENTER
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader

# ── Rutas de recursos ─────────────────────────────────────────────────────────
_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # Contratos/
_RECURSOS = os.path.join(_BASE, '..', 'recursos')
PLANTILLA_PNG = os.path.join(_RECURSOS, 'plantilla_acta.png')
LOGO_PNG      = os.path.join(_RECURSOS, 'euro-logo.png')

# Altura del membrete (banda superior con logos y tiras decorativas)
_HEADER_H = 3.4 * cm

# ── Estilos tipográficos ──────────────────────────────────────────────────────
_ST_NORMAL = ParagraphStyle(
    'normal', fontName='Helvetica', fontSize=10, leading=14,
    alignment=TA_JUSTIFY, spaceAfter=8,
)
_ST_BOLD = ParagraphStyle(
    'bold', fontName='Helvetica-Bold', fontSize=10, leading=14,
    alignment=TA_LEFT, spaceAfter=4,
)
_ST_CENTER = ParagraphStyle(
    'center', fontName='Helvetica-Bold', fontSize=11, leading=14,
    alignment=TA_CENTER, spaceAfter=10,
)
_ST_SMALL = ParagraphStyle(
    'small', fontName='Helvetica', fontSize=9, leading=12,
    alignment=TA_LEFT, spaceAfter=4,
)
_ST_FIRMA = ParagraphStyle(
    'firma', fontName='Helvetica', fontSize=9, leading=12,
    alignment=TA_CENTER,
)
_ST_TITULO_OTROSI = ParagraphStyle(
    'titulo_otrosi', fontName='Helvetica-Bold', fontSize=11, leading=16,
    alignment=TA_CENTER, spaceAfter=10,
)

_DURACION_TEXTO = {
    '1_MES':    'Un (1) mes',
    '2_MESES':  'Dos (2) meses',
    '3_MESES':  'Tres (3) meses',
    '4_MESES':  'Cuatro (4) meses',
    '5_MESES':  'Cinco (5) meses',
    '6_MESES':  'Seis (6) meses',
    '7_MESES':  'Siete (7) meses',
    '8_MESES':  'Ocho (8) meses',
    '9_MESES':  'Nueve (9) meses',
    '10_MESES': 'Diez (10) meses',
    '11_MESES': 'Once (11) meses',
    '12_MESES': 'Doce (12) meses',
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def _to_date(d):
    if d is None:
        return None
    if isinstance(d, str):
        from datetime import datetime as _dt
        return _dt.strptime(d[:10], '%Y-%m-%d').date()
    return d


def _fmt_fecha(d) -> str:
    d = _to_date(d)
    if not d:
        return ''
    MESES = ['enero','febrero','marzo','abril','mayo','junio',
             'julio','agosto','septiembre','octubre','noviembre','diciembre']
    return f'{d.day} de {MESES[d.month - 1]} de {d.year}'


def _fmt_fecha_corta(d) -> str:
    d = _to_date(d)
    return d.strftime('%d/%m/%Y') if d else ''


def _duracion_label(codigo: str) -> str:
    return {'3_MESES': 'tres (3) meses', '6_MESES': 'seis (6) meses',
            '12_MESES': 'doce (12) meses'}.get(codigo, codigo)


def _fmt_sueldo(valor) -> str:
    """Convierte un valor numérico al formato legal colombiano.
    Ej: 2500000 → '2.500.000 (DOS MILLONES QUINIENTOS MIL PESOS COLOMBIANOS)'
    """
    from num2words import num2words
    val = int(valor)
    numero_fmt = f'{val:,}'.replace(',', '.')
    palabras = num2words(val, lang='es').upper()
    return f'{numero_fmt} ({palabras} PESOS COLOMBIANOS)'


def _build_canvas(buf: io.BytesIO) -> tuple:
    """Crea canvas A4 con la plantilla corporativa, sin el membrete superior."""
    c = rl_canvas.Canvas(buf, pagesize=A4)
    w, h = A4  # 595.28 x 841.89 pts

    # Fondo con plantilla (incluye marca de agua y footer decorativo)
    if os.path.exists(PLANTILLA_PNG):
        c.drawImage(PLANTILLA_PNG, 0, 0, width=w, height=h, mask='auto')

    # Cubrir el membrete (banda superior con logos y tiras de color) con blanco
    c.setFillColor(colors.white)
    c.rect(0, h - _HEADER_H, w, _HEADER_H, stroke=0, fill=1)

    # Re-colocar el logo Euro Supermercados en la esquina superior derecha
    if os.path.exists(LOGO_PNG):
        logo_side = 2.4 * cm
        margin    = 0.45 * cm
        c.drawImage(
            LOGO_PNG,
            w - logo_side - margin,
            h - logo_side - margin,
            width=logo_side, height=logo_side,
            mask='auto', preserveAspectRatio=True,
        )

    return c, w, h


def _draw_paragraphs(c: rl_canvas.Canvas, paras: list, x: float, y: float,
                     width: float, min_y: float = 120) -> float:
    """Dibuja párrafos y retorna la posición Y final."""
    for p in paras:
        pw, ph = p.wrap(width, 9999)
        if y - ph < min_y:
            break
        p.drawOn(c, x, y - ph)
        y -= ph
    return y


# ── Cuerpo de cartas ──────────────────────────────────────────────────────────

def _parrafos_no_prorroga(contrato) -> list:
    nombre = contrato.nombre_completo.title()
    cargo  = contrato.cargo.title()
    sede   = contrato.sede.nombre if contrato.sede else ''
    fecha_fin = _fmt_fecha(contrato.fecha_finalizacion)

    return [
        Paragraph(f'<b>Ciudad y Fecha:</b> {_fmt_fecha(date.today())}', _ST_NORMAL),
        Paragraph('&nbsp;', _ST_SMALL),
        Paragraph('Señor(a)', _ST_NORMAL),
        Paragraph(f'<b>{contrato.nombre_completo.upper()}</b>', _ST_BOLD),
        Paragraph(f'{contrato.tipo_documento} N.° {contrato.documento_id}', _ST_NORMAL),
        Paragraph(f'Cargo: {cargo}', _ST_NORMAL),
        Paragraph(f'Sede: {sede}', _ST_NORMAL),
        Paragraph('&nbsp;', _ST_SMALL),
        Paragraph('<b>Asunto: No renovación de contrato de trabajo</b>', _ST_BOLD),
        Paragraph('&nbsp;', _ST_SMALL),
        Paragraph(f'Estimado(a) señor(a) {nombre}:', _ST_NORMAL),
        Paragraph('&nbsp;', _ST_SMALL),
        Paragraph(
            f'Por medio de la presente, y de conformidad con lo establecido en el artículo 46 '
            f'del Código Sustantivo del Trabajo, nos permitimos informarle que el contrato de '
            f'trabajo a término fijo que lo/la vincula con <b>EURO SUPERMERCADOS S.A.S.</b>, '
            f'vence el día <b>{fecha_fin}</b>.',
            _ST_NORMAL,
        ),
        Paragraph('&nbsp;', _ST_SMALL),
        Paragraph(
            f'En este sentido, la empresa ha tomado la decisión de <b>NO RENOVAR</b> dicho '
            f'contrato, razón por la cual el mismo terminará en la fecha indicada, sin que '
            f'exista derecho a indemnización alguna conforme a la ley.',
            _ST_NORMAL,
        ),
        Paragraph('&nbsp;', _ST_SMALL),
        Paragraph(
            f'Agradecemos el desempeño y dedicación durante su vinculación con la empresa, '
            f'y le deseamos éxitos en sus proyectos personales y profesionales.',
            _ST_NORMAL,
        ),
        Paragraph('&nbsp;', _ST_SMALL),
        Paragraph('Atentamente,', _ST_NORMAL),
        Paragraph('&nbsp;', _ST_SMALL),
        Paragraph('&nbsp;', _ST_SMALL),
        Paragraph('<b>EURO SUPERMERCADOS S.A.S.</b>', _ST_BOLD),
        Paragraph('Gestión Humana', _ST_NORMAL),
    ]


def _parrafos_prorroga(contrato) -> list:
    """Genera el otrosí de prórroga con estructura legal formal."""
    nombre_emp   = contrato.nombre_completo.upper()
    duracion_cod = contrato.duracion_prorroga or ''
    duracion_txt = _DURACION_TEXTO.get(duracion_cod, duracion_cod)
    fecha_fin    = _fmt_fecha_corta(contrato.fecha_fin_prorroga)
    fecha_hoy    = _fmt_fecha_corta(date.today())

    NIT    = '811045607-6'
    REP    = 'CARLOS ALBERTO JARAMILLO CORREA'
    CC_REP = '70.560.257'
    CIUDAD = 'Itagüí'

    parrafos = [
        Paragraph(
            f'OTROSI AL CONTRATO CELEBRADO ENTRE INVERSIONES EURO S.A<br/>'
            f'Y <u><b>{nombre_emp}</b></u>',
            _ST_TITULO_OTROSI,
        ),
        Paragraph('&nbsp;', _ST_SMALL),
        Paragraph(
            f'Entre los suscritos a saber <b>INVERSIONES EURO S.A.</b>, Entidad con domicilio '
            f'principal en el municipio de {CIUDAD}, Antioquia, identificada con Nit. {NIT}, '
            f'representada legalmente por <b>{REP}</b>, identificado con la cédula de ciudadanía '
            f'Nº {CC_REP}, en adelante <b>EL EMPLEADOR</b>; y <b>{nombre_emp}</b>, '
            f'identificado(a) con la cédula de ciudadanía Nº {contrato.documento_id}, '
            f'en adelante <b>EL EMPLEADO</b> y conjuntamente <b>LAS PARTES</b>, han convenido '
            f'prorrogar el Contrato de Trabajo Fijo en los aspectos que se relacionan y regulan '
            f'por las siguientes cláusulas:',
            _ST_NORMAL,
        ),
        Paragraph('&nbsp;', _ST_SMALL),
        Paragraph(
            f'<b>PRIMERA: Duración del Contrato.</b> Las Partes convienen prorrogar la duración '
            f'del Contrato por un término adicional de {duracion_txt}, es decir, hasta el '
            f'<b>{fecha_fin}</b>, Contrato que no será prorrogado y por lo tanto en dicha fecha '
            f'terminará definitivamente sin necesidad de ningún preaviso adicional al que se '
            f'establece y declara en la presente cláusula.',
            _ST_NORMAL,
        ),
        Paragraph('&nbsp;', _ST_SMALL),
    ]

    clausula_vigencia = 'SEGUNDA'
    parrafos += [
        Paragraph(
            f'<b>{clausula_vigencia}: Vigencia.</b> En lo no modificado por el presente otrosí, '
            f'continúan vigentes las condiciones estipuladas.',
            _ST_NORMAL,
        ),
        Paragraph('&nbsp;', _ST_SMALL),
        Paragraph(
            f'Para constancia de lo estipulado, se firma en el Municipio de {CIUDAD} al día '
            f'<b>{fecha_hoy}</b>.',
            _ST_NORMAL,
        ),
        Paragraph('&nbsp;', _ST_SMALL),
        Paragraph('Cordialmente,', _ST_NORMAL),
    ]
    return parrafos


def _parrafos_terminacion(contrato) -> list:
    nombre    = contrato.nombre_completo.title()
    cargo     = contrato.cargo.title()
    sede      = contrato.sede.nombre if contrato.sede else ''
    fecha_fin = _fmt_fecha(contrato.fecha_finalizacion)

    return [
        Paragraph(f'<b>Ciudad y Fecha:</b> {_fmt_fecha(date.today())}', _ST_NORMAL),
        Paragraph('&nbsp;', _ST_SMALL),
        Paragraph('Señor(a)', _ST_NORMAL),
        Paragraph(f'<b>{contrato.nombre_completo.upper()}</b>', _ST_BOLD),
        Paragraph(f'{contrato.tipo_documento} N.° {contrato.documento_id}', _ST_NORMAL),
        Paragraph(f'Cargo: {cargo}', _ST_NORMAL),
        Paragraph(f'Sede: {sede}', _ST_NORMAL),
        Paragraph('&nbsp;', _ST_SMALL),
        Paragraph('<b>Asunto: Terminación de contrato de trabajo por mutuo acuerdo</b>', _ST_BOLD),
        Paragraph('&nbsp;', _ST_SMALL),
        Paragraph(f'Estimado(a) señor(a) {nombre}:', _ST_NORMAL),
        Paragraph('&nbsp;', _ST_SMALL),
        Paragraph(
            f'Por medio de la presente, y de mutuo acuerdo entre las partes, nos permitimos '
            f'informarle que se ha decidido dar por terminado el contrato de trabajo que lo/la '
            f'vincula con <b>EURO SUPERMERCADOS S.A.S.</b>, con efectividad a partir del día '
            f'<b>{fecha_fin}</b>.',
            _ST_NORMAL,
        ),
        Paragraph('&nbsp;', _ST_SMALL),
        Paragraph(
            f'Esta terminación se realiza de conformidad con el numeral 1.° del artículo 61 '
            f'del Código Sustantivo del Trabajo, por mutuo consentimiento de empleador y '
            f'trabajador, lo cual implica el pago de la liquidación de prestaciones sociales '
            f'a que haya lugar conforme a la ley.',
            _ST_NORMAL,
        ),
        Paragraph('&nbsp;', _ST_SMALL),
        Paragraph(
            f'Agradecemos el trabajo y dedicación aportados durante su vinculación y le '
            f'deseamos éxitos en sus futuros proyectos.',
            _ST_NORMAL,
        ),
        Paragraph('&nbsp;', _ST_SMALL),
        Paragraph('Atentamente,', _ST_NORMAL),
        Paragraph('&nbsp;', _ST_SMALL),
        Paragraph('&nbsp;', _ST_SMALL),
        Paragraph('<b>EURO SUPERMERCADOS S.A.S.</b>', _ST_BOLD),
        Paragraph('Gestión Humana', _ST_NORMAL),
    ]


# ── Función principal de generación ──────────────────────────────────────────

def _generar_pdf_bytes(contrato, firma_data: str = None) -> bytes:
    """
    Genera el PDF de la carta (con o sin firma) y retorna los bytes.
    firma_data: base64 PNG de la firma. Si se provee, se pinta sobre el espacio reservado.
    El bloque de firma SIEMPRE se dibuja al pie; vacío cuando no hay firma.
    """
    buf = io.BytesIO()
    c, w, h = _build_canvas(buf)

    # Área de contenido
    margin_x   = 2.2 * cm
    margin_top = _HEADER_H + 2.0 * cm
    margin_bot = 3.0 * cm
    content_w  = w - 2 * margin_x
    y_start    = h - margin_top

    # Reservar siempre espacio para el bloque de firma al pie
    SIG_BLOCK_H = 4.0 * cm
    y_min = margin_bot + SIG_BLOCK_H

    # Párrafos según tipo de carta
    tipo = contrato.tipo_carta
    if tipo == 'NO_PRORROGA':
        parrafos = _parrafos_no_prorroga(contrato)
    elif tipo == 'PRORROGA':
        parrafos = _parrafos_prorroga(contrato)
    elif tipo == 'TERMINACION':
        parrafos = _parrafos_terminacion(contrato)
    else:
        parrafos = _parrafos_no_prorroga(contrato)

    y = y_start
    for p in parrafos:
        pw, ph = p.wrap(content_w, 9999)
        if y - ph < y_min:
            break
        p.drawOn(c, margin_x, y - ph)
        y -= ph

    # ── Bloque de firma (siempre visible) ────────────────────────────────────
    sig_x   = margin_x
    sig_w   = content_w * 0.58
    # base del bloque de firma: arriba del footer con un poco de margen
    base_y  = margin_bot + SIG_BLOCK_H - 0.2 * cm

    # Etiqueta firma
    sig_label = 'El Empleado,' if contrato.tipo_carta == 'PRORROGA' else 'Firma del empleado:'
    c.setFont('Helvetica', 8)
    c.setFillColor(colors.HexColor('#64748b'))
    c.drawString(sig_x, base_y + 2.6 * cm, sig_label)

    if firma_data:
        # Dibujar imagen de firma encima del espacio reservado
        try:
            img_data   = base64.b64decode(firma_data.split(',')[-1])
            img_reader = ImageReader(io.BytesIO(img_data))
            c.drawImage(img_reader, sig_x, base_y + 0.5 * cm,
                        width=sig_w, height=1.9 * cm,
                        mask='auto', preserveAspectRatio=True)
        except Exception as e:
            import logging as _log
            _log.getLogger(__name__).error(f'Error dibujando firma en PDF: {e}')
    else:
        # Espacio vacío con borde punteado para indicar dónde va la firma
        c.setStrokeColor(colors.HexColor('#cbd5e1'))
        c.setLineWidth(0.6)
        c.setDash(3, 4)
        c.rect(sig_x, base_y + 0.4 * cm, sig_w, 1.9 * cm, stroke=1, fill=0)
        c.setDash()   # restaurar línea sólida

    # Línea horizontal bajo el espacio de firma
    c.setStrokeColor(colors.HexColor('#334155'))
    c.setLineWidth(0.5)
    c.line(sig_x, base_y + 0.3 * cm, sig_x + sig_w, base_y + 0.3 * cm)

    # Nombre y documento (con separación respecto a la línea)
    c.setFont('Helvetica', 8)
    c.setFillColor(colors.HexColor('#475569'))
    c.drawString(sig_x, base_y - 0.05 * cm,
                 f'{contrato.nombre_completo.upper()}  —  '
                 f'{contrato.tipo_documento} {contrato.documento_id}')

    if firma_data and contrato.fecha_firma:
        fecha_str = contrato.fecha_firma.strftime('%d/%m/%Y %H:%M')
        c.drawString(sig_x, base_y - 0.4 * cm, f'Firmado digitalmente el {fecha_str}')

        # Sello verde "FIRMADO"
        c.setFont('Helvetica-Bold', 9)
        c.setFillColor(colors.HexColor('#16a34a'))
        c.drawRightString(w - margin_x, base_y + 0.3 * cm, '✓ DOCUMENTO FIRMADO DIGITALMENTE')
    else:
        # Indicación de pendiente en gris
        c.setFont('Helvetica', 8)
        c.setFillColor(colors.HexColor('#94a3b8'))
        c.drawRightString(w - margin_x, base_y + 0.3 * cm, 'Pendiente de firma')

    c.save()
    return buf.getvalue()


def _generar_y_subir(contrato, firma_data=None) -> str:
    """Genera el PDF, lo sube a MinIO y retorna la clave."""
    from .minio_client import upload_to_minio

    pdf_bytes = _generar_pdf_bytes(contrato, firma_data=firma_data)
    buf = io.BytesIO(pdf_bytes)

    tipo_lower = contrato.tipo_carta.lower()
    if firma_data:
        key = f'contratos/{contrato.documento_id}/firmado_{contrato.token_firma}.pdf'
    else:
        key = f'contratos/{contrato.documento_id}/{tipo_lower}_{contrato.token_firma}.pdf'

    upload_to_minio(buf, key, content_type='application/pdf')
    return key


# ── API pública ───────────────────────────────────────────────────────────────

def generar_carta_no_prorroga(contrato) -> str:
    return _generar_y_subir(contrato)


def generar_carta_prorroga(contrato) -> str:
    return _generar_y_subir(contrato)


def generar_carta_terminacion(contrato) -> str:
    return _generar_y_subir(contrato)


def generar_pdf_firmado(contrato, firma_data: str) -> str:
    return _generar_y_subir(contrato, firma_data=firma_data)


def generar_pdf_no_prorroga_firmada(contrato, firma_data: str) -> str:
    """Genera la NO_PRORROGA firmada aunque tipo_carta ya sea PRORROGA/TERMINACION (firma secuencial)."""
    original_tipo = contrato.tipo_carta
    original_fecha_firma = contrato.fecha_firma
    contrato.tipo_carta = 'NO_PRORROGA'
    contrato.fecha_firma = timezone.now()
    try:
        from .minio_client import upload_to_minio
        pdf_bytes = _generar_pdf_bytes(contrato, firma_data=firma_data)
        buf = io.BytesIO(pdf_bytes)
        key = f'contratos/{contrato.documento_id}/no_prorroga_firmada_seq_{contrato.token_firma}.pdf'
        upload_to_minio(buf, key, content_type='application/pdf')
        return key
    finally:
        contrato.tipo_carta = original_tipo
        contrato.fecha_firma = original_fecha_firma
