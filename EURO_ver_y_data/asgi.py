import os
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'EURO_ver_y_data.settings')
application = get_asgi_application()
