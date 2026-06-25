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
SEDES_CANONICAS = [
    # Tiendas EURO — área metropolitana Medellín
    {'codigo': 'EUR-FRONTERA',     'nombre': 'Euro Frontera',         'ciudad': 'Itagüí'},
    {'codigo': 'EUR-MAYORISTA',    'nombre': 'Euro Mayorista',        'ciudad': 'Medellín'},
    {'codigo': 'EUR-FLORIDA',      'nombre': 'Euro Florida',          'ciudad': 'Medellín'},
    {'codigo': 'EUR-LAURELES',     'nombre': 'Euro Laureles',         'ciudad': 'Medellín'},
    {'codigo': 'EUR-BERNAL',       'nombre': 'Euro Los Bernal',       'ciudad': 'Medellín'},
    {'codigo': 'EUR-SABANETA',     'nombre': 'Euro Sabaneta',         'ciudad': 'Sabaneta'},
    {'codigo': 'EUR-GUADALCANAL',  'nombre': 'Euro Guadalcanal',      'ciudad': 'Medellín'},
    {'codigo': 'EUR-PALMAS',       'nombre': 'Euro Palmas',           'ciudad': 'Medellín'},
    {'codigo': 'EUR-NIQUIA',       'nombre': 'Euro Niquia',           'ciudad': 'Bello'},
    {'codigo': 'EUR-ITAGUI',       'nombre': 'Euro Itagüí',           'ciudad': 'Itagüí'},
    {'codigo': 'EUR-BARBOSA',      'nombre': 'Euro Barbosa',          'ciudad': 'Barbosa'},
    {'codigo': 'EUR-MARINILLA',    'nombre': 'Euro Marinilla',        'ciudad': 'Marinilla'},
    {'codigo': 'EUR-BELLO',        'nombre': 'Euro Bello',            'ciudad': 'Bello'},
    {'codigo': 'EUR-CASTILLA',     'nombre': 'Euro Castilla',         'ciudad': 'Medellín'},
    {'codigo': 'EUR-LLANOGRANDE',  'nombre': 'Euro Llanogrande',      'ciudad': 'Rionegro'},
    {'codigo': 'EUR-ARKADIA',      'nombre': 'Euro Arkadia',          'ciudad': 'Medellín'},
    {'codigo': 'EUR-TERRACINA',    'nombre': 'Euro Terracina',        'ciudad': 'Envigado'},
    {'codigo': 'EUR-MURANO',       'nombre': 'Euro Murano',           'ciudad': 'Envigado'},
    {'codigo': 'EUR-MIXY',         'nombre': 'Euro Mixy',             'ciudad': 'Medellín'},
    {'codigo': 'EUR-CARNAVAL',     'nombre': 'Euro Carnaval',         'ciudad': 'Medellín'},
    {'codigo': 'EUR-INFERIOR',     'nombre': 'Euro La Inferior',      'ciudad': 'Medellín'},
    {'codigo': 'EUR-GRANMANZANA',  'nombre': 'Euro Gran Manzana',     'ciudad': 'Medellín'},
    # Montería
    {'codigo': 'EUR-MONTERIA',     'nombre': 'Euro Montería',         'ciudad': 'Montería'},
    {'codigo': 'EUR-NTR-MONTERIA', 'nombre': 'Euro Nuestro Montería', 'ciudad': 'Montería'},
    # Tiendas BIG
    {'codigo': 'BIG-MAYORISTA',    'nombre': 'Big Mayorista',         'ciudad': 'Medellín'},
    {'codigo': 'BIG-CASTILLA',     'nombre': 'Big Castilla',          'ciudad': 'Medellín'},
    {'codigo': 'BIG-LAURELES',     'nombre': 'Big Laureles',          'ciudad': 'Medellín'},
    {'codigo': 'BIG-CALDAS',       'nombre': 'Big Caldas',            'ciudad': 'Caldas'},
    {'codigo': 'BIG-CRISTOBAL',    'nombre': 'Big Cristóbal',         'ciudad': 'Medellín'},
    {'codigo': 'BIG-PALACE',       'nombre': 'Big Palace',            'ciudad': 'Medellín'},
    # Operaciones
    {'codigo': 'OPS-CEDI',         'nombre': 'CEDI',                  'ciudad': 'Medellín'},
    {'codigo': 'OPS-DESPOSTE',     'nombre': 'Planta de Desposte',    'ciudad': 'Medellín'},
    {'codigo': 'OPS-ADMIN',        'nombre': 'Administración',        'ciudad': 'Medellín'},
    {'codigo': 'OPS-ACOPIO',       'nombre': 'Acopio',                'ciudad': 'Medellín'},
    # Omnicanal — domicilios
    {'codigo': 'OMN',              'nombre': 'Omnicanal',             'ciudad': 'Medellín'},
]

