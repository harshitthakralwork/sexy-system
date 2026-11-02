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
| Search by country/state/city/locality + category | Not Started | `DiscoveryQuery` carries `country`, `category` and `place_name`, but nothing resolves an administrative cascade into geometry |
| Radius selection | Implemented in the API, no UI | `POST /api/v1/discovery/jobs` accepts centre + `radius_km` (bounded `0 < r <= 50`, validated against the Overpass ceiling); `LocationSpec` enforcement is **Tested** in the adapter tests, an end-to-end radius job is not |
| Rectangle and polygon drawing | Not Started | Frontend has no map library installed; `search_areas` table does not exist |
| Save/load search areas | Not Started | `search_areas` is specified in `database-schema.md` §7.6, with no migration written |
| Grid tiling for large regions | Not Started | `job_batches` exists as a model with no tile columns and no writer; the planner is unwritten |
| Per-tile progress, retry, resume | Partial | Job-level progress and cancel are **Tested** (14 tests in `tests/test_discovery_jobs.py`); per-tile granularity is the missing layer |
| Discovery job over an area | Not Started | `POST /api/v1/discovery/jobs` accepts keywords, category and a centre/radius payload today; area ids are not accepted |
| Overpass geographic adapter | Implemented, live-unverified | Query builder, tag whitelist, coordinate/radius validation and element cap are **Tested** against mocked transports; no real endpoint has been called yet |
| SearXNG as a non-spatial source | Implemented, live-unverified | Adapter **Tested** with mocks; per §9.4 it must degrade to administrative text, which is not implemented |
| Pins, clustering, marker preview | Not Started | Sidebar exposes "Map Explorer" as a disabled control; nothing renders |
| Map ↔ table sync | Not Started | The businesses API filters and paginates but accepts no `bbox`, so there is no viewport query to share |
| Map filters (rating, reviews) | Not Started | `rating` / `review_count` columns are specified but not migrated. Of the required dimensions, `website_status` is already an owner-scoped filter on the businesses API; **phone availability is not**, and neither is rating or review count |
| Dedup across overlapping searches | Partial | Identity rules (domain, then phone, never name alone) and provenance-preserving merges are **Tested**; nothing yet exercises them across two geographic units |
| Provenance per tile | Not Started | `source_records.job_id` is written and **Tested**; `batch_id` does not exist |
| Live job progress with named failures | **Tested** | `discovery_jobs.report` carries per-source outcomes and counters; a failed source yields `failed`, and a partial one `completed` with the failure named |
| Export the current selection | Partial | CSV export with formula neutralisation is **Tested** end-to-end; exporting a *map* selection waits on the map |
| Bounds, throttles, no keyed provider | Partial | Keyword/page/radius/element caps are **Tested** at the adapter level, and job creation is CSRF-gated (**Tested**). The 10-jobs-per-5-minutes limit is implemented but has no test yet. No per-user geographic request quota exists |

**Honest limits.** Nothing in this feature has been demonstrated against a live map
provider. The two things that would falsify the plan fastest are (1) how many usable
Indian business records Overpass actually returns for a Bengaluru radius, which is the
pending D4 measurement, and (2) whether tile counts stay inside a public instance's
tolerance. Both must be measured before the UI work in this section is scheduled.

## MVP definition of done (PRD section 21)

| # | Requirement | Where it lands | Status | Evidence |
|---|---|---|---|---|
| 1 | Open and securely access the platform | `modules/auth` | **Tested** | Register, login, logout, session; 13 authentication tests + live HTTP smoke test |
| 2 | Discover businesses using supported sources | `modules/discovery/adapters` | **Implemented** | SearXNG + Overpass adapters written against the `DiscoveryAdapter` contract; **Tested** with mocked transports (17 tests). Not yet run against a live instance |
| 3 | View results in tables and on a map | frontend leads screens | Not Started | Phase 2a (table) / 2b (map) |
| 4 | Research individual business profiles | `modules/businesses` | Not Started | Phase 2a |
| 5 | Filter and deduplicate discovered businesses | `shared/normalization`, `modules/deduplication` | **Tested** | 13 normalisation + 10 deduplication tests. Confirmed auto-merges; probable/possible become a review backlog |
| 6 | Evaluate businesses against configurable services | `shared/signals`, `shared/scoring`, `services_catalog` | **Tested** | Deterministic evaluator (12 tests) + canonical signal vocabulary. Storage models implemented, not yet exercised against a database |
| 7 | Shortlist promising opportunities | `modules/crm/service.py`, `modules/businesses` | **Tested** | Shortlist endpoint with ownership enforcement, stage history and activity; cross-owner shortlist rejected |
| 8 | Manage shortlisted businesses through a CRM pipeline | `modules/crm` | Implemented | Per-owner default pipeline with the 12 documented stages, stage moves recorded with history. Kanban UI is Phase 6 |
| 9 | Export data to CSV or Excel | `modules/exports/csv_export.py` | **Implemented** | CSV writer **Tested** (13 tests) incl. spreadsheet-formula neutralisation. Excel export and job persistence pending the database |
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
| Audit logging of important actions | PRD §17 | In Progress — auth paths **Tested** incl. durable failed-attempt writes; business/export actions done, CRM and source-config writes still to wire |
| Security headers / CSP | Not specified | Not Started — Phase 11 |
| Dependency vulnerability triage | Not specified | Not Started — 16 moderate npm advisories still untriaged |

## Deferred (with reason — see IMPLEMENTATION_PLAN.md section 7)

Hybrid worker dispatch and heartbeats · Google Sheets two-way sync · cloud browser
automation · PostGIS · dedicated search engine · multi-tenancy · auto-send email ·
Startup Intelligence tables · Social Intelligence tables.

## Known gaps to close before they become expensive

1. **D4 has no measured basis yet.** Nothing verifies that SearXNG or Overpass
   actually return usable Indian business records. Both adapters are tested against
   mocked transports, which proves the code and not the data. Phase 2a exists to
   measure this; if the counts are thin, D4 must be revisited before UI work
   multiplies the mistake.
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
