import re
from collections import defaultdict

from django.db import transaction

from migracion_masiva_archivo.models import DocumentoDigitalizado, LogProcesoDocumental, RelacionDocumento
from migracion_masiva_archivo.services.error_message_service import build_phase3_error_message
from migracion_masiva_archivo.services.file_name_service import (
    extraer_metadata_nombre_archivo,
    get_documental_natural_sort_key,
    has_ok_marker,
    is_ambiguous_pel_filename,
)

MIN_RELATION_CONFIDENCE = 80
ALLOWED_RELATION_STATES = {'VALIDADO', 'METADATA_EXTRAIDA', 'OCR_PROCESADO', 'RELACIONADO'}


def group_documents_by_metadata(documents):
    groups = defaultdict(list)
    seen = set()
    for document in documents:
        if not _is_relation_candidate(document):
            continue
        for code in _relation_codes(document):
            key = code['group_key']
            seen_key = (key, document.id)
            if seen_key in seen:
                continue
            groups[key].append(document)
            seen.add(seen_key)

    return dict(groups)


@transaction.atomic
def relacionar_documentos_lote(lote, min_confidence=MIN_RELATION_CONFIDENCE, recrear=False):
    if recrear:
        RelacionDocumento.objects.filter(documento_principal__lote=lote).delete()

    documents = sorted(
        list(lote.documentos.select_related('metadata').all()),
        key=lambda document: document_natural_order_key(document),
    )
    groups = group_documents_by_metadata(documents)
    created_relations = {}
    relation_details = {}
    ambiguous_groups = _orphan_groups(documents)
    discarded_relations = []
    omitted_documents = _omitted_documents(documents)
    docs_to_relacionar = {}  # id → doc; deduplicado para bulk_update final

    for key, group_documents in groups.items():
        if len(group_documents) < 2:
            # Un PEL simple o un unico documento de una familia no requiere
            # relacion migracion_masiva_archivo. Fase 4 acepta VALIDADO como documento
            # individual, asi que no fabricamos un estado RELACIONADO.
            continue

        principal_result = _select_principal_document(group_documents, key)
        principal = principal_result.get('document')
        if not principal:
            ambiguous_groups.append(
                {
                    'grupo': key,
                    'motivo': principal_result.get('reason', 'Sin documento principal claro'),
                    'documentos': [document.id for document in group_documents],
                    'codigo_error': principal_result.get('codigo_error', 'PRINCIPAL_NO_ENCONTRADO'),
                }
            )
            continue

        for related in group_documents:
            if related.id == principal.id:
                continue

            relation_match = _build_relation_match(principal, related, key)
            confidence = relation_match.get('confianza')
            if not _has_real_confidence(confidence):
                discarded_relations.append({
                    'documento_principal': principal.id,
                    'documento_relacionado': related.id,
                    'criterio': key,
                    'confianza': confidence,
                    'motivo': relation_match.get(
                        'motivo',
                        'No se pudo calcular confianza de relacion documental',
                    ),
                    'codigo_error': relation_match.get('codigo_error', 'CONFIANZA_NO_CALCULADA'),
                })
                continue
            if float(confidence) < min_confidence:
                discarded_relations.append({
                    'documento_principal': principal.id,
                    'documento_relacionado': related.id,
                    'criterio': key,
                    'confianza': confidence,
                    'motivo': relation_match['motivo'],
                    'codigo_error': relation_match.get('codigo_error', 'CONFIANZA_RELACION_BAJA'),
                })
                continue

            criterio_relacion = relation_match['criterio_relacion']
            try:
                relation, _created = RelacionDocumento.objects.get_or_create(
                    documento_principal=principal,
                    documento_relacionado=related,
                    tipo_relacion=_infer_relation_type(related, key),
                    defaults={
                        'criterio_relacion': criterio_relacion,
                        'confianza': relation_match['confianza'],
                    },
                )
            except Exception as exc:
                discarded_relations.append(
                    _with_phase3_error(
                        {
                            'documento_principal': principal.id,
                            'documento_relacionado': related.id,
                            'criterio': key,
                            'confianza': relation_match['confianza'],
                            'motivo': 'Error al crear RelacionDocumento',
                            'exception': str(exc),
                            'codigo_error': 'ERROR_TECNICO_RELACION',
                        }
                    )
                )
                continue
            if not _created and _should_update_relation(relation, relation_match):
                relation.confianza = relation_match['confianza']
                relation.criterio_relacion = criterio_relacion
                relation.save(update_fields=['confianza', 'criterio_relacion'])
            created_relations[relation.id] = relation
            relation_details[relation.id] = {
                'documento_principal': principal.id,
                'documento_relacionado': related.id,
                'criterio_relacion': criterio_relacion,
                'confianza': relation_match['confianza'],
                'motivo': relation_match['motivo'],
            }

            for document in (principal, related):
                if document.estado_proceso in {'VALIDADO', 'METADATA_EXTRAIDA'}:
                    document.estado_proceso = 'RELACIONADO'
                    docs_to_relacionar[document.id] = document

    if docs_to_relacionar:
        DocumentoDigitalizado.objects.bulk_update(
            list(docs_to_relacionar.values()),
            ['estado_proceso'],
        )

    ambiguous_groups = [_with_phase3_error(group) for group in ambiguous_groups]
    discarded_relations = [_with_phase3_error(relation) for relation in discarded_relations]
    omitted_documents = [_with_phase3_error(document) for document in omitted_documents]
    order_warnings = [_with_phase3_error(warning) for warning in _group_order_warnings(groups)]

    LogProcesoDocumental.objects.create(
        lote=lote,
        evento='relacion_documental',
        mensaje='Relacion documental ejecutada',
        detalle={
            'relaciones_creadas': len(created_relations),
            'detalle_relaciones': list(relation_details.values()),
            'grupos_ambiguos': ambiguous_groups,
            'relaciones_descartadas': discarded_relations,
            'documentos_omitidos': omitted_documents,
            'advertencias_orden': order_warnings,
            'confianza_minima': min_confidence,
        },
    )

    return {
        'relaciones': list(created_relations.values()),
        'detalle_relaciones': list(relation_details.values()),
        'grupos_ambiguos': ambiguous_groups,
        'relaciones_descartadas': discarded_relations,
        'documentos_omitidos': omitted_documents,
        'advertencias_orden': order_warnings,
    }


