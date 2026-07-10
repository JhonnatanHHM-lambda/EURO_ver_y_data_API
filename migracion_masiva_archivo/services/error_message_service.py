import re

PHASE_1 = 'FASE_1'
PHASE_2 = 'FASE_2'
PHASE_3 = 'FASE_3'
PHASE_4 = 'FASE_4'
PHASE_5 = 'FASE_5'

PHASE2_MANUAL_REVIEW_CODES = {
    'OCR_SIN_TEXTO',
    'OCR_TEXTO_INSUFICIENTE',
    'CONSECUTIVO_NO_DETECTADO',
    'CONSECUTIVO_NO_COINCIDE',
    'CONFIANZA_BAJA',
    'METADATA_AMBIGUA',
    'IDENTIDAD_DOCUMENTAL_NO_DETECTADA',
}

PHASE3_MANUAL_REVIEW_CODES = {
    'PRINCIPAL_NO_ENCONTRADO',
    'PRINCIPALES_MULTIPLES',
    'DOCUMENTO_SIN_METADATA',
    'DOCUMENTO_EN_REVISION',
    'DATOS_PEL_INCOMPLETOS',
    'CONFIANZA_RELACION_BAJA',
    'CONFIANZA_NO_CALCULADA',
    'METADATA_RELACION_INSUFICIENTE',
    'TOMO_SECUENCIA_INCOMPLETA',
    'GRUPO_SIN_RELACION_AUTOMATICA',
}

PHASE4_MANUAL_REVIEW_CODES = {
    'DOCUMENTO_SIN_METADATA',
    'METADATA_REQUIERE_REVISION',
    'DATOS_PEL_INCOMPLETOS',
    'CONSECUTIVO_NO_NORMALIZABLE',
    'CONSECUTIVO_NO_COINCIDE_NOMBRE',
    'SOPORTES_ESTADO_INVALIDO',
}

PHASE5_MANUAL_REVIEW_CODES = {
    'SAIA_NO_CONFIRMADA',
    'SELECTOR_NO_ENCONTRADO',
    'CREDENCIALES_SAIA_INVALIDAS',
    'TIMEOUT_SAIA',
    'SESION_EXPIRADA',
    'BROWSER_CERRADO',
    'ERROR_RED_SAIA',
    'ERROR_INESPERADO_SAIA',
}

PHASE2_MANUAL_GUIDANCE = (
    'El sistema no pudo leer o validar la informacion automaticamente. '
    'Revise manualmente el documento y, si la informacion es correcta, '
    'realice la carga manual en SAIA o solicite soporte.'
)
PHASE3_MANUAL_GUIDANCE = (
    'No se pudo confirmar la relacion documental automaticamente. '
    'Revise manualmente el grupo documental antes de realizar la carga manual en SAIA.'
)
PHASE4_MANUAL_GUIDANCE = (
    'El documento no cumple las condiciones para carga automatica. '
    'Corrija la informacion o realice la carga manual en SAIA solo si ya verifico el caso.'
)
PHASE5_MANUAL_GUIDANCE = (
    'Revise manualmente en SAIA si el documento quedo cargado antes de reintentar, '
    'para evitar duplicados. Si la carga automatica no puede continuar, '
    'realice la carga manual o solicite soporte tecnico.'
)


DEFAULT_ERROR = {
    'codigo_error_usuario': '',
    'fase_error': PHASE_1,
    'severidad_error': '',
    'mensaje_usuario': '',
    'accion_recomendada': '',
    'bloquea_fase_2': False,
    'bloquea_saia': False,
}


