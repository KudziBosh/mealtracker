"""Celery application for mealtracker."""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mealtracker.settings.dev")

app = Celery("mealtracker")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
