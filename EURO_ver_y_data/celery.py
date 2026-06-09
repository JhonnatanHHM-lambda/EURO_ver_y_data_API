import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'EURO_ver_y_data.settings')

app = Celery('EURO_ver_y_data_API')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()
