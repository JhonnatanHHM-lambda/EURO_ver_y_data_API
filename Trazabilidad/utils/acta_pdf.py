"""
Generador de PDF del Acta de Carga de Datos.
Usa PLANTILLA LOGO CON OPACIDAD.png como fondo de página completo,
siguiendo exactamente el mismo patrón de euro_generador_actas.
"""
import base64
import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    Image, Paragraph, Spacer, Table, TableStyle, SimpleDocTemplate,
)

from .acta_brand import (
    AZUL, AMARILLO, GRIS_BG, BORDE, TEXTO, SUAVE, FIRMA_BG, BLANCO, VERDE, ROJO,
    PAGE_W, PAGE_H, TOP, BOT, LEFT, RIGHT,
    PLANTILLA_PNG,
    register_fonts, F, to_rml,
)


# ── Callback de página: membrete como fondo (mismo que euro_generador_actas) ──

def _page_cb(canvas, doc):
    if PLANTILLA_PNG:
        canvas.saveState()
        canvas.drawImage(
            PLANTILLA_PNG, 0, 0,
            width=PAGE_W, height=PAGE_H,
            preserveAspectRatio=False, mask=None,
        )
        # Velo blanco semi-transparente sobre el área de contenido
        canvas.setFillColor(colors.Color(1, 1, 1, alpha=0.92))
        canvas.rect(0, BOT, PAGE_W, PAGE_H - TOP - BOT, fill=1, stroke=0)
        canvas.restoreState()

    # Número de página
    canvas.saveState()
    canvas.setFont(F(), 8)
    canvas.setFillColor(SUAVE)
    canvas.drawRightString(PAGE_W - RIGHT, 20, f'Pág. {doc.page}')
    canvas.restoreState()


def _page_revertida(canvas, doc):
    """Callback con marca de agua REVERTIDA."""
    _page_cb(canvas, doc)
    canvas.saveState()
    canvas.setFont(F(True), 52)
    canvas.setFillColor(colors.Color(0.9, 0.15, 0.15, alpha=0.10))
    canvas.translate(PAGE_W / 2, PAGE_H / 2)
    canvas.rotate(35)
    canvas.drawCentredString(0, 0, 'REVERTIDA')
    canvas.restoreState()


# ── Estilos (misma familia tipográfica que euro_generador_actas) ──────────────

def _styles():
    return {
        'title': ParagraphStyle('T',
            fontName=F(True), fontSize=12, leading=16,
            textColor=TEXTO, spaceAfter=6),
        'label': ParagraphStyle('L',
            fontName=F(), fontSize=10, leading=14,
            textColor=TEXTO, spaceAfter=4, alignment=TA_JUSTIFY),
        'section': ParagraphStyle('S',
            fontName=F(True), fontSize=11, leading=15,
            textColor=TEXTO, spaceBefore=10, spaceAfter=5),
        'sub': ParagraphStyle('Sub',
            fontName=F(True), fontSize=10, leading=14,
            textColor=TEXTO, spaceBefore=7, spaceAfter=3),
        'body': ParagraphStyle('B',
            fontName=F(), fontSize=10, leading=14,
            textColor=TEXTO, spaceAfter=5, alignment=TA_JUSTIFY),
        'small': ParagraphStyle('Sm',
            fontName=F(), fontSize=8.5, leading=12, textColor=SUAVE),
        'placeholder': ParagraphStyle('Ph',
            fontName=F(), fontSize=9, leading=13,
            textColor=SUAVE, spaceAfter=4, alignment=TA_JUSTIFY),
        'firma_hdr': ParagraphStyle('FH',
            fontName=F(True), fontSize=8, leading=12, textColor=AZUL),
        'firma_sub': ParagraphStyle('FS',
            fontName=F(), fontSize=9, leading=13, textColor=TEXTO),
        'firma_meta': ParagraphStyle('FM',
            fontName=F(), fontSize=8, leading=11, textColor=SUAVE),
        'banner': ParagraphStyle('Ban',
            fontName=F(True), fontSize=9, leading=14,
            textColor=colors.HexColor('#991B1B')),
    }


# ── Tabla de estadísticas (KPIs al estilo del generador) ─────────────────────

