import os
import re
from pathlib import Path

from migracion_masiva_archivo.execution_control import control
from migracion_masiva_archivo.models import DocumentoDigitalizado, IntentoCargaSAIA
from migracion_masiva_archivo.services.file_name_service import get_documental_natural_sort_key
from migracion_masiva_archivo.services.error_message_service import build_phase4_error_message
from migracion_masiva_archivo.services.saia.exceptions import SAIANormalizationError
from migracion_masiva_archivo.services.saia.historical_service import find_historical_saia_evidence
from migracion_masiva_archivo.services.saia.normalization import normalize_saia_subject
from migracion_masiva_archivo.services.saia.routes import detect_saia_route, get_saia_route_config


ALLOWED_SAIA_STATES = {'VALIDADO', 'RELACIONADO'}
# Estados que permiten que un soporte sea subido o ya fue subido a SAIA.
# Si un soporte del principal no está en alguno de estos estados, el principal
# queda bloqueado para evitar cargar un expediente incompleto en SAIA.
_ESTADOS_VALIDOS_SOPORTE = frozenset({'VALIDADO', 'RELACIONADO', 'CARGADO_SAIA'})
OK_FILENAME_RE = re.compile(r'(^|[\s_\-])OK([\s_\-\.]|$)', re.IGNORECASE)
SUBJECT_BASED_ROUTE_CODES = {
    'BANCOLOMBIA', 'CCA', 'CCV',
    'CORBANCA', 'COLPATRIA',
    'CORREVAL', 'CORFICOLOMBIANA', 'BBVA', 'DAVIVIENDA', 'BOGOTA',
    'RICA', 'ECB', 'EGC', 'EGE',
}


