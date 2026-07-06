"""
Motor de conciliación RADIAN ↔ Zimbra para OptimizacionCorreos.

Estrategia de match por niveles:
  N1 — CUFE idéntico → CONCILIADA
  N2 — NIT proveedor + número documento → CONCILIADA
  N3 — NIT proveedor + monto ±1 COP + fecha ±3 días → REVISION_MANUAL
  Sin par en correo → SOLO_RADIAN
  Sin par en RADIAN → SOLO_CORREO

Adaptado de londonogomez-radicacionfacturas/backend/app/conciliacion.py
para trabajar con los modelos Django de este módulo.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Optional

TOLERANCIA_VALOR = Decimal("1.00")
TOLERANCIA_DIAS = 3


def _key_cufe(cufe: Optional[str]) -> Optional[str]:
    return (cufe or "").strip() or None


def _key_nit_num(nit: Optional[str], numero: Optional[str]) -> Optional[str]:
    if nit and numero:
        return f"{nit.strip()}|{numero.strip()}"
    return None


def conciliar(ejecucion, facturas_radian, facturas_correo) -> list:
    """
    Ejecuta la conciliación y retorna lista de dicts con los datos de
    cada ResultadoConciliacion (sin guardar — el caller hace el bulk_create).
    """
    # Construir índices sobre correo
    correo_by_cufe: dict[str, object] = {}
    correo_by_nit_num: dict[str, object] = {}
    for fc in facturas_correo:
        k_cufe = _key_cufe(fc.cufe)
        if k_cufe:
            correo_by_cufe[k_cufe] = fc
        k_nn = _key_nit_num(fc.nit_proveedor, fc.numero)
        if k_nn:
            correo_by_nit_num[k_nn] = fc

    usados_correo: set[int] = set()
    resultados = []

    for fr in facturas_radian:
        match_fc = None
        nivel = ""

        # N1 — CUFE exacto
        k_cufe = _key_cufe(fr.cufe)
        if k_cufe and k_cufe in correo_by_cufe:
            match_fc = correo_by_cufe[k_cufe]
            nivel = "N1"

        # N2 — NIT + número
        if not match_fc:
            k_nn = _key_nit_num(fr.nit_proveedor, fr.numero)
            if k_nn and k_nn in correo_by_nit_num:
                match_fc = correo_by_nit_num[k_nn]
                nivel = "N2"

        # N3 — heurística
        if not match_fc:
            for fc in facturas_correo:
                if fc.id in usados_correo:
                    continue
                if not (fr.nit_proveedor and fc.nit_proveedor):
                    continue
                if fr.nit_proveedor.strip() != fc.nit_proveedor.strip():
                    continue
                if fr.total is not None and fc.total is not None:
                    if abs(fr.total - fc.total) <= TOLERANCIA_VALOR:
                        if fr.fecha_emision and fc.fecha_emision:
                            fecha_fc = (fc.fecha_emision.date()
                                        if hasattr(fc.fecha_emision, "date")
                                        else fc.fecha_emision)
                            delta_dias = abs((fr.fecha_emision - fecha_fc).days)
                            if delta_dias <= TOLERANCIA_DIAS:
                                match_fc = fc
                                nivel = "N3"
                                break
                        else:
                            match_fc = fc
                            nivel = "N3"
                            break

        if match_fc:
            usados_correo.add(match_fc.id)
            estado = (
                "CONCILIADA" if nivel in ("N1", "N2") else "REVISION_MANUAL"
            )
            delta = None
            if fr.total is not None and match_fc.total is not None:
                delta = fr.total - match_fc.total
            resultados.append({
                "ejecucion": ejecucion,
                "factura_radian": fr,
                "factura_correo": match_fc,
                "cufe": fr.cufe or "",
                "numero": fr.numero or "",
                "nit_proveedor": fr.nit_proveedor or "",
                "nombre_proveedor": fr.nombre_proveedor or "",
                "monto_radian": fr.total,
                "monto_correo": match_fc.total,
                "delta_monto": delta,
                "fecha_radian": fr.fecha_emision,
                "fecha_correo": match_fc.fecha_correo,
                "asunto_correo": match_fc.asunto_correo or "",
                "estado": estado,
                "nivel_match": nivel,
            })
        else:
            resultados.append({
                "ejecucion": ejecucion,
                "factura_radian": fr,
                "factura_correo": None,
                "cufe": fr.cufe or "",
                "numero": fr.numero or "",
                "nit_proveedor": fr.nit_proveedor or "",
                "nombre_proveedor": fr.nombre_proveedor or "",
                "monto_radian": fr.total,
                "monto_correo": None,
                "delta_monto": None,
                "fecha_radian": fr.fecha_emision,
                "fecha_correo": None,
                "asunto_correo": "",
                "estado": "SOLO_RADIAN",
                "nivel_match": "",
            })

    # Correos sin par en RADIAN
    for fc in facturas_correo:
        if fc.id in usados_correo:
            continue
        resultados.append({
            "ejecucion": ejecucion,
            "factura_radian": None,
            "factura_correo": fc,
            "cufe": fc.cufe or "",
            "numero": fc.numero or "",
            "nit_proveedor": fc.nit_proveedor or "",
            "nombre_proveedor": fc.nombre_proveedor or "",
            "monto_radian": None,
            "monto_correo": fc.total,
            "delta_monto": None,
            "fecha_radian": None,
            "fecha_correo": fc.fecha_correo,
            "asunto_correo": fc.asunto_correo or "",
            "estado": "SOLO_CORREO",
            "nivel_match": "",
        })

    return resultados
