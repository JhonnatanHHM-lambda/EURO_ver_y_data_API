import datetime as dt
import json
import re
import tempfile
import traceback
from pathlib import Path

from django.core.management.base import BaseCommand

from OptimizacionCorreos.utils.config import get_settings
from OptimizacionCorreos.utils.crypto_utils import decrypt_credential
from OptimizacionCorreos.utils.dian_client import DianClient
from OptimizacionCorreos.utils.xml_parser import parse_zip, parse_invoice_element, _extraer_invoice_de_attached
from OptimizacionCorreos.utils.zimbra_client import ZimbraHttpClient


class Command(BaseCommand):
    help = "Traza en consola el flujo RADIAN -> Graph -> Zimbra de OptimizacionCorreos"
    SENSITIVE_KEY_RE = re.compile(
        r"(token|secret|password|pass|credential|access_url|endpoint|request_token|client_secret|api_key)",
        re.IGNORECASE,
    )

    def add_arguments(self, parser):
        parser.add_argument("--fecha-desde", required=True, help="Fecha inicial YYYY-MM-DD")
        parser.add_argument("--fecha-hasta", required=True, help="Fecha final YYYY-MM-DD")
        parser.add_argument("--timeout-otp", type=int, default=240, help="Segundos esperando correo DIAN")
        parser.add_argument("--limite-documentos", type=int, default=3, help="Maximo ZIPs RADIAN a descargar")
        parser.add_argument("--limite-correos", type=int, default=5, help="Maximo correos Zimbra a detallar")
        parser.add_argument(
            "--guardar-evidencias",
            action="store_true",
            help="Guarda capturas PNG, trace.log y JSON/TXT redactados del flujo",
        )
        parser.add_argument(
            "--evidencias-dir",
            default="tmp_optimizacion_correos/radian_email_flow",
            help="Directorio base donde se creara la subcarpeta de evidencias",
        )
        parser.add_argument(
            "--headful",
            action="store_true",
            help="Abre Chromium visible durante los pasos Playwright de RADIAN",
        )

    def _setup_evidence_dir(self, options):
        self.evidence_dir = None
        if not options["guardar_evidencias"]:
            return
        stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        base = Path(options["evidencias_dir"])
        self.evidence_dir = base / f"run_{stamp}"
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        self.trace_path = self.evidence_dir / "trace.log"

    def _redact(self, value, key=""):
        if isinstance(value, dict):
            return {k: self._redact(v, k) for k, v in value.items()}
        if isinstance(value, list):
            return [self._redact(v, key) for v in value]
        if self.SENSITIVE_KEY_RE.search(str(key)):
            if value in (None, "", False):
                return value
            return "***REDACTED***"
        if isinstance(value, str):
            value = re.sub(
                r"https://catalogo-vpfe\.dian\.gov\.co/User/AuthToken\?[^\s\"'<>]+",
                "https://catalogo-vpfe.dian.gov.co/User/AuthToken?***REDACTED***",
                value,
            )
            value = re.sub(
                r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
                "***UUID-REDACTED***",
                value,
            )
        return value

    def _write_json(self, filename, payload):
        if not self.evidence_dir:
            return
        path = self.evidence_dir / filename
        path.write_text(
            json.dumps(self._redact(payload), indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )

    def _write_text(self, filename, text):
        if not self.evidence_dir:
            return
        (self.evidence_dir / filename).write_text(str(text), encoding="utf-8")

    def log(self, message, style=None):
        prefix = dt.datetime.now().strftime("%H:%M:%S")
        line = f"[{prefix}] {message}"
        if getattr(self, "evidence_dir", None):
            with self.trace_path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        if style:
            self.stdout.write(style(line))
        else:
            self.stdout.write(line)

    def ok(self, message):
        self.log(message, self.style.SUCCESS)

    def warn(self, message):
        self.log(message, self.style.WARNING)

    def handle(self, *args, **options):
        self._setup_evidence_dir(options)
        fecha_desde = dt.date.fromisoformat(options["fecha_desde"])
        fecha_hasta = dt.date.fromisoformat(options["fecha_hasta"])
        timeout_otp = options["timeout_otp"]
        limite_documentos = options["limite_documentos"]
        limite_correos = options["limite_correos"]
        headful = options["headful"]

        self.log("Inicio traza OptimizacionCorreos")
        self.log(f"Rango: {fecha_desde.isoformat()} -> {fecha_hasta.isoformat()}")
        self.log(f"Modo navegador: {'visible/headful' if headful else 'oculto/headless'}")
        if self.evidence_dir:
            self.ok(f"Evidencias: {self.evidence_dir.resolve()}")

        s = get_settings()
        self.log("Validando configuracion OC_*")
        checks = {
            "DIAN NIT": bool(s.dian_nit),
            "CapSolver API key": bool(s.capsolver_api_key),
            "Graph tenant": bool(s.graph_tenant_id),
            "Graph client": bool(s.graph_client_id),
            "Graph mailbox": bool(s.graph_mailbox_upn),
            "Graph secret/cert": bool(s.graph_client_secret or s.graph_cert_private_key_path),
        }
        self._write_json("00_config_check.json", checks)
        for label, value in checks.items():
            self.log(f"  {label}: {'OK' if value else 'FALTA'}")

        self.log("Descifrando credenciales locales")
        cc_rep = decrypt_credential("OC_DIAN_CC_REP_ENC")
        _ = decrypt_credential("OC_ZIMBRA_PASSWORD_ENC")
        self.ok("Credenciales cifradas: OK")

        cli = DianClient(cc_rep=cc_rep, evidence_dir=self.evidence_dir, headful=headful)

        self.log("RADIAN 1/4: warm-up Playwright + token antifalsificacion + Turnstile + solicitud de acceso")
        try:
            solicitud = cli.solicitar_otp()
        except Exception:
            self._write_text("99_error.txt", traceback.format_exc())
            raise
        self._write_json("02_radian_solicitud_otp.json", solicitud)
        self.ok(f"RADIAN solicitud enviada: HTTP {solicitud.get('status')}")

        self.log(f"Graph 2/4: esperando correo DIAN en buzon ({timeout_otp}s max)")
        try:
            buzon = cli.esperar_otp_en_buzon(timeout_s=timeout_otp)
        except Exception:
            self._write_text("99_error.txt", traceback.format_exc())
            raise
        self._write_json("03_graph_correo_dian.json", buzon)
        self.ok(
            "Graph encontro correo DIAN: "
            f"recibido={buzon.get('received_at')} token={'SI' if buzon.get('token') else 'NO'}"
        )

        self.log("RADIAN 3/4: activando URL de acceso de un solo uso")
        try:
            submit = cli.submit_otp(buzon["access_url"])
        except Exception:
            self._write_text("99_error.txt", traceback.format_exc())
            raise
        self._write_json("04_radian_activacion_sesion.json", submit)
        self.ok(
            "RADIAN sesion: "
            f"activacion={submit.get('status_activacion')} "
            f"validacion={submit.get('status_validacion')} "
            f"ok={submit.get('ok')}"
        )
        if not submit.get("ok"):
            self.warn("La sesion RADIAN no quedo autenticada; se detiene antes de listar documentos")
            return

        self.log("RADIAN 4/4: listando documentos del rango")
        resultado = cli.listar_documentos(
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
            length=max(limite_documentos, 1),
        )
        documentos = resultado.get("data", [])
        self._write_json("06_radian_documentos_resumen.json", {
            "rango": resultado.get("rango"),
            "total": resultado.get("total"),
            "recibidos": len(documentos),
            "primer_documento_claves": sorted(documentos[0].keys()) if documentos else [],
            "primer_documento": documentos[0] if documentos else None,
        })
        self.ok(f"RADIAN documentos: total={resultado.get('total')} recibidos={len(documentos)}")

        self.log(f"RADIAN: descargando y parseando hasta {limite_documentos} ZIP(s)")
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            for idx, doc in enumerate(documentos[:limite_documentos], start=1):
                candidates = cli._download_id_candidates(doc)
                if not candidates:
                    self.warn(
                        f"  Doc {idx}: sin identificador descargable, omitido. "
                        f"Claves disponibles: {', '.join(sorted(doc.keys()))}"
                    )
                    continue
                self.log(
                    f"  Doc {idx}: probando descarga con "
                    f"{', '.join(key for key, _ in candidates)}"
                )
                try:
                    zip_path, source_key, used_id = cli.descargar_zip_documento(doc, tmp_path)
                except Exception as exc:
                    self.warn(f"  Doc {idx}: no se pudo descargar ZIP: {exc}")
                    continue
                factura = parse_zip(zip_path)
                self._write_json(f"07_radian_zip_{idx}_factura.json", factura.__dict__)
                self.ok(
                    "  Doc "
                    f"{idx}: id_fuente={source_key} id=***{used_id[-6:]} "
                    f"numero={factura.numero or '-'} "
                    f"cufe={'SI' if factura.cufe else 'NO'} "
                    f"nit={factura.emisor_nit or '-'} "
                    f"total={factura.total if factura.total is not None else '-'}"
                )

        self.log("Zimbra: consultando buzon de facturas electronicas")
        zimbra = ZimbraHttpClient()
        self._write_json("08_zimbra_request.json", {
            "api_url": zimbra.api_url,
            "email_configurado": bool(zimbra.email),
            "fecha_desde": fecha_desde.isoformat(),
            "fecha_hasta": fecha_hasta.isoformat(),
        })
        try:
            correos = zimbra.obtener_correos(
                fecha_desde=fecha_desde.isoformat(),
                fecha_hasta=fecha_hasta.isoformat(),
            )
        except Exception:
            self._write_text("99_error.txt", traceback.format_exc())
            raise
        self._write_json("09_zimbra_response_resumen.json", {
            "total": len(correos),
            "primer_correo_claves": sorted(correos[0].keys()) if correos else [],
        })
        self.ok(f"Zimbra correos recibidos: {len(correos)}")

        self.log(f"Zimbra: parseando adjuntos de hasta {limite_correos} correo(s)")
        for idx, correo in enumerate(correos[:limite_correos], start=1):
            asunto = correo.get("subject") or correo.get("asunto") or ""
            remitente = correo.get("from") or correo.get("remitente") or correo.get("sender") or ""
            self.log(f"  Correo {idx}: asunto={asunto[:80]!r} remitente={str(remitente)[:80]!r}")
            xml_bytes = zimbra.descargar_adjunto_xml(correo)
            if not xml_bytes:
                self.warn(f"  Correo {idx}: sin XML/ZIP procesable")
                continue
            invoice = _extraer_invoice_de_attached(xml_bytes)
            if invoice is None:
                self.warn(f"  Correo {idx}: XML sin Invoice UBL detectable")
                continue
            factura = parse_invoice_element(invoice)
            self._write_json(f"10_zimbra_correo_{idx}_factura.json", factura.__dict__)
            self.ok(
                "  Correo "
                f"{idx}: numero={factura.numero or '-'} "
                f"cufe={'SI' if factura.cufe else 'NO'} "
                f"nit={factura.emisor_nit or '-'} "
                f"total={factura.total if factura.total is not None else '-'}"
            )

        self.ok("Traza finalizada")