def validate_document_for_saia(documento, include_errored=False):
    errors = []
    warnings = []
    asunto_saia = build_saia_subject_from_filename(documento.nombre_archivo)
    asunto_nombre = asunto_saia
    metadata = getattr(documento, 'metadata', None)
    file_path = Path(documento.ruta_archivo)
    route_code = detect_saia_route(documento, metadata)
    route_config = get_saia_route_config(route_code)

    if route_code in ('CCA', 'CCV', 'RICA', 'ECB', 'EGC', 'EGE') and metadata:
        _datos_cc = getattr(metadata, 'datos_pel', None) or {}
        if _datos_cc.get('asunto_saia'):
            asunto_saia = _datos_cc['asunto_saia']

    if not file_path.exists():
        errors.append(f'Archivo fisico no existe: {documento.ruta_archivo}')
    else:
        if file_path.suffix.lower() != '.pdf':
            errors.append('El archivo para SAIA debe ser PDF')
        try:
            size = file_path.stat().st_size
            if size <= 0:
                errors.append('El archivo PDF esta vacio')
            else:
                max_bytes = _max_pdf_bytes()
                if size > max_bytes:
                    warnings.append(
                        f'PDF_PESADO_SAIA: el archivo pesa '
                        f'({size / (1024 * 1024):.1f} MB > {max_bytes // (1024 * 1024)} MB). '
                        'La carga puede tardar mas, pero no bloquea SAIA.'
                    )
        except OSError as exc:
            errors.append(f'No se pudo leer el tamano del archivo: {exc}')
        if not _can_read_file(file_path):
            errors.append('El archivo parece estar bloqueado o no se puede leer')
        elif file_path.suffix.lower() == '.pdf':
            if not _is_valid_pdf(file_path):
                errors.append('El archivo PDF esta corrupto o danado (encabezado invalido)')
            else:
                # Gap A: verificar contrasena y paginas con pypdf
                errors.extend(_pdf_content_errors(file_path))

    if not documento.es_soportado:
        errors.append('Formato no soportado')

    if documento.es_duplicado:
        errors.append('Documento duplicado dentro del lote')

    if has_ok_marker(documento.nombre_archivo):
        errors.append('Archivo omitido porque el nombre contiene OK')

    if not route_code:
        errors.append('No se pudo determinar la ruta SAIA para este documento')
    elif not route_config:
        errors.append(f'La ruta SAIA {route_code} no esta configurada')

    # REQUIERE_REVISION: resultado ambiguo en intento anterior — se permite reintentar
    estados_permitidos = (ALLOWED_SAIA_STATES | {'ERROR_SAIA', 'REQUIERE_REVISION'}) if include_errored else ALLOWED_SAIA_STATES
    if documento.estado_proceso not in estados_permitidos:
        errors.append(f'Estado no permitido para SAIA: {documento.estado_proceso}')

    if not metadata:
        errors.append('Documento sin metadata extraida')
    else:
        datos_pel = metadata.datos_pel or {}
        # Discrepancia consecutivo bloqueante (persistida en datos_pel por Fase 2).
        # Se reporta con mensaje específico y se persiste REQUIERE_REVISION para que
        # el documento aparezca en Revisión Manual, no como "omitido".
        if datos_pel.get('mismatch_bloquea'):
            ocr_orig = datos_pel.get('ocr_consecutivo_mismatch', '')
            mismatch_msg = (
                'Discrepancia consecutivo bloqueante: el contenido del PDF indica '
                + (f'"{ocr_orig}"' if ocr_orig else 'un consecutivo diferente')
                + ' pero el nombre del archivo indica otro. '
                'No se carga a SAIA. Verificar si el archivo esta mal nombrado o si el OCR fallo.'
            )
            errors.append(mismatch_msg)
            _mark_document_mismatch_review(documento, mismatch_msg)
        elif metadata.requiere_revision:
            errors.append('Metadata marcada como requiere_revision')
        if route_code in SUBJECT_BASED_ROUTE_CODES:
            if not (metadata.consecutivo or datos_pel.get('identidad_documental') or asunto_saia):
                errors.append('Metadata sin asunto documental para validar contra SAIA')
            if route_code == 'BBVA':
                if not datos_pel.get('bbva_subexpediente'):
                    errors.append('BBVA sin carpeta/subexpediente SAIA detectado desde la ruta del archivo')
                if not datos_pel.get('bbva_a\u00f1o'):
                    errors.append('BBVA sin anio documental detectado')
                if not datos_pel.get('bbva_mes_num'):
                    errors.append('BBVA sin mes documental detectado')
                if datos_pel.get('bbva_titulo_ok') is False:
                    errors.append('BBVA: el PDF no confirma el titulo CONCILIACION BANCARIA')
                if datos_pel.get('bbva_banco_ok') is False:
                    errors.append('BBVA: el PDF no confirma BANCO BBVA')
                for inconsistencia in datos_pel.get('bbva_inconsistencias') or []:
                    errors.append(f'BBVA inconsistente: {inconsistencia}')
            if route_code == 'DAVIVIENDA':
                if not datos_pel.get('davivienda_subexpediente'):
                    errors.append('Davivienda sin carpeta/subexpediente SAIA detectado desde la ruta del archivo')
                if not datos_pel.get('davivienda_a\u00f1o'):
                    errors.append('Davivienda sin anio documental detectado')
                if not datos_pel.get('davivienda_mes_num'):
                    errors.append('Davivienda sin mes documental detectado')
                if datos_pel.get('davivienda_titulo_ok') is False:
                    errors.append('Davivienda: el PDF no confirma el titulo CONCILIACION BANCARIA')
                if datos_pel.get('davivienda_banco_ok') is False:
                    errors.append('Davivienda: el PDF no confirma BANCO DAVIVIENDA')
                for inconsistencia in datos_pel.get('davivienda_inconsistencias') or []:
                    errors.append(f'Davivienda inconsistente: {inconsistencia}')
            if route_code == 'BOGOTA':
                if not datos_pel.get('bogota_subexpediente'):
                    errors.append('Banco de Bogota sin carpeta/subexpediente SAIA detectado desde la ruta del archivo')
                if not datos_pel.get('bogota_a\u00f1o'):
                    errors.append('Banco de Bogota sin anio documental detectado')
                if not datos_pel.get('bogota_mes_num'):
                    errors.append('Banco de Bogota sin mes documental detectado')
                if datos_pel.get('bogota_titulo_ok') is False:
                    errors.append('Banco de Bogota: el PDF no confirma CONCILIACION BANCARIA o CREDITO ROTATIVO')
                if datos_pel.get('bogota_banco_ok') is False:
                    errors.append('Banco de Bogota: el PDF no confirma BANCO DE BOGOTA')
                for inconsistencia in datos_pel.get('bogota_inconsistencias') or []:
                    errors.append(f'Banco de Bogota inconsistente: {inconsistencia}')
            if route_code == 'RICA':
                if not datos_pel.get('retencion_ica_a\u00f1o'):
                    errors.append('Retencion ICA sin anio documental detectado')
                if datos_pel.get('retencion_ica_titulo_ok') is False:
                    errors.append('Retencion ICA: el PDF no confirma DECLARACION BIMESTRAL')
                for inconsistencia in datos_pel.get('retencion_ica_inconsistencias') or []:
                    errors.append(f'Retencion ICA inconsistente: {inconsistencia}')
            if route_code == 'EGC':
                if not datos_pel.get('egc_a\u00f1o'):
                    errors.append('EGC sin anio documental detectado')
                if not datos_pel.get('egc_numero'):
                    errors.append('EGC sin numero/consecutivo detectado')
                if datos_pel.get('egc_titulo_ok') is False:
                    errors.append('EGC: el PDF no confirma EGRESOS CHEQUES')
                for inconsistencia in datos_pel.get('egc_inconsistencias') or []:
                    errors.append(f'EGC inconsistente: {inconsistencia}')
            if route_code == 'ECB':
                if not datos_pel.get('ecb_a\u00f1o'):
                    errors.append('ECB sin anio documental detectado')
                if not datos_pel.get('ecb_numero'):
                    errors.append('ECB sin numero/consecutivo detectado')
                if datos_pel.get('ecb_titulo_ok') is False:
                    errors.append('ECB: el PDF no confirma EGRESOS CHEQUES BANCOLOMBIA')
                for inconsistencia in datos_pel.get('ecb_inconsistencias') or []:
                    errors.append(f'ECB inconsistente: {inconsistencia}')
            if route_code == 'EGE':
                if not datos_pel.get('ege_año'):
                    errors.append('EGE sin anio documental detectado')
                if not datos_pel.get('ege_numero'):
                    errors.append('EGE sin numero/consecutivo detectado')
                if datos_pel.get('ege_titulo_ok') is False:
                    errors.append('EGE: el PDF no confirma EGRESOS EFECTIVO')
                for inconsistencia in datos_pel.get('ege_inconsistencias') or []:
                    errors.append(f'EGE inconsistente: {inconsistencia}')
        elif not metadata.consecutivo and not datos_pel.get('identidad_documental'):
            errors.append('Metadata sin consecutivo para validar contra SAIA')
        else:
            try:
                consecutivo_metadata = normalize_saia_subject(
                    metadata.consecutivo or datos_pel.get('identidad_documental') or ''
                )
                consecutivo_nombre = normalize_saia_subject(documento.nombre_archivo)
                if consecutivo_metadata and consecutivo_nombre and consecutivo_metadata != consecutivo_nombre:
                    if not consecutivo_nombre.startswith(consecutivo_metadata + ' '):
                        errors.append(
                            f'Consecutivo del documento no coincide con nombre: '
                            f'{consecutivo_metadata} != {consecutivo_nombre}'
                        )
            except SAIANormalizationError as exc:
                errors.append(str(exc))

    # A2: bloquear el principal si alguno de sus soportes está en estado roto.
    # Un soporte en REQUIERE_REVISION o ERROR_SAIA no puede subirse a SAIA,
    # dejando el expediente incompleto.
    relaciones = documento.relaciones_principales.select_related('documento_relacionado').all()
    rotos = [
        f'{r.documento_relacionado.nombre_archivo} ({r.documento_relacionado.estado_proceso})'
        for r in relaciones
        if r.documento_relacionado.estado_proceso not in _ESTADOS_VALIDOS_SOPORTE
    ]
    if rotos:
        errors.append(
            'El documento tiene soportes en estado invalido para SAIA: '
            + ', '.join(rotos[:3])
            + (f' y {len(rotos) - 3} mas' if len(rotos) > 3 else '')
        )

    if IntentoCargaSAIA.objects.filter(documento=documento, exitoso=True).exists():
        errors.append('Documento ya tiene carga exitosa registrada en SAIA')

    historical_evidence = find_historical_saia_evidence(documento, asunto_saia=asunto_saia)
    if historical_evidence:
        message = historical_evidence.get('mensaje_bloqueo_saia_historico') or (
            'Documento encontrado en historico documental'
        )
        errors.append(message)
        _mark_document_historical_review(documento, historical_evidence)

    user_errors = _build_user_errors(errors, documento)
    user_warnings = _build_user_warnings(warnings, documento)

    return {
        'documento_id': documento.id,
        'nombre_archivo': documento.nombre_archivo,
        'listo_para_saia': not errors,
        'asunto_saia': asunto_saia,
        'asunto_nombre': asunto_nombre,
        'route_code': route_code,
        'route_description': route_config.get('descripcion', '') if route_config else '',
        'errores': errors,
        'errores_usuario': user_errors,
        'error_usuario_principal': user_errors[0] if user_errors else {},
        'advertencias': warnings,
        'advertencias_usuario': user_warnings,
        'historico_saia': historical_evidence or {},
    }


