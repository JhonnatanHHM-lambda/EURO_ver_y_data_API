SIGNATURES = {
    'pdf': (b'%PDF',),
    'jpg': (b'\xff\xd8\xff',),
    'jpeg': (b'\xff\xd8\xff',),
    'png': (b'\x89PNG\r\n\x1a\n',),
    'tif': (b'II*\x00', b'MM\x00*'),
    'tiff': (b'II*\x00', b'MM\x00*'),
}


def inspect_file_signature(path, extension):
    extension = (extension or '').lower().lstrip('.')
    try:
        with open(path, 'rb') as file:
            header = file.read(16)
    except PermissionError as exc:
        return _error_result('No se tiene permiso para leer la firma del archivo', exc)
    except FileNotFoundError as exc:
        return _error_result('Archivo no encontrado al leer la firma', exc)
    except OSError as exc:
        return _error_result('No se pudo leer la firma del archivo', exc)

    detected = detect_signature_type(header)
    expected = extension if extension in SIGNATURES else ''
    matches = bool(expected and detected == expected)

    if expected in {'jpg', 'jpeg'} and detected in {'jpg', 'jpeg'}:
        matches = True
    if expected in {'tif', 'tiff'} and detected in {'tif', 'tiff'}:
        matches = True

    return {
        'firma_archivo': header.hex(' ').upper(),
        'tipo_detectado_por_firma': detected,
        'extension_coincide_con_firma': matches if expected else False,
        'error_firma_archivo': '',
    }


def detect_signature_type(header):
    for file_type, signatures in SIGNATURES.items():
        if any(header.startswith(signature) for signature in signatures):
            if file_type == 'jpeg':
                return 'jpg'
            if file_type == 'tiff':
                return 'tif'
            return file_type
    return 'desconocido'


def _error_result(message, exc):
    return {
        'firma_archivo': '',
        'tipo_detectado_por_firma': '',
        'extension_coincide_con_firma': False,
        'error_firma_archivo': f'{message}: {exc}',
    }


