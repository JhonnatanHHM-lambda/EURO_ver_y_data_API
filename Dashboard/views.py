import os
import pandas as pd
from datetime import date
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

# ─── paths ────────────────────────────────────────────────────────────────────

_API_DIR  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DATA_DIR = os.path.normpath(os.path.join(_API_DIR, '..', 'documentación', 'doc-dashboards'))

_NOMINA_DIR     = os.path.join(_DATA_DIR, 'Base Nómina')
_VENTAS_PATH    = os.path.join(_DATA_DIR, 'Ventas', 'Ventas_Tienda.xlsx')
_EMPLEADOS_PATH = os.path.join(_DATA_DIR, 'Informacion Empleados', 'Informacion Empleados.xlsx')
_CONCEPTOS_PATH = os.path.join(_DATA_DIR, 'Diccionarios', 'Informacion Conceptos.xlsx')

_CACHE: dict = {}

_MESES_ORDER = {
    'ENERO': 1, 'FEBRERO': 2, 'MARZO': 3, 'ABRIL': 4,
    'MAYO': 5, 'JUNIO': 6, 'JULIO': 7, 'AGOSTO': 8,
    'SEPTIEMBRE': 9, 'OCTUBRE': 10, 'NOVIEMBRE': 11, 'DICIEMBRE': 12,
}

_DIRECCION_CENTROS = {'ADMINISTRACIÓN', 'CEDI', 'DESPOSTAR', 'OMNICANAL'}
_MESES_INV = {v: k for k, v in _MESES_ORDER.items()}  # {1: 'ENERO', 2: 'FEBRERO', ...}

_TIPO_CONTRATO     = {'F': 'Fijo', 'I': 'Indefinido', '': 'Sin definir'}
_TIPO_CONTRATO_INV = {v: k for k, v in _TIPO_CONTRATO.items()}

# Conceptos TNL que NO deben contar como "ausencias" (tienen 0 horas, son registros de costo):
#   026 = INCAP. PAGADA POR LA EMPRESA  (costo empleador, no la ausencia en sí)
#   027 = INCAP ADMINIS 2 PRIMEROS DIAS (ídem, 0 horas)
#   103 = ACCIDENTE LABORAL             (concepto auxiliar, 0 horas)
_TNL_EXCLUIR_AUSENTISMO = {'026', '027', '103'}


# ─── helpers ──────────────────────────────────────────────────────────────────

def _tnl_horas_max(qs) -> float:
    """
    Suma de MAX(horas) por (cédula, concepto_id).
    SIESA crea múltiples sub-registros por período de incapacidad (una fila por quincena
    o reconocimiento EPS). Sumar todas infla las horas TNL. Tomar el MAX por par
    (cédula, concepto) corrige esa inflación y alinea con el Excel de PBI.
    """
    from django.db.models import Max, Sum
    return float(
        qs.values('cedula', 'concepto_id')
        .annotate(mh=Max('horas'))
        .aggregate(total=Sum('mh'))['total'] or 0
    )


def _tnl_horas_max_by(qs, group_field: str) -> dict:
    """
    Igual que _tnl_horas_max pero agrupado por un campo adicional (co_nombre, cedula, mes…).
    Retorna {valor_del_campo: horas_corregidas}.
    Django no soporta Sum-de-Max en una sola query ORM, por eso se agrupa en Python.
    """
    from django.db.models import Max
    result: dict = {}
    for r in qs.values(group_field, 'cedula', 'concepto_id').annotate(mh=Max('horas')):
        key = r[group_field]
        result[key] = result.get(key, 0.0) + float(r['mh'] or 0)
    return result


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = df.columns.str.strip()
    for cand in ['Año', 'año', 'ANO', 'ano']:
        if cand in df.columns:
            df = df.rename(columns={cand: 'AÑO'})
            break
    return df


def _find_data_sheet(path: str) -> int:
    """Retorna el índice de la hoja con 'Tercero' que tenga más filas (la hoja principal de datos)."""
    import openpyxl as _opx
    wb = _opx.load_workbook(path, read_only=True)
    best_idx, best_rows = 0, 0
    for i, name in enumerate(wb.sheetnames):
        ws = wb[name]
        try:
            first_row = [c.value for c in next(ws.iter_rows(max_row=1), [])]
        except StopIteration:
            first_row = []
        if 'Tercero' in first_row:
            rows = ws.max_row or 0
            if rows > best_rows:
                best_rows = rows
                best_idx  = i
    wb.close()
    return best_idx


def _load_nomina() -> pd.DataFrame:
    if 'nomina' in _CACHE:
        return _CACHE['nomina']
    frames = []
    for fname in sorted(os.listdir(_NOMINA_DIR)):
        if fname.lower().endswith('.xlsx'):
            path = os.path.join(_NOMINA_DIR, fname)
            try:
                sheet_idx = _find_data_sheet(path)
                df = pd.read_excel(path, sheet_name=sheet_idx, engine='openpyxl')
                frames.append(df)
            except Exception:
                pass
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    df = _normalize(df)
    # Concepto puede venir como float ('3.0') o str ('003') — normalizar siempre
    df['Concepto'] = (
        pd.to_numeric(df['Concepto'], errors='coerce')
        .fillna(0).astype(int).astype(str).str.zfill(3)
    )
    df['Devengo']      = pd.to_numeric(df['Devengo'], errors='coerce').fillna(0)
    df['Horas Movto.'] = pd.to_numeric(df['Horas Movto.'], errors='coerce').fillna(0)
    df['MES']          = df['MES'].astype(str).str.upper().str.strip()
    # Descartar filas sin mes o año válidos (excluye filas de cabecera duplicadas y NaN)
    df = df[df['MES'].isin(_MESES_ORDER.keys())]
    _CACHE['nomina'] = df
    return df


def _load_ventas() -> pd.DataFrame:
    if 'ventas' in _CACHE:
        return _CACHE['ventas']
    df = pd.read_excel(_VENTAS_PATH, engine='openpyxl')
    df = _normalize(df)
    for col in df.columns:
        if 'Venta' in col:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    df['MES'] = df['MES'].astype(str).str.upper().str.strip()
    _CACHE['ventas'] = df
    return df


def _load_empleados() -> pd.DataFrame:
    if 'empleados' in _CACHE:
        return _CACHE['empleados']
    df = pd.read_excel(_EMPLEADOS_PATH, engine='openpyxl')
    df = _normalize(df)
    _CACHE['empleados'] = df
    return df


def _load_conceptos() -> pd.DataFrame:
    if 'conceptos' in _CACHE:
        return _CACHE['conceptos']
    df = pd.read_excel(_CONCEPTOS_PATH, engine='openpyxl')
    df = _normalize(df)
    df['Concepto'] = df['Concepto'].astype(str).str.strip().str.zfill(3)
    _CACHE['conceptos'] = df
    return df


def _month_sort_key(m):
    return _MESES_ORDER.get(str(m).upper(), 99)


# ─── views ────────────────────────────────────────────────────────────────────

