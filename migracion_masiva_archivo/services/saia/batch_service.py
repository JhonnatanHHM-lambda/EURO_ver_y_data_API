import os
import time

from migracion_masiva_archivo.models import (
    DocumentoDigitalizado,
    EjecucionCargaMasiva,
    IntentoCargaSAIA,
    LogProcesoDocumental,
    LoteDocumental,
)
from migracion_masiva_archivo.execution_control import control
from migracion_masiva_archivo.services.error_message_service import build_phase5_error_message
from migracion_masiva_archivo.services.file_name_service import get_documental_natural_sort_key
from migracion_masiva_archivo.services.saia.browser_client import SAIABrowserClient
from migracion_masiva_archivo.services.saia.config import get_saia_config
from migracion_masiva_archivo.services.saia.exceptions import (
    SAIADocumentValidationError,
    SAIAError,
    SAIALocalFileError,
    SAIALoginError,
    SAIASelectorError,
)
from migracion_masiva_archivo.services.saia.local_file_service import mark_document_file_ok
from migracion_masiva_archivo.services.saia.routes import resolve_saia_route_context
from migracion_masiva_archivo.services.saia.validation_service import validate_document_for_saia
from pathlib import Path


_HEARTBEAT_S = 300  # renovar sesion SAIA si pasan mas de 5 min sin actividad

_NETWORK_ERROR_SIGNALS = (
    'net::err_timed_out',
    'net::err_internet_disconnected',
    'net::err_name_not_resolved',
    'net::err_connection_refused',
    'net::err_connection_reset',
    'net::err_connection_failed',
    'err_timed_out',
    'page.goto: timeout',
)


def _es_error_red(exc):
    msg = str(exc).lower()
    return any(signal in msg for signal in _NETWORK_ERROR_SIGNALS)


def _ping_saia(client, config):
    """Verifica conectividad con SAIA con timeout corto. Retorna True si hay red."""
    try:
        client.page.goto(config.base_url, wait_until='domcontentloaded', timeout=10000)
        return True
    except Exception:
        return False


def _cancelacion_solicitada(ejecucion_id):
    """
    Verifica si se solicito cancelar la ejecucion activa. Cuando hay
    ejecucion_id, lee la bandera persistida en BD (unico canal valido para
    cruzar del proceso API al worker Celery que corre este batch). Sin
    ejecucion_id (uso desde management commands en un solo proceso) cae de
    vuelta al singleton en memoria por compatibilidad.
    """
    if ejecucion_id is None:
        return control.cancel_requested
    return bool(
        EjecucionCargaMasiva.objects
        .filter(pk=ejecucion_id, cancelacion_solicitada=True)
        .exists()
    )


