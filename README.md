# SparkXFlow Nexus

Business & Market Intelligence platform: discovers businesses, researches them from
permitted public sources, scores them against configurable services, and manages the
resulting leads.

**Status:** Phase 0 complete-ish — see [PROJECT_STATUS.md](PROJECT_STATUS.md).
**Specifications:** [docs/](docs) (PRD, design, architecture, database schema, roadmap). Those five
documents plus [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) are the source of truth.

---

## What is here

```
sparkxflow-nexus/
├── backend/          FastAPI modular monolith (Python 3.12, uv)
│   ├── app/core/       config, logging, database, security, exceptions, middleware
│   ├── app/modules/    auth, sources, discovery, businesses, crm, services_catalog, exports, notifications, health
│   ├── app/shared/     normalisation + deterministic scoring (the tested core)
│   ├── app/workers/    Celery app and the runner-agnostic dispatcher
│   └── migrations/     Alembic
├── frontend/         Next.js + TypeScript + Tailwind
├── infra/searxng/    self-hosted discovery engine config
├── scripts/          Windows PowerShell dev/ops entry points
├── docs/             specifications + runbooks
├── docker-compose.yml
└── .env.example
```

## First run

```powershell
./scripts/bootstrap.ps1      # creates .env, installs both toolchains
```

Then set two values in `.env` (`SPARKX_SIGNING_SECRET`, `SEARXNG_SECRET`), and start
infrastructure. Docker Desktop must be installed first — see
[docs/RUNBOOK-DOCKER.md](docs/RUNBOOK-DOCKER.md), which also covers the Windows-native
fallback if you cannot install it.

```powershell
./scripts/infra-up.ps1       # postgres, redis, searxng
./scripts/db-migrate.ps1     # alembic upgrade head
./scripts/dev-backend.ps1    # API on http://127.0.0.1:8000  (docs at /docs)
./scripts/dev-frontend.ps1   # UI  on http://localhost:3000
./scripts/dev-worker.ps1     # background job worker
```

## Scripts

| Script | Does |
|---|---|
| `bootstrap.ps1` | Create `.env`, install backend and frontend dependencies |
| `infra-up.ps1` / `infra-down.ps1` | Start/stop Postgres, Redis, SearXNG (`-Purge` deletes volumes) |
| `db-migrate.ps1` | Apply pending migrations |
| `db-revision.ps1 -Message "..."` | Autogenerate a migration — always review the output |
| `dev-backend.ps1` | Uvicorn with reload |
| `dev-frontend.ps1` | Next.js dev server |
| `dev-worker.ps1` | Celery worker (`--pool solo`, see runbook) |
| `test.ps1` | ruff + mypy + pytest + eslint + tsc |

## Checks without any infrastructure

The Phase 0 suite deliberately avoids the database, so it runs on a bare machine:

```powershell
cd backend
python -m uv run pytest
```

41 tests cover email/phone/domain/name normalisation, the deterministic scoring
evaluator, configuration validation, and the health/correlation/error-envelope
behaviour of the API.

## Conventions that are not negotiable

These come from the specifications and are enforced by how the code is written.

- **No fabricated data.** Scores, metrics and search results derive from stored
  records. A source that failed is reported as failed.
- **Provenance on everything collected.** Raw payloads stay in `source_records`;
  normalised entities link back to them.
- **Extraction is not verification.** A scraped email is `unverified` until
  independently confirmed.
- **AI is optional and never gates a score.** Scoring is a deterministic rule
  evaluator so any result can be re-derived.
- **Retention protects shortlisted records** at the SQL predicate level, not by
  application convention.
- **Secrets stay out of the repo, the DB, and the browser bundle.**

## Requirements not yet built

Auth flow, source adapters, discovery pipeline, map, CRM UI, exports, scheduler.
Phase order and blockers are tracked in [PROJECT_STATUS.md](PROJECT_STATUS.md).
