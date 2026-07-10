from django.db import transaction

from migracion_masiva_archivo.execution_control import control
from migracion_masiva_archivo.models import DocumentoDigitalizado, LogProcesoDocumental, MetadataDocumento
from migracion_masiva_archivo.services.error_message_service import (
    PHASE_2,
    build_phase2_error_message,
    get_blocking_phase_error,
)
from migracion_masiva_archivo.services.extraction_service import extract_metadata_from_text
from migracion_masiva_archivo.services.ocr_service import OCRNotConfiguredError, extract_text_with_ocr
from migracion_masiva_archivo.services.validacion_service import validate_metadata


def procesar_documento_metadata(documento, usar_ocr=True, max_pages=2):
    # Fix 2: @transaction.atomic eliminado del decorador — el OCR puede durar 10-30 seg
    # y no debe mantener la transacción de BD abierta. Las escrituras finales tienen
    # su propio bloque with transaction.atomic() más abajo.

    blocking_error = get_blocking_phase_error(documento, target_phase=PHASE_2)
    if blocking_error:
        return _skip_blocked_previous_phase(documento, blocking_error)

    if documento.es_duplicado:
        return _mark_revision(documento, 'Documento duplicado. No se procesa metadata automaticamente.')

    if not documento.es_soportado:
        return _mark_revision(documento, 'Formato no soportado para extraccion documental.')

    if _is_retencion_ica_document(documento):
        max_pages = max(max_pages, 3)

    text = documento.texto_extraido or ''
    pages_text = []
    page_detected = None

    if usar_ocr and documento.requiere_ocr and not text:
        # Fix 2: OCR corre fuera de transacción
        ocr = _ejecutar_ocr(documento, max_pages)
        if ocr.get('mark_revision'):
            return _mark_revision(documento, ocr['mensaje'], event=ocr['event'])
        text       = ocr['text']
        pages_text = ocr['pages_text']
        page_detected = ocr['page_detected']

    if not text:
        return _mark_revision(documento, 'No hay texto disponible para extraer metadata.')

    metadata_values = (
        extract_metadata_from_pages(pages_text, documento.nombre_archivo, ruta_archivo=documento.ruta_archivo)
        if pages_text
        else extract_metadata_from_text(text, filename=documento.nombre_archivo, ruta_archivo=documento.ruta_archivo)
    )
    validation = validate_metadata(metadata_values)
    metadata_values['requiere_revision'] = metadata_values['requiere_revision'] or not validation['is_valid']
    extraction_notes = metadata_values.pop('observaciones_extraccion', '')
    # Fix 1: mismatch_consecutivo es un flag de extracción, no un campo del modelo
    metadata_values.pop('mismatch_consecutivo', None)
    mismatch_bloquea = metadata_values.pop('mismatch_bloquea', False)
    ocr_consecutivo_original = metadata_values.pop('ocr_consecutivo_original', '')
    _roi_obs_extra = ''
    if mismatch_bloquea:
        roi_consecutivo = _intentar_roi_ocr(documento)
        if roi_consecutivo:
            if roi_consecutivo == metadata_values.get('consecutivo'):
                # ROI confirma el nombre → fallo de OCR en página completa → desbloquear
                mismatch_bloquea = False
                revalidation = validate_metadata(metadata_values)
                metadata_values['requiere_revision'] = not revalidation['is_valid']
                LogProcesoDocumental.objects.create(
                    lote=documento.lote,
                    documento=documento,
                    nivel='INFO',
                    evento='roi_ocr_confirma_consecutivo',
                    mensaje='ROI OCR confirmó el consecutivo del nombre de archivo; error descartado como fallo OCR.',
                    detalle={'roi_consecutivo': roi_consecutivo},
                )
            elif roi_consecutivo == ocr_consecutivo_original:
                # ROI confirma OCR → doble evidencia de archivo mal nombrado
                _roi_obs_extra = (
                    f'ROI OCR confirma consecutivo interno ({roi_consecutivo}); '
                    'el nombre del archivo puede ser incorrecto — revisar manualmente.'
                )
                LogProcesoDocumental.objects.create(
                    lote=documento.lote,
                    documento=documento,
                    nivel='WARNING',
                    evento='roi_ocr_sugiere_archivo_mal_nombrado',
                    mensaje='ROI OCR confirma el consecutivo interno; el nombre del archivo puede ser incorrecto.',
                    detalle={
                        'roi_consecutivo': roi_consecutivo,
                        'ocr_consecutivo': ocr_consecutivo_original,
                        'filename_consecutivo': metadata_values.get('consecutivo'),
                    },
                )
            else:
                # ROI inconclusivo → bloqueo se mantiene sin información adicional
                LogProcesoDocumental.objects.create(
                    lote=documento.lote,
                    documento=documento,
                    nivel='INFO',
                    evento='roi_ocr_inconclusivo',
                    mensaje='ROI OCR no coincide con OCR ni con nombre de archivo; resultado inconclusivo.',
                    detalle={'roi_consecutivo': roi_consecutivo},
                )
    metadata_values['observaciones'] = '; '.join(
        item for item in [extraction_notes, _roi_obs_extra, '; '.join(validation['errors'])] if item
    )
    phase2_error = build_phase2_error_message(
        metadata_values['observaciones'],
        _build_phase2_error_context(
            metadata_values,
            extraction_notes=extraction_notes,
            validation_errors=validation['errors'],
            text=text,
        ),
    )
    phase2_user_note = _format_phase2_user_note(phase2_error)
    if phase2_user_note:
        metadata_values['observaciones'] = '; '.join(
            item for item in [metadata_values['observaciones'], phase2_user_note] if item
        )

    # Persistir mismatch_bloquea en datos_pel para que Fase 4 lo detecte explícitamente.
    # Si ROI no lo resolvió (mismatch_bloquea sigue True), el flag queda en el JSONField
    # para que Phase 4 genere el error correcto y el documento aparezca en Revisión Manual.
    if mismatch_bloquea:
        _persist_mismatch_in_datos_pel(metadata_values, ocr_consecutivo_original)

    if page_detected and not metadata_values.get('pagina_detectada'):
        metadata_values['pagina_detectada'] = page_detected
    _sync_pel_page(metadata_values)

    # Fix 2: solo las escrituras en BD están dentro de la transacción
    with transaction.atomic():
        metadata, _created = MetadataDocumento.objects.update_or_create(
            documento=documento,
            defaults=metadata_values,
        )

        nuevo_estado = 'VALIDADO' if validation['is_valid'] and not metadata.requiere_revision else 'REQUIERE_REVISION'
        documento.estado_proceso = nuevo_estado
        save_fields = ['estado_proceso', 'modificado']
        if nuevo_estado == 'REQUIERE_REVISION' and not documento.error:
            documento.error = (
                metadata.observaciones
                or 'Metadata incompleta o no válida. Revise el documento e ingrese los datos manualmente.'
            )
            save_fields.append('error')
        documento.save(update_fields=save_fields)

        LogProcesoDocumental.objects.create(
            lote=documento.lote,
            documento=documento,
            evento='metadata_extraida',
            mensaje='Extraccion y normalizacion de metadata ejecutada',
            detalle={
                'nit': metadata.nit,
                'consecutivo': metadata.consecutivo,
                'confianza': float(metadata.confianza),
                'requiere_revision': metadata.requiere_revision,
                'observaciones': metadata.observaciones,
                'error_usuario_fase_2': phase2_error,
            },
        )

    return {
        'documento': documento,
        'metadata': metadata,
        'estado': documento.estado_proceso,
        'ok': validation['is_valid'] and not metadata.requiere_revision,
        'errores': validation['errors'],
    }


