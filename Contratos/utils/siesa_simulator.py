"""Simulador de Siesa — lee empleados_simulados.json hasta tener integración real."""
import json
import os
from datetime import date

SIMULADOS_PATH = os.path.join(
    os.path.dirname(__file__), '..', '..', 'data', 'empleados_simulados.json'
)


def obtener_empleados_por_dias(fecha_objetivo: date) -> list:
    try:
        with open(SIMULADOS_PATH, 'r', encoding='utf-8') as f:
            empleados = json.load(f)
        return [
            e for e in empleados
            if date.fromisoformat(e['fecha_finalizacion']) == fecha_objetivo
        ]
    except FileNotFoundError:
        return []


def obtener_empleados_en_rango(fecha_inicio: date, fecha_fin: date) -> list:
    """Retorna empleados cuyo contrato vence entre fecha_inicio y fecha_fin (inclusive)."""
    try:
        with open(SIMULADOS_PATH, 'r', encoding='utf-8') as f:
            empleados = json.load(f)
        return [
            e for e in empleados
            if fecha_inicio <= date.fromisoformat(e['fecha_finalizacion']) <= fecha_fin
        ]
    except FileNotFoundError:
        return []


def obtener_todos_los_empleados() -> list:
    try:
        with open(SIMULADOS_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return []
