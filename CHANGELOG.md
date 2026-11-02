# Changelog

Meaningful implementation changes for SparkXFlow Nexus. Newest first.
Status labels match `REQUIREMENTS_TRACEABILITY.md`: Tested · Implemented ·
In Progress · Blocked · Deferred.

---

## 2026-11-03 (Master plan #27) — Analytics and Reports

The next genuinely-incomplete roadmap task after Global Search. No new third-party
dependency, no new framework, and the only new table is additive.

### What changed

- **New `analytics` module** — `app/modules/analytics/`. `GET /api/v1/analytics` runs nine
  `GROUP BY` aggregates over the operator's own rows: leads by website status and by
  lifecycle, CRM by stage (record joined to stage), opportunities by status, discovery jobs
  by status, social results by classification / source platform / track type, and startups by
  funding stage, plus `leads_total` from non-deleted businesses. Every surface that already
  existed is counted through its own model — nothing is read from a fixture, and a surface
  with no rows returns an empty list rather than a zero that looks like a finding.
- **`saved_reports`** (migration `ef461cd22fb6`, additive) — name, description,
  `report_type` CHECK-constrained to `analytics|leads|social|startups`, a `snapshot` JSONB
  and `captured_at`. `POST/GET/DELETE /analytics/reports` plus
  `/analytics/reports/{id}/export`. A report stores the summary **as it was at capture**, so
  it does not silently drift when new leads arrive; that is asserted by test.
- **CSV export** — `GET /analytics/export` flattens the same summary to
  `section,key,count`, and a saved report exports its own snapshot. Audited as
  `export.create`; the `report.saved` / `report.deleted` audit actions were added to the
  registry so these writes are traceable like every other sensitive one.
- **Frontend `/analytics`** — leads total, nine bucket cards whose bars are scaled from the
  real counts (each card links to the surface it counts, reusing the Social engine's
  classifications and the leads/CRM/startups rows), Export CSV, and a Saved reports panel to
  capture / list / export / delete. The sidebar's Analytics entry is enabled, and Reports now
  anchors to the saved-reports panel instead of pointing at a route that does not exist.
- **`/api/v1/info`** reports `analytics` among enabled modules.
- **Dashboard corrected — it was lying.** `/dashboard` had a "Leads Intelligence" panel
  hard-coded to *"No businesses discovered yet — Discovery is being wired to the database"*,
  written when that was true and never revisited. The operator now has 29 real leads, so the
  screen asserted the opposite of the database. It reads the same `/analytics` aggregate as
  the Analytics page — leads, discovery jobs, social results and startups, each linking to its
  surface — and the "Nothing collected yet" state appears only when every one of those counts
  is genuinely zero.

### Tests + verification

- 10 new tests (real PostgreSQL): empty account → no numbers; seeded quantities asserted
  bucket-for-bucket; soft-deleted leads excluded from every lead figure; CRM and opportunity
  counts produced through the product's own shortlist/qualify routes; CSV mirrors the JSON;
  snapshot captured then proven non-drifting; unknown report type falls back, blank name 422;
  POST without CSRF refused; list/pagination; and full cross-owner isolation on read, export
  and delete.
- Backend **388 passed**; ruff clean; mypy clean across 115 source files;
  `alembic check` reports no drift at head `ef461cd22fb6`.
- Frontend tsc / eslint / `next build` clean; `/analytics` prerenders.
- **Browser-verified against the operator's real data**: 29 leads, 29 unknown-website,
  29 active, CRM Qualified 1, opportunities candidate 1, jobs completed 6 + failed 4,
  social classification 36 + 6 + 5 + 3 = 50, source hackernews 50, track demand 50,
  startups 1. Saved "Milestone check 2026-11-03" (snapshot 29 leads), then exported both the
  live and the report CSV over HTTP — 200, `text/csv`, 15 rows, `leads_total,,29` — and
  confirmed `report.saved` and `export.create` landed in `audit_logs`.
