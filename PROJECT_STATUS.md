# SparkXFlow Nexus — Project Status

**Last updated:** 2026-11-03 (social-intelligence milestone)
**Current phase:** **Full product completion, in progress.** Phases 1 (background
execution), 2 (leads intelligence), 3 (startup intelligence) and 4 (social
intelligence) are implemented and tested; work continues through the remaining phases
in order.
**Overall status:** Authentication and ownership enforcement are proven with two
separate users. Discovery jobs run against real PostgreSQL and persist businesses with
provenance. Jobs run exactly once per submission (atomic claim), can be retried
safely, and recover from a dead worker. Leads intelligence is usable end to end in the
browser (standalone table, profiles, qualification, 12-stage CRM, notes, tags);
startup intelligence has its own 9-table schema, 21 API routes and browser UI
(records, founders, products, pricing, evidence-labelled revenue, competitors,
research, watchlists); and social intelligence now has a 4-table schema, an honest
6-platform catalogue (only Reddit enabled), research queries with real Reddit
collection, deduplicated content storage, owner isolation, CSV export and a browser
workspace (`/social`) — all browser-verified, including the honest live failure when
Reddit's public JSON returns 403 from this client. 295 backend tests pass. Redis is
still absent on this machine, so the Celery queued path is configured and tested but
not live-run; the inline execution path is fully exercised.

### Documentation change (2026-11-02)

Map-Based Business Discovery was approved as core Leads Intelligence but was barely
specified. It now has written requirements, UI behaviour, architecture, a data model
and acceptance criteria across the five governing documents — see `DECISIONS.md` D-046
and the dedicated section of `REQUIREMENTS_TRACEABILITY.md`. **The documentation is
deliberately ahead of the build:** almost every capability in it is Not Started.

### Phase mapping

This file uses the master prompt's Phase 0–11 numbering. The mapping to
`docs/implementation-roadmap.md` Phase 0–6 is recorded in `DECISIONS.md` D-036.

## 0. Phase progress at a glance

| Phase | Scope | Status |
|---|---|---|
| 0 | Repository audit and stabilisation | **Complete** — baseline committed at `0efa064` |
| 1 | Infrastructure, database and background execution | **Complete for PostgreSQL.** Job claim/retry/stale-recovery and worker readiness are **Tested** (7 new tests). Redis and SearXNG still absent, so the Celery queued path is configured but not live-run |
| 2 | Authentication and authorization | **Complete** — includes the mandatory two-user isolation proof |
| 3 | Discovery vertical slice + map discovery | **Complete** — jobs, progress, cancel, provenance, SQL persistence, the geographic grid/map API, and the browser UI (Leads table, profiles, qualification, CRM board, service catalog) are all implemented and verified |
| 4 | Startup Intelligence | **Complete except discovery-from-sources, reports and comparison.** 9-table schema (startups, founders, products, pricing, revenue records, competitors, research records, watchlists), 21 owner-scoped API routes with audit writes, and a browser UI (dashboard, profile, watchlists) — manual entry, research, evidence-labelled revenue, competitor and watchlist flows all browser-verified. Discovery from configured startup sources (Product Hunt, HN, GitHub) is **Deferred** (needs new adapters), and report generation / company comparison are **Not Started** (Phase 7) |
| 5 | Social Intelligence | **Complete except live Reddit reachability.** 4-table schema (platforms, profiles, content, research queries), an honest 6-platform catalogue (Reddit enabled; LinkedIn/Instagram/Facebook/X/YouTube disabled with their real access terms stated), research-query CRUD + run with deduplication, owner-isolated content list/filter/CSV export, business linking, and the `/social` browser workspace. Live Reddit requests return 403 from this client, which the adapter reports honestly as a failure rather than fabricating results |
| 6–11 | Automation, Global Search, Analytics, Source Manager, Import/Export, Hardening | Not Started — the next milestone is Phase 5 Automation Engine |

## 1. Security review findings (2026-11-02)

Scope: discovery adapters, pipeline, normalisation, validation, deduplication,
scoring, in-memory store, CSV export, plus config, middleware, logging and security
helpers.

