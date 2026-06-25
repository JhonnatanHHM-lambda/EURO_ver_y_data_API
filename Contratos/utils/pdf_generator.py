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

# Altura del membrete
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
    from num2words import num2words
    val = int(valor)
    numero_fmt = f'{val:,}'.replace(',', '.')
    palabras = num2words(val, lang='es').upper()
    return f'{numero_fmt} ({palabras} PESOS COLOMBIANOS)'


def _build_canvas(buf: io.BytesIO) -> tuple:
    c = rl_canvas.Canvas(buf, pagesize=A4)
    w, h = A4

    if os.path.exists(PLANTILLA_PNG):
        c.drawImage(PLANTILLA_PNG, 0, 0, width=w, height=h, mask='auto')

    c.setFillColor(colors.white)
    c.rect(0, h - _HEADER_H, w, _HEADER_H, stroke=0, fill=1)

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


def _draw_paragraphs(c, paras, x, y, width, min_y=120):
    for p in paras:
        pw, ph = p.wrap(width, 9999)
        if y - ph < min_y:
            break
        p.drawOn(c, x, y - ph)
        y -= ph
    return y


# ── Helper: obtener firma empleador activa ────────────────────────────────────

def get_firma_empleador_activa() -> dict | None:
    """
    Retorna dict con info del empleador firmante activo, o None si no hay firma.
    {'usuario': obj, 'imagen': base64str, 'nombre': str, 'cedula': str, 'es_provisional': bool}
    """
    try:
        from Contratos.models import FirmaGH, FirmaProvisional
        firma_gh = FirmaGH.objects.filter(habilitada=True).select_related('usuario').first()
        if firma_gh:
            u = firma_gh.usuario
            return {
                'usuario': u,
                'imagen': firma_gh.firma_imagen,
                'nombre': f'{u.nombres} {u.apellidos}'.strip().upper(),
                'cedula': u.cedula,
                'es_provisional': False,
            }
        prov = FirmaProvisional.objects.select_related('usuario').first()
        if prov:
            u = prov.usuario
            return {
                'usuario': u,
                'imagen': prov.firma_imagen,
                'nombre': f'{u.nombres} {u.apellidos}'.strip().upper(),
                'cedula': u.cedula,
                'es_provisional': True,
            }
    except Exception as e:
        import logging as _log
        _log.getLogger(__name__).warning(f'get_firma_empleador_activa: {e}')
    return None


# ── Cuerpo de cartas ──────────────────────────────────────────────────────────

def _parrafos_no_prorroga(contrato) -> list:
    nombre    = contrato.nombre_completo.upper()
    cargo     = contrato.cargo.title()
    fecha_fin = _fmt_fecha_corta(contrato.fecha_finalizacion)
    fecha_ini = _fmt_fecha_corta(contrato.fecha_inicio_contrato) if contrato.fecha_inicio_contrato else ''
    CIUDAD    = 'Itagüí'

    cuerpo = (
        f'La presente es con el fin de informarle que el día <b>{fecha_fin}</b>, se dará por '
        f'terminado el contrato de trabajo a término fijo firmado entre las partes'
    )
    if fecha_ini:
        cuerpo += f' con fecha inicial del <b>{fecha_ini}</b>'
    cuerpo += ', ya que la empresa ha decidido que dicho contrato no será prorrogado.'

    return [
        Paragraph(f'{CIUDAD}, {_fmt_fecha(date.today())}', _ST_NORMAL),
        Paragraph('&nbsp;', _ST_SMALL),
        Paragraph('Señor(a)', _ST_NORMAL),
        Paragraph(f'<b>{nombre}</b>', _ST_BOLD),
        Paragraph(f'{cargo}', _ST_NORMAL),
        Paragraph('<b>Inversiones Euro S.A.</b>', _ST_NORMAL),
        Paragraph('Ciudad', _ST_NORMAL),
        Paragraph('&nbsp;', _ST_SMALL),
        Paragraph('<b>Asunto: NOTIFICACIÓN PREAVISO</b>', _ST_BOLD),
        Paragraph('&nbsp;', _ST_SMALL),
        Paragraph(cuerpo, _ST_NORMAL),
        Paragraph('&nbsp;', _ST_SMALL),
        Paragraph(
            'Lo anterior, con base en el artículo 46 del Código Sustantivo del Trabajo, '
            'Subrogado L. 50/90 Art. 3 Contrato a término fijo., numeral 1: '
            '[&#8220;Si antes de la fecha de vencimiento del término estipulado, ninguna de '
            'las partes avisare por escrito a la otra su determinación de no prorrogar el '
            'contrato, este se entenderá renovado por un periodo igual al inicialmente '
            'pactado, y así sucesivamente.&#8221;]',
            _ST_NORMAL,
        ),
        Paragraph('&nbsp;', _ST_SMALL),
        Paragraph(
            'Agradecemos su valioso aporte, al tiempo que le deseamos muchos éxitos en su '
            'vida, no sólo laboral, sino también personal.',
            _ST_NORMAL,
        ),
        Paragraph('&nbsp;', _ST_SMALL),
        Paragraph('Atentamente,', _ST_NORMAL),
    ]


