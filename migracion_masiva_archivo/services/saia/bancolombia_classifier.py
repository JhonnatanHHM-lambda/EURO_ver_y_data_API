import os
import re
import unicodedata

_MESES_ES = {
    'ENERO': 1, 'FEBRERO': 2, 'MARZO': 3, 'ABRIL': 4,
    'MAYO': 5, 'JUNIO': 6, 'JULIO': 7, 'AGOSTO': 8,
    'SEPTIEMBRE': 9, 'OCTUBRE': 10, 'NOVIEMBRE': 11, 'DICIEMBRE': 12,
}

# Sub-expedientes canónicos dentro del expediente BANCOLOMBIA en SAIA.
BANCOLOMBIA_SUBEXPEDIENTES = [
    'CONCILIACION BANCARIA 2016',
    'CONCILIACION BANCARIA BANCOLOMBIA CTA AHORROS 2016',
    'CONCILIACION PROSEGUIR ENE - SEP 2016',
    'CONCILIACION PROSEGUIR OCT - DIC 2016',
    'CONCILIACION BANCARIA CTA CTE NOV - DIC',
    'ENERO - DICIEMBRE 2015',
    'ENERO - DICIEMBRE 2016',
    'ENERO - JUNIO 2017',
    'FIDUBANCOL 2016',
    'FIDUCIARIA 2016',
    'JULIO - DICIEMBRE 2017',
]

_DEFAULT_SUBEXPEDIENTE = 'CONCILIACION BANCARIA 2016'

# Patrones para extraer periodo (año, mes) del texto de página 1
_PERIODO_SLASH_RE = re.compile(r'\b(20\d{2})[/\-](\d{1,2})\b')
_MES_AÑO_RE = re.compile(
    r'\b(ENERO|FEBRERO|MARZO|ABRIL|MAYO|JUNIO|JULIO|AGOSTO|'
    r'SEPTIEMBRE|OCTUBRE|NOVIEMBRE|DICIEMBRE)\s+(?:DE\s+)?(20\d{2})\b',
)
_AÑO_SOLO_RE = re.compile(r'\b(20\d{2})\b')
# El formulario de conciliacion bancaria rotula el periodo con "MES <nombre>".
# Se prioriza sobre el escaneo ciego de meses (mas abajo) porque el pie de
# firma suele incluir la fecha en que se firmo el informe (ej. "Enero 04 de
# 2017" para el informe de DICIEMBRE), y esa fecha no es el periodo real.
_MES_LABEL_RE = re.compile(
    r'\bMES\s*[:\-_]*\s*(ENERO|FEBRERO|MARZO|ABRIL|MAYO|JUNIO|JULIO|AGOSTO|'
    r'SEPTIEMBRE|OCTUBRE|NOVIEMBRE|DICIEMBRE)\b'
)


def extract_bancolombia_period(text):
    """
    Extrae (año, mes_num) del texto de la página 1 de un PDF Bancolombia.
    Retorna (None, None) si no se puede determinar.
    """
    upper = str(text or '').upper()

    m = _PERIODO_SLASH_RE.search(upper)
    if m:
        year, month = int(m.group(1)), int(m.group(2))
        if 1 <= month <= 12:
            return year, month

    m = _MES_AÑO_RE.search(upper)
    if m:
        return int(m.group(2)), _MESES_ES[m.group(1)]

    # Buscar año solo + mes suelto
    year_m = _AÑO_SOLO_RE.search(upper)
    year = int(year_m.group(1)) if year_m else None

    m = _MES_LABEL_RE.search(upper)
    if m:
        return year, _MESES_ES[m.group(1)]

    for mes_name, mes_num in _MESES_ES.items():
        if re.search(rf'\b{mes_name}\b', upper):
            return year, mes_num

    return year, None


