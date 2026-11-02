# SparkXFlow Nexus — Decision Log

Append-only record of decisions and conflict resolutions, as required by the master
prompt section 1 and section 13. Newest entries at the top.

Format: decision, driver, alternatives rejected, consequence.

---

## D-050 | Source Manager: shared registry, per-account switches, generated descriptions

**Decision:** Master-plan #28 builds the Source Manager over the four tables that already
existed but had no API (`sources`, `source_configurations`, `source_health_checks`,
`source_usage_records`). The registry rows are **generated from the adapters**: the
catalogue is derived by asking the existing factories which providers this build can
actually run, so no hand-maintained list can drift from the code. A shared row's
descriptive columns are re-synced on every read of `/api/v1/sources`, and that
catalogue pass is the only writer allowed to correct a row's display name.

Enable/disable is **per account**, stored in `source_configurations` (owner-scoped, one
row per source per user, enforced by a new unique constraint), while `sources.is_enabled`
stays the provider-wide switch. The switch is honoured by the runners, not just displayed:
`discovery.runner.execute` drops disabled slugs before building adapters, logs each skip,
records them in `report.skipped_sources`, and fails a job with a named reason if nothing
enabled remains; `social.tracks.execute_track_run` skips them per source so a run ends
`completed_with_warnings` rather than pretending. Configuration is real too: the RSS
feed list an operator stores here is read back by the track runner as the fallback when a
track names no feeds.

**Driver:** PRD §6 and DESIGN §10 demand enable/disable, health, last run, recent errors,
quota, coverage, limitations, and a configure/test/history action set. The previous phase
deliberately left Sources read-only; that held while there was nothing to manage, but a
roadmap task called "Full Source Manager management" cannot be met by a read-only list.
A switch nobody honours is the kind of control this project has been refusing to ship.

**Alternatives rejected:**
- *Global-only enable/disable* — rejected: one account turning off Overpass would silently
  change another account's collection, and the schema already provides an owner-scoped
  table for exactly this.
- *A per-source config form with no consumer* — rejected: `configuration` exists in the
  schema, and a form that stored values nothing reads is the placeholder UI the mandate
  forbids. Only the RSS feed list is accepted, because only RSS has a runner that reads it.
- *Deleting stale registry rows from tests* — rejected: `source_records` and
  `business_social_profiles` reference `sources` with `ON DELETE CASCADE`, so purging a
  registry row would destroy the provenance it exists to describe. Repair, never delete.

**Consequence:** Test doubles that declare their own `AdapterCapabilities` can still write
a registry row under a real slug — but the next Source Manager read repairs it, which is
how the browser caught a stale "Fake hackernews" row being shown as a provider name. The
repair is limited to the descriptive columns and the name, and only on the catalogue path,
so a run's provenance write can never rename a provider underneath another reader. Per-source
`records_accepted` is recorded only where a run genuinely knows it (social tracks know
what they stored; discovery counts storage per job, not per source) — the column became
nullable so the manager can say "not reported per source" instead of showing `0`.

Supersedes the read-only-Sources position recorded in D-049.

---

## D-049 | Social & Demand Intelligence Engine: extend `social`, keyless-first, deterministic classification, compliance-first connectors

**Decision:** The Social & Demand Intelligence Engine is built *inside* the existing
`social` module rather than as the `social_intelligence` / `demand_intelligence` /
`social_discovery` / … packages the directive suggested as one possible layout. It adds
two independent tracks (Demand and Business) over shared infrastructure: new tables
`social_search_tracks`, `social_discovery_runs`, `social_saved_items`,
`social_classification_history` and nullable intelligence columns on the existing
`social_content`. The step engine reuses the existing dispatcher, task registry,
SSRF guard, normalisation, dedup, notifications and Businesses models. Sources are
implemented free-first and keyless (Reddit already; plus Hacker News, RSS/Atom,
SearXNG indexed-snippets, Stack Overflow, Bluesky, Mastodon), each behind the existing
`SocialAdapter` contract with honest `AdapterCapabilities`. Classification is a
transparent deterministic rule engine with stored evidence, confidence and method; local
Ollama is an optional hook, never mandatory, and there is no paid-API fallback.

**Driver:** The directive's own rules — do not replace the architecture, do not duplicate
infrastructure, no mandatory paid services, keep restricted-platform access compliant,
and do not present an adapter as working when it is not. Extending `social` (already the
home of `SocialPlatform`, `SocialContent`, `SocialResearchQuery`, the Reddit adapter and
the run/store/dedup flow) avoids a parallel system; the two tracks stay separate via a
`track_type` discriminator plus distinct vocabulary, categories and saved views.

