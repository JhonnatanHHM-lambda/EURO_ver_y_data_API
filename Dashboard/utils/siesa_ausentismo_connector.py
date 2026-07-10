"""
Conector SIESA para datos de ausentismo/tiempo-no-laborado.
Fuente correcta: w0602_movto_nomina (movimientos de nómina).
Join: mv -> w0540_empleados -> w0541_terceros_seleccion (join probado: 0 sin match).
Verificado 2026-07: cubre 100% de las claves (cédula+concepto+mes) del Excel operativos.
"""
import logging
import os
from datetime import date, datetime

import pyodbc

logger = logging.getLogger(__name__)

# Mapeo estático CO código → nombre legible.
# No existe tabla de COs en SIESA para esta instancia (verificado 2026-07).
# Los nombres del Excel ("EURO FRONTERA", etc.) se mapean a estos códigos.
CO_NOMBRES = {
    'ADM': 'ADMINISTRACIÓN',
    'ACA': 'EURO ARKADIA LA 80',
    'BAR': 'BARRANQUILLA',
    'BEL': 'EURO BELLO',
    'BER': 'BERLÍN',
    'BIG': 'BIG',
    'CAR': 'EURO BARRANQUILLA CARNAVAL',
    'CAL': 'CALDAS',
    'CED': 'CEDI',
    'CRI': 'CRISTÓBAL',
    'DES': 'DESPOSTAR',
    'EMA': 'EMA',
    'ESC': 'ESCUELA',
    'FLO': 'EURO FLORIDA',
    'FRO': 'EURO FRONTERA',
    'GUA': 'EURO GUADALCANAL',
    'ITA': 'EURO ITAGUI',
    'LAL': 'LA LOMA',
    'LAU': 'EURO LAURELES',
    'LLA': 'EURO LLANOGRANDE',
    'LOB': 'EURO LOS BERNAL',
    'MAR': 'MARINILLA',
    'MAY': 'EURO MAYORISTA',
    'MAZ': 'MAZURÉN',
    'MIX': 'EURO MIXY LOS COLORES',
    'MON': 'EURO MONTERIA PLACES',
    'MUR': 'EURO MURANO ENVIGADO',
    'NUM': 'EURO NUESTRO MONTERIA',
    'OMN': 'OMNICANAL',
    'PAL': 'PALERMO',
    'ROS': 'EURO ROSALES BARRANQUILLA',
    'SAB': 'EURO SABANETA VEGAS PLAZA',
    'SAL': 'EURO LA INFERIOR',
    'TER': 'EURO TERRACINA ENVIGADO',
    'VEG': 'EURO PALMAS PALMA GRANDE',
}

# Códigos de conceptos TIEMPO NO LABORADO (del diccionario de conceptos, verificado contra Excel).
_TNL_IDS = (
    '021', '022', '023', '024', '025', '026', '027', '028',
    '031', '032', '036', '037', '038', '039', '040', '103',
)

_TNL_IN = ', '.join(f"'{c}'" for c in _TNL_IDS)

