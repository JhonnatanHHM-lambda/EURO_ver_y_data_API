import os
from django.db import transaction
from django.utils import timezone
from pathlib import Path
from migracion_masiva_archivo.models import (
    DocumentoDigitalizado,
    LogProcesoDocumental,
    LoteDocumental,
)
from migracion_masiva_archivo.services.continuidad_service import (
    recuperar_faltantes_desde_secundaria,
    resolver_carpeta_secundaria_automatica,
)
from migracion_masiva_archivo.services.error_message_service import build_phase1_error_message
from migracion_masiva_archivo.services.file_name_service import get_document_identity_from_filename
from migracion_masiva_archivo.services.saia.historical_service import find_historical_saia_evidence

_MESES_IDENTIDAD = frozenset({
    'ENERO', 'FEBRERO', 'MARZO', 'ABRIL', 'MAYO', 'JUNIO',
    'JULIO', 'AGOSTO', 'SEPTIEMBRE', 'OCTUBRE', 'NOVIEMBRE', 'DICIEMBRE',
})


def _is_month_based_identity(identity):
    """True cuando la identidad documental está basada en un nombre de mes (ej. BANCOLOMBIA-ENERO)."""
    return bool(identity) and any(p in _MESES_IDENTIDAD for p in str(identity).upper().split('-'))


def _parent_folder(ruta):
    """Nombre en mayúsculas de la carpeta inmediata que contiene el archivo."""
    if not ruta:
        return ''
    try:
        return os.path.basename(os.path.dirname(str(ruta))).upper().strip()
    except Exception:
        return ''
from migracion_masiva_archivo.services.scanner_service import normalize_selected_folder, scan_folder_with_context


DOCUMENT_MODEL_FIELDS = {
    field.name for field in DocumentoDigitalizado._meta.fields
    if field.name not in {'id', 'creado', 'modificado', 'estado', 'lote'}
}


