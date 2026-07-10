import re
from pathlib import Path

from migracion_masiva_archivo.services.saia import selectors


BANCOLOMBIA_IDENTIFIERS = {
    # Meses individuales (con variantes de partes)
    'ENERO', 'ENERO - 1', 'ENERO - 2', 'ENERO - 3',
    'FEBRERO', 'FEBRERO - 1', 'FEBRERO - 2',
    'MARZO', 'MARZO - 1', 'MARZO - 2',
    'ABRIL', 'ABRIL - 1', 'ABRIL - 2',
    'MAYO', 'MAYO - 1', 'MAYO - 2',
    'JUNIO', 'JUNIO - 1', 'JUNIO - 2',
    'JULIO', 'JULIO - 1', 'JULIO - 2',
    'AGOSTO', 'AGOSTO - 1', 'AGOSTO - 2',
    'SEPTIEMBRE', 'SEPTIEMBRE - 1', 'SEPTIEMBRE - 2',
    'OCTUBRE', 'OCTUBRE - 1', 'OCTUBRE - 2',
    'NOVIEMBRE', 'NOVIEMBRE - 1', 'NOVIEMBRE - 2',
    'DICIEMBRE', 'DICIEMBRE - 1', 'DICIEMBRE - 2',
    # Entidades especiales
    'FIDUBANCOL', 'FIDUCIARIA', 'PROSEGUIR',
}


def get_saia_route_config(route_code):
    code = str(route_code or '').upper().strip()
    return selectors.SAIA_ROUTE_CONFIG.get(code)


def get_saia_route_steps(route_code, year=None, subexpediente=None):
    config = get_saia_route_config(route_code)
    if not config:
        return []
    steps = []
    for step in config.get('navigation_steps', []):
        only_years = step.get('only_years')
        if only_years and str(year) not in {str(item) for item in only_years}:
            continue
        if step.get('dynamic_year'):
            if year:
                prefix = step.get('year_prefix', '')
                label = f'{prefix}{year}'
                resolved = {'labels': [label], 'optional': step.get('optional', False)}
                if step.get('navigate_into'):
                    resolved['navigate_into'] = True
                steps.append(resolved)
            elif not step.get('optional', False):
                steps.append({'missing_dynamic_year': True, 'optional': False})
        elif step.get('dynamic_subexpediente'):
            if subexpediente:
                resolved = {'labels': [subexpediente], 'optional': step.get('optional', False)}
                if step.get('navigate_into'):
                    resolved['navigate_into'] = True
                steps.append(resolved)
            elif not step.get('optional', False):
                steps.append({'missing_dynamic_subexpediente': True, 'optional': False})
        elif step.get('dynamic_month'):
            if subexpediente:
                month_label = str(subexpediente).strip().upper()
                resolved = {
                    'labels': [month_label, month_label.title()],
                    'optional': step.get('optional', False),
                }
                if step.get('navigate_into'):
                    resolved['navigate_into'] = True
                steps.append(resolved)
            elif not step.get('optional', False):
                steps.append({'missing_dynamic_month': True, 'optional': False})
        else:
            steps.append(step)
    return steps


CONCILIACION_YEAR_FIELDS = {
    'CORBANCA': 'corbanca_a\u00f1o',
    'COLPATRIA': 'colpatria_a\u00f1o',
    'CORREVAL': 'correval_a\u00f1o',
    'CORFICOLOMBIANA': 'corficolombiana_a\u00f1o',
    'BBVA': 'bbva_a\u00f1o',
    'DAVIVIENDA': 'davivienda_a\u00f1o',
    'BOGOTA': 'bogota_a\u00f1o',
    'ECB': 'ecb_a\u00f1o',
    'EGC': 'egc_a\u00f1o',
}


def resolve_saia_route_context(documento, route_code):
    """Return (year, subexpediente) required by dynamic SAIA routes."""
    code = str(route_code or '').upper().strip()
    year = extract_document_year(documento)
    metadata = getattr(documento, 'metadata', None)
    datos_pel = (getattr(metadata, 'datos_pel', None) or {}) if metadata else {}

    if code in CONCILIACION_YEAR_FIELDS:
        year = datos_pel.get(CONCILIACION_YEAR_FIELDS[code]) or year
        if not year:
            year = _first_valid_metadata_year(datos_pel)

    subexpediente = None
    if code == 'BANCOLOMBIA':
        subexpediente = datos_pel.get('bancolombia_subexpediente') or None
    elif code == 'BBVA':
        subexpediente = datos_pel.get('bbva_subexpediente') or None
    elif code == 'DAVIVIENDA':
        subexpediente = datos_pel.get('davivienda_subexpediente') or None
    elif code == 'BOGOTA':
        subexpediente = datos_pel.get('bogota_subexpediente') or None
    elif code == 'RICA':
        year = datos_pel.get('retencion_ica_a\u00f1o') or year

    return year, subexpediente