_SQL = f"""
SELECT
    mv.c0602_rowid                         AS rowid_tnl,
    t.c0541_id                             AS cedula,
    RTRIM(CONCAT(
        ISNULL(t.c0541_nombres,  ''), ' ',
        ISNULL(t.c0541_apellido1,''), ' ',
        ISNULL(t.c0541_apellido2,'')
    ))                                     AS nombre,
    cp.c0501_id                            AS concepto_id,
    cp.c0501_descripcion                   AS concepto_desc,
    CASE cp.c0501_ind_naturaleza
        WHEN 1 THEN 'DEVENGADO'
        WHEN 2 THEN 'DEDUCCION'
        ELSE ''
    END                                    AS tipo_concepto,
    mv.c0602_horas                         AS horas,
    mv.c0602_valor_devengo                 AS valor,
    mv.c0602_dias_tnl                      AS dias,
    ISNULL(g.c0763_descripcion, '')        AS cargo,
    mv.c0602_id_co_mov                     AS co_codigo,
    mv.c0602_id_periodo % 100              AS mes,
    mv.c0602_id_periodo / 100              AS ano,
    mv.c0602_fecha_inicial_tnl             AS fecha_inicio,
    mv.c0602_fecha_final_tnl               AS fecha_fin,
    CASE ISNULL(e.c0540_ind_sexo, 0)
        WHEN 1 THEN 'F'
        ELSE 'M'
    END                                    AS sexo,
    CASE ISNULL(con.c0550_ind_termino_contrato, 0)
        WHEN 1 THEN 'F'
        ELSE 'I'
    END                                    AS tipo_contrato,
    CAST(e.c0540_fecha_ingreso AS DATE)    AS fecha_ingreso
FROM w0602_movto_nomina mv
INNER JOIN w0501_conceptos          cp  ON mv.c0602_rowid_concepto = cp.c0501_rowid
LEFT  JOIN w0540_empleados          e   ON mv.c0602_rowid_tercero  = e.c0540_rowid_tercero
LEFT  JOIN w0541_terceros_seleccion t   ON e.c0540_rowid_prospecto = t.c0541_rowid
LEFT  JOIN w0550_contratos          con ON mv.c0602_rowid_contrato = con.c0550_rowid
LEFT  JOIN w0763_gh01_cargos        g   ON con.c0550_rowid_cargo   = g.c0763_rowid
WHERE mv.c0602_id_periodo >= ?
  AND cp.c0501_id IN ({_TNL_IN})
ORDER BY mv.c0602_rowid
"""


def _build_conn_str() -> str:
    return (
        "DRIVER={ODBC Driver 17 for SQL Server};"
        f"SERVER={os.getenv('SIESA_SERVER', '')};"
        f"DATABASE={os.getenv('SIESA_DB', '')};"
        f"UID={os.getenv('SIESA_UID', '')};"
        f"PWD={os.getenv('SIESA_PWD', '')};"
        "TrustServerCertificate=yes;"
    )


def _to_date(v):
    if isinstance(v, datetime):
        return v.date()
    return v


def _periodo_from_date(d: date) -> int:
    """Convierte date → YYYYMM (formato c0602_id_periodo)."""
    return d.year * 100 + d.month


def obtener_ausentismos(desde: date) -> list:
    """
    Retorna todos los registros TNL desde `desde` hasta hoy.
    `desde` se convierte a período YYYYMM para filtrar en w0602_id_periodo.
    Retorna lista de dicts con claves que coinciden con los campos de AusentismoDato.
    """
    periodo_desde = _periodo_from_date(desde)
    try:
        conn = pyodbc.connect(_build_conn_str(), timeout=60)
        cur = conn.cursor()
        cur.execute(_SQL, [periodo_desde])
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
        conn.close()

        result = []
        for row in rows:
            r = dict(zip(cols, row))
            r['fecha_inicio']  = _to_date(r['fecha_inicio'])
            r['fecha_fin']     = _to_date(r['fecha_fin'])
            r['fecha_ingreso'] = _to_date(r['fecha_ingreso'])

            # Si fecha_inicio es NULL en w0602, derivar desde el período (primer día del mes).
            if r['fecha_inicio'] is None:
                ano, mes = int(r['ano']), int(r['mes'])
                r['fecha_inicio'] = date(ano, mes, 1)

            # SIESA guarda cédulas duplicadas como "12345678@1" — descartar sufijo.
            cedula = (r['cedula'] or '').strip()
            if '@' in cedula:
                cedula = cedula.split('@')[0]
            r['cedula'] = cedula

            result.append(r)

        logger.info(
            "siesa_ausentismo_connector: %d registros desde período %d",
            len(result), periodo_desde,
        )
        return result
    except Exception as exc:
        logger.error("siesa_ausentismo_connector.obtener_ausentismos error: %s", exc)
        return []
