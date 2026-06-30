import logging
from django.core.mail import send_mail
from django.conf import settings

logger = logging.getLogger(__name__)

# -- Logo (base64 embebido -- mismo PNG que otp_email.html) -------------------
_LOGO_B64 = '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'

# -- Helpers HTML -------------------------------------------------------------------

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
    logo_tag = (
        f'<img src="data:image/png;base64,{_LOGO_B64}" alt="Euro Supermercados" '
        f'width="72" height="72" '
        f'style="width:72px;height:72px;border-radius:50%;display:block;'
        f'margin:0 auto 18px;border:3px solid rgba(255,255,255,0.25);" />'
    )

    return (
        '<!DOCTYPE html><html lang="es"><head>'
        '<meta charset="UTF-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
        '<title>Euro Supermercados â€” GestiÃ³n Humana</title>'
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
        'Plataforma de GestiÃ³n Humana</p>'
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


# â”€â”€ URLs â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _build_firma_url(contrato) -> str:
    base = getattr(settings, 'FRONTEND_URL', 'http://localhost:5173/ver-y-data')
    return f'{base}/firma/{contrato.token_firma}'


def _panel_url() -> str:
    base = getattr(settings, 'FRONTEND_URL', 'http://localhost:5173/ver-y-data')
    return f'{base.rstrip("/")}/login'


def _fmt_fecha(d) -> str:
    return d.strftime('%d/%m/%Y') if d else 'â€”'


# â”€â”€ Funciones de envÃ­o â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def enviar_email_empleado(contrato):
    firma_url = _build_firma_url(contrato)
    tipo_display = contrato.get_tipo_carta_display()

    cuerpo = (
        _p(f'Hola, <strong style="color:#ffffff;">{contrato.nombre_completo}</strong>', size=15, bottom=8)
        + _p(f'Tienes una carta de <strong style="color:#ffffff;">{tipo_display}</strong> '
             f'pendiente de firma en el sistema de GestiÃ³n Humana.', bottom=4)
        + _info_table([
            ('Tipo de carta', tipo_display),
            ('Documento', f'{contrato.tipo_documento} {contrato.documento_id}'),
            ('Cargo', contrato.cargo or 'â€”'),
        ])
        + _btn(firma_url, 'Firmar carta ahora', '#6366f1')
        + _divider()
        + _p('Este enlace es de un solo uso y expira en '
             '<strong style="color:rgba(255,255,255,0.80);">7 dÃ­as</strong>. '
             'Si tienes dudas, contacta a tu director de sede.',
             color='rgba(255,255,255,0.40)', size=11, bottom=0)
    )

    send_mail(
        subject=f'[Euro Supermercados] Carta de {tipo_display} pendiente de firma',
        message=(
            f'Hola {contrato.nombre_completo},\n\n'
            f'Tienes una carta pendiente de firma. Accede aquÃ­:\n{firma_url}\n\n'
            f'Este enlace es de un solo uso y expira en 7 dÃ­as.\n\n'
            f'Inversiones Euro S.A. â€” GestiÃ³n Humana'
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
    logger.info(f'[WA SIMULADO] â†' {contrato.celular}: {mensaje}')


def enviar_alerta_director(director, contrato, dias_restantes):
    panel = _panel_url()

    cuerpo = (
        _p(f'Hola, <strong style="color:#ffffff;">{director.nombres}</strong>', size=15, bottom=8)
        + _p('El siguiente contrato estÃ¡ prÃ³ximo a vencer y requiere tu decisiÃ³n.', bottom=4)
        + _info_table([
            ('Empleado', contrato.nombre_completo),
            ('Documento', f'{contrato.tipo_documento} {contrato.documento_id}'),
            ('Cargo', contrato.cargo or 'â€”'),
            ('Vence el', _fmt_fecha(contrato.fecha_finalizacion)),
            ('DÃ­as restantes', str(dias_restantes)),
        ])
        + _btn(panel, 'Ver panel de contratos', '#27348B')
        + _divider()
        + _p('Ingresa al panel y toma la decisiÃ³n: '
             '<strong style="color:rgba(255,255,255,0.80);">prorrogar o terminar</strong>.',
             color='rgba(255,255,255,0.40)', size=11, bottom=0)
    )

    send_mail(
        subject=f'[Euro Supermercados] Contrato prÃ³ximo a vencer: {contrato.nombre_completo}',
        message=(
            f'Hola {director.nombres},\n\n'
            f'El contrato de {contrato.nombre_completo} ({contrato.tipo_documento} {contrato.documento_id}), '
            f'cargo {contrato.cargo}, vence el {contrato.fecha_finalizacion} (en {dias_restantes} dÃ­as).\n\n'
            f'Ingresa al panel: {panel}\n\nInversiones Euro S.A.'
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[director.correo],
        html_message=_html_email(cuerpo),
        fail_silently=False,
    )
    logger.info(f'[CORREO] Alerta director {director.correo} â†' contrato {contrato.documento_id}')


def enviar_alerta_sin_firma(director, contrato):
    panel = _panel_url()
    tipo_display = contrato.get_tipo_carta_display()

    cuerpo = (
        _p(f'Hola, <strong style="color:#ffffff;">{director.nombres}</strong>', size=15, bottom=8)
        + _p('Un empleado lleva <strong style="color:#f59e0b;">mÃ¡s de 3 dÃ­as</strong> '
             'sin firmar su carta. Por favor comunÃ­cate con Ã©l/ella.', bottom=4)
        + _info_table([
            ('Empleado', contrato.nombre_completo),
            ('Documento', f'{contrato.tipo_documento} {contrato.documento_id}'),
            ('Tipo de carta', tipo_display),
            ('Enviada el', _fmt_fecha(contrato.fecha_primer_envio)),
        ])
        + _btn(panel, 'Ver panel de contratos', '#f59e0b')
        + _divider()
        + _p('ComunÃ­cate directamente con el empleado para que complete la firma antes del vencimiento.',
             color='rgba(255,255,255,0.40)', size=11, bottom=0)
    )

    send_mail(
        subject=f'[Euro Supermercados] {contrato.nombre_completo} aÃºn no ha firmado',
        message=(
            f'Hola {director.nombres},\n\n'
            f'El empleado {contrato.nombre_completo} (CC {contrato.documento_id}) '
            f'lleva mÃ¡s de 3 dÃ­as sin firmar su carta de {tipo_display}.\n\n'
            f'Panel: {panel}\n\nInversiones Euro S.A.'
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[director.correo],
        html_message=_html_email(cuerpo),
        fail_silently=False,
    )
    logger.info(f'[CORREO] Alerta sin firma â†' director {director.correo}')


def enviar_recordatorio_decision(director, contrato):
    panel = _panel_url()

    cuerpo = (
        _p(f'Hola, <strong style="color:#ffffff;">{director.nombres}</strong>', size=15, bottom=8)
        + _p('Tienes una decisiÃ³n pendiente sobre el siguiente contrato.', bottom=4)
        + _info_table([
            ('Empleado', contrato.nombre_completo),
            ('Documento', f'{contrato.tipo_documento} {contrato.documento_id}'),
            ('Cargo', contrato.cargo or 'â€”'),
            ('Vence el', _fmt_fecha(contrato.fecha_finalizacion)),
        ])
        + _btn(panel, 'Tomar decisiÃ³n', '#27348B')
        + _divider()
        + _p('Ingresa al panel de contratos para prorrogar o dar por terminado este contrato.',
             color='rgba(255,255,255,0.40)', size=11, bottom=0)
    )

    send_mail(
        subject=f'[Euro Supermercados] Pendiente decisiÃ³n: {contrato.nombre_completo}',
        message=(
            f'Hola {director.nombres},\n\n'
            f'EstÃ¡ pendiente tu decisiÃ³n para {contrato.nombre_completo}, '
            f'cuyo contrato vence el {contrato.fecha_finalizacion}.\n\n'
            f'Panel: {panel}\n\nInversiones Euro S.A.'
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[director.correo],
        html_message=_html_email(cuerpo),
        fail_silently=False,
    )


def enviar_recordatorio_decision_digest(director, contratos: list):
    """Un solo correo al director con TODOS sus contratos pendientes de decisiÃ³n."""
    panel = _panel_url()
    n = len(contratos)

    filas_html = ''
    for c in contratos:
        dias = (c.fecha_finalizacion - c.fecha_finalizacion.today()).days if hasattr(c.fecha_finalizacion, 'today') else 'â€”'
        try:
            from django.utils import timezone as _tz
            dias = (c.fecha_finalizacion - _tz.localdate()).days
        except Exception:
            dias = 'â€”'
        color_dias = '#ef4444' if isinstance(dias, int) and dias <= 5 else 'rgba(255,255,255,0.75)'
        filas_html += (
            '<tr style="border-bottom:1px solid rgba(255,255,255,0.06);">'
            f'<td style="padding:9px 8px;color:rgba(255,255,255,0.85);font-size:12px;">{c.nombre_completo}</td>'
            f'<td style="padding:9px 8px;color:rgba(255,255,255,0.55);font-size:11px;">{c.cargo or "â€”"}</td>'
            f'<td style="padding:9px 8px;color:{color_dias};font-size:12px;font-weight:600;white-space:nowrap;">'
            f'{_fmt_fecha(c.fecha_finalizacion)}</td>'
            '</tr>'
        )

    tabla_contratos = (
        '<table cellpadding="0" cellspacing="0" border="0" width="100%" '
        'style="margin:16px 0;border-radius:10px;overflow:hidden;background:rgba(255,255,255,0.04);">'
        '<thead><tr style="background:rgba(255,255,255,0.08);">'
        '<th style="padding:8px;text-align:left;color:rgba(255,255,255,0.40);font-size:11px;font-weight:600;">Empleado</th>'
        '<th style="padding:8px;text-align:left;color:rgba(255,255,255,0.40);font-size:11px;font-weight:600;">Cargo</th>'
        '<th style="padding:8px;text-align:left;color:rgba(255,255,255,0.40);font-size:11px;font-weight:600;">Vence</th>'
        '</tr></thead>'
        f'<tbody>{filas_html}</tbody>'
        '</table>'
    )

    cuerpo = (
        _p(f'Hola, <strong style="color:#ffffff;">{director.nombres}</strong>', size=15, bottom=8)
        + _p(
            f'Tienes <strong style="color:#f59e0b;">{n} contrato{"s" if n != 1 else ""}</strong> '
            f'pendiente{"s" if n != 1 else ""} de decisiÃ³n.',
            bottom=4,
        )
        + tabla_contratos
        + _btn(panel, 'Ir al panel de contratos', '#27348B')
        + _divider()
        + _p(
            'Ingresa al panel y toma una decisiÃ³n (prÃ³rroga o terminaciÃ³n) para cada contrato.',
            color='rgba(255,255,255,0.40)', size=11, bottom=0,
        )
    )

    plain = (
        f'Hola {director.nombres},\n\n'
        f'Tienes {n} contrato{"s" if n != 1 else ""} pendiente{"s" if n != 1 else ""} de decisiÃ³n:\n\n'
        + ''.join(f'- {c.nombre_completo} ({c.cargo or "â€”"}) vence {c.fecha_finalizacion}\n' for c in contratos)
        + f'\nPanel: {panel}\n\nInversiones Euro S.A.'
    )

    send_mail(
        subject=f'[Euro Supermercados] {n} contrato{"s" if n != 1 else ""} pendiente{"s" if n != 1 else ""} de decisiÃ³n',
        message=plain,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[director.correo],
        html_message=_html_email(cuerpo),
        fail_silently=False,
    )
    logger.info(f'[CORREO] Digest decisiones â†' director {director.correo} ({n} contratos)')


def enviar_email_gh_decision_director(gh_usuario, contrato, tipo_decision):
    """Notifica a GH que el director tomÃ³ decisiÃ³n de prorrogar o terminar."""
    panel = _panel_url()
    es_prorroga = tipo_decision == 'PRORROGA'
    accion_txt = 'prorrogar' if es_prorroga else 'dar por terminado'
    color_accion = '#6366f1' if es_prorroga else '#ef4444'

    cuerpo = (
        _p(f'Hola, <strong style="color:#ffffff;">{gh_usuario.nombres}</strong>', size=15, bottom=8)
        + _p(f'El director de sede ha decidido <strong style="color:{color_accion};">{accion_txt}</strong> '
             f'el contrato del siguiente empleado. Se requiere tu intervenciÃ³n para definir las condiciones.', bottom=4)
        + _info_table([
            ('Empleado', contrato.nombre_completo),
            ('Documento', f'{contrato.tipo_documento} {contrato.documento_id}'),
            ('Cargo', contrato.cargo or 'â€”'),
            ('Sede', contrato.sede.nombre if contrato.sede else 'â€”'),
            ('Vence el', _fmt_fecha(contrato.fecha_finalizacion)),
            ('DecisiÃ³n', 'PrÃ³rroga' if es_prorroga else 'TerminaciÃ³n'),
        ])
        + _btn(panel, 'Definir condiciones', color_accion)
        + _divider()
        + _p('Ingresa al panel de contratos y define las condiciones correspondientes.',
             color='rgba(255,255,255,0.40)', size=11, bottom=0)
    )

    send_mail(
        subject=f'[Euro Supermercados] AcciÃ³n requerida: {contrato.nombre_completo} â€” {("PrÃ³rroga" if es_prorroga else "TerminaciÃ³n")}',
        message=(
            f'Hola {gh_usuario.nombres},\n\n'
            f'El director decidiÃ³ {accion_txt} el contrato de {contrato.nombre_completo} '
            f'({contrato.tipo_documento} {contrato.documento_id}), cargo {contrato.cargo}.\n\n'
            f'Ingresa al panel para definir las condiciones: {panel}\n\nInversiones Euro S.A.'
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[gh_usuario.correo],
        html_message=_html_email(cuerpo),
        fail_silently=False,
    )
    logger.info(f'[CORREO] NotificaciÃ³n GH {gh_usuario.correo} â†' contrato {contrato.documento_id} decisiÃ³n {tipo_decision}')


def enviar_email_director_condiciones_listas(director, contrato):
    """Notifica al director que GH ya definiÃ³ las condiciones."""
    panel = _panel_url()
    es_prorroga = contrato.tipo_carta == 'PRORROGA'
    tipo_display = 'prÃ³rroga' if es_prorroga else 'terminaciÃ³n'
    color = '#6366f1' if es_prorroga else '#ef4444'

    rows = [
        ('Empleado', contrato.nombre_completo),
        ('Documento', f'{contrato.tipo_documento} {contrato.documento_id}'),
        ('Cargo', contrato.cargo or 'â€”'),
        ('Tipo', 'PrÃ³rroga' if es_prorroga else 'TerminaciÃ³n'),
    ]
    if es_prorroga and contrato.duracion_prorroga:
        rows.append(('DuraciÃ³n', contrato.get_duracion_prorroga_display()))
        rows.append(('Sueldo', 'Se mantiene' if contrato.mantener_condiciones else f'${contrato.nuevo_sueldo:,.0f}'))

    if es_prorroga:
        accion_txt = 'GH notificarÃ¡ directamente al empleado.'
        accion_plain = 'GH notificarÃ¡ directamente al empleado.'
        btn_label = 'Ver en el panel'
        pie_txt = 'Puedes consultar el estado del contrato en el panel de vencimientos.'
    else:
        accion_txt = 'Ya puedes notificarle directamente.'
        accion_plain = 'Ya puedes notificar al empleado.'
        btn_label = 'Notificar al empleado'
        pie_txt = 'Ingresa al panel de contratos y usa el botÃ³n "Notificar al empleado" para enviarle la carta.'

    cuerpo = (
        _p(f'Hola, <strong style="color:#ffffff;">{director.nombres}</strong>', size=15, bottom=8)
        + _p(f'GestiÃ³n Humana ha definido las condiciones para la '
             f'<strong style="color:{color};">{tipo_display}</strong> del siguiente empleado. '
             f'{accion_txt}', bottom=4)
        + _info_table(rows)
        + _btn(panel, btn_label, color)
        + _divider()
        + _p(pie_txt, color='rgba(255,255,255,0.40)', size=11, bottom=0)
    )

    send_mail(
        subject=f'[Euro Supermercados] Condiciones listas â€” {contrato.nombre_completo}',
        message=(
            f'Hola {director.nombres},\n\n'
            f'GestiÃ³n Humana ha definido las condiciones para la {tipo_display} de '
            f'{contrato.nombre_completo}. {accion_plain}\n\n'
            f'Panel: {panel}\n\nInversiones Euro S.A.'
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[director.correo],
        html_message=_html_email(cuerpo),
        fail_silently=False,
    )
    logger.info(f'[CORREO] Condiciones listas â†' director {director.correo} contrato {contrato.documento_id}')


def enviar_email_gh_contrato_firmado(gh_usuario, contrato):
    """Notifica a GH que el empleado firmÃ³ el contrato."""
    panel = _panel_url()
    tipo_display = contrato.get_tipo_carta_display()

    cuerpo = (
        _p(f'Hola, <strong style="color:#ffffff;">{gh_usuario.nombres}</strong>', size=15, bottom=8)
        + _p(f'El empleado <strong style="color:#22c55e;">{contrato.nombre_completo}</strong> '
             f'ha firmado su carta de <strong style="color:#ffffff;">{tipo_display}</strong> exitosamente.', bottom=4)
        + _info_table([
            ('Empleado', contrato.nombre_completo),
            ('Documento', f'{contrato.tipo_documento} {contrato.documento_id}'),
            ('Cargo', contrato.cargo or 'â€”'),
            ('Sede', contrato.sede.nombre if contrato.sede else 'â€”'),
            ('Tipo de carta', tipo_display),
            ('Fecha firma', _fmt_fecha(contrato.fecha_firma)),
        ])
        + _btn(panel, 'Ver contrato firmado', '#22c55e')
        + _divider()
        + _p('El documento firmado estÃ¡ disponible en el panel de contratos.',
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
    logger.info(f'[CORREO] Contrato firmado â†' GH {gh_usuario.correo} contrato {contrato.documento_id}')


def enviar_alerta_gh(gh, contrato, dias_restantes):
    """Notifica a GH que un contrato está próximo a vencer y requiere su decisión."""
    panel = _panel_url()

    cuerpo = (
        _p(f'Hola, <strong style="color:#ffffff;">{gh.nombres}</strong>', size=15, bottom=8)
        + _p('El siguiente contrato está próximo a vencer y requiere tu decisión '
             '(<strong style="color:#ffffff;">prorrogar o terminar</strong>).', bottom=4)
        + _info_table([
            ('Empleado', contrato.nombre_completo),
            ('Documento', f'{contrato.tipo_documento} {contrato.documento_id}'),
            ('Cargo', contrato.cargo or '—'),
            ('Vence el', _fmt_fecha(contrato.fecha_finalizacion)),
            ('Días restantes', str(dias_restantes)),
        ])
        + _btn(panel, 'Tomar decisión', '#0ea5e9')
        + _divider()
        + _p('Ingresa al panel de contratos y toma la decisión: '
             '<strong style="color:rgba(255,255,255,0.80);">prorrogar o terminar</strong>.',
             color='rgba(255,255,255,0.40)', size=11, bottom=0)
    )

    send_mail(
        subject=f'[Euro Supermercados] Contrato próximo a vencer: {contrato.nombre_completo}',
        message=(
            f'Hola {gh.nombres},\n\n'
            f'El contrato de {contrato.nombre_completo} ({contrato.tipo_documento} {contrato.documento_id}), '
            f'cargo {contrato.cargo}, vence el {contrato.fecha_finalizacion} (en {dias_restantes} días).\n\n'
            f'Ingresa al panel para tomar la decisión: {panel}\n\nInversiones Euro S.A.'
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[gh.correo],
        html_message=_html_email(cuerpo),
        fail_silently=False,
    )
    logger.info(f'[CORREO] Alerta GH {gh.correo} → contrato {contrato.documento_id}')


def enviar_recordatorio_decision_gh_digest(gh, contratos: list):
    """Un solo correo a GH con TODOS sus contratos pendientes de decisión."""
    panel = _panel_url()
    n = len(contratos)

    filas_html = ''
    for c in contratos:
        try:
            from django.utils import timezone as _tz
            dias = (c.fecha_finalizacion - _tz.localdate()).days
        except Exception:
            dias = '—'
        color_dias = '#ef4444' if isinstance(dias, int) and dias <= 5 else 'rgba(255,255,255,0.75)'
        filas_html += (
            '<tr style="border-bottom:1px solid rgba(255,255,255,0.06);">'
            f'<td style="padding:9px 8px;color:rgba(255,255,255,0.85);font-size:12px;">{c.nombre_completo}</td>'
            f'<td style="padding:9px 8px;color:rgba(255,255,255,0.55);font-size:11px;">{c.cargo or "—"}</td>'
            f'<td style="padding:9px 8px;color:{color_dias};font-size:12px;font-weight:600;white-space:nowrap;">'
            f'{_fmt_fecha(c.fecha_finalizacion)}</td>'
            '</tr>'
        )

    tabla_contratos = (
        '<table cellpadding="0" cellspacing="0" border="0" width="100%" '
        'style="margin:16px 0;border-radius:10px;overflow:hidden;background:rgba(255,255,255,0.04);">'
        '<thead><tr style="background:rgba(255,255,255,0.08);">'
        '<th style="padding:8px;text-align:left;color:rgba(255,255,255,0.40);font-size:11px;font-weight:600;">Empleado</th>'
        '<th style="padding:8px;text-align:left;color:rgba(255,255,255,0.40);font-size:11px;font-weight:600;">Cargo</th>'
        '<th style="padding:8px;text-align:left;color:rgba(255,255,255,0.40);font-size:11px;font-weight:600;">Vence</th>'
        '</tr></thead>'
        f'<tbody>{filas_html}</tbody>'
        '</table>'
    )

    cuerpo = (
        _p(f'Hola, <strong style="color:#ffffff;">{gh.nombres}</strong>', size=15, bottom=8)
        + _p(
            f'Tienes <strong style="color:#0ea5e9;">{n} contrato{"s" if n != 1 else ""}</strong> '
            f'pendiente{"s" if n != 1 else ""} de decisión.',
            bottom=4,
        )
        + tabla_contratos
        + _btn(panel, 'Ir al panel de contratos', '#0ea5e9')
        + _divider()
        + _p(
            'Ingresa al panel y toma una decisión (prórroga o terminación) para cada contrato.',
            color='rgba(255,255,255,0.40)', size=11, bottom=0,
        )
    )

    plain = (
        f'Hola {gh.nombres},\n\n'
        f'Tienes {n} contrato{"s" if n != 1 else ""} pendiente{"s" if n != 1 else ""} de decisión:\n\n'
        + ''.join(f'- {c.nombre_completo} ({c.cargo or "—"}) vence {c.fecha_finalizacion}\n' for c in contratos)
        + f'\nPanel: {panel}\n\nInversiones Euro S.A.'
    )

    send_mail(
        subject=f'[Euro Supermercados] {n} contrato{"s" if n != 1 else ""} pendiente{"s" if n != 1 else ""} de decisión',
        message=plain,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[gh.correo],
        html_message=_html_email(cuerpo),
        fail_silently=False,
    )
    logger.info(f'[CORREO] Digest decisiones GH → {gh.correo} ({n} contratos)')


def enviar_alerta_gh_sin_firma(gh, contrato):
    """4to escalamiento sin firma — notifica a GH como escalamiento final."""
    panel = _panel_url()
    tipo_display = contrato.get_tipo_carta_display()

    cuerpo = (
        _p(f'Hola, <strong style="color:#ffffff;">{gh.nombres}</strong>', size=15, bottom=8)
        + f'<p style="color:#ef4444;font-size:14px;font-weight:700;margin:0 0 12px;'
          f'font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',Arial,sans-serif;">'
          f'⚠ ESCALAMIENTO FINAL</p>'
        + _p('Un empleado lleva <strong style="color:#ef4444;">más de 12 días</strong> '
             'sin firmar su carta. Se han agotado los recordatorios al director. '
             'Se requiere intervención directa de Gestión Humana.', bottom=4)
        + _info_table([
            ('Empleado', contrato.nombre_completo),
            ('Documento', f'{contrato.tipo_documento} {contrato.documento_id}'),
            ('Tipo de carta', tipo_display),
            ('Enviada el', _fmt_fecha(contrato.fecha_primer_envio)),
            ('Escalamientos previos', str(contrato.contador_escalamientos)),
        ])
        + _btn(panel, 'Ver panel de contratos', '#ef4444')
        + _divider()
        + _p('Este es el último aviso automático. Por favor comunícate directamente con el empleado.',
             color='rgba(255,255,255,0.40)', size=11, bottom=0)
    )

    send_mail(
        subject=f'[Euro Supermercados] ESCALAMIENTO FINAL — {contrato.nombre_completo} no ha firmado',
        message=(
            f'Hola {gh.nombres},\n\n'
            f'ESCALAMIENTO FINAL: El empleado {contrato.nombre_completo} (CC {contrato.documento_id}) '
            f'lleva más de 12 días sin firmar su carta de {tipo_display}. '
            f'Se han enviado {contrato.contador_escalamientos} recordatorio(s) al director sin resultado.\n\n'
            f'Panel: {panel}\n\nInversiones Euro S.A.'
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[gh.correo],
        html_message=_html_email(cuerpo),
        fail_silently=False,
    )
    logger.info(f'[CORREO] Escalamiento final sin firma → GH {gh.correo}')


def enviar_alerta_urgente_director(director, contrato, dias_restantes):
    panel = _panel_url()
    if dias_restantes == 0:
        dias_txt = 'Â¡HOY!'
        color_dias = '#ef4444'
    elif dias_restantes == 1:
        dias_txt = 'maÃ±ana (1 dÃ­a)'
        color_dias = '#f59e0b'
    else:
        dias_txt = f'en {dias_restantes} dÃ­as'
        color_dias = '#f59e0b'

    cuerpo = (
        _p(f'Hola, <strong style="color:#ffffff;">{director.nombres}</strong>', size=15, bottom=8)
        + f'<p style="color:#ef4444;font-size:15px;font-weight:700;margin:0 0 12px;'
          f'font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',Arial,sans-serif;">'
          f'âš ï¸ ACCIÃ“N URGENTE REQUERIDA</p>'
        + _p(f'El siguiente contrato vence '
             f'<strong style="color:{color_dias};">{dias_txt}</strong> '
             f'y aÃºn no ha sido resuelto.', bottom=4)
        + _info_table([
            ('Empleado', contrato.nombre_completo),
            ('Documento', f'{contrato.tipo_documento} {contrato.documento_id}'),
            ('Cargo', contrato.cargo or 'â€”'),
            ('Vence el', _fmt_fecha(contrato.fecha_finalizacion)),
            ('Estado', contrato.estado.replace('_', ' ')),
        ])
        + _btn(panel, 'AcciÃ³n urgente requerida', '#ef4444')
        + _divider()
        + _p('Ingresa al panel inmediatamente y toma la decisiÃ³n correspondiente.',
             color='rgba(255,255,255,0.40)', size=11, bottom=0)
    )

    send_mail(
        subject=f'[URGENTE] Contrato vence {dias_txt} â€” {contrato.nombre_completo}',
        message=(
            f'Hola {director.nombres},\n\n'
            f'ALERTA URGENTE: El contrato de {contrato.nombre_completo} '
            f'({contrato.tipo_documento} {contrato.documento_id}), cargo {contrato.cargo}, '
            f'vence el {_fmt_fecha(contrato.fecha_finalizacion)} ({dias_txt}).\n\n'
            f'Estado: {contrato.estado.replace("_", " ")}\n\n'
            f'Panel: {panel}\n\nInversiones Euro S.A. â€” GestiÃ³n Humana'
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


def enviar_alerta_urgente_gh(gh, contrato, dias_restantes):
    """Alerta urgente a GH cuando un contrato vence en ≤2 días y requiere decisión inmediata."""
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
        _p(f'Hola, <strong style="color:#ffffff;">{gh.nombres}</strong>', size=15, bottom=8)
        + f'<p style="color:#ef4444;font-size:15px;font-weight:700;margin:0 0 12px;'
          f'font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',Arial,sans-serif;">'
          f'⚠ ACCIÓN URGENTE REQUERIDA</p>'
        + _p(f'El siguiente contrato vence '
             f'<strong style="color:{color_dias};">{dias_txt}</strong> '
             f'y aún no ha sido resuelto. Se requiere tu decisión inmediata.', bottom=4)
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
            f'Hola {gh.nombres},\n\n'
            f'ALERTA URGENTE: El contrato de {contrato.nombre_completo} '
            f'({contrato.tipo_documento} {contrato.documento_id}), cargo {contrato.cargo}, '
            f'vence el {_fmt_fecha(contrato.fecha_finalizacion)} ({dias_txt}).\n\n'
            f'Estado: {contrato.estado.replace("_", " ")}\n\n'
            f'Panel: {panel}\n\nInversiones Euro S.A. — Gestión Humana'
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[gh.correo],
        html_message=_html_email(cuerpo),
        fail_silently=False,
    )
    logger.info(
        f'[CORREO] Alerta urgente GH → {gh.correo} '
        f'contrato {contrato.documento_id} vence {contrato.fecha_finalizacion}'
    )
