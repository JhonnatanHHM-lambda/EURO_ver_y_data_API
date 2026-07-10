import hashlib
import os
from pathlib import Path

from .file_name_service import (
    extract_pel_numbers_from_text,
    extraer_metadata_nombre_archivo,
    should_omit_system_file,
    validate_filename_for_phase1,
)
from .file_signature_service import inspect_file_signature
from .pdf_service import inspect_pdf


DOCUMENT_EXTENSIONS = {'.pdf', '.png', '.jpg', '.jpeg', '.tif', '.tiff'}
MIN_PDF_BYTES = 1024
MIN_IMAGE_BYTES = 512


class FolderValidationError(ValueError):
    pass


def normalize_selected_folder(raw_path):
    raw = str(raw_path or '').strip().strip('"').strip("'")
    if not raw:
        raise FolderValidationError('Selecciona una carpeta antes de iniciar.')

    folder = Path(raw).expanduser()
    if not folder.is_absolute():
        raise FolderValidationError(
            'La ruta de la carpeta no es completa. Selecciona la carpeta con Explorar '
            'o pega la ruta absoluta completa, por ejemplo C:\\...\\PEL\\PEL 2019.'
        )

    try:
        folder = folder.resolve(strict=False)
    except OSError as exc:
        raise FolderValidationError(f'No se pudo resolver la ruta de la carpeta: {exc}') from exc

    if not folder.exists():
        raise FolderValidationError(f'La carpeta no existe: {folder}')
    if not folder.is_dir():
        raise FolderValidationError(f'La ruta seleccionada no es una carpeta: {folder}')

    try:
        with os.scandir(folder):
            pass
    except PermissionError as exc:
        raise FolderValidationError(f'No hay permisos para leer la carpeta: {folder}') from exc
    except OSError as exc:
        raise FolderValidationError(f'No se pudo abrir la carpeta seleccionada: {exc}') from exc

    return folder


def count_pdf_files(folder):
    folder = Path(folder)
    return sum(
        1 for path in folder.rglob('*')
        if path.is_file() and path.suffix.lower() == '.pdf' and not should_omit_system_file(path)
    )


def validate_selected_folder_for_inventory(raw_path):
    folder = normalize_selected_folder(raw_path)
    if count_pdf_files(folder) == 0:
        raise FolderValidationError(
            f'La carpeta seleccionada no contiene archivos PDF para procesar: {folder}'
        )
    return folder


def scan_folder(folder_path):
    documents, _context = scan_folder_with_context(folder_path)
    return documents


def scan_folder_with_context(folder_path):
    folder = validate_selected_folder_for_inventory(folder_path)

    results = []
    context = _empty_scan_context()
    for path in sorted(folder.rglob('*')):
        if _is_omitted_path(path):
            _register_omitted_path(path, context)
            continue
        file_info = scan_file(path)
        if file_info:
            results.append(file_info)
            if not file_info.get('es_soportado'):
                context['total_no_soportados'] += 1
    return results, context


