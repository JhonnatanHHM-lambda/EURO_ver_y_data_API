"""
Shim de configuración para los clientes copiados (dian_client, graph_client,
capsolver). Lee variables de entorno con prefijo OC_ para no colisionar con
otras apps del proyecto.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass
class Settings:
    # ─── DIAN / RADIAN ──────────────────────────────────────────────────────
    dian_nit: str = os.environ.get("OC_DIAN_NIT", "")
    dian_cc_rep: str = os.environ.get("OC_DIAN_CC_REP", "")
    dian_nombre_rep: str = os.environ.get("OC_DIAN_NOMBRE_REP", "")
    dian_login_url: str = os.environ.get(
        "OC_DIAN_LOGIN_URL",
        "https://catalogo-vpfe.dian.gov.co/User/CompanyLogin",
    )
    dian_auth_url: str = os.environ.get(
        "OC_DIAN_AUTH_URL",
        "https://catalogo-vpfe.dian.gov.co/User/CompanyAuthentication",
    )

    # ─── CapSolver ──────────────────────────────────────────────────────────
    capsolver_api_key: str = os.environ.get("OC_CAPSOLVER_API_KEY", "")
    capsolver_site_key: str = os.environ.get(
        "OC_CAPSOLVER_SITE_KEY",
        "0x4AAAAAAAg1WuNb-OnOa76z",
    )

    # ─── Microsoft Graph ────────────────────────────────────────────────────
    graph_tenant_id: str = os.environ.get("OC_GRAPH_TENANT_ID", "")
    graph_client_id: str = os.environ.get("OC_GRAPH_CLIENT_ID", "")
    graph_mailbox_upn: str = os.environ.get("OC_GRAPH_MAILBOX_UPN", "")
    graph_cert_private_key_path: str = os.environ.get(
        "OC_GRAPH_CERT_KEY_PATH", "./certs/oc_graph.key.pem"
    )
    graph_cert_public_path: str = os.environ.get(
        "OC_GRAPH_CERT_PUB_PATH", "./certs/oc_graph.cer"
    )
    # Client secret — alternativa al certificado (más simple, menos seguro)
    graph_client_secret: str = os.environ.get("OC_GRAPH_CLIENT_SECRET", "")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
