import io
import re
import unicodedata
import traceback
from datetime import datetime
from difflib import SequenceMatcher

# Grupos sanguíneos válidos: O+, O-, A+, A-, B+, B-, AB+, AB-
# También acepta variantes con espacio: "O POSITIVO", "A NEGATIVO"
_TIPO_SANGRE_RE = re.compile(
    r'^(O|A|B|AB)\s*[+\-]$|'
    r'^(O|A|B|AB)\s*(POSITIVO|NEGATIVO|POS|NEG)$',
    re.IGNORECASE,
)

import openpyxl
import pandas as pd
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, parsers
from drf_yasg.utils import swagger_auto_schema

from EURO_ver_y_data.decoradores import require_permission
from Trazabilidad.models import Sede, EmpleadoTrazabilidad, CargaExcel
from Trazabilidad.serializers import CargaExcelSerializer
from Trazabilidad.mapeo_columnas import detectar_mapeo, CAMPOS_DISPLAY, refinar_fechas_divididas
from Trazabilidad.variantes_sede import resolver_sede
from Trazabilidad.validacion_columnas import validar_mapeo, reubicar_valores_erroneos


def _leer_excel(archivo, sheet_name=None, skip_rows=0):
    """
    Lee un archivo Excel o CSV.
    skip_rows: número de filas a saltear antes del encabezado (útil cuando
               la primera fila es un título y los encabezados reales están más abajo).
    Retorna (DataFrame, nombre_hoja, lista_hojas).
    """
    nombre    = archivo.name.lower()
    contenido = archivo.read()
    hojas     = []

    if nombre.endswith('.csv'):
        df = pd.read_csv(io.BytesIO(contenido), dtype=str,
                         encoding='utf-8-sig', skiprows=skip_rows)
        hoja_usada = 'csv'
    else:
        xf = pd.ExcelFile(io.BytesIO(contenido))
        hojas = xf.sheet_names

        if sheet_name and sheet_name in hojas:
            target = sheet_name
        else:
            # Usar la primera hoja con datos; si la primera está vacía, probar las siguientes
            target = hojas[0]
            for h in hojas:
                df_tmp = pd.read_excel(xf, sheet_name=h, dtype=str,
                                       header=skip_rows if skip_rows else 0, nrows=5)
                if not df_tmp.empty:
                    target = h
                    break

        df = pd.read_excel(xf, sheet_name=target, dtype=str,
                           header=skip_rows if skip_rows else 0)
        hoja_usada = target

    df.columns = [str(c).strip() for c in df.columns]
    df = df.where(pd.notnull(df), '')
    return df, hoja_usada, hojas


def _leer_excel_bytes(contenido_bytes, nombre_archivo, sheet_name=None, skip_rows=0):
    """Versión que acepta bytes directamente (para carga de todas las hojas)."""
    hojas = []
    if nombre_archivo.lower().endswith('.csv'):
        df = pd.read_csv(io.BytesIO(contenido_bytes), dtype=str,
                         encoding='utf-8-sig', skiprows=skip_rows)
        return df, 'csv', []
    xf = pd.ExcelFile(io.BytesIO(contenido_bytes))
    hojas = xf.sheet_names
    target = sheet_name if sheet_name and sheet_name in hojas else hojas[0]
    df = pd.read_excel(xf, sheet_name=target, dtype=str,
                       header=skip_rows if skip_rows else 0)
    df.columns = [str(c).strip() for c in df.columns]
    df = df.where(pd.notnull(df), '')
    return df, target, hojas


# ── Palabras clave que indican INHABILITACIÓN ────────────────────────────────
# Lógica: si alguna de estas está CONTENIDA en el motivo → INHABILITADO
# Se ordenan de más específico a más general para evitar falsos positivos
_PALABRAS_INHABILITADO = {
    # Abandono — la causa más común en estos archivos
    'ABANDONO',             # cubre: ABANDONO, ABANDONO DEL CARGO, ABANDONO INJUSTIFICADO...

    # Conducta / disciplina
    'FRAUDE',
    'ROBO', 'HURTO',
    'CONDUCTA',             # cubre: MALA CONDUCTA, CONDUCTA INADECUADA, etc.
    'DISCIPLINARIO', 'DISCIPLINARIA',
    'SANCION',              # sanción disciplinaria
    'FALTAS DISCIPLINARIAS',

    # Bloqueo / veto explícito
    'INHABILITADO', 'INHABILITADA',
    'VETADO', 'VETADA', 'VETO',
    'BLOQUEADO', 'BLOQUEADA',
    'NO APTO', 'NO APTA',

    # Términos directos de despido por justa causa (SOLO con justa causa)
    'CON JUSTA CAUSA',      # cubre: DESPIDO CON JUSTA CAUSA, TERMINACION CON JUSTA CAUSA
    # NOTA: 'SIN JUSTA CAUSA' está en HABILITADO_SOLO para evitar falsos positivos
    'HURTO INTERNO',
    'AGRESION',             # agresión física/verbal
    'ACOSO',                # acoso laboral/sexual
    # Antecedentes en entrevistas
    'ANTECEDENTE DISCIPLINARIO',
    'ANTECEDENTE EN TRABAJO',   # "Antecedente en trabajo anterior (faltante en inventario)"
    'FALTANTE EN INVENTARIO',
    'FALTANTE DE CAJA',
    'ROBO EN TRABAJO',
}

# ── Motivos que indican HABILITADO (terminación normal, sin problema de conducta) ──
# Si el motivo contiene alguno de estos Y no tiene palabras de inhabilitación → HABILITADO
_PALABRAS_HABILITADO_SOLO = {
    'RENUNCIA VOLUNTARIA', 'RENUNCIA',
    'FIN DE CONTRATO', 'FIN CONTRATO', 'TERMINACION DE CONTRATO', 'TERMINACION CONTRATO',
    'VENCIMIENTO', 'VENCIMIENTO DE CONTRATO',
    'TRASLADO',
    'ACUERDO MUTUO',
    'INCAPACIDAD',
    'MEJOR OFERTA', 'MEJOR OPORTUNIDAD',
    'MOTIVOS PERSONALES', 'MOTIVOS FAMILIARES',
    'LIQUIDACION',
    'RESTRUCTURACION', 'REESTRUCTURACION',
    # Terminación sin culpa del empleado → HABILITADO
    'SIN JUSTA CAUSA',      # el empleador terminó sin motivo válido, pagó indemnización
    'TERMINACION SIN JUSTA CAUSA',
    'DESPIDO SIN JUSTA CAUSA',
}

