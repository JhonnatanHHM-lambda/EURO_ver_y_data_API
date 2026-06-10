from celery import shared_task
from django.utils import timezone
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)


@shared_task(name='Contratos.tasks.revisar_contratos_60_dias', queue='contratos')
def revisar_contratos_60_dias():
    """Genera cartas de no prórroga para empleados que vencen en 60 días."""
    from .utils.siesa_simulator import obtener_empleados_por_dias
    from .utils.pdf_generator import generar_carta_no_prorroga
    from .utils.notificaciones import enviar_notificacion_empleado_task
    from .models import Contrato
    from Trazabilidad.models import Sede

    fecha_objetivo = timezone.localdate() + timedelta(days=60)
    empleados = obtener_empleados_por_dias(fecha_objetivo)

    procesados = 0
    for emp in empleados:
        existe = Contrato.objects.filter(
            documento_id=emp['documento_id'],
            tipo_carta='NO_PRORROGA',
            fecha_finalizacion=emp['fecha_finalizacion'],
            token_usado=False,
        ).exists()
        if existe:
            continue

        try:
            sede = None
            try:
                sede = Sede.objects.get(codigo=emp.get('centro_operacion'))
            except Sede.DoesNotExist:
                pass

            contrato = Contrato.objects.create(
                tipo_documento=emp['tipo_documento'],
                documento_id=emp['documento_id'],
                nombre_completo=emp['nombre_completo'],
                cargo=emp['cargo'],
                fecha_finalizacion=emp['fecha_finalizacion'],
                celular=emp.get('celular', ''),
                email=emp.get('email', ''),
                tipo_carta='NO_PRORROGA',
                estado='PENDIENTE_FIRMA_NO_PRORROGA',
                sede=sede,
                token_expira_en=timezone.now() + timedelta(days=7),
                fecha_primer_envio=timezone.now(),
            )

            pdf_key = generar_carta_no_prorroga(contrato)
            contrato.pdf_carta_key = pdf_key
            contrato.save(update_fields=['pdf_carta_key'])

            enviar_notificacion_empleado_task.delay(contrato.id)
            procesados += 1

        except Exception as e:
            logger.error(f'Error procesando empleado {emp.get("documento_id")}: {e}')

    logger.info(f'revisar_contratos_60_dias: {procesados} contratos creados para {fecha_objetivo}')


@shared_task(name='Contratos.tasks.revisar_contratos_proximos_vencer', queue='contratos')
def revisar_contratos_proximos_vencer():
    """Notifica a directores según la configuración de días de cada sede."""
    from Trazabilidad.models import Sede
    from .models import Contrato, EventoContrato, AsignacionCentro
    from .utils.notificaciones import enviar_alerta_director

    hoy = timezone.localdate()

    for sede in Sede.objects.filter(estado=True):
        fecha_objetivo = hoy + timedelta(days=sede.dias_alerta_director)

        contratos = Contrato.objects.filter(
            sede=sede,
            fecha_finalizacion=fecha_objetivo,
        ).exclude(estado__in=['PRORROGA', 'TERMINACION', 'PENDIENTE_DECISION_DIRECTOR'])

        if not contratos.exists():
            continue

        asignaciones = AsignacionCentro.objects.filter(
            sede=sede,
            rol='DIRECTOR',
            activo=True,
            usuario__is_active=True,
        ).select_related('usuario')

        for asignacion in asignaciones:
            try:
                enviar_alerta_director(asignacion.usuario, list(contratos), sede.dias_alerta_director)
                for contrato in contratos:
                    contrato.estado = 'PENDIENTE_DECISION_DIRECTOR'
                    contrato.save(update_fields=['estado'])
                    EventoContrato.objects.create(
                        contrato=contrato,
                        tipo_evento='ESCALADO',
                        detalle={'motivo': 'revision_proximos_vencer', 'dias': sede.dias_alerta_director},
                    )
            except Exception as e:
                logger.error(f'Error notificando director {asignacion.usuario.correo}: {e}')


