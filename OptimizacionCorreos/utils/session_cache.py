"""
Cache en memoria para reutilizar una sesión RADIAN autenticada.

La autenticación contra DIAN/RADIAN depende de Playwright, WAF, Turnstile y
correo Graph. Reautenticar en cada ejecución aumenta la probabilidad de falla
cuando el portal está lento o cambia temporalmente. Este cache reduce ese
riesgo reutilizando una sesión viva durante una ventana corta.
"""
from __future__ import annotations

import threading
import time
from typing import Optional

from .dian_client import DianClient

_lock = threading.Lock()
_cliente: Optional[DianClient] = None
_obtenido_en: float = 0.0

# La sesión DIAN suele durar cerca de 30 minutos. Refrescamos antes.
TTL_S = 60 * 25


def set_cliente(cliente: DianClient) -> None:
    global _cliente, _obtenido_en
    with _lock:
        _cliente = cliente
        _obtenido_en = time.time()


def get_cliente_vivo() -> Optional[DianClient]:
    with _lock:
        if _cliente is None:
            return None
        if time.time() - _obtenido_en > TTL_S:
            return None
        return _cliente


def clear() -> None:
    global _cliente, _obtenido_en
    with _lock:
        _cliente = None
        _obtenido_en = 0.0