# Tipos deducibles del nombre de la hoja (clave = hoja normalizada en MAYÚSCULAS)
_TIPO_POR_HOJA = {
    # Formatos principales (COOPISER, JG EFECTIVOS, EXELA, EXTRAS, JIRO...)
    'RETIRADOS':              'RETIRADO',
    'RETIRADOS ACTUAL':       'RETIRADO',
    'RETIRADOS ANTIGUOS':     'RETIRADO',
    'PERSONAL RETIRADO':      'RETIRADO',
    'RETIRADO':               'RETIRADO',
    # Activos/vinculados
    'VINCULADOS':             'EMPLEADO',
    'VINCULADOS ACTIVOS':     'EMPLEADO',
    'ACTIVOS':                'EMPLEADO',
    'ACTIVO':                 'EMPLEADO',
    'MIXTO':                  'EMPLEADO',     # JG EFECTIVOS mixto
    'PERSONAL ACTIVO':        'EMPLEADO',
    # Euro viejita
    'ACTIVOS':                'EMPLEADO',
    'SUSTITUCION PATRONAL':   'EMPLEADO',
    # Aprendices
    'APRENDICES':             'APRENDIZ',
    'AREA OPERATIVA':         'APRENDIZ',
    'AREA ADMINISTRATIVA':    'APRENDIZ',
    'CEDIDO':                 'APRENDIZ',
    'HOJA3':                  'APRENDIZ',
    # Pasantes (estudiantes universitarios en práctica)
    'PASANTIAS':              'PASANTE',
    'PASANTÍAS':              'PASANTE',
    'PASANTE':                'PASANTE',
    'PASANTES':               'PASANTE',
    # Candidatos / ingresos
    'CANDIDATOS ACTIVOS':     'CANDIDATO',
    'INGRESOS':               'CANDIDATO',
}


def _inferir_proceso_y_estado(kwargs, nombre_hoja=''):
    """
    Infiere tipo_proceso y estado_candidato si no están ya establecidos
    en el registro, basándose en:
      1. Nombre de la hoja (RETIRADOS, VINCULADOS, ACTIVOS…)
      2. Presencia de fecha_retiro / motivo_retiro
      3. Palabras clave en el motivo
    """
    hoja_upper = nombre_hoja.upper().strip()

    # Si el nombre de la hoja es una fecha española completa (ej. "19 de Noviembre de 2024")
    # es un registro de INGRESO, no de entrevista.
    # _parsear_fecha solo retorna fecha si hay dígitos de día al inicio, así que
    # "NOVIEMBRE 2024" (hoja de entrevistas) devuelve None y NO colisiona.
    _fecha_de_hoja = _parsear_fecha(nombre_hoja) if nombre_hoja else None

    # Detectar hojas de entrevistas: mes suelto O nombre de psicóloga O palabra clave
    # — excluir si el nombre ya es una fecha completa (eso es INGRESO)
    _es_entrevista = (
        _fecha_de_hoja is None and
        (
            'ENTREVISTA' in hoja_upper or
            'ENTREVISTAS' in hoja_upper or
            any(mes in hoja_upper for mes in ['ENERO','FEBRERO','MARZO','ABRIL','MAYO','JUNIO',
                                               'JULIO','AGOSTO','SEPTIEMBRE','OCTUBRE','NOVIEMBRE','DICIEMBRE'])
        )
    )

    # ── Inyectar fecha_ingreso desde el nombre de la hoja si aplica ──────────
    # Solo si la hoja es una fecha completa y el registro aún no tiene fecha_ingreso.
    # Esto permite archivos donde cada hoja es el día de ingreso (ej. "19 de Noviembre de 2024").
    if _fecha_de_hoja and not kwargs.get('fecha_ingreso'):
        kwargs['fecha_ingreso'] = _fecha_de_hoja

    # ── tipo_proceso ─────────────────────────────────────────────────────────
    _TIPOS_VALIDOS_PROCESO = {
        'EMPLEADO', 'RETIRADO', 'CANDIDATO', 'APRENDIZ',
        'SELECCIONADO', 'ENTREVISTADO', 'PASANTE',
    }
    # Descartar valores inválidos (ej: "Tiempo Completo" de la columna MODALIDAD)
    tp_actual = str(kwargs.get('tipo_proceso', '') or '').upper().strip()
    if tp_actual and tp_actual not in _TIPOS_VALIDOS_PROCESO:
        kwargs.pop('tipo_proceso', None)

    if not kwargs.get('tipo_proceso'):
        if _fecha_de_hoja:
            # Hoja = fecha de ingreso → todos son ingresos → EMPLEADO
            kwargs['tipo_proceso'] = 'EMPLEADO'
        elif _es_entrevista:
            kwargs['tipo_proceso'] = 'ENTREVISTADO'
        else:
            tipo_hoja = _TIPO_POR_HOJA.get(hoja_upper)
            if tipo_hoja:
                kwargs['tipo_proceso'] = tipo_hoja
            elif kwargs.get('fecha_retiro') or kwargs.get('motivo_retiro'):
                kwargs['tipo_proceso'] = 'RETIRADO'
            elif kwargs.get('fecha_ingreso'):
                kwargs['tipo_proceso'] = 'EMPLEADO'
            # sin datos suficientes → queda vacío

    # ENTREVISTADO + fecha_ingreso → fue efectivamente contratado → EMPLEADO
    # (la fecha_entrevista registra la entrevista; la fecha_ingreso confirma la vinculación)
    # No afecta archivos de entrevistas ya mapeados: en esos archivos la fecha va
    # a fecha_entrevista, no a fecha_ingreso, así que esta condición no se activa.
    if kwargs.get('tipo_proceso') == 'ENTREVISTADO' and kwargs.get('fecha_ingreso'):
        kwargs['tipo_proceso'] = 'EMPLEADO'

    # Si el tipo es EMPLEADO/APRENDIZ/PASANTE y tiene fecha o motivo de retiro → RETIRADO
    # - EMPLEADO: ocurre en COOPISER VINCULADOS que mezcla activos y retirados
    # - APRENDIZ/PASANTE: cuando ya tiene TERM. PRACTICA (fecha_retiro) fue completado
    if (kwargs.get('tipo_proceso') in ('EMPLEADO', 'APRENDIZ', 'PASANTE') and
            (kwargs.get('fecha_retiro') or kwargs.get('motivo_retiro'))):
        kwargs['tipo_proceso'] = 'RETIRADO'

    # ── estado_candidato ─────────────────────────────────────────────────────
    if not kwargs.get('estado_candidato') or kwargs['estado_candidato'] == 'REGISTRADO':
        motivo = (
            str(kwargs.get('motivo_retiro', '') or '') + ' ' +
            str(kwargs.get('observaciones', '') or '')
        ).upper().strip()

        # 1. Verificar palabras que indican inhabilitación (prioridad máxima)
        if motivo and any(p in motivo for p in _PALABRAS_INHABILITADO):
            kwargs['estado_candidato'] = 'INHABILITADO'

        # 2. Terminaciones normales explícitas → HABILITADO
        elif motivo and any(p in motivo for p in _PALABRAS_HABILITADO_SOLO):
            kwargs['estado_candidato'] = 'HABILITADO'

        # 3. Sin motivo pero tiene tipo_proceso definido → HABILITADO
        elif kwargs.get('tipo_proceso') in ('EMPLEADO', 'APRENDIZ', 'PASANTE', 'SELECCIONADO', 'RETIRADO'):
            kwargs['estado_candidato'] = 'HABILITADO'

        # 4. ENTREVISTADO: inferir desde observaciones
        elif kwargs.get('tipo_proceso') == 'ENTREVISTADO':
            _palabras_seleccionado = (
                'CONTINUA PARA CONTRATACION', 'CONTINÚA PARA CONTRATACION',
                'CONTINUA PARA CONTRATACIÓN', 'CONTINÚA PARA CONTRATACIÓN',
                'SE VINCULA', 'INGRESA CON', 'INGRESO EL', 'INGRESA EL',
                'PARA CONTRATACION', 'PARA CONTRATACIÓN',
            )
            if motivo and any(p in motivo for p in _palabras_seleccionado):
                kwargs['estado_candidato'] = 'HABILITADO'   # fue seleccionado
            else:
                kwargs['estado_candidato'] = 'REGISTRADO'   # entrevistado, sin decisión clara

        # 5. CANDIDATO sin más info → queda REGISTRADO


