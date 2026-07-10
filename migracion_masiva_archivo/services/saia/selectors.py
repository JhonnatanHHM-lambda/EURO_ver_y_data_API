LOGIN_USER_SELECTORS = [
    'input[name="usuario"]',
    'input[name="user"]',
    'input[name="username"]',
    'input[name="login"]',
    'input[id*="usuario" i]',
    'input[id*="user" i]',
    'input[type="text"]',
]

LOGIN_PASSWORD_SELECTORS = [
    'input[name="clave"]',
    'input[name="password"]',
    'input[id*="clave" i]',
    'input[id*="pass" i]',
    'input[type="password"]',
]

LOGIN_SUBMIT_SELECTORS = [
    '#ingresar',
    'button[type="submit"]',
    'input[type="submit"]',
    'button:has-text("Iniciar sesión")',
    'button:has-text("Iniciar sesion")',
    'button:has-text("Ingresar")',
    'button:has-text("Entrar")',
    'input[value*="Iniciar sesión" i]',
    'input[value*="Iniciar sesion" i]',
    'input[value*="Ingresar" i]',
    'input[value*="Entrar" i]',
]

LOGIN_SUCCESS_TEXTS = [
    'has ingresado al sistema saia',
    'bienvenido',
]

LOGIN_ERROR_TEXTS = [
    'usuario o clave',
    'clave incorrecta',
    'usuario incorrecto',
    'no puedes acceder',
    'credenciales',
    'error',
]

SAIA_NAVIGATION_STEPS = [
    {'labels': ['Archivo'], 'optional': False},
    {'title_contains': 'Mis expedientes', 'optional': False},
    {
        'labels': [
            'Archivo Central',
            'Archivo central',
            'ARCHIVO CENTRAL',
            'Archivo de Gestión',
            'Archivo de Gestion',
            'ARCHIVO DE GESTIÓN',
            'ARCHIVO DE GESTION',
        ],
        'optional': False,
    },
    {'labels': ['Pagos', 'PAGOS'], 'optional': False},
    {'labels': ['Comprobantes contables', 'COMPROBANTES CONTABLES'], 'optional': False},
    {'labels': ['Pagos electrónicos - PEL', 'Pagos electronicos - PEL', 'PAGOS ELECTRONICOS - PEL'], 'optional': False},
    {'labels': ['2019'], 'optional': False},
    {'labels': ['Acciones'], 'optional': False},
    {'labels': ['Adicionar documento'], 'optional': False},
]

# Pasos para llegar a Archivo Central > Dirección de Contabilidad > Conciliaciones Bancarias
SAIA_NAVIGATION_STEPS_PRO = [
    {'labels': ['Archivo'], 'optional': False},
    {'title_contains': 'Mis expedientes', 'optional': False},
    {'labels': ['Archivo Central', 'Archivo central', 'ARCHIVO CENTRAL'], 'optional': False},
    {'labels': ['Pagos', 'PAGOS'], 'optional': False},
    {'labels': ['Comprobantes Contables', 'Comprobantes contables', 'COMPROBANTES CONTABLES'], 'optional': False},
    {
        'labels': [
            'PAGOS ELECTRONICOS PRO',
            'Pagos Electronicos PRO',
            'Pagos Electrónicos PRO',
            'PAGOS ELECTRÓNICOS PRO',
            'PAGOS ELECTRONICOS - PRO',
            'Pagos Electronicos - PRO',
            'Pagos ElectrÃ³nicos - PRO',
        ],
        'optional': False,
    },
    {
        'labels': [
            '2017',
            'PRO 2017',
            'Pro 2017',
        ],
        'optional': False,
    },
    {'labels': ['Acciones'], 'optional': False},
    {'labels': ['Adicionar documento'], 'optional': False},
]

SAIA_NAVIGATION_STEPS_RCG = [
    {'labels': ['Archivo'], 'optional': False},
    {'title_contains': 'Mis expedientes', 'optional': False},
    {'labels': ['Archivo Central', 'Archivo central', 'ARCHIVO CENTRAL'], 'optional': False},
    {'labels': ['Cartera', 'CARTERA'], 'optional': False},
    {'labels': ['Comprobantes Contables', 'Comprobantes contables', 'COMPROBANTES CONTABLES'], 'optional': False},
    {
        'labels': [
            'Recibos Caja ConsignaciÃƒÂ³n - RCG',
            'Recibos Caja Consignacion - RCG',
            'RECIBOS CAJA CONSIGNACION - RCG',
        ],
        'optional': False,
    },
    {'labels': ['Acciones'], 'optional': False},
    {'labels': ['Adicionar documento'], 'optional': False},
]

SAIA_NAVIGATION_STEPS_RCI = [
    {'labels': ['Archivo'], 'optional': False},
    {'title_contains': 'Mis expedientes', 'optional': False},
    {'labels': ['Archivo Central', 'Archivo central', 'ARCHIVO CENTRAL'], 'optional': False},
    {'labels': ['Cartera', 'CARTERA'], 'optional': False},
    {'labels': ['Comprobantes Contables', 'Comprobantes contables', 'COMPROBANTES CONTABLES'], 'optional': False},
    {
        'labels': [
            'Recibos Caja Cierre - RCI',
            'Recibos Caja Cierre-RCI',
            'Recibos caja cierre-RCI',
            'RECIBOS CAJA CIERRE - RCI',
            'RECIBOS CAJA CIERRE-RCI',
        ],
        'optional': False,
    },
    {'labels': ['Acciones'], 'optional': False},
    {'labels': ['Adicionar documento'], 'optional': False},
]

SAIA_NAVIGATION_STEPS_RCP = [
    {'labels': ['Archivo'], 'optional': False},
    {'title_contains': 'Mis expedientes', 'optional': False},
    {'labels': ['Archivo Central', 'Archivo central', 'ARCHIVO CENTRAL'], 'optional': False},
    {'labels': ['Cartera', 'CARTERA'], 'optional': False},
    {'labels': ['Comprobantes Contables', 'Comprobantes contables', 'COMPROBANTES CONTABLES'], 'optional': False},
    {
        'labels': [
            'Reclasificaciones de Cuentas - RCP',
            'Reclasificaciones de Cuentas-RCP',
            'Reclasificaciones de cuentas-RCP',
            'RECLASIFICACIONES DE CUENTAS - RCP',
            'RECLASIFICACIONES DE CUENTAS-RCP',
        ],
        'optional': False,
    },
    {'labels': ['Acciones'], 'optional': False},
    {'labels': ['Adicionar documento'], 'optional': False},
]