**Alternatives rejected:**
- *A new parallel module set* (`demand_intelligence`, `social_discovery`, …) — rejected:
  it duplicates the adapter protocol, job/dispatcher, dedup and ownership machinery that
  already exist, which the directive forbids.
- *A dedicated per-user source-enablement table* — rejected for now: the platform
  catalogue is global operator data (capabilities/terms are not per-user), so the Sources
  UI is read-only and enable/config stays an operator action; a user must not mutate
  shared source state.
- *LLM-first classification* — rejected: paid/credentialed providers are barred, and a
  transparent rule engine with evidence is auditable and works offline. Ollama is a
  non-mandatory enrichment path only.

**Consequence:** LinkedIn/Instagram/Facebook/X have no scraping path implemented and remain
disabled with their real terms in the catalogue; their public snippets are reachable only
through the SearXNG indexed-snippet route, explicitly labelled as snippets, not retrieved
posts. A dedicated cross-entity Global Search module and full Analytics/Reports are still
the master-plan phases; the engine exposes `GET /social/results?query=` for a future search
to consume, and does not fabricate the higher-level analytics it has not built.
*(Closed later, not by a decision entry: cross-entity Global Search landed as master-plan
#26 and Analytics/Reports as #27 — see `PROJECT_STATUS.md`. The read-only-Sources position
below is superseded by D-050.)*

---

## D-048 | Automation Engine: two modules, approval-first email, SMTP-first sending

**Decision:** Phase 5 (Automation Engine) lands as two backend modules — `automation`
(workflows, schedules, executions, approvals) and `email` (accounts, campaigns,
messages, events, suppression list) — exposing `/api/v1/workflows` and
`/api/v1/email` as the architecture document already names them. The workflow step
engine implements five steps in version 1 — `qualify`, `shortlist`, `email_draft`,
`approval`, `send` — each wired to real backend logic (the existing deterministic
qualifier, the CRM shortlist stage, and a draft generator fed by real business
context). Email sending is gated: a message must be approved by a human and routed
through a configured, connected account; there is no auto-send. The first sending
adapter is **SMTP** (stdlib `smtplib`, environment-configured), not Gmail OAuth,
because SMTP is testable locally without credentials while Gmail OAuth is
credential-gated; the account model already carries `secret_reference`, so the OAuth
adapter slots in behind the same `EmailProvider` interface later.

**Driver:** PRD §5.4 and §9 require the full trigger→…→send→track pipeline with
human approval before sending and honest refusal when no provider exists. Gmail OAuth
and any real send need credentials this machine does not have, so the engine must
degrade to a clear error rather than pretend to send — the same honesty rule that
already governs Redis and SearXNG.

**Rejected:** a single `automation` module containing the email tables (the
architecture already separates the components, and 10 tables in one module is
unreadable); a "dry-run send" that marks messages sent without a provider (violates
the no-fake-completeness rule); implementing `discovery`/`research` as workflow steps
now (discovery is already an independently schedulable job, and wiring it as a step
would duplicate the job runner).

**Consequence:** the recurring-schedule tick is a Celery beat task that is configured
but live-unverified without Redis; "run now" executes inline via the same
`SynchronousDispatcher`-style path as discovery. Automated discovery-from-a-workflow
step and Gmail OAuth sending are recorded as deferred with reasons.

---

## D-047 | Where a record was found is never the record's website
**Decision:** `DiscoveredItem` carries an explicit `website_hint`. The SearXNG adapter
sets it to the result URL; the Overpass adapter never does. `normalized_domain` — a
confirmed-duplicate identity key — is derived only from a website the record itself
declares.
**Driver:** D4's live run returned 16 hospitals inside one kilometre of Hisar and
stored 3. Each record's provenance URL (`openstreetmap.org/node/…`) had become its
domain, so all of them shared an identity key and 13 were auto-merged.
**Rejected:** using the source URL but excluding `openstreetmap.org` (a blocklist of
aggregator domains is a moving target, and the next source's URL is just as
unqualifiable); keeping the merge and demoting domain to a *probable* key (would
weaken a control that is correct for genuine websites, which D4 showed only 10% of
records have).
**Consequence:** unmapped businesses now have no website rather than a borrowed one,
`website_status` stays `unknown` until a crawl actually checks it, and the map's
"no rating reported" is true instead of inherited from a source page.

