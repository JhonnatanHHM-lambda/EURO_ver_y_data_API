from pathlib import Path

from migracion_masiva_archivo.models import DocumentoDigitalizado, IntentoCargaSAIA, LogProcesoDocumental
from migracion_masiva_archivo.services.error_message_service import build_phase5_error_message
from migracion_masiva_archivo.services.saia.browser_client import SAIABrowserClient
from migracion_masiva_archivo.services.saia.config import get_saia_config
from migracion_masiva_archivo.services.saia.exceptions import (
    SAIACredentialsError,
    SAIADocumentValidationError,
    SAIAError,
    SAIALocalFileError,
)
from migracion_masiva_archivo.services.saia.local_file_service import mark_document_file_ok
from migracion_masiva_archivo.services.saia.routes import resolve_saia_route_context
from migracion_masiva_archivo.services.saia.validation_service import validate_document_for_saia


def probar_carga_documento_saia(
    documento_id,
    dry_run=True,
    headful=False,
    confirmar_carga=False,
    adjuntar_en_dry_run=False,
):
    documento = _get_document(documento_id)
    validation = validate_document_for_saia(documento)
    asunto_saia = validation.get('asunto_saia') or ''
    route_code = validation.get('route_code') or 'PEL'
    year, subexpediente = resolve_saia_route_context(documento, route_code)
    file_path = Path(documento.ruta_archivo)
    config = get_saia_config()

    intento = _create_attempt(
        documento=documento,
        usuario_saia=config.username,
        request_metadata={
            'dry_run': dry_run,
            'confirmar_carga': confirmar_carga,
            'adjuntar_en_dry_run': adjuntar_en_dry_run,
            'asunto_saia': asunto_saia,
            'route_code': route_code,
            'route_description': validation.get('route_description', ''),
            'year': year,
            'subexpediente': subexpediente,
            'archivo': str(file_path),
            'nombre_archivo': documento.nombre_archivo,
            'validacion_previa': validation,
        },
    )

    _log(
        documento,
        'INFO' if validation['listo_para_saia'] else 'WARNING',
        'saia_validacion_previa',
        'Validacion previa para carga individual SAIA ejecutada.',
        {
            'intento_id': intento.id,
            'listo_para_saia': validation['listo_para_saia'],
            'errores': validation['errores'],
            'advertencias': validation['advertencias'],
        },
    )

    if not validation['listo_para_saia']:
        message = '; '.join(validation['errores'])
        _finish_attempt(
            intento,
            endpoint='',
            exitoso=False,
            respuesta={
                'modo': _attempt_mode(dry_run, confirmar_carga),
                'validacion_previa': validation,
                'pasos_completados': ['validacion_previa'],
            },
            mensaje_error=message,
        )
        raise SAIADocumentValidationError(message)

    try:
        config.validate_credentials()
    except SAIACredentialsError as exc:
        _finish_attempt(
            intento,
            endpoint='',
            exitoso=False,
            respuesta={
                'modo': _attempt_mode(dry_run, confirmar_carga),
                'validacion_previa': validation,
                'pasos_completados': ['validacion_previa'],
            },
            mensaje_error=str(exc),
        )
        _log(documento, 'ERROR', 'saia_error', str(exc), {'intento_id': intento.id})
        raise

    try:
        attempt_result = None
        log_result = None
        pending_logs = []
        completed_steps = ['validacion_previa']
        evidence = {}
        with SAIABrowserClient(config=config, headful=headful) as client:
            client.login()
            completed_steps.append('login')
            evidence['login'] = client.capture_screenshot(f'intento_{intento.id}_login_ok')
            _queue_log(pending_logs, 'INFO', 'saia_login_ok', 'Login SAIA ejecutado correctamente.', {'intento_id': intento.id, 'screenshot': evidence['login']})

            client.navigate_to_route(route_code, year=year, subexpediente=subexpediente)
            completed_steps.append(f'navegacion_{route_code.lower()}')
            evidence['navegacion'] = client.capture_screenshot(f'intento_{intento.id}_navegacion_{route_code.lower()}')
            _queue_log(
                pending_logs,
                'INFO',
                'saia_navegacion_ok',
                f'Navegacion SAIA completada para ruta {route_code}.',
                {
                    'intento_id': intento.id,
                    'screenshot': evidence['navegacion'],
                    'route_code': route_code,
                    'route_description': validation.get('route_description', ''),
                },
            )

            client.fill_document_form(
                asunto_saia=asunto_saia,
                file_path=file_path,
                attach_file=confirmar_carga or adjuntar_en_dry_run,
            )
            completed_steps.append('formulario')
            evidence['formulario'] = client.capture_screenshot(f'intento_{intento.id}_formulario')
            _queue_log(pending_logs, 'INFO', 'saia_formulario_ok', 'Formulario SAIA diligenciado.', {'intento_id': intento.id, 'asunto_saia': asunto_saia, 'screenshot': evidence['formulario']})

            if confirmar_carga or adjuntar_en_dry_run:
                completed_steps.append('adjunto')
                _queue_log(pending_logs, 'INFO', 'saia_adjunto_ok', 'Anexo PDF adjuntado en SAIA.', {'intento_id': intento.id, 'archivo': str(file_path)})

            if dry_run and not confirmar_carga:
                screenshot = client.dry_run_checkpoint()
                evidence['dry_run'] = screenshot
                attempt_result = {
                    'endpoint': client.current_url(),
                    'exitoso': False,
                    'respuesta': {
                        'modo': 'dry_run',
                        'mensaje': 'Flujo validado hasta antes de confirmar carga.',
                        'screenshot': screenshot,
                        'evidencia': evidence,
                        'pasos_completados': completed_steps,
                        'asunto_saia': asunto_saia,
                        'archivo_local': str(file_path),
                        'confirmacion_visual': False,
                    },
                    'mensaje_error': '',
                    'id_documento_saia': '',
                }
                log_result = {
                    'nivel': 'INFO',
                    'evento': 'saia_dry_run',
                    'mensaje': 'Dry-run SAIA completado.',
                    'detalle': {'screenshot': screenshot},
                }
            else:
                result = client.continue_and_confirm(expected_subject=asunto_saia)
                completed_steps.append('confirmacion')
                result['evidencia'] = evidence
                result['pasos_completados'] = completed_steps
                result['asunto_saia'] = asunto_saia
                result['archivo_local'] = str(file_path)
                visual_confirmed = bool(
                    result.get('subject_confirmed')
                    or result.get('document_detail_confirmed')
                    or result.get('document_list_confirmed')
                    or result.get('left_panel_confirmed')
                    or result.get('left_panel_v1_confirmed')
                    or result.get('anexo_confirmed')
                )
                result['confirmacion_visual'] = bool(result.get('success_detected') and visual_confirmed)
                attempt_result = {
                    'endpoint': result.get('url') or client.current_url(),
                    'exitoso': bool(result.get('success_detected') and visual_confirmed),
                    'respuesta': result,
                    'id_documento_saia': result.get('id_documento_saia', ''),
                    'mensaje_error': '' if result.get('success_detected') and visual_confirmed else 'SAIA no confirmo visualmente el documento cargado.',
                }
                if attempt_result['exitoso']:
                    _queue_log(pending_logs, 'INFO', 'saia_confirmacion_ok', 'SAIA confirmo visualmente el PEL cargado.', result)
                log_result = {
                    'nivel': 'INFO' if attempt_result['exitoso'] else 'WARNING',
                    'evento': 'saia_carga_documento',
                    'mensaje': (
                        'Carga SAIA ejecutada.'
                        if attempt_result['exitoso']
                        else 'Carga SAIA sin exito confirmado.'
                    ),
                    'detalle': result,
                }
        _flush_logs(documento, pending_logs)

        if attempt_result and attempt_result['exitoso']:
            documento.estado_proceso = 'CARGADO_SAIA'
            documento.save(update_fields=['estado_proceso', 'modificado'])
            try:
                local_ok_result = mark_document_file_ok(documento)
                attempt_result['respuesta']['marcacion_local_ok'] = local_ok_result
                _log(
                    documento,
                    'INFO',
                    'saia_marcado_ok',
                    'Archivo local marcado con OK despues de confirmacion SAIA.',
                    local_ok_result,
                )
            except SAIALocalFileError as exc:
                attempt_result['respuesta']['marcacion_local_ok'] = {
                    'renombrado': False,
                    'error': str(exc),
                }
                _log(
                    documento,
                    'ERROR',
                    'saia_archivo_local_ok_error',
                    str(exc),
                    {'intento_id': intento.id},
                )

        if attempt_result:
            _finish_attempt(
                intento,
                endpoint=attempt_result['endpoint'],
                exitoso=attempt_result['exitoso'],
                respuesta=attempt_result['respuesta'],
                mensaje_error=attempt_result['mensaje_error'],
                id_documento_saia=attempt_result['id_documento_saia'],
            )
        if log_result:
            _log(
                documento,
                log_result['nivel'],
                log_result['evento'],
                log_result['mensaje'],
                log_result['detalle'],
            )
        return intento
    except SAIAError as exc:
        _flush_logs(documento, locals().get('pending_logs', []))
        _finish_attempt(
            intento,
            endpoint='',
            exitoso=False,
            respuesta={'pasos_completados': locals().get('completed_steps', ['validacion_previa'])},
            mensaje_error=str(exc),
        )
        _log(documento, 'ERROR', 'saia_error', str(exc), {'intento_id': intento.id})
        raise
    except Exception as exc:
        _flush_logs(documento, locals().get('pending_logs', []))
        _finish_attempt(
            intento,
            endpoint='',
            exitoso=False,
            respuesta={'pasos_completados': locals().get('completed_steps', ['validacion_previa'])},
            mensaje_error=f'Error inesperado: {exc}',
        )
        _log(documento, 'ERROR', 'saia_error', str(exc), {'intento_id': intento.id})
        raise


