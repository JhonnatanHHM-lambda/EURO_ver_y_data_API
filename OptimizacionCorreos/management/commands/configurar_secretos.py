"""
Comando de gestión: python manage.py configurar_secretos

Genera secrets/oc_master.key (si no existe), pide credenciales sensibles,
las encripta con Fernet y las escribe en .env como variables OC_*_ENC.
"""
import os
from pathlib import Path

from cryptography.fernet import Fernet
from django.core.management.base import BaseCommand
from dotenv import set_key


class Command(BaseCommand):
    help = 'Configura las credenciales encriptadas del módulo OptimizacionCorreos'

    def handle(self, *args, **options):
        base_dir = Path(os.getcwd())
        secrets_dir = base_dir / 'secrets'
        key_path = secrets_dir / 'oc_master.key'
        env_path = base_dir / '.env'

        # ── Generar clave maestra si no existe ───────────────────────────────
        secrets_dir.mkdir(exist_ok=True)
        if key_path.exists():
            self.stdout.write(f'  Clave maestra existente: {key_path}')
            key = key_path.read_bytes().strip()
        else:
            key = Fernet.generate_key()
            key_path.write_bytes(key)
            self.stdout.write(self.style.SUCCESS(f'  Nueva clave maestra generada: {key_path}'))

        fernet = Fernet(key)

        # ── Solicitar credenciales por input seguro ──────────────────────────
        self.stdout.write('\n─── Configuración DIAN ──────────────────────────────────')
        cc_rep = input('  Cédula del representante legal DIAN (CC_REP): ').strip()

        self.stdout.write('\n─── Configuración Zimbra ────────────────────────────────')
        zimbra_pass = input('  Contraseña del buzón Zimbra: ').strip()

        if not cc_rep or not zimbra_pass:
            self.stdout.write(self.style.ERROR('  No se ingresaron valores. Operación cancelada.'))
            return

        # ── Encriptar y guardar en .env ──────────────────────────────────────
        cc_rep_enc = fernet.encrypt(cc_rep.encode()).decode()
        zimbra_pass_enc = fernet.encrypt(zimbra_pass.encode()).decode()

        if not env_path.exists():
            env_path.touch()

        set_key(str(env_path), 'OC_DIAN_CC_REP_ENC', cc_rep_enc)
        set_key(str(env_path), 'OC_ZIMBRA_PASSWORD_ENC', zimbra_pass_enc)
        set_key(str(env_path), 'OC_MASTER_KEY_PATH', str(key_path))

        self.stdout.write(self.style.SUCCESS('\n✓ Secretos configurados correctamente'))
        self.stdout.write(f'  OC_DIAN_CC_REP_ENC  → {cc_rep_enc[:20]}...')
        self.stdout.write(f'  OC_ZIMBRA_PASSWORD_ENC → {zimbra_pass_enc[:20]}...')
        self.stdout.write(f'  OC_MASTER_KEY_PATH → {key_path}')
        self.stdout.write('\n  IMPORTANTE: secrets/oc_master.key NO debe subirse al repositorio.')