@transaction.atomic
def crear_lote_desde_carpeta(
    carpeta_origen,
    nombre=None,
    usuario=None,
    carpeta_secundaria=None,
    inventariar_secundaria_completa=False,
    retornar_contexto=False,
):
    carpeta_origen = str(normalize_selected_folder(carpeta_origen))
    carpeta_secundaria = str(normalize_selected_folder(carpeta_secundaria)) if carpeta_secundaria else None
    scanned_documents, scanner_context = scan_folder_with_context(carpeta_origen)

    # Si no se configuró carpeta secundaria explícitamente, intentar detectar
    # automáticamente la ruta en GestionDocumental(192.168.1.245):
    # Escritorio → GestionDocumental(245) → ARCHIVO CENTRAL → DIGITALIZACIÓN →
    # COMPROBANTES CONTABLES → {identificador del lote}
    if not carpeta_secundaria:
        _detected = resolver_carpeta_secundaria_automatica(scanned_documents)
        if _detected:
            carpeta_secundaria = _detected

    recovered_documents, continuity_context = recuperar_faltantes_desde_secundaria(
        scanned_documents,
        carpeta_secundaria=carpeta_secundaria,
        inventariar_secundaria_completa=inventariar_secundaria_completa,
    )
    scanned_documents.extend(recovered_documents)
    _merge_scanner_context(continuity_context, scanner_context, scanned_documents)

    # Excluir archivos que ya fueron cargados exitosamente a SAIA en lotes anteriores.
    # No necesitan pasar por OCR, validación ni carga — ya están en la plataforma.
    scanned_documents, total_omitidos_saia = _excluir_ya_cargados_saia(scanned_documents)

    # Excluir archivos que no son PDF — solo se procesan documentos PDF.
    scanned_documents, total_omitidos_no_pdf = _excluir_no_pdf(scanned_documents)

    now = timezone.now()
    lote = LoteDocumental.objects.create(
        nombre=nombre or f'Lote documental {now:%Y-%m-%d %H:%M}',
        carpeta_origen=carpeta_origen,
        estado_proceso='EN_PROCESO',
        total_archivos=len(scanned_documents),
        total_procesados=0,
        iniciado_por=str(usuario) if usuario and usuario.is_authenticated else None,
        fecha_inicio=now,
    )

    created_documents = []
    total_revision = 0
    total_fallidos = 0
    seen_hashes = {}
    seen_identities = {}
    seen_normalized_paths = {}
    simple_by_base = {}
    subpart1_by_base = {}

    for file_info in scanned_documents:
        duplicate_of = _find_duplicate_by_identity(file_info, seen_identities)
        duplicate_reason = 'Archivo duplicado por identidad documental'
        if not duplicate_of:
            duplicate_of = _find_duplicate_by_hash(file_info, seen_hashes)
            duplicate_reason = 'Archivo duplicado por hash'
        if not duplicate_of:
            duplicate_of = _find_duplicate_by_normalized_path(file_info, seen_normalized_paths)
            duplicate_reason = 'Archivo duplicado por ruta normalizada'

        if duplicate_of:
            file_info['es_duplicado'] = True
            file_info['documento_duplicado_de'] = duplicate_of
            file_info['estado_proceso'] = 'REQUIERE_REVISION'
            file_info['error'] = _append_error(file_info.get('error', ''), duplicate_reason)

        document = DocumentoDigitalizado.objects.create(lote=lote, **_model_file_info(file_info))
        created_documents.append(document)
        _register_file_validation_context(continuity_context, document, file_info)
        _register_simple_subpart_conflict(continuity_context, document, simple_by_base, subpart1_by_base)
        historic_duplicate = _find_historic_duplicate(document)
        if historic_duplicate:
            _register_historic_duplicate(continuity_context, document, historic_duplicate)
            mensaje_historico = (
                historic_duplicate.get('mensaje_bloqueo_saia_historico')
                or (
                    'Documento ya cargado exitosamente a SAIA en lote anterior'
                    if historic_duplicate.get('ya_cargado_saia')
                    else 'Documento encontrado en lote anterior sin evidencia de carga SAIA exitosa'
                )
            )
            if historic_duplicate.get('ya_cargado_saia'):
                # Ya subido a SAIA → bloquear para evitar carga duplicada
                if document.estado_proceso != 'REQUIERE_REVISION':
                    total_revision += 1
                document.estado_proceso = 'REQUIERE_REVISION'
                document.error = _append_error(document.error, mensaje_historico)
                document.save(update_fields=['estado_proceso', 'error'])
                _log_document(document, 'WARNING', 'duplicado_historico', document.error, historic_duplicate)
                continue
            else:
                # Encontrado en lote anterior fallido → advertencia, continúa a F2
                document.error = _append_error(document.error, mensaje_historico)
                document.save(update_fields=['error'])
                _log_document(document, 'WARNING', 'duplicado_historico', document.error, historic_duplicate)

        if document.hash_archivo and not document.es_duplicado:
            seen_hashes[document.hash_archivo] = document
        normalized_path = _normalize_path(document.ruta_archivo)
        if normalized_path and not document.es_duplicado:
            seen_normalized_paths[normalized_path] = document
        identity = get_document_identity_from_filename(document.nombre_archivo)
        if identity and not document.es_duplicado:
            seen_identities[identity] = document

        if document.es_duplicado:
            total_revision += 1
            _log_document(
                document,
                'WARNING',
                'archivo_duplicado',
                document.error,
                {'duplicado_de': duplicate_of.id if duplicate_of else None},
            )
            continue

        if not document.es_soportado:
            total_revision += 1
            _log_document(document, 'WARNING', 'formato_no_soportado', document.error)
            continue

        if file_info.get('error') and _file_info_blocks_phase2(file_info):
            total_fallidos += 1
            document.estado_proceso = 'REQUIERE_REVISION'
            document.save(update_fields=['estado_proceso'])
            _log_document(document, 'WARNING', 'archivo_con_error', file_info['error'])
            continue
        if file_info.get('error'):
            _log_document(document, 'WARNING', 'archivo_con_advertencia', file_info['error'])

    lote.total_procesados = len(created_documents)
    blocked_documents = _persist_continuity_blocks(lote, continuity_context, created_documents)
    total_revision += blocked_documents
    lote.total_revision = total_revision
    lote.total_fallidos = total_fallidos
    lote.total_exitosos = max(0, len(created_documents) - total_revision - total_fallidos)
    lote.estado_proceso = 'FINALIZADO_CON_ERRORES' if total_revision or total_fallidos else 'FINALIZADO'
    lote.fecha_fin = timezone.now()
    lote.save(
        update_fields=[
            'total_procesados',
            'total_revision',
            'total_fallidos',
            'total_exitosos',
            'estado_proceso',
            'fecha_fin',
        ]
    )

    LogProcesoDocumental.objects.create(
        lote=lote,
        evento='exploracion_carpeta',
        mensaje='Exploracion documental finalizada',
        detalle={
            'carpeta_origen': carpeta_origen,
            'total_archivos': len(created_documents),
            'total_exitosos': lote.total_exitosos,
            'total_revision': total_revision,
            'total_fallidos': total_fallidos,
            'omitidos_ya_en_saia': total_omitidos_saia,
            'omitidos_no_pdf': total_omitidos_no_pdf,
            'continuidad': continuity_context.get('resumen', {}),
        },
    )
    _log_continuity_context(lote, continuity_context)
    _log_historic_duplicates(lote, continuity_context)

    if retornar_contexto:
        return lote, created_documents, continuity_context
    return lote, created_documents