ERROR_MESSAGES = {
    'ARCHIVO_VACIO': {
        'severidad_error': 'ALTA',
        'mensaje_usuario': 'El archivo está vacío y no contiene información para revisar.',
        'accion_recomendada': 'Solicita una nueva copia del documento antes de continuar.',
        'bloquea_fase_2': True,
        'bloquea_saia': True,
    },
    'ARCHIVO_PEQUENO': {
        'severidad_error': 'MEDIA',
        'mensaje_usuario': 'El archivo es demasiado pequeño y podría estar incompleto.',
        'accion_recomendada': 'Abre el archivo manualmente y confirma que el documento se visualiza completo.',
        'bloquea_fase_2': True,
        'bloquea_saia': True,
    },
    'SIN_PERMISO_LECTURA': {
        'severidad_error': 'ALTA',
        'mensaje_usuario': 'No se tiene permiso para leer el archivo.',
        'accion_recomendada': 'Verifica permisos de la carpeta o solicita acceso antes de continuar.',
        'bloquea_fase_2': True,
        'bloquea_saia': True,
    },
    'ARCHIVO_NO_ENCONTRADO': {
        'severidad_error': 'ALTA',
        'mensaje_usuario': 'El archivo no se encontró durante la exploración.',
        'accion_recomendada': 'Confirma que el archivo exista y que no haya sido movido o eliminado.',
        'bloquea_fase_2': True,
        'bloquea_saia': True,
    },
    'ARCHIVO_BLOQUEADO': {
        'severidad_error': 'MEDIA',
        'mensaje_usuario': 'El archivo parece estar bloqueado por otro proceso.',
        'accion_recomendada': 'Cierra el archivo si está abierto y vuelve a ejecutar la exploración.',
        'bloquea_fase_2': True,
        'bloquea_saia': True,
    },
    'ARCHIVO_EN_SINCRONIZACION': {
        'severidad_error': 'MEDIA',
        'mensaje_usuario': 'El archivo parece estar sincronizándose y aún no está disponible localmente.',
        'accion_recomendada': 'Espera a que OneDrive termine de sincronizar y vuelve a explorar la carpeta.',
        'bloquea_fase_2': True,
        'bloquea_saia': True,
    },
    'HASH_NO_CALCULADO': {
        'severidad_error': 'MEDIA',
        'mensaje_usuario': 'No se pudo calcular la huella del archivo.',
        'accion_recomendada': 'Verifica que el archivo se pueda abrir y que no esté bloqueado.',
        'bloquea_fase_2': True,
        'bloquea_saia': True,
    },
    'TAMANO_NO_LEIDO': {
        'severidad_error': 'MEDIA',
        'mensaje_usuario': 'No se pudo leer el tamaño del archivo.',
        'accion_recomendada': 'Verifica permisos, disponibilidad local y sincronización del archivo.',
        'bloquea_fase_2': True,
        'bloquea_saia': True,
    },
    'PDF_DANADO': {
        'severidad_error': 'ALTA',
        'mensaje_usuario': 'El PDF parece estar dañado o incompleto.',
        'accion_recomendada': 'Solicita una nueva copia del documento o intenta abrirlo manualmente antes de continuar.',
        'bloquea_fase_2': True,
        'bloquea_saia': True,
    },
    'PDF_CORRUPTO': {
        'severidad_error': 'ALTA',
        'mensaje_usuario': 'El PDF no se pudo abrir correctamente.',
        'accion_recomendada': 'Solicita una nueva copia del documento antes de continuar.',
        'bloquea_fase_2': True,
        'bloquea_saia': True,
    },
    'EXTENSION_NO_COINCIDE': {
        'severidad_error': 'ALTA',
        'mensaje_usuario': 'La extensión del archivo no coincide con su contenido real.',
        'accion_recomendada': 'Verifica si el archivo fue renombrado de forma incorrecta.',
        'bloquea_fase_2': True,
        'bloquea_saia': True,
    },
    'FORMATO_NO_SOPORTADO': {
        'severidad_error': 'MEDIA',
        'mensaje_usuario': 'El tipo de archivo no es compatible con el proceso documental.',
        'accion_recomendada': 'Usa un archivo PDF, JPG, PNG o TIFF.',
        'bloquea_fase_2': True,
        'bloquea_saia': True,
    },
    'NOMBRE_NO_RECONOCIDO': {
        'severidad_error': 'MEDIA',
        'mensaje_usuario': 'No se pudo identificar el consecutivo PEL desde el nombre del archivo.',
        'accion_recomendada': 'Revisa que el nombre tenga un formato como PEL 97372, PEL 97372 -1 o PEL 97574 TOMO 1-1.',
        'bloquea_fase_2': True,
        'bloquea_saia': True,
    },
    'OK_DETECTADO': {
        'severidad_error': 'BAJA',
        'mensaje_usuario': 'El archivo ya tiene OK en el nombre.',
        'accion_recomendada': 'No se volverá a cargar en SAIA. Verifica solo si el OK fue agregado por error.',
        'bloquea_fase_2': False,
        'bloquea_saia': True,
    },
    'FALTANTE_PEL_BASE': {
        'severidad_error': 'ALTA',
        'mensaje_usuario': 'Falta un consecutivo PEL en la secuencia.',
        'accion_recomendada': 'Busca el consecutivo faltante en la carpeta principal o en la carpeta 245 antes de continuar.',
        'bloquea_fase_2': True,
        'bloquea_saia': True,
    },
    'FALTA_PRINCIPAL_SUBPARTE': {
        'severidad_error': 'ALTA',
        'mensaje_usuario': 'Se encontró una subparte, pero falta el documento principal.',
        'accion_recomendada': 'Busca el archivo con terminación -1 antes de procesar las demás subpartes.',
        'bloquea_fase_2': True,
        'bloquea_saia': True,
    },
    'FALTANTE_SUBPARTE': {
        'severidad_error': 'ALTA',
        'mensaje_usuario': 'Falta una subparte intermedia del documento.',
        'accion_recomendada': 'Verifica que estén todas las partes del PEL antes de continuar.',
        'bloquea_fase_2': True,
        'bloquea_saia': True,
    },
    'FALTA_TOMO_INICIAL': {
        'severidad_error': 'ALTA',
        'mensaje_usuario': 'Falta el primer tomo del grupo documental.',
        'accion_recomendada': 'Busca el tomo inicial antes de procesar el grupo documental.',
        'bloquea_fase_2': True,
        'bloquea_saia': True,
    },
    'FALTANTE_TOMO': {
        'severidad_error': 'ALTA',
        'mensaje_usuario': 'Falta un tomo dentro del grupo documental.',
        'accion_recomendada': 'Verifica que todos los tomos del PEL estén disponibles antes de continuar.',
        'bloquea_fase_2': True,
        'bloquea_saia': True,
    },
    'FALTA_PARTE_INICIAL': {
        'severidad_error': 'ALTA',
        'mensaje_usuario': 'Falta la primera parte de un tomo.',
        'accion_recomendada': 'Busca la parte inicial del tomo antes de procesar el grupo documental.',
        'bloquea_fase_2': True,
        'bloquea_saia': True,
    },
    'FALTANTE_PARTE_TOMO': {
        'severidad_error': 'ALTA',
        'mensaje_usuario': 'Falta una parte dentro de un tomo.',
        'accion_recomendada': 'Busca la parte faltante del tomo antes de procesar el grupo documental.',
        'bloquea_fase_2': True,
        'bloquea_saia': True,
    },
    'CAMBIO_DE_RANGO': {
        'severidad_error': 'MEDIA',
        'mensaje_usuario': 'Se detectó un cambio grande en la secuencia de consecutivos.',
        'accion_recomendada': 'Confirma si el salto corresponde a un cambio real de rango documental.',
        'bloquea_fase_2': False,
        'bloquea_saia': False,
    },
    'DUPLICADO_LOTE': {
        'severidad_error': 'MEDIA',
        'mensaje_usuario': 'Este documento aparece repetido dentro del mismo lote.',
        'accion_recomendada': 'Verifica cuál archivo corresponde conservar y cuál debe quedar solo como referencia.',
        'bloquea_fase_2': True,
        'bloquea_saia': True,
    },
    'DUPLICADO_HISTORICO': {
        'severidad_error': 'BAJA',
        'mensaje_usuario': 'Este documento ya fue inventariado en un lote anterior.',
        'accion_recomendada': 'Verifica si estás reexplorando la misma carpeta o si se trata de una copia repetida.',
        'bloquea_fase_2': False,
        'bloquea_saia': False,
    },
    'DUPLICADO_HISTORICO_SIN_CARGA_SAIA': {
        'severidad_error': 'MEDIA',
        'mensaje_usuario': 'El documento fue encontrado en un lote anterior, pero no hay evidencia de que haya sido cargado exitosamente en SAIA.',
        'accion_recomendada': 'Revise el lote anterior o el historial de SAIA. Si confirma que no fue cargado, reproceselo o carguelo manualmente. No lo cargue dos veces sin verificar.',
        'bloquea_fase_2': True,
        'bloquea_saia': True,
    },
    'YA_CARGADO_SAIA': {
        'severidad_error': 'ALTA',
        'mensaje_usuario': 'Este documento ya fue cargado exitosamente en SAIA.',
        'accion_recomendada': 'No debe cargarse nuevamente. Consulta el lote anterior si necesitas evidencia.',
        'bloquea_fase_2': False,
        'bloquea_saia': True,
    },
    'YA_CARGADO_SAIA_HISTORICO': {
        'severidad_error': 'ALTA',
        'mensaje_usuario': 'Este documento ya tiene evidencia historica de carga exitosa en SAIA.',
        'accion_recomendada': 'No debe cargarse nuevamente. Revisa el lote, documento e intento historico reportado.',
        'bloquea_fase_2': False,
        'bloquea_saia': True,
    },
    'CARPETA_ORIGEN_NO_EXISTE': {
        'severidad_error': 'ALTA',
        'mensaje_usuario': 'La carpeta origen no existe o no se puede abrir.',
        'accion_recomendada': 'Verifica la ruta de la carpeta y vuelve a ejecutar la exploración.',
        'bloquea_fase_2': True,
        'bloquea_saia': True,
    },
    'CARPETA_SECUNDARIA_NO_CONFIGURADA': {
        'severidad_error': 'MEDIA',
        'mensaje_usuario': 'Hay faltantes, pero no se configuró carpeta secundaria para buscarlos.',
        'accion_recomendada': 'Ejecuta la exploración indicando la carpeta 245 si necesitas recuperar faltantes.',
        'bloquea_fase_2': True,
        'bloquea_saia': True,
    },
    'CARPETA_SECUNDARIA_NO_ACCESIBLE': {
        'severidad_error': 'ALTA',
        'mensaje_usuario': 'La carpeta secundaria no se pudo abrir.',
        'accion_recomendada': 'Verifica que la ruta exista y que tengas permisos de lectura.',
        'bloquea_fase_2': True,
        'bloquea_saia': True,
    },
    'PDF_PESADO_SAIA': {
        'severidad_error': 'ADVERTENCIA',
        'mensaje_usuario': 'El PDF es pesado y puede tardar mas en cargarse en SAIA, pero no bloquea la carga automatica.',
        'accion_recomendada': 'Continue con la carga. No cierre el navegador. Si SAIA tarda en confirmar, espere o verifique manualmente antes de reintentar.',
        'bloquea_fase_2': False,
        'bloquea_saia': False,
        'advertencia': True,
        'requiere_timeout_extendido': True,
    },
    'PDF_SUPERA_LIMITE_SAIA': {
        'severidad_error': 'ADVERTENCIA',
        'mensaje_usuario': 'El PDF es pesado y puede tardar mas en cargarse en SAIA, pero no bloquea la carga automatica.',
        'accion_recomendada': 'Continue con la carga. No cierre el navegador. Si SAIA tarda en confirmar, espere o verifique manualmente antes de reintentar.',
        'bloquea_fase_2': False,
        'bloquea_saia': False,
        'advertencia': True,
        'requiere_timeout_extendido': True,
    },
    'NOMBRE_PEL_AMBIGUO': {
        'severidad_error': 'ALTA',
        'mensaje_usuario': 'El nombre del archivo PEL es ambiguo o contiene sufijos no reconocidos.',
        'accion_recomendada': 'Revisa y confirma manualmente el consecutivo antes de procesar el documento.',
        'bloquea_fase_2': True,
        'bloquea_saia': True,
    },
    'PEL_SIMPLE_Y_SUBPARTE_1_CONFLICTO': {
        'severidad_error': 'ALTA',
        'mensaje_usuario': 'Existe conflicto entre un PEL simple y su subparte 1 en el mismo lote.',
        'accion_recomendada': 'Confirma si ambos archivos son equivalentes o si uno debe excluirse antes de continuar.',
        'bloquea_fase_2': True,
        'bloquea_saia': True,
    },
    'CARACTERES_NO_COMPATIBLES_SAIA': {
        'severidad_error': 'MEDIA',
        'mensaje_usuario': 'El nombre del archivo contiene caracteres que pueden fallar en SAIA.',
        'accion_recomendada': 'Renombra el archivo o confirma manualmente que SAIA acepta esos caracteres.',
        'bloquea_fase_2': False,
        'bloquea_saia': True,
    },
    'DUPLICADO_RUTA_NORMALIZADA': {
        'severidad_error': 'MEDIA',
        'mensaje_usuario': 'El archivo aparece duplicado al normalizar la ruta.',
        'accion_recomendada': 'Verifica si se trata del mismo archivo referenciado con una ruta equivalente.',
        'bloquea_fase_2': False,
        'bloquea_saia': True,
    },
    'EXTENSION_DOBLE_O_SOSPECHOSA': {
        'severidad_error': 'ALTA',
        'mensaje_usuario': 'El archivo tiene una extension doble o sospechosa.',
        'accion_recomendada': 'Confirma el tipo real del archivo y reemplazalo por un PDF valido si corresponde.',
        'bloquea_fase_2': True,
        'bloquea_saia': True,
    },
    'CONSECUTIVO_NOMBRE_NO_COINCIDE_CONTENIDO': {
        'severidad_error': 'ALTA',
        'mensaje_usuario': 'El consecutivo del nombre no coincide con el consecutivo leido en el PDF.',
        'accion_recomendada': 'Compara el PDF contra el nombre del archivo y corrige el caso antes de cargarlo.',
        'bloquea_fase_2': True,
        'bloquea_saia': True,
    },
    'FALTANTE_SUBPARTE_NO_ENCONTRADO': {
        'severidad_error': 'ALTA',
        'mensaje_usuario': 'Falta una subparte y no fue encontrada en la carpeta secundaria.',
        'accion_recomendada': 'Busca la subparte faltante antes de procesar el grupo documental.',
        'bloquea_fase_2': True,
        'bloquea_saia': True,
    },
    'FALTANTE_PARTE_TOMO_NO_ENCONTRADO': {
        'severidad_error': 'ALTA',
        'mensaje_usuario': 'Falta una parte de tomo y no fue encontrada en la carpeta secundaria.',
        'accion_recomendada': 'Busca la parte faltante del tomo antes de procesar el grupo documental.',
        'bloquea_fase_2': True,
        'bloquea_saia': True,
    },
}


DEFAULT_PHASE3_ERROR = {
    'codigo_error_usuario': '',
    'fase_error': PHASE_3,
    'severidad_error': '',
    'mensaje_usuario': '',
    'accion_recomendada': '',
    'bloquea_relacion': False,
    'bloquea_saia': False,
}