def _first_valid_metadata_year(datos_pel):
    for key, value in (datos_pel or {}).items():
        if not str(key).endswith('_a\u00f1o'):
            continue
        try:
            year = int(value)
        except (TypeError, ValueError):
            continue
        if 2000 <= year <= 2099:
            return year
    return None


_MONTH_NAMES = {
    1: 'ENERO',
    2: 'FEBRERO',
    3: 'MARZO',
    4: 'ABRIL',
    5: 'MAYO',
    6: 'JUNIO',
    7: 'JULIO',
    8: 'AGOSTO',
    9: 'SEPTIEMBRE',
    10: 'OCTUBRE',
    11: 'NOVIEMBRE',
    12: 'DICIEMBRE',
}


def _month_name_from_metadata(datos_pel, month_name_key, month_num_key):
    month_name = str((datos_pel or {}).get(month_name_key) or '').strip().upper()
    if month_name:
        return month_name
    try:
        month_num = int((datos_pel or {}).get(month_num_key) or 0)
    except (TypeError, ValueError):
        return None
    return _MONTH_NAMES.get(month_num)


def extract_document_year(documento):
    """Extract a 4-digit document year for dynamic SAIA folder navigation."""
    fecha = getattr(documento, 'fecha_documento', None)
    if fecha and hasattr(fecha, 'year'):
        return fecha.year

    try:
        parts = Path(getattr(documento, 'ruta_archivo', '') or '').parts
        for part in reversed(parts):
            if part.isdigit() and len(part) == 4 and 2000 <= int(part) <= 2099:
                return int(part)
    except Exception:
        pass
    return None


def detect_saia_route(documento, metadata=None):
    return detect_document_identifier(documento, metadata)