def _model_file_info(file_info):
    return {key: value for key, value in file_info.items() if key in DOCUMENT_MODEL_FIELDS}


def _find_duplicate_by_identity(file_info, seen_identities):
    identity = get_document_identity_from_filename(file_info.get('nombre_archivo'))
    if not identity:
        return None

    if identity in seen_identities:
        # Archivos de mes compartido (ENERO, FEBRERO…) pueden pertenecer a bancos distintos
        # (Bancolombia, Colpatria, Corbanca, CCA, CCV). Si la carpeta padre difiere,
        # son documentos distintos y no deben marcarse como duplicados entre sí.
        if _is_month_based_identity(identity):
            prev_doc = seen_identities[identity]
            if _parent_folder(file_info.get('ruta_archivo')) != _parent_folder(prev_doc.ruta_archivo):
                return None
        return seen_identities[identity]

    return None


def _find_duplicate_by_hash(file_info, seen_hashes):
    file_hash = file_info.get('hash_archivo')
    if not file_hash:
        return None

    identity = get_document_identity_from_filename(file_info.get('nombre_archivo'))

    if file_hash in seen_hashes:
        previous_document = seen_hashes[file_hash]
        previous_identity = get_document_identity_from_filename(previous_document.nombre_archivo)
        if identity and previous_identity and identity != previous_identity:
            return None
        return previous_document

    return None


def _find_duplicate_by_normalized_path(file_info, seen_paths):
    normalized = _normalize_path(file_info.get('ruta_archivo'))
    if not normalized:
        return None
    return seen_paths.get(normalized)


def _find_historic_duplicate(document):
    return find_historical_saia_evidence(document)


def _merge_scanner_context(continuity_context, scanner_context, scanned_documents):
    resumen = continuity_context.setdefault('resumen', {})
    for key, value in scanner_context.items():
        resumen[key] = resumen.get(key, 0) + value
    continuity_context.setdefault('validaciones_archivo', {})
    continuity_context.setdefault('duplicados_historicos', [])
    continuity_context.setdefault('conflictos_simple_subparte_1', [])


def _register_file_validation_context(context, document, file_info):
    validation_fields = {
        'archivo_vacio',
        'archivo_sospechosamente_pequeno',
        'validacion_tamano',
        'firma_archivo',
        'extension_coincide_con_firma',
        'tipo_detectado_por_firma',
        'error_firma_archivo',
        'error_lectura_tamano',
        'error_lectura_hash',
        'archivo_posiblemente_bloqueado',
        'archivo_posiblemente_sincronizando',
        'pdf_supera_limite_saia',
        'pdf_pesado_saia',
        'advertencia_tamano_saia',
        'requiere_timeout_extendido',
        'saia_max_file_mb',
        'validacion_tamano_saia',
        'nombre_pel_ambiguo',
        'caracteres_no_compatibles_saia',
        'caracteres_problematicos_saia',
        'extension_doble_o_sospechosa',
        'consecutivo_nombre_no_coincide_contenido',
        'consecutivos_contenido_detectados',
        'validaciones_nombre',
        'error_pdf',
    }
    context.setdefault('validaciones_archivo', {})[document.id] = {
        key: file_info.get(key, '') for key in validation_fields
    }


