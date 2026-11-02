# Changelog

Meaningful implementation changes for SparkXFlow Nexus. Newest first.
Status labels match `REQUIREMENTS_TRACEABILITY.md`: Tested · Implemented ·
In Progress · Blocked · Deferred.

---

## 2026-11-02 — Baseline checkpoint (repository audit + security hardening)

First commit for this repository. Everything below existed as uncommitted work.

### Product foundation
- Read all five governing documents (`docs/PRD.md`, `docs/DESIGN.md`,
  `docs/architecture.md`, `docs/database-schema.md`,
  `docs/implementation-roadmap.md`) and produced the tracking set:
  `PROJECT_STATUS.md`, `DECISIONS.md`, `REQUIREMENTS_TRACEABILITY.md`,
  `IMPLEMENTATION_PLAN.md`.
- Eight product/technical decisions approved and recorded (D1–D8): India-first,
  email+password auth, SearXNG primary with OSM/Overpass supplementary,
  local-first execution, one-way Sheets export, vertical-slice-first.

### Backend — FastAPI modular monolith
- Application factory with lifespan, settings validation that refuses to boot a
  misconfigured production instance, structured JSON logging with request
  correlation IDs, and a single error envelope for framework and domain errors.
- Async SQLAlchemy 2.0 session management and a session-scoped transaction helper.
- Argon2id password hashing, opaque session tokens stored as SHA-256 digests,
  HMAC sign/unsign helpers for CSRF tokens.
- Celery application behind a runner-agnostic `TaskDispatcher` protocol, plus a
  `SynchronousDispatcher` so development continues without a broker.
- 37 ORM models across auth, sources, discovery, businesses, CRM, service
  catalogue, exports and system tables, with the CHECK constraints and indexes
  from `database-schema.md` §20–21.
- Alembic wired async-aware; revision `0001_extensions` installs `pgcrypto` and
  `pg_trgm`. **`0002_initial_schema` is Blocked — needs a live PostgreSQL.**

### Discovery pipeline (Phase 3 work, built ahead of sequence)
- Adapter contract with capability declaration and an honest error taxonomy
  (`access_denied`, `rate_limited`, `unsupported_query`, `malformed_response`).
- SearXNG adapter: pagination, request accounting, JSON-format detection, health
  probe distinguishing "up but serving HTML" from "down".
- Overpass adapter: radius/bbox query building, element mapping, unnamed elements
  dropped, attribution URLs preserved, refuses place-name-only searches.
- Eight-stage pipeline `Discover → Normalize → Validate → Deduplicate → Enrich →
  Score → Store → Report` against a `BusinessStore` protocol.
- Deduplication classification: confirmed auto-merge; probable/possible become a
  review backlog. Provenance transfers from the merged-away record.
- Normalisation: E.164 phone with country-aware parsing, eTLD+1 domain, canonical
  business name, order-independent fingerprints.
- Deterministic scoring evaluator returning per-rule contributions, missing
  signals and confidence. AI annotates scores; it does not create them.
- Canonical observation vocabulary in `shared/signals.py` — a signal is an
  observation, never a claim about reality; `None` is never coerced to `False`.
- CSV export with fixed column order, provenance columns included, and
  spreadsheet-formula neutralisation.

### Frontend
- Next.js 16 + TypeScript + Tailwind v4 app shell.
- Design tokens for both themes from `DESIGN.md` §2.1, 4 px spacing scale,
  visible focus states, reduced-motion support.
- Collapsible sidebar that renders unbuilt modules as disabled rather than
  linking to empty pages; live backend-status header; theme switching.
- Dashboard renders real readiness state and an explicit empty state instead of
  fabricated metrics.

### Security review (15 findings, all fixed, 42 regression tests)
High: Overpass QL injection; missing SSRF gate for discovered URLs.
Medium: unbounded query fan-out; attacker text stored verbatim; no field-length
bounds; unvalidated reflected correlation ID; provenance lost on merge;
login enumeration oracle; wildcard CORS with credentialed cookies.
Low: runaway configuration accepted; negative/NaN scoring weights; writable
container source mounts; unpinned redirect behaviour; path-smuggling in service
base URLs; SearXNG crash-looping on an empty secret.
See `PROJECT_STATUS.md` §1 for the finding table and `DECISIONS.md` D-030…D-035.

### Verification (this commit)
| Gate | Result |
|---|---|
| `pytest` | 139 passed |
| `ruff check` | clean |
| `mypy app` | clean, 53 source files |
| `eslint` | clean |
| `tsc --noEmit` | clean |
| `next build` | success, `/` and `/dashboard` prerendered |

### Tooling
- `uv`-managed Python 3.12 with `uv.lock`; 10 PowerShell dev/ops scripts;
  `docker-compose.yml` for Postgres, Redis, SearXNG, API and worker with memory
  caps and loopback-only port bindings; README; `docs/RUNBOOK-DOCKER.md` with the
  Windows-native fallback.

### Not done, and why
- PostgreSQL and Redis are not running; Docker Desktop needs administrator rights
  and a reboot, neither available to this session. Migrations, auth endpoints,
  the SQLAlchemy store and every live source call are Blocked on that.
- No auth endpoints, no rate limiting, no CSRF enforcement, no CSP, no audit
  writes, no live adapter verification, and 16 moderate npm advisories untriaged.
