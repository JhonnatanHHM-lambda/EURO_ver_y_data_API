"""
Parser XML UBL 2.1 de las facturas electrónicas DIAN.

Extrae los campos críticos del XML que viaja dentro del ZIP descargado de
RADIAN. El más solicitado: el **correo donde el proveedor envió la factura**
(adquirente), que NO viene en el listado JSON del portal.

Estructura típica:
  ZIP
   └─ <unId>.xml    (UBL Attached Document)
        └─ <cac:Attachment>/.../cac:ExternalReference/...   ← contiene el UBL
                                                              real codificado
        ó directamente <Invoice>...
"""
from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from xml.etree import ElementTree as ET

NS = {
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
    "ext": "urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2",
    "ds": "http://www.w3.org/2000/09/xmldsig#",
    "i": "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2",
}


# ─── Modelo de salida ────────────────────────────────────────────────────────
@dataclass
class FacturaXML:
    cufe: Optional[str] = None
    numero: Optional[str] = None
    fecha_emision: Optional[str] = None
    fecha_vencimiento: Optional[str] = None
    forma_pago: Optional[str] = None
    medio_pago: Optional[str] = None
    moneda: Optional[str] = None
    subtotal: Optional[float] = None
    iva: Optional[float] = None
    total: Optional[float] = None
    # emisor — datos generales
    emisor_nit: Optional[str] = None
    emisor_nombre: Optional[str] = None
    emisor_nombre_comercial: Optional[str] = None
    emisor_correo: Optional[str] = None
    emisor_telefono: Optional[str] = None
    emisor_direccion: Optional[str] = None
    emisor_municipio: Optional[str] = None
    # emisor — calidad tributaria
    emisor_tipo_persona: Optional[str] = None         # natural | juridica
    emisor_regimen: Optional[str] = None              # común / simple / no-IVA
    emisor_tipo_documento_id: Optional[str] = None    # NIT / CC / etc
    emisor_codigo_actividad: Optional[str] = None     # CIIU
    emisor_responsabilidades: list[dict] = field(default_factory=list)  # [{codigo,nombre}]
    # adquirente
    adquirente_nit: Optional[str] = None
    adquirente_nombre: Optional[str] = None
    adquirente_correo: Optional[str] = None
    adquirente_telefono: Optional[str] = None
    adquirente_direccion: Optional[str] = None
    adquirente_municipio: Optional[str] = None
    adquirente_tipo_persona: Optional[str] = None
    adquirente_regimen: Optional[str] = None
    adquirente_responsabilidades: list[dict] = field(default_factory=list)
    # items + impuestos
    items: list[dict] = field(default_factory=list)
    impuestos: list[dict] = field(default_factory=list)
    retenciones: list[dict] = field(default_factory=list)
    # raw
    notas: list[str] = field(default_factory=list)


def _t(el) -> Optional[str]:
    if el is None: return None
    s = (el.text or "").strip()
    return s or None


def _f(el) -> Optional[float]:
    s = _t(el)
    if not s: return None
    try: return float(s)
    except Exception: return None  # noqa: BLE001


def _find(node, path):
    return node.find(path, NS)


def _findall(node, path):
    return node.findall(path, NS)


# ─── Codigos de responsabilidad fiscal DIAN (Resolución 042/2020) ────────────
RESPONSABILIDADES_DIAN = {
    "O-13":"Gran contribuyente","O-15":"Autorretenedor",
    "O-23":"Agente de retención IVA","O-47":"Régimen Simple de Tributación",
    "R-99-PN":"No aplica - Otros","ZZ":"No aplica",
}

REGIMEN_DIAN = {
    "48":"Responsable del impuesto sobre las ventas - IVA",
    "49":"No responsable de IVA",
    "ZZ":"No aplica",
}