- **Dashboard browser-verified**: Leads 29 (active 29 · archived 0), Discovery jobs 10
  (completed 6 · failed 4), Social results 50 (36 unclassified), Startups 1 — identical to
  `/analytics`, beside the real system status (Database Up, Redis Down `TimeoutError`,
  Worker Up, 13 modules mounted, AI disabled).

Deferred honestly: no scheduled report generation, no PDF/Excel renderer, no time-series
trends (a snapshot records one instant; charting across captures needs a reader over
`captured_at`), and no startup side-by-side comparison. The `Content-Disposition` filename
is not readable through a cross-origin fetch, which affects only a programmatic reader —
clicking an export link still downloads with the right name.

---

## 2026-11-03 (Master plan) — Global Search across every owned entity

Returned to the original roadmap (after the Social & Demand Engine directive) with
the first genuinely-incomplete master-plan task: **#26 Global Search**.

### What changed

- **New `search` module** — `GET /api/v1/search?q=&limit=&offset=` aggregates one
  ILIKE query across five owned surfaces, calling the **existing** list functions
  rather than re-implementing search: businesses (`list_businesses`), startups
  (`list_startups`), social intelligence results and saved items
  (`social.tracks.list_intelligence`), and discovery tracks (a small name/keywords
  query). Results come back grouped with each group's own total; the only aggregate
  reported is the sum of those totals — no invented ranking. Ownership is enforced by
  the reused functions (every one is owner-scoped), so cross-entity search cannot leak.
- **Frontend** — `/search` page (query box + grouped result cards, each hit linking
  to its real destination: a lead, a startup, the intelligence/saved/track views);
  the header's stale "Global search — Phase 2" placeholder is replaced with a working
  link; the nav entry is enabled.
- **`/api/v1/info`** now reports `search` among enabled modules.

### Tests + verification

- 3 new tests (real PostgreSQL): a single query reaches all seeded entities, empty
  query returns nothing, and cross-owner isolation (another user finds none of it).
- Backend **378 passed**; ruff + mypy clean (110 files). Frontend tsc/eslint/next build
  clean; `/search` prerenders.
- **Browser-verified live**: searching "agency" returned the discovery track by name
  via the real backend and rendered as a "Discovery tracks · 1" group card.

Deferred honestly: this is entity-level text search over the owner's own data (ILIKE),
matching the existing convention — Postgres full-text/tsvector and relevance ranking
are not introduced, and the engine's intelligence results remain the highest-value
searchable surface.

---

## 2026-11-03 (Social & Demand Intelligence Engine) — two tracks, keyless connectors, deterministic classification

A separate standing directive, built inside the existing `social` module — no new
competing package, no redesign — reusing auth/CSRF/audit/ownership, SSRF,
normalisation, dedup, notifications, the Businesses model, the source registry, the
dispatcher and the automation recurrence maths.

### What changed

- **Schema** — migrations `9fd5409a50ff` + `c2f7937c920d`: `social_search_tracks`
  (Demand | Business, keyword/phrase/exclusion/hashtag vocabulary, platform selection,
  language/geography/date range, interval-or-cron schedule, `source_config`),
  `social_discovery_runs` (per-run observability incl. `completed_with_warnings` and
  distinct discovered/returned/stored/duplicate counts), `social_saved_items`,
  `social_classification_history`, and nullable intelligence columns on `social_content`
  (retrieval_status kept separate from classification, plus confidence, evidence,
  matched_terms, signals, dedup fingerprint, cross-source attribution).
- **Connectors (keyless, free-first)** — Hacker News (Algolia), RSS/Atom (stdlib XML,
  DTD-refused, SSRF-guarded), SearXNG indexed-snippets, Stack Overflow, Bluesky,
  Mastodon, alongside Reddit. Each declares honest capabilities; a refusal is reported,
  never worked around.
- **Classification** — a transparent rule engine: confidence only rises on an *intent*
  phrase, a bare keyword is demoted to discussion, tutorial/news/job-seeker context
  lowers it; evidence + method + rule version are stored; optional local-Ollama hook is
  never mandatory and there is no paid fallback. `pipeline.py` normalises, dedups within
  and across sources (attribution preserved) and classifies.
