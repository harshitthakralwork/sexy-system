# SparkXFlow Nexus — Decision Log

Append-only record of decisions and conflict resolutions, as required by the master
prompt section 1 and section 13. Newest entries at the top.

Format: decision, driver, alternatives rejected, consequence.

---

## D-035 · Two URL policies, deliberately asymmetric
**Decision:** `validate_service_base_url()` permits loopback and plain http;
`validate_discovered_target()` refuses every non-public address unless explicitly
opted out.
**Driver:** Security review S-2. A single strict rule would break the product's own
self-hosted SearXNG; a single permissive rule would turn the future crawler into an
SSRF machine against cloud metadata, Redis and PostgreSQL.
**Rejected:** One policy for both cases; blocking private ranges globally; deferring
the guard until the crawler exists (the guard is what the crawler will be written
against).
**Consequence:** Every resolved DNS answer is checked, not just the first, so
split-horizon hosts cannot pass. `allow_private_networks` must be set deliberately.

## D-034 · Untrusted text is cleaned at the boundary, not at the render
**Decision:** `sanitize_text()` strips tag markup, control and zero-width characters,
and clips to schema widths before anything is stored.
**Driver:** Review S-4/S-5. Scraped titles are attacker content. React escapes on
render, which covers the browser but not the CSV export, not a log line, and not the
zero-width case — `Sp​ark` and `Spark` are different strings to the dedup matcher.
**Rejected:** Sanitising only in the API response (exports bypass it); relying on
an HTML parser (a tag-shape regex is enough here and adds no dependency).

## D-033 · Query fan-out has hard ceilings that configuration cannot raise
**Decision:** 10 keywords, 10 pages, 500 results, 300-character queries, 50 km radius,
1000 Overpass elements.
**Driver:** Review S-3. Each extra page multiplies requests to a search proxy that
upstream engines rate-limit as a unit, so an abusive query penalises every future run,
not only its own.
**Rejected:** Trusting `.env` to be sane; per-source runtime tuning.

## D-032 · Overpass tag values are whitelisted, never escaped
**Decision:** `^[A-Za-z0-9:_-]{1,40}$` or the query is refused.
**Driver:** Review S-1 (High). Overpass QL has no parameter binding. Hand-rolled
escaping in a query language is where injection bugs are born; OSM tag keys do not need
anything outside that class.
**Rejected:** Doubling quotes; percent-encoding; allowing non-ASCII categories
(`café` is not an OSM tag value, so refusing it is correct rather than restrictive).

## D-031 · Confirmed merges carry the loser's evidence forward
**Decision:** On a confirmed duplicate, the discarded record's attributions and
observed signals move to the survivor, and the count is reported.
**Driver:** Review S-7. Corroboration by a second source is the reason multi-source
discovery exists; erasing it at merge time destroys the evidence behind the very score
the platform shows.
**Rejected:** Keeping both rows (duplicates the CRM), or dropping provenance
(database-schema.md §12.2 forbids it).

## D-030 · Login verification costs the same whether or not the account exists
**Decision:** `verify_password_for_login()` verifies a dummy Argon2 hash when no user
matches.
**Driver:** Review S-8. An unknown email returning instantly while a known one burns a
full hash is an account-enumeration oracle — on a product whose stated purpose is
finding people.
**Rejected:** Ship the endpoint and "fix it later"; rate limiting (slows but does not
remove the signal).

## D-029 · Deduplication is quadratic, with the threshold stated in code
**Decision:** Compare all candidate pairs inside one discovery batch; revisit past a
few hundred records.
**Driver:** Blocking by identity key (domain/phone/email buckets) is correct at scale
but adds a second code path now, before any batch has ever been that large.
**Rejected:** Pretending it scales. The cost is written in the docstring so the next
reader meets it as a known limit rather than a surprise.
**Consequence:** A 1,000-result sweep will be slow and that will be visible, not silent.

## D-028 · A probable match scores on the signals that exist
**Decision:** When one side has no address, similarity is the name score — not the
average of name and a missing address.
**Driver:** Test output showed `similarity=0.4737` on a pair classified PROBABLE. A
review queue that reports 0.47 for a 0.95 name match trains the operator to ignore
good matches.
**Rejected:** Averaging whatever is present, which conflates "different" with "unknown".

