"""
Mapeo de TODOS los valores encontrados en los Excel reales → código canónico de sede.
Normalización: mayúsculas, sin tildes, sin espacios dobles.
"""
import unicodedata, re


def norm(s):
    """Normaliza: upper, sin tildes, sin espacios extras."""
    if not s:
        return ''
    s = str(s).upper().strip()
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode('ascii')
    s = re.sub(r'\s+', ' ', s).strip()
    return s


# ── Catálogo canónico ─────────────────────────────────────────────────────────
# Códigos = códigos SIESA (c0550_id_co) para consistencia con el módulo Contratos
SEDES_CANONICAS = [
    # Tiendas EURO — área metropolitana Medellín
    {'codigo': 'FRO', 'nombre': 'Euro Frontera',         'ciudad': 'Itagüí'},
    {'codigo': 'MAY', 'nombre': 'Euro Mayorista',        'ciudad': 'Medellín'},
    {'codigo': 'FLO', 'nombre': 'Euro Florida',          'ciudad': 'Medellín'},
    {'codigo': 'LAU', 'nombre': 'Euro Laureles',         'ciudad': 'Medellín'},
    {'codigo': 'LOB', 'nombre': 'Euro Los Bernal',       'ciudad': 'Medellín'},
    {'codigo': 'SAB', 'nombre': 'Euro Sabaneta',         'ciudad': 'Sabaneta'},
    {'codigo': 'GUA', 'nombre': 'Euro Guadalcanal',      'ciudad': 'Medellín'},
    {'codigo': 'VEG', 'nombre': 'Euro Palmas',           'ciudad': 'Medellín'},
    {'codigo': 'NIQ', 'nombre': 'Euro Niquia',           'ciudad': 'Bello'},
    {'codigo': 'ITA', 'nombre': 'Euro Itagüí',           'ciudad': 'Itagüí'},
    {'codigo': 'BAR', 'nombre': 'Euro Barbosa',          'ciudad': 'Barbosa'},
    {'codigo': 'MAR', 'nombre': 'Euro Marinilla',        'ciudad': 'Marinilla'},
    {'codigo': 'BEL', 'nombre': 'Euro Bello',            'ciudad': 'Bello'},
    {'codigo': 'ESC', 'nombre': 'Euro Castilla',         'ciudad': 'Medellín'},
    {'codigo': 'LLA', 'nombre': 'Euro Llanogrande',      'ciudad': 'Rionegro'},
    {'codigo': 'ACA', 'nombre': 'Euro Arkadia',          'ciudad': 'Medellín'},
    {'codigo': 'TER', 'nombre': 'Euro Terracina',        'ciudad': 'Envigado'},
    {'codigo': 'MUR', 'nombre': 'Euro Murano',           'ciudad': 'Envigado'},
    {'codigo': 'MIX', 'nombre': 'Euro Mixy',             'ciudad': 'Medellín'},
    {'codigo': 'CAR', 'nombre': 'Euro Carnaval',         'ciudad': 'Medellín'},
    {'codigo': 'SAL', 'nombre': 'Euro La Inferior',      'ciudad': 'Medellín'},
    {'codigo': 'MAN', 'nombre': 'Euro Gran Manzana',     'ciudad': 'Medellín'},
    # Montería
    {'codigo': 'MON', 'nombre': 'Euro Montería',         'ciudad': 'Montería'},
    {'codigo': 'NUM', 'nombre': 'Euro Nuestro Montería', 'ciudad': 'Montería'},
    # Tiendas BIG
    {'codigo': 'BIG',          'nombre': 'Big Mayorista',    'ciudad': 'Medellín'},
    {'codigo': 'BIG-CASTILLA', 'nombre': 'Big Castilla',     'ciudad': 'Medellín'},
    {'codigo': 'LAL',          'nombre': 'Big Laureles',     'ciudad': 'Medellín'},
    {'codigo': 'CAL',          'nombre': 'Big Caldas',       'ciudad': 'Caldas'},
    {'codigo': 'CRI',          'nombre': 'Big Cristóbal',    'ciudad': 'Medellín'},
    {'codigo': 'PAL',          'nombre': 'Big Palace',       'ciudad': 'Medellín'},
    # Operaciones
    {'codigo': 'OPS-ACOPIO',   'nombre': 'Acopio',            'ciudad': 'Medellín'},
    {'codigo': 'CED',          'nombre': 'CEDI',              'ciudad': 'Medellín'},
    {'codigo': 'DES',          'nombre': 'Planta de Desposte', 'ciudad': 'Medellín'},
    {'codigo': 'ADM',          'nombre': 'Administración',    'ciudad': 'Medellín'},
    # Omnicanal — domicilios
    {'codigo': 'OMN', 'nombre': 'Omnicanal', 'ciudad': 'Medellín'},
]

