"""
Conector SIESA para datos de Rotación (activos + retirados).
Fuente: w0550_contratos.
  - Activos:   c0550_ind_estado = 1
  - Retirados: c0550_ind_estado IN (2, 4)

Joins verificados (2026-07):
  - t200_mm_terceros  (f200_rowid)         → cédula, nombre completo
  - w0540_empleados   (c0540_rowid_tercero) → sexo (c0540_ind_sexo: 0=M, 1=F)
  - w0763_gh01_cargos (c0763_rowid)        → descripción cargo
  - w0555_motivos_retiro (c0555_id)        → descripción motivo retiro
  - t285_co_centro_op (f285_id, f285_id_cia=1) → nombre tienda/CO

NOTA: w0541_terceros_seleccion solo cubre 12,441 empleados históricos.
      t200_mm_terceros cubre la totalidad (193,823 filas, rango rowid hasta 215,862).
      Por eso se usa t200 como fuente principal de identificación.

Nombre: formato "AP1 AP2 NOMBRES" — igual al que generan los reportes SIESA (verificado
        contra Excel insumo junio 2026: 89/89 = 100% coincidencia).

Surrogate key: c0550_rowid (PK única verificada 2026-07)
Cédulas con sufijo '@1' → se toma la parte antes del '@'.
"""
import logging
import os
from datetime import date, datetime

import pyodbc

logger = logging.getLogger(__name__)


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


_SQL_RETIRADOS = """
SELECT
    c.c0550_rowid                                         AS rowid_contrato,
    t.f200_id                                             AS cedula,
    RTRIM(CONCAT(
        ISNULL(t.f200_apellido1, ''), ' ',
        ISNULL(t.f200_apellido2, ''), ' ',
        ISNULL(t.f200_nombres,   '')
    ))                                                    AS nombre,
    ISNULL(g.c0763_descripcion, '')                       AS cargo,
    c.c0550_id_co                                         AS co_codigo,
    ISNULL(co.f285_descripcion, c.c0550_id_co)            AS co_nombre,
    CAST(c.c0550_fecha_ingreso       AS DATE)             AS fecha_ingreso,
    CAST(c.c0550_fecha_retiro        AS DATE)             AS fecha_retiro,
    c.c0550_id_motivo_retiro                              AS id_motivo_retiro,
    ISNULL(mr.c0555_descripcion, ISNULL(c.c0550_id_motivo_retiro, '')) AS motivo_retiro,
    c.c0550_salario                                       AS salario,
    c.c0550_salario_anterior                              AS salario_anterior,
    CAST(c.c0550_fecha_contrato_hasta AS DATE)            AS fecha_contrato_hasta,
    CASE c.c0550_ind_termino_contrato WHEN 1 THEN 'F' ELSE 'I' END AS tipo_contrato,
    CASE e.c0540_ind_sexo             WHEN 1 THEN 'F' ELSE 'M' END AS sexo
FROM w0550_contratos c
INNER JOIN t200_mm_terceros     t  ON c.c0550_rowid_tercero    = t.f200_rowid
LEFT  JOIN w0540_empleados      e  ON c.c0550_rowid_tercero    = e.c0540_rowid_tercero
LEFT  JOIN w0763_gh01_cargos    g  ON c.c0550_rowid_cargo      = g.c0763_rowid
LEFT  JOIN w0555_motivos_retiro mr  ON c.c0550_id_motivo_retiro = mr.c0555_id
LEFT  JOIN t285_co_centro_op    co  ON c.c0550_id_co = co.f285_id AND co.f285_id_cia = 1
WHERE c.c0550_ind_estado IN (2, 4)
  AND c.c0550_fecha_retiro >= ?
ORDER BY c.c0550_rowid
"""