def _datos_party(party) -> dict:
    """Extrae todos los datos tributarios de un nodo cac:Party (emisor o adq)."""
    d: dict = {
        "nit": None, "nombre": None, "nombre_comercial": None,
        "tipo_documento_id": None, "tipo_persona": None,
        "regimen": None, "codigo_actividad": None,
        "correo": None, "telefono": None,
        "direccion": None, "municipio": None,
        "responsabilidades": [],
    }
    if party is None: return d
    # nombre + nombre comercial
    d["nombre"] = (_t(_find(party, "cac:PartyTaxScheme/cbc:RegistrationName"))
                   or _t(_find(party, "cac:PartyLegalEntity/cbc:RegistrationName"))
                   or _t(_find(party, "cac:PartyName/cbc:Name")))
    d["nombre_comercial"] = _t(_find(party, "cac:PartyName/cbc:Name"))
    # NIT
    pid = _find(party, "cac:PartyIdentification/cbc:ID")
    cid = _find(party, "cac:PartyTaxScheme/cbc:CompanyID")
    d["nit"] = _t(cid) or _t(pid)
    # tipo doc (schemeName del ID)
    if pid is not None:
        d["tipo_documento_id"] = (pid.attrib.get("schemeName")
                                  or pid.attrib.get("schemeID"))
    if cid is not None and not d["tipo_documento_id"]:
        d["tipo_documento_id"] = (cid.attrib.get("schemeName")
                                  or cid.attrib.get("schemeID"))
    # Contacto
    d["correo"] = _t(_find(party, "cac:Contact/cbc:ElectronicMail"))
    d["telefono"] = _t(_find(party, "cac:Contact/cbc:Telephone"))
    # Direccion (intentamos varias rutas)
    d["direccion"] = (_t(_find(party, "cac:PartyTaxScheme/cac:RegistrationAddress/cac:AddressLine/cbc:Line"))
                     or _t(_find(party, "cac:PhysicalLocation/cac:Address/cac:AddressLine/cbc:Line")))
    d["municipio"] = (_t(_find(party, "cac:PartyTaxScheme/cac:RegistrationAddress/cbc:CityName"))
                     or _t(_find(party, "cac:PhysicalLocation/cac:Address/cbc:CityName"))
                     or _t(_find(party, "cac:PartyTaxScheme/cac:RegistrationAddress/cbc:CountrySubentity")))
    # Tipo persona (1 = juridica, 2 = natural — atributo schemeID en CompanyID o nombre)
    # En facturas DIAN UBL aparece cbc:AdditionalAccountID con valor 1/2
    tp = _t(_find(party, "cbc:AdditionalAccountID"))
    if tp == "1": d["tipo_persona"] = "Jurídica"
    elif tp == "2": d["tipo_persona"] = "Natural"
    # Régimen DIAN — viene en cbc:TaxLevelCode (R-99-PN, O-15, etc.) o como lista
    # Las responsabilidades vienen como string separado por ; en TaxLevelCode
    tlc = _t(_find(party, "cac:PartyTaxScheme/cbc:TaxLevelCode"))
    if tlc:
        # listOnly attribute o separado por ;
        codes = re.split(r"[;,\s]+", tlc.strip())
        for c in codes:
            if c:
                d["responsabilidades"].append({"codigo": c,
                                                "nombre": RESPONSABILIDADES_DIAN.get(c, c)})
    # CIIU
    d["codigo_actividad"] = _t(_find(party, "cac:PartyTaxScheme/cbc:TaxLevelCode"))
    # Régimen del IVA (TaxScheme ID 01 = IVA)
    for ts in _findall(party, "cac:PartyTaxScheme/cac:TaxScheme"):
        nombre = _t(_find(ts, "cbc:Name"))
        codigo = _t(_find(ts, "cbc:ID"))
        if codigo in REGIMEN_DIAN and not d["regimen"]:
            d["regimen"] = REGIMEN_DIAN[codigo] + (f" ({nombre})" if nombre else "")
    return d


