import os
from migracion_masiva_archivo.models import DocumentoDigitalizado, IntentoCargaSAIA
from migracion_masiva_archivo.services.file_name_service import (
    extraer_metadata_nombre_archivo,
    get_document_identity_from_filename,
)
from migracion_masiva_archivo.services.saia.exceptions import SAIANormalizationError
from migracion_masiva_archivo.services.saia.normalization import normalize_saia_subject

_MESES_IDENTIDAD = frozenset({
    'ENERO', 'FEBRERO', 'MARZO', 'ABRIL', 'MAYO', 'JUNIO',
    'JULIO', 'AGOSTO', 'SEPTIEMBRE', 'OCTUBRE', 'NOVIEMBRE', 'DICIEMBRE',
})


def _is_month_based_identity(identity):
    return bool(identity) and any(p in _MESES_IDENTIDAD for p in str(identity).upper().split('-'))


def _parent_folder(ruta):
    if not ruta:
        return ''
    try:
        return os.path.basename(os.path.dirname(str(ruta))).upper().strip()
    except Exception:
        return ''


def find_historical_saia_evidence(documento, asunto_saia=''):
    """
    Busca evidencia historica de documentos ya inventariados y de cargas SAIA
    exitosas. Retorna una estructura usable por Fase 1, reportes y validacion SAIA.
    """
    evidence = _empty_evidence(documento)
    candidates = (
        DocumentoDigitalizado.objects
        .exclude(lote=documento.lote)
        .select_related('lote')
        .order_by('-creado')
    )

    matches = _find_document_matches(documento, candidates)
    normalized_subject = _resolve_subject(documento, asunto_saia)
    subject_attempt = _find_successful_attempt_by_subject(normalized_subject, documento)
    if subject_attempt:
        matches.append(('ASUNTO_SAIA', subject_attempt.documento))

    if not matches:
        return None

    match_by_doc = {}
    for match_type, historic_doc in matches:
        match_by_doc.setdefault(historic_doc.id, {'documento': historic_doc, 'tipos': set()})
        match_by_doc[historic_doc.id]['tipos'].add(match_type)

    successful = []
    for item in match_by_doc.values():
        historic_doc = item['documento']
        intento = _latest_successful_attempt(historic_doc)
        if intento:
            successful.append((historic_doc, intento, item['tipos']))

    if successful:
        historic_doc, intento, match_types = successful[0]
        evidence.update(_document_evidence(historic_doc, match_types))
        evidence.update(
            {
                'ya_cargado_saia': True,
                'carga_saia_historica': True,
                'intento_saia_exitoso_id': intento.id,
                'id_documento_saia_historico': intento.id_documento_saia or '',
                'usuario_saia_historico': intento.usuario_saia or '',
                'fecha_carga_saia_historica': intento.creado.isoformat() if intento.creado else '',
                'codigo_error_usuario': 'YA_CARGADO_SAIA_HISTORICO',
                'mensaje_bloqueo_saia_historico': _historical_saia_message(historic_doc, intento, match_types),
            }
        )
        return evidence

    historic_doc, match_types = _best_non_successful_match(match_by_doc)
    evidence.update(_document_evidence(historic_doc, match_types))
    evidence['mensaje_bloqueo_saia_historico'] = _historical_duplicate_message(historic_doc, match_types)
    return evidence


def _empty_evidence(documento):
    return {
        'duplicado_historico': True,
        'duplicado_historico_por': '',
        'documento_id': documento.id,
        'documento_historico_id': '',
        'lote_historico_id': '',
        'ya_cargado_saia': False,
        'carga_saia_historica': False,
        'intento_saia_exitoso_id': '',
        'id_documento_saia_historico': '',
        'usuario_saia_historico': '',
        'fecha_carga_saia_historica': '',
        'ruta_archivo': documento.ruta_archivo,
        'coincidencias_historicas': '',
        'mensaje_bloqueo_saia_historico': '',
    }