def detect_document_identifier(documento, metadata=None):
    metadata = metadata if metadata is not None else getattr(documento, 'metadata', None)
    values = [
        getattr(documento, 'nombre_archivo', ''),
        getattr(documento, 'ruta_archivo', ''),
        getattr(metadata, 'consecutivo', '') if metadata else '',
        getattr(metadata, 'tipo_documento', '') if metadata else '',
        getattr(metadata, 'observaciones', '') if metadata else '',
    ]
    datos_pel = getattr(metadata, 'datos_pel', None) or {}
    if isinstance(datos_pel, dict):
        values.extend(str(value) for value in datos_pel.values() if value not in (None, ''))

    # CCA/CCV MUST run before bancolombia: month names (ENERO, FEBRERO…) exist
    # in BANCOLOMBIA_IDENTIFIERS, so a "ENERO.pdf" in a Cartera Colectiva folder
    # would be mis-routed as BANCOLOMBIA without this early check.
    ruta_upper = str(getattr(documento, 'ruta_archivo', '') or '').upper()
    tipo_meta  = str(getattr(metadata, 'tipo_documento', '') or '').upper()
    consecutivo_meta = str(getattr(metadata, 'consecutivo', '') or '').upper()
    is_cartera = (
        'CARTERA COLECTIVA' in ruta_upper
        or 'CARTERA_COLECTIVA' in ruta_upper
        or 'CARTERA COLECTIVA' in consecutivo_meta
        or 'DOCUMENTO_CCA' in tipo_meta
        or 'DOCUMENTO_CCV' in tipo_meta
    )
    if is_cartera:
        combined = ' '.join([ruta_upper, tipo_meta, consecutivo_meta])
        if 'ABIERTA' in combined or tipo_meta in ('DOCUMENTO_CCA',):
            return 'CCA'
        if 'VALOR' in combined or tipo_meta in ('DOCUMENTO_CCV',):
            return 'CCV'
        return 'CCA'

    is_retencion_ica = (
        'RETENCION DE ICA' in ruta_upper
        or 'RETENCIÓN DE ICA' in ruta_upper
        or 'RETENCION ICA' in ruta_upper
        or 'RETENCIÓN ICA' in ruta_upper
        or 'DECLARACION DE RETENCION DE ICA' in ruta_upper
        or 'DECLARACIÓN DE RETENCIÓN DE ICA' in ruta_upper
        or tipo_meta == 'DOCUMENTO_RETENCION_ICA'
    )
    if is_retencion_ica:
        return 'RICA'

    is_ecb = (
        'EGRESOS CHEQUES BANCOLOMBIA' in ruta_upper
        or 'EGRESOS Y CHEQUES BANCOLOMBIA' in ruta_upper
        or tipo_meta == 'DOCUMENTO_ECB'
    )
    if is_ecb:
        return 'ECB'

    is_egc = (
        'EGRESOS CHEQUES - EGC' in ruta_upper
        or 'EGRESOS CHEQUES-EGC' in ruta_upper
        or 'EGRESOS Y CHEQUES' in ruta_upper
        or tipo_meta == 'DOCUMENTO_EGC'
    )
    if is_egc:
        return 'EGC'

    is_ege = (
        'EGRESOS EFECTIVO' in ruta_upper
        or tipo_meta == 'DOCUMENTO_EGE'
    )
    if is_ege:
        return 'EGE'

    # Corbanca/Corpbanca: detectar por ruta antes que BANCOLOMBIA (comparten nombres de mes)
    if 'CORBANCA' in ruta_upper or 'CORPBANCA' in ruta_upper or tipo_meta == 'DOCUMENTO_CORBANCA':
        return 'CORBANCA'

    # Colpatria: detectar por ruta antes que BANCOLOMBIA (comparten nombres de mes)
    if 'COLPATRIA' in ruta_upper or tipo_meta == 'DOCUMENTO_COLPATRIA':
        return 'COLPATRIA'

    # Correval: detectar antes de BANCOLOMBIA (comparten nombres de mes)
    if 'CORREVAL' in ruta_upper or tipo_meta == 'DOCUMENTO_CORREVAL':
        return 'CORREVAL'

    # Corficolombiana: detectar antes de BANCOLOMBIA ('FIDUCIARIA' está en BANCOLOMBIA_IDENTIFIERS)
    if 'CORFICOLOMBIANA' in ruta_upper or tipo_meta == 'DOCUMENTO_CORFICOLOMBIANA':
        return 'CORFICOLOMBIANA'

    # BBVA: después de COLPATRIA para no capturar rutas COLPATRIA que pasan por carpeta BBVA
    if 'BBVA' in ruta_upper or tipo_meta == 'DOCUMENTO_BBVA':
        return 'BBVA'

    # Davivienda: detectar antes de BANCOLOMBIA (comparten nombres de mes)
    if 'DAVIVIENDA' in ruta_upper or tipo_meta == 'DOCUMENTO_DAVIVIENDA':
        return 'DAVIVIENDA'

    # Banco de Bogota: detectar antes de BANCOLOMBIA (comparten nombres de mes)
    if 'BOGOTA' in ruta_upper or tipo_meta == 'DOCUMENTO_BOGOTA':
        return 'BOGOTA'

    # Detección por tipo_documento persistido en metadata (respaldo confiable post-extracción)
    if tipo_meta == 'DOCUMENTO_BANCOLOMBIA':
        return 'BANCOLOMBIA'

    if _contains_bancolombia_identifier(values):
        return 'BANCOLOMBIA'

    text = ' '.join(str(value or '') for value in values).upper()
    if _contains_identifier(text, 'ECG'):
        return 'EGC'
    for identifier in ('RICA', 'RCP', 'RCI', 'RCG', 'RCC', 'INC', 'IND', 'NIC', 'PP1', 'PP2', 'PP3', 'ECB', 'EGC', 'EGE', 'PEC', 'IC1', 'IC2', 'IC3', 'IC4', 'IC5', 'IC6', 'PRO', 'PEL'):
        if _contains_identifier(text, identifier):
            return identifier
    return ''


def _contains_identifier(text, identifier):
    identifier = str(identifier or '').upper()
    patterns = [
        rf'\b(?:MAY[-\s]?)?{identifier}[-\s]?0*\d{{3,8}}\b',
        rf'\b{identifier}\b',
        rf'\b{identifier}[-_]',
    ]
    return any(re.search(pattern, text) for pattern in patterns)


# Acepta cualquier mes español solo o seguido de " - N" (ej. "MAYO - 3", "OCTUBRE - 12")
_BANCOLOMBIA_MES_RE = re.compile(
    r'^(ENERO|FEBRERO|MARZO|ABRIL|MAYO|JUNIO|JULIO|AGOSTO|'
    r'SEPTIEMBRE|OCTUBRE|NOVIEMBRE|DICIEMBRE)(\s+-\s+\d+)?$'
)


def _contains_bancolombia_identifier(values):
    for value in values:
        normalized = _normalize_bancolombia_identifier(value)
        if normalized in BANCOLOMBIA_IDENTIFIERS or _BANCOLOMBIA_MES_RE.match(normalized):
            return True
    return False


def _normalize_bancolombia_identifier(value):
    text = str(value or '').strip()
    if not text:
        return ''
    try:
        text = Path(text).stem if Path(text).suffix else text
    except (OSError, ValueError):
        pass
    text = re.sub(r'\bOK\b', ' ', text, flags=re.IGNORECASE)
    text = text.replace('_', ' ').upper()
    text = re.sub(r'\s*-\s*', ' - ', text)
    return re.sub(r'\s+', ' ', text).strip()