def _select_principal_document(documents, group_key):
    candidates = []
    for document in documents:
        best_rank = _principal_rank(document, group_key)
        if best_rank <= 0:
            continue
        candidates.append((best_rank, _metadata_confidence(document), -document.id, document))

    if not candidates:
        return {
            'document': None,
            'reason': 'No existe documento principal claro para el grupo',
            'codigo_error': 'PRINCIPAL_NO_ENCONTRADO',
        }

    candidates.sort(reverse=True)
    best = candidates[0]
    tied = [
        candidate for candidate in candidates
        if candidate[0] == best[0] and candidate[1] == best[1]
    ]
    if len(tied) > 1:
        return {
            'document': None,
            'reason': 'Existen varios documentos principales posibles con la misma confianza',
            'codigo_error': 'PRINCIPALES_MULTIPLES',
        }
    return {
        'document': best[3],
        'reason': '',
    }


def _with_phase3_error(item):
    context = dict(item)
    error_message = build_phase3_error_message(context.get('motivo', ''), context)
    item['error_usuario_fase_3'] = error_message
    item['codigo_error_usuario'] = error_message.get('codigo_error_usuario', '')
    item['mensaje_usuario'] = error_message.get('mensaje_usuario', '')
    item['accion_recomendada'] = error_message.get('accion_recomendada', '')
    item['fase_error'] = error_message.get('fase_error', '')
    item['severidad_error'] = error_message.get('severidad_error', '')
    item['bloquea_relacion'] = error_message.get('bloquea_relacion', False)
    item['bloquea_saia'] = error_message.get('bloquea_saia', False)
    item['error_tecnico'] = error_message.get('error_tecnico', '')
    return item