class DashboardAusentismoOpcionesView(APIView):
    """
    Endpoint ligero que devuelve solo las listas para poblar los filtros.
    Se llama una vez al montar el componente; los resultados se cachean en
    memoria 10 minutos para no repetir las queries en cada sesión.
    """
    permission_classes = [IsAuthenticated]
    _cache_ts   = 0
    _cache_data = None

    def get(self, request):
        import time
        from .models import NominaDato
        from django.db.models import Max

        now = time.time()
        if self._cache_data and (now - self._cache_ts) < 600:
            return Response(self._cache_data)

        conceptos   = _load_conceptos()
        known_concs = set(conceptos['Concepto'])
        qs_base = NominaDato.objects.filter(concepto_id__in=known_concs)

        meses          = sorted({_MESES_INV[m] for m in qs_base.values_list('mes', flat=True).distinct()}, key=_month_sort_key)
        anios          = sorted(qs_base.values_list('ano', flat=True).distinct(), reverse=True)
        tiendas        = sorted(qs_base.values_list('co_nombre', flat=True).distinct())
        tipos_concepto = sorted(conceptos['Tipo de Concepto'].dropna().unique().tolist())
        descs_concepto = sorted(qs_base.values_list('concepto_desc', flat=True).distinct())
        cargos_list    = sorted(filter(None, qs_base.values_list('cargo', flat=True).distinct()))
        empleados_list = [
            {'cc': r['cedula'], 'nombre': r['nombre']}
            for r in qs_base.values('cedula').annotate(nombre=Max('nombre')).order_by('nombre')
        ]

        payload = {
            'meses_disponibles':                  meses,
            'anios_disponibles':                  list(anios),
            'tiendas_disponibles':                list(tiendas),
            'tipos_concepto_disponibles':         tipos_concepto,
            'descripciones_concepto_disponibles': list(descs_concepto),
            'cargos_disponibles':                 list(cargos_list),
            'empleados_disponibles':              empleados_list,
        }
        DashboardAusentismoOpcionesView._cache_ts   = now
        DashboardAusentismoOpcionesView._cache_data = payload
        return Response(payload)


