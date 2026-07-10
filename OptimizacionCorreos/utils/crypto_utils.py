"""
Encriptación Fernet para credenciales sensibles del módulo OptimizacionCorreos.

Flujo:
  - La clave maestra se genera UNA VEZ con `manage.py configurar_secretos`
    y se guarda en secrets/oc_master.key (fuera del repo).
  - Los valores encriptados se almacenan en .env (ej. OC_ZIMBRA_PASSWORD_ENC).
  - En runtime, decrypt_credential() lee la variable cifrada y devuelve texto plano.
"""
from __future__ import annotations

import os
from pathlib import Path

from cryptography.fernet import Fernet


def get_fernet() -> Fernet:
    key_path = Path(os.environ.get("OC_MASTER_KEY_PATH", "./secrets/oc_master.key"))
    key = key_path.read_bytes().strip()
    return Fernet(key)


def decrypt_credential(env_var_name: str) -> str:
    """Lee os.environ[env_var_name], desencripta y retorna texto plano."""
    f = get_fernet()
    encrypted = os.environ[env_var_name]
    return f.decrypt(encrypted.encode()).decode()


def encrypt_value(plain: str) -> str:
    """Encripta y retorna token base64 para guardar en .env."""
    f = get_fernet()
    return f.encrypt(plain.encode()).decode()
