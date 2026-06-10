import logging
from django.core.mail import send_mail
from django.conf import settings

logger = logging.getLogger(__name__)


def _build_firma_url(contrato) -> str:
    base = getattr(settings, 'FRONTEND_URL', 'http://localhost:5173/ver-y-data')
    return f'{base}/firma/{contrato.token_firma}'


def enviar_email_empleado(contrato):
    firma_url = _build_firma_url(contrato)
    send_mail(
        subject=f'[Euro Supermercados] Carta de {contrato.get_tipo_carta_display()} pendiente de firma',
        message=(
            f'Hola {contrato.nombre_completo},\n\n'
            f'Tienes una carta pendiente de firma. Accede aquí:\n{firma_url}\n\n'
            f'Este enlace es de un solo uso y expira en 7 días.\n\n'
            f'Inversiones Euro S.A. — Gestión Humana'
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[contrato.email],
        fail_silently=False,
    )


def enviar_whatsapp_empleado(contrato):
    firma_url = _build_firma_url(contrato)
    mensaje = (
        f'Hola {contrato.nombre_completo}, desde Euro Supermercados '
        f'te informamos que tienes una carta pendiente de firma: {firma_url}'
    )
    logger.info(f'[WA SIMULADO] → {contrato.celular}: {mensaje}')


def enviar_alerta_director(director, contratos, dias_restantes):
    nombres = '\n'.join([f'- {c.nombre_completo} ({c.cargo})' for c in contratos])
    send_mail(
        subject=f'[Euro Supermercados] {len(contratos)} contrato(s) vencen en {dias_restantes} días',
        message=(
            f'Hola {director.nombres},\n\n'
            f'Los siguientes empleados tienen contratos que vencen en {dias_restantes} días:\n\n'
            f'{nombres}\n\n'
            f'Ingresa al panel para decidir la acción a tomar.\n\n'
            f'Inversiones Euro S.A.'
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[director.correo],
        fail_silently=False,
    )
    logger.info(f'[WA SIMULADO] Alerta director {director.correo}: {len(contratos)} contratos')


def enviar_alerta_sin_firma(director, contrato):
    send_mail(
        subject=f'[Euro Supermercados] {contrato.nombre_completo} aún no ha firmado',
        message=(
            f'Hola {director.nombres},\n\n'
            f'El empleado {contrato.nombre_completo} (CC {contrato.documento_id}) '
            f'lleva más de 3 días sin firmar su carta de {contrato.get_tipo_carta_display()}.\n\n'
            f'Por favor comunícate con él/ella.\n\n'
            f'Inversiones Euro S.A.'
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[director.correo],
        fail_silently=False,
    )
    logger.info(f'[WA SIMULADO] Alerta sin firma → director {director.correo}')


def enviar_recordatorio_decision(director, contrato):
    send_mail(
        subject=f'[Euro Supermercados] Pendiente decisión: {contrato.nombre_completo}',
        message=(
            f'Hola {director.nombres},\n\n'
            f'Está pendiente tu decisión (prórroga o terminación) para {contrato.nombre_completo}, '
            f'cuyo contrato vence el {contrato.fecha_finalizacion}.\n\n'
            f'Inversiones Euro S.A.'
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[director.correo],
        fail_silently=False,
    )