def scan_file(path):
    path = Path(path)
    if not path.is_file() or should_omit_system_file(path):
        return None

    extension = path.suffix.lower()
    is_supported = extension in DOCUMENT_EXTENSIONS
    error = '' if is_supported else 'Formato no soportado para exploracion documental'
    errors = [error] if error else []
    size_result = safe_file_size(path)
    hash_result = safe_sha256(path)
    signature = inspect_file_signature(path, extension) if is_supported else _empty_signature()
    size_validation = _validate_size(extension, size_result['peso_bytes'])
    filename_validation = validate_filename_for_phase1(path.name)
    saia_size_validation = _validate_saia_size(extension, size_result['peso_bytes'])

    if size_validation['error']:
        errors.append(size_validation['error'])
    if filename_validation['error_validacion_nombre']:
        errors.append(filename_validation['error_validacion_nombre'])
    if size_result['error_lectura_tamano']:
        errors.append(size_result['error_lectura_tamano'])
    if hash_result['error_lectura_hash']:
        errors.append(hash_result['error_lectura_hash'])
    if signature['error_firma_archivo']:
        errors.append(signature['error_firma_archivo'])
    elif is_supported and not signature['extension_coincide_con_firma']:
        errors.append(_signature_mismatch_message(extension, signature['tipo_detectado_por_firma']))

    file_info = {
        'ruta_archivo': str(path),
        'nombre_archivo': path.name,
        'extension': extension.replace('.', '') or 'sin_extension',
        'peso_bytes': size_result['peso_bytes'],
        'hash_archivo': hash_result['hash_archivo'],
        'es_soportado': is_supported,
        'es_duplicado': False,
        'documento_duplicado_de': None,
        'es_pdf': extension == '.pdf',
        'numero_paginas': 0,
        'es_digital': False,
        'requiere_ocr': is_supported and extension != '.pdf',
        'texto_extraido': '',
        'estado_proceso': 'LEIDO' if is_supported else 'REQUIERE_REVISION',
        'error': '; '.join(errors),
        'archivo_vacio': size_validation['archivo_vacio'],
        'archivo_sospechosamente_pequeno': size_validation['archivo_sospechosamente_pequeno'],
        'validacion_tamano': size_validation['validacion_tamano'],
        'pdf_supera_limite_saia': saia_size_validation['pdf_supera_limite_saia'],
        'pdf_pesado_saia': saia_size_validation['pdf_pesado_saia'],
        'advertencia_tamano_saia': saia_size_validation['advertencia'],
        'requiere_timeout_extendido': saia_size_validation['requiere_timeout_extendido'],
        'saia_max_file_mb': saia_size_validation['saia_max_file_mb'],
        'validacion_tamano_saia': saia_size_validation['validacion_tamano_saia'],
        'error_lectura_tamano': size_result['error_lectura_tamano'],
        'error_lectura_hash': hash_result['error_lectura_hash'],
        'archivo_posiblemente_bloqueado': _is_lock_or_sync_error(
            size_result['error_lectura_tamano'],
            hash_result['error_lectura_hash'],
            signature['error_firma_archivo'],
        ),
        'archivo_posiblemente_sincronizando': _is_sync_error(
            size_result['error_lectura_tamano'],
            hash_result['error_lectura_hash'],
            signature['error_firma_archivo'],
        ),
        'nombre_pel_ambiguo': filename_validation['nombre_pel_ambiguo'],
        'caracteres_no_compatibles_saia': filename_validation['caracteres_no_compatibles_saia'],
        'caracteres_problematicos_saia': filename_validation['caracteres_problematicos_saia'],
        'extension_doble_o_sospechosa': filename_validation['extension_doble_o_sospechosa'],
        'validaciones_nombre': filename_validation['validaciones_nombre'],
        'consecutivo_nombre_no_coincide_contenido': False,
        'consecutivos_contenido_detectados': '',
        'error_pdf': '',
        **signature,
    }

    if is_supported and extension == '.pdf':
        pdf_info = inspect_pdf(path)
        pdf_error = pdf_info.pop('error', '')
        file_info.update(pdf_info)
        file_info['error_pdf'] = pdf_error
        file_info['error'] = _append_error(file_info['error'], pdf_error)
        file_info['texto_extraido'] = ''
        content_validation = _validate_name_content_consistency(path.name, pdf_info.get('texto_extraido', ''))
        if content_validation['error']:
            file_info['error'] = _append_error(file_info['error'], content_validation['error'])
            file_info['consecutivo_nombre_no_coincide_contenido'] = True
        file_info['consecutivos_contenido_detectados'] = content_validation['consecutivos_contenido_detectados']

    return file_info


def calculate_sha256(path):
    hasher = hashlib.sha256()
    with open(path, 'rb') as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b''):
            hasher.update(chunk)
    return hasher.hexdigest()


def safe_sha256(path):
    try:
        return {'hash_archivo': calculate_sha256(path), 'error_lectura_hash': ''}
    except PermissionError as exc:
        return {'hash_archivo': '', 'error_lectura_hash': f'No se pudo calcular hash: {exc}'}
    except FileNotFoundError as exc:
        return {'hash_archivo': '', 'error_lectura_hash': f'Archivo no encontrado al calcular hash: {exc}'}
    except OSError as exc:
        return {'hash_archivo': '', 'error_lectura_hash': f'No se pudo calcular hash: {exc}'}


def safe_file_size(path):
    try:
        return {'peso_bytes': path.stat().st_size, 'error_lectura_tamano': ''}
    except PermissionError as exc:
        return {'peso_bytes': 0, 'error_lectura_tamano': f'No se pudo leer tamano: {exc}'}
    except FileNotFoundError as exc:
        return {'peso_bytes': 0, 'error_lectura_tamano': f'Archivo no encontrado al leer tamano: {exc}'}
    except OSError as exc:
        return {'peso_bytes': 0, 'error_lectura_tamano': f'No se pudo leer tamano: {exc}'}


