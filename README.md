# Euro VER & DATA — API Backend

> Plataforma de trazabilidad, verificación y gestión de candidatos y empleados para **Euro Supermercados**. Desarrollada por **Lambda Analytics**.

---

## Tabla de contenido

1. [Descripción del proyecto](#1-descripción-del-proyecto)
2. [Stack tecnológico](#2-stack-tecnológico)
3. [Requisitos previos](#3-requisitos-previos)
4. [Instalación y configuración local](#4-instalación-y-configuración-local)
5. [Variables de entorno](#5-variables-de-entorno)
6. [Estructura de carpetas](#6-estructura-de-carpetas)
7. [Scripts disponibles](#7-scripts-disponibles)
8. [API / Endpoints](#8-api--endpoints)
9. [Flujo de datos](#9-flujo-de-datos)
10. [Convenciones de código](#10-convenciones-de-código)
11. [Testing](#11-testing)
12. [Despliegue](#12-despliegue)
13. [Troubleshooting / FAQ](#13-troubleshooting--faq)
14. [Contacto del equipo](#14-contacto-del-equipo)
15. [Changelog](#15-changelog)
16. [Licencia](#16-licencia)

---

## 1. Descripción del proyecto

**Euro VER & DATA** es una plataforma web de trazabilidad end-to-end para el área de Gestión Humana de Euro Supermercados. Permite:

- **Carga masiva** de archivos Excel con datos de candidatos y empleados desde múltiples fuentes (Ingresos, Entrevistas, Time Jobs, etc.).
- **Trazabilidad unificada** de cada persona a lo largo de su ciclo de vida laboral (candidato → seleccionado → empleado → retirado).
- **Verificación y auditoría** con historial de cambios, justificaciones y firma digital de actas de carga.
- **Gestión administrativa** de usuarios, roles, permisos, sedes y orígenes de datos.
- **Notificaciones** en tiempo real para administradores (recuperación de contraseñas, alertas).

Este repositorio contiene el **backend** (API REST) construido con Django REST Framework. El frontend está en el repositorio [`EURO_ver_y_data_UI`](https://github.com/JhonnatanHHM-lambda/EURO_ver_y_data_UI).

---

## 2. Stack tecnológico

| Capa | Tecnología | Versión |
|------|-----------|---------|
| Framework web | Django | 5.0 |
| API REST | Django REST Framework | 3.16.1 |
| Autenticación | SimpleJWT | 5.5.1 |
| Base de datos | PostgreSQL | 14+ |
| ORM | Django ORM + psycopg2-binary | 2.9.12 |
| Cola de tareas | Celery | 5.5.3 |
| Broker/Backend | Redis | 7+ |
| Scheduler | django-celery-beat | 2.8.1 |
| Email | Gmail SMTP (django.core.mail) | — |
| Generación PDF | ReportLab + Pillow | — |
| Generación Word | python-docx (implícito) | — |
| Documentación API | drf-yasg (Swagger/ReDoc) | 1.21.11 |
| Servidor prod | Gunicorn + WhiteNoise | 23.0 / 6.11 |
| CORS | django-cors-headers | 4.9.0 |

---

## 3. Requisitos previos

Antes de instalar, asegúrate de tener:

| Requisito | Versión mínima | Notas |
|-----------|---------------|-------|
| Python | 3.11+ | Usar `python --version` para verificar |
| pip | 23+ | Incluido con Python |
| PostgreSQL | 14+ | Debe estar corriendo en puerto 5432 |
| Redis | 7+ | Debe estar corriendo en puerto 6379 |
| Git | 2.40+ | Para clonar el repositorio |

> **Nota sobre Redis en Windows:** La forma más sencilla es usar [Redis para Windows](https://github.com/microsoftarchive/redis/releases) o correrlo mediante **WSL2** (`wsl redis-server`).

---

## 4. Instalación y configuración local

```bash
# 1. Clonar el repositorio
git clone https://github.com/JhonnatanHHM-lambda/EURO_ver_y_data_API.git
cd EURO_ver_y_data_API

# 2. Crear y activar entorno virtual
python -m venv venv

# Windows
venv\Scripts\activate
# Linux/Mac
source venv/bin/activate

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Configurar variables de entorno
cp .env.example .env
# Editar .env con tus credenciales reales (ver sección 5)

# 5. Crear la base de datos en PostgreSQL
# Conéctate a psql y ejecuta:
#   CREATE DATABASE ver_y_data;

# 6. Aplicar migraciones
python manage.py migrate

# 7. Cargar datos iniciales (sedes y orígenes)
python manage.py seed_sedes

# 8. Crear superusuario
python manage.py createsuperuser

# 9. Levantar el servidor de desarrollo
python manage.py runserver

# 10. (Opcional) Levantar worker de Celery para tareas asíncronas (emails, etc.)
python -m celery -A EURO_ver_y_data worker --loglevel=info --pool=solo
```

La API estará disponible en `http://127.0.0.1:8000/api/`  
Swagger interactivo: `http://127.0.0.1:8000/swagger/`  
Panel admin Django: `http://127.0.0.1:8000/admin/`

---

## 5. Variables de entorno

Copia `.env.example` a `.env` y completa cada variable:

| Variable | Descripción | Default | Obligatoria |
|----------|-------------|---------|-------------|
| `DJANGO_SETTINGS_MODULE` | Módulo de settings | `EURO_ver_y_data.settings` | Sí |
| `DEBUG` | Modo debug | `True` | Sí |
| `SECRET_KEY` | Clave secreta Django | *(ver .env.example)* | Sí |
| `DB_NAME` | Nombre de la base de datos | `ver_y_data` | Sí |
| `DB_USER` | Usuario PostgreSQL | `postgres` | Sí |
| `DB_PASSWORD` | Contraseña PostgreSQL | — | Sí |
| `DB_HOST` | Host PostgreSQL | `localhost` | Sí |
| `DB_PORT` | Puerto PostgreSQL | `5432` | No |
| `ACCESS_TOKEN_LIFETIME` | Duración token JWT (minutos) | `60` | No |
| `REFRESH_TOKEN_LIFETIME` | Duración refresh token (días) | `1` | No |
| `EMAIL_USER` | Correo Gmail remitente | — | Sí (para OTP/notifs) |
| `EMAIL_PASS` | App Password de Gmail | — | Sí (para OTP/notifs) |
| `CELERY_BROKER_URL` | URL broker Redis | `redis://localhost:6379/0` | Sí (para Celery) |
| `CELERY_RESULT_BACKEND` | URL backend Redis | `redis://localhost:6379/1` | Sí (para Celery) |
| `CORS_ALLOWED_ORIGINS` | Orígenes CORS permitidos (separados por coma) | `http://localhost:5173` | Sí |

> **App Password de Gmail:** No uses tu contraseña normal. Ve a [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords), activa verificación 2 pasos y genera una App Password.

---

## 6. Estructura de carpetas

```
EURO_ver_y_data_API/
│
├── manage.py                          # CLI de gestión Django
├── requirements.txt                   # Dependencias Python
├── .env.example                       # Plantilla de variables de entorno
│
├── EURO_ver_y_data/                   # Paquete principal (configuración)
│   ├── settings.py                    # Configuración global (DB, JWT, Celery, etc.)
│   ├── urls.py                        # Rutas principales del proyecto
│   ├── celery.py                      # Configuración de Celery
│   ├── wsgi.py                        # Entrada para servidores WSGI (Gunicorn)
│   ├── asgi.py                        # Entrada para servidores ASGI
│   └── decoradores.py                 # Decoradores personalizados de permisos
│
├── Base/                              # App base
│   └── models.py                      # BaseModel abstracto (creado, actualizado, etc.)
│
├── Usuarios/                          # App de usuarios y autenticación
│   ├── models.py                      # Usuario, OTP, SolicitudRecuperacion, Notificacion
│   ├── serializers.py                 # Serializers DRF
│   ├── urls.py                        # Rutas: auth/*, usuarios/*, roles/*
│   └── views/
│       ├── auth_views.py              # Login, OTP, JWT refresh, logout, recuperación
│       ├── usuarios_views.py          # CRUD de usuarios
│       └── grupos_views.py            # Gestión de roles y permisos
│
├── Notificaciones/                    # App de notificaciones
│   ├── tasks.py                       # Tareas Celery: envío de emails OTP y alertas
│   └── templates/emails/
│       └── otp_email.html             # Template HTML del email de OTP
│
├── Trazabilidad/                      # App principal — gestión de trazabilidad
│   ├── models.py                      # Origen, Sede, EmpleadoTrazabilidad,
│   │                                  # HistorialCambioRegistro, CargaExcel
│   ├── serializers.py                 # Serializers para listados y detalle
│   ├── urls.py                        # Rutas: trazabilidad/*, admin/*
│   ├── mapeo_columnas.py              # Mapeo Excel → campos del modelo
│   ├── validacion_columnas.py         # Reglas de validación de columnas
│   ├── variantes_sede.py              # Normalización de nombres de sede
│   ├── management/commands/
│   │   └── seed_sedes.py              # Comando: python manage.py seed_sedes
│   ├── utils/
│   │   ├── acta_brand.py              # Constantes de branding (logos, colores)
│   │   ├── acta_pdf.py                # Generación de actas en PDF (ReportLab)
│   │   └── acta_word.py               # Generación de actas en Word
│   └── views/
│       ├── carga_views.py             # Carga y validación de archivos Excel
│       ├── empleados_views.py         # Listado y detalle de candidatos/empleados
│       ├── historial_views.py         # Historial de cargas y logs
│       ├── edicion_views.py           # Edición, auditoría y eliminación de registros
│       ├── acta_views.py              # Generación y firma de actas
│       ├── sedes_views.py             # APIs de sedes
│       ├── administracion_views.py    # CRUD de sedes y orígenes (admin)
│       └── resolver_sedes.py          # Utilidad: resolución de sede por texto
│
└── recursos/                          # Recursos estáticos (fonts, imágenes)
    └── fonts/                         # Fuentes para generación de PDFs
```

---

## 7. Scripts disponibles

| Comando | Descripción |
|---------|-------------|
| `python manage.py runserver` | Inicia servidor de desarrollo en `http://127.0.0.1:8000` |
| `python manage.py migrate` | Aplica todas las migraciones pendientes |
| `python manage.py makemigrations` | Genera migraciones a partir de cambios en modelos |
| `python manage.py createsuperuser` | Crea un usuario administrador interactivamente |
| `python manage.py seed_sedes` | Carga las sedes y orígenes de datos iniciales de Euro Supermercados |
| `python manage.py collectstatic` | Recolecta archivos estáticos para producción |
| `python -m celery -A EURO_ver_y_data worker --loglevel=info --pool=solo` | Inicia worker Celery (Windows: `--pool=solo` obligatorio) |
| `python -m celery -A EURO_ver_y_data beat --loglevel=info` | Inicia scheduler Celery para tareas periódicas |
| `python manage.py shell` | Abre shell interactivo Django |

---

## 8. API / Endpoints

**Base URL:** `http://127.0.0.1:8000/api/`  
**Autenticación:** `Authorization: Bearer <access_token>` en todos los endpoints protegidos.

### Autenticación

| Método | Ruta | Descripción | Auth |
|--------|------|-------------|------|
| `POST` | `auth/login/` | Envía OTP al correo del usuario | No |
| `POST` | `auth/verificar-otp/` | Verifica OTP y retorna access + refresh tokens | No |
| `POST` | `auth/refresh/` | Renueva el access token con refresh token | No |
| `POST` | `auth/logout/` | Invalida el refresh token | Sí |
| `GET` | `auth/me/` | Retorna datos del usuario en sesión | Sí |
| `POST` | `auth/recuperar-password/` | Solicita recuperación de contraseña | No |
| `POST` | `auth/recuperar-password/confirmar/` | Confirma nueva contraseña con token | No |

### Usuarios y Roles

| Método | Ruta | Descripción | Permiso |
|--------|------|-------------|---------|
| `GET` | `usuarios/` | Lista todos los usuarios | `can_manage_users` |
| `POST` | `usuarios/` | Crea nuevo usuario | `can_manage_users` |
| `PUT` | `usuarios/<id>/` | Actualiza usuario | `can_manage_users` |
| `DELETE` | `usuarios/<id>/` | Elimina usuario | `can_manage_users` |
| `GET` | `roles/` | Lista roles con permisos | `can_manage_roles` |
| `POST` | `roles/` | Crea rol | `can_manage_roles` |
| `PUT` | `roles/<id>/` | Actualiza rol | `can_manage_roles` |
| `DELETE` | `roles/<id>/` | Elimina rol | `can_manage_roles` |
| `GET` | `permisos/` | Lista todos los permisos disponibles | `can_manage_roles` |

### Trazabilidad — Cargas

| Método | Ruta | Descripción | Permiso |
|--------|------|-------------|---------|
| `POST` | `trazabilidad/preview/` | Previsualiza Excel antes de cargar | `can_upload_excel` |
| `POST` | `trazabilidad/cargar/` | Procesa y guarda registros del Excel | `can_upload_excel` |
| `GET` | `trazabilidad/historial/` | Lista historial de cargas con filtros | `can_manage_cargas` |
| `POST` | `trazabilidad/cargas/<id>/revertir/` | Revierte una carga (elimina registros) | `can_manage_cargas` |
| `POST` | `trazabilidad/cargas/<id>/firmar/` | Firma el acta digital de una carga | `can_manage_cargas` |
| `GET` | `trazabilidad/cargas/<id>/acta/pdf/` | Descarga acta en PDF | `can_manage_cargas` |
| `GET` | `trazabilidad/cargas/<id>/acta/word/` | Descarga acta en Word | `can_manage_cargas` |

### Trazabilidad — Empleados y Registros

| Método | Ruta | Descripción | Permiso |
|--------|------|-------------|---------|
| `GET` | `trazabilidad/empleados/` | Lista empleados/candidatos (paginado, filtros) | `can_view_trazabilidad` |
| `GET` | `trazabilidad/empleados/<doc>/detalle/` | Detalle completo de una persona por documento | `can_view_trazabilidad` |
| `GET` | `trazabilidad/kpis/` | KPIs globales (total, activos, retirados, inhabilitados) | `can_view_trazabilidad` |
| `POST` | `trazabilidad/registros/crear/` | Crea registro manual individual | `can_edit_registros` |
| `PUT` | `trazabilidad/registros/<id>/editar/` | Edita un registro (con auditoría) | `can_edit_registros` |
| `DELETE` | `trazabilidad/registros/<id>/eliminar/` | Elimina registro (bloqueado si tiene relaciones) | `can_edit_registros` |
| `GET` | `trazabilidad/registros/<id>/historial/` | Historial de auditoría de un registro | `can_view_trazabilidad` |
| `GET` | `trazabilidad/admin/registros/` | Lista TODOS los registros individuales (admin) | `can_edit_registros` |

### Administración

| Método | Ruta | Descripción | Permiso |
|--------|------|-------------|---------|
| `GET/POST` | `admin/sedes/` | Lista y crea sedes | `can_manage_sedes` |
| `PUT/DELETE` | `admin/sedes/<id>/` | Actualiza/elimina sede | `can_manage_sedes` |
| `GET/POST` | `admin/origenes/` | Lista y crea orígenes de datos | `can_manage_sedes` |
| `PUT/DELETE` | `admin/origenes/<id>/` | Actualiza/elimina origen | `can_manage_sedes` |
| `GET` | `admin/notificaciones/` | Notificaciones del admin | `can_manage_users` |
| `PUT` | `admin/notificaciones/<id>/` | Marca notificación como leída | `can_manage_users` |
| `POST` | `admin/recuperaciones/<id>/resolver/` | Admin resuelve ticket de recuperación | `can_manage_users` |
| `GET` | `sedes/` | Lista sedes (público autenticado) | Autenticado |

> **Documentación interactiva completa:** Accede a `http://127.0.0.1:8000/swagger/` con el servidor corriendo.

---

## 9. Flujo de datos

```
Excel (.xlsx)
    │
    ▼
POST /api/trazabilidad/preview/          ← Valida columnas, detecta errores, retorna preview
    │
    ▼ (aprobado por GH)
POST /api/trazabilidad/cargar/           ← Procesa, mapea columnas, infiere proceso/estado,
    │                                       detecta duplicados, guarda EmpleadoTrazabilidad[]
    │                                       + CargaExcel (metadata + errores JSON)
    ▼
GET  /api/trazabilidad/empleados/        ← Frontend: tabla paginada con filtros
GET  /api/trazabilidad/empleados/<doc>/  ← Frontend: drawer de detalle (todas las casillas)
    │
    ▼ (edición)
PUT  /api/trazabilidad/registros/<id>/editar/
    │  ├── Campos clasificación (estado/proceso): requiere justificación → crea HistorialCambio
    │  └── Campos de datos (nombre, cédula, etc.): sin justificación, propaga a todos los
    │      registros del mismo documento
    ▼
GET  /api/trazabilidad/registros/<id>/historial/  ← Auditoría completa del registro

    ▼ (acta de carga)
POST /api/trazabilidad/cargas/<id>/firmar/        ← Guarda firma en base64 en CargaExcel
GET  /api/trazabilidad/cargas/<id>/acta/pdf/      ← Genera y descarga PDF firmado
```

---

## 10. Convenciones de código

### Commits
Seguimos [Conventional Commits](https://www.conventionalcommits.org/):

```
feat:     nueva funcionalidad
fix:      corrección de bug
refactor: refactorización sin cambio funcional
docs:     solo documentación
style:    formato, espacios (sin cambio lógico)
test:     agregar o corregir tests
chore:    tareas de mantenimiento (deps, build)
```

Ejemplos:
```
feat: agregar edición de registros con auditoría
fix: corregir deduplicación dentro de misma carga
docs: actualizar README con endpoints de admin
```

### Branching

```
main            → producción estable (solo merge via PR)
develop         → integración de features
feat/<nombre>   → nuevas funcionalidades
fix/<nombre>    → correcciones
release/<v>     → preparación de release
```

### Estilo Python
- PEP 8 — líneas máx 120 chars
- Nombres de clases en `PascalCase`, variables/funciones en `snake_case`
- Las vistas DRF van en `views/` separadas por dominio
- Prefijo `_` para funciones internas de módulos (ej. `_inferir_proceso_y_estado`)

---

## 11. Testing

> El proyecto no tiene suite de tests automatizados implementada en Fase 1. Se recomienda implementar con:

```bash
# Instalar pytest-django
pip install pytest pytest-django pytest-cov

# Configurar pytest.ini
[pytest]
DJANGO_SETTINGS_MODULE = EURO_ver_y_data.settings
python_files = tests/*.py

# Correr tests
pytest

# Con cobertura
pytest --cov=. --cov-report=html
```

**Cobertura objetivo:** 70% mínimo en apps `Trazabilidad` y `Usuarios`.

---

## 12. Despliegue

### Desarrollo local
Ver sección [4. Instalación](#4-instalación-y-configuración-local).

### Servidor de producción (Ubuntu / Debian)

```bash
# 1. Clonar y configurar entorno
git clone https://github.com/JhonnatanHHM-lambda/EURO_ver_y_data_API.git
cd EURO_ver_y_data_API
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 2. Variables de entorno
cp .env.example .env
# Editar .env con valores de producción:
#   DEBUG=False
#   SECRET_KEY=<clave_segura_aleatoria>
#   ALLOWED_HOSTS=tu-dominio.com

# 3. Migraciones y estáticos
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py seed_sedes

# 4. Gunicorn (servidor WSGI)
gunicorn EURO_ver_y_data.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers 3 \
    --timeout 120

# 5. Celery (worker + beat) — en procesos separados
celery -A EURO_ver_y_data worker --loglevel=info -c 4
celery -A EURO_ver_y_data beat --loglevel=info
```

**Variables críticas para producción:**
- `DEBUG=False`
- `SECRET_KEY` diferente al de desarrollo
- `ALLOWED_HOSTS` con dominios reales
- `CORS_ALLOWED_ORIGINS` con URL del frontend
- Credenciales de PostgreSQL y Redis de producción

---

## 13. Troubleshooting / FAQ

**¿Error `psycopg2` al instalar requirements?**
```bash
# Windows: instalar Visual C++ Build Tools, o usar el binario:
pip install psycopg2-binary
```

**¿Error de CORS en desarrollo?**
Verifica que `CORS_ALLOWED_ORIGINS` en `.env` incluya la URL exacta del frontend (`http://localhost:5173`).

**¿El OTP no llega al correo?**
- Verifica `EMAIL_USER` y `EMAIL_PASS` en `.env`
- Asegúrate de usar App Password de Gmail (no la contraseña normal)
- Revisa que el worker Celery esté corriendo: `python -m celery -A EURO_ver_y_data worker --pool=solo`

**¿Error `relation does not exist` en PostgreSQL?**
```bash
python manage.py migrate  # Aplicar todas las migraciones pendientes
```

**¿Celery no corre en Windows?**
```bash
# Usar --pool=solo es obligatorio en Windows:
python -m celery -A EURO_ver_y_data worker --loglevel=info --pool=solo
```

**¿`distinct()` falla con `order_by` en PostgreSQL?**
Para queries con `distinct('campo')`, PostgreSQL requiere que el `order_by` incluya ese campo como primer elemento.

**¿Cómo acceder a la documentación Swagger?**
Con el servidor corriendo: `http://127.0.0.1:8000/swagger/`

---

## 14. Contacto del equipo

| Nombre | Rol | Correo |
|--------|-----|--------|
| Michel David Rojas | Project Manager | michel.rojas@lambdaanalytics.co |
| Ricardo González | Business Analyst | ricardo.gonzalez@lambdaanalytics.co |
| Jonnathan Henao | Tech Lead / Dev | jonnathan.henao@lambdaanalytics.co |
| Manuela Valentina Palacio | Product Owner (Euro) | — |
| Henry Alonso Cadavid Ríos | TI Euro Supermercados | — |

---

## 15. Changelog

### v1.0.0 — Fase 1 (junio 2026)

**Nuevas funcionalidades:**
- Sistema de autenticación JWT con OTP por correo electrónico
- Carga masiva de archivos Excel con mapeo automático de columnas
- Inferencia automática de tipo de proceso y estado del candidato
- Detección de hojas con fecha (fecha_ingreso) y hojas de entrevistas
- Regla ENTREVISTADO + fecha_ingreso → EMPLEADO
- Deduplicación dentro de la misma carga y contra BD existente
- Verificación de coherencia de nombres (SequenceMatcher < 75%)
- Panel de trazabilidad con filtros, paginación y KPIs
- Detalle por persona con todas sus casillas/registros
- Edición de registros con auditoría (HistorialCambioRegistro)
- Propagación de nombre/cédula a todos los registros del mismo documento
- Creación manual de registros individuales
- Administración de todos los registros (AdminRegistros)
- Generación de actas de carga en PDF y Word (sin referencias a Lambda)
- Firma digital de actas con canvas
- Gestión de usuarios, roles y permisos granulares
- Gestión de sedes y orígenes de datos
- Sidebar reorganizado: BD Centralizada / Gestión Humana / Administración

---

## 16. Licencia

Uso interno — Lambda Analytics SAS para Euro Supermercados.  
No distribuir sin autorización expresa de Lambda Analytics SAS.

---

*Documento generado por Lambda Analytics SAS · v1.0 · Fase 1 · Junio 2026*
