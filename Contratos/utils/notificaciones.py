import os
import logging
from django.core.mail import send_mail
from django.conf import settings

logger = logging.getLogger(__name__)

# ── Logo ──────────────────────────────────────────────────────────────────────
_LOGO_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    'logo_b64.txt',
)


def _logo_b64() -> str:
    try:
        with open(_LOGO_PATH) as f:
            return f.read().strip()
    except Exception:
        return ''


# ── Helpers HTML ──────────────────────────────────────────────────────────────

def _p(texto: str, color: str = 'rgba(255,255,255,0.65)', size: int = 14, bottom: int = 12) -> str:
    return (
        f'<p style="color:{color};font-size:{size}px;line-height:1.6;margin:0 0 {bottom}px;'
        f'font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',Arial,sans-serif;">{texto}</p>'
    )


def _info_row(label: str, valor: str) -> str:
    return (
        f'<tr>'
        f'<td style="color:rgba(255,255,255,0.40);font-size:12px;padding:4px 12px 4px 0;'
        f'width:38%;font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',Arial,sans-serif;">{label}</td>'
        f'<td style="color:rgba(255,255,255,0.85);font-size:12px;padding:4px 0;font-weight:600;'
        f'font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',Arial,sans-serif;">{valor}</td>'
        f'</tr>'
    )


def _info_table(rows: list) -> str:
    rows_html = ''.join(_info_row(label, valor) for label, valor in rows)
    return (
        '<table cellpadding="0" cellspacing="0" border="0" width="100%" style="margin:16px 0;">'
        '<tr><td style="background:rgba(255,255,255,0.05);border-radius:10px;padding:14px 18px;">'
        '<table cellpadding="0" cellspacing="0" border="0" width="100%">'
        + rows_html +
        '</table></td></tr></table>'
    )


def _btn(url: str, texto: str, color: str = '#27348B') -> str:
    return (
        '<table cellpadding="0" cellspacing="0" border="0" width="100%" style="margin:20px 0 4px;">'
        '<tr><td align="center">'
        f'<a href="{url}" target="_blank" '
        f'style="display:inline-block;background:{color};color:#ffffff;font-size:14px;font-weight:700;'
        f'text-decoration:none;padding:13px 36px;border-radius:10px;letter-spacing:0.02em;'
        f'font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',Arial,sans-serif;">'
        f'{texto}</a>'
        '</td></tr></table>'
    )


def _divider() -> str:
    return (
        '<table cellpadding="0" cellspacing="0" border="0" width="100%" style="margin:20px 0;">'
        '<tr><td style="border-top:1px solid rgba(255,255,255,0.08);height:1px;font-size:0;line-height:0;">'
        '&nbsp;</td></tr></table>'
    )


def _html_email(cuerpo_html: str) -> str:
    logo = _logo_b64()
    if logo:
        logo_tag = (
            f'<img src="data:image/png;base64,{logo}" alt="Euro Supermercados" '
            f'width="72" height="72" '
            f'style="width:72px;height:72px;border-radius:50%;display:block;'
            f'margin:0 auto 18px;border:3px solid rgba(255,255,255,0.25);" />'
        )
    else:
        logo_tag = (
            '<div style="width:72px;height:72px;border-radius:50%;background:#1a235f;'
            'margin:0 auto 18px;line-height:72px;text-align:center;'
            'font-size:18px;font-weight:900;color:#fff;">euro</div>'
        )

    return (
        '<!DOCTYPE html><html lang="es"><head>'
        '<meta charset="UTF-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
        '<title>Euro Supermercados — Gestión Humana</title>'
        '</head>'
        '<body style="margin:0;padding:0;background:#0f172a;'
        'font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',Arial,sans-serif;">'
        '<table width="100%" cellpadding="0" cellspacing="0" border="0" '
        'style="background:#0f172a;padding:40px 20px;">'
        '<tr><td align="center">'
        '<table width="520" cellpadding="0" cellspacing="0" border="0" '
        'style="max-width:520px;background:#1a1a2e;border:1px solid rgba(255,255,255,0.12);border-radius:16px;">'

        # Header
        '<tr><td align="center" style="background:linear-gradient(135deg,#27348B,#1a235f);'
        'padding:36px 40px 28px;border-radius:16px 16px 0 0;">'
        + logo_tag +
        '<h1 style="margin:0 0 6px;color:#ffffff;font-size:22px;font-weight:900;'
        'font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',Arial,sans-serif;">'
        'Euro Supermercados</h1>'
        '<p style="margin:0;color:rgba(255,255,255,0.70);font-size:13px;'
        'font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',Arial,sans-serif;">'
        'Plataforma de Gestión Humana</p>'
        '</td></tr>'

        # Cuerpo
        '<tr><td style="padding:36px 40px;">'
        + cuerpo_html +
        '</td></tr>'

        # Footer
        '<tr><td style="background:rgba(0,0,0,0.30);padding:18px 40px;text-align:center;'
        'border-radius:0 0 16px 16px;">'
        '<p style="color:rgba(255,255,255,0.30);font-size:11px;margin:0;'
        'font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',Arial,sans-serif;">'
        '&copy; 2026 Euro Supermercados &middot; Lambda Analytics SAS'
        '</p></td></tr>'

        '</table></td></tr></table>'
        '</body></html>'
    )