def _register_historic_duplicate(context, document, duplicate_info):
    duplicate_info['documento_id'] = document.id
    context.setdefault('duplicados_historicos', []).append(duplicate_info)


def _register_simple_subpart_conflict(context, document, simple_by_base, subpart1_by_base):
    from migracion_masiva_archivo.services.file_name_service import extraer_metadata_nombre_archivo

    metadata = extraer_metadata_nombre_archivo(document.nombre_archivo)
    base = metadata.get('pel_base_nombre')
    if not base or metadata.get('tomo_nombre'):
        return

    is_simple = metadata.get('identidad_documental') == f'PEL-{base}'
    is_subpart_1 = metadata.get('subparte_nombre') == 1 and metadata.get('identidad_documental') != f'PEL-{base}'

    if is_simple:
        simple_by_base[base] = document
        other = subpart1_by_base.get(base)
    elif is_subpart_1:
        subpart1_by_base[base] = document
        other = simple_by_base.get(base)
    else:
        return

    if not other:
        return

    conflict = {
        'pel_base': base,
        'estado_continuidad': 'PEL_SIMPLE_Y_SUBPARTE_1_CONFLICTO',
        'observacion_continuidad': (
            f'Conflicto entre PEL {base} simple y PEL {base} - 1; requiere revision documental'
        ),
        'documentos': [other.id, document.id],
        'nombres': [other.nombre_archivo, document.nombre_archivo],
    }
    context.setdefault('conflictos_simple_subparte_1', []).append(conflict)


def _persist_continuity_blocks(lote, context, documents):
    blocked_bases = _blocked_bases_from_context(context)
    blocked_ids = {
        doc_id
        for conflict in context.get('conflictos_simple_subparte_1', [])
        for doc_id in conflict.get('documentos', [])
    }
    updated = 0
    for document in documents:
        from migracion_masiva_archivo.services.file_name_service import extraer_metadata_nombre_archivo

        metadata = extraer_metadata_nombre_archivo(document.nombre_archivo)
        base = metadata.get('pel_base_nombre')
        reason = ''
        if base in blocked_bases:
            reason = blocked_bases[base]
        elif document.id in blocked_ids:
            reason = 'Bloqueado por continuidad documental: conflicto entre PEL simple y subparte 1'
        if not reason:
            continue
        if document.estado_proceso != 'REQUIERE_REVISION':
            updated += 1
        document.estado_proceso = 'REQUIERE_REVISION'
        document.error = _append_error(document.error, reason)
        document.save(update_fields=['estado_proceso', 'error'])
        _log_document(document, 'WARNING', 'bloqueo_continuidad', reason)
    return updated


def _blocked_bases_from_context(context):
    blocking_statuses = {
        'FALTANTE_PEL_BASE',
        'FALTANTE_NO_ENCONTRADO',
        'CARPETA_SECUNDARIA_NO_CONFIGURADA',
        'CARPETA_SECUNDARIA_NO_ACCESIBLE',
        'FALTANTE_SUBPARTE',
        'FALTA_PRINCIPAL_SUBPARTE',
        'FALTANTE_SUBPARTE_NO_ENCONTRADO',
        'FALTANTE_TOMO',
        'FALTA_TOMO_INICIAL',
        'FALTANTE_PARTE_TOMO',
        'FALTA_PARTE_INICIAL',
        'FALTANTE_PARTE_TOMO_NO_ENCONTRADO',
    }
    blocked = {}
    for collection in (
        context.get('alertas', []),
        context.get('subpartes', {}).get('faltantes', []),
        context.get('tomos', {}).get('faltantes', []),
    ):
        for item in collection:
            if item.get('estado_continuidad') not in blocking_statuses:
                continue
            base = item.get('pel_base')
            if base:
                missing = item.get('consecutivo_faltante') or f'PEL {base}'
                blocked[base] = f'Bloqueado por continuidad documental: falta {missing}'
    return blocked


