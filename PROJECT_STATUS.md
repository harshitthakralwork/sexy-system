# SparkXFlow Nexus — Project Status

**Last updated:** 2026-11-02 (security review session)
**Current phase:** Phase 0 complete. Phase 1 blocked on infrastructure. Phase 2a
domain core built and tested ahead of the roadmap order.
**Overall status:** Code reviewed as Security Engineer; 9 confirmed issues fixed, 42
regression tests added, nothing marked complete that is not verified

---

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
| `pytest` | **139 passed** (was 97; +42 security regression tests) |
| `ruff check` | All checks passed |
| `mypy app` | No issues in 53 source files |
| `eslint` / `tsc --noEmit` | Clean |
| `next build` | Verified in the previous session; no frontend changes in this review |
| Live probe | `/health/ready` → `degraded` with per-component detail, not a 500 |

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

| Item | Blocked by | Unblocks when |
|---|---|---|
| `0002_initial_schema` revision | No PostgreSQL | Docker Desktop **or** native Postgres (runbook §3.1) |
| SQLAlchemy `BusinessStore` | Same | Written when it can be tested, not before |
| Auth endpoints end to end | Same | Same |
| Source Manager with real rows | Same | Same |
| Celery worker running jobs | No Redis | Runbook §2.4 or §3.2 (Memurai) |
| Live SearXNG / Overpass verification | No container runtime yet | After infra — mocked tests cover code, not data |
| Phase 2a UI | All of the above | After Phase 1 |

Docker remains blocked for two reasons that are not workarounds: the shell is not
elevated, and enabling the container backend requires a reboot. **No installation or
privileged action was attempted in this session, per instruction.**

## 5. Bugs found and fixed across both sessions

Nine from the security review above, plus five functional bugs found by tests
earlier: `lstrip("mailto:")` eating leading address characters; `get_db` referencing an
undefined `_session_scope`; framework 404s bypassing the error envelope; `csv.writer`
handed a list instead of a file object; and validation warnings rejecting usable leads.

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

## 7. Exact procedure to unblock Phase 1

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

## 8. Phase 1 work queue once infrastructure exists

1. `0002_initial_schema` applied and re-verifiable from an empty database.
2. Auth: register, login, logout, session middleware, CSRF token, current-user
   dependency, and **authorization tests proving one owner cannot read another's rows**
   — the IDOR surface that `owner_user_id` creates.
3. `SqlBusinessStore` implementing the existing `BusinessStore` protocol, with a
   bounded `raw_data` size.
4. Celery worker running a real discovery job with progress from actual counts.
5. Source Manager reading the live `sources` table.
6. Dependency audit triage (`npm audit`, `uv` lock review).
7. Security headers / CSP on the frontend, and rate limiting on the API.

## 8. Status vocabulary

Not Started · In Progress · Implemented · Tested · Blocked · Deferred (with reason)

Nothing in this file is marked complete because code exists. Blocked items stay
labelled blocked.