def cargar_lote_saia(
    lote_id, limite=10, dry_run=False, headful=False,
    pausa_entre=3, max_reintentos=3, include_errors=False,
    max_reintentos_red=None, ejecucion_id=None,
):
    """
    Carga en SAIA todos los documentos listos de un lote.
    Abre una sola sesion de browser para todo el lote (un solo login).
    Retorna resumen con exitosos, fallidos, omitidos.
    """
    lote = _get_lote(lote_id)
    config = get_saia_config()
    config.validate_credentials()

    documentos = get_documentos_listos(lote, limite, include_errors=include_errors)
    resumen = {
        'lote_id': lote_id,
        'total': len(documentos),
        'exitosos': 0,
        'fallidos': 0,
        'omitidos': 0,
        'detalles': [],
    }

    _log_lote(lote, 'INFO', 'batch_inicio',
              f'Iniciando carga masiva SAIA: {len(documentos)} documentos '
              f'(dry_run={dry_run}, limite={limite}, max_reintentos={max_reintentos}).',
              {'limite': limite, 'dry_run': dry_run, 'headful': headful,
               'max_reintentos': max_reintentos, 'include_errors': include_errors})

    if not documentos:
        _log_lote(lote, 'INFO', 'batch_sin_documentos',
                  'No hay documentos listos para cargar en SAIA.', {})
        return resumen

    try:
        with SAIABrowserClient(config=config, headful=headful) as client:
            client.login()
            ultimo_login = time.time()
            _log_lote(lote, 'INFO', 'batch_login_ok', 'Login SAIA exitoso.', {})

            try:
                client.preflight_navigation()
                _log_lote(lote, 'INFO', 'batch_preflight_ok',
                          'Pre-flight SAIA exitoso: ruta de navegacion accesible.', {})
            except SAIASelectorError as exc:
                resumen['error_critico'] = str(exc)
                _log_lote(lote, 'ERROR', 'batch_preflight_fallido', str(exc),
                          {'documentos_sin_tocar': len(documentos)})
                return resumen

            for documento in documentos:
                # Fix #10: verificar cancelacion antes de cada documento
                if _cancelacion_solicitada(ejecucion_id):
                    _log_lote(lote, 'WARNING', 'batch_cancelado_usuario',
                              'Carga detenida por solicitud del usuario.', {})
                    resumen['cancelado'] = True
                    break

                control.doc_actual = documento.nombre_archivo
                resultado = _cargar_documento(
                    client, documento, dry_run, config, max_reintentos,
                    include_errored=include_errors,
                    max_reintentos_red=max_reintentos_red,
                )
                # A3 + Fix #7: capturar elapsed antes de resetear el timer.
                # El heartbeat se evalua DESPUES del documento, no antes, para que
                # keep_alive() no navegue justo cuando _cargar_documento va a
                # interactuar con el formulario.
                elapsed = time.time() - ultimo_login
                ultimo_login = time.time()
                resumen['detalles'].append(resultado)

                if resultado['exitoso']:
                    resumen['exitosos'] += 1
                elif resultado.get('omitido'):
                    resumen['omitidos'] += 1
                else:
                    resumen['fallidos'] += 1

                if resultado.get('detener_lote'):
                    _log_lote(lote, 'ERROR', 'batch_detenido',
                              'Lote detenido por error critico en SAIA.',
                              {'documento_id': documento.id, 'error': resultado.get('error', '')})
                    break

                # A3: heartbeat entre documentos (antes de la pausa), nunca
                # durante los reintentos internos de _cargar_documento.
                if elapsed >= _HEARTBEAT_S:
                    try:
                        relogged = client.keep_alive()
                        if relogged:
                            _log_lote(lote, 'INFO', 'batch_heartbeat_relogin',
                                      'Sesion SAIA renovada por heartbeat (relogin).', {})
                    except Exception as hb_exc:
                        _log_lote(lote, 'WARNING', 'batch_heartbeat_error',
                                  f'Error en heartbeat SAIA: {hb_exc}', {})

                if not dry_run and pausa_entre > 0:
                    time.sleep(pausa_entre)

    except KeyboardInterrupt:
        _log_lote(lote, 'WARNING', 'batch_interrumpido',
                  'Lote interrumpido por el usuario (Ctrl+C / cierre del script).', {})
        resumen['error_critico'] = 'Interrumpido por el usuario.'
        raise
    except SAIALoginError as exc:
        resumen['error_critico'] = str(exc)
        _log_lote(lote, 'ERROR', 'batch_login_error', str(exc), {})
    except SAIAError as exc:
        resumen['error_critico'] = str(exc)
        _log_lote(lote, 'ERROR', 'batch_error_critico', str(exc), {})

    # Contar docs VALIDADO/RELACIONADO que quedaron sin procesar (límite alcanzado)
    control.doc_actual = ''
    ya_cargados_ids = set(
        IntentoCargaSAIA.objects
        .filter(documento__lote=lote, exitoso=True)
        .values_list('documento_id', flat=True)
    )
    pendientes = (
        DocumentoDigitalizado.objects
        .filter(lote=lote, es_soportado=True, es_duplicado=False,
                estado_proceso__in=['VALIDADO', 'RELACIONADO'])
        .exclude(id__in=ya_cargados_ids)
        .count()
    )
    resumen['pendientes'] = pendientes

    _log_lote(
        lote, 'INFO', 'batch_fin',
        f'Carga masiva finalizada: {resumen["exitosos"]} exitosos, '
        f'{resumen["fallidos"]} fallidos, {resumen["omitidos"]} omitidos, '
        f'{pendientes} pendientes por limite.',
        {k: v for k, v in resumen.items() if k != 'detalles'},
    )
    return resumen


