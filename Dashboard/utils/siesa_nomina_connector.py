"""
Conector SIESA para TODOS los movimientos de nómina (w0602_movto_nomina).
Incluye todos los conceptos y todos los empleados (no solo TNL).
Fuente validada: cédulas de Excel operativos 100% cubiertas (verificado 2026-07).
Join: mv -> w0540_empleados -> w0541_terceros_seleccion (0 sin match verificado).
"""
import logging
import os
from datetime import date, datetime

import pyodbc

from .siesa_ausentismo_connector import CO_NOMBRES, _TNL_IDS

logger = logging.getLogger(__name__)

_TNL_SET = set(_TNL_IDS)

_SQL = """
SELECT
    mv.c0602_rowid                         AS rowid_mv,
    t.c0541_id                             AS cedula,
    RTRIM(CONCAT(
        ISNULL(t.c0541_nombres,  ''), ' ',
        ISNULL(t.c0541_apellido1,''), ' ',
        ISNULL(t.c0541_apellido2,'')
    ))                                     AS nombre,
    cp.c0501_id                            AS concepto_id,
    cp.c0501_descripcion                   AS concepto_desc,
    cp.c0501_ind_naturaleza                AS naturaleza,
    mv.c0602_horas                         AS horas,
    mv.c0602_valor_devengo                 AS valor,
    mv.c0602_dias_tnl                      AS dias_tnl,
    ISNULL(g.c0763_descripcion, '')        AS cargo,
    mv.c0602_id_co_mov                     AS co_codigo,
    mv.c0602_id_periodo % 100              AS mes,
    mv.c0602_id_periodo / 100              AS ano,
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
    return d.year * 100 + d.month


def obtener_nomina_completa(desde: date) -> list:
    """
    Retorna todos los movimientos de nómina desde `desde` hasta el período actual.
    Incluye todos los conceptos (no solo TNL).
    """
    periodo_desde = _periodo_from_date(desde)
    try:
        conn = pyodbc.connect(_build_conn_str(), timeout=300)
        cur = conn.cursor()
        cur.execute(_SQL, [periodo_desde])
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
        conn.close()

        result = []
        for row in rows:
            r = dict(zip(cols, row))

            r['fecha_ingreso'] = _to_date(r['fecha_ingreso'])

            # Cédulas con sufijo '@1' (duplicados en SIESA)
            cedula = (r['cedula'] or '').strip()
            if '@' in cedula:
                cedula = cedula.split('@')[0]
            r['cedula'] = cedula

            r['nombre'] = (r['nombre'] or '').strip()

            # CO nombre desde diccionario estático; fallback al código si no está mapeado
            co = (r['co_codigo'] or '').strip()
            r['co_nombre'] = CO_NOMBRES.get(co, co)

            # Flag TNL: coincide con los 16 conceptos del diccionario Excel (ausentismo)
            r['es_tnl'] = r['concepto_id'] in _TNL_SET

            # dias_tnl = 0 en w0602 para conceptos no-TNL → guardar como None
            if not r.get('dias_tnl'):
                r['dias_tnl'] = None

            result.append(r)

        logger.info(
            "siesa_nomina_connector: %d registros desde período %d",
            len(result), periodo_desde,
        )
        return result
    except Exception as exc:
        logger.error("siesa_nomina_connector.obtener_nomina_completa error: %s", exc)
        return []