def build_saia_subject_from_filename(nombre_archivo):
    subject = Path(nombre_archivo).stem.strip()
    return re.sub(r'\s+OK$', '', subject, flags=re.IGNORECASE).strip()


def validate_lote_for_saia(lote, solo_listos=False):
    _base_qs = (
        DocumentoDigitalizado.objects
        .select_related('metadata')
        .prefetch_related('relaciones_principales__documento_relacionado')
    )
    documentos = sorted(
        list(
            _base_qs
            .filter(lote=lote, estado_proceso__in=ALLOWED_SAIA_STATES)
            .order_by('id')
        ),
        key=lambda documento: get_documental_natural_sort_key(documento.nombre_archivo),
    )
    results = []
    for documento in documentos:
        control.doc_actual = documento.nombre_archivo
        results.append(validate_document_for_saia(documento))

    # Documentos bloqueados por discrepancia de consecutivo en Fase 2:
    # se incluyen explícitamente para que aparezcan en Revisión Manual con
    # su error detallado, no como documentos silenciosamente omitidos.
    docs_mismatch = sorted(
        list(
            _base_qs
            .filter(
                lote=lote,
                estado_proceso='REQUIERE_REVISION',
                metadata__datos_pel__mismatch_bloquea=True,
            )
            .order_by('id')
        ),
        key=lambda documento: get_documental_natural_sort_key(documento.nombre_archivo),
    )
    for documento in docs_mismatch:
        control.doc_actual = documento.nombre_archivo
        results.append(validate_document_for_saia(documento, include_errored=True))

    control.doc_actual = ""

    # Gap B: detectar asunto_saia duplicados dentro del lote
    _flag_duplicate_asuntos(results)

    if solo_listos:
        return [result for result in results if result['listo_para_saia']]
    return results