# Pasos para llegar a Archivo de Gestión > Dirección de Contabilidad > Ajustes Contables > INC
# IMPORTANTE: los labels exactos deben verificarse navegando manualmente con el script
# scripts/inspeccion_saia_inc.py antes de usar en producción. SAIA usa encoding corrupto
# frecuente (ó → Ã³). Las variantes de cada paso cubren los encodings más comunes.
SAIA_NAVIGATION_STEPS_INC = [
    {'labels': ['Archivo'], 'optional': False},
    {'title_contains': 'Mis expedientes', 'optional': False},
    {'labels': ['Archivo Central', 'Archivo central', 'ARCHIVO CENTRAL'], 'optional': False},
    {
        'labels': [
            'Dirección de Contabilidad',
            'Direccion de Contabilidad',
            'DirecciÃ³n de Contabilidad',
            'DirecciÃƒÂ³n de Contabilidad',
            'DIRECCIÓN DE CONTABILIDAD',
            'DIRECCION DE CONTABILIDAD',
        ],
        'optional': False,
    },
    {
        'labels': [
            'Ajustes Contables',
            'AJUSTES CONTABLES',
        ],
        'optional': False,
    },
    # Label confirmado visualmente: "Indirectos Contables cierre - INC"
    {
        'labels': [
            'Indirectos Contables cierre - INC',
            'Indirectos contables cierre - INC',
            'INDIRECTOS CONTABLES CIERRE - INC',
            'Indirectos Contables Cierre - INC',
        ],
        'optional': False,
    },
    # Label confirmado visualmente: "Soportes Contables"
    {
        'labels': [
            'Soportes Contables',
            'Soportes contables',
            'SOPORTES CONTABLES',
        ],
        'optional': False,
    },
    {'labels': ['Acciones'], 'optional': False},
    {'labels': ['Adicionar documento'], 'optional': False},
]

# Pasos para llegar a Archivo de Gestión > Dirección de Contabilidad > Ajustes Contables > NIC
# IMPORTANTE: los labels exactos deben verificarse navegando manualmente con el script
# scripts/inspeccion_saia_nic.py antes de usar en producción. SAIA usa encoding corrupto
# frecuente (ó → Ã³). Las variantes de cada paso cubren los encodings más comunes.
SAIA_NAVIGATION_STEPS_NIC = [
    {'labels': ['Archivo'], 'optional': False},
    {'title_contains': 'Mis expedientes', 'optional': False},
    {'labels': ['Archivo Central', 'Archivo central', 'ARCHIVO CENTRAL'], 'optional': False},
    {
        'labels': [
            'Dirección de Contabilidad',
            'Direccion de Contabilidad',
            'DirecciÃ³n de Contabilidad',
            'DirecciÃƒÂ³n de Contabilidad',
            'DIRECCIÓN DE CONTABILIDAD',
            'DIRECCION DE CONTABILIDAD',
        ],
        'optional': False,
    },
    {
        'labels': [
            'Ajustes Contables',
            'AJUSTES CONTABLES',
        ],
        'optional': False,
    },
    # Label confirmado visualmente: "Notas Interna Contable - NIC"
    {
        'labels': [
            'Notas Interna Contable - NIC',
            'Notas interna contable - NIC',
            'NOTAS INTERNA CONTABLE - NIC',
            'Notas Interna Contable-NIC',
            'NOTAS INTERNA CONTABLE-NIC',
        ],
        'optional': False,
    },
    # Label confirmado visualmente: "Soportes contables"
    {
        'labels': [
            'Soportes contables',
            'Soportes Contables',
            'SOPORTES CONTABLES',
        ],
        'optional': False,
    },
    {'labels': ['Acciones'], 'optional': False},
    {'labels': ['Adicionar documento'], 'optional': False},
]

# Pasos para llegar a Archivo de Gestión > Dirección de Contabilidad > Ajustes Contables > IND
# IMPORTANTE: verificar el subnodo final con scripts/inspeccion_saia_ind.py antes de producción.
SAIA_NAVIGATION_STEPS_IND = [
    {'labels': ['Archivo'], 'optional': False},
    {'title_contains': 'Mis expedientes', 'optional': False},
    {'labels': ['Archivo Central', 'Archivo central', 'ARCHIVO CENTRAL'], 'optional': False},
    {
        'labels': [
            'Dirección de Contabilidad',
            'Direccion de Contabilidad',
            'DirecciÃ³n de Contabilidad',
            'DirecciÃƒÂ³n de Contabilidad',
            'DIRECCIÓN DE CONTABILIDAD',
            'DIRECCION DE CONTABILIDAD',
        ],
        'optional': False,
    },
    {
        'labels': [
            'Ajustes Contables',
            'AJUSTES CONTABLES',
        ],
        'optional': False,
    },
    # Label confirmado visualmente: "Indirectos Contables - IND"
    {
        'labels': [
            'Indirectos Contables - IND',
            'Indirectos contables - IND',
            'INDIRECTOS CONTABLES - IND',
            'Indirectos Contables-IND',
            'INDIRECTOS CONTABLES-IND',
        ],
        'optional': False,
    },
    # Label confirmado visualmente: "Soportes contables"
    {
        'labels': [
            'Soportes contables',
            'Soportes Contables',
            'SOPORTES CONTABLES',
        ],
        'optional': False,
    },
    {'labels': ['Acciones'], 'optional': False},
    {'labels': ['Adicionar documento'], 'optional': False},
]

# ── Declaraciones Tributarias ── Pendientes por Ingreso PEL 2015 ──────────────
# Ruta compartida: Archivo de Gestión > Impuestos > Declaraciones Tributarias
# IMPORTANTE: labels exactos pendientes de verificación con scripts/inspeccion_saia_pp.py
# SAIA usa encoding corrupto frecuente (ó → Ã³).

_SAIA_STEPS_DT_BASE = [
    {'labels': ['Archivo'], 'optional': False},
    {'title_contains': 'Mis expedientes', 'optional': False},
    {'labels': ['Archivo Central', 'Archivo central', 'ARCHIVO CENTRAL'], 'optional': False},
    {
        'labels': [
            'Impuestos',
            'IMPUESTOS',
        ],
        'optional': False,
    },
    {
        'labels': [
            'Declaraciones Tributarias',
            'Declaraciones tributarias',
            'DECLARACIONES TRIBUTARIAS',
        ],
        'optional': False,
    },
]

# PP1 — PENDIENTES POR INGRESO PEL 2015 -1
SAIA_NAVIGATION_STEPS_RICA = _SAIA_STEPS_DT_BASE + [
    {
        'labels': [
            'Declaraci?n de Retenci?n de ICA',
            'Declaracion de Retencion de ICA',
            'DECLARACION DE RETENCION DE ICA',
            'Declaraci?n Retenci?n ICA',
            'Declaracion Retencion ICA',
            'Retenci?n de ICA',
            'Retencion de ICA',
            'RETENCION DE ICA',
        ],
        'optional': False,
    },
    {'dynamic_year': True, 'year_prefix': '', 'optional': False, 'navigate_into': True},
    {'labels': ['Acciones'], 'optional': False},
    {'labels': ['Adicionar documento'], 'optional': False},
]

SAIA_NAVIGATION_STEPS_PP1 = _SAIA_STEPS_DT_BASE + [
    # Subnodo -1 — reemplazar con label real del script de inspección.
    {
        'labels': [
            'PENDIENTES POR INGRESO PEL 2015 -1',
            'Pendientes por ingreso PEL 2015 -1',
            'PENDIENTES POR INGRESO PEL 2015-1',
            'Pendientes Por Ingreso PEL 2015 -1',
            'PEL 2015 -1',
        ],
        'optional': False,
    },
    {'labels': ['Acciones'], 'optional': False},
    {'labels': ['Adicionar documento'], 'optional': False},
]

# PP2 — PENDIENTES POR INGRESO PEL 2015 -2
SAIA_NAVIGATION_STEPS_PP2 = _SAIA_STEPS_DT_BASE + [
    {
        'labels': [
            'PENDIENTES POR INGRESO PEL 2015 -2',
            'Pendientes por ingreso PEL 2015 -2',
            'PENDIENTES POR INGRESO PEL 2015-2',
            'Pendientes Por Ingreso PEL 2015 -2',
            'PEL 2015 -2',
        ],
        'optional': False,
    },
    {'labels': ['Acciones'], 'optional': False},
    {'labels': ['Adicionar documento'], 'optional': False},
]

# PP3 — PENDIENTES POR INGRESO PEL 2015 -3
SAIA_NAVIGATION_STEPS_PP3 = _SAIA_STEPS_DT_BASE + [
    {
        'labels': [
            'PENDIENTES POR INGRESO PEL 2015 -3',
            'Pendientes por ingreso PEL 2015 -3',
            'PENDIENTES POR INGRESO PEL 2015-3',
            'Pendientes Por Ingreso PEL 2015 -3',
            'PEL 2015 -3',
        ],
        'optional': False,
    },
    {'labels': ['Acciones'], 'optional': False},
    {'labels': ['Adicionar documento'], 'optional': False},
]

# Pasos para llegar a Archivo de Gestión > Pagos > Comprobantes Contables
#   > Egresos cheques bancolombia > Soportes
# IMPORTANTE: labels exactos pendientes de verificación con scripts/inspeccion_saia_ecb.py
# SAIA usa encoding corrupto frecuente (ó → Ã³, é → Ã©).
SAIA_NAVIGATION_STEPS_ECB = [
    {'labels': ['Archivo'], 'optional': False},
    {'title_contains': 'Mis expedientes', 'optional': False},
    {'labels': ['Archivo Central', 'Archivo central', 'ARCHIVO CENTRAL'], 'optional': False},
    {
        'labels': [
            'Pagos',
            'PAGOS',
        ],
        'optional': False,
    },
    {
        'labels': [
            'Comprobantes Contables',
            'Comprobantes contables',
            'COMPROBANTES CONTABLES',
        ],
        'optional': False,
    },
    {
        'labels': [
            'Egresos Cheques Bancolombia - ECB',
            'Egresos cheques bancolombia - ECB',
            'EGRESOS CHEQUES BANCOLOMBIA - ECB',
            'Egresos Cheques Bancolombia-ECB',
            'EGRESOS CHEQUES BANCOLOMBIA-ECB',
        ],
        'optional': False,
    },
    {'dynamic_year': True, 'year_prefix': 'ECB ', 'optional': False, 'navigate_into': True},
    {'labels': ['Acciones'], 'optional': False},
    {'labels': ['Adicionar documento'], 'optional': False},
]

# Pasos para llegar a Archivo de Gestión > Pagos > Comprobantes Contables
#   > Egresos Efectivo - EGE > Soportes
# Labels confirmados visualmente en SAIA (captura 25/Jun/2026).
# Se mantienen variantes de encoding corrupto (ó → Ã³) por consistencia defensiva.

SAIA_NAVIGATION_STEPS_EGC = [
    {'labels': ['Archivo'], 'optional': False},
    {'title_contains': 'Mis expedientes', 'optional': False},
    {'labels': ['Archivo Central', 'Archivo central', 'ARCHIVO CENTRAL'], 'optional': False},
    {
        'labels': [
            'Pagos',
            'PAGOS',
        ],
        'optional': False,
    },
    {
        'labels': [
            'Comprobantes Contables',
            'Comprobantes contables',
            'COMPROBANTES CONTABLES',
        ],
        'optional': False,
    },
    {
        'labels': [
            'Egresos Cheques - EGC',
            'Egresos cheques - EGC',
            'EGRESOS CHEQUES - EGC',
            'Egresos Cheques-EGC',
            'EGRESOS CHEQUES-EGC',
        ],
        'optional': False,
    },
    {'dynamic_year': True, 'year_prefix': 'EGC ', 'optional': False, 'navigate_into': True},
    {'labels': ['Acciones'], 'optional': False},
    {'labels': ['Adicionar documento'], 'optional': False},
]

SAIA_NAVIGATION_STEPS_EGE = [
    {'labels': ['Archivo'], 'optional': False},
    {'title_contains': 'Mis expedientes', 'optional': False},
    {'labels': ['Archivo Central', 'Archivo central', 'ARCHIVO CENTRAL'], 'optional': False},
    {
        'labels': [
            'Pagos',
            'PAGOS',
        ],
        'optional': False,
    },
    {
        'labels': [
            'Comprobantes Contables',
            'Comprobantes contables',
            'COMPROBANTES CONTABLES',
        ],
        'optional': False,
    },
    # Label confirmado visualmente: "Egresos Efectivo - EGE"
    {
        'labels': [
            'Egresos Efectivo - EGE',
            'Egresos efectivo - EGE',
            'EGRESOS EFECTIVO - EGE',
            'Egresos Efectivo-EGE',
            'EGRESOS EFECTIVO-EGE',
            'Egresos Efectivo',
            'EGRESOS EFECTIVO',
        ],
        'optional': False,
    },
    {'dynamic_year': True, 'optional': False, 'navigate_into': True},
    # Solo 2016 contiene el sub-expediente MAYORISTA. navigate_into=True hace
    # que el cliente espere a que la fila cargue antes de entrar.
    {
        'labels': ['Mayorista', 'MAYORISTA', 'mayorista'],
        'optional': False,
        'navigate_into': True,
        'only_years': [2016],
    },
    {'labels': ['Acciones'], 'optional': False},
    {'labels': ['Adicionar documento'], 'optional': False},
]

# Pasos para llegar a Archivo de Gestión > Pagos > Comprobantes Contables
#   > Pagos Electrónicos Cierre - PEC > Soportes
# Labels confirmados visualmente en SAIA (captura 25/Jun/2026).
# Se mantienen variantes de encoding corrupto (ó → Ã³) por consistencia defensiva.
SAIA_NAVIGATION_STEPS_PEC = [
    {'labels': ['Archivo'], 'optional': False},
    {'title_contains': 'Mis expedientes', 'optional': False},
    {'labels': ['Archivo Central', 'Archivo central', 'ARCHIVO CENTRAL'], 'optional': False},
    {
        'labels': [
            'Pagos',
            'PAGOS',
        ],
        'optional': False,
    },
    {
        'labels': [
            'Comprobantes Contables',
            'Comprobantes contables',
            'COMPROBANTES CONTABLES',
        ],
        'optional': False,
    },
    # Label confirmado visualmente: "Pagos Electrónicos Cierre - PEC"
    {
        'labels': [
            'Pagos Electrónicos Cierre - PEC',
            'Pagos Electronicos Cierre - PEC',
            'PAGOS ELECTRÓNICOS CIERRE - PEC',
            'PAGOS ELECTRONICOS CIERRE - PEC',
            'Pagos ElectrÃ³nicos Cierre - PEC',
            'Pagos Electrónicos Cierre-PEC',
            'PAGOS ELECTRONICOS CIERRE-PEC',
        ],
        'optional': False,
    },
    # Label confirmado visualmente: "Soportes"
    {
        'labels': [
            'Soportes',
            'SOPORTES',
        ],
        'optional': False,
    },
    {'labels': ['Acciones'], 'optional': False},
    {'labels': ['Adicionar documento'], 'optional': False},
]

# ── Impuesto al Consumo 2014 ── Bimestres 1 al 6 ─────────────────────────────
# Ruta: Archivo de Gestión > Impuestos > Declaraciones Tributarias
#        > Impuesto al Consumo 2014 > [Bimestre X]
# IMPORTANTE: labels exactos de "Impuesto al Consumo 2014" y bimestres pendientes
# de verificación visual. SAIA usa encoding corrupto frecuente (ó → Ã³).

_SAIA_STEPS_IC_BASE = _SAIA_STEPS_DT_BASE + [
    # Nodo "Impuesto al Consumo 2014" — verificar label real con captura.
    {
        'labels': [
            'Impuesto al Consumo 2014',
            'IMPUESTO AL CONSUMO 2014',
            'Impuesto Al Consumo 2014',
            'Impuesto al consumo 2014',
        ],
        'optional': False,
    },
]

# IC1 — IMPUESTO AL CONSUMO BIMESTRE 1
SAIA_NAVIGATION_STEPS_IC1 = _SAIA_STEPS_IC_BASE + [
    {
        'labels': [
            'IMPUESTO AL CONSUMO BIMESTRE 1',
            'Impuesto al Consumo Bimestre 1',
            'Impuesto al consumo bimestre 1',
            'BIMESTRE 1',
            'Bimestre 1',
        ],
        'optional': False,
    },
    {'labels': ['Acciones'], 'optional': False},
    {'labels': ['Adicionar documento'], 'optional': False},
]

# IC2 — IMPUESTO AL CONSUMO BIMESTRE 2
SAIA_NAVIGATION_STEPS_IC2 = _SAIA_STEPS_IC_BASE + [
    {
        'labels': [
            'IMPUESTO AL CONSUMO BIMESTRE 2',
            'Impuesto al Consumo Bimestre 2',
            'Impuesto al consumo bimestre 2',
            'BIMESTRE 2',
            'Bimestre 2',
        ],
        'optional': False,
    },
    {'labels': ['Acciones'], 'optional': False},
    {'labels': ['Adicionar documento'], 'optional': False},
]

# IC3 — IMPUESTO AL CONSUMO BIMESTRE 3
SAIA_NAVIGATION_STEPS_IC3 = _SAIA_STEPS_IC_BASE + [
    {
        'labels': [
            'IMPUESTO AL CONSUMO BIMESTRE 3',
            'Impuesto al Consumo Bimestre 3',
            'Impuesto al consumo bimestre 3',
            'BIMESTRE 3',
            'Bimestre 3',
        ],
        'optional': False,
    },
    {'labels': ['Acciones'], 'optional': False},
    {'labels': ['Adicionar documento'], 'optional': False},
]

# IC4 — IMPUESTO AL CONSUMO BIMESTRE 4
SAIA_NAVIGATION_STEPS_IC4 = _SAIA_STEPS_IC_BASE + [
    {
        'labels': [
            'IMPUESTO AL CONSUMO BIMESTRE 4',
            'Impuesto al Consumo Bimestre 4',
            'Impuesto al consumo bimestre 4',
            'BIMESTRE 4',
            'Bimestre 4',
        ],
        'optional': False,
    },
    {'labels': ['Acciones'], 'optional': False},
    {'labels': ['Adicionar documento'], 'optional': False},
]

# IC5 — IMPUESTO AL CONSUMO BIMESTRE 5
SAIA_NAVIGATION_STEPS_IC5 = _SAIA_STEPS_IC_BASE + [
    {
        'labels': [
            'IMPUESTO AL CONSUMO BIMESTRE 5',
            'Impuesto al Consumo Bimestre 5',
            'Impuesto al consumo bimestre 5',
            'BIMESTRE 5',
            'Bimestre 5',
        ],
        'optional': False,
    },
    {'labels': ['Acciones'], 'optional': False},
    {'labels': ['Adicionar documento'], 'optional': False},
]

# IC6 — IMPUESTO AL CONSUMO BIMESTRE 6
SAIA_NAVIGATION_STEPS_IC6 = _SAIA_STEPS_IC_BASE + [
    {
        'labels': [
            'IMPUESTO AL CONSUMO BIMESTRE 6',
            'Impuesto al Consumo Bimestre 6',
            'Impuesto al consumo bimestre 6',
            'BIMESTRE 6',
            'Bimestre 6',
        ],
        'optional': False,
    },
    {'labels': ['Acciones'], 'optional': False},
    {'labels': ['Adicionar documento'], 'optional': False},
]

# Pasos para llegar a Archivo Central > Cartera > Comprobantes Contables
#   > Recibos de Caja - RCC > Soportes
# PROVISIONAL: la sección y los labels exactos deben verificarse con captura de pantalla
# antes de usar en producción. SAIA usa encoding corrupto frecuente (ó → Ã³).
SAIA_NAVIGATION_STEPS_RCC = [
    {'labels': ['Archivo'], 'optional': False},
    {'title_contains': 'Mis expedientes', 'optional': False},
    {'labels': ['Archivo Central', 'Archivo central', 'ARCHIVO CENTRAL'], 'optional': False},
    {'labels': ['Cartera', 'CARTERA'], 'optional': False},
    {
        'labels': [
            'Comprobantes Contables',
            'Comprobantes contables',
            'COMPROBANTES CONTABLES',
        ],
        'optional': False,
    },
    {
        'labels': [
            'Recibos de Caja - RCC',
            'Recibos de caja - RCC',
            'RECIBOS DE CAJA - RCC',
            'Recibos de Caja-RCC',
            'RECIBOS DE CAJA-RCC',
            'Recibos de Caja',
            'RECIBOS DE CAJA',
        ],
        'optional': False,
    },
    {
        'labels': [
            'Soportes',
            'SOPORTES',
        ],
        'optional': False,
    },
    {'labels': ['Acciones'], 'optional': False},
    {'labels': ['Adicionar documento'], 'optional': False},
]

SAIA_NAVIGATION_STEPS_BANCOLOMBIA = [
    {'labels': ['Archivo'], 'optional': False},
    {'title_contains': 'Mis expedientes', 'optional': False},
    {'labels': ['Archivo Central', 'ARCHIVO CENTRAL'], 'optional': False},
    {
        'labels': [
            'Direccion de Contabilidad',
            'DirecciÃ³n de Contabilidad',
            'DirecciÃƒÂ³n de Contabilidad',
            'DIRECCION DE CONTABILIDAD',
            'DIRECCIÓN DE CONTABILIDAD',
            'DIRECCIÓN DE CONTABILIDAD',
        ],
        'optional': False,
    },
    {'labels': ['Conciliaciones', 'CONCILIACIONES'], 'optional': False},
    {
        'labels': [
            'Conciliaciones Bancarias',
            'CONCILIACIONES BANCARIAS',
            'Conciliacion Bancaria',
            'CONCILIACION BANCARIA',
        ],
        'optional': False,
    },
    {'labels': ['Bancolombia', 'BANCOLOMBIA'], 'optional': False},
    {'dynamic_subexpediente': True, 'optional': False},
    {'labels': ['Acciones'], 'optional': False},
    {'labels': ['Adicionar documento'], 'optional': False},
]


SAIA_NAVIGATION_STEPS_CCA = [
    {'labels': ['Archivo'], 'optional': False},
    {'title_contains': 'Mis expedientes', 'optional': False},
    {'labels': ['Archivo Central', 'Archivo central', 'ARCHIVO CENTRAL'], 'optional': False},
    {
        'labels': [
            'DIRECCIÓN DE CONTABILIDAD',
            'DIRECCION DE CONTABILIDAD',
            'Dirección de Contabilidad',
            'Direccion de Contabilidad',
        ],
        'optional': False,
    },
    {'labels': ['Conciliaciones', 'CONCILIACIONES'], 'optional': False},
    {'labels': ['Conciliaciones Bancarias', 'CONCILIACIONES BANCARIAS', 'Conciliaciones bancarias'], 'optional': False},
    {'labels': ['CARTERA COLECTIVA', 'Cartera Colectiva', 'Cartera colectiva'], 'optional': False},
    {'dynamic_year': True, 'year_prefix': 'CARTERA COLECTIVA ABIERTA ', 'optional': False},
    {'labels': ['Acciones'], 'optional': False},
    {'labels': ['Adicionar documento'], 'optional': False},
]

SAIA_NAVIGATION_STEPS_CCV = [
    {'labels': ['Archivo'], 'optional': False},
    {'title_contains': 'Mis expedientes', 'optional': False},
    {'labels': ['Archivo Central', 'Archivo central', 'ARCHIVO CENTRAL'], 'optional': False},
    {
        'labels': [
            'DIRECCIÓN DE CONTABILIDAD',
            'DIRECCION DE CONTABILIDAD',
            'Dirección de Contabilidad',
            'Direccion de Contabilidad',
        ],
        'optional': False,
    },
    {'labels': ['Conciliaciones', 'CONCILIACIONES'], 'optional': False},
    {'labels': ['Conciliaciones Bancarias', 'CONCILIACIONES BANCARIAS', 'Conciliaciones bancarias'], 'optional': False},
    {'labels': ['CARTERA COLECTIVA', 'Cartera Colectiva', 'Cartera colectiva'], 'optional': False},
    {'dynamic_year': True, 'year_prefix': 'CARTERA COLECTIVA VALOR ', 'optional': False},
    {'labels': ['Acciones'], 'optional': False},
    {'labels': ['Adicionar documento'], 'optional': False},
]


SAIA_NAVIGATION_STEPS_CORBANCA = [
    {'labels': ['Archivo'], 'optional': False},
    {'title_contains': 'Mis expedientes', 'optional': False},
    {'labels': ['Archivo Central', 'Archivo central', 'ARCHIVO CENTRAL'], 'optional': False},
    {
        'labels': [
            'DIRECCIÓN DE CONTABILIDAD',
            'DIRECCION DE CONTABILIDAD',
            'Dirección de Contabilidad',
            'Direccion de Contabilidad',
        ],
        'optional': False,
    },
    {'labels': ['Conciliaciones', 'CONCILIACIONES'], 'optional': False},
    {
        'labels': [
            'Conciliaciones Bancarias',
            'CONCILIACIONES BANCARIAS',
            'Conciliaciones bancarias',
        ],
        'optional': False,
    },
    {
        'labels': [
            'Conciliación bancaria Corbanca',
            'Conciliacion bancaria Corbanca',
            'CONCILIACION BANCARIA CORBANCA',
            'Conciliacion Bancaria Corbanca',
        ],
        'optional': False,
    },
    {'dynamic_year': True, 'year_prefix': '', 'optional': False, 'navigate_into': True},
    {'labels': ['Acciones'], 'optional': False},
    {'labels': ['Adicionar documento'], 'optional': False},
]


SAIA_NAVIGATION_STEPS_COLPATRIA = [
    {'labels': ['Archivo'], 'optional': False},
    {'title_contains': 'Mis expedientes', 'optional': False},
    {'labels': ['Archivo Central', 'Archivo central', 'ARCHIVO CENTRAL'], 'optional': False},
    {
        'labels': [
            'DIRECCIÓN DE CONTABILIDAD',
            'DIRECCION DE CONTABILIDAD',
            'Dirección de Contabilidad',
            'Direccion de Contabilidad',
        ],
        'optional': False,
    },
    {'labels': ['Conciliaciones', 'CONCILIACIONES'], 'optional': False},
    {
        'labels': [
            'Conciliaciones Bancarias',
            'CONCILIACIONES BANCARIAS',
            'Conciliaciones bancarias',
        ],
        'optional': False,
    },
    {
        'labels': [
            'Conciliación bancaria Colpatria',
            'Conciliacion bancaria Colpatria',
            'CONCILIACION BANCARIA COLPATRIA',
            'Conciliacion Bancaria Colpatria',
            'CONCILIACION BANCARIA COLPATIA',
            'Conciliacion Bancaria Colpatia',
        ],
        'optional': False,
    },
    {'dynamic_year': True, 'year_prefix': '', 'optional': False, 'navigate_into': True},
    {'labels': ['Acciones'], 'optional': False},
    {'labels': ['Adicionar documento'], 'optional': False},
]


# ─── Pasos base comunes a todas las conciliaciones bancarias ─────────────────
_STEPS_BASE_CONCILIACION = [
    {'labels': ['Archivo'], 'optional': False},
    {'title_contains': 'Mis expedientes', 'optional': False},
    {'labels': ['Archivo Central', 'Archivo central', 'ARCHIVO CENTRAL'], 'optional': False},
    {
        'labels': [
            'DIRECCIÓN DE CONTABILIDAD',
            'DIRECCION DE CONTABILIDAD',
            'Dirección de Contabilidad',
            'Direccion de Contabilidad',
        ],
        'optional': False,
    },
    {'labels': ['Conciliaciones', 'CONCILIACIONES'], 'optional': False},
    {
        'labels': [
            'Conciliaciones Bancarias',
            'CONCILIACIONES BANCARIAS',
            'Conciliaciones bancarias',
        ],
        'optional': False,
    },
]

_STEPS_YEAR_AND_ADD = [
    {'dynamic_year': True, 'year_prefix': '', 'optional': False, 'navigate_into': True},
    {'labels': ['Acciones'], 'optional': False},
    {'labels': ['Adicionar documento'], 'optional': False},
]


SAIA_NAVIGATION_STEPS_CORREVAL = _STEPS_BASE_CONCILIACION + [
    {
        'labels': [
            'Conciliación bancaria Correval',
            'Conciliacion bancaria Correval',
            'CONCILIACION BANCARIA CORREVAL',
            'Conciliacion Bancaria Correval',
            'CORREVAL',
            'Correval',
        ],
        'optional': False,
    },
] + _STEPS_YEAR_AND_ADD

SAIA_NAVIGATION_STEPS_CORFICOLOMBIANA = _STEPS_BASE_CONCILIACION + [
    {
        'labels': [
            'FIDUCIARIA CORFICOLOMBIANA',
            'Fiduciaria Corficolombiana',
            'fiduciaria corficolombiana',
            'CORFICOLOMBIANA',
            'Corficolombiana',
            'Conciliación bancaria Corficolombiana',
            'Conciliacion bancaria Corficolombiana',
            'CONCILIACION BANCARIA CORFICOLOMBIANA',
        ],
        'optional': False,
    },
] + _STEPS_YEAR_AND_ADD

SAIA_NAVIGATION_STEPS_BBVA = _STEPS_BASE_CONCILIACION + [
    {'labels': ['BANCO BBVA', 'Banco BBVA', 'banco bbva'], 'optional': False},
    {'dynamic_subexpediente': True, 'optional': False, 'navigate_into': True},
    {'labels': ['Acciones'], 'optional': False},
    {'labels': ['Adicionar documento'], 'optional': False},
]

SAIA_NAVIGATION_STEPS_DAVIVIENDA = _STEPS_BASE_CONCILIACION + [
    {
        'labels': [
            'BANCO DAVIVIENDA',
            'Banco Davivienda',
            'banco davivienda',
            'DAVIVIENDA',
            'Davivienda',
            'Conciliación bancaria Davivienda',
            'Conciliacion bancaria Davivienda',
            'CONCILIACION BANCARIA DAVIVIENDA',
        ],
        'optional': False,
    },
    {'dynamic_subexpediente': True, 'optional': False, 'navigate_into': True},
    {'labels': ['Acciones'], 'optional': False},
    {'labels': ['Adicionar documento'], 'optional': False},
]

SAIA_NAVIGATION_STEPS_BOGOTA = _STEPS_BASE_CONCILIACION + [
    {
        'labels': [
            'BANCO DE BOGOTA',
            'Banco de Bogota',
            'BANCO DE BOGOTÁ',
            'Banco de Bogotá',
            'banco de bogota',
            'Conciliación bancaria Banco de Bogota',
            'Conciliacion bancaria Banco de Bogota',
            'CONCILIACION BANCARIA BANCO DE BOGOTA',
        ],
        'optional': False,
    },
    {'dynamic_subexpediente': True, 'optional': False, 'navigate_into': True},
    {'labels': ['Acciones'], 'optional': False},
    {'labels': ['Adicionar documento'], 'optional': False},
]


SAIA_ROUTE_CONFIG = {
    'PEL': {
        'codigo': 'PEL',
        'descripcion': 'Pagos Electronicos PEL',
        'navigation_steps': SAIA_NAVIGATION_STEPS,
    },
    'PRO': {
        'codigo': 'PRO',
        'descripcion': 'Pagos Electronicos PRO',
        'navigation_steps': SAIA_NAVIGATION_STEPS_PRO,
    },
    'RCG': {
        'codigo': 'RCG',
        'descripcion': 'Recibos Caja Consignacion RCG',
        'navigation_steps': SAIA_NAVIGATION_STEPS_RCG,
    },
    'RCI': {
        'codigo': 'RCI',
        'descripcion': 'Recibos Caja Cierre RCI',
        'navigation_steps': SAIA_NAVIGATION_STEPS_RCI,
    },
    'RCP': {
        'codigo': 'RCP',
        'descripcion': 'Reclasificaciones de Cuentas RCP',
        'navigation_steps': SAIA_NAVIGATION_STEPS_RCP,
    },
    'INC': {
        'codigo': 'INC',
        'descripcion': 'Ajustes Contables INC',
        'navigation_steps': SAIA_NAVIGATION_STEPS_INC,
    },
    'IND': {
        'codigo': 'IND',
        'descripcion': 'Ajustes Contables IND',
        'navigation_steps': SAIA_NAVIGATION_STEPS_IND,
    },
    'NIC': {
        'codigo': 'NIC',
        'descripcion': 'Ajustes Contables NIC',
        'navigation_steps': SAIA_NAVIGATION_STEPS_NIC,
    },
    'PP1': {
        'codigo': 'PP1',
        'descripcion': 'Pendientes por Ingreso PEL 2015 -1',
        'navigation_steps': SAIA_NAVIGATION_STEPS_PP1,
    },
    'PP2': {
        'codigo': 'PP2',
        'descripcion': 'Pendientes por Ingreso PEL 2015 -2',
        'navigation_steps': SAIA_NAVIGATION_STEPS_PP2,
    },
    'PP3': {
        'codigo': 'PP3',
        'descripcion': 'Pendientes por Ingreso PEL 2015 -3',
        'navigation_steps': SAIA_NAVIGATION_STEPS_PP3,
    },
    'ECB': {
        'codigo': 'ECB',
        'descripcion': 'Egresos Cheques Bancolombia - Soportes',
        'navigation_steps': SAIA_NAVIGATION_STEPS_ECB,
    },
    'EGC': {
        'codigo': 'EGC',
        'descripcion': 'Egresos Cheques - EGC',
        'navigation_steps': SAIA_NAVIGATION_STEPS_EGC,
    },
    'EGE': {
        'codigo': 'EGE',
        'descripcion': 'Egresos Efectivo - EGE - Soportes',
        'navigation_steps': SAIA_NAVIGATION_STEPS_EGE,
    },
    'PEC': {
        'codigo': 'PEC',
        'descripcion': 'Pagos Electronicos Cierre - PEC - Soportes',
        'navigation_steps': SAIA_NAVIGATION_STEPS_PEC,
    },
    'RICA': {
        'codigo': 'RICA',
        'descripcion': 'Declaracion de Retencion de ICA',
        'navigation_steps': SAIA_NAVIGATION_STEPS_RICA,
    },
    'BANCOLOMBIA': {
        'codigo': 'BANCOLOMBIA',
        'descripcion': 'Conciliaciones Bancarias - Bancolombia',
        'navigation_steps': SAIA_NAVIGATION_STEPS_BANCOLOMBIA,
    },
    'IC1': {'codigo': 'IC1', 'descripcion': 'Impuesto Consumo 2014 Bimestre 1', 'navigation_steps': SAIA_NAVIGATION_STEPS_IC1},
    'IC2': {'codigo': 'IC2', 'descripcion': 'Impuesto Consumo 2014 Bimestre 2', 'navigation_steps': SAIA_NAVIGATION_STEPS_IC2},
    'IC3': {'codigo': 'IC3', 'descripcion': 'Impuesto Consumo 2014 Bimestre 3', 'navigation_steps': SAIA_NAVIGATION_STEPS_IC3},
    'IC4': {'codigo': 'IC4', 'descripcion': 'Impuesto Consumo 2014 Bimestre 4', 'navigation_steps': SAIA_NAVIGATION_STEPS_IC4},
    'IC5': {'codigo': 'IC5', 'descripcion': 'Impuesto Consumo 2014 Bimestre 5', 'navigation_steps': SAIA_NAVIGATION_STEPS_IC5},
    'IC6': {'codigo': 'IC6', 'descripcion': 'Impuesto Consumo 2014 Bimestre 6', 'navigation_steps': SAIA_NAVIGATION_STEPS_IC6},
    'RCC': {
        'codigo': 'RCC',
        'descripcion': 'Recibos de Caja - RCC',
        'navigation_steps': SAIA_NAVIGATION_STEPS_RCC,
    },
    'CCA': {
        'codigo': 'CCA',
        'descripcion': 'Cartera Colectiva Abierta - CCA',
        'navigation_steps': SAIA_NAVIGATION_STEPS_CCA,
    },
    'CCV': {
        'codigo': 'CCV',
        'descripcion': 'Cartera Colectiva Valor - CCV',
        'navigation_steps': SAIA_NAVIGATION_STEPS_CCV,
    },
    'CORBANCA': {
        'codigo': 'CORBANCA',
        'descripcion': 'Conciliacion Bancaria Corbanca',
        'navigation_steps': SAIA_NAVIGATION_STEPS_CORBANCA,
    },
    'COLPATRIA': {
        'codigo': 'COLPATRIA',
        'descripcion': 'Conciliacion Bancaria Colpatria',
        'navigation_steps': SAIA_NAVIGATION_STEPS_COLPATRIA,
    },
    'CORREVAL': {
        'codigo': 'CORREVAL',
        'descripcion': 'Conciliacion Bancaria Correval',
        'navigation_steps': SAIA_NAVIGATION_STEPS_CORREVAL,
    },
    'CORFICOLOMBIANA': {
        'codigo': 'CORFICOLOMBIANA',
        'descripcion': 'Conciliacion Bancaria Fiduciaria Corficolombiana',
        'navigation_steps': SAIA_NAVIGATION_STEPS_CORFICOLOMBIANA,
    },
    'BBVA': {
        'codigo': 'BBVA',
        'descripcion': 'Conciliacion Bancaria Banco BBVA',
        'navigation_steps': SAIA_NAVIGATION_STEPS_BBVA,
    },
    'DAVIVIENDA': {
        'codigo': 'DAVIVIENDA',
        'descripcion': 'Conciliacion Bancaria Banco Davivienda',
        'navigation_steps': SAIA_NAVIGATION_STEPS_DAVIVIENDA,
    },
    'BOGOTA': {
        'codigo': 'BOGOTA',
        'descripcion': 'Conciliacion Bancaria Banco de Bogota',
        'navigation_steps': SAIA_NAVIGATION_STEPS_BOGOTA,
    },
}

SAIA_NAVIGATION_STEPS_CONCILIACIONES = [
    {'labels': ['Archivo'], 'optional': False},
    {'title_contains': 'Mis expedientes', 'optional': False},
    {'labels': ['Archivo Central', 'Archivo central'], 'optional': False},
    {
        'labels': [
            'DIRECCIÓN DE CONTABILIDAD',
            'Dirección de Contabilidad',
            'DIRECCION DE CONTABILIDAD',
            'Direccion de Contabilidad',
        ],
        'optional': False,
    },
    {'labels': ['Conciliaciones', 'CONCILIACIONES'], 'optional': False},
    {
        'labels': [
            'Conciliaciones Bancarias',
            'CONCILIACIONES BANCARIAS',
            'Conciliacion Bancaria',
            'CONCILIACION BANCARIA',
        ],
        'optional': False,
    },
]

DEPENDENCY_LABELS = [
    'DEPENDENCIA DEL CREADOR DEL DOCUMENTO',
    'Dependencia del creador del documento',
]

DEPENDENCY_OPTION = 'Jefatura de Gestión documental, Sistemas de Información e Innovación - (Gestión Documental)'
DEPENDENCY_OPTION_ALIASES = [
    DEPENDENCY_OPTION,
    'Jefatura de Gestion documental, Sistemas de Informacion e Innovacion - (Gestion Documental)',
    'JEFATURA DE GESTIÓN DOCUMENTAL, SISTEMAS DE INFORMACIÓN E INNOVACIÓN - (GESTIÓN DOCUMENTAL)',
    'JEFATURA DE GESTION DOCUMENTAL, SISTEMAS DE INFORMACION E INNOVACION - (GESTION DOCUMENTAL)',
    'Jefatura de GestiÃ³n documental, Sistemas de InformaciÃ³n e InnovaciÃ³n - (GestiÃ³n Documental)',
    'Jefatura de GestiÃƒÂ³n documental, Sistemas de InformaciÃƒÂ³n e InnovaciÃƒÂ³n - (GestiÃƒÂ³n Documental)',
]

SUBJECT_LABELS = [
    'Nombre o asunto',
    'Nombre',
    'Asunto',
]

FILE_INPUT_SELECTORS = [
    'input[type="file"]',
]

CONTINUE_SELECTORS = [
    'button:has-text("Continuar")',
    'input[value*="Continuar" i]',
    'a:has-text("Continuar")',
]

# Señales de éxito fuertes: específicas de la confirmación de carga en SAIA.
# Solas bastan para declarar éxito (si no hay señal de error fuerte).
SUCCESS_TEXTS_STRONG = [
    'exitosamente',
    'documento creado',
    'documento adicionado',
    'documento vinculado',
    'vinculado',
    'insertado',
]

# Señales de éxito débiles: genéricas, solo cuentan cuando subject_confirmed también es True.
SUCCESS_TEXTS = [
    'exitosamente',
    'correctamente',
    'documento creado',
    'documento adicionado',
    'documento vinculado',
    'vinculado',
    'guardado',
    'insertado',
    'cargado',
]

# Señales de error fuertes: indican rechazo explícito de SAIA.
# Anulan cualquier señal positiva, incluyendo subject_confirmed.
# NOTA: 'fall' se excluye deliberadamente — es demasiado amplio y genera falsos
# positivos con 'Tareas Fallidas' del sidebar de SAIA (que aparece en la página
# de confirmación exitosa y hace que has_strong_error=True bloquee toda detección
# de éxito → resultado ambiguo). 'fall' permanece solo en ERROR_TEXTS (débil).
ERROR_TEXTS_STRONG = [
    'campo obligatorio',
    'no se pudo',
    'rechaz',
]

# Señales de error débiles: genéricas, solo cuentan si no hay ninguna positiva.
ERROR_TEXTS = [
    'error',
    'obligatorio',
    'campo obligatorio',
    'no se pudo',
    'rechaz',
    'fall',
]

# Textos que indica que SAIA rechazó el archivo durante la carga del anexo
# (tamaño excedido, tipo no permitido, etc.). Se evalúan dentro de
# _wait_for_attachment_ready para fallar rápido en lugar de esperar el timeout completo.
ATTACHMENT_ERROR_TEXTS = [
    'tamaño máximo',
    'tamaño maximo',
    'excede el límite',
    'excede el limite',
    'tamaño del archivo',
    'tamano del archivo',
    'tipo de archivo no',
    'formato no permit',
    'no se pudo adjuntar',
    'archivo no válido',
    'archivo no valido',
    'restricción de tamaño',
    'restriccion de tamano',
    'supera el límite',
    'supera el limite',
    'no se permite este tipo',
]


