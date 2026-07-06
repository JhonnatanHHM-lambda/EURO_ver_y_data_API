"""
Cliente del portal RADIAN (catalogo-vpfe.dian.gov.co) parametrizado para
Londoño Gómez.

Flujo:
  1. GET  CompanyLogin                → extrae __RequestVerificationToken
  2. CapSolver AntiTurnstile          → cf-turnstile-response
  3. POST CompanyAuthentication       → dispara envío del OTP al correo
                                         (LG tiene una regla de reenvío que lo
                                          enruta a abastecimiento@londonogomez.com)
  4. Graph poll del buzón             → extrae el OTP
  5. POST <endpoint OTP>              → completa autenticación con el código
  6. Sesión autenticada → listar / descargar documentos

Adaptado de:
  Proyectos/Sites/Login.py  +  Proyectos/Sites/Fvdownload.py
"""
from __future__ import annotations

import calendar
import datetime as dt
import json
import time
from urllib.parse import quote
from pathlib import Path
from typing import Any, Optional

import requests
from bs4 import BeautifulSoup

# Desde 2026-06 la DIAN migró el portal a Azure Front Door, que filtra
# requests por TLS fingerprint (JA3/JA4) además de User-Agent. requests
# usa OpenSSL y queda fingerprinted como bot → 403 directo. curl_cffi
# implementa libcurl con boringssl impersonando Chrome a nivel TLS y pasa
# el filtro. Usar curl_cffi en lugar de requests SOLO para el portal DIAN.
try:
    from curl_cffi import requests as _cf_requests  # type: ignore
    _HAS_CURL_CFFI = True
except ImportError:
    _HAS_CURL_CFFI = False

from .capsolver import resolver_turnstile
from .config import get_settings
from .graph_client import GraphClient


class DianAuthError(RuntimeError):
    pass


