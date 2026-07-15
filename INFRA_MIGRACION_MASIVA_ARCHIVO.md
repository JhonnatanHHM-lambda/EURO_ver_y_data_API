# Infraestructura requerida — módulo Migración Masiva de Archivo

Checklist para el equipo de Infraestructura/DevOps antes de poner en producción el módulo
`migracion_masiva_archivo` (automatización de cargue masivo de documentos a SAIA, con OCR,
extracción de metadata y conciliación bancaria).

Este módulo es la migración a Web del aplicativo de escritorio `Euro_gestion_documental_API`
(Django + Playwright + Tesseract, corriendo localmente en un equipo dentro de la red de
Eurosupermercados). Varias partes de su lógica **asumen implícitamente el entorno del equipo de
escritorio** (sesión de Windows, acceso directo a la red de oficina, un usuario humano al frente).
Este documento existe porque esos supuestos no se sostienen automáticamente en un servidor Web, y
si no se resuelven explícitamente, el módulo puede "funcionar" parcialmente sin que nadie note que
una función crítica quedó deshabilitada en silencio.

**Decisión de despliegue ya tomada (2026-07), actualizada tras revisar la topología real:** este
módulo corre como un servicio más (`celery_migracion`) dentro del **mismo `docker-compose.yml`** que
ya usa el resto del proyecto (`api`, `celery`, `celery_beat`, `db`, `redis`, `minio`), sobre Linux, en
el servidor de producción existente (IP pública documentada en `.env.production.example`) — **no** en
una máquina física separada dentro de la oficina como se planteó inicialmente. Esto significa que la
conectividad del punto 1 (acceso a `\\192.168.1.246`) debe resolverse como una **VPN site-to-site (o
equivalente) desde ese servidor hacia la red de Eurosupermercados**, no como "estar físicamente en la
oficina" — se corrige aquí porque una versión anterior de este documento asumía lo segundo. Las
secciones 1, 2, 8 y la nueva sección 9 reflejan esta topología real.

Cambios de código ya aplicados como consecuencia de esta decisión:
- `EURO_ver_y_data/settings.py` — nueva variable `MIGRACION_ARCHIVOS_CARPETA_SECUNDARIA_HABILITADA`
  (default `False`).
- `migracion_masiva_archivo/services/continuidad_service.py` —
  `resolver_carpeta_secundaria_automatica()` corta explícitamente y deja log INFO cuando el flag está
  en `False`, en vez de depender del `try/except` silencioso de `win32com` (ver punto 2).
- No se agregó `pywin32` a `requirements.txt` (no aplica en Linux).
- **Retención de disco (2026-07):** 3 tareas periódicas de Celery Beat nuevas en
  `migracion_masiva_archivo/tasks.py` — `purgar_screenshots_saia` (30 días, configurable con
  `SAIA_SCREENSHOT_RETENTION_DIAS`) y `purgar_uploads_antiguos` (90 días, configurable con
  `MIGRACION_ARCHIVOS_UPLOADS_RETENTION_DIAS`), sumadas a `purgar_logs_antiguos` ya existente. Ver
  detalle en el punto 6 (Playwright/almacenamiento) más abajo — probadas en vivo antes de este commit.

---

## 1. Acceso de red a las carpetas de documentos origen

- [ ] Existe una **VPN site-to-site** (o mecanismo equivalente: WireGuard, IPsec, etc.) entre el
  servidor de producción (donde corre `docker-compose.yml`, incluido el nuevo servicio
  `celery_migracion`) y la red interna de Eurosupermercados donde vive `\\192.168.1.246`. El servidor
  **no** está físicamente en la oficina — necesita esta conectividad para poder montar la carpeta.
- [ ] Sobre esa VPN, se montó la ruta de red de origen como CIFS/SMB **en el host Docker** (no dentro
  del contenedor), ej. `/mnt/gestion-documental/`.
- [ ] El montaje quedó persistente entre reinicios del host (entrada en `/etc/fstab` o unidad
  `systemd .mount`, no un `mount` manual que se pierde al reiniciar).
- [ ] El punto de montaje del host (`/mnt/gestion-documental`) está expuesto al contenedor
  `celery_migracion` vía bind mount en `docker-compose.yml` (ya agregado:
  `- /mnt/gestion-documental:/mnt/gestion-documental`) — confirmar que el path coincide exactamente
  con el que se monta en el host real.
