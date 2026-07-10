"""
Singleton de control de ejecucion. Usado por views_api.py y procesar_lote_completo
para coordinar inicio, cancelacion y estado del proceso activo.
"""


class _ExecutionControl:
    def __init__(self):
        self.cancel_requested = False
        self.running = False
        self.estado = "PENDIENTE"
        self.lote_id_activo = None
        self.ejecucion_id_activa = None
        self.fase_actual = ""
        self.doc_actual = ""
        self.last_error = ""
        self.pendientes_saia = 0       # docs VALIDADO/RELACIONADO sin procesar tras el límite
        self.email_status = None       # None=no intentado, True=enviado, str=error

    def reset(self):
        self.cancel_requested = False
        self.running = False
        self.estado = "PENDIENTE"
        self.lote_id_activo = None
        self.ejecucion_id_activa = None
        self.fase_actual = ""
        self.doc_actual = ""
        self.last_error = ""
        self.pendientes_saia = 0
        self.email_status = None

    def iniciar(self, lote_id, ejecucion_id=None):
        self.cancel_requested = False
        self.running = True
        self.estado = "EN_EJECUCION"
        self.lote_id_activo = lote_id
        self.ejecucion_id_activa = ejecucion_id
        self.fase_actual = "Iniciando..."
        self.doc_actual = ""
        self.last_error = ""

    def solicitar_cancelacion(self):
        self.cancel_requested = True
        self.estado = "DETENIENDO"

    def marcar_finalizado(self, con_error=False):
        self.running = False
        self.estado = "ERROR" if con_error else "FINALIZADO"
        self.cancel_requested = False
        self.fase_actual = ""
        self.doc_actual = ""

    def marcar_cancelado(self):
        self.running = False
        self.estado = "DETENIDO_POR_USUARIO"
        self.cancel_requested = False


control = _ExecutionControl()


