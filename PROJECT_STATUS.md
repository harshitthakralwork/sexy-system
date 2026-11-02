# SparkXFlow Nexus — Project Status

**Last updated:** 2026-11-02 (Phase 2 session)
**Current phase:** **Phase 2 complete and verified.** Phase 3 (discovery vertical slice)
is next and is largely unblocked.
**Overall status:** Authentication, authorization, ownership enforcement and real SQL
persistence are implemented and proven with two separate users. 173 tests pass.

### Phase mapping

This file uses the master prompt's Phase 0–11 numbering. The mapping to
`docs/implementation-roadmap.md` Phase 0–6 is recorded in `DECISIONS.md` D-036.

## 0. Phase progress at a glance

| Phase | Scope | Status |
|---|---|---|
| 0 | Repository audit and stabilisation | **Complete** — baseline committed at `0efa064` |
| 1 | Infrastructure and database foundation | **Complete for PostgreSQL.** Redis and SearXNG still absent |
| 2 | Authentication and authorization | **Complete** — includes the mandatory two-user isolation proof |
| 3 | Discovery vertical slice | **In Progress** — pipeline, adapters and SQL store exist; job management and the UI table/profile/export wiring remain |
| 4–11 | Leads UI, enrichment, CRM, Startup, Social, Automation, Analytics, Hardening | Not Started |

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
| `pytest` | **173 passed** (146 previous + 13 authentication + 14 authorization) |
| `ruff check` | All checks passed |
| `mypy app` | No issues in 65 source files |
| `eslint` / `tsc --noEmit` | Clean |
| `next build` | Succeeds; routes `/`, `/dashboard`, `/login` prerendered |
| `alembic upgrade head` from empty | 4 revisions applied to a scratch database, 37 tables created |
| `alembic check` on that schema | **No new upgrade operations detected** |
| Schema audit query | 37/37 tables have a primary key; 15 CHECK constraints, 37 FKs, 146 indexes |
| Live HTTP smoke test | register 201 → login 200 → session 200 → businesses 200 → **anonymous 401** → **shortlist without CSRF 403** → logout 200 → **session after logout 401** |

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

1. Discovery job management: create a job, dispatch through `TaskDispatcher`, track
   progress from real processed counts, support cancel and honest failure reporting.
2. Wire `run_pipeline` to `SqlBusinessStore` inside a job, persisting `source_records`
   with bounded payloads and `expires_at`.
3. Overpass live test — public endpoint, no container needed. Record how many real
   businesses come back for a Bengaluru query. This is the D4 measurement.
4. SearXNG live test once an instance exists; until then the Source Manager shows it as
   unavailable rather than silent.
5. Results table UI: raw / filtered / qualified views with filters, sorting, pagination.
6. Business profile page: overview, contacts with verification state, provenance,
   research history, CRM block, actions.
7. Shortlist and export wired to the existing endpoints with CSRF.
8. Duplicate review queue surfaced in the UI (probable and possible pairs).

### Completed in Phase 2, carried forward

Auth endpoints, sessions, CSRF, rate limiting, audit writes, `SqlBusinessStore`,
businesses API, per-owner CRM pipeline, and the two-user isolation proof. Remaining
Phase 2 leftovers: security headers/CSP on the frontend, and dependency advisory
triage — both scheduled with Phase 11 hardening, and both still true gaps.

Do not expose the application beyond loopback until the Phase 3 endpoints inherit the
same owner-scoped tests.

## 9. Status vocabulary

Not Started · In Progress · Implemented · Tested · Blocked · Deferred (with reason)

Nothing in this file is marked complete because code exists. Blocked items stay
labelled blocked.
