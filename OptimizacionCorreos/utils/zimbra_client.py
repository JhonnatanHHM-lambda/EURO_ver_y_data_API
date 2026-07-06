"""
Cliente HTTP para la API Euro Zimbra (corre en localhost:8765).

Lee correos del buzón de facturas electrónicas y extrae el XML de adjuntos
ZIP o XML para la conciliación RADIAN.
"""
from __future__ import annotations

import base64
import datetime as dt
import email
import io
import imaplib
import os
import zipfile
from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime
from typing import Optional

import requests

from .crypto_utils import decrypt_credential


class ZimbraHttpClient:
    def __init__(self):
        self.api_url = os.environ.get("OC_ZIMBRA_API_URL", "http://localhost:8765").rstrip("/")
        self.host = os.environ.get("OC_ZIMBRA_HOST", "")
        self.imap_port = int(os.environ.get("OC_ZIMBRA_IMAP_PORT", "993"))
        self.email = os.environ.get("OC_ZIMBRA_EMAIL", "")
        self.password = decrypt_credential("OC_ZIMBRA_PASSWORD_ENC")

    def obtener_correos(self, fecha_desde: str, fecha_hasta: str) -> list[dict]:
        """POST /api/emails — retorna lista de mensajes con attachments."""
        try:
            resp = requests.post(
                f"{self.api_url}/api/emails",
                json={
                    "email": self.email,
                    "password": self.password,
                    "since_date": fecha_desde,
                    "until_date": fecha_hasta,
                    "include_subfolders": True,
                    "max_emails": 500,
                    "mark_as_read": False,
                },
                timeout=120,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("messages", [])
        except requests.RequestException:
            return self._obtener_correos_imap(fecha_desde, fecha_hasta)

    def _decode_mime_header(self, value: str) -> str:
        if not value:
            return ""
        try:
            return str(make_header(decode_header(value)))
        except Exception:
            return value

    def _imap_date(self, value: str) -> str:
        parsed = dt.date.fromisoformat(value)
        return parsed.strftime("%d-%b-%Y")

    def _obtener_correos_imap(self, fecha_desde: str, fecha_hasta: str) -> list[dict]:
        if not self.host:
            raise RuntimeError("OC_ZIMBRA_HOST no esta configurado para fallback IMAP")

        since = self._imap_date(fecha_desde)
        before = (dt.date.fromisoformat(fecha_hasta) + dt.timedelta(days=1)).strftime("%d-%b-%Y")
        messages: list[dict] = []

        with imaplib.IMAP4_SSL(self.host, self.imap_port) as imap:
            imap.login(self.email, self.password)
            status, _ = imap.select("INBOX", readonly=True)
            if status != "OK":
                raise RuntimeError("No se pudo abrir INBOX por IMAP")

            status, data = imap.search(None, "SINCE", since, "BEFORE", before)
            if status != "OK":
                raise RuntimeError("Busqueda IMAP fallida")

            ids = data[0].split()
            for msg_id in ids[-500:]:
                status, msg_data = imap.fetch(msg_id, "(RFC822)")
                if status != "OK" or not msg_data or not msg_data[0]:
                    continue
                raw_msg = msg_data[0][1]
                parsed = email.message_from_bytes(raw_msg)

                attachments = []
                for part in parsed.walk():
                    filename = part.get_filename()
                    disposition = (part.get("Content-Disposition") or "").lower()
                    if not filename and "attachment" not in disposition:
                        continue
                    payload = part.get_payload(decode=True)
                    if not payload:
                        continue
                    attachments.append({
                        "filename": self._decode_mime_header(filename or "adjunto"),
                        "content": base64.b64encode(payload).decode("ascii"),
                    })

                raw_date = parsed.get("Date", "")
                try:
                    date_value = parsedate_to_datetime(raw_date).isoformat()
                except Exception:
                    date_value = raw_date

                messages.append({
                    "subject": self._decode_mime_header(parsed.get("Subject", "")),
                    "from": self._decode_mime_header(parsed.get("From", "")),
                    "date": date_value,
                    "folder": "INBOX",
                    "attachments": attachments,
                })

        return messages

    def descargar_adjunto_xml(self, correo: dict) -> Optional[bytes]:
        """
        Si el correo tiene adjunto .zip o .xml, retorna el contenido del XML.
        Si es ZIP, abre en memoria y extrae el primer .xml encontrado.
        Retorna None si no hay adjunto procesable.
        """
        attachments = correo.get("attachments", []) or []
        for att in attachments:
            filename = (att.get("filename") or att.get("name") or "").lower()
            content_raw = att.get("content") or att.get("data") or att.get("body")
            if not content_raw:
                continue

            # Decodificar si viene como base64 string
            if isinstance(content_raw, str):
                try:
                    raw_bytes = base64.b64decode(content_raw)
                except Exception:
                    raw_bytes = content_raw.encode("latin-1")
            else:
                raw_bytes = bytes(content_raw)

            if filename.endswith(".xml"):
                return raw_bytes

            if filename.endswith(".zip"):
                try:
                    with zipfile.ZipFile(io.BytesIO(raw_bytes)) as zf:
                        xmls = [n for n in zf.namelist() if n.lower().endswith(".xml")]
                        if xmls:
                            # El XML principal suele ser el más pesado
                            xmls.sort(key=lambda n: -zf.getinfo(n).file_size)
                            return zf.read(xmls[0])
                except zipfile.BadZipFile:
                    continue

        return None
