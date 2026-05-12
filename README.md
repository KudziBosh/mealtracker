# Mealtracker

> Personal weight-loss and habit tracker. Self-hosted Django + Telegram bot,
> tailored to a research-backed 9–14 month protocol (120 kg → ~90 kg).
> Single user. Not a general-purpose fitness app — see [`CLAUDE.md`](./CLAUDE.md)
> for the why, the scope, and what's deliberately out of scope.

---

## Status

**Slice 1 (this commit).** Thin end-to-end vertical: two models (`DailyLog`,
`WeightEntry`), Django admin, a single dashboard at `/` rendered server-side,
and a Docker Compose stack that boots clean.

Still to land before MVP: `FoodItem` + `MealEntry`, HTMX meal/habit forms,
DRF API, Celery + Telegram bot, food seed migration. See
[`CLAUDE.md`](./CLAUDE.md) §"MVP Scope (Phase 1)".

---

## Stack

- Django 5.2 + DRF + django-htmx
- PostgreSQL 16
- Redis 7 (reserved for Celery; nothing connects yet)
- Docker Compose for local dev; will deploy behind Cloudflare Tunnel
- Python 3.12, Black + Ruff, pytest-django

---

## Quick start

Prereqs: Docker + Docker Compose. No host Python install needed.

```bash
# 1. Configure
cp .env.example .env
# Edit DJANGO_SECRET_KEY (any long random string) and POSTGRES_PASSWORD.

# 2. Boot the stack — runs migrations and collectstatic on first start.
docker compose up -d

# 3. Create your superuser.
docker compose run --rm web python manage.py createsuperuser

# 4. Open the dashboard.
#    Default host port is 8001 (override with WEB_HOST_PORT in .env).
open http://127.0.0.1:8001/         # redirects to admin login
open http://127.0.0.1:8001/admin/   # admin UI for DailyLog, WeightEntry
```

Logs: `docker compose logs -f web`. Stop: `docker compose down`. Wipe data:
`docker compose down -v` (drops the `pgdata` volume).

---

## Common commands

```bash
# Tests
docker compose run --rm web pytest

# Django system check
docker compose run --rm web python manage.py check

# Migrations
docker compose run --rm web python manage.py makemigrations
docker compose run --rm web python manage.py migrate

# Shell (django-extensions shell_plus)
docker compose run --rm web python manage.py shell_plus

# Format / lint
docker compose run --rm web black .
docker compose run --rm web ruff check .
```

The container runs as UID 1000 by default, so files Django creates from inside
(migrations, etc.) land on the host owned by the developer. If your host UID
differs, rebuild with `docker compose build --build-arg APP_UID=$(id -u) --build-arg APP_GID=$(id -g) web`.

---

## Project layout

```
mealtracker/
├── CLAUDE.md                   # project memory — read first
├── docker-compose.yml          # web + db + redis (celery + bot land later)
├── Dockerfile
├── manage.py
├── pyproject.toml              # black / ruff / pytest config
├── requirements.txt            # runtime deps (pinned)
├── requirements-dev.txt        # dev tooling on top of runtime
├── mealtracker/
│   ├── settings/{base,dev,prod}.py
│   ├── urls.py
│   └── wsgi.py / asgi.py
└── tracker/
    ├── models.py               # DailyLog, WeightEntry (FoodItem/MealEntry next slice)
    ├── admin.py
    ├── views.py                # dashboard view
    ├── urls.py
    ├── protocol.py             # hardcoded plan constants (targets, habits, walking buildup)
    ├── templates/tracker/{base,dashboard}.html
    ├── migrations/0001_initial.py
    └── tests/test_models.py
```

---

## Environment variables

See [`.env.example`](./.env.example). The ones that matter on first boot:

| Var | Purpose |
|---|---|
| `DJANGO_SECRET_KEY` | **Required.** Long random string. Generate with `python -c "import secrets; print(secrets.token_urlsafe(60))"`. |
| `DJANGO_DEBUG` | Stays `False` per project policy, even in dev. |
| `DJANGO_TIME_ZONE` | Defaults to `Africa/Harare`. |
| `POSTGRES_*` | DB credentials — shared between the `db` container and Django. |
| `REDIS_URL` | Reserved for Celery in a later slice. |
| `TELEGRAM_BOT_TOKEN` | Leave blank until the bot slice. |
| `WEB_HOST_PORT` | Host-side port mapping for the web service (default `8001`). Change if it clashes. |

---

## Conventions

- Black + Ruff, 100-char line length (`pyproject.toml`).
- Type hints on public functions; docstrings on every model and Celery task.
- Migrations are committed (always).
- Tests next to code: `tracker/tests/test_*.py`.
- Settings split: `mealtracker/settings/{base,dev,prod}.py`. Env via
  `django-environ`. No hardcoded secrets.
- `DEBUG=False` everywhere; reach for `runserver_plus` (django-extensions) if
  you need richer error pages.

---

## License

Private. Single-user app. No license granted.
