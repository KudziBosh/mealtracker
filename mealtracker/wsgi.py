"""WSGI entrypoint for production servers (gunicorn)."""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mealtracker.settings.prod")

application = get_wsgi_application()