def _ejecutar_ocr(documento, max_pages):
    """Ejecuta el OCR fuera de transacción — puede durar 10-30 seg por documento.

    Retorna dict con:
      {'ok': True, 'text': ..., 'pages_text': ..., 'page_detected': ...}
      {'ok': False, 'mark_revision': True, 'mensaje': ..., 'event': ...}
    """
    _MSG_OCR_AGOTADO = (
        'OCR agotado: el documento no contiene texto legible tras el reconocimiento optico. '
        'Ingrese el consecutivo manualmente desde el dashboard.'
    )

    if documento.ocr_agotado:
        return {'ok': False, 'mark_revision': True, 'mensaje': _MSG_OCR_AGOTADO, 'event': 'ocr_agotado'}

    def _early_exit_check(pages_so_far):
        if max_pages < 2 or not pages_so_far:
            return False
        if _is_retencion_ica_document(documento) and len(pages_so_far) < 3:
            return False
        first_meta = extract_metadata_from_text(
            pages_so_far[0]['text'],
            filename=documento.nombre_archivo,
            ruta_archivo=documento.ruta_archivo,
        )
        return _metadata_has_key_fields(first_meta)

    try:
        ocr_result = extract_text_with_ocr(
            documento.ruta_archivo,
            max_pages=max_pages,
            early_exit_fn=_early_exit_check,
        )
    except OCRNotConfiguredError as exc:
        return {'ok': False, 'mark_revision': True, 'mensaje': str(exc), 'event': 'ocr_no_configurado'}

    text         = ocr_result['text']
    pages_text   = ocr_result.get('pages_text') or []
    page_detected = ocr_result['page_detected']

    documento.texto_extraido = text
    documento.requiere_ocr   = not bool(text)
    if not text:
        documento.ocr_agotado = True
    documento.estado_proceso = 'OCR_PROCESADO' if text else 'REQUIERE_REVISION'
    # Save intermedio fuera de transacción — registra estado OCR aunque la extracción
    # posterior falle; no requiere atomicidad con las escrituras de metadata.
    documento.save(update_fields=['texto_extraido', 'requiere_ocr', 'ocr_agotado', 'estado_proceso', 'modificado'])

    LogProcesoDocumental.objects.create(
        lote=documento.lote,
        documento=documento,
        nivel='WARNING' if not text else 'INFO',
        evento='ocr_procesado',
        mensaje='OCR ejecutado sobre documento' if text else 'OCR ejecutado: sin texto detectado.',
        detalle={
            'paginas_procesadas': ocr_result['pages_processed'],
            'pagina_detectada': page_detected,
            'texto_extraido_len': len(text),
            'ocr_agotado': documento.ocr_agotado,
        },
    )

    if not text:
        return {'ok': False, 'mark_revision': True, 'mensaje': _MSG_OCR_AGOTADO, 'event': 'ocr_agotado'}

    return {'ok': True, 'text': text, 'pages_text': pages_text, 'page_detected': page_detected}