def _file_info_blocks_phase2(file_info):
    if file_info.get('nombre_pel_ambiguo'):
        return True
    if file_info.get('extension_doble_o_sospechosa'):
        return True
    if file_info.get('consecutivo_nombre_no_coincide_contenido'):
        return True
    if file_info.get('archivo_vacio') or file_info.get('archivo_sospechosamente_pequeno'):
        return True
    if file_info.get('error_lectura_tamano') or file_info.get('error_lectura_hash'):
        return True
    if file_info.get('error_firma_archivo') or file_info.get('error_pdf'):
        return True
    if file_info.get('es_soportado') and file_info.get('extension_coincide_con_firma') is False:
        return True
    return False


def _normalize_path(path):
    raw = str(path or '').strip()
    if not raw:
        return ''
    try:
        raw = str(Path(raw).resolve())
    except OSError:
        pass
    return ' '.join(raw.replace('\\', '/').lower().split())


def _log_document(document, nivel, evento, mensaje, detalle=None):
    log_detail = detalle or {}
    log_detail['error_usuario'] = build_phase1_error_message(mensaje, {
        'contiene_ok': ' OK' in document.nombre_archivo.upper(),
        'es_duplicado': document.es_duplicado,
        'es_soportado': document.es_soportado,
    })
    LogProcesoDocumental.objects.create(
        lote=document.lote,
        documento=document,
        nivel=nivel,
        evento=evento,
        mensaje=mensaje,
        detalle=log_detail,
    )


def _log_continuity_context(lote, context):
    resumen = context.get('resumen', {})
    faltantes = context.get('faltantes', [])
    cambios_rango = context.get('cambios_rango', [])
    subpartes = context.get('subpartes', {}).get('faltantes', [])
    tomos = context.get('tomos', {}).get('faltantes', [])
    recuperados = context.get('recuperados', [])
    alertas = context.get('alertas', [])
    duplicados_entre_carpetas = context.get('duplicados_entre_carpetas', [])

    if faltantes or cambios_rango:
        LogProcesoDocumental.objects.create(
            lote=lote,
            nivel='WARNING',
            evento='continuidad_base_detectada',
            mensaje='Se detectaron saltos en la continuidad de consecutivos PEL',
            detalle={
                'resumen': resumen,
                'faltantes': faltantes,
                'cambios_rango': cambios_rango,
            },
        )

    for recovered in recuperados:
        LogProcesoDocumental.objects.create(
            lote=lote,
            nivel='INFO',
            evento=(
                'inventario_secundaria_completo'
                if recovered.get('estado_continuidad') == 'INVENTARIO_SECUNDARIA_COMPLETO'
                else 'faltante_encontrado_secundaria'
            ),
            mensaje=(
                'Documento incluido desde inventario completo de carpeta secundaria'
                if recovered.get('estado_continuidad') == 'INVENTARIO_SECUNDARIA_COMPLETO'
                else 'Consecutivo faltante encontrado en carpeta secundaria'
            ),
            detalle=recovered,
        )

    for alert in alertas:
        error_usuario = build_phase1_error_message(alert.get('observacion_continuidad', ''), alert)
        event = (
            'carpeta_secundaria_no_accesible'
            if alert.get('estado_continuidad') == 'CARPETA_SECUNDARIA_NO_ACCESIBLE'
            else 'faltante_no_encontrado'
        )
        LogProcesoDocumental.objects.create(
            lote=lote,
            nivel='WARNING',
            evento=event,
            mensaje=alert.get('observacion_continuidad', ''),
            detalle={**alert, 'error_usuario': error_usuario},
        )

    if subpartes:
        LogProcesoDocumental.objects.create(
            lote=lote,
            nivel='WARNING',
            evento='continuidad_subparte_detectada',
            mensaje='Se detectaron faltantes en subpartes PEL',
            detalle={
                'faltantes': subpartes,
                'resumen': resumen,
                'error_usuario': build_phase1_error_message('', subpartes[0]),
            },
        )

    if tomos:
        LogProcesoDocumental.objects.create(
            lote=lote,
            nivel='WARNING',
            evento='continuidad_tomo_detectada',
            mensaje='Se detectaron faltantes en tomos o partes PEL',
            detalle={
                'faltantes': tomos,
                'resumen': resumen,
                'error_usuario': build_phase1_error_message('', tomos[0]),
            },
        )

    for duplicate in duplicados_entre_carpetas:
        LogProcesoDocumental.objects.create(
            lote=lote,
            nivel='WARNING',
            evento='duplicado_entre_carpetas',
            mensaje='Documento duplicado entre carpeta principal y secundaria',
            detalle={
                **duplicate,
                'error_usuario': build_phase1_error_message(
                    'Documento duplicado entre carpeta principal y secundaria',
                    {'es_duplicado': True},
                ),
            },
        )