| # | Severity | Finding | Status |
|---|---|---|---|
| S-1 | **High** | **Overpass QL injection.** `build_query()` interpolated `query.category` straight into the query language. Overpass has no parameter binding, so `cafe"]["shop` or `"]; node["shop"]; out;` broke out of the filter — arbitrary and arbitrarily expensive queries against shared public instances, plus data exfiltration beyond the intended scope. | **Fixed** — tag values whitelist-validated (`^[A-Za-z0-9:_-]{1,40}$`), rejected otherwise rather than escaped. 5 regression tests |
| S-2 | **High** | **No SSRF gate for discovered URLs.** Nothing today fetches a discovered URL, but the enrichment crawler is designed to, and fetching attacker-chosen URLs from a server is the classic path to cloud metadata, admin panels, and the Redis/PostgreSQL on the same host. | **Fixed proactively** — `shared/url_safety.py:validate_discovered_target()` refuses non-http(s), embedded credentials, loopback/RFC1918/CGNAT/link-local/reserved targets and named metadata IPs, and checks **every** DNS answer so split-horizon hosts cannot slip through. Private access requires an explicit opt-out. 11 tests |
| S-3 | **Medium** | **Unbounded query fan-out.** A single query could carry thousands of keywords × up to `max_pages` requests, and `max_results` had no ceiling. Each extra page multiplies requests to a search proxy, which gets the whole instance blocked upstream — damage that outlives the abusive run. | **Fixed** — `MAX_KEYWORDS_PER_QUERY=10`, `MAX_PAGES_LIMIT=10`, `MAX_RESULTS_LIMIT=500`, query length 300, Overpass radius ≤50 km, bbox ≤50 km, elements ≤1000. Configuration cannot raise them |
| S-4 | **Medium** | **Attacker-controlled text stored verbatim.** Page titles and snippets went into the database, the CSV export and any future renderer untouched: markup, NUL, ANSI escapes, zero-width characters. A zero-width space also makes two visually identical names compare unequal, which corrupts deduplication. | **Fixed** — `sanitize_text()` strips tag markup, control and zero-width characters, collapses whitespace and clips to declared widths. 4 tests |
| S-5 | **Medium** | **No field-length bounds.** A 5 MB "email" reached `VARCHAR(320)` and failed at the INSERT with an opaque database error; oversized phone strings were handed to the number parser as-is. | **Fixed** — bounds in `normalization.py` matched to the schema; oversized contact values are refused, not silently truncated |
| S-6 | **Medium** | **Correlation ID reflected unvalidated.** The inbound `X-Correlation-ID` was length-checked only, then written to structured logs and echoed back in a response header. Escape sequences survive JSON encoding and reach a terminal log viewer, spoofing log lines. | **Fixed** — `^[A-Za-z0-9._-]{1,64}$`, else a fresh id is minted. 1 test |
| S-7 | **Medium** | **Provenance lost on confirmed merges.** Deduplication discarded the merged-away record, erasing exactly the second-source evidence that corroborated the survivor — the opposite of `database-schema.md` §12.2 and of PRD principle 6. | **Fixed** — losing record's attributions and observed signals transfer to the survivor; reported as `provenances_merged` so the UI can state it |
| S-8 | **Medium** | **Account-enumeration oracle waiting to be built.** Login against a missing user returns instantly; a real user costs a full Argon2 verification. That timing gap is an enumeration oracle — and this product's whole purpose is finding people. | **Fixed pre-emptively** — `verify_password_for_login()` verifies a dummy hash when no account matches, so both paths cost the same. 1 test |
| S-9 | **Medium** | **Wildcard CORS with credentialed cookies.** `allow_origins=["*"]` plus `allow_credentials=True` and cookie auth would let any site the operator visits read the entire API. Nothing rejected it. | **Fixed** — production startup refuses a wildcard origin. 1 test |
| S-10 | **Low** | **Runaway configuration accepted silently.** 999 pages, a 3600 s timeout, a 0-hour or 10-year session. | **Fixed** — bounded field validators reject out-of-range values at load time |
| S-11 | **Low** | **Negative or NaN scoring weight** could push a published score below zero. The schema forbids it; the evaluator was more permissive than the database. | **Fixed** — non-finite or negative weights raise |
| S-12 | **Low** | **Writable source mounts in containers** let a compromised app process rewrite its own code. | **Fixed** — `:ro` on all three backend bind mounts; `api_exports` stays writable |
| S-13 | **Low** | **Adapters followed redirects** implicitly (httpx default is off, but nothing stated or pinned it). A redirect moves the request to a host configuration never approved. | **Fixed** — `follow_redirects=False` explicit in both adapters, with a test asserting one request and a surfaced failure |
| S-14 | **Low** | **Service base URL accepted a smuggled path or userinfo**, changing which resource is actually requested and putting credentials into URLs. | **Fixed** — `validate_service_base_url()` requires an origin; Overpass now takes a base URL and owns `/api/interpreter` itself |
| S-15 | **Low** | **SearXNG crash-looping on an empty secret** with a message that does not name the cause. | **Fixed** — `infra-up.ps1` detects the empty secret, starts Postgres/Redis, and explains the missing value |