def _parrafos_prorroga(contrato) -> list:
    nombre_emp   = contrato.nombre_completo.upper()
    duracion_cod = contrato.duracion_prorroga or ''
    duracion_txt = _DURACION_TEXTO.get(duracion_cod, duracion_cod)
    fecha_fin    = _fmt_fecha_corta(contrato.fecha_fin_prorroga)
    fecha_hoy    = _fmt_fecha_corta(date.today())

    NIT    = '811045607-6'
    REP    = 'CARLOS ALBERTO JARAMILLO CORREA'
    CC_REP = '70.560.257'
    CIUDAD = 'Itagüí'

    return [
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
        Paragraph(
            '<b>SEGUNDA: Vigencia.</b> En lo no modificado por el presente otrosí, '
            'continúan vigentes las condiciones estipuladas.',
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


def _parrafos_terminacion(contrato) -> list:
    nombre    = contrato.nombre_completo.upper()
    cargo     = contrato.cargo.title()
    fecha_fin = _fmt_fecha_corta(contrato.fecha_finalizacion)
    fecha_ini = _fmt_fecha_corta(contrato.fecha_inicio_contrato) if contrato.fecha_inicio_contrato else ''
    CIUDAD    = 'Itagüí'

    return [
        Paragraph(f'{CIUDAD}, {_fmt_fecha(date.today())}', _ST_NORMAL),
        Paragraph('&nbsp;', _ST_SMALL),
        Paragraph('Señor(a)', _ST_NORMAL),
        Paragraph(f'<b>{nombre}</b>', _ST_BOLD),
        Paragraph(f'{cargo}', _ST_NORMAL),
        Paragraph('<b>Inversiones Euro S.A.</b>', _ST_NORMAL),
        Paragraph('Ciudad', _ST_NORMAL),
        Paragraph('&nbsp;', _ST_SMALL),
        Paragraph('<b>Asunto: Terminación de contrato de trabajo por mutuo acuerdo</b>', _ST_BOLD),
        Paragraph('&nbsp;', _ST_SMALL),
        Paragraph(
            f'Por medio de la presente, y de mutuo acuerdo entre las partes, nos permitimos '
            f'informarle que se ha decidido dar por terminado el contrato de trabajo a término '
            f'fijo que lo/la vincula con <b>INVERSIONES EURO S.A.</b>, '
            + (f'con fecha de inicio del <b>{fecha_ini}</b>, ' if fecha_ini else '')
            + f'con efectividad a partir del día <b>{fecha_fin}</b>.',
            _ST_NORMAL,
        ),
        Paragraph('&nbsp;', _ST_SMALL),
        Paragraph(
            'Esta terminación se realiza de conformidad con el numeral 1.° del artículo 61 '
            'del Código Sustantivo del Trabajo, por mutuo consentimiento de empleador y '
            'trabajador, lo cual implica el pago de la liquidación de prestaciones sociales '
            'a que haya lugar conforme a la ley.',
            _ST_NORMAL,
        ),
        Paragraph('&nbsp;', _ST_SMALL),
        Paragraph(
            'Agradecemos el trabajo y dedicación aportados durante su vinculación y le '
            'deseamos éxitos en sus futuros proyectos.',
            _ST_NORMAL,
        ),
        Paragraph('&nbsp;', _ST_SMALL),
        Paragraph('Atentamente,', _ST_NORMAL),
    ]


# ── Función principal de generación ──────────────────────────────────────────

def _generar_pdf_bytes(contrato, firma_data: str = None, firma_empleador: dict = None) -> bytes:
    """
    Genera el PDF con bloque doble de firma: izquierda empleador, derecha empleado.
    firma_data: base64 PNG de la firma del empleado.
    firma_empleador: dict con {'imagen', 'nombre', 'cedula'} del GH/provisional.
    """
    buf = io.BytesIO()
    c, w, h = _build_canvas(buf)

    margin_x   = 2.2 * cm
    margin_top = _HEADER_H + 2.0 * cm
    margin_bot = 3.0 * cm
    content_w  = w - 2 * margin_x
    y_start    = h - margin_top

    SIG_BLOCK_H = 4.5 * cm
    y_min = margin_bot + SIG_BLOCK_H

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

    # ── Bloque doble de firma ────────────────────────────────────────────────
    SIG_W     = content_w * 0.44   # ancho de cada bloque
    GAP       = content_w * 0.12   # separación entre los dos bloques
    emp_x     = margin_x           # empleador (izquierda)
    empldo_x  = margin_x + SIG_W + GAP  # empleado (derecha)
    base_y    = margin_bot + SIG_BLOCK_H - 0.2 * cm

    SIG_IMG_H = 1.8 * cm
    LINE_Y    = base_y + 0.3 * cm
    IMG_Y     = base_y + 0.5 * cm

    def _draw_sig_block(x, label, sig_img_b64, nombre, cedula, fecha_firma_dt=None):
        """Dibuja un bloque de firma (empleador o empleado)."""
        # Etiqueta
        c.setFont('Helvetica', 8)
        c.setFillColor(colors.HexColor('#64748b'))
        c.drawString(x, base_y + 2.7 * cm, label)

        if sig_img_b64:
            try:
                img_data   = base64.b64decode(sig_img_b64.split(',')[-1])
                img_reader = ImageReader(io.BytesIO(img_data))
                c.drawImage(img_reader, x, IMG_Y,
                            width=SIG_W, height=SIG_IMG_H,
                            mask='auto', preserveAspectRatio=True)
            except Exception as e:
                import logging as _log
                _log.getLogger(__name__).error(f'Error dibujando firma en PDF: {e}')
        else:
            c.setStrokeColor(colors.HexColor('#cbd5e1'))
            c.setLineWidth(0.6)
            c.setDash(3, 4)
            c.rect(x, IMG_Y, SIG_W, SIG_IMG_H, stroke=1, fill=0)
            c.setDash()

        # Línea
        c.setStrokeColor(colors.HexColor('#334155'))
        c.setLineWidth(0.5)
        c.line(x, LINE_Y, x + SIG_W, LINE_Y)

        # Nombre y CC
        c.setFont('Helvetica', 8)
        c.setFillColor(colors.HexColor('#475569'))
        c.drawString(x, base_y - 0.05 * cm, nombre.upper())
        c.drawString(x, base_y - 0.4 * cm, f'C.C. {cedula}')

        if fecha_firma_dt:
            fecha_str = fecha_firma_dt.strftime('%d/%m/%Y %H:%M')
            c.setFont('Helvetica', 7)
            c.setFillColor(colors.HexColor('#94a3b8'))
            c.drawString(x, base_y - 0.75 * cm, f'Firmado: {fecha_str}')

    # Bloque empleador (izquierda)
    emp_label = 'El Empleador,'
    emp_img   = firma_empleador.get('imagen') if firma_empleador else None
    emp_nom   = firma_empleador.get('nombre', '') if firma_empleador else ''
    emp_ced   = firma_empleador.get('cedula', '') if firma_empleador else ''
    _draw_sig_block(emp_x, emp_label, emp_img, emp_nom, emp_ced)

    # Bloque empleado (derecha)
    empldo_label = 'El Empleado,' if tipo == 'PRORROGA' else 'El Empleado,'
    empldo_nom   = contrato.nombre_completo
    empldo_ced   = f'{contrato.tipo_documento} {contrato.documento_id}'
    fecha_firma  = contrato.fecha_firma if firma_data and contrato.fecha_firma else None
    _draw_sig_block(empldo_x, empldo_label, firma_data, empldo_nom, empldo_ced, fecha_firma)

    # Sello "FIRMADO" si el empleado ya firmó
    if firma_data and contrato.fecha_firma:
        c.setFont('Helvetica-Bold', 9)
        c.setFillColor(colors.HexColor('#16a34a'))
        c.drawRightString(w - margin_x, base_y + 0.3 * cm, '✓ DOCUMENTO FIRMADO DIGITALMENTE')
    else:
        c.setFont('Helvetica', 8)
        c.setFillColor(colors.HexColor('#94a3b8'))
        c.drawRightString(w - margin_x, base_y + 0.3 * cm, 'Pendiente de firma')

    c.save()
    return buf.getvalue()


def _get_firma_empleador_para_contrato(contrato) -> dict | None:
    """
    Para PDFs firmados (con empleado), recupera el snapshot del empleador
    guardado en RegistroFirmaEmpleador, para mantener consistencia legal.
    Si no existe, usa la firma activa actual.
    """
    try:
        from Contratos.models import RegistroFirmaEmpleador
        reg = (
            RegistroFirmaEmpleador.objects
            .filter(contrato=contrato)
            .order_by('fecha_generacion')
            .first()
        )
        if reg:
            return {
                'imagen': reg.firma_imagen_snapshot,
                'nombre': reg.nombre_empleador,
                'cedula': reg.cedula_empleador,
            }
    except Exception:
        pass
    return get_firma_empleador_activa()


def _generar_y_subir(contrato, firma_data=None, firma_empleador=None) -> str:
    from .minio_client import upload_to_minio

    if firma_empleador is None:
        if firma_data:
            # PDF firmado: usar snapshot guardado para mantener coherencia legal
            firma_empleador = _get_firma_empleador_para_contrato(contrato)
        else:
            firma_empleador = get_firma_empleador_activa()

    pdf_bytes = _generar_pdf_bytes(contrato, firma_data=firma_data, firma_empleador=firma_empleador)
    buf = io.BytesIO(pdf_bytes)

    tipo_lower = contrato.tipo_carta.lower()
    if firma_data:
        key = f'contratos/{contrato.documento_id}/firmado_{contrato.token_firma}.pdf'
    else:
        key = f'contratos/{contrato.documento_id}/{tipo_lower}_{contrato.token_firma}.pdf'

    upload_to_minio(buf, key, content_type='application/pdf')
    return key


def _registrar_firma_empleador(contrato, firma_empleador: dict):
    """Crea RegistroFirmaEmpleador al generar un documento con firma del empleador."""
    if not firma_empleador:
        return
    try:
        from Contratos.models import RegistroFirmaEmpleador
        RegistroFirmaEmpleador.objects.create(
            contrato=contrato,
            tipo_carta=contrato.tipo_carta,
            usuario_empleador=firma_empleador.get('usuario'),
            nombre_empleador=firma_empleador.get('nombre', ''),
            cedula_empleador=firma_empleador.get('cedula', ''),
            firma_imagen_snapshot=firma_empleador.get('imagen', ''),
            es_provisional=firma_empleador.get('es_provisional', False),
        )
    except Exception as e:
        import logging as _log
        _log.getLogger(__name__).error(f'Error registrando firma empleador: {e}')


# ── API pública ───────────────────────────────────────────────────────────────

def generar_carta_no_prorroga(contrato) -> str:
    firma_empleador = get_firma_empleador_activa()
    key = _generar_y_subir(contrato, firma_empleador=firma_empleador)
    _registrar_firma_empleador(contrato, firma_empleador)
    return key


def generar_carta_prorroga(contrato) -> str:
    firma_empleador = get_firma_empleador_activa()
    key = _generar_y_subir(contrato, firma_empleador=firma_empleador)
    _registrar_firma_empleador(contrato, firma_empleador)
    return key


def generar_carta_terminacion(contrato) -> str:
    firma_empleador = get_firma_empleador_activa()
    key = _generar_y_subir(contrato, firma_empleador=firma_empleador)
    _registrar_firma_empleador(contrato, firma_empleador)
    return key


def generar_pdf_firmado(contrato, firma_data: str) -> str:
    # Usa el snapshot del empleador guardado al generar la carta original
    firma_empleador = _get_firma_empleador_para_contrato(contrato)
    return _generar_y_subir(contrato, firma_data=firma_data, firma_empleador=firma_empleador)


def generar_pdf_no_prorroga_firmada(contrato, firma_data: str) -> str:
    """Genera la NO_PRORROGA firmada aunque tipo_carta ya sea PRORROGA/TERMINACION."""
    original_tipo = contrato.tipo_carta
    original_fecha_firma = contrato.fecha_firma
    contrato.tipo_carta = 'NO_PRORROGA'
    contrato.fecha_firma = timezone.now()
    try:
        from .minio_client import upload_to_minio
        firma_empleador = _get_firma_empleador_para_contrato(contrato)
        pdf_bytes = _generar_pdf_bytes(contrato, firma_data=firma_data, firma_empleador=firma_empleador)
        buf = io.BytesIO(pdf_bytes)
        key = f'contratos/{contrato.documento_id}/no_prorroga_firmada_seq_{contrato.token_firma}.pdf'
        upload_to_minio(buf, key, content_type='application/pdf')
        return key
    finally:
        contrato.tipo_carta = original_tipo
        contrato.fecha_firma = original_fecha_firma