# Nombres de meses en español
_MESES_ES = {
    'ENERO':1,'FEBRERO':2,'MARZO':3,'ABRIL':4,'MAYO':5,'JUNIO':6,
    'JULIO':7,'AGOSTO':8,'SEPTIEMBRE':9,'OCTUBRE':10,'NOVIEMBRE':11,'DICIEMBRE':12,
    'ENE':1,'FEB':2,'MAR':3,'ABR':4,'JUN':6,'JUL':7,'AGO':8,
    'SEP':9,'OCT':10,'NOV':11,'DIC':12,
}


def _parsear_fecha(valor):
    if not valor or str(valor).strip() in ('', 'nan', 'None'):
        return None
    v = str(valor).strip()

    # Excel serial date
    try:
        serial = int(float(v))
        if 1000 < serial < 100000:
            base = datetime(1899, 12, 30)
            return (base + __import__('datetime').timedelta(days=serial)).date()
    except (ValueError, OverflowError):
        pass

    # Formatos numéricos estándar (incluyendo timestamps pandas)
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%d/%m/%y',
                '%Y/%m/%d', '%m/%d/%Y', '%d-%m-%y', '%Y.%m.%d',
                '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M:%S.%f'):
        try:
            return datetime.strptime(v, fmt).date()
        except ValueError:
            continue

    # Fechas en español: "01 MARZO DE 2017", "01 DE MARZO DE 2017",
    # "1 de marzo de 2017", "01 MARZO 2017"
    import re as _re
    m = _re.match(
        r'^(\d{1,2})\s+(?:DE\s+)?([A-ZÀ-ÿ]+)\s+(?:DE\s+)?(\d{4})$',
        v.upper().strip(),
    )
    if m:
        try:
            dia = int(m.group(1))
            mes = _MESES_ES.get(m.group(2).strip())
            ano = int(m.group(3))
            if mes and 1 <= dia <= 31 and 1900 <= ano <= 2100:
                return datetime(ano, mes, dia).date()
        except (ValueError, TypeError):
            pass

    return None


def _combinar_fecha_dma(dia, mes, ano):
    """Combina día, mes y año separados en un objeto date."""
    try:
        d, m, a = int(float(str(dia))), int(float(str(mes))), int(float(str(ano)))
        if 1900 < a < 2100 and 1 <= m <= 12 and 1 <= d <= 31:
            return datetime(a, m, d).date()
    except Exception:
        pass
    return None


class PreviewExcelView(APIView):
    parser_classes = [parsers.MultiPartParser]

    @swagger_auto_schema(operation_summary='Preview y detección de columnas del Excel', tags=['Carga Excel'])
    @require_permission(['can_upload_excel'], app_label='Usuarios')
    def post(self, request):
        archivo    = request.FILES.get('archivo')
        sheet_name = request.data.get('sheet_name', '')
        skip_rows  = int(request.data.get('skip_rows', 0) or 0)
        if not archivo:
            return Response({'error': 'Adjunta un archivo Excel o CSV.'}, status=400)

        try:
            df, hoja_usada, hojas = _leer_excel(archivo,
                                                 sheet_name=sheet_name or None,
                                                 skip_rows=skip_rows)
        except Exception as e:
            return Response({'error': f'No se pudo leer el archivo: {e}'}, status=400)

        if df.empty:
            return Response({'error': 'El archivo está vacío o no tiene datos válidos.'}, status=400)

        headers = list(df.columns)
        mapeo   = detectar_mapeo(headers)
        # Refinamiento: detectar fechas divididas (DÍA/MES/AÑO en celdas fusionadas)
        mapeo   = refinar_fechas_divididas(df, mapeo)
        preview = df.head(5).to_dict(orient='records')

        campos_disponibles = [
            {'value': k, 'label': v} for k, v in CAMPOS_DISPLAY.items()
        ]

        # ── Filtrar filas vacías para el conteo de sedes ─────────────────────
        # Solo considerar filas con al menos 2 valores reales (excluir filas de Excel vacías)
        _mascara_real = df.apply(
            lambda r: sum(
                1 for h, v in r.items()
                if h != '__hoja_origen__'
                and str(v).strip() not in ('', 'nan', 'None', 'NaN', '--', '-')
            ) >= 2,
            axis=1,
        )
        df_real = df[_mascara_real]

        # ── Detectar sedes presentes en el Excel (incluye vacíos) ────────────
        sedes_detectadas = []
        col_sede = next((h for h, campo in mapeo.items() if campo == 'sede'), None)
        if col_sede and col_sede in df_real.columns:
            serie = df_real[col_sede].fillna('').str.strip().str.upper()
            conteo_con_valor = (
                serie[serie != '']
                .value_counts()
                .head(15)
                .to_dict()
            )
            vacios = int((serie == '').sum())
            sedes_detectadas = [
                {'codigo': k, 'total': v}
                for k, v in conteo_con_valor.items()
            ]
            # Registros con sede vacía → incluir datos de identificación
            if vacios > 0:
                filas_vacias = df_real[serie == '']
                # Identificar columnas clave según el mapeo detectado
                def _col(campo):
                    return next((h for h, c in mapeo.items() if c == campo), None)

                cc    = _col('documento_id')
                nom   = _col('nombre_completo') or _col('nombres')
                ape   = _col('apellidos')
                cel   = _col('celular') or _col('telefono')
                mot   = _col('motivo_retiro')

                registros_vacios = []
                for idx, row in filas_vacias.iterrows():  # sin límite — paginación en frontend
                    r = {
                        'df_index': int(idx),   # clave única para asignación individual
                        'cedula':  str(row.get(cc,  '') or '').strip() if cc  else '',
                        'celular': str(row.get(cel, '') or '').strip() if cel else '',
                        'motivo':  str(row.get(mot, '') or '').strip() if mot else '',
                    }
                    nombre = str(row.get(nom, '') or '').strip() if nom else ''
                    if ape:
                        apellido = str(row.get(ape, '') or '').strip()
                        r['nombre'] = f'{nombre} {apellido}'.strip()
                    else:
                        r['nombre'] = nombre
                    registros_vacios.append(r)

                sedes_detectadas.append({
                    'codigo':    '',
                    'total':     vacios,
                    'sin_sede':  True,
                    'registros': registros_vacios,
                })

        advertencias = validar_mapeo(df, mapeo)

        return Response({
            'headers':            headers,
            'mapeo_sugerido':     mapeo,
            'preview':            preview,
            'total_filas':        len(df_real),  # solo filas con datos reales
            'campos_disponibles': campos_disponibles,
            'hojas':              hojas,
            'hoja_activa':        hoja_usada,
            'sedes_detectadas':   sedes_detectadas,
            'tiene_col_sede':     col_sede is not None,
            'advertencias_mapeo': advertencias,
        })