- **Background** — idempotent pending-claim run with per-source failure isolation (a
  refused source yields `completed_with_warnings`, the rest still persist); inline in dev,
  Celery + beat in prod; reuses the automation recurrence.
- **UI** — `/intelligence` Overview (real counts only), Demand & Business result browsers
  with filters/evidence/source links/save/CSV export, Discovery Tracks, Saved Items, and a
  read-only `/social/sources`.
- **Integration** — high-confidence demand → in-app `Notification` (deduped, no email);
  convert-result-to-lead reuses `Business` with owner+domain dedup + provenance link and
  refuses without a real entity; JSON export; `/social/notifications`.

### Verification

- **Live source**: created a Demand track and ran it against real Hacker News — 50 live
  posts stored and classified (Freelancer Hiring 5 / Service Needed 3 / General
  Discussion 6 / Unclassified 36); Demand filtered by confidence (6 ≥ 50); one saved
  surfaced in Saved + Overview; Sources renders 12 connectors honestly.
- 44 new tests (schema/connectors/pipeline/runs/integration); **375 backend tests pass**;
  ruff + mypy clean (106 files); `next build` ok; `alembic check` drift-free (66 tables).

### Honest limits

No dedicated Global Search module or full Analytics/Reports yet (separate master-plan
phases; the engine exposes a queryable results endpoint for a future search to consume).
SearXNG needs a running instance (absent here) and Reddit's public JSON is 403 from this
client — both reported, not faked. Paid/credentialed connectors (X, YouTube Data API,
LinkedIn partner API) are left unimplemented; LinkedIn public snippets are reachable only
via the SearXNG indexed-snippet path. The Celery queued path and beat tick are tested but
not live-run (no Redis).

---

## 2026-11-03 (Automation Engine) — workflows, recurring schedules, approval-gated email

Phase 5 of full product completion. The automation engine is two modules that share
the auth/CSRF/audit/ownership infrastructure: `automation` runs versioned step
workflows and recurring schedules; `email` holds accounts, campaigns, the message
lifecycle, events and a suppression list. Sending is approval-gated and refuses
without a connected, configured account — there is no dry-run that reports success.

### What changed

- **Schema** — 10 tables in migration `682d9e15b781`: `workflows`,
  `workflow_executions`, `workflow_step_executions`, `schedules`, `workflow_approvals`,
  `email_accounts`, `campaigns`, `email_messages`, `email_events`, `suppression_list`,
  with status/step-type CHECK constraints, owner-scoped unique indexes and cascade FKs.
  `email_accounts` stores a `secret_reference` only; the spec's `encrypted_credentials`
  column is deliberately omitted in favour of an external secret manager.
- **Step engine** — a `pending`-claim idempotent runner executes `qualify` → `shortlist`
  → `email_draft` → `send` in order, committing one `workflow_step_executions` row per
  step. `qualify` calls the real services-catalog scorer, `shortlist` the real CRM
  repository, `email_draft` renders a deterministic draft from the business's actual
  website state and raises an approval gate, and `send` only sends approved,
  un-suppressed messages attached to a connected account.
- **Recurrence** — a custom five-field cron parser (interval or cron, no new
  dependency) stores `next_run_at` rather than deriving it; `tick_schedules` is
  registered for Celery beat.
- **Providers** — an `EmailProvider` protocol with an SMTP implementation and a
  Gmail-OAuth implementation that reports itself unconfigured until credentials exist.
- **API** — 32 owner-scoped routes across `/workflows` and `/email` (workflow/schedule/
  account/campaign/suppression CRUD, run-now, execution history with step detail,
  approval review, message create/approve/send and event listing), CSRF-gated with audit
  writes on state changes.
- **Frontend** — `/automation/workflows`, `/automation/scheduler`,
  `/automation/approvals` and `/email` workspaces, navigation enabled, existing purple
  design system and routing conventions preserved.

### Bugs fixed

- **`/workflows/approvals` returned 422** — `GET /{workflow_id}` was registered ahead of
  the static routes and FastAPI matches in order, so the UUID converter rejected
  "approvals". Static sub-resource routes moved before the dynamic one.
