import logging
import requests
from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger(__name__)

_GRAPH_API_URL = 'https://graph.microsoft.com/v1.0'
_GRAPH_SCOPE   = 'https://graph.microsoft.com/.default'


class MicrosoftGraphEmailBackend(BaseEmailBackend):
    """
    Backend de email que envía a través de Microsoft Graph API usando
    OAuth2 client-credentials (AZURE_CLIENT_ID / AZURE_SECRET_KEY / AZURE_TENANT_ID).
    Compatible con send_mail() y EmailMultiAlternatives de Django sin cambios en notificaciones.py.
    """

    def __init__(self, fail_silently=False, **kwargs):
        super().__init__(fail_silently=fail_silently, **kwargs)
        from django.conf import settings
        self._client_id     = settings.AZURE_CLIENT_ID
        self._client_secret = settings.AZURE_SECRET_KEY
        self._tenant_id     = settings.AZURE_TENANT_ID
        self._sender        = settings.DEFAULT_FROM_EMAIL

    def _get_token(self):
        url  = f'https://login.microsoftonline.com/{self._tenant_id}/oauth2/v2.0/token'
        data = {
            'client_id':     self._client_id,
            'client_secret': self._client_secret,
            'scope':         _GRAPH_SCOPE,
            'grant_type':    'client_credentials',
        }
        resp = requests.post(url, data=data, timeout=15)
        if resp.status_code == 200:
            return resp.json()['access_token']
        raise RuntimeError(f'Error obteniendo token Azure: {resp.text}')

    def send_messages(self, email_messages):
        if not email_messages:
            return 0

        try:
            token = self._get_token()
        except Exception as exc:
            if not self.fail_silently:
                raise
            logger.error('MicrosoftGraphEmailBackend: error obteniendo token — %s', exc)
            return 0

        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type':  'application/json; charset=utf-8',
        }
        send_url = f'{_GRAPH_API_URL}/users/{self._sender}/sendMail'
        sent     = 0

        for msg in email_messages:
            try:
                # Preferir HTML si el mensaje tiene alternativas (EmailMultiAlternatives)
                body_content = msg.body
                body_type    = 'Text'
                if hasattr(msg, 'alternatives'):
                    for content, mimetype in msg.alternatives:
                        if mimetype == 'text/html':
                            body_content = content
                            body_type    = 'HTML'
                            break

                payload = {
                    'message': {
                        'subject': msg.subject,
                        'body': {'contentType': body_type, 'content': body_content},
                        'toRecipients': [
                            {'emailAddress': {'address': a}} for a in msg.to
                        ],
                    },
                    'saveToSentItems': 'true',
                }

                if msg.cc:
                    payload['message']['ccRecipients'] = [
                        {'emailAddress': {'address': a}} for a in msg.cc
                    ]
                if msg.bcc:
                    payload['message']['bccRecipients'] = [
                        {'emailAddress': {'address': a}} for a in msg.bcc
                    ]

                response = requests.post(send_url, json=payload, headers=headers, timeout=30)

                if response.status_code == 202:
                    sent += 1
                    logger.debug('Correo enviado a %s vía Microsoft Graph', msg.to)
                else:
                    logger.error(
                        'Graph API error %s al enviar a %s: %s',
                        response.status_code, msg.to, response.text,
                    )
                    if not self.fail_silently:
                        response.raise_for_status()

            except Exception as exc:
                logger.error('Error enviando correo a %s: %s', msg.to, exc)
                if not self.fail_silently:
                    raise

        return sent