## D-046 | Map-Based Business Discovery specified with JSON geometry, not PostGIS
**Decision:** The approved map feature was written into all five governing documents.
Geometry is stored as validated JSON on a new `search_areas` table, one `job_batches`
row per grid tile, and `source_records.batch_id` for tile-level provenance. `rating`
and `review_count` become explicit nullable columns on `businesses`. No keyed
commercial map provider is assumed anywhere.
**Driver:** The feature was approved as core Leads Intelligence but the documents
carried only two sentences about it ("Custom map area", "Map Explorer" plus a 12-bullet
feature list). Radius, drawing, tiling, map↔table sync, saved areas and per-tile
progress had no specified behaviour, no data model and no acceptance criteria — which
for a feature this size means it would have been invented under time pressure during
implementation.
**Rejected:**
- PostGIS with a geometry column and GiST indexes now — it is the right answer at
  scale and the wrong answer while nothing has measured pin density; a bounding-box
  pre-filter plus containment is sufficient and reversible. Deferred, as the schema
  document already deferred it.
- Storing geometry inside `searches.query_config` — it duplicates the shape per
  search, so a corrected area would leave every past search holding a stale copy.
- Reusing `search_presets` for areas — a preset is "how I search", an area is "where",
  and merging them would make a saved polygon unlistable without loading each config.
- Adding rating/reviews to the `enrichment` JSONB — the requirement names them as
  filter dimensions, and a filter that cannot be indexed or distinguished from
  absence is not a filter.
**Consequence:** The map feature is now buildable against written acceptance criteria.
Two documents (`database-schema.md`, `implementation-roadmap.md`) gained forward
requirements the current code does not meet, so `REQUIREMENTS_TRACEABILITY.md` records
the feature mostly as Not Started — the documentation is ahead of the build by design.

## D-045 | A discovery job commits before its inline run, and reports only observed counts
**Decision:** `runner.dispatch()` commits the job row before scheduling the inline
execution as a background task. Progress counts only records that reached the end of
the pipeline (stored or rejected); cancellation is re-read at checkpoints, not per
record. A job with no reachable broker is marked `blocked`, not left `queued`.
**Driver:** The first live run returned 201 and then logged `discovery_job_missing`:
the background task started in its own session and could not see a job row the request
transaction had not committed yet. Uncommitted work is invisible to the runner, which
is exactly the worker's situation on the real Celery path.
**Rejected:** Running the job inside the request (a large sweep would hang the caller
and the API would claim a finished job that was still running); sharing the request
session with the runner (a job must survive its own request); estimating progress from
elapsed time.
**Consequence:** Jobs survive their request. Progress can be honest — `completed` with
a named failing source, `cancelled` with partial results kept, `blocked` with the
reason and the dev-mode fix in the message.

## D-044 | Failed attempts are audited in their own transaction
**Decision:** `record_audit()` joins the caller's transaction; `record_attempt()` opens
its own and commits before the caller raises.
**Driver:** Phase 2 test found failed logins recorded nothing — the audit row was
written in the request transaction and the raised exception rolled it back.
**Rejected:** One mechanism for both (either losing attempts, or persisting success
records for actions that later rolled back).
**Consequence:** "What happened" is atomic with the change; "what was attempted" is
durable regardless. A brute-force trail that records nothing is worse than none,
because it reads as no attempts.

## D-043 | The engine belongs to the app instance, not the module
**Decision:** `create_app()` builds the engine and session factory onto `app.state`;
`get_db` reads them from the request's app. Standalone code uses `session_scope()`,
which builds a short-lived unpooled engine.
**Driver:** A module-global engine outlives the event loop that created it. Invisible
with one production process; fatal the moment a second client exists — every pooled
connection then belongs to a dead loop and fails with "Event loop is closed".
**Rejected:** Test-only workarounds (shared client, monkeypatched loops) that leave the
architectural flaw in place.
**Consequence:** Two cost notes, both accepted: the integration suite now runs about
four minutes, and `session_scope()` pays a fresh connection per call — fine for workers
and scripts, not something to put in a hot request path.

## D-042 | CSRF double-submit with an unguessable echo value
**Decision:** Cookie holds an HMAC-signed token; the client echoes an unguessable nonce
that the signature commits to. Enforced on unsafe methods when a session cookie exists;
login and registration are exempt because there is no session yet.
**Driver:** The first implementation signed a *deterministic* value, so anyone who knew
the scheme could construct the header without reading the cookie — a CSRF control that
was not one.
**Rejected:** SameSite-only (a defence, not a control); synchronizer tokens needing
server state per anonymous visitor.
**Consequence:** `signing_secret` is mandatory in production; without it the signature
falls back to a published development key.