## D-027 · Signals are observations, never claims about reality
**Decision:** A single canonical vocabulary in `app/shared/signals.py`
(`website_claimed`, `website_checked`, `website_reachable`, …). `None` means "not
observed" and is never coerced to `False`.
**Driver:** `scoring_rules.signal_key` is a free-text column; without a defined
vocabulary two rules could quietly mean different things. This was gap 2 in
`REQUIREMENTS_TRACEABILITY.md`.
**Rejected:** A `has_website` boolean. It cannot express "we never looked", which is
the state almost every discovered record is actually in.
**Consequence:** `derive_website_status()` returns `unknown` until something really
fetches the site, so a "no website" opportunity signal can only fire on evidence.

## D-026 · CSV export neutralises spreadsheet formulas
**Decision:** Prefix a leading `=`, `+`, `-`, `@`, tab or CR in any exported cell with
an apostrophe.
**Driver:** Exported names and descriptions come from public web pages. Excel
evaluates such a cell *after* unquoting, so quoting alone does not defuse a page
titled `=cmd|'/C calc'!A0`. CSV injection is the realistic path from "scraped text"
to "code running on the operator's machine".
**Rejected:** Quoting only; dropping the character; refusing to export those rows.
**Consequence:** A rare legitimate name starting with `-` gains a leading apostrophe.
Accepted as cheaper than the alternative.

## D-025 · Validation warnings do not reject records
**Decision:** `ValidationOutcome` separates `reasons` (reject) from `warnings`
(keep, count). Only "identifies nothing" rejects.
**Driver:** Found as a bug the same day: an unparseable website URL silently deleted
usable leads, which is the exact opposite of what the validation stage is for.
**Rejected:** Warnings-as-errors (loses data) and no warnings at all (hides data
quality from the operator).
**Consequence:** `PipelineReport.counters.warning_flagged` gives the UI something
honest to display: "3 records stored, 1 with an unverified URL".

## D-024 · Initial schema revision deferred, not hand-written
**Decision:** Alembic is configured and `0001_extensions` is committed, but
`0002_initial_schema` is autogenerated against a live PostgreSQL rather than typed by
hand.
**Driver:** A hand-written 37-table migration cannot be verified against the models
that generated it, and an unverifiable migration is worse than a missing one.
**Rejected:** Writing the DDL blind. It would have "looked done" while being the
largest untested artifact in the repository.
**Consequence:** `db-revision.ps1` is the first command to run once a database exists.
The generated file must be read before `db-migrate.ps1`.

## D-023 · Dispatcher selection is configuration, not code branches
**Decision:** `TaskDispatcher` protocol with `CeleryDispatcher` (queued) and
`SynchronousDispatcher` (inline). Selected by `SPARKX_RUN_JOBS_SYNCHRONOUSLY`.
**Driver:** No Redis exists on this machine, and the roadmap forbids blocking on one
integration. `architecture.md` §3.2 requires task interfaces independent of Celery.
**Rejected:** Importing Celery tasks directly in services (locks the stack to one
runner); silently no-op'ing submissions when the broker is down (a job row would read
"queued" forever).
**Consequence:** Discovery is testable end-to-end today. The inline path blocks the
caller, so scheduled workflows and long sweeps genuinely require the Celery path —
enforced by refusing `run_jobs_synchronously=true` in production.

## D-022 · Nested git repository, excluded from the parent clone locally
**Decision:** `sparkxflow-nexus` is its own repository. The parent AgencyAgents clone
ignores it via `.git/info/exclude`, not by editing its tracked `.gitignore`.
**Driver:** The workspace root is a clone of a third-party repository. A `git add -A`
there would otherwise sweep the whole product into someone else's project history.
**Consequence:** Two repos, deliberately. `.git/info/exclude` is local and untracked, so
updating the parent clone cannot resurrect the problem.

## D-021 · Synchronous test suite proves behaviour without infrastructure
**Decision:** Phase 0 tests cover pure domain logic and framework behaviour only. No
database-backed test was written, and none pretends to pass.
**Driver:** Roadmap §24 forbids ordinary automated tests depending on unreliable public
providers; the same logic applies to absent infrastructure.
**Consequence:** 47 tests run on a bare machine. `REQUIREMENTS_TRACEABILITY.md` marks auth as
"Implemented but unexercised" rather than complete.

