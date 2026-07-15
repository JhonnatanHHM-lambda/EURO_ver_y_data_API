import os
import re
from datetime import date

from .file_name_service import extraer_metadata_nombre_archivo
from .normalizacion_service import normalize_consecutivo, normalize_date, normalize_money, normalize_nit, normalize_text

_CC_ABIERTA_RE = re.compile(r'CARTERA\s+COLECTIVA\s+ABIERTA', re.IGNORECASE)
_CC_VALOR_RE   = re.compile(r'CARTERA\s+COLECTIVA\s+(?:DE\s+)?VALOR', re.IGNORECASE)
_CC_MES_RE     = re.compile(
    r'\b(ENERO|FEBRERO|MARZO|ABRIL|MAYO|JUNIO|JULIO|AGOSTO|'
    r'SEPTIEMBRE|OCTUBRE|NOVIEMBRE|DICIEMBRE)\b', re.IGNORECASE,
)
_CC_AÑO_RE = re.compile(r'\b(20\d{2})\b')
_CC_MESES_NUM = {
    'ENERO': 1, 'FEBRERO': 2, 'MARZO': 3, 'ABRIL': 4,
    'MAYO': 5, 'JUNIO': 6, 'JULIO': 7, 'AGOSTO': 8,
    'SEPTIEMBRE': 9, 'OCTUBRE': 10, 'NOVIEMBRE': 11, 'DICIEMBRE': 12,
}
_MESES_POR_NUM = {value: key for key, value in _CC_MESES_NUM.items()}
_RETENCION_ICA_TITLE = 'DECLARACION DE RETENCION DE ICA'
_RETENCION_ICA_BIMESTRAL_TITLE = 'DECLARACION BIMESTRAL'


# Acepta separadores extendidos (:, #) y caracteres que OCR confunde con dígitos
# (O→0, l/I→1, S→5, B→8, G→6) dentro del número capturado.
MAIN_HEADER_RE = re.compile(r'PAGOS?\s+ELECTRONICOS?(?:\s*-\s*PEL)?', re.IGNORECASE)
PROVIDER_RE = re.compile(r'INVERSIONES\s+(?:EURO|MURO|EIJRO|EUR0)\s+[S8]\.?\s*A\.?', re.IGNORECASE)

# Pre-compilados para normalización OCR antes de aplicar CONSECUTIVO_RE
_DIGIT_SPACE_RE = re.compile(r'(\d)\s+(\d)')
_PEL_SPACED_RE  = re.compile(r'\bP\s+E\s+L\b', re.IGNORECASE)
_PRO_SPACED_RE  = re.compile(r'\bP\s+R\s+O\b', re.IGNORECASE)
_RCG_SPACED_RE  = re.compile(r'\bR\s+C\s+G\b', re.IGNORECASE)
_RCI_SPACED_RE  = re.compile(r'\bR\s+C\s+I\b', re.IGNORECASE)
_RCP_SPACED_RE  = re.compile(r'\bR\s+C\s+P\b', re.IGNORECASE)
_ECB_SPACED_RE  = re.compile(r'\bE\s+C\s+B\b', re.IGNORECASE)
_EGC_SPACED_RE  = re.compile(r'\bE\s+G\s+C\b', re.IGNORECASE)
_ECG_SPACED_RE  = re.compile(r'\bE\s+C\s+G\b', re.IGNORECASE)
_EGE_SPACED_RE  = re.compile(r'\bE\s+G\s+E\b', re.IGNORECASE)

# Encabezado propio de "Egresos Efectivo - EGE". No confundir con MAIN_HEADER_RE
# (Pagos Electronicos - PEL): son rutas SAIA distintas con formularios distintos.
_EGE_TITLE_RE   = re.compile(r'\bEGRESOS?\s+EFECTIVO\b', re.IGNORECASE)
# Tabla de sustitución: confusiones dígito-letra más frecuentes en Tesseract
_OCR_DIGIT_TABLE = str.maketrans('OolISBG', '0011586')
FILENAME_IDENTITY_DOCUMENTS = {
    'PRO', 'RCG', 'RCI', 'RCP', 'RCC', 'INC', 'IND', 'NIC', 'PP1', 'PP2', 'PP3',
    'ECB', 'EGC', 'EGE', 'PEC', 'IC1', 'IC2', 'IC3', 'IC4', 'IC5', 'IC6',
    'BANCOLOMBIA', 'CCA', 'CCV', 'CARTERA_COLECTIVA',
}


def _clasificar_cartera_colectiva(text, filename, ruta_archivo=''):
    upper = text.upper()
    if _CC_ABIERTA_RE.search(upper):
        subtipo, route_code = 'ABIERTA', 'CCA'
    elif _CC_VALOR_RE.search(upper):
        subtipo, route_code = 'VALOR', 'CCV'
    else:
        ruta_upper = str(ruta_archivo or '').upper()
        if 'ABIERTA' in ruta_upper:
            subtipo, route_code = 'ABIERTA', 'CCA'
        elif 'VALOR' in ruta_upper:
            subtipo, route_code = 'VALOR', 'CCV'
        else:
            return None

    match_mes = _CC_MES_RE.search(upper)
    mes = match_mes.group(1).upper() if match_mes else None
    if not mes:
        stem = os.path.splitext(os.path.basename(filename))[0].upper()
        mes = stem if stem in _CC_MESES_NUM else None

    match_año = _CC_AÑO_RE.search(upper)
    año = int(match_año.group(1)) if match_año else None

    if not año and ruta_archivo:
        import re as _re_año
        m_ruta = _re_año.search(r'\b(20\d{2})\b', str(ruta_archivo))
        if m_ruta:
            año = int(m_ruta.group(1))

    if not mes or not año:
        return None

    asunto = f'CARTERA COLECTIVA {subtipo} {mes} {año}'
    return {
        'route_code': route_code,
        'subtipo': subtipo,
        'mes': mes,
        'año': año,
        'asunto_saia': asunto,
        'fecha_documento': date(año, _CC_MESES_NUM[mes], 1),
        'identidad_documental': f'{route_code}-{mes}-{año}',
    }


def _extract_cartera_colectiva_metadata(text, filename, filename_metadata, ruta_archivo=''):
    resultado = _clasificar_cartera_colectiva(text, filename, ruta_archivo)
    if not resultado:
        return {
            'nit': '', 'proveedor': '', 'consecutivo': '',
            'fecha_documento': None,
            'tipo_documento': 'DOCUMENTO_CARTERA_COLECTIVA',
            'valor': None, 'medio_pago': '',
            'confianza': 0, 'normalizado': False,
            'requiere_revision': True,
            'mismatch_consecutivo': False, 'mismatch_bloquea': False,
            'ocr_consecutivo_original': '',
            'datos_pel': {'error': 'No se pudo determinar subtipo (ABIERTA/VALOR), mes o año'},
            'observaciones_extraccion': 'Cartera Colectiva: clasificacion incompleta - revision manual requerida',
        }
    return {
        'nit': '',
        'proveedor': 'INVERSIONES EURO S.A',
        'consecutivo': resultado['asunto_saia'],
        'fecha_documento': resultado['fecha_documento'],
        'tipo_documento': f'DOCUMENTO_{resultado["route_code"]}',
        'valor': None,
        'medio_pago': '',
        'confianza': 95,
        'normalizado': True,
        'requiere_revision': False,
        'mismatch_consecutivo': False,
        'mismatch_bloquea': False,
        'ocr_consecutivo_original': '',
        'datos_pel': {
            'mes': resultado['mes'],
            'año': resultado['año'],
            'subtipo': resultado['subtipo'],
            'asunto_saia': resultado['asunto_saia'],
            'identidad_documental': resultado['identidad_documental'],
            'cc_subtipo': resultado['subtipo'],
            'cc_año': resultado['año'],
            'cc_mes_num': _CC_MESES_NUM.get(resultado['mes']),
        },
        'observaciones_extraccion': (
            f'Cartera Colectiva {resultado["subtipo"]} - {resultado["mes"]} {resultado["año"]}'
        ),
    }


def _is_retencion_ica_path(ruta_archivo):
    ruta_upper = normalize_text(ruta_archivo)
    return (
        'RETENCION DE ICA' in ruta_upper
        or 'RETENCION ICA' in ruta_upper
        or 'DECLARACION DE RETENCION DE ICA' in ruta_upper
    )


def _extract_retencion_ica_metadata(text, filename, filename_metadata, ruta_archivo=''):
    from migracion_masiva_archivo.services.saia.bancolombia_classifier import extract_bancolombia_period

    text_upper = str(text or '').upper()
    filename_stem = os.path.splitext(os.path.basename(filename))[0].strip() if filename else ''
    filename_upper = normalize_text(filename_stem)
    route_upper = normalize_text(ruta_archivo)
    searchable_text = ' '.join(item for item in [text_upper, filename_upper, route_upper] if item)
    title_search_text = ' '.join(item for item in [text_upper, filename_upper] if item)
    title_ok = bool(
        re.search(r'\bDECLARACION\s+BIMESTR(?:AL|E)\b', title_search_text)
        or 'DECLARACION DE RETENCION DE ICA' in title_search_text
        or 'RETENCION DE ICA' in title_search_text
        or 'RETENCION ICA' in title_search_text
    )
    text_year, month_num = extract_bancolombia_period(text)
    content_month_num = month_num
    filename_year = None
    filename_month = None

    if filename:
        filename_year, filename_month = extract_bancolombia_period(
            filename_stem
        )
        month_num = month_num or filename_month

    path_year = _extract_year_from_text(ruta_archivo)
    year = path_year or filename_year or text_year

    if not month_num:
        route_text = str(ruta_archivo or '')
        _, route_month = extract_bancolombia_period(route_text)
        month_num = route_month

    bimestre_num = _extract_retencion_ica_bimestre(searchable_text)
    if not month_num and bimestre_num:
        month_num = min(bimestre_num * 2, 12)

    month_name = _MESES_POR_NUM.get(month_num)
    inconsistencias = []
    if path_year and text_year and path_year != text_year and not filename_year:
        inconsistencias.append(f'anio carpeta {path_year} no coincide con anio PDF {text_year}')
    if filename_month and content_month_num and filename_month != content_month_num:
        inconsistencias.append(
            f'mes nombre {_MESES_POR_NUM.get(filename_month, filename_month)} '
            f'no coincide con mes PDF {_MESES_POR_NUM.get(content_month_num, content_month_num)}'
        )
    if not title_ok:
        inconsistencias.append('PDF no confirma titulo DECLARACION BIMESTRAL')

    titulo_documento = _extract_retencion_ica_title(searchable_text)
    asunto = filename_stem or (
        f'{titulo_documento} {year}' if year else titulo_documento
    )
    fecha_documento = date(year, month_num or 1, 1) if year else None
    if year and title_ok and not inconsistencias:
        confianza, requiere_revision = 95, False
    elif year or title_ok:
        confianza, requiere_revision = 60, True
    else:
        confianza, requiere_revision = 40, True

    return {
        'nit': '',
        'proveedor': 'INVERSIONES EURO S.A',
        'consecutivo': asunto,
        'fecha_documento': fecha_documento,
        'tipo_documento': 'DOCUMENTO_RETENCION_ICA',
        'valor': None,
        'medio_pago': '',
        'confianza': confianza,
        'normalizado': bool(year and month_name),
        'requiere_revision': requiere_revision,
        'mismatch_consecutivo': False,
        'mismatch_bloquea': False,
        'ocr_consecutivo_original': '',
        'datos_pel': {
            'retencion_ica_titulo': _RETENCION_ICA_TITLE,
            'retencion_ica_titulo_documento': titulo_documento,
            'retencion_ica_a\u00f1o': year,
            'retencion_ica_a\u00f1o_carpeta': path_year,
            'retencion_ica_a\u00f1o_pdf': text_year,
            'retencion_ica_a\u00f1o_nombre': filename_year,
            'retencion_ica_bimestre': bimestre_num,
            'retencion_ica_mes': month_name or '',
            'retencion_ica_mes_num': month_num,
            'retencion_ica_mes_num_nombre': filename_month,
            'retencion_ica_mes_num_pdf': content_month_num,
            'retencion_ica_titulo_ok': title_ok,
            'retencion_ica_inconsistencias': inconsistencias,
            'asunto_saia': asunto,
            'identidad_documental': f'RICA-{year}-{asunto}' if year else asunto,
        },
        'observaciones_extraccion': (
            f'Retencion ICA: titulo={titulo_documento}, anio={year}, bimestre={bimestre_num}, mes={month_num}'
        ),
    }