def _is_relation_candidate(document):
    if document.estado_proceso not in ALLOWED_RELATION_STATES:
        return False
    metadata = getattr(document, 'metadata', None)
    if not metadata:
        return False
    if metadata.requiere_revision:
        return False
    if has_ok_marker(document.nombre_archivo):
        return False
    if is_ambiguous_pel_filename(document.nombre_archivo):
        return False
    return _has_relation_identity(document)


def _omitted_documents(documents):
    omitted = []
    for document in documents:
        metadata = getattr(document, 'metadata', None)
        reason = ''
        if has_ok_marker(document.nombre_archivo):
            reason = 'Archivo omitido porque el nombre contiene OK'
            code = 'DOCUMENTO_OK_OMITIDO'
        elif is_ambiguous_pel_filename(document.nombre_archivo):
            reason = 'Nombre PEL ambiguo o con sufijos no reconocidos'
            code = 'NOMBRE_PEL_AMBIGUO'
        else:
            code = ''
        if reason:
            omitted.append(
                {
                    'documento': document.id,
                    'nombre_archivo': document.nombre_archivo,
                    'motivo': reason,
                    'codigo_error': code,
                }
            )
    return omitted


def _group_order_warnings(groups):
    warnings = []
    for group_key, documents in groups.items():
        if not str(group_key).startswith('PEL-'):
            continue

        metadata_by_document = [
            (document, _document_pel_metadata(document))
            for document in documents
        ]
        suffixes = sorted(
            {
                int(metadata.get('subparte_nombre'))
                for _document, metadata in metadata_by_document
                if metadata.get('subparte_nombre')
            }
        )
        if suffixes:
            missing_suffixes = [number for number in range(1, max(suffixes) + 1) if number not in suffixes]
            if missing_suffixes:
                warnings.append(
                    {
                        'grupo': group_key,
                        'tipo': 'SUBPARTE_FALTANTE',
                        'faltantes': [f'{group_key}-{number}' for number in missing_suffixes],
                        'motivo': 'Faltan subpartes intermedias del grupo documental',
                        'codigo_error': 'SECUENCIA_INCOMPLETA_ADVERTENCIA',
                    }
                )

        tomo_parts = defaultdict(set)
        for _document, metadata in metadata_by_document:
            tomo = metadata.get('tomo_nombre')
            part = metadata.get('parte_nombre')
            if tomo and part:
                tomo_parts[int(tomo)].add(int(part))

        if tomo_parts and (1 not in tomo_parts or 1 not in tomo_parts[1]):
            warnings.append(
                {
                    'grupo': group_key,
                    'tipo': 'TOMO_PRINCIPAL_FALTANTE',
                    'faltantes': [f'{group_key}-TOMO-1-PARTE-1'],
                    'motivo': 'Existen tomos o partes, pero falta TOMO 1-1',
                    'codigo_error': 'TOMO_PRINCIPAL_FALTANTE',
                }
            )
        for tomo, parts in sorted(tomo_parts.items()):
            missing_parts = [number for number in range(1, max(parts) + 1) if number not in parts]
            if missing_parts:
                warnings.append(
                    {
                        'grupo': group_key,
                        'tipo': 'PARTE_TOMO_FALTANTE',
                        'faltantes': [f'{group_key}-TOMO-{tomo}-PARTE-{part}' for part in missing_parts],
                        'motivo': 'Faltan partes intermedias de un tomo',
                        'codigo_error': 'SECUENCIA_INCOMPLETA_ADVERTENCIA',
                    }
                )
    return warnings


