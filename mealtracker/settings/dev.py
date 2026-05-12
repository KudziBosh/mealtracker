"""Dev settings — used by `docker compose up` in development.

Per project policy, DEBUG defaults to False even in dev. Use `runserver_plus`
from django-extensions for richer error pages when needed.
"""

from .base import *  # noqa: F401,F403
from .base import INSTALLED_APPS, MIDDLEWARE

INSTALLED_APPS = [*INSTALLED_APPS, "django_extensions"]

# Verbose-but-not-DEBUG SQL logging is fine in dev; quiet noisy migration logs.
INTERNAL_IPS = ["127.0.0.1"]