### Checked and found sound

- **SQL injection:** no string-built SQL anywhere. All access goes through SQLAlchemy
  Core/ORM expressions; the only raw SQL is the constant `SELECT 1` health probe and
  fixed extension DDL in `0001_extensions`. Alembic reads the URL from the environment.
- **CSV formula injection:** already neutralised in the previous session (`=`, `+`, `-`,
  `@`, tab, CR) and now additionally proven that an embedded CRLF cannot forge rows.
- **Secret exposure:** the database error handler logs only the exception type and
  returns a generic message; `httpx` error details are reduced to the type name because
  the message can embed the request URL; session tokens are stored as SHA-256 digests;
  `secret_reference` columns hold pointers, not secrets. Verified by test that the query
  string never reaches the access log.
- **Frontend XSS sinks:** no `dangerouslySetInnerHTML`, `innerHTML`, `document.write` or
  `eval` in `frontend/src`. Text reaches the DOM through React's escaping only.
- **Auth primitives:** Argon2id with library defaults, 256-bit opaque session tokens,
  constant-time comparison on HMAC lookups.

### Deliberate, documented non-hardening

- `validate_service_base_url` **permits** loopback and `http`. This application is
  local-first; blocking that would break its own SearXNG. The strict rule applies to
  *discovered* URLs, which are attacker-chosen. This asymmetry is in the function
  docstring so nobody "fixes" it the wrong way later.
- SearXNG's own outbound behaviour is the instance's concern, not the adapter's. A
  misconfigured instance can be pointed anywhere; the compose stack binds it to
  loopback.

## 2. Verification results

| Gate | Result |
|---|---|
| `pytest` | **295 passed** |
| `ruff check` | All checks passed |
| `mypy app` | No issues in 91 source files |
| `eslint` / `tsc --noEmit` | Clean |
| `next build` | Succeeds; routes `/`, `/dashboard`, `/leads`, `/leads/[id]`, `/leads/crm`, `/leads/map`, `/leads/services`, `/login`, `/social`, `/startups`, `/startups/[id]`, `/startups/watchlists` |
| `alembic upgrade head` from empty | 8 revisions applied to a scratch database, 52 tables created (4 social tables) |
| `alembic check` on that schema | **No new upgrade operations detected** |
| Schema audit query | 52/52 tables have a primary key; 29 named CHECK constraints, 55 FKs, 201 indexes |
| Live HTTP smoke test | register 201 → login 200 → session 200 → businesses 200 → **anonymous 401** → **shortlist without CSRF 403** → logout 200 → **session after logout 401** |
| Browser mutation smoke test | qualify 200 (score/status/evidence rendered) → note 201 → shortlist 200 → stage move 200, all against real PostgreSQL |

Runtime note: the suite now takes about four minutes because the auth and
authorization tests hit a real database and real Argon2 hashing. That is the cost of
integration truth over mocks, recorded rather than hidden.

### Phase 2 — what was built

- **`SqlBusinessStore`** — ownership fixed at construction rather than passed per write;
  merges on domain or phone (never name); fills gaps instead of overwriting; writes
  contacts as `unverified`; one `source_record` plus link per contributing source;
  bounds raw payloads; counts skipped provenance instead of faking a source id.
- **Auth endpoints** — register, login, logout, session. Hashed session tokens,
  server-side revocation, generic credential errors, per-IP+email login throttle with
  `Retry-After`, switchable registration, double-submit CSRF with an unguessable echo.
- **Businesses API** — list with filters, detail with provenance, shortlist, archive,
  soft delete, stage changes, CSV export. Every statement carries the owner predicate.
- **Audit trail** — declared action list, secret redaction, and a separate durable write
  for attempts so a rolled-back request still records what was tried.
- **CRM bootstrap** — per-owner default pipeline with the 12 documented stages, stage
  history and activity written on every move.
- **Frontend** — login screen, session provider, dashboard gate, sign-out, CSRF-aware
  API client. The signup affordance follows the server's `registration_open` flag
  instead of assuming it.

### Defects the Phase 2 tests found (all fixed)

1. **Failed logins recorded nothing.** The audit row was written inside the request
   transaction, which the raised exception rolled back.
2. **Audit writes crashed on non-IP client hosts.** `ip_address` is `INET`; test and
   proxied clients put a name there, failing the whole request.
3. **A module-global engine outlived its event loop.** Invisible in production, fatal
   for any second client; the engine now belongs to the app instance.
4. **`NullPool` rejected the pooling arguments** it was being handed.
5. **The CRM model referenced `services` without importing it**, producing
   `NoReferencedTableError` whenever one module was loaded alone.