def _tabla_kpis(carga, doc_w, S):
    total  = carga.total_registros
    exit_  = carga.exitosos
    fall_  = carga.fallidos

    def kpi_cell(valor, label, color=AZUL):
        num = ParagraphStyle('KN', fontName=F(True), fontSize=16,
                             textColor=color, leading=20, alignment=TA_CENTER)
        lbl = ParagraphStyle('KL', fontName=F(), fontSize=8,
                             textColor=SUAVE, leading=10, alignment=TA_CENTER)
        return [Paragraph(str(valor), num), Paragraph(label, lbl)]

    data = [[
        kpi_cell(total, 'TOTAL EN ARCHIVO'),
        kpi_cell(exit_, 'CARGADOS', VERDE if exit_ > 0 else SUAVE),
        kpi_cell(fall_, 'CON ERROR', ROJO if fall_ > 0 else SUAVE),
    ]]

    col = doc_w / 3
    t = Table(data, colWidths=[col, col, col])
    t.setStyle(TableStyle([
        ('BACKGROUND',   (0,0),(-1,-1), GRIS_BG),
        ('BOX',          (0,0),(-1,-1), 0.6, BORDE),
        ('INNERGRID',    (0,0),(-1,-1), 0.4, BORDE),
        ('TOPPADDING',   (0,0),(-1,-1), 10),
        ('BOTTOMPADDING',(0,0),(-1,-1), 10),
        ('VALIGN',       (0,0),(-1,-1), 'MIDDLE'),
    ]))
    return t


# ── Tabla de información de la carga ─────────────────────────────────────────

def _tabla_info(carga, doc_w, S):
    fecha_carga = carga.creado.strftime('%d/%m/%Y %H:%M') if carga.creado else '—'
    cargado_por = (carga.cargado_por.obtener_nombre_completo()
                   if carga.cargado_por else '—')
    sede_nombre = carga.sede.nombre if carga.sede else 'Sin sede asignada'

    HDR = ParagraphStyle('IH', fontName=F(True), fontSize=9,
                         textColor=BLANCO, leading=13)
    CEL = ParagraphStyle('IC', fontName=F(), fontSize=9.5,
                         textColor=TEXTO, leading=13)

    data = [
        [Paragraph('<b>ARCHIVO</b>', HDR), Paragraph('<b>HOJA</b>', HDR),
         Paragraph('<b>ORIGEN</b>', HDR)],
        [Paragraph(to_rml(carga.nombre_archivo), CEL),
         Paragraph(to_rml(carga.hoja or '—'), CEL),
         Paragraph(to_rml(carga.origen_datos), CEL)],
        [Paragraph('<b>SEDE</b>', HDR), Paragraph('<b>CARGADO POR</b>', HDR),
         Paragraph('<b>FECHA DE CARGA</b>', HDR)],
        [Paragraph(to_rml(sede_nombre), CEL),
         Paragraph(to_rml(cargado_por), CEL),
         Paragraph(fecha_carga, CEL)],
    ]

    col = doc_w / 3
    t = Table(data, colWidths=[col, col, col])
    t.setStyle(TableStyle([
        ('BACKGROUND',   (0,0),(-1,0), AZUL),
        ('BACKGROUND',   (0,2),(-1,2), AZUL),
        ('LINEBELOW',    (0,0),(-1,0), 1.5, AMARILLO),
        ('LINEBELOW',    (0,2),(-1,2), 1.5, AMARILLO),
        ('BACKGROUND',   (0,1),(-1,1), GRIS_BG),
        ('BACKGROUND',   (0,3),(-1,3), GRIS_BG),
        ('BOX',          (0,0),(-1,-1), 0.6, BORDE),
        ('INNERGRID',    (0,0),(-1,-1), 0.4, BORDE),
        ('TOPPADDING',   (0,0),(-1,-1), 6),
        ('BOTTOMPADDING',(0,0),(-1,-1), 6),
        ('LEFTPADDING',  (0,0),(-1,-1), 8),
        ('RIGHTPADDING', (0,0),(-1,-1), 8),
        ('VALIGN',       (0,0),(-1,-1), 'MIDDLE'),
    ]))
    return t


# ── Tabla de errores ──────────────────────────────────────────────────────────