- [ ] Se probó manualmente, **desde dentro del contenedor** (`docker compose exec celery_migracion
  ls /mnt/gestion-documental`), que se pueden listar y leer archivos — montar en el host no garantiza
  que el bind mount hacia el contenedor esté bien configurado.
- [ ] `carpeta_origen` en las cargas nuevas usa la ruta tal como la ve el contenedor (ej.
  `/mnt/gestion-documental/PEL 2019`), **no** la sintaxis UNC de Windows
  (`\\192.168.1.246\...`) — el código no traduce una sintaxis a la otra.

**Cómo montar (ejemplo Debian/Ubuntu):**
```bash
sudo apt install cifs-utils
sudo mkdir -p /mnt/gestion-documental
# credenciales en un archivo con permisos 600, no en fstab en texto plano
sudo tee /etc/samba/credentials-gestion-documental <<'EOF'
username=usuario_red
password=clave_red
EOF
sudo chmod 600 /etc/samba/credentials-gestion-documental
echo '//192.168.1.246/GestionDocumental /mnt/gestion-documental cifs credentials=/etc/samba/credentials-gestion-documental,uid=<usuario-worker>,iocharset=utf8,vers=3.0 0 0' | sudo tee -a /etc/fstab
sudo mount -a
```

**Por qué:** `LoteDocumental.carpeta_origen` (`migracion_masiva_archivo/models.py:56`) es un
`CharField` de texto libre con una ruta de carpeta — no un upload real vía HTTP. `lote_service.py`
(`crear_lote_desde_carpeta`) simplemente hace `scan_folder_with_context(carpeta_origen)` sobre esa
ruta, usando las llamadas estándar del sistema de archivos de Python (`Path`/`os`) — no sabe nada de
SMB ni de Windows. Por eso, para que el código funcione sin cambios, el punto de montaje debe
aparecer ante Python como una carpeta local normal: eso es exactamente lo que logra el montaje CIFS.

---

## 2. "Carpeta secundaria" (recuperación de PEL faltantes) — decidida: deshabilitada en este despliegue

- [x] Decisión tomada: **deshabilitada** en producción (servidor Linux). No requiere acción de
  infraestructura — el código ya la desactiva por configuración.
- [ ] `MIGRACION_ARCHIVOS_CARPETA_SECUNDARIA_HABILITADA` está en `False` (o ausente) en el `.env` de
  producción — confirmar que nadie lo puso en `True` "para probar" y lo dejó así.
- [ ] Se documentó en el manual de operación / en el frontend que esta función está deshabilitada,
  para que un analista no asuma que el sistema buscará automáticamente PEL faltantes en el servidor
  secundario (192.168.1.245) — hoy, si un PEL falta en la carpeta principal, quedará marcado como
  faltante sin intento de recuperación automática.

**Por qué queda deshabilitada:** `services/continuidad_service.py` (`_find_245_base_path`, líneas
~587-616) busca un acceso directo `.lnk` en `%USERPROFILE%\Desktop` o `\Escritorio` de **Windows**,
cuyo nombre contenga `192.168.1.245`, y resuelve su destino real con
`win32com.client.Dispatch('WScript.Shell')` (`_resolve_lnk_target`, línea 619). Esto no es portable a
Linux bajo ninguna configuración: no hay escritorio de Windows, no hay `.lnk`, y `win32com.client` no
existe como concepto fuera de Windows. Con el servidor decidido en Linux, esta función no puede
existir — no es un bug a corregir, es una limitación de plataforma.

**Ya no degrada en silencio:** antes de este cambio, la ausencia de `win32com`/del `.lnk` se absorbía
en un `try/except Exception: pass`, y el único rastro era el estado `CARPETA_SECUNDARIA_NO_ACCESIBLE`
en los reportes de continuidad — indistinguible de un problema de configuración real. Ahora
`resolver_carpeta_secundaria_automatica()` verifica primero
`settings.MIGRACION_ARCHIVOS_CARPETA_SECUNDARIA_HABILITADA` y, si está apagado (el default), corta de
inmediato dejando un log `INFO` explícito ("Carpeta secundaria deshabilitada por configuracion") —
es una decisión visible en los logs, no un fallo silencioso.

