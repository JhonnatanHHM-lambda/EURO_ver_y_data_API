import re

from migracion_masiva_archivo.services.saia.exceptions import SAIANormalizationError


def normalize_saia_subject(value):
    if not value:
        raise SAIANormalizationError('El documento no tiene consecutivo para SAIA.')

    text = str(value).upper().strip()
    text = re.sub(r'\s+', ' ', text)
    text = text.replace('_', '-')

    pro_structured_tomo_match = re.search(
        r'PRO[- ]?0*(\d{4,8})[- ]*TOMO[- ]*0*(\d{1,2})[- ]*PARTE[- ]*0*(\d{1,2})',
        text,
    )
    if pro_structured_tomo_match:
        number, tomo, suffix = pro_structured_tomo_match.groups()
        return f'PRO {int(number)} TOMO {int(tomo)}-{int(suffix)}'

    pro_tomo_match = re.search(
        r'(?:MAY[- ]?)?PRO[- ]?0*(\d{4,8})[- ]*TOMO[- ]*0*(\d{1,2})\s*[- ]\s*0*(\d{1,2})',
        text,
    )
    if pro_tomo_match:
        number, tomo, suffix = pro_tomo_match.groups()
        return f'PRO {int(number)} TOMO {int(tomo)}-{int(suffix)}'

    pro_suffix_match = re.search(r'(?:MAY[- ]?)?PRO[- ]?0*(\d{4,8})\s*[- ]\s*0*(\d{1,2})\b', text)
    if pro_suffix_match:
        number, suffix = pro_suffix_match.groups()
        return f'PRO {int(number)} -{int(suffix)}'

    pro_simple_match = re.search(r'(?:MAY[- ]?)?PRO[- ]?0*(\d{4,8})\b', text)
    if pro_simple_match:
        return f'PRO {int(pro_simple_match.group(1))}'

    pro_compacto_match = re.search(r'MAYPRO0*(\d{4,8})\b', text)
    if pro_compacto_match:
        return f'PRO {int(pro_compacto_match.group(1))}'

    rcg_structured_tomo_match = re.search(
        r'RCG[- ]?0*(\d{4,8})[- ]*TOMO[- ]*0*(\d{1,2})[- ]*PARTE[- ]*0*(\d{1,2})',
        text,
    )
    if rcg_structured_tomo_match:
        number, tomo, suffix = rcg_structured_tomo_match.groups()
        return f'RCG {int(number)} TOMO {int(tomo)}-{int(suffix)}'

    rcg_tomo_match = re.search(
        r'(?:MAY[- ]?)?RCG[- ]?0*(\d{4,8})[- ]*TOMO[- ]*0*(\d{1,2})\s*[- ]\s*0*(\d{1,2})',
        text,
    )
    if rcg_tomo_match:
        number, tomo, suffix = rcg_tomo_match.groups()
        return f'RCG {int(number)} TOMO {int(tomo)}-{int(suffix)}'

    rcg_suffix_match = re.search(r'(?:MAY[- ]?)?RCG[- ]?0*(\d{4,8})\s*[- ]\s*0*(\d{1,2})\b', text)
    if rcg_suffix_match:
        number, suffix = rcg_suffix_match.groups()
        return f'RCG {int(number)} -{int(suffix)}'

    rcg_simple_match = re.search(r'(?:MAY[- ]?)?RCG[- ]?0*(\d{4,8})\b', text)
    if rcg_simple_match:
        return f'RCG {int(rcg_simple_match.group(1))}'

    rcg_compacto_match = re.search(r'MAYRCG0*(\d{4,8})\b', text)
    if rcg_compacto_match:
        return f'RCG {int(rcg_compacto_match.group(1))}'

    rci_structured_tomo_match = re.search(
        r'RCI[- ]?0*(\d{4,8})[- ]*TOMO[- ]*0*(\d{1,2})[- ]*PARTE[- ]*0*(\d{1,2})',
        text,
    )
    if rci_structured_tomo_match:
        number, tomo, suffix = rci_structured_tomo_match.groups()
        return f'RCI {int(number)} TOMO {int(tomo)}-{int(suffix)}'

    rci_tomo_match = re.search(
        r'(?:MAY[- ]?)?RCI[- ]?0*(\d{4,8})[- ]*TOMO[- ]*0*(\d{1,2})\s*[- ]\s*0*(\d{1,2})',
        text,
    )
    if rci_tomo_match:
        number, tomo, suffix = rci_tomo_match.groups()
        return f'RCI {int(number)} TOMO {int(tomo)}-{int(suffix)}'

    rci_suffix_match = re.search(r'(?:MAY[- ]?)?RCI[- ]?0*(\d{4,8})\s*[- ]\s*0*(\d{1,2})\b', text)
    if rci_suffix_match:
        number, suffix = rci_suffix_match.groups()
        return f'RCI {int(number)} -{int(suffix)}'

    rci_simple_match = re.search(r'(?:MAY[- ]?)?RCI[- ]?0*(\d{4,8})\b', text)
    if rci_simple_match:
        return f'RCI {int(rci_simple_match.group(1))}'

    rci_compacto_match = re.search(r'MAYRCI0*(\d{4,8})\b', text)
    if rci_compacto_match:
        return f'RCI {int(rci_compacto_match.group(1))}'

    rcp_structured_tomo_match = re.search(
        r'RCP[- ]?0*(\d{4,8})[- ]*TOMO[- ]*0*(\d{1,2})[- ]*PARTE[- ]*0*(\d{1,2})',
        text,
    )
    if rcp_structured_tomo_match:
        number, tomo, suffix = rcp_structured_tomo_match.groups()
        return f'RCP {int(number)} TOMO {int(tomo)}-{int(suffix)}'

    rcp_tomo_match = re.search(
        r'(?:MAY[- ]?)?RCP[- ]?0*(\d{4,8})[- ]*TOMO[- ]*0*(\d{1,2})\s*[- ]\s*0*(\d{1,2})',
        text,
    )
    if rcp_tomo_match:
        number, tomo, suffix = rcp_tomo_match.groups()
        return f'RCP {int(number)} TOMO {int(tomo)}-{int(suffix)}'

    rcp_suffix_match = re.search(r'(?:MAY[- ]?)?RCP[- ]?0*(\d{4,8})\s*[- ]\s*0*(\d{1,2})\b', text)
    if rcp_suffix_match:
        number, suffix = rcp_suffix_match.groups()
        return f'RCP {int(number)} -{int(suffix)}'

    rcp_simple_match = re.search(r'(?:MAY[- ]?)?RCP[- ]?0*(\d{4,8})\b', text)
    if rcp_simple_match:
        return f'RCP {int(rcp_simple_match.group(1))}'

    rcp_compacto_match = re.search(r'MAYRCP0*(\d{4,8})\b', text)
    if rcp_compacto_match:
        return f'RCP {int(rcp_compacto_match.group(1))}'

    structured_tomo_match = re.search(
        r'PEL[- ]?0*(\d{4,8})[- ]*TOMO[- ]*0*(\d{1,2})[- ]*PARTE[- ]*0*(\d{1,2})',
        text,
    )
    if structured_tomo_match:
        number, tomo, suffix = structured_tomo_match.groups()
        return f'PEL {int(number)} TOMO {int(tomo)}-{int(suffix)}'

    structured_subpart_match = re.search(
        r'PEL[- ]?0*(\d{4,8})[- ]*SUBPARTE[- ]*0*(\d{1,2})',
        text,
    )
    if structured_subpart_match:
        number, suffix = structured_subpart_match.groups()
        return f'PEL {int(number)} -{int(suffix)}'

    tomo_match = re.search(
        r'(?:MAY[- ]?)?PEL[- ]?0*(\d{4,8})[- ]*TOMO[- ]*0*(\d{1,2})\s*[- ]\s*0*(\d{1,2})',
        text,
    )
    if tomo_match:
        number, tomo, suffix = tomo_match.groups()
        return f'PEL {int(number)} TOMO {int(tomo)}-{int(suffix)}'

    suffix_match = re.search(r'(?:MAY[- ]?)?PEL[- ]?0*(\d{4,8})\s*[- ]\s*0*(\d{1,2})\b', text)
    if suffix_match:
        number, suffix = suffix_match.groups()
        return f'PEL {int(number)} -{int(suffix)}'

    simple_match = re.search(r'(?:MAY[- ]?)?PEL[- ]?0*(\d{4,8})\b', text)
    if simple_match:
        return f'PEL {int(simple_match.group(1))}'

    compacto_match = re.search(r'MAYPEL0*(\d{4,8})\b', text)
    if compacto_match:
        return f'PEL {int(compacto_match.group(1))}'

    raise SAIANormalizationError(f'No se pudo normalizar el consecutivo para SAIA: {value}')