## D-041 | Ownership is fixed at construction and cross-owner reads return 404
**Decision:** `SqlBusinessStore` takes `owner_user_id` once; every read statement in the
repository starts from `_base_statement(owner)`. A row belonging to someone else is
`not_found`, never `permission_denied`.
**Driver:** Phase 2's mandatory two-user proof. A store accepting an owner per call is
one forgotten argument from writing to another user's data; a 403 confirms the id exists.
**Rejected:** Filter-in-the-frontend; soft-scoping via optional filters.
**Consequence:** The isolation test suite is the regression guard for every future
endpoint — a new owned resource without a cross-owner test is incomplete.

## D-040 · Integrity is asserted against the database, not the model
**Decision:** `tests/test_database_schema.py` queries `pg_constraint` and attempts real
writes, asserting every table has a primary key, foreign keys reject dangling rows,
composite keys reject duplicates, CHECK constraints reject invented enum values, and
`timestamptz`/JSONB round-trip correctly.
**Driver:** D-039. Nothing in the previous 139-test suite could have seen a missing
primary key, because every schema test worked from SQLAlchemy metadata — the same
document that was wrong.
**Rejected:** Trusting `alembic check` (it reported no drift while the key was absent);
a metadata-only assertion (proves the model, not the database).
**Consequence:** These tests skip when no PostgreSQL is reachable, so the suite still
runs on a bare machine — but a skip is not a pass, and the skip reason names the
missing dependency.

## D-039 · Alembic autogenerate is a draft that must be read, and a defect is repaired forward
**Decision:** `0002` created `business_tags` with a UNIQUE constraint over the same two
columns as its declared composite primary key — and **no primary key at all**.
Autogenerate then reported "no drift" in either direction. Fixed by a forward
migration (`7c41d0b52ae3`) that adds the key, not by editing `0002`.
**Driver:** Observed live. A table without a primary key is unreplicable, unmergeable
and free to accumulate duplicates. Editing an already-applied migration would leave
this database and its history describing different schemas.
**Rejected:** Rewriting `0002`; leaving the redundant unique constraint in the model
(it was the trigger); silently accepting "no drift" as proof of correctness.
**Consequence:** Verified by rebuilding from an empty database: 37 tables, zero without
a primary key. Rule adopted: after any autogenerate that creates a table whose primary
key and a unique constraint share columns, read the DDL.

## D-038 · Development PostgreSQL comes from a pip wheel, not an installer
**Decision:** `postgresql-binaries` (dev extra) supplies real PostgreSQL 18.6 binaries;
`scripts/devdb.ps1` runs `initdb`/`pg_ctl` against a gitignored `backend/.devdb` data
directory, listening on 127.0.0.1 only with trust authentication.
**Driver:** Docker Desktop and the EDB installer both need administrator rights and a
reboot. The roadmap and the master prompt both require a documented native fallback
rather than stalling Phase 1.
**Rejected:** SQLite (the prompt explicitly refuses SQLite-only testing as proof of
PostgreSQL behaviour, and JSONB/`gen_random_uuid`/`pg_trgm` are not portable); waiting
for an elevated session.
**Consequence:** Migrations, integrity constraints and asyncpg behaviour are now
genuinely testable. Two caveats that must not be forgotten: these are third-party
repackaged binaries, so they stay out of every runtime dependency set and production
still uses the container image; and the postmaster must be started with its `bin`
directory on `PATH`, or every backend dies with `0xC0000142` while the server still
reports "ready to accept connections".

## D-037 · Both loopback spellings are first-class CORS origins
**Decision:** Default `cors_origins` includes `http://localhost:3000` **and**
`http://127.0.0.1:3000`.
**Driver:** Observed during preview: a dashboard opened at `127.0.0.1:3000` could not
read the API because the browser treats it as a different origin from `localhost:3000`,
and the failure looked like a dead backend rather than a blocked request.
**Rejected:** Telling the operator to always use one spelling; wildcard `*` (refused in
production by D-009-class validation, since session cookies are credentialed).

## D-036 · Master prompt phases govern sequencing; the five documents govern detail
**Decision:** The master prompt's Phase 0–11 sequence supersedes the roadmap document's
Phase 0–6 numbering. Mapping: prompt 0→roadmap 0; prompt 1→roadmap 1 (infrastructure);
prompt 2→roadmap 1 (authentication); prompt 3–5→roadmap 2 (Leads MVP, split into
slice/enrichment); prompt 6→roadmap 2 (CRM); prompt 7→roadmap 5 (Startup);
prompt 8→roadmap 3 (Social); prompt 9→roadmap 4 (Automation); prompt 10→roadmap
§11 analytics; prompt 11→roadmap deployment.
**Driver:** Two authoritative phase lists now exist. Numbering them differently without
a map guarantees the tracking documents drift apart.
**Consequence:** `PROJECT_STATUS.md` speaks in master-prompt phases and cites the
roadmap section for requirements detail.

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