def extract_metadata_from_pages(pages_text, filename='', ruta_archivo=''):
    combined_text = '\n'.join(page['text'] for page in pages_text)
    combined_metadata = extract_metadata_from_text(
        combined_text,
        filename=filename,
        ruta_archivo=ruta_archivo,
    )
    detected_page = None

    for page in pages_text:
        page_metadata = extract_metadata_from_text(
            page['text'],
            filename=filename,
            ruta_archivo=ruta_archivo,
        )
        if _metadata_has_key_fields(page_metadata) and detected_page is None:
            detected_page = page['page']

    if detected_page:
        combined_metadata['pagina_detectada'] = detected_page

    return combined_metadata


def _persist_mismatch_in_datos_pel(metadata_values, ocr_consecutivo_original=''):
    datos_pel = metadata_values.get('datos_pel') or {}
    datos_pel['mismatch_bloquea'] = True
    if ocr_consecutivo_original:
        datos_pel['ocr_consecutivo_mismatch'] = ocr_consecutivo_original
    metadata_values['datos_pel'] = datos_pel


def _metadata_has_key_fields(metadata):
    return bool(metadata.get('consecutivo'))


def _is_retencion_ica_document(documento):
    text = ' '.join([
        str(getattr(documento, 'ruta_archivo', '') or ''),
        str(getattr(documento, 'nombre_archivo', '') or ''),
    ]).upper()
    return (
        'RETENCION DE ICA' in text
        or 'RETENCI\u00d3N DE ICA' in text
        or 'RETENCION ICA' in text
        or 'RETENCI\u00d3N ICA' in text
        or 'DECLARACION DE RETENCION DE ICA' in text
        or 'DECLARACI\u00d3N DE RETENCI\u00d3N DE ICA' in text
    )


def _sync_pel_page(metadata_values):
    datos_pel = metadata_values.get('datos_pel') or {}
    if metadata_values.get('pagina_detectada') and not datos_pel.get('pagina_detectada_cruce'):
        datos_pel['pagina_detectada_cruce'] = metadata_values['pagina_detectada']
    metadata_values['datos_pel'] = datos_pel


def procesar_lote_metadata(lote, usar_ocr=True, max_pages=2, incluir_duplicados=False):
    documentos = DocumentoDigitalizado.objects.filter(lote=lote).order_by('id')
    if not incluir_duplicados:
        documentos = documentos.filter(es_duplicado=False)

    resultados = []
    for documento in documentos:
        control.doc_actual = documento.nombre_archivo
        # Fix 3: recuperación por documento — un PDF corrupto no detiene el lote completo
        try:
            resultados.append(
                procesar_documento_metadata(
                    documento,
                    usar_ocr=usar_ocr,
                    max_pages=max_pages,
                )
            )
        except Exception as exc:
            resultados.append(
                _mark_revision(
                    documento,
                    f'Error inesperado procesando documento: {exc}',
                    event='error_inesperado',
                )
            )

    control.doc_actual = ""
    _actualizar_totales_lote(lote)
    return resultados