## D-020 · Python 3.12 via uv, not the installed 3.15
**Decision:** `uv` provisions managed CPython 3.12.16; the project pins `>=3.12,<3.13`.
**Driver:** Master prompt §4 explicitly forbids building on 3.15 because it happens to
be installed. SQLAlchemy, Celery and Playwright wheels lag new CPython releases.
**Rejected:** Using system 3.15; conda (heavier install, and the user wants everything
inside Qoder's own tooling).
**Consequence:** System Python stays untouched. `uv.lock` is the reproducibility
artifact the Dockerfile installs from.

## D-019 · Compose limits memory per service and binds to loopback
**Decision:** Explicit `memory` caps; every published port bound to `127.0.0.1`.
**Driver:** 16 GB RAM with ~2.1 GB free at inspection, and PostgreSQL/Redis must not be
publicly reachable (`architecture.md` §8.5).
**Consequence:** A starved container fails visibly instead of degrading the desktop.
Local AI, if ever added, needs its own budget decision.

## D-018 · Unbuilt modules render as disabled, not as links
**Decision:** Sidebar entries for Phase 1+ work are disabled buttons labelled "soon".
**Driver:** `DESIGN.md` §3.2: "Do not show unfinished modules as if they are
operational." Master prompt §8: no static mockups labelled complete.
**Consequence:** The app has exactly one working route. That is the honest state.

## D-017 · Scoring is deterministic; AI may annotate, never produce
**Decision:** Weighted rule evaluator with stored profile version; evidence rows record
each contribution and missing signals.
**Driver:** PRD §16 requires core function without AI; `architecture.md` §12 requires a
deterministic fallback and reproducible scores.
**Rejected:** LLM-assigned scores. They are not reproducible from stored data and
cannot carry evidence.
**Consequence:** `confidence` degrades visibly when signals are missing rather than
silently guessing. The `signal_key` vocabulary is still undefined — tracked as a gap
that must close before the Service Catalog UI.

## D-016 · Phone uniqueness deliberately not enforced
**Decision:** No global unique constraint on phone or email across businesses.
**Driver:** `database-schema.md` §20: shared numbers, agencies and chains are legitimate.
**Consequence:** Dedup uses scored candidate classes (confirmed / probable / possible /
not) and only confirmed duplicates auto-merge.

## D-015 · Retention protection lives in SQL, not application goodwill
**Decision:** `retention_policies` rows plus protected categories (`shortlisted_lead`,
`outreach_history`), enforced by predicate in the cleanup query.
**Driver:** PRD §10 and `database-schema.md` §19.3 forbid deleting shortlisted records
during temporary cleanup. An application-level check can be forgotten by the next
feature.

## D-014 · One-way Google Sheets export only
**Decision:** Two-way sync deferred.
**Driver:** Approved decision D6. Quota-limited, conflict-prone, and not required by the
MVP definition of done.

## D-013 · Local-first execution; hybrid dispatch deferred
**Decision:** Build against one execution target; keep `execution_target` on jobs.
**Driver:** Approved D5. Also resolves a contradiction — see C-003.

## C-003 · Conflict: local workers vs. "never expose PostgreSQL"
**Sources:** `architecture.md` §8.5 requires local workers to reach the authoritative
database securely, while also forbidding exposing PostgreSQL publicly. No mechanism is
specified, and no outbound-only worker design exists.
**Resolution:** Deferred hybrid dispatch entirely; local-first for now, so the conflict
is not yet load-bearing. Kept the schema column so a later dispatcher is additive.
**Revisit when:** Phase 4 scheduling introduces a second execution environment.

## C-002 · Conflict: "single-user" versus full session and ownership model
**Sources:** PRD §4 says private single-user; `database-schema.md` §5 defines `users`,
`user_sessions`, `is_superuser`, and `owner_user_id` everywhere; §19 hedges on the auth
mechanism ("if password authentication is used").
**Resolution:** Resolved by decision D3 — implement email + password with Argon2id and
hashed session tokens. The hedge in the documents was an undecided requirement, not a
permission to skip auth.

## C-001 · Conflict: free-first vision versus Vercel and Railway terms
**Sources:** PRD §2 and §15 / `architecture.md` §22 target Vercel + Railway on free
tiers; PRD §1 forbids mandatory paid services.
**Resolution:** Hosting is treated as unverified, not chosen. Vercel's Hobby plan
prohibits commercial use, and Railway's perpetual free tier no longer exists in the
form the documents assume. `architecture.md` §22.1 already demands verification before
selection; that verification is an open task, not a skipped one.
**Revisit when:** Any deployment work begins.

## D-012 · Correlation ids minted by the service, echoed to the client
**Decision:** Middleware binds one id per request; the client never invents one.
**Driver:** `architecture.md` §20 requires connecting API requests to background jobs.
A client-supplied id cannot be trusted to be unique or present.

## D-011 · Raw records are storage-expiring; normalised entities are not
**Decision:** `source_records` carry `expires_at`; promoted entities have no retention
deadline, only lifecycle status.
**Driver:** PRD §10 requires 15-day temporary retention while shortlisted leads persist,
and `architecture.md` §9.3 requires raw data kept separately.

## D-010 · Argon2id for passwords, SHA-256 digest for session tokens
**Decision:** `argon2-cffi` for hashes; sessions store `sha256(token)` only.
**Driver:** PRD §17; `database-schema.md` §5.3 explicitly names a token hash column.
A database leak must not yield live sessions.

## D-009 · Website status distinguishes missing / inaccessible / unknown
**Driver:** `database-schema.md` §9.1 warns that no website and an unreachable website
are different claims, and only the first is an opportunity signal.

## D-008 · India-first normalisation without hardcoding India
**Decision:** `default_region` is configuration (`SPARKX_DEFAULT_REGION=IN`), passed into
phone parsing at call time; original values preserved next to normalised ones.
**Driver:** Master prompt §5 Geography.
**Consequence:** Changing country is a config edit, not a schema change. The test suite
asserts a bare number resolves differently for `IN` and `US`, so the region parameter
cannot silently rot into a constant.

## D-007 · SearXNG self-hosted, JSON format enabled explicitly
**Driver:** The default SearXNG install does not serve JSON, so the adapter would fail
against an unmodified container. `infra/searxng/settings.yml` enables it deliberately
and disables engines that add noise without improving business coverage.

## D-006 · Celery retained, Windows path documented rather than hidden
**Decision:** Celery stays (roadmap §3.2 preference). On a Windows host it runs
`--pool solo`; real parallelism lives in the Linux container.
**Driver:** Celery's prefork pool does not support Windows. Hiding that would produce a
worker that appears to run one job at a time by design.

## D-005 · PostgreSQL FTS + pg_trgm; no search engine, no PostGIS yet
**Driver:** `architecture.md` §17 and `database-schema.md` §21 both say to start with
what PostgreSQL does well and add a dedicated engine only when measured.

## D-004 · TanStack Query owns server state; no client-side mirroring
**Driver:** `architecture.md` §5 warns against unnecessary global state. Dashboard data
is fetched, cached and invalidated in one place.

## D-003 · Errors return one envelope: `code`, `message`, `correlation_id`
**Driver:** PRD §19 wants clear errors; a framework-default 404 body would have forced
the frontend into two parsing paths. Fixed by test, not by inspection — see the bug
note in `PROJECT_STATUS.md` §6.

## D-002 · Async SQLAlchemy 2.0 throughout
**Driver:** FastAPI is async; mixing a sync ORM into request handlers would block the
event loop on the discovery workers' own queries. Alembic runs through
`connection.run_sync`.

## D-001 · UUID primary keys with `gen_random_uuid()` server default
**Driver:** `database-schema.md` §4.1. Requires `pgcrypto` on PostgreSQL < 13 and the
extension revision `0001_extensions` records that dependency explicitly.

## Approved decisions carried in from the audit (2026-11-02)

| Ref | Area | Decision |
|---|---|---|
| D1 | Environment | Docker Desktop preferred; documented Windows-native fallback so work never stalls |
| D2 | Geography | India-first, multi-geo-ready (see D-008) |
| D3 | Authentication | Local email + password, Argon2id, secure sessions (see C-002) |
| D4 | Discovery | SearXNG primary, OSM/Overpass supplementary, permitted crawler for enrichment |
| D5 | Execution | Local-first, cloud-ready contracts, hybrid dispatch deferred (see C-003) |
| D6 | Google Sheets | One-way export (see D-014) |
| D7 | First slice | Source → discovery → normalization → DB → table → profile → shortlist → CSV |
| D8 | Trust | Attribution, evidence-based scoring, enforced retention, honest source failure |
