"""
Navega en SAIA hasta el módulo Conciliaciones Bancarias y toma un screenshot.

Flujo:
  Archivo → (atrás) → Archivo Central → Dirección de Contabilidad
  → Conciliaciones → Conciliaciones Bancarias

Uso:
  python manage.py probar_conciliaciones_saia
  python manage.py probar_conciliaciones_saia --headful
"""

import os

from django.core.management.base import BaseCommand, CommandError

from migracion_masiva_archivo.services.saia.browser_client import SAIABrowserClient
from migracion_masiva_archivo.services.saia.config import get_saia_config
from migracion_masiva_archivo.services.saia.exceptions import SAIACredentialsError, SAIAError


class Command(BaseCommand):
    help = 'Navega hasta Conciliaciones Bancarias en SAIA y toma un screenshot de verificación.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--headful',
            action='store_true',
            help='Muestra el navegador durante la navegación.',
        )

    def handle(self, *args, **options):
        os.environ.setdefault('DJANGO_ALLOW_ASYNC_UNSAFE', 'true')

        config = get_saia_config()
        try:
            config.validate_credentials()
        except SAIACredentialsError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write('Iniciando navegación a Conciliaciones Bancarias en SAIA...')
        self.stdout.write(f'  Usuario : {config.username}')
        self.stdout.write(f'  URL     : {config.base_url}')

        try:
            with SAIABrowserClient(config, headful=options['headful']) as client:
                self.stdout.write('  Paso 1: Login...')
                client.login()
                self.stdout.write(self.style.SUCCESS('  Login OK'))

                self.stdout.write('  Paso 2: Navegando a Conciliaciones Bancarias...')
                client.navigate_to_conciliaciones_bancarias()
                self.stdout.write(self.style.SUCCESS('  Navegación OK'))

                screenshot = client.capture_screenshot('conciliaciones_bancarias_ok')
                self.stdout.write(f'  Screenshot: {screenshot}')
                self.stdout.write(f'  URL final : {client.current_url()}')

        except SAIAError as exc:
            raise CommandError(f'Error SAIA: {exc}') from exc

        self.stdout.write(self.style.SUCCESS('Flujo Conciliaciones Bancarias completado exitosamente.'))