def _cargar_documento(client, documento, dry_run, config, max_reintentos=3, include_errored=False, max_reintentos_red=None):
    if max_reintentos_red is None:
        try:
            max_reintentos_red = max(int(os.getenv('SAIA_MAX_REINTENTOS_RED', '5')), 0)
        except (ValueError, TypeError):
            max_reintentos_red = 5
    validation = validate_document_for_saia(documento, include_errored=include_errored)
    if not validation['listo_para_saia']:
        errores = '; '.join(validation['errores'])
        _log(documento, 'WARNING', 'batch_doc_omitido',
             f'Documento omitido: {errores}', {
                 'errores': validation['errores'],
                 'errores_usuario': validation.get('errores_usuario', []),
             })
        return {
            'documento_id': documento.id,
            'asunto_saia': validation.get('asunto_saia', ''),
            'exitoso': False,
            'omitido': True,
            'error': errores,
            'errores_usuario': validation.get('errores_usuario', []),
        }

    asunto_saia = validation['asunto_saia']
    route_code = validation.get('route_code') or 'PEL'
    file_path = Path(documento.ruta_archivo)
    extended_timeout = _requires_extended_timeout(documento, validation)
    intento = _create_attempt(documento, config.username, {
        'dry_run': dry_run,
        'asunto_saia': asunto_saia,
        'route_code': route_code,
        'route_description': validation.get('route_description', ''),
        'archivo': str(file_path),
        'nombre_archivo': documento.nombre_archivo,
        'requiere_timeout_extendido': extended_timeout,
        'advertencias': validation.get('advertencias', []),
    })

    relogin_intentado = False
    reinicio_browser_intentado = False
    reintentos_restantes = max_reintentos
    reintentos_red_restantes = max_reintentos_red

    year, subexpediente = resolve_saia_route_context(documento, route_code)

    while True:
        try:
            if client.try_adicionar_sin_ruta(route_code, year, subexpediente):
                _log(documento, 'INFO', 'saia_ruta_reutilizada',
                     f'Ruta SAIA reutilizada (sin home): {route_code}', {
                         'intento_id': intento.id,
                         'route_code': route_code,
                     })
            else:
                client.navigate_to_route(route_code, year=year, subexpediente=subexpediente)
                _log(documento, 'INFO', 'saia_ruta_seleccionada',
                     f'Ruta SAIA seleccionada: {route_code}', {
                         'intento_id': intento.id,
                         'route_code': route_code,
                         'route_description': validation.get('route_description', ''),
                     })
            client.fill_document_form(
                asunto_saia=asunto_saia,
                file_path=file_path,
                attach_file=not dry_run,
                extended_timeout=extended_timeout,
            )

            if dry_run:
                screenshot = client.dry_run_checkpoint()
                _finish_attempt(intento, endpoint=client.current_url(), exitoso=False,
                                respuesta={'modo': 'dry_run', 'screenshot': screenshot})
                _log(documento, 'INFO', 'batch_dry_run',
                     f'Dry-run validado: {asunto_saia}', {'screenshot': screenshot})
                return {
                    'documento_id': documento.id,
                    'asunto_saia': asunto_saia,
                    'exitoso': False,
                    'omitido': True,
                    'intento_id': intento.id,
                }

            result = client.continue_and_confirm(
                expected_subject=asunto_saia,
                extended_timeout=extended_timeout,
            )
            exitoso = bool(result.get('success_detected'))
            ambiguo = bool(result.get('ambiguous'))

            if exitoso:
                nuevo_estado = 'CARGADO_SAIA'
                mensaje_error = ''
            elif ambiguo:
                nuevo_estado = 'REQUIERE_REVISION'
                mensaje_error = (
                    'SAIA no emitio confirmacion clara. '
                    'Verifique manualmente si el documento fue cargado antes de reintentar.'
                )
            else:
                nuevo_estado = 'ERROR_SAIA'
                mensaje_error = 'SAIA no confirmo carga exitosa.'

            _finish_attempt(
                intento,
                endpoint=result.get('url') or client.current_url(),
                exitoso=exitoso,
                respuesta=result,
                id_documento_saia=result.get('id_documento_saia', ''),
                mensaje_error=mensaje_error,
            )
            _actualizar_estado(documento, nuevo_estado)

            if exitoso:
                client.mark_route_navigated(route_code, year, subexpediente)
                try:
                    mark_document_file_ok(documento)
                except SAIALocalFileError as exc:
                    _log(documento, 'WARNING', 'batch_ok_marcacion_error', str(exc), {})
                _log(documento, 'INFO', 'batch_cargado_ok',
                     f'Cargado en SAIA: {asunto_saia}', result)
            elif ambiguo:
                client.clear_route_state()
                _log(documento, 'WARNING', 'batch_ambiguo',
                     f'Resultado ambiguo SAIA: {asunto_saia} — verificacion manual requerida', result)
            else:
                client.clear_route_state()
                _log(documento, 'WARNING', 'batch_sin_exito',
                     f'Sin exito SAIA: {asunto_saia}', result)

            return {
                'documento_id': documento.id,
                'asunto_saia': asunto_saia,
                'exitoso': exitoso,
                'ambiguo': ambiguo,
                'intento_id': intento.id,
                'id_documento_saia': result.get('id_documento_saia', ''),
            }

        except SAIALoginError as exc:
            _finish_attempt(intento, endpoint='', exitoso=False, respuesta={},
                            mensaje_error=str(exc))
            _log(documento, 'ERROR', 'batch_login_perdido', str(exc), {})
            return {
                'documento_id': documento.id,
                'asunto_saia': asunto_saia,
                'exitoso': False,
                'error': str(exc),
                'detener_lote': True,
                'intento_id': intento.id,
            }

        except SAIASelectorError as exc:
            # Prioridad 1a: browser crasheado → reiniciar proceso completo
            if not reinicio_browser_intentado and not client.is_browser_alive():
                reinicio_browser_intentado = True
                relogin_intentado = True
                _log(documento, 'WARNING', 'batch_browser_crash',
                     f'Browser Chromium caido al procesar {asunto_saia}. Reiniciando...', {})
                try:
                    client.restart_browser()
                    _log(documento, 'INFO', 'batch_browser_reiniciado',
                         'Browser reiniciado y sesion SAIA restaurada.', {})
                    continue
                except Exception as restart_exc:
                    _finish_attempt(intento, endpoint='', exitoso=False, respuesta={},
                                    mensaje_error=str(restart_exc))
                    _log(documento, 'ERROR', 'batch_browser_reinicio_fallido', str(restart_exc), {})
                    return {
                        'documento_id': documento.id,
                        'asunto_saia': asunto_saia,
                        'exitoso': False,
                        'error': str(restart_exc),
                        'detener_lote': True,
                        'intento_id': intento.id,
                    }
            # Prioridad 1b: sesion expirada → relogin (no consume reintento)
            if not relogin_intentado and not client.is_session_alive():
                relogin_intentado = True
                _log(documento, 'WARNING', 'batch_sesion_expirada',
                     f'Sesion SAIA expirada al procesar {asunto_saia}. Reconectando...', {})
                try:
                    client.relogin()
                    _log(documento, 'INFO', 'batch_reconexion_ok',
                         'Reconexion SAIA exitosa. Reintentando documento.', {})
                    continue
                except SAIALoginError as login_exc:
                    _finish_attempt(intento, endpoint='', exitoso=False, respuesta={},
                                    mensaje_error=str(login_exc))
                    _log(documento, 'ERROR', 'batch_reconexion_fallida', str(login_exc), {})
                    return {
                        'documento_id': documento.id,
                        'asunto_saia': asunto_saia,
                        'exitoso': False,
                        'error': str(login_exc),
                        'detener_lote': True,
                        'intento_id': intento.id,
                    }
            # Prioridad 2: reintentar si quedan intentos
            if reintentos_restantes > 0:
                num = max_reintentos - reintentos_restantes + 1
                reintentos_restantes -= 1
                _log(documento, 'WARNING', 'batch_reintento',
                     f'Reintento {num}/{max_reintentos} para {asunto_saia}: {exc}',
                     {'intento_num': num, 'max_reintentos': max_reintentos})
                client.clear_route_state()
                time.sleep(5)
                continue
            screenshot = getattr(client, 'last_screenshot', '')
            _finish_attempt(intento, endpoint=client.current_url(), exitoso=False,
                            respuesta={'screenshot': screenshot}, mensaje_error=str(exc))
            _log(documento, 'ERROR', 'batch_selector_error', str(exc),
                 {'screenshot': screenshot, 'intento_id': intento.id})
            return {
                'documento_id': documento.id,
                'asunto_saia': asunto_saia,
                'exitoso': False,
                'error': str(exc),
                'intento_id': intento.id,
            }

        except SAIAError as exc:
            if reintentos_restantes > 0:
                num = max_reintentos - reintentos_restantes + 1
                reintentos_restantes -= 1
                _log(documento, 'WARNING', 'batch_reintento',
                     f'Reintento {num}/{max_reintentos} para {asunto_saia}: {exc}',
                     {'intento_num': num, 'max_reintentos': max_reintentos})
                client.clear_route_state()
                time.sleep(5)
                continue
            _finish_attempt(intento, endpoint='', exitoso=False, respuesta={},
                            mensaje_error=str(exc))
            _log(documento, 'ERROR', 'batch_saia_error', str(exc),
                 {'intento_id': intento.id})
            return {
                'documento_id': documento.id,
                'asunto_saia': asunto_saia,
                'exitoso': False,
                'error': str(exc),
                'intento_id': intento.id,
            }

        except Exception as exc:
            # Prioridad 0: error de red — esperar recuperacion sin consumir reintentos de logica
            if _es_error_red(exc) and reintentos_red_restantes > 0:
                num_red = max_reintentos_red - reintentos_red_restantes + 1
                reintentos_red_restantes -= 1
                espera_s = min(30 * (2 ** (num_red - 1)), 120)
                _log(documento, 'WARNING', 'batch_espera_red',
                     f'Error de red (intento {num_red}/{max_reintentos_red}) para {asunto_saia}. '
                     f'Esperando {espera_s}s para recuperacion...',
                     {'espera_s': espera_s, 'intento_red': num_red,
                      'max_reintentos_red': max_reintentos_red, 'error': str(exc)[:200]})
                time.sleep(espera_s)
                if not _ping_saia(client, config):
                    _log(documento, 'WARNING', 'batch_red_no_recuperada',
                         f'Red aun no disponible tras {espera_s}s. Continuando espera.',
                         {'reintentos_red_restantes': reintentos_red_restantes})
                    continue
                _log(documento, 'INFO', 'batch_red_restaurada',
                     'Conectividad con SAIA restaurada. Reiniciando browser para conexiones limpias.', {})
                try:
                    client.restart_browser()
                    relogin_intentado = False
                    reinicio_browser_intentado = False
                    _log(documento, 'INFO', 'batch_browser_reiniciado_red',
                         'Browser reiniciado tras recuperacion de red. Reintentando documento.', {})
                except Exception as restart_exc:
                    _finish_attempt(intento, endpoint='', exitoso=False, respuesta={},
                                    mensaje_error=str(restart_exc))
                    _log(documento, 'ERROR', 'batch_browser_reinicio_fallido_red', str(restart_exc), {})
                    return {
                        'documento_id': documento.id,
                        'asunto_saia': asunto_saia,
                        'exitoso': False,
                        'error': str(restart_exc),
                        'detener_lote': True,
                        'intento_id': intento.id,
                    }
                continue
            # Prioridad 1a: browser crasheado → reiniciar proceso completo
            if not reinicio_browser_intentado and not client.is_browser_alive():
                reinicio_browser_intentado = True
                relogin_intentado = True
                _log(documento, 'WARNING', 'batch_browser_crash',
                     f'Browser Chromium caido al procesar {asunto_saia}: {exc}. Reiniciando...', {})
                try:
                    client.restart_browser()
                    _log(documento, 'INFO', 'batch_browser_reiniciado',
                         'Browser reiniciado y sesion SAIA restaurada.', {})
                    continue
                except Exception as restart_exc:
                    _finish_attempt(intento, endpoint='', exitoso=False, respuesta={},
                                    mensaje_error=str(restart_exc))
                    _log(documento, 'ERROR', 'batch_browser_reinicio_fallido', str(restart_exc), {})
                    return {
                        'documento_id': documento.id,
                        'asunto_saia': asunto_saia,
                        'exitoso': False,
                        'error': str(restart_exc),
                        'detener_lote': True,
                        'intento_id': intento.id,
                    }
            # Prioridad 1b: sesion expirada → relogin (no consume reintento)
            if not relogin_intentado and not client.is_session_alive():
                relogin_intentado = True
                _log(documento, 'WARNING', 'batch_sesion_expirada',
                     f'Sesion SAIA interrumpida al procesar {asunto_saia}: {exc}. Reconectando...', {})
                try:
                    client.relogin()
                    _log(documento, 'INFO', 'batch_reconexion_ok',
                         'Reconexion SAIA exitosa. Reintentando documento.', {})
                    continue
                except SAIALoginError as login_exc:
                    _finish_attempt(intento, endpoint='', exitoso=False, respuesta={},
                                    mensaje_error=str(login_exc))
                    _log(documento, 'ERROR', 'batch_reconexion_fallida', str(login_exc), {})
                    return {
                        'documento_id': documento.id,
                        'asunto_saia': asunto_saia,
                        'exitoso': False,
                        'error': str(login_exc),
                        'detener_lote': True,
                        'intento_id': intento.id,
                    }
            # Prioridad 2: reintentar si quedan intentos
            if reintentos_restantes > 0:
                num = max_reintentos - reintentos_restantes + 1
                reintentos_restantes -= 1
                _log(documento, 'WARNING', 'batch_reintento',
                     f'Reintento {num}/{max_reintentos} para {asunto_saia}: {exc}',
                     {'intento_num': num, 'max_reintentos': max_reintentos})
                time.sleep(5)
                continue
            _finish_attempt(intento, endpoint='', exitoso=False, respuesta={},
                            mensaje_error=f'Error inesperado: {exc}')
            _log(documento, 'ERROR', 'batch_error_inesperado', str(exc),
                 {'intento_id': intento.id})
            return {
                'documento_id': documento.id,
                'asunto_saia': asunto_saia,
                'exitoso': False,
                'error': str(exc),
                'intento_id': intento.id,
            }


