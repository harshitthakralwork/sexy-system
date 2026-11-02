# SparkXFlow Nexus — Implementation Plan

**Project:** SparkXFlow Nexus
**Derived from:** `docs/PRD.md`, `docs/DESIGN.md`, `docs/architecture.md`, `docs/database-schema.md`, `docs/implementation-roadmap.md` (all v1.0)
**Plan version:** 1.0
**Date:** 2026-11-02
**Owner:** Harshit
**Execution model (decided):** Local-first, cloud-ready. Advanced hybrid worker dispatch deferred.

---

## 1. Approved decisions

These were decided on 2026-11-02 and are authoritative for implementation.

| # | Area | Decision |
|---|---|---|
| D1 | Environment | Docker Desktop is the primary local infrastructure path. It is technically supported by this machine but cannot install silently (no elevation, reboot required). A documented Windows-native fallback must exist so the project is never blocked. |
| D2 | Geography | India-first. Data model and adapters must not encode India assumptions in a way that blocks other countries/regions. |
| D3 | Authentication | Email + password with Argon2id hashing and server-side session records. No plaintext, no auth-free mode. |
| D4 | Discovery sources | SearXNG (search) primary; OSM/Overpass (geographic) supplementary; permitted public website crawler (enrichment). No exclusive dependence on OSM or Google Maps. |
| D5 | Execution | Local-first. Keep `execution_target` on jobs and a runner-agnostic task interface, but defer capability-based hybrid dispatch. |
| D6 | Google Sheets | One-way export only. Two-way sync deferred. |
| D7 | First deliverable | Vertical slice: source → discovery → normalization → database → results table → business profile → shortlist → CSV export. |
| D8 | Trust rules | Transparent source attribution, evidence-based scoring foundations, retention rules enforced, honest source-failure reporting. No fabricated data anywhere. |

## 2. Environment findings (2026-11-02)

| Check | Result | Consequence |
|---|---|---|
| OS | Windows 11 Pro, build 26300 | Docker Desktop supported |
| CPU | 6 physical / 12 logical | Sufficient |
| RAM | 15.8 GB total, **2.1 GB free** | Tight. Stack needs ~4–6 GB. Background apps must be closed before running containers. |
| Virtualization | Firmware enabled, SLAT supported | Container backend viable |
| Hypervisor | **Not present** | Enabling Virtual Machine Platform / WSL2 requires a reboot |
| Shell elevation | **Not administrator** | Docker Desktop cannot be installed from this session |
| Docker | Not installed | Infrastructure unavailable until D1 install step completes |
| WSL | Binary present, not installed | Same reboot requirement |
| PostgreSQL | Not installed (no binary, no service) | DB-dependent work blocked until D1 |
| Redis | Not installed | Job runner blocked until D1 |
| Python | 3.15.1 only | Too new for SQLAlchemy/Celery/Playwright wheels → provision 3.12 via `uv` |
| Node | v24.21.0 + npm 11.19.0 | Frontend unblocked |
| Disk | C: 26.2 GB free, D: 58.5 GB free | Project on D:. Docker image/WSL data must be relocated to D: before install |

**Blocking assessment:** Phase 0 acceptance criteria do not require PostgreSQL or Redis. Phase 0 can complete fully. Phase 1 (Core foundation) requires D1 to be executed.

## 3. Technical decisions made by the agent

Decisions not covered by the five documents, made under the standing approval.

| Area | Decision | Reason |
|---|---|---|
| Python env | `uv` with managed CPython 3.12, installed user-level | Python 3.15 wheel support is immature; user-level install needs no admin |
| Job runner | Celery, behind a `TaskDispatcher` interface | `architecture.md` §3.2 prefers Celery and requires runner independence |
| Windows fallback for jobs | Celery `--pool=solo` / `threads` against a local Redis | Prefork pool is unsupported on Windows; documented rather than silent |
| Postgres access | SQLAlchemy 2.0 async + asyncpg | Matches async FastAPI; keeps one execution model |
| Password hashing | Argon2id via `argon2-cffi` | Current default for new systems |
| Sessions | Opaque random token, hash stored in `user_sessions`, HttpOnly SameSite cookie | `database-schema.md` §5.3 stores a token hash |
| Migrations | Alembic, autogenerate off in CI, hand-reviewed | `database-schema.md` §23 |
| Frontend data | TanStack Query only; no server data in global stores | `architecture.md` §5 |
| API contract | OpenAPI from FastAPI; Pydantic v2 schemas; `/api/v1` | No contract existed in the docs; derived here |
| Validation | Zod on client mirroring Pydantic on server | Both stacks already chosen |
| Maps | Leaflet via `react-leaflet`, clustering deferred to Phase 2b | Tile cost/limits noted in `architecture.md` §3.4 |
| Scoring | Deterministic rule evaluator with stored profile version; AI only annotates | `architecture.md` §12 requires a deterministic fallback |
| Phone/domain normalisation | `phonenumbers` with region default `IN` (configurable), `tldextract` for eTLD+1 | Dedup depends on deterministic normalisation; India-first per D2 |
| Correlation IDs | `X-Correlation-ID` propagated into Celery headers and log lines | `architecture.md` §20 |
| Retention | Single retention worker; shortlisted/qualified records excluded by SQL predicate, not application convention | `database-schema.md` §19.3 |
| Git layout | `sparkxflow-nexus` is its own repository; parent clone excludes it locally via `.git/info/exclude` | Prevents the project being committed into the third-party AgencyAgents clone |