def _find_document_matches(documento, candidates):
    matches = []
    current_identity = get_document_identity_from_filename(documento.nombre_archivo)
    current_components = _pel_components(documento.nombre_archivo)

    if documento.hash_archivo:
        for historic_doc in candidates.filter(hash_archivo=documento.hash_archivo):
            matches.append(('HASH', historic_doc))

    if current_identity:
        current_folder = _parent_folder(documento.ruta_archivo)
        for historic_doc in candidates:
            if get_document_identity_from_filename(historic_doc.nombre_archivo) == current_identity:
                # Identidades basadas en nombre de mes (BANCOLOMBIA-ENERO, etc.) son compartidas
                # por Bancolombia, Colpatria, Corbanca, CCA y CCV. Sólo es un duplicado real
                # si el archivo está en la misma carpeta padre (mismo banco/ruta).
                if _is_month_based_identity(current_identity):
                    if current_folder and _parent_folder(historic_doc.ruta_archivo) != current_folder:
                        continue
                matches.append(('IDENTIDAD_DOCUMENTAL', historic_doc))

    if current_components:
        for historic_doc in candidates:
            if _pel_components(historic_doc.nombre_archivo) == current_components:
                matches.append(('COMPONENTES_PEL', historic_doc))

    if documento.ruta_archivo:
        for historic_doc in candidates.filter(ruta_archivo=documento.ruta_archivo):
            matches.append(('RUTA_ARCHIVO', historic_doc))

    return matches


def _pel_components(filename):
    metadata = extraer_metadata_nombre_archivo(filename)
    if not metadata.get('pel_base_nombre'):
        return None
    return (
        metadata.get('pel_base_nombre'),
        metadata.get('subparte_nombre'),
        metadata.get('tomo_nombre'),
        metadata.get('parte_nombre'),
    )


def _resolve_subject(documento, asunto_saia):
    if asunto_saia:
        return asunto_saia
    for value in (documento.nombre_archivo, get_document_identity_from_filename(documento.nombre_archivo)):
        try:
            return normalize_saia_subject(value)
        except SAIANormalizationError:
            continue
    return ''


def _find_successful_attempt_by_subject(asunto_saia, documento):
    if not asunto_saia:
        return None
    candidates = (
        IntentoCargaSAIA.objects
        .filter(exitoso=True, request_metadata__asunto_saia=asunto_saia)
        .exclude(documento=documento)
        .select_related('documento', 'documento__lote')
        .order_by('-creado')
    )
    # Cuando el asunto es un nombre de mes (ENERO, FEBRERO…), el mismo valor es
    # compartido por Bancolombia, Colpatria, Corbanca, CCA y CCV. Solo se considera
    # duplicado si el intento histórico corresponde a un archivo de la misma carpeta padre.
    asunto_upper = str(asunto_saia).upper().strip()
    if asunto_upper in _MESES_IDENTIDAD:
        current_folder = _parent_folder(documento.ruta_archivo)
        if current_folder:
            for attempt in candidates:
                attempt_folder = _parent_folder(getattr(attempt.documento, 'ruta_archivo', ''))
                if not attempt_folder or attempt_folder == current_folder:
                    return attempt
            return None
    return candidates.first()


def _latest_successful_attempt(documento):
    return (
        IntentoCargaSAIA.objects
        .filter(documento=documento, exitoso=True)
        .order_by('-creado')
        .first()
    )


def _document_evidence(historic_doc, match_types):
    return {
        'duplicado_historico_por': ','.join(sorted(match_types)),
        'documento_historico_id': historic_doc.id,
        'lote_historico_id': historic_doc.lote_id,
        'coincidencias_historicas': ','.join(sorted(match_types)),
    }


def _best_non_successful_match(match_by_doc):
    item = next(iter(match_by_doc.values()))
    return item['documento'], item['tipos']


def _historical_saia_message(historic_doc, intento, match_types):
    match_text = ', '.join(sorted(match_types))
    return (
        'Documento ya cargado exitosamente a SAIA en historico: '
        f'lote {historic_doc.lote_id}, documento {historic_doc.id}, '
        f'intento {intento.id}, coincidencia por {match_text}'
    )


def _historical_duplicate_message(historic_doc, match_types):
    match_text = ', '.join(sorted(match_types))
    return (
        'Documento encontrado en lote anterior sin evidencia de carga SAIA exitosa: '
        f'lote {historic_doc.lote_id}, documento {historic_doc.id}, coincidencia por {match_text}'
    )