def _log_historic_duplicates(lote, context):
    for duplicate in context.get('duplicados_historicos', []):
        LogProcesoDocumental.objects.create(
            lote=lote,
            nivel='WARNING',
            evento='duplicado_historico',
            mensaje='Documento encontrado en lote anterior',
            detalle={
                **duplicate,
                'error_usuario': build_phase1_error_message('', duplicate),
            },
        )


def _excluir_no_pdf(scanned_documents):
    """
    Filtra archivos que no son PDF antes de crear el lote.
    Solo se procesan documentos PDF — cualquier otro formato se omite
    completamente sin crear registro en BD ni generar errores en el log.
    Retorna (lista_filtrada, total_omitidos).
    """
    filtered = []
    omitidos = 0
    for file_info in scanned_documents:
        if file_info.get('extension', '').lower() == 'pdf':
            filtered.append(file_info)
        else:
            omitidos += 1
    return filtered, omitidos


def _excluir_ya_cargados_saia(scanned_documents):
    """
    Filtra de la lista de escaneo los archivos que ya fueron cargados
    exitosamente a SAIA. Un archivo se omite si cumple CUALQUIERA de:

      1. Su nombre contiene ' OK' → marca de negocio que indica carga exitosa.
      2. Su hash SHA-256 coincide con un CARGADO_SAIA en BD → mismo contenido.
      3. Su identidad PEL coincide con un CARGADO_SAIA en BD → mismo expediente.

    Los criterios 2 y 3 dependen de la BD; el criterio 1 es independiente
    y actúa como red de seguridad cuando la BD no tiene el historial.

    Usa 2 queries a la BD y lookup O(1) por archivo.
    Retorna (lista_filtrada, total_omitidos).
    """
    cargados_hashes = set(
        DocumentoDigitalizado.objects
        .filter(estado_proceso='CARGADO_SAIA', hash_archivo__gt='')
        .values_list('hash_archivo', flat=True)
    )
    cargados_identidades = set(filter(None, (
        get_document_identity_from_filename(n)
        for n in DocumentoDigitalizado.objects
        .filter(estado_proceso='CARGADO_SAIA')
        .values_list('nombre_archivo', flat=True)
    )))

    filtered = []
    omitidos = 0
    for file_info in scanned_documents:
        nombre = file_info.get('nombre_archivo', '')
        file_hash = file_info.get('hash_archivo', '')
        file_identity = get_document_identity_from_filename(nombre)

        tiene_ok_en_nombre = ' ok' in nombre.lower()
        en_bd_por_hash = file_hash and file_hash in cargados_hashes
        en_bd_por_identidad = file_identity and file_identity in cargados_identidades

        if tiene_ok_en_nombre or en_bd_por_hash or en_bd_por_identidad:
            omitidos += 1
            continue
        filtered.append(file_info)
    return filtered, omitidos


def _append_error(current, extra):
    if not extra:
        return current or ''
    if not current:
        return extra
    return f'{current}; {extra}'