class DashboardAusentismoView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from .models import NominaDato
        from django.db.models import Sum, Count, Max

        conceptos     = _load_conceptos()
        tnl_set       = set(conceptos[conceptos['Tipo de Concepto'] == 'TIEMPO NO LABORADO']['Concepto'])
        known_concs   = set(conceptos['Concepto'])

        # Por defecto carga el mes y año en curso para que la carga inicial sea rápida.
        _today       = date.today()
        _default_mes  = _MESES_INV[_today.month]
        _default_anio = str(_today.year)

        mes           = request.query_params.get('mes', _default_mes).upper().strip()
        anio          = request.query_params.get('anio', _default_anio).strip()
        tiendas_param = request.query_params.get('tiendas', '').strip()
        tiendas_sel   = [t for t in tiendas_param.split(',') if t.strip()] if tiendas_param else []
        tipo_concepto = request.query_params.get('tipo_concepto', '').strip()
        desc_concepto = request.query_params.get('descripcion_concepto', '').strip()
        empleado_cc   = request.query_params.get('empleado_cc', '').strip()
        cargo_q       = request.query_params.get('cargo', '').strip()

        qs = NominaDato.objects.filter(concepto_id__in=known_concs)
        if mes:
            qs = qs.filter(mes=_MESES_ORDER[mes])
        if anio:
            qs = qs.filter(ano=int(anio))
        if tiendas_sel:
            qs = qs.filter(co_nombre__in=tiendas_sel)
        if tipo_concepto:
            tc_set = set(conceptos[conceptos['Tipo de Concepto'] == tipo_concepto]['Concepto'])
            qs = qs.filter(concepto_id__in=tc_set)
        if desc_concepto:
            qs = qs.filter(concepto_desc=desc_concepto)
        if empleado_cc:
            qs = qs.filter(cedula=empleado_cc)
        if cargo_q:
            qs = qs.filter(cargo=cargo_q)

        # qs_tnl: todos los conceptos TNL → para nómina y horas (incluye 026 que sí tiene valor $)
        qs_tnl = qs.filter(concepto_id__in=tnl_set)
        # qs_tnl_aus: excluye conceptos auxiliares de 0 horas que NO representan ausencias reales
        qs_tnl_aus = qs_tnl.exclude(concepto_id__in=_TNL_EXCLUIR_AUSENTISMO)

        # ── KPIs ──────────────────────────────────────────────────────────────
        agg = qs.aggregate(
            nomina_total=Sum('valor'),
            total_colaboradores=Count('cedula', distinct=True),
        )
        nomina_tnl          = float(qs_tnl.aggregate(n=Sum('valor'))['n'] or 0)
        # Horas TNL: MAX por (cédula, concepto) para corregir sub-registros SIESA
        horas_tnl           = _tnl_horas_max(qs_tnl)
        # Horas Total: no-TNL (Sum correcto) + TNL corregido
        horas_no_tnl        = float(
            qs.exclude(concepto_id__in=tnl_set).aggregate(h=Sum('horas'))['h'] or 0
        )
        horas_total         = horas_no_tnl + horas_tnl
        # Cantidad de ausentismos: pares distintos (cedula, concepto) para no contar múltiples
        # registros SIESA de un mismo período de incapacidad como eventos separados
        cantidad_ausentismo = qs_tnl_aus.values('cedula', 'concepto_id').distinct().count()
        personas_ausentismo = int(
            qs_tnl_aus.aggregate(pers=Count('cedula', distinct=True))['pers']
        )
        nomina_total        = float(agg['nomina_total'] or 0)
        total_colaboradores = int(agg['total_colaboradores'])
        pct_nomina_tnl      = round(nomina_tnl / nomina_total * 100, 2) if nomina_total else 0
        pct_ausentismo      = round(horas_tnl / horas_total * 100, 2) if horas_total else 0

        # ── Tabla colaboradores ───────────────────────────────────────────────
        colab_nom = {
            r['cedula']: r
            for r in qs.values('cedula').annotate(
                nombre=Max('nombre'), nomina=Sum('valor'),
            )
        }
        # Horas no-TNL por colaborador (Sum correcto)
        colab_horas_no_tnl = {
            r['cedula']: float(r['h'] or 0)
            for r in qs.exclude(concepto_id__in=tnl_set)
            .values('cedula').annotate(h=Sum('horas'))
        }
        # Nómina TNL por colaborador
        colab_nom_tnl = {
            r['cedula']: float(r['n'] or 0)
            for r in qs_tnl.values('cedula').annotate(n=Sum('valor'))
        }
        # Horas TNL por colaborador corregidas (MAX por concepto, luego Sum)
        colab_horas_tnl = _tnl_horas_max_by(qs_tnl, 'cedula')

        _colab_rows = []
        for ced, nom in sorted(colab_nom.items(), key=lambda x: -(float(x[1]['nomina'] or 0))):
            v_nom  = float(nom['nomina'] or 0)
            v_thrs = colab_horas_tnl.get(ced, 0.0)
            v_hrs  = colab_horas_no_tnl.get(ced, 0.0) + v_thrs
            v_tnom = colab_nom_tnl.get(ced, 0.0)
            _colab_rows.append({
                'cc': ced, 'nombre': nom['nombre'] or ced,
                'nomina': round(v_nom), 'nomina_tnl': round(v_tnom),
                'pct_nomina_tnl': round(v_tnom / v_nom * 100, 2) if v_nom else 0,
                'horas_total': round(v_hrs), 'horas_tnl': round(v_thrs),
                'pct_aus': round(v_thrs / v_hrs * 100, 2) if v_hrs else 0,
                'dias': round(v_thrs / 8, 2),
            })
        _colab_rows.append({
            'cc': '__TOTAL__', 'nombre': 'Total',
            'nomina': round(nomina_total), 'nomina_tnl': round(nomina_tnl),
            'pct_nomina_tnl': pct_nomina_tnl,
            'horas_total': round(horas_total), 'horas_tnl': round(horas_tnl),
            'pct_aus': pct_ausentismo, 'dias': round(horas_tnl / 8, 2),
        })

        # ── Tabla tiendas ─────────────────────────────────────────────────────
        tienda_nom = {
            r['co_nombre']: r
            for r in qs.values('co_nombre').annotate(
                nomina=Sum('valor'), personas=Count('cedula', distinct=True),
            )
        }
        # Horas no-TNL por tienda (Sum correcto)
        tienda_horas_no_tnl = {
            r['co_nombre']: float(r['h'] or 0)
            for r in qs.exclude(concepto_id__in=tnl_set)
            .values('co_nombre').annotate(h=Sum('horas'))
        }
        # Nómina TNL por tienda (026 tiene valor $, se incluye)
        tienda_nom_tnl = {
            r['co_nombre']: float(r['n'] or 0)
            for r in qs_tnl.values('co_nombre').annotate(n=Sum('valor'))
        }
        # Horas TNL por tienda corregidas (MAX por cédula+concepto, luego Sum)
        tienda_horas_tnl = _tnl_horas_max_by(qs_tnl, 'co_nombre')
        # personas_aus usa solo conceptos que representan ausencias reales (excl 026/027/103)
        tienda_tnl_aus = {
            r['co_nombre']: int(r['personas_aus'])
            for r in qs_tnl_aus.values('co_nombre').annotate(
                personas_aus=Count('cedula', distinct=True),
            )
        }
        tienda_cargos = {
            r['co_nombre']: int(r['cargos'])
            for r in qs.values('co_nombre').annotate(cargos=Count('cargo', distinct=True))
        }
        _total_cargos = int(qs.aggregate(c=Count('cargo', distinct=True))['c'])
        _tiendas_rows = []
        for co_nom, nom in sorted(tienda_nom.items(), key=lambda x: -(float(x[1]['nomina'] or 0))):
            v_nom  = float(nom['nomina'] or 0)
            v_thrs = tienda_horas_tnl.get(co_nom, 0.0)
            v_hrs  = tienda_horas_no_tnl.get(co_nom, 0.0) + v_thrs
            v_tnom = tienda_nom_tnl.get(co_nom, 0.0)
            _tiendas_rows.append({
                'tienda': co_nom,
                'nomina': round(v_nom), 'nomina_tnl': round(v_tnom),
                'pct_nomina_tnl': round(v_tnom / v_nom * 100, 2) if v_nom else 0,
                'horas_total': round(v_hrs), 'horas_tnl': round(v_thrs),
                'pct_aus': round(v_thrs / v_hrs * 100, 2) if v_hrs else 0,
                'personas': int(nom['personas']),
                'cargos': tienda_cargos.get(co_nom, 0),
                'personas_aus': tienda_tnl_aus.get(co_nom, 0),
            })
        _tiendas_rows.append({
            'tienda': '__TOTAL__',
            'nomina': round(nomina_total), 'nomina_tnl': round(nomina_tnl),
            'pct_nomina_tnl': pct_nomina_tnl,
            'horas_total': round(horas_total), 'horas_tnl': round(horas_tnl),
            'pct_aus': pct_ausentismo,
            'personas': total_colaboradores, 'cargos': _total_cargos,
            'personas_aus': personas_ausentismo,
        })

        # ── Tabla conceptos ───────────────────────────────────────────────────
        _conceptos_full_rows = [
            {
                'desc_concepto': r['concepto_desc'],
                'nomina':      float(r['nomina'] or 0),
                'horas_total': float(r['horas_total'] or 0),
                'personas':    int(r['personas']),
            }
            for r in qs.values('concepto_desc').annotate(
                nomina=Sum('valor'), horas_total=Sum('horas'),
                personas=Count('cedula', distinct=True),
            ).order_by('-nomina')
        ]
        _conceptos_full_rows.append({
            'desc_concepto': '__TOTAL__',
            'nomina': round(nomina_total), 'horas_total': round(horas_total),
            'personas': total_colaboradores,
        })

        # ── Comparación mensual por tienda (TNL) ──────────────────────────────
        comp_tnl_map = {
            (r['co_nombre'], r['mes'], r['ano']): float(r['nomina_tnl'] or 0)
            for r in qs_tnl.values('co_nombre', 'mes', 'ano').annotate(nomina_tnl=Sum('valor'))
        }
        ct_tnl_map = {
            (r['mes'], r['ano']): float(r['nomina_tnl'] or 0)
            for r in qs_tnl.values('mes', 'ano').annotate(nomina_tnl=Sum('valor'))
        }
        comp_data, ct_data = [], []
        for r in qs.values('co_nombre', 'mes', 'ano').annotate(nomina=Sum('valor')):
            tda, m, a = r['co_nombre'], r['mes'], int(r['ano'])
            v_nom = float(r['nomina'] or 0)
            v_tnl = comp_tnl_map.get((tda, m, a), 0.0)
            comp_data.append({
                'tienda': tda, 'MES': _MESES_INV[m], 'AÑO': a,
                'label': _MESES_INV[m].title() + ' ' + str(a),
                'nomina': round(v_nom), 'nomina_tnl': round(v_tnl),
                'pct_nomina_tnl': round(v_tnl / v_nom * 100, 2) if v_nom else 0,
            })
        for r in qs.values('mes', 'ano').annotate(nomina=Sum('valor')):
            m, a  = r['mes'], int(r['ano'])
            v_nom = float(r['nomina'] or 0)
            v_tnl = ct_tnl_map.get((m, a), 0.0)
            ct_data.append({
                'tienda': '__TOTAL__', 'MES': _MESES_INV[m], 'AÑO': a,
                'label': _MESES_INV[m].title() + ' ' + str(a),
                'nomina': round(v_nom), 'nomina_tnl': round(v_tnl),
                'pct_nomina_tnl': round(v_tnl / v_nom * 100, 2) if v_nom else 0,
            })
        if comp_data or ct_data:
            df_comp = pd.DataFrame(comp_data + ct_data)
            df_comp['mes_num'] = df_comp['MES'].map(_MESES_ORDER).fillna(0)
            df_comp = df_comp.sort_values(['tienda', 'AÑO', 'mes_num'])
            df_comp['var_pct_mm']    = df_comp.groupby('tienda')['pct_nomina_tnl'].diff().round(2)
            df_comp['var_dinero_mm'] = df_comp.groupby('tienda')['nomina_tnl'].diff().round(0)
            for _col in ['var_pct_mm', 'var_dinero_mm']:
                df_comp[_col] = df_comp[_col].astype(object).where(pd.notna(df_comp[_col]), None)
            _cols = ['tienda', 'label', 'MES', 'AÑO', 'nomina', 'nomina_tnl', 'pct_nomina_tnl', 'var_pct_mm', 'var_dinero_mm']
            _comp_aus_rows = df_comp[_cols].to_dict('records')
        else:
            _comp_aus_rows = []

        # ── Calendario — respeta el año/tiendas seleccionados, muestra todos los meses de ese año ──
        # Si hay año filtrado lo usa; si no, carga solo el año en curso para evitar traer todo el histórico.
        _cal_anio = int(anio) if anio else _today.year
        qs_cal     = NominaDato.objects.filter(concepto_id__in=known_concs, ano=_cal_anio)
        qs_cal_tnl = NominaDato.objects.filter(concepto_id__in=tnl_set, ano=_cal_anio)
        if tiendas_sel:
            qs_cal     = qs_cal.filter(co_nombre__in=tiendas_sel)
            qs_cal_tnl = qs_cal_tnl.filter(co_nombre__in=tiendas_sel)
        # Horas no-TNL por (mes, año) — Sum correcto
        cal_horas_no_tnl = {
            (r['mes'], r['ano']): float(r['h'] or 0)
            for r in qs_cal.exclude(concepto_id__in=tnl_set)
            .values('mes', 'ano').annotate(h=Sum('horas'))
        }
        # Horas TNL por (mes, año) corregidas — agregación Python por la limitación ORM
        _cal_tnl_raw: dict = {}
        for r in qs_cal_tnl.values('mes', 'ano', 'cedula', 'concepto_id').annotate(mh=Max('horas')):
            k = (r['mes'], r['ano'])
            _cal_tnl_raw[k] = _cal_tnl_raw.get(k, 0.0) + float(r['mh'] or 0)
        cal_horas_tnl = _cal_tnl_raw
        cal_nom_map = {
            (r['mes'], r['ano']): r
            for r in qs_cal.values('mes', 'ano').annotate(nomina=Sum('valor'))
        }
        cal_tnl_map = {
            (r['mes'], r['ano']): r
            for r in qs_cal_tnl.values('mes', 'ano').annotate(
                nom_tnl=Sum('valor'),
                personas=Count('cedula', distinct=True),
            )
        }
        cal_records = []
        for (m, a), nom in sorted(cal_nom_map.items(), key=lambda x: (x[0][1], x[0][0])):
            tnl   = cal_tnl_map.get((m, a), {})
            v_nom = float(nom['nomina'] or 0)
            v_thr = cal_horas_tnl.get((m, a), 0.0)
            v_hrs = cal_horas_no_tnl.get((m, a), 0.0) + v_thr
            v_tnl = float(tnl.get('nom_tnl') or 0)
            cal_records.append({
                'MES': _MESES_INV[m], 'AÑO': int(a),
                'label': _MESES_INV[m].title() + ' ' + str(a),
                'nomina': round(v_nom), 'horas': round(v_hrs),
                'nom_tnl': round(v_tnl), 'hrs_tnl': round(v_thr),
                'personas':    int(tnl.get('personas') or 0),
                'pct_tnl':     round(v_tnl / v_nom * 100, 2) if v_nom else 0,
                'pct_aus_cal': round(v_thr / v_hrs * 100, 2) if v_hrs else 0,
            })

        # ── Último período COMPLETO con datos (≥100 empleados distintos).
        # Sirve de fallback cuando el mes en curso aún no ha cerrado en SIESA y tiene muy pocos registros.
        _ultimo_nd = (
            NominaDato.objects.filter(concepto_id__in=known_concs)
            .values('ano', 'mes')
            .annotate(_n=Count('cedula', distinct=True))
            .filter(_n__gte=100)
            .order_by('-ano', '-mes')
            .first()
        )
        _ultimo_periodo = None
        if _ultimo_nd:
            _ultimo_periodo = {
                'mes':  _MESES_INV.get(_ultimo_nd['mes'], ''),
                'anio': str(_ultimo_nd['ano']),
            }

        return Response({
            'kpis': {
                'nomina_total':        round(nomina_total),
                'nomina_tnl':          round(nomina_tnl),
                'horas_total':         round(horas_total),
                'horas_tnl':           round(horas_tnl),
                'pct_nomina_tnl':      pct_nomina_tnl,
                'total_colaboradores': total_colaboradores,
                'personas_ausentismo': personas_ausentismo,
                'pct_ausentismo':      pct_ausentismo,
                'cantidad_ausentismo': cantidad_ausentismo,
            },
            'ultimo_periodo_con_datos': _ultimo_periodo,
            'tabla_tiendas':           _tiendas_rows,
            'tabla_conceptos_full':    _conceptos_full_rows,
            'tabla_colaboradores':     _colab_rows,
            'comparacion_mensual_aus': _comp_aus_rows,
            'calendario':              cal_records,
        })


