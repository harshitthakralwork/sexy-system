# SparkXFlow Nexus — Requirements Traceability

**Purpose:** `implementation-roadmap.md` section 12 requires a checklist linking major
PRD requirements to implementation status and tests. Statuses: Not Started ·
In Progress · Implemented · Tested · Blocked · Deferred (with reason).

A requirement is **Tested** only when an automated test or a verified manual run
covers the behaviour, not because a file with the right name exists.

---

## Map-Based Business Discovery (approved core feature, documented 2026-11-02)

Specified in `PRD.md` §7.1.1, `DESIGN.md` §6.2–6.3, `architecture.md` §3.4/§6/§9.4/§17,
`database-schema.md` §3/§7.2/§7.4/§7.6/§8.1/§9.1/§20/§21/§24/§25, and
`implementation-roadmap.md` §5. Statuses here describe **code**, not the documents.

| Capability | Status | Evidence |
|---|---|---|
| Category + geometry search | **Tested** | `POST /discovery/jobs` accepts `category` (OSM `key=value`) with circle/rectangle/polygon geometry; the administrative cascade (country → state → city → locality) is still Not Started — it needs a geocoder, which is not wired `DiscoveryQuery` carries `country`, `category` and `place_name`, but nothing resolves an administrative cascade into geometry |
| Radius selection | **Tested** | `POST /api/v1/discovery/jobs` accepts centre + `radius_km` (bounded `0 < r <= 50`, validated against the Overpass ceiling); `LocationSpec` enforcement is **Tested** in the adapter tests, an end-to-end radius job is not |
| Rectangle and polygon drawing | Implemented, manually verified | Leaflet drawing in `components/map/map-canvas.tsx`; geometry is re-validated server-side. Verified in the browser, not covered by an automated frontend test — there is no frontend test runner in this project yet
| Save/load search areas | **Tested** | `search_areas` migrated (`2c1d3459383d`) with geometry CHECK constraints; CRUD is owner-scoped and cross-owner reads/updates/deletes return 404 in `test_map_discovery.py` |
| Grid tiling for large regions | **Tested** | `shared/geo.py` + `discovery/tiles.py`: deterministic non-overlapping partition, stable keys, refusal with the tile count when over the limit; 30 unit tests plus an end-to-end 16-tile job |
| Per-tile progress, retry, resume | **Tested** | One `job_batches` row per tile × source with bounds, counters, truncation flag and retry count; `open_batch` reuses a tile by its deterministic key instead of inserting a second row |
| Truncation and subdivision | **Tested** (unit) | `last_capped` → batch `truncated` → quarters the tile, bounded by `discovery_max_tile_depth`; the job names the capped units. Never exercised live: no public query came near a cap |
| Discovery job over an area | **Tested** | `POST /discovery/jobs` accepts an ad-hoc geometry or a saved `area_id` (never both), stores the resolved shape on the search row, and runs it — verified end to end against live Overpass |
| Overpass geographic adapter | **Live-verified** | Query builder, `key=value` tags, `nwr` + `out center`, tag whitelist, radius/element caps. A real 1 km Hisar query returned 16 hospitals; the pre-D4 query shape was rejected by the live interpreter as a parse error, and two tests now pin the shape Query builder, tag whitelist, coordinate/radius validation and element cap are **Tested** against mocked transports; no real endpoint has been called yet |
| SearXNG as a non-spatial source | Implemented, live-unverified | Adapter **Tested** with mocks; per §9.4 it must degrade to administrative text, which is not implemented |
| Pins, clustering, marker preview | Implemented, manually verified | Pixel-grid clustering and marker previews render real stored records; browser-verified against live Hisar data. No automated frontend test Sidebar exposes "Map Explorer" as a disabled control; nothing renders |
| Map ↔ table sync | Implemented | The map's own results panel shares filters, selection and export with the pins; the standalone Leads results table (Phase 4) does not yet share that state The businesses API filters and paginates but accepts no `bbox`, so there is no viewport query to share |
| Map filters | Implemented for what exists | Website status, phone availability and category filter real stored data and are **Tested**; `rating`/`review_count` columns exist but nothing populates them yet, so no rating filter is offered `rating` / `review_count` columns are specified but not migrated. Of the required dimensions, `website_status` is already an owner-scoped filter on the businesses API; **phone availability is not**, and neither is rating or review count |
| Dedup across overlapping searches | **Tested** | Identity now includes the source record id, so one OSM node seen in two tiles or two re-runs is one business with every sighting kept. D4 caught the opposite failure: 16 hospitals stored as 3 Identity rules (domain, then phone, never name alone) and provenance-preserving merges are **Tested**; nothing yet exercises them across two geographic units |
| Provenance per tile | **Tested** | `source_records.job_id` and `batch_id` are both written; a tile's records can be named, re-run or excluded from a coverage claim |
| Live job progress with named failures | **Tested** | `discovery_jobs.report` carries per-source outcomes and counters; a failed source yields `failed`, and a partial one `completed` with the failure named |
| Export the current selection | **Tested** | `POST /businesses/export/selected` returns the picked rows with provenance, refuses cross-owner ids and reports how many were skipped; CSRF required |
| Bounds, throttles, no keyed provider | **Tested** | Job-creation rate limit now covered; per-user geographic request quotas beyond it are still Not Started Keyword/page/radius/element caps are **Tested** at the adapter level, and job creation is CSRF-gated (**Tested**). The 10-jobs-per-5-minutes limit is implemented but has no test yet. No per-user geographic request quota exists |