def _get_lote(lote_id):
    try:
        return LoteDocumental.objects.get(pk=lote_id)
    except LoteDocumental.DoesNotExist as exc:
        raise SAIADocumentValidationError(f'No existe el lote {lote_id}.') from exc


def get_documentos_listos(lote, limite, include_errors=False):
    ya_cargados = (
        IntentoCargaSAIA.objects
        .filter(documento__lote=lote, exitoso=True)
        .values_list('documento_id', flat=True)
    )
    estados = ['VALIDADO', 'RELACIONADO']
    if include_errors:
        # REQUIERE_REVISION incluye documentos con resultado ambiguo en SAIA
        # (carga no confirmada). El analista debe verificar en SAIA antes de reintentar.
        estados.extend(['ERROR_SAIA', 'REQUIERE_REVISION'])
    qs = (
        DocumentoDigitalizado.objects
        .select_related('metadata')
        .filter(
            lote=lote,
            es_soportado=True,
            es_duplicado=False,
            estado_proceso__in=estados,
        )
        .exclude(id__in=list(ya_cargados))
        .exclude(metadata__isnull=True)
        .exclude(metadata__requiere_revision=True)
        .exclude(nombre_archivo__icontains=' ok')
        .order_by('id')
    )
    docs_list = list(qs)
    # Calcular año dominante CCA/CCV para documentos que no tienen cc_año en datos_pel.
    # Sucede cuando el PDF no contiene el año en el texto y la extracción falló parcialmente.
    # Se usa el año mínimo encontrado en otros documentos del mismo lote.
    _cc_years = []
    for _d in docs_list:
        _meta = getattr(_d, 'metadata', None)
        _dp = (getattr(_meta, 'datos_pel', None) or {}) if _meta else {}
        _yr = _dp.get('cc_año')
        if _yr:
            _cc_years.append(_yr)
    _dominant_cc_year = min(_cc_years) if _cc_years else None

    _MESES_NUM_CTX = {
        'ENERO': 1, 'FEBRERO': 2, 'MARZO': 3, 'ABRIL': 4,
        'MAYO': 5, 'JUNIO': 6, 'JULIO': 7, 'AGOSTO': 8,
        'SEPTIEMBRE': 9, 'OCTUBRE': 10, 'NOVIEMBRE': 11, 'DICIEMBRE': 12,
    }

    def _sort_key_with_context(doc):
        key = _sort_key_documento_lote(doc)
        if key[0] == 9999 and _dominant_cc_year is not None:
            # Si el nombre del archivo es un mes español, usar su número correcto
            # para que ENERO(1) < FEBRERO(2) < ... junto a los demás documentos del año.
            nombre = getattr(doc, 'nombre_archivo', '') or ''
            stem = os.path.splitext(nombre)[0].upper().strip()
            mes_num = _MESES_NUM_CTX.get(stem)
            if mes_num is not None:
                return (_dominant_cc_year, mes_num, key[2])
            return (_dominant_cc_year, key[1], key[2])
        return key

    documentos = sorted(docs_list, key=_sort_key_with_context)
    if limite:
        documentos = documentos[:limite]
    return documentos