class DashboardNominaVentaView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from .models import NominaDato
        from django.db.models import Sum, Count

        df_ven_all = _load_ventas()
        conceptos  = _load_conceptos()

        nov_set       = set(conceptos[conceptos['Tipo de Concepto'] == 'NOVEDADES']['Concepto'])
        known_concepts = set(conceptos['Concepto'])

        mes           = request.query_params.get('mes', '').upper().strip()
        anio          = request.query_params.get('anio', '').strip()
        tiendas_param = request.query_params.get('tiendas', '').strip()
        tiendas_sel   = [t for t in tiendas_param.split(',') if t.strip()] if tiendas_param else []
        is_only_omni  = tiendas_sel == ['OMNICANAL']
        non_omni_sel  = [t for t in tiendas_sel if t != 'OMNICANAL']

        df_ven = df_ven_all.copy()
        if mes:
            df_ven = df_ven[df_ven['MES'] == mes]
        if anio:
            df_ven = df_ven[df_ven['AÑO'].astype(str) == anio]
        if non_omni_sel:
            df_ven = df_ven[df_ven['Descripción C.O. Movimiento'].isin(non_omni_sel)]

        ven_col_gen = next((c for c in df_ven_all.columns if 'Venta General' in c), None)
        ven_col_omn = next((c for c in df_ven_all.columns if 'OMNICANAL' in c.upper() and c != ven_col_gen), None)

        # Queryset base: solo conceptos mapeados
        qs = NominaDato.objects.filter(concepto_id__in=known_concepts)
        if mes:
            qs = qs.filter(mes=_MESES_ORDER[mes])
        if anio:
            qs = qs.filter(ano=int(anio))
        if tiendas_sel:
            qs = qs.filter(co_nombre__in=tiendas_sel)

        qs_nov = qs.filter(concepto_id__in=nov_set)

        # ── KPIs ─────────────────────────────────────────────────────────────────
        nomina_total = float(qs.aggregate(v=Sum('valor'))['v'] or 0)
        if is_only_omni:
            venta_omnicanal = float(df_ven[ven_col_omn].sum()) if ven_col_omn else 0
            venta_total     = venta_omnicanal
            venta_tiendas   = 0.0
        else:
            venta_total     = float(df_ven[ven_col_gen].sum()) if ven_col_gen else 0
            venta_omnicanal = float(df_ven[ven_col_omn].sum()) if ven_col_omn else 0
            venta_tiendas   = venta_total - venta_omnicanal

        _pct_nom_denom = (venta_total    if is_only_omni
                          else venta_tiendas if tiendas_sel
                          else venta_total)
        pct_nom_venta       = round(nomina_total    / _pct_nom_denom * 100, 2) if _pct_nom_denom else 0
        pct_tiendas_venta   = round(venta_tiendas   / venta_total    * 100, 2) if venta_total else 0
        pct_omnicanal_venta = round(venta_omnicanal / venta_total    * 100, 2) if venta_total else 0

        # ── Tabla tiendas (nómina + ventas) ──────────────────────────────────────
        nom_co_df = pd.DataFrame([
            {'Descripción C.O. Movimiento': r['co_nombre'], 'nomina': float(r['nomina'] or 0)}
            for r in qs.values('co_nombre').annotate(nomina=Sum('valor'))
        ])
        agg_ven = {}
        if ven_col_gen: agg_ven['venta_total_row']     = (ven_col_gen, 'sum')
        if ven_col_omn: agg_ven['venta_omnicanal_row'] = (ven_col_omn, 'sum')
        if agg_ven:
            ven_all = df_ven.groupby('Descripción C.O. Movimiento', as_index=False).agg(**agg_ven)
        else:
            ven_all = pd.DataFrame(columns=['Descripción C.O. Movimiento'])

        if not nom_co_df.empty:
            tab = nom_co_df.merge(ven_all, on='Descripción C.O. Movimiento', how='outer').fillna(0)
        else:
            tab = ven_all.copy(); tab['nomina'] = 0
        tab = tab.rename(columns={'Descripción C.O. Movimiento': 'tienda'})
        if 'venta_total_row'     not in tab.columns: tab['venta_total_row']     = 0
        if 'venta_omnicanal_row' not in tab.columns: tab['venta_omnicanal_row'] = 0
        tab['venta_tiendas_row'] = tab['venta_total_row'] - tab['venta_omnicanal_row']
        if ven_col_omn:
            omn_v    = float(df_ven[ven_col_omn].sum())
            omn_mask = tab['tienda'] == 'OMNICANAL'
            if omn_mask.any():
                tab.loc[omn_mask, 'venta_total_row']     = omn_v
                tab.loc[omn_mask, 'venta_omnicanal_row'] = omn_v
                tab.loc[omn_mask, 'venta_tiendas_row']   = 0.0
        tab['pct_nom'] = tab.apply(
            lambda r: round(r['nomina'] / r['venta_tiendas_row'] * 100, 2) if r['venta_tiendas_row'] > 0
            else round(r['nomina'] / r['venta_total_row'] * 100, 2) if r['venta_total_row'] > 0
            else 0, axis=1,
        )
        tab['pct_tda'] = tab.apply(lambda r: round(r['venta_tiendas_row'] / r['venta_total_row'] * 100, 2) if r['venta_total_row'] > 0 else 0, axis=1)
        tab['pct_omn'] = tab.apply(lambda r: round(r['venta_omnicanal_row'] / r['venta_total_row'] * 100, 2) if r['venta_total_row'] > 0 else 0, axis=1)
        if is_only_omni:
            tab = tab[tab['tienda'] == 'OMNICANAL']
        tab = tab.sort_values('nomina', ascending=False)
        _tot_denom = (venta_total if is_only_omni else venta_tiendas if tiendas_sel else venta_total)
        _tabla_rows = tab[['tienda', 'venta_total_row', 'venta_tiendas_row',
                            'venta_omnicanal_row', 'nomina', 'pct_nom', 'pct_tda', 'pct_omn']].to_dict('records')
        _tabla_rows.append({
            'tienda': '__TOTAL__',
            'venta_total_row': round(venta_total), 'venta_tiendas_row': round(venta_tiendas),
            'venta_omnicanal_row': round(venta_omnicanal), 'nomina': round(nomina_total),
            'pct_nom': round(nomina_total / _tot_denom * 100, 2) if _tot_denom else 0,
            'pct_tda': pct_tiendas_venta, 'pct_omn': pct_omnicanal_venta,
        })

        # ── Tendencia (respeta sedes, ignora mes, excluye dirección/centros) ──────
        qs_tend = NominaDato.objects.filter(concepto_id__in=known_concepts)
        if tiendas_sel:
            qs_tend = qs_tend.filter(co_nombre__in=tiendas_sel)
        if anio:
            qs_tend = qs_tend.filter(ano=int(anio))
        all_sel_direc = tiendas_sel and all(t in _DIRECCION_CENTROS for t in tiendas_sel)
        qs_tda_tend = qs_tend if all_sel_direc else qs_tend.exclude(co_nombre__in=_DIRECCION_CENTROS)

        tend_ven = df_ven_all.copy()
        non_omni_tend = [t for t in tiendas_sel if t != 'OMNICANAL']
        if non_omni_tend:
            tend_ven = tend_ven[tend_ven['Descripción C.O. Movimiento'].isin(non_omni_tend)]
        if anio:
            tend_ven = tend_ven[tend_ven['AÑO'].astype(str) == anio]

        nom_tend_rows = list(qs_tda_tend.values('mes', 'ano').annotate(nomina=Sum('valor')))
        t_n = pd.DataFrame([
            {'MES': _MESES_INV[r['mes']], 'AÑO': int(r['ano']), 'nomina': float(r['nomina'] or 0)}
            for r in nom_tend_rows
        ]) if nom_tend_rows else pd.DataFrame(columns=['MES', 'AÑO', 'nomina'])

        agg_tend = {}
        if ven_col_gen: agg_tend['ventas_gen'] = (ven_col_gen, 'sum')
        if ven_col_omn: agg_tend['ventas_omn'] = (ven_col_omn, 'sum')
        if agg_tend:
            t_v = tend_ven.groupby(['MES', 'AÑO'], as_index=False).agg(**agg_tend)
        else:
            t_v = pd.DataFrame(columns=['MES', 'AÑO'])

        if not t_n.empty:
            tend = t_n.merge(t_v, on=['MES', 'AÑO'], how='left').fillna(0)
        else:
            tend = pd.DataFrame(columns=['MES', 'AÑO', 'nomina', 'ventas_gen', 'ventas_omn'])
        if 'ventas_gen' not in tend.columns: tend['ventas_gen'] = 0
        if 'ventas_omn' not in tend.columns: tend['ventas_omn'] = 0
        tend['ventas'] = tend['ventas_omn'] if is_only_omni else tend['ventas_gen'] - tend['ventas_omn']
        tend['pct']     = tend.apply(lambda r: round(r['nomina'] / r['ventas'] * 100, 2) if r['ventas'] > 0 else 0, axis=1)
        tend['mes_num'] = tend['MES'].map(_MESES_ORDER).fillna(0)
        tend = tend.sort_values(['AÑO', 'mes_num'])
        tend['label'] = tend['MES'].str.title() + ' ' + tend['AÑO'].astype(str)
        tend = tend.drop(columns=['mes_num', 'ventas_gen', 'ventas_omn'])

        # ── Novedades por tienda (incluye todos los COs) ──────────────────────────
        nov_nom_map = {
            r['co_nombre']: float(r['nomina'] or 0)
            for r in qs.values('co_nombre').annotate(nomina=Sum('valor'))
        }
        nov_agg = list(qs_nov.values('co_nombre').annotate(
            novedades=Sum('valor'), horas=Sum('horas'),
        ))
        _nov_rows = sorted([
            {
                'tienda': r['co_nombre'],
                'nomina': round(nov_nom_map.get(r['co_nombre'], 0)),
                'novedades': round(float(r['novedades'] or 0)),
                'pct_novedades': round(float(r['novedades'] or 0) / nov_nom_map.get(r['co_nombre'], 1) * 100, 2)
                    if nov_nom_map.get(r['co_nombre']) else 0,
                'horas': round(float(r['horas'] or 0), 1),
            }
            for r in nov_agg
        ], key=lambda x: -x['novedades'])
        _nov_nom_tot = nomina_total
        _nov_nov_tot = float(qs_nov.aggregate(v=Sum('valor'))['v'] or 0)
        _nov_hrs_tot = float(qs_nov.aggregate(h=Sum('horas'))['h'] or 0)
        _nov_rows.append({
            'tienda': '__TOTAL__', 'nomina': round(_nov_nom_tot),
            'novedades': round(_nov_nov_tot),
            'pct_novedades': round(_nov_nov_tot / _nov_nom_tot * 100, 2) if _nov_nom_tot else 0,
            'horas': round(_nov_hrs_tot, 1),
        })

        # ── Comparación mensual por tienda (novedades) — todos los COs ───────────
        comp_nov_map = {
            (r['co_nombre'], r['mes'], r['ano']): float(r['novedades'] or 0)
            for r in qs_nov.values('co_nombre', 'mes', 'ano').annotate(novedades=Sum('valor'))
        }
        ct_nov_map = {
            (r['mes'], r['ano']): float(r['novedades'] or 0)
            for r in qs_nov.values('mes', 'ano').annotate(novedades=Sum('valor'))
        }
        comp_data = []
        for r in qs.values('co_nombre', 'mes', 'ano').annotate(nomina=Sum('valor')):
            co, m, a = r['co_nombre'], r['mes'], int(r['ano'])
            v_nom = float(r['nomina'] or 0)
            v_nov = comp_nov_map.get((co, m, a), 0.0)
            comp_data.append({
                'tienda': co, 'MES': _MESES_INV[m], 'AÑO': a,
                'label': _MESES_INV[m].title() + ' ' + str(a),
                'nomina': round(v_nom), 'novedades': round(v_nov),
                'pct_novedades': round(v_nov / v_nom * 100, 2) if v_nom else 0,
            })
        ct_data = []
        for r in qs.values('mes', 'ano').annotate(nomina=Sum('valor')):
            m, a  = r['mes'], int(r['ano'])
            v_nom = float(r['nomina'] or 0)
            v_nov = ct_nov_map.get((m, a), 0.0)
            ct_data.append({
                'tienda': '__TOTAL__', 'MES': _MESES_INV[m], 'AÑO': a,
                'label': _MESES_INV[m].title() + ' ' + str(a),
                'nomina': round(v_nom), 'novedades': round(v_nov),
                'pct_novedades': round(v_nov / v_nom * 100, 2) if v_nom else 0,
            })
        if comp_data or ct_data:
            def _co_sort(n): return (0, n) if n == 'OMNICANAL' else ((1, n) if str(n).startswith('EURO') else (2, n))
            df_comp = pd.DataFrame(comp_data + ct_data)
            df_comp['mes_num'] = df_comp['MES'].map(_MESES_ORDER).fillna(0)
            df_comp['_sort']   = df_comp['tienda'].apply(_co_sort)
            df_comp = df_comp.sort_values(['_sort', 'AÑO', 'mes_num']).drop(columns=['_sort'])
            df_comp['var_pct_mm']    = df_comp.groupby('tienda')['pct_novedades'].diff().round(2)
            df_comp['var_dinero_mm'] = df_comp.groupby('tienda')['novedades'].diff().round(0)
            for col in ['var_pct_mm', 'var_dinero_mm']:
                df_comp[col] = df_comp[col].astype(object).where(pd.notna(df_comp[col]), None)
            _comp_cols = ['tienda', 'label', 'MES', 'AÑO', 'nomina', 'novedades', 'pct_novedades', 'var_pct_mm', 'var_dinero_mm']
            _comp_rows = df_comp[_comp_cols].to_dict('records')
        else:
            _comp_rows = []

        # ── Opciones de filtros ───────────────────────────────────────────────────
        qs_base = NominaDato.objects.filter(concepto_id__in=known_concepts)
        meses        = sorted({_MESES_INV[m] for m in qs_base.values_list('mes', flat=True).distinct()}, key=_month_sort_key)
        anios        = sorted(qs_base.values_list('ano', flat=True).distinct())
        tiendas_list = sorted(
            qs_base.exclude(co_nombre__in=_DIRECCION_CENTROS)
            .values_list('co_nombre', flat=True).distinct()
        )

        return Response({
            'kpis': {
                'nomina_total':        round(nomina_total),
                'venta_total':         round(venta_total),
                'venta_tiendas':       round(venta_tiendas),
                'venta_omnicanal':     round(venta_omnicanal),
                'pct_nom_venta':       pct_nom_venta,
                'pct_tiendas_venta':   pct_tiendas_venta,
                'pct_omnicanal_venta': pct_omnicanal_venta,
            },
            'tabla_tiendas':       _tabla_rows,
            'tendencia':           tend[['label', 'MES', 'AÑO', 'nomina', 'ventas', 'pct']].to_dict('records'),
            'novedades_tienda':    _nov_rows,
            'comparacion_mensual': _comp_rows,
            'meses_disponibles':   meses,
            'anios_disponibles':   list(anios),
            'tiendas_disponibles': list(tiendas_list),
        })