def _orphan_groups(documents):
    by_base = defaultdict(list)
    for document in documents:
        if not _is_relation_candidate(document):
            continue
        metadata = _document_pel_metadata(document)
        base = metadata.get('pel_base_nombre')
        if base:
            by_base[str(int(base))].append((document, metadata))

    orphans = []
    for base, items in by_base.items():
        suffixes = {
            int(metadata.get('subparte_nombre'))
            for _document, metadata in items
            if metadata.get('subparte_nombre')
        }
        has_tomos = any(metadata.get('tomo_nombre') for _document, metadata in items)
        has_tomo_principal = any(
            metadata.get('tomo_nombre') == 1 and metadata.get('parte_nombre') == 1
            for _document, metadata in items
        )

        if suffixes and 1 not in suffixes:
            orphans.append(
                {
                    'grupo': f'PEL-{base}',
                    'motivo': 'Existe subparte documental, pero falta el documento principal -1',
                    'documentos': [document.id for document, _metadata in items],
                    'codigo_error': 'SUBPARTE_HUERFANA',
                }
            )
        if has_tomos and not has_tomo_principal:
            orphans.append(
                {
                    'grupo': f'PEL-{base}',
                    'motivo': 'Existen tomos o partes, pero falta TOMO 1-1',
                    'documentos': [document.id for document, _metadata in items],
                    'codigo_error': 'TOMO_PRINCIPAL_FALTANTE',
                }
            )
    return orphans


def _metadata_confidence(document):
    metadata = getattr(document, 'metadata', None)
    return float(metadata.confianza) if metadata else 0


def _metadata_type(document):
    metadata = getattr(document, 'metadata', None)
    return metadata.tipo_documento if metadata else ''


def _has_required_datos_pel(metadata):
    datos_pel = getattr(metadata, 'datos_pel', None) or {}
    return bool(datos_pel.get('identidad_documental') and datos_pel.get('pel_base_nombre'))


def _has_relation_identity(document):
    metadata = getattr(document, 'metadata', None)
    if metadata and _has_required_datos_pel(metadata):
        return True
    name_metadata = _document_pel_metadata(document)
    return bool(
        name_metadata.get('nombre_reconocido')
        and name_metadata.get('identidad_documental')
        and name_metadata.get('pel_base_nombre')
    )


def _infer_relation_type(document, group_key=''):
    document_type = _metadata_type(document)
    if document_type == 'EGRESO':
        return 'EGRESO'
    if document_type == 'EXTRACTO BANCARIO':
        return 'EXTRACTO_BANCARIO'
    if document_type == 'CONCILIACION':
        return 'CONCILIACION'
    return 'OTRO_SOPORTE'


def _build_relation_match(principal, related, group_key):
    filename_match = _filename_relation_match(principal, related, group_key)
    if filename_match:
        return filename_match

    if _same_pel_family(principal, related):
        confidence = 85 if _is_tomo_document(related) else 90
        return {
            'criterio_relacion': f'Coincidencia por {group_key}',
            'confianza': confidence,
            'prioridad': 80,
            'motivo': 'Misma familia PEL y documento principal claro',
        }

    confidence = _relation_confidence(principal, related, group_key)
    return {
        'criterio_relacion': f'Coincidencia por {group_key}',
        'confianza': confidence,
        'prioridad': 50,
        'motivo': 'Coincidencia documental insuficiente',
        'codigo_error': 'CONFIANZA_NO_CALCULADA' if not _has_real_confidence(confidence) else 'FAMILIA_PEL_NO_CONFIABLE',
    }


def _should_update_relation(relation, relation_match):
    current_priority = _relation_priority(relation.criterio_relacion)
    next_priority = relation_match.get('prioridad', 0)
    current_confidence = float(relation.confianza)
    next_confidence = relation_match['confianza']
    return next_priority > current_priority or (
        next_priority == current_priority and next_confidence > current_confidence
    )


def _relation_priority(criterio_relacion):
    criterio = str(criterio_relacion or '').upper()
    if 'PEL-' in criterio:
        return 80
    return 0