# ── Variantes → código canónico ────────────────────────────────────────────────
# Clave: valor normalizado (norm()), Valor: código de sede
_VARIANTES_RAW = {
    # EURO FRONTERA
    'EURO FRONTERA': 'FRO',
    'FRONTERA': 'FRO',
    'EURO FRONTERO': 'FRO',       # typo
    'EURO PALMAS (FRONTERA)': 'FRO',

    # EURO MAYORISTA
    'EURO MAYORISTA': 'MAY',
    'MAYORISTA': 'MAY',

    # EURO FLORIDA
    'EURO FLORIDA': 'FLO',
    'FLORIDA': 'FLO',

    # EURO LAURELES
    'EURO LAURELES': 'LAU',
    'LAURELES': 'LAU',

    # EURO LOS BERNAL
    'EURO LOS BERNAL': 'LOB',
    'EURO BERNAL': 'LOB',
    'EURO LOMA BERNAL': 'LOB',
    'LOMA LOS BERNAL': 'LOB',
    'BERNAL': 'LOB',

    # EURO SABANETA
    'EURO SABANETA': 'SAB',
    'EURO SABANETA VEGAS PLAZA': 'SAB',
    'PROYECTO SABANETA': 'SAB',

    # EURO GUADALCANAL
    'EURO GUADALCANAL': 'GUA',
    'GUADALCANAL': 'GUA',

    # EURO PALMAS
    'EURO PALMAS': 'VEG',
    'EURO PALMAS PALMA GRANDE': 'VEG',
    'EURO PALMA GRANDE': 'VEG',
    'PALMAS': 'VEG',
    'EUO PALMAS': 'VEG',          # typo

    # EURO NIQUIA
    'EURO NIQUIA': 'NIQ',
    'NIQUIA': 'NIQ',

    # EURO ITAGUI
    'EURO ITAGUI': 'ITA',
    'ITAGUI': 'ITA',
    'EUTO ITAGUI': 'ITA',         # typo

    # EURO BARBOSA
    'EURO BARBOSA': 'BAR',
    'BARBOSA': 'BAR',

    # EURO MARINILLA
    'EURO MARINILLA': 'MAR',
    'MARINILLA': 'MAR',

    # EURO BELLO
    'EURO BELLO': 'BEL',
    'BELLO': 'BEL',

    # EURO CASTILLA
    'EURO CASTILLA': 'ESC',
    'CASTILLA': 'ESC',
    'SUPERMERCADOS CASTILLA': 'ESC',

    # EURO LLANOGRANDE
    'EURO LLANOGRANDE': 'LLA',
    'EURO LLANO GRANDE': 'LLA',

    # EURO ARKADIA
    'EURO ARKADIA': 'ACA',

    # EURO TERRACINA
    'EURO TERRACINA ENVIGADO': 'TER',
    'EURO TERRACINA': 'TER',

    # EURO MURANO
    'EURO MURANO ENVIGADO': 'MUR',
    'EURO MURANO': 'MUR',

    # EURO MIXY
    'EURO MIXY LOS COLORES': 'MIX',
    'EURO MIXY': 'MIX',

    # EURO CARNAVAL
    'EURO CARNAVAL': 'CAR',

    # EURO LA INFERIOR
    'EURO LA INFERIOR': 'SAL',

    # EURO GRAN MANZANA
    'EURO GRAN MANZANA': 'MAN',

    # MONTERÍA
    'EURO MONTERIA': 'MON',
    'EURO MONTERIA PLACES': 'MON',
    'EURO NUESTRO MONTERIA': 'NUM',
    'MONTERIA': 'MON',

    # BIG
    'BIG MAYORISTA': 'BIG',
    'BIG CASTILLA': 'BIG-CASTILLA',
    'BIG LAURELES': 'LAL',
    'BIG CALDAS': 'CAL',
    'BIG CRISTOBAL': 'CRI',
    'BIG PALACE': 'PAL',
    'PALACE': 'PAL',

    # Operaciones
    'CEDI': 'CED',
    'CEDI EMPAQUETADO': 'CED',
    'CEDI CONDUCTOR': 'CED',
    'CENTRO DISTRIB.': 'CED',
    'CENTRO DISTRIB': 'CED',
    'ACOPIO': 'OPS-ACOPIO',
    'PLANTA DE DESPOSTE': 'DES',
    'PLANTA DESPOSTE': 'DES',
    'DESPOSTAR': 'DES',
    'ADMINSTRACION': 'ADM',
    'ADMINISTRATIVOS': 'ADM',
    'ADMINISTRACION': 'ADM',
    'ACMINISTRACION': 'ADM',
    'ADMIISTRATIVOS': 'ADM',
}

# Pre-normalizar todas las claves para lookup rápido
VARIANTES = {norm(k): v for k, v in _VARIANTES_RAW.items()}


def resolver_sede(valor):
    """
    Dado un valor de Excel, retorna el código canónico de la sede
    o None si no se reconoce.
    """
    return VARIANTES.get(norm(valor))