def _get_document(documento_id):
    try:
        return DocumentoDigitalizado.objects.select_related('metadata', 'lote').get(pk=documento_id)
    except DocumentoDigitalizado.DoesNotExist as exc:
        raise SAIADocumentValidationError(f'No existe el documento {documento_id}.') from exc


def _create_attempt(documento, usuario_saia, request_metadata):
    next_attempt = IntentoCargaSAIA.objects.filter(documento=documento).count() + 1
    return IntentoCargaSAIA.objects.create(
        documento=documento,
        numero_intento=next_attempt,
        endpoint='',
        exitoso=False,
        usuario_saia=usuario_saia,
        request_metadata=request_metadata,
    )


def _finish_attempt(intento, endpoint, exitoso, respuesta, mensaje_error='', id_documento_saia=''):
    intento.endpoint = endpoint
    intento.exitoso = exitoso
    intento.id_documento_saia = id_documento_saia or intento.id_documento_saia
    intento.respuesta = _with_phase5_user_error(respuesta or {}, mensaje_error)
    intento.mensaje_error = mensaje_error
    intento.save(
        update_fields=[
            'endpoint',
            'exitoso',
            'id_documento_saia',
            'respuesta',
            'mensaje_error',
            'modificado',
        ]
    )


def _with_phase5_user_error(respuesta, mensaje_error):
    if not mensaje_error:
        return respuesta
    payload = build_phase5_error_message(mensaje_error, respuesta)
    if payload.get('codigo_error_usuario'):
        enriched = dict(respuesta)
        enriched['error_usuario_fase_5'] = payload
        return enriched
    return respuesta


def _queue_log(pending_logs, nivel, evento, mensaje, detalle):
    pending_logs.append(
        {
            'nivel': nivel,
            'evento': evento,
            'mensaje': mensaje,
            'detalle': detalle or {},
        }
    )


def _flush_logs(documento, pending_logs):
    while pending_logs:
        item = pending_logs.pop(0)
        _log(
            documento,
            item['nivel'],
            item['evento'],
            item['mensaje'],
            item['detalle'],
        )


def _log(documento, nivel, evento, mensaje, detalle):
    LogProcesoDocumental.objects.create(
        lote=documento.lote,
        documento=documento,
        nivel=nivel,
        evento=evento,
        mensaje=mensaje,
        detalle=detalle or {},
    )


def _attempt_mode(dry_run, confirmar_carga):
    if confirmar_carga:
        return 'confirmar_carga'
    if dry_run:
        return 'dry_run'
    return 'prueba'