def _relation_confidence(principal, related, group_key):
    principal_codes = _matching_codes(principal, group_key)
    related_codes = _matching_codes(related, group_key)
    if not principal_codes or not related_codes:
        return None

    score = 70
    if any(
        code.get('suffix') == 1
        or code.get('source') == 'consecutivo'
        or (code.get('tomo') == 1 and code.get('parte') == 1)
        or _metadata_type(principal) == 'FACTURA_PRINCIPAL_PEL'
        for code in principal_codes
    ):
        score += 15
    if any(
        (code.get('suffix') or 0) > 1
        or code.get('tomo')
        or code.get('parte')
        for code in related_codes
    ):
        score += 10

    if _filename_base(principal) and _filename_base(principal) == _filename_base(related):
        score += 5

    return min(score, 100)


def document_natural_order_key(document):
    return get_documental_natural_sort_key(getattr(document, 'nombre_archivo', ''))


def _filename_relation_match(principal, related, group_key):
    if not str(group_key).startswith('PEL-') or not _same_pel_family(principal, related):
        return None

    principal_meta = _document_pel_metadata(principal)
    related_meta = _document_pel_metadata(related)
    if not principal_meta.get('nombre_reconocido') or not related_meta.get('nombre_reconocido'):
        return None

    if _is_same_tomo_family(principal_meta, related_meta):
        return {
            'criterio_relacion': f'Familia documental por nombre {group_key} TOMO',
            'confianza': 100,
            'prioridad': 98,
            'motivo': 'Misma familia PEL por nombre y tomos ordenables',
        }

    if _is_same_subparte_family(principal_meta, related_meta):
        return {
            'criterio_relacion': f'Familia documental por nombre {group_key} SUBPARTE',
            'confianza': 100,
            'prioridad': 98,
            'motivo': 'Misma familia PEL por nombre y subpartes ordenables',
        }

    return {
        'criterio_relacion': f'Coincidencia por nombre {group_key}',
        'confianza': 85,
        'prioridad': 85,
        'motivo': 'Misma familia PEL por nombre, sin estructura complementaria clara',
    }


def _is_same_tomo_family(principal_meta, related_meta):
    return bool(
        principal_meta.get('tomo_nombre')
        and principal_meta.get('parte_nombre')
        and related_meta.get('tomo_nombre')
        and related_meta.get('parte_nombre')
    )


def _is_same_subparte_family(principal_meta, related_meta):
    return bool(
        principal_meta.get('subparte_nombre')
        and related_meta.get('subparte_nombre')
        and not principal_meta.get('tomo_nombre')
        and not related_meta.get('tomo_nombre')
    )


def _has_real_confidence(value):
    if value in (None, ''):
        return False
    try:
        float(value)
    except (TypeError, ValueError):
        return False
    return True


def _principal_rank(document, group_key):
    codes = _matching_codes(document, group_key)
    ranks = []
    for code in codes:
        if code.get('kind') == 'pel':
            suffix = code.get('suffix')
            tomo = code.get('tomo')
            parte = code.get('parte')
            is_principal_type = _metadata_type(document) == 'FACTURA_PRINCIPAL_PEL'

            if suffix is not None and suffix > 1:
                # Filename confirma posición no-principal — OCR irrelevante
                ranks.append(0)
            elif tomo is not None and not (tomo == 1 and parte == 1):
                # Tomo no es 1-1 — nunca principal
                ranks.append(0)
            elif suffix == 1 or (tomo == 1 and parte == 1):
                # Filename confirma posición principal
                ranks.append(120 if is_principal_type else 100)
            elif suffix is None and code.get('source') == 'consecutivo':
                # Documento autónomo identificado por consecutivo
                ranks.append(120 if is_principal_type else 90)
            else:
                ranks.append(120 if is_principal_type else 0)
    return max(ranks or [0])


