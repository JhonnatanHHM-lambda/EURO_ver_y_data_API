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


# ─── helpers ──────────────────────────────────────────────────────────────────

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

class DashboardAusentismoView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        df_all    = _load_nomina()
        conceptos = _load_conceptos()
        emp_all   = _load_empleados()

        # Normalizar cédula para join con Tercero
        emp = emp_all.copy()
        emp['Cédula'] = emp['Cédula'].astype(str).str.strip()

        tnl_set        = set(conceptos[conceptos['Tipo de Concepto'] == 'TIEMPO NO LABORADO']['Concepto'])
        # Igual que PBI: solo contar conceptos que existen en el diccionario
        known_concepts = set(conceptos['Concepto'])

        # ── filtros ───────────────────────────────────────────────────────────
        mes           = request.query_params.get('mes', '').upper().strip()
        anio          = request.query_params.get('anio', '').strip()
        tienda        = request.query_params.get('tienda', '').strip()
        tipo_concepto = request.query_params.get('tipo_concepto', '').strip()
        desc_concepto = request.query_params.get('descripcion_concepto', '').strip()
        empleado_cc   = request.query_params.get('empleado_cc', '').strip()
        cargo         = request.query_params.get('cargo', '').strip()

        # Filtrar a conceptos mapeados (misma lógica que PBI y DashboardNominaVentaView)
        df = df_all[df_all['Concepto'].isin(known_concepts)].copy()
        df['Tercero'] = df['Tercero'].astype(str).str.strip()

        if mes:
            df = df[df['MES'] == mes]
        if anio:
            df = df[df['AÑO'].astype(str) == anio]
        if tienda:
            df = df[df['Descripción C.O. Movimiento'] == tienda]
        if tipo_concepto:
            tc_set = set(conceptos[conceptos['Tipo de Concepto'] == tipo_concepto]['Concepto'])
            df = df[df['Concepto'].isin(tc_set)]
        if desc_concepto:
            df = df[df['Descripción Concepto'] == desc_concepto]
        if empleado_cc:
            df = df[df['Tercero'] == empleado_cc]
        if cargo:
            cedulas_cargo = set(emp[emp['Cargo'] == cargo]['Cédula'])
            df = df[df['Tercero'].isin(cedulas_cargo)]

        df_tnl = df[df['Concepto'].isin(tnl_set)]

        # ── KPIs ──────────────────────────────────────────────────────────────
        nomina_total        = float(df['Devengo'].sum())
        nomina_tnl          = float(df_tnl['Devengo'].sum())
        horas_tnl           = float(df_tnl['Horas Movto.'].sum())
        horas_total         = float(df['Horas Movto.'].sum())
        pct_nomina_tnl      = round(nomina_tnl / nomina_total * 100, 2) if nomina_total else 0
        # Tasa de ausentismo = horas TNL / horas totales × 100
        pct_ausentismo      = round(horas_tnl / horas_total * 100, 2) if horas_total else 0
        total_colaboradores = int(df['Tercero'].nunique())
        personas_ausentismo = int(df_tnl['Tercero'].nunique())
        cantidad_ausentismo = int(len(df_tnl))

        # ── Detectar columna de días si existe en el Excel ────────────────────
        _dias_col = None
        for _c in df.columns:
            _cl = _c.lower()
            if ('día' in _cl or 'dia' in _cl) and ('mov' in _cl or 'base' in _cl):
                _dias_col = _c
                break

        # ── Tabla colaboradores ───────────────────────────────────────────────
        _nom_c_agg = {'nomina': ('Devengo', 'sum'), 'horas_total': ('Horas Movto.', 'sum')}
        if _dias_col:
            _nom_c_agg['dias'] = (_dias_col, 'sum')
        nom_c = df.groupby('Tercero', as_index=False).agg(**_nom_c_agg)
        tnl_c = df_tnl.groupby('Tercero', as_index=False).agg(
            nomina_tnl=('Devengo', 'sum'),
            horas_tnl=('Horas Movto.', 'sum'),
        )
        tab_colab = nom_c.merge(tnl_c, on='Tercero', how='left').fillna(0)
        if 'dias' not in tab_colab.columns:
            tab_colab['dias'] = (tab_colab['horas_total'] / 8).round(2)
        tab_colab['pct_nomina_tnl'] = tab_colab.apply(
            lambda r: round(r['nomina_tnl'] / r['nomina'] * 100, 2) if r['nomina'] > 0 else 0, axis=1
        )
        tab_colab['pct_aus'] = tab_colab.apply(
            lambda r: round(r['horas_tnl'] / r['horas_total'] * 100, 2) if r['horas_total'] > 0 else 0, axis=1
        )
        _emp_names = emp[['Cédula', 'Nombre y Apellido']].rename(
            columns={'Cédula': 'Tercero', 'Nombre y Apellido': 'nombre'}
        )
        tab_colab = tab_colab.merge(_emp_names, on='Tercero', how='left')
        tab_colab['nombre'] = tab_colab['nombre'].fillna(tab_colab['Tercero'])
        tab_colab = tab_colab.sort_values('nomina', ascending=False)
        tab_colab = tab_colab.rename(columns={'Tercero': 'cc'})
        _colab_rows = tab_colab[
            ['cc', 'nombre', 'nomina', 'nomina_tnl', 'pct_nomina_tnl', 'horas_total', 'horas_tnl', 'pct_aus', 'dias']
        ].to_dict('records')
        _colab_rows.append({
            'cc': '__TOTAL__', 'nombre': 'Total',
            'nomina':        round(nomina_total),
            'nomina_tnl':    round(nomina_tnl),
            'pct_nomina_tnl': pct_nomina_tnl,
            'horas_total':   round(horas_total),
            'horas_tnl':     round(horas_tnl),
            'pct_aus':       pct_ausentismo,
            'dias':          round(float(tab_colab['dias'].sum()), 2),
        })

        # ── Tabla tiendas (Tienda Conceptos TNL) ─────────────────────────────
        nom_t = df.groupby('Descripción C.O. Movimiento', as_index=False).agg(
            nomina=('Devengo', 'sum'),
            horas_total=('Horas Movto.', 'sum'),
            personas=('Tercero', 'nunique'),
        )
        tnl_t = df_tnl.groupby('Descripción C.O. Movimiento', as_index=False).agg(
            nomina_tnl=('Devengo', 'sum'),
            horas_tnl=('Horas Movto.', 'sum'),
            personas_aus=('Tercero', 'nunique'),
        )
        tab_tiendas = nom_t.merge(tnl_t, on='Descripción C.O. Movimiento', how='left').fillna(0)
        tab_tiendas['pct_nomina_tnl'] = tab_tiendas.apply(
            lambda r: round(r['nomina_tnl'] / r['nomina'] * 100, 2) if r['nomina'] > 0 else 0, axis=1
        )
        tab_tiendas['pct_aus'] = tab_tiendas.apply(
            lambda r: round(r['horas_tnl'] / r['horas_total'] * 100, 2) if r['horas_total'] > 0 else 0, axis=1
        )
        tab_tiendas = tab_tiendas.sort_values('nomina', ascending=False)
        tab_tiendas = tab_tiendas.rename(columns={'Descripción C.O. Movimiento': 'tienda'})

        # Cargos únicos por tienda (join nómina × empleados)
        _tda_cargos_df = (
            df[['Tercero', 'Descripción C.O. Movimiento']].drop_duplicates()
            .merge(emp[['Cédula', 'Cargo']].rename(columns={'Cédula': 'Tercero'}), on='Tercero', how='left')
        )
        _cargos_by_tienda = (
            _tda_cargos_df.groupby('Descripción C.O. Movimiento', as_index=False)
            .agg(cargos=('Cargo', 'nunique'))
            .rename(columns={'Descripción C.O. Movimiento': 'tienda'})
        )
        _total_cargos = int(_tda_cargos_df['Cargo'].dropna().nunique())
        tab_tiendas = tab_tiendas.merge(_cargos_by_tienda, on='tienda', how='left').fillna(0)
        tab_tiendas['cargos'] = tab_tiendas['cargos'].astype(int)

        _tiendas_rows = tab_tiendas[
            ['tienda', 'nomina', 'nomina_tnl', 'pct_nomina_tnl', 'horas_total', 'horas_tnl', 'pct_aus', 'personas', 'cargos', 'personas_aus']
        ].to_dict('records')
        _tiendas_rows.append({
            'tienda': '__TOTAL__',
            'nomina':         round(nomina_total),
            'nomina_tnl':     round(nomina_tnl),
            'pct_nomina_tnl': pct_nomina_tnl,
            'horas_total':    round(horas_total),
            'horas_tnl':      round(horas_tnl),
            'pct_aus':        pct_ausentismo,
            'personas':       total_colaboradores,
            'cargos':         _total_cargos,
            'personas_aus':   personas_ausentismo,
        })

        # ── Tabla conceptos (todos los conceptos mapeados) ────────────────────
        tab_conceptos_full = df.groupby('Descripción Concepto', as_index=False).agg(
            nomina=('Devengo', 'sum'),
            horas_total=('Horas Movto.', 'sum'),
            personas=('Tercero', 'nunique'),
        ).sort_values('nomina', ascending=False)
        tab_conceptos_full = tab_conceptos_full.rename(columns={'Descripción Concepto': 'desc_concepto'})
        _conceptos_full_rows = tab_conceptos_full.to_dict('records')
        _conceptos_full_rows.append({
            'desc_concepto': '__TOTAL__',
            'nomina':      round(nomina_total),
            'horas_total': round(horas_total),
            'personas':    total_colaboradores,
        })

        # ── Comparación mensual por tienda (TNL) ──────────────────────────────
        _comp_nom = df.groupby(['Descripción C.O. Movimiento', 'MES', 'AÑO'], as_index=False).agg(
            nomina=('Devengo', 'sum'),
        )
        _comp_tnl = df_tnl.groupby(['Descripción C.O. Movimiento', 'MES', 'AÑO'], as_index=False).agg(
            nomina_tnl=('Devengo', 'sum'),
        )
        comp_aus = _comp_nom.merge(_comp_tnl, on=['Descripción C.O. Movimiento', 'MES', 'AÑO'], how='left').fillna(0)
        comp_aus['pct_nomina_tnl'] = comp_aus.apply(
            lambda r: round(r['nomina_tnl'] / r['nomina'] * 100, 2) if r['nomina'] > 0 else 0, axis=1
        )
        comp_aus['mes_num'] = comp_aus['MES'].map(_MESES_ORDER).fillna(0)
        comp_aus = comp_aus.sort_values(['Descripción C.O. Movimiento', 'AÑO', 'mes_num'])
        comp_aus['label'] = comp_aus['MES'].str.title() + ' ' + comp_aus['AÑO'].astype(str)
        comp_aus = comp_aus.rename(columns={'Descripción C.O. Movimiento': 'tienda'})
        comp_aus['var_pct_mm']    = comp_aus.groupby('tienda')['pct_nomina_tnl'].diff().round(2)
        comp_aus['var_dinero_mm'] = comp_aus.groupby('tienda')['nomina_tnl'].diff().round(0)
        for _col in ['var_pct_mm', 'var_dinero_mm']:
            comp_aus[_col] = comp_aus[_col].astype(object).where(pd.notna(comp_aus[_col]), None)
        # Total por mes
        _ct_nom = df.groupby(['MES', 'AÑO'], as_index=False).agg(nomina=('Devengo', 'sum'))
        _ct_tnl = df_tnl.groupby(['MES', 'AÑO'], as_index=False).agg(nomina_tnl=('Devengo', 'sum'))
        ct_aus = _ct_nom.merge(_ct_tnl, on=['MES', 'AÑO'], how='left').fillna(0)
        ct_aus['pct_nomina_tnl'] = ct_aus.apply(
            lambda r: round(r['nomina_tnl'] / r['nomina'] * 100, 2) if r['nomina'] > 0 else 0, axis=1
        )
        ct_aus['mes_num'] = ct_aus['MES'].map(_MESES_ORDER).fillna(0)
        ct_aus = ct_aus.sort_values(['AÑO', 'mes_num'])
        ct_aus['label']         = ct_aus['MES'].str.title() + ' ' + ct_aus['AÑO'].astype(str)
        ct_aus['tienda']        = '__TOTAL__'
        ct_aus['var_pct_mm']    = ct_aus['pct_nomina_tnl'].diff().round(2)
        ct_aus['var_dinero_mm'] = ct_aus['nomina_tnl'].diff().round(0)
        for _col in ['var_pct_mm', 'var_dinero_mm']:
            ct_aus[_col] = ct_aus[_col].astype(object).where(pd.notna(ct_aus[_col]), None)
        _comp_aus_cols = ['tienda', 'label', 'MES', 'AÑO', 'nomina', 'nomina_tnl', 'pct_nomina_tnl', 'var_pct_mm', 'var_dinero_mm']
        _comp_aus_rows = comp_aus[_comp_aus_cols].to_dict('records') + ct_aus[_comp_aus_cols].to_dict('records')

        # ── Tendencia mensual (sin filtros de usuario, solo conceptos mapeados) ──
        df_cal     = df_all[df_all['Concepto'].isin(known_concepts)].copy()
        df_tnl_cal = df_cal[df_cal['Concepto'].isin(tnl_set)]
        cal_n = df_cal.groupby(['MES', 'AÑO'], as_index=False).agg(
            nomina=('Devengo', 'sum'), horas=('Horas Movto.', 'sum'),
        )
        cal_t = df_tnl_cal.groupby(['MES', 'AÑO'], as_index=False).agg(
            nom_tnl=('Devengo', 'sum'),
            hrs_tnl=('Horas Movto.', 'sum'),
            personas=('Tercero', 'nunique'),
        )
        cal = cal_n.merge(cal_t, on=['MES', 'AÑO'], how='left').fillna(0)
        cal['pct_tnl'] = cal.apply(
            lambda r: round(r['nom_tnl'] / r['nomina'] * 100, 2) if r['nomina'] else 0, axis=1
        )
        cal['pct_aus_cal'] = cal.apply(
            lambda r: round(r['hrs_tnl'] / r['horas'] * 100, 2) if r['horas'] else 0, axis=1
        )
        cal['label']   = cal['MES'].str.title() + ' ' + cal['AÑO'].astype(str)
        cal['mes_num'] = cal['MES'].map(_MESES_ORDER).fillna(0)
        cal = cal.sort_values(['AÑO', 'mes_num']).drop(columns=['mes_num'])

        # ── Opciones de filtros ───────────────────────────────────────────────
        df_all_norm = df_all.copy()
        df_all_norm['Tercero'] = df_all_norm['Tercero'].astype(str).str.strip()

        meses           = sorted(df_all['MES'].dropna().unique().tolist(), key=_month_sort_key)
        anios           = sorted(df_all['AÑO'].dropna().astype(int).unique().tolist())
        tiendas         = sorted(df_all['Descripción C.O. Movimiento'].dropna().unique().tolist())
        tipos_concepto  = sorted(conceptos['Tipo de Concepto'].dropna().unique().tolist())
        descs_concepto  = sorted(df_all['Descripción Concepto'].dropna().unique().tolist())

        # Empleados presentes en nómina (para filtros de empleado y cargo)
        terceros_set = set(df_all_norm['Tercero'].dropna().unique())
        emp_nomina   = emp[emp['Cédula'].isin(terceros_set)].drop_duplicates(subset=['Cédula'])
        empleados_list = [
            {'cc': r['Cédula'], 'nombre': r['Nombre y Apellido']}
            for _, r in emp_nomina.sort_values('Nombre y Apellido').iterrows()
        ]
        cargos_list = sorted(emp_nomina['Cargo'].dropna().unique().tolist())

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
            'tabla_tiendas':           _tiendas_rows,
            'tabla_conceptos_full':    _conceptos_full_rows,
            'tabla_colaboradores':     _colab_rows,
            'comparacion_mensual_aus': _comp_aus_rows,
            'calendario':              cal.to_dict('records'),
            'meses_disponibles':                  meses,
            'anios_disponibles':                  anios,
            'tiendas_disponibles':                tiendas,
            'tipos_concepto_disponibles':         tipos_concepto,
            'descripciones_concepto_disponibles': descs_concepto,
            'empleados_disponibles':              empleados_list,
            'cargos_disponibles':                 cargos_list,
        })