- **mypy `Incompatible types in assignment`** in `list_approvals` — annotated the
  accumulating `where` as `ColumnElement[bool]`.

### Deferred

- **Live SMTP delivery and Gmail OAuth** — the send path is proven to the provider
  boundary (and its refusals) but no mail server/credentials exist here, so no real
  delivery is claimed.
- **Celery queued path and the beat-driven schedule tick** — configured and tested;
  Redis is absent, so "run now" executes the same engine inline.

### Verification

- Browser-verified against real PostgreSQL: workflow created (201), run inline to
  `completed` with its `shortlist` step `completed`; schedule created with `next_run_at`
  computed; email draft → approve → **send honestly reported "blocked: no sending
  account"**; approval queue rendered.
- 331 backend tests pass (36 new: 21 `test_automation.py` + 15 `test_email.py`); ruff and
  mypy clean (102 files); `next build` succeeds; `alembic upgrade head` + `check`
  drift-free (62 tables, 43 named CHECKs, 67 FKs).

---

## 2026-11-03 (Social Intelligence) — honest platform catalogue, Reddit research, content workspace

Phase 4 of full product completion. Social Intelligence shares the
auth/CSRF/audit/ownership infrastructure, and is honest about what each platform's
permitted public access actually allows: only Reddit offers a key-free method, so only
Reddit is enabled.

### What changed

- **Schema** — 4 tables (`social_platforms`, `social_profiles`, `social_content`,
  `social_research_queries`) in migration `6dbf1bf0e71c`, with a content-type CHECK and
  unique owner/platform/external-id indexes so re-runs deduplicate instead of duplicating.
- **Platform catalogue** — `PLATFORM_DEFINITIONS` states each platform's real access
  terms. LinkedIn/Instagram/Facebook/X/YouTube are disabled with their terms stated;
  Reddit is enabled via its unauthenticated public JSON.
- **Reddit adapter** — validates query kind/sort/limit, one request per run,
  `follow_redirects=False`, descriptive User-Agent; maps 429/401/403/400 to distinct
  adapter errors; health check endpoint.
- **API** — 13 owner-scoped routes under `/social` (platforms, research-query CRUD +
  run, content list/filter/export, delete, link-to-business), CSRF-gated, with audit
  writes on run and link.
- **Frontend** — `/social` workspace: platform catalogue, create-query form, query list
  with run/delete and honest last-run status, collected-content table with filters,
  CSV export, per-row delete and link-to-business. Navigation enables the section.

### Bug fixed

- **Response schemas could not be built by `model_validate`** — `SocialResearchQueryOut`
  and `SocialContentOut` carry `platform_slug`/`author_username` that live on joined
  rows, not the ORM object, so the router now constructs them explicitly.
- **`link_content_to_business` read a non-existent column** (`content.author_username`);
  it now resolves the `SocialProfile` via `profile_id`.
- **`SourceUnavailableError` called with one argument** in three places; fixed to the
  `(source_slug, reason)` signature.

### Deferred

- **Live Reddit collection** — the full path is tested against a mocked transport and
  browser-verified, but the live request returns 403 from this client. The UI reports
  that honestly rather than fabricating data.

### Verification

- Browser-verified against real PostgreSQL: catalogue rendered (6 platforms, Reddit
  "available", others "restricted"), query created, run returned the honest 403
  failure surfaced in the UI, delete removed the row.
- 295 backend tests pass (10 new in `test_social.py`); ruff and mypy clean (91 files);
  `next build` exit 0 with the new `/social` route.
- `alembic upgrade head` from empty: 8 revisions, 52 tables; `alembic check` clean;
  52/52 tables have a primary key.

---

## 2026-11-03 (Startup Intelligence) — 9-table schema, 21 routes, dashboard, profiles, watchlists

Phase 3 of full product completion. Startup Intelligence is its own module sharing the
auth/CSRF/audit/ownership infrastructure with Leads Intelligence, not a re-labelled
copy of it.

### What changed