def _tabla_errores(errores, doc_w):
    LABELS = {
        'sin_documento':       'Sin número de documento',
        'sin_nombre':          'Sin nombre completo',
        'duplicado':           'Registro duplicado',
        'error_inesperado':    'Error de formato / longitud',
        'nombre_incoherente':  'Nombre incoherente con BD',
    }
    MAX_FILAS = 20

    HDR = ParagraphStyle('EH', fontName=F(True), fontSize=9,
                         textColor=BLANCO, leading=13)
    CEL = ParagraphStyle('EC', fontName=F(), fontSize=9,
                         textColor=TEXTO, leading=13)

    _ts_base = TableStyle([
        ('BOX',          (0,0),(-1,-1), 0.6, BORDE),
        ('INNERGRID',    (0,1),(-1,-1), 0.4, BORDE),
        ('TOPPADDING',   (0,0),(-1,-1), 5),
        ('BOTTOMPADDING',(0,0),(-1,-1), 5),
        ('LEFTPADDING',  (0,0),(-1,-1), 8),
        ('RIGHTPADDING', (0,0),(-1,-1), 8),
        ('VALIGN',       (0,0),(-1,-1), 'TOP'),
    ])

    tiene_hojas = any(e.get('hoja') for e in errores)

    if tiene_hojas:
        # ── Vista agrupada por hoja ───────────────────────────────────────────
        por_hoja = {}
        for e in errores:
            hoja = e.get('hoja') or '—'
            tipo = e.get('tipo', 'error_inesperado')
            por_hoja.setdefault(hoja, {}).setdefault(tipo, []).append(
                e.get('fila_hoja') or e.get('fila', '?'))

        tablas = []
        for hoja, tipos_en_hoja in por_hoja.items():
            total_hoja = sum(len(v) for v in tipos_en_hoja.values())
            data = [[
                Paragraph(f'<b>Hoja: {to_rml(hoja)}</b>', HDR),
                Paragraph(f'<b>{total_hoja} filas</b>', HDR),
                Paragraph('', HDR),
            ]]
            for tipo, filas in tipos_en_hoja.items():
                mostrar   = [str(f) for f in filas[:MAX_FILAS]]
                filas_txt = ', '.join(mostrar)
                if len(filas) > MAX_FILAS:
                    filas_txt += f' (+{len(filas)-MAX_FILAS} más)'
                data.append([
                    Paragraph(LABELS.get(tipo, tipo), CEL),
                    Paragraph(str(len(filas)), CEL),
                    Paragraph(filas_txt, CEL),
                ])
            t = Table(data, colWidths=[doc_w * 0.40, doc_w * 0.10, doc_w * 0.50])
            ts = TableStyle(list(_ts_base._cmds) + [
                ('BACKGROUND', (0,0),(-1,0), AZUL),
                ('BACKGROUND', (0,1),(-1,-1), GRIS_BG),
            ])
            t.setStyle(ts)
            tablas.append(t)
            tablas.append(Spacer(1, 5))
        return tablas

    else:
        # ── Vista plana (hoja única) ──────────────────────────────────────────
        grupos = {}
        for e in errores:
            tipo = e.get('tipo', 'error_inesperado')
            grupos.setdefault(tipo, []).append(
                e.get('fila_hoja') or e.get('fila', '?'))

        data = [[Paragraph('<b>TIPO DE ERROR</b>', HDR),
                 Paragraph('<b>CANT.</b>', HDR),
                 Paragraph('<b>FILAS</b>', HDR)]]
        for tipo, filas in grupos.items():
            mostrar   = [str(f) for f in filas[:MAX_FILAS]]
            filas_txt = ', '.join(mostrar)
            if len(filas) > MAX_FILAS:
                filas_txt += f' (+{len(filas)-MAX_FILAS} más)'
            data.append([
                Paragraph(LABELS.get(tipo, tipo), CEL),
                Paragraph(str(len(filas)), CEL),
                Paragraph(filas_txt, CEL),
            ])
        t = Table(data, colWidths=[doc_w * 0.45, doc_w * 0.1, doc_w * 0.45])
        ts = TableStyle(list(_ts_base._cmds) + [
            ('BACKGROUND', (0,0),(-1,0), ROJO),
            ('BACKGROUND', (0,1),(-1,-1), GRIS_BG),
        ])
        t.setStyle(ts)
        return t


# ── Tabla de firma (1 columna: Gestión Humana) ────────────────────────────────

def _tabla_firmas(carga, doc_w, S):
    nombre = carga.firma_gh_nombre or '___________________'
    cargo  = carga.firma_gh_cargo  or '___________________'
    fecha  = (carga.firma_gh_fecha.strftime('%d/%m/%Y %H:%M')
              if carga.firma_gh_fecha else '___/___/_______')

    gh_content = [Paragraph('GESTIÓN HUMANA · EURO SUPERMERCADOS', S['firma_hdr'])]

    if carga.firma_gh_imagen:
        try:
            img_data = carga.firma_gh_imagen
            if img_data.startswith('data:'):
                img_data = img_data.split(',', 1)[1]
            img_bytes = base64.b64decode(img_data)
            gh_content.append(Image(io.BytesIO(img_bytes), width=doc_w * 0.35, height=52))
        except Exception:
            gh_content.append(Paragraph('________________________________', S['firma_sub']))
            gh_content.append(Spacer(1, 20))
    else:
        gh_content.append(Paragraph('________________________________', S['firma_sub']))
        gh_content.append(Spacer(1, 20))

    gh_content += [
        Spacer(1, 4),
        Paragraph(f'<b>{to_rml(nombre)}</b>', S['firma_sub']),
        Paragraph(to_rml(cargo), S['firma_meta']),
        Paragraph(f'Fecha: {fecha}', S['firma_meta']),
    ]

    t = Table([[gh_content]], colWidths=[doc_w])
    t.setStyle(TableStyle([
        ('BACKGROUND',   (0,0),(-1,-1), FIRMA_BG),
        ('BOX',          (0,0),(-1,-1), 0.8, AZUL),
        ('TOPPADDING',   (0,0),(-1,-1), 12),
        ('BOTTOMPADDING',(0,0),(-1,-1), 12),
        ('LEFTPADDING',  (0,0),(-1,-1), 14),
        ('RIGHTPADDING', (0,0),(-1,-1), 14),
        ('VALIGN',       (0,0),(-1,-1), 'TOP'),
    ]))
    return t