class DianClient:
    """
    Sesión autenticada contra el portal de recepción de la DIAN.
    Una instancia = una sesión.
    """

    def __init__(self, nit: Optional[str] = None,
                 cc_rep: Optional[str] = None,
                 graph: Optional[GraphClient] = None,
                 evidence_dir: Optional[str | Path] = None,
                 headful: bool = False):
        s = get_settings()
        self.nit = nit or s.dian_nit
        self.cc_rep = cc_rep or s.dian_cc_rep
        if _HAS_CURL_CFFI:
            # Impersonar Chrome 124 (versión soportada con TLS fingerprint
            # estable contra Azure Front Door a 2026-06).
            self.session = _cf_requests.Session(impersonate="chrome124")
        else:
            # Fallback con requests estándar — caerá en 403 contra el portal
            # actual, pero permite levantar el módulo si curl_cffi no está
            # instalado en algún ambiente.
            self.session = requests.Session()
            self.session.headers.update({
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/130.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "es-CO,es;q=0.9,en;q=0.8",
            })
        self.graph = graph
        self.ultimo_otp: dict[str, Any] | None = None
        self._autenticado: bool = False
        self._last_afv_token: Optional[str] = None
        self.headful = headful
        self.evidence_dir: Optional[Path] = None
        if evidence_dir:
            self.set_evidence_dir(evidence_dir)

    def set_evidence_dir(self, evidence_dir: str | Path) -> None:
        self.evidence_dir = Path(evidence_dir)
        self.evidence_dir.mkdir(parents=True, exist_ok=True)

    def _capture_page(self, page, filename: str) -> None:
        if not self.evidence_dir:
            return
        page.screenshot(path=str(self.evidence_dir / filename), full_page=True)

    # ── Warm-up de sesión vía Playwright (Azure WAF JS Challenge) ───────────
    def _warmup_con_playwright(self) -> tuple[str, str]:
        """
        Desde 2026-06 la DIAN está detrás de Azure Front Door con WAF que
        emite un *JS Challenge* (`afd_azwaf_jsclearance`). Sin ejecutar JS no
        hay forma de obtener esa cookie, por eso usamos Chromium headless
        sólo para el warm-up: navegamos al login, esperamos el challenge,
        extraemos cookies + `__RequestVerificationToken`, y reusamos todo en
        la sesión normal (curl_cffi/requests) para los pasos siguientes.

        Devuelve (request_token, html_body).
        """
        from playwright.sync_api import sync_playwright
        s = get_settings()
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=not self.headful,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                ],
            )
            ctx = browser.new_context(
                user_agent=("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) "
                              "Chrome/131.0.0.0 Safari/537.36"),
                viewport={"width": 1280, "height": 800},
                locale="es-CO", timezone_id="America/Bogota",
            )
            # Stealth: el WAF detecta navigator.webdriver, ausencia de
            # plugins y otros marcadores de automation.
            ctx.add_init_script("""
                Object.defineProperty(navigator,'webdriver',{get:()=>undefined});
                Object.defineProperty(navigator,'languages',{get:()=>['es-CO','es','en']});
                Object.defineProperty(navigator,'plugins',{get:()=>[1,2,3,4,5]});
                window.chrome = { runtime: {} };
            """)
            page = ctx.new_page()
            page.goto(s.dian_login_url, wait_until="domcontentloaded", timeout=45000)
            # Esperar a que el JS challenge se ejecute y deje la cookie
            page.wait_for_timeout(5000)
            self._capture_page(page, "01_radian_login_warmup.png")
            content = page.content()
            cookies = ctx.cookies()
            browser.close()
        # Trasladar cookies al cliente HTTP normal
        for c in cookies:
            self.session.cookies.set(c["name"], c["value"],
                                       domain=c.get("domain", "catalogo-vpfe.dian.gov.co"),
                                       path=c.get("path", "/"))
        # Extraer __RequestVerificationToken del HTML
        soup = BeautifulSoup(content, "html.parser")
        token_input = soup.find("input", {"name": "__RequestVerificationToken"})
        if not token_input:
            raise DianAuthError(
                "Warm-up Playwright no encontró __RequestVerificationToken. "
                "Posible cambio en el HTML del portal DIAN o JS challenge fallido."
            )
        return token_input.get("value") or "", content

    # ── Paso 1+2: solicitud que dispara el OTP ──────────────────────────────
    def solicitar_otp(self) -> dict:
        """
        Warm-up con Playwright (pasa Azure WAF JS Challenge), resuelve el
        Turnstile con CapSolver y POSTea las credenciales. La DIAN responde
        enviando un OTP al correo del representante legal.
        """
        s = get_settings()
        # Paso 0: Playwright warm-up (cookies AFD_AZWAF + __RequestVerificationToken)
        request_token, _ = self._warmup_con_playwright()

        cf_token = resolver_turnstile(url_obj=s.dian_login_url)

        data = {
            "__RequestVerificationToken": request_token,
            "cf-turnstile-response": cf_token,
            "IdentificationType": "10910094",   # CC
            "UserCode": self.cc_rep,
            "CompanyCode": self.nit,
            "X-Requested-With": "XMLHttpRequest",
        }
        post = self.session.post(s.dian_auth_url, data=data, timeout=30,
                                 headers={"X-Requested-With": "XMLHttpRequest"})
        post.raise_for_status()
        out: dict[str, Any] = {
            "status": post.status_code,
            "solicitado_en": dt.datetime.utcnow().isoformat() + "Z",
            "request_token": request_token,
        }
        # La respuesta suele venir como HTML con un script; capturamos por las dudas
        # cualquier hint de éxito ("Email" / "se ha enviado").
        out["respuesta_preview"] = post.text[:400]
        return out

    # ── Paso 4: traer la URL de acceso del buzón vía Graph ──────────────────
    def esperar_otp_en_buzon(self, timeout_s: int = 240) -> dict:
        """
        Espera el correo de la DIAN con la URL de acceso. Filtra por NIT/CC
        para no agarrar correos de otros usuarios del mismo buzón.
        """
        if self.graph is None:
            self.graph = GraphClient()
        since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=30)
        info = self.graph.extraer_acceso_dian(
            since=since, timeout_s=timeout_s,
            cc_rep=self.cc_rep, nit=self.nit,
        )
        self.ultimo_otp = info
        return info

    # ── Paso 5: activar la URL → la sesión queda autenticada ────────────────
    def _looks_like_login_response(self, response) -> bool:
        final_url = str(getattr(response, "url", "") or "").lower()
        preview = (getattr(response, "text", "") or "")[:5000].lower()
        return (
            "companylogin" in final_url
            or "user/companylogin" in preview
            or "dian | acceder" in preview
            or "companyauthentication" in preview
        )

    def _validar_sesion_recibidos(self):
        try:
            check = self.session.get(
                "https://catalogo-vpfe.dian.gov.co/Document/Received",
                timeout=90,
                allow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            autenticado = check.status_code == 200 and not self._looks_like_login_response(check)
            return check, autenticado
        except Exception as exc:
            return {"status_code": None, "error": str(exc)}, False

    def submit_otp(self, access_url: str) -> dict:
        """
        Visita la URL de acceso (uso único) emitida por la DIAN. Esa visita
        autentica la sesión actual del cliente. La URL contiene un parámetro
        `token=<uuid>` que es la credencial real.
        """
        activation = self._submit_otp_con_playwright(access_url)
        check, autenticado = self._validar_sesion_recibidos()
        if not autenticado and activation.get("ok") and activation.get("token_en_dom"):
            autenticado = True
        ok = bool(activation.get("ok")) and autenticado
        self._autenticado = autenticado
        return {
            "endpoint": access_url,
            "status_activacion": activation.get("status_activacion"),
            "status_validacion": getattr(check, "status_code", None)
            if not isinstance(check, dict) else check.get("status_code"),
            "ok": ok and autenticado,
            "playwright": activation,
        }

        # Validación rápida: tras la activación, la página /Document/Received
        # debe responder 200 sin redirigir a CompanyLogin.

    # ── Paso 6: listar documentos del rango dado ────────────────────────────
    def _submit_otp_con_playwright(self, access_url: str) -> dict:
        """
        Fallback para cuando Azure WAF bloquea el GET HTTP directo a AuthToken.
        Abre la URL de uso unico en Chromium y copia las cookies resultantes a
        la sesion HTTP principal.
        """
        from playwright.sync_api import sync_playwright

        received_url = "https://catalogo-vpfe.dian.gov.co/Document/Received"
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=not self.headful,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                ],
            )
            ctx = browser.new_context(
                user_agent=("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/131.0.0.0 Safari/537.36"),
                viewport={"width": 1280, "height": 800},
                locale="es-CO",
                timezone_id="America/Bogota",
            )
            ctx.add_init_script("""
                Object.defineProperty(navigator,'webdriver',{get:()=>undefined});
                Object.defineProperty(navigator,'languages',{get:()=>['es-CO','es','en']});
                Object.defineProperty(navigator,'plugins',{get:()=>[1,2,3,4,5]});
                window.chrome = { runtime: {} };
            """)
            page = ctx.new_page()
            activation = validation = None
            activation_error = validation_error = None
            afv_token = None
            try:
                activation = page.goto(access_url, wait_until="domcontentloaded", timeout=45000)
            except Exception as exc:
                activation_error = str(exc)
            page.wait_for_timeout(4000)
            self._capture_page(page, "04_radian_auth_token_activation.png")
            try:
                validation = page.goto(received_url, wait_until="commit", timeout=45000)
            except Exception as exc:
                validation_error = str(exc)
                try:
                    page.wait_for_load_state("domcontentloaded", timeout=10000)
                except Exception:
                    pass
            page.wait_for_timeout(2000)
            self._capture_page(page, "05_radian_received_validated.png")
            current_url = page.url
            content = page.content()
            soup = BeautifulSoup(content, "html.parser")
            token_input = soup.find("input", {"name": "__RequestVerificationToken"})
            afv_token = token_input.get("value") if token_input else None
            cookies = ctx.cookies()
            browser.close()

        self.session.cookies.clear()
        for c in cookies:
            self.session.cookies.set(
                c["name"],
                c["value"],
                domain=c.get("domain", "catalogo-vpfe.dian.gov.co"),
                path=c.get("path", "/"),
            )

        status_activacion = activation.status if activation else None
        status_validacion = validation.status if validation else None
        if afv_token:
            self._last_afv_token = afv_token
        return {
            "status_activacion": status_activacion,
            "status_validacion": status_validacion,
            "current_url": current_url,
            "activation_error": activation_error,
            "validation_error": validation_error,
            "token_en_dom": bool(afv_token),
            "ok": status_validacion == 200 and "CompanyLogin" not in current_url,
        }

    def _afv_token(self) -> str:
        """Saca el __RequestVerificationToken del DOM de /Document/Received.

        Siempre hace un GET fresco — no usar el token cacheado de Playwright porque
        ese token pertenece a la sesión del navegador, no a self.session (curl_cffi).
        Usarlo en el POST causaría que el servidor devuelva la pantalla de login.
        """
        r = self.session.get("https://catalogo-vpfe.dian.gov.co/Document/Received",
                             timeout=90, allow_redirects=True,
                             headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        if self._looks_like_login_response(r):
            raise DianAuthError(
                "RADIAN no tiene una sesion autenticada activa; /Document/Received "
                "devolvio la pantalla de acceso."
            )
        soup = BeautifulSoup(r.text, "html.parser")
        inp = soup.find("input", {"name": "__RequestVerificationToken"})
        if not inp:
            # algunas vistas lo dejan en un meta o en JS
            import re as _re
            m = _re.search(r"__RequestVerificationToken[\"']?\s*[:=]\s*[\"']([^\"']+)", r.text)
            if m:
                return m.group(1)
            raise DianAuthError("No se encontró __RequestVerificationToken en /Document/Received")
        return inp.get("value") or ""

    def listar_documentos(
        self,
        fecha_desde: Optional[dt.date] = None,
        fecha_hasta: Optional[dt.date] = None,
        length: int = 100,
        document_type: str = "01",
        filter_type: str = "3",
    ) -> dict:
        if fecha_desde is None or fecha_hasta is None:
            hoy = dt.date.today()
            fecha_desde = fecha_desde or hoy.replace(day=1)
            ultimo = calendar.monthrange(hoy.year, hoy.month)[1]
            fecha_hasta = fecha_hasta or hoy.replace(day=ultimo)

        afv = self._afv_token()
        payload = {
            "__RequestVerificationToken": afv,
            "draw": 1, "start": 0, "length": length,
            "DocumentKey": "", "SerieAndNumber": "",
            "SenderCode": "", "ReceiverCode": "",
            "StartDate": fecha_desde.strftime("%Y-%m-%d"),
            "EndDate": fecha_hasta.strftime("%Y-%m-%d"),
            "DocumentTypeId": document_type,
            "Status": "0",
            "IsNextPage": "false",
            "FilterType": filter_type,
            "blockIndex": 0,
            "RadianStatus": "0",
        }
        r = self.session.post(
            "https://catalogo-vpfe.dian.gov.co/Document/GetDocumentsPageToken",
            data=payload, timeout=60,
            headers={
                "X-Requested-With": "XMLHttpRequest",
                "RequestVerificationToken": afv,
                "Referer": "https://catalogo-vpfe.dian.gov.co/Document/Received",
                "User-Agent": "Mozilla/5.0",
                "Origin": "https://catalogo-vpfe.dian.gov.co",
            },
        )
        if r.status_code >= 400:
            preview = r.text[:300].replace("\n", " ").replace("\r", " ")
            raise DianAuthError(
                "RADIAN fallo al listar documentos. "
                f"status={r.status_code} content_type={r.headers.get('Content-Type', '')} "
                f"preview={preview!r}"
            )
        if self._looks_like_login_response(r):
            preview = r.text[:300].replace("\n", " ").replace("\r", " ")
            raise DianAuthError(
                "RADIAN devolvio la pantalla de acceso al listar documentos. "
                f"status={r.status_code} preview={preview!r}"
            )
        content_type = r.headers.get("Content-Type", "")
        try:
            body = json.loads(r.text)
        except json.JSONDecodeError as exc:
            preview = r.text[:300].replace("\n", " ").replace("\r", " ")
            raise DianAuthError(
                "RADIAN no devolvio JSON al listar documentos. "
                f"status={r.status_code} content_type={content_type} "
                f"preview={preview!r}"
            ) from exc
        return {
            "rango": [fecha_desde.isoformat(), fecha_hasta.isoformat()],
            "total": body.get("recordsTotal", len(body.get("data", []))),
            "data": body.get("data", []),
        }

    # ── descarga ZIP por trackId ────────────────────────────────────────────
    def _download_id_candidates(self, doc: dict) -> list[tuple[str, str]]:
        keys = (
            "trackId", "TrackId", "track_id",
            "DocumentKey", "Id", "Identifier", "TokenConsulta",
        )
        candidates: list[tuple[str, str]] = []
        seen: set[str] = set()
        for key in keys:
            value = doc.get(key)
            if value is None:
                continue
            value = str(value).strip()
            if not value or value in seen:
                continue
            seen.add(value)
            candidates.append((key, value))
        return candidates

    def descargar_zip_documento(self, doc: dict, dest_dir: Path) -> tuple[Path, str, str]:
        errors = []
        captcha = resolver_turnstile(
            url_obj="https://catalogo-vpfe.dian.gov.co/Document/Received"
        )
        for source_key, value in self._download_id_candidates(doc):
            try:
                return self.descargar_zip(value, dest_dir, captcha=captcha), source_key, value
            except Exception as exc:
                errors.append(f"{source_key}: {exc}")
        raise DianAuthError(
            "No fue posible descargar ZIP con los identificadores disponibles. "
            + " | ".join(errors)
        )

    def descargar_zip(self, track_id: str, dest_dir: Path, captcha: Optional[str] = None) -> Path:
        url = f"https://catalogo-vpfe.dian.gov.co/Document/DownloadZipFiles?trackId={track_id}"
        if captcha:
            url = f"{url}&captcha={quote(captcha)}"
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/zip,application/octet-stream,*/*",
            "Referer": "https://catalogo-vpfe.dian.gov.co/",
            "Accept-Language": "es-ES,es;q=0.9",
        }
        r = self.session.get(url, headers=headers, timeout=60)
        content_type = r.headers.get("Content-Type", "")
        looks_zip = r.content[:2] == b"PK"
        if r.status_code != 200 or ("application/zip" not in content_type and not looks_zip):
            raise DianAuthError(f"Descarga falló trackId={track_id} status={r.status_code}")
        dest_dir.mkdir(parents=True, exist_ok=True)
        path = dest_dir / f"{track_id}.zip"
        path.write_bytes(r.content)
        return path

    # ── flujo end‑to‑end ────────────────────────────────────────────────────
    def autenticar(self, timeout_otp_s: int = 240) -> dict:
        """
        Ejecuta el flujo completo: solicitar acceso → esperar correo → activar URL.
        """
        out: dict[str, Any] = {}
        out["solicitud"] = self.solicitar_otp()
        out["buzon"] = self.esperar_otp_en_buzon(timeout_s=timeout_otp_s)
        out["submit"] = self.submit_otp(out["buzon"]["access_url"])
        out["autenticado"] = self._autenticado
        if not self._autenticado:
            raise DianAuthError(
                "RADIAN no quedo autenticado despues de activar la URL de acceso."
            )
        return out