class DashboardAntiguedadView(APIView):
    permission_classes = [IsAuthenticated]

    _PAGE_SIZE_DEFAULT = 50
    _PAGE_SIZE_MAX     = 200

    def get(self, request):
        import math
        from .models import RotacionDato

        today = date.today()

        tienda        = request.query_params.get('tienda', '').strip()
        cargo         = request.query_params.get('cargo', '').strip()
        tipo_contrato = request.query_params.get('tipo_contrato', '').strip()
        sexo          = request.query_params.get('sexo', '').strip()
        cedula        = request.query_params.get('cedula', '').strip()
        nombre        = request.query_params.get('nombre', '').strip()

        try:
            page = max(1, int(request.query_params.get('page', 1)))
        except (ValueError, TypeError):
            page = 1
        try:
            page_size = min(
                max(1, int(request.query_params.get('page_size', self._PAGE_SIZE_DEFAULT))),
                self._PAGE_SIZE_MAX,
            )
        except (ValueError, TypeError):
            page_size = self._PAGE_SIZE_DEFAULT

        qs_all = RotacionDato.objects.filter(es_activo=True, fecha_ingreso__isnull=False)
        qs     = qs_all

        if tienda:
            qs = qs.filter(co_nombre=tienda)
        if cargo:
            qs = qs.filter(cargo__icontains=cargo)
        if tipo_contrato:
            # Acepta tanto label ('Fijo') como código ('F') para no romper bookmarks existentes
            tc_code = _TIPO_CONTRATO_INV.get(tipo_contrato, tipo_contrato)
            qs = qs.filter(tipo_contrato=tc_code)
        if sexo:
            qs = qs.filter(sexo=sexo)
        if cedula:
            qs = qs.filter(cedula__icontains=cedula)
        if nombre:
            qs = qs.filter(nombre__icontains=nombre)

        # Traer campos necesarios; ~1300 filas → liviano en memoria
        campos = ['cedula', 'nombre', 'co_nombre', 'cargo', 'tipo_contrato', 'sexo', 'fecha_ingreso']
        registros = list(qs.values(*campos).order_by('fecha_ingreso'))

        for r in registros:
            dias = (today - r['fecha_ingreso']).days if r['fecha_ingreso'] else 0
            r['_dias']  = dias
            r['_anios'] = dias / 365.25

        total_todos = qs_all.count()
        total       = len(registros)
        pct_total   = round(total / total_todos * 100, 2) if total_todos else 0
        avg_dias    = sum(r['_dias'] for r in registros) / total if total else 0.0
        avg_anios   = avg_dias / 365.25

        td = int(avg_dias)
        ya, ym, yd = td // 365, (td % 365) // 30, (td % 365) % 30
        avg_texto = f'{ya} años, {ym} meses y {yd} días'

        # ── Por tienda ────────────────────────────────────────────────────────
        tda_map: dict = {}
        for r in registros:
            t = r['co_nombre'] or ''
            if t not in tda_map:
                tda_map[t] = {'empleados': 0, '_sum': 0.0}
            tda_map[t]['empleados'] += 1
            tda_map[t]['_sum']      += r['_anios']
        por_tda = sorted(
            [{'tienda': t, 'empleados': v['empleados'], 'prom_anios': round(v['_sum'] / v['empleados'], 2)}
             for t, v in tda_map.items()],
            key=lambda x: x['prom_anios'], reverse=True,
        )

        # ── Donuts ────────────────────────────────────────────────────────────
        sx_map: dict = {}
        for r in registros:
            sx_map[r['sexo']] = sx_map.get(r['sexo'], 0) + 1
        por_sexo = [{'name': k, 'value': v} for k, v in sorted(sx_map.items())]

        tc_map: dict = {}
        for r in registros:
            label = _TIPO_CONTRATO.get(r['tipo_contrato'], r['tipo_contrato'] or 'Sin definir')
            tc_map[label] = tc_map.get(label, 0) + 1
        por_contrato = [{'name': k, 'value': v} for k, v in sorted(tc_map.items())]

        # ── Detalle paginado (más antiguos primero) ───────────────────────────
        registros_ord = sorted(registros, key=lambda x: x['_dias'], reverse=True)
        total_registros = len(registros_ord)
        total_paginas   = max(1, math.ceil(total_registros / page_size))
        page            = min(page, total_paginas)
        inicio          = (page - 1) * page_size

        detalle = [
            {
                'cedula':          r['cedula'],
                'nombre':          r['nombre'],
                'tienda':          r['co_nombre'],
                'cargo':           r['cargo'],
                'tipo_contrato':   _TIPO_CONTRATO.get(r['tipo_contrato'], r['tipo_contrato'] or ''),
                'sexo':            r['sexo'],
                'fecha_ingreso':   r['fecha_ingreso'].strftime('%d/%m/%Y') if r['fecha_ingreso'] else '',
                'antiguedad_dias':  r['_dias'],
                'antiguedad_anios': round(r['_anios'], 2),
            }
            for r in registros_ord[inicio: inicio + page_size]
        ]

        # ── Opciones para filtros (sobre universo completo de activos) ────────
        tiendas   = sorted(qs_all.values_list('co_nombre', flat=True).distinct())
        contratos = sorted({
            _TIPO_CONTRATO.get(tc, tc or 'Sin definir')
            for tc in qs_all.values_list('tipo_contrato', flat=True).distinct()
        })
        sexos = sorted(filter(None, qs_all.values_list('sexo', flat=True).distinct()))

        return Response({
            'kpis': {
                'total_empleados': total,
                'total_todos':     total_todos,
                'pct_total':       pct_total,
                'avg_dias':        round(avg_dias),
                'avg_anios':       round(avg_anios, 2),
                'avg_texto':       avg_texto,
            },
            'por_tienda':   por_tda,
            'por_sexo':     por_sexo,
            'por_contrato': por_contrato,
            'detalle':      detalle,
            'paginacion': {
                'pagina_actual': page,
                'total_paginas': total_paginas,
                'total_registros': total_registros,
                'page_size': page_size,
            },
            'tiendas_disponibles':   tiendas,
            'contratos_disponibles': contratos,
            'sexos_disponibles':     sexos,
        })