def _extract_retencion_ica_bimestre(value):
    match = re.search(r'\bBIMESTR(?:AL|E)?\s*(\d{1,2})\b', normalize_text(value))
    if not match:
        return None
    try:
        bimestre = int(match.group(1))
    except ValueError:
        return None
    return bimestre if 1 <= bimestre <= 6 else None


def _extract_retencion_ica_title(value):
    text = normalize_text(value)
    if re.search(r'\bDECLARACION\s+BIMESTR(?:AL|E)\b', text):
        return _RETENCION_ICA_BIMESTRAL_TITLE
    return _RETENCION_ICA_TITLE


# ── Impuesto al Consumo (Recibo Oficial de Pago Impuestos Nacionales - DIAN 490) ──
# Portado desde Euro_gestion_documental_API/Documental/services/extraction_service.py
# (nunca se habia portado — ver Fase 7 de la migracion). Clasificacion por
# CARPETA/CONTENIDO (igual que RICA/ECB/EGC/Bancolombia), no por codigo de nombre
# de archivo: los archivos originales conservan su nombre de escaneo y viven en una
# carpeta "Impuesto al Consumo" (con subcarpetas o nombres de archivo que mencionan
# el bimestre). El contenido OCR confirma el titulo del formulario 490 y extrae los
# datos minimos (periodo/bimestre, año, valor, fecha de pago, NIT) para validacion
# cruzada antes de subir a SAIA.
_IMPUESTO_CONSUMO_PATH_RE = re.compile(r'IMPUESTOS?\s+AL\s+CONSUMO|IMPUESTOS?\s+CONSUMO')
_IMPUESTO_CONSUMO_TITLE_RE = re.compile(
    r'RECIBO\s+OFICIAL\s+DE\s+PAGO\s+(?:DE\s+)?IMPUESTOS?\s+NACIONALES',
)
_IMPUESTO_CONSUMO_BIMESTRE_RE = re.compile(r'\bBIMESTRE\s*([1-6])\b')
_IMPUESTO_CONSUMO_PERIODO_RE = re.compile(
    r'\bPERIODO\b(?!\s*(?:INICIAL|FINAL))\D{0,10}?([1-6])\b',
)
_IMPUESTO_CONSUMO_ANO_RE = re.compile(r'\bANO\b\D{0,10}?(20\d{2})\b')
_IMPUESTO_CONSUMO_CONCEPTO_RE = re.compile(r'\bCONCEPTO\D{0,10}?(\d{2})\b')
_IMPUESTO_CONSUMO_VALOR_RE = re.compile(
    r'VALOR\s+PAGO\s+IMPUESTO\D{0,20}?([\d.,]{4,15})',
)
_IMPUESTO_CONSUMO_FECHA_PAGO_RE = re.compile(
    r'FECHA\s+PARA\s+EL\s+PAGO\D{0,20}?(\d{4})\D{1,3}(\d{1,2})\D{1,3}(\d{1,2})\b',
)
_IMPUESTO_CONSUMO_NIT_RE = re.compile(r'\bNIT\D{0,15}?(\d{6,10}[-\s]?\d)\b')
_IMPUESTO_CONSUMO_CODES = {'IC1', 'IC2', 'IC3', 'IC4', 'IC5', 'IC6'}

# Ademas de los 6 recibos bimestrales (IC1..IC6), existe un septimo expediente
# separado en SAIA ("IMPUESTO AL CONSUMO2014", sin espacio) para el auxiliar
# contable anual de la cuenta 24780101 - no es un recibo DIAN y no tiene bimestre.
_IMPUESTO_CONSUMO_LEDGER_RE = re.compile(
    r'CONSULTAS\s+CUENTAS|PUC[\s\-]*PLAN\s+UNICO\s+DE\s+CUENTAS|AUXILIAR\s*[:.]',
)


def _is_impuesto_consumo_path(ruta_archivo):
    return bool(_IMPUESTO_CONSUMO_PATH_RE.search(normalize_text(ruta_archivo)))


def _looks_like_impuesto_consumo_content(text_upper):
    """Respaldo cuando la carpeta no menciona 'Impuesto al Consumo': el titulo
    del recibo 490 por si solo no basta (la DIAN lo usa para Renta, IVA, etc.),
    asi que se exige ademas la mencion literal 'IMPUESTO AL CONSUMO' (presente
    en la pagina del auxiliar contable) o el codigo de concepto 21."""
    if _IMPUESTO_CONSUMO_TITLE_RE.search(text_upper):
        if _IMPUESTO_CONSUMO_PATH_RE.search(text_upper):
            return True
        return _extract_impuesto_consumo_concepto(text_upper) == '21'
    # Sin titulo de recibo DIAN: solo clasifica como Impuesto al Consumo si es
    # inequivocamente el auxiliar contable de esa cuenta especifica.
    return bool(_IMPUESTO_CONSUMO_LEDGER_RE.search(text_upper) and _IMPUESTO_CONSUMO_PATH_RE.search(text_upper))


def _is_impuesto_consumo_ledger(text_upper):
    return bool(_IMPUESTO_CONSUMO_LEDGER_RE.search(text_upper))


def _extract_impuesto_consumo_anual_metadata(text, filename, filename_metadata, ruta_archivo=''):
    text_upper = normalize_text(text)
    filename_stem = os.path.splitext(os.path.basename(filename))[0].strip() if filename else ''

    ledger_ok = _is_impuesto_consumo_ledger(text_upper)
    año = (
        _extract_impuesto_consumo_ano(text_upper)
        or _extract_year_from_text(text_upper)
        or _extract_year_from_text(ruta_archivo)
        or _extract_year_from_text(filename_stem)
    )

    inconsistencias = []
    if not ledger_ok:
        inconsistencias.append('PDF no confirma el auxiliar contable (Consultas Cuentas / PUC)')
    if not año:
        inconsistencias.append('No se detecto anio en el documento')

    asunto = filename_stem or (f'IMPUESTO AL CONSUMO {año}' if año else '')

    if ledger_ok and año:
        confianza, requiere_revision = 90, False
    elif ledger_ok or año:
        confianza, requiere_revision = 60, True
    else:
        confianza, requiere_revision = 35, True

    return {
        'nit': '',
        'proveedor': 'INVERSIONES EURO S.A',
        'consecutivo': asunto,
        'fecha_documento': date(año, 12, 31) if año else None,
        'tipo_documento': 'DOCUMENTO_IMPUESTO_CONSUMO_ANUAL',
        'valor': None,
        'medio_pago': '',
        'confianza': confianza,
        'normalizado': bool(año),
        'requiere_revision': requiere_revision,
        'mismatch_consecutivo': False,
        'mismatch_bloquea': False,
        'ocr_consecutivo_original': '',
        'datos_pel': {
            'impuesto_consumo_anual_ledger_ok': ledger_ok,
            'impuesto_consumo_anual_año': año,
            'impuesto_consumo_anual_inconsistencias': inconsistencias,
            'asunto_saia': asunto,
            'identidad_documental': asunto,
        },
        'observaciones_extraccion': (
            f'Impuesto al Consumo (auxiliar anual): ledger_ok={ledger_ok}, anio={año}'
        ),
    }


def _extract_impuesto_consumo_metadata(text, filename, filename_metadata, ruta_archivo=''):
    text_upper = normalize_text(text)
    ruta_upper = normalize_text(ruta_archivo)
    filename_stem = os.path.splitext(os.path.basename(filename))[0].strip() if filename else ''

    document_identifier = filename_metadata.get('tipo_documento_nombre') or ''
    periodo_nombre = (
        int(document_identifier[-1])
        if document_identifier in _IMPUESTO_CONSUMO_CODES
        else None
    )

    title_ok = bool(_IMPUESTO_CONSUMO_TITLE_RE.search(text_upper))
    periodo_pdf = _extract_impuesto_consumo_periodo(text_upper)
    periodo_carpeta = _extract_impuesto_consumo_bimestre(ruta_upper) or _extract_impuesto_consumo_bimestre(
        normalize_text(filename_stem)
    )
    año = _extract_impuesto_consumo_ano(text_upper) or _extract_year_from_text(ruta_archivo)
    concepto = _extract_impuesto_consumo_concepto(text_upper)
    valor_pago = _extract_impuesto_consumo_valor(text_upper)
    fecha_pago = _extract_impuesto_consumo_fecha_pago(text_upper)
    nit = _extract_impuesto_consumo_nit(text_upper)

    bimestre = periodo_pdf or periodo_carpeta or periodo_nombre

    inconsistencias = []
    if not title_ok:
        inconsistencias.append('PDF no confirma titulo RECIBO OFICIAL DE PAGO IMPUESTOS NACIONALES')
    if periodo_pdf and periodo_carpeta and periodo_pdf != periodo_carpeta:
        inconsistencias.append(
            f'periodo del PDF ({periodo_pdf}) no coincide con el bimestre de la carpeta ({periodo_carpeta})'
        )
    if periodo_pdf and periodo_nombre and periodo_pdf != periodo_nombre:
        inconsistencias.append(
            f'periodo del PDF ({periodo_pdf}) no coincide con el bimestre del nombre de archivo ({periodo_nombre})'
        )
    if not año:
        inconsistencias.append('No se detecto anio en el PDF')
    if not bimestre:
        inconsistencias.append('No se detecto el bimestre (periodo) del documento')

    asunto = filename_stem or (f'IMPUESTO AL CONSUMO BIMESTRE {bimestre} {año}' if bimestre and año else '')
    fecha_documento = fecha_pago or (date(año, 1, 1) if año else None)

    if title_ok and año and bimestre and not inconsistencias:
        confianza, requiere_revision = 95, False
    elif title_ok or periodo_pdf or año:
        confianza, requiere_revision = 65, True
    else:
        confianza, requiere_revision = 40, True

    return {
        'nit': nit,
        'proveedor': 'INVERSIONES EURO S.A',
        'consecutivo': asunto,
        'fecha_documento': fecha_documento,
        'tipo_documento': 'DOCUMENTO_IMPUESTO_CONSUMO',
        'valor': valor_pago,
        'medio_pago': '',
        'confianza': confianza,
        'normalizado': bool(año and bimestre),
        'requiere_revision': requiere_revision,
        'mismatch_consecutivo': False,
        'mismatch_bloquea': False,
        'ocr_consecutivo_original': '',
        'datos_pel': {
            'impuesto_consumo_titulo_ok': title_ok,
            'impuesto_consumo_periodo': periodo_pdf,
            'impuesto_consumo_periodo_carpeta': periodo_carpeta,
            'impuesto_consumo_periodo_nombre': periodo_nombre,
            'impuesto_consumo_bimestre': bimestre,
            'impuesto_consumo_año': año,
            'impuesto_consumo_concepto': concepto,
            'impuesto_consumo_valor_pago': str(valor_pago) if valor_pago is not None else '',
            'impuesto_consumo_fecha_pago': fecha_pago.isoformat() if fecha_pago else '',
            'impuesto_consumo_nit': nit,
            'impuesto_consumo_inconsistencias': inconsistencias,
            'asunto_saia': asunto,
            'identidad_documental': asunto,
        },
        'observaciones_extraccion': (
            f'Impuesto al Consumo: titulo_ok={title_ok}, bimestre={bimestre}, '
            f'anio={año}, valor={valor_pago}'
        ),
    }


