"""
Biblioteca de validadores por campo del modelo.
Detecta cuando una columna del Excel contiene valores inesperados para el campo
al que fue mapeada (ej: columna "RH" con fondos de pensión en vez de grupos sanguíneos).
"""
import re
from datetime import datetime

# ── Patrones de referencia ────────────────────────────────────────────────────

_TIPO_SANGRE_RE = re.compile(
    r'^(O|A|B|AB)\s*[+\-]$|^(O|A|B|AB)\s*(POSITIVO|NEGATIVO|POS|NEG)$',
    re.IGNORECASE,
)
_DOCUMENTO_RE = re.compile(r'^\d{5,15}$')
_CELULAR_RE   = re.compile(r'^(\+57)?\d{7,12}$')
_FECHA_FMTS   = ['%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%d/%m/%y', '%Y/%m/%d', '%m/%d/%Y', '%d.%m.%Y']

def _es_fecha(val):
    v = val.strip()
    # Pandas Timestamp: '2018-11-02 00:00:00' o '2018-11-02 00:00:00.000000'
    if re.match(r'^\d{4}-\d{2}-\d{2}(\s\d{2}:\d{2})', v):
        return True
    # Fecha en español con "de": '02 de Mayo de 2019', '2 de febrero de 2020'
    if re.search(r'\d+\s+de\s+\w+', v, re.IGNORECASE):
        return True
    # Fecha en español sin "de" entre día y mes: '01 MARZO DE 2017', '01 marzo 2017'
    if re.match(r'^\d{1,2}\s+[A-ZÀ-ÿa-z]{3,}(\s+DE)?\s+\d{4}$', v, re.IGNORECASE):
        return True
    # Número serial de Excel
    try:
        n = int(float(v))
        if 1000 < n < 100000:
            return True
    except (ValueError, TypeError):
        pass
    # Formatos estándar
    for fmt in _FECHA_FMTS:
        try:
            datetime.strptime(v, fmt)
            return True
        except ValueError:
            continue
    return False


# ── Diccionario de validadores ────────────────────────────────────────────────
# Cada entrada: campo_modelo → {nombre, descripcion, fn (str→bool), umbral (0-1)}
# umbral = fracción mínima de valores válidos para NO alertar
# (si menos del umbral son válidos → se emite advertencia)

_SEXO_RE = re.compile(
    r'^(M|F|H|MASCULINO|FEMENINO|HOMBRE|MUJER|MALE|FEMALE)$',
    re.IGNORECASE,
)

_EMAIL_RE = re.compile(r'^[^\s@]+@[^\s@]+\.[^\s@]+$')

# Tipos de documento colombianos reconocidos
_TIPOS_DOC = {
    'CC', 'C.C.', 'C.C', 'CEDULA', 'CEDULA DE CIUDADANIA',
    'TI', 'T.I.', 'TARJETA DE IDENTIDAD',
    'NIT', 'N.I.T.',
    'CE', 'C.E.', 'CEDULA DE EXTRANJERIA',
    'PA', 'PASAPORTE',
    'RC', 'REGISTRO CIVIL',
    'NUIP', 'PEP',
}

# Estados civiles colombianos reconocidos
_ESTADOS_CIVILES = {
    'SOLTERO', 'SOLTERA', 'CASADO', 'CASADA',
    'UNION LIBRE', 'UNIÓN LIBRE', 'UNION', 'CONVIVIENTE',
    'SEPARADO', 'SEPARADA', 'DIVORCIADO', 'DIVORCIADA',
    'VIUDO', 'VIUDA', 'S', 'C', 'U', 'V', 'D',
}

# Niveles de escolaridad reconocidos
_ESCOLARIDAD = {
    'PRIMARIA', 'BASICA PRIMARIA', 'BACHILLER', 'BACHILLERATO',
    'SECUNDARIA', 'MEDIA', 'TECNICO', 'TÉCNICO', 'TECNOLOGIA',
    'TECNOLOGÍA', 'TECNOLOGO', 'TECNÓLOGO',
    'UNIVERSITARIO', 'PROFESIONAL', 'PREGRADO',
    'ESPECIALIZACION', 'ESPECIALIZACIÓN', 'ESPECIALISTA',
    'MAESTRIA', 'MAESTRÍA', 'MAGISTER', 'MAGÍSTER',
    'DOCTORADO', 'PHD', 'NINGUNO', 'NINGUNA',
}

# ARL colombianas reconocidas
_ARL = {
    'SURA', 'ARL SURA', 'POSITIVA', 'COLMENA', 'LIBERTY',
    'EQUIDAD', 'AXA COLPATRIA', 'COLPATRIA', 'BOLIVAR',
    'SEGUROS BOLIVAR', 'MAPFRE', 'COMPAÑIA SURAMERICANA',
    'SURAMERICANA', 'CHUBB', 'AIG', 'GENERALI',
    'PREVISORA', 'LA PREVISORA', 'SEGUROS DEL ESTADO',
    'ESTADO',
    # Antiguo fondo de riesgos laborales
    'FOSYGA', 'ISS', 'INSTITUTO DE SEGUROS SOCIALES',
}