6. **`dict(Result)` is invalid** — the export path raised instead of returning rows.
7. **The CSRF echo value was deterministic**, which made double-submit forgeable from
   the URL alone.

Items 1, 2 and 7 were security defects in code written hours earlier; none would have
shown up as a functional bug.

### Phase 3 — what was built

- **Startup schema (9 tables)** — `startups`, `startup_founders`, `startup_products`,
  `startup_pricing`, `startup_revenue_records`, `startup_competitors`,
  `startup_research_records`, `startup_watchlists`, `startup_watchlist_items`. CHECK
  constraints enforce the status vocabulary, non-negative pricing/revenue amounts,
  the revenue-confidence range, and no self-referencing competitor. `database-schema.md`
  §13 already documents them, so the build was made to match the spec.
- **21 owner-scoped API routes** under `/startups` — CRUD for startups, founders,
  products, pricing, revenue records, competitors, research records and watchlists;
  every write is CSRF-gated, and create/delete/watchlist-create write audit rows.
- **Revenue evidence classes enforced in code, not just schema.** `verified`,
  `founder_reported`, `estimated`, `not_available`; `not_available` must carry a null
  amount and `estimated` must name a methodology — so an estimate without its reasoning
  is refused rather than stored as if it were fact.
- **Competitor integrity** — self-reference is rejected and a duplicate pair is a 409.
- **Duplicate startup detection** — the domain is normalised and a second record with
  the same domain conflicts rather than silently duplicating.
- **Frontend** — Startup dashboard (`/startups`, filter/search/paginate/create/delete),
  profile (`/startups/[id]` with overview PATCH, revenue, competitors, founders,
  products, research and watchlists), and watchlists view (`/startups/watchlists`).
  Navigation enables both; `/startups/discover` stays disabled because there is no
  startup source adapter yet.

### Defects the Phase 3 tests found (all fixed)

1. **Serializing a just-flushed row raised `MissingGreenlet`.** Server-default
   timestamp columns are expired after `flush()`, and `model_validate` in sync context
   cannot lazily refresh them. Nine service functions now `await session.refresh()`
   after flush before returning. The businesses paths never hit this because they only
   select; the startup create/update paths return the created row.
2. **The first startup migration emitted duplicate indexes.** Six columns carried both
   `index=True` and a redundant named `Index()` on the same column. Removed the six
   redundant declarations and regenerated the migration as `a02df3cff960`.

### Deferred (honest)

- **Startup discovery from configured sources** is the one Phase 3 acceptance item not
  met. The existing adapters are Overpass (geographic) and SearXNG (search); neither is
  a startup directory. Product Hunt needs a key, Hacker News and GitHub are free
  candidates — the adapter choice is still open, so `/startups/discover` remains
  disabled rather than a decorative control.

### Phase 4 — what was built

- **Social schema (4 tables)** — `social_platforms` (name, slug, adapter_key,
  capabilities/limitations JSONB, health status, last run), `social_profiles`
  (platform + owner + external author id, unique per owner/platform/author),
  `social_content` (platform + owner + research query + author profile, content type
  CHECK, engagement JSONB, provenance `source_id`, unique per owner/platform/external
  id), and `social_research_queries` (owner + platform, query_config JSONB, last-run
  status). `owner_user_id` and `research_query_id` are deliberate additions beyond
  `database-schema.md` §14 so the two-user isolation proof applies to social data too.
- **Honest platform catalogue** — `PLATFORM_DEFINITIONS` states each platform's actual
  permitted access. Reddit alone is enabled (unauthenticated public JSON, descriptive
  User-Agent, one request per run, no redirects); LinkedIn, Instagram, Facebook,
  X and YouTube are disabled with their real terms stated, so the UI shows
  "restricted" instead of implying availability.
- **Reddit adapter** — validates query kind (`search`/`subreddit`/`user`), sort and
  limit ceilings; maps Listing JSON to `SocialResult`; treats 429/401/403/400 as
  distinct `AdapterError` classifications; health check via `/r/announcements.json`.
- **13 owner-scoped API routes** under `/social` — platform listing, research-query
  CRUD + run, content list (platform/type/text filters), CSV export, content delete,
  and link-to-business. Every write is CSRF-gated; runs and links write audit rows;
  re-runs deduplicate by external id and report `duplicates` rather than hiding them.
- **Frontend** — `/social` workspace: platform catalogue, create-query form
  (platform/kind/terms/sort/limit), query list with run/delete and honest last-run
  status, collected-content table with filters, CSV export, per-row delete and
  link-to-business. Navigation enables the section.

