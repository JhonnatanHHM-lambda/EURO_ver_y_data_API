import os
from pathlib import Path
from datetime import timedelta
from dotenv import load_dotenv
from celery.schedules import crontab

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-fallback')
DEBUG = os.getenv('DEBUG', 'True') == 'True'

# En DEBUG (dev local) se acepta cualquier host por conveniencia. En producción
# se exige una lista explícita vía ALLOWED_HOSTS (mismo patrón que
# CORS_ALLOWED_ORIGINS más abajo); 'localhost'/'127.0.0.1' se agregan siempre
# porque el healthcheck de docker-compose.yml llama a la API como
# http://localhost:8000 desde dentro del propio contenedor.
if DEBUG:
    ALLOWED_HOSTS = ['*']
else:
    ALLOWED_HOSTS = [
        host.strip() for host in os.getenv('ALLOWED_HOSTS', '').split(',') if host.strip()
    ] + ['localhost', '127.0.0.1']

# Cuando Django está detrás de Nginx con SSL, build_absolute_uri usa https://
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True

# Cookies seguras + redirect forzado a HTTPS. Default False a propósito: hoy no
# está confirmado cuál config de nginx/*.conf está realmente activa en el
# servidor de producción, y algunas de ellas (ip.conf, euro.conf) sirven la API
# por HTTP plano sin certificado. Activar esto sin HTTPS real en frente rompe el
# sitio (bucle de redirect, cookies que el navegador nunca llega a enviar).
# Activar SECURE_SSL_ENABLED=True en el .env del servidor SOLO después de
# confirmar que ese servidor sirve la API exclusivamente por HTTPS.
SECURE_SSL_ENABLED = os.getenv('SECURE_SSL_ENABLED', 'False') == 'True'
if SECURE_SSL_ENABLED:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

# HSTS es más agresivo y difícil de revertir (el navegador recuerda la política
# de "solo HTTPS" durante el tiempo configurado, incluso si luego se desactiva
# el certificado). Se controla aparte de SECURE_SSL_ENABLED; la recomendación de
# Django es empezar con un valor bajo (ej. 3600 = 1 hora) y solo subirlo a algo
# como 31536000 (1 año) una vez confirmado que todo sigue funcionando por HTTPS.
SECURE_HSTS_SECONDS = int(os.getenv('SECURE_HSTS_SECONDS', '0'))

DJANGO_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django_celery_beat',
    'django_celery_results',
]

LOCAL_APPS = [
    'Base',
    'Usuarios',
    'Notificaciones',
    'Trazabilidad',
    'Contratos',
    'OptimizacionCorreos',
    'migracion_masiva_archivo',
]

THIRD_PARTY_APPS = [
    'corsheaders',
    'drf_yasg',
    'rest_framework',
    'rest_framework_simplejwt',
]

INSTALLED_APPS = DJANGO_APPS + LOCAL_APPS + THIRD_PARTY_APPS

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'EURO_ver_y_data.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'EURO_ver_y_data.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': os.getenv('DB_ENGINE', 'django.db.backends.postgresql'),
        'NAME': os.getenv('DB_NAME', 've_y_data'),
        'USER': os.getenv('DB_USER', 'postgres'),
        'PASSWORD': os.getenv('DB_PASSWORD', '123456'),
        'HOST': os.getenv('DB_HOST', 'localhost'),
        'PORT': os.getenv('DB_PORT', '5432'),
    }
}

AUTH_USER_MODEL = 'Usuarios.Usuario'

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=int(os.getenv('ACCESS_TOKEN_LIFETIME', 60))),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=int(os.getenv('REFRESH_TOKEN_LIFETIME', 1))),
    'ROTATE_REFRESH_TOKENS': False,
    'AUTH_HEADER_TYPES': ('Bearer',),
}

if DEBUG:
    CORS_ALLOW_ALL_ORIGINS = True
else:
    CORS_ALLOW_ALL_ORIGINS = False
    CORS_ALLOWED_ORIGINS = os.getenv('CORS_ALLOWED_ORIGINS', '').split(',')
CORS_ALLOW_CREDENTIALS = True

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'es-co'
TIME_ZONE = 'America/Bogota'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

MEDIA_URL = '/media/'
MEDIA_ROOT = Path(os.getenv('MEDIA_ROOT', BASE_DIR / 'media'))

MIGRACION_ARCHIVOS_MEDIA_ROOT = Path(
    os.getenv('MIGRACION_ARCHIVOS_MEDIA_ROOT', MEDIA_ROOT / 'migracion_masiva_archivo')
)
MIGRACION_ARCHIVOS_TEMP_ROOT = Path(
    os.getenv('MIGRACION_ARCHIVOS_TEMP_ROOT', BASE_DIR / 'tmp_migracion_masiva_archivo')
)
MIGRACION_ARCHIVOS_MAX_UPLOAD_MB = int(os.getenv('MIGRACION_ARCHIVOS_MAX_UPLOAD_MB', '100'))
MIGRACION_ARCHIVOS_SAIA_LIMITE = int(os.getenv('MIGRACION_ARCHIVOS_SAIA_LIMITE', '70'))
# Decisión de despliegue: servidor Linux → la función de "carpeta secundaria"
# (services/continuidad_service.py, resuelve accesos directos .lnk de Windows vía
# win32com) no es portable y queda deshabilitada por diseño, no por fallo silencioso.
MIGRACION_ARCHIVOS_CARPETA_SECUNDARIA_HABILITADA = (
    os.getenv('MIGRACION_ARCHIVOS_CARPETA_SECUNDARIA_HABILITADA', 'False') == 'True'
)

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Email — Microsoft Graph API (Office 365)
if DEBUG:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
else:
    EMAIL_BACKEND = 'EURO_ver_y_data.email_backends.MicrosoftGraphEmailBackend'