@shared_task(name='Contratos.tasks.enviar_notificacion_empleado_task', queue='contratos')
def enviar_notificacion_empleado_task(contrato_id):
    """Envía email + WhatsApp al empleado con el link de firma."""
    from .models import Contrato, EventoContrato
    from .utils.notificaciones import enviar_email_empleado, enviar_whatsapp_empleado

    try:
        contrato = Contrato.objects.get(id=contrato_id)
    except Contrato.DoesNotExist:
        return

    hora_actual = timezone.localtime().hour
    if not (7 <= hora_actual < 20):
        manana = timezone.now() + timedelta(days=1)
        eta = manana.replace(hour=7, minute=0, second=0, microsecond=0)
        enviar_notificacion_empleado_task.apply_async(args=[contrato_id], eta=eta)
        return

    if not contrato.email and not contrato.celular:
        contrato.estado = 'SIN_CANAL_CONTACTO'
        contrato.save(update_fields=['estado'])
        return

    if contrato.email:
        try:
            enviar_email_empleado(contrato)
            EventoContrato.objects.create(
                contrato=contrato, tipo_evento='ENVIADO_EMAIL',
                detalle={'email': contrato.email}
            )
        except Exception as e:
            logger.error(f'Error enviando email a contrato {contrato_id}: {e}')

    if contrato.celular:
        try:
            enviar_whatsapp_empleado(contrato)
            EventoContrato.objects.create(
                contrato=contrato, tipo_evento='ENVIADO_WA',
                detalle={'celular': contrato.celular}
            )
        except Exception as e:
            logger.error(f'Error enviando WhatsApp a contrato {contrato_id}: {e}')


@shared_task(name='Contratos.tasks.escalar_contratos_sin_firma', queue='contratos')
def escalar_contratos_sin_firma():
    """A los 3 días sin firma notifica al director. Reescala cada 3 días."""
    from .models import Contrato, EventoContrato, AsignacionCentro
    from .utils.notificaciones import enviar_alerta_sin_firma
    from django.db.models import Q

    limite = timezone.now() - timedelta(days=3)
    contratos = Contrato.objects.filter(
        estado__in=['PENDIENTE_FIRMA_NO_PRORROGA', 'PENDIENTE_FIRMA_PRORROGA', 'PENDIENTE_FIRMA_TERMINACION'],
        fecha_primer_envio__lte=limite,
        token_usado=False,
    ).filter(
        Q(fecha_ultimo_escalamiento__isnull=True) |
        Q(fecha_ultimo_escalamiento__lte=timezone.now() - timedelta(days=3))
    )

    for contrato in contratos:
        if not contrato.sede:
            continue

        asignaciones = AsignacionCentro.objects.filter(
            sede=contrato.sede,
            rol='DIRECTOR',
            activo=True,
            usuario__is_active=True,
        ).select_related('usuario')

        for asignacion in asignaciones:
            try:
                enviar_alerta_sin_firma(asignacion.usuario, contrato)
                contrato.contador_escalamientos += 1
                contrato.fecha_ultimo_escalamiento = timezone.now()
                contrato.save(update_fields=['contador_escalamientos', 'fecha_ultimo_escalamiento'])
                EventoContrato.objects.create(
                    contrato=contrato, tipo_evento='ESCALADO',
                    detalle={'director': asignacion.usuario.correo, 'nro': contrato.contador_escalamientos},
                )
            except Exception as e:
                logger.error(f'Error escalando contrato {contrato.id} a {asignacion.usuario.correo}: {e}')


@shared_task(name='Contratos.tasks.notificar_directores_sin_decision', queue='contratos')
def notificar_directores_sin_decision():
    """Recuerda diariamente a directores los contratos pendientes de su decisión."""
    from .models import Contrato, AsignacionCentro
    from .utils.notificaciones import enviar_recordatorio_decision

    contratos = Contrato.objects.filter(
        estado='PENDIENTE_DECISION_DIRECTOR'
    ).select_related('sede')

    for contrato in contratos:
        if not contrato.sede:
            continue

        asignaciones = AsignacionCentro.objects.filter(
            sede=contrato.sede,
            rol='DIRECTOR',
            activo=True,
            usuario__is_active=True,
        ).select_related('usuario')

        for asignacion in asignaciones:
            try:
                enviar_recordatorio_decision(asignacion.usuario, contrato)
            except Exception as e:
                logger.error(f'Error recordatorio director {asignacion.usuario.correo}: {e}')


@shared_task(name='Contratos.tasks.generar_y_guardar_pdf_firmado', queue='contratos')
def generar_y_guardar_pdf_firmado(contrato_id):
    """Genera el PDF firmado y lo guarda en MinIO tras confirmar la firma."""
    from .models import Contrato
    from .utils.pdf_generator import generar_pdf_firmado

    try:
        contrato = Contrato.objects.get(id=contrato_id)
        pdf_key = generar_pdf_firmado(contrato, contrato.firma_canvas_data)
        contrato.pdf_firmado_key = pdf_key
        contrato.save(update_fields=['pdf_firmado_key'])
    except Contrato.DoesNotExist:
        logger.error(f'generar_y_guardar_pdf_firmado: contrato {contrato_id} no encontrado')
    except Exception as e:
        logger.error(f'Error generando PDF firmado para contrato {contrato_id}: {e}')
