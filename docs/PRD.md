# SparkXFlow — Product Requirements Document (PRD)

**Product:** SparkXFlow  
**Category:** Business & Market Intelligence Platform  
**Document:** Product Requirements Document  
**Version:** 1.0  
**Status:** Initial specification  
**Development approach:** Greenfield — built from scratch

---

## 1. Product Overview

SparkXFlow is a Business & Market Intelligence Operating System designed to discover businesses, research markets, identify opportunities, manage leads, and automate business development workflows.

It combines two primary intelligence modules:

1. **Leads Intelligence** — discovers and researches businesses, identifies potential service opportunities, and manages prospects.
2. **Startup Intelligence** — researches startups, SaaS products, founders, competitors, market trends, and emerging opportunities.

A shared **Automation Engine** connects these modules with scheduled research, qualification workflows, email drafting, approvals, and other repeatable tasks.

SparkXFlow is not simply a Google Maps scraper or a traditional CRM. It is intended to become a unified intelligence and business-development workspace.

## 2. Product Vision

Build a powerful, extensible intelligence platform that can operate locally or in the cloud, relies primarily on free and open-source technology, and does not require paid AI or data APIs to perform its core functions.

The long-term vision is to help users answer:

- Which businesses exist in a particular market?
- Which businesses have a genuine opportunity for a particular service?
- What information is publicly available about a business?
- Which startups and products are emerging?
- What are competitors doing?
- What market opportunities are developing?
- Which opportunities deserve attention?
- How can repetitive research and outreach work be automated responsibly?

## 3. Product Principles

1. **Free-first:** No mandatory paid APIs, AI providers, subscriptions, or proprietary data services.
2. **AI optional:** Core functionality must work without AI.
3. **Source diversity:** Never depend on one discovery provider.
4. **Evidence-based intelligence:** Scores and conclusions must show their supporting evidence.
5. **User control:** Users control filters, qualification criteria, shortlists, and automation approvals.
6. **Data transparency:** Preserve source attribution, retrieval dates, and verification status.
7. **Privacy and security:** Protect credentials, personal data, and business information.
8. **Modular architecture:** New intelligence modules and integrations should be addable without redesigning the platform.
9. **Responsible collection:** Respect source terms, access restrictions, privacy requirements, and applicable laws.
10. **Useful before extensive:** Deliver a functional Leads Intelligence MVP before expanding into every advanced capability.

## 4. Target Users

### Initial user

A private, single-user workspace for operating and developing the platform.

### Future users

- Sales and business development professionals.
- Digital and technology agencies.
- Market researchers.
- Startup founders.
- Competitive intelligence teams.
- Business consultants.

The system should allow future multi-user support without making the initial release unnecessarily complex.

## 5. Main Product Modules

### 5.1 Leads Intelligence

The primary business discovery and prospect research module.

**Core capabilities:**

- Discover businesses by keyword, industry, geography, and other criteria.
- Search using map-based and conventional search interfaces.
- Research business websites and publicly accessible information.
- Extract permitted public contact information.
- Identify potential service opportunities.
- Evaluate businesses against multiple services.
- Filter, shortlist, tag, archive, and manage businesses.
- Export results and connect optional external spreadsheets.
- Track outreach and CRM pipeline activity.

**Initial service categories:**

- Website development.
- Web applications.
- E-commerce.
- Business automation.
- AI integrations.
- SEO and digital presence.
- Custom software solutions.

Services must be configurable rather than hardcoded.

### 5.2 Startup Intelligence

A separate research workspace for discovering and analysing startups and technology companies.

**Core capabilities:**

- Discover startups and SaaS products.
- Identify new product launches.
- Research founders and companies using permitted public information.
- Monitor competitors.
- Track pricing and product changes.
- Identify emerging industries and market opportunities.
- Maintain startup watchlists.
- Generate research reports.

**Initial discovery sources:**

- Product Hunt.
- Hacker News.
- Reddit.
- GitHub and open-source projects.
- Public startup directories.
- Company websites.
- Public pricing pages and changelogs.
- Search engines through configured discovery providers.

Startup Intelligence begins as a private research dashboard. A public startup directory is a possible future expansion, not an initial requirement.

### 5.3 Social Intelligence

A configurable public-data research feature.

Users should be able to choose:

- Platform.
- Keywords and search terms.
- Hashtags.
- Public usernames or profiles.
- Available geography and date filters.
- Requested data fields.
- Collection limits.

Initial platforms to investigate:

- LinkedIn.
- Reddit.
- Instagram.
- Facebook.
- X.
- YouTube.

