# SparkXFlow — Implementation Roadmap

**Document:** `implementation-roadmap.md`  
**Project:** SparkXFlow  
**Approach:** Greenfield development — start from an empty project folder  
**Execution model:** Hybrid local + cloud  
**Development principle:** Build in controlled phases, with working and tested deliverables at every stage.

---

## 1. Purpose

This roadmap defines how SparkXFlow will be built from scratch.

The five project documents must be provided to the coding agent together:

1. `PRD.md` — product requirements and functionality.
2. `design.md` — UI/UX and visual design.
3. `architecture.md` — technical architecture.
4. `database-schema.md` — data model and relationships.
5. `implementation-roadmap.md` — development sequence and acceptance criteria.

The agent must understand the complete product before beginning implementation. However, it must build the system incrementally rather than attempting to generate the entire platform in one operation.

## 2. Global implementation rules

- Treat all five documents as the project's source of truth.
- Start from the empty project folder; do not assume an existing codebase.
- Do not silently omit specified functionality.
- Do not invent integrations, API capabilities, data, or successful results.
- Prefer free, open-source, self-hosted, and free-tier options.
- Verify current provider limits, pricing, and terms before depending on them.
- Keep paid services optional wherever technically possible.
- Keep the application modular and maintainable.
- Use real database-backed functionality rather than static mock data.
- Build reusable components and source adapters.
- Keep credentials and secrets out of frontend code and source control.
- Add automated tests as features are implemented.
- Maintain a project progress tracker and update it after each meaningful milestone.
- Do not start a new phase while the previous phase's acceptance criteria remain unfulfilled, unless a documented dependency requires parallel work.

## 3. Phase 0 — Project understanding and setup

### Objectives

Understand the five documents, establish the development plan, and prepare the empty folder.

### Tasks

1. Read all five documents completely.
2. Identify dependencies, contradictions, missing details, and technical risks.
3. Resolve conflicts using the PRD as the product authority and architecture/schema documents as technical authorities.
4. Create a task breakdown covering every major requirement.
5. Identify which Qoder custom agents and AgencyAgents roles are actually useful.
6. Inspect the development environment before assuming Docker, WSL, or other tools are installed.
7. Scaffold the project from scratch.

### Initial setup deliverables

- Git repository and `.gitignore`.
- Frontend and backend project structure.
- Dependency and package configuration.
- `.env.example` containing variable names but no real secrets.
- README with setup instructions.
- Development scripts.
- Initial database migration setup.
- Testing and linting configuration.
- Project progress tracker.
- Clear local development instructions for Windows.

### Acceptance criteria

- The frontend starts successfully.
- The backend starts successfully.
- Configuration is documented.
- No secrets are committed.
- The initial project structure follows the architecture document.
- The agent has a traceable implementation plan.

## 4. Phase 1 — Core foundation

**Priority: Critical**

### Objectives

Build the shared infrastructure required by all product modules.

### Tasks

- PostgreSQL database setup.
- Redis and background job infrastructure.
- Backend configuration and modular structure.
- Frontend application shell.
- Authentication and secure session management.
- Main dashboard layout and sidebar navigation.
- Shared design system and reusable UI components.
- Database migrations and seed data for development.
- Background job status and execution history.
- Source Manager foundation.
- Application logging and error handling.
- Basic monitoring and health checks.
- Backup and recovery foundation.

### Acceptance criteria

- A user can securely log in.
- The dashboard loads from the actual backend.
- Database operations work.
- Background jobs can be queued, executed, and monitored.
- Source Manager displays real configured source status.
- Application errors are logged appropriately.
- Local development setup is repeatable.

## 5. Phase 2 — Leads Intelligence MVP

**Priority: Highest product priority**

### Objectives

Deliver the first genuinely usable business-discovery and lead-management workflow.

### Tasks

**Discovery**
- Keyword-based business discovery.
- Location-based discovery.
- Geographic map search.
- Search provider adapters.
- OpenStreetMap-based geographic functionality.
- Search configuration and saved presets.

**Map-Based Business Discovery**
- Store a drawn or resolved area: circle (centre + radius), rectangle, polygon, and
  administrative (country → state → city → locality) scopes.
- Validate and bound geometry server-side before any provider is contacted; refuse an
  oversized area with a reason and a smaller workable unit rather than clipping it.
- Deterministic grid tiling for regions larger than one request, one `job_batches` row
  per tile with its bounds, tile identity, source, and counters.
- Tile queue with bounded concurrency, per-tile retry, cancel between tiles, and
  resume that skips tiles already done.
- Truncation detection: a tile returning the provider's element cap is subdivided or
  reported, never presented as a complete answer.
- Adapter capability declarations for geometry support, so a source that cannot answer
  a spatial question is not credited with having answered one.