# strict=True  → conjunto finito conocido; se usa para DETECTAR y como DESTINO de rerouting.
# strict=False → solo detecta valores obviamente incorrectos; NO es destino de rerouting.

VALIDADORES = {
    'sexo': {
        'nombre':     'Sexo / Género',
        'descripcion': (
            'Los valores encontrados no parecen ser géneros '
            '(se esperan: M, F, MASCULINO, FEMENINO, HOMBRE, MUJER). '
            'Puede que la columna contenga estado civil en lugar de género.'
        ),
        'fn':      lambda v: bool(_SEXO_RE.match(v.strip())),
        'umbral':  0.40,
        'strict':  True,
    },
    'tipo_sangre': {
        'nombre':     'Tipo de sangre',
        'descripcion': (
            'Los valores encontrados no parecen ser grupos sanguíneos '
            '(se esperan: O+, A+, B-, AB-, O NEGATIVO, etc.).'
        ),
        'fn':      lambda v: bool(_TIPO_SANGRE_RE.match(v.upper())),
        'umbral':  0.40,
        'strict':  True,
    },
    'documento_id': {
        'nombre':     'Documento / Cédula',
        'descripcion': (
            'Los valores encontrados no parecen ser números de cédula '
            '(se esperan 5–15 dígitos sin letras ni símbolos).'
        ),
        'fn':      lambda v: bool(_DOCUMENTO_RE.match(v.replace('.', '').replace(' ', ''))),
        'umbral':  0.60,
        'strict':  False,
    },
    'celular': {
        'nombre':     'Celular',
        'descripcion': (
            'Los valores encontrados no parecen ser números de celular colombianos '
            '(10 dígitos, con o sin +57).'
        ),
        'fn':      lambda v: bool(_CELULAR_RE.match(v.replace(' ', '').replace('-', ''))),
        'umbral':  0.50,
        'strict':  False,
    },
    'fecha_ingreso': {
        'nombre':     'Fecha de ingreso',
        'descripcion': 'Los valores encontrados no parecen ser fechas válidas.',
        'fn':      _es_fecha,
        'umbral':  0.50,
        'strict':  False,
    },
    'fecha_retiro': {
        'nombre':     'Fecha de retiro',
        'descripcion': 'Los valores encontrados no parecen ser fechas válidas.',
        'fn':      _es_fecha,
        'umbral':  0.50,
        'strict':  False,
    },
    'fecha_nacimiento': {
        'nombre':     'Fecha de nacimiento',
        'descripcion': 'Los valores encontrados no parecen ser fechas válidas.',
        'fn':      _es_fecha,
        'umbral':  0.50,
        'strict':  False,
    },
    'eps': {
        'nombre':     'EPS',
        'descripcion': (
            'Los valores encontrados no parecen ser nombres de EPS '
            '(¿está mapeada la columna correcta?).'
        ),
        'fn':      lambda v: bool(re.match(r'^[A-ZÁÉÍÓÚÑ\s\-\.]{3,}$', v, re.IGNORECASE)) and not _es_fecha(v),
        'umbral':  0.50,
        'strict':  False,
    },
    'pensiones': {
        'nombre':     'Pensiones / AFP',
        'descripcion': 'Los valores encontrados no parecen ser nombres de fondos de pensiones.',
        'fn':      lambda v: bool(re.match(r'^[A-ZÁÉÍÓÚÑ\s\-\.]{3,}$', v, re.IGNORECASE)) and not _es_fecha(v),
        'umbral':  0.50,
        'strict':  False,
    },
    'arl': {
        'nombre':     'ARL',
        'descripcion': (
            'Los valores encontrados no parecen ser nombres de ARL colombianas '
            '(SURA, POSITIVA, COLMENA, LIBERTY, EQUIDAD, etc.).'
        ),
        'fn':      lambda v: v.upper().strip() in _ARL or bool(re.match(r'^[A-ZÁÉÍÓÚÑ\s\-\.\(\)]{3,}$', v, re.IGNORECASE)),
        'umbral':  0.50,
        'strict':  False,
    },
    'tipo_documento': {
        'nombre':     'Tipo de documento',
        'descripcion': (
            'Los valores encontrados no parecen ser tipos de documento colombianos '
            '(CC, TI, NIT, CE, PASAPORTE, RC, etc.).'
        ),
        'fn':      lambda v: v.upper().strip() in _TIPOS_DOC
                             or bool(re.match(r'^(CC|TI|NIT|CE|PA|RC|NUIP|PEP)[\s\.]', v.upper())),
        'umbral':  0.50,
        'strict':  True,
    },
    'estado_civil': {
        'nombre':     'Estado civil',
        'descripcion': (
            'Los valores encontrados no parecen ser estados civiles '
            '(SOLTERO/A, CASADO/A, UNION LIBRE, SEPARADO/A, etc.).'
        ),
        'fn':      lambda v: v.upper().strip() in _ESTADOS_CIVILES,
        'umbral':  0.40,
        'strict':  True,
    },
    'nivel_escolaridad': {
        'strict':  True,
        'nombre':     'Nivel de escolaridad',
        'descripcion': (
            'Los valores encontrados no parecen ser niveles educativos '
            '(BACHILLER, TÉCNICO, UNIVERSITARIO, etc.).'
        ),
        'fn':      lambda v: v.upper().strip() in _ESCOLARIDAD,
        'umbral':  0.35,
    },
    'email': {
        'nombre':     'Correo electrónico',
        'descripcion': (
            'Los valores encontrados no tienen formato de correo electrónico (usuario@dominio.com).'
        ),
        'fn':      lambda v: bool(_EMAIL_RE.match(v.strip())),
        'umbral':  0.50,
        'strict':  True,
    },
    'tipo_proceso': {
        'nombre':     'Tipo de proceso',
        'descripcion': (
            'Los valores encontrados no parecen ser tipos de proceso válidos '
            '(EMPLEADO, RETIRADO, CANDIDATO, APRENDIZ, SELECCIONADO, ENTREVISTADO).'
        ),
        'fn':      lambda v: v.upper().strip() in {
            'EMPLEADO', 'RETIRADO', 'CANDIDATO', 'APRENDIZ',
            'SELECCIONADO', 'ENTREVISTADO', 'ACTIVO', 'INACTIVO',
        },
        'umbral':  0.50,
        'strict':  True,
    },
    'motivo_retiro': {
        'nombre':     'Motivo de retiro',
        'descripcion': (
            'Los valores encontrados parecen ser fechas u otros datos en vez de motivos de retiro.'
        ),
        'fn':      lambda v: not _es_fecha(v) and not v.strip().lstrip('-').isdigit(),
        'umbral':  0.70,
        'strict':  False,
    },
}