Actual coverage and available fields depend on each platform's permitted access methods. The product must not promise unrestricted collection.

Social Intelligence is not restricted to finding sales prospects. Users control how collected information is filtered and used.

### 5.4 Automation Engine

A shared engine for executing repeatable workflows.

**Initial capabilities:**

- Manual and scheduled triggers.
- Business discovery.
- Research and enrichment.
- Configurable qualification.
- Automatic shortlisting based on user-defined rules.
- Personalized email drafting.
- Human approval before sending.
- Sending through supported email integrations.
- Reply and outcome tracking.
- Workflow execution history.

The initial email workflow must require approval before sending. Controlled auto-send can be considered later with explicit limits and safeguards.

## 6. Discovery Architecture — Product Requirements

SparkXFlow must support four independent discovery channels.

| Channel | Purpose |
|---|---|
| Search Intelligence | Discover information through search engines and indexed websites |
| Geographic Intelligence | Discover businesses by location and geographic area |
| Opportunity Intelligence | Identify signals such as missing websites, outdated websites, or business activity |
| Social Intelligence | Research permitted public social and community information |

All discovery channels feed a shared processing pipeline:

**Discover → Normalize → Validate → Deduplicate → Enrich → Score → Store → Report**

### Source Manager

A dedicated dashboard must allow users to:

- Enable or disable individual sources.
- View source status.
- View source health: working, degraded, or failed.
- See the last successful run.
- See recent errors.
- View available usage or quota information.
- Understand source coverage and limitations.

No single provider should become a critical dependency.

## 7. Leads Intelligence — Functional Requirements

### 7.1 Business Discovery

Users can search by:

- Business name.
- Keyword.
- Industry.
- City or region.
- Geographic radius.
- Custom map area.
- Configurable discovery sources.

The product should support both map-based discovery and traditional search results.

### 7.2 Business Research

Where publicly accessible and permitted, collect:

- Business name.
- Industry and category.
- Address and location.
- Website.
- Public phone number.
- Public business email.
- Social profiles.
- Description.
- Operating information.
- Source URLs.
- Retrieval timestamp.

Every collected field should retain its source or provenance wherever possible.

### 7.3 Contact Verification

Use four explicit statuses:

- Verified.
- Unverified.
- Invalid.
- Unknown.

Extracting an email address does not automatically make it verified.

Store verification date and supporting evidence.

### 7.4 Service Opportunity Finder

Users can configure services and their ideal customer profiles.

Each business can be evaluated against multiple services independently.

For example, one business could have:

- A website development opportunity.
- An automation opportunity.
- An SEO opportunity.

Each opportunity receives a separate configurable score.

Scores must include:

- Score.
- Evidence.
- Reasoning.
- Relevant signals.
- Missing information.
- Qualification status.

A missing website is a potential signal, not proof that the owner wants one.

### 7.5 Results Management

Maintain four distinct result categories:

1. **Raw Results:** All records discovered before user filters.
2. **Filtered Results:** Records matching selected filters.
3. **Qualified Leads:** Records explicitly shortlisted or qualified by the user.
4. **Exports:** Data prepared for external use.

Users must be able to apply filters without losing the original collected information.

### 7.6 CRM

Default pipeline:

1. New
2. Researched
3. Qualified
4. Shortlisted
5. Contacted
6. Follow-up
7. Interested
8. Meeting Scheduled
9. Proposal Sent
10. Won
11. Lost
12. Archived

Requirements:

- Custom stages.
- Drag-and-drop pipeline.
- Notes and activity history.
- Tags and custom fields.
- Follow-up tracking.
- Outreach history.
- Bulk actions.

### 7.7 Duplicate Management

Use phone, email, domain, profile URL, and fuzzy matching to identify duplicates.

- Automatically merge only confidently confirmed duplicates.
- Send uncertain matches for manual review.
- Preserve original source links and historical information.
- Never silently discard potentially useful records.

### 7.8 Import and Export

Support:

- CSV.
- Excel.
- JSON.
- Bulk import with field mapping.
- Selected or filtered exports.
- Background processing for large datasets.
- Duplicate detection.
- Optional Google Sheets integration.

Google Sheets integration should support import, export, optional two-way sync, and duplicate protection. Never silently overwrite existing spreadsheet data.

## 8. Startup Intelligence — Functional Requirements

### Startup Discovery

Users can configure:

- Keywords.
- Industries.
- Countries and regions.
- Date ranges.
- Funding stages where publicly available.
- Discovery sources.
- Custom filters.

### Startup Research

Store relevant public information, including:

- Startup and product name.
- Website.
- Industry.
- Founders.
- Launch date where available.
- Product description.
- Pricing.
- Public product updates.
- Source references.
- Research history.

### Revenue Intelligence

Revenue information must be classified as:

| Classification | Meaning |
|---|---|
| Verified | Supported by reliable financial evidence |
| Founder Reported | Public claim made by the founder or company |
| Estimated | Derived using a documented methodology and assumptions |
| Not Available | No sufficiently reliable information found |

Never invent revenue figures or present estimates as verified financial information. Revenue must not be confused with profit.

### Watchlists and Reports

Users can:

- Save startups.
- Track competitors.
- Monitor product and pricing changes.
- Maintain research notes.
- Generate reports.
- Compare companies and market segments.

## 9. Automation and Scheduling Requirements

### Scheduler

Support fully configurable recurring schedules, including:

- Every three hours.
- Weekdays at a specified time.
- Selected weekdays.
- Monthly dates.
- Specific dates.
- Custom intervals.

Each schedule must include:

- Timezone.
- Start and optional end date.
- Next scheduled run.
- Previous run status.
- Pause and resume.
- Run now.
- Failure information.

Every execution must have separate history, results, and logs.

### Workflow Execution

A workflow should support:

1. Trigger.
2. Discovery.
3. Research.
4. Qualification.
5. Shortlisting.
6. Email drafting.
7. Human approval.
8. Sending.
9. Reply tracking.
10. Outcome recording.

Multiple workflows should be capable of running independently.

### Email Integration

Initial priority: Gmail OAuth.

Future integrations may include Outlook and generic SMTP through provider adapters.

Email sending must include responsible sending limits, bounce monitoring, opt-out handling, duplicate prevention, and suppression lists.

## 10. Global Search and Data Management

Provide global search across:

- Businesses.
- Contacts.
- Startups.
- Reports.
- Research history.

Support search by name, domain, phone, email, and keywords.

Include filters for module, industry, location, source, and date.

Users should also be able to create reusable search presets containing sources, keywords, locations, and filters.

### Data Retention

- Rejected or unqualified lead records: 15 days.
- Temporary enrichment and research data: 15 days.
- Shortlisted leads: Retained until manually archived or deleted.
- Outreach history: Retained with the corresponding lead.
- Shortlisted information must be promoted to durable storage before temporary cleanup.

Implement tiered log retention and avoid storing secrets or unnecessary sensitive information in logs.

## 11. Analytics and Reporting

### Leads Analytics

Track:

- Businesses discovered.
- Unique businesses after deduplication.
- Verified contacts.
- Qualified opportunities.
- CRM stage conversion.
- Source performance.
- Campaign performance.

### Startup Analytics

Track:

- Startups discovered.
- Industry trends.
- Geographic trends.
- Product launches.
- Pricing changes.
- Competitor growth signals.
- Market opportunities.

Support date filters and CSV/PDF reporting.

## 12. Notifications

Provide an in-app notification centre for:

- Job completion.
- Job failure.
- New qualified leads.
- Scheduled search completion.
- Source failures or restrictions.
- Email replies.
- Pending approvals.

Email notifications can be added as an optional later capability.

## 13. Dashboard Customization

Users should eventually be able to:

- Rearrange dashboard widgets.
- Save custom filters and views.
- Customize CRM stages.
- Add custom fields and tags.
- Configure scoring weights.
- Choose visible table columns.
- Switch between dark and light themes.

## 14. User Interface Requirements

The initial visual direction is a premium dark dashboard with purple accents.

Design characteristics:

- Modern sidebar navigation.
- Clean dashboard cards.
- Subtle gradients.
- Analytics charts.
- Tables with powerful filtering.
- Live job progress.
- Source health indicators.
- Recent activity feed.
- Responsive layouts.

Leads Intelligence must provide:

- Dashboard view.
- Table view.
- Dedicated full-screen interactive map.

Startup Intelligence should have a distinct research-oriented layout while sharing the same visual language.

The interface must be functional and data-driven, not a static mockup.

## 15. Technical Product Constraints

The initial architecture is based on:

| Layer | Preferred technology |
|---|---|
| Frontend | Next.js + TypeScript |
| Backend | Python + FastAPI |
| Database | PostgreSQL |
| Background jobs | Redis + workers |
| Maps | Leaflet + OpenStreetMap |
| Browser automation | Playwright |
| HTML extraction | HTTP clients + BeautifulSoup |
| Search | PostgreSQL full-text search initially |
| Search discovery | Self-hosted SearXNG and other permitted providers |

Architecture style: Modular Monolith with separate background workers.

