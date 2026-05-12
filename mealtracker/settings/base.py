"""
Base settings — shared by dev and prod.

Env vars are read via django-environ. Required vars are declared without a
default so a missing one fails fast at startup rather than silently degrading.
"""

from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(
    DJANGO_DEBUG=(bool, False),
    DJANGO_ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
    DJANGO_TIME_ZONE=(str, "Africa/Harare"),
    TELEGRAM_BOT_TOKEN=(str, ""),
    REDIS_URL=(str, "redis://redis:6379/0"),
)

# Read .env from project root if present. In docker compose, vars come from the
# compose file's env_file/environment blocks, so this is a no-op there.
environ.Env.read_env(BASE_DIR / ".env")


# ---- Core ------------------------------------------------------------------

SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env("DJANGO_DEBUG")
ALLOWED_HOSTS = env("DJANGO_ALLOWED_HOSTS")


# ---- Applications ----------------------------------------------------------

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third party
    "rest_framework",
    "django_htmx",
    # Local
    "tracker",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
]

ROOT_URLCONF = "mealtracker.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "mealtracker.wsgi.application"
ASGI_APPLICATION = "mealtracker.asgi.application"


# ---- Database --------------------------------------------------------------

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB"),
        "USER": env("POSTGRES_USER"),
        "PASSWORD": env("POSTGRES_PASSWORD"),
        "HOST": env("POSTGRES_HOST", default="db"),
        "PORT": env("POSTGRES_PORT", default="5432"),
        "CONN_MAX_AGE": 60,
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ---- Auth ------------------------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# ---- I18n / TZ -------------------------------------------------------------

LANGUAGE_CODE = "en-us"
TIME_ZONE = env("DJANGO_TIME_ZONE")
USE_I18N = True
USE_TZ = True


# ---- Static / media --------------------------------------------------------

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"


# ---- DRF -------------------------------------------------------------------

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.FormParser",
    ],
}


# ---- Logging ---------------------------------------------------------------

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {name} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}


# ---- Celery ----------------------------------------------------------------

from celery.schedules import crontab  # noqa: E402

CELERY_BROKER_URL = env("REDIS_URL")
CELERY_RESULT_BACKEND = env("REDIS_URL")
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_BEAT_SCHEDULE = {
    "morning-ping": {
        "task": "tracker.tasks.send_morning_ping",
        "schedule": crontab(hour=7, minute=0),
    },
    "evening-habit-check": {
        "task": "tracker.tasks.send_evening_habit_check",
        "schedule": crontab(hour=21, minute=0),
    },
    "weekly-summary": {
        "task": "tracker.tasks.send_weekly_summary",
        "schedule": crontab(hour=19, minute=0, day_of_week="sun"),
    },
}


# ---- Telegram --------------------------------------------------------------

TELEGRAM_BOT_TOKEN = env("TELEGRAM_BOT_TOKEN")
