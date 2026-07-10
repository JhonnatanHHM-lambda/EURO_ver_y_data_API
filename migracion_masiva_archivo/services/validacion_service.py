import re


def validate_metadata(metadata):
    errors = []

    consecutivo = metadata.get('consecutivo') or ''
    datos = metadata.get('datos_pel') or {}
    identifier = (
        datos.get('tipo_identificador')
        or metadata.get('tipo_documento_nombre')
        or _identifier_from_values(metadata)
    )
    is_principal = metadata.get('tipo_documento') == 'FACTURA_PRINCIPAL_PEL'

    if identifier == 'PRO':
        identidad = datos.get('identidad_documental') or ''
        if not identidad and not re.match(r'^MAY-PRO-\d{8}$', consecutivo):
            errors.append('Consecutivo PRO invalido o ausente')
    elif is_principal and not re.match(r'^MAY-PEL-\d{8}$', consecutivo):
        errors.append('Consecutivo invalido o ausente')

    identidad = datos.get('identidad_documental') or ''
    if metadata.get('mismatch_consecutivo') and not identidad:
        errors.append('Consecutivo no coincide con nombre de archivo')

    confidence = metadata.get('confianza') or 0
    if confidence < 80:
        errors.append('Confianza menor al minimo requerido')

    return {
        'is_valid': not errors,
        'errors': errors,
    }


def _identifier_from_values(metadata):
    values = [
        metadata.get('consecutivo'),
        metadata.get('tipo_documento'),
        metadata.get('observaciones_extraccion'),
    ]
    text = ' '.join(str(value or '') for value in values).upper()
    if re.search(r'\b(?:MAY[-\s]?)?PRO[-\s]?0*\d{4,8}\b|\bDOCUMENTO_PRO\b', text):
        return 'PRO'
    if re.search(r'\b(?:MAY[-\s]?)?PEL[-\s]?0*\d{4,8}\b|\bPEL\b', text):
        return 'PEL'
    return 'PEL'