PHASE3_ERROR_MESSAGES = {
    'PRINCIPAL_NO_ENCONTRADO': {
        'severidad_error': 'ALTA',
        'mensaje_usuario': 'No se encontro el documento principal del grupo PEL.',
        'accion_recomendada': 'Busque el archivo principal, por ejemplo PEL 97372 - 1 o PEL 97574 TOMO 1-1, antes de continuar.',
        'bloquea_relacion': True,
        'bloquea_saia': True,
    },
    'PRINCIPALES_MULTIPLES': {
        'severidad_error': 'ALTA',
        'mensaje_usuario': 'Se encontraron varios documentos que podrian ser el principal del grupo.',
        'accion_recomendada': 'Revise manualmente cual documento debe quedar como principal antes de continuar.',
        'bloquea_relacion': True,
        'bloquea_saia': True,
    },
    'SUBPARTE_HUERFANA': {
        'severidad_error': 'ALTA',
        'mensaje_usuario': 'Se encontro una subparte, pero falta el documento principal.',
        'accion_recomendada': 'Busque el archivo con terminacion -1 antes de relacionar automaticamente.',
        'bloquea_relacion': True,
        'bloquea_saia': True,
    },
    'TOMO_PRINCIPAL_FALTANTE': {
        'severidad_error': 'ALTA',
        'mensaje_usuario': 'Se encontraron tomos o partes, pero falta TOMO 1-1.',
        'accion_recomendada': 'Busque TOMO 1-1 antes de relacionar automaticamente.',
        'bloquea_relacion': True,
        'bloquea_saia': True,
    },
    'DOCUMENTO_SIN_METADATA': {
        'severidad_error': 'ALTA',
        'mensaje_usuario': 'El documento no tiene metadata de Fase 2.',
        'accion_recomendada': 'Ejecute Fase 2 para extraer y normalizar la metadata antes de relacionar.',
        'bloquea_relacion': True,
        'bloquea_saia': True,
    },
    'DOCUMENTO_EN_REVISION': {
        'severidad_error': 'ALTA',
        'mensaje_usuario': 'El documento requiere revision y no puede relacionarse automaticamente.',
        'accion_recomendada': 'Revise y corrija la metadata antes de ejecutar relaciones.',
        'bloquea_relacion': True,
        'bloquea_saia': True,
    },
    'NOMBRE_PEL_AMBIGUO': {
        'severidad_error': 'ALTA',
        'mensaje_usuario': 'El nombre del archivo no permite identificar con seguridad la relacion documental.',
        'accion_recomendada': 'Revise si pertenece a otro expediente o si debe cargarse manualmente.',
        'bloquea_relacion': True,
        'bloquea_saia': True,
    },
    'DOCUMENTO_OK_OMITIDO': {
        'severidad_error': 'BAJA',
        'mensaje_usuario': 'El archivo ya tiene OK en el nombre y se considera cargado previamente.',
        'accion_recomendada': 'No lo relacione ni lo cargue nuevamente en SAIA salvo que el OK haya sido agregado por error.',
        'bloquea_relacion': False,
        'bloquea_saia': False,
    },
    'ESTADO_NO_PERMITIDO': {
        'severidad_error': 'MEDIA',
        'mensaje_usuario': 'El estado del documento no permite relacionarlo automaticamente.',
        'accion_recomendada': 'Verifique el estado del documento y confirme si debe reprocesarse o excluirse.',
        'bloquea_relacion': True,
        'bloquea_saia': True,
    },

    'TOMO_SECUENCIA_INCOMPLETA': {
        'severidad_error': 'MEDIA',
        'mensaje_usuario': 'Los tomos del documento no forman una secuencia completa o clara.',
        'accion_recomendada': 'Revise manualmente los tomos y confirme si falta una parte intermedia.',
        'bloquea_relacion': True,
        'bloquea_saia': True,
    },
    'SECUENCIA_INCOMPLETA_ADVERTENCIA': {
        'severidad_error': 'ADVERTENCIA',
        'mensaje_usuario': 'Se detecto una posible secuencia incompleta.',
        'accion_recomendada': 'Revise si faltan partes del expediente antes de cargar en SAIA.',
        'bloquea_relacion': False,
        'bloquea_saia': False,
    },
    'CONFIANZA_RELACION_BAJA': {
        'severidad_error': 'MEDIA',
        'mensaje_usuario': 'La relacion fue evaluada, pero la confianza calculada es menor al minimo requerido.',
        'accion_recomendada': 'Revise manualmente la relacion antes de continuar.',
        'bloquea_relacion': True,
        'bloquea_saia': True,
    },
    'CONFIANZA_NO_CALCULADA': {
        'severidad_error': 'MEDIA',
        'mensaje_usuario': 'No se pudo calcular la confianza de la relacion documental por informacion incompleta.',
        'accion_recomendada': 'Revise el grupo documental antes de continuar.',
        'bloquea_relacion': True,
        'bloquea_saia': True,
    },
    'METADATA_RELACION_INSUFICIENTE': {
        'severidad_error': 'MEDIA',
        'mensaje_usuario': 'La metadata disponible no es suficiente para calcular la relacion documental.',
        'accion_recomendada': 'Revise la metadata PEL, cruce y consecutivo antes de relacionar.',
        'bloquea_relacion': True,
        'bloquea_saia': True,
    },
    'FAMILIA_PEL_NO_CONFIABLE': {
        'severidad_error': 'MEDIA',
        'mensaje_usuario': 'No se pudo confirmar que los documentos pertenezcan a la misma familia PEL.',
        'accion_recomendada': 'Revise el nombre de los archivos y la identidad documental generada en Fase 2.',
        'bloquea_relacion': True,
        'bloquea_saia': True,
    },
    'DATOS_PEL_INCOMPLETOS': {
        'severidad_error': 'MEDIA',
        'mensaje_usuario': 'La metadata PEL estructurada esta incompleta.',
        'accion_recomendada': 'Vuelva a ejecutar Fase 2 para generar datos_pel antes de relacionar.',
        'bloquea_relacion': True,
        'bloquea_saia': True,
    },
    'RELACION_DUPLICADA': {
        'severidad_error': 'BAJA',
        'mensaje_usuario': 'La relacion documental ya existe.',
        'accion_recomendada': 'Use --recrear si necesita recalcular las relaciones del lote.',
        'bloquea_relacion': False,
        'bloquea_saia': False,
    },
    'GRUPO_SIN_RELACION_AUTOMATICA': {
        'severidad_error': 'MEDIA',
        'mensaje_usuario': 'El grupo documental no tiene suficiente informacion para relacionarse automaticamente.',
        'accion_recomendada': 'Revise manualmente el grupo y confirme la relacion si corresponde.',
        'bloquea_relacion': True,
        'bloquea_saia': True,
    },
    'ERROR_TECNICO_RELACION': {
        'severidad_error': 'ALTA',
        'mensaje_usuario': 'Ocurrio un error tecnico durante la relacion documental.',
        'accion_recomendada': 'Revise el detalle tecnico o solicite apoyo del equipo de desarrollo.',
        'bloquea_relacion': True,
        'bloquea_saia': True,
    },
}


def build_phase3_error_message(error_tecnico='', contexto=None):
    context = contexto or {}
    code = classify_phase3_error(error_tecnico, context)
    if not code:
        result = DEFAULT_PHASE3_ERROR.copy()
        result['error_tecnico'] = error_tecnico or ''
        return result

    result = DEFAULT_PHASE3_ERROR.copy()
    result.update(PHASE3_ERROR_MESSAGES[code])
    result['codigo_error_usuario'] = code
    result['fase_error'] = PHASE_3
    if code in PHASE3_MANUAL_REVIEW_CODES:
        result['accion_recomendada'] = _append_guidance(
            result.get('accion_recomendada', ''),
            PHASE3_MANUAL_GUIDANCE,
        )
    result['error_tecnico'] = error_tecnico or _phase3_context_text(context)
    return result


def classify_phase3_error(error_tecnico='', contexto=None):
    context = contexto or {}
    text = normalize_error_text(error_tecnico)
    context_text = normalize_error_text(_phase3_context_text(context))
    combined = f'{text}; {context_text}'
    relation_evaluated = _phase3_relation_was_evaluated(context, combined)

    explicit_code = context.get('codigo_error') or context.get('codigo_error_usuario')
    if explicit_code in PHASE3_ERROR_MESSAGES:
        return explicit_code

    if 'varios documentos principales' in combined or 'multiples principales' in combined:
        return 'PRINCIPALES_MULTIPLES'
    if 'subparte' in combined and ('falta el documento principal' in combined or 'falta -1' in combined):
        return 'SUBPARTE_HUERFANA'
    if 'tomo 1-1' in combined and ('falta' in combined or 'principal faltante' in combined):
        return 'TOMO_PRINCIPAL_FALTANTE'
    if 'no existe documento principal' in combined or 'sin documento principal' in combined:
        return 'PRINCIPAL_NO_ENCONTRADO'
    if 'nombre pel ambiguo' in combined or 'sufijos no reconocidos' in combined:
        return 'NOMBRE_PEL_AMBIGUO'
    if 'nombre contiene ok' in combined:
        return 'DOCUMENTO_OK_OMITIDO'
    if context.get('codigo_error') == 'SECUENCIA_INCOMPLETA_ADVERTENCIA':
        return 'SECUENCIA_INCOMPLETA_ADVERTENCIA'
    if 'tomo' in combined and ('secuencia' in combined or 'parte intermedia' in combined or 'incompleta' in combined):
        return 'TOMO_SECUENCIA_INCOMPLETA'

    if relation_evaluated and _has_phase3_numeric_confidence(context):
        if _safe_float(context.get('confianza')) < 80:
            return 'CONFIANZA_RELACION_BAJA'
    elif relation_evaluated and 'confianza' in combined and ('no calculada' in combined or 'confianza=' in combined):
        return 'CONFIANZA_NO_CALCULADA'
    elif relation_evaluated and 'confianza' in combined and ('menor' in combined or 'baja' in combined):
        parsed_confidence = _extract_phase3_confidence(combined)
        if parsed_confidence is not None and parsed_confidence < 80:
            return 'CONFIANZA_RELACION_BAJA'
        return 'CONFIANZA_NO_CALCULADA'
    if relation_evaluated and 'metadata' in combined and 'insuficiente' in combined:
        return 'METADATA_RELACION_INSUFICIENTE'
    if relation_evaluated and 'no se pudo calcular' in combined and 'relacion' in combined:
        return 'CONFIANZA_NO_CALCULADA'
    if relation_evaluated and context.get('confianza') in ('', None) and 'confianza' in combined:
        return 'CONFIANZA_NO_CALCULADA'
    if relation_evaluated and context.get('confianza') is not None and not _has_phase3_numeric_confidence(context):
        return 'CONFIANZA_NO_CALCULADA'
    if 'familia pel' in combined and ('no confiable' in combined or 'no se pudo confirmar' in combined):
        return 'FAMILIA_PEL_NO_CONFIABLE'
    if 'relacion documental ya existe' in combined or 'duplicada' in combined:
        return 'RELACION_DUPLICADA'

    if relation_evaluated and _has_phase3_numeric_confidence(context) and _safe_float(context.get('confianza')) < 80:
        return 'CONFIANZA_RELACION_BAJA'
    if 'sin relacion automatica' in combined:
        return 'GRUPO_SIN_RELACION_AUTOMATICA'
    if relation_evaluated:
        if 'sin metadata' in combined or 'no tiene metadata' in combined:
            return 'DOCUMENTO_SIN_METADATA'
        if 'requiere revision' in combined:
            return 'DOCUMENTO_EN_REVISION'
        if 'estado no permitido' in combined:
            return 'ESTADO_NO_PERMITIDO'
        if 'datos_pel' in combined and ('incomplet' in combined or 'vacio' in combined):
            return 'DATOS_PEL_INCOMPLETOS'
        return 'ERROR_TECNICO_RELACION' if context.get('exception') else 'GRUPO_SIN_RELACION_AUTOMATICA'
    return ''


def get_phase3_recommended_action(codigo_error, contexto=None):
    return PHASE3_ERROR_MESSAGES.get(codigo_error, {}).get('accion_recomendada', '')


