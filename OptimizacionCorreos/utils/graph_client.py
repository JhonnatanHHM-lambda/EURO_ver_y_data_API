"""
Cliente Microsoft Graph para el buzón `abastecimiento@londonogomez.com`.

Autenticación: OAuth 2.0 **Client Credentials Flow** con **certificado X.509**
(no se aceptan client secrets — política de TI de LG).

Operaciones:
  • obtener_access_token()          — token de aplicación
  • listar_mensajes(filtro, top)    — listado del Inbox del buzón
  • leer_mensaje(message_id)        — cuerpo + headers de un mensaje
  • extraer_otp_dian(timeout, since)
        Espera/poll del buzón hasta encontrar el correo de la DIAN con el OTP
        de RADIAN. Extrae el código y lo devuelve.

Permisos requeridos en Entra ID (ya configurados por LG):
  Mail.Read   (Application)

Documentación oficial:
  https://learn.microsoft.com/en-us/graph/api/user-list-messages
"""
from __future__ import annotations

import datetime as dt
import re
import time
import urllib.parse as urlparse
from pathlib import Path
from typing import Any, Optional

import httpx
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from msal import ConfidentialClientApplication

from .config import get_settings

GRAPH = "https://graph.microsoft.com/v1.0"
SCOPE = ["https://graph.microsoft.com/.default"]


def _load_cert(private_path: str, public_path: str) -> dict:
    """Construye el bloque `client_credential` que MSAL espera."""
    pk_bytes = Path(private_path).read_bytes()
    cer_bytes = Path(public_path).read_bytes()
    cert = x509.load_pem_x509_certificate(cer_bytes)
    thumbprint_sha1 = cert.fingerprint(hashes.SHA1()).hex().upper()
    return {
        "private_key": pk_bytes.decode("utf-8"),
        "thumbprint": thumbprint_sha1,
        "public_certificate": cer_bytes.decode("utf-8"),
    }


