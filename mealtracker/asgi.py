"""ASGI entrypoint — reserved for any future async features."""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mealtracker.settings.prod")

application = get_asgi_application()