def is_phase3_blocking_error(codigo_error):
    data = PHASE3_ERROR_MESSAGES.get(codigo_error, {})
    return bool(data.get('bloquea_relacion') or data.get('bloquea_saia'))


DEFAULT_PHASE4_ERROR = {
    'codigo_error_usuario': '',
    'fase_error': PHASE_4,
    'severidad_error': '',
    'mensaje_usuario': '',
    'accion_recomendada': '',
    'bloquea_validacion': False,
    'bloquea_saia': False,
}


PHASE4_ERROR_MESSAGES = {
    'ARCHIVO_FISICO_NO_EXISTE': {
        'severidad_error': 'ALTA',
        'mensaje_usuario': 'No se puede cargar en SAIA porque el archivo fisico ya no existe en la ruta registrada.',
        'accion_recomendada': 'Confirma que el archivo no haya sido movido o eliminado y vuelve a validar.',
        'bloquea_validacion': True,
        'bloquea_saia': True,
    },
    'ARCHIVO_NO_PDF': {
        'severidad_error': 'ALTA',
        'mensaje_usuario': 'No se puede cargar en SAIA porque el archivo no es PDF.',
        'accion_recomendada': 'Reemplaza o convierte el archivo a PDF antes de continuar.',
        'bloquea_validacion': True,
        'bloquea_saia': True,
    },
    'PDF_VACIO': {
        'severidad_error': 'ALTA',
        'mensaje_usuario': 'El PDF esta vacio y no puede cargarse en SAIA.',
        'accion_recomendada': 'Solicita una nueva copia del PDF antes de cargarlo.',
        'bloquea_validacion': True,
        'bloquea_saia': True,
    },
    'PDF_PESADO_SAIA': {
        'severidad_error': 'ADVERTENCIA',
        'mensaje_usuario': 'El PDF es pesado y puede tardar mas en cargarse en SAIA, pero no bloquea la carga automatica.',
        'accion_recomendada': 'Continue con la carga. No cierre el navegador. Si SAIA tarda en confirmar, espere o verifique manualmente antes de reintentar.',
        'bloquea_validacion': False,
        'bloquea_saia': False,
        'advertencia': True,
        'requiere_timeout_extendido': True,
    },
    'PDF_SUPERA_LIMITE_SAIA': {
        'severidad_error': 'ADVERTENCIA',
        'mensaje_usuario': 'El PDF es pesado y puede tardar mas en cargarse en SAIA, pero no bloquea la carga automatica.',
        'accion_recomendada': 'Continue con la carga. No cierre el navegador. Si SAIA tarda en confirmar, espere o verifique manualmente antes de reintentar.',
        'bloquea_validacion': False,
        'bloquea_saia': False,
        'advertencia': True,
        'requiere_timeout_extendido': True,
    },
    'ARCHIVO_BLOQUEADO': {
        'severidad_error': 'MEDIA',
        'mensaje_usuario': 'El archivo parece estar bloqueado o no se puede leer.',
        'accion_recomendada': 'Cierra el archivo si esta abierto, verifica permisos y vuelve a validar.',
        'bloquea_validacion': True,
        'bloquea_saia': True,
    },
    'PDF_CORRUPTO': {
        'severidad_error': 'ALTA',
        'mensaje_usuario': 'No se puede cargar en SAIA porque el PDF esta corrupto o tiene encabezado invalido.',
        'accion_recomendada': 'Reemplaza el PDF por una copia valida antes de cargarlo.',
        'bloquea_validacion': True,
        'bloquea_saia': True,
    },
    'FORMATO_NO_SOPORTADO': {
        'severidad_error': 'ALTA',
        'mensaje_usuario': 'El documento tiene un formato no soportado para SAIA.',
        'accion_recomendada': 'Usa un PDF valido y vuelve a ejecutar la validacion.',
        'bloquea_validacion': True,
        'bloquea_saia': True,
    },
    'DOCUMENTO_DUPLICADO': {
        'severidad_error': 'MEDIA',
        'mensaje_usuario': 'El documento esta marcado como duplicado dentro del lote.',
        'accion_recomendada': 'Verifica cual copia debe conservarse antes de cargar en SAIA.',
        'bloquea_validacion': True,
        'bloquea_saia': True,
    },
    'OK_DETECTADO': {
        'severidad_error': 'BAJA',
        'mensaje_usuario': 'El archivo ya tiene OK en el nombre.',
        'accion_recomendada': 'No lo cargues nuevamente en SAIA salvo que el OK haya sido agregado por error.',
        'bloquea_validacion': True,
        'bloquea_saia': True,
    },
    'ESTADO_NO_PERMITIDO_SAIA': {
        'severidad_error': 'MEDIA',
        'mensaje_usuario': 'No se puede cargar en SAIA porque el documento no esta en estado VALIDADO o RELACIONADO.',
        'accion_recomendada': 'Completa las fases pendientes o corrige la revision antes de validar de nuevo.',
        'bloquea_validacion': True,
        'bloquea_saia': True,
    },
    'DOCUMENTO_SIN_METADATA': {
        'severidad_error': 'ALTA',
        'mensaje_usuario': 'El documento no tiene metadata extraida.',
        'accion_recomendada': 'Ejecuta Fase 2 antes de validar para SAIA.',
        'bloquea_validacion': True,
        'bloquea_saia': True,
    },
    'METADATA_REQUIERE_REVISION': {
        'severidad_error': 'ALTA',
        'mensaje_usuario': 'No se puede cargar en SAIA porque la metadata requiere revision manual.',
        'accion_recomendada': 'Corrige o aprueba la metadata desde Revision Manual antes de cargar.',
        'bloquea_validacion': True,
        'bloquea_saia': True,
    },
    'DATOS_PEL_INCOMPLETOS': {
        'severidad_error': 'ALTA',
        'mensaje_usuario': 'La metadata PEL estructurada esta incompleta para SAIA.',
        'accion_recomendada': 'Vuelve a ejecutar Fase 2 o corrige datos_pel antes de validar.',
        'bloquea_validacion': True,
        'bloquea_saia': True,
    },
    'CONSECUTIVO_NO_NORMALIZABLE': {
        'severidad_error': 'ALTA',
        'mensaje_usuario': 'No se puede cargar en SAIA porque el consecutivo PEL no se pudo normalizar.',
        'accion_recomendada': 'Corrige el consecutivo del documento o el nombre del archivo.',
        'bloquea_validacion': True,
        'bloquea_saia': True,
    },
    'CONSECUTIVO_NO_COINCIDE_NOMBRE': {
        'severidad_error': 'ALTA',
        'mensaje_usuario': 'No se puede cargar en SAIA porque el consecutivo validado no coincide con el nombre del archivo.',
        'accion_recomendada': 'Compara el PDF, la metadata y el nombre antes de cargarlo en SAIA.',
        'bloquea_validacion': True,
        'bloquea_saia': True,
    },
    'SOPORTES_ESTADO_INVALIDO': {
        'severidad_error': 'ALTA',
        'mensaje_usuario': 'No se puede cargar en SAIA porque uno o mas soportes relacionados estan pendientes o con error.',
        'accion_recomendada': 'Corrige los soportes relacionados antes de cargar el documento principal.',
        'bloquea_validacion': True,
        'bloquea_saia': True,
    },
    'YA_CARGADO_SAIA': {
        'severidad_error': 'ALTA',
        'mensaje_usuario': 'El documento ya tiene una carga exitosa registrada en SAIA.',
        'accion_recomendada': 'No lo cargues nuevamente. Consulta el intento exitoso anterior.',
        'bloquea_validacion': True,
        'bloquea_saia': True,
    },
    'DUPLICADO_HISTORICO_SAIA': {
        'severidad_error': 'ALTA',
        'mensaje_usuario': 'Existe evidencia historica de carga exitosa en SAIA.',
        'accion_recomendada': 'No lo cargues nuevamente. Revisa la evidencia historica reportada.',
        'bloquea_validacion': True,
        'bloquea_saia': True,
    },
    'RUTA_SAIA_NO_DETECTADA': {
        'severidad_error': 'ALTA',
        'mensaje_usuario': 'No se pudo determinar la ruta SAIA para este documento.',
        'accion_recomendada': 'Revise el identificador del archivo o la metadata y seleccione la ruta correcta antes de cargar.',
        'bloquea_validacion': True,
        'bloquea_saia': True,
    },
    'RUTA_SAIA_NO_CONFIGURADA': {
        'severidad_error': 'ALTA',
        'mensaje_usuario': 'La ruta SAIA detectada no esta configurada en el sistema.',
        'accion_recomendada': 'Solicite configurar la ruta SAIA antes de reintentar la carga automatica.',
        'bloquea_validacion': True,
        'bloquea_saia': True,
    },
}


def build_phase4_error_message(error_tecnico='', contexto=None):
    context = contexto or {}
    code = classify_phase4_error(error_tecnico, context)
    if not code:
        result = DEFAULT_PHASE4_ERROR.copy()
        result['error_tecnico'] = error_tecnico or ''
        return result

    result = DEFAULT_PHASE4_ERROR.copy()
    result.update(PHASE4_ERROR_MESSAGES[code])
    result['codigo_error_usuario'] = code
    result['fase_error'] = PHASE_4
    if code in PHASE4_MANUAL_REVIEW_CODES:
        result['accion_recomendada'] = _append_guidance(
            result.get('accion_recomendada', ''),
            PHASE4_MANUAL_GUIDANCE,
        )
    result['error_tecnico'] = error_tecnico or _phase4_context_text(context)
    return result