Si en el futuro se decide que esta función sí hace falta en producción, la opción recomendada **no**
es mover el worker a Windows solo por esto: es reemplazar la búsqueda por acceso directo de escritorio
por una segunda ruta de red configurable explícitamente (una variable de entorno tipo
`MIGRACION_ARCHIVOS_CARPETA_SECUNDARIA_PATH`, montada igual que el punto 1), sin depender de un
usuario humano de Windows con un `.lnk` en su escritorio.

---

## 3. Robustez del scraping SAIA — SAIA no tiene API limpia

- [ ] Se definió un canal de alerta (email/Slack/Teams) para cuando la tasa de resultados
  "ambiguos" o "no reconocidos" supere un umbral.
- [ ] Se acordó con el equipo funcional un umbral razonable (ej. "más de 3 documentos ambiguos en
  una misma ejecución" o "más del 10% de una carga en un ciclo").
- [ ] Se documentó el procedimiento manual a seguir cuando la alerta se dispare (quién revisa,
  dónde: ver `LogProcesoDocumental` y las capturas de pantalla, campo 4 más abajo).

**Por qué:** `services/saia/browser_client.py` no tiene ninguna API de SAIA que confirme éxito/error
de forma estructurada — determina el resultado de una carga **comparando el texto de la respuesta
HTML** contra listas de cadenas conocidas (`selectors.SUCCESS_TEXTS_STRONG`, `ERROR_TEXTS_STRONG`,
`SUCCESS_TEXTS`, `ERROR_TEXTS`, líneas ~353-388), y cuando ninguna combinación es concluyente, marca
el resultado como `ambiguous` (línea 388) para que un analista lo revise manualmente. **Este
mecanismo es inherentemente frágil ante cualquier cambio futuro en la interfaz de SAIA** (aunque sea
un cambio de texto menor, no funcional) — el código no tiene forma de detectar por sí mismo que
"algo cambió", solo puede fallar en silencio clasificando todo como ambiguo o, peor, como error/éxito
incorrecto si el nuevo texto coincide por casualidad con un patrón existente.

**Monitoreo mínimo recomendado:**
- Alertar si la proporción de `ambiguous=True` (`IntentoCargaSAIA` con resultado ambiguo, o el
  estado `REQUIERE_REVISION` originado en Fase 5) sube de forma anormal en un periodo corto —
  indicaría que SAIA cambió y el detector de texto dejó de reconocer patrones.
  Existe evidencia previa de este riesgo materializándose: `diagnostico_endpoint_saia.txt` y
  `qa_saia.py` en el proyecto local documentan una quirk específica de SAIA (login redirige a un
  expediente previo) que ya rompió la navegación una vez y requirió un `preflight_navigation()`
  explícito (ya portado en el código Web, `browser_client.py`).
- Las capturas de pantalla (`SAIA_SCREENSHOT_DIR`, ver punto 5) son la única evidencia visual de qué
  pasó realmente en un intento ambiguo — deben conservarse accesibles para quien investigue la alerta,
  no solo loguearse y perderse.

---

## 4. Clasificación de rutas SAIA — mantenimiento manual, no descubrimiento dinámico

- [ ] El equipo de infra/soporte sabe que **agregar un tipo de documento o ruta SAIA nueva requiere
  un cambio de código**, no una configuración en base de datos ni en el admin.
- [ ] Existe un canal claro (ticket/issue) para que el área funcional (Eurosupermercados) reporte
  cuándo SAIA agregue una ruta/expediente nuevo, para que se priorice como tarea de desarrollo.

**Por qué:** `services/saia/selectors.py` define `SAIA_ROUTE_CONFIG` (línea 984) con **33 rutas
hardcodeadas** por tipo de documento/banco (PEL, PRO, RCG, RCI, RCP, INC, IND, NIC, PP1-3, ECB, EGC,
EGE, PEC, RICA, BANCOLOMBIA, IC1-IC6, RCC, CCA, CCV, CORBANCA, COLPATRIA, CORREVAL, CORFICOLOMBIANA,
BBVA, DAVIVIENDA, BOGOTA), cada una con su propio árbol de navegación (`navigation_steps`) y, para
las rutas bancarias, su propia lógica de resolución de año/mes/subexpediente en
`services/saia/routes.py`. No hay ningún mecanismo de descubrimiento automático de la estructura de
carpetas de SAIA — si Eurosupermercados abre un expediente nuevo en SAIA para un tipo de documento
que no está en esta lista, el sistema **no sabrá navegar hacia él** y el documento quedará bloqueado
en validación (Fase 4) hasta que se agregue el árbol de navegación correspondiente en el código.

---

## 5. Tesseract OCR

- [x] Ya resuelto en código (2026-07): `Dockerfile.celery-migracion` instala
  `tesseract-ocr tesseract-ocr-spa tesseract-ocr-eng` vía `apt-get` — no requiere ningún paso manual
  en el host, se reconstruye automáticamente con `docker compose build`.
- [ ] Se verificó, dentro del contenedor ya construido, que `TESSERACT_CMD`/`TESSDATA_DIR` en
  `.env.production.example` (`/usr/bin/tesseract`, `/usr/share/tesseract-ocr/5/tessdata`) coinciden
  con la versión real de Tesseract que instaló Debian bookworm (`docker compose exec celery_migracion
  dpkg -L tesseract-ocr-spa` — la ruta cambia entre versiones mayores de Tesseract).

**Hallazgo concreto en el `.env` actual del repo (entorno de desarrollo):**
`TESSDATA_DIR` apunta hoy a `C:\Users\EQUIPO\Euro_gestion_documental_API\recursos\tessdata` — es
decir, **al directorio del otro proyecto** (el aplicativo de escritorio) en la máquina de un
desarrollador. Esto funciona por casualidad en ese equipo porque ambos proyectos coexisten ahí, pero
**no debe copiarse tal cual a ningún `.env` de producción** — `.env.example` ya se actualizó con
valores de ejemplo apropiados para Linux (`/usr/bin/tesseract`,
`/usr/share/tesseract-ocr/5/tessdata`); confirmar la ruta exacta con `dpkg -L` en el servidor real
antes de copiarla al `.env` de producción.

---

## 6. Playwright

- [x] Ya resuelto en código (2026-07): `Dockerfile.celery-migracion` ejecuta
  `playwright install --with-deps chromium` durante el build — instala el binario y las librerías de
  sistema en un solo paso, dentro de la imagen. No requiere ejecutarse manualmente en el host.
- [ ] Se confirmó que el proceso corre en modo headless en producción (ya es el comportamiento por
  defecto del código: `browser_client.py` llama `chromium.launch(headless=not self.headful)`, y
  `headful` nunca se activa desde el flujo de producción vía API/Celery — solo desde herramientas de
  diagnóstico manuales).
- [ ] Se definió dónde vive `SAIA_SCREENSHOT_DIR` en el servidor y que ese disco es **persistente**
  (no un volumen efímero de contenedor) — son la evidencia de auditoría de cada intento de carga.

**Retención ya resuelta en código (2026-07):** `migracion_masiva_archivo.tasks.purgar_screenshots_saia`
(Celery Beat, 3:10 AM diario) elimina capturas con más de `SAIA_SCREENSHOT_RETENTION_DIAS` días
(default 30) usando la fecha de modificación del archivo. De igual forma,
`migracion_masiva_archivo.tasks.purgar_uploads_antiguos` (3:20 AM) elimina las carpetas de archivos
subidos vía API (`MIGRACION_ARCHIVOS_MEDIA_ROOT/uploads/<uuid>`) para lotes en estado terminal
(`FINALIZADO`/`FINALIZADO_CON_ERRORES`/`CANCELADO`) con más de `MIGRACION_ARCHIVOS_UPLOADS_RETENTION_DIAS`
días (default 90) — con un guard explícito que **nunca** toca `carpeta_origen` fuera de esa carpeta de
uploads, para no arriesgar el repositorio de red de la oficina. Ambas tareas ya están probadas
funcionalmente (ver commits de este módulo). Sigue pendiente de Infra: confirmar que el disco donde
vive `SAIA_SCREENSHOT_DIR`/`MEDIA_ROOT` es persistente y que Celery Beat corre en producción (punto 7).

---

## 7. Celery — cola nueva

- [x] Ya resuelto para el despliegue Docker (2026-07): el servicio `celery_migracion` en
  `docker-compose.yml` corre dedicado a `-Q migracion_masiva_archivo`, separado de `celery`
  (`contratos,default`) — no hay que tocar el comando del worker existente.
- [ ] `celery_beat` (ya existe en `docker-compose.yml`, compartido por todo el proyecto) está
  corriendo y fue reiniciado tras este despliegue (ver punto 9 — usa `DatabaseScheduler`).

**Nota que sigue vigente para cualquiera que corra el proyecto fuera de Docker** (ej. desarrollo local
en Windows, per `CLAUDE.md`): el comando manual documentado ahí
(`--queues=celery,optimizacion_correos,contratos,migracion_masiva_archivo`) sigue siendo la referencia
para ese escenario — ya fue actualizado para incluir la cola nueva. En producción vía Docker, en
cambio, cada cola vive en su propio servicio/contenedor (`celery` y `celery_migracion`), no en un único
comando con `--queues`.

---

## 8. Sistema operativo del servidor de worker — decidido: Linux, mismo servidor que el resto del stack

- [x] Decisión tomada: el worker de Celery de este módulo (`celery_migracion` en `docker-compose.yml`)
  corre en **Linux**, en el **mismo servidor** donde ya corren `api`/`celery`/`celery_beat`/`db`/`redis`
  — no en una máquina separada dentro de la oficina.
- [ ] `pywin32` **no** se agrega a `requirements.txt` (no aplica en Linux — confirmar que nadie lo
  agregue "por si acaso").
- [ ] El equipo funcional fue informado de que la función de "carpeta secundaria" (punto 2) no está
  disponible en este despliegue.
- [ ] En `docker-compose.yml`, `celery_migracion` corre con `--concurrency=1` (no `--pool=solo`, que
  es sintaxis específica de Windows) — el motivo es el mismo: `execution_control.py` es un singleton
  en memoria de proceso, un solo worker/proceso a la vez (ver punto 9).

Como el servidor **no** está dentro de la red de oficina (ver corrección al inicio de este documento),
el punto 1 (acceso a las carpetas de red) requiere una VPN site-to-site, no un montaje CIFS "local"
simple como se planteó en una versión anterior de este documento.

---

## 9. Supervisión de procesos — Docker Compose

- [x] Ya resuelto en código/configuración (2026-07): se agregó el servicio `celery_migracion` a
  `docker-compose.yml`, con `restart: unless-stopped` (igual que el resto de servicios del proyecto)
  y un `Dockerfile.celery-migracion` dedicado (Playwright + Tesseract + paquetes de idioma).
- [ ] Se construyó y desplegó la imagen (`docker compose build celery_migracion` /
  `docker compose up -d celery_migracion`) en el servidor real.
- [ ] Se creó en el host el punto de montaje `/mnt/gestion-documental` (VPN + CIFS, punto 1) **antes**
  de levantar `celery_migracion` — si el bind mount apunta a un directorio vacío porque el CIFS no
  está montado en el host, el contenedor arranca igual pero no vera ningún archivo.
- [ ] Se confirmó que `celery_beat` se reinició después de este despliegue. **Importante:**
  `celery_beat` corre con `--scheduler django_celery_beat.schedulers:DatabaseScheduler`, que lee el
  cronograma desde la base de datos (`django_celery_beat_periodictask`), no directamente de
  `CELERY_BEAT_SCHEDULE` en `settings.py` en cada tick. Los nuevos schedules
  (`purgar_screenshots_saia`, `purgar_uploads_antiguos`) solo se insertan en esa tabla la primera vez
  que el proceso de Beat arranca después de que el código con esos nombres nuevos ya está desplegado
  — si `celery_beat` no se reinicia tras este deploy, esas dos tareas nunca correrán aunque el código
  ya esté en producción.

**Hallazgo relacionado, fuera del alcance de este cambio (no se modificó):** `docker-compose.yml`
tenía ya, antes de este cambio, el mismo problema para otro módulo: el servicio `celery` existente
solo escucha `-Q contratos,default` — **no** consume la cola `optimizacion_correos`. Además existe un
`Dockerfile.celery-oc` en la raíz del repo (con Playwright ya instalado) que **no está referenciado
en ningún lado de `docker-compose.yml`** — parece un intento previo de resolver esto para
`OptimizacionCorreos` que quedó a medias. No lo toqué porque es un módulo distinto al de esta
conversación, pero probablemente `OptimizacionCorreos` tiene hoy el mismo problema que tenía
`migracion_masiva_archivo` antes de este cambio: sus tareas se encolan pero nadie las consume en este
despliegue Docker.

**Volúmenes agregados** (`docker-compose.yml`):
- `migracion_media_data` → montado en `api` y `celery_migracion`, en
  `/app/media/migracion_masiva_archivo` — compartido porque `api` recibe los archivos subidos
  (`views._guardar_archivos_temporales`) y `celery_migracion` los lee para procesarlos.
- `migracion_saia_screenshots` → montado solo en `celery_migracion`, en `/app/saia_screenshots`
  (`SAIA_SCREENSHOT_DIR`) — nadie más los necesita.
- Bind mount `/mnt/gestion-documental` (host) → mismo path dentro de `celery_migracion` — no es un
  volumen nombrado de Docker porque el contenido real vive fuera de Docker (en la red de oficina, vía
  VPN + CIFS).

---

## Resumen ejecutivo para quien apruebe el despliegue

**Decisiones tomadas:** worker en Linux, como servicio `celery_migracion` dentro del mismo
`docker-compose.yml` que el resto del proyecto — **no** una máquina física en la oficina (corregido,
ver aviso al inicio de este documento). Carpeta secundaria deshabilitada por diseño (punto 2).

**Ya resuelto en código/configuración, listo para construir y desplegar (puntos 5, 6, 7, 9):**
Tesseract, Playwright, la cola de Celery dedicada y la retención de disco (logs + screenshots +
uploads) ya están resueltos en `Dockerfile.celery-migracion`, `docker-compose.yml` y
`migracion_masiva_archivo/tasks.py`. No requieren pasos manuales adicionales de Infra más allá de
construir y levantar el servicio.

**Pendiente de ejecutar por Infra/DevOps (bloqueante — sin esto el módulo no procesa nada):**
- Punto 1: levantar la VPN site-to-site hacia la red de Eurosupermercados y montar el CIFS **en el
  host** (no dentro del contenedor).
- Punto 9: `docker compose build celery_migracion && docker compose up -d celery_migracion`, y
  **reiniciar `celery_beat`** para que registre las 2 tareas de retención nuevas.
- Confirmar credenciales SAIA reales en el `.env` de producción (`.env.production.example` ya tiene
  las variables documentadas, solo faltan los valores reales).

**No bloqueante pero requiere seguimiento activo (el sistema degrada en silencio si se ignora):**
- Punto 3: definir el canal y umbral de alerta para resultados "ambiguos" de SAIA.
- Punto 4: tener un canal claro para que Eurosupermercados avise de rutas SAIA nuevas.

**Hallazgo relacionado, no corregido (otro módulo):** `OptimizacionCorreos` probablemente tiene hoy
el mismo problema que tenía este módulo antes de este cambio — su cola no la consume ningún servicio
de `docker-compose.yml`, y existe un `Dockerfile.celery-oc` húerfano que sugiere que alguien empezó a
resolverlo y no terminó. Ver punto 9.

**Nota menor:** `MIGRACION_ARCHIVOS_TEMP_ROOT` está definido en `settings.py`/`.env.example` pero
ningún código lo usa todavía. Es una variable reservada, no un requisito activo hoy.

**Hallazgos de seguridad generales del proyecto (no específicos de este módulo), corregidos de paso:**
- `ALLOWED_HOSTS` ya no es `['*']` en producción — ahora se lee de la variable `ALLOWED_HOSTS`
  (default: solo `localhost`/`127.0.0.1`, para no romper el healthcheck de Docker).
- Se agregó `SECURE_SSL_ENABLED` (default `False`, sin cambio de comportamiento hoy) para activar
  `SECURE_SSL_REDIRECT`/`SESSION_COOKIE_SECURE`/`CSRF_COOKIE_SECURE` de un solo interruptor, y
  `SECURE_HSTS_SECONDS` (default `0`) por separado. **No se activaron** porque al revisar `nginx/*.conf`
  encontramos que el repo tiene configs contradictorias: `ip.conf`/`euro.conf` sirven la API por HTTP
  plano sin certificado, mientras que `euro-dev.conf` sí tiene HTTPS real vía certbot, y `api.conf`/
  `storage.conf` dependen de que alguien ya haya corrido `certbot` en el servidor. No se pudo confirmar
  desde el repo cuál está activa hoy — **antes de poner `SECURE_SSL_ENABLED=True` en producción, verificar
  en el servidor real (`nginx -T` o revisar `/etc/nginx/sites-enabled/`) que el tráfico llega
  exclusivamente por HTTPS**, o el sitio quedará en bucle de redirect / sin poder loguearse.