DEFAULT_FROM_EMAIL = 'Notificaciones@lambdaanalytics.co'
AZURE_TENANT_ID    = os.getenv('AZURE_TENANT_ID', '')
AZURE_CLIENT_ID    = os.getenv('AZURE_CLIENT_ID', '')
AZURE_SECRET_KEY   = os.getenv('AZURE_SECRET_KEY', '')

# Celery
CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/1')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE

# OTP config
OTP_EXPIRY_MINUTES = 10

# MinIO
MINIO_ENDPOINT = os.getenv('MINIO_ENDPOINT', 'localhost:9000')
MINIO_PUBLIC_ENDPOINT = os.getenv('MINIO_PUBLIC_ENDPOINT', 'localhost:9000')
MINIO_ACCESS_KEY = os.getenv('MINIO_ACCESS_KEY', 'minioadmin')
MINIO_SECRET_KEY = os.getenv('MINIO_SECRET_KEY', 'minioadmin')
MINIO_BUCKET = os.getenv('MINIO_BUCKET', 'euro-vyd')
MINIO_USE_HTTPS = os.getenv('MINIO_USE_HTTPS', 'False') == 'True'
MINIO_PUBLIC_USE_HTTPS = os.getenv('MINIO_PUBLIC_USE_HTTPS', 'False') == 'True'
MINIO_CERT_CHECK = os.getenv('MINIO_CERT_CHECK', 'False') == 'True'

# Contratos — bucket separado dentro del mismo MinIO
MINIO_BUCKET_CONTRATOS = os.getenv('MINIO_BUCKET_CONTRATOS', 'euro-contratos')

# URL base del frontend (para links de firma en emails)
FRONTEND_URL = os.getenv('FRONTEND_URL', 'http://localhost:5173/ver-y-data')

# Celery Beat — tareas programadas del módulo Contratos
CELERY_BEAT_SCHEDULE = {
    'contratos-revisar-60-dias': {
        'task': 'Contratos.tasks.revisar_contratos_60_dias',
        'schedule': crontab(hour=7, minute=0),
    },
    'contratos-revisar-proximos-vencer': {
        'task': 'Contratos.tasks.revisar_contratos_proximos_vencer',
        'schedule': crontab(hour=7, minute=5),
    },
    'contratos-escalar-sin-firma': {
        'task': 'Contratos.tasks.escalar_contratos_sin_firma',
        'schedule': crontab(hour=7, minute=10),
    },
    'contratos-notificar-directores-sin-decision': {
        'task': 'Contratos.tasks.notificar_directores_sin_decision',
        'schedule': crontab(hour=7, minute=15),
    },
    'contratos-alertar-urgentes': {
        'task': 'Contratos.tasks.alertar_contratos_urgentes',
        'schedule': crontab(hour=7, minute=20),
    },
    # Migración Masiva de Archivo — retención de disco (logs, screenshots SAIA,
    # carpetas de uploads de lotes terminados). Ver INFRA_MIGRACION_MASIVA_ARCHIVO.md.
    'migracion-masiva-archivo-purgar-logs': {
        'task': 'migracion_masiva_archivo.tasks.purgar_logs_antiguos',
        'schedule': crontab(hour=3, minute=0),
    },
    'migracion-masiva-archivo-purgar-screenshots-saia': {
        'task': 'migracion_masiva_archivo.tasks.purgar_screenshots_saia',
        'schedule': crontab(hour=3, minute=10),
    },
    'migracion-masiva-archivo-purgar-uploads': {
        'task': 'migracion_masiva_archivo.tasks.purgar_uploads_antiguos',
        'schedule': crontab(hour=3, minute=20),
    },
}

# Celery — cola predeterminada para tareas sin ruta explícita
CELERY_TASK_DEFAULT_QUEUE = 'default'

# Enrutamiento de colas
CELERY_TASK_ROUTES = {
    'Contratos.tasks.*':          {'queue': 'contratos'},
    'Notificaciones.tasks.*':     {'queue': 'default'},
    'OptimizacionCorreos.tasks.*': {'queue': 'optimizacion_correos'},
    'migracion_masiva_archivo.tasks.*': {'queue': 'migracion_masiva_archivo'},
}

# Swagger
SWAGGER_SETTINGS = {
    'SECURITY_DEFINITIONS': {
        'Bearer': {
            'type': 'apiKey',
            'name': 'Authorization',
            'in': 'header',
        }
    },
    'USE_SESSION_AUTH': False,
}

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'simple': {
            'format': '[%(levelname)s %(name)s] %(message)s',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
    },
    'loggers': {
        'Contratos': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'Notificaciones': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}
