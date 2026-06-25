"""
Conector SIESA real (SQL Server via pyodbc).
Reemplaza siesa_simulator en produccion.

EMAIL_OVERRIDE: mientras se hace la transicion a produccion, todos los correos
de notificacion van a jonnathan.henao@lambdaanalytics.co en lugar del correo
real del empleado. Cuando se quite esta constante, los emails van al empleado.
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

EMAIL_OVERRIDE = "jonnathan.henao@lambdaanalytics.co"

_TIPO_DOC = {"C": "CC", "T": "TI", "E": "CE", "P": "PA"}

# Centros de operación cerrados — se excluyen del procesamiento de contratos
_CENTROS_CERRADOS = {'BAR', 'ESC', 'MAR', 'MAZ'}


_SQL = """
    SELECT
        t.c0541_id_tipo_ident                      AS tipo_documento_raw,
        t.c0541_id                                 AS documento,
        RTRIM(CONCAT(
            ISNULL(t.c0541_nombres,  ''), ' ',
            ISNULL(t.c0541_apellido1,''), ' ',
            ISNULL(t.c0541_apellido2,'')
        ))                                         AS nombre_completo,
        g.c0763_descripcion                        AS cargo,
        c.c0550_id_co                              AS centro_op_codigo,
        CAST(c.c0550_fecha_ingreso        AS DATE) AS fecha_inicio,
        CAST(c.c0550_fecha_contrato_hasta AS DATE) AS fecha_fin,
        t.c0541_telefono_1                         AS celular,
        t.c0541_correo                             AS email_siesa
    FROM w0540_empleados e
    INNER JOIN w0541_terceros_seleccion t  ON e.c0540_rowid_prospecto = t.c0541_rowid
    INNER JOIN w0550_contratos c           ON e.c0540_rowid_tercero   = c.c0550_rowid_tercero
    LEFT  JOIN w0763_gh01_cargos g         ON c.c0550_rowid_cargo     = g.c0763_rowid
    WHERE c.c0550_ind_termino_contrato = 1
      AND c.c0550_ind_estado = 1
      AND c.c0550_fecha_contrato_hasta >= ?
      AND c.c0550_fecha_contrato_hasta <= ?
    ORDER BY c.c0550_fecha_contrato_hasta
"""


def _to_date(v):
    if isinstance(v, datetime):
        return v.date()
    return v


def _row_to_dict(row) -> dict:
    tipo_raw = (row.tipo_documento_raw or "").strip()
    fecha_fin = _to_date(row.fecha_fin)
    fecha_inicio = _to_date(row.fecha_inicio)
    return {
        "tipo_documento":       _TIPO_DOC.get(tipo_raw, tipo_raw),
        "documento_id":         (row.documento or "").strip(),
        "nombre_completo":      (row.nombre_completo or "").strip(),
        "cargo":                (row.cargo or "").strip(),
        "centro_operacion":     (row.centro_op_codigo or "").strip(),
        "fecha_inicio_contrato": fecha_inicio,
        "fecha_finalizacion":   fecha_fin,
        "celular":              (row.celular or "").strip(),
        "email":                EMAIL_OVERRIDE,
    }


def obtener_empleados_en_rango(fecha_inicio: date, fecha_fin: date) -> list:
    """Retorna empleados con contratos a termino fijo que vencen entre fecha_inicio y fecha_fin."""
    try:
        conn = pyodbc.connect(_build_conn_str(), timeout=15)
        cur = conn.cursor()
        cur.execute(_SQL, [fecha_inicio, fecha_fin])
        rows = cur.fetchall()
        conn.close()
        resultado = [
            _row_to_dict(r) for r in rows
            if r.fecha_fin and (r.centro_op_codigo or '').strip() not in _CENTROS_CERRADOS
        ]
        logger.info(f"siesa_connector: {len(resultado)} contratos en rango {fecha_inicio} - {fecha_fin}")
        return resultado
    except Exception as exc:
        logger.error(f"siesa_connector.obtener_empleados_en_rango error: {exc}")
        return []