- Viewport-bounded, owner-scoped pin query, with unlocated records still counted.
- Map Explorer: pins, clustering, marker preview with source and retrieval time.
- Area drawing tools with editable, closable and deletable shapes, plus tile grid
  overlay showing per-tile state by icon and text as well as colour.
- Map ↔ results table shared state: filters, sort, selection, bulk actions, export.
- Map filters on the dimensions the data supports: category, rating, review count,
  website availability, phone availability — each distinguishing absent from known-missing.
- Deduplication across overlapping and repeated areas using the shared identity rules,
  merging provenance rather than creating second leads.
- Saved areas: create, list, rename, delete, re-run, and see job history per area.
- Live job progress on the map from observed counters, with named source failures.
- Export the current map selection, producing the same rows the table would export.

**Processing**
- Data normalization.
- Duplicate detection.
- Source attribution.
- Contact extraction from permitted public sources.
- Contact verification status.
- Business profile enrichment.
- Evidence-based opportunity scoring.

**User interface**
- Leads dashboard.
- Interactive full-screen map.
- Table and list views.
- Business detail pages.
- Advanced filters.
- Global search.
- Raw, filtered, and qualified result views.
- Bulk actions.

**Lead management**
- Configurable CRM stages.
- Shortlisting and tagging.
- Activity history.
- Custom fields.
- Service Catalog.
- Service-specific opportunity scoring.

**Data management**
- CSV and Excel import/export.
- JSON export.
- Google Sheets integration where configured.
- Duplicate-safe imports.
- Retention and cleanup jobs.

### Acceptance criteria

A user can:

1. Create a business discovery search.
2. Discover businesses using supported sources.
3. View results on a map and in a table.
4. Open a business profile.
5. Review extracted contact information and its source.
6. Filter and search results.
7. Shortlist a business.
8. Move it through CRM stages.
9. Export selected records.
10. Review search and job history.
11. Draw a rectangle or polygon, or pick a radius, and start a real discovery job over
    exactly that area.
12. Watch a large region progress tile by tile, see which tiles failed and why, retry
    one tile, and cancel the rest without losing what was already stored.
13. See discovered businesses as pins, clustered at low zoom, with each pin naming the
    source and retrieval time behind it.
14. Filter, select and bulk-act on the same records from the map and the table, and
    export the shared selection.
15. Save an area, come back later, re-run it, and see new businesses as new rather
    than as repeat discoveries of the same ones.

An empty map must always be explained by the sources that were asked, never
presented as evidence that no businesses exist in the area. Map discovery must not
depend on a keyed commercial map provider, and its request volume must stay within
the declared limits for shared public infrastructure.

This phase must produce a real, end-to-end usable Leads Intelligence workflow. It must not rely on fake scraping results.

## 6. Phase 3 — Social Intelligence

### Objectives

Add configurable public social and community intelligence.

### Initial platforms

- LinkedIn.
- Reddit.
- Instagram.
- Facebook.
- X.
- YouTube.

### Tasks

- Platform-specific source adapters.
- User-defined keywords, hashtags, usernames, and profiles.
- Available date and location filters.
- Configurable extraction limits.
- Source-specific extraction rules.
- Result normalization.
- Duplicate detection.
- Source attribution and retrieval timestamps.
- Social search history.
- Results filtering and export.

### Important constraints

Platform capabilities differ. The application must not promise access to unavailable or restricted data.

Use permitted public access and documented APIs where available. Do not build credential abuse, unauthorized private endpoint access, CAPTCHA bypass, or access-control circumvention.

### Acceptance criteria

- Users can configure social searches.
- Supported sources return clearly attributed results.
- Unsupported or restricted sources display honest status messages.
- Users can filter and export collected results.
- Social results can be linked to relevant business records without silently merging uncertain matches.

## 7. Phase 4 — Automation Engine

### Objectives

Turn discovery and research into controlled, repeatable workflows.

### Tasks

- Custom scheduler.
- Recurring search configurations.
- Workflow manager.
- Trigger and rules engine.
- Automated discovery.
- Automated research and qualification.
- Automated shortlisting rules.
- Personalized email draft generation.
- Approval queue.
- Gmail OAuth integration.
- Email sending adapter.
- Campaign tracking.
- Reply and outcome tracking.
- Suppression and opt-out management.
- Failure notifications and execution history.

### Email workflow

The initial workflow must require approval before sending.

The system should support this sequence:

`Trigger → Discover → Research → Qualify → Shortlist → Draft Email → Human Approval → Send → Track Reply`

Automatic sending may be introduced later under explicit user-configured limits and safeguards.

### Acceptance criteria

- Users can create and schedule workflows.
- Multiple workflows can operate independently.
- Every execution has its own history.
- Email drafts are generated using actual lead context.
- Sending requires approval initially.
- Sending outcomes and failures are recorded.
- Opt-outs and suppression rules are respected.

## 8. Phase 5 — Startup Intelligence

### Objectives

Build the independent startup and market research module.

### Tasks