def _normalizar_motivo(motivo):
    """Normaliza un motivo de retiro para comparación fuzzy."""
    if not motivo:
        return ''
    m = str(motivo).strip().upper()
    m = unicodedata.normalize('NFKD', m).encode('ascii', 'ignore').decode('ascii')
    m = re.sub(r'[^A-Z0-9\s]', ' ', m)
    return re.sub(r'\s+', ' ', m).strip()


def _motivos_similares(m1, m2, umbral=0.80):
    """
    True si dos motivos de retiro son suficientemente similares para
    considerarlos el mismo registro y fusionar.

    Casos que fusiona:
      'TERMINACION' vs 'TERMINACION '        → normalización exacta
      'TERMINACION' vs 'TERMINACION DE CONTRATO' → uno contiene al otro
      'ABANDONO'    vs 'ABANDONO DEL CARGO'  → uno contiene al otro
      'RENUNCIA'    vs 'RENUNCIA VOLUNTARIA' → uno contiene al otro

    Casos que NO fusiona (carga separado):
      'TERMINACION' vs 'RENUNCIA'            → ratio ~0.35
      'TERMINACION' vs 'ABANDONO'            → ratio ~0.30
      ''            vs 'RENUNCIA'            → motivos distintos
    """
    a, b = _normalizar_motivo(m1), _normalizar_motivo(m2)
    if a == b:                          # coincidencia exacta (incluye ambos vacíos)
        return True
    if not a or not b:                  # uno vacío y otro no → distintos
        return False
    if a in b or b in a:               # uno contiene al otro
        return True
    return SequenceMatcher(None, a, b).ratio() >= umbral


def _extraer_campos_clave(fila, mapeo):
    """
    Extrae (documento_id, fecha_ingreso, fecha_retiro, nombre, motivo_retiro, sede_valor)
    de una fila usando el mapeo de columnas. Maneja fechas divididas.
    sede_valor es el string crudo de la columna sede en el Excel.
    """
    doc_id = None
    fi = fr = None
    nombre = motivo = sede_valor = ''
    parts = {}

    for header, campo in mapeo.items():
        v = str(fila.get(header, '')).strip()
        if not v or v.lower() in ('nan', 'none', ''):
            continue
        if campo == 'documento_id':
            doc_id = v
        elif campo == 'nombre_completo':
            nombre = v
        elif campo == 'nombres':
            nombre = (v + ' ' + nombre).strip()
        elif campo == 'apellidos':
            nombre = (nombre + ' ' + v).strip()
        elif campo == 'fecha_ingreso':
            fi = _parsear_fecha(v)
        elif campo == 'fecha_retiro':
            fr = _parsear_fecha(v)
        elif campo == 'motivo_retiro':
            motivo = v
        elif campo == 'sede':
            sede_valor = v
        elif campo and campo.startswith('_'):
            parts[campo] = v

    # Fechas divididas
    if not fi:
        d, m, a = parts.get('_dia_ingreso', ''), parts.get('_mes_ingreso', ''), parts.get('_ano_ingreso', '')
        if d and m and a:
            fi = _combinar_fecha_dma(d, m, a)
    if not fr:
        d, m, a = parts.get('_dia_retiro', ''), parts.get('_mes_retiro', ''), parts.get('_ano_retiro', '')
        if d and m and a:
            fr = _combinar_fecha_dma(d, m, a)

    return doc_id, fi, fr, nombre.strip(), motivo.strip(), sede_valor.strip()


def _resolver_sede_id_clave(sede_valor, df_index,
                             mapeo_sedes_obj, mapeo_filas_obj,
                             sedes_por_codigo, sedes_por_nombre,
                             sede_fallback_id):
    """
    Resuelve sede_id para check_only usando la misma prioridad que la carga real.
    Retorna el ID de la sede (int) o sede_fallback_id si no se resuelve.
    """
    # 1. Mapeo individual por fila (sede asignada manualmente para esa fila)
    s = mapeo_filas_obj.get(str(df_index))
    if s:
        return s.id

    val_upper = sede_valor.upper().strip()

    # 2. Mapeo explícito del usuario (paso "Resolver Sedes")
    s = mapeo_sedes_obj.get(val_upper if val_upper else '')
    if s:
        return s.id

    # 3. Variantes canónicas
    if val_upper:
        codigo = resolver_sede(sede_valor)
        if codigo:
            s = sedes_por_codigo.get(codigo.upper())
            if s:
                return s.id
        # Código o nombre exacto
        s = sedes_por_codigo.get(val_upper) or sedes_por_nombre.get(val_upper)
        if s:
            return s.id

    # 4. Fallback
    return sede_fallback_id


