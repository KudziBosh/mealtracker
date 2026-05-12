# Mealtracker — Project Memory

> Personal weight-loss and habit tracker. Self-hosted Django + Telegram bot replacement for MyFitnessPal, tailored to a research-backed 9–14 month protocol. Single user (the owner of this repo). This file is project memory — read it at the start of every session.

---

## Why This Exists

The owner is committed to a structured 9–14 month fat-loss protocol (120 kg → ~90 kg). Off-the-shelf trackers (MyFitnessPal, Lose It, etc.) don't model the specific behaviours that predict long-term success per the National Weight Control Registry, don't carry satiety scoring from the Holt research, and don't own the data. Existing self-hosted options (wger) are over-spec'd for workouts and under-spec'd for the habit + satiety + nudge layer that matters here.

This app is a thin, opinionated tracker built around one person's plan. It is **not** a general-purpose fitness app. Resist the urge to generalise.

---

## Owner Profile

- Based in Harare, Zimbabwe
- Strong Django backend developer (runs a production Django app, CloudPay)
- Self-hosting infrastructure: Docker, Portainer, Cloudflare Tunnel, Tailscale, all running on a home server
- Knows Next.js / React but prefers backend-heavy Django work
- Will be the only user. No multi-tenancy. No auth flows beyond a single account.

---

## Tech Stack (Decided)

| Layer | Choice | Reason |
|---|---|---|
| Backend | Django 5.x + DRF | Owner's strongest stack |
| Database | PostgreSQL | Already runs Postgres elsewhere |
| Queue / scheduler | Celery + Redis + celery beat | Standard, owner has Redis already |
| Frontend (Phase 1) | Django templates + HTMX + Tailwind | Server-rendered, minimal JS |
| Frontend (Phase 2) | Same templates, add service worker → PWA | Add offline later when needed |
| Notifications | Telegram bot (python-telegram-bot) | Reliable on Android, free, supports interactive callback buttons |
| Deploy | Docker Compose, behind Cloudflare Tunnel | Joins existing Portainer-managed stack |
| Auth | Django admin + a single superuser | Single-user app |

**Do not introduce:** Node frontend frameworks, React, GraphQL, microservices, message brokers other than Redis, ORMs other than Django's. Keep the dependency graph small.

---

## MVP Scope (Phase 1)

Build the smallest thing that solves the daily logging problem end-to-end before adding anything else.

**In scope for the MVP:**

1. Five Django models (see Data Model below)
2. Django admin enabled for all models — that's the initial "UI" for testing
3. One templated dashboard page at `/` that shows: today's running totals (kcal, protein), today's habit checkboxes, this week's weight trend, latest weight entry
4. HTMX-driven form for logging a meal entry (food + grams) on the dashboard
5. HTMX-driven habit toggles on the dashboard
6. Telegram bot worker (Celery beat schedule) that fires:
   - 07:00 daily — "Good morning. Target today: 2000 kcal, 190 g protein. Tuesday? Reply with /weigh"
   - 21:00 daily — "Habit check" with inline keyboard for the 5 booleans
   - Sunday 19:00 — Weekly summary (weight change, habit completion %, walking minutes)
7. Seed data: ~25 hand-curated `FoodItem` rows from the meal plan (potato, sweet potato, chicken breast, chicken thigh, kapenta, eggs, Greek yoghurt, peanut butter, etc.) with macros + satiety scores
8. Docker compose file with web, db, redis, celery_worker, celery_beat, telegram_bot services
9. README with `docker compose up` setup, env vars, bot token instructions

**Definition of done:** Owner can SSH to their server, run `docker compose up -d`, register their Telegram chat ID, and log a full day of meals and habits via either the dashboard or the bot.

**Out of scope for MVP (do not build these yet):**

- Food autocomplete / full search
- Barcode scanning
- Workout tracking (Phase 2)
- Open Food Facts import (Phase 2)
- PWA / service worker (Phase 2)
- Photo upload / progress gallery
- Multiple users, user registration, OAuth
- Mobile app
- Email notifications
- Insights / charts beyond the simple weight trend
- Recipe management (recipes are in a separate document the owner cooks from)

---

## Data Model

Five models. Resist adding fields not listed here without asking.

### `FoodItem`
```
id, name, kcal_per_100g, protein_g, fat_g, carb_g
satiety_index (int, nullable)   # Holt 1995 scale, white bread = 100
common_unit (str)               # e.g. "1 medium = 200g"
notes (str, blank=True)
created_at, updated_at
```

### `MealEntry`
```
id, user (FK, default=single user)
eaten_at (datetime)
food (FK to FoodItem)
grams (decimal)
# Computed properties: kcal, protein_g, etc. = (grams / 100) * food.field
```