def classify_phase4_error(error_tecnico='', contexto=None):
    context = contexto or {}
    text = normalize_error_text(error_tecnico)
    context_text = normalize_error_text(_phase4_context_text(context))
    combined = f'{text}; {context_text}'
    explicit_code = context.get('codigo_error') or context.get('codigo_error_usuario')
    if explicit_code in PHASE4_ERROR_MESSAGES:
        return explicit_code

    if 'archivo fisico no existe' in combined or 'no existe el archivo local' in combined:
        return 'ARCHIVO_FISICO_NO_EXISTE'
    if 'debe ser pdf' in combined or 'archivo para saia debe ser pdf' in combined:
        return 'ARCHIVO_NO_PDF'
    if 'pdf esta vacio' in combined or 'pdf esta vacío' in combined:
        return 'PDF_VACIO'
    if 'pdf_pesado_saia' in combined or 'pdf pesado' in combined:
        return 'PDF_PESADO_SAIA'
    if 'supera el limite de tamano' in combined or 'supera el limite de tamaño' in combined:
        return 'PDF_PESADO_SAIA'
    if 'bloqueado' in combined or 'no se puede leer' in combined:
        return 'ARCHIVO_BLOQUEADO'
    if 'pdf esta corrupto' in combined or 'encabezado invalido' in combined or 'encabezado inválido' in combined:
        return 'PDF_CORRUPTO'
    if 'formato no soportado' in combined:
        return 'FORMATO_NO_SOPORTADO'
    if 'documento duplicado' in combined:
        return 'DOCUMENTO_DUPLICADO'
    if 'nombre contiene ok' in combined or 'archivo omitido porque el nombre contiene ok' in combined:
        return 'OK_DETECTADO'
    if 'estado no permitido para saia' in combined:
        return 'ESTADO_NO_PERMITIDO_SAIA'
    if 'documento sin metadata' in combined:
        return 'DOCUMENTO_SIN_METADATA'
    if 'metadata marcada como requiere_revision' in combined or 'metadata requiere revision' in combined:
        return 'METADATA_REQUIERE_REVISION'
    if 'datos_pel incompleta' in combined or 'datos_pel incompleto' in combined or 'metadata sin datos_pel' in combined:
        return 'DATOS_PEL_INCOMPLETOS'
    if 'no normalizable para saia' in combined or 'no se pudo normalizar el consecutivo' in combined:
        return 'CONSECUTIVO_NO_NORMALIZABLE'
    if 'no coincide con nombre' in combined or 'consecutivo del documento no coincide' in combined:
        return 'CONSECUTIVO_NO_COINCIDE_NOMBRE'
    if 'soportes en estado invalido' in combined or 'soportes en estado inválido' in combined:
        return 'SOPORTES_ESTADO_INVALIDO'
    if 'ya tiene carga exitosa registrada en saia' in combined:
        return 'YA_CARGADO_SAIA'
    if 'cargado exitosamente a saia en historico' in combined or 'historico documental' in combined:
        return 'DUPLICADO_HISTORICO_SAIA'
    if 'no se pudo determinar la ruta saia' in combined:
        return 'RUTA_SAIA_NO_DETECTADA'
    if 'ruta saia' in combined and 'no esta configurada' in combined:
        return 'RUTA_SAIA_NO_CONFIGURADA'
    return ''


DEFAULT_PHASE5_ERROR = {
    'codigo_error_usuario': '',
    'fase_error': PHASE_5,
    'severidad_error': '',
    'mensaje_usuario': '',
    'accion_recomendada': '',
    'reintentable': False,
    'detener_lote': False,
    'requiere_intervencion_usuario': False,
    'requiere_timeout_extendido': False,
}


PHASE5_ERROR_MESSAGES = {
    'CREDENCIALES_SAIA_INVALIDAS': {
        'severidad_error': 'ALTA',
        'mensaje_usuario': 'No fue posible iniciar sesion en SAIA.',
        'accion_recomendada': 'Verifica credenciales, usuario, clave, permisos y conexion antes de reintentar.',
        'reintentable': False,
        'detener_lote': True,
        'requiere_intervencion_usuario': True,
    },
    'TIMEOUT_SAIA': {
        'severidad_error': 'MEDIA',
        'mensaje_usuario': 'SAIA tardo demasiado en responder.',
        'accion_recomendada': 'Reintenta mas tarde o valida si SAIA esta lento.',
        'reintentable': True,
        'detener_lote': False,
        'requiere_intervencion_usuario': False,
    },
    'SELECTOR_NO_ENCONTRADO': {
        'severidad_error': 'ALTA',
        'mensaje_usuario': 'No se encontro un campo o boton esperado en SAIA.',
        'accion_recomendada': 'Revisa si SAIA cambio la pantalla o solicita ajuste de selectores.',
        'reintentable': True,
        'detener_lote': False,
        'requiere_intervencion_usuario': True,
    },
    'SESION_EXPIRADA': {
        'severidad_error': 'MEDIA',
        'mensaje_usuario': 'La sesion de SAIA expiro o se interrumpio durante la carga.',
        'accion_recomendada': 'Reintenta la carga; si se repite, revisa estabilidad de red o tiempo de sesion.',
        'reintentable': True,
        'detener_lote': False,
        'requiere_intervencion_usuario': False,
    },
    'BROWSER_CERRADO': {
        'severidad_error': 'ALTA',
        'mensaje_usuario': 'El navegador de automatizacion se cerro durante la carga.',
        'accion_recomendada': 'Reinicia el proceso de carga y revisa que Chromium/Playwright esten disponibles.',
        'reintentable': True,
        'detener_lote': False,
        'requiere_intervencion_usuario': True,
    },
    'ERROR_RED_SAIA': {
        'severidad_error': 'MEDIA',
        'mensaje_usuario': 'Hubo un error de red al conectar con SAIA.',
        'accion_recomendada': 'Verifica la conexion a internet o VPN y reintenta.',
        'reintentable': True,
        'detener_lote': False,
        'requiere_intervencion_usuario': False,
    },
    'SAIA_NO_CONFIRMADA': {
        'severidad_error': 'ALTA',
        'mensaje_usuario': 'SAIA no confirmo visualmente la carga del documento.',
        'accion_recomendada': 'Revisa el intento en SAIA antes de reintentar para evitar duplicados.',
        'reintentable': True,
        'detener_lote': False,
        'requiere_intervencion_usuario': True,
    },
    'MARCACION_OK_FALLIDA': {
        'severidad_error': 'MEDIA',
        'mensaje_usuario': 'El documento cargo en SAIA, pero no se pudo marcar OK localmente.',
        'accion_recomendada': 'Verifica permisos/ruta del archivo y marca OK manualmente si corresponde.',
        'reintentable': False,
        'detener_lote': False,
        'requiere_intervencion_usuario': True,
    },
    'LOTE_DETENIDO_ERROR_CRITICO': {
        'severidad_error': 'ALTA',
        'mensaje_usuario': 'El lote fue detenido por un error critico durante la carga SAIA.',
        'accion_recomendada': 'Revisa el error critico, corrige la causa y reanuda el lote.',
        'reintentable': False,
        'detener_lote': True,
        'requiere_intervencion_usuario': True,
    },
    'ERROR_INESPERADO_SAIA': {
        'severidad_error': 'ALTA',
        'mensaje_usuario': 'Ocurrio un error inesperado durante la carga en SAIA.',
        'accion_recomendada': 'Revisa el detalle tecnico y reintenta solo si no hay evidencia de carga duplicada.',
        'reintentable': True,
        'detener_lote': False,
        'requiere_intervencion_usuario': True,
    },
    'SELECTOR_RUTA_SAIA_NO_ENCONTRADO': {
        'severidad_error': 'ALTA',
        'mensaje_usuario': 'SAIA no mostro una opcion esperada de la ruta configurada.',
        'accion_recomendada': 'Revise si la ruta existe en SAIA, si el usuario tiene permisos o si cambio el nombre del agrupador.',
        'reintentable': True,
        'detener_lote': False,
        'requiere_intervencion_usuario': True,
    },
}


def build_phase5_error_message(error_tecnico='', contexto=None):
    context = contexto or {}
    code = classify_phase5_error(error_tecnico, context)
    if not code:
        result = DEFAULT_PHASE5_ERROR.copy()
        result['error_tecnico'] = error_tecnico or ''
        return result

    result = DEFAULT_PHASE5_ERROR.copy()
    result.update(PHASE5_ERROR_MESSAGES[code])
    result['codigo_error_usuario'] = code
    result['fase_error'] = PHASE_5
    if code in PHASE5_MANUAL_REVIEW_CODES:
        result['accion_recomendada'] = _append_guidance(
            result.get('accion_recomendada', ''),
            PHASE5_MANUAL_GUIDANCE,
        )
    if context.get('requiere_timeout_extendido') or 'pdf pesado' in normalize_error_text(error_tecnico):
        result['mensaje_usuario'] = 'SAIA tardo mas de lo esperado cargando un PDF pesado.'
        result['accion_recomendada'] = (
            'Verifique manualmente si el documento quedo cargado en SAIA antes de reintentar, '
            'para evitar duplicados.'
        )
        result['requiere_intervencion_usuario'] = True
        result['requiere_timeout_extendido'] = True
    result['error_tecnico'] = error_tecnico or _phase5_context_text(context)
    if context.get('detener_lote'):
        result['detener_lote'] = True
    return result


def classify_phase5_error(error_tecnico='', contexto=None):
    context = contexto or {}
    text = normalize_error_text(error_tecnico)
    context_text = normalize_error_text(_phase5_context_text(context))
    combined = f'{text}; {context_text}'
    explicit_code = context.get('codigo_error') or context.get('codigo_error_usuario')
    if explicit_code in PHASE5_ERROR_MESSAGES:
        return explicit_code

    if 'saialoginerror' in combined or 'login' in combined or 'credencial' in combined or 'clave' in combined:
        return 'CREDENCIALES_SAIA_INVALIDAS'
    if 'pdf pesado' in combined and ('tardo' in combined or 'timeout' in combined or 'demorado' in combined):
        return 'TIMEOUT_SAIA'
    if 'timeout' in combined or 'tardo demasiado' in combined:
        return 'TIMEOUT_SAIA'
    if 'ruta saia' in combined and 'no encontrada' in combined:
        return 'SELECTOR_RUTA_SAIA_NO_ENCONTRADO'
    if 'ruta saia' in combined and 'no configurada' in combined:
        return 'SELECTOR_RUTA_SAIA_NO_ENCONTRADO'
    if (
        'selector' in combined
        or 'no se encontro selector' in combined
        or 'no se encontro campo' in combined
        or 'no se pudo encontrar el campo' in combined
        or 'no se pudo seleccionar dependencia' in combined
        or 'dependencia del creador del documento' in combined
    ):
        return 'SELECTOR_NO_ENCONTRADO'
    if 'sesion saia expirada' in combined or 'sesion saia interrumpida' in combined or 'frame detached' in combined or 'stream has ended' in combined:
        return 'SESION_EXPIRADA'
    if 'browser chromium caido' in combined or 'target closed' in combined or 'browser cerrado' in combined:
        return 'BROWSER_CERRADO'
    if 'net::err' in combined or 'error de red' in combined:
        return 'ERROR_RED_SAIA'
    if 'no confirmo carga exitosa' in combined or 'no confirmo visualmente' in combined:
        return 'SAIA_NO_CONFIRMADA'
    if 'renombrar archivo a ok' in combined or 'marcar ok' in combined or 'marcado ok' in combined:
        return 'MARCACION_OK_FALLIDA'
    if 'lote detenido' in combined or context.get('detener_lote'):
        return 'LOTE_DETENIDO_ERROR_CRITICO'
    if error_tecnico or context:
        return 'ERROR_INESPERADO_SAIA'
    return ''


