# JobPilot backend

FastAPI + SQLAlchemy 2 + Alembic + Celery. See [`../docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md).

## Local setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env                    # edit as needed

# with Postgres (pgvector) + Redis running (docker compose up db redis — Phase 12):
alembic upgrade head                    # applies db/schema.sql as revision 0001

uvicorn app.main:app --reload           # API on :8000, docs at /api/v1/docs
celery -A app.worker.celery_app worker -l info    # background workers
celery -A app.worker.celery_app beat -l info      # cron emitter (one instance only)
```

## Quality gates

```bash
pytest              # unit + API tests
ruff check app tests
lint-imports        # module boundary contracts
```

## Layout

```
app/
├── main.py          # FastAPI factory; mounts every module router under /api/v1
├── core/            # settings, db engines, errors (RFC-7807), logging, crypto
├── common/          # pagination envelope, audit trail
├── worker/          # Celery app + beat schedule (America/Chicago)
├── health/          # liveness + readiness probes
└── <feature>/       # auth, user, resume, connector, ingestion, ai, matching,
                     # generation, application, assistant, analytics,
                     # notification, scheduler, admin — each: router.py,
                     # api.py (public facade), service/models/schemas as built
alembic/             # migrations; 0001 = canonical Phase 2 schema
```

Module boundaries are enforced: feature modules may only import each other via
`api.py` facades, and `core`/`common` never import features (`lint-imports`).
