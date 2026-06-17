from celery import shared_task
from django.utils import timezone
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)


@shared_task(name='Contratos.tasks.revisar_contratos_60_dias', queue='contratos')
def revisar_contratos_60_dias():
    """Genera cartas de no prórroga para empleados que vencen en 60 días."""
    from .utils.siesa_connector import obtener_empleados_en_rango
    from .utils.pdf_generator import generar_carta_no_prorroga
    from .models import Contrato, EventoContrato
    from Trazabilidad.models import Sede

    hoy = timezone.localdate()
    fecha_limite = hoy + timedelta(days=60)
    empleados = obtener_empleados_en_rango(hoy, fecha_limite)

    procesados = 0
    for emp in empleados:
        # Bloquear si ya existe CUALQUIER contrato activo para este empleado+fecha,
        # sin importar el tipo. Evita crear NO_PRORROGA cuando ya hay TERMINACION o
        # PRORROGA (generadas por decisión del director en un ciclo anterior).
        # En producción esto nunca colisiona: cada ciclo de contrato tiene nueva fecha.
        existe = Contrato.objects.filter(
            documento_id=emp['documento_id'],
            fecha_finalizacion=emp['fecha_finalizacion'],
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

            from Contratos.tasks import enviar_notificacion_empleado_task as _enviar
            _enviar.delay(contrato.id)
            procesados += 1

        except Exception as e:
            logger.error(f'Error procesando empleado {emp.get("documento_id")}: {e}')

    logger.info(f'revisar_contratos_60_dias: {procesados} contratos creados (hasta {fecha_limite})')


@shared_task(name='Contratos.tasks.revisar_contratos_proximos_vencer', queue='contratos')
def revisar_contratos_proximos_vencer():
    """Notifica a directores según la configuración de días de cada sede."""
    from Trazabilidad.models import Sede
    from .models import Contrato, EventoContrato, AsignacionCentro
    from .utils.notificaciones import enviar_alerta_director

    hoy = timezone.localdate()

    for sede in Sede.objects.filter(estado=True):
        fecha_objetivo = hoy + timedelta(days=sede.dias_alerta_director)

        # Rango: desde hoy hasta hoy+dias_alerta_director, para que si el task falla
        # un día los contratos no queden atrapados hasta el siguiente ciclo exacto.
        # alertar_contratos_urgentes cubre los ya expirados (fecha < hoy).
        contratos = Contrato.objects.filter(
            sede=sede,
            fecha_finalizacion__lte=fecha_objetivo,
            fecha_finalizacion__gte=hoy,
        ).exclude(estado__in=[
            'PENDIENTE_DECISION_DIRECTOR',
            'PENDIENTE_FIRMA_PRORROGA',
            'PENDIENTE_FIRMA_TERMINACION',
            'SIN_CANAL_CONTACTO',
            'ERROR_NOTIFICACION',
        ]).exclude(
            estado='FIRMADO',
            tipo_carta__in=['PRORROGA', 'TERMINACION'],
        )

        if not contratos.exists():
            continue

        asignaciones = AsignacionCentro.objects.filter(
            sede=sede,
            rol='DIRECTOR',
            activo=True,
            usuario__is_active=True,
        ).select_related('usuario')

        for contrato in contratos:
            for asignacion in asignaciones:
                try:
                    enviar_alerta_director(asignacion.usuario, contrato, sede.dias_alerta_director)
                    contrato.estado = 'PENDIENTE_DECISION_DIRECTOR'
                    contrato.save(update_fields=['estado'])
                    EventoContrato.objects.create(
                        contrato=contrato,
                        tipo_evento='ESCALADO',
                        detalle={
                            'motivo': 'revision_proximos_vencer',
                            'dias': sede.dias_alerta_director,
                            'director': asignacion.usuario.correo,
                        },
                    )
                    from Usuarios.models import NotificacionAdmin
                    NotificacionAdmin.objects.create(
                        tipo='alerta_contrato',
                        titulo=f'Contrato próximo a vencer — {contrato.nombre_completo}',
                        cuerpo=(
                            f'{contrato.nombre_completo} (Doc: {contrato.documento_id}) — '
                            f'Cargo: {contrato.cargo}. '
                            f'Vence el {contrato.fecha_finalizacion.strftime("%d/%m/%Y")}. '
                            f'Quedan {sede.dias_alerta_director} día(s). '
                            f'Por favor ingresa al panel de contratos y toma una decisión.'
                        ),
                        usuario=asignacion.usuario,
                        contrato=contrato,
                    )
                except Exception as e:
                    logger.error(f'Error notificando director {asignacion.usuario.correo} para contrato {contrato.id}: {e}')


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
            EventoContrato.objects.create(
                contrato=contrato, tipo_evento='ERROR',
                detalle={'canal': 'email', 'destinatario': contrato.email, 'error': str(e)}
            )

    if contrato.celular:
        try:
            enviar_whatsapp_empleado(contrato)
            EventoContrato.objects.create(
                contrato=contrato, tipo_evento='ENVIADO_WA',
                detalle={'celular': contrato.celular}
            )
        except Exception as e:
            logger.error(f'Error enviando WhatsApp a contrato {contrato_id}: {e}')
            EventoContrato.objects.create(
                contrato=contrato, tipo_evento='ERROR',
                detalle={'canal': 'whatsapp', 'destinatario': contrato.celular, 'error': str(e)}
            )


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
    """Genera el PDF firmado con la firma del empleado y lo guarda en MinIO."""
    from .models import Contrato, DocumentoAdicional
    from .utils.pdf_generator import generar_pdf_firmado

    _TIPO_LABELS = {'NO_PRORROGA': 'No Prorroga', 'PRORROGA': 'Prorroga', 'TERMINACION': 'Terminacion'}

    try:
        contrato = Contrato.objects.get(id=contrato_id)
        old_firmado_key = contrato.pdf_firmado_key  # capturar ANTES de sobrescribir
        old_carta_key   = contrato.pdf_carta_key    # capturar para borrar de MinIO tras firmar

        pdf_key = generar_pdf_firmado(contrato, contrato.firma_canvas_data)

        # Red de seguridad: si ya había un PDF firmado de un ciclo anterior y no fue
        # preservado por _preservar_carta_firmada en la vista, guardarlo ahora.
        if old_firmado_key and old_firmado_key != pdf_key:
            ya_existe = DocumentoAdicional.objects.filter(
                contrato=contrato, minio_key=old_firmado_key
            ).exists()
            if not ya_existe:
                tipo_label = _TIPO_LABELS.get(contrato.tipo_carta, contrato.tipo_carta)
                DocumentoAdicional.objects.create(
                    contrato=contrato,
                    nombre_archivo=f'Carta {tipo_label} firmada (ciclo anterior).pdf',
                    minio_key=old_firmado_key,
                    subido_por=None,
                )
                logger.info(f'PDF firmado anterior preservado como DocumentoAdicional: {old_firmado_key}')

        contrato.pdf_firmado_key = pdf_key
        contrato.pdf_carta_key = ''
        contrato.save(update_fields=['pdf_firmado_key', 'pdf_carta_key'])
        logger.info(f'PDF firmado generado para contrato {contrato_id}: {pdf_key}')

        # Eliminar la carta sin firmar — ya no es necesaria; solo se conserva la firmada
        if old_carta_key and old_carta_key != pdf_key:
            from .utils.minio_client import delete_from_minio as _del
            try:
                _del(old_carta_key)
                logger.info(f'Carta sin firmar eliminada de MinIO: {old_carta_key}')
            except Exception as e:
                logger.warning(f'No se pudo eliminar carta sin firmar {old_carta_key}: {e}')
    except Contrato.DoesNotExist:
        logger.error(f'generar_y_guardar_pdf_firmado: contrato {contrato_id} no encontrado')
    except Exception as e:
        logger.error(f'Error generando PDF firmado para contrato {contrato_id}: {e}')


@shared_task(name='Contratos.tasks.alertar_contratos_urgentes', queue='contratos')
def alertar_contratos_urgentes():
    """Alerta urgente al director cuando un contrato activo vence en ≤2 días.
    Sin deduplicación: se envía aunque se haya notificado el día anterior."""
    from .models import Contrato, AsignacionCentro, EventoContrato
    from .utils.notificaciones import enviar_alerta_urgente_director
    from django.db.models import Q
    from Usuarios.models import NotificacionAdmin

    hoy = timezone.localdate()
    fecha_limite = hoy + timedelta(days=2)

    contratos = Contrato.objects.filter(
        fecha_finalizacion__lte=fecha_limite,  # hasta hoy+2
        # Sin límite inferior: incluye contratos ya expirados que no llegaron a transicionar
    ).exclude(
        Q(estado='FIRMADO') & Q(tipo_carta__in=['PRORROGA', 'TERMINACION'])
    ).exclude(
        # Estos estados ya están en manos del director o más adelante — no reenviar alerta
        estado__in=['PENDIENTE_DECISION_DIRECTOR', 'PENDIENTE_CONDICIONES_GH',
                    'PENDIENTE_NOTIFICACION_EMPLEADO', 'PENDIENTE_FIRMA_PRORROGA',
                    'PENDIENTE_FIRMA_TERMINACION', 'SIN_CANAL_CONTACTO', 'ERROR_NOTIFICACION'],
    ).select_related('sede')

    for contrato in contratos:
        if not contrato.sede:
            continue

        dias_restantes = (contrato.fecha_finalizacion - hoy).days

        asignaciones = AsignacionCentro.objects.filter(
            sede=contrato.sede,
            rol='DIRECTOR',
            activo=True,
            usuario__is_active=True,
        ).select_related('usuario')

        for asignacion in asignaciones:
            try:
                enviar_alerta_urgente_director(asignacion.usuario, contrato, dias_restantes)

                # Solo escalar a PENDIENTE_DECISION_DIRECTOR si el empleado aún no
                # firmó la NO_PRORROGA y el director no ha tomado ninguna decisión.
                # Para PRORROGA/TERMINACION el director ya decidió — NO revertir.
                if contrato.estado == 'PENDIENTE_FIRMA_NO_PRORROGA':
                    contrato.estado = 'PENDIENTE_DECISION_DIRECTOR'
                    contrato.save(update_fields=['estado'])

                EventoContrato.objects.create(
                    contrato=contrato,
                    tipo_evento='ESCALADO',
                    detalle={
                        'motivo': 'alerta_urgente_vencimiento',
                        'dias_restantes': dias_restantes,
                        'director': asignacion.usuario.correo,
                    },
                )
                NotificacionAdmin.objects.create(
                    tipo='alerta_urgente',
                    titulo=f'URGENTE — Contrato vence en {dias_restantes} día(s): {contrato.nombre_completo}',
                    cuerpo=(
                        f'{contrato.nombre_completo} (Doc: {contrato.documento_id}) — '
                        f'Cargo: {contrato.cargo}. '
                        f'Vence el {contrato.fecha_finalizacion.strftime("%d/%m/%Y")}. '
                        f'Quedan {dias_restantes} día(s). Acción inmediata requerida.'
                    ),
                    usuario=asignacion.usuario,
                    contrato=contrato,
                )
            except Exception as e:
                logger.error(
                    f'Error alerta urgente contrato {contrato.id} → {asignacion.usuario.correo}: {e}'
                )

    logger.info(f'alertar_contratos_urgentes: {contratos.count()} contratos urgentes revisados')