### Defects the Phase 4 tests found (all fixed)

1. **`SocialResearchQueryOut`/`SocialContentOut` could not be built by
   `model_validate`.** The response schemas carry `platform_slug`/`author_username`
   fields that live on joined rows, not on the ORM object, so validating the ORM row
   first raised `platform_slug: Field required`. The router now constructs the schema
   explicitly instead of round-tripping through `model_validate`.
2. **`link_content_to_business` referenced a non-existent column.** It read
   `content.author_username`; author identity lives on `SocialProfile` via
   `content.profile_id`. The service now resolves the profile and passes its username
   through (nullable).
3. **`SourceUnavailableError` was called with one argument** in three places; its
   signature is `(source_slug, reason)`.

### Social — deferred (honest)

- **Live Reddit collection.** The adapter and storage path are fully tested against a
  mocked transport, and the browser run works end to end, but the live request
  returns **403 — "Reddit refused the request (403). Unauthenticated JSON access may
  be blocked for this client."** — from this network. That is reported honestly in the
  UI, not replaced with sample data. No other platform has a permitted, key-free
  access method to add.

### Infrastructure actually running

| Service | How | State |
|---|---|---|
| PostgreSQL 18.6 | `scripts/devdb.ps1` — pip-provided binaries, data in `backend/.devdb`, 127.0.0.1:5432, trust auth | **Running and verified** |
| Redis | Not installed (no Memurai, no container) | Absent — blocks Celery execution only |
| SearXNG | Needs a container runtime | Absent — adapters are unit-tested against mocked transports, never live |
| FastAPI | `scripts/dev-backend.ps1` (uvicorn --reload, 127.0.0.1:8000) | Running |
| Next.js | `scripts/dev-frontend.ps1` (localhost:3000) | Running |

**Trust caveat, stated plainly:** the PostgreSQL binaries are a third-party repackaging
from PyPI, used for development only. Production still targets the container image. They
are confined to the `dev` dependency extra so they cannot leak into a runtime install.

`./scripts/test.ps1` runs all five gates.

## 3. Phase 0 acceptance criteria

| Criterion (roadmap §3) | Status |
|---|---|
| Frontend starts successfully | **Tested** |
| Backend starts successfully | **Tested** |
| Configuration is documented | Implemented |
| No secrets committed | Implemented — verified again this session |
| Structure follows `architecture.md` | Implemented |
| Traceable plan exists | Implemented |

## 4. Blocked

| Item | Blocked by | Status / unblocks when |
|---|---|---|
| ~~`0002_initial_schema`~~ | ~~No PostgreSQL~~ | **Done** — autogenerated, reviewed, applied, drift-free |
| ~~Schema revision chain~~ | ~~No PostgreSQL~~ | **Done** — verified by rebuilding into an empty database |
| ~~Auth endpoints end to end~~ | ~~Nothing~~ | **Done** — Phase 2, proven with two users |
| ~~SQLAlchemy `BusinessStore`~~ | ~~Nothing~~ | **Done** — `SqlBusinessStore`, tested |
| Source Manager with real rows | Nothing | **Unblocked** — next after discovery |
| Celery worker running jobs | No Redis | Blocked — Memurai (runbook §3.2) or Docker (§2.4). `SynchronousDispatcher` covers development |
| Live SearXNG verification | No container runtime | Blocked — needs a SearXNG instance. **Overpass can be live-tested now** (public endpoint, internet confirmed working) |
| Discovery UI | Nothing | Next: Phase 3 job management, then the results table |
| Gmail sending | No credentials, and scope verification | Not attempted — adapter and approval queue first |

**No administrator rights are required for anything marked Unblocked.** The remaining
blockers are Redis, a SearXNG container and Google credentials — each recorded with its
own path rather than treated as a general stop.

Docker remains blocked for two reasons that are not workarounds: the shell is not
elevated, and enabling the container backend requires a reboot. **No installation or
privileged action was attempted in this session, per instruction.**

## 5. Bugs found and fixed

**From the security review:** the nine findings in §1 (Overpass QL injection, missing
SSRF gate, unbounded fan-out, untrusted text stored verbatim, no field-length bounds,
unvalidated correlation ID, provenance lost on merge, login enumeration oracle, wildcard
CORS) plus six lower-severity items.

**Found by tests in earlier sessions:** `lstrip("mailto:")` eating leading address
characters; `get_db` referencing an undefined `_session_scope`; framework 404s bypassing
the error envelope; `csv.writer` handed a list instead of a file object; validation
warnings rejecting usable leads; probable-duplicate similarity averaging in a missing
address.

**Found this session, against the real database:**

