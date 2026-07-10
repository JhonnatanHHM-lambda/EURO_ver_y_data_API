import errno
import time
from pathlib import Path

from migracion_masiva_archivo.services.saia.exceptions import SAIALocalFileError
from migracion_masiva_archivo.services.saia.validation_service import has_ok_marker

_RENAME_MAX_INTENTOS = 3
_RENAME_PAUSA_S = 2


def mark_document_file_ok(documento):
    current_path = Path(documento.ruta_archivo)
    if not current_path.exists():
        raise SAIALocalFileError(f'No existe el archivo local para marcar OK: {current_path}')

    if has_ok_marker(current_path.name):
        return {
            'renombrado': False,
            'ruta_anterior': str(current_path),
            'ruta_nueva': str(current_path),
            'mensaje': 'El archivo ya tenia OK en el nombre.',
        }

    new_path = current_path.with_name(f'{current_path.stem} OK{current_path.suffix}')
    if new_path.exists():
        raise SAIALocalFileError(f'No se marca OK porque ya existe el destino: {new_path}')

    ultimo_error = None
    for intento in range(1, _RENAME_MAX_INTENTOS + 1):
        try:
            current_path.rename(new_path)
            break
        except OSError as exc:
            ultimo_error = exc
            # WinError 32 = archivo bloqueado por otro proceso (PermissionError en Windows)
            es_bloqueado = (
                getattr(exc, 'winerror', None) == 32
                or getattr(exc, 'errno', None) in (errno.EACCES, errno.EBUSY)
            )
            if not es_bloqueado:
                raise SAIALocalFileError(f'Error al renombrar archivo a OK: {exc}') from exc
            if intento < _RENAME_MAX_INTENTOS:
                time.sleep(_RENAME_PAUSA_S)
    else:
        raise SAIALocalFileError(
            f'Archivo bloqueado por otro proceso tras {_RENAME_MAX_INTENTOS} intentos '
            f'({_RENAME_PAUSA_S}s entre cada uno): {current_path} | {ultimo_error}'
        )

    documento.ruta_archivo = str(new_path)
    documento.nombre_archivo = new_path.name
    documento.marcado_ok = True
    documento.save(update_fields=['ruta_archivo', 'nombre_archivo', 'marcado_ok', 'modificado'])

    return {
        'renombrado': True,
        'ruta_anterior': str(current_path),
        'ruta_nueva': str(new_path),
        'mensaje': 'Archivo local marcado con OK.',
    }