def _extract_impuesto_consumo_periodo(value):
    match = _IMPUESTO_CONSUMO_PERIODO_RE.search(value)
    if not match:
        return None
    try:
        periodo = int(match.group(1))
    except ValueError:
        return None
    return periodo if 1 <= periodo <= 6 else None


def _extract_impuesto_consumo_bimestre(value):
    match = _IMPUESTO_CONSUMO_BIMESTRE_RE.search(value)
    return int(match.group(1)) if match else None


def _extract_impuesto_consumo_ano(value):
    match = _IMPUESTO_CONSUMO_ANO_RE.search(value)
    return int(match.group(1)) if match else None


def _extract_impuesto_consumo_concepto(value):
    match = _IMPUESTO_CONSUMO_CONCEPTO_RE.search(value)
    return match.group(1) if match else ''


def _extract_impuesto_consumo_valor(value):
    match = _IMPUESTO_CONSUMO_VALOR_RE.search(value)
    if not match:
        return None
    return normalize_money(match.group(1))


def _extract_impuesto_consumo_fecha_pago(value):
    match = _IMPUESTO_CONSUMO_FECHA_PAGO_RE.search(value)
    if not match:
        return None
    year, month, day = (int(item) for item in match.groups())
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _extract_impuesto_consumo_nit(value):
    match = _IMPUESTO_CONSUMO_NIT_RE.search(value)
    return normalize_nit(match.group(1)) if match else ''


# ── Ajustes Contables internos: INC "Indirectos Contables Cierre" e IND
# "Indirectos Contables" (comprobantes contable internos) ───────────────────
# Ambos viven en SAIA bajo Archivo Central > Direccion de Contabilidad >
# Ajustes Contables, comparten el mismo formato de encabezado interno
# ("Numero:", "Fecha:") y NO tienen encabezado "Pagos Electronicos" (no son
# PEL), asi que usan su propio extractor en vez del generico. No devuelve
# nit, proveedor, valor ni medio_pago (D. Cruce/M. Pago): no aplican a este
# tipo de documento y no aportan nada para ubicarlo o validarlo, asi que ni
# siquiera se incluyen en el diccionario. El prefijo del consecutivo varia
# segun el area que lo emite (ej. "MAY-INC-00000185" Mayorista,
# "ADM-IND-00000041" Administracion), por lo que se lee del propio documento
# en vez de asumir siempre "MAY". Clasificacion por CARPETA (disco:
# .../INC|IND/<año>/...) o por el codigo de nombre de archivo, igual que
# RCG/ECB. Portado desde Euro_gestion_documental_API (nunca se habia portado).
_INC_TITLE_RE = re.compile(r'INDIRECTOS\s+CONTABLES\s+CIERRE')
# IND no lleva "CIERRE"; el lookahead negativo evita que un comprobante INC
# (que SI contiene "INDIRECTOS CONTABLES" como subcadena) se clasifique como IND.
_IND_TITLE_RE = re.compile(r'INDIRECTOS\s+CONTABLES\b(?!\s+CIERRE)')
_AJUSTE_CONTABLE_FECHA_RE = re.compile(r'\bFECHA\s*[:\-]?\s*(\d{1,2})[\/\-]([A-Z]{3}|\d{1,2})[\/\-](\d{2,4})\b')
_AJUSTE_CONTABLE_MESES_ABREV_EN = {
    'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
    'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12,
}


def _is_inc_path(ruta_archivo):
    ruta_upper = normalize_text(ruta_archivo)
    return bool(re.search(r'[\\/]INC[\\/]', ruta_upper)) or 'INDIRECTOS CONTABLES CIERRE' in ruta_upper


def _is_ind_path(ruta_archivo):
    return bool(re.search(r'[\\/]IND[\\/]', normalize_text(ruta_archivo)))


def _extract_ajuste_contable_fecha(text_upper):
    match = _AJUSTE_CONTABLE_FECHA_RE.search(text_upper)
    if not match:
        return None
    day_s, month_s, year_s = match.groups()
    try:
        day = int(day_s)
    except ValueError:
        return None
    month = _AJUSTE_CONTABLE_MESES_ABREV_EN.get(month_s) if month_s.isalpha() else int(month_s)
    if not month:
        return None
    year = int(year_s)
    if year < 100:
        year += 2000
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _extract_ajuste_contable_numero(text_upper, code):
    match = re.search(rf'\b([A-Z]{{2,4}})[\s\-]*{code}[\s\-]*0*(\d{{3,8}})\b', text_upper)
    if not match:
        return '', None
    prefix, number = match.groups()
    return prefix, int(number)


def _extract_ajuste_contable_numero_from_filename(filename_stem, code):
    # file_name_service.py exige 4-8 digitos (pensado para PEL/RCG/ECB), pero
    # estos comprobantes usan numeros cortos sin ceros a la izquierda (ej.
    # "IND 41.pdf"), asi que se extraen aqui con una regla propia mas
    # permisiva (1-8 digitos).
    match = re.search(rf'\b{code}\s*[\-]?\s*0*(\d{{1,8}})\b', normalize_text(filename_stem))
    return int(match.group(1)) if match else None


def _extract_ajuste_contable_metadata(text_upper, filename_stem, ruta_archivo, code, title_re, tipo_documento):
    prefix_key = code.lower()

    title_ok = bool(title_re.search(text_upper))
    prefix, numero_pdf = _extract_ajuste_contable_numero(text_upper, code)
    fecha = _extract_ajuste_contable_fecha(text_upper)
    filename_numero = _extract_ajuste_contable_numero_from_filename(filename_stem, code)

    # El OCR de comprobantes antiguos (impresora de matriz de puntos) confunde
    # digitos (0/9) y letras similares en el numero impreso (ej. "ING" en vez
    # de "INC"); el nombre de archivo (tecleado a mano) es la fuente de
    # verdad para el numero. El OCR solo aporta el prefijo de area
    # (MAY/ADM/...), que no esta en el nombre de archivo.
    numero = filename_numero or numero_pdf
    año = fecha.year if fecha else _extract_year_from_text(ruta_archivo)

    # Solo se valida (bloquea) el consecutivo interno y el año del
    # encabezado. El titulo se registra en datos_pel como dato informativo,
    # pero ya no bloquea la carga a SAIA aunque no se lea.
    inconsistencias = []
    if not numero:
        inconsistencias.append('No se detecto el numero de comprobante ni en el PDF ni en el nombre de archivo')
    if numero_pdf and filename_numero and int(numero_pdf) != int(filename_numero):
        inconsistencias.append(
            f'numero del PDF ({numero_pdf}) no coincide con el numero del nombre de archivo ({filename_numero})'
        )
    if not año:
        inconsistencias.append('No se detecto el anio del comprobante')

    if numero and prefix:
        consecutivo = f'{prefix}-{code}-{int(numero):08d}'
    elif numero:
        consecutivo = f'{code}-{int(numero):08d}'
    else:
        consecutivo = filename_stem

    if numero and año and not inconsistencias:
        confianza, requiere_revision = 95, False
    elif numero or año:
        confianza, requiere_revision = 65, True
    else:
        confianza, requiere_revision = 40, True

    return {
        'consecutivo': consecutivo,
        'fecha_documento': fecha or (date(año, 1, 1) if año else None),
        'tipo_documento': tipo_documento,
        'confianza': confianza,
        'normalizado': bool(numero and fecha),
        'requiere_revision': requiere_revision,
        'mismatch_consecutivo': False,
        'mismatch_bloquea': False,
        'ocr_consecutivo_original': '',
        'datos_pel': {
            f'{prefix_key}_titulo_ok': title_ok,
            f'{prefix_key}_prefijo': prefix,
            f'{prefix_key}_numero': numero,
            f'{prefix_key}_numero_pdf': numero_pdf,
            f'{prefix_key}_numero_nombre': filename_numero,
            f'{prefix_key}_fecha': fecha.isoformat() if fecha else '',
            f'{prefix_key}_año': año,
            f'{prefix_key}_inconsistencias': inconsistencias,
            'asunto_saia': consecutivo,
            'identidad_documental': consecutivo,
        },
        'observaciones_extraccion': (
            f'{code}: titulo_ok={title_ok}, numero={consecutivo}, fecha={fecha}'
        ),
    }


def _extract_inc_metadata(text, filename, filename_metadata, ruta_archivo=''):
    text_upper = normalize_text(text)
    filename_stem = os.path.splitext(os.path.basename(filename))[0].strip() if filename else ''
    return _extract_ajuste_contable_metadata(
        text_upper, filename_stem, ruta_archivo,
        code='INC', title_re=_INC_TITLE_RE,
        tipo_documento='DOCUMENTO_INC',
    )


# Al menos IND 2016 organiza los comprobantes en sub-expedientes por sede
# (ADMINISTRACION, BARBOSA, BELLO, BERNAL, CASTILLA, CEDI, DESPOSTAR,
# FLORIDA, LAURELES, MARINILLA, MAYORISTA, MONTERIA, PALMAS, SABANETA...) -
# la sede confiable para RUTEAR es la carpeta local (igual que BBVA/
# Davivienda/Bogota), ya que en SAIA el mismo nombre de carpeta es el
# sub-expediente dentro de "IND <año>". Para VALIDAR se usa el nombre de
# sede impreso en el propio documento (linea debajo del NIT, en la columna
# izquierda del encabezado - ej. "EURO BARBOSA", "ADMINISTRACION"), no el
# prefijo del consecutivo: asi cubre cualquier sede sin necesitar una tabla
# de siglas confirmadas una por una.
_TERCERO_LABEL_RE = re.compile(r'\bTERCERO\b')


def _extract_ind_sede_from_path(ruta_archivo):
    """Nombre de la subcarpeta de sede (padre inmediato del archivo), o '' si
    el archivo vive directo en la carpeta del año (años sin sub-expediente)."""
    if not ruta_archivo:
        return ''
    try:
        from pathlib import PurePosixPath, PureWindowsPath
        ruta_text = str(ruta_archivo)
        parent = PureWindowsPath(ruta_text).parent.name or PurePosixPath(ruta_text).parent.name
        parent = parent.strip()
    except Exception:
        return ''
    if not parent or re.fullmatch(r'20\d{2}', parent):
        return ''
    return parent


def _extract_ind_sede_header(text_upper):
    """Nombre de sede impreso en el encabezado (debajo del NIT), tomando el
    texto entre el final de la linea 'Fecha:' y la siguiente etiqueta
    'Tercero:'. Es la sede tal como la escribio quien emitio el documento,
    no un codigo que haya que traducir."""
    fecha_match = _AJUSTE_CONTABLE_FECHA_RE.search(text_upper)
    if not fecha_match:
        return ''
    resto = text_upper[fecha_match.end():]
    tercero_match = _TERCERO_LABEL_RE.search(resto)
    candidate = resto[:tercero_match.start()] if tercero_match else resto[:60]
    candidate = re.sub(r'\bEURO\b', ' ', candidate)
    candidate = re.sub(r'[^A-Z\s]', ' ', candidate)
    return re.sub(r'\s+', ' ', candidate).strip()


def _sede_header_matches_folder(sede_header, sede_carpeta):
    """True/False si se puede comparar; None si falta alguno de los dos lados."""
    header_norm = normalize_text(sede_header)
    carpeta_norm = normalize_text(sede_carpeta)
    if not header_norm or not carpeta_norm:
        return None
    return carpeta_norm in header_norm or header_norm in carpeta_norm