1. **`business_tags` had no primary key.** Autogenerate emitted only the unique
   constraint because both covered the same columns, then reported no drift in either
   direction. Dropping the redundant constraint left the table with no uniqueness at
   all. Repaired forward in `7c41d0b52ae3` and locked in by a test asserting every
   table has a key.
2. **Every PostgreSQL connection failed with `0xC0000142`.** The postmaster was started
   without its `bin` directory on `PATH`, so each connection's child process could not
   load its DLLs — while the server logged "ready to accept connections". Fixed in
   `scripts/devdb.ps1`, with the reason written down.
3. **The dashboard looked dead when opened at `127.0.0.1:3000`.** Different origin from
   `localhost:3000`, so CORS blocked the API. Both are allowed by default now.
4. **Every browser mutation failed with "Failed to fetch".** `allow_headers` in the
   CORS middleware omitted `X-CSRF-Token`, so the preflight for any state-changing
   request was rejected while GETs worked. Adding the header unblocked qualify,
   shortlist, note, tag and stage moves — invisible to the backend tests because
   `TestClient` does not run a browser CORS preflight.

None of these three were visible to the previous 139 tests, and two were invisible to
`alembic check` as well — which is the argument for asserting integrity against the
database rather than the model.

## 6. Known limitations and open security work

1. **`raw_data` is unbounded.** `source_records.raw_data` will hold whatever a source
   returns. Nothing caps it yet, so one pathological response bloats the database.
   Must be bounded when the SQLAlchemy store is written — the field is deliberately not
   invented in the in-memory path.
2. **No API rate limiting or auth middleware exists yet.** Single-user and loopback
   bound for now; `architecture.md` §19 requires rate limits, and PRD §17 requires
   access control. Both land with Phase 1 auth. Until then, **do not expose this
   service beyond loopback.**
3. **No security headers / CSP yet.** Frontend is Phase 1 work. React escaping is the
   only current protection, which is sufficient today because no untrusted data is
   rendered.
4. **CSRF is unaddressed by design choice, not oversight.** Cookie sessions will need
   SameSite plus a double-submit token; `sign_value`/`unsign_value` exist in
   `core/security.py` but nothing calls them yet.
5. **No audit-log writes yet.** The table exists; the actions that should log are
   Phase 1+.
6. **Deduplication is O(n²)** per batch — a performance limit, not a security one,
   but it becomes a resource-exhaustion vector once batches grow. Blocking by identity
   key is scheduled for Phase 2b.
7. **`to_csv` builds the whole file in memory.** Fine at development scale, wrong at
   100k rows; the export job must stream. Deferred with the export API.
8. **Dependency audit not run.** 16 moderate npm advisories were reported by
   `create-next-app` and not triaged. `npm audit` + a lockfile review is a Phase 1
   task; nothing in this stack is yet reachable by an attacker, which is why it is
   listed rather than alarmist.

## 7. Remaining infrastructure procedure

**PostgreSQL is done** — `./scripts/devdb.ps1` brings up a real 18.6 cluster on
127.0.0.1:5432 with no administrator rights, and the migration chain is verified against
it. Steps 1–7 below apply only to **Redis and SearXNG**, which still need either Docker
Desktop or a native substitute. Do not re-run them for the database.

**Step 1 — open an elevated PowerShell** (Start → `powershell` → Run as administrator).
The agent shell is not elevated, so steps 1–3 cannot be done from this session.

**Step 2 — move container storage off C: first.** C: has 26 GB free; the images alone
need ~10 GB. In Docker Desktop → Settings → Resources → Advanced, set Disk image
location to `D:\DockerData` (or pre-create
`%USERPROFILE%\.docker\desktop\vhdx-path.json` with `{"dataFolder":"D:\\DockerData"}`).

**Step 3 — install and reboot.**

```powershell
winget install -e --id Docker.DockerDesktop
```

This enables Virtual Machine Platform and WSL2. **Reboot.** Without the reboot,
`docker info` fails in a way that looks like a Docker bug but is not.

**Step 4 — verify the runtime.**

```powershell
docker info --format '{{.ServerVersion}}'
docker compose version
```