def _sort_key_documento_lote(documento):
    """
    Clave de ordenamiento unificada para documentos de un lote.
    - Bancolombia: ordena por bancolombia_año + bancolombia_mes_num.
    - CCA/CCV: ordena por cc_año + cc_mes_num.
    - Resto: ordenamiento natural por nombre de archivo (último, 9999/99).
    """
    metadata = getattr(documento, 'metadata', None)
    datos_pel = (getattr(metadata, 'datos_pel', None) or {}) if metadata else {}
    natural = get_documental_natural_sort_key(documento.nombre_archivo)

    # Bancolombia
    bco_year = datos_pel.get('bancolombia_año')
    bco_month = datos_pel.get('bancolombia_mes_num')
    if bco_month is not None:
        if bco_year is None:
            # Páginas de continuación pueden tener mes pero sin año en datos_pel.
            # Intentar recuperarlo desde el nombre del sub-expediente.
            bco_sub = str(datos_pel.get('bancolombia_subexpediente') or '')
            import re as _re_sort
            _ym = _re_sort.search(r'\b(20\d{2})\b', bco_sub)
            bco_year = int(_ym.group(1)) if _ym else None
        if bco_year is not None:
            return (bco_year, bco_month, natural)

    # Cartera Colectiva (CCA / CCV)
    cc_year = datos_pel.get('cc_año')
    cc_month = datos_pel.get('cc_mes_num')
    if cc_year is not None and cc_month is not None:
        return (cc_year, cc_month, natural)

    # Fallback CCA/CCV: nombre de archivo = nombre de mes, año desde ruta de carpeta.
    # Se activa cuando cc_año/cc_mes_num están ausentes pero el nombre del archivo ES un mes.
    # No requiere "CARTERA" en la ruta (el nombre de la carpeta puede tener errores tipográficos).
    _CC_MESES_SORT = {
        'ENERO': 1, 'FEBRERO': 2, 'MARZO': 3, 'ABRIL': 4,
        'MAYO': 5, 'JUNIO': 6, 'JULIO': 7, 'AGOSTO': 8,
        'SEPTIEMBRE': 9, 'OCTUBRE': 10, 'NOVIEMBRE': 11, 'DICIEMBRE': 12,
    }
    nombre = getattr(documento, 'nombre_archivo', '') or ''
    stem = os.path.splitext(nombre)[0].upper().strip()
    ruta = getattr(documento, 'ruta_archivo', '') or ''
    if stem in _CC_MESES_SORT and datos_pel.get('bancolombia_mes_num') is None:
        import re as _re_sort2
        m_year = _re_sort2.search(r'\b(20\d{2})\b', ruta)
        fb_year = int(m_year.group(1)) if m_year else 9999
        return (fb_year, _CC_MESES_SORT[stem], natural)

    # Conciliaciones bancarias con año+mes en datos_pel (orden de mes)
    _CONCILIACION_MES_FIELDS = [
        ('corbanca_año', 'corbanca_mes_num'),
        ('colpatria_año', 'colpatria_mes_num'),
        ('correval_año', 'correval_mes_num'),
        ('corficolombiana_año', 'corficolombiana_mes_num'),
        ('bbva_año', 'bbva_mes_num'),
        ('davivienda_año', 'davivienda_mes_num'),
        ('bogota_año', 'bogota_mes_num'),
        ('retencion_ica_a?o', 'retencion_ica_mes_num'),
        ('ecb_a\u00f1o', 'ecb_numero'),
        ('egc_a\u00f1o', 'egc_numero'),
    ]
    for _año_field, _mes_field in _CONCILIACION_MES_FIELDS:
        _y = datos_pel.get(_año_field)
        _m = datos_pel.get(_mes_field)
        if _y is not None and _m is not None:
            return (_y, _m, natural)

    return (9999, 99, natural)


