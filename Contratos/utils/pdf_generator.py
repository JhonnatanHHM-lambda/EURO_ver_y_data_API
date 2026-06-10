"""Generador de PDFs de contratos. TODO: implementar con ReportLab."""


def generar_carta_no_prorroga(contrato) -> str:
    return f'contratos/{contrato.documento_id}/no_prorroga_{contrato.token_firma}.pdf'


def generar_carta_prorroga(contrato) -> str:
    return f'contratos/{contrato.documento_id}/prorroga_{contrato.token_firma}.pdf'


def generar_carta_terminacion(contrato) -> str:
    return f'contratos/{contrato.documento_id}/terminacion_{contrato.token_firma}.pdf'


def generar_pdf_firmado(contrato, firma_data: str) -> str:
    return f'contratos/{contrato.documento_id}/firmado_{contrato.token_firma}.pdf'