DEFAULT_PHASE2_ERROR = {
    'codigo_error_usuario': '',
    'fase_error': PHASE_2,
    'severidad_error': '',
    'mensaje_usuario': '',
    'accion_recomendada': '',
    'bloquea_fase_3': False,
    'bloquea_saia': False,
}


PHASE2_ERROR_MESSAGES = {
    'OCR_NO_CONFIGURADO': {
        'severidad_error': 'ALTA',
        'mensaje_usuario': 'El OCR no esta configurado correctamente en el equipo.',
        'accion_recomendada': 'Verifica la instalacion de Tesseract y que los idiomas spa y eng esten disponibles antes de procesar documentos escaneados.',
        'bloquea_fase_3': True,
        'bloquea_saia': True,
    },
    'OCR_SIN_TEXTO': {
        'severidad_error': 'ALTA',
        'mensaje_usuario': 'No se obtuvo texto del documento.',
        'accion_recomendada': 'Abre el archivo y confirma que sea legible. Si es un escaneo, vuelve a procesarlo con mejor calidad o revisalo manualmente.',
        'bloquea_fase_3': True,
        'bloquea_saia': True,
    },
    'OCR_TEXTO_INSUFICIENTE': {
        'severidad_error': 'MEDIA',
        'mensaje_usuario': 'El texto extraido es muy corto para validar el documento con seguridad.',
        'accion_recomendada': 'Revisa la calidad del escaneo y confirma manualmente si se alcanzan a leer encabezado, consecutivo y D. Cruce / M. Pago.',
        'bloquea_fase_3': True,
        'bloquea_saia': True,
    },
    'ENCABEZADO_PAGOS_NO_DETECTADO': {
        'severidad_error': 'MEDIA',
        'mensaje_usuario': 'No se detecto el encabezado de Pagos electronicos.',
        'accion_recomendada': 'Verifica si el documento es realmente una factura principal PEL o si el encabezado esta borroso, cortado o en otra pagina.',
        'bloquea_fase_3': False,
        'bloquea_saia': True,
    },
    'PROVEEDOR_EURO_NO_DETECTADO': {
        'severidad_error': 'MEDIA',
        'mensaje_usuario': 'No se detecto INVERSIONES EURO S.A. en el encabezado.',
        'accion_recomendada': 'Confirma visualmente que el encabezado pertenece a INVERSIONES EURO S.A. y que el OCR no haya leido mal el texto.',
        'bloquea_fase_3': False,
        'bloquea_saia': True,
    },
    'CONSECUTIVO_NO_DETECTADO': {
        'severidad_error': 'ALTA',
        'mensaje_usuario': 'No se pudo leer el consecutivo MAY-PEL del documento.',
        'accion_recomendada': 'Verifica manualmente el consecutivo del encabezado y confirma si coincide con el nombre del archivo.',
        'bloquea_fase_3': True,
        'bloquea_saia': True,
    },
    'CONSECUTIVO_INVALIDO': {
        'severidad_error': 'ALTA',
        'mensaje_usuario': 'El consecutivo detectado no tiene el formato esperado MAY-PEL.',
        'accion_recomendada': 'Corrige la lectura o revisa el documento manualmente antes de relacionarlo o cargarlo en SAIA.',
        'bloquea_fase_3': True,
        'bloquea_saia': True,
    },
    'CONSECUTIVO_NO_COINCIDE': {
        'severidad_error': 'ALTA',
        'mensaje_usuario': 'El consecutivo leido dentro del documento no coincide con el nombre del archivo.',
        'accion_recomendada': 'Compara el encabezado del PDF con el nombre del archivo. No cargues el documento hasta confirmar cual consecutivo es correcto.',
        'bloquea_fase_3': True,
        'bloquea_saia': True,
    },
    'IDENTIDAD_DOCUMENTAL_NO_DETECTADA': {
        'severidad_error': 'ALTA',
        'mensaje_usuario': 'No se pudo identificar la identidad documental desde el nombre del archivo.',
        'accion_recomendada': 'Renombra o revisa el archivo con un formato como PEL 97372, PEL 97372 -1 o PEL 97574 TOMO 1-1.',
        'bloquea_fase_3': True,
        'bloquea_saia': True,
    },
    'CONFIANZA_BAJA': {
        'severidad_error': 'MEDIA',
        'mensaje_usuario': 'La extraccion no tiene suficiente confianza para continuar automaticamente.',
        'accion_recomendada': 'Revisa manualmente encabezado, consecutivo y D. Cruce / M. Pago. Si la informacion es correcta, ajusta las reglas de OCR o regex.',
        'bloquea_fase_3': True,
        'bloquea_saia': True,
    },
    'METADATA_AMBIGUA': {
        'severidad_error': 'MEDIA',
        'mensaje_usuario': 'El sistema no pudo validar automaticamente este documento y requiere revision manual.',
        'accion_recomendada': 'Compare el consecutivo que aparece dentro del documento con el numero que figura en el nombre del archivo PDF. Si la informacion es correcta, realice la carga manual en SAIA.',
        'bloquea_fase_3': True,
        'bloquea_saia': True,
    },
}


def build_phase2_error_message(error_tecnico='', contexto=None):
    context = contexto or {}
    code = classify_phase2_error(error_tecnico, context)
    if not code:
        result = DEFAULT_PHASE2_ERROR.copy()
        result['error_tecnico'] = error_tecnico or ''
        return result

    result = DEFAULT_PHASE2_ERROR.copy()
    result.update(PHASE2_ERROR_MESSAGES[code])
    result['codigo_error_usuario'] = code
    result['fase_error'] = PHASE_2
    if _is_retencion_ica_phase2_context(context):
        _apply_retencion_ica_phase2_message(result, code)
    if _is_ecb_phase2_context(context):
        _apply_ecb_phase2_message(result, code)
    if _is_egc_phase2_context(context):
        _apply_egc_phase2_message(result, code)
    if _is_ege_phase2_context(context):
        _apply_ege_phase2_message(result, code)
    if code in PHASE2_MANUAL_REVIEW_CODES:
        result['accion_recomendada'] = _append_guidance(
            result.get('accion_recomendada', ''),
            PHASE2_MANUAL_GUIDANCE,
        )
    result['error_tecnico'] = error_tecnico or _technical_phase2_error_from_context(context, code)
    return result


def _is_retencion_ica_phase2_context(context):
    values = [
        context.get('tipo_documento'),
        context.get('consecutivo'),
        context.get('observaciones_extraccion'),
        context.get('identidad_documental'),
    ]
    datos_pel = context.get('datos_pel') or {}
    values.extend([
        datos_pel.get('retencion_ica_titulo'),
        datos_pel.get('retencion_ica_titulo_documento'),
        datos_pel.get('identidad_documental'),
    ])
    text = normalize_error_text(' '.join(str(value or '') for value in values))
    return 'documento_retencion_ica' in text or 'retencion ica' in text or 'rica-' in text


def _apply_retencion_ica_phase2_message(result, code):
    if code == 'OCR_TEXTO_INSUFICIENTE':
        result['accion_recomendada'] = (
            'Revisa las primeras tres paginas y confirma que se lea el titulo '
            'DECLARACION BIMESTRAL y la fecha o anio del formulario.'
        )
    elif code == 'CONFIANZA_BAJA':
        result['accion_recomendada'] = (
            'Revisa manualmente las primeras tres paginas y confirma el titulo '
            'DECLARACION BIMESTRAL y la fecha o anio.'
        )
    elif code == 'METADATA_AMBIGUA':
        result['accion_recomendada'] = (
            'Confirma manualmente el titulo DECLARACION BIMESTRAL y la fecha o anio antes de cargar en SAIA.'
        )


def _is_egc_phase2_context(context):
    values = [
        context.get('tipo_documento'),
        context.get('consecutivo'),
        context.get('observaciones_extraccion'),
        context.get('identidad_documental'),
    ]
    datos_pel = context.get('datos_pel') or {}
    values.extend([
        datos_pel.get('egc_titulo'),
        datos_pel.get('egc_consecutivo_may'),
        datos_pel.get('identidad_documental'),
    ])
    text = normalize_error_text(' '.join(str(value or '') for value in values))
    return (
        'documento_egc' in text
        or 'may-egc' in text
        or 'egc-' in text
        or ('egresos cheques' in text and 'bancolombia' not in text)
    )


def _is_ecb_phase2_context(context):
    values = [
        context.get('tipo_documento'),
        context.get('consecutivo'),
        context.get('observaciones_extraccion'),
        context.get('identidad_documental'),
    ]
    datos_pel = context.get('datos_pel') or {}
    values.extend([
        datos_pel.get('ecb_titulo'),
        datos_pel.get('ecb_consecutivo_may'),
        datos_pel.get('identidad_documental'),
    ])
    text = normalize_error_text(' '.join(str(value or '') for value in values))
    return 'documento_ecb' in text or 'egresos cheques bancolombia' in text or 'may-ecb' in text or 'ecb-' in text


def _apply_ecb_phase2_message(result, code):
    if code == 'OCR_TEXTO_INSUFICIENTE':
        result['accion_recomendada'] = (
            'Revisa que se lea el titulo EGRESOS CHEQUES BANCOLOMBIA, el numero MAY-ECB y la fecha.'
        )
    elif code == 'CONFIANZA_BAJA':
        result['accion_recomendada'] = (
            'Revisa manualmente el titulo EGRESOS CHEQUES BANCOLOMBIA, el numero MAY-ECB y la fecha.'
        )
    elif code == 'METADATA_AMBIGUA':
        result['accion_recomendada'] = (
            'Confirma el titulo EGRESOS CHEQUES BANCOLOMBIA, el numero MAY-ECB y el anio antes de cargar en SAIA.'
        )


def _apply_egc_phase2_message(result, code):
    if code == 'OCR_TEXTO_INSUFICIENTE':
        result['accion_recomendada'] = (
            'Revisa que se lea el titulo EGRESOS CHEQUES, el numero MAY-EGC y la fecha del comprobante.'
        )
    elif code == 'CONFIANZA_BAJA':
        result['accion_recomendada'] = (
            'Revisa manualmente el titulo EGRESOS CHEQUES, el numero MAY-EGC y la fecha del comprobante.'
        )
    elif code == 'METADATA_AMBIGUA':
        result['accion_recomendada'] = (
            'Confirma manualmente el titulo EGRESOS CHEQUES, el numero MAY-EGC y el anio antes de cargar en SAIA.'
        )