- **Schema** — 9 tables (`startups`, founders, products, pricing, revenue records,
  competitors, research records, watchlists, watchlist items) in migration
  `a02df3cff960`, with CHECK constraints for the status vocabulary, non-negative
  amounts, the revenue-confidence range and no self-referencing competitor. Matches
  `database-schema.md` §13.
- **API** — 21 owner-scoped routes under `/startups` (CRUD for startups, founders,
  products, pricing, revenue, competitors, research, watchlists), CSRF-gated, with
  audit writes on create/delete/watchlist-create.
- **Revenue evidence classes enforced in code** — `verified`, `founder_reported`,
  `estimated`, `not_available`; `not_available` requires a null amount and `estimated`
  requires a methodology, so estimates cannot be stored as facts.
- **Competitor integrity** — self-reference rejected, duplicate pair is a 409.
- **Duplicate startup detection** — normalised domain; a second record on the same
  domain conflicts.
- **Frontend** — Startup dashboard (`/startups`, filter/search/paginate/create/delete),
  startup profile (`/startups/[id]` with overview, revenue, competitors, founders,
  products, research, watchlists) and a watchlists view (`/startups/watchlists`).
  Navigation enables both.

### Bug fixed

- **Serializing a just-flushed row raised `MissingGreenlet`.** Server-default timestamp
  columns are expired after `flush()`, so `model_validate` in sync context tried to
  lazily refresh them. Nine service functions now `await session.refresh()` after flush.

### Deferred

- **Startup discovery from configured sources.** The existing adapters are geographic
  (Overpass) and search (SearXNG); no startup-directory adapter exists yet. Product Hunt
  needs a key; Hacker News and GitHub are free candidates. `/startups/discover` stays
  disabled rather than a nonfunctional screen.
- **Report generation and company comparison** are not built yet; they are Phase 7
  (Analytics/Reports) work, recorded rather than implied.

### Verification

- Browser-verified against real PostgreSQL: dashboard create (Zerodha → normalised
  domain, status, source), founder add, and watchlist create all returned real rows.
- 285 backend tests pass (8 new in `test_startups.py`); ruff and mypy clean (84 files);
  `next build` exit 0 with routes `/startups`, `/startups/[id]`, `/startups/watchlists`.
- `alembic upgrade head` from empty: 7 revisions, 48 tables; `alembic check` clean;
  48/48 tables have a primary key.

---

## 2026-11-02 (Leads Intelligence UI) — table, profiles, qualification, CRM in the browser

Phase 2 frontend, closing the loop on the already-committed leads-intelligence
backend. A signed-in user can now discover businesses, view them in the standalone
Leads table, open profiles, qualify them against the service catalog, shortlist,
move them through the 12-stage CRM pipeline, add notes and tags, and export.

### What changed

- **Leads table** (`/leads`) — real rows with filters (query, city, website status,
  phone availability), 25-row pagination, per-row shortlist, and CSV export. The
  stage pill is fetched live per row, not faked.
- **Business profile** (`/leads/[id]`) — overview with provenance and contacts,
  archive/shortlist actions, a per-service qualification panel, CRM stage dropdown
  with the activity feed, notes, and tags. All actions POST/PUT to real endpoints
  with CSRF.
- **CRM board** (`/leads/crm`) — kanban columns for the 12 default stages, cards
  grouped by stage, per-card stage moves, and "Add stage".
- **Service catalog** (`/leads/services`) — service list with expandable
  detail (profiles + rules) and service creation.
- **Navigation** — Leads Dashboard, CRM Pipeline and Service Catalog are enabled;
  Analytics/Reports/Global Search/etc. remain disabled and labelled "not built yet".
- **`modules_enabled`** now reports `services_catalog` so the runtime info is honest.

### Bug fixed

- **CORS blocked every browser mutation.** `allow_headers` omitted `X-CSRF-Token`,
  so the preflight for any POST/PATCH/PUT/DELETE (which all send that header) was
  rejected and every state-changing button failed with "Failed to fetch" while GETs
  succeeded. Adding `X-CSRF-Token` to `allow_headers` unblocked qualify, shortlist,
  note, tag and stage-move.

### Verification

