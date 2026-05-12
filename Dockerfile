# syntax=docker/dockerfile:1.7

# Slim Python base. Pin to 3.12 for stability — matches pyproject.toml target.
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# psycopg[binary] ships its libpq, but we still want libpq-dev for any
# fallbacks and curl for the in-container healthcheck.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user that matches the host UID/GID so bind-mounted files
# (migrations, etc.) created from inside the container are owned correctly on
# the host. UID/GID default to 1000 — override at build with --build-arg.
ARG APP_UID=1000
ARG APP_GID=1000
RUN groupadd --gid "$APP_GID" app \
    && useradd --uid "$APP_UID" --gid "$APP_GID" --create-home --shell /bin/bash app

WORKDIR /app

# Install requirements first so layer cache survives source edits.
COPY requirements.txt requirements-dev.txt ./
ARG INSTALL_DEV=0
RUN if [ "$INSTALL_DEV" = "1" ]; then \
        pip install -r requirements-dev.txt; \
    else \
        pip install -r requirements.txt; \
    fi

COPY --chown=app:app . .
USER app

# Default to dev settings; compose overrides for the prod-like web service.
ENV DJANGO_SETTINGS_MODULE=mealtracker.settings.dev

EXPOSE 8000

# Dev default — compose overrides with runserver_plus or gunicorn as needed.
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