def _extract_bancolombia_subexpediente(documento):
    """Retorna el sub-expediente Bancolombia almacenado en datos_pel, o None."""
    metadata = getattr(documento, 'metadata', None)
    if not metadata:
        return None
    datos_pel = getattr(metadata, 'datos_pel', None) or {}
    return datos_pel.get('bancolombia_subexpediente') or None


def _extract_document_year(documento):
    """Extrae el año del documento para rutas con paso de año dinámico (ej. EGE).

    Orden de prioridad:
    1. fecha_documento del modelo (más fiable).
    2. Carpeta inmediata del archivo si su nombre es un año de 4 dígitos.
    3. Cualquier parte de la ruta que sea un año entre 2000 y 2099.
    """
    fecha = getattr(documento, 'fecha_documento', None)
    if fecha and hasattr(fecha, 'year'):
        return fecha.year

    try:
        parts = Path(documento.ruta_archivo).parts
        # Carpeta padre directa primero
        for part in reversed(parts):
            if part.isdigit() and len(part) == 4 and 2000 <= int(part) <= 2099:
                return int(part)
    except Exception:
        pass
    return None


def _requires_extended_timeout(documento, validation=None):
    validation = validation or {}
    if any('PDF_PESADO_SAIA' in str(warning) for warning in validation.get('advertencias', [])):
        return True
    try:
        file_size = Path(documento.ruta_archivo).stat().st_size
    except OSError:
        file_size = getattr(documento, 'peso_bytes', 0) or 0
    max_mb = _saia_max_file_mb()
    return file_size > max_mb * 1024 * 1024