def _is_ege_phase2_context(context):
    values = [
        context.get('tipo_documento'),
        context.get('consecutivo'),
        context.get('observaciones_extraccion'),
        context.get('identidad_documental'),
    ]
    datos_pel = context.get('datos_pel') or {}
    values.extend([
        datos_pel.get('ege_titulo'),
        datos_pel.get('ege_consecutivo_may'),
        datos_pel.get('identidad_documental'),
    ])
    text = normalize_error_text(' '.join(str(value or '') for value in values))
    return 'documento_ege' in text or 'may-ege' in text or 'ege-' in text or 'egresos efectivo' in text


def _apply_ege_phase2_message(result, code):
    if code == 'OCR_TEXTO_INSUFICIENTE':
        result['accion_recomendada'] = (
            'Revisa que se lea el titulo EGRESOS EFECTIVO, el numero MAY-EGE y la fecha del comprobante.'
        )
    elif code == 'CONFIANZA_BAJA':
        result['accion_recomendada'] = (
            'Revisa manualmente el titulo EGRESOS EFECTIVO, el numero MAY-EGE y la fecha del comprobante.'
        )
    elif code == 'METADATA_AMBIGUA':
        result['accion_recomendada'] = (
            'Confirma manualmente el titulo EGRESOS EFECTIVO, el numero MAY-EGE y el anio antes de cargar en SAIA.'
        )


def classify_phase2_error(error_tecnico='', contexto=None):
    context = contexto or {}
    text = normalize_error_text(error_tecnico)
    context_text = normalize_error_text(_phase2_context_text(context))
    combined = f'{text}; {context_text}'

    if any(item in combined for item in ['tesseract', 'tessdata', 'ocr no esta configurado', 'ocr no esta instalado']):
        return 'OCR_NO_CONFIGURADO'
    if 'ocr agotado' in combined:
        return 'OCR_SIN_TEXTO'
    if 'no hay texto disponible' in combined or context.get('texto_extraido_len') == 0:
        return 'OCR_SIN_TEXTO'
    if context.get('texto_extraido_len') and context.get('texto_extraido_len') < 80:
        return 'OCR_TEXTO_INSUFICIENTE'

    if 'no se detecto encabezado pagos electronicos' in combined:
        return 'ENCABEZADO_PAGOS_NO_DETECTADO'
    if 'no se detecto inversiones euro' in combined:
        return 'PROVEEDOR_EURO_NO_DETECTADO'
    if 'consecutivo no coincide' in combined or 'no coincide con el nombre' in combined:
        return 'CONSECUTIVO_NO_COINCIDE'
    if 'consecutivo invalido' in combined:
        return 'CONSECUTIVO_INVALIDO'
    if 'no se detecto consecutivo' in combined or 'consecutivo may-pel' in combined and 'no se pudo leer' in combined:
        return 'CONSECUTIVO_NO_DETECTADO'
    has_confidence = context.get('confianza') not in (None, '')
    if 'confianza menor' in combined or has_confidence and _phase2_confidence(context) < 80 and context.get('requiere_revision'):
        return 'CONFIANZA_BAJA'
    if 'ambigua' in combined or 'ambiguo' in combined:
        return 'METADATA_AMBIGUA'
    if context.get('requiere_revision') and not context.get('identidad_documental') and 'identidad_documental=' not in context_text:
        return 'IDENTIDAD_DOCUMENTAL_NO_DETECTADA'
    if context.get('requiere_revision'):
        return 'METADATA_AMBIGUA'

    return ''


def get_phase2_recommended_action(codigo_error, contexto=None):
    return PHASE2_ERROR_MESSAGES.get(codigo_error, {}).get('accion_recomendada', '')


def is_phase2_blocking_error(codigo_error):
    data = PHASE2_ERROR_MESSAGES.get(codigo_error, {})
    return bool(data.get('bloquea_fase_3') or data.get('bloquea_saia'))


def get_blocking_phase_error(documento, target_phase=None):
    """
    Retorna el primer error bloqueante conocido del documento.

    target_phase permite preguntar si el bloqueo aplica antes de ejecutar una
    fase concreta. Por ejemplo, target_phase=PHASE_2 solo considera errores F1
    que bloquean Fase 2, no advertencias que solo bloquean SAIA.
    """
    context = _document_phase_context(documento)
    technical_error = getattr(documento, 'error', '') or ''

    phase1_error = build_phase1_error_message(technical_error, context)
    if phase1_error.get('codigo_error_usuario'):
        if target_phase == PHASE_2 and phase1_error.get('bloquea_fase_2'):
            return phase1_error
        if target_phase in (None, PHASE_3, PHASE_4, PHASE_5) and (
            phase1_error.get('bloquea_fase_2') or phase1_error.get('bloquea_saia')
        ):
            return phase1_error

    if target_phase == PHASE_2:
        return None

    phase2_error = build_phase2_error_message(technical_error, context)
    if phase2_error.get('codigo_error_usuario'):
        if target_phase in (None, PHASE_3, PHASE_4, PHASE_5) and (
            phase2_error.get('bloquea_fase_3') or phase2_error.get('bloquea_saia')
        ):
            return phase2_error

    if target_phase == PHASE_3:
        return None

    phase3_error = build_phase3_error_message(technical_error, context)
    if phase3_error.get('codigo_error_usuario'):
        if target_phase in (None, PHASE_4, PHASE_5) and (
            phase3_error.get('bloquea_relacion') or phase3_error.get('bloquea_saia')
        ):
            return phase3_error

    if target_phase == PHASE_4:
        return None

    phase4_error = build_phase4_error_message(technical_error, context)
    if phase4_error.get('codigo_error_usuario'):
        if target_phase in (None, PHASE_5) and (
            phase4_error.get('bloquea_validacion') or phase4_error.get('bloquea_saia')
        ):
            return phase4_error

    return None


def _document_phase_context(documento):
    metadata = getattr(documento, 'metadata', None)
    datos_pel = getattr(metadata, 'datos_pel', None) or {}
    return {
        'es_soportado': getattr(documento, 'es_soportado', True),
        'es_duplicado': getattr(documento, 'es_duplicado', False),
        'contiene_ok': ' OK' in str(getattr(documento, 'nombre_archivo', '')).upper() and not getattr(documento, 'marcado_ok', False),
        'estado_proceso': getattr(documento, 'estado_proceso', ''),
        'nombre_archivo': getattr(documento, 'nombre_archivo', ''),
        'texto_extraido_len': len(getattr(documento, 'texto_extraido', '') or ''),
        'ocr_agotado': getattr(documento, 'ocr_agotado', False),
        'observaciones': getattr(metadata, 'observaciones', '') if metadata else '',
        'requiere_revision': getattr(metadata, 'requiere_revision', False) if metadata else False,
        'confianza': getattr(metadata, 'confianza', '') if metadata else '',
        'datos_pel': datos_pel,
        'identidad_documental': datos_pel.get('identidad_documental', ''),
    }


def build_phase1_error_message(error_tecnico='', contexto=None):
    context = contexto or {}
    code = classify_phase1_error(error_tecnico, context)
    if not code:
        result = DEFAULT_ERROR.copy()
        result['error_tecnico'] = error_tecnico or ''
        return result

    result = DEFAULT_ERROR.copy()
    result.update(ERROR_MESSAGES[code])
    result['codigo_error_usuario'] = code
    result['fase_error'] = PHASE_1
    result['error_tecnico'] = error_tecnico or _technical_error_from_context(context, code)
    if code == 'YA_CARGADO_SAIA_HISTORICO' and context.get('mensaje_bloqueo_saia_historico'):
        result['mensaje_usuario'] = context['mensaje_bloqueo_saia_historico']
    return result


