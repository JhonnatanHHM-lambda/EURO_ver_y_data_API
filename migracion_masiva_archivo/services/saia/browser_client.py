import re
import unicodedata
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

from migracion_masiva_archivo.services.saia import selectors
from migracion_masiva_archivo.services.saia.exceptions import SAIALoginError, SAIASelectorError, SAIATimeoutError
from migracion_masiva_archivo.services.saia.routes import get_saia_route_steps


SAIA_POST_CONTINUE_MIN_WAIT_MS = 30000
SAIA_POST_CONTINUE_TIMEOUT_MS = 90000
SAIA_POST_CONTINUE_EXTENDED_TIMEOUT_MS = 300000
SAIA_RECONCILE_TIMEOUT_MS = 60000


class SAIABrowserClient:
    def __init__(self, config, headful=False):
        self.config = config
        self.headful = headful
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.last_screenshot = ''
        self._saia_timing_events = []
        self._last_route_key = None   # (route_code, year, subexpediente) tras upload exitoso
        self._last_year_clicked = None  # año seleccionado en el frame de contenido (para Acciones de fila)

    def __enter__(self):
        try:
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise SAIATimeoutError(
                'Playwright no esta instalado. Instala dependencias y ejecuta: playwright install chromium'
            ) from exc

        self._timeout_error = PlaywrightTimeoutError
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=not self.headful)
        self.context = self.browser.new_context(accept_downloads=True)
        self.page = self.context.new_page()
        self.page.set_default_timeout(self.config.timeout_ms)
        # Auto-aceptar dialogos JavaScript (alert/confirm) de SAIA.
        # Si SAIA muestra un alert() sin este handler, Playwright queda bloqueado:
        # inner_text() falla, networkidle nunca se alcanza, y read_result lee vacio.
        self.page.on('dialog', lambda dialog: dialog.accept())
        return self

    def __exit__(self, exc_type, exc, traceback):
        if self.context:
            self.context.close()
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()

    def current_url(self):
        return self.page.url if self.page else ''

    def open_login(self):
        self.page.goto(self.config.base_url, wait_until='domcontentloaded')

    def login(self):
        self.open_login()
        user_field = self._first_visible(selectors.LOGIN_USER_SELECTORS, 'campo usuario')
        password_field = self._first_visible(selectors.LOGIN_PASSWORD_SELECTORS, 'campo contraseña')
        user_field.fill(self.config.username)
        password_field.fill(self.config.password)

        login_data = None
        try:
            with self.page.expect_response(
                lambda response: 'verificar_login.php' in response.url,
                timeout=self.config.timeout_ms,
            ) as response_info:
                submitted = self._click_first_optional(selectors.LOGIN_SUBMIT_SELECTORS)
                if not submitted:
                    password_field.press('Enter')
            login_data = response_info.value.json()
        except self._timeout_error:
            pass

        if login_data:
            if int(login_data.get('ingresar') or 0) != 1:
                self.capture_screenshot('login_error_saia')
                raise SAIALoginError(login_data.get('mensaje') or 'SAIA rechazo el login.')

            route = login_data.get('ruta') or ''
            if route:
                self.page.goto(urljoin(self.config.base_url, route), wait_until='domcontentloaded')
                try:
                    self.page.wait_for_load_state('networkidle', timeout=self.config.timeout_ms)
                except self._timeout_error:
                    pass
                return

        try:
            self.page.wait_for_load_state('networkidle', timeout=self.config.timeout_ms)
        except self._timeout_error:
            pass

        self.page.wait_for_timeout(4500)

        login_status = self._login_status()
        if login_status == 'success':
            if self._looks_like_login_page():
                self.capture_screenshot('login_sin_redireccion')
                raise SAIALoginError('SAIA autentico, pero no entrego una ruta de ingreso.')
            return
        if login_status == 'error':
            self.capture_screenshot('login_error_saia')
            raise SAIALoginError('SAIA rechazo el login. Verifica usuario, clave o permisos.')

        if self._looks_like_login_page():
            self.capture_screenshot('login_fallido')
            raise SAIALoginError('SAIA sigue mostrando la pantalla de login. Verifica credenciales.')

    def navigate_to_pel_2019(self):
        self.navigate_to_route('PEL')

    def navigate_to_route(self, route_code, year=None, subexpediente=None):
        # Volver a home garantiza estado limpio independientemente de en qué
        # página SAIA dejó el upload anterior (confirmación, error, etc.)
        self.page.goto(self.config.base_url, wait_until='domcontentloaded')
        try:
            self.page.wait_for_load_state('networkidle', timeout=5000)
        except self._timeout_error:
            pass
        steps = get_saia_route_steps(route_code, year=year, subexpediente=subexpediente)
        if not steps:
            raise SAIASelectorError(f'Ruta SAIA no configurada: {route_code}')
        try:
            self._run_navigation_steps(steps)
        except SAIASelectorError as exc:
            self.capture_screenshot(f'ruta_saia_{self._slug(route_code)}_no_encontrada')
            raise SAIASelectorError(f'Ruta SAIA {route_code} no encontrada: {exc}') from exc

    def _try_quick_click(self, label, attempts=4):
        """Intenta click en label con espera corta. Retorna True si logra, False si no."""
        for _ in range(attempts):
            for frame in self.page.frames:
                for locator in [
                    frame.get_by_role('link', name=label, exact=False),
                    frame.get_by_role('button', name=label, exact=False),
                    frame.get_by_text(label, exact=False),
                ]:
                    try:
                        if locator.count() and locator.first.is_visible():
                            locator.first.click()
                            try:
                                self.page.wait_for_load_state('networkidle', timeout=5000)
                            except self._timeout_error:
                                pass
                            self.page.wait_for_timeout(2000)
                            return True
                    except Exception:
                        continue
            self.page.wait_for_timeout(1000)
        return False

    def try_adicionar_sin_ruta(self, route_code, year, subexpediente):
        """Reusa posicion SAIA post-upload: click Acciones→Adicionar documento.
        Retorna True si llega al formulario, False si debe hacer navegacion completa.
        Nunca lanza excepciones — cualquier fallo retorna False."""
        if self._last_route_key != (route_code, year, subexpediente):
            return False
        try:
            if not self._try_quick_click('Acciones'):
                return False
            if not self._try_quick_click('Adicionar documento'):
                return False
            return True
        except Exception:
            return False

    def mark_route_navigated(self, route_code, year, subexpediente):
        """Registra que el ultimo upload exitoso fue en esta ruta/sub-expediente."""
        self._last_route_key = (route_code, year, subexpediente)

    def clear_route_state(self):
        """Limpia el estado de ruta guardado (estado SAIA desconocido tras error)."""
        self._last_route_key = None
        self._last_year_clicked = None

    def navigate_to_pro(self):
        self.navigate_to_route('PRO')

    def navigate_to_conciliaciones_bancarias(self):
        self._run_navigation_steps(selectors.SAIA_NAVIGATION_STEPS_CONCILIACIONES)

    def preflight_navigation(self):
        # Verifica que la ruta SAIA esté accesible navegando hasta "Pagos"
        # (Archivo → Mis expedientes → Archivo Central → Pagos) sin abrir
        # formularios ni tocar documentos. Vuelve al inicio tras el chequeo.
        #
        # Navegar a home primero garantiza estado limpio: el login puede redirigir
        # a un expediente previo (ej. PAGOS) donde "Archivo Central" no aparece
        # como nodo en el árbol, igual que hace navigate_to_route().
        self.page.goto(self.config.base_url, wait_until='domcontentloaded')
        try:
            self.page.wait_for_load_state('networkidle', timeout=5000)
        except self._timeout_error:
            pass
        try:
            self._run_navigation_steps(selectors.SAIA_NAVIGATION_STEPS[:4])
        except SAIASelectorError as exc:
            self.capture_screenshot('preflight_fallido')
            raise SAIASelectorError(
                f'Pre-flight SAIA: ruta de navegacion no accesible — {exc}'
            ) from exc
        self.page.goto(self.config.base_url, wait_until='domcontentloaded')
        try:
            self.page.wait_for_load_state('networkidle', timeout=5000)
        except self._timeout_error:
            pass

    def _run_navigation_steps(self, steps):
        for index, step in enumerate(steps):
            try:
                if step.get('missing_dynamic_year'):
                    raise SAIASelectorError('La ruta SAIA requiere un anio y no se pudo resolver desde el documento.')
                if step.get('missing_dynamic_subexpediente'):
                    raise SAIASelectorError('La ruta SAIA requiere un subexpediente y no se pudo resolver desde el documento.')
                if step.get('missing_dynamic_month'):
                    raise SAIASelectorError('La ruta SAIA requiere un mes y no se pudo resolver desde el documento.')
                if step.get('title_contains'):
                    self.click_by_title(step['title_contains'])
                elif step.get('navigate_into') and step.get('labels'):
                    if self._is_inside_subexpediente(step['labels'][0]):
                        continue
                    # Para seleccionar un sub-expediente cuyo mismo texto aparece en el árbol:
                    # busca el frame de contenido (identificado por "Tomo:") y hace click ahí.
                    self.click_text_near_tomo(step['labels'][0])
                    self._assert_navigated_into_subexpediente(step['labels'][0])
                elif step.get('in_tomo_frame') and step.get('labels'):
                    # Para clickear un elemento (ej. "Acciones") en el frame de contenido,
                    # evitando el botón global del toolbar que opera sobre el expediente padre.
                    self.click_any_text_in_tomo_frame(step['labels'])
                else:
                    self.click_any_text(step['labels'])

                next_step = steps[index + 1] if index + 1 < len(steps) else {}
                if next_step.get('navigate_into') and next_step.get('labels'):
                    self._wait_for_subexpediente_row(next_step['labels'][0])
            except SAIASelectorError:
                if step.get('optional'):
                    continue
                raise

    def fill_document_form(self, asunto_saia, file_path=None, attach_file=False, extended_timeout=False):
        self._wait_for_document_form()
        self._select_dependency()
        self._fill_subject(asunto_saia)
        if attach_file and file_path:
            self._attach_file(file_path, extended_timeout=extended_timeout)

    def dry_run_checkpoint(self):
        return self.capture_screenshot('dry_run_antes_confirmar')

    def continue_and_confirm(self, expected_subject=None, extended_timeout=False):
        self._saia_timing_events = []
        continue_started_at = datetime.now()
        url_before = self.current_url()
        self._click_first_required(selectors.CONTINUE_SELECTORS, 'boton Continuar')
        self._record_timing('saia_timing_continue_click', continue_started_at, asunto=expected_subject or '')
        self.page.wait_for_timeout(2000)
        self._wait_for_submission_result(
            expected_subject=expected_subject,
            extended_timeout=extended_timeout,
            url_before=url_before,
            started_at=continue_started_at,
        )
        # Dejar que la red se estabilice: evita leer la pagina mientras SAIA
        # aun actualiza el iframe de contenido tras mostrar la confirmacion.
        try:
            self.page.wait_for_load_state('networkidle', timeout=8000)
        except self._timeout_error:
            pass
        self.page.wait_for_timeout(1000)
        result = self.read_result(expected_subject=expected_subject, url_before=url_before)
        # Si el resultado es ambiguo, la vista del expediente puede estar cargando
        # los chips de documento via AJAX (despues de networkidle). Esperar y reintentar.
        if result.get('ambiguous'):
            self.page.wait_for_timeout(5000)
            result = self.read_result(expected_subject=expected_subject, url_before=url_before)
        if result.get('ambiguous'):
            reconcile = self.reconcile_uploaded_document(
                expected_subject=expected_subject,
                timeout_ms=SAIA_RECONCILE_TIMEOUT_MS,
            )
            if reconcile.get('found'):
                result.update({
                    'success_detected': True,
                    'error_detected': False,
                    'ambiguous': False,
                    'document_list_confirmed': True,
                    'confirmation_source': reconcile.get('confirmation_source', 'reconciled_document_list'),
                    'id_documento_saia': reconcile.get('id_documento_saia', ''),
                    'fecha_carga_saia_text': reconcile.get('fecha_carga_saia_text', ''),
                    'matched_subject': reconcile.get('matched_subject', ''),
                    'matched_anexo': reconcile.get('matched_anexo', ''),
                    'reconciled_after_ambiguous': True,
                    'reconcile_evidence': reconcile.get('evidence', ''),
                    'screenshot': reconcile.get('screenshot') or result.get('screenshot', ''),
                })
        if result.get('success_detected'):
            self._record_timing(
                'saia_timing_success_confirmed',
                continue_started_at,
                confirmation_source=result.get('confirmation_source', ''),
            )
        result['timing_events'] = list(getattr(self, '_saia_timing_events', []))
        return result

    def read_result(self, expected_subject=None, url_before=None):
        raw_content = self._all_frames_text()
        content = raw_content.lower()
        current_url = self.current_url()
        list_record = self._find_saia_document_list_record(raw_content, expected_subject)
        subject_confirmed = self._subject_in_text(expected_subject, content)
        left_panel_confirmed = self._subject_in_left_panel(expected_subject)
        left_panel_v1_confirmed = self._left_panel_version_visible(expected_subject, raw_content)
        anexo_confirmed = self._anexo_visible(expected_subject, raw_content)
        # "Asunto: PEL 97335" aparece en la tabla de confirmacion de SAIA tras
        # carga exitosa. El formulario de carga usa "Nombre o asunto:" como label,
        # nunca "Asunto:" seguido del valor, por lo que es senal inequivoca de exito.
        asunto_field_confirmed = self._asunto_field_visible(expected_subject, raw_content)
        document_detail_confirmed = (
            self._looks_like_document_detail(content, current_url)
            and (
                subject_confirmed
                or left_panel_confirmed
                or left_panel_v1_confirmed
                or asunto_field_confirmed
                or anexo_confirmed
            )
        )
        document_list_confirmed = bool(list_record) or self._looks_like_document_list_confirmation(
            raw_content,
            expected_subject,
        )

        url_changed = (
            bool(url_before)
            and current_url != url_before
            and current_url != self.config.base_url
            and not self._looks_like_login_page()
        )

        has_strong_success = any(t in content for t in selectors.SUCCESS_TEXTS_STRONG)
        has_strong_error   = any(t in content for t in selectors.ERROR_TEXTS_STRONG)
        has_any_success    = has_strong_success or any(t in content for t in selectors.SUCCESS_TEXTS)
        has_any_error      = has_strong_error or any(t in content for t in selectors.ERROR_TEXTS)

        success = (
            (has_strong_success and not has_strong_error)
            or (asunto_field_confirmed and not has_strong_error)
            or (document_detail_confirmed and not has_strong_error)
            or (document_list_confirmed and not has_strong_error)
            or (left_panel_v1_confirmed and not has_strong_error)
            or (left_panel_confirmed and not has_strong_error)
            or (subject_confirmed and has_any_success and not has_strong_error)
            or (url_changed and has_any_success and not has_strong_error)
        )
        # Si el boton "Enviando..." sigue activo, el POST HTTP aun esta en vuelo.
        # Las señales de error son del formulario mismo (validaciones de campos
        # vaciados mid-POST), no del rechazo de SAIA. Tratar como ambiguous para
        # que reconcile pueda verificar el resultado real en la pagina de SAIA.
        submission_in_progress = (
            not document_detail_confirmed
            and not document_list_confirmed
            and not asunto_field_confirmed
            and 'enviando' in self._all_frames_text_compat(include_controls=True).lower()
        )
        error = (
            not submission_in_progress
            and not document_detail_confirmed
            and not document_list_confirmed
            and not asunto_field_confirmed
        ) and (
            has_strong_error or (
                has_any_error and not has_any_success and not subject_confirmed
            )
        )
        ambiguous = not success and not error
        confirmation_source = self._build_confirmation_source(
            document_detail_confirmed=document_detail_confirmed,
            document_list_confirmed=document_list_confirmed,
            left_panel_v1_confirmed=left_panel_v1_confirmed,
            left_panel_confirmed=left_panel_confirmed,
            asunto_field_confirmed=asunto_field_confirmed,
            anexo_confirmed=anexo_confirmed,
            subject_confirmed=subject_confirmed,
            success=success,
        )

        screenshot = self.capture_screenshot('resultado_saia')
        return {
            'success_detected': success,
            'error_detected': error,
            'ambiguous': ambiguous,
            'url_changed': url_changed,
            'subject_confirmed': subject_confirmed,
            'left_panel_confirmed': left_panel_confirmed,
            'left_panel_v1_confirmed': left_panel_v1_confirmed,
            'asunto_field_confirmed': asunto_field_confirmed,
            'anexo_confirmed': anexo_confirmed,
            'document_detail_confirmed': document_detail_confirmed,
            'document_list_confirmed': document_list_confirmed,
            'confirmation_source': confirmation_source,
            'matched_subject': list_record.get('matched_subject', '') if list_record else '',
            'matched_anexo': f'{expected_subject}.pdf' if anexo_confirmed and expected_subject else '',
            'expected_subject': expected_subject or '',
            'url': current_url,
            'screenshot': screenshot,
            'id_documento_saia': (
                list_record.get('id_documento_saia', '') if list_record
                else self._extract_document_id(content, current_url)
            ),
            'fecha_carga_saia_text': (
                list_record.get('fecha_carga_saia_text', '') if list_record
                else self._extract_saia_timestamp_text(raw_content)
            ),
        }

    def reconcile_uploaded_document(self, expected_subject, route_code=None, timeout_ms=SAIA_RECONCILE_TIMEOUT_MS):
        started_at = datetime.now()
        while True:
            self._scroll_saia_lists_to_top()
            raw_content = self._all_frames_text()
            content = raw_content.lower()
            current_url = self.current_url()

            record = self._find_saia_document_list_record(raw_content, expected_subject)
            if record:
                screenshot = self.capture_screenshot('saia_reconciliacion_ok')
                return {
                    'found': True,
                    'confirmation_source': 'reconciled_document_list',
                    'id_documento_saia': record.get('id_documento_saia', ''),
                    'fecha_carga_saia_text': record.get('fecha_carga_saia_text', ''),
                    'matched_subject': record.get('matched_subject', ''),
                    'matched_anexo': '',
                    'evidence': record.get('evidence', ''),
                    'screenshot': screenshot,
                }

            left_panel_v1_confirmed = self._left_panel_version_visible(expected_subject, raw_content)
            anexo_confirmed = self._anexo_visible(expected_subject, raw_content)
            if (
                self._looks_like_document_detail(content, current_url)
                and (
                    self._subject_in_text(expected_subject, raw_content)
                    or self._subject_in_left_panel(expected_subject)
                    or left_panel_v1_confirmed
                    or self._asunto_field_visible(expected_subject, raw_content)
                    or anexo_confirmed
                )
            ):
                screenshot = self.capture_screenshot('saia_reconciliacion_detalle_ok')
                return {
                    'found': True,
                    'confirmation_source': self._build_confirmation_source(
                        document_detail_confirmed=True,
                        document_list_confirmed=False,
                        left_panel_v1_confirmed=left_panel_v1_confirmed,
                        left_panel_confirmed=self._subject_in_left_panel(expected_subject),
                        asunto_field_confirmed=self._asunto_field_visible(expected_subject, raw_content),
                        anexo_confirmed=anexo_confirmed,
                        subject_confirmed=self._subject_in_text(expected_subject, raw_content),
                        success=True,
                    ) or 'reconciled_document_detail',
                    'id_documento_saia': self._extract_document_id(content, current_url),
                    'fecha_carga_saia_text': self._extract_saia_timestamp_text(raw_content),
                    'matched_subject': expected_subject or '',
                    'matched_anexo': f'{expected_subject}.pdf' if anexo_confirmed and expected_subject else '',
                    'evidence': self._trim_evidence(raw_content),
                    'screenshot': screenshot,
                }

            elapsed_ms = (datetime.now() - started_at).total_seconds() * 1000
            if elapsed_ms >= timeout_ms:
                break
            if 'enviando' in content or 'cargando' in content:
                self.page.wait_for_timeout(1000)
            else:
                self.page.wait_for_timeout(2000)

        return {
            'found': False,
            'id_documento_saia': '',
            'fecha_carga_saia_text': '',
            'matched_subject': '',
            'evidence': self._trim_evidence(self._all_frames_text()),
            'screenshot': self.capture_screenshot('saia_reconciliacion_no_encontrada'),
        }

    def click_text(self, label):
        total_attempts = 10
        for attempt in range(total_attempts):
            for frame in self.page.frames:
                candidates = [
                    frame.get_by_role('link', name=label, exact=False),
                    frame.get_by_role('button', name=label, exact=False),
                    frame.get_by_text(label, exact=False),
                ]
                for locator in candidates:
                    try:
                        if locator.count():
                            # El elemento puede existir en el árbol pero estar fuera del viewport
                            try:
                                locator.first.scroll_into_view_if_needed(timeout=5000)
                            except Exception:
                                pass
                            if locator.first.is_visible():
                                locator.first.click()
                                try:
                                    self.page.wait_for_load_state('networkidle', timeout=8000)
                                except self._timeout_error:
                                    pass
                                self.page.wait_for_timeout(2500)
                                return
                    except self._timeout_error:
                        continue

            self._scroll_saia_content(attempt)
            self.page.wait_for_timeout(1500)

        self.capture_screenshot(f'selector_no_encontrado_{self._slug(label)}')
        raise SAIASelectorError(f'No se encontro selector visible para: {label}')

    def _scroll_saia_content(self, attempt=0):
        # SAIA carga algunos agrupadores con demora y otros quedan fuera del
        # viewport. El scroll se aplica a ventana, contenedores scrollables
        # del frame principal Y a todos los frames hijos (árbol de navegación).
        direction = 1 if attempt < 7 else -1
        distance = 520 * direction
        _scroll_js = """(distance) => {
            const scrollables = Array.from(document.querySelectorAll('*'))
              .filter((el) => {
                const style = window.getComputedStyle(el);
                return /(auto|scroll)/.test(style.overflowY)
                  && el.scrollHeight > el.clientHeight + 20;
              });
            for (const el of scrollables) {
              el.scrollTop += distance;
            }
            window.scrollBy(0, distance);
        }"""
        try:
            self.page.mouse.wheel(0, distance)
        except Exception:
            pass
        try:
            self.page.evaluate(_scroll_js, distance)
        except Exception:
            pass
        for frame in self.page.frames:
            if frame == self.page.main_frame:
                continue
            try:
                frame.evaluate(_scroll_js, distance)
            except Exception:
                pass

    def _wait_for_subexpediente_row(self, label):
        label_text = str(label)
        label_upper = label_text.upper()
        row_re = re.compile(rf'\b{re.escape(label_text)}\b', re.IGNORECASE)

        for _ in range(30):
            if self._is_inside_subexpediente(label_text):
                return
            for frame in self.page.frames:
                try:
                    body = frame.locator('body')
                    if not body.count():
                        continue
                    try:
                        body_text = body.inner_text(timeout=1500)
                    except Exception:
                        continue
                    if label_upper not in body_text.upper():
                        continue
                    if 'Tomo' not in body_text and 'tomo' not in body_text:
                        continue

                    if self._subexpediente_row_visible(frame, label_text, row_re):
                        return
                except Exception:
                    continue
            self.page.wait_for_timeout(2000)

        self.capture_screenshot(f'subexpediente_{self._slug(label_text)}_no_cargado')
        raise SAIASelectorError(
            f'No cargo la fila del subexpediente "{label_text}" para poder ingresar antes de abrir Acciones.'
        )

    @staticmethod
    def _subexpediente_row_visible(frame, label, row_re=None):
        label_text = str(label).strip()
        try:
            found = frame.evaluate(r"""(lbl) => {
                const norm = (value) => (value || '')
                  .normalize('NFD')
                  .replace(/[\u0300-\u036f]/g, '')
                  .replace(/\s+/g, ' ')
                  .trim()
                  .toUpperCase();
                const wanted = norm(lbl);
                const visible = (el) => !!(
                  el && el.offsetParent !== null
                  && window.getComputedStyle(el).visibility !== 'hidden'
                );
                const exact = Array.from(document.querySelectorAll(
                  'a,span,div,td,strong,b,label'
                )).filter((el) => visible(el) && norm(el.textContent) === wanted);
                for (const target of exact) {
                  let container = target;
                  for (let depth = 0; container && depth < 8; depth += 1) {
                    const text = norm(container.innerText || container.textContent);
                    if (text.includes(wanted) && text.includes('TOMO')) return true;
                    container = container.parentElement;
                  }
                }
                return false;
            }""", label_text)
            if found:
                return True
        except Exception:
            pass

        try:
            row_re = row_re or re.compile(
                rf'\b{re.escape(label_text)}\b',
                re.IGNORECASE,
            )
            rows = frame.locator('tr').filter(has_text=row_re)
            return rows.count() > 0 and rows.first.is_visible()
        except Exception:
            return False

    def _is_inside_subexpediente(self, label):
        label_text = str(label).strip()
        label_upper = label_text.upper()

        for frame in self.page.frames:
            try:
                body = frame.locator('body')
                if not body.count():
                    continue
                body_text = body.inner_text(timeout=1500)
                body_upper = body_text.upper()
                if label_upper not in body_upper or 'ACCIONES' not in body_upper:
                    continue

                # SAIA conserva nodos ocultos de otras rutas. Solo aceptamos el
                # texto exacto cuando está visible en la franja del breadcrumb.
                in_visible_header = frame.evaluate(r"""(lbl) => {
                    const norm = (value) => (value || '')
                      .normalize('NFD')
                      .replace(/[\u0300-\u036f]/g, '')
                      .replace(/\s+/g, ' ')
                      .trim()
                      .toUpperCase();
                    const wanted = norm(lbl);
                    const visible = (el) => {
                      if (!el || el.offsetParent === null) return false;
                      const style = window.getComputedStyle(el);
                      return style.visibility !== 'hidden' && style.display !== 'none';
                    };
                    return Array.from(document.querySelectorAll(
                      'a,span,div,li,td,strong,b,label'
                    )).some((el) => {
                      if (!visible(el) || norm(el.textContent) !== wanted) return false;
                      if (el.closest('.well, .kenlace_saia, [id^="resultado_pantalla_"]')) {
                        return false;
                      }
                      const rect = el.getBoundingClientRect();
                      return rect.width > 0 && rect.height > 0
                        && rect.top >= 0 && rect.top <= 180;
                    });
                }""", label_text)
                if in_visible_header:
                    return True

                # Fallback: el panel lateral "Informacion del expediente" muestra
                # "Nombre del expediente: <label>" cuando ese nodo es el activo.
                # SAIA renderiza un frame anidado por cada nivel del arbol de
                # expedientes (uno por idexpediente en la jerarquia); el panel de
                # detalle vive fuera de la franja superior de 180px que usa el
                # chequeo de breadcrumb, asi que sin esto _is_inside_subexpediente
                # nunca detecta la navegacion en rutas con arboles profundos
                # (ej. Conciliaciones Bancarias > Fiduciaria Corficolombiana > año).
                normalized = self._soft_space(body_text).upper()
                name_re = re.compile(
                    r'NOMBRE\s+DEL\s+EXPEDIENTE\s*:?\s*' + re.escape(label_upper) + r'\b'
                )
                if name_re.search(normalized):
                    return True
            except Exception:
                continue
        return False

    def _dismiss_stray_expediente_modal(self):
        """Cierra el dialogo 'Nuevo responsable' (mover expediente) que SAIA abre
        cuando el click cae sobre el icono de mover/reasignar en vez del icono de
        navegacion. Sin esto el dialogo deja un backdrop que bloquea los siguientes
        intentos de click_text_near_tomo, haciendo que parezca que MAYORISTA nunca
        responde al click."""
        closed = False
        for frame in self.page.frames:
            try:
                body = frame.locator('body')
                if not body.count():
                    continue
                body_text = body.inner_text(timeout=1000)
            except Exception:
                continue
            if 'nuevo responsable' not in body_text.lower():
                continue
            for selector in [
                'button:has-text("Cerrar")',
                'a:has-text("Cerrar")',
                'text=CERRAR',
                'button:has-text("Cancelar")',
                'a:has-text("Cancelar")',
            ]:
                try:
                    locator = frame.locator(selector)
                    if locator.count() and locator.first.is_visible():
                        locator.first.click()
                        closed = True
                        break
                except Exception:
                    continue
        if closed:
            try:
                self.page.wait_for_timeout(800)
            except Exception:
                pass
        return closed

    def click_text_near_tomo(self, label):
        """Navega DENTRO de un sub-expediente (ej. '2016') haciendo click en el ícono
        de carpeta (📂) de su fila en el frame de contenido (identificado por 'Tomo:').

        En SAIA la fila de un sub-expediente tiene:
          [📂 ícono]  [texto "2016"]  Tomo: 1 de 1  [íconos de acción]
        El ícono 📂 es el primer <a:has(img)> de la fila y ES el que realmente navega
        DENTRO del expediente, cambiando el breadcrumb y el contexto del botón Acciones.
        Hacer click en el texto "2016" solo SELECCIONA la fila sin navegar.

        Estrategias en orden:
        1. Primer <a:has(img)> en la <tr> que contiene el año  ← ícono de carpeta
        2. Primer <a> en esa <tr>                              ← fallback fila
        3. Links con texto exacto del año en el frame          ← fallback texto
        4. JS click en link con texto exacto                   ← fallback JS
        5. click_text global                                   ← fallback absoluto
        """
        self._last_year_clicked = label
        label_text = str(label)
        label_upper = label_text.upper()
        year_re = re.compile(rf'\b{re.escape(label_text)}\b', re.IGNORECASE)
        exact_re = re.compile(rf'^\s*{re.escape(label_text)}\s*$', re.IGNORECASE)

        for attempt in range(8):
            self._dismiss_stray_expediente_modal()
            for frame in self.page.frames:
                try:
                    body = frame.locator('body')
                    if not body.count():
                        continue
                    try:
                        body_text = body.inner_text(timeout=2000)
                    except Exception:
                        continue
                    if 'Tomo' not in body_text and 'tomo' not in body_text:
                        continue
                    if label_upper not in body_text.upper():
                        continue

                    try:
                        clicked = frame.evaluate(r"""(lbl) => {
                            const norm = (value) => (value || '')
                              .normalize('NFD')
                              .replace(/[\u0300-\u036f]/g, '')
                              .replace(/\s+/g, ' ')
                              .trim()
                              .toUpperCase();
                            const wanted = norm(lbl);
                            const visible = (el) => !!(
                              el && el.offsetParent !== null
                              && window.getComputedStyle(el).visibility !== 'hidden'
                            );
                            const exact = Array.from(document.querySelectorAll(
                              'a,span,div,td,strong,b,label'
                            )).filter((el) => visible(el) && norm(el.textContent) === wanted);

                            const rowCardFor = (target) => {
                              let container = target;
                              for (let depth = 0; container && depth < 10; depth += 1) {
                                const text = norm(container.innerText || container.textContent);
                                if (text.includes(wanted) && text.includes('TOMO')) {
                                  return container.closest('.well, [id^="resultado_pantalla_"]') || container;
                                }
                                container = container.parentElement;
                              }
                              return null;
                            };


                            const clickFolderInCard = (card) => {
                              if (!visible(card)) return false;
                              const navigation = Array.from(card.querySelectorAll('.kenlace_saia[enlace]'))
                                .find((el) => visible(el) && norm(el.textContent).includes(wanted));
                              if (navigation) {
                                navigation.click();
                                return true;
                              }

                              const controls = Array.from(card.querySelectorAll(
                                'a,button,[role="button"],[onclick],[enlace],input[type="image"],img[onclick]'
                              )).filter(visible);
                              const ranked = controls.map((control, index) => {
                                const img = control.matches('img,input[type="image"]')
                                  ? control
                                  : control.querySelector('img');
                                const icon = control.querySelector('i');
                                const meta = norm([
                                  control.className,
                                  control.title,
                                  control.getAttribute('aria-label'),
                                  control.getAttribute('enlace'),
                                  control.getAttribute('href'),
                                  control.getAttribute('onclick'),
                                  control.getAttribute('value'),
                                  control.getAttribute('src'),
                                  icon && icon.className,
                                  img && img.alt,
                                  img && img.title,
                                  img && img.getAttribute('src')
                                ].filter(Boolean).join(' '));
                                let score = (img || icon) ? 20 : 0;
                                if (/KENLACE_SAIA/.test(meta)) score += 200;
                                if (/(CARPETA|FOLDER|EXPEDIENTE|ABRIR|INGRESAR|CONSULTA_BUSQUEDA_EXPEDIENTE)/.test(meta)) score += 120;
                                if (/(LOCK|CANDADO|BLOQUE|PRINT|IMPRIM|EDIT|ELIMIN|DELETE|INFO|RESPONSABLE|MOVER|TRASLAD|REASIGN|CAMBIAR)/.test(meta)) score -= 150;
                                return {control, score, index};
                              }).sort((a, b) => b.score - a.score || a.index - b.index);
                              if (ranked[0] && ranked[0].score >= 20) {
                                ranked[0].control.click();
                                return true;
                              }
                              return false;
                            };

                            // La tarjeta .well también puede tener textContent "2016".
                            // Resolver primero el enlace exacto evita accionar controles
                            // pertenecientes a otra tarjeta del listado.
                            const directNavigation = Array.from(document.querySelectorAll(
                              '.kenlace_saia[enlace]'
                            )).find((el) => visible(el) && norm(el.textContent) === wanted);
                            if (directNavigation) {
                              directNavigation.click();
                              return true;
                            }

                            for (const target of exact) {
                              const rowCard = rowCardFor(target);
                              if (rowCard && clickFolderInCard(rowCard)) {
                                return true;
                              }

                              // SAIA usa un div.kenlace_saia[enlace], no un <a>.
                              // El texto interno solo selecciona la fila; el contenedor
                              // es el que abre el expediente y cambia el breadcrumb.
                              const navigation = target.closest(
                                '.kenlace_saia[enlace], .kenlace_saia, [enlace*="consulta_busqueda_expediente"]'
                              );
                              if (visible(navigation)) {
                                navigation.click();
                                return true;
                              }

                              let container = target;
                              for (let depth = 0; container && depth < 8; depth += 1) {
                                const text = norm(container.innerText || container.textContent);
                                const controls = Array.from(container.querySelectorAll(
                                  'a,button,[role="button"],[onclick],[enlace],input[type="image"],img[onclick]'
                                )).filter(visible);
                                if (text.includes(wanted) && text.includes('TOMO') && controls.length) {
                                  const ranked = controls.map((control, index) => {
                                    const img = control.matches('img,input[type="image"]')
                                      ? control
                                      : control.querySelector('img');
                                    const icon = control.querySelector('i');
                                    const meta = norm([
                                      control.className,
                                      control.title,
                                      control.getAttribute('aria-label'),
                                      control.getAttribute('enlace'),
                                      control.getAttribute('href'),
                                      control.getAttribute('onclick'),
                                      control.getAttribute('value'),
                                      control.getAttribute('src'),
                                      icon && icon.className,
                                      img && img.alt,
                                      img && img.title,
                                      img && img.getAttribute('src')
                                    ].filter(Boolean).join(' '));
                                    let score = (img || icon) ? 20 : 0;
                                    if (/KENLACE_SAIA/.test(meta)) score += 200;
                                    if (/(CARPETA|FOLDER|EXPEDIENTE|ABRIR|INGRESAR)/.test(meta)) score += 100;
                                    if (/(LOCK|CANDADO|BLOQUE|PRINT|IMPRIM|EDIT|ELIMIN|DELETE|INFO|RESPONSABLE|MOVER|TRASLAD|REASIGN|CAMBIAR)/.test(meta)) score -= 100;
                                    return {control, score, index};
                                  }).sort((a, b) => b.score - a.score || a.index - b.index);
                                  if (ranked[0] && ranked[0].score >= 20) {
                                    ranked[0].control.click();
                                    return true;
                                  }
                                }
                                container = container.parentElement;
                              }
                            }
                            return false;
                        }""", label)
                        if clicked:
                            try:
                                self.page.wait_for_load_state('networkidle', timeout=8000)
                            except self._timeout_error:
                                pass
                            if self._wait_until_parent_subexpediente_row_disappears(label):
                                return
                    except Exception:
                        pass

                    # ── Estrategia 1 y 2: ícono de carpeta en la fila del año ──────────
                    # El primer <a:has(img)> de la <tr> es el ícono 📂 que navega dentro
                    try:
                        year_row = frame.locator('tr').filter(has_text=year_re)
                        if year_row.count() > 0:
                            row = year_row.first
                            for folder_sel in [
                                'a:has(img[src*="carpeta" i])',
                                'a:has(img[src*="folder" i])',
                                'a:has(img[title*="abrir" i])',
                                'button:has(img)',
                                '[onclick]:has(img)',
                                'input[type="image"]',
                                'img[onclick]',
                                'a:has(img)',
                            ]:
                                try:
                                    folder_loc = row.locator(folder_sel)
                                    if folder_loc.count() > 0 and folder_loc.first.is_visible():
                                        folder_loc.first.click()
                                        try:
                                            self.page.wait_for_load_state('networkidle', timeout=8000)
                                        except self._timeout_error:
                                            pass
                                        if self._wait_until_parent_subexpediente_row_disappears(label):
                                            return
                                except Exception:
                                    continue
                    except Exception:
                        pass

                    # ── Estrategia 3: click en el texto del año ───────────────────────
                    for locator in [
                        frame.get_by_role('link', name=label, exact=True),
                        frame.locator('a').filter(has_text=exact_re),
                        frame.get_by_role('link', name=label, exact=False),
                        frame.locator('a').filter(has_text=label),
                        frame.get_by_text(label, exact=True),
                        frame.get_by_text(label, exact=False),
                    ]:
                        try:
                            if locator.count() and locator.first.is_visible():
                                locator.first.click()
                                try:
                                    self.page.wait_for_load_state('networkidle', timeout=8000)
                                except self._timeout_error:
                                    pass
                                if self._wait_until_parent_subexpediente_row_disappears(label):
                                    return
                        except Exception:
                            continue

                    # ── Estrategia 4: JS click en el texto exacto ─────────────────────
                    try:
                        clicked = frame.evaluate("""(lbl) => {
                            const links = Array.from(document.querySelectorAll('a'));
                            for (const link of links) {
                                if (
                                    link.textContent.trim().toUpperCase() === lbl.trim().toUpperCase()
                                    && link.offsetParent !== null
                                ) {
                                    link.click();
                                    return true;
                                }
                            }
                            return false;
                        }""", label)
                        if clicked:
                            try:
                                self.page.wait_for_load_state('networkidle', timeout=8000)
                            except self._timeout_error:
                                pass
                            if self._wait_until_parent_subexpediente_row_disappears(label):
                                return
                    except Exception:
                        pass
                except Exception:
                    continue
            self.page.wait_for_timeout(1500)

        # ── Estrategia 5: fallback global ─────────────────────────────────────────
        self.capture_screenshot(f'subexpediente_{self._slug(label)}_click_sin_navegacion')
        raise SAIASelectorError(
            f'No se pudo abrir la carpeta del subexpediente "{label}". '
            'SAIA mantuvo visible la fila del listado padre.'
        )

    def _wait_until_parent_subexpediente_row_disappears(self, label, attempts=8):
        label_text = str(label)
        label_upper = label_text.upper()
        row_re = re.compile(rf'\b{re.escape(label_text)}\b', re.IGNORECASE)
        for _ in range(attempts):
            if self._is_inside_subexpediente(label_text):
                return True

            parent_row_visible = False
            for frame in self.page.frames:
                try:
                    body = frame.locator('body')
                    if not body.count():
                        continue
                    body_text = body.inner_text(timeout=1500)
                    if label_upper not in body_text.upper():
                        continue
                    if 'Tomo' not in body_text and 'tomo' not in body_text:
                        continue
                    if self._subexpediente_row_visible(frame, label_text, row_re):
                        parent_row_visible = True
                        break
                except Exception:
                    continue
            if not parent_row_visible:
                self.page.wait_for_timeout(1500)
                return True
            self.page.wait_for_timeout(1500)
        return False

    def _assert_navigated_into_subexpediente(self, label):
        """Fail if SAIA stayed on the parent list after clicking a year folder."""
        label_text = str(label)
        label_upper = label_text.upper()
        row_re = re.compile(rf'\b{re.escape(label_text)}\b', re.IGNORECASE)
        saw_label = False

        for _ in range(8):
            if self._is_inside_subexpediente(label_text):
                return
            still_on_parent_row = False
            saw_label = False
            for frame in self.page.frames:
                try:
                    body = frame.locator('body')
                    if not body.count():
                        continue
                    try:
                        body_text = body.inner_text(timeout=1500)
                    except Exception:
                        continue
                    if label_upper in body_text.upper():
                        saw_label = True
                    if 'Tomo' not in body_text and 'tomo' not in body_text:
                        continue

                    if self._subexpediente_row_visible(frame, label_text, row_re):
                        still_on_parent_row = True
                        break
                except Exception:
                    continue

            # La desaparición de la fila no demuestra que se haya navegado;
            # el breadcrumb visible debe confirmar el destino esperado.
            self.page.wait_for_timeout(1500)

        self.capture_screenshot(f'subexpediente_{self._slug(label_text)}_no_ingresado')
        if still_on_parent_row:
            detail = ' SAIA sigue mostrando la fila del subexpediente en el listado padre.'
        elif saw_label:
            detail = ' El texto existe, pero no aparece en el breadcrumb visible.'
        else:
            detail = ' El breadcrumb visible no cambio al subexpediente esperado.'
        raise SAIASelectorError(
            f'No se ingreso al subexpediente "{label_text}" antes de abrir Acciones.{detail}'
        )

    def click_any_text_in_tomo_frame(self, labels):
        """Click en el frame de contenido (identificado por 'Tomo:'), priorizando
        el elemento dentro de la fila del año previamente seleccionado (_last_year_clicked).

        Estrategia en orden de especificidad:
        1. Elemento en la <tr> que contiene el año → Acciones de la fila exacta de 2016
        2. Cualquier elemento en el frame de contenido → Acciones dentro del frame Tomo
        3. Click global en todos los frames (fallback final)
        """
        year_re = (
            re.compile(rf'\b{re.escape(self._last_year_clicked)}\b')
            if self._last_year_clicked else None
        )
        for attempt in range(8):
            for frame in self.page.frames:
                try:
                    body = frame.locator('body')
                    if not body.count():
                        continue
                    try:
                        body_text = body.inner_text(timeout=2000)
                    except Exception:
                        continue
                    if 'Tomo' not in body_text and 'tomo' not in body_text:
                        continue

                    # ── Estrategia 1: click en la fila <tr> que contiene el año ──────
                    if year_re:
                        try:
                            year_row = frame.locator('tr').filter(has_text=year_re)
                            if year_row.count() > 0:
                                row = year_row.first
                                for label in labels:
                                    for row_loc in [
                                        row.get_by_role('link', name=label, exact=True),
                                        row.get_by_role('button', name=label, exact=True),
                                        row.get_by_role('link', name=label, exact=False),
                                        row.get_by_role('button', name=label, exact=False),
                                        row.get_by_text(label, exact=False),
                                        row.locator('a').filter(has_text=label),
                                    ]:
                                        try:
                                            if row_loc.count() and row_loc.first.is_visible():
                                                row_loc.first.click()
                                                try:
                                                    self.page.wait_for_load_state('networkidle', timeout=8000)
                                                except self._timeout_error:
                                                    pass
                                                self.page.wait_for_timeout(2500)
                                                return
                                        except Exception:
                                            continue
                        except Exception:
                            pass

                    # ── Estrategia 2: cualquier elemento en el frame de contenido ─────
                    for label in labels:
                        for locator in [
                            frame.get_by_role('link', name=label, exact=True),
                            frame.get_by_role('button', name=label, exact=True),
                            frame.get_by_role('link', name=label, exact=False),
                            frame.get_by_role('button', name=label, exact=False),
                            frame.get_by_text(label, exact=True),
                            frame.get_by_text(label, exact=False),
                        ]:
                            try:
                                if locator.count() and locator.first.is_visible():
                                    locator.first.click()
                                    try:
                                        self.page.wait_for_load_state('networkidle', timeout=8000)
                                    except self._timeout_error:
                                        pass
                                    self.page.wait_for_timeout(2500)
                                    return
                            except Exception:
                                continue
                except Exception:
                    continue
            self.page.wait_for_timeout(1500)

        # ── Estrategia 3: fallback global ────────────────────────────────────────
        self.click_any_text(labels)

    def click_any_text(self, labels):
        errors = []
        for label in labels:
            try:
                self.click_text(label)
                return
            except SAIASelectorError as exc:
                errors.append(str(exc))
        raise SAIASelectorError('No se encontro ninguna alternativa: ' + ' | '.join(errors))

    def click_by_title(self, title_contains):
        selector = f'a[title*="{title_contains}"], button[title*="{title_contains}"], img[title*="{title_contains}"]'
        # Hasta 10 intentos x 2 s = 20 s de espera maxima.
        # SAIA usa framesets y el frame del menu puede tardar varios segundos en
        # actualizar despues de que otro frame termina su navegacion.
        for _attempt in range(10):
            for frame in self.page.frames:
                locator = frame.locator(selector)
                try:
                    if locator.count() and locator.first.is_visible():
                        locator.first.click()
                        try:
                            self.page.wait_for_load_state('networkidle', timeout=5000)
                        except self._timeout_error:
                            pass
                        self.page.wait_for_timeout(1500)
                        return
                except (self._timeout_error, Exception):
                    continue
            self.page.wait_for_timeout(2000)

        self.capture_screenshot(f'titulo_no_encontrado_{self._slug(title_contains)}')
        raise SAIASelectorError(f'No se encontro elemento con title: {title_contains}')

    def capture_screenshot(self, name):
        self.config.screenshot_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        path = self.config.screenshot_dir / f'{timestamp}_{self._slug(name)}.png'
        self.page.screenshot(path=str(path), full_page=True)
        self.last_screenshot = str(path)
        return str(path)

    def _select_dependency(self):
        self.page.wait_for_timeout(2000)
        if self._select_dependency_from_native_select():
            return

        for label in selectors.DEPENDENCY_LABELS:
            try:
                field = self.page.get_by_label(label, exact=False)
                if field.count() and field.first.is_visible():
                    field.first.click()
                    self.page.wait_for_timeout(1500)
                    if self._select_dependency_from_native_select():
                        return
                    self.click_text(selectors.DEPENDENCY_OPTION)
                    return
            except self._timeout_error:
                continue

        try:
            self.click_text('por favor seleccione')
            self.page.wait_for_timeout(1500)
            if self._select_dependency_from_native_select():
                return
            self.click_text(selectors.DEPENDENCY_OPTION)
            return
        except SAIASelectorError:
            pass

        if self._select_dependency_from_native_select(allow_single_option=True):
            return

        self.capture_screenshot('dependencia_no_encontrada')
        raise SAIASelectorError('No se pudo seleccionar DEPENDENCIA DEL CREADOR DEL DOCUMENTO.')

    def _select_dependency_from_native_select(self, allow_single_option=False):
        expected_values = [
            self._normalize_for_match(value)
            for value in getattr(selectors, 'DEPENDENCY_OPTION_ALIASES', [selectors.DEPENDENCY_OPTION])
        ]
        for _attempt in range(6):
            for frame in self.page.frames:
                selects = frame.locator('select')
                for index in range(selects.count()):
                    select = selects.nth(index)
                    try:
                        if not select.is_visible() or not select.is_enabled():
                            continue
                        try:
                            select.click(timeout=1500)
                            self.page.wait_for_timeout(500)
                        except Exception:
                            pass
                        options_data = select.evaluate(
                            """(element) => Array.from(element.options).map((option, index) => ({
                                index,
                                value: option.value || '',
                                text: option.textContent || '',
                                disabled: option.disabled,
                            }))"""
                        )
                        real_options = [
                            option for option in options_data
                            if self._is_real_select_option(option)
                        ]
                        selected_option = self._find_dependency_option(real_options, expected_values)
                        if selected_option is None and allow_single_option and len(real_options) == 1:
                            selected_option = real_options[0]
                        if selected_option is None:
                            continue
                        value = selected_option.get('value')
                        self._apply_select_option(select, selected_option)
                        self.page.wait_for_timeout(700)
                        return True
                    except Exception:
                        continue
            self.page.wait_for_timeout(1000)
        return False

    def _apply_select_option(self, select, selected_option):
        value = selected_option.get('value')
        index = selected_option.get('index')
        try:
            if value:
                select.select_option(value=value, timeout=5000)
            else:
                select.select_option(index=index, timeout=5000)
            return
        except Exception:
            pass

        select.evaluate(
            """(element, selection) => {
                const value = selection.value || '';
                const index = Number(selection.index);
                if (value) {
                    element.value = value;
                } else if (!Number.isNaN(index) && element.options[index]) {
                    element.selectedIndex = index;
                }
                element.dispatchEvent(new Event('change', { bubbles: true }));
                element.dispatchEvent(new Event('input', { bubbles: true }));
            }""",
            {'value': value or '', 'index': index},
        )

    def _is_real_select_option(self, option):
        if option.get('disabled'):
            return False
        text = self._normalize_for_match(option.get('text'))
        value = self._normalize_for_match(option.get('value'))
        if not text and not value:
            return False
        placeholder_markers = ('PORFAVORSELECCIONE', 'SELECCIONE', 'SELECCIONAR', 'ESCOJA')
        return not any(marker in text for marker in placeholder_markers)

    def _find_dependency_option(self, options_data, expected_values):
        for option in options_data:
            normalized = self._normalize_for_match(
                f"{option.get('text', '')} {option.get('value', '')}"
            )
            if any(expected and (expected in normalized or normalized in expected) for expected in expected_values):
                return option
            has_core_tokens = all(token in normalized for token in ('ARCHIVOCENTRAL', 'ANALISTA'))
            has_gestion_tokens = 'GESTIONDOCUMENTAL' in normalized or (
                'GESTION' in normalized and 'DOCUMENTAL' in normalized
            )
            if has_core_tokens and has_gestion_tokens:
                return option
        return None

    def _wait_for_document_form(self):
        for _attempt in range(20):
            for frame in self.page.frames:
                try:
                    selects = frame.locator('select')
                    file_inputs = frame.locator('input[type="file"]')
                    has_dependency_select = any(
                        selects.nth(index).is_visible()
                        for index in range(selects.count())
                    )
                    has_file_input = file_inputs.count() > 0
                    body_text = frame.locator('body').inner_text(timeout=1000) if frame.locator('body').count() else ''
                    if has_dependency_select or has_file_input or 'DEPENDENCIA DEL CREADOR' in body_text.upper():
                        return
                except Exception:
                    continue
            self.page.wait_for_timeout(1500)

        self.capture_screenshot('formulario_adicionar_no_cargado')
        raise SAIASelectorError('No cargo el formulario de Adicionar documento en SAIA.')

    def _fill_subject(self, asunto_saia):
        for label in selectors.SUBJECT_LABELS:
            try:
                field = self.page.get_by_label(label, exact=False)
                if field.count() and field.first.is_visible():
                    field.first.fill(asunto_saia)
                    return
            except self._timeout_error:
                continue

        candidates = []
        for frame in self.page.frames:
            text_inputs = frame.locator('input[type="text"], textarea')
            for index in range(text_inputs.count()):
                field = text_inputs.nth(index)
                try:
                    if not field.is_visible():
                        continue
                    box = field.bounding_box() or {}
                    candidates.append((box.get('width') or 0, field))
                except self._timeout_error:
                    continue

        if candidates:
            candidates.sort(key=lambda item: item[0], reverse=True)
            candidates[0][1].fill(asunto_saia)
            return

        self.capture_screenshot('asunto_no_encontrado')
        raise SAIASelectorError('No se pudo encontrar el campo Nombre o asunto.')

    def _attach_file(self, file_path, extended_timeout=False):
        attach_started_at = datetime.now()
        self._record_timing('saia_timing_attach_start', attach_started_at, archivo=str(file_path))

        # SAIA usa Dropzone.js: el archivo se sube via AJAX POST a cargar_archivos_formato.php
        # inmediatamente al hacer set_input_files(). Interceptar esa respuesta es más fiable
        # que leer el DOM (que nunca muestra 'quitar anexo' con Dropzone).
        # 180s (antes 120s): en uso real SAIA a veces tarda mas de 2 min en responder
        # incluso con PDFs livianos, y un timeout corto aqui fuerza un reintento completo
        # del documento (re-navegar, re-llenar formulario, re-adjuntar) en vez de solo
        # esperar un poco mas.
        attachment_timeout_ms = 300000 if extended_timeout else 180000

        for frame in self.page.frames:
            for selector in selectors.FILE_INPUT_SELECTORS:
                locator = frame.locator(selector)
                if locator.count():
                    try:
                        with self.page.expect_response(
                            self._is_attachment_upload_response,
                            timeout=attachment_timeout_ms,
                        ) as response_info:
                            locator.first.set_input_files(str(file_path))

                        resp = response_info.value
                        if self._attachment_response_is_success(resp):
                            self._record_timing(
                                'saia_timing_attach_ready',
                                attach_started_at,
                                archivo=Path(file_path).name,
                            )
                            return
                        # Dropzone respondió pero sin confirmar éxito — fallback a DOM
                        self._wait_for_attachment_ready(
                            Path(file_path).name,
                            extended_timeout=extended_timeout,
                            started_at=attach_started_at,
                        )
                        return

                    except self._timeout_error:
                        # cargar_archivos_formato.php no respondió — puede ser otro tipo
                        # de input (no Dropzone). Intentar con DOM polling como fallback.
                        self._wait_for_attachment_ready(
                            Path(file_path).name,
                            extended_timeout=extended_timeout,
                            started_at=attach_started_at,
                        )
                        return

        self.capture_screenshot('input_archivo_no_encontrado')
        raise SAIASelectorError('No se encontro input de archivo para adjuntar anexo.')

    @staticmethod
    def _is_attachment_upload_response(response):
        url = str(getattr(response, 'url', '') or '').lower()
        request = getattr(response, 'request', None)
        method = str(getattr(request, 'method', 'POST') or 'POST').upper()
        upload_markers = (
            'cargar_archiv',
            'subir_archiv',
            'upload',
            'adjunt',
        )
        return method == 'POST' and any(marker in url for marker in upload_markers)

    @classmethod
    def _attachment_response_is_success(cls, response):
        status = int(getattr(response, 'status', 0) or 0)
        if status < 200 or status >= 300:
            return False
        try:
            payload = response.json()
        except Exception:
            return False
        return cls._attachment_payload_is_success(payload)

    @classmethod
    def _attachment_payload_is_success(cls, payload):
        if isinstance(payload, list):
            return any(cls._attachment_payload_is_success(item) for item in payload)
        if not isinstance(payload, dict):
            return False

        normalized = {str(key).lower(): value for key, value in payload.items()}
        error_value = normalized.get('error')
        error_ok = error_value in (0, '0', False, None, '')
        id_value = next(
            (
                value
                for key, value in normalized.items()
                if key in {'id', 'idarchivo', 'id_archivo', 'archivo_id', 'id_anexo'}
                and value not in (None, '', 0, '0')
            ),
            None,
        )
        explicit_success = normalized.get('success') in (True, 1, '1', 'true')
        if error_ok and (id_value is not None or explicit_success):
            return True
        return any(cls._attachment_payload_is_success(value) for value in payload.values())

    @staticmethod
    def _attachment_dom_is_ready(frame, filename, body_text):
        normalized = str(body_text or '').lower()
        filename_visible = str(filename or '').lower() in normalized
        still_loading = any(
            marker in normalized
            for marker in ('cancelar carga', 'enviando', 'cargando')
        )
        if still_loading:
            return False

        if 'quitar anexo' in normalized:
            return True

        try:
            completed = frame.locator(
                '.dz-preview.dz-success, '
                '.dz-preview.dz-complete:not(.dz-error), '
                '[data-dz-remove]'
            )
            if completed.count():
                return filename_visible or completed.first.is_visible()
        except Exception:
            return False
        return False

    def _wait_for_attachment_ready(self, filename, extended_timeout=False, started_at=None):
        # 150 intentos (~150s, antes 90s): fallback de respaldo cuando el intercepto de
        # red en _attach_file no confirma el anexo a tiempo. Ampliado junto con
        # attachment_timeout_ms para reducir reintentos completos por falsos timeouts.
        attempts = 300 if extended_timeout else 150
        stable_ready_count = 0
        started_at = started_at or datetime.now()
        for _attempt in range(attempts):
            for frame in self.page.frames:
                try:
                    body_text = frame.locator('body').inner_text(timeout=1000) if frame.locator('body').count() else ''
                    normalized = body_text.lower()

                    # Detectar rechazo explícito de SAIA (tamaño/tipo) para fallar rápido.
                    # Se espera ≥5 s para no reaccionar a textos transitorios durante el upload.
                    if _attempt >= 5 and any(err in normalized for err in selectors.ATTACHMENT_ERROR_TEXTS):
                        self.capture_screenshot('saia_rechazo_anexo')
                        raise SAIASelectorError(
                            f'SAIA rechazo el archivo adjunto "{filename}" '
                            '(posible restriccion de tamano o tipo). '
                            'Verifique los limites de SAIA y cargue el documento manualmente.'
                        )

                    attachment_ready = self._attachment_dom_is_ready(
                        frame,
                        filename,
                        body_text,
                    )
                    if attachment_ready:
                        stable_ready_count += 1
                    else:
                        stable_ready_count = 0
                    if stable_ready_count >= 1:
                        self._record_timing('saia_timing_attach_ready', started_at, archivo=filename)
                        return
                except SAIASelectorError:
                    raise
                except Exception:
                    continue
            self.page.wait_for_timeout(1000)

        self.capture_screenshot('anexo_no_listo')
        if extended_timeout:
            raise SAIASelectorError(
                'SAIA tardo mas de lo esperado cargando un PDF pesado. '
                'Verifique manualmente si el documento quedo cargado antes de reintentar, para evitar duplicados.'
            )
        raise SAIASelectorError('El anexo no termino de cargar en SAIA antes de continuar.')

    def _wait_for_submission_result(self, expected_subject=None, extended_timeout=False, url_before=None, started_at=None):
        timeout_ms = (
            SAIA_POST_CONTINUE_EXTENDED_TIMEOUT_MS
            if extended_timeout else SAIA_POST_CONTINUE_TIMEOUT_MS
        )
        min_wait_ms = SAIA_POST_CONTINUE_MIN_WAIT_MS
        started_at = started_at or datetime.now()
        # Contador de lecturas consecutivas sin señal de "cargando/enviando".
        # frame.evaluate() puede fallar mientras el frame transiciona durante la
        # subida HTTP (retorna '' silenciosamente). Una sola lectura en '' causaria
        # salida prematura; requerimos 3 lecturas consecutivas para confirmar que
        # la subida realmente termino y no es un fallo transitorio de lectura.
        not_loading_count = 0
        while True:
            # Sin controls: evita que el campo asunto (input value) o el nombre
            # del archivo adjunto (visible en body) activen deteccion prematura de
            # exito mientras el formulario aun esta visible durante el envio.
            text = self._all_frames_text(include_controls=False)
            normalized = text.lower()
            current_url = self.current_url()
            elapsed_ms = (datetime.now() - started_at).total_seconds() * 1000

            # Senales de exito inequivocas: solo aparecen en la pagina de
            # confirmacion de SAIA, no en el formulario de carga.
            if any(success in normalized for success in selectors.SUCCESS_TEXTS):
                self._record_timing('saia_timing_success_text_visible', started_at)
                return
            if self._asunto_field_visible(expected_subject, text):
                self._record_timing('saia_timing_asunto_visible', started_at)
                return
            if (
                self._looks_like_document_detail(text, current_url)
                and self._subject_in_text(expected_subject, text)
            ):
                self._record_timing('saia_timing_document_detail_visible', started_at)
                return
            if self._left_panel_version_visible(expected_subject, text):
                self._record_timing('saia_timing_left_panel_subject_visible', started_at)
                return
            if self._anexo_visible(expected_subject, text) and self._looks_like_document_detail(text, current_url):
                self._record_timing('saia_timing_anexo_visible', started_at)
                return
            # _looks_like_document_list_confirmation NO se usa en el wait loop:
            # el formulario muestra "VINCULAR DOCUMENTOS A UN EXPEDIENTE" como
            # titulo de pagina Y el nombre del archivo adjunto en el body, lo que
            # coincide con el asunto y causaria salida prematura mientras SAIA
            # aun procesa el envio. Solo se usa en read_result (pagina estabilizada).

            # IMPORTANTE: el check del formulario debe ir ANTES de los checks de error,
            # porque durante "Enviando..." SAIA puede mostrar textos de validacion
            # ("campo obligatorio" para campos vaciados mid-POST) que son falsos positivos.
            # "adjuntar archivo" / "nombre o asunto" aparecen UNICAMENTE en el formulario
            # de carga; nunca en la pagina de confirmacion ni en la lista de expedientes.
            form_visible = 'adjuntar archivo' in normalized or 'nombre o asunto' in normalized
            # Solo verificar errores fuertes cuando el formulario ya no esta visible.
            # Con formulario visible, los textos de validacion son parte del formulario
            # mismo y no indican rechazo de SAIA al documento.
            if not form_visible and any(error in normalized for error in selectors.ERROR_TEXTS_STRONG):
                return
            if elapsed_ms < min_wait_ms:
                self.page.wait_for_timeout(1000)
                continue
            if elapsed_ms >= timeout_ms:
                break
            if form_visible:
                not_loading_count = 0
                self.page.wait_for_timeout(1000)
                continue
            # Formulario ya no visible: ahora si checar URL y panel izquierdo.
            if url_before and current_url != url_before:
                return
            if self._subject_in_left_panel(expected_subject):
                return
            # Verificar si el boton sigue activo con controls (frame.evaluate ya
            # funciona porque el POST HTTP termino y el frame no esta bloqueado).
            normalized_all = self._all_frames_text(include_controls=True).lower()
            if 'enviando' in normalized_all or 'cargando' in normalized_all:
                self._record_timing('saia_timing_sending_visible', started_at)
                not_loading_count = 0
                self.page.wait_for_timeout(1000)
                continue
            if any(error in normalized_all for error in selectors.ERROR_TEXTS):
                return
            # El formulario desaparecio y no hay indicador de carga activo.
            # Requerir 3 lecturas consecutivas antes de llamar read_result,
            # para dar tiempo a que la pagina de confirmacion cargue.
            not_loading_count += 1
            if not_loading_count >= 3:
                self._record_timing('saia_timing_sending_finished', started_at)
                return
            self.page.wait_for_timeout(1000)

        self.capture_screenshot('envio_saia_sin_respuesta')
        self._record_timing('saia_timing_ambiguous_timeout', started_at)
        return

    def _all_frames_text(self, include_controls=False):
        chunks = []
        for frame in self.page.frames:
            try:
                if frame.locator('body').count():
                    chunks.append(frame.locator('body').inner_text(timeout=1000))
                    if include_controls:
                        chunks.append(self._frame_controls_text(frame))
            except Exception:
                continue
        return '\n'.join(chunks)

    def _frame_controls_text(self, frame):
        try:
            return frame.evaluate(
                """() => Array.from(
                    document.querySelectorAll('input, button, select, textarea')
                ).map((element) => [
                    element.value || '',
                    element.textContent || '',
                    element.getAttribute('title') || '',
                    element.getAttribute('aria-label') || '',
                    element.disabled ? 'disabled' : '',
                ].join(' ')).join('\\n')"""
            )
        except Exception:
            return ''

    def _subject_in_text(self, expected_subject, text):
        if not expected_subject:
            return False
        return self._subject_exact_visible(expected_subject, text)

    def _asunto_field_visible(self, expected_subject, text):
        """Detecta 'Asunto: PEL 97335' en la tabla de confirmacion de SAIA.
        El formulario de carga usa el label 'Nombre o asunto', nunca 'Asunto:'
        seguido directamente del valor — por lo que su presencia es senal inequivoca
        de que SAIA ya proceso y confirmo la carga del documento."""
        if not expected_subject:
            return False
        expected = self._soft_space(expected_subject)
        pattern = (
            rf'(?<!nombre o )asunto\s*[:\|]\s*'
            rf'{re.escape(expected)}(?!\s*-\s*[A-Za-z0-9])(?![A-Za-z0-9])'
        )
        return bool(re.search(pattern, self._soft_space(text), re.IGNORECASE))

    def _subject_in_left_panel(self, expected_subject):
        if not expected_subject:
            return False

        selectors_left = [
            '#left, #left_content, #menu, #menu_principal, #panel_izquierdo',
            '.left, .menu, .menu_left, .modulos_saia',
            'td:first-child, div:first-child',
        ]
        for frame in self.page.frames:
            for selector in selectors_left:
                locator = frame.locator(selector)
                try:
                    count = min(locator.count(), 8)
                    for index in range(count):
                        element = locator.nth(index)
                        if not element.is_visible():
                            continue
                        text = element.inner_text(timeout=700)
                        if self._subject_exact_visible(expected_subject, text):
                            return True
                except Exception:
                    continue
        return False

    def _left_panel_version_visible(self, expected_subject, content=None):
        if not expected_subject:
            return False
        if content is not None:
            return self._version_subject_visible(expected_subject, content)

        selectors_left = [
            '#left, #left_content, #menu, #menu_principal, #panel_izquierdo',
            '.left, .menu, .menu_left, .modulos_saia',
            'td:first-child, div:first-child',
        ]
        for frame in self.page.frames:
            for selector in selectors_left:
                locator = frame.locator(selector)
                try:
                    count = min(locator.count(), 8)
                    for index in range(count):
                        element = locator.nth(index)
                        if not element.is_visible():
                            continue
                        text = element.inner_text(timeout=700)
                        if self._version_subject_visible(expected_subject, text):
                            return True
                except Exception:
                    continue
        return False

    def _version_subject_visible(self, expected_subject, content):
        expected = self._soft_space(expected_subject)
        if not expected:
            return False
        text = self._soft_space(content)
        # Acepta separadores "V1." / "V1: " / "V1 " — SAIA usa "V1: PEL ..." con dos puntos
        pattern = rf'(?<![A-Za-z0-9])v\s*1[\s.:]+{re.escape(expected)}(?!\s*-\s*[A-Za-z0-9])(?![A-Za-z0-9])'
        return bool(re.search(pattern, text, re.IGNORECASE))

    def _all_frames_text_compat(self, include_controls=False):
        try:
            return self._all_frames_text(include_controls=include_controls)
        except TypeError:
            return self._all_frames_text()

    def _anexo_visible(self, expected_subject, content):
        expected = self._soft_space(expected_subject)
        if not expected:
            return False
        expected_file = rf'{re.escape(expected)}\s*\.pdf'
        text = self._soft_space(content)
        patterns = (
            rf'anexo\s*[:\|]\s*{expected_file}(?![A-Za-z0-9])',
            rf'(?<![A-Za-z0-9]){expected_file}(?![A-Za-z0-9])',
        )
        return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)

    def _build_confirmation_source(
        self,
        document_detail_confirmed=False,
        document_list_confirmed=False,
        left_panel_v1_confirmed=False,
        left_panel_confirmed=False,
        asunto_field_confirmed=False,
        anexo_confirmed=False,
        subject_confirmed=False,
        success=False,
    ):
        if not success:
            return ''
        if document_detail_confirmed and left_panel_v1_confirmed:
            return 'document_detail_left_panel_v1'
        if document_detail_confirmed and anexo_confirmed:
            return 'document_detail_anexo'
        if document_detail_confirmed and asunto_field_confirmed:
            return 'document_detail_asunto'
        if document_detail_confirmed:
            return 'document_detail'
        if document_list_confirmed:
            return 'document_list'
        if left_panel_v1_confirmed:
            return 'left_panel_v1'
        if left_panel_confirmed:
            return 'left_panel'
        if subject_confirmed:
            return 'subject_with_success_text'
        return 'success_text'

    def _looks_like_document_detail(self, content, url=''):
        normalized = self._normalize_for_match(content)
        url_text = str(url or '').lower()
        return (
            'DOCUMENTONO' in normalized
            or 'DOCUMENTONRO' in normalized
            or 'ACCIONESDOCUMENTO' in normalized
            or 'ver_documento' in url_text
        )

    def _looks_like_document_list_confirmation(self, content, expected_subject):
        if not expected_subject:
            return False
        if self._find_saia_document_list_record(content, expected_subject):
            return True
        if not self._subject_exact_visible(expected_subject, content):
            return False

        normalized = self._normalize_for_match(content)
        # "ADJUNTARARCHIVO" es exclusivo del formulario de carga de SAIA.
        # Si aparece, la pagina es el formulario (el nombre del archivo adjunto
        # hace que el asunto sea visible aunque el upload no haya terminado).
        # La pagina de confirmacion de expediente NUNCA tiene este marcador.
        if 'ADJUNTARARCHIVO' in normalized:
            return False

        list_markers = (
            'NOMBREOASUNTO',
            'MASRESULTADOS',
            'ACCIONES',
            'LISTAR',
            'VINCULARDOCUMENTOSAUNEXPEDIENTE',
            'PAGOSELECTRONICOS',
            'COMPROBANTESCONTABLES',
        )
        return any(marker in normalized for marker in list_markers)

    def _find_saia_document_list_record(self, content, expected_subject):
        if not expected_subject:
            return {}
        for record in self._parse_saia_document_list_records(content):
            subject = record.get('matched_subject', '')
            if self._subject_value_exact(expected_subject, subject):
                return record
        return {}

    def _parse_saia_document_list_records(self, content):
        records = []
        current = None
        lines = [line.strip() for line in str(content or '').splitlines() if line.strip()]

        for line in lines:
            header_match = re.match(r'^(\d{4,})\s*[-â€“]\s*(.+)$', line)
            if header_match:
                if current:
                    records.append(self._finalize_saia_list_record(current))
                current = {
                    'id_documento_saia': header_match.group(1),
                    'header': header_match.group(2).strip(),
                    'lines': [line],
                }
                continue

            if current is None:
                current = {'id_documento_saia': '', 'header': '', 'lines': []}
            current['lines'].append(line)

        if current:
            records.append(self._finalize_saia_list_record(current))

        return [record for record in records if record.get('matched_subject')]

    def _finalize_saia_list_record(self, record):
        lines = record.get('lines', [])
        block = '\n'.join(lines)
        matched_subject = ''

        for line in lines:
            match = re.search(r'nombre\s+o\s+asunto\s*[:\|]\s*(.+)$', line, re.IGNORECASE)
            if match:
                matched_subject = self._clean_saia_subject_value(match.group(1))
                break

        if not matched_subject:
            match = re.search(
                r'nombre\s+o\s+asunto\s*[:\|]\s*(.+?)(?:\s+vence\s*[:\|]|\s+ver\s*[:\|]|$)',
                self._soft_space(block),
                re.IGNORECASE,
            )
            if match:
                matched_subject = self._clean_saia_subject_value(match.group(1))

        return {
            'id_documento_saia': record.get('id_documento_saia', ''),
            'fecha_carga_saia_text': self._extract_saia_timestamp_text(block),
            'matched_subject': matched_subject,
            'serie': record.get('header', ''),
            'evidence': self._trim_evidence(block),
        }

    def _clean_saia_subject_value(self, value):
        subject = re.split(r'\s+(?:vence|ver)\s*[:\|]', str(value or ''), maxsplit=1, flags=re.IGNORECASE)[0]
        return self._soft_space(subject)

    def _subject_value_exact(self, expected_subject, candidate_subject):
        expected = self._soft_space(expected_subject).lower()
        candidate = self._soft_space(candidate_subject).lower()
        return bool(expected) and expected == candidate

    def _scroll_saia_lists_to_top(self):
        try:
            for frame in self.page.frames:
                try:
                    frame.evaluate(
                        """() => {
                            window.scrollTo(0, 0);
                            for (const element of document.querySelectorAll('body, div, td, iframe')) {
                                if (element && element.scrollHeight > element.clientHeight) {
                                    element.scrollTop = 0;
                                }
                            }
                        }"""
                    )
                except Exception:
                    continue
        except Exception:
            return

    def _trim_evidence(self, value, limit=500):
        return self._soft_space(value)[:limit]

    def _record_timing(self, event, started_at=None, **details):
        if not hasattr(self, '_saia_timing_events') or self._saia_timing_events is None:
            self._saia_timing_events = []
        if any(item.get('event') == event for item in self._saia_timing_events):
            return
        elapsed_ms = 0
        if started_at:
            elapsed_ms = int((datetime.now() - started_at).total_seconds() * 1000)
        payload = {'event': event, 'elapsed_ms': elapsed_ms}
        payload.update({key: value for key, value in details.items() if value not in (None, '')})
        self._saia_timing_events.append(payload)

    def _subject_exact_visible(self, expected_subject, content):
        expected = self._soft_space(expected_subject)
        text = self._soft_space(content)
        if not expected:
            return False
        # No uses \s* before the generic alphanumeric boundary: SAIA cards render
        # the next label (for example "Vence:") after a newline, and that is not
        # part of the subject. Only reject real subject suffixes such as "- 1".
        pattern = rf'(?<![A-Za-z0-9]){re.escape(expected)}(?!\s*-\s*[A-Za-z0-9])(?![A-Za-z0-9])'
        return bool(re.search(pattern, text, re.IGNORECASE))

    def _soft_space(self, value):
        return re.sub(r'\s+', ' ', str(value or '')).strip()

    def _first_visible(self, selector_list, description):
        for selector in selector_list:
            locator = self.page.locator(selector)
            if locator.count() and locator.first.is_visible():
                return locator.first
        self.capture_screenshot(f'{description}_no_encontrado')
        raise SAIASelectorError(f'No se encontro {description}.')

    def _click_first_optional(self, selector_list):
        for frame in self.page.frames:
            for selector in selector_list:
                locator = frame.locator(selector)
                if locator.count() and locator.first.is_visible():
                    locator.first.click()
                    return True
        return False

    def _click_first_required(self, selector_list, description):
        if self._click_first_optional(selector_list):
            return
        self.capture_screenshot(f'{description}_no_encontrado')
        raise SAIASelectorError(f'No se encontro {description}.')

    def _looks_like_login_page(self):
        password_inputs = self.page.locator('input[type="password"]')
        return password_inputs.count() and password_inputs.first.is_visible()

    def is_browser_alive(self):
        """Returns True si el proceso Chromium sigue activo y conectado."""
        try:
            return self.browser is not None and self.browser.is_connected()
        except Exception:
            return False

    def restart_browser(self):
        """
        Cierra el browser crasheado, crea uno nuevo y hace login.
        Usar cuando is_browser_alive() retorna False.
        """
        for obj, method in ((self.context, 'close'), (self.browser, 'close')):
            if obj:
                try:
                    getattr(obj, method)()
                except Exception:
                    pass
        # Limpiar referencias antes del relanzamiento: si chromium.launch falla,
        # is_browser_alive() devuelve False de forma consistente (browser is None).
        self.browser = None
        self.context = None
        self.page = None
        self.browser = self.playwright.chromium.launch(headless=not self.headful)
        self.context = self.browser.new_context(accept_downloads=True)
        self.page = self.context.new_page()
        self.page.set_default_timeout(self.config.timeout_ms)
        self._last_route_key = None
        self.login()

    def is_session_alive(self):
        """Returns False si SAIA redirigió al login (sesión expirada)."""
        try:
            return not self._looks_like_login_page()
        except Exception:
            return False

    def relogin(self):
        """Re-autentica con SAIA tras una expiración de sesión."""
        self._last_route_key = None
        self.login()

    def keep_alive(self):
        """Navega a la base URL de SAIA para mantener la sesion activa.
        Si detecta sesion expirada hace relogin automaticamente.
        Retorna True si fue necesario relogin, False si la sesion ya estaba activa."""
        self._last_route_key = None  # keep_alive navega al home; estado de ruta invalido
        self.page.goto(self.config.base_url, wait_until='domcontentloaded', timeout=self.config.timeout_ms)
        try:
            self.page.wait_for_load_state('networkidle', timeout=5000)
        except self._timeout_error:
            pass
        if not self.is_session_alive():
            self.relogin()
            return True
        return False

    def _login_status(self):
        try:
            content = self.page.locator('body').inner_text(timeout=5000).lower()
        except self._timeout_error:
            return 'unknown'

        if any(text in content for text in selectors.LOGIN_SUCCESS_TEXTS):
            return 'success'
        if any(text in content for text in selectors.LOGIN_ERROR_TEXTS):
            return 'error'
        return 'unknown'

    def _slug(self, value):
        return ''.join(char if char.isalnum() else '_' for char in str(value).lower()).strip('_')[:80]

    def _extract_document_id(self, content, url):
        # Patrones de URL: parametros especificos; [?&]id= requiere ancla de
        # parametro para no coincidir con session_id= o user_id=.
        for pattern in (
            r'(?:id_documento|documento_id)=(\d+)',
            r'[?&]id=(\d+)',
        ):
            match = re.search(pattern, url, re.IGNORECASE)
            if match:
                return match.group(1)

        # Patrones de contenido: texto de confirmacion de SAIA.
        for pattern in (
            r'(?:id_documento|documento_id)\s*[=:]\s*(\d{4,})',
            r'\bdocumento\s*(?:numero|nro|no\.?|id|radicado)?\s*[:#-]?\s*(\d{4,})\b',
            r'^\s*(\d{4,})\s*[-–]\s*[^\n]+(?:pagos|comprobantes|electr)',
            r'\bradicado\s*(?:no\.?|numero|nro)?\s*[:#-]?\s*(\d{4,})\b',
            r'\bnumero\s*[:#]\s*(\d{4,})\b',
        ):
            match = re.search(pattern, content, re.IGNORECASE | re.MULTILINE)
            if match:
                return match.group(1)

        return ''

    def _extract_saia_timestamp_text(self, content):
        text = str(content or '')
        for pattern in (
            r'actualizado\s+(\d{1,2}/[a-z]{3}/\d{4}\s+\d{1,2}:\d{2})',
            r'\b(\d{1,2}-[a-z]{3}-\d{4})\b',
            r'fecha\s*[:#-]\s*(\d{1,2}\s+de\s+[a-záéíóúñ]+\s+del?\s+\d{4}(?:\s+\d{1,2}:\d{2})?)',
            r'fecha\s*[:#-]\s*(\d{1,2}/\d{1,2}/\d{4}(?:\s+\d{1,2}:\d{2})?)',
            r'\b(\d{1,2}:\d{2})\b',
        ):
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return re.sub(r'\s+', ' ', match.group(1)).strip()
        return ''

    def _normalize_for_match(self, value):
        text = str(value or '').upper()
        text = ''.join(
            char for char in unicodedata.normalize('NFD', text)
            if unicodedata.category(char) != 'Mn'
        )
        return re.sub(r'[^A-Z0-9]', '', text)