**Step 5 — fill in the two secrets** in `sparkxflow-nexus\.env`
(create it from `.env.example` if `bootstrap.ps1` has not):

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"   # SPARKX_SIGNING_SECRET
python -c "import secrets; print(secrets.token_urlsafe(48))"   # SEARXNG_SECRET
```

**Step 6 — start infrastructure and check memory.** With only ~2.1 GB RAM free at last
inspection, close Discord, Chrome and CamoStudio first.

```powershell
cd D:\SPARKXFLOWSCAPPER\sparkxflow-nexus
./scripts/bootstrap.ps1
./scripts/infra-up.ps1
docker compose ps        # postgres, redis, searxng must all be healthy
docker stats --no-stream # confirm the caps in docker-compose.yml are being respected
```

**Step 7 — create the first schema revision and read it.**

```powershell
./scripts/db-revision.ps1 -Message "initial schema"
# open the new file in backend/migrations/versions/ and read every drop/alter
./scripts/db-migrate.ps1
```

Autogenerate is a draft. It has never seen this database, so it may propose
extensions it assumes exist or indexes you did not intend.

**Step 8 — first live verification of the adapters.** This is the measurement that
validates or overturns decision D4:

```powershell
./scripts/dev-backend.ps1
python -c "import asyncio, json; from app.modules.discovery.adapters.searxng import SearxngAdapter; from app.modules.discovery.adapters.base import DiscoveryQuery; a=SearxngAdapter('http://localhost:8080'); print(asyncio.run(a.health_check())); print(len(asyncio.run(a.discover(DiscoveryQuery(keywords=('coffee shop Bengaluru',),max_results=20)))))"
```

Record the returned counts in `REQUIREMENTS_TRACEABILITY.md`. If SearXNG returns
nothing usable, that is a finding about the product, not a bug to hide.

**Shorter path if you want to skip containers:** install PostgreSQL alone via the EDB
installer (runbook §3.1), point `.env` at it, and run steps 7 immediately. That unblocks
the schema revision, the SQLAlchemy store, auth, and Source Manager — everything except
background jobs and SearXNG.

## 8. Phase 3 work queue — the first usable discovery workflow

Target: **Source → Discover → Normalize → Database → Table → Profile → Shortlist → CSV
Export**, running end to end for a signed-in user with real collected data.

1. ~~Discovery job management~~ **Done** — create, dispatch, progress from observed
   counts, cancel, honest failure and `blocked` reporting. 14 tests.
2. ~~Wire `run_pipeline` to `SqlBusinessStore` inside a job~~ **Done** — businesses,
   contacts and `source_records` with `job_id`, bounded payloads and `expires_at`.
3. Overpass live test — public endpoint, no container needed. Record how many real
   businesses come back for a Bengaluru query. This is the D4 measurement.
4. SearXNG live test once an instance exists; until then the Source Manager shows it as
   unavailable rather than silent.
5. Results table UI: raw / filtered / qualified views with filters, sorting, pagination.
6. Business profile page: overview, contacts with verification state, provenance,
   research history, CRM block, actions.
7. Shortlist and export wired to the existing endpoints with CSRF.
8. Duplicate review queue surfaced in the UI (probable and possible pairs).

### Map-Based Business Discovery — documented 2026-11-02, not yet built

Nothing below is implemented. The order matters: the D4 measurement in item 3 decides
whether the tile budgets designed in `architecture.md` §9.4 are even the right shape,
so it must come before the map work, not after it.

9. `search_areas` table + migrations (schema §7.6), with server-side geometry
   validation and the size ceilings (integrity rules 16–19).
10. Area-capable API: accept `area_id` on `POST /discovery/jobs`, add `GET /businesses?bbox=`.
11. Deterministic grid planner writing one `job_batches` row per tile, with truncation
    detection and per-tile retry/resume.
12. Leaflet Map Explorer: pins, clustering, marker preview with source and retrieval time.
13. Drawing tools (radius, rectangle, polygon) and the tile-state overlay.
14. Shared filter/selection state between map and table; phone-availability filter is
    missing from the businesses API and must be added for the map filters to work.
15. `rating` / `review_count` columns, written only from source-reported values.
16. `source_records.batch_id` so provenance names the tile, not just the job.

### Completed in Phase 2, carried forward

Auth endpoints, sessions, CSRF, rate limiting, audit writes, `SqlBusinessStore`,
businesses API, per-owner CRM pipeline, and the two-user isolation proof. Remaining
Phase 2 leftovers: security headers/CSP on the frontend, and dependency advisory
triage — both scheduled with Phase 11 hardening, and both still true gaps.

Do not expose the application beyond loopback until the Phase 3 endpoints inherit the
same owner-scoped tests.

## 9. D4 — live source measurement (2026-11-02)

`scripts/d4_overpass_probe.py` was run against the public
`https://overpass-api.de/api/interpreter` with one request in flight, a 20–25 s gap
between queries, and an identifying User-Agent. Roughly 35 requests were made in
total across three runs, after which the instance began refusing even 0.5 km
count-only queries; the probing was stopped rather than keep hammering shared
infrastructure. **These are the numbers that actually came back.**