class GraphClient:
    """Cliente para operaciones de lectura sobre el buzón designado."""

    # La DIAN no envía un OTP numérico: envía un correo con una URL única
    # https://catalogo-vpfe.dian.gov.co/User/AuthToken?pk=...&rk=...&token=<uuid>
    # `pk` = IdentificationType|UserCode (ej. 10910094|42887005)
    # `rk` = NIT empresa
    # `token` = UUID de acceso (uso único)
    URL_DIAN_AUTH = re.compile(
        r"https?://catalogo-vpfe\.dian\.gov\.co/User/AuthToken\?[^\s\"'<>]+",
        re.IGNORECASE,
    )
    UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                         r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")

    def __init__(self, mailbox: Optional[str] = None,
                 cert_priv: Optional[str] = None,
                 cert_pub: Optional[str] = None,
                 client_secret: Optional[str] = None):
        s = get_settings()
        self.tenant_id = s.graph_tenant_id
        self.client_id = s.graph_client_id
        self.mailbox = mailbox or s.graph_mailbox_upn
        self.cert_priv = cert_priv or s.graph_cert_private_key_path
        self.cert_pub = cert_pub or s.graph_cert_public_path
        # Client secret tiene prioridad sobre certificado si está disponible
        self.client_secret = client_secret or s.graph_client_secret
        self._token: Optional[str] = None
        self._token_exp: float = 0.0

    # ── auth ────────────────────────────────────────────────────────────────
    def _app(self) -> ConfidentialClientApplication:
        # Usar client secret si está configurado; si no, intentar con certificado
        if self.client_secret:
            cred = self.client_secret
        else:
            cred = _load_cert(self.cert_priv, self.cert_pub)
        return ConfidentialClientApplication(
            client_id=self.client_id,
            authority=f"https://login.microsoftonline.com/{self.tenant_id}",
            client_credential=cred,
        )

    def obtener_access_token(self) -> str:
        if self._token and time.time() < self._token_exp - 60:
            return self._token
        app = self._app()
        res = app.acquire_token_for_client(scopes=SCOPE)
        if "access_token" not in res:
            raise RuntimeError(
                "Graph token error: "
                f"{res.get('error')} / {res.get('error_description')}"
            )
        self._token = res["access_token"]
        self._token_exp = time.time() + int(res.get("expires_in", 3600))
        return self._token

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.obtener_access_token()}",
                "Accept": "application/json"}

    # ── operaciones de buzón ────────────────────────────────────────────────
    def listar_mensajes(
        self,
        top: int = 25,
        filtro_odata: Optional[str] = None,
        order_by: str = "receivedDateTime desc",
        select: str = "id,receivedDateTime,subject,from,bodyPreview,hasAttachments",
    ) -> list[dict]:
        params: dict[str, Any] = {
            "$top": top,
            "$orderby": order_by,
            "$select": select,
        }
        if filtro_odata:
            params["$filter"] = filtro_odata
        url = f"{GRAPH}/users/{self.mailbox}/messages"
        with httpx.Client(timeout=30.0) as c:
            r = c.get(url, headers=self._headers(), params=params)
        r.raise_for_status()
        return r.json().get("value", [])

    def leer_mensaje(self, message_id: str) -> dict:
        url = f"{GRAPH}/users/{self.mailbox}/messages/{message_id}"
        with httpx.Client(timeout=30.0) as c:
            r = c.get(url, headers=self._headers())
        r.raise_for_status()
        return r.json()

    # ── Acceso DIAN (URL única con token UUID) ──────────────────────────────
    def extraer_acceso_dian(
        self,
        since: Optional[dt.datetime] = None,
        timeout_s: int = 240,
        intervalo_s: int = 5,
        remitente_contiene: str = "dian.gov.co",
        cc_rep: Optional[str] = None,
        nit: Optional[str] = None,
    ) -> dict:
        """
        Polling del Inbox hasta encontrar el correo de la DIAN posterior a
        `since` con la URL de acceso (`/User/AuthToken?...&token=<uuid>`).
        Devuelve `{access_url, token, pk, rk, message_id, received_at, asunto, destinatario}`.

        Si se pasan `cc_rep` y `nit`, exige que la URL contenga `pk=*|<cc_rep>` y
        `rk=<nit>` — así cuando varios usuarios solicitan tokens simultáneamente
        agarra el del usuario correcto (no el de otro destinatario LG).
        """
        since = since or (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=5))
        since_str = since.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        filtro = f"receivedDateTime ge {since_str}"
        deadline = time.time() + timeout_s
        ultimo_visto: set[str] = set()
        while time.time() < deadline:
            mensajes = self.listar_mensajes(top=20, filtro_odata=filtro)
            for m in mensajes:
                if m["id"] in ultimo_visto:
                    continue
                ultimo_visto.add(m["id"])
                from_addr = (
                    (m.get("from") or {}).get("emailAddress", {}).get("address", "") or ""
                ).lower()
                if remitente_contiene and remitente_contiene not in from_addr:
                    continue
                detalle = self.leer_mensaje(m["id"])
                cuerpo_html = (detalle.get("body") or {}).get("content") or ""
                cuerpo = cuerpo_html.replace("&amp;", "&")
                urls = self.URL_DIAN_AUTH.findall(cuerpo)
                for url in urls:
                    # URL viene con %7C en vez de | — normalizamos para los
                    # filtros de NIT/CC.
                    url_norm = urlparse.unquote(url)
                    if nit and f"rk={nit}" not in url_norm:
                        continue
                    if cc_rep and f"|{cc_rep}" not in url_norm:
                        continue
                    token_m = self.UUID_RE.search(url)
                    token = token_m.group(0) if token_m else None
                    pk = re.search(r"pk=([^&]+)", url_norm)
                    rk = re.search(r"rk=([^&]+)", url_norm)
                    return {
                        "access_url": url,
                        "token": token,
                        "pk": pk.group(1) if pk else None,
                        "rk": rk.group(1) if rk else None,
                        "message_id": m["id"],
                        "received_at": m.get("receivedDateTime"),
                        "asunto": detalle.get("subject"),
                        "destinatario": detalle.get("subject", "").replace("Estimado (a),", "").strip(),
                        "from": from_addr,
                    }
            time.sleep(intervalo_s)
        criterio = []
        if nit: criterio.append(f"NIT={nit}")
        if cc_rep: criterio.append(f"CC={cc_rep}")
        criterio = ", ".join(criterio) if criterio else "cualquiera"
        raise TimeoutError(
            f"No llegó correo de la DIAN al buzón {self.mailbox} en {timeout_s}s "
            f"(criterio: {criterio})"
        )

    # alias retrocompat (deprecado)
    def extraer_otp_dian(self, **kw):
        return self.extraer_acceso_dian(**kw)


# ─── smoke test ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import json
    gc = GraphClient()
    print("Solicitando token…")
    tok = gc.obtener_access_token()
    print(f"  ✓ token len={len(tok)}")
    print(f"Últimos 5 mensajes del buzón {gc.mailbox}:")
    for m in gc.listar_mensajes(top=5):
        print(f"  • {m['receivedDateTime']}  {m.get('from',{}).get('emailAddress',{}).get('address','?')}  "
              f"— {m.get('subject','')[:60]}")
