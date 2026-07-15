# JobPilot

Self-hosted, AI-powered job search platform — a free, private alternative to
Jobright. It hunts for jobs on a schedule, scores every posting against your
resume, drafts tailored application materials that never invent facts, tracks
your pipeline on a kanban board, emails you a nightly report, and answers
questions about your search through a built-in assistant ("Jarvis").

Built with Python 3.12 · FastAPI · SQLAlchemy 2 · PostgreSQL 16 + pgvector ·
Celery + Redis · React 18 + TypeScript + Vite + MUI. Runs entirely on your
machine with `docker compose up` — no paid services required.

---

## Table of contents

1. [Features](#features)
2. [Repository layout](#repository-layout)
3. [How it works (architecture)](#how-it-works)
4. [Running the service — Docker (recommended)](#running-with-docker-recommended)
5. [Running the service — local development](#running-locally-for-development)
6. [First-run walkthrough](#first-run-walkthrough)
7. [Configuration reference](#configuration-reference)
8. [Job sources & compliance](#job-sources--compliance)
9. [Scheduled automation](#scheduled-automation)
10. [Testing & CI](#testing--ci)
11. [Troubleshooting](#troubleshooting)
12. [Status & honest limitations](#status--honest-limitations)

---

## Features

| Area | What you get |
|---|---|
| **Automatic discovery** | 6:00 AM daily sweep + every-2-hours incremental checks across Greenhouse, Lever, Ashby, SmartRecruiters (official ATS APIs — covers most companies *and* staffing firms like TEKsystems/Apex via a watchlist), Dice's public feed, and Adzuna/Jooble aggregators that index Indeed/Monster/ZipRecruiter inventory |
| **Your filters** | Title keywords, full-time vs contract (**W2 / 1099 / C2C third-party** auto-detected from posting text), remote/hybrid/onsite, country, salary floor, posted-within window, **visa sponsorship** posture |
| **Match scoring** | Deterministic sub-scores per job — resume skill overlap, ATS keyword coverage, salary fit, location fit, visa fit — plus a persisted skill-gap list, so "why did this score 39?" always has an answer. AI adds a natural-language rationale; it never changes the numbers |
| **Document generation** | Tailored resume summary, cover letter, recruiter email, LinkedIn note, cold email. Every draft passes a **truthfulness guardrail**: any skill/credential not present in your real resume rejects the draft. Recruiter contacts found in postings are extracted for you |
| **Application tracker** | 11-stage kanban (saved → interested → resume generated → applied → recruiter contacted → OA → interview → rejected/offer/accepted/declined) with event-sourced history |
| **Daily report** | 9 PM email (+ optional Slack/Discord webhooks) with new matches, KPIs, and suggested next actions; weekly analytics snapshots feed trend charts |
| **Dashboard** | Funnel KPIs, applications-by-week and score-distribution charts, top matches, booming companies, tech-demand trends, data-grounded suggestions |
| **Jarvis assistant** | Chat grounded in *your* data (pipeline, matches, gaps) — never free-floating LLM guesses |
| **AI provider chain** | **Ollama → OpenRouter → Gemini → Claude → OpenAI**, first available wins. Every AI feature degrades to deterministic logic, so the platform is fully functional with **zero API keys** |
| **Security** | bcrypt + short-lived JWTs, rotating refresh tokens with theft detection, RBAC (first account = admin), AES-256-GCM-encrypted secrets, append-only audit log of everything the robot does |

## Repository layout

```
jobpilot-platform/
├── docker-compose.yml          # the whole platform: db, redis, api, worker, beat, web
├── README.md                   # you are here
├── api/
│   ├── openapi.yaml            # Phase-3 design contract (OpenAPI 3.1)
│   └── openapi.runtime.json    # spec generated from the live app (frontend types source)
├── db/
│   └── schema.sql              # canonical DDL: 31 tables, 17 enums, seeds
├── docs/
│   ├── ARCHITECTURE.md         # system design, module map, connector SPI, AI gateway
│   ├── DATABASE.md             # ER diagrams + design principles
│   └── API.md                  # REST conventions + endpoint catalog
├── backend/                    # FastAPI + SQLAlchemy + Celery (one image, three roles)
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── .env.example            # every config knob, documented
│   ├── alembic/                # migrations (0001 = full schema)
│   ├── app/
│   │   ├── main.py             # FastAPI factory (all routers under /api/v1)
│   │   ├── core/               # settings, db engines, RFC-7807 errors, logging, crypto, security
│   │   ├── common/             # pagination envelope, audit trail
│   │   ├── worker/             # Celery app + beat schedule (America/Chicago)
│   │   ├── auth/               # register/login/refresh-rotation/reset/OAuth, RBAC deps
│   │   ├── user/               # profile, preferences, notification settings
│   │   ├── resume/             # upload (docx/pdf), parse, ATS analysis
│   │   ├── connector/          # SPI + 11 connectors + registry + jobs API
│   │   ├── ingestion/          # orchestrator, normalize/dedupe, Celery tasks
│   │   ├── ai/                 # provider gateway (fallback chain), JD extraction
│   │   ├── matching/           # scoring engine, match API
│   │   ├── generation/         # documents + truthfulness guardrail
│   │   ├── application/        # tracker CRUD, status events, compliance-gated apply
│   │   ├── assistant/          # Jarvis conversations
│   │   ├── analytics/          # dashboard/trends queries, weekly snapshots
│   │   ├── notification/       # SMTP/Slack/Discord channels, daily report
│   │   ├── scheduler/          # scheduled_tasks/runs bookkeeping
│   │   └── admin/              # schedules, run history, connector toggles
│   └── tests/                  # 67 tests incl. integration against real PostgreSQL
└── frontend/                   # React 18 + TS + Vite + MUI
    ├── Dockerfile              # build → nginx (serves SPA, proxies /api)
    ├── nginx.conf
    └── src/
        ├── api/                # typed client generated from the OpenAPI spec
        ├── stores/auth.ts      # session store (silent refresh, single-flight)
        ├── components/         # app shell, route guards
        └── pages/              # Dashboard, Jobs, Tracker, Assistant, Resumes, Preferences, Admin, Login
```

## How it works

```
                        ┌─────────────────────────────────────────────┐
 Browser ── :8080 ────► │ frontend (nginx)  ── /api/* proxied ──►     │
                        │ api (FastAPI)  ◄── PostgreSQL 16 + pgvector │
                        │      ▲                    ▲                 │
                        │      │ Redis (broker/cache/rate-limit)     │
                        │ worker (Celery) ── beat (cron emitter)      │
                        └───────┬─────────────────────────────────────┘
                                │ polite HTTP: honest UA, rate limits
                          job sources (ATS APIs, Dice feed, aggregators)
                          AI providers (Ollama → … → OpenAI, optional)
```

One backend image runs in three roles: **api** (HTTP), **worker** (scraping,
scoring, documents, emails), **beat** (fires the schedule). Everything the
robot does is written to `scheduled_runs` + `audit_events` and inspectable in
the Admin panel. Full details: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Running with Docker (recommended)

**Prerequisites:** Docker Desktop (or any Docker Engine ≥ 24 with the compose
plugin). Nothing else.

```bash
# 1. clone / cd into the platform
cd jobpilot-platform

# 2. (production only — skip for a local try-out) set real secrets
cat > .env <<'EOF'
JOBPILOT_JWT_SECRET=<long random string>
JOBPILOT_MASTER_KEY=<long random string>
POSTGRES_PASSWORD=<db password>
EOF

# 3. build and start everything
docker compose up -d --build

# 4. open the app
open http://localhost:8080          # register — the FIRST account becomes admin
```

That's it. The API container applies database migrations automatically on
boot. Useful extras:

```bash
docker compose ps                        # health of all six services
docker compose logs -f worker           # watch scraping/scoring live
docker compose --profile ollama up -d   # add free local AI…
docker compose exec ollama ollama pull llama3.2   # …and pull a model
docker compose down                     # stop (add -v to also wipe data)
```

Direct API access (Swagger UI): http://localhost:8000/api/v1/docs

## Running locally (for development)

**Prerequisites:** Python 3.12+, Node 20+, PostgreSQL 15+ (16 recommended,
with the pgvector extension for embedding features), Redis.

```bash
# --- backend ---------------------------------------------------------------
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env                       # point JOBPILOT_DATABASE_URL at your Postgres
alembic upgrade head                       # create the schema
uvicorn app.main:app --reload              # API on :8000

# --- background processing (separate terminals; needs Redis running) --------
celery -A app.worker.celery_app worker -l info -Q default,ingest,ai,notify
celery -A app.worker.celery_app beat -l info        # exactly one instance

# --- frontend ----------------------------------------------------------------
cd frontend
npm install
npm run dev                                # UI on :5173, /api proxied to :8000
```

Without Redis, the API still runs — search-runs return a clear 503 and rate
limiting degrades open. Without an AI key or Ollama, everything falls back to
deterministic logic.

## First-run walkthrough

1. **Register** at the web UI — the first account is automatically **ADMIN**.
2. **Preferences** → set desired titles (e.g. "Java Developer", "Backend
   Engineer"), employment types (Full-time / Contract), **W2 / C2C**,
   workplace, salary floor, sponsorship needs, and the auto-apply policy.
3. **Resumes** → upload your resume (.docx or .pdf). It's parsed, skills are
   extracted, and it becomes the default for matching and generation.
4. **Admin → connectors** *(optional)* — add free Adzuna/Jooble API keys for
   wider coverage; add staffing firms / target companies to the watchlist
   with their ATS slug (e.g. Greenhouse board name).
5. **Jobs → "Run new search"** — or wait for the 6:00 AM automatic sweep.
   Results appear with W2/C2C chips; **Track** puts a job on the kanban;
   **Export CSV** covers the LinkedIn/Indeed manual-apply lane.
6. Open any job for its **score breakdown and skill gap**; generate a
   tailored cover letter / recruiter email from the Documents API.
7. **Notification settings** → confirm the 9 PM report; add SMTP creds in
   `.env` (Gmail: create an [App Password](https://myaccount.google.com/apppasswords))
   to receive it by email — otherwise deliveries are recorded as SKIPPED.

## Configuration reference

All knobs are environment variables prefixed `JOBPILOT_` (full annotated list
in [backend/.env.example](backend/.env.example)). The most important:

| Variable | Default | Purpose |
|---|---|---|
| `JOBPILOT_JWT_SECRET` | dev value | **Set in production** — signs access tokens |
| `JOBPILOT_MASTER_KEY` | dev value | **Set in production** — AES-256-GCM key for stored secrets |
| `JOBPILOT_DATABASE_URL` | localhost | `postgresql+psycopg://user:pass@host:5432/jobpilot` |
| `JOBPILOT_REDIS_URL` | localhost | Celery broker / cache / rate limits |
| `JOBPILOT_OLLAMA_BASE_URL` | `http://localhost:11434` | local AI (first in the chain) |
| `JOBPILOT_OPENROUTER_API_KEY` | empty | free-tier cloud LLM (2nd in chain) |
| `JOBPILOT_GEMINI_API_KEY` / `ANTHROPIC` / `OPENAI` | empty | further fallbacks — any subset works |
| `JOBPILOT_SMTP_HOST/PORT/USER/PASSWORD/FROM` | empty | daily-report + password-reset email |
| `JOBPILOT_DEFAULT_TIMEZONE` | America/Chicago | schedule timezone |

Runtime settings (connector on/off, rate limits, cron expressions, Slack/
Discord webhooks, Adzuna/Jooble keys) live in the database, managed from the
**Admin** panel, encrypted at rest.

## Job sources & compliance

Compliance is a framework property, not a promise. Every connector declares a
mode and the platform enforces what that mode allows:

| Mode | Sources | Behavior |
|---|---|---|
| `OFFICIAL_API` | Greenhouse, Lever, Ashby, SmartRecruiters, Adzuna, Jooble | Documented public APIs, rate-limited, honest User-Agent |
| `PUBLIC_FEED` | Dice | Public search feed; read-only |
| `SEARCH_LINK` | LinkedIn, Indeed, Monster, ZipRecruiter | **Never scraped.** Compliant search URLs + CSV export for manual applying |
| `USER_AUTHORIZED_AUTOMATION` | ATS form autofill | Reserved; disabled in this release |

JobPilot never evades bot detection, never solves CAPTCHAs, and
`POST /applications/{id}/apply` refuses (409 + manual link) for any source
whose mode forbids automation — with the decision audited.

## Scheduled automation

Managed in **Admin → schedules** (cron, America/Chicago by default):

| Task | Default | What it does |
|---|---|---|
| `ingest.full` | 6:00 AM daily | full sweep of all sources + scoring |
| `ingest.incremental` | 8 AM–6 PM, every 2h | recent postings only |
| `report.daily` | 9:00 PM daily | per-user email/Slack/Discord report |
| `analytics.weekly` | Sunday 6 PM | metrics snapshot for trend history |

Every execution is recorded in run history (status, stats, errors) —
**Admin → runs**.

## Testing & CI

```bash
cd backend && pytest                 # 67 tests; boots a throwaway real PostgreSQL
pytest --cov=app                     # ~87% line coverage
ruff check app tests && lint-imports # style + module-boundary contracts

cd frontend && npm test              # Vitest + Testing Library
npm run build                        # strict TS + production build
```

GitHub Actions ([.github/workflows/ci.yml](.github/workflows/ci.yml)) runs
the backend suite against a real pgvector Postgres with Alembic migrations,
the frontend build/tests, `docker compose config` validation, and full image
builds on every push.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `/api/v1/health/ready` says `degraded` | It names the dependency that's down (`database`/`redis`) — check `docker compose ps` |
| "Task queue unavailable" on Run new search | Worker/Redis not running — `docker compose up -d worker redis` (local dev: start Redis + the Celery worker) |
| Daily report shows SKIPPED | SMTP not configured — set the `JOBPILOT_SMTP_*` vars and restart |
| No jobs found | Check Preferences titles aren't too narrow; check **Admin → runs** for connector errors; Dice needs no key, aggregators do |
| AI features feel "basic" | No provider reachable — pull an Ollama model or add any API key; everything still works deterministically |
| Login loops after backend restart with new `JWT_SECRET` | Old tokens are invalid by design — log in again |

## Status & honest limitations

- **Auto-submission is gated, not enabled.** Sources permitting automation
  return an explicit 501 (never a fake "applied"); all others get the manual
  queue with your generated documents and a direct link.
- pgvector semantic search activates when an embedding model is configured;
  matching is fully functional on deterministic scoring without it.
- OAuth (Google/GitHub) endpoints are implemented and tested but return 501
  until you supply client credentials.
- Multi-user ready (roles + isolation are tested); sized for personal or
  small-group self-hosting.