# ─── Extracción de un <Invoice> ──────────────────────────────────────────────
def parse_invoice_element(inv) -> FacturaXML:
    out = FacturaXML()
    out.cufe = _t(_find(inv, "cbc:UUID"))
    out.numero = _t(_find(inv, "cbc:ID"))
    out.fecha_emision = _t(_find(inv, "cbc:IssueDate"))
    out.fecha_vencimiento = _t(_find(inv, "cbc:DueDate"))
    out.moneda = _t(_find(inv, "cbc:DocumentCurrencyCode"))
    for n in _findall(inv, "cbc:Note"):
        nt = _t(n)
        if nt: out.notas.append(nt)

    # totales
    lmt = _find(inv, "cac:LegalMonetaryTotal")
    if lmt is not None:
        out.subtotal = _f(_find(lmt, "cbc:LineExtensionAmount"))
        out.total = (_f(_find(lmt, "cbc:PayableAmount"))
                      or _f(_find(lmt, "cbc:TaxInclusiveAmount")))
    # impuestos consolidados + por tipo
    for tt in _findall(inv, "cac:TaxTotal"):
        valor = _f(_find(tt, "cbc:TaxAmount"))
        for sub in _findall(tt, "cac:TaxSubtotal"):
            esquema = _t(_find(sub, "cac:TaxCategory/cac:TaxScheme/cbc:ID"))
            nombre = _t(_find(sub, "cac:TaxCategory/cac:TaxScheme/cbc:Name")) or esquema
            tarifa = _f(_find(sub, "cac:TaxCategory/cbc:Percent"))
            valor_sub = _f(_find(sub, "cbc:TaxAmount"))
            base = _f(_find(sub, "cbc:TaxableAmount"))
            obj = {"codigo": esquema, "nombre": nombre, "tarifa": tarifa,
                   "valor": valor_sub, "base": base}
            # retención si código en {ReteIVA, ReteFte, ReteICA, 05, 06, 07}
            if esquema in ("05","06","07") or (nombre and "Rete" in nombre):
                out.retenciones.append(obj)
            else:
                out.impuestos.append(obj)
        if not out.impuestos and not out.retenciones:
            # fallback total
            out.impuestos.append({"codigo":"01","nombre":"Impuestos","valor":valor})
    # IVA total (suma de impuestos no-retención con código 01)
    out.iva = sum((i["valor"] or 0) for i in out.impuestos if (i.get("codigo")=="01"))

    # forma de pago / medio
    pm = _find(inv, "cac:PaymentMeans")
    if pm is not None:
        codigo_pm = _t(_find(pm, "cbc:PaymentMeansCode"))
        id_pm = _t(_find(pm, "cbc:ID"))
        # PaymentMeans ID: 1 contado / 2 crédito
        out.forma_pago = ("Contado" if id_pm == "1" else
                          "Crédito" if id_pm == "2" else id_pm)
        out.medio_pago = codigo_pm

    # Emisor + adquirente
    e = _datos_party(_find(inv, "cac:AccountingSupplierParty/cac:Party"))
    out.emisor_nit = e["nit"]; out.emisor_nombre = e["nombre"]
    out.emisor_nombre_comercial = e["nombre_comercial"]
    out.emisor_correo = e["correo"]; out.emisor_telefono = e["telefono"]
    out.emisor_direccion = e["direccion"]; out.emisor_municipio = e["municipio"]
    out.emisor_tipo_persona = e["tipo_persona"]; out.emisor_regimen = e["regimen"]
    out.emisor_tipo_documento_id = e["tipo_documento_id"]
    out.emisor_codigo_actividad = e["codigo_actividad"]
    out.emisor_responsabilidades = e["responsabilidades"]

    a = _datos_party(_find(inv, "cac:AccountingCustomerParty/cac:Party"))
    out.adquirente_nit = a["nit"]; out.adquirente_nombre = a["nombre"]
    out.adquirente_correo = a["correo"]; out.adquirente_telefono = a["telefono"]
    out.adquirente_direccion = a["direccion"]; out.adquirente_municipio = a["municipio"]
    out.adquirente_tipo_persona = a["tipo_persona"]; out.adquirente_regimen = a["regimen"]
    out.adquirente_responsabilidades = a["responsabilidades"]

    # Items
    for ln in _findall(inv, "cac:InvoiceLine"):
        item = {
            "id": _t(_find(ln, "cbc:ID")),
            "descripcion": _t(_find(ln, "cac:Item/cbc:Description"))
                            or _t(_find(ln, "cac:Item/cbc:Name")),
            "cantidad": _f(_find(ln, "cbc:InvoicedQuantity")),
            "unidad": (_find(ln, "cbc:InvoicedQuantity").attrib.get("unitCode")
                       if _find(ln, "cbc:InvoicedQuantity") is not None else None),
            "precio_unit": _f(_find(ln, "cac:Price/cbc:PriceAmount")),
            "valor_linea": _f(_find(ln, "cbc:LineExtensionAmount")),
        }
        out.items.append(item)
    return out


# ─── Soporte de ApplicationResponse / AttachedDocument ───────────────────────
def _extraer_invoice_de_attached(xml_bytes: bytes) -> Optional[ET.Element]:
    """
    El ZIP de RADIAN suele traer un AttachedDocument que envuelve al Invoice
    real codificado en CDATA o como subnodo. Si no hay AttachedDocument,
    devolvemos la raíz si es <Invoice>.
    """
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return None
    tag = root.tag.split("}")[-1]
    if tag == "Invoice":
        return root
    # AttachedDocument → cac:Attachment/cac:ExternalReference/cbc:Description tiene
    # el XML embebido como CDATA o texto plano
    ext = root.find(".//cac:ExternalReference/cbc:Description", NS)
    if ext is not None and ext.text:
        # quita XML envoltura — busca <Invoice ...>...</Invoice>
        m = re.search(r"<(?:\w+:)?Invoice[\s\S]+?</(?:\w+:)?Invoice>", ext.text)
        inner = m.group(0) if m else ext.text
        try:
            return ET.fromstring(inner)
        except ET.ParseError:
            return None
    return None


def parse_zip(path: str | Path) -> FacturaXML:
    """Toma la ruta a un ZIP RADIAN y devuelve el FacturaXML extraído."""
    path = Path(path)
    out = FacturaXML()
    with zipfile.ZipFile(path) as zf:
        # primero XMLs grandes (el Invoice principal pesa más que recibos)
        xmls = sorted([n for n in zf.namelist() if n.lower().endswith(".xml")],
                      key=lambda n: -zf.getinfo(n).file_size)
        for name in xmls:
            data = zf.read(name)
            inv = _extraer_invoice_de_attached(data)
            if inv is not None:
                return parse_invoice_element(inv)
    return out


if __name__ == "__main__":
    import sys, json
    fx = parse_zip(sys.argv[1])
    d = fx.__dict__.copy()
    print(json.dumps(d, indent=2, ensure_ascii=False, default=str))