### `DailyLog`
```
id, user (FK)
date (date, unique per user)
walked_minutes (int, default=0)
steps (int, nullable)
hit_protein (bool, default=False)
under_calories (bool, default=False)
walked_30 (bool, default=False)
ate_breakfast (bool, default=False)
no_alcohol_or_sugar (bool, default=False)
notes (text, blank=True)
```

The five booleans are deliberately hardcoded — they match the document's principles. Do not refactor to a dynamic `HabitDefinition` table; that's future bloat.

### `WeightEntry`
```
id, user (FK)
date (date, unique per user)
weight_kg (decimal, 5 digits, 2 decimal places)
notes (text, blank=True)
```

### `TelegramSettings` (single-row singleton)
```
chat_id (str)
bot_token (str)           # or read from env; whichever is cleaner
morning_ping_time (time, default=07:00)
evening_ping_time (time, default=21:00)
weekly_summary_day (int, default=6)  # 0=Mon, 6=Sun
weekly_summary_time (time, default=19:00)
```

---

## API Surface (DRF)

Minimal. Bot and dashboard hit these.

```
GET  /api/today/            → today's DailyLog, MealEntries, running totals
POST /api/meals/            → log a MealEntry  {food_id, grams, eaten_at?}
PATCH /api/daily/<date>/    → toggle a habit boolean
POST /api/weight/           → log a WeightEntry {weight_kg, date?}
GET  /api/summary/week/     → current week summary (used by Sunday Telegram message)
GET  /api/foods/            → list FoodItems (filterable by name contains)
```

DRF serializers, function-based views are fine for this scale. No need for ViewSets unless they save real code.

---

## Telegram Bot Design

- Use `python-telegram-bot` (async version, v20+)
- Bot runs as its own service in docker-compose (separate from web)
- For the MVP, only outbound messages and a few inbound commands:
  - `/start` — bind the chat
  - `/weigh <kg>` — log a WeightEntry  
  - `/log <food> <grams>` — log a MealEntry (basic substring match on food name)
  - `/today` — return running totals
- Evening habit ping uses an inline keyboard with 5 callback buttons; pressing toggles the boolean and edits the message in place to show ticks

Bot token comes from `TELEGRAM_BOT_TOKEN` env var. Chat ID is set via `/start` and stored on `TelegramSettings`.

---

## Notification Copy (Reference)

The protocol numbers should be hardcoded as defaults in a `protocol.py` constants file. Use these strings as the message templates — they're calibrated to the document's tone:

```python
# Morning, weekday
"Good morning. Today's targets: 2000 kcal, 190 g protein. Walk 30+ min. Don't skip breakfast."

# Morning, Tuesday
"Tuesday weigh-in day. Step on the scale before food, after the toilet. Reply with /weigh <kg>."

# Evening habit ping
"Habit check for today. Tap to toggle:"
# [✓/☐ Hit protein] [✓/☐ Under cals] [✓/☐ Walked 30+]
# [✓/☐ Ate breakfast] [✓/☐ No alcohol/sugar]

# Sunday weekly summary
"Week {n} done.
Weight: {start_kg} → {end_kg} ({delta_kg:+.1f} kg)
Habits: {pct}% ({hit}/35)
Walking: {total_min} min across {days_walked}/7 days
{nudge_line}"
```

`nudge_line` rotates from a small list keyed off performance — e.g. weekend consistency reminder if Sat/Sun habit rate < weekday rate. Keep nudges grounded in the document's research; don't invent motivational fluff.

---

## Protocol Constants (Hardcode These)

```python
# protocol.py - the diet plan numbers
GOAL_WEIGHT_KG = 90
START_WEIGHT_KG = 120
DAILY_KCAL_TARGET = 2000
DAILY_PROTEIN_G = 190
DAILY_FAT_G = 60
DAILY_CARB_G = 165
KCAL_FLOOR = 1800   # don't drop below this regardless
WALKING_MIN_PER_DAY = 60   # target for week 5+
WEIGH_IN_DAY = 1   # Tuesday (Mon=0)
```

---

## Seed Food Data

Hand-curate ~25 items from the meal plan doc. Owner will provide macros if any are unclear. Each entry needs a satiety score (use Holt 1995 values where available, estimate plausibly for items not in the original study — potato 323, fish 225, oranges 202, apples 197, brown bread 154, popcorn 154, bran cereal 151, eggs 150, beans 168, white bread = 100 baseline).