def _validate_size(extension, size):
    result = {
        'archivo_vacio': size == 0,
        'archivo_sospechosamente_pequeno': False,
        'validacion_tamano': 'OK',
        'error': '',
    }
    if size == 0:
        result['validacion_tamano'] = 'ARCHIVO_VACIO'
        result['error'] = 'Archivo vacio'
        return result
    if extension == '.pdf' and size < MIN_PDF_BYTES:
        result['archivo_sospechosamente_pequeno'] = True
        result['validacion_tamano'] = 'PDF_SOSPECHOSAMENTE_PEQUENO'
        result['error'] = 'Archivo PDF sospechosamente pequeno'
    elif extension in {'.png', '.jpg', '.jpeg', '.tif', '.tiff'} and size < MIN_IMAGE_BYTES:
        result['archivo_sospechosamente_pequeno'] = True
        result['validacion_tamano'] = 'IMAGEN_SOSPECHOSAMENTE_PEQUENA'
        result['error'] = 'Archivo de imagen sospechosamente pequeno'
    return result


def _validate_saia_size(extension, size):
    max_mb = _saia_max_file_mb()
    max_bytes = max_mb * 1024 * 1024
    exceeds = extension == '.pdf' and size > max_bytes
    return {
        'pdf_supera_limite_saia': exceeds,
        'pdf_pesado_saia': exceeds,
        'advertencia': (
            f'PDF pesado para SAIA ({size / (1024 * 1024):.1f} MB > {max_mb} MB). '
            'La carga puede tardar mas, pero no se bloquea automaticamente.'
            if exceeds else ''
        ),
        'requiere_timeout_extendido': exceeds,
        'saia_max_file_mb': max_mb,
        'validacion_tamano_saia': 'PDF_PESADO_SAIA' if exceeds else 'OK',
        'error': '',
    }


def _saia_max_file_mb():
    try:
        value = int(os.getenv('SAIA_MAX_FILE_MB', '50'))
        return value if value > 0 else 50
    except (TypeError, ValueError):
        return 50


def _validate_name_content_consistency(filename, text):
    metadata = extraer_metadata_nombre_archivo(filename)
    expected = metadata.get('pel_base_nombre')
    content_numbers = extract_pel_numbers_from_text(text)
    if not expected or not content_numbers:
        return {'error': '', 'consecutivos_contenido_detectados': ','.join(map(str, content_numbers))}
    if int(expected) in content_numbers:
        return {'error': '', 'consecutivos_contenido_detectados': ','.join(map(str, content_numbers))}
    return {
        'error': (
            'Consecutivo del nombre no coincide con contenido: '
            f'archivo PEL {expected}, texto PEL {", ".join(map(str, content_numbers[:5]))}'
        ),
        'consecutivos_contenido_detectados': ','.join(map(str, content_numbers)),
    }


def _signature_mismatch_message(extension, detected):
    if extension == '.pdf':
        return 'Extension PDF no coincide con contenido real'
    detected_text = detected or 'desconocido'
    return f'Extension no coincide con firma binaria; detectado={detected_text}'


def _empty_signature():
    return {
        'firma_archivo': '',
        'tipo_detectado_por_firma': '',
        'extension_coincide_con_firma': False,
        'error_firma_archivo': '',
    }


def _append_error(current, extra):
    if not extra:
        return current
    if not current:
        return extra
    return f'{current}; {extra}'


def _is_lock_or_sync_error(*errors):
    text = ' '.join(error for error in errors if error).lower()
    return any(pattern in text for pattern in ['permission', 'permiso', 'denied', 'bloqueado', 'cloud', 'sync'])


def _is_sync_error(*errors):
    text = ' '.join(error for error in errors if error).lower()
    return any(pattern in text for pattern in ['cloud', 'sync', 'sincroniz', 'onedrive', 'placeholder'])


def _is_omitted_path(path):
    return not path.is_file() or should_omit_system_file(path)


def _register_omitted_path(path, context):
    if path.is_dir():
        context['total_carpetas_omitidas'] += 1
        return

    name = path.name.lower()
    if name.startswith('~$'):
        context['total_omitidos_temporales'] += 1
    elif name in {'desktop.ini', 'thumbs.db', '.ds_store'}:
        context['total_omitidos_sistema'] += 1
    elif name.startswith('.'):
        context['total_omitidos_ocultos'] += 1
    else:
        context['total_omitidos_sistema'] += 1


def _empty_scan_context():
    return {
        'total_omitidos_sistema': 0,
        'total_omitidos_temporales': 0,
        'total_omitidos_ocultos': 0,
        'total_carpetas_omitidas': 0,
        'total_no_soportados': 0,
    }