_SQL_ACTIVOS = """
SELECT
    c.c0550_rowid                                         AS rowid_contrato,
    t.f200_id                                             AS cedula,
    RTRIM(CONCAT(
        ISNULL(t.f200_apellido1, ''), ' ',
        ISNULL(t.f200_apellido2, ''), ' ',
        ISNULL(t.f200_nombres,   '')
    ))                                                    AS nombre,
    ISNULL(g.c0763_descripcion, '')                       AS cargo,
    c.c0550_id_co                                         AS co_codigo,
    ISNULL(co.f285_descripcion, c.c0550_id_co)            AS co_nombre,
    CAST(c.c0550_fecha_ingreso       AS DATE)             AS fecha_ingreso,
    NULL                                                  AS fecha_retiro,
    NULL                                                  AS id_motivo_retiro,
    ''                                                    AS motivo_retiro,
    c.c0550_salario                                       AS salario,
    c.c0550_salario_anterior                              AS salario_anterior,
    CAST(c.c0550_fecha_contrato_hasta AS DATE)            AS fecha_contrato_hasta,
    CASE c.c0550_ind_termino_contrato WHEN 1 THEN 'F' ELSE 'I' END AS tipo_contrato,
    CASE e.c0540_ind_sexo             WHEN 1 THEN 'F' ELSE 'M' END AS sexo
FROM w0550_contratos c
INNER JOIN t200_mm_terceros  t  ON c.c0550_rowid_tercero = t.f200_rowid
LEFT  JOIN w0540_empleados   e  ON c.c0550_rowid_tercero = e.c0540_rowid_tercero
LEFT  JOIN w0763_gh01_cargos g  ON c.c0550_rowid_cargo   = g.c0763_rowid
LEFT  JOIN t285_co_centro_op co  ON c.c0550_id_co = co.f285_id AND co.f285_id_cia = 1
WHERE c.c0550_ind_estado = 1
ORDER BY c.c0550_rowid
"""


def _normalize_row(row, cols, es_activo: bool) -> dict:
    r = dict(zip(cols, row))

    cedula = (r['cedula'] or '').strip()
    if '@' in cedula:
        cedula = cedula.split('@')[0]
    r['cedula'] = cedula

    r['nombre']         = (r['nombre'] or '').strip()
    r['cargo']          = (r['cargo'] or '').strip()
    r['motivo_retiro']  = (r['motivo_retiro'] or '').strip()
    r['id_motivo_retiro'] = (r['id_motivo_retiro'] or '').strip()

    co = (r['co_codigo'] or '').strip()
    r['co_codigo'] = co
    r['co_nombre'] = (r.get('co_nombre') or co).strip()

    r['fecha_ingreso']       = _to_date(r['fecha_ingreso'])
    r['fecha_retiro']        = _to_date(r['fecha_retiro'])
    r['fecha_contrato_hasta'] = _to_date(r['fecha_contrato_hasta'])

    r['salario']          = float(r['salario'])          if r['salario']          is not None else None
    r['salario_anterior'] = float(r['salario_anterior']) if r['salario_anterior'] is not None else None

    r['es_activo'] = es_activo
    return r


def obtener_retirados(desde: date) -> list:
    """
    Retorna todos los registros de empleados retirados (ind_estado IN (2,4))
    cuya fecha_retiro >= `desde`.
    """
    try:
        conn = pyodbc.connect(_build_conn_str(), timeout=120)
        cur = conn.cursor()
        cur.execute(_SQL_RETIRADOS, [desde])
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
        conn.close()
        result = [_normalize_row(r, cols, es_activo=False) for r in rows]
        logger.info("siesa_rotacion_connector.retirados: %d registros desde %s", len(result), desde)
        return result
    except Exception as exc:
        logger.error("siesa_rotacion_connector.obtener_retirados error: %s", exc)
        return []


def obtener_activos() -> list:
    """
    Retorna snapshot completo de todos los empleados activos (ind_estado=1).
    """
    try:
        conn = pyodbc.connect(_build_conn_str(), timeout=120)
        cur = conn.cursor()
        cur.execute(_SQL_ACTIVOS)
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
        conn.close()
        result = [_normalize_row(r, cols, es_activo=True) for r in rows]
        logger.info("siesa_rotacion_connector.activos: %d registros", len(result))
        return result
    except Exception as exc:
        logger.error("siesa_rotacion_connector.obtener_activos error: %s", exc)
        return []