Items to seed (non-exhaustive, owner can edit):
- Regular potato, sweet potato (white), pumpkin, brown rice (cooked), sadza (cooked), brown bread
- Chicken breast (cooked), chicken thigh (cooked), lean beef mince, kapenta (dried), river bream, canned tuna
- Whole egg, Greek yoghurt (plain, full-fat and low-fat as two entries), cottage cheese, firm tofu
- Peanut butter, olive oil, sesame oil
- Apple, banana, orange, mango (raw, in season)
- Kale, broccoli, bok choy, cabbage, tomato, onion

Create a Django data migration with these (not a fixture), so it runs automatically on first `migrate`.

---

## wger as Reference (Not a Dependency)

[wger](https://github.com/wger-project/wger) is the closest existing project. It is **NOT a dependency** of this app. We will not import or vendor any wger code. We will study patterns and re-implement what's useful.

Things worth reading in wger's repo when stuck:

- `wger/nutrition/models.py` — their `Ingredient` schema is well-thought-out for multi-unit food (g, servings, "1 medium"). Steal the *idea*, write your own model.
- `wger/nutrition/management/commands/import-off-products.py` (or similar) — when we add Open Food Facts data in Phase 2, copy the ingestion approach.
- Their DRF serializer patterns for nested writes (meal containing multiple ingredients in one POST) — useful when we add multi-food meals.
- Their docker-compose.yml — useful sanity-check for our own compose file structure.

**Do not:**
- Fork wger
- Use wger as a base and patch it
- Copy wger code into this repo (AGPL license; if you ever copy you must AGPL ours too)
- Try to be wger. We are deliberately smaller.

---

## Suggested First Session

Before writing any code, scaffold the smallest end-to-end working slice:

1. `django-admin startproject mealtracker`
2. `python manage.py startapp tracker`
3. Create just the `DailyLog` and `WeightEntry` models (skip `FoodItem` and `MealEntry` for the first slice)
4. Register them in Django admin
5. Write a Dockerfile and a docker-compose.yml with: web, db, redis (no celery yet)
6. Create one URL `/` that renders a template showing today's `DailyLog` and the latest `WeightEntry`
7. Write one test: `test_daily_log_creation`
8. Get `docker compose up` working
9. Commit. Push to a private GitHub repo.

Once that's running, add: `FoodItem`, `MealEntry`, the DRF API endpoints, then the Celery + Telegram bot stack last.

Resist the urge to scaffold everything at once. The thin slice catches stack issues early — broken Postgres connection in compose, missing env vars, port conflicts, etc.

---

## Open Decisions Owner Should Make

Ask these before assuming defaults:

1. **Domain name** — what subdomain on owner's Cloudflare-tunneled domain will this live at? (Probably something under `.eport.cloud` or similar.)
2. **Bot username** — owner needs to create a Telegram bot via @BotFather and provide the token and bot username.
3. **Postgres credentials** — new dedicated DB for this app, or share an existing instance?
4. **Time zone** — confirm Africa/Harare for all datetime operations and Celery schedules.
5. **Walking units** — do we want both minutes AND steps, or just one? (Currently both, with steps optional.)
6. **Starting date** — what is "Week 1" of the tracker? Owner picks. Defaults to first Monday after first `WeightEntry`.

---

## Reference Documents

The meal plan documents (in the same folder as this CLAUDE.md or stored elsewhere by the owner) are the authoritative source for:

- Daily macro targets (2000 / 190 / 60 / 165)
- The five tracked habits
- Walking buildup schedule (8 weeks: 30 → 60 min)
- Recipe list (informs food seed data)
- Shopping list (informs food seed data)
- Ten Principles (informs nudge copy)
- Research basis (Holt satiety, NWCR, protein/satiety hormones — informs why each feature exists)

Do not contradict the protocol in those docs. If a design choice feels like it conflicts, flag it to the owner.

---

## Coding Conventions

- Black for formatting, ruff for linting, 100 char line length
- Type hints on all public functions
- Docstrings on every Django model and every Celery task
- Migrations checked into the repo (always)
- Tests next to code: `tracker/tests/test_models.py` etc.
- Settings split: `settings/base.py`, `settings/dev.py`, `settings/prod.py`
- Env vars via `django-environ`, never hardcoded
- `DEBUG=False` even in dev compose (use `runserver_plus` if better errors are needed)

---

## First Prompt to Run

After saving this file as `CLAUDE.md` in an empty repo, paste this to start the first session:

> Read `CLAUDE.md`. Do not write any code yet. Confirm you've understood:
> 1. The MVP scope (5 models, dashboard, Telegram bot)
> 2. What's deliberately out of scope
> 3. The "thin first slice" plan in "Suggested First Session"
> 4. The wger reference policy (read, don't copy)
> 
> Then ask me the open decisions in the "Open Decisions" section before proceeding. Wait for my answers, then scaffold the first slice.