def reubicar_valores_erroneos(kwargs):
    """
    Para cada campo con validador strict=True:
    1. Si el valor falla su propio validador, busca otro campo strict=True cuyo fn pase.
    2. Si lo encuentra y ese campo destino está vacío → mueve el valor.
    3. Si no hay destino claro → deja el valor original (sin borrar datos).

    Ejemplos:
      sexo='SOLTERO'       → estado_civil='SOLTERO'   (ambos strict)
      sexo='UNION LIBRE'   → estado_civil='UNION LIBRE'
      estado_civil='MEDELLIN' → ningún strict lo acepta → queda igual
    """
    _STRICT_DESTINOS = {
        campo: config
        for campo, config in VALIDADORES.items()
        if config.get('strict', False)
    }

    for campo_origen, config in VALIDADORES.items():
        if not config.get('strict', False):
            continue  # solo reubicar desde campos estrictos

        valor = str(kwargs.get(campo_origen, '') or '').strip()
        if not valor:
            continue

        try:
            es_valido = config['fn'](valor)
        except Exception:
            continue

        if es_valido:
            continue  # valor correcto → no mover

        # Buscar destino en los otros campos estrictos
        campo_destino = None
        for otro_campo, otro_config in _STRICT_DESTINOS.items():
            if otro_campo == campo_origen:
                continue
            try:
                if otro_config['fn'](valor):
                    campo_destino = otro_campo
                    break
            except Exception:
                continue

        if campo_destino and not kwargs.get(campo_destino):
            kwargs[campo_destino] = kwargs[campo_origen]
            del kwargs[campo_origen]

    return kwargs


def validar_mapeo(df, mapeo):
    """
    Analiza si los valores del DataFrame coinciden con el campo destino del mapeo.

    df     : pandas.DataFrame del Excel (valores como str, vacíos como '')
    mapeo  : {header_excel: campo_modelo}  — el mapeo detectado/confirmado por el usuario

    Retorna lista de advertencias:
      [{
        'campo':          str,   # campo del modelo afectado
        'campo_display':  str,   # nombre legible
        'columna_excel':  str,   # nombre de la columna en el Excel
        'descripcion':    str,   # explicación del problema
        'valores_muestra': list, # hasta 5 valores problemáticos encontrados
        'tasa_validos':   int,   # porcentaje de valores que sí pasaron
      }]
    """
    advertencias = []

    for header, campo in mapeo.items():
        if not campo or campo not in VALIDADORES:
            continue
        if header not in df.columns:
            continue

        validador = VALIDADORES[campo]
        serie = df[header].fillna('').astype(str)
        muestra_no_vacia = [
            v.strip() for v in serie
            if v.strip() and v.strip().lower() not in ('nan', 'none', '')
        ][:100]

        if not muestra_no_vacia:
            continue

        resultados = [validador['fn'](v) for v in muestra_no_vacia]
        tasa = sum(resultados) / len(resultados)

        if tasa < validador['umbral']:
            vals_malos = [v for v, ok in zip(muestra_no_vacia, resultados) if not ok][:5]
            advertencias.append({
                'campo':          campo,
                'campo_display':  validador['nombre'],
                'columna_excel':  header,
                'descripcion':    validador['descripcion'],
                'valores_muestra': vals_malos,
                'tasa_validos':   round(tasa * 100),
            })

    return advertencias
