"""Cliente mínimo de CapSolver para resolver Cloudflare Turnstile en RADIAN."""
from __future__ import annotations

import time
from typing import Optional

import httpx

from .config import get_settings


def resolver_turnstile(timeout_s: int = 120, intervalo_s: int = 3,
                       url_obj: Optional[str] = None) -> str:
    s = get_settings()
    payload = {
        "clientKey": s.capsolver_api_key,
        "task": {
            "type": "AntiTurnstileTaskProxyLess",
            "websiteKey": s.capsolver_site_key,
            "websiteURL": url_obj or s.dian_login_url,
        },
    }
    with httpx.Client(timeout=30.0) as c:
        r = c.post("https://api.capsolver.com/createTask", json=payload)
        r.raise_for_status()
        data = r.json()
        if data.get("errorId"):
            raise RuntimeError(f"CapSolver createTask: {data}")
        task_id = data["taskId"]
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            time.sleep(intervalo_s)
            poll = c.post("https://api.capsolver.com/getTaskResult",
                          json={"clientKey": s.capsolver_api_key, "taskId": task_id})
            poll.raise_for_status()
            d = poll.json()
            if d.get("errorId"):
                raise RuntimeError(f"CapSolver getTaskResult: {d}")
            if d.get("status") == "ready":
                return d["solution"]["token"]
    raise TimeoutError("CapSolver no resolvió el Turnstile a tiempo")