## 4. Phase 0 — Project understanding and setup

Deliverables and how they map to `implementation-roadmap.md` §3.

| Deliverable | Location | Status |
|---|---|---|
| Git repository + `.gitignore` | `sparkxflow-nexus/.gitignore` | Done — no commit made yet |
| Frontend structure | `sparkxflow-nexus/frontend` | Done |
| Backend structure | `sparkxflow-nexus/backend` | Done |
| Dependency configuration | `backend/pyproject.toml`, `backend/uv.lock`, `frontend/package.json` | Done |
| `.env.example` (names only) | `sparkxflow-nexus/.env.example` | Done |
| README with setup | `sparkxflow-nexus/README.md` | Done |
| Dev scripts | `sparkxflow-nexus/scripts/*.ps1` | Done — 10 scripts |
| Migration setup | `backend/migrations`, `backend/alembic.ini` | Done — schema revision needs a live database |
| Testing + linting config | `ruff`, `mypy`, `pytest` in `pyproject.toml`; `eslint`/`tsconfig` | Done — all green |
| Progress tracker | `sparkxflow-nexus/PROJECT_STATUS.md` | Done |
| Windows local dev instructions | `README.md` (First run / Scripts) | Done |
| Docker install procedure + fallback | `docs/RUNBOOK-DOCKER.md` | Done |
| Requirements traceability checklist | `REQUIREMENTS_TRACEABILITY.md` (repo root, per master prompt §13) | Done |

**Acceptance criteria (roadmap §3):** frontend starts, backend starts, configuration documented, no secrets committed, structure follows `architecture.md`, traceable plan exists.

## 5. Phase 1 — Core foundation

Blocked on D1 (Docker Desktop) for PostgreSQL and Redis. Not blocked for: auth, app shell, design system, logging, health checks, Source Manager foundation.

Order once infrastructure exists:
1. Postgres + Redis reachable, migrations run.
2. Auth (register/login/session/logout), seeded single user for local dev.
3. Job infrastructure + `discovery_jobs` status endpoints.
4. Design system components + shell + theme.
5. Source Manager displaying real source registry rows.
6. Backup foundation (scheduled `pg_dump` locally).

## 6. Phase 2 — Vertical slice, then breadth

**2a — Thin working slice (the approved D7 path):**
`SearXNG adapter → discovery job → source_records → normalization → businesses → results table → business profile → shortlist → CSV export`

This slice must run end-to-end against real network sources with visible provenance. It is the point where the India-first data-coverage risk becomes measurable rather than theoretical.

**2b — Breadth, only after 2a works:**
Map Explorer, dedup review queue, Service Catalog + scoring rules, CRM Kanban, filters/bulk actions, Overpass adapter, crawler enrichment adapter.

## 7. Deferred with documented reason

| Item | Roadmap location | Reason |
|---|---|---|
| Hybrid local/cloud worker dispatch, worker registration, heartbeats | `architecture.md` §8.3–8.4 | No cloud deployment exists. `execution_target` column and runner-agnostic interface are kept so this is additive later. |
| Google Sheets two-way sync | PRD §7.8 | Conflict-prone and quota-limited; one-way export satisfies MVP. |
| Playwright-based browser automation in cloud | `architecture.md` §3.2 | Free containers lack RAM; datacenter IPs get blocked, and circumvention is forbidden by D8/PRD §17. |
| PostGIS | `database-schema.md` §21 | Radius queries can use haversine SQL at MVP volumes. |
| Dedicated search engine | `architecture.md` §17 | Postgres FTS + trigrams is the specified start. |
| Multi-tenancy / org model | PRD §4 | `owner_user_id` present on every owned table; single user for now. |
| Auto-send email | PRD §9 | Approval gate required. |
| Startup Intelligence tables | `database-schema.md` §24 | Phase 5. |
| Social Intelligence tables | `database-schema.md` §24 | Phase 3. |

## 8. Open risks

| Risk | Impact | Mitigation |
|---|---|---|
| Free RAM is 2.1 GB | Containers will thrash or fail to start | Close Discord/Chrome/CamoStudio before running the stack; cap container memory in compose |
| C: has 26 GB free | Docker + WSL2 VHDX will fill the system drive | Relocate Docker/WSL data to D: as part of the install procedure |
| Reboot required | Interrupts this session | Schedule the install deliberately; scaffold does not depend on it |
| OSM/Overpass India coverage thin | MVP finds fewer businesses than expected, looks broken | Measured at 2a; SearXNG + crawler carry the load per D4 |
| Python 3.15 on PATH | Silent resolver conflicts | Project pinned to `uv`-managed 3.12; never use system Python |
| SearXNG public instances rate-limit | Flaky discovery | Self-hosted instance in compose; adapter reports failure honestly per D8 |

---

**End of implementation plan v1.0**