Deployment direction: Vercel for the frontend and Railway for backend/workers initially, with Render as an alternative. Deployment choices must be validated against free-tier availability and current limits before implementation.

The platform must support local execution and optional cloud execution.

## 16. AI Requirements

AI is an optional intelligence layer, not the foundation of the product.

Potential applications:

- Business research summaries.
- Opportunity explanations.
- Startup research summaries.
- Email personalization.
- Market analysis.
- Natural-language search assistance.

Requirements:

- Core product functions must work without AI.
- Prefer local models and open-source tools.
- Optional free providers may be integrated.
- Paid AI services must never be mandatory.
- Provide rule-based fallbacks.
- Never invent facts or financial information.

## 17. Security, Privacy and Compliance

Required safeguards:

- Secure authentication and sessions.
- Encrypted secret storage.
- No API keys in frontend code.
- Access controls.
- Audit logs.
- Backups and recovery.
- Source attribution.
- Data retention enforcement.
- Opt-out and suppression management.
- Responsible outreach controls.

Only collect information through permitted public access or authorized integrations.

Do not implement credential abuse, unauthorized private endpoint access, authentication bypass, or CAPTCHA/anti-bot circumvention.

## 18. Backup and Monitoring Requirements

### Backups

- Daily backups.
- Seven daily restore points.
- Longer-term weekly retention.
- Separate backup storage.
- Periodic restore testing.
- CSV export capability.

### Monitoring

Track:

- Source health.
- Worker status.
- Job progress.
- Failures and error logs.
- Available API quotas.
- Usage limits.
- Processing performance.

## 19. Non-Functional Requirements

- Modular and maintainable code.
- Reliable background job execution.
- Resumable jobs where practical.
- Retry handling and rate limits.
- Deduplication and data integrity.
- Secure configuration management.
- Responsive user interface.
- Clear error messages.
- Exportable user data.
- Graceful degradation when external sources fail.
- No dependency on a single AI or discovery provider.

## 20. Development Priorities

### Phase 1 — Foundation

- Project setup.
- Authentication.
- Database.
- Core dashboard.
- Source Manager.
- Background job infrastructure.
- Local development environment.
- Deployment foundation.

### Phase 2 — Leads Intelligence MVP

- Business discovery.
- Map interface.
- Search and filters.
- Business profiles.
- Enrichment.
- Deduplication.
- Service opportunity scoring.
- Shortlisting.
- CRM.
- CSV and Excel exports.

### Phase 3 — Social Intelligence

- Platform-specific adapters.
- Configurable public-data research.
- Search filters.
- Processing and source attribution.

### Phase 4 — Automation Engine

- Scheduler.
- Workflow manager.
- Qualification automation.
- Email drafting.
- Approval system.
- Sending integrations.
- Reply and outcome tracking.

### Phase 5 — Startup Intelligence

- Startup discovery.
- Founder and product research.
- Competitor tracking.
- Revenue intelligence.
- Market research.
- Watchlists and reports.

### Phase 6 — Advanced Intelligence

- Advanced analytics.
- Local AI integration.
- Advanced automation.
- Expanded source ecosystem.
- Further research capabilities.

## 21. MVP Definition of Done

The first meaningful SparkXFlow release should allow a user to:

1. Open and securely access the platform.
2. Discover businesses using supported search and geographic sources.
3. View results in tables and on an interactive map.
4. Open and research individual business profiles.
5. Filter and deduplicate discovered businesses.
6. Evaluate businesses against configurable services.
7. Shortlist promising opportunities.
8. Manage shortlisted businesses through a CRM pipeline.
9. Export data to CSV or Excel.
10. See job status, source health, and processing errors.

A working, reliable Leads Intelligence MVP takes priority over a large collection of unfinished features.

## 22. Success Metrics

Evaluate the product using measurable indicators:

- Successful discovery job completion rate.
- Unique business records discovered.
- Duplicate rate.
- Percentage of records with useful contact information.
- Contact verification rate.
- Time required to research a business.
- Qualified opportunities identified.
- Workflow success rate.
- Export reliability.
- Source availability and freshness.

Do not define success solely by the number of raw records collected.

## 23. Explicitly Out of Scope for Initial Release

- Public startup directory.
- Full multi-tenant SaaS billing.
- Mandatory paid AI services.
- Mandatory paid data APIs.
- Microservices architecture.
- Unrestricted social media scraping.
- Automatic mass email campaigns without approval.
- Advanced relationship graph visualization.
- Guaranteed revenue estimates.
- Guaranteed discovery of every business in a market.

---

**End of PRD v1.0**