def has_ok_marker(filename):
    return bool(OK_FILENAME_RE.search(str(filename or '')))


def _flag_duplicate_asuntos(results):
    # Gap B: marca como bloqueados todos los documentos que comparten el mismo
    # asunto_saia Y route_code dentro del lote.
    # La clave incluye route_code para evitar falsos positivos cuando distintos bancos
    # (Bancolombia, Colpatria, Corbanca, CCA, CCV) usan el mismo nombre de mes como asunto.
    seen = {}
    duplicates = set()
    for result in results:
        asunto = result.get('asunto_saia', '')
        if not asunto:
            continue
        route_code = result.get('route_code', '')
        key = f'{route_code}::{asunto}' if route_code else asunto
        if key in seen:
            duplicates.add(key)
        else:
            seen[key] = True
    for result in results:
        asunto = result.get('asunto_saia', '')
        route_code = result.get('route_code', '')
        key = f'{route_code}::{asunto}' if route_code else asunto
        if key in duplicates:
            result['errores'].append(
                f'asunto_saia duplicado en el lote: "{asunto}" aparece en mas de un documento de la misma ruta'
            )
            result['listo_para_saia'] = False


def _mark_document_mismatch_review(documento, mensaje):
    """Persiste REQUIERE_REVISION con el mensaje de discrepancia para que el documento
    aparezca en la pestaña Revisión Manual con el detalle del conflicto."""
    changed = []
    if documento.estado_proceso != 'REQUIERE_REVISION':
        documento.estado_proceso = 'REQUIERE_REVISION'
        changed.append('estado_proceso')
    if mensaje and mensaje not in (documento.error or ''):
        documento.error = f'{documento.error}; {mensaje}' if documento.error else mensaje
        changed.append('error')
    if changed:
        changed.append('modificado')
        documento.save(update_fields=changed)