def _extract_ind_metadata(text, filename, filename_metadata, ruta_archivo=''):
    text_upper = normalize_text(text)
    filename_stem = os.path.splitext(os.path.basename(filename))[0].strip() if filename else ''
    result = _extract_ajuste_contable_metadata(
        text_upper, filename_stem, ruta_archivo,
        code='IND', title_re=_IND_TITLE_RE,
        tipo_documento='DOCUMENTO_IND',
    )

    sede_carpeta = _extract_ind_sede_from_path(ruta_archivo)
    sede_header = _extract_ind_sede_header(text_upper)
    if _sede_header_matches_folder(sede_header, sede_carpeta) is False:
        result['datos_pel']['ind_inconsistencias'].append(
            f'sede del encabezado ({sede_header}) no coincide con la carpeta ({sede_carpeta})'
        )
        result['requiere_revision'] = True
        result['confianza'] = min(result['confianza'], 65)
    result['datos_pel']['ind_sede'] = sede_carpeta
    result['datos_pel']['ind_sede_encabezado'] = sede_header
    return result


def _is_ecb_path(ruta_archivo):
    ruta_upper = normalize_text(ruta_archivo)
    return (
        'EGRESOS CHEQUES BANCOLOMBIA' in ruta_upper
        or 'EGRESOS Y CHEQUES BANCOLOMBIA' in ruta_upper
        or re.search(r'\bECB\s*20\d{2}\b', ruta_upper)
    )


def _extract_ecb_metadata(text, filename, filename_metadata, ruta_archivo=''):
    text_upper = normalize_text(text)
    filename_stem = os.path.splitext(os.path.basename(filename))[0].strip() if filename else ''
    title_ok = bool(re.search(r'\bEGRESOS?\s+CHEQUES?\s+BANCOLOMBIA\b', text_upper))
    filename_number = _extract_ecb_number(filename_stem)
    ocr_number = _extract_ecb_number(text_upper)
    cheque_number = _extract_ecb_cheque_number(text_upper) or ocr_number or filename_number
    year = _extract_year_from_text(ruta_archivo) or _extract_year_from_text(text_upper)
    fecha_documento = _extract_ecb_date(text_upper)
    if fecha_documento and not year:
        year = fecha_documento.year
    consecutivo_number = ocr_number or filename_number or cheque_number
    consecutivo = f'MAY-ECB-{int(consecutivo_number):08d}' if consecutivo_number else (filename_stem or '')
    asunto = filename_stem or (f'ECB {int(consecutivo_number)}' if consecutivo_number else consecutivo)
    inconsistencias = []

    if not title_ok:
        inconsistencias.append('PDF no confirma titulo EGRESOS CHEQUES BANCOLOMBIA')
    if not consecutivo_number:
        inconsistencias.append('No se detecto consecutivo ECB')
    pdf_number_for_match = ocr_number or cheque_number
    if filename_number and pdf_number_for_match and filename_number != pdf_number_for_match:
        inconsistencias.append(f'numero nombre {filename_number} no coincide con numero PDF {pdf_number_for_match}')
    if year and fecha_documento and year != fecha_documento.year:
        inconsistencias.append(f'anio carpeta {year} no coincide con fecha PDF {fecha_documento.year}')

    if title_ok and consecutivo_number and year and not inconsistencias:
        confianza, requiere_revision = 95, False
    elif consecutivo_number or year or title_ok:
        confianza, requiere_revision = 60, True
    else:
        confianza, requiere_revision = 40, True

    return {
        'nit': '',
        'proveedor': 'INVERSIONES EURO S.A',
        'consecutivo': asunto,
        'fecha_documento': fecha_documento or (date(year, 1, 1) if year else None),
        'tipo_documento': 'DOCUMENTO_ECB',
        'valor': None,
        'medio_pago': '',
        'confianza': confianza,
        'normalizado': bool(consecutivo_number and year),
        'requiere_revision': requiere_revision,
        'mismatch_consecutivo': False,
        'mismatch_bloquea': False,
        'ocr_consecutivo_original': '',
        'datos_pel': {
            'ecb_titulo': 'EGRESOS CHEQUES BANCOLOMBIA',
            'ecb_titulo_ok': title_ok,
            'ecb_a\u00f1o': year,
            'ecb_numero': int(consecutivo_number) if consecutivo_number else None,
            'ecb_numero_nombre': int(filename_number) if filename_number else None,
            'ecb_numero_pdf': int(ocr_number) if ocr_number else None,
            'ecb_cheque_numero': int(cheque_number) if cheque_number else None,
            'ecb_consecutivo_may': consecutivo if consecutivo_number else '',
            'ecb_inconsistencias': inconsistencias,
            'asunto_saia': asunto,
            'identidad_documental': f'ECB-{year}-{int(consecutivo_number)}' if (year and consecutivo_number) else asunto,
        },
        'observaciones_extraccion': (
            f'ECB: titulo=EGRESOS CHEQUES BANCOLOMBIA, anio={year}, numero={consecutivo_number}'
        ),
    }