Clean measurements — Hisar, centre (29.1499, 75.7211), 5 km radius, limit 200:

| Category filter | Elements | Named | Coordinates | Phone | Website | Nodes / ways |
|---|---|---|---|---|---|---|
| `amenity=hospital` | 80 | 80 | 80 | 2 (2.5%) | 8 (10%) | 78 / 2 |
| `tourism=hotel` | 4 | 4 | 4 | 0 | 0 | 4 / 0 |
| `amenity=restaurant` | 2 | 2 | 2 | 0 | 0 | 0 / 2 |
| `leisure=fitness_centre` | 0 | — | — | — | — | — |
| `shop=grocery` | 0 | — | — | — | — | — |
| `amenity=clinic`, `amenity=school` | **not measured** — 502 | | | | | |
| Delhi, Gurugram, all larger areas | **not measured** — 502/504 | | | | | |

Latency and reliability, which the previous design had no basis for at all:

- Successful queries: **36.6 s to 45.3 s** each for one 78.5 km² circle at a 200-element limit.
- **7 of 12** coverage cases failed. Observed failures were `502 Gateway Timeout`,
  `504`, and — importantly — **an error page returned with HTTP 200**. The adapter
  already treats that correctly as a retryable `MalformedResponseError`, because it
  parses the body rather than trusting the status.
- No successful query came near the element limit, so **truncation frequency remains
  unmeasured**. The detector is implemented (`source.last_capped` → batch `truncated`
  → subdivision) but is not yet exercised against a real dense area.

What this decides:

1. **D4 stands, and is now evidenced.** OSM/Overpass in India is strong for a few
   large institutional categories (80 hospitals near Hisar, all named and located)
   and effectively empty for local commerce (2 restaurants, 0 groceries, 0 gyms in
   the same circle). A leads product built on Overpass alone would report that a
   city of three million people has no shops. Search-based discovery and the
   permitted website crawler are not nice-to-have.
2. **Contact coverage is thin even where the record exists.** Of 80 hospitals, 2
   carried a phone and 8 a website. "Discovered 80 businesses" is not "80 usable
   leads", which is the metric PRD §22 warns about. Enrichment has to be a real
   stage, not a bonus.
3. **Tile defaults are set from latency and refusal behaviour, not coverage.**
   Smaller units answer faster, but more units is what a saturated endpoint cannot
   take — so `discovery_tile_target_area_km2 = 25`, `discovery_max_tiles_per_job = 40`,
   `discovery_max_tile_depth = 1`, one source in flight, and a 90 s client timeout
   (45 s was the slowest observed success).
4. **Public Overpass is a demo path, not a production path.** The endpoint is
   configuration (`SPARKX_OVERPASS_BASE_URL`); production use means self-hosting it.

What remains blocked for D4: per-category coverage at Delhi and Gurugram, the
tile-size/latency curve beyond 5 km, and truncation frequency. They need either a
healthier moment on the public instance or a self-hosted one — which needs Docker
or a second native install, both still unavailable here.

### The live run found a data-loss bug (same day)

Running a real job through the API — `amenity=hospital`, 1 km circle at Hisar —
returned **16 records and stored 3**. The OpenStreetMap page each record was found
on had become every business's `normalized_domain`, and a shared domain is a
confirmed-duplicate identity key: 13 distinct hospitals were folded into 3 with
their provenance merged, silently. Mocked tests had passed for weeks because the
fixtures never produced two records from the same source.

Fixed by making the claim explicit per source (`DiscoveredItem.website_hint`,
set by the search adapter, never by Overpass). Verified live again after the fix:
`duplicates_merged` 13 → **0**, all 16 records processed. Locked in by
`test_sixteen_real_hospitals_store_as_sixteen_businesses`, which replays the
captured names through the pipeline and the real store.

Also observed live, and now reported rather than hidden: the 3 km job failed with
`overpass: 4 of 4 unit(s) failed — unexpected — ReadError`, stored nothing, and
left the reason on the job row. Failure paths are real, not decorative.

### Map Intelligence — verified in the browser (2026-11-02)

Signed in as the operator at `/leads/map`: Leaflet renders OSM tiles with
attribution; the viewport query returned the 3 real Hisar hospitals persisted by
the live job; clicking a result row selected its pin and opened the marker preview
("hospital · website unknown · no phone reported · no rating reported"). Choosing
no area leaves *Start discovery* disabled rather than running an unbounded query.

## 10. Status vocabulary

Not Started · In Progress · Implemented · Tested · Blocked · Deferred (with reason)

Nothing in this file is marked complete because code exists. Blocked items stay
labelled blocked.