def _mark_document_historical_review(documento, evidence):
    message = evidence.get('mensaje_bloqueo_saia_historico') or ''
    if not message:
        return
    current_error = documento.error or ''
    if message not in current_error:
        documento.error = f'{current_error}; {message}' if current_error else message
    if documento.estado_proceso != 'REQUIERE_REVISION':
        documento.estado_proceso = 'REQUIERE_REVISION'
    documento.save(update_fields=['estado_proceso', 'error', 'modificado'])


def _can_read_file(file_path):
    try:
        with open(file_path, 'rb') as file:
            file.read(1)
        return True
    except OSError:
        return False


def _is_valid_pdf(file_path):
    try:
        with open(file_path, 'rb') as f:
            return f.read(5) == b'%PDF-'
    except OSError:
        return False


def _pdf_content_errors(file_path):
    # Gap A: usa pypdf para detectar contrasena y PDF sin paginas.
    # Si pypdf no esta disponible o falla inesperadamente, no bloqueamos
    # (la cabecera ya fue verificada por _is_valid_pdf).
    errors = []
    try:
        import pypdf
        reader = pypdf.PdfReader(str(file_path))
        if reader.is_encrypted:
            errors.append(
                'El archivo PDF esta protegido con contrasena y no puede ser procesado por SAIA'
            )
        elif len(reader.pages) == 0:
            errors.append('El archivo PDF no contiene paginas legibles')
    except Exception:
        pass
    return errors


def _max_pdf_bytes():
    """D10: limite de tamano de PDF leido desde SAIA_MAX_FILE_MB (default 50 MB)."""
    try:
        return int(os.getenv('SAIA_MAX_FILE_MB', '50')) * 1024 * 1024
    except (ValueError, TypeError):
        return 50 * 1024 * 1024


def _build_user_errors(errors, documento):
    result = []
    context = {
        'estado_proceso': documento.estado_proceso,
        'nombre_archivo': documento.nombre_archivo,
        'es_soportado': documento.es_soportado,
        'es_duplicado': documento.es_duplicado,
    }
    for error in errors:
        user_error = build_phase4_error_message(error, context)
        if user_error.get('codigo_error_usuario'):
            result.append(user_error)
    return result


def _build_user_warnings(warnings, documento):
    result = []
    context = {
        'estado_proceso': documento.estado_proceso,
        'nombre_archivo': documento.nombre_archivo,
        'codigo_error': 'PDF_PESADO_SAIA',
    }
    for warning in warnings:
        if 'PDF_PESADO_SAIA' not in str(warning):
            continue
        user_warning = build_phase4_error_message(warning, context)
        if user_warning.get('codigo_error_usuario'):
            result.append(user_warning)
    return result