class CargarExcelView(APIView):
    parser_classes = [parsers.MultiPartParser]

    @swagger_auto_schema(operation_summary='Cargar Excel a la tabla de trazabilidad', tags=['Carga Excel'])
    @require_permission(['can_upload_excel'], app_label='Usuarios')
    def post(self, request):
        import json
        archivo          = request.FILES.get('archivo')
        sede_id          = request.data.get('sede_id')
        origen_datos     = request.data.get('origen_datos', '').strip().upper()
        sheet_name       = request.data.get('sheet_name', '')
        check_only       = request.data.get('check_only', '0') == '1'
        modo_duplicados  = request.data.get('modo_duplicados', 'separado')
        skip_rows        = int(request.data.get('skip_rows', 0) or 0)
        todas_las_hojas  = request.data.get('todas_las_hojas', '0') == '1'

        mapeo_sedes_raw = request.data.get('mapeo_sedes', '{}')
        try:
            mapeo_sedes_ids = json.loads(mapeo_sedes_raw)
        except Exception:
            mapeo_sedes_ids = {}

        mapeo_filas_raw = request.data.get('mapeo_filas', '{}')
        try:
            mapeo_filas_ids = {str(k): str(v) for k, v in json.loads(mapeo_filas_raw).items()}
        except Exception:
            mapeo_filas_ids = {}

        mapeo_raw = request.data.get('mapeo', '{}')
        try:
            mapeo = json.loads(mapeo_raw)
        except Exception:
            return Response({'error': 'Mapeo de columnas inválido.'}, status=400)

        if not archivo:
            return Response({'error': 'Adjunta un archivo.'}, status=400)

        # Leer el archivo (guardar bytes para modo todas-las-hojas)
        contenido_bytes = archivo.read()
        archivo_nombre  = archivo.name

        class _FakeFile:
            """Envuelve bytes para reutilizar _leer_excel."""
            def __init__(self, b, n): self._b = b; self.name = n
            def read(self): return self._b

        try:
            df, hoja_usada, todas_hojas = _leer_excel(
                _FakeFile(contenido_bytes, archivo_nombre),
                sheet_name=sheet_name or None,
                skip_rows=skip_rows,
            )
        except Exception as e:
            return Response({'error': f'No se pudo leer el archivo: {e}'}, status=400)

        # Modo "todas las hojas": acumular DataFrames de cada hoja
        if todas_las_hojas and todas_hojas and not check_only:
            hojas_a_cargar = todas_hojas
        else:
            hojas_a_cargar = [hoja_usada]

        # ── Modo pre-escaneo: detectar duplicados sin cargar ─────────────────────
        if check_only:
            # Construir caches de sedes para resolver sede por fila
            _sedes_por_id     = {str(s.id): s for s in Sede.objects.filter(estado=True)}
            _sedes_por_codigo = {s.codigo.upper(): s for s in Sede.objects.filter(estado=True)}
            _sedes_por_nombre = {s.nombre.upper(): s for s in Sede.objects.filter(estado=True)}

            _mapeo_sedes_obj = {}
            for val_excel, sid in mapeo_sedes_ids.items():
                s = _sedes_por_id.get(str(sid))
                if s:
                    _mapeo_sedes_obj[val_excel.upper().strip()] = s

            _NO_SEDE = '__NO_SEDE__'
            _mapeo_filas_obj  = {}
            _filas_sin_sede   = set()
            for row_idx, sid in mapeo_filas_ids.items():
                if sid == _NO_SEDE:
                    _filas_sin_sede.add(str(row_idx))
                else:
                    s = _sedes_por_id.get(str(sid))
                    if s:
                        _mapeo_filas_obj[str(row_idx)] = s

            _sede_real = sede_id if sede_id and sede_id != '__NO_SEDE__' else None
            _sede_fallback_id = int(_sede_real) if _sede_real else None

            filas_info = []
            for idx, fila in df.iterrows():
                doc_id, fi, fr, nombre, motivo, sede_valor = _extraer_campos_clave(fila, mapeo)
                if doc_id:
                    if str(idx) in _filas_sin_sede:
                        sid = None  # sin-sede explícito
                    else:
                        sid = _resolver_sede_id_clave(
                            sede_valor, idx,
                            _mapeo_sedes_obj, _mapeo_filas_obj,
                            _sedes_por_codigo, _sedes_por_nombre,
                            _sede_fallback_id,
                        )
                    filas_info.append((idx + 2, doc_id, fi, fr, nombre, motivo, sid))

            docs_unicos = list({f[1] for f in filas_info})

            # {(doc_id, fi, fr, sede_id): [motivo1, motivo2, ...]}
            existentes_dict = {}
            for doc, fi, fr, mot, sid in EmpleadoTrazabilidad.objects.filter(
                documento_id__in=docs_unicos, estado=True
            ).values_list('documento_id', 'fecha_ingreso', 'fecha_retiro', 'motivo_retiro', 'sede_id'):
                existentes_dict.setdefault((doc, fi, fr, sid), []).append(mot or '')

            duplicados = []
            for fila_num, doc_id, fi, fr, nombre, motivo, sid in filas_info:
                motivos_existentes = existentes_dict.get((doc_id, fi, fr, sid), [])
                if motivos_existentes and any(_motivos_similares(motivo, m) for m in motivos_existentes):
                    duplicados.append({
                        'fila':          fila_num,
                        'documento_id':  doc_id,
                        'nombre':        nombre,
                        'fecha_ingreso': str(fi) if fi else None,
                        'fecha_retiro':  str(fr) if fr else None,
                        'motivo':        motivo or None,
                    })

            return Response({'duplicados': duplicados, 'total': len(duplicados)})

        # ── Validaciones para carga real ─────────────────────────────────────────
        # '__NO_SEDE__' es el sentinel del frontend para "Sin sede / No definida"
        sede_id_original = sede_id   # guardar antes de sobreescribir
        sede_id_real = sede_id if sede_id and sede_id != '__NO_SEDE__' else None

        if not sede_id_real:
            # Casos válidos sin sede numérica:
            # 1. El usuario eligió explícitamente "Sin sede / No definida" como global
            # 2. Hay asignación individual por filas (mapeo_filas con __NO_SEDE__)
            eligio_sin_sede  = sede_id_original == '__NO_SEDE__'
            tiene_asignacion = bool(mapeo_filas_ids)
            if not eligio_sin_sede and not tiene_asignacion:
                return Response({'error': 'Selecciona una sede o asigna sede a los registros.'}, status=400)
            sede = None
        else:
            try:
                sede = Sede.objects.get(id=sede_id_real, estado=True)
            except Sede.DoesNotExist:
                return Response({'error': 'Sede no encontrada.'}, status=404)

        # Usar sede_id_real (int o None) para el resto de la lógica
        sede_id = sede_id_real

        if not origen_datos:
            return Response({'error': 'Especifica el origen de datos.'}, status=400)

        errores    = []
        exitosos   = 0
        fusionados = 0
        nombre_archivo = archivo_nombre

        # En modo "todas las hojas": concatenar todos los DataFrames en uno solo
        if todas_las_hojas and len(todas_hojas) > 1:
            dfs = []
            xf_todas = pd.ExcelFile(io.BytesIO(contenido_bytes))
            for h in todas_hojas:
                try:
                    # Detectar automáticamente si la hoja necesita saltar una fila de título
                    # (cuando la fila 1 es un título fusionado y los headers reales están en fila 2)
                    _skip = skip_rows  # usar el skip global como punto de partida
                    if _skip == 0:
                        df_test = pd.read_excel(xf_todas, sheet_name=h, dtype=str, nrows=2, header=0)
                        df_test.columns = [str(c).strip() for c in df_test.columns]
                        # Si la primera columna parece un título (>50% columnas son "Unnamed")
                        _n_unnamed = sum(1 for c in df_test.columns if c.lower().startswith('unnamed'))
                        if _n_unnamed / max(len(df_test.columns), 1) > 0.5:
                            _skip = 1   # el título ocupa fila 1, encabezados reales en fila 2

                    df_h = pd.read_excel(xf_todas, sheet_name=h, dtype=str, header=_skip)
                    df_h.columns = [str(c).strip() for c in df_h.columns]
                    df_h = df_h.where(pd.notnull(df_h), '')
                    df_h['__hoja_origen__'] = h
                    # Número de fila dentro de esa hoja (para reportar correctamente en errores)
                    df_h['__fila_hoja__'] = range((_skip or 0) + 2, len(df_h) + (_skip or 0) + 2)
                    dfs.append(df_h)
                except Exception:
                    pass
            if dfs:
                df = pd.concat(dfs, ignore_index=True, sort=False).fillna('')

                # ── Fusionar columnas sinónimas en el concat ──────────────────
                # Cuando hojas distintas usan CC / CEDULA / C.C. / DOCUMENTO
                # para la cédula, el concat las trata como columnas separadas.
                # Se detectan TODOS los grupos de sinónimos y se fusionan.
                from Trazabilidad.mapeo_columnas import normalizar, CAMPOS_DESTINO
                _cols_df = list(df.columns)
                _procesados = set()

                for campo, patrones in CAMPOS_DESTINO.items():
                    # Buscar TODAS las columnas que coincidan con los patrones de este campo
                    _grupo = []
                    for h in _cols_df:
                        # Proteger columnas internas del sistema (empiezan con __)
                        if h in _procesados or h.startswith('__'):
                            continue
                        h_norm = normalizar(h)
                        if not h_norm:
                            continue
                        for patron in patrones:
                            if h_norm == patron or patron in h_norm or h_norm in patron:
                                _grupo.append(h)
                                break

                    if len(_grupo) <= 1:
                        continue

                    # Fusionar: primer col = destino, resto = fuentes adicionales
                    col_dest = _grupo[0]
                    _procesados.add(col_dest)
                    for col_src in _grupo[1:]:
                        if col_src not in df.columns:
                            continue
                        mask = (df[col_dest] == '') & (df[col_src] != '')
                        df.loc[mask, col_dest] = df.loc[mask, col_src]
                        df.drop(columns=[col_src], inplace=True)
                        _procesados.add(col_src)
                # ─────────────────────────────────────────────────────────────

                hoja_label = f'TODAS LAS HOJAS ({len(dfs)})'
            else:
                hoja_label = hoja_usada
        else:
            df['__hoja_origen__'] = hoja_usada
            df['__fila_hoja__']   = range(2, len(df) + 2)
            hoja_label = hoja_usada

        # Contar solo filas con al menos 2 valores reales (excluir vacías de Excel)
        total_filas = sum(
            1 for _, fila in df.iterrows()
            if sum(
                1 for h, v in fila.items()
                if h != '__hoja_origen__'
                and str(v).strip() not in ('', 'nan', 'None', 'NaN', '--', '-')
            ) >= 2
        )

        # Crear el registro de carga ANTES del loop para poder vincularlo a cada empleado
        registro_carga = CargaExcel.objects.create(
            sede=sede,
            nombre_archivo=nombre_archivo,
            hoja=hoja_label,  # "TODAS LAS HOJAS (N)" o nombre de hoja individual
            origen_datos=origen_datos,
            total_registros=total_filas,
            exitosos=0,
            fallidos=0,
            cargado_por=request.user,
        )

        # Cache de sedes para resolver por código/nombre sin N+1 queries
        sedes_cache = {s.codigo.upper(): s for s in Sede.objects.filter(estado=True)}
        sedes_cache.update({s.nombre.upper(): s for s in Sede.objects.filter(estado=True)})

        # Cache de sedes por id (para resolver mapeo_sedes del frontend)
        sedes_por_id     = {str(s.id): s for s in Sede.objects.filter(estado=True)}
        # Cache por código/nombre para fallback por variantes
        sedes_por_codigo = {s.codigo.upper(): s for s in Sede.objects.filter(estado=True)}
        sedes_por_nombre = {s.nombre.upper(): s for s in Sede.objects.filter(estado=True)}
        # Pre-resolver mapeo_sedes a objetos Sede
        mapeo_sedes_obj = {}
        for val_excel, sid in mapeo_sedes_ids.items():
            s = sedes_por_id.get(str(sid))
            if s:
                mapeo_sedes_obj[val_excel.upper().strip()] = s

        # Sentinel que el frontend usa cuando el usuario elige "Sin sede / No definida"
        NO_SEDE_SENTINEL = '__NO_SEDE__'

        # Pre-resolver mapeo_filas (row_idx → Sede o None para sin-sede explícito)
        mapeo_filas_obj  = {}   # row_idx → Sede object
        filas_sin_sede   = set()  # row_idx con sede = None explícito
        for row_idx, sid in mapeo_filas_ids.items():
            if sid == NO_SEDE_SENTINEL:
                filas_sin_sede.add(str(row_idx))
            else:
                s = sedes_por_id.get(str(sid))
                if s:
                    mapeo_filas_obj[str(row_idx)] = s
        CAMPOS_IGNORAR_EXCEL = {'origen_datos'}

        # Pre-construir dict de existentes para modo fusionar (1 query, no N)
        # {(doc_id, fi, fr, sede_id): [motivo1, motivo2, ...]}
        existentes_dict = {}
        if modo_duplicados == 'fusionar':
            for doc, fi, fr, mot, sid in (
                EmpleadoTrazabilidad.objects.filter(estado=True)
                .values_list('documento_id', 'fecha_ingreso', 'fecha_retiro', 'motivo_retiro', 'sede_id')
            ):
                existentes_dict.setdefault((doc, fi, fr, sid), []).append(mot or '')

        # Pre-cargar nombres actuales en BD por cédula para detectar incoherencias
        # {documento_id: nombre_completo_normalizado}
        nombres_en_bd = {
            doc: nom
            for doc, nom in EmpleadoTrazabilidad.objects.filter(estado=True)
            .values_list('documento_id', 'nombre_completo')
            .order_by('documento_id', '-creado')
            .distinct('documento_id')
        }

        for idx, fila in df.iterrows():
            fila_num = idx + 2
            try:
                # Saltar filas completamente vacías (Excel tiene filas en blanco al final)
                valores_utiles = sum(
                    1 for h, v in fila.items()
                    if h != '__hoja_origen__'
                    and str(v).strip() not in ('', 'nan', 'None', 'NaN', '--', '-')
                )
                if valores_utiles < 2:
                    continue   # fila vacía → ignorar sin contar como error

                # Sede inicial: prioridad → sin-sede explícito → mapeo por fila → fallback
                _idx_str = str(idx)
                if _idx_str in filas_sin_sede:
                    sede_inicial = None                          # usuario eligió "No definida"
                else:
                    sede_inicial = mapeo_filas_obj.get(_idx_str) or sede
                kwargs = {
                    'origen_datos': origen_datos,
                    'sede': sede_inicial,
                    'fuente_carga': nombre_archivo,
                    'cargado_por': request.user,
                }

                for header, campo in mapeo.items():
                    if not campo or campo == 'ignorar':
                        continue
                    # Campos que vienen del formulario — ignorar valor del Excel
                    if campo in CAMPOS_IGNORAR_EXCEL:
                        continue
                    valor = str(fila.get(header, '')).strip()
                    if not valor or valor in ('nan', 'None', 'NaN'):
                        valor = ''

                    if campo in ('fecha_ingreso', 'fecha_retiro', 'fecha_nacimiento', 'fecha_entrevista'):
                        kwargs[campo] = _parsear_fecha(valor)
                    elif campo == 'sede':
                        val_upper = valor.upper().strip()
                        # 1. Usar mapeo explícito del usuario (paso "Resolver Sedes")
                        #    '' → aplica a filas con sede vacía
                        clave_busqueda = val_upper if val_upper else ''
                        sede_excel = mapeo_sedes_obj.get(clave_busqueda)
                        # 2. Si hay valor y no hay mapeo explícito → variantes canónicas
                        if not sede_excel and val_upper:
                            codigo = resolver_sede(valor)
                            if codigo:
                                sede_excel = sedes_por_codigo.get(codigo.upper())
                        # 3. Código o nombre exacto
                        if not sede_excel and val_upper:
                            sede_excel = (sedes_por_codigo.get(val_upper) or
                                          sedes_por_nombre.get(val_upper))
                        if sede_excel:
                            kwargs['sede'] = sede_excel
                        # 4. Fallback → sede_id del formulario
                    elif campo == 'telefono':
                        if valor and not kwargs.get('celular'):
                            kwargs['celular'] = valor
                    elif campo.startswith('_'):
                        # Componente de fecha dividida (DIA/MES/AÑO)
                        kwargs[campo] = valor
                    else:
                        kwargs[campo] = valor

                # Reconstruir fechas divididas si no se cargaron como fecha unificada
                if not kwargs.get('fecha_ingreso'):
                    d, m, a = kwargs.pop('_dia_ingreso', ''), kwargs.pop('_mes_ingreso', ''), kwargs.pop('_ano_ingreso', '')
                    if d and m and a:
                        kwargs['fecha_ingreso'] = _combinar_fecha_dma(d, m, a)
                else:
                    kwargs.pop('_dia_ingreso', None); kwargs.pop('_mes_ingreso', None); kwargs.pop('_ano_ingreso', None)

                if not kwargs.get('fecha_retiro'):
                    d, m, a = kwargs.pop('_dia_retiro', ''), kwargs.pop('_mes_retiro', ''), kwargs.pop('_ano_retiro', '')
                    if d and m and a:
                        kwargs['fecha_retiro'] = _combinar_fecha_dma(d, m, a)
                else:
                    kwargs.pop('_dia_retiro', None); kwargs.pop('_mes_retiro', None); kwargs.pop('_ano_retiro', None)

                if not kwargs.get('fecha_nacimiento'):
                    d, m, a = kwargs.pop('_dia_nacimiento', ''), kwargs.pop('_mes_nacimiento', ''), kwargs.pop('_ano_nacimiento', '')
                    if d and m and a:
                        kwargs['fecha_nacimiento'] = _combinar_fecha_dma(d, m, a)
                else:
                    kwargs.pop('_dia_nacimiento', None); kwargs.pop('_mes_nacimiento', None); kwargs.pop('_ano_nacimiento', None)

                # nombre_completo: rechazar valores triviales (dígitos, muy corto)
                nc = str(kwargs.get('nombre_completo', '') or '').strip()
                if nc and (nc.isdigit() or len(nc) < 2):
                    kwargs['nombre_completo'] = ''

                # nombre_completo fallback: combinar nombres + apellidos
                if not kwargs.get('nombre_completo'):
                    nombres   = kwargs.pop('nombres', '')
                    apellidos = kwargs.pop('apellidos', '')
                    if nombres or apellidos:
                        kwargs['nombre_completo'] = f'{nombres} {apellidos}'.strip()
                    else:
                        errores.append({'fila': fila_num, 'error': 'Sin nombre completo', 'tipo': 'sin_nombre'})
                        continue
                else:
                    kwargs.pop('nombres', None)
                    kwargs.pop('apellidos', None)

                if not kwargs.get('documento_id'):
                    errores.append({'fila': fila_num, 'error': 'Sin número de documento', 'tipo': 'sin_documento'})
                    continue

                # Validar tipo_sangre: descartar si no es un grupo sanguíneo real
                ts = str(kwargs.get('tipo_sangre', '') or '').strip().upper()
                if ts and not _TIPO_SANGRE_RE.match(ts):
                    kwargs.pop('tipo_sangre', None)

                # Reubicar valores en campos incorrectos usando la biblioteca de validadores
                # Ej: sexo con "UNION LIBRE" → estado_civil; estado_civil con fechas → descarta
                reubicar_valores_erroneos(kwargs)

                # Inferir tipo_proceso — usar la hoja de origen de cada fila
                _hoja_fila = str(fila.get('__hoja_origen__', '') or hoja_usada)
                _inferir_proceso_y_estado(kwargs, nombre_hoja=_hoja_fila)

                # Filtrar solo campos válidos del modelo para evitar TypeError
                campos_modelo = {f.name for f in EmpleadoTrazabilidad._meta.get_fields()
                                 if hasattr(f, 'column')}
                kwargs_limpio = {k: v for k, v in kwargs.items() if k in campos_modelo}

                # Modo FUSIONAR: mismas fechas + misma sede + motivo similar → no duplicar
                if modo_duplicados == 'fusionar':
                    sede_obj = kwargs_limpio.get('sede')
                    llave = (
                        kwargs_limpio.get('documento_id'),
                        kwargs_limpio.get('fecha_ingreso'),
                        kwargs_limpio.get('fecha_retiro'),
                        sede_obj.id if sede_obj else None,
                    )
                    motivos_existentes = existentes_dict.get(llave, [])
                    motivo_nuevo = str(kwargs_limpio.get('motivo_retiro', '') or '')
                    if motivos_existentes and any(_motivos_similares(motivo_nuevo, m) for m in motivos_existentes):
                        exitosos   += 1
                        fusionados += 1
                        continue

                # Verificar coherencia de nombre vs. BD para esta cédula
                doc_id_nuevo = kwargs_limpio.get('documento_id', '')
                nom_nuevo    = str(kwargs_limpio.get('nombre_completo', '') or '').upper().strip()
                nom_en_bd    = nombres_en_bd.get(doc_id_nuevo)
                if nom_en_bd and nom_nuevo:
                    sim = SequenceMatcher(
                        None,
                        nom_en_bd.upper().strip(),
                        nom_nuevo,
                    ).ratio()
                    if sim < 0.75:
                        _hoja_aviso = str(fila.get('__hoja_origen__', '') or hoja_usada)
                        errores.append({
                            'fila':      fila_num,
                            'error':     (
                                f'Nombre incoherente para cédula {doc_id_nuevo}: '
                                f'en BD "{nom_en_bd}" ≠ en archivo "{kwargs_limpio.get("nombre_completo")}" '
                                f'(similitud {int(sim*100)}%)'
                            ),
                            'tipo':      'nombre_incoherente',
                            'hoja':      _hoja_aviso,
                        })
                        # Actualizar el dict para no duplicar la advertencia en filas posteriores del mismo archivo
                        nombres_en_bd[doc_id_nuevo] = nom_en_bd  # mantener el nombre de BD como canónico

                kwargs_limpio['carga'] = registro_carga
                EmpleadoTrazabilidad.objects.create(**kwargs_limpio)
                exitosos += 1

                # Registrar el nuevo registro en los dicts en-memoria para que
                # filas posteriores del MISMO archivo lo detecten como existente.
                _doc_nuevo  = kwargs_limpio.get('documento_id')
                _fi_nuevo   = kwargs_limpio.get('fecha_ingreso')
                _fr_nuevo   = kwargs_limpio.get('fecha_retiro')
                _mot_nuevo  = str(kwargs_limpio.get('motivo_retiro', '') or '')
                _sid_nuevo  = kwargs_limpio.get('sede').id if kwargs_limpio.get('sede') else None
                existentes_dict.setdefault((_doc_nuevo, _fi_nuevo, _fr_nuevo, _sid_nuevo), []).append(_mot_nuevo)
                # También actualizar el nombre canónico si aún no estaba en BD
                if _doc_nuevo and not nombres_en_bd.get(_doc_nuevo):
                    nombres_en_bd[_doc_nuevo] = str(kwargs_limpio.get('nombre_completo', '') or '')

            except Exception as e:
                msg = str(e)
                # Clasificar el error para mejor diagnóstico
                if 'Sin número de documento' in msg:
                    tipo = 'sin_documento'
                elif 'Sin nombre completo' in msg:
                    tipo = 'sin_nombre'
                elif 'unique' in msg.lower() or 'duplicate' in msg.lower():
                    tipo = 'duplicado'
                elif 'does not exist' in msg.lower():
                    tipo = 'referencia_invalida'
                else:
                    tipo = 'error_inesperado'

                errores.append({
                    'fila':      fila_num,
                    'fila_hoja': int(fila.get('__fila_hoja__', fila_num)),
                    'hoja':      str(fila.get('__hoja_origen__', '')),
                    'error':     msg,
                    'tipo':      tipo,
                })
                import logging
                logger = logging.getLogger('trazabilidad.carga')
                logger.warning(f'[CARGA] {nombre_archivo} fila {fila_num} [{tipo}]: {msg[:200]}')

        # Actualizar el registro de carga con los resultados finales
        registro_carga.exitosos  = exitosos
        registro_carga.fallidos  = len(errores)
        registro_carga.errores   = errores[:200]   # guardar hasta 200 para el acta/historial
        registro_carga.save(update_fields=['exitosos', 'fallidos', 'errores'])

        nuevos = exitosos - fusionados
        return Response({
            'mensaje': f'{nuevos} registros nuevos cargados.' + (f' {fusionados} fusionados (ya existían).' if fusionados else ''),
            'total':      total_filas,   # filas reales (excluye vacías)
            'exitosos':   exitosos,
            'nuevos':     nuevos,
            'fusionados': fusionados,
            'fallidos':   len(errores),
            'errores':    errores[:200],   # retornar hasta 200 para el panel de resultados
            'carga_id':   registro_carga.id,
        }, status=201)


class HistorialCargasView(APIView):

    @swagger_auto_schema(operation_summary='Historial de cargas Excel', tags=['Carga Excel'])
    @require_permission(['can_upload_excel'], app_label='Usuarios')
    def get(self, request):
        cargas = CargaExcel.objects.select_related('sede', 'cargado_por').all()[:50]
        return Response(CargaExcelSerializer(cargas, many=True).data)
