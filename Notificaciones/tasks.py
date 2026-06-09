import logging
from celery import shared_task
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def enviar_otp_email(self, usuario_id, codigo_otp):
    try:
        from Usuarios.models import Usuario
        usuario = Usuario.objects.get(id=usuario_id)

        context = {
            'nombre': usuario.obtener_nombre_completo(),
            'codigo': codigo_otp,
            'expiry_minutes': settings.OTP_EXPIRY_MINUTES,
        }

        html_message = render_to_string('emails/otp_email.html', context)
        plain_message = strip_tags(html_message)

        send_mail(
            subject='Tu código de acceso — Euro VER & DATA',
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[usuario.correo],
            html_message=html_message,
            fail_silently=False,
        )
        logger.info(f'OTP enviado a {usuario.correo}')

    except Exception as e:
        logger.error(f'Error enviando OTP a usuario {usuario_id}: {e}', exc_info=True)
        raise self.retry(exc=e)
