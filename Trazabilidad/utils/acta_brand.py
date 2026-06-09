"""Constantes de marca y helpers compartidos para el generador de actas."""
import os
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# ── Rutas de recursos ──────────────────────────────────────────────────────────
_BASE  = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_REC   = os.path.join(_BASE, 'recursos')
_FONTS = os.path.join(_REC, 'fonts')

def _res(name):
    p = os.path.join(_REC, name)
    return p if os.path.exists(p) else None

LOGO_EURO     = _res('euro-logo.png')
PLANTILLA_PNG = _res('plantilla_acta.png')  # membrete completo (fondo de página)

# ── Paleta (misma que euro_generador_actas) ───────────────────────────────────
AZUL      = colors.HexColor('#27348B')
AMARILLO  = colors.HexColor('#FFE302')
GRIS_BG   = colors.HexColor('#F5F6FA')
BORDE     = colors.HexColor('#D8DCF0')
TEXTO     = colors.HexColor('#2C2C2C')
SUAVE     = colors.HexColor('#666666')
FIRMA_BG  = colors.HexColor('#EEF0F8')
BLANCO    = colors.white
VERDE     = colors.HexColor('#16A34A')
ROJO      = colors.HexColor('#DC2626')

PAGE_W, PAGE_H = letter

# ── Márgenes (igual que euro_generador_actas) ─────────────────────────────────
TOP    = 115.0
BOT    =  68.0
LEFT   =  54.0
RIGHT  =  54.0


def register_fonts():
    """Registra Montserrat en ReportLab (idempotente)."""
    try:
        pdfmetrics.getFont('Montserrat')
        return
    except KeyError:
        pass
    try:
        pdfmetrics.registerFont(TTFont('Montserrat',      os.path.join(_FONTS, 'Montserrat-Regular.ttf')))
        pdfmetrics.registerFont(TTFont('Montserrat-Bold', os.path.join(_FONTS, 'Montserrat-Bold.ttf')))
        pdfmetrics.registerFont(TTFont('Montserrat-Med',  os.path.join(_FONTS, 'Montserrat-Medium.ttf')))
        pdfmetrics.registerFontFamily('Montserrat', normal='Montserrat', bold='Montserrat-Bold')
    except Exception:
        pass


def F(bold=False):
    """Nombre de fuente disponible."""
    try:
        pdfmetrics.getFont('Montserrat')
        return 'Montserrat-Bold' if bold else 'Montserrat'
    except KeyError:
        return 'Helvetica-Bold' if bold else 'Helvetica'


def to_rml(text):
    from html import escape
    if not text:
        return ''
    return escape(str(text)).replace('\n', '<br/>')