# ── URLs ──────────────────────────────────────────────────────────────────────

def _build_firma_url(contrato) -> str:
    base = getattr(settings, 'FRONTEND_URL', 'http://localhost:5173/ver-y-data')
    return f'{base}/firma/{contrato.token_firma}'


def _panel_url() -> str:
    base = getattr(settings, 'FRONTEND_URL', 'http://localhost:5173/ver-y-data')
    return f'{base.rstrip("/")}/login'


def _fmt_fecha(d) -> str:
    return d.strftime('%d/%m/%Y') if d else '—'


# ── Funciones de envío ────────────────────────────────────────────────────────

def enviar_email_empleado(contrato):
    firma_url = _build_firma_url(contrato)
    tipo_display = contrato.get_tipo_carta_display()

    cuerpo = (
        _p(f'Hola, <strong style="color:#ffffff;">{contrato.nombre_completo}</strong>', size=15, bottom=8)
        + _p(f'Tienes una carta de <strong style="color:#ffffff;">{tipo_display}</strong> '
             f'pendiente de firma en el sistema de Gestión Humana.', bottom=4)
        + _info_table([
            ('Tipo de carta', tipo_display),
            ('Documento', f'{contrato.tipo_documento} {contrato.documento_id}'),
            ('Cargo', contrato.cargo or '—'),
        ])
        + _btn(firma_url, 'Firmar carta ahora', '#6366f1')
        + _divider()
        + _p('Este enlace es de un solo uso y expira en '
             '<strong style="color:rgba(255,255,255,0.80);">7 días</strong>. '
             'Si tienes dudas, contacta a tu director de sede.',
             color='rgba(255,255,255,0.40)', size=11, bottom=0)
    )

    send_mail(
        subject=f'[Euro Supermercados] Carta de {tipo_display} pendiente de firma',
        message=(
            f'Hola {contrato.nombre_completo},\n\n'
            f'Tienes una carta pendiente de firma. Accede aquí:\n{firma_url}\n\n'
            f'Este enlace es de un solo uso y expira en 7 días.\n\n'
            f'Inversiones Euro S.A. — Gestión Humana'
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[contrato.email],
        html_message=_html_email(cuerpo),
        fail_silently=False,
    )


def enviar_whatsapp_empleado(contrato):
    firma_url = _build_firma_url(contrato)
    mensaje = (
        f'Hola {contrato.nombre_completo}, desde Euro Supermercados '
        f'te informamos que tienes una carta pendiente de firma: {firma_url}'
    )
    logger.info(f'[WA SIMULADO] → {contrato.celular}: {mensaje}')


def enviar_alerta_director(director, contrato, dias_restantes):
    panel = _panel_url()

    cuerpo = (
        _p(f'Hola, <strong style="color:#ffffff;">{director.nombres}</strong>', size=15, bottom=8)
        + _p('El siguiente contrato está próximo a vencer y requiere tu decisión.', bottom=4)
        + _info_table([
            ('Empleado', contrato.nombre_completo),
            ('Documento', f'{contrato.tipo_documento} {contrato.documento_id}'),
            ('Cargo', contrato.cargo or '—'),
            ('Vence el', _fmt_fecha(contrato.fecha_finalizacion)),
            ('Días restantes', str(dias_restantes)),
        ])
        + _btn(panel, 'Ver panel de contratos', '#27348B')
        + _divider()
        + _p('Ingresa al panel y toma la decisión: '
             '<strong style="color:rgba(255,255,255,0.80);">prorrogar o terminar</strong>.',
             color='rgba(255,255,255,0.40)', size=11, bottom=0)
    )

    send_mail(
        subject=f'[Euro Supermercados] Contrato próximo a vencer: {contrato.nombre_completo}',
        message=(
            f'Hola {director.nombres},\n\n'
            f'El contrato de {contrato.nombre_completo} ({contrato.tipo_documento} {contrato.documento_id}), '
            f'cargo {contrato.cargo}, vence el {contrato.fecha_finalizacion} (en {dias_restantes} días).\n\n'
            f'Ingresa al panel: {panel}\n\nInversiones Euro S.A.'
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[director.correo],
        html_message=_html_email(cuerpo),
        fail_silently=False,
    )
    logger.info(f'[CORREO] Alerta director {director.correo} → contrato {contrato.documento_id}')


def enviar_alerta_sin_firma(director, contrato):
    panel = _panel_url()
    tipo_display = contrato.get_tipo_carta_display()

    cuerpo = (
        _p(f'Hola, <strong style="color:#ffffff;">{director.nombres}</strong>', size=15, bottom=8)
        + _p('Un empleado lleva <strong style="color:#f59e0b;">más de 3 días</strong> '
             'sin firmar su carta. Por favor comunícate con él/ella.', bottom=4)
        + _info_table([
            ('Empleado', contrato.nombre_completo),
            ('Documento', f'{contrato.tipo_documento} {contrato.documento_id}'),
            ('Tipo de carta', tipo_display),
            ('Enviada el', _fmt_fecha(contrato.fecha_primer_envio)),
        ])
        + _btn(panel, 'Ver panel de contratos', '#f59e0b')
        + _divider()
        + _p('Comunícate directamente con el empleado para que complete la firma antes del vencimiento.',
             color='rgba(255,255,255,0.40)', size=11, bottom=0)
    )

    send_mail(
        subject=f'[Euro Supermercados] {contrato.nombre_completo} aún no ha firmado',
        message=(
            f'Hola {director.nombres},\n\n'
            f'El empleado {contrato.nombre_completo} (CC {contrato.documento_id}) '
            f'lleva más de 3 días sin firmar su carta de {tipo_display}.\n\n'
            f'Panel: {panel}\n\nInversiones Euro S.A.'
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[director.correo],
        html_message=_html_email(cuerpo),
        fail_silently=False,
    )
    logger.info(f'[CORREO] Alerta sin firma → director {director.correo}')


def enviar_recordatorio_decision(director, contrato):
    panel = _panel_url()

    cuerpo = (
        _p(f'Hola, <strong style="color:#ffffff;">{director.nombres}</strong>', size=15, bottom=8)
        + _p('Tienes una decisión pendiente sobre el siguiente contrato.', bottom=4)
        + _info_table([
            ('Empleado', contrato.nombre_completo),
            ('Documento', f'{contrato.tipo_documento} {contrato.documento_id}'),
            ('Cargo', contrato.cargo or '—'),
            ('Vence el', _fmt_fecha(contrato.fecha_finalizacion)),
        ])
        + _btn(panel, 'Tomar decisión', '#27348B')
        + _divider()
        + _p('Ingresa al panel de contratos para prorrogar o dar por terminado este contrato.',
             color='rgba(255,255,255,0.40)', size=11, bottom=0)
    )

    send_mail(
        subject=f'[Euro Supermercados] Pendiente decisión: {contrato.nombre_completo}',
        message=(
            f'Hola {director.nombres},\n\n'
            f'Está pendiente tu decisión para {contrato.nombre_completo}, '
            f'cuyo contrato vence el {contrato.fecha_finalizacion}.\n\n'
            f'Panel: {panel}\n\nInversiones Euro S.A.'
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[director.correo],
        html_message=_html_email(cuerpo),
        fail_silently=False,
    )


def enviar_email_gh_decision_director(gh_usuario, contrato, tipo_decision):
    """Notifica a GH que el director tomó decisión de prorrogar o terminar."""
    panel = _panel_url()
    es_prorroga = tipo_decision == 'PRORROGA'
    accion_txt = 'prorrogar' if es_prorroga else 'dar por terminado'
    color_accion = '#6366f1' if es_prorroga else '#ef4444'

    cuerpo = (
        _p(f'Hola, <strong style="color:#ffffff;">{gh_usuario.nombres}</strong>', size=15, bottom=8)
        + _p(f'El director de sede ha decidido <strong style="color:{color_accion};">{accion_txt}</strong> '
             f'el contrato del siguiente empleado. Se requiere tu intervención para definir las condiciones.', bottom=4)
        + _info_table([
            ('Empleado', contrato.nombre_completo),
            ('Documento', f'{contrato.tipo_documento} {contrato.documento_id}'),
            ('Cargo', contrato.cargo or '—'),
            ('Sede', contrato.sede.nombre if contrato.sede else '—'),
            ('Vence el', _fmt_fecha(contrato.fecha_finalizacion)),
            ('Decisión', 'Prórroga' if es_prorroga else 'Terminación'),
        ])
        + _btn(panel, 'Definir condiciones', color_accion)
        + _divider()
        + _p('Ingresa al panel de contratos y define las condiciones correspondientes.',
             color='rgba(255,255,255,0.40)', size=11, bottom=0)
    )

    send_mail(
        subject=f'[Euro Supermercados] Acción requerida: {contrato.nombre_completo} — {("Prórroga" if es_prorroga else "Terminación")}',
        message=(
            f'Hola {gh_usuario.nombres},\n\n'
            f'El director decidió {accion_txt} el contrato de {contrato.nombre_completo} '
            f'({contrato.tipo_documento} {contrato.documento_id}), cargo {contrato.cargo}.\n\n'
            f'Ingresa al panel para definir las condiciones: {panel}\n\nInversiones Euro S.A.'
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[gh_usuario.correo],
        html_message=_html_email(cuerpo),
        fail_silently=False,
    )
    logger.info(f'[CORREO] Notificación GH {gh_usuario.correo} → contrato {contrato.documento_id} decisión {tipo_decision}')


def enviar_email_director_condiciones_listas(director, contrato):
    """Notifica al director que GH ya definió las condiciones."""
    panel = _panel_url()
    es_prorroga = contrato.tipo_carta == 'PRORROGA'
    tipo_display = 'prórroga' if es_prorroga else 'terminación'
    color = '#6366f1' if es_prorroga else '#ef4444'

    rows = [
        ('Empleado', contrato.nombre_completo),
        ('Documento', f'{contrato.tipo_documento} {contrato.documento_id}'),
        ('Cargo', contrato.cargo or '—'),
        ('Tipo', 'Prórroga' if es_prorroga else 'Terminación'),
    ]
    if es_prorroga and contrato.duracion_prorroga:
        rows.append(('Duración', contrato.get_duracion_prorroga_display()))
        rows.append(('Sueldo', 'Se mantiene' if contrato.mantener_condiciones else f'${contrato.nuevo_sueldo:,.0f}'))

    if es_prorroga:
        accion_txt = 'GH notificará directamente al empleado.'
        accion_plain = 'GH notificará directamente al empleado.'
        btn_label = 'Ver en el panel'
        pie_txt = 'Puedes consultar el estado del contrato en el panel de vencimientos.'
    else:
        accion_txt = 'Ya puedes notificarle directamente.'
        accion_plain = 'Ya puedes notificar al empleado.'
        btn_label = 'Notificar al empleado'
        pie_txt = 'Ingresa al panel de contratos y usa el botón "Notificar al empleado" para enviarle la carta.'

    cuerpo = (
        _p(f'Hola, <strong style="color:#ffffff;">{director.nombres}</strong>', size=15, bottom=8)
        + _p(f'Gestión Humana ha definido las condiciones para la '
             f'<strong style="color:{color};">{tipo_display}</strong> del siguiente empleado. '
             f'{accion_txt}', bottom=4)
        + _info_table(rows)
        + _btn(panel, btn_label, color)
        + _divider()
        + _p(pie_txt, color='rgba(255,255,255,0.40)', size=11, bottom=0)
    )

    send_mail(
        subject=f'[Euro Supermercados] Condiciones listas — {contrato.nombre_completo}',
        message=(
            f'Hola {director.nombres},\n\n'
            f'Gestión Humana ha definido las condiciones para la {tipo_display} de '
            f'{contrato.nombre_completo}. {accion_plain}\n\n'
            f'Panel: {panel}\n\nInversiones Euro S.A.'
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[director.correo],
        html_message=_html_email(cuerpo),
        fail_silently=False,
    )
    logger.info(f'[CORREO] Condiciones listas → director {director.correo} contrato {contrato.documento_id}')


def enviar_email_gh_contrato_firmado(gh_usuario, contrato):
    """Notifica a GH que el empleado firmó el contrato."""
    panel = _panel_url()
    tipo_display = contrato.get_tipo_carta_display()

    cuerpo = (
        _p(f'Hola, <strong style="color:#ffffff;">{gh_usuario.nombres}</strong>', size=15, bottom=8)
        + _p(f'El empleado <strong style="color:#22c55e;">{contrato.nombre_completo}</strong> '
             f'ha firmado su carta de <strong style="color:#ffffff;">{tipo_display}</strong> exitosamente.', bottom=4)
        + _info_table([
            ('Empleado', contrato.nombre_completo),
            ('Documento', f'{contrato.tipo_documento} {contrato.documento_id}'),
            ('Cargo', contrato.cargo or '—'),
            ('Sede', contrato.sede.nombre if contrato.sede else '—'),
            ('Tipo de carta', tipo_display),
            ('Fecha firma', _fmt_fecha(contrato.fecha_firma)),
        ])
        + _btn(panel, 'Ver contrato firmado', '#22c55e')
        + _divider()
        + _p('El documento firmado está disponible en el panel de contratos.',
             color='rgba(255,255,255,0.40)', size=11, bottom=0)
    )

    send_mail(
        subject=f'[Euro Supermercados] Contrato firmado: {contrato.nombre_completo}',
        message=(
            f'Hola {gh_usuario.nombres},\n\n'
            f'{contrato.nombre_completo} ({contrato.tipo_documento} {contrato.documento_id}) '
            f'ha firmado su carta de {tipo_display}.\n\n'
            f'Panel: {panel}\n\nInversiones Euro S.A.'
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[gh_usuario.correo],
        html_message=_html_email(cuerpo),
        fail_silently=False,
    )
    logger.info(f'[CORREO] Contrato firmado → GH {gh_usuario.correo} contrato {contrato.documento_id}')


def enviar_alerta_urgente_director(director, contrato, dias_restantes):
    panel = _panel_url()
    if dias_restantes == 0:
        dias_txt = '¡HOY!'
        color_dias = '#ef4444'
    elif dias_restantes == 1:
        dias_txt = 'mañana (1 día)'
        color_dias = '#f59e0b'
    else:
        dias_txt = f'en {dias_restantes} días'
        color_dias = '#f59e0b'

    cuerpo = (
        _p(f'Hola, <strong style="color:#ffffff;">{director.nombres}</strong>', size=15, bottom=8)
        + f'<p style="color:#ef4444;font-size:15px;font-weight:700;margin:0 0 12px;'
          f'font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',Arial,sans-serif;">'
          f'⚠️ ACCIÓN URGENTE REQUERIDA</p>'
        + _p(f'El siguiente contrato vence '
             f'<strong style="color:{color_dias};">{dias_txt}</strong> '
             f'y aún no ha sido resuelto.', bottom=4)
        + _info_table([
            ('Empleado', contrato.nombre_completo),
            ('Documento', f'{contrato.tipo_documento} {contrato.documento_id}'),
            ('Cargo', contrato.cargo or '—'),
            ('Vence el', _fmt_fecha(contrato.fecha_finalizacion)),
            ('Estado', contrato.estado.replace('_', ' ')),
        ])
        + _btn(panel, 'Acción urgente requerida', '#ef4444')
        + _divider()
        + _p('Ingresa al panel inmediatamente y toma la decisión correspondiente.',
             color='rgba(255,255,255,0.40)', size=11, bottom=0)
    )

    send_mail(
        subject=f'[URGENTE] Contrato vence {dias_txt} — {contrato.nombre_completo}',
        message=(
            f'Hola {director.nombres},\n\n'
            f'ALERTA URGENTE: El contrato de {contrato.nombre_completo} '
            f'({contrato.tipo_documento} {contrato.documento_id}), cargo {contrato.cargo}, '
            f'vence el {_fmt_fecha(contrato.fecha_finalizacion)} ({dias_txt}).\n\n'
            f'Estado: {contrato.estado.replace("_", " ")}\n\n'
            f'Panel: {panel}\n\nInversiones Euro S.A. — Gestión Humana'
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[director.correo],
        html_message=_html_email(cuerpo),
        fail_silently=False,
    )
    logger.info(
        f'[CORREO] Alerta urgente → director {director.correo} '
        f'contrato {contrato.documento_id} vence {contrato.fecha_finalizacion}'
    )
