import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'EURO_ver_y_data.settings')
application = get_wsgi_application()