def _saia_max_file_mb():
    try:
        return max(int(os.getenv('SAIA_MAX_FILE_MB', '50')), 1)
    except (TypeError, ValueError):
        return 50


def _actualizar_estado(documento, nuevo_estado):
    documento.estado_proceso = nuevo_estado
    documento.save(update_fields=['estado_proceso', 'modificado'])


def _create_attempt(documento, usuario_saia, request_metadata):
    next_num = IntentoCargaSAIA.objects.filter(documento=documento).count() + 1
    meta = dict(request_metadata)
    return IntentoCargaSAIA.objects.create(
        documento=documento,
        numero_intento=next_num,
        endpoint='',
        exitoso=False,
        usuario_saia=usuario_saia,
        request_metadata=meta,
    )


def _finish_attempt(intento, endpoint, exitoso, respuesta,
                    mensaje_error='', id_documento_saia=''):
    intento.endpoint = endpoint
    intento.exitoso = exitoso
    intento.id_documento_saia = id_documento_saia or intento.id_documento_saia
    intento.respuesta = _with_phase5_user_error(respuesta or {}, mensaje_error)
    intento.mensaje_error = mensaje_error
    intento.save(update_fields=[
        'endpoint', 'exitoso', 'id_documento_saia',
        'respuesta', 'mensaje_error', 'modificado',
    ])


def _with_phase5_user_error(respuesta, mensaje_error):
    if not mensaje_error:
        return respuesta
    payload = build_phase5_error_message(mensaje_error, respuesta)
    if payload.get('codigo_error_usuario'):
        enriched = dict(respuesta)
        enriched['error_usuario_fase_5'] = payload
        return enriched
    return respuesta


def _log(documento, nivel, evento, mensaje, detalle):
    LogProcesoDocumental.objects.create(
        lote=documento.lote,
        documento=documento,
        nivel=nivel,
        evento=evento,
        mensaje=mensaje,
        detalle=detalle or {},
    )


def _log_lote(lote, nivel, evento, mensaje, detalle):
    LogProcesoDocumental.objects.create(
        lote=lote,
        nivel=nivel,
        evento=evento,
        mensaje=mensaje,
        detalle=detalle or {},
    )