- Browser-verified against real PostgreSQL: qualify (score/status/evidence rendered),
  note (201), shortlist (200), stage move (200) — all confirmed in the backend log.
- 277 backend tests pass; ruff and mypy clean; `next build` exit 0 with routes
  `/leads`, `/leads/[id]`, `/leads/crm`, `/leads/services`, `/leads/map`.

---

## 2026-11-02 (Background execution) — jobs run exactly once, retry safely, recover

Phase 1 of full product completion. The queued-execution path (Celery + Redis)
already existed; this milestone closes the correctness gaps around it.

### What changed

- **Idempotent claim.** `job_service.claim_job` moves a job `queued/blocked/failed`
  → `running` with a single `UPDATE … RETURNING`; a duplicate Celery delivery or a
  re-submitted retry gets `None` and does not sweep the region twice. `runner.execute`
  now claims before running instead of reading and trusting the row.
- **Retry endpoint.** `POST /discovery/jobs/{id}/retry` re-queues a `failed`,
  `blocked` or `cancelled` job — never a `completed` one (re-querying shared
  infrastructure for nothing). Counters/timestamps reset; prior history stays in
  the job log and audit trail; `retry_count` is exposed on `JobOut`.
- **Stale-job recovery.** `job_service.recover_stale_jobs` marks jobs left in
  `running` past `stale_job_after_seconds` (default 6 h) as failed with a
  `stale` flag, so a worker that died mid-run leaves a retryable row instead of
  one stuck "running" forever. Published on a Celery beat schedule
  (`sparkxflow.maintenance.recover_stale_jobs`, every 10 min) and directly
  callable.
- **Worker readiness.** `/health/ready` now reports a third component, `worker`:
  `inline (API process)` under `SPARKX_RUN_JOBS_SYNCHRONOUSLY`, otherwise a
  Celery ping with a named failure when no worker answers.
- **Beat service.** `docker-compose.yml` gains a `beat` service running the
  schedule the worker executes.

### Verification

- 7 new tests in `tests/test_job_lifecycle.py`: duplicate delivery is a no-op,
  claim hands a job to exactly one worker, a failed job retries and runs again,
  retrying a completed job is refused (409), cross-user retry is 404, stale
  running jobs are failed, recent running jobs are untouched. 267 backend tests
  pass; ruff and mypy clean.

### Blocked

- **Redis/Celery live path not exercised.** This machine has no Docker or Redis,
  so the worker actually consuming a queued job, broker-redelivery after a crash,
  and beat firing on schedule are verified by configuration and tests only. The
  inline (synchronous) execution path is fully exercised. Live verification of the
  queued path is blocked on a Redis instance.

---

## 2026-11-02 (Map Intelligence) — D4 measurement, the bug it caught, and the map

### Live measurement (D4)

`scripts/d4_overpass_probe.py` ran controlled queries against the public Overpass
interpreter. Hisar, 5 km: **80 hospitals** (all named, all located, **2 with a
phone**, 8 with a website), 4 hotels, 2 restaurants, 0 gyms, 0 grocery shops.
Latency 36–45 s per successful query; **7 of 12 queries failed** with 502/504 or
an error page served under HTTP 200. Defaults (25 km² tiles, 40 per job, one
subdivision, 90 s timeout) were set from that, not from arithmetic.

### Defects found only by running it

- **Overpass QL the interpreter had never accepted.** The union block omitted the
  inner semicolon and the category was used as a tag *key*, so `cafe` matched
  nothing and the real endpoint answered `parse error: ';' expected`. Every
  mocked test had passed.
- **16 businesses stored as 3.** A record's provenance URL became its
  `normalized_domain`; a shared domain is a confirmed-duplicate key, so hospitals
  found on the same site merged, with their provenance folded in. Now identity
  requires a website the record itself declares (`website_hint`, set per source).
- **An inverted viewport bbox returned everything.** It parsed, failed validation
  quietly and the filter was dropped — an unbounded read behind a map control.
- **A circle re-ran as its own square.** Jobs stored only the bounding box, so a
  saved 3 km search silently widened. Geometry now round-trips as drawn.