class DashboardNominaVentaView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        df_nom_all = _load_nomina()
        df_ven_all = _load_ventas()
        conceptos  = _load_conceptos()

        nov_set        = set(conceptos[conceptos['Tipo de Concepto'] == 'NOVEDADES']['Concepto'])
        # Conceptos mapeados: PBI excluye filas cuyo código no existe en el diccionario
        known_concepts = set(conceptos['Concepto'])

        mes    = request.query_params.get('mes', '').upper().strip()
        anio   = request.query_params.get('anio', '').strip()
        tienda = request.query_params.get('tienda', '').strip()

        # Filtrar nómina a solo conceptos mapeados (igual que PBI)
        df_nom_all_mapped = df_nom_all[df_nom_all['Concepto'].isin(known_concepts)]

        df_nom = df_nom_all_mapped.copy()
        df_ven = df_ven_all.copy()
        if mes:
            df_nom = df_nom[df_nom['MES'] == mes]
            df_ven = df_ven[df_ven['MES'] == mes]
        if anio:
            df_nom = df_nom[df_nom['AÑO'].astype(str) == anio]
            df_ven = df_ven[df_ven['AÑO'].astype(str) == anio]
        if tienda:
            df_nom = df_nom[df_nom['Descripción C.O. Movimiento'] == tienda]
            # OMNICANAL no es una fila en ventas.xlsx — su venta es la columna OMNICANAL
            # de todas las tiendas; no filtrar df_ven para poder sumar esa columna.
            if tienda != 'OMNICANAL':
                df_ven = df_ven[df_ven['Descripción C.O. Movimiento'] == tienda]

        # El Excel de ventas tiene DOS columnas: 'Venta General' (físico) y 'Venta OMNICANAL' (digital)
        # No existe una fila 'OMNICANAL' — cada tienda tiene ambas columnas.
        ven_col_gen = next((c for c in df_ven_all.columns if 'Venta General' in c), None)
        ven_col_omn = next((c for c in df_ven_all.columns if 'OMNICANAL' in c.upper() and c != ven_col_gen), None)

        df_tda_nom = df_nom[~df_nom['Descripción C.O. Movimiento'].isin(_DIRECCION_CENTROS)]
        df_nov     = df_tda_nom[df_tda_nom['Concepto'].isin(nov_set)]

        # ── KPIs ─────────────────────────────────────────────────────────────────
        # 'Venta General' = total (físico + omnicanal incluido)
        # 'Venta OMNICANAL' = subconjunto digital de 'Venta General'
        # → venta_tiendas = Venta General - Venta OMNICANAL (solo físico)
        nomina_total = float(df_nom['Devengo'].sum())
        if tienda == 'OMNICANAL':
            # Su venta = suma de la columna Venta OMNICANAL de todas las tiendas
            venta_omnicanal = float(df_ven[ven_col_omn].sum()) if ven_col_omn else 0
            venta_total     = venta_omnicanal
            venta_tiendas   = 0.0
        else:
            venta_total     = float(df_ven[ven_col_gen].sum()) if ven_col_gen else 0
            venta_omnicanal = float(df_ven[ven_col_omn].sum()) if ven_col_omn else 0
            venta_tiendas   = venta_total - venta_omnicanal

        # OMNICANAL usa venta_total (=venta_omnicanal) como denominador
        # Tiendas físicas usan venta_tiendas (física); global usa venta_total
        _pct_nom_denom = (venta_total    if tienda == 'OMNICANAL'
                          else venta_tiendas if tienda
                          else venta_total)
        pct_nom_venta       = round(nomina_total    / _pct_nom_denom * 100, 2) if _pct_nom_denom else 0
        pct_tiendas_venta   = round(venta_tiendas   / venta_total    * 100, 2) if venta_total else 0
        pct_omnicanal_venta = round(venta_omnicanal / venta_total    * 100, 2) if venta_total else 0

        # ── Tabla tiendas ────────────────────────────────────────────────────────
        nom_all = df_nom.groupby('Descripción C.O. Movimiento', as_index=False).agg(nomina=('Devengo', 'sum'))
        agg_ven = {}
        if ven_col_gen: agg_ven['venta_total_row']   = (ven_col_gen, 'sum')  # total por tienda
        if ven_col_omn: agg_ven['venta_omnicanal_row'] = (ven_col_omn, 'sum')
        if agg_ven:
            ven_all = df_ven.groupby('Descripción C.O. Movimiento', as_index=False).agg(**agg_ven)
        else:
            ven_all = pd.DataFrame(columns=['Descripción C.O. Movimiento'])

        tab = nom_all.merge(ven_all, on='Descripción C.O. Movimiento', how='outer').fillna(0)
        tab = tab.rename(columns={'Descripción C.O. Movimiento': 'tienda'})
        if 'venta_total_row'     not in tab.columns: tab['venta_total_row']     = 0
        if 'venta_omnicanal_row' not in tab.columns: tab['venta_omnicanal_row'] = 0
        tab['venta_tiendas_row'] = tab['venta_total_row'] - tab['venta_omnicanal_row']
        # OMNICANAL CO: su venta total = suma de la columna Venta OMNICANAL de todas las tiendas
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
            else 0,
            axis=1,
        )
        tab['pct_tda'] = tab.apply(lambda r: round(r['venta_tiendas_row'] / r['venta_total_row'] * 100, 2) if r['venta_total_row'] > 0 else 0, axis=1)
        tab['pct_omn'] = tab.apply(lambda r: round(r['venta_omnicanal_row'] / r['venta_total_row'] * 100, 2) if r['venta_total_row'] > 0 else 0, axis=1)
        # Cuando OMNICANAL está seleccionado, df_ven no fue filtrado → eliminar tiendas extras
        if tienda == 'OMNICANAL':
            tab = tab[tab['tienda'] == 'OMNICANAL']
        tab = tab.sort_values('nomina', ascending=False)
        # Fila Total — mismo denominador que el KPI principal
        _tot_denom = (venta_total    if tienda == 'OMNICANAL'
                      else venta_tiendas if tienda
                      else venta_total)
        _tabla_rows = tab[['tienda', 'venta_total_row', 'venta_tiendas_row',
                            'venta_omnicanal_row', 'nomina', 'pct_nom', 'pct_tda', 'pct_omn']].to_dict('records')
        _tabla_rows.append({
            'tienda': '__TOTAL__',
            'venta_total_row': round(venta_total), 'venta_tiendas_row': round(venta_tiendas),
            'venta_omnicanal_row': round(venta_omnicanal), 'nomina': round(nomina_total),
            'pct_nom': round(nomina_total / _tot_denom * 100, 2) if _tot_denom else 0,
            'pct_tda': pct_tiendas_venta, 'pct_omn': pct_omnicanal_venta,
        })

        # ── Tendencia (respeta tienda, ignora mes para mostrar evolución completa) ─
        tend_nom = df_nom_all_mapped.copy()
        tend_ven = df_ven_all.copy()
        if tienda:
            tend_nom = tend_nom[tend_nom['Descripción C.O. Movimiento'] == tienda]
            # OMNICANAL no tiene filas en ventas — keep all para sumar columna por mes
            if tienda != 'OMNICANAL':
                tend_ven = tend_ven[tend_ven['Descripción C.O. Movimiento'] == tienda]

        # Para DIRECCION_CENTROS filtrados, incluir el CO; de lo contrario excluirlos
        if tienda in _DIRECCION_CENTROS:
            df_tda_tend = tend_nom
        else:
            df_tda_tend = tend_nom[~tend_nom['Descripción C.O. Movimiento'].isin(_DIRECCION_CENTROS)]
        t_n = df_tda_tend.groupby(['MES', 'AÑO'], as_index=False).agg(nomina=('Devengo', 'sum'))
        agg_tend = {}
        if ven_col_gen: agg_tend['ventas_gen'] = (ven_col_gen, 'sum')
        if ven_col_omn: agg_tend['ventas_omn'] = (ven_col_omn, 'sum')
        if agg_tend:
            t_v = tend_ven.groupby(['MES', 'AÑO'], as_index=False).agg(**agg_tend)
        else:
            t_v = pd.DataFrame(columns=['MES', 'AÑO'])
        tend = t_n.merge(t_v, on=['MES', 'AÑO'], how='left').fillna(0)
        if 'ventas_gen' not in tend.columns: tend['ventas_gen'] = 0
        if 'ventas_omn' not in tend.columns: tend['ventas_omn'] = 0
        # OMNICANAL: venta = columna Venta OMNICANAL; demás: venta física = General - OMNICANAL
        if tienda == 'OMNICANAL':
            tend['ventas'] = tend['ventas_omn']
        else:
            tend['ventas'] = tend['ventas_gen'] - tend['ventas_omn']
        tend['pct']     = tend.apply(lambda r: round(r['nomina'] / r['ventas'] * 100, 2) if r['ventas'] > 0 else 0, axis=1)
        tend['mes_num'] = tend['MES'].map(_MESES_ORDER).fillna(0)
        tend = tend.sort_values(['AÑO', 'mes_num'])
        tend['label'] = tend['MES'].str.title() + ' ' + tend['AÑO'].astype(str)
        tend = tend.drop(columns=['mes_num', 'ventas_gen', 'ventas_omn'])

        # ── Novedades por tienda (agrupado) — incluye todos los COs (tiendas + centros) ──
        _nov_all  = df_nom[df_nom['Concepto'].isin(nov_set)]
        nov_nom_t = df_nom.groupby('Descripción C.O. Movimiento', as_index=False).agg(nomina=('Devengo', 'sum'))
        nov_nov_t = _nov_all.groupby('Descripción C.O. Movimiento', as_index=False).agg(
            novedades=('Devengo', 'sum'), horas=('Horas Movto.', 'sum'),
        )
        nov_tda = nov_nom_t.merge(nov_nov_t, on='Descripción C.O. Movimiento', how='left').fillna(0)
        nov_tda['pct_novedades'] = nov_tda.apply(
            lambda r: round(r['novedades'] / r['nomina'] * 100, 2) if r['nomina'] > 0 else 0, axis=1
        )
        nov_tda = nov_tda.sort_values('novedades', ascending=False)
        nov_tda = nov_tda.rename(columns={'Descripción C.O. Movimiento': 'tienda'})
        # Fila Total novedades
        _nov_nom_tot = float(df_nom['Devengo'].sum())
        _nov_nov_tot = float(_nov_all['Devengo'].sum())
        _nov_hrs_tot = float(_nov_all['Horas Movto.'].sum()) if 'Horas Movto.' in _nov_all.columns else 0.0
        _nov_rows = nov_tda[['tienda', 'nomina', 'novedades', 'pct_novedades', 'horas']].to_dict('records')
        _nov_rows.append({
            'tienda': '__TOTAL__', 'nomina': round(_nov_nom_tot),
            'novedades': round(_nov_nov_tot),
            'pct_novedades': round(_nov_nov_tot / _nov_nom_tot * 100, 2) if _nov_nom_tot else 0,
            'horas': round(_nov_hrs_tot, 1),
        })

        # ── Comparación mensual por tienda — todos los COs ────────────────────────
        _comp_nov_src = df_nom[df_nom['Concepto'].isin(nov_set)]
        comp_nom = df_nom.groupby(['Descripción C.O. Movimiento', 'MES', 'AÑO'], as_index=False).agg(nomina=('Devengo', 'sum'))
        comp_nov = _comp_nov_src.groupby(['Descripción C.O. Movimiento', 'MES', 'AÑO'], as_index=False).agg(novedades=('Devengo', 'sum'))
        comp = comp_nom.merge(comp_nov, on=['Descripción C.O. Movimiento', 'MES', 'AÑO'], how='left').fillna(0)
        comp['pct_novedades'] = comp.apply(
            lambda r: round(r['novedades'] / r['nomina'] * 100, 2) if r['nomina'] > 0 else 0, axis=1
        )
        comp['mes_num'] = comp['MES'].map(_MESES_ORDER).fillna(0)
        # Orden: OMNICANAL, EURO*, otros centros
        def _co_sort(n): return (0, n) if n == 'OMNICANAL' else ((1, n) if str(n).startswith('EURO') else (2, n))
        comp['_sort'] = comp['Descripción C.O. Movimiento'].apply(_co_sort)
        comp = comp.sort_values(['_sort', 'AÑO', 'mes_num']).drop(columns=['_sort'])
        comp['label'] = comp['MES'].str.title() + ' ' + comp['AÑO'].astype(str)
        comp = comp.rename(columns={'Descripción C.O. Movimiento': 'tienda'})
        comp['var_pct_mm']    = comp.groupby('tienda')['pct_novedades'].diff().round(2)
        comp['var_dinero_mm'] = comp.groupby('tienda')['novedades'].diff().round(0)
        for col in ['var_pct_mm', 'var_dinero_mm']:
            comp[col] = comp[col].astype(object).where(pd.notna(comp[col]), None)
        # Fila Total por mes
        ct_nom = df_nom.groupby(['MES', 'AÑO'], as_index=False).agg(nomina=('Devengo', 'sum'))
        ct_nov = _comp_nov_src.groupby(['MES', 'AÑO'], as_index=False).agg(novedades=('Devengo', 'sum'))
        ct = ct_nom.merge(ct_nov, on=['MES', 'AÑO'], how='left').fillna(0)
        ct['pct_novedades'] = ct.apply(lambda r: round(r['novedades'] / r['nomina'] * 100, 2) if r['nomina'] > 0 else 0, axis=1)
        ct['mes_num'] = ct['MES'].map(_MESES_ORDER).fillna(0)
        ct = ct.sort_values(['AÑO', 'mes_num'])
        ct['label']         = ct['MES'].str.title() + ' ' + ct['AÑO'].astype(str)
        ct['tienda']        = '__TOTAL__'
        ct['var_pct_mm']    = ct['pct_novedades'].diff().round(2)
        ct['var_dinero_mm'] = ct['novedades'].diff().round(0)
        for col in ['var_pct_mm', 'var_dinero_mm']:
            ct[col] = ct[col].astype(object).where(pd.notna(ct[col]), None)
        _comp_cols = ['tienda', 'label', 'MES', 'AÑO', 'nomina', 'novedades', 'pct_novedades', 'var_pct_mm', 'var_dinero_mm']
        _comp_rows = comp[_comp_cols].to_dict('records') + ct[_comp_cols].to_dict('records')
        comp = comp.drop(columns=['mes_num'])

        meses   = sorted(df_nom_all_mapped['MES'].dropna().unique().tolist(), key=_month_sort_key)
        anios   = sorted(df_nom_all_mapped['AÑO'].dropna().astype(int).unique().tolist())
        tiendas_list = sorted(
            df_nom_all_mapped[~df_nom_all_mapped['Descripción C.O. Movimiento'].isin(_DIRECCION_CENTROS)]
            ['Descripción C.O. Movimiento'].dropna().unique().tolist()
        )

        return Response({
            'kpis': {
                'nomina_total':       round(nomina_total),
                'venta_total':        round(venta_total),
                'venta_tiendas':      round(venta_tiendas),
                'venta_omnicanal':    round(venta_omnicanal),
                'pct_nom_venta':      pct_nom_venta,
                'pct_tiendas_venta':  pct_tiendas_venta,
                'pct_omnicanal_venta': pct_omnicanal_venta,
            },
            'tabla_tiendas': _tabla_rows,
            'tendencia':         tend[['label', 'MES', 'AÑO', 'nomina', 'ventas', 'pct']].to_dict('records'),
            'novedades_tienda':  _nov_rows,
            'comparacion_mensual': _comp_rows,
            'meses_disponibles':  meses,
            'anios_disponibles':  anios,
            'tiendas_disponibles': tiendas_list,
        })