def _extract_ecb_number(value):
    text = str(value or '').upper()
    text = _ECB_SPACED_RE.sub('ECB', text)
    text = text.replace('â€”', '-').replace('â€“', '-')
    patterns = [
        r'\bMAY\s*[- ]?ECB\s*[- ]?0*(\d{3,8})\b',
        r'\bECB\s*[- ]?0*(\d{3,8})\b',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return int(_clean_ocr_digits(match.group(1)))
    return None


def _extract_ecb_cheque_number(value):
    text = normalize_text(value)
    match = re.search(r'CHEQUE\s+NO\.?\s*0*(\d{3,8})\b', text)
    return int(match.group(1)) if match else None


def _extract_ecb_date(value):
    text = normalize_text(value)
    match = re.search(r'\b(\d{1,2})[-/](?:OCT|OCTUBRE|(\d{1,2}))[-/](\d{2,4})\b', text)
    if match:
        day = int(match.group(1))
        month = 10 if match.group(2) is None else int(match.group(2))
        raw_year = int(match.group(3))
        year = 2000 + raw_year if raw_year < 100 else raw_year
        try:
            return date(year, month, day)
        except ValueError:
            return None
    match = re.search(r'\b(20\d{2})\s+(\d{1,2})\s+(\d{1,2})\b', text)
    if match:
        year, month, day = (int(item) for item in match.groups())
        try:
            return date(year, month, day)
        except ValueError:
            return None
    return None


def _is_egc_path(ruta_archivo):
    ruta_upper = normalize_text(ruta_archivo)
    return (
        'EGRESOS CHEQUES - EGC' in ruta_upper
        or 'EGRESOS CHEQUES-EGC' in ruta_upper
        or 'EGRESOS Y CHEQUES' in ruta_upper
        or re.search(r'\bEGC\s*20\d{2}\b', ruta_upper)
        or re.search(r'\bECG\s*20\d{2}\b', ruta_upper)
    )


def _extract_egc_metadata(text, filename, filename_metadata, ruta_archivo=''):
    text_upper = normalize_text(text)
    filename_stem = os.path.splitext(os.path.basename(filename))[0].strip() if filename else ''
    title_ok = bool(re.search(r'\bEGRESOS?\s+CHEQUES?\b', text_upper))
    filename_number = _extract_egc_number(filename_stem)
    ocr_number = _extract_egc_number(text_upper)
    cheque_number = _extract_egc_cheque_number(text_upper) or ocr_number or filename_number
    year = _extract_year_from_text(ruta_archivo) or _extract_year_from_text(text_upper)
    fecha_documento = _extract_egc_date(text_upper)
    if fecha_documento and not year:
        year = fecha_documento.year
    consecutivo_number = ocr_number or filename_number or cheque_number
    consecutivo = f'MAY-EGC-{int(consecutivo_number):08d}' if consecutivo_number else (filename_stem or '')
    asunto = filename_stem or (f'EGC {int(consecutivo_number)}' if consecutivo_number else consecutivo)
    inconsistencias = []

    if not title_ok:
        inconsistencias.append('PDF no confirma titulo EGRESOS CHEQUES')
    if not consecutivo_number:
        inconsistencias.append('No se detecto consecutivo EGC')
    pdf_number_for_match = ocr_number or cheque_number
    if filename_number and pdf_number_for_match and filename_number != pdf_number_for_match:
        inconsistencias.append(f'numero nombre {filename_number} no coincide con numero PDF {pdf_number_for_match}')
    if year and fecha_documento and year != fecha_documento.year:
        inconsistencias.append(f'anio carpeta {year} no coincide con fecha PDF {fecha_documento.year}')

    if title_ok and consecutivo_number and year and not inconsistencias:
        confianza, requiere_revision = 95, False
    elif consecutivo_number or year or title_ok:
        confianza, requiere_revision = 60, True
    else:
        confianza, requiere_revision = 40, True

    return {
        'nit': '',
        'proveedor': 'INVERSIONES EURO S.A',
        'consecutivo': asunto,
        'fecha_documento': fecha_documento or (date(year, 1, 1) if year else None),
        'tipo_documento': 'DOCUMENTO_EGC',
        'valor': None,
        'medio_pago': '',
        'confianza': confianza,
        'normalizado': bool(consecutivo_number and year),
        'requiere_revision': requiere_revision,
        'mismatch_consecutivo': False,
        'mismatch_bloquea': False,
        'ocr_consecutivo_original': '',
        'datos_pel': {
            'egc_titulo': 'EGRESOS CHEQUES',
            'egc_titulo_ok': title_ok,
            'egc_a\u00f1o': year,
            'egc_numero': int(consecutivo_number) if consecutivo_number else None,
            'egc_numero_nombre': int(filename_number) if filename_number else None,
            'egc_numero_pdf': int(ocr_number) if ocr_number else None,
            'egc_cheque_numero': int(cheque_number) if cheque_number else None,
            'egc_consecutivo_may': consecutivo if consecutivo_number else '',
            'egc_inconsistencias': inconsistencias,
            'asunto_saia': asunto,
            'identidad_documental': f'EGC-{year}-{int(consecutivo_number)}' if (year and consecutivo_number) else asunto,
        },
        'observaciones_extraccion': (
            f'EGC: titulo=EGRESOS CHEQUES, anio={year}, numero={consecutivo_number}'
        ),
    }


def _extract_egc_number(value):
    text = str(value or '').upper()
    text = _EGC_SPACED_RE.sub('EGC', text)
    text = _ECG_SPACED_RE.sub('ECG', text)
    text = text.replace('â€”', '-').replace('â€“', '-')
    patterns = [
        r'\bMAY\s*[- ]?EGC\s*[- ]?0*(\d{3,8})\b',
        r'\bMAY\s*[- ]?ECG\s*[- ]?0*(\d{3,8})\b',
        r'\bEGC\s*[- ]?0*(\d{3,8})\b',
        r'\bECG\s*[- ]?0*(\d{3,8})\b',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return int(_clean_ocr_digits(match.group(1)))
    return None


def _extract_egc_cheque_number(value):
    text = normalize_text(value)
    match = re.search(r'CHEQUE\s+NO\.?\s*0*(\d{3,8})\b', text)
    return int(match.group(1)) if match else None


def _extract_egc_date(value):
    text = normalize_text(value)
    match = re.search(r'\b(\d{1,2})/(\d{1,2})/(20\d{2})\b', text)
    if match:
        day, month, year = (int(item) for item in match.groups())
        try:
            return date(year, month, day)
        except ValueError:
            return None
    match = re.search(r'\b(20\d{2})\s+(\d{1,2})\s+(\d{1,2})\b', text)
    if match:
        year, month, day = (int(item) for item in match.groups())
        try:
            return date(year, month, day)
        except ValueError:
            return None
    return None


def _is_ege_path(ruta_archivo):
    ruta_upper = normalize_text(ruta_archivo)
    return (
        'EGRESOS EFECTIVO' in ruta_upper
        or bool(re.search(r'\bEGE\s*20\d{2}\b', ruta_upper))
    )


def _extract_ege_metadata(text, filename, filename_metadata, ruta_archivo=''):
    text_upper = normalize_text(text)
    filename_stem = os.path.splitext(os.path.basename(filename))[0].strip() if filename else ''
    title_ok = bool(_EGE_TITLE_RE.search(text_upper))
    filename_number = _extract_ege_number(filename_stem)
    ocr_number = _extract_ege_number(text_upper)
    consecutivo_number = ocr_number or filename_number
    year = _extract_year_from_text(ruta_archivo) or _extract_year_from_text(text_upper)
    fecha_documento = normalize_date(text_upper)
    if fecha_documento and not year:
        year = fecha_documento.year

    consecutivo = f'MAY-EGE-{int(consecutivo_number):08d}' if consecutivo_number else (filename_stem or '')
    asunto = filename_stem or (f'EGE {int(consecutivo_number)}' if consecutivo_number else consecutivo)
    inconsistencias = []

    if not title_ok:
        inconsistencias.append('PDF no confirma titulo EGRESOS EFECTIVO')
    if not consecutivo_number:
        inconsistencias.append('No se detecto consecutivo EGE')
    if filename_number and ocr_number and filename_number != ocr_number:
        inconsistencias.append(f'numero nombre {filename_number} no coincide con numero PDF {ocr_number}')
    if year and fecha_documento and year != fecha_documento.year:
        inconsistencias.append(f'anio carpeta {year} no coincide con fecha PDF {fecha_documento.year}')

    if title_ok and consecutivo_number and year and not inconsistencias:
        confianza, requiere_revision = 95, False
    elif consecutivo_number or year or title_ok:
        confianza, requiere_revision = 60, True
    else:
        confianza, requiere_revision = 40, True

    return {
        'nit': '',
        'proveedor': '',
        'consecutivo': asunto,
        'fecha_documento': fecha_documento or (date(year, 1, 1) if year else None),
        'tipo_documento': 'DOCUMENTO_EGE',
        'valor': None,
        'medio_pago': '',
        'confianza': confianza,
        'normalizado': bool(consecutivo_number and year),
        'requiere_revision': requiere_revision,
        'mismatch_consecutivo': False,
        'mismatch_bloquea': False,
        'ocr_consecutivo_original': '',
        'datos_pel': {
            'ege_titulo': 'EGRESOS EFECTIVO',
            'ege_titulo_ok': title_ok,
            'ege_año': year,
            'ege_numero': int(consecutivo_number) if consecutivo_number else None,
            'ege_numero_nombre': int(filename_number) if filename_number else None,
            'ege_numero_pdf': int(ocr_number) if ocr_number else None,
            'ege_consecutivo_may': consecutivo if consecutivo_number else '',
            'ege_inconsistencias': inconsistencias,
            'asunto_saia': asunto,
            'identidad_documental': f'EGE-{year}-{int(consecutivo_number)}' if (year and consecutivo_number) else asunto,
        },
        'observaciones_extraccion': (
            f'EGE: titulo=EGRESOS EFECTIVO, anio={year}, numero={consecutivo_number}'
        ),
    }


def _extract_ege_number(value):
    text = str(value or '').upper()
    text = _EGE_SPACED_RE.sub('EGE', text)
    text = text.replace('â€”', '-').replace('â€“', '-')
    patterns = [
        r'\bMAY\s*[- ]?EGE\s*[- ]?0*(\d{3,8})\b',
        r'\bEGE\s*[- ]?0*(\d{3,8})\b',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return int(_clean_ocr_digits(match.group(1)))
    return None


def _extract_corbanca_metadata(text, filename, filename_metadata, ruta_archivo=''):
    from migracion_masiva_archivo.services.saia.bancolombia_classifier import extract_bancolombia_period

    año, mes_num = extract_bancolombia_period(text)

    stem = os.path.splitext(os.path.basename(filename))[0].strip() if filename else ''
    consecutivo = stem or ''

    if año and mes_num:
        confianza, requiere_revision = 90, False
    elif año or mes_num:
        confianza, requiere_revision = 60, False
    else:
        confianza, requiere_revision = 40, True

    return {
        'nit': '',
        'proveedor': 'INVERSIONES EURO S.A',
        'consecutivo': consecutivo,
        'fecha_documento': date(año, mes_num, 1) if (año and mes_num) else None,
        'tipo_documento': 'DOCUMENTO_CORBANCA',
        'valor': None,
        'medio_pago': '',
        'confianza': confianza,
        'normalizado': bool(consecutivo),
        'requiere_revision': requiere_revision,
        'mismatch_consecutivo': False,
        'mismatch_bloquea': False,
        'ocr_consecutivo_original': '',
        'datos_pel': {
            'corbanca_año': año,
            'corbanca_mes_num': mes_num,
            'asunto_saia': consecutivo,
            'identidad_documental': consecutivo,
        },
        'observaciones_extraccion': (
            f'Corbanca: año={año}, mes={mes_num}'
        ),
    }


def _extract_colpatria_metadata(text, filename, filename_metadata, ruta_archivo=''):
    from migracion_masiva_archivo.services.saia.bancolombia_classifier import extract_bancolombia_period

    año, mes_num = extract_bancolombia_period(text)

    stem = os.path.splitext(os.path.basename(filename))[0].strip() if filename else ''
    consecutivo = stem or ''

    if año and mes_num:
        confianza, requiere_revision = 90, False
    elif año or mes_num:
        confianza, requiere_revision = 60, False
    else:
        confianza, requiere_revision = 40, True

    return {
        'nit': '',
        'proveedor': 'INVERSIONES EURO S.A',
        'consecutivo': consecutivo,
        'fecha_documento': date(año, mes_num, 1) if (año and mes_num) else None,
        'tipo_documento': 'DOCUMENTO_COLPATRIA',
        'valor': None,
        'medio_pago': '',
        'confianza': confianza,
        'normalizado': bool(consecutivo),
        'requiere_revision': requiere_revision,
        'mismatch_consecutivo': False,
        'mismatch_bloquea': False,
        'ocr_consecutivo_original': '',
        'datos_pel': {
            'colpatria_año': año,
            'colpatria_mes_num': mes_num,
            'asunto_saia': consecutivo,
            'identidad_documental': consecutivo,
        },
        'observaciones_extraccion': (
            f'Colpatria: año={año}, mes={mes_num}'
        ),
    }


def _make_conciliacion_metadata(text, filename, tipo_documento, año_key, mes_key, banco_label):
    from migracion_masiva_archivo.services.saia.bancolombia_classifier import extract_bancolombia_period
    año, mes_num = extract_bancolombia_period(text)
    stem = os.path.splitext(os.path.basename(filename))[0].strip() if filename else ''
    consecutivo = stem or ''
    if año and mes_num:
        confianza, requiere_revision = 90, False
    elif año or mes_num:
        confianza, requiere_revision = 60, False
    else:
        confianza, requiere_revision = 40, True
    return {
        'nit': '',
        'proveedor': 'INVERSIONES EURO S.A',
        'consecutivo': consecutivo,
        'fecha_documento': date(año, mes_num, 1) if (año and mes_num) else None,
        'tipo_documento': tipo_documento,
        'valor': None,
        'medio_pago': '',
        'confianza': confianza,
        'normalizado': bool(consecutivo),
        'requiere_revision': requiere_revision,
        'mismatch_consecutivo': False,
        'mismatch_bloquea': False,
        'ocr_consecutivo_original': '',
        'datos_pel': {
            año_key: año,
            mes_key: mes_num,
            'asunto_saia': consecutivo,
            'identidad_documental': consecutivo,
        },
        'observaciones_extraccion': f'{banco_label}: año={año}, mes={mes_num}',
    }


def _extract_correval_metadata(text, filename, filename_metadata, ruta_archivo=''):
    return _make_conciliacion_metadata(
        text, filename, 'DOCUMENTO_CORREVAL', 'correval_año', 'correval_mes_num', 'Correval',
    )


def _extract_corficolombiana_year_folder(ruta_archivo):
    """Retorna el nombre de la carpeta padre si es un año de 4 digitos.
    Estructura en disco: .../FIDUCIARIA CORFICOLOMBIANA/<año>/<mes>.pdf —
    el año vive en el nombre de esa carpeta, no en el contenido del PDF."""
    if not ruta_archivo:
        return ''
    try:
        from pathlib import PurePosixPath, PureWindowsPath
        ruta_text = str(ruta_archivo)
        parent = PureWindowsPath(ruta_text).parent.name or PurePosixPath(ruta_text).parent.name
        parent = parent.strip()
    except Exception:
        return ''
    return parent if _extract_year_from_text(parent) else ''


def _extract_corficolombiana_metadata(text, filename, filename_metadata, ruta_archivo=''):
    from migracion_masiva_archivo.services.saia.bancolombia_classifier import extract_bancolombia_period

    text_upper = str(text or '').upper()
    year_folder = _extract_corficolombiana_year_folder(ruta_archivo)
    path_year = _extract_year_from_text(year_folder) or _extract_year_from_text(ruta_archivo)
    text_year, mes_num = extract_bancolombia_period(text)
    content_month_num = mes_num
    filename_month_num = None

    stem = os.path.splitext(os.path.basename(filename))[0].strip() if filename else ''
    if filename:
        _, filename_month_num = extract_bancolombia_period(stem)
        if mes_num is None:
            mes_num = filename_month_num

    # El año de la carpeta es mas confiable que el del PDF (estructura organizada
    # manualmente por contador); el texto del PDF solo se usa como respaldo/cruce.
    year = path_year or text_year
    consecutivo = stem or ''
    title_ok = bool(re.search(r'\bCORFICOLOMBIANA\b', text_upper) or re.search(r'\bFIDUCIARIA\b', text_upper))
    inconsistencias = []

    if path_year and text_year and path_year != text_year:
        inconsistencias.append(f'anio carpeta {path_year} no coincide con anio PDF {text_year}')
    if filename_month_num and content_month_num and filename_month_num != content_month_num:
        inconsistencias.append(
            f'mes nombre {_MESES_POR_NUM.get(filename_month_num, filename_month_num)} '
            f'no coincide con mes PDF {_MESES_POR_NUM.get(content_month_num, content_month_num)}'
        )
    if not title_ok:
        inconsistencias.append('PDF no confirma titulo FIDUCIARIA CORFICOLOMBIANA')

    if title_ok and year and mes_num and not inconsistencias:
        confianza, requiere_revision = 95, False
    elif year or mes_num or title_ok:
        confianza, requiere_revision = 70, True
    else:
        confianza, requiere_revision = 40, True

    return {
        'nit': '',
        'proveedor': 'INVERSIONES EURO S.A',
        'consecutivo': consecutivo,
        'fecha_documento': date(year, mes_num, 1) if (year and mes_num) else None,
        'tipo_documento': 'DOCUMENTO_CORFICOLOMBIANA',
        'valor': None,
        'medio_pago': '',
        'confianza': confianza,
        'normalizado': bool(consecutivo and year and mes_num),
        'requiere_revision': requiere_revision,
        'mismatch_consecutivo': False,
        'mismatch_bloquea': False,
        'ocr_consecutivo_original': '',
        'datos_pel': {
            'corficolombiana_año': year,
            'corficolombiana_año_carpeta': path_year,
            'corficolombiana_año_pdf': text_year,
            'corficolombiana_mes_num': mes_num,
            'corficolombiana_mes_num_nombre': filename_month_num,
            'corficolombiana_mes_num_pdf': content_month_num,
            'corficolombiana_mes': _MESES_POR_NUM.get(mes_num, ''),
            'corficolombiana_titulo_ok': title_ok,
            'corficolombiana_inconsistencias': inconsistencias,
            'asunto_saia': consecutivo,
            'identidad_documental': f'CORFICOLOMBIANA-{year}-{consecutivo}' if year else consecutivo,
        },
        'observaciones_extraccion': (
            f'Corficolombiana: anio={year}, mes={mes_num}, titulo_ok={title_ok}'
        ),
    }


def _extract_bbva_metadata(text, filename, filename_metadata, ruta_archivo=''):
    from migracion_masiva_archivo.services.saia.bancolombia_classifier import extract_bancolombia_period

    text_upper = str(text or '').upper()
    subexpediente = _extract_bbva_subexpediente_from_path(ruta_archivo)
    path_year = _extract_year_from_text(subexpediente)
    text_year, mes_num = extract_bancolombia_period(text)
    content_month_num = mes_num
    filename_month_num = None

    if mes_num is None and filename:
        stem_text = os.path.splitext(os.path.basename(filename))[0]
        _, filename_month_num = extract_bancolombia_period(stem_text)
        mes_num = filename_month_num
    elif filename:
        stem_text = os.path.splitext(os.path.basename(filename))[0]
        _, filename_month_num = extract_bancolombia_period(stem_text)

    year = path_year or text_year
    stem = os.path.splitext(os.path.basename(filename))[0].strip() if filename else ''
    consecutivo = stem or subexpediente or ''
    title_ok = bool(re.search(r'\bCONCILIACI[OÓ]N\s+BANCARIA\b', text_upper))
    bank_ok = bool(re.search(r'\b(?:BANCO\s+)?BBVA\b', text_upper))
    inconsistencias = []

    if path_year and text_year and path_year != text_year:
        inconsistencias.append(f'anio carpeta {path_year} no coincide con anio PDF {text_year}')
    if filename_month_num and content_month_num and filename_month_num != content_month_num:
        inconsistencias.append(
            f'mes nombre {_MESES_POR_NUM.get(filename_month_num, filename_month_num)} '
            f'no coincide con mes PDF {_MESES_POR_NUM.get(content_month_num, content_month_num)}'
        )
    if not title_ok:
        inconsistencias.append('PDF no confirma titulo CONCILIACION BANCARIA')
    if not bank_ok:
        inconsistencias.append('PDF no confirma BANCO BBVA')

    if subexpediente and year and mes_num and not inconsistencias:
        confianza, requiere_revision = 95, False
    elif subexpediente and (year or mes_num):
        confianza, requiere_revision = 70, True
    else:
        confianza, requiere_revision = 40, True

    return {
        'nit': '',
        'proveedor': 'INVERSIONES EURO S.A',
        'consecutivo': consecutivo,
        'fecha_documento': date(year, mes_num, 1) if (year and mes_num) else None,
        'tipo_documento': 'DOCUMENTO_BBVA',
        'valor': None,
        'medio_pago': '',
        'confianza': confianza,
        'normalizado': bool(subexpediente and consecutivo and year and mes_num),
        'requiere_revision': requiere_revision,
        'mismatch_consecutivo': False,
        'mismatch_bloquea': False,
        'ocr_consecutivo_original': '',
        'datos_pel': {
            'bbva_subexpediente': subexpediente or '',
            'bbva_a\u00f1o': year,
            'bbva_a\u00f1o_carpeta': path_year,
            'bbva_a\u00f1o_pdf': text_year,
            'bbva_mes_num': mes_num,
            'bbva_mes_num_nombre': filename_month_num,
            'bbva_mes_num_pdf': content_month_num,
            'bbva_mes': _MESES_POR_NUM.get(mes_num, ''),
            'bbva_titulo_ok': title_ok,
            'bbva_banco_ok': bank_ok,
            'bbva_inconsistencias': inconsistencias,
            'asunto_saia': consecutivo,
            'identidad_documental': f'BBVA-{subexpediente}-{consecutivo}' if subexpediente else consecutivo,
        },
        'observaciones_extraccion': (
            f'BBVA: subexpediente={subexpediente or "N/A"}, anio={year}, mes={mes_num}'
        ),
    }


def _extract_bbva_subexpediente_from_path(ruta_archivo):
    if not ruta_archivo:
        return ''
    try:
        from pathlib import PurePosixPath, PureWindowsPath
        ruta_text = str(ruta_archivo)
        parent = PureWindowsPath(ruta_text).parent.name or PurePosixPath(ruta_text).parent.name
        parent = parent.strip()
    except Exception:
        return ''
    parent_upper = parent.upper()
    month_in_parent = any(month in parent_upper for month in _CC_MESES_NUM)
    if ('CONCILIACIONES BANCARIAS' in parent_upper or month_in_parent) and _extract_year_from_text(parent):
        return parent
    return ''


def _extract_year_from_text(value):
    match = re.search(r'\b(20\d{2})\b', str(value or ''))
    return int(match.group(1)) if match else None


def _extract_years_from_text(value):
    return [int(item) for item in re.findall(r'\b(20\d{2})\b', str(value or ''))]


def _extract_davivienda_metadata(text, filename, filename_metadata, ruta_archivo=''):
    from migracion_masiva_archivo.services.saia.bancolombia_classifier import extract_bancolombia_period

    text_upper = str(text or '').upper()
    subexpediente = _extract_davivienda_subexpediente_from_path(ruta_archivo)
    path_year = _extract_year_from_text(subexpediente)
    text_year, mes_num = extract_bancolombia_period(text)
    content_month_num = mes_num
    filename_month_num = None

    if mes_num is None and filename:
        stem_text = os.path.splitext(os.path.basename(filename))[0]
        _, filename_month_num = extract_bancolombia_period(stem_text)
        mes_num = filename_month_num
    elif filename:
        stem_text = os.path.splitext(os.path.basename(filename))[0]
        _, filename_month_num = extract_bancolombia_period(stem_text)

    year = path_year or text_year
    stem = os.path.splitext(os.path.basename(filename))[0].strip() if filename else ''
    consecutivo = stem or subexpediente or ''
    title_ok = bool(re.search(r'\bCONCILIACI[OÃ“]N\s+BANCARIA\b', text_upper))
    bank_ok = bool(re.search(r'\b(?:BANCO\s+)?DAVIVIENDA\b', text_upper))
    inconsistencias = []

    if path_year and text_year and path_year != text_year:
        inconsistencias.append(f'anio carpeta {path_year} no coincide con anio PDF {text_year}')
    if filename_month_num and content_month_num and filename_month_num != content_month_num:
        inconsistencias.append(
            f'mes nombre {_MESES_POR_NUM.get(filename_month_num, filename_month_num)} '
            f'no coincide con mes PDF {_MESES_POR_NUM.get(content_month_num, content_month_num)}'
        )
    if not title_ok:
        inconsistencias.append('PDF no confirma titulo CONCILIACION BANCARIA')
    if not bank_ok:
        inconsistencias.append('PDF no confirma BANCO DAVIVIENDA')

    if subexpediente and year and mes_num and not inconsistencias:
        confianza, requiere_revision = 95, False
    elif subexpediente and (year or mes_num):
        confianza, requiere_revision = 70, True
    else:
        confianza, requiere_revision = 40, True

    return {
        'nit': '',
        'proveedor': 'INVERSIONES EURO S.A',
        'consecutivo': consecutivo,
        'fecha_documento': date(year, mes_num, 1) if (year and mes_num) else None,
        'tipo_documento': 'DOCUMENTO_DAVIVIENDA',
        'valor': None,
        'medio_pago': '',
        'confianza': confianza,
        'normalizado': bool(subexpediente and consecutivo and year and mes_num),
        'requiere_revision': requiere_revision,
        'mismatch_consecutivo': False,
        'mismatch_bloquea': False,
        'ocr_consecutivo_original': '',
        'datos_pel': {
            'davivienda_subexpediente': subexpediente or '',
            'davivienda_a\u00f1o': year,
            'davivienda_a\u00f1o_carpeta': path_year,
            'davivienda_a\u00f1o_pdf': text_year,
            'davivienda_mes_num': mes_num,
            'davivienda_mes_num_nombre': filename_month_num,
            'davivienda_mes_num_pdf': content_month_num,
            'davivienda_mes': _MESES_POR_NUM.get(mes_num, ''),
            'davivienda_titulo_ok': title_ok,
            'davivienda_banco_ok': bank_ok,
            'davivienda_inconsistencias': inconsistencias,
            'asunto_saia': consecutivo,
            'identidad_documental': f'DAVIVIENDA-{subexpediente}-{consecutivo}' if subexpediente else consecutivo,
        },
        'observaciones_extraccion': (
            f'Davivienda: subexpediente={subexpediente or "N/A"}, anio={year}, mes={mes_num}'
        ),
    }


def _extract_davivienda_subexpediente_from_path(ruta_archivo):
    if not ruta_archivo:
        return ''
    try:
        from pathlib import PurePosixPath, PureWindowsPath
        ruta_text = str(ruta_archivo)
        parent = PureWindowsPath(ruta_text).parent.name or PurePosixPath(ruta_text).parent.name
        parent = parent.strip()
    except Exception:
        return ''
    parent_upper = parent.upper()
    month_in_parent = any(month in parent_upper for month in _CC_MESES_NUM)
    is_davivienda_folder = (
        'CONCILIACION BANCARIA' in parent_upper
        or 'CONCILIACIONES BANCARIAS' in parent_upper
        or 'DAVIVIENDA' in parent_upper
        or month_in_parent
    )
    if is_davivienda_folder and _extract_year_from_text(parent):
        return parent
    return ''


def _extract_bogota_metadata(text, filename, filename_metadata, ruta_archivo=''):
    from migracion_masiva_archivo.services.saia.bancolombia_classifier import extract_bancolombia_period

    text_upper = str(text or '').upper()
    subexpediente = _extract_bogota_subexpediente_from_path(ruta_archivo)
    path_years = _extract_years_from_text(subexpediente)
    text_year, mes_num = extract_bancolombia_period(text)
    content_month_num = mes_num
    filename_month_num = None

    if mes_num is None and filename:
        stem_text = os.path.splitext(os.path.basename(filename))[0]
        _, filename_month_num = extract_bancolombia_period(stem_text)
        mes_num = filename_month_num
    elif filename:
        stem_text = os.path.splitext(os.path.basename(filename))[0]
        _, filename_month_num = extract_bancolombia_period(stem_text)

    if text_year:
        year = text_year
    elif path_years:
        year = path_years[-1]
    else:
        year = None

    stem = os.path.splitext(os.path.basename(filename))[0].strip() if filename else ''
    consecutivo = stem or subexpediente or ''
    title_ok = bool(
        re.search(r'\bCONCILIACION\s+BANCARIA\b', text_upper)
        or re.search(r'\bCREDITO\s+ROTATIVO\b', text_upper)
    )
    bank_ok = bool(re.search(r'\b(?:BANCO\s+(?:DE\s+)?)?BOGOTA\b', text_upper))
    inconsistencias = []

    if path_years and text_year and text_year not in path_years:
        years_label = ', '.join(str(item) for item in path_years)
        inconsistencias.append(f'anio carpeta {years_label} no coincide con anio PDF {text_year}')
    if filename_month_num and content_month_num and filename_month_num != content_month_num:
        inconsistencias.append(
            f'mes nombre {_MESES_POR_NUM.get(filename_month_num, filename_month_num)} '
            f'no coincide con mes PDF {_MESES_POR_NUM.get(content_month_num, content_month_num)}'
        )
    if not title_ok:
        inconsistencias.append('PDF no confirma titulo CONCILIACION BANCARIA o CREDITO ROTATIVO')
    if not bank_ok:
        inconsistencias.append('PDF no confirma BANCO DE BOGOTA')

    if subexpediente and year and mes_num and not inconsistencias:
        confianza, requiere_revision = 95, False
    elif subexpediente and (year or mes_num):
        confianza, requiere_revision = 70, True
    else:
        confianza, requiere_revision = 40, True

    return {
        'nit': '',
        'proveedor': 'INVERSIONES EURO S.A',
        'consecutivo': consecutivo,
        'fecha_documento': date(year, mes_num, 1) if (year and mes_num) else None,
        'tipo_documento': 'DOCUMENTO_BOGOTA',
        'valor': None,
        'medio_pago': '',
        'confianza': confianza,
        'normalizado': bool(subexpediente and consecutivo and year and mes_num),
        'requiere_revision': requiere_revision,
        'mismatch_consecutivo': False,
        'mismatch_bloquea': False,
        'ocr_consecutivo_original': '',
        'datos_pel': {
            'bogota_subexpediente': subexpediente or '',
            'bogota_a\u00f1o': year,
            'bogota_a\u00f1os_carpeta': path_years,
            'bogota_a\u00f1o_carpeta': path_years[-1] if path_years else None,
            'bogota_a\u00f1o_pdf': text_year,
            'bogota_mes_num': mes_num,
            'bogota_mes_num_nombre': filename_month_num,
            'bogota_mes_num_pdf': content_month_num,
            'bogota_mes': _MESES_POR_NUM.get(mes_num, ''),
            'bogota_titulo_ok': title_ok,
            'bogota_banco_ok': bank_ok,
            'bogota_inconsistencias': inconsistencias,
            'asunto_saia': consecutivo,
            'identidad_documental': f'BOGOTA-{subexpediente}-{consecutivo}' if subexpediente else consecutivo,
        },
        'observaciones_extraccion': (
            f'Banco de Bogota: subexpediente={subexpediente or "N/A"}, anio={year}, mes={mes_num}'
        ),
    }


def _extract_bogota_subexpediente_from_path(ruta_archivo):
    if not ruta_archivo:
        return ''
    try:
        from pathlib import PurePosixPath, PureWindowsPath
        ruta_text = str(ruta_archivo)
        parent = PureWindowsPath(ruta_text).parent.name or PurePosixPath(ruta_text).parent.name
        parent = parent.strip()
    except Exception:
        return ''
    parent_upper = normalize_text(parent)
    month_in_parent = any(month in parent_upper for month in _CC_MESES_NUM)
    is_bogota_folder = (
        'CONCILIACION BANCARIA' in parent_upper
        or 'CONCILIACIONES BANCARIAS' in parent_upper
        or 'CREDITO ROTATIVO' in parent_upper
        or 'BOGOTA' in parent_upper
        or month_in_parent
    )
    if is_bogota_folder and _extract_year_from_text(parent):
        return parent
    return ''


def _extract_bancolombia_metadata(text, filename, filename_metadata, ruta_archivo=''):
    from migracion_masiva_archivo.services.saia.bancolombia_classifier import (
        classify_bancolombia_subexpediente,
        classify_from_path,
        extract_bancolombia_period,
    )

    # Path-based classification is primary: disk folder names equal SAIA sub-expediente labels.
    path_subexp, path_year = classify_from_path(ruta_archivo)

    # Month must come from the PDF text / filename stem (each file = one month).
    text_year, mes_num = extract_bancolombia_period(text)
    if mes_num is None and filename:
        stem_text = os.path.splitext(os.path.basename(filename))[0]
        _, mes_num = extract_bancolombia_period(stem_text)

    if path_subexp is not None:
        subexpediente = path_subexp
        año = path_year or text_year
        source = 'path'
    else:
        # Fall back to content-based classification
        subexpediente, content_year, content_month = classify_bancolombia_subexpediente(text, filename)
        año = content_year
        if mes_num is None:
            mes_num = content_month
        source = 'content'

    # Páginas de continuación (-2, -3) pueden no tener el año en su texto.
    # Inferirlo desde el nombre del sub-expediente (ej. "CONCILIACION BANCARIA 2016" → 2016).
    if año is None and subexpediente:
        import re as _re_bco
        _m = _re_bco.search(r'\b(20\d{2})\b', subexpediente)
        if _m:
            año = int(_m.group(1))

    stem = os.path.splitext(os.path.basename(filename))[0].strip() if filename else ''
    consecutivo = stem or subexpediente or ''

    confianza = 95 if source == 'path' else (90 if subexpediente else 60)

    return {
        'nit': '',
        'proveedor': 'INVERSIONES EURO S.A',
        'consecutivo': consecutivo,
        'fecha_documento': date(año, mes_num, 1) if (año and mes_num) else None,
        'tipo_documento': 'DOCUMENTO_BANCOLOMBIA',
        'valor': None,
        'medio_pago': '',
        'confianza': confianza,
        'normalizado': bool(consecutivo),
        'requiere_revision': not bool(subexpediente),
        'mismatch_consecutivo': False,
        'mismatch_bloquea': False,
        'ocr_consecutivo_original': '',
        'datos_pel': {
            'bancolombia_subexpediente': subexpediente or '',
            'bancolombia_año': año,
            'bancolombia_mes_num': mes_num,
            'asunto_saia': consecutivo,
            'identidad_documental': consecutivo,
        },
        'observaciones_extraccion': (
            f'Bancolombia [{source}]: subexpediente={subexpediente or "N/A"}, año={año}, mes={mes_num}'
        ),
    }


def extract_metadata_from_text(text, filename='', ruta_archivo=''):
    normalized_text = normalize_text(text)
    filename_metadata = extraer_metadata_nombre_archivo(filename)
    document_identifier = filename_metadata.get('tipo_documento_nombre') or 'PEL'

    if _is_retencion_ica_path(ruta_archivo):
        return _extract_retencion_ica_metadata(
            normalized_text, filename, filename_metadata, ruta_archivo,
        )

    if (
        document_identifier in _IMPUESTO_CONSUMO_CODES
        or _is_impuesto_consumo_path(ruta_archivo)
        or _looks_like_impuesto_consumo_content(normalized_text)
    ):
        # El titulo del recibo DIAN manda cuando esta presente (incluso en un PDF
        # combinado que tambien incluya el auxiliar contable). Sin ese titulo, si
        # el contenido es el auxiliar contable, es el septimo expediente anual
        # ("IMPUESTO AL CONSUMO2014"), no uno de los 6 recibos bimestrales.
        if not _IMPUESTO_CONSUMO_TITLE_RE.search(normalized_text) and _is_impuesto_consumo_ledger(normalized_text):
            return _extract_impuesto_consumo_anual_metadata(
                normalized_text, filename, filename_metadata, ruta_archivo,
            )
        return _extract_impuesto_consumo_metadata(
            normalized_text, filename, filename_metadata, ruta_archivo,
        )

    if document_identifier == 'INC' or _is_inc_path(ruta_archivo):
        return _extract_inc_metadata(
            normalized_text, filename, filename_metadata, ruta_archivo,
        )

    if document_identifier == 'IND' or _is_ind_path(ruta_archivo):
        return _extract_ind_metadata(
            normalized_text, filename, filename_metadata, ruta_archivo,
        )

    if _is_ecb_path(ruta_archivo) or document_identifier == 'ECB':
        return _extract_ecb_metadata(
            normalized_text, filename, filename_metadata, ruta_archivo,
        )

    if _is_egc_path(ruta_archivo) or document_identifier == 'EGC':
        return _extract_egc_metadata(
            normalized_text, filename, filename_metadata, ruta_archivo,
        )

    if _is_ege_path(ruta_archivo) or document_identifier == 'EGE':
        return _extract_ege_metadata(
            normalized_text, filename, filename_metadata, ruta_archivo,
        )

    if document_identifier in ('CARTERA_COLECTIVA', 'CCA', 'CCV'):
        return _extract_cartera_colectiva_metadata(
            normalized_text, filename, filename_metadata, ruta_archivo,
        )

    ruta_upper = normalize_text(ruta_archivo)
    if 'BBVA' in ruta_upper:
        return _extract_bbva_metadata(
            normalized_text, filename, filename_metadata, ruta_archivo,
        )
    if 'DAVIVIENDA' in ruta_upper:
        return _extract_davivienda_metadata(
            normalized_text, filename, filename_metadata, ruta_archivo,
        )
    if 'BOGOTA' in ruta_upper:
        return _extract_bogota_metadata(
            normalized_text, filename, filename_metadata, ruta_archivo,
        )

    if document_identifier == 'BANCOLOMBIA':
        if 'CORBANCA' in ruta_upper or 'CORPBANCA' in ruta_upper:
            return _extract_corbanca_metadata(
                normalized_text, filename, filename_metadata, ruta_archivo,
            )
        if 'COLPATRIA' in ruta_upper:
            return _extract_colpatria_metadata(
                normalized_text, filename, filename_metadata, ruta_archivo,
            )
        if 'CORREVAL' in ruta_upper:
            return _extract_correval_metadata(
                normalized_text, filename, filename_metadata, ruta_archivo,
            )
        if 'CORFICOLOMBIANA' in ruta_upper:
            return _extract_corficolombiana_metadata(
                normalized_text, filename, filename_metadata, ruta_archivo,
            )
        if 'BBVA' in ruta_upper:
            return _extract_bbva_metadata(
                normalized_text, filename, filename_metadata, ruta_archivo,
            )
        if 'DAVIVIENDA' in ruta_upper:
            return _extract_davivienda_metadata(
                normalized_text, filename, filename_metadata, ruta_archivo,
            )
        if 'BOGOTA' in ruta_upper:
            return _extract_bogota_metadata(
                normalized_text, filename, filename_metadata, ruta_archivo,
            )
        return _extract_bancolombia_metadata(
            normalized_text, filename, filename_metadata, ruta_archivo,
        )

    has_header = bool(MAIN_HEADER_RE.search(normalized_text))
    has_provider = bool(PROVIDER_RE.search(normalized_text))
    consecutivo = extract_document_consecutivo(normalized_text, document_identifier)
    if document_identifier in FILENAME_IDENTITY_DOCUMENTS and not consecutivo:
        consecutivo = _consecutivo_from_filename(filename_metadata, document_identifier)

    expected_pel = filename_metadata.get('pel_base_nombre')
    consecutive_matches_filename = True
    if consecutivo and expected_pel:
        consecutive_matches_filename = consecutivo.endswith(str(expected_pel).zfill(8))

    es_factura_principal = bool(has_header and consecutivo) if document_identifier == 'PEL' else False
    if not es_factura_principal:
        _subparte = filename_metadata.get('subparte_nombre') or None
        _tomo = filename_metadata.get('tomo_nombre') or None
        _parte = filename_metadata.get('parte_nombre') or None
        if _subparte is not None and int(_subparte) == 1:
            es_factura_principal = True
        elif _tomo is not None and _parte is not None and int(_tomo) == 1 and int(_parte) == 1:
            es_factura_principal = True
    has_filename_identity = bool(filename_metadata.get('identidad_documental'))
    support_identity_from_filename = _is_filename_identified_support(
        filename_metadata,
        es_factura_principal,
    )
    if support_identity_from_filename:
        consecutivo = _consecutivo_from_filename(filename_metadata, document_identifier)
        consecutive_matches_filename = True

    # Resolución de discrepancia: cuando OCR y nombre no coinciden, el nombre es fuente de verdad
    _mismatch_bloquea = False
    _mismatch_observacion = ''
    _ocr_consecutivo_original = ''
    if not consecutive_matches_filename and consecutivo and expected_pel:
        _ocr_num = _extraer_numero_consecutivo(consecutivo)
        _filename_num = int(expected_pel)
        if _es_transposicion_digitos(_ocr_num, _filename_num):
            _mismatch_observacion = (
                f'Transposicion de digitos corregida: OCR={_ocr_num}, '
                f'nombre={_filename_num}. Se almacena el valor del nombre de archivo.'
            )
            consecutivo = _consecutivo_from_filename(filename_metadata, document_identifier)
            consecutive_matches_filename = True
        elif _es_digito_insertado(_ocr_num, _filename_num):
            _mismatch_observacion = (
                f'Digito extra detectado en OCR: OCR={_ocr_num}, nombre={_filename_num}. '
                f'Corregido automaticamente tomando el nombre del archivo como fuente de verdad.'
            )
            consecutivo = _consecutivo_from_filename(filename_metadata, document_identifier)
            consecutive_matches_filename = True
        else:
            _ocr_consecutivo_original = consecutivo
            _delta = _diferencia_numerica(_ocr_num, _filename_num)
            consecutivo = _consecutivo_from_filename(filename_metadata, document_identifier)
            consecutive_matches_filename = True
            _mismatch_bloquea = True
            _mismatch_observacion = (
                f'Discrepancia consecutivo: OCR={_ocr_num} vs nombre={_filename_num} '
                f'(diferencia={int(_delta)}). Verificar si el archivo esta mal nombrado o si el OCR fallo.'
            )

    observations = build_observations(
        filename_metadata=filename_metadata,
        es_factura_principal=es_factura_principal,
        has_header=has_header,
        has_provider=has_provider,
        consecutivo=consecutivo,
        consecutive_matches_filename=consecutive_matches_filename,
        has_filename_identity=has_filename_identity,
    )
    if _mismatch_observacion:
        observations.append(_mismatch_observacion)
    confidence = calculate_pel_confidence(
        has_header=has_header,
        consecutivo=consecutivo,
        consecutive_matches_filename=consecutive_matches_filename,
        has_filename_identity=has_filename_identity,
        es_factura_principal=es_factura_principal,
        document_identifier=document_identifier,
    )
    consecutive_mismatch_blocks = (
        not consecutive_matches_filename
        and confidence < 90
        and not has_filename_identity
    )
    if support_identity_from_filename:
        requires_review = False
    else:
        requires_review = (
            not has_filename_identity
            or confidence < 75
            or consecutive_mismatch_blocks
            or _mismatch_bloquea
        )

    return {
        'nit': '',
        'proveedor': 'INVERSIONES EURO S.A' if has_provider else '',
        'consecutivo': consecutivo,
        'fecha_documento': None,
        'tipo_documento': _build_tipo_documento(document_identifier, es_factura_principal),
        'valor': None,
        'medio_pago': '',
        'confianza': confidence,
        'normalizado': bool(consecutivo),
        'requiere_revision': requires_review,
        'mismatch_consecutivo': bool(consecutivo and expected_pel and not consecutive_matches_filename),
        'mismatch_bloquea': _mismatch_bloquea,
        'ocr_consecutivo_original': _ocr_consecutivo_original,
        'datos_pel': build_datos_pel(
            filename_metadata=filename_metadata,
            es_factura_principal=es_factura_principal,
            consecutivo=consecutivo,
        ),
        'observaciones_extraccion': '; '.join(observations),
    }


def extract_may_pel_consecutivo(text):
    return extract_document_consecutivo(text, 'PEL')


def extract_document_consecutivo(text, identifier='PEL'):
    code = str(identifier or 'PEL').upper()
    normalized = _normalize_for_consecutivo(text)
    pattern = re.compile(
        rf'\b(?:MAY\s*[._ \-]?\s*{code}|MAY{code}|{code})'
        r'[\s._ \-:#]*'
        r'0*([0-9OolISBG]{4,8})\b',
        re.IGNORECASE,
    )
    match = pattern.search(normalized)
    if not match:
        return ''
    return normalize_may_identifier(_clean_ocr_digits(match.group(1)), code)


def _normalize_for_consecutivo(text):
    # Colapsa "P E L" → "PEL" (OCR inserta espacios entre letras del prefijo)
    text = _PEL_SPACED_RE.sub('PEL', text)
    text = _PRO_SPACED_RE.sub('PRO', text)
    text = _RCG_SPACED_RE.sub('RCG', text)
    text = _RCI_SPACED_RE.sub('RCI', text)
    text = _RCP_SPACED_RE.sub('RCP', text)
    text = _ECB_SPACED_RE.sub('ECB', text)
    text = _EGC_SPACED_RE.sub('EGC', text)
    text = _ECG_SPACED_RE.sub('ECG', text)
    # Normaliza guiones tipográficos y sustituciones de letra E frecuentes en OCR
    text = text.replace('—', '-').replace('–', '-')
    text = text.replace('€', 'E').replace('\xca', 'E').replace('\xc8', 'E')
    # Colapsa espacios dentro de secuencias de dígitos: "975 74" → "97574"
    # Itera hasta 4 veces para cubrir "9 7 5 7 4" en múltiples pasadas
    for _ in range(4):
        text, changed = _DIGIT_SPACE_RE.subn(r'\1\2', text)
        if not changed:
            break
    return text


def _clean_ocr_digits(raw):
    # Convierte caracteres OCR al dígito correcto dentro del número capturado
    return raw.translate(_OCR_DIGIT_TABLE)


def normalize_may_pel(value):
    return normalize_may_identifier(value, 'PEL')


def normalize_may_identifier(value, identifier='PEL'):
    code = str(identifier or 'PEL').upper()
    text = normalize_text(value)
    match = re.search(rf'(?:MAY\s*[- ]?\s*{code}|MAY{code}|{code})?\s*[- ]?0*(\d{{4,8}})', text)
    if not match:
        return normalize_consecutivo(value)
    return f'MAY-{code}-{int(match.group(1)):08d}'


def _consecutivo_from_filename(filename_metadata, identifier):
    if str(identifier or '').upper() == 'BANCOLOMBIA':
        return filename_metadata.get('asunto_documental') or filename_metadata.get('identidad_documental') or ''
    base = filename_metadata.get('documento_base_nombre') or filename_metadata.get('pel_base_nombre')
    if not base:
        return ''
    return f'MAY-{identifier}-{int(base):08d}'


def _build_tipo_documento(document_identifier, es_factura_principal):
    if document_identifier == 'PRO':
        return 'DOCUMENTO_PRO_PRINCIPAL' if es_factura_principal else 'DOCUMENTO_PRO'
    if document_identifier == 'PEL':
        return 'FACTURA_PRINCIPAL_PEL' if es_factura_principal else 'SOPORTE_PEL'
    if document_identifier in ('CCA', 'CCV', 'CARTERA_COLECTIVA'):
        return f'DOCUMENTO_{document_identifier}'
    return f'DOCUMENTO_{document_identifier}' if document_identifier else ''


def _is_filename_identified_support(filename_metadata, es_factura_principal):
    if es_factura_principal:
        return False
    if not filename_metadata.get('identidad_documental'):
        return False
    tipo_nombre = str(filename_metadata.get('tipo_nombre') or '').upper()
    return tipo_nombre.endswith('_SUBPARTE') or tipo_nombre.endswith('_TOMO')



def calculate_pel_confidence(
    has_header,
    consecutivo,
    consecutive_matches_filename,
    has_filename_identity,
    es_factura_principal,
    document_identifier='PEL',
):
    confidence = 0
    confidence += 35 if has_header or document_identifier in {'PRO', 'RCG', 'RCI', 'RCP', 'BANCOLOMBIA', 'CCA', 'CCV'} else 0
    confidence += 40 if consecutivo else 0
    confidence += 15 if consecutive_matches_filename else 0
    # Piso alto: filename + encabezado confirman identidad sin ambigüedad
    if document_identifier in {'PRO', 'RCG', 'RCI', 'RCP', 'BANCOLOMBIA', 'CCA', 'CCV'} and has_filename_identity:
        confidence = max(confidence, 90)
    elif has_filename_identity and has_header:
        confidence = max(confidence, 85)
    # Piso medio: documentos soporte con identidad PEL en nombre (sin encabezado propio)
    elif has_filename_identity:
        confidence = max(confidence, 80)
    return min(confidence, 100)


def build_observations(
    filename_metadata,
    es_factura_principal,
    has_header,
    has_provider,
    consecutivo,
    consecutive_matches_filename,
    has_filename_identity=False,
):
    observations = [f'es_factura_principal={es_factura_principal}']
    for key in [
        'tipo_documento_nombre',
        'identidad_documental',
        'pel_base_nombre',
        'pro_base_nombre',
        'rcg_base_nombre',
        'rci_base_nombre',
        'rcp_base_nombre',
        'bancolombia_base_nombre',
        'documento_base_nombre',
        'mes_nombre',
        'asunto_documental',
        'subparte_nombre',
        'tomo_nombre',
        'parte_nombre',
    ]:
        value = filename_metadata.get(key)
        if value not in (None, ''):
            observations.append(f'{key}={value}')

    document_identifier = filename_metadata.get('tipo_documento_nombre') or 'PEL'
    if _is_filename_identified_support(filename_metadata, es_factura_principal):
        observations.append(
            'Soporte identificado por nombre; no requiere encabezado ni consecutivo OCR.'
        )
    if document_identifier == 'PEL' and not has_header and not filename_metadata.get('identidad_documental'):
        observations.append('No se detecto encabezado Pagos electronicos.')
    if document_identifier == 'PEL' and has_header and not has_provider:
        observations.append('Nombre de proveedor no detectado en texto.')
    if document_identifier == 'PEL' and has_header and not consecutivo:
        observations.append('No se detecto consecutivo MAY-PEL.')
    if not consecutive_matches_filename:
        if has_filename_identity:
            observations.append(
                'Consecutivo OCR difiere del nombre de archivo; '
                'el nombre de archivo se toma como fuente autorizada.'
            )
        else:
            observations.append('El consecutivo del documento no coincide con el nombre del archivo.')
    return observations


def build_datos_pel(
    filename_metadata,
    es_factura_principal,
    consecutivo,
):
    return {
        'es_factura_principal': es_factura_principal,
        'tipo_identificador': filename_metadata.get('tipo_documento_nombre') or '',
        'identidad_documental': filename_metadata.get('identidad_documental') or '',
        'pel_base_nombre': filename_metadata.get('pel_base_nombre') or '',
        'pro_base_nombre': filename_metadata.get('pro_base_nombre') or '',
        'rcg_base_nombre': filename_metadata.get('rcg_base_nombre') or '',
        'rci_base_nombre': filename_metadata.get('rci_base_nombre') or '',
        'rcp_base_nombre': filename_metadata.get('rcp_base_nombre') or '',
        'bancolombia_base_nombre': filename_metadata.get('bancolombia_base_nombre') or '',
        'mes_nombre': filename_metadata.get('mes_nombre') or '',
        'asunto_documental': filename_metadata.get('asunto_documental') or '',
        'documento_base_nombre': filename_metadata.get('documento_base_nombre') or filename_metadata.get('pel_base_nombre') or '',
        'subparte_nombre': filename_metadata.get('subparte_nombre') or None,
        'tomo_nombre': filename_metadata.get('tomo_nombre') or None,
        'parte_nombre': filename_metadata.get('parte_nombre') or None,
        'consecutivo': consecutivo or '',
    }


def _extraer_numero_consecutivo(consecutivo_str):
    """Extrae el número entero final de un consecutivo normalizado (e.g. 'MAY-PEL-00097431' → 97431)."""
    if not consecutivo_str:
        return None
    match = re.search(r'(\d+)\s*$', consecutivo_str.strip())
    return int(match.group(1)) if match else None


def _es_transposicion_digitos(ocr_num, filename_num):
    """True si los dígitos de ambos números son los mismos en distinto orden (transposición OCR)."""
    if ocr_num is None or filename_num is None or ocr_num == filename_num:
        return False
    return sorted(str(ocr_num)) == sorted(str(filename_num))


def _diferencia_numerica(ocr_num, filename_num):
    """Diferencia absoluta entre dos números de consecutivo; inf si alguno es None."""
    if ocr_num is None or filename_num is None:
        return float('inf')
    return abs(ocr_num - filename_num)


def _es_digito_insertado(ocr_num, filename_num):
    """True si el OCR leyó exactamente un dígito extra (insertado) respecto al nombre del archivo.

    Verifica que el string del nombre es subsequencia del string del OCR, con
    exactamente un carácter de diferencia de longitud. Ejemplo: OCR=973534,
    nombre=97354 → True (el '3' extra fue insertado por el OCR en la posición 3).
    """
    if ocr_num is None or filename_num is None or ocr_num == filename_num:
        return False
    ocr_str = str(ocr_num)
    fname_str = str(filename_num)
    if len(ocr_str) != len(fname_str) + 1:
        return False
    it = iter(ocr_str)
    return all(c in it for c in fname_str)


def _get_consecutivo_delta_max():
    try:
        return max(int(os.getenv('SAIA_CONSECUTIVO_DELTA_MAX', '50')), 0)
    except (ValueError, TypeError):
        return 50