# ─── Rotación ─────────────────────────────────────────────────────────────────

_MESES_NOMBRES_ROT = [
    'ENERO', 'FEBRERO', 'MARZO', 'ABRIL', 'MAYO', 'JUNIO',
    'JULIO', 'AGOSTO', 'SEPTIEMBRE', 'OCTUBRE', 'NOVIEMBRE', 'DICIEMBRE',
]


class DashboardRotacionOpcionesView(APIView):
    """
    Endpoint ligero: devuelve las opciones de filtro disponibles para el
    dashboard de Rotación. Cacheado en memoria 10 minutos (datos cambian solo
    tras la sync diaria de las 7:25 AM).
    """
    permission_classes = [IsAuthenticated]
    _cache_ts   = 0
    _cache_data = None

    def get(self, request):
        import time
        from .models import RotacionDato
        from django.db.models import Max

        now = time.time()
        if self._cache_data and (now - self._cache_ts) < 600:
            return Response(self._cache_data)

        qs = RotacionDato.objects.all()

        # Años y meses disponibles (de fechas_retiro de retirados)
        qs_ret = qs.filter(es_activo=False).exclude(fecha_retiro__isnull=True)
        anios_ret   = sorted(qs_ret.values_list('fecha_retiro__year',  flat=True).distinct(), reverse=True)
        meses_nums  = sorted(qs_ret.values_list('fecha_retiro__month', flat=True).distinct())
        meses_disp  = [_MESES_NOMBRES_ROT[m - 1] for m in meses_nums]

        tiendas  = sorted(filter(None, qs.values_list('co_nombre', flat=True).distinct()))
        motivos  = sorted(filter(None, qs.filter(es_activo=False).values_list('motivo_retiro', flat=True).distinct()))
        cargos   = sorted(filter(None, qs.values_list('cargo', flat=True).distinct()))

        payload = {
            'anios_disponibles':   list(anios_ret),
            'meses_disponibles':   meses_disp,
            'tiendas_disponibles': tiendas,
            'motivos_disponibles': motivos,
            'cargos_disponibles':  cargos,
        }
        DashboardRotacionOpcionesView._cache_ts   = now
        DashboardRotacionOpcionesView._cache_data = payload
        return Response(payload)


