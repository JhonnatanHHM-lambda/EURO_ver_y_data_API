import logging

from django.apps import AppConfig

logger = logging.getLogger('migracion_masiva_archivo')

# Clave arbitraria y fija para el advisory lock de Postgres usado por la
# reconciliacion de arranque. Es una defensa extra para evitar logs duplicados
# si alguna vez hay mas de un worker de Celery arrancando a la vez; la operacion
# en si ya es idempotente sin el lock (ver _reconciliar_procesos_interrumpidos).
_RECONCILIACION_LOCK_KEY = 851274300


class MigracionMasivaArchivoConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'migracion_masiva_archivo'
    verbose_name = 'Migración Masiva de Archivo'

    def ready(self):
        # Este receptor se registra en TODOS los procesos que importan la app
        # (web/Gunicorn, manage.py, worker de Celery), pero la señal worker_ready
        # solo la emite el propio proceso de worker de Celery al terminar de
        # arrancar -- jamas un proceso Django/Gunicorn -- asi que la
        # reconciliacion nunca corre por accidente en cada worker web ni
        # durante comandos de manage.py como migrate/makemigrations.
        from celery.signals import worker_ready

        worker_ready.connect(
            _on_worker_ready,
            dispatch_uid='migracion_masiva_archivo_reconciliar_en_worker_ready',
        )


def _on_worker_ready(sender=None, **kwargs):
    _reconciliar_procesos_interrumpidos()


def _reconciliar_procesos_interrumpidos():
    """
    Al arrancar el worker de Celery, cualquier LoteDocumental o EjecucionCargaMasiva
    que haya quedado en EN_PROCESO (porque el worker anterior se cayo o fue
    reiniciado a mitad de una carga) se marca como interrumpido, para que el
    dashboard no muestre un proceso "en curso" que en realidad ya no existe.

    La mutacion de estado es un UPDATE atomico filtrado por
    estado_proceso='EN_PROCESO' (no fetch+save por fila), por lo que es
    naturalmente idempotente: si dos procesos la corrieran en paralelo, el
    segundo UPDATE simplemente no encontraria filas para tocar. El advisory
    lock de Postgres evita ademas que se dupliquen las entradas de log en ese
    escenario.
    """
    from django.db import connection
    from django.utils import timezone

    from .models import EjecucionCargaMasiva, LogProcesoDocumental, LoteDocumental

    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_try_advisory_lock(%s)', [_RECONCILIACION_LOCK_KEY])
            adquirido = cursor.fetchone()[0]

        if not adquirido:
            logger.info('Reconciliacion de arranque omitida: otro proceso ya la esta ejecutando.')
            return

        try:
            ahora = timezone.now()

            lote_ids = list(
                LoteDocumental.objects.filter(estado_proceso='EN_PROCESO').values_list('id', flat=True)
            )
            if lote_ids:
                LoteDocumental.objects.filter(id__in=lote_ids, estado_proceso='EN_PROCESO').update(
                    estado_proceso='FINALIZADO_CON_ERRORES',
                    fecha_fin=ahora,
                    modificado=ahora,
                )
                for lote_id in lote_ids:
                    LogProcesoDocumental.objects.create(
                        lote_id=lote_id,
                        nivel='WARNING',
                        evento='proceso_interrumpido_reinicio',
                        mensaje=(
                            'El proceso fue interrumpido por un reinicio del worker de Celery. '
                            'Estado restaurado a FINALIZADO_CON_ERRORES.'
                        ),
                        detalle={},
                    )
                logger.warning(
                    'Reconciliacion de arranque: %d lote(s) marcados como interrumpidos.',
                    len(lote_ids),
                )

            EjecucionCargaMasiva.objects.filter(estado_proceso='EN_PROCESO').update(
                estado_proceso='FALLIDO',
                error='Proceso interrumpido por un reinicio del worker de Celery.',
                fecha_fin=ahora,
                modificado=ahora,
            )
        finally:
            with connection.cursor() as cursor:
                cursor.execute('SELECT pg_advisory_unlock(%s)', [_RECONCILIACION_LOCK_KEY])
    except Exception:
        logger.exception('Error al reconciliar procesos interrumpidos de migracion_masiva_archivo.')
