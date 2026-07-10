import re
import stat
from pathlib import Path


SYSTEM_FILE_NAMES = {
    'desktop.ini',
    'thumbs.db',
    '.ds_store',
}


OK_FILENAME_RE = re.compile(r'(^|[\s_\-])OK([\s_\-\.]|$)', re.IGNORECASE)
BANCOLOMBIA_IDENTIFIERS = {
    # Meses individuales
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
AMBIGUOUS_WORD_RE = re.compile(
    r'\b(copia|copy|final|corregido|corregida|version|versi[oó]n|v\d+|duplicado|'
    r'nuevo|nueva|scan|escaneo|prueba|temporal)\b',
    re.IGNORECASE,
)
PROBLEMATIC_SAIA_CHARS_RE = re.compile(r'[#%&?\'"|\r\n\t<>]')
SUSPICIOUS_FINAL_EXTENSIONS = {
    '.tmp', '.download', '.partial', '.crdownload', '.bak', '.old', '.exe'
}


def should_omit_system_file(path):
    file_path = Path(path)
    name = file_path.name
    lower_name = name.lower()

    for part in file_path.parts:
        lower_part = part.lower()
        if lower_part in SYSTEM_FILE_NAMES:
            return True
        if part.startswith('~$'):
            return True
        if part.startswith('.') and part not in {'.', '..'}:
            return True

    try:
        attributes = file_path.stat().st_file_attributes
    except (AttributeError, OSError):
        attributes = 0

    hidden_attribute = getattr(stat, 'FILE_ATTRIBUTE_HIDDEN', 0)
    system_attribute = getattr(stat, 'FILE_ATTRIBUTE_SYSTEM', 0)
    if attributes & (hidden_attribute | system_attribute):
        return True

    return False


def has_ok_marker(filename):
    return bool(OK_FILENAME_RE.search(str(filename or '')))


def validate_filename_for_phase1(filename):
    name = Path(str(filename or '')).name
    stem = _normalized_stem(name)
    issues = []

    if has_suspicious_double_extension(name):
        issues.append({
            'codigo': 'EXTENSION_DOBLE_O_SOSPECHOSA',
            'mensaje': 'Extension doble o sospechosa para el proceso documental',
            'bloquea_fase_2': True,
            'bloquea_saia': True,
        })

    bad_chars = sorted(set(PROBLEMATIC_SAIA_CHARS_RE.findall(name)))
    if bad_chars:
        issues.append({
            'codigo': 'CARACTERES_NO_COMPATIBLES_SAIA',
            'mensaje': f'Nombre con caracteres problematicos para SAIA: {" ".join(bad_chars)}',
            'bloquea_fase_2': False,
            'bloquea_saia': True,
        })

    if is_ambiguous_pel_filename(name):
        issues.append({
            'codigo': 'NOMBRE_PEL_AMBIGUO',
            'mensaje': 'Nombre PEL ambiguo o con sufijos no reconocidos',
            'bloquea_fase_2': True,
            'bloquea_saia': True,
        })

    return {
        'nombre_pel_ambiguo': any(i['codigo'] == 'NOMBRE_PEL_AMBIGUO' for i in issues),
        'caracteres_no_compatibles_saia': bool(bad_chars),
        'caracteres_problematicos_saia': ' '.join(bad_chars),
        'extension_doble_o_sospechosa': any(i['codigo'] == 'EXTENSION_DOBLE_O_SOSPECHOSA' for i in issues),
        'validaciones_nombre': issues,
        'error_validacion_nombre': '; '.join(issue['mensaje'] for issue in issues),
        'stem_normalizado': stem,
    }


def is_ambiguous_pel_filename(filename):
    stem = _normalized_stem(filename)
    if not stem:
        return False

    pel_numbers = re.findall(r'(?:MAY\s*[- ]?)?PEL\s*[- ]?0*(\d{4,8})\b', stem, re.IGNORECASE)
    compact_numbers = re.findall(r'MAYPEL0*(\d{4,8})\b', stem, re.IGNORECASE)
    if len(set(pel_numbers + compact_numbers)) > 1:
        return True

    if AMBIGUOUS_WORD_RE.search(stem):
        return True

    if _is_known_valid_pel_name(stem):
        return False

    return bool(pel_numbers or compact_numbers)


def has_suspicious_double_extension(filename):
    name = str(filename or '').lower()
    suffix = Path(name).suffix.lower()
    if suffix in SUSPICIOUS_FINAL_EXTENSIONS:
        return True
    return '.pdf.' in name and suffix != '.pdf'


def extract_pel_numbers_from_text(text):
    normalized = str(text or '').upper()
    numbers = set()
    patterns = [
        r'MAY\s*[- ]?PEL\s*[- ]?0*(\d{4,8})\b',
        r'\bPEL\s*[- ]?0*(\d{4,8})\b',
        r'\bMAYPEL0*(\d{4,8})\b',
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, normalized, flags=re.IGNORECASE):
            numbers.add(int(match.group(1)))
    return sorted(numbers)


_MESES_CC = {
    'ENERO', 'FEBRERO', 'MARZO', 'ABRIL', 'MAYO', 'JUNIO',
    'JULIO', 'AGOSTO', 'SEPTIEMBRE', 'OCTUBRE', 'NOVIEMBRE', 'DICIEMBRE',
}


def extraer_metadata_nombre_archivo(nombre_archivo):
    stem = _normalized_stem(nombre_archivo)
    contiene_ok = has_ok_marker(nombre_archivo)
    metadata = _empty_name_metadata(contiene_ok)

    bancolombia_metadata = _extract_bancolombia_name_metadata(stem)
    if bancolombia_metadata:
        metadata.update(bancolombia_metadata)
        return metadata

    if stem.upper() in _MESES_CC:
        month = stem.upper()
        metadata.update({
            'tipo_documento_nombre': 'CARTERA_COLECTIVA',
            'tipo_nombre': 'CARTERA_COLECTIVA_MES',
            'mes_nombre': month,
            'asunto_documental': month,
            'identidad_documental': f'CARTERA_COLECTIVA-{month}',
            'nombre_reconocido': True,
        })
        return metadata

    for code in ('RCP', 'RCI', 'RCG', 'RCC', 'INC', 'IND', 'NIC', 'PP1', 'PP2', 'PP3', 'ECB', 'EGC', 'ECG', 'EGE', 'PEC', 'IC1', 'IC2', 'IC3', 'IC4', 'IC5', 'IC6', 'PRO', 'PEL'):
        structured_metadata = _extract_structured_name_metadata(stem, code)
        if structured_metadata:
            if code == 'ECG':
                structured_metadata['identificador_documental_original'] = 'ECG'
            metadata.update(structured_metadata)
            return metadata

    return metadata


_BANCOLOMBIA_ENTIDADES = {'FIDUBANCOL', 'FIDUCIARIA', 'PROSEGUIR'}

# Acepta cualquier mes español solo o seguido de " - N" (ej. "MAYO - 3", "OCTUBRE - 12")
_BANCOLOMBIA_MES_RE = re.compile(
    r'^(ENERO|FEBRERO|MARZO|ABRIL|MAYO|JUNIO|JULIO|AGOSTO|'
    r'SEPTIEMBRE|OCTUBRE|NOVIEMBRE|DICIEMBRE)(\s+-\s+\d+)?$'
)


def _extract_bancolombia_name_metadata(stem):
    identifier = _normalize_bancolombia_identifier(stem)
    if identifier not in BANCOLOMBIA_IDENTIFIERS and not _BANCOLOMBIA_MES_RE.match(identifier):
        return {}

    # Entidades especiales (no tienen estructura mes-parte)
    if identifier in _BANCOLOMBIA_ENTIDADES:
        return {
            'tipo_documento_nombre': 'BANCOLOMBIA',
            'tipo_nombre': 'BANCOLOMBIA_ENTIDAD',
            'documento_base_nombre': identifier,
            'bancolombia_base_nombre': identifier,
            'mes_nombre': '',
            'subparte_nombre': None,
            'grupo_documental_nombre': f'BANCOLOMBIA {identifier}',
            'identidad_documental': f'BANCOLOMBIA-{identifier}',
            'asunto_documental': stem,
            'nombre_reconocido': True,
        }

    month, part = _split_bancolombia_identifier(identifier)
    identity = f'BANCOLOMBIA-{month}' + (f'-{part}' if part else '')
    return {
        'tipo_documento_nombre': 'BANCOLOMBIA',
        'tipo_nombre': 'BANCOLOMBIA_MES_PARTE' if part else 'BANCOLOMBIA_MES',
        'documento_base_nombre': identifier,
        'bancolombia_base_nombre': identifier,
        'mes_nombre': month,
        'subparte_nombre': int(part) if part else None,
        'grupo_documental_nombre': f'BANCOLOMBIA {month}',
        'identidad_documental': identity,
        'asunto_documental': stem,
        'nombre_reconocido': True,
    }


def _normalize_bancolombia_identifier(value):
    text = str(value or '').strip().upper()
    text = re.sub(r'\bOK\b', ' ', text, flags=re.IGNORECASE)
    text = text.replace('_', ' ')
    text = re.sub(r'\s*-\s*', ' - ', text)
    return re.sub(r'\s+', ' ', text).strip()


def _split_bancolombia_identifier(identifier):
    match = re.match(r'^([A-Z]+)(?:\s*-\s*(\d+))?$', str(identifier or '').strip())
    if not match:
        return str(identifier or '').strip(), ''
    return match.group(1), match.group(2) or ''


def _extract_structured_name_metadata(stem, identifier):
    code = str(identifier or '').upper()
    output_code = 'EGC' if code == 'ECG' else code

    tomo_match = re.search(
        rf'(?:MAY\s*[- ]?)?{code}\s*[- ]?0*(\d{{4,8}})\s*[- ]*TOMO\s*0*(\d{{1,2}})\s*[- ]\s*0*(\d{{1,2}})',
        stem,
        re.IGNORECASE,
    )
    if tomo_match:
        base, tomo, parte = (int(value) for value in tomo_match.groups())
        return _build_name_metadata(output_code, base, f'{output_code}_TOMO', tomo=tomo, parte=parte)

    suffix_match = re.search(
        rf'(?:MAY\s*[- ]?)?{code}\s*[- ]?0*(\d{{4,8}})\s*[- ]\s*0*(\d{{1,2}})\b',
        stem,
        re.IGNORECASE,
    )
    if suffix_match:
        base, subparte = (int(value) for value in suffix_match.groups())
        return _build_name_metadata(output_code, base, f'{output_code}_SUBPARTE', subparte=subparte)

    simple_match = re.search(
        rf'(?:MAY\s*[- ]?)?{code}\s*[- ]?0*(\d{{4,8}})\b',
        stem,
        re.IGNORECASE,
    )
    if simple_match:
        base = int(simple_match.group(1))
        return _build_name_metadata(output_code, base, f'{output_code}_SIMPLE', subparte=1)

    compact_match = re.search(rf'MAY{code}0*(\d{{4,8}})\b', stem, re.IGNORECASE)
    if compact_match:
        base = int(compact_match.group(1))
        return _build_name_metadata(output_code, base, f'{output_code}_SIMPLE', subparte=1)

    return {}


def _build_name_metadata(code, base, tipo_nombre, tomo=None, parte=None, subparte=None):
    metadata = {
        'tipo_documento_nombre': code,
        'tipo_nombre': tipo_nombre,
        'pel_base_nombre': base,
        'documento_base_nombre': base,
        f'{code.lower()}_base_nombre': base,
        'tomo_nombre': tomo,
        'parte_nombre': parte,
        'parte_tomo_nombre': parte,
        'subparte_nombre': subparte,
        'grupo_documental_nombre': f'{code} {base}',
        'nombre_reconocido': True,
    }
    if tomo is not None and parte is not None:
        metadata['identidad_documental'] = f'{code}-{base}-TOMO-{tomo}-PARTE-{parte}'
    elif str(tipo_nombre).endswith('_SUBPARTE') and subparte is not None:
        metadata['identidad_documental'] = f'{code}-{base}-SUBPARTE-{subparte}'
    else:
        metadata['identidad_documental'] = f'{code}-{base}'
    return metadata


def _is_known_valid_pel_name(stem):
    valid_patterns = [
        r'^(?:MAY\s*[- ]?)?PEL\s*[- ]?0*\d{4,8}$',
        r'^(?:MAY\s*[- ]?)?PEL\s*[- ]?0*\d{4,8}\s*[- ]\s*0*\d{1,2}$',
        r'^(?:MAY\s*[- ]?)?PEL\s*[- ]?0*\d{4,8}\s*[- ]*TOMO\s*0*\d{1,2}\s*[- ]\s*0*\d{1,2}$',
        r'^MAYPEL0*\d{4,8}$',
    ]
    return any(re.match(pattern, stem, flags=re.IGNORECASE) for pattern in valid_patterns)


def extract_expected_consecutivo_from_filename(filename):
    stem = _normalized_stem(filename)

    for code in ('RCP', 'RCI', 'RCG', 'RCC', 'INC', 'IND', 'NIC', 'PP1', 'PP2', 'PP3', 'ECB', 'EGC', 'ECG', 'EGE', 'PEC', 'IC1', 'IC2', 'IC3', 'IC4', 'IC5', 'IC6', 'PRO', 'PEL'):
        output_code = 'EGC' if code == 'ECG' else code
        tomo_match = re.search(
            rf'(?:MAY\s*[- ]?)?{code}\s*[- ]?0*(\d{{4,8}})\s*[- ]*TOMO\s*0*(\d{{1,2}})\s*[- ]\s*0*(\d{{1,2}})',
            stem,
            re.IGNORECASE,
        )
        if tomo_match:
            number, tomo, suffix = tomo_match.groups()
            return f'{output_code} {int(number)} TOMO {int(tomo)}-{int(suffix)}'

        suffix_match = re.search(
            rf'(?:MAY\s*[- ]?)?{code}\s*[- ]?0*(\d{{4,8}})\s*[- ]\s*0*(\d{{1,2}})\b',
            stem,
            re.IGNORECASE,
        )
        if suffix_match:
            number, suffix = suffix_match.groups()
            return f'{output_code} {int(number)} -{int(suffix)}'

        simple_match = re.search(rf'(?:MAY\s*[- ]?)?{code}\s*[- ]?0*(\d{{4,8}})\b', stem, re.IGNORECASE)
        if simple_match:
            return f'{output_code} {int(simple_match.group(1))}'

        compact_match = re.search(rf'MAY{code}0*(\d{{4,8}})\b', stem, re.IGNORECASE)
        if compact_match:
            return f'{output_code} {int(compact_match.group(1))}'

    return ''


def get_document_identity_from_filename(filename):
    return extraer_metadata_nombre_archivo(filename).get('identidad_documental') or ''


def get_documental_natural_sort_key(filename):
    metadata = extraer_metadata_nombre_archivo(filename)
    code_order = {
        'PEL': 0,
        'PRO': 1,
        'RCG': 2,
        'RCI': 3,
        'RCP': 4,
        'BANCOLOMBIA': 5,
    }.get(metadata.get('tipo_documento_nombre'), 9)
    pel_base = _int_or_large(metadata.get('pel_base_nombre'))
    tomo = _int_or_zero(metadata.get('tomo_nombre'))
    parte_tomo = _int_or_zero(metadata.get('parte_tomo_nombre') or metadata.get('parte_nombre'))
    subparte = _int_or_zero(metadata.get('subparte_nombre'))
    return (
        code_order,
        pel_base,
        tomo,
        parte_tomo,
        subparte,
        _normalized_stem(filename),
    )


def _normalized_stem(filename):
    stem = Path(str(filename or '')).stem.upper()
    stem = re.sub(r'\bOK\b', ' ', stem, flags=re.IGNORECASE)
    stem = stem.replace('_', ' ')
    return re.sub(r'\s+', ' ', stem).strip()


def _empty_name_metadata(contiene_ok):
    return {
        'tipo_documento_nombre': '',
        'tipo_nombre': '',
        'pel_base_nombre': '',
        'pro_base_nombre': '',
        'bancolombia_base_nombre': '',
        'documento_base_nombre': '',
        'mes_nombre': '',
        'asunto_documental': '',
        'tomo_nombre': '',
        'parte_nombre': '',
        'parte_tomo_nombre': '',
        'subparte_nombre': '',
        'grupo_documental_nombre': '',
        'identidad_documental': '',
        'contiene_ok': contiene_ok,
        'nombre_reconocido': False,
    }


def _int_or_zero(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _int_or_large(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 999999999


def humanize_file_error(error):
    if not error:
        return ''

    text = str(error)
    normalized = text.lower()

    if 'archivo vacio' in normalized:
        return 'Archivo vacio'
    if 'sospechosamente pequeno' in normalized:
        return 'Archivo sospechosamente pequeno'
    if 'no coincide con contenido real' in normalized or 'no coincide con firma binaria' in normalized:
        return 'La extension del archivo no coincide con su contenido real'
    if 'no se pudo calcular hash' in normalized:
        return 'No se pudo calcular hash del archivo'
    if 'no se pudo leer tamano' in normalized:
        return 'No se pudo leer tamano del archivo'
    if 'sincroniz' in normalized or 'onedrive' in normalized or 'cloud' in normalized:
        return 'Archivo posiblemente bloqueado o en sincronizacion'
    if 'ya cargado exitosamente a saia' in normalized:
        return 'Documento ya cargado exitosamente a SAIA'

    if 'eof marker not found' in normalized or 'stream has ended unexpectedly' in normalized:
        return 'PDF posiblemente dañado o incompleto'
    if 'cannot open broken document' in normalized or 'broken document' in normalized:
        return 'PDF no se pudo abrir; posible archivo corrupto'
    if 'permission denied' in normalized or 'access is denied' in normalized or 'acceso denegado' in normalized:
        return 'No se tiene permiso para leer el archivo'
    if 'file not found' in normalized or 'no such file' in normalized or 'archivo no encontrado' in normalized:
        return 'Archivo no encontrado durante la exploracion'
    if 'formato no soportado' in normalized:
        return 'Formato no soportado para exploracion documental'
    if 'duplicado por identidad documental' in normalized:
        return 'Archivo duplicado por identidad documental'
    if 'duplicado por hash' in normalized:
        return 'Archivo duplicado por contenido/hash'
    if 'pdf supera limite saia' in normalized:
        return 'PDF supera el limite de tamano permitido para SAIA'
    if 'nombre pel ambiguo' in normalized:
        return 'Nombre PEL ambiguo'
    if 'simple y subparte 1' in normalized:
        return 'Conflicto entre PEL simple y subparte 1'
    if 'caracteres problematicos para saia' in normalized:
        return 'Nombre con caracteres no compatibles con SAIA'
    if 'duplicado por ruta normalizada' in normalized:
        return 'Archivo duplicado por ruta normalizada'
    if 'extension doble o sospechosa' in normalized:
        return 'Extension doble o sospechosa'
    if 'consecutivo del nombre no coincide con contenido' in normalized:
        return 'Consecutivo del nombre no coincide con el contenido'

    return 'Error tecnico durante la exploracion; revisar detalle original'