def _matching_codes(document, group_key):
    return [code for code in _relation_codes(document) if code['group_key'] == group_key]



def _same_pel_family(first, second):
    first_base = _filename_base(first)
    second_base = _filename_base(second)
    return bool(first_base and second_base and first_base == second_base)



def _is_tomo_document(document):
    metadata = _document_pel_metadata(document)
    return bool(metadata.get('tomo_nombre'))


def _relation_codes(document):
    metadata = getattr(document, 'metadata', None)

    values = []
    if metadata:
        values.append(('consecutivo', metadata.consecutivo))

    codes = []
    seen = set()
    for source, value in values:
        parsed = _parse_relation_code(value, source)
        if not parsed:
            continue
        key = (parsed['group_key'], parsed['normalized'], parsed['source'])
        if key in seen:
            continue
        codes.append(parsed)
        seen.add(key)

    filename_code = _parse_filename_relation_code(document)
    if filename_code:
        key = (filename_code['group_key'], filename_code['normalized'], filename_code['source'])
        if key not in seen:
            codes.append(filename_code)
    return codes


def _parse_filename_relation_code(document):
    metadata = _document_pel_metadata(document)
    if not metadata.get('nombre_reconocido') or not metadata.get('pel_base_nombre'):
        return None

    base = str(int(metadata['pel_base_nombre']))
    tomo = metadata.get('tomo_nombre')
    parte = metadata.get('parte_nombre')
    suffix = metadata.get('subparte_nombre')

    if tomo and parte:
        tomo_value = int(tomo)
        parte_value = int(parte)
        return {
            'kind': 'pel',
            'source': 'nombre_archivo',
            'normalized': f'PEL-{base}-TOMO-{tomo_value}-{parte_value}',
            'group_key': f'PEL-{base}',
            'suffix': None,
            'tomo': tomo_value,
            'parte': parte_value,
        }

    suffix_value = int(suffix) if suffix else None
    normalized = f'PEL-{base}-{suffix_value}' if suffix_value else f'PEL-{base}'
    return {
        'kind': 'pel',
        'source': 'nombre_archivo',
        'normalized': normalized,
        'group_key': f'PEL-{base}',
        'suffix': suffix_value,
        'tomo': None,
        'parte': None,
    }


def _parse_relation_code(value, source):
    if not value:
        return None

    text = str(value).upper().strip()
    text = re.sub(r'\s+', ' ', text)

    pel_match = re.search(r'\b(?:[A-Z]{2,4}-)?PEL[- ]?0*(\d{4,8})(?:\s*[- ]\s*(\d{1,2}))?\b', text)
    if pel_match:
        number, suffix = pel_match.groups()
        suffix_value = int(suffix) if suffix else None
        number = str(int(number))
        normalized = f'PEL-{number}-{suffix_value}' if suffix_value else f'PEL-{number}'
        return {
            'kind': 'pel',
            'source': source,
            'normalized': normalized,
            'group_key': f'PEL-{number}',
            'suffix': suffix_value,
            'tomo': None,
            'parte': None,
        }

    return None


def _filename_base(document):
    metadata = _document_pel_metadata(document)
    base = metadata.get('pel_base_nombre')
    return str(int(base)) if base else ''


def _document_pel_metadata(document):
    name_metadata = extraer_metadata_nombre_archivo(document.nombre_archivo)
    metadata = getattr(document, 'metadata', None)
    datos_pel = getattr(metadata, 'datos_pel', None) or {}

    result = dict(name_metadata)
    for key in [
        'identidad_documental',
        'pel_base_nombre',
        'subparte_nombre',
        'tomo_nombre',
        'parte_nombre',
        'parte_tomo_nombre',
        'tipo_nombre',
    ]:
        value = datos_pel.get(key)
        if value not in (None, ''):
            result[key] = value

    if result.get('pel_base_nombre') and result.get('identidad_documental'):
        result['nombre_reconocido'] = True
    return result