**Discovery**
- Product Hunt discovery.
- Hacker News discovery.
- Reddit discovery.
- GitHub and open-source project discovery.
- Startup directories and public company databases.
- Company website and pricing-page research.

**Intelligence**
- Startup profiles.
- Founder and company research.
- Product launch tracking.
- Competitor tracking.
- Industry and geography trends.
- Market opportunity research.
- Pricing history where evidence exists.
- Revenue intelligence.

**Revenue evidence categories**
- Verified.
- Founder Reported.
- Estimated.
- Not Available.

Every estimate must include its methodology and assumptions. Revenue must never be represented as profit.

**User interface**
- Separate Startup Intelligence dashboard.
- Search and filtering.
- Startup detail pages.
- Watchlists.
- Research history.
- Reports and exports.

### Acceptance criteria

- Users can discover startups from configured sources.
- Startup records include source attribution.
- Users can research and compare startups.
- Revenue information is evidence-labelled.
- Users can create watchlists and generate reports.
- Startup Intelligence remains distinct from Leads Intelligence while sharing common infrastructure.

## 9. Phase 6 — Advanced intelligence and optimization

### Objectives

Improve the platform after the core modules are working reliably.

### Potential tasks

- Advanced analytics.
- More sophisticated opportunity scoring.
- Local AI model integration.
- Optional free AI provider integrations.
- Advanced research summaries.
- Improved relationship discovery.
- More detailed source performance analytics.
- Advanced workflow automation.
- Additional CRM and reporting capabilities.
- Performance optimization.
- Additional integrations.

AI must remain optional. Core product functionality must continue working without an AI provider.

## 10. Deployment and operations

### Initial deployment direction

- Frontend: Vercel.
- Backend and workers: Railway.
- Alternative backend deployment: Render.
- Database: PostgreSQL.
- Queue: Redis.
- File storage: select a suitable free or self-hosted option.

Verify current pricing, free-tier limitations, persistent storage rules, and service availability before deployment. Do not assume any hosting provider will offer permanent free hosting.

### Hybrid execution

The application should support:

- Local development and optional local workloads.
- Cloud-hosted application access.
- Cloud background workers.
- Optional local execution for heavier jobs.
- Resumable jobs.
- Retry and failure handling.
- Workload movement between local and cloud environments without architectural redesign.

The cloud application should remain accessible when the user's personal PC is switched off. Local AI and local-only workloads naturally require the PC to be running.

### Operational requirements

- Environment-specific configuration.
- Secure secret management.
- Database migrations.
- Scheduled backups.
- Restore testing.
- Health checks.
- Job monitoring.
- Source health monitoring.
- Error reporting.
- Data export and recovery procedures.

## 11. Quality gates

Every phase must pass these checks before being considered complete.

### Code quality
- Type checking.
- Linting.
- Formatting.
- Consistent project structure.
- No unnecessary duplicated logic.

### Testing
- Unit tests for core logic.
- Integration tests for database and backend operations.
- API tests.
- Frontend interaction tests for critical workflows.
- End-to-end tests for important user journeys.

### Security
- Authentication and authorization checks.
- Input validation.
- Secret handling.
- Safe error responses.
- No exposed API credentials.
- Appropriate rate limiting.
- Audit logging for important operations.

### Product quality
- Functional UI controls.
- Loading, empty, success, and error states.
- Responsive layout.
- Clear source attribution.
- No misleading metrics.
- No fabricated business or startup records presented as real data.

## 12. Progress tracking

Maintain a `PROJECT_STATUS.md` file in the project root.

It must include:

- Current phase.
- Completed tasks.
- In-progress tasks.
- Blocked tasks.
- Remaining tasks.
- Test status.
- Known bugs.
- Architecture decisions.
- Next recommended tasks.

Also maintain a requirements traceability checklist linking major PRD requirements to their implementation status and tests.

Use these statuses:

- Not Started.
- In Progress.
- Implemented.
- Tested.
- Blocked.
- Deferred — with documented reason.

Do not mark a feature complete merely because its UI exists. It must work end-to-end and pass its relevant tests.

## 13. Definition of done

A phase is complete only when:

1. Its required functionality is implemented.
2. The relevant database and API work is complete.
3. The UI is connected to real functionality.
4. Tests pass.
5. Security and error handling have been considered.
6. Documentation is updated.
7. Known limitations are recorded.
8. The progress tracker is updated.

## 14. Final development principle

SparkXFlow is a long-term platform, but development must produce useful working software at every stage.

The priority is not to create the largest possible codebase as quickly as possible. The priority is to build a reliable foundation, deliver a genuinely usable Leads Intelligence MVP, and then expand into Social Intelligence, Automation Engine, and Startup Intelligence.

The complete product vision must remain represented in the architecture and documentation from day one, even though implementation happens in phases.

**Build the whole vision deliberately. Deliver each phase properly. Never confuse a large feature list with a finished product.**