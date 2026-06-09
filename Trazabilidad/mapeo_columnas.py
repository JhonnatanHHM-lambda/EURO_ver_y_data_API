"""
Motor de detección automática de columnas — basado en análisis real de 17 Excel de Euro.
Cubre: COOPISER, EXELA, JG EFECTIVOS, EURO VIEJITA, TEMPORAL BARRANQUILLA,
       APRENDICES, EXTRAS, JIRO, COMPLEMENTOS HUMANOS, TIEMPOS, TIME JOBS,
       ENTREVISTAS (por psicóloga y por fecha), INGRESOS 2024/2025, DOTACION 2018
"""
import unicodedata, re

# ── Mapa de columnas del Excel a campos del modelo ─────────────────────────────
CAMPOS_DESTINO = {

    # ── IDENTIFICACIÓN ──────────────────────────────────────────────────────────
    'documento_id': [
        'cedula', 'cedula de ciudadania', 'cedula ciudadania',
        'cc', 'c.c.', 'documento', 'numero documento', 'nro documento',
        'num cedula', 'no cedula', 'numero de cedula', 'no. cedula',
        'numero cedula', 'documento identidad', 'identificacion',
        'cedula', 'cedula',  # con tilde normalizado
    ],
    'tipo_documento': [
        'tipo documento', 'tipo de documento', 'tipo doc', 'tdoc', 't.i.',
    ],
    'expedida_en': [
        'expedida en', 'lugar expedicion', 'expedicion', 'exp en', 'expedida',
        'fecha expedicion',
    ],

    # ── NOMBRE ─────────────────────────────────────────────────────────────────
    'nombre_completo': [
        # Patrones exactos — NO incluye variantes con "de hijos"
        'nombre y apellido', 'nombre y apellidos',
        'nombre completo', 'nombre apellido', 'nombre y apellido completo',
    ],
    'nombres': [
        'nombre', 'nombres', 'primer nombre',
    ],
    'apellidos': [
        'apellido', 'apellidos', 'primer apellido',
    ],

    # ── SEDE / ÁREA ─────────────────────────────────────────────────────────────
    'sede': [
        'sede', 'centro de operacion', 'centro de operacion', 'sucursal',
        'tienda', 'punto',
    ],

    # ── LABORAL ─────────────────────────────────────────────────────────────────
    'cargo': [
        'cargo', 'cargo desempenado', 'puesto', 'cargo actual',
        'cargo/pasantia', 'cargo pasantia',
    ],
    'tipo_proceso': [
        'tipo proceso', 'tipo de proceso', 'proceso', 'vinculacion',
        'tipo vinculacion', 'modalidad',
    ],
    'centro_costos': [
        'centro costos', 'c.costos', 'c costos', 'codigo centro costos',
        'cod cc', 'centro de costos', 'c. de costos', 'c.c',
    ],
    'jornada': [
        'jornada',
    ],
    'nivel_jerarquico': [
        'nivel jerarquico',
    ],
    'tipo_contrato': [
        'tipo contrato', 'tipo de contrato',
    ],

    # ── FECHAS UNIFICADAS ───────────────────────────────────────────────────────
    'fecha_ingreso': [
        'fecha ingreso', 'f ingreso', 'fecha de ingreso',
        'f. ingreso euro', 'f. ingreso', 'fecha inicio',
        'fecha vinculacion', 'fecha de ingreso',
    ],
    'fecha_retiro': [
        'fecha retiro', 'fecha de retiro',
        'fecha finalizacion', 'fecha de finalizacion',
        'fecha fin', 'fecha de fin',
        'fecha terminacion', 'fecha de terminacion',
        'fecha salida', 'fecha de salida',
        'fecha egreso', 'fecha de egreso',
        # Aprendices / Pasantes: término de práctica
        'term. practica', 'term practica',
        'terminacion practica', 'termino practica',
        'fecha term. practica', 'fecha terminacion practica',
        'fecha term practica',
        # Entrevistas: fecha de finalización del proceso
        'fecha de finalizacion', 'fecha finalizacion',
    ],
    'fecha_nacimiento': [
        'f. nacimiento', 'fecha nacimiento', 'fecha de nacimiento',
    ],
    'fecha_entrevista': [
        'fecha entrevista', 'fecha de entrevista',
    ],

    # ── FECHAS DIVIDIDAS (DIA / MES / AÑO) ──────────────────────────────────────
    '_dia_ingreso':  ['dia ingreso', 'dia de ingreso', 'dia'],
    '_mes_ingreso':  ['mes ingreso', 'mes de ingreso'],
    '_ano_ingreso':  ['ano ingreso', 'anio ingreso', 'year ingreso', 'ano'],

    '_dia_ingreso_sa': ['dia ingreso super a'],
    '_mes_ingreso_sa': ['mes de ingreso super a'],
    '_ano_ingreso_sa': ['ano de ingreso super a'],

    '_dia_retiro':   ['dia retiro', 'dia de retiro'],
    '_mes_retiro':   ['mes retiro', 'mes de retiro'],
    '_ano_retiro':   ['ano retiro', 'anio retiro'],

    '_dia_nacimiento': ['dia nacimiento', 'dia de nacimiento', 'nacimiento dia'],
    '_mes_nacimiento': ['mes nacimiento', 'mes de nacimiento', 'nacimiento mes'],
    '_ano_nacimiento': ['ano nacimiento', 'anio nacimiento', 'nacimiento ano'],

    # ── MOTIVO DE RETIRO ─────────────────────────────────────────────────────────
    'motivo_retiro': [
        'motivo retiro', 'motivo renuncia', 'causa retiro', 'causa',
        'motivo salida', 'motivo de retiro', 'retiro',
    ],

    # ── CONTACTO ─────────────────────────────────────────────────────────────────
    'celular': [
        'celular', 'nro. celular', 'nro celular', 'numero celular', 'movil',
    ],
    'telefono': [
        'telefono', 'tel', 'phone', 'numero telefono', 'fijo', 'telefono',
    ],
    'email': [
        'correo', 'email', 'correo electronico', 'correo electronico',
        'e-mail', 'mail', 'correo e', 'e mail',
    ],
    'direccion': [
        'direccion', 'dir', 'domicilio', 'direccion residencia', 'direccion',
    ],
    'barrio_municipio': [
        'barrio', 'municipio', 'barrio municipio', 'localidad',
        'barrio/sede',  # formato ingresos
    ],

    # ── SEGURIDAD SOCIAL ─────────────────────────────────────────────────────────
    'eps': [
        'eps', 'entidad promotora', 'entidad eps',
    ],
    'pensiones': [
        'pensiones', 'fondo pensiones', 'afp', 'fondo de pensiones', 'pension',
    ],
    'arl': [
        'arl', 'arp', 'a.r.l.', 'a.r.p.', 'aseguradora riesgos',
        'administradora riesgos',
    ],
    'tipo_sangre': [
        'rh', 'grupo sanguineo', 'tipo sangre', 'sangre',
        'grupo rh', 'tipo de sangre',
    ],

    # ── DATOS PERSONALES ─────────────────────────────────────────────────────────
    'sexo': [
        'sexo', 'genero', 'gender', 'gen',
    ],
    'estado_civil': [
        'e. civil', 'ecivil', 'estado civil',
    ],
    'nivel_escolaridad': [
        'escolaridad', 'nivel escolaridad', 'nivel educativo',
        'educacion', 'estudios', 'nivel de escolaridad', 'nivel escolaridad',
    ],
    'estudios_realizados': [
        'estudios realizados',
    ],

    # ── OBSERVACIONES / PSICÓLOGA ────────────────────────────────────────────────
    'observaciones': [
        'observaciones', 'notas', 'comentarios', 'observacion',
        'observaciones generales y/o pendientes', 'observacion',
    ],
    'psicologa': [
        'psicologa', 'psicologo', 'evaluador', 'psicologa evaluadora',
    ],

    # ── CAMPOS APRENDICES ────────────────────────────────────────────────────────
    '_etapa':          ['etapa'],
    '_term_lectiva':   ['term. lectiva', 'term lectiva'],
    '_inicio_practica':['inicio practica'],
    '_term_practica':  ['term. practica', 'term practica'],
    '_area':           ['area', 'area que apoya'],
    '_evaluaciones':   ['evaluaciones'],

    # ── INGRESOS (formato candidatos) ────────────────────────────────────────────
    'nivel_escolaridad': [
        'nivel educativo', 'escolaridad', 'nivel escolaridad',
        'nivel de escolaridad',
    ],
    '_refiere':         ['refiere'],
    '_experiencia':     ['experiencia laboral'],
    '_edad':            ['edad'],
    '_medio_transporte':['medio de trasporte', 'medio de transporte'],

    # ── CAMPOS DE DOTACIÓN ───────────────────────────────────────────────────────
    # (SEGUNDA ENTREGA DOTACION) — se omiten tallas etc., solo se captura lo esencial
}

# Nombres de display para el frontend
CAMPOS_DISPLAY = {
    'documento_id':      'Documento ID',
    'tipo_documento':    'Tipo documento',
    'expedida_en':       'Expedida en',
    'nombre_completo':   'Nombre completo',
    'nombres':           'Nombres',
    'apellidos':         'Apellidos',
    'sede':              'Sede',
    'cargo':             'Cargo',
    'tipo_proceso':      'Tipo de proceso',
    'centro_costos':     'Centro costos',
    # jornada y tipo_contrato se detectan pero NO se guardan en el modelo
    # (se omiten del dropdown para no confundir al usuario)
    'fecha_ingreso':     'Fecha ingreso',
    'fecha_retiro':      'Fecha retiro',
    'fecha_nacimiento':  'Fecha nacimiento',
    'fecha_entrevista':  'Fecha entrevista',
    'motivo_retiro':     'Motivo retiro/causa',
    'celular':           'Celular',
    'telefono':          'Teléfono',
    'email':             'Correo electrónico',
    'direccion':         'Dirección',
    'barrio_municipio':  'Barrio/Municipio',
    'eps':               'EPS',
    'pensiones':         'Pensiones',
    'arl':               'ARL',
    'tipo_sangre':       'Tipo de sangre',
    'sexo':              'Sexo',
    # estado_civil se detecta y sirve como campo destino para valores mal ubicados
    # pero NO se guarda en el modelo (no aparece en el dropdown)
    'nivel_escolaridad': 'Nivel escolaridad',
    'observaciones':     'Observaciones',
    'psicologa':         'Psicóloga',
    # Componentes de fecha dividida (DÍA / MES / AÑO en columnas separadas)
    '_dia_ingreso':      'Día ingreso ↳ fecha dividida',
    '_mes_ingreso':      'Mes ingreso ↳ fecha dividida',
    '_ano_ingreso':      'Año ingreso ↳ fecha dividida',
    '_dia_retiro':       'Día retiro ↳ fecha dividida',
    '_mes_retiro':       'Mes retiro ↳ fecha dividida',
    '_ano_retiro':       'Año retiro ↳ fecha dividida',
    '_dia_nacimiento':   'Día nacimiento ↳ fecha dividida',
    '_mes_nacimiento':   'Mes nacimiento ↳ fecha dividida',
    '_ano_nacimiento':   'Año nacimiento ↳ fecha dividida',
}


def normalizar(s):
    if not s:
        return ''
    s = str(s).lower().strip()
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode('ascii')
    s = re.sub(r'[^a-z0-9\s/.]', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def detectar_mapeo(headers):
    """
    Recibe lista de headers del Excel.
    Retorna dict: { header_original: campo_destino_o_None }
    """
    resultado = {}
    usados = set()

    for header in headers:
        h_norm = normalizar(header)
        if not h_norm:
            resultado[header] = None
            continue

        matched = None
        best_score = 0

        for campo, patrones in CAMPOS_DESTINO.items():
            if campo in usados:
                continue
            for patron in patrones:
                if h_norm == patron:
                    matched = campo
                    best_score = 100
                    break
                if patron in h_norm or h_norm in patron:
                    score = len(set(h_norm.split()) & set(patron.split())) * 10
                    if score > best_score:
                        best_score = score
                        matched = campo
            if best_score == 100:
                break

        if matched:
            usados.add(matched)
        resultado[header] = matched

    return resultado


# Mapa: campo_fecha → (campo_dia, campo_mes, campo_ano)
_SPLIT_DATE_MAP = {
    'fecha_ingreso':    ('_dia_ingreso',    '_mes_ingreso',    '_ano_ingreso'),
    'fecha_retiro':     ('_dia_retiro',     '_mes_retiro',     '_ano_retiro'),
    'fecha_nacimiento': ('_dia_nacimiento', '_mes_nacimiento', '_ano_nacimiento'),
    'fecha_entrevista': ('_dia_nacimiento', '_mes_nacimiento', '_ano_nacimiento'),
}


def refinar_fechas_divididas(df, mapeo):
    """
    Post-procesado inteligente: detecta fechas que llegaron como celda fusionada
    (ej: 'FECHA DE INGRESO' sobre columnas DÍA / MES / AÑO sin nombres propios).

    Cuando una columna mapeada a fecha_ingreso/fecha_retiro/fecha_nacimiento
    contiene solo números pequeños (1–31) y las dos columnas inmediatamente
    siguientes en el DataFrame contienen meses (1–12) y años (1900–2100),
    las reasigna a _dia_ingreso / _mes_ingreso / _ano_ingreso.

    Devuelve un nuevo dict de mapeo corregido.
    """
    mapeo_nuevo = dict(mapeo)
    headers = list(df.columns)

    for i, header in enumerate(headers):
        campo = mapeo.get(header)
        if campo not in _SPLIT_DATE_MAP:
            continue

        # ── Samplear valores de esta columna ─────────────────────────────────
        sample = (
            df[header].replace('', None)
                      .dropna()
                      .head(20)
        )
        if sample.empty:
            continue

        # Convertir a entero filtrando valores no numéricos (ej: "30/ 30*" = anotación)
        nums_dia = []
        for v in sample:
            vstr = str(v).strip()
            if vstr.lower() in ('', 'nan', 'none'):
                continue
            try:
                nums_dia.append(int(float(vstr)))
            except (ValueError, TypeError):
                pass   # saltar anotaciones o textos

        if not nums_dia:
            continue

        # Al menos el 70% deben ser días válidos (tolerancia a anotaciones en la celda)
        dias_validos = [n for n in nums_dia if 1 <= n <= 31]
        if len(dias_validos) / len(nums_dia) < 0.70:
            continue

        # ── Buscar columnas adyacentes sin nombre propio ──────────────────────
        if i + 2 >= len(headers):
            continue

        col_mes = headers[i + 1]
        col_ano = headers[i + 2]

        # La columna mes debe estar sin mapear útil o ser "Unnamed"
        if mapeo.get(col_mes) not in (None, 'fecha_ingreso', 'fecha_retiro'):
            continue

        # Parsear mes tolerando anotaciones como '3/12*'
        nums_mes = []
        for v in df[col_mes].replace('', None).dropna().head(20):
            try:
                nums_mes.append(int(float(str(v).strip())))
            except (ValueError, TypeError):
                pass
        meses_validos = [n for n in nums_mes if 1 <= n <= 12]
        if not nums_mes or len(meses_validos) / len(nums_mes) < 0.70:
            continue

        # Parsear año tolerando anotaciones
        nums_ano = []
        for v in df[col_ano].replace('', None).dropna().head(20):
            try:
                nums_ano.append(int(float(str(v).strip())))
            except (ValueError, TypeError):
                pass
        anos_validos = [n for n in nums_ano if 1900 <= n <= 2100]
        if not nums_ano or len(anos_validos) / len(nums_ano) < 0.70:
            continue

        # ¡Patrón detectado! Reasignar los tres campos
        dia_campo, mes_campo, ano_campo = _SPLIT_DATE_MAP[campo]
        mapeo_nuevo[header]  = dia_campo
        mapeo_nuevo[col_mes] = mes_campo
        mapeo_nuevo[col_ano] = ano_campo

    return mapeo_nuevo