class DashboardRotacionView(APIView):
    """
    Dashboard principal de Rotación.
    Carga inicial: año y mes actuales (misma optimización que Ausentismo).
    Datos provienen exclusivamente de RotacionDato (sincronizado desde SIESA).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from .models import RotacionDato
        from django.db.models import Count, Avg, F, ExpressionWrapper, DurationField, Q

        _today = date.today()
        _default_anio = str(_today.year)
        _default_mes  = _MESES_NOMBRES_ROT[_today.month - 1]

        anio_q   = request.query_params.get('anio',   _default_anio).strip()
        mes_q    = request.query_params.get('mes',    _default_mes).upper().strip()
        tienda_q = request.query_params.get('tienda', '').strip()
        motivo_q = request.query_params.get('motivo', '').strip()
        cargo_q  = request.query_params.get('cargo',  '').strip()

        # ── Convertir mes a número ───────────────────────────────────────────
        mes_num = _MESES_NOMBRES_ROT.index(mes_q) + 1 if mes_q in _MESES_NOMBRES_ROT else _today.month
        anio_num = int(anio_q) if anio_q.isdigit() else _today.year

        # ── Base de activos (snapshot actual) ────────────────────────────────
        qs_activos = RotacionDato.objects.filter(es_activo=True)
        if tienda_q:
            qs_activos = qs_activos.filter(co_nombre=tienda_q)

        total_activos = qs_activos.count()

        # ── Base de retirados del período seleccionado ───────────────────────
        qs_ret_base = RotacionDato.objects.filter(
            es_activo=False,
            fecha_retiro__year=anio_num,
            fecha_retiro__month=mes_num,
        )
        if tienda_q:
            qs_ret_base = qs_ret_base.filter(co_nombre=tienda_q)
        if motivo_q:
            qs_ret_base = qs_ret_base.filter(motivo_retiro=motivo_q)

        # Snapshot previo al filtro de cargo (para tabla_cargos completa)
        qs_ret_pre_cargo = qs_ret_base
        if cargo_q:
            qs_ret_base = qs_ret_base.filter(cargo=cargo_q)

        total_retiros = qs_ret_base.count()
        idx_rotacion  = round(total_retiros / total_activos * 100, 2) if total_activos > 0 else 0.0

        # ── Desglose por tipo de retiro ───────────────────────────────────────
        def _count_motivo(qs, keywords):
            q = Q()
            for kw in keywords:
                q |= Q(motivo_retiro__icontains=kw)
            return qs.filter(q).count()

        ret_renuncia    = _count_motivo(qs_ret_base, ['RENUNCIA'])
        ret_terminacion = _count_motivo(qs_ret_base, ['TERMINACION CONTRATO', 'TERMINO FIJO'])
        ret_despido     = _count_motivo(qs_ret_base, ['JUSTA CAUSA'])
        ret_aprendizaje = _count_motivo(qs_ret_base, ['APRENDIZAJE'])

        # ── Antigüedad promedio de retirados del período ──────────────────────
        antig_rows = list(
            qs_ret_base.exclude(fecha_ingreso__isnull=True).exclude(fecha_retiro__isnull=True)
            .values_list('fecha_ingreso', 'fecha_retiro')
        )
        if antig_rows:
            dias_list = [(r - i).days for i, r in antig_rows if r and i]
            avg_ant_dias  = sum(dias_list) / len(dias_list) if dias_list else 0.0
        else:
            avg_ant_dias = 0.0
        avg_ant_anios = round(avg_ant_dias / 365.25, 1)

        # ── Tabla por tienda ──────────────────────────────────────────────────
        # Activos por CO
        act_by_co = {
            r['co_nombre']: r['cnt']
            for r in qs_activos.values('co_nombre').annotate(cnt=Count('id'))
        }
        # Retirados por CO (con motivo más frecuente)
        ret_by_co_raw = list(
            qs_ret_base.values('co_nombre', 'motivo_retiro').annotate(cnt=Count('id'))
        )
        ret_by_co: dict = {}
        for r in ret_by_co_raw:
            co = r['co_nombre']
            if co not in ret_by_co:
                ret_by_co[co] = {'retiros': 0, 'motivos': {}}
            ret_by_co[co]['retiros'] += r['cnt']
            ret_by_co[co]['motivos'][r['motivo_retiro']] = ret_by_co[co]['motivos'].get(r['motivo_retiro'], 0) + r['cnt']

        all_cos = sorted(set(list(act_by_co.keys()) + list(ret_by_co.keys())))
        _tiendas_rows = []
        for co in all_cos:
            _act = act_by_co.get(co, 0)
            _ret_info = ret_by_co.get(co, {'retiros': 0, 'motivos': {}})
            _ret = _ret_info['retiros']
            _top_mot = max(_ret_info['motivos'], key=_ret_info['motivos'].get) if _ret_info['motivos'] else ''
            _tiendas_rows.append({
                'tienda':          co,
                'activos':         _act,
                'retiros':         _ret,
                'indice_rotacion': round(_ret / _act * 100, 2) if _act > 0 else 0.0,
                'motivo_principal': _top_mot,
            })
        _tiendas_rows.sort(key=lambda x: -x['indice_rotacion'])
        _tiendas_rows.append({
            'tienda': '__TOTAL__', 'activos': total_activos, 'retiros': total_retiros,
            'indice_rotacion': idx_rotacion, 'motivo_principal': '',
        })

        # ── Tabla por motivo ──────────────────────────────────────────────────
        motivos_agg = list(
            qs_ret_base.values('motivo_retiro').annotate(cantidad=Count('id')).order_by('-cantidad')
        )
        _motivos_rows = [
            {
                'motivo':    r['motivo_retiro'],
                'cantidad':  r['cantidad'],
                'pct':       round(r['cantidad'] / total_retiros * 100, 2) if total_retiros else 0,
            }
            for r in motivos_agg
        ]

        # ── Tabla por cargo (top 15, usa qs_ret_pre_cargo) ───────────────────
        total_pre_cargo = qs_ret_pre_cargo.count()
        cargos_agg = list(
            qs_ret_pre_cargo.values('cargo').annotate(cantidad=Count('id')).order_by('-cantidad')[:15]
        )
        _cargos_rows = [
            {
                'cargo':    r['cargo'],
                'cantidad': r['cantidad'],
                'pct':      round(r['cantidad'] / total_pre_cargo * 100, 2) if total_pre_cargo else 0,
            }
            for r in cargos_agg
        ]

        # ── Detalle de retirados del período ──────────────────────────────────
        det_qs = list(
            qs_ret_base.values(
                'cedula', 'nombre', 'cargo', 'co_nombre', 'motivo_retiro',
                'salario', 'fecha_ingreso', 'fecha_retiro',
            ).order_by('-fecha_retiro')
        )
        _detalle_rows = []
        for r in det_qs:
            antig = (r['fecha_retiro'] - r['fecha_ingreso']).days if r['fecha_retiro'] and r['fecha_ingreso'] else 0
            _detalle_rows.append({
                'cedula':          str(r['cedula']),
                'nombre':          r['nombre'],
                'cargo':           r['cargo'],
                'tienda':          r['co_nombre'],
                'motivo':          r['motivo_retiro'],
                'salario':         int(r['salario']) if r['salario'] else 0,
                'fecha_ingreso':   r['fecha_ingreso'].strftime('%d/%m/%Y') if r['fecha_ingreso'] else '',
                'fecha_retiro':    r['fecha_retiro'].strftime('%d/%m/%Y')  if r['fecha_retiro']  else '',
                'antiguedad_anios': round(antig / 365.25, 1),
            })

        # ── Tendencia mensual (histórico sin filtros) ─────────────────────────
        tend_qs = list(
            RotacionDato.objects.filter(es_activo=False)
            .exclude(fecha_retiro__isnull=True)
            .values('fecha_retiro__year', 'fecha_retiro__month')
            .annotate(retiros=Count('id'))
            .order_by('fecha_retiro__year', 'fecha_retiro__month')
        )
        _total_activos_global = RotacionDato.objects.filter(es_activo=True).count()
        _tend_rows = []
        for r in tend_qs:
            _y, _m = r['fecha_retiro__year'], r['fecha_retiro__month']
            _label = f"{_MESES_NOMBRES_ROT[_m - 1][:3]} {_y}"
            _idx   = round(r['retiros'] / _total_activos_global * 100, 2) if _total_activos_global else 0
            _tend_rows.append({
                'label':          _label,
                'anio':           _y,
                'mes':            _m,
                'retiros':        r['retiros'],
                'activos_cierre': _total_activos_global,
                'indice':         _idx,
            })

        # ── KPIs de referencia global ─────────────────────────────────────────
        _ref_anio, _ref_mes = anio_num, mes_num
        kpi_ret_mensual   = RotacionDato.objects.filter(
            es_activo=False,
            fecha_retiro__year=_ref_anio, fecha_retiro__month=_ref_mes,
        ).count()
        kpi_ret_anual     = RotacionDato.objects.filter(
            es_activo=False, fecha_retiro__year=_ref_anio,
        ).count()
        kpi_ret_acumulada = RotacionDato.objects.filter(
            es_activo=False,
            fecha_retiro__year=_ref_anio, fecha_retiro__month__lte=_ref_mes,
        ).count()
        _base_global = _total_activos_global or 1
        kpi_rot_mensual   = round(kpi_ret_mensual   / _base_global * 100, 2)
        kpi_rot_anual     = round(kpi_ret_anual     / _base_global * 100, 2)
        kpi_rot_acumulada = round(kpi_ret_acumulada / _base_global * 100, 2)

        return Response({
            'kpis': {
                'total_retiros':        total_retiros,
                'total_activos':        total_activos,
                'indice_rotacion':      idx_rotacion,
                'ret_renuncia':         ret_renuncia,
                'ret_terminacion':      ret_terminacion,
                'ret_despido':          ret_despido,
                'ret_aprendizaje':      ret_aprendizaje,
                'avg_antiguedad_anios': avg_ant_anios,
                'avg_antiguedad_dias':  round(avg_ant_dias),
                'pct_renuncia':         round(ret_renuncia    / total_retiros * 100, 1) if total_retiros else 0,
                'pct_terminacion':      round(ret_terminacion / total_retiros * 100, 1) if total_retiros else 0,
            },
            'tabla_tiendas':  _tiendas_rows,
            'tabla_motivos':  _motivos_rows,
            'tabla_cargos':   _cargos_rows,
            'detalle':        _detalle_rows,
            'tendencia':      _tend_rows,
            'kpis_referencia': {
                'rotacion_mensual':   kpi_rot_mensual,
                'rotacion_anual':     kpi_rot_anual,
                'rotacion_acumulada': kpi_rot_acumulada,
                'retiros_mensual':    kpi_ret_mensual,
                'retiros_anual':      kpi_ret_anual,
                'retiros_acumulada':  kpi_ret_acumulada,
                'anio_ref':           _ref_anio,
                'mes_ref':            _ref_mes,
            },
        })


class DashboardCacheReloadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        _CACHE.clear()
        return Response({'ok': True, 'message': 'Caché limpiado. Los datos se recargarán en la próxima consulta.'})
