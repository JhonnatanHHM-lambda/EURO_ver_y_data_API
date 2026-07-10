import logging
from datetime import date

from celery import shared_task

logger = logging.getLogger(__name__)

# Fecha de inicio histórico para la sincronización de ausentismo y nómina.
_SYNC_DESDE = date(2024, 1, 1)

# Fecha de inicio histórico para rotación (histórico completo desde SIESA).
_SYNC_ROTACION_DESDE = date(2013, 1, 1)


@shared_task(name='Dashboard.tasks.sync_ausentismo_from_siesa', queue='dashboard')
def sync_ausentismo_from_siesa():
    """
    Sincroniza datos de ausentismo desde SIESA a la tabla local AusentismoDato.
    Hace upsert por rowid_tnl (clave surrogate de SIESA) — idempotente y seguro
    para ejecuciones repetidas.
    Corre diariamente a las 7:00 AM vía Celery Beat (cola 'dashboard').
    """
    from .models import AusentismoDato
    from .utils.siesa_ausentismo_connector import obtener_ausentismos

    registros = obtener_ausentismos(desde=_SYNC_DESDE)
    if not registros:
        logger.warning("sync_ausentismo_from_siesa: SIESA no devolvió datos")
        return {"creados": 0, "actualizados": 0, "total": 0}

    creados = actualizados = 0
    for r in registros:
        rowid = r['rowid_tnl']
        defaults = {
            'cedula':        r['cedula'],
            'nombre':        (r['nombre'] or '').strip(),
            'concepto_id':   r['concepto_id'],
            'concepto_desc': r['concepto_desc'],
            'tipo_concepto': r['tipo_concepto'],
            'horas':         r['horas'],
            'valor':         r['valor'],
            'dias':          r['dias'],
            'cargo':         r['cargo'],
            'co_codigo':     r['co_codigo'],
            'mes':           r['mes'],
            'ano':           r['ano'],
            'fecha_inicio':  r['fecha_inicio'],
            'fecha_fin':     r['fecha_fin'],
            'sexo':          r['sexo'],
            'tipo_contrato': r['tipo_contrato'],
            'fecha_ingreso': r['fecha_ingreso'],
        }
        _, created = AusentismoDato.objects.update_or_create(
            rowid_tnl=rowid,
            defaults=defaults,
        )
        if created:
            creados += 1
        else:
            actualizados += 1

    logger.info(
        "sync_ausentismo_from_siesa: creados=%d actualizados=%d total=%d",
        creados, actualizados, len(registros),
    )
    return {"creados": creados, "actualizados": actualizados, "total": len(registros)}


@shared_task(name='Dashboard.tasks.sync_nomina_from_siesa', queue='dashboard')
def sync_nomina_from_siesa():
    """
    Sincroniza TODOS los movimientos de nómina desde SIESA a la tabla NominaDato.
    Hace upsert por rowid_mv (clave surrogate de SIESA) con bulk_create — idempotente.
    Corre diariamente a las 7:00 AM vía Celery Beat (cola 'dashboard').
    """
    from .models import NominaDato
    from .utils.siesa_nomina_connector import obtener_nomina_completa

    registros = obtener_nomina_completa(desde=_SYNC_DESDE)
    if not registros:
        logger.warning("sync_nomina_from_siesa: SIESA no devolvió datos")
        return {"total": 0}

    _UPDATE_FIELDS = [
        'cedula', 'nombre', 'concepto_id', 'concepto_desc', 'naturaleza',
        'horas', 'valor', 'dias_tnl', 'cargo', 'co_codigo', 'co_nombre',
        'mes', 'ano', 'es_tnl', 'sexo', 'tipo_contrato', 'fecha_ingreso',
    ]

    objs = [NominaDato(**r) for r in registros]
    batch_size = 2000
    for i in range(0, len(objs), batch_size):
        NominaDato.objects.bulk_create(
            objs[i: i + batch_size],
            update_conflicts=True,
            unique_fields=['rowid_mv'],
            update_fields=_UPDATE_FIELDS,
        )

    logger.info("sync_nomina_from_siesa: total=%d", len(registros))
    return {"total": len(registros)}


@shared_task(name='Dashboard.tasks.sync_rotacion_from_siesa', queue='dashboard')
def sync_rotacion_from_siesa():
    """
    Sincroniza datos de rotación (activos + retirados) desde SIESA a RotacionDato.
    Estrategia:
      1. Traer snapshot completo de activos → upsert por rowid_contrato.
      2. Traer retirados históricos desde _SYNC_ROTACION_DESDE → upsert por rowid_contrato.
    El upsert garantiza idempotencia: un activo que se retira actualiza su fila existente
    con fecha_retiro, motivo y es_activo=False en la siguiente ejecución.
    Corre diariamente a las 7:25 AM vía Celery Beat (cola 'dashboard').
    """
    from .models import RotacionDato
    from .utils.siesa_rotacion_connector import obtener_activos, obtener_retirados

    _UPDATE_FIELDS = [
        'cedula', 'nombre', 'cargo', 'co_codigo', 'co_nombre',
        'fecha_ingreso', 'fecha_retiro', 'id_motivo_retiro', 'motivo_retiro',
        'salario', 'salario_anterior', 'fecha_contrato_hasta',
        'tipo_contrato', 'sexo', 'es_activo',
    ]

    activos    = obtener_activos()
    retirados  = obtener_retirados(desde=_SYNC_ROTACION_DESDE)

    total_act  = len(activos)
    total_ret  = len(retirados)

    if not activos and not retirados:
        logger.warning("sync_rotacion_from_siesa: SIESA no devolvió datos")
        return {"activos": 0, "retirados": 0}

    batch_size = 2000
    todos = activos + retirados
    objs  = [RotacionDato(**r) for r in todos]

    for i in range(0, len(objs), batch_size):
        RotacionDato.objects.bulk_create(
            objs[i: i + batch_size],
            update_conflicts=True,
            unique_fields=['rowid_contrato'],
            update_fields=_UPDATE_FIELDS,
        )

    logger.info(
        "sync_rotacion_from_siesa: activos=%d retirados=%d total=%d",
        total_act, total_ret, len(todos),
    )
    return {"activos": total_act, "retirados": total_ret, "total": len(todos)}