# ── Función principal ─────────────────────────────────────────────────────────

def generar_pdf_acta(carga) -> bytes:
    """Genera el PDF del acta on-demand. Retorna bytes del PDF."""
    register_fonts()
    S         = _styles()
    buf       = io.BytesIO()
    revertida = not carga.estado

    doc = SimpleDocTemplate(
        buf, pagesize=(PAGE_W, PAGE_H),
        leftMargin=LEFT, rightMargin=RIGHT,
        topMargin=TOP, bottomMargin=BOT,
    )
    doc_w = PAGE_W - LEFT - RIGHT
    flow  = []

    # ── Banner REVERTIDA ──────────────────────────────────────────────────
    if revertida:
        fecha_rev = carga.modificado.strftime('%d/%m/%Y %H:%M') if carga.modificado else '—'
        ban_data = [[Paragraph(
            f'⚠  CARGA REVERTIDA  —  Los registros fueron eliminados el '
            f'<b>{fecha_rev}</b>. Este documento es el acta histórica del proceso.',
            S['banner'],
        )]]
        ban = Table(ban_data, colWidths=[doc_w])
        ban.setStyle(TableStyle([
            ('BACKGROUND',   (0,0),(-1,-1), colors.HexColor('#FEE2E2')),
            ('BOX',          (0,0),(-1,-1), 1.2, colors.HexColor('#F87171')),
            ('TOPPADDING',   (0,0),(-1,-1), 9),
            ('BOTTOMPADDING',(0,0),(-1,-1), 9),
            ('LEFTPADDING',  (0,0),(-1,-1), 12),
            ('RIGHTPADDING', (0,0),(-1,-1), 12),
        ]))
        flow.append(ban)
        flow.append(Spacer(1, 10))

    # ── Título ────────────────────────────────────────────────────────────
    flow.append(Paragraph('<b>ACTA DE CARGA DE DATOS</b>', S['title']))
    flow.append(Spacer(1, 4))

    # ── 1. Información de la carga ─────────────────────────────────────
    flow.append(Paragraph('<b>1. Información de la carga</b>', S['section']))
    flow.append(_tabla_info(carga, doc_w, S))
    flow.append(Spacer(1, 10))

    # ── 2. Estadísticas de homologación ────────────────────────────────
    flow.append(Paragraph('<b>2. Estadísticas de homologación</b>', S['section']))
    flow.append(_tabla_kpis(carga, doc_w, S))
    flow.append(Spacer(1, 10))

    # ── 3. Errores ──────────────────────────────────────────────────────
    errores = carga.errores or []
    flow.append(Paragraph('<b>3. Detalle de registros con error</b>', S['section']))
    if errores:
        resultado_errores = _tabla_errores(errores, doc_w)
        if isinstance(resultado_errores, list):
            flow.extend(resultado_errores)   # múltiples tablas (por hoja)
        elif resultado_errores:
            flow.append(resultado_errores)   # tabla única
    else:
        flow.append(Paragraph(
            'No se registraron errores. Todos los registros fueron procesados correctamente.',
            S['placeholder']))
    flow.append(Spacer(1, 10))

    # ── 4. Certificación técnica ────────────────────────────────────────
    flow.append(Paragraph('<b>4. Certificación técnica</b>', S['section']))
    flow.append(Paragraph(
        'El presente proceso de carga y homologación fue ejecutado siguiendo los estándares de '
        'calidad definidos en el Acta de Inicio del proyecto. '
        'Los datos han sido homologados al modelo unificado de trazabilidad de Euro Supermercados, '
        'con validación de campos obligatorios, detección de duplicados, inferencia de estados '
        'y limpieza de valores incorrectos. '
        'Este documento constituye evidencia técnica del proceso ejecutado.',
        S['body'],
    ))
    flow.append(Spacer(1, 18))

    # ── 5. Firmas ────────────────────────────────────────────────────────
    flow.append(Paragraph('<b>5. Firmas</b>', S['section']))
    flow.append(_tabla_firmas(carga, doc_w, S))

    cb = _page_revertida if revertida else _page_cb
    doc.build(flow, onFirstPage=cb, onLaterPages=cb)
    return buf.getvalue()