@transaction.atomic
def _mark_revision(documento, mensaje, event='metadata_requiere_revision'):
    # Fix 2: @transaction.atomic aquí garantiza que el save del documento
    # y el log sean atómicos, sin mantener una transacción larga en el caller.
    phase2_error = build_phase2_error_message(mensaje, {'error': mensaje})
    documento.estado_proceso = 'REQUIERE_REVISION'
    if mensaje:
        documento.error = mensaje
    documento.save(update_fields=['estado_proceso', 'error', 'modificado'])

    LogProcesoDocumental.objects.create(
        lote=documento.lote,
        documento=documento,
        nivel='WARNING',
        evento=event,
        mensaje=phase2_error.get('mensaje_usuario') or mensaje,
        detalle={
            'error_usuario_fase_2': phase2_error,
            'error_tecnico': mensaje,
        },
    )

    return {
        'documento': documento,
        'metadata': None,
        'estado': documento.estado_proceso,
        'ok': False,
        'errores': [mensaje],
    }


def _skip_blocked_previous_phase(documento, blocking_error):
    LogProcesoDocumental.objects.create(
        lote=documento.lote,
        documento=documento,
        nivel='INFO',
        evento='metadata_omitida_por_bloqueo_previo',
        mensaje='Documento omitido en Fase 2 porque esta bloqueado por una fase previa.',
        detalle={
            'error_usuario_bloqueante': blocking_error,
            'error_tecnico': documento.error,
        },
    )
    return {
        'documento': documento,
        'metadata': getattr(documento, 'metadata', None),
        'estado': documento.estado_proceso,
        'ok': False,
        'omitido_por_bloqueo_previo': True,
        'errores': [documento.error or blocking_error.get('error_tecnico', '')],
    }


def _build_phase2_error_context(metadata_values, extraction_notes='', validation_errors=None, text=''):
    validation_errors = validation_errors or []
    context = dict(metadata_values)
    context.update(
        {
            'observaciones_extraccion': extraction_notes,
            'errores_validacion': validation_errors,
            'texto_extraido_len': len(text or ''),
        }
    )
    return context


def _format_phase2_user_note(error_message):
    code = error_message.get('codigo_error_usuario')
    if not code:
        return ''
    return (
        f"error_usuario_fase_2={code}; "
        f"mensaje_usuario={error_message.get('mensaje_usuario', '')}; "
        f"accion_recomendada={error_message.get('accion_recomendada', '')}"
    )


def _intentar_roi_ocr(documento):
    """Intenta extraer el consecutivo de la región superior derecha del PDF via ROI OCR.

    Retorna el consecutivo normalizado (e.g. 'MAY-PEL-00097343') o cadena vacía.
    Nunca lanza excepción — el ROI es siempre opcional.
    """
    try:
        if not documento.ruta_archivo:
            return ''
        from migracion_masiva_archivo.services.ocr_service import extract_consecutivo_roi
        from migracion_masiva_archivo.services.extraction_service import extract_document_consecutivo
        from migracion_masiva_archivo.services.file_name_service import extraer_metadata_nombre_archivo

        filename_meta = extraer_metadata_nombre_archivo(documento.nombre_archivo)
        doc_identifier = filename_meta.get('tipo_documento_nombre') or 'PEL'

        roi_text = extract_consecutivo_roi(documento.ruta_archivo)
        if not roi_text:
            return ''
        return extract_document_consecutivo(roi_text, doc_identifier)
    except Exception:
        return ''


def _actualizar_totales_lote(lote):
    documentos = lote.documentos.all()
    lote.total_procesados = documentos.count()
    lote.total_exitosos = documentos.filter(estado_proceso__in=['VALIDADO', 'RELACIONADO']).count()
    lote.total_revision = documentos.filter(estado_proceso='REQUIERE_REVISION').count()
    lote.total_fallidos = documentos.filter(estado_proceso='ERROR_SAIA').count()
    lote.estado_proceso = 'FINALIZADO_CON_ERRORES' if lote.total_revision or lote.total_fallidos else 'FINALIZADO'
    lote.save(
        update_fields=[
            'total_procesados',
            'total_exitosos',
            'total_revision',
            'total_fallidos',
            'estado_proceso',
            'modificado',
        ]
    )