- **Floating-point noise cost a row of tiles.** A region fitting exactly 4×4 was
  planned as 5×5 and, near the limit, refused.

### Backend

`search_areas` (validated, bounded, owner-scoped CRUD), deterministic grid tiling
with one batch per tile × source, truncation detection and subdivision, viewport
pin queries that report what they left out, selected-row export that names the
ids it refused, and source-record identity so a node seen in two tiles is one
business.

### Frontend

Map Intelligence at `/leads/map`: Leaflet with OSM attribution, radius / rectangle /
polygon drawing wired to real jobs, tile-state overlay, pixel-grid clustering,
marker previews that say "no rating reported" when nothing reported one, live job
and per-tile progress, saved areas, and one selection shared by pins and list.

### Verification

| Gate | Result |
|---|---|
| `pytest` | **260 passed**, 0 skipped (was 189) |
| `ruff` / `mypy` | Clean, 73 files |
| `tsc` / `eslint` / `next build` | Clean |
| Live source | One 1 km Hisar job stored 16 real records; a 3 km job failed on `ReadError` and reported it |
| Browser | Pins, selection sync and marker preview verified against the live records |

## 2026-11-02 (Phase 3) — Discovery jobs, and map discovery written down

### Backend

- **Discovery jobs** — `POST /api/v1/discovery/jobs` creates a job, registers the
  source in the registry, runs the pipeline and persists through `SqlBusinessStore`.
  Progress counts only records that reached the end (stored or rejected); cancellation
  is honoured between units of work and keeps what is already stored.
- **Honest outcomes** — `completed` with a named partial failure, `failed` when no
  source answered, `cancelled` mid-run, `blocked` when no worker exists, each with the
  reason the source gave. Per-source outcomes and counters are stored on the job.
- **Source registry** — adapters self-register from their declared capabilities,
  including their limitations, so provenance has something real to point at.
- **Celery task** added for the same job body, so the queued and inline paths cannot
  drift apart.
- **Bug:** a `model_validator` failure returned 500. Pydantic attaches the raising
  `ValueError` as `ctx`, which is not JSON — the error envelope now strips
  non-serialisable context instead of crashing on it.
- **Bug:** `.env` was overriding what two dispatcher tests claimed to prove about
  defaults; they now suppress the env file and assert the code default.

### Documentation

Map-Based Business Discovery — approved as core, previously specified as one bullet
and a feature list — now has functional requirements, UI behaviour and workflows,
geographic architecture, a data model, and roadmap tasks with acceptance criteria. See
D-046 for the rejected alternatives and `REQUIREMENTS_TRACEABILITY.md` for what is and
is not built. **No map code was written.**

### Verification

| Gate | Result |
|---|---|
| `pytest` | **189 passed** (was 175; +14 discovery job tests) |
| `ruff` / `mypy` | Clean, 70 files |
| Migration | `3f56cd53b45a` applied to real PostgreSQL 18.6 |

## 2026-11-02 (Phase 2) — Authentication, authorization, SQL store, two-user proof

### Backend
- **`SqlBusinessStore`** — real PostgreSQL persistence. Owner fixed at construction;
  merges on domain or phone, never name; fills gaps rather than overwriting; writes
  contacts as `unverified`; one `source_records` row plus link per contributing source;
  bounds raw payloads to 64 KB; counts skipped provenance instead of inventing a source id.
- **Auth endpoints** — register, login, logout, session. Hashed session tokens,
  server-side revocation, identical errors for unknown email and wrong password,
  per-IP+email login throttle with `Retry-After`, switchable registration.
- **CSRF** — double-submit cookie with an HMAC-signed, unguessable echo value; enforced
  on unsafe methods whenever a session exists.
- **Audit** — declared action list, redaction of secret-shaped keys, and a durable
  write path for failed attempts.
- **Businesses API** — list with filters, detail with provenance, shortlist, archive,
  soft delete, stage changes, CSV export. Every query carries the owner predicate.
- **CRM bootstrap** — per-owner default pipeline with the 12 documented stages; every
  stage move writes history and an activity row.