**Honest limits.** The live path is now demonstrated: a real Overpass query stored
real Hisar businesses and the browser drew them as pins, and the failures are real
too (the 3 km job died on a `ReadError` and reported it). What is still unproven at
scale is Delhi/Gurugram coverage, the tile-size curve beyond 5 km, and truncation
frequency — the public instance refused enough queries that these are recorded as
blocked, not as measured. The map has no automated frontend tests; its behaviour was
verified by hand, and the backend behind every control is covered.

## MVP definition of done (PRD section 21)

| # | Requirement | Where it lands | Status | Evidence |
|---|---|---|---|---|
| 1 | Open and securely access the platform | `modules/auth` | **Tested** | Register, login, logout, session; 13 authentication tests + live HTTP smoke test |
| 2 | Discover businesses using supported sources | `modules/discovery/adapters` | **Implemented** | SearXNG + Overpass adapters written against the `DiscoveryAdapter` contract; **Tested** with mocked transports (17 tests). Not yet run against a live instance |
| 3 | View results in tables and on a map | **Tested** | Standalone Leads table (`/leads`) with filters, pagination, shortlist and CSV export; Leaflet map explorer with pins/clustering. Browser-verified against real PostgreSQL; backend covered by tests |
| 4 | Research individual business profiles | **Tested** | `/leads/[id]` shows overview, contacts with verification state, provenance, CRM stage/activity, notes and tags — all wired to real endpoints. Browser-verified |
| 5 | Filter and deduplicate discovered businesses | `shared/normalization`, `modules/deduplication` | **Tested** | 13 normalisation + 10 deduplication tests. Confirmed auto-merges; probable/possible become a review backlog |
| 6 | Evaluate businesses against configurable services | `shared/signals`, `shared/scoring`, `services_catalog` | **Tested** | Deterministic evaluator (12 tests) + canonical signal vocabulary. Qualification endpoint exercised end to end: score, status, evidence and missing signals render in the browser from real stored opportunities |
| 7 | Shortlist promising opportunities | `modules/crm/service.py`, `modules/businesses` | **Tested** | Shortlist endpoint with ownership enforcement, stage history and activity; cross-owner shortlist rejected |
| 8 | Manage shortlisted businesses through a CRM pipeline | `modules/crm` | **Tested** | Per-owner default pipeline with the 12 documented stages, stage moves recorded with history; kanban board (`/leads/crm`) renders the 12 columns and moves cards. Browser-verified |
| 9 | Export data to CSV or Excel | `modules/exports/` | **Tested** | CSV, JSON and XLSX writers **Tested** (13 original CSV tests plus 42 import/export tests) incl. spreadsheet-formula neutralisation and text-only columns. Jobs persist in the existing `export_jobs` table; Excel and job persistence are implemented (master-plan #29) |
| 10 | See job status, source health and processing errors | `modules/health`, `discovery/pipeline.py`, `modules/sources` | In Progress | Readiness + per-source failure reporting in `PipelineReport` are **Tested**. Job rows and Source Manager UI need the database |

## Product principles (PRD section 3)

| Principle | Status | Evidence |
|---|---|---|
| P1 Free-first | Implemented | Compose stack is Postgres/Redis/SearXNG; no paid API in dependencies |
| P2 AI optional | Tested | `/api/v1/info` reports `ai_enabled: false`; scoring works with no AI path at all |
| P3 Source diversity | In Progress | Adapter protocol designed; one adapter implemented (zero so far) |
| P4 Evidence-based intelligence | Tested | `opportunity_evidence` model + evaluator returns per-rule contributions and missing signals |
| P6 Data transparency | In Progress | `source_records` kept separate from normalised entities; provenance columns exist; pipeline not built |
| P9 Responsible collection | Implemented | No credential use, no CAPTCHA or anti-bot handling anywhere; runbook states blocked sources are reported as unavailable |
| P10 Useful before extensive | Implemented | Plan splits Phase 2 into a thin slice (2a) before breadth |

## Non-functional requirements (PRD section 19)

| Requirement | Status | Evidence |
|---|---|---|
| Modular, maintainable code | Implemented | Module boundaries per `architecture.md` 4.1; ruff + mypy strict pass |
| Reliable background job execution | Blocked | Needs Redis. Runner-agnostic dispatcher **Tested** for both paths |
| Resumable jobs where practical | Not Started | `job_batches` model exists; no resume logic |
| Retry handling and rate limits | Not Started | Celery config set; `tenacity` installed, unused |
| Deduplication and data integrity | In Progress | Hashing **Tested**; constraints modelled |
| Secure configuration management | Tested | Production startup refuses without signing secret, secure cookies, non-localhost DB, and no inline job execution |
| Clear error messages | Tested | Single error envelope with `code` + `correlation_id` on 404 and domain errors |
| Graceful degradation when sources fail | Tested | `/health/ready` returns `degraded` with per-component detail rather than raising; `run_pipeline` records a failed source and keeps storing the rest |
| Eight-stage discovery pipeline | In Progress | `Discover → Normalize → Validate → Deduplicate → Enrich → Score → Store → Report` order asserted; every stage except Enrich (placeholder) and Store (in-memory) is **Tested** |
| No single-provider dependency | In Progress | Adapter protocol satisfies it; only enforced once live adapters exist |

## Cross-cutting engineering rules (architecture section 25)

| Rule | Status | Evidence |
|---|---|---|
| Migrations for every schema change | **Tested** | Alembic async-aware; 4 revisions applied to a real PostgreSQL 18.6, verified by rebuilding from an empty database (37 tables, `alembic check` clean) |
| Never hardcode credentials | Tested | `.env` git-ignored, `.env.example` only; compose reads secrets from env |
| Never fake successful operations | Implemented | No seeded/demo data; dashboard renders an empty state instead of numbers |
| Do not silently ignore failures | Tested | Synchronous dispatcher raises on an unknown task instead of no-op |
| Preserve source attribution | Implemented | `source_record_links` + per-field `source_url`/`source_id` on contacts |
| Idempotency for background operations | Not Started | Phase 2 |
| Secrets out of browser bundles | Implemented | Only `NEXT_PUBLIC_API_BASE_URL` is exposed to the client |

## Security controls added by review (2026-11-02)

Several of these are not stated in the five source documents, which is itself the
finding: the specs describe *what* to collect but never *how* to treat collected text
as hostile input. They are recorded here so they cannot be dropped later.

| Control | Origin | Status | Evidence |
|---|---|---|---|
| SSRF gate for discovered URLs | Not in any document | **Tested** | `shared/url_safety.py` — 11 tests covering loopback, RFC1918, link-local, metadata IPs, split-horizon DNS, credential smuggling |
| Overpass tag whitelist | Implied by "responsible collection" | **Tested** | 5 injection payloads refused |
| Query fan-out ceilings | PRD §19 rate limits | **Tested** | Keyword, page, result, radius and element caps that configuration cannot raise |
| Untrusted text cleaning | PRD §17 | **Tested** | Markup, control and zero-width characters removed; widths clipped to schema bounds |
| CSV formula neutralisation | Not in any document | **Tested** | `= + - @` prefixes defanged; embedded CRLF cannot forge rows |
| Provenance preserved through merges | `database-schema.md` §12.2 | **Tested** | Loser's attributions transfer to the survivor |
| Correlation ID validation | `architecture.md` §20 | **Tested** | Hostile header discarded, clean header echoed |
| Query string excluded from logs | PRD §17 | **Tested** | Access log line asserted not to contain a token |
| Wildcard CORS refused | PRD §17 | **Tested** | Production config validation |
| Anti-enumeration login verification | Not in any document | **Tested** | Dummy-hash path costs the same verification |

### Security work still required by the documents

| Requirement | Source | Status |
|---|---|---|
| Secure authentication and sessions | PRD §17, `architecture.md` §19 | **Tested** — endpoints live; server-side revocation proven by replaying a stolen cookie |
| Authorization / ownership enforcement | PRD §17 | **Tested** — two users; read, shortlist, stage change, delete and export are cross-owner rejected with 404, and the store is owner-scoped at construction |
| CSRF protection | `architecture.md` §19 | **Tested** — missing, mismatched and forged cookie cases all rejected |
| Rate limiting | PRD §19, `architecture.md` §19 | **Tested** for login/registration. Limitation: in-process window, not shared between workers, resets on restart — Redis-backed later |
| Audit logging of important actions | PRD §17 | In Progress — auth paths **Tested** incl. durable failed-attempt writes; business, CRM, source-config, startup, social, export/import, analytics, automation and email writes all audit. Still to wire: the qualification, deduplication, enrichment and notification modules |
| Security headers / CSP | Not specified | Not Started — Phase 11 |
| Dependency vulnerability triage | Not specified | Not Started — 16 moderate npm advisories still untriaged |

## Background execution (Phase 1, implemented 2026-11-02)

| Capability | Status | Evidence |
|---|---|---|
| Job submission without blocking the API | **Tested** (inline) / configured (queued) | Inline dispatch runs the job after the response; the Celery path publishes to a broker. The queued path is not live-run here — no Redis on this machine |
| Worker processes the job | Configured, live-unverified | `sparkxflow.discovery.run_job` is the shared entry point for both the Celery worker and the inline runner; the inline path is fully exercised by tests |
| Exactly-once execution | **Tested** | `claim_job` transitions with `UPDATE … RETURNING`; a duplicate delivery returns `None` and `runner.execute` refuses to re-run (`test_job_lifecycle.py`) |
| Progress and final status persisted | **Tested** | `discovery_jobs` counters/report, `job_batches`, `job_logs` |
| Failed tasks retried safely | **Tested** | `POST /discovery/jobs/{id}/retry` re-queues failed/blocked/cancelled; refused for completed (409); cross-owner is 404 |
| Recovery after worker restart | **Tested** (logic) | `recover_stale_jobs` fails `running` jobs older than `stale_job_after_seconds`; broker-side redelivery comes from `acks_late` + `visibility_timeout`; live crash redelivery unverified without Redis |
| Duplicate job prevention | **Tested** | The atomic claim is the prevention — a re-delivered task is a no-op |
| Scheduled job execution | Configured, live-unverified | Celery beat schedule (`recover-stale-jobs` every 10 min) + `beat` compose service; needs a beat process |
| Health/readiness: DB, Redis, workers | **Tested** | `/health/ready` reports `database`, `redis`, `worker` individually |

## Startup Intelligence (Phase 3, implemented 2026-11-03)

Specified in `PRD.md` §8, `DESIGN.md` §7, `architecture.md` §14,
`database-schema.md` §13, and `implementation-roadmap.md` §8. Statuses describe
**code**, not documents.

| Capability | Status | Evidence |
|---|---|---|
| Startup records with source attribution | Implemented | `startups` table with `source_id` provenance fields on founders; manual entry names the source as `manual`. Discovery from configured sources is **Deferred** (below) |
| Research and compare startups | **Tested** | `startup_research_records` (findings + source references as JSONB); `last_researched_at` bumped on write, covered by `test_startups.py` |
| Revenue information is evidence-labelled | **Tested** | `classification` ∈ `verified`/`founder_reported`/`estimated`/`not_available` enforced in service + CHECK constraint; `not_available` requires null amount and `estimated` requires methodology — asserted in tests |
| Competitor tracking | **Tested** | self-reference rejected (422), duplicate pair is 409, cross-owner is 404 |
| Watchlists | **Tested** | create/list/delete, unique `(watchlist_id, startup_id)`, owner-scoped |
| Founders, products, pricing | **Tested** | CRUD owner-scoped; cross-owner read/delete returns 404 |
| Generate reports | **Tested** (saved reports) / Not Started (startup comparison) | `saved_reports` snapshots + CSV export cover startups (`startups_by_funding_stage`); side-by-side company comparison does not exist yet |
| Compare companies / market segments | Not Started | PRD §8; no comparison view exists yet |
| Ownership and CSRF on every write | **Tested** | all 21 routes use `CurrentUser` + CSRF; `test_another_user_cannot_read_or_delete` |
| Startup detail pages and dashboard | Implemented, browser-verified | `/startups` (create/filter/paginate/delete) and `/startups/[id]` (overview PATCH, revenue, competitors, founders, products, research, watchlists) verified against real PostgreSQL |
| Distinct from Leads while sharing infrastructure | Implemented | separate module (`app/modules/startups`), separate tables, same auth/CSRF/audit/ownership machinery |

**Deferred with reason — startup discovery from configured sources.** The one Phase 3
acceptance item in the roadmap that is not met. The existing adapters are Overpass
(geographic) and SearXNG (search); no startup-directory adapter exists. Product Hunt
requires an API key; Hacker News and GitHub are free candidates. Until one is chosen and
built, `/startups/discover` stays disabled rather than a nonfunctional control. Reports
and company comparison are also not yet built (Not Started above). No startup record is
invented — every row was created through the API by the operator.

## Social Intelligence (Phase 4, implemented 2026-11-03)

Specified in `PRD.md` §5, `architecture.md` §15 and `database-schema.md` §14. Statuses
describe **code**, not documents.

| Capability | Status | Evidence |
|---|---|---|
| Honest platform catalogue | **Tested** | `PLATFORM_DEFINITIONS` states each platform's permitted access; Reddit enabled, LinkedIn/Instagram/Facebook/X/YouTube disabled with their real terms; `test_platform_catalogue_seeds_honestly` |
| Research queries (create/list/run/delete) | **Tested** | `POST/GET/DELETE /social/research-queries`, `POST .../run`; disabled platform → 409, invalid config → 422, failed run marks `last_run_status=failed` |
| Reddit collection | **Tested** (mocked transport) | `RedditAdapter` validates query kind/sort/limit, one request, `follow_redirects=False`, descriptive User-Agent; 429/401/403/400 mapped to distinct errors |
| Content storage with deduplication | **Tested** | unique `(owner, platform, external_id)`; re-run reports `duplicates` instead of re-storing; `test_run_stores_content_and_dedups` |
| Content list/filter/export | **Tested** | platform/type/text filters; CSV export with neutralised formula values |
| Link content to business | **Tested** | `POST /social/content/{id}/link` → `BusinessSocialProfile`, audit `social.link` |
| Ownership and CSRF on every write | **Tested** | `test_cross_owner_isolation`; all writes CSRF-gated |
| Social workspace UI | Implemented, browser-verified | `/social` renders the catalogue, create/run/delete queries and the content table against real PostgreSQL; the live 403 is surfaced honestly |

**Deferred with reason — live Reddit reachability.** The full path is tested against a
mocked transport and browser-verified, but a live request from this client returns
**403** (unauthenticated JSON blocked). The UI reports that as a failure rather than
fabricating results. No other platform offers a permitted, key-free access method to
add.

## Automation Engine (Phase 5, implemented 2026-11-03)

Specified in `PRD.md` §10, `architecture.md` §16, `database-schema.md` §15–16, and
`implementation-roadmap.md`. Two modules — `automation` and `email` — sharing the
auth/CSRF/audit/ownership machinery. Statuses describe **code**, not documents.

| Capability | Status | Evidence |
|---|---|---|
| Versioned workflow definition | **Tested** | `workflows.workflow_definition` JSON of validated steps; `version` bumps only on a definition change; unsupported step type → 422, duplicate keys → 422 |
| Step engine runs in order, records each step | **Tested**, browser-verified | `run_workflow_execution` claims a `pending` execution (idempotent), executes `qualify`/`shortlist`/`email_draft`/`send`, one `workflow_step_executions` row per step; `test_run_workflow_*` |
| Steps connect to real logic | **Tested** | `qualify` calls the services-catalog scorer, `shortlist` the CRM repository, `email_draft` renders from the business's actual `website_status`/domain, `send` the SMTP path |
| Approval gate before any send | **Tested**, browser-verified | workflow drafts create an `email_send` `workflow_approvals` row and a `pending_approval` message; `send` refuses non-approved, suppressed, or accountless messages; `test_run_workflow_drafts_email_and_gates_on_approval`, `test_send_without_account_blocks_honestly` |
| Approval review flips the message | **Tested** | approve sets message `approved`, reject sets `rejected`; double review → 409; cross-owner review → 404 |
| Recurring schedules (interval + cron) | **Tested**, browser-verified | custom five-field cron parser + interval recurrence; `next_run_at` stored; invalid recurrence → 422, unknown timezone → 422; `next_cron`/`compute_next_run` unit-tested incl. Feb-31 → None |
| Email accounts, campaigns, messages, events, suppression | **Tested** | 5-table schema; account CRUD (duplicate → 409, unknown provider → 422), campaign CRUD, message lifecycle with events, suppression unique per owner+normalized email |
| Suppression enforced | **Tested** | a suppressed recipient is refused at draft (409); a suppressed message returns status `suppressed` on send |
| Secrets never stored in the database | Implemented | `email_accounts` holds `secret_reference` only; the spec's `encrypted_credentials` column is deliberately omitted in favour of an external secret manager |
| Ownership and CSRF on every write | **Tested** | all 32 routes use `CurrentUser` + CSRF; `test_cross_owner_cannot_see_or_run_workflow`, `test_cross_owner_email_isolation` |
| Workspaces UI | Implemented, browser-verified | `/automation/workflows`, `/automation/scheduler`, `/automation/approvals` and `/email` render and mutate against real PostgreSQL |

**Deferred with reason — live delivery and the queued path.** SMTP is proven only to the
provider boundary (and its honest refusals); no mail server/credentials exist here, so no
real delivery is claimed. Gmail OAuth reports itself unconfigured. The Celery `run_workflow`
task and the beat-driven `tick_schedules` are registered and tested but not run live because
Redis is absent — "run now" executes the same engine inline.

## Social & Demand Intelligence Engine (added directive, implemented 2026-11-03)

A separate standing directive extending `modules/social` (no competing package) with two
independent tracks over shared infrastructure. Maps the directive's §19 acceptance criteria
to real status; sources are labelled Operational / Partial / Unavailable / Planned honestly.

| Capability (directive §) | Status | Evidence |
|---|---|---|
| Create Demand + Business tracks (§6) | **Tested** | `social_search_tracks` with track_type demand\|business, keyword/phrase/exclusion/hashtag vocabulary, platforms, schedule; 422 on bad type/empty terms |
| Select supported sources (§6) | **Implemented, browser-verified** | catalogue exposes only permitted sources; Tracks UI multi-selects enabled platforms |
| Manual run through the real pipeline (§5,§11) | **Tested**, live-verified | `execute_track_run` normalise→classify→dedup→store; a **live Hacker News run** stored 50 real posts, classified Freelancer Hiring 5 / Service Needed 3 / General Discussion 6 / Unclassified 36 |
| Results persisted in PostgreSQL (§9) | **Tested** | intelligence columns on `social_content`; owner-scoped |
| Duplicate handling (§10) | **Tested** | within- and cross-source dedup by external id / canonical-URL fingerprint; attribution preserved; re-run does not inflate totals |
| Deterministic classification w/ evidence + confidence (§8) | **Tested** | intent required; keyword-without-intent demoted; negatives lower confidence; method+rule version stored; no mandatory AI/paid path |
| Inspect attribution + retrieval quality (§7,§12) | **Implemented, browser-verified** | retrieval_status kept separate from classification; source_attribution; UI shows labels + evidence |
| Filter and search results (§12) | **Tested** | `GET /social/results` filters (track_type/platform/classification/min_confidence/retrieval_status/needs_review/saved_only/query) + pagination |
| Save opportunities (§12) | **Tested**, browser-verified | `social_saved_items` note+tags; appears in Saved + Overview |
| Export records (§13) | **Tested** | CSV and JSON export of filtered/saved results, URLs + provenance preserved |
| Convert business record → Leads (§13) | **Tested** | `convert_result_to_lead` reuses `Business` with owner+domain dedup (no duplicate lead) + `BusinessSocialProfile` provenance; refuses without a real entity |
| Source health + run history visible (§13) | **Implemented, browser-verified** | `/social/platforms` health + last run/error; `social_discovery_runs` history; read-only Sources UI |
| Partial-source failure isolation (§11) | **Tested** | refused/unconfigured source → `completed_with_warnings`, other sources persist; never a fake success |
| Scheduled execution (§11) | **Implemented** (live-queued unverified) | interval/cron `next_run_at` (reuses automation recurrence); Celery `tick_tracks` registered; Redis absent so inline only |
| In-app alerts, no spam (§14) | **Tested** | high-confidence demand → `Notification`, deduped per content; no email required |
| Existing modules still work + cross-user boundaries (§19) | **Tested** | 388-test suite green incl. two-user isolation on tracks/results/save/convert |
| No paid API/AI required; LinkedIn honest (§5,§19) | **Implemented** | keyless connectors only; LinkedIn/IG/FB/X disabled with real terms; snippets only via SearXNG, labelled `indexed_snippet` |

**Engine — deferred with reason.** SearXNG needs a running instance (absent here) and
Reddit's public JSON returns 403 from this client — both reported honestly. Per-user source
enable/disable is deliberately omitted (a user must not mutate shared source state); Sources
is read-only. X, YouTube Data API and LinkedIn partner API connectors are unimplemented
rather than faked.

## Global Search (master-plan #26, implemented 2026-11-03)

| Requirement | Status | Evidence |
|---|---|---|
| One query across every owned entity | **Tested** | `GET /api/v1/search` groups businesses, startups, social results, saved items and tracks; a single query reaches all seeded surfaces |
| Reuse existing module queries, not a second search engine | **Implemented** | calls `list_businesses`, `list_startups`, `list_intelligence` and the track query; no duplicated filtering |
| Results are actionable | **Implemented, browser-verified** | each hit carries `kind`/`id`/`url`; `/search` links to the lead, startup or intelligence view |
| No fabricated ranking or totals | **Implemented** | the only aggregate is the sum of the group totals the per-entity queries actually returned |
| Owner isolation | **Tested** | a second account finds 0 of another user's rows |

**Not built:** Postgres full-text/tsvector and relevance ranking. Search is ILIKE, matching
the convention every other module already uses.

## Analytics and Reports (master-plan #27, implemented 2026-11-03)

| Requirement | Status | Evidence |
|---|---|---|
| Dashboard metrics are real | **Tested** | nine `GROUP BY` surfaces over the operator's rows; a fresh account gets empty lists, not zeros (`test_analytics_is_empty_before_any_data`) |
| Counts are exact, not sampled | **Tested** | seeded quantities asserted bucket-for-bucket (`test_analytics_buckets_count_exactly_the_seeded_rows`) |
| Soft-deleted leads excluded | **Tested** | `deleted_at` removes a lead from the total and both lead buckets |
| CRM and opportunity counts come from the real flows | **Tested** | shortlist + qualify routes produce the rows the analytics then counts |
| Export | **Tested**, browser-verified | `GET /analytics/export` CSV mirrors the JSON summary row-for-row |
| Saved reports | **Tested**, browser-verified | `saved_reports` + CRUD; snapshot equals the live summary at capture and does not drift when new data arrives |
| Reports are point-in-time | **Tested** | after a fourth lead, live reads 4 and the stored snapshot still reads 3 |
| Ownership and CSRF | **Tested** | another owner gets 404 on read/export/delete; POST/DELETE without a CSRF token are refused |
| Audited | **Tested** (row observed live) | `report.saved`, `report.deleted`, `export.create` in `audit_logs` |

**Not built:** scheduled report generation, PDF/Excel output, time-series trending
(`captured_at` stores one instant, so a chart across captures is future work) and startup
side-by-side comparison. Analytics covers the surfaces that actually have rows; it does not
invent a section for a module with no data model behind it.

## Source Manager (master-plan #28, implemented 2026-11-03)

| Requirement (PRD §6, DESIGN §10) | Status | Evidence |
|---|---|---|
| Enable or disable individual sources | **Tested** | `POST /sources/{slug}/enable|disable` per account, and **honoured by the runners**: a disabled source is never queried by a discovery job (`test_disabled_source_is_skipped_by_a_discovery_job` asserts the stub's call list is empty and its business never appears), and a track records the skip rather than faking success |
| No provider becomes a critical dependency | **Tested** | a job whose every source is disabled fails with the reason named instead of silently returning nothing; one refused source leaves the others running |
| View source status | **Tested** | `GET /sources` grouped by category; provider-wide and per-account state reported separately so one user cannot appear to change another's |
| Health: working / degraded / failed | **Tested**, browser-verified | `POST /sources/{slug}/test` calls the adapter's own `health_check()` and records a `source_health_checks` row; live HN probe returned working in 1541 ms, SearXNG honestly `failed — ConnectError` |
| Never a badge without evidence | **Tested** | an unprobed row shows `unknown` with no last-check (`test_a_source_that_has_never_been_probed_claims_no_health`); RSS reports *per-feed, unknown* rather than inventing a provider-wide answer |
| Last successful run | **Tested** | taken from `source_usage_records.measured_at`, written only by runs that completed for that source |
| Recent errors | **Tested** | `sources.last_error` set from a real refusal, shown on the card and in history |
| Usage / quota information | **Partially Implemented** | requests made, records returned and (for social tracks) records accepted are recorded and aggregated. **Quota is Deferred**: no free connector here exposes quota headers, so `quota_remaining` stays null rather than estimated |
| Coverage and limitations visible | **Tested** | generated from `AdapterCapabilities`, not hand-written; a row that stops matching its adapter is re-synced (`test_the_manager_repairs_a_row_that_stopped_matching_its_adapter`) |
| Configure action | **Tested** | per-account RSS feed list, validated by the real connector — so the existing SSRF guard rejects loopback/private and non-http targets at save time — and refused for a source that cannot use it |
| Configuration is actually read | **Tested** | the track runner falls back to the account's configured feeds when a track names none (`test_track_uses_feeds_configured_in_the_source_manager`) |
| View history | Implemented, browser-verified | `GET /sources/{slug}/history` returns probes and per-source run counters, newest first |
| Grouped by discovery category | Implemented, browser-verified | Geographic / Search / Social grouping from the registry's own `category` |
| Per-user isolation | **Tested** | disable and configuration are owner-scoped; a second account sees `enabled_for_user: true` and `no configuration` while the first is disabled |
| Source failure must not disable the platform | **Tested** | skips are recorded per source; the job and the run both continue with the sources that answered |

**Deferred with reason.** Provider-wide enable/disable needs an admin role that does not
exist yet — `sources.is_enabled` is read and enforced, but no control is exposed for it.
Credential entry is out of scope: only `secret_reference` is stored, never a value. The
startup connectors (Product Hunt, GitHub) are still unimplemented from Phase 3, so they are
absent from the manager rather than listed as broken.

## Import and Export (master-plan #29, implemented 2026-11-03)

| Requirement (PRD §7.8, roadmap "Data management") | Status | Evidence |
|---|---|---|
| CSV export | **Tested**, browser-verified | `POST /exports` → `GET /exports/{id}/download`; the exported CSV carried the leading-zero phone number quoted rather than coerced to a number |
| Excel (XLSX) export | **Tested** | `openpyxl` writer; `phone`, `email` and `postal_code` are written as text cells, and a value starting `=`, `+`, `-` or `@` is neutralised instead of becoming a formula |
| JSON export | **Tested** | the same renderer serves `application/json` for the same rows |
| Excel and CSV import | **Tested**, browser-verified | a real CSV uploaded through `/settings` produced 3 businesses with their phone numbers intact as text, visible on the Leads Dashboard |
| Duplicate-safe imports | **Tested** | the three strategies the roadmap names — `skip`, `merge`, `create` — each covered; the run reports created / merged / duplicates skipped separately |
| The import lands in the real model | **Tested** | rows are written to `businesses` and `business_contacts`, with `source_slug = file_import` so provenance survives |
| Import errors are reported honestly | **Tested** | the job row carries processed / failed counts and the per-row errors with their spreadsheet row numbers; reported errors are capped at 100 so a broken file cannot produce a megabyte of JSON |
| An impossible mapping is refused before work is queued | **Tested** | the mapping is validated against the uploaded file before the job is queued, so a bad mapping is a 422 rather than a job that fails later (`test_a_mapping_naming_a_column_the_file_does_not_have_is_refused`) |
| Import provenance is visible | Implemented, browser-verified | the Source Manager shows `File import` under **Imported files**, states that there is no provider behind it, and offers no Enable or Test control for it |
| The platform's own data can be exported per module | **Tested** | four modules — leads, collected content, classified demand results, startups — each using the column set its owning module already uses, so the ad-hoc CSV endpoints and the exporter cannot drift |
| An export filter is really applied | **Tested** | `shortlisted_only` was accepted by the API and then silently ignored, returning every record the account owned; it now resolves against the CRM stage, owner-scoped, and the export honours it |
| Exports are real jobs, not a held-open request | **Tested** | the create returns `queued`; the file appears on a later read of the job row. The row records what was asked for and what came out |
| Retention and cleanup | **Tested** | `purge_expired_files` deletes files past `export_retention_hours` / `import_retention_hours`, driven by the row's own `expires_at`, with a file-age sweep as an orphan backstop |
| Ownership | **Tested** | storage keys are `exports/{owner}/{job}.{ext}`; another account's job is a 404 and its file cannot be addressed |
| CSRF and audit | **Tested** | writes are CSRF-guarded; `export.create`, `export.download`, `export.delete`, `import.create`, `import.run` and `import.delete` are reserved audit actions |
| Rate limits | Implemented | 20 exports per 5 minutes, 5 uploads per hour, per account |
| The Data surface | Implemented, browser-verified | `/settings` renders the export panel (module, format, filters, column selection, recent exports, download) and the import panel (upload, mapping, duplicate strategy, per-row outcome) |

**Not built.** JSON *import* — the PRD asks for CSV and Excel on the way in; JSON is
export-only and is not advertised as an import format. Google Sheets two-way sync
remains deferred under D6. There is no object-store adapter: `LocalFileStorage` writes
under `backend/var/`, and the `StorageAdapter` boundary exists so one can replace it,
but no cloud adapter is implemented and none is claimed.

## Deferred (with reason — see IMPLEMENTATION_PLAN.md section 7)

Hybrid worker dispatch and heartbeats · Google Sheets two-way sync · cloud browser
automation · PostGIS · dedicated search engine · multi-tenancy · auto-send email ·
object-store storage adapter · JSON as an import format.

## Known gaps to close before they become expensive

1. **D4 is partly measured, and it already changed the code.** A live Overpass query
   returned 16 real Hisar hospitals and exposed an identity bug that had been
   silently destroying records (see `PROJECT_STATUS.md` section 9). SearXNG remains
   unmeasured — no instance exists here — and Delhi/Gurugram coverage plus the tile
   curve are blocked on a saturated public endpoint, not on our code.
2. ~~`signal_key` has no defined vocabulary~~ **Closed** —
   `app/shared/signals.py` now defines the contract, with the rule that a signal is an
   observation and `None` never becomes `False`. The starter list covers identity,
   website, activity and freshness; extend it as enrichment lands.
3. ~~Auth is implemented but unexercised~~ **Unblocked** — a real PostgreSQL is running;
   the endpoints and their integration tests are Phase 2 work, not a missing dependency.
4. ~~The in-memory store is not the real store~~ **Closed** — `SqlBusinessStore` is
   implemented and tested against PostgreSQL. The pipeline still defaults to the
   in-memory store; jobs must pass the SQL one, which is Phase 3 step 2.
5. **Live network verification has not happened.** The first real SearXNG and Overpass
   calls will be the first test of the error taxonomies against actual failures such as
   bot protection and instance throttling.