def classify_phase1_error(error_tecnico='', contexto=None):
    context = contexto or {}
    text = normalize_error_text(error_tecnico)

    if _is_historical_duplicate_without_saia_success(text, context):
        return 'DUPLICADO_HISTORICO_SIN_CARGA_SAIA'
    if context.get('carga_saia_historica') or 'cargado exitosamente a saia en historico' in text:
        return 'YA_CARGADO_SAIA_HISTORICO'
    if context.get('ya_cargado_saia'):
        return 'YA_CARGADO_SAIA'

    if context.get('archivo_vacio') or 'archivo vacio' in text:
        return 'ARCHIVO_VACIO'
    if context.get('pdf_pesado_saia') or context.get('pdf_supera_limite_saia') or 'pdf pesado saia' in text:
        return 'PDF_PESADO_SAIA'
    if 'pdf supera limite saia' in text:
        return 'PDF_PESADO_SAIA'
    if context.get('pel_simple_subparte_1_conflicto') or 'simple y subparte 1' in text:
        return 'PEL_SIMPLE_Y_SUBPARTE_1_CONFLICTO'
    if context.get('extension_doble_o_sospechosa') or 'extension doble o sospechosa' in text:
        return 'EXTENSION_DOBLE_O_SOSPECHOSA'
    if context.get('consecutivo_nombre_no_coincide_contenido') or 'consecutivo del nombre no coincide con contenido' in text:
        return 'CONSECUTIVO_NOMBRE_NO_COINCIDE_CONTENIDO'
    if context.get('duplicado_ruta_normalizada') or 'duplicado por ruta normalizada' in text:
        return 'DUPLICADO_RUTA_NORMALIZADA'
    if context.get('caracteres_no_compatibles_saia') or 'caracteres problematicos para saia' in text:
        return 'CARACTERES_NO_COMPATIBLES_SAIA'
    if context.get('nombre_pel_ambiguo') or 'nombre pel ambiguo' in text:
        return 'NOMBRE_PEL_AMBIGUO'
    if context.get('archivo_sospechosamente_pequeno') or 'sospechosamente pequeno' in text:
        return 'ARCHIVO_PEQUENO'
    if context.get('extension_coincide_con_firma') is False and context.get('es_soportado'):
        return 'EXTENSION_NO_COINCIDE'
    if 'bloqueado por continuidad documental' in text and 'falta' in text:
        return 'FALTANTE_PEL_BASE'
    if context.get('archivo_posiblemente_sincronizando') or 'sincroniz' in text or 'onedrive' in text:
        return 'ARCHIVO_EN_SINCRONIZACION'
    if context.get('archivo_posiblemente_bloqueado') or 'bloqueado' in text:
        return 'ARCHIVO_BLOQUEADO'

    if 'permission denied' in text or 'access is denied' in text or 'acceso denegado' in text or 'permiso' in text:
        return 'SIN_PERMISO_LECTURA'
    if 'file not found' in text or 'no such file' in text or 'archivo no encontrado' in text:
        return 'ARCHIVO_NO_ENCONTRADO'
    if 'no se pudo calcular hash' in text:
        return 'HASH_NO_CALCULADO'
    if 'no se pudo leer tamano' in text:
        return 'TAMANO_NO_LEIDO'
    if 'eof marker not found' in text or 'stream has ended unexpectedly' in text:
        return 'PDF_DANADO'
    if 'cannot open broken document' in text or 'broken document' in text:
        return 'PDF_CORRUPTO'
    if 'no coincide con contenido real' in text or 'no coincide con firma binaria' in text:
        return 'EXTENSION_NO_COINCIDE'
    if 'formato no soportado' in text or context.get('es_soportado') is False:
        return 'FORMATO_NO_SOPORTADO'

    if context.get('estado_duplicado_documental') == 'NOMBRE_NO_RECONOCIDO' or context.get('nombre_reconocido') is False:
        return 'NOMBRE_NO_RECONOCIDO'
    if context.get('contiene_ok') or context.get('omitido_carga_por_ok'):
        return 'OK_DETECTADO'
    if context.get('duplicado_historico'):
        return 'DUPLICADO_HISTORICO'
    if context.get('es_duplicado') or context.get('estado_duplicado_documental') == 'DUPLICADO_REAL':
        return 'DUPLICADO_LOTE'
    if 'duplicado por identidad documental' in text or 'duplicado por hash' in text:
        return 'DUPLICADO_LOTE'
    if 'cargado exitosamente a saia en historico' in text:
        return 'YA_CARGADO_SAIA_HISTORICO'
    if 'ya cargado exitosamente a saia' in text:
        return 'YA_CARGADO_SAIA'
    if 'carpeta origen no existe' in text or 'no es un directorio valido' in text:
        return 'CARPETA_ORIGEN_NO_EXISTE'
    if 'no se configuro carpeta secundaria' in text:
        return 'CARPETA_SECUNDARIA_NO_CONFIGURADA'
    if 'carpeta secundaria no existe' in text or 'carpeta secundaria no es accesible' in text:
        return 'CARPETA_SECUNDARIA_NO_ACCESIBLE'
    if 'faltante' in text and 'subparte' in text and 'no fue encontrada' in text:
        return 'FALTANTE_SUBPARTE_NO_ENCONTRADO'
    if 'parte de tomo faltante' in text and 'no fue encontrada' in text:
        return 'FALTANTE_PARTE_TOMO_NO_ENCONTRADO'
    if 'consecutivo no encontrado en carpeta principal ni secundaria' in text:
        return 'FALTANTE_PEL_BASE'

    status = context.get('estado_continuidad') or context.get('estado_continuidad_subparte') or context.get('estado_continuidad_tomo')
    if status in {
        'FALTA_PRINCIPAL_SUBPARTE',
        'FALTANTE_SUBPARTE',
        'FALTA_TOMO_INICIAL',
        'FALTANTE_TOMO',
        'FALTA_PARTE_INICIAL',
        'FALTANTE_PARTE_TOMO',
        'FALTANTE_SUBPARTE_NO_ENCONTRADO',
        'FALTANTE_PARTE_TOMO_NO_ENCONTRADO',
        'CAMBIO_DE_RANGO',
        'CARPETA_SECUNDARIA_NO_CONFIGURADA',
        'CARPETA_SECUNDARIA_NO_ACCESIBLE',
    }:
        return status
    if status in {'FALTANTE_NO_ENCONTRADO', 'FALTANTE_PEL_BASE'}:
        return 'FALTANTE_PEL_BASE'

    return ''


def _is_historical_duplicate_without_saia_success(text, context):
    if context.get('duplicado_historico') and not (
        context.get('ya_cargado_saia') or context.get('carga_saia_historica')
    ):
        return True
    return any(
        marker in text
        for marker in (
            'documento encontrado en lote anterior sin evidencia de carga saia exitosa',
            'lote anterior sin evidencia de carga saia',
            'sin evidencia de carga saia exitosa',
        )
    )


def get_phase1_recommended_action(codigo_error, contexto=None):
    return ERROR_MESSAGES.get(codigo_error, {}).get('accion_recomendada', '')


def is_phase1_blocking_error(codigo_error):
    data = ERROR_MESSAGES.get(codigo_error, {})
    return bool(data.get('bloquea_fase_2') or data.get('bloquea_saia'))


def normalize_error_text(error_tecnico):
    return str(error_tecnico or '').strip().lower()


def _append_guidance(action, guidance):
    action = str(action or '').strip()
    guidance = str(guidance or '').strip()
    if not guidance:
        return action
    if not action:
        return guidance
    if guidance in action:
        return action
    return f'{action} {guidance}'


def _technical_error_from_context(context, code):
    if code == 'OK_DETECTADO':
        return 'Archivo con OK detectado en el nombre'
    if code == 'DUPLICADO_HISTORICO':
        return 'Documento inventariado en lote anterior'
    if code == 'YA_CARGADO_SAIA':
        return 'Documento con carga SAIA exitosa previa'
    if code == 'YA_CARGADO_SAIA_HISTORICO':
        return context.get('mensaje_bloqueo_saia_historico') or 'Documento con carga SAIA historica exitosa'
    if code == 'NOMBRE_NO_RECONOCIDO':
        return 'No se reconocio consecutivo PEL desde el nombre'
    if code in {'PDF_PESADO_SAIA', 'PDF_SUPERA_LIMITE_SAIA'}:
        return 'PDF pesado para SAIA'
    if code == 'NOMBRE_PEL_AMBIGUO':
        return 'Nombre PEL ambiguo'
    if code == 'PEL_SIMPLE_Y_SUBPARTE_1_CONFLICTO':
        return 'Conflicto entre PEL simple y subparte 1'
    if code == 'CARACTERES_NO_COMPATIBLES_SAIA':
        return 'Nombre con caracteres problematicos para SAIA'
    if code == 'DUPLICADO_RUTA_NORMALIZADA':
        return 'Duplicado por ruta normalizada'
    if code == 'EXTENSION_DOBLE_O_SOSPECHOSA':
        return 'Extension doble o sospechosa'
    if code == 'CONSECUTIVO_NOMBRE_NO_COINCIDE_CONTENIDO':
        return 'Consecutivo del nombre no coincide con contenido'
    return context.get('observacion_continuidad') or context.get('motivo_orden_invalido') or ''


def _technical_phase2_error_from_context(context, code):
    if code == 'IDENTIDAD_DOCUMENTAL_NO_DETECTADA':
        return 'No se reconocio identidad documental desde el nombre del archivo'
    if code == 'CONFIANZA_BAJA':
        return f"Confianza menor al minimo requerido: {context.get('confianza', '')}"
    return _phase2_context_text(context)


def _phase2_context_text(context):
    parts = [
        context.get('error'),
        context.get('observaciones'),
        context.get('observaciones_extraccion'),
        context.get('errores_validacion'),
        context.get('validation_errors'),
    ]
    if context.get('texto_extraido_len') not in (None, ''):
        parts.append(f"texto_extraido_len={context.get('texto_extraido_len')}")
    if context.get('confianza') not in (None, ''):
        parts.append(f"confianza={context.get('confianza')}")
    if context.get('requiere_revision') not in (None, ''):
        parts.append(f"requiere_revision={context.get('requiere_revision')}")
    if context.get('identidad_documental') not in (None, ''):
        parts.append(f"identidad_documental={context.get('identidad_documental')}")
    return '; '.join(_stringify_phase2_part(part) for part in parts if part)


def _phase4_context_text(context):
    parts = [
        context.get('error'),
        context.get('errores'),
        context.get('motivo'),
        context.get('estado_proceso'),
        context.get('nombre_archivo'),
    ]
    return '; '.join(_stringify_phase2_part(part) for part in parts if part)


def _phase5_context_text(context):
    parts = [
        context.get('error'),
        context.get('mensaje_error'),
        context.get('evento'),
        context.get('motivo'),
        context.get('exception'),
        context.get('estado_proceso'),
    ]
    if context.get('detener_lote'):
        parts.append('detener_lote=True')
    return '; '.join(_stringify_phase2_part(part) for part in parts if part)


def _stringify_phase2_part(value):
    if isinstance(value, (list, tuple, set)):
        return '; '.join(str(item) for item in value if item)
    return str(value)


def _phase2_confidence(context):
    try:
        return float(context.get('confianza') or 0)
    except (TypeError, ValueError):
        return 0


def _phase3_context_text(context):
    parts = [
        context.get('error'),
        context.get('motivo'),
        context.get('grupo'),
        context.get('criterio'),
        context.get('criterio_relacion'),
        context.get('estado_proceso'),
        context.get('nombre_archivo'),
        context.get('tipo'),
        context.get('exception'),
    ]
    if context.get('confianza') is not None:
        parts.append(f"confianza={context.get('confianza')}")
    if context.get('faltantes'):
        parts.append(f"faltantes={context.get('faltantes')}")
    if context.get('documentos'):
        parts.append(f"documentos={context.get('documentos')}")
    return '; '.join(_stringify_phase2_part(part) for part in parts if part)


def _safe_float(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0


def _has_phase3_numeric_confidence(context):
    if not context or context.get('confianza') in (None, ''):
        return False
    try:
        float(context.get('confianza'))
    except (TypeError, ValueError):
        return False
    return True


def _phase3_relation_was_evaluated(context, combined_text=''):
    if context.get('relacion_evaluada'):
        return True
    if context.get('exception'):
        return True
    if context.get('documento_principal') or context.get('documento_relacionado'):
        return True
    if context.get('criterio') or context.get('criterio_relacion') or context.get('grupo'):
        return True
    markers = (
        'relacion fue evaluada',
        'documento principal',
        'grupo documental',
        'sin relacion automatica',
        'no se pudo relacionar',
    )
    return any(marker in combined_text for marker in markers)


def _extract_phase3_confidence(text):
    match = re.search(r'confianza\s*[=:]?\s*(\d+(?:\.\d+)?)', str(text or ''))
    if not match:
        return None
    try:
        return float(match.group(1))
    except (TypeError, ValueError):
        return None