# ── Variantes → código canónico ────────────────────────────────────────────────
# Clave: valor normalizado (norm()), Valor: código de sede
_VARIANTES_RAW = {
    # EURO FRONTERA
    'EURO FRONTERA': 'EUR-FRONTERA',
    'FRONTERA': 'EUR-FRONTERA',
    'EURO FRONTERO': 'EUR-FRONTERA',       # typo
    'EURO PALMAS (FRONTERA)': 'EUR-FRONTERA',

    # EURO MAYORISTA
    'EURO MAYORISTA': 'EUR-MAYORISTA',
    'MAYORISTA': 'EUR-MAYORISTA',

    # EURO FLORIDA
    'EURO FLORIDA': 'EUR-FLORIDA',
    'FLORIDA': 'EUR-FLORIDA',

    # EURO LAURELES
    'EURO LAURELES': 'EUR-LAURELES',
    'LAURELES': 'EUR-LAURELES',

    # EURO LOS BERNAL
    'EURO LOS BERNAL': 'EUR-BERNAL',
    'EURO BERNAL': 'EUR-BERNAL',
    'EURO LOMA BERNAL': 'EUR-BERNAL',
    'LOMA LOS BERNAL': 'EUR-BERNAL',
    'BERNAL': 'EUR-BERNAL',

    # EURO SABANETA
    'EURO SABANETA': 'EUR-SABANETA',
    'EURO SABANETA VEGAS PLAZA': 'EUR-SABANETA',
    'PROYECTO SABANETA': 'EUR-SABANETA',

    # EURO GUADALCANAL
    'EURO GUADALCANAL': 'EUR-GUADALCANAL',
    'GUADALCANAL': 'EUR-GUADALCANAL',

    # EURO PALMAS
    'EURO PALMAS': 'EUR-PALMAS',
    'EURO PALMAS PALMA GRANDE': 'EUR-PALMAS',
    'EURO PALMA GRANDE': 'EUR-PALMAS',
    'PALMAS': 'EUR-PALMAS',
    'EUO PALMAS': 'EUR-PALMAS',            # typo

    # EURO NIQUIA
    'EURO NIQUIA': 'EUR-NIQUIA',
    'NIQUIA': 'EUR-NIQUIA',

    # EURO ITAGUI
    'EURO ITAGUI': 'EUR-ITAGUI',
    'ITAGUI': 'EUR-ITAGUI',
    'EUTO ITAGUI': 'EUR-ITAGUI',           # typo

    # EURO BARBOSA
    'EURO BARBOSA': 'EUR-BARBOSA',
    'BARBOSA': 'EUR-BARBOSA',

    # EURO MARINILLA
    'EURO MARINILLA': 'EUR-MARINILLA',
    'MARINILLA': 'EUR-MARINILLA',

    # EURO BELLO
    'EURO BELLO': 'EUR-BELLO',
    'BELLO': 'EUR-BELLO',

    # EURO CASTILLA
    'EURO CASTILLA': 'EUR-CASTILLA',
    'CASTILLA': 'EUR-CASTILLA',
    'SUPERMERCADOS CASTILLA': 'EUR-CASTILLA',

    # EURO LLANOGRANDE
    'EURO LLANOGRANDE': 'EUR-LLANOGRANDE',
    'EURO LLANO GRANDE': 'EUR-LLANOGRANDE',

    # EURO ARKADIA
    'EURO ARKADIA': 'EUR-ARKADIA',

    # EURO TERRACINA
    'EURO TERRACINA ENVIGADO': 'EUR-TERRACINA',
    'EURO TERRACINA': 'EUR-TERRACINA',

    # EURO MURANO
    'EURO MURANO ENVIGADO': 'EUR-MURANO',
    'EURO MURANO': 'EUR-MURANO',

    # EURO MIXY
    'EURO MIXY LOS COLORES': 'EUR-MIXY',
    'EURO MIXY': 'EUR-MIXY',

    # EURO CARNAVAL
    'EURO CARNAVAL': 'EUR-CARNAVAL',

    # EURO LA INFERIOR
    'EURO LA INFERIOR': 'EUR-INFERIOR',

    # EURO GRAN MANZANA
    'EURO GRAN MANZANA': 'EUR-GRANMANZANA',

    # MONTERÍA
    'EURO MONTERIA': 'EUR-MONTERIA',
    'EURO MONTERIA PLACES': 'EUR-NTR-MONTERIA',
    'EURO NUESTRO MONTERIA': 'EUR-NTR-MONTERIA',
    'MONTERIA': 'EUR-MONTERIA',

    # BIG
    'BIG MAYORISTA': 'BIG-MAYORISTA',
    'BIG CASTILLA': 'BIG-CASTILLA',
    'BIG LAURELES': 'BIG-LAURELES',
    'BIG CALDAS': 'BIG-CALDAS',
    'BIG CRISTOBAL': 'BIG-CRISTOBAL',
    'BIG PALACE': 'BIG-PALACE',
    'PALACE': 'BIG-PALACE',

    # Operaciones
    'CEDI': 'OPS-CEDI',
    'CEDI EMPAQUETADO': 'OPS-CEDI',
    'CEDI CONDUCTOR': 'OPS-CEDI',
    'CENTRO DISTRIB.': 'OPS-CEDI',
    'CENTRO DISTRIB': 'OPS-CEDI',
    'ACOPIO': 'OPS-ACOPIO',
    'PLANTA DE DESPOSTE': 'OPS-DESPOSTE',
    'PLANTA DESPOSTE': 'OPS-DESPOSTE',
    'DESPOSTAR': 'OPS-DESPOSTE',
    'ADMINSTRACION': 'OPS-ADMIN',
    'ADMINISTRATIVOS': 'OPS-ADMIN',
    'ADMINISTRACION': 'OPS-ADMIN',
    'ACMINISTRACION': 'OPS-ADMIN',
    'ADMIISTRATIVOS': 'OPS-ADMIN',
    'ADMINISTRACION': 'OPS-ADMIN',
}

# Pre-normalizar todas las claves para lookup rápido
VARIANTES = {norm(k): v for k, v in _VARIANTES_RAW.items()}


def resolver_sede(valor):
    """
    Dado un valor de Excel, retorna el código canónico de la sede
    o None si no se reconoce.
    """
    return VARIANTES.get(norm(valor))
