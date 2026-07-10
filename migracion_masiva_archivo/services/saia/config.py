import os
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings

from migracion_masiva_archivo.services.saia.exceptions import SAIACredentialsError


DEFAULT_SAIA_URL = 'https://eurosupermercados.netsaia.com/eurosupermercados/saia/index.php'


@dataclass(frozen=True)
class SAIAConfig:
    base_url: str
    username: str
    password: str
    screenshot_dir: Path
    timeout_ms: int = 30000

    def validate_credentials(self):
        if not self.username or not self.password:
            raise SAIACredentialsError(
                'No se encontraron las credenciales de SAIA. Configure SAIA_USER y SAIA_PASSWORD en el archivo .env o en las variables de entorno.'
            )


def get_saia_config():
    screenshot_dir = Path(
        os.getenv(
            'SAIA_SCREENSHOT_DIR',
            str(settings.BASE_DIR / 'tmp_documental_phase4' / 'saia_screenshots'),
        )
    )
    return SAIAConfig(
        base_url=os.getenv('SAIA_BASE_URL', DEFAULT_SAIA_URL),
        username=os.getenv('SAIA_USER', ''),
        password=os.getenv('SAIA_PASSWORD', ''),
        screenshot_dir=screenshot_dir,
        timeout_ms=int(os.getenv('SAIA_TIMEOUT_MS', '30000')),
    )


