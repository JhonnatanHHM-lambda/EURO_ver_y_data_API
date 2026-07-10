"""
Diagnóstico de endpoints SAIA: captura todo el tráfico HTTP durante una carga real.

Instala listeners de red en Playwright ANTES del login y los mantiene activos
hasta el final, registrando cada request y response. El reporte completo se guarda
en diagnostico_endpoint_saia.txt.

Uso:
  python manage.py diagnosticar_endpoint_saia --headful
  python manage.py diagnosticar_endpoint_saia --headful --asunto "PEL 97574 TOMO 1-2" --archivo "C:\\ruta\\doc.pdf"
  python manage.py diagnosticar_endpoint_saia --headful --ruta PEL

NOTA: este script realiza UNA carga real en SAIA. El documento NO se marca como
      CARGADO_SAIA en la base de datos local; si la carga es exitosa, la próxima
      ejecución del batch lo detectará via reconcile y lo marcará correctamente.
"""

import os
import re
from datetime import datetime
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from migracion_masiva_archivo.services.saia.browser_client import SAIABrowserClient
from migracion_masiva_archivo.services.saia.config import get_saia_config
from migracion_masiva_archivo.services.saia.exceptions import SAIACredentialsError, SAIAError

REPORT_PATH = Path('C:/Users/EQUIPO/Euro_gestion_documental_API/diagnostico_endpoint_saia.txt')

SKIP_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.gif', '.css', '.js', '.ico', '.woff', '.woff2', '.ttf', '.svg')
SUCCESS_SIGNALS = ['exitosamente', 'documento creado', 'documento adicionado', 'insertado', 'vinculado']
ERROR_SIGNALS   = ['rechaz', 'no se pudo', 'campo obligatorio', 'error']


# ---------------------------------------------------------------------------
# Monitor de red
# ---------------------------------------------------------------------------

class NetworkMonitor:
    def __init__(self):
        self.events = []
        self._active = False

    def start(self, page):
        self._active = True
        page.on('request',  self._on_request)
        page.on('response', self._on_response)

    def mark(self, label):
        self.events.append({'type': 'MARKER', 'ts': datetime.now().isoformat(), 'label': label})

    def _skip(self, url):
        return any(url.lower().endswith(ext) for ext in SKIP_EXTENSIONS)

    def _on_request(self, request):
        if not self._active or self._skip(request.url):
            return
        entry = {
            'type':          'REQUEST',
            'ts':            datetime.now().isoformat(),
            'method':        request.method,
            'url':           request.url,
            'resource_type': request.resource_type,
            'post_data':     None,
            'headers':       {},
        }
        try:
            entry['post_data'] = request.post_data or None
        except Exception:
            entry['post_data'] = '[multipart/binario — no legible como texto]'
        try:
            h = dict(request.headers)
            entry['headers'] = {
                k: v for k, v in h.items()
                if k.lower() in ('content-type', 'x-csrf-token', 'authorization',
                                  'x-requested-with', 'referer', 'origin')
            }
        except Exception:
            pass
        self.events.append(entry)

    def _on_response(self, response):
        if not self._active or self._skip(response.url):
            return
        entry = {
            'type':    'RESPONSE',
            'ts':      datetime.now().isoformat(),
            'status':  response.status,
            'url':     response.url,
            'headers': {},
            'body':    None,
            'signals': [],
        }
        try:
            ct = response.headers.get('content-type', '')
            entry['headers'] = {'content-type': ct}
            if any(t in ct for t in ('text', 'html', 'json', 'xml')):
                body = response.text()
                entry['body'] = body[:3000]
                bl = body.lower()
                entry['signals'] += [f'[OK] "{s}"' for s in SUCCESS_SIGNALS if s in bl]
                entry['signals'] += [f'[ERR] "{s}"' for s in ERROR_SIGNALS  if s in bl]
                m = re.search(r'documento\s*n[ro]\.?\s*(\d+)', bl)
                if m:
                    entry['signals'].append(f'[DOC_NO] {m.group(1)}')
        except Exception as exc:
            entry['body'] = f'[No se pudo leer body: {exc}]'
        self.events.append(entry)

    def events_after_marker(self, marker_label):
        idx = next((i for i, e in enumerate(self.events)
                    if e['type'] == 'MARKER' and e.get('label') == marker_label), None)
        if idx is None:
            return []
        return self.events[idx + 1:]


# ---------------------------------------------------------------------------
# Comando Django
# ---------------------------------------------------------------------------