### Frontend
- Login screen with a signup affordance that follows the server's `registration_open`
  flag; session provider; dashboard gate; sign-out; CSRF-aware API client.

### Defects found by the new tests (all fixed)
Failed logins audited nothing (rolled back with the request); audit writes crashed on
non-IP client hosts against an `INET` column; a module-global engine outlived its event
loop; `NullPool` was handed pooling arguments; the CRM model referenced `services`
without importing it (`NoReferencedTableError`); `dict(Result)` is invalid; the CSRF
echo value was deterministic and therefore forgeable.

### Verification
| Gate | Result |
|---|---|
| `pytest` | **173 passed** (was 146) — 13 authentication, 14 authorization |
| ruff / mypy | clean, 65 files |
| eslint / tsc / `next build` | clean; `/`, `/dashboard`, `/login` prerendered |
| Live HTTP smoke | register 201 → login 200 → session 200 → businesses 200 → anonymous **401** → shortlist without CSRF **403** → logout 200 → replayed cookie **401** |

### The mandatory proof
`tests/test_authorization.py` creates two real users and shows that user B cannot read,
shortlist, change the stage of, delete, or export user A's records — each returning 404
rather than confirming existence — and that `SqlBusinessStore` built for B returns none
of A's rows. Two differently-named businesses in different accounts stay separate.

### Commits
`dddafb9` Phase 2 backend and tests.

### Cost, stated
The suite now takes about four minutes because these tests use a real database and real
Argon2 hashing. Runtime rose deliberately in exchange for integration truth.

---

## 2026-11-02 (later) — Phase 1 infrastructure unblocked, real migrations verified

### Unblocked without administrator rights
- Added `postgresql-binaries` as a **dev-only** dependency: real PostgreSQL 18.6
  binaries in a pip wheel. `scripts/devdb.ps1` initialises and controls a project-local
  cluster at `backend/.devdb` (gitignored), bound to 127.0.0.1 with trust auth.
- Verified through `asyncpg`, the driver the application actually uses: server version,
  database creation, and both extensions installed.
- Redis is still absent; `/health/ready` now reports `database: ok`,
  `redis: TimeoutError`, which is the accurate state.

### Migrations
- `0002` (`a7189272189c`) autogenerated the full initial schema: 37 tables, 15 CHECK
  constraints, 37 foreign keys, 146 indexes.
- `0003` (`0e2cb7da9112`) dropped a unique constraint that duplicated a composite key.
- `0004` (`7c41d0b52ae3`) added the primary key that autogenerate had silently omitted
  from `business_tags`.
- Verified by rebuilding into an empty scratch database: the whole chain runs, produces
  37 tables, **none without a primary key**, and `alembic check` reports no drift.
  Scratch database dropped afterwards.

### Bug found and fixed
`business_tags` was created with no primary key and no uniqueness at all once the
redundant constraint was dropped. Alembic's autogenerate reported "no drift" in both
directions, so this was invisible to the existing 139 tests — every one of which worked
from SQLAlchemy metadata, the same source that was wrong. Fixed forward rather than by
editing an applied migration. See DECISIONS.md D-039.

### Tests added
- `tests/test_database_schema.py` — 7 integrity tests that query `pg_constraint` and
  attempt real writes: every table has a primary key, foreign keys reject dangling
  rows, composite keys reject duplicates, CHECK constraints reject invented enum values
  (`website_status='definitely_has_one'`, `progress_percent=140`), `gen_random_uuid()`
  works, and `timestamptz`/JSONB round-trip. They **skip** when no database is
  reachable, so the suite still runs on a bare machine.
- Suite: **146 passed** (was 139). ruff, mypy, eslint, tsc all clean.

### Configuration
- Created a local `.env` (gitignored) with generated secrets and the dev database URL.
- Default CORS origins now include both `http://localhost:3000` and
  `http://127.0.0.1:3000`; a dashboard opened on the latter previously looked like a
  dead backend. See D-037.
- `.gitattributes` added so checkouts stop rewriting the entire tree to CRLF.

### Commits
- `0efa064` baseline checkpoint (127 files), `840e0f9` line-ending policy.

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
