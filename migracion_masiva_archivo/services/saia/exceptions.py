class SAIAError(Exception):
    """Error base de la integracion SAIA."""


class SAIACredentialsError(SAIAError):
    """Credenciales SAIA faltantes o invalidas."""


class SAIATimeoutError(SAIAError):
    """SAIA no respondio dentro del tiempo esperado."""


class SAIASelectorError(SAIAError):
    """No fue posible identificar un selector en SAIA."""


class SAIADocumentValidationError(SAIAError):
    """El documento no cumple condiciones para probar carga en SAIA."""


class SAIADuplicateError(SAIAError):
    """El documento ya tiene una carga exitosa registrada."""


class SAIANormalizationError(SAIAError):
    """El consecutivo no se pudo convertir al asunto esperado por SAIA."""


class SAIALoginError(SAIAError):
    """No fue posible iniciar sesion en SAIA."""


class SAIALocalFileError(SAIAError):
    """No fue posible marcar el archivo local como cargado."""