class DashboardAntiguedadView(APIView):
    permission_classes = [IsAuthenticated]

    _PAGE_SIZE_DEFAULT = 50
    _PAGE_SIZE_MAX     = 200

    def get(self, request):
        import math
        df_all = _load_empleados()

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

        df = df_all.copy()
        if tienda:
            df = df[df['Centro de Operación'] == tienda]
        if cargo:
            df = df[df['Cargo'].str.contains(cargo, case=False, na=False)]
        if tipo_contrato:
            df = df[df['Tipo de Contrato'] == tipo_contrato]
        if sexo:
            df = df[df['Sexo'] == sexo]
        if cedula:
            df = df[df['Cédula'].astype(str).str.contains(cedula, na=False)]
        if nombre:
            df = df[df['Nombre y Apellido'].str.contains(nombre, case=False, na=False)]

        today = date.today()
        df['_fecha'] = pd.to_datetime(df['F. Ingreso Euro'], errors='coerce')
        df['_dias']  = df['_fecha'].apply(
            lambda x: (today - x.date()).days if pd.notna(x) else 0
        )
        df['_anios'] = df['_dias'] / 365.25

        total     = len(df)
        avg_dias  = float(df['_dias'].mean()) if total else 0
        avg_anios = float(df['_anios'].mean()) if total else 0
        pct_total = round(total / len(df_all) * 100, 2) if df_all.shape[0] else 0

        td = int(avg_dias)
        ya, ym, yd = td // 365, (td % 365) // 30, (td % 365) % 30
        avg_texto = f'{ya} años, {ym} meses y {yd} días'

        # Por tienda — ascending=False: recharts vertical dibuja el primer item arriba → más antiguos arriba
        por_tda = df.groupby('Centro de Operación', as_index=False).agg(
            empleados=('Cédula', 'count'),
            prom_anios=('_anios', 'mean'),
        )
        por_tda['prom_anios'] = por_tda['prom_anios'].round(2)
        por_tda = por_tda.sort_values('prom_anios', ascending=False)
        por_tda = por_tda.rename(columns={'Centro de Operación': 'tienda'})

        # Donuts
        por_sexo = df['Sexo'].value_counts().reset_index()
        por_sexo.columns = ['name', 'value']

        por_contrato = df['Tipo de Contrato'].value_counts().reset_index()
        por_contrato.columns = ['name', 'value']

        # Detalle paginado — ordenado por antigüedad descendente
        det = df[['Cédula', 'Nombre y Apellido', 'Centro de Operación', 'Cargo',
                  'Tipo de Contrato', 'Sexo', '_fecha', '_dias', '_anios']].copy()
        det['_fecha'] = det['_fecha'].dt.strftime('%d/%m/%Y').fillna('')
        det['_anios'] = det['_anios'].round(2)
        det = det.sort_values('_dias', ascending=False)
        det = det.rename(columns={
            'Cédula': 'cedula',
            'Nombre y Apellido': 'nombre',
            'Centro de Operación': 'tienda',
            'Cargo': 'cargo',
            'Tipo de Contrato': 'tipo_contrato',
            'Sexo': 'sexo',
            '_fecha': 'fecha_ingreso',
            '_dias': 'antiguedad_dias',
            '_anios': 'antiguedad_anios',
        })

        total_registros = len(det)
        total_paginas   = max(1, math.ceil(total_registros / page_size))
        page            = min(page, total_paginas)
        inicio          = (page - 1) * page_size
        det_page        = det.iloc[inicio: inicio + page_size]

        tiendas   = sorted(df_all['Centro de Operación'].dropna().unique().tolist())
        contratos = sorted(df_all['Tipo de Contrato'].dropna().unique().tolist())
        sexos     = sorted(df_all['Sexo'].dropna().unique().tolist())

        return Response({
            'kpis': {
                'total_empleados': total,
                'total_todos': len(df_all),
                'pct_total': pct_total,
                'avg_dias': round(avg_dias),
                'avg_anios': round(avg_anios, 2),
                'avg_texto': avg_texto,
            },
            'por_tienda': por_tda.to_dict('records'),
            'por_sexo': por_sexo.to_dict('records'),
            'por_contrato': por_contrato.to_dict('records'),
            'detalle': det_page.to_dict('records'),
            'paginacion': {
                'pagina_actual': page,
                'total_paginas': total_paginas,
                'total_registros': total_registros,
                'page_size': page_size,
            },
            'tiendas_disponibles': tiendas,
            'contratos_disponibles': contratos,
            'sexos_disponibles': sexos,
        })


class DashboardCacheReloadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        _CACHE.clear()
        return Response({'ok': True, 'message': 'Caché limpiado. Los datos se recargarán en la próxima consulta.'})