def classify_bancolombia_subexpediente(text, filename=''):
    """
    Determina a qué sub-expediente SAIA pertenece un documento Bancolombia.

    Usa el texto OCR del documento y el nombre del archivo para la clasificación.
    Retorna (subexpediente, año, mes_num).

    Prioridad de clasificación:
    1. FIDUBANCOL → FIDUBANCOL 2016
    2. FIDUCIARIA → FIDUCIARIA 2016
    3. PROSEGUIR + mes 1-9 → CONCILIACION PROSEGUIR ENE - SEP 2016
    4. PROSEGUIR + mes 10-12 → CONCILIACION PROSEGUIR OCT - DIC 2016
    5. CTA AHORROS → CONCILIACION BANCARIA BANCOLOMBIA CTA AHORROS 2016
    6. CTA CTE + mes nov/dic → CONCILIACION BANCARIA CTA CTE NOV - DIC
    7. año 2015 → ENERO - DICIEMBRE 2015
    8. año 2017 mes 1-6 → ENERO - JUNIO 2017
    9. año 2017 mes 7-12 → JULIO - DICIEMBRE 2017
    10. Default → CONCILIACION BANCARIA 2016
    """
    text_upper = str(text or '').upper()
    stem_upper = os.path.splitext(os.path.basename(filename))[0].upper() if filename else ''
    combined = f'{text_upper} {stem_upper}'

    year, month = extract_bancolombia_period(combined)

    if 'FIDUBANCOL' in combined:
        return 'FIDUBANCOL 2016', year, month

    if 'FIDUCIARIA' in combined:
        return 'FIDUCIARIA 2016', year, month

    if 'PROSEGUIR' in combined:
        if month and month >= 10:
            return 'CONCILIACION PROSEGUIR OCT - DIC 2016', year, month
        return 'CONCILIACION PROSEGUIR ENE - SEP 2016', year, month

    _ahorros_pats = ('CTA AHORROS', 'CUENTA AHORROS', 'CTA. AHORROS', 'CTA.AHORROS', 'CUENTAS DE AHORRO')
    if any(p in combined for p in _ahorros_pats):
        return 'CONCILIACION BANCARIA BANCOLOMBIA CTA AHORROS 2016', year, month

    _cte_pats = ('CTA CTE', 'CUENTA CORRIENTE', 'CTA. CTE', 'CTA.CTE')
    if any(p in combined for p in _cte_pats) and month and month in (11, 12):
        return 'CONCILIACION BANCARIA CTA CTE NOV - DIC', year, month

    if year == 2015:
        return 'ENERO - DICIEMBRE 2015', year, month

    if year == 2017:
        if month and month <= 6:
            return 'ENERO - JUNIO 2017', year, month
        return 'JULIO - DICIEMBRE 2017', year, month

    return _DEFAULT_SUBEXPEDIENTE, year, month


def _strip_accents(s):
    return unicodedata.normalize('NFD', s).encode('ascii', 'ignore').decode('ascii')


def classify_from_path(ruta_archivo):
    """
    Determines (subexpediente, year) from the immediate parent folder of the file.
    Disk folder names are confirmed to be identical to SAIA sub-expediente labels.
    Returns (None, None) if the parent folder doesn't match any known sub-expediente.
    """
    if not ruta_archivo:
        return None, None
    try:
        parent_name = os.path.basename(os.path.dirname(str(ruta_archivo))).strip()
    except Exception:
        return None, None
    if not parent_name:
        return None, None

    parent_normalized = _strip_accents(parent_name.upper())
    for subexp in BANCOLOMBIA_SUBEXPEDIENTES:
        if _strip_accents(subexp.upper()) == parent_normalized:
            year_m = _AÑO_SOLO_RE.search(subexp)
            year = int(year_m.group(1)) if year_m else None
            return subexp, year
    return None, None


def sort_key_bancolombia(documento):
    """Clave de ordenamiento para documentos Bancolombia: (año, mes_num, nombre_archivo)."""
    metadata = getattr(documento, 'metadata', None)
    datos_pel = (getattr(metadata, 'datos_pel', None) or {}) if metadata else {}
    year = datos_pel.get('bancolombia_año') or 9999
    month = datos_pel.get('bancolombia_mes_num') or 99
    return (year, month, getattr(documento, 'nombre_archivo', ''))