class Command(BaseCommand):
    help = 'Captura tráfico HTTP de SAIA durante carga de documento para identificar endpoints.'

    def add_arguments(self, parser):
        parser.add_argument('--headful', action='store_true',
                            help='Muestra el navegador.')
        parser.add_argument('--asunto', type=str, default='',
                            help='Asunto SAIA del documento (ej: "PEL 97574 TOMO 1-2").')
        parser.add_argument('--archivo', type=str, default='',
                            help='Ruta del PDF a adjuntar.')
        parser.add_argument('--ruta', type=str, default='PEL',
                            help='Código de ruta SAIA (default: PEL).')

    def handle(self, *args, **options):
        os.environ.setdefault('DJANGO_ALLOW_ASYNC_UNSAFE', 'true')

        config = get_saia_config()
        try:
            config.validate_credentials()
        except SAIACredentialsError as exc:
            raise CommandError(str(exc)) from exc

        asunto_saia, file_path = self._resolver_documento(options)
        route_code = (options.get('ruta') or 'PEL').upper()

        self.stdout.write(f'Usuario   : {config.username}')
        self.stdout.write(f'URL SAIA  : {config.base_url}')
        self.stdout.write(f'Asunto    : {asunto_saia}')
        self.stdout.write(f'Archivo   : {file_path}')
        self.stdout.write(f'Ruta      : {route_code}')
        self.stdout.write('')

        monitor  = NetworkMonitor()
        lines    = []
        result   = {}
        error_msg = None

        def w(text=''):
            lines.append(text)

        w('=' * 80)
        w('DIAGNOSTICO ENDPOINT SAIA — CARGA DE DOCUMENTO')
        w(f'Generado : {datetime.now().isoformat()}')
        w(f'Asunto   : {asunto_saia}')
        w(f'Archivo  : {file_path}')
        w(f'Ruta     : {route_code}')
        w('=' * 80)
        w()

        try:
            with SAIABrowserClient(config, headful=options['headful']) as client:

                # Activar monitor ANTES de cualquier navegación
                monitor.start(client.page)
                w('[NET] Monitor de red activo desde este momento.')
                w()

                # Paso 1: Login
                self.stdout.write('[1/4] Login...')
                monitor.mark('login_start')
                client.login()
                monitor.mark('login_ok')
                self.stdout.write(self.style.SUCCESS('  OK'))
                w(f'[1] Login OK  — URL: {client.current_url()}')
                w()

                # Paso 2: Navegar a ruta
                self.stdout.write(f'[2/4] Navegando a {route_code}...')
                monitor.mark('nav_start')
                client.navigate_to_route(route_code)
                monitor.mark('nav_ok')
                self.stdout.write(self.style.SUCCESS('  OK'))
                w(f'[2] Navegación {route_code} OK  — URL: {client.current_url()}')
                w()

                # Paso 3: Llenar formulario (dependencia + asunto + adjunto)
                self.stdout.write('[3/4] Llenando formulario + adjuntando archivo...')
                monitor.mark('form_fill_start')
                client.fill_document_form(
                    asunto_saia=asunto_saia,
                    file_path=file_path,
                    attach_file=bool(file_path),
                    extended_timeout=False,
                )
                monitor.mark('form_fill_ok')
                self.stdout.write(self.style.SUCCESS('  OK'))
                w(f'[3] Formulario llenado  — URL: {client.current_url()}')
                w()

                # Paso 4: CLIC EN CONTINUAR  ← punto crítico
                self.stdout.write('[4/4] Clic en Continuar (capturando red)...')
                url_before = client.current_url()
                monitor.mark('continuar_click')
                result = client.continue_and_confirm(
                    expected_subject=asunto_saia,
                    extended_timeout=False,
                )
                monitor.mark('continuar_done')
                self.stdout.write(self.style.SUCCESS('  OK'))
                w(f'[4] continue_and_confirm completado')
                w(f'    URL antes  : {url_before}')
                w(f'    URL después: {client.current_url()}')
                w(f'    success_detected   : {result.get("success_detected")}')
                w(f'    ambiguous          : {result.get("ambiguous")}')
                w(f'    error_detected     : {result.get("error_detected")}')
                w(f'    confirmation_source: {result.get("confirmation_source")}')
                w(f'    id_documento_saia  : {result.get("id_documento_saia")}')
                w()

        except SAIAError as exc:
            error_msg = str(exc)
            self.stdout.write(self.style.ERROR(f'Error SAIA: {exc}'))
            w(f'[ERROR SAIA] {exc}')
            w()
        except Exception as exc:
            error_msg = str(exc)
            self.stdout.write(self.style.ERROR(f'Error inesperado: {exc}'))
            w(f'[ERROR INESPERADO] {exc}')
            w()

        # ---------------------------------------------------------------
        # Volcado completo de tráfico de red
        # ---------------------------------------------------------------
        w('=' * 80)
        w('TRAFICO COMPLETO DE RED')
        w('=' * 80)
        w()

        in_critical = False
        for event in monitor.events:
            if event['type'] == 'MARKER':
                if event['label'] == 'continuar_click':
                    in_critical = True
                    w()
                    w('▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼')
                    w('  >>> CLIC EN CONTINUAR — INICIO ZONA CRITICA <<<')
                    w('▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼')
                    w()
                elif event['label'] == 'continuar_done':
                    in_critical = False
                    w()
                    w('▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲')
                    w('  >>> FIN ZONA CRITICA <<<')
                    w('▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲')
                    w()
                else:
                    marker_str = '*** ' if in_critical else '    '
                    w(f'{marker_str}[MARCADOR] {event["label"]}  ({event["ts"]})')
                continue

            pfx = '*** ' if in_critical else '    '

            if event['type'] == 'REQUEST':
                w(f'{pfx}REQUEST  [{event["ts"]}]')
                w(f'{pfx}  {event["method"]:6} {event["url"]}')
                w(f'{pfx}  Tipo    : {event.get("resource_type")}')
                for k, v in (event.get('headers') or {}).items():
                    w(f'{pfx}  {k}: {v[:200]}')
                if event.get('post_data'):
                    pd = str(event['post_data'])[:600]
                    w(f'{pfx}  POST body (600c): {pd}')
                w()

            elif event['type'] == 'RESPONSE':
                signals_str = '  |  '.join(event.get('signals') or [])
                w(f'{pfx}RESPONSE [{event["ts"]}]')
                w(f'{pfx}  Status : {event["status"]}  {event["url"]}')
                for k, v in (event.get('headers') or {}).items():
                    w(f'{pfx}  {k}: {v[:200]}')
                if signals_str:
                    w(f'{pfx}  *** SENALES: {signals_str} ***')
                if event.get('body'):
                    w(f'{pfx}  Body (3000c):')
                    for line in event['body'].splitlines()[:50]:
                        w(f'{pfx}    {line}')
                w()

        # ---------------------------------------------------------------
        # Análisis automático
        # ---------------------------------------------------------------
        after_click = monitor.events_after_marker('continuar_click')

        post_requests = [
            e for e in after_click
            if e['type'] == 'REQUEST' and e.get('method') == 'POST'
        ]
        responses_with_signals = [
            e for e in after_click
            if e['type'] == 'RESPONSE' and e.get('signals')
        ]

        w('=' * 80)
        w('ANALISIS AUTOMATICO')
        w('=' * 80)
        w()
        w(f'Total eventos de red capturados : {len(monitor.events)}')
        w(f'Eventos en zona critica (post-click): {len(after_click)}')
        w()

        w(f'POST requests después del clic en Continuar: {len(post_requests)}')
        for req in post_requests:
            w(f'  {req["method"]} {req["url"]}')
            if req.get('post_data'):
                w(f'    Body: {str(req["post_data"])[:400]}')
            for k, v in (req.get('headers') or {}).items():
                w(f'    {k}: {v[:150]}')
        w()

        w(f'Responses con señales de éxito/error en zona critica: {len(responses_with_signals)}')
        for resp in responses_with_signals:
            w(f'  Status {resp["status"]}  {resp["url"]}')
            w(f'  Señales: {" | ".join(resp.get("signals", []))}')
            if resp.get('body'):
                w(f'  Body preview: {resp["body"][:500]}')
        w()

        if error_msg:
            w(f'ERROR FINAL: {error_msg}')
        else:
            w(f'Resultado final: success_detected={result.get("success_detected")} | '
              f'ambiguous={result.get("ambiguous")}')

        # Guardar reporte
        report_text = '\n'.join(lines)
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(report_text, encoding='utf-8')

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(f'Reporte guardado: {REPORT_PATH}'))

    def _resolver_documento(self, options):
        asunto = (options.get('asunto') or '').strip()
        archivo = (options.get('archivo') or '').strip()

        if asunto and archivo:
            p = Path(archivo)
            if not p.exists():
                raise CommandError(f'Archivo no encontrado: {archivo}')
            return asunto, p

        try:
            from migracion_masiva_archivo.models import DocumentoDigitalizado
            from migracion_masiva_archivo.services.saia.validation_service import validate_document_for_saia

            qs = (
                DocumentoDigitalizado.objects
                .filter(
                    estado_proceso__in=['VALIDADO', 'REQUIERE_REVISION'],
                    ruta_archivo__isnull=False,
                )
                .order_by('-modificado')
            )
            for doc in qs[:10]:
                validation = validate_document_for_saia(doc, include_errored=True)
                asunto_saia = validation.get('asunto_saia') or doc.nombre_archivo
                ruta = Path(doc.ruta_archivo)
                if ruta.exists():
                    return asunto_saia, ruta
                self.stdout.write(self.style.WARNING(
                    f'Archivo no existe en disco: {ruta}. Probando siguiente...'
                ))
        except Exception as exc:
            self.stdout.write(self.style.WARNING(f'No se pudo consultar DB: {exc}'))

        raise CommandError(
            'No se encontró documento de prueba en la DB con archivo en disco.\n'
            'Use: --asunto "PEL 97574 TOMO 1-2" --archivo "C:\\ruta\\doc.pdf"'
        )


