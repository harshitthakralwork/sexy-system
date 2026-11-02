# SparkXFlow — UI/UX Design Specification

**File:** `design.md`  
**Version:** 1.0  
**Status:** Initial specification  
**Product:** SparkXFlow

---

# 1. Design Vision

SparkXFlow should look and feel like a premium Business & Market Intelligence Operating System.

The interface should communicate:

- Intelligence.
- Precision.
- Productivity.
- Control.
- Reliability.
- Modern technology.

The design should be professional enough for business operators, researchers, founders, and agency owners.

It must not look like a generic admin dashboard or a basic CRM template.

## 1.1 Visual Direction

Primary visual direction: Premium dark interface with purple accents.

Design characteristics:

- Deep charcoal and near-black backgrounds.
- Purple and violet primary accents.
- Subtle gradients.
- Soft borders.
- Carefully designed cards.
- Modern typography.
- Restrained shadows and glow effects.
- Clean charts and visual analytics.
- High-quality icons.
- Consistent spacing.
- Subtle interaction animations.

Avoid excessive gradients, glowing borders, unnecessary animations, and overcrowded dashboards.

The interface should feel premium without sacrificing usability.

# 2. Design System

## 2.1 Color Palette

Use centralized design tokens rather than hardcoding colors throughout the application.

### Dark theme

| Token | Suggested value | Usage |
|---|---|---|
| Background | `#09090F` | Main application background |
| Sidebar | `#0D0D16` | Navigation background |
| Surface | `#13131F` | Cards and panels |
| Elevated surface | `#191927` | Modals and elevated components |
| Primary | `#8B5CF6` | Main actions and highlights |
| Primary hover | `#7C3AED` | Hover states |
| Secondary accent | `#A78BFA` | Secondary highlights |
| Main text | `#F4F4F8` | Primary text |
| Muted text | `#9292A5` | Secondary text |
| Border | `#28283A` | Card and component borders |
| Success | `#22C55E` | Successful states |
| Warning | `#F59E0B` | Warnings |
| Error | `#EF4444` | Errors |
| Information | `#38BDF8` | Informational states |

These are initial design tokens. They should be adjustable centrally.

### Light theme

Support a light theme with:

- Light neutral backgrounds.
- White surfaces.
- Dark readable text.
- Purple primary accents.
- Appropriate semantic status colors.
- Accessible contrast.

Dark theme is the default.

## 2.2 Typography

Use a modern sans-serif font system.

Preferred fonts:

- Inter.
- Geist.
- System sans-serif fallback.

Typography hierarchy:

- Large page headings.
- Medium section headings.
- Clear card titles.
- Readable body text.
- Smaller secondary labels.
- Monospaced styling for technical identifiers where appropriate.

Avoid excessive font sizes and inconsistent weights.

## 2.3 Spacing

Use a consistent spacing scale based on 4px increments.

Recommended values:

- 4px
- 8px
- 12px
- 16px
- 20px
- 24px
- 32px
- 40px
- 48px

## 2.4 Components

Create reusable components for:

- Buttons.
- Inputs.
- Search fields.
- Select menus.
- Dropdowns.
- Cards.
- Tables.
- Tabs.
- Modals.
- Drawers.
- Tooltips.
- Badges.
- Status indicators.
- Pagination.
- Date pickers.
- Filters.
- Charts.
- Empty states.
- Loading states.
- Error states.
- Confirmation dialogs.

Every component must support consistent spacing, colors, typography, hover states, focus states, and accessibility.

# 3. Application Layout

## 3.1 Main Layout

Use a persistent application shell with:

1. Left sidebar.
2. Top header.
3. Main content area.
4. Optional contextual panels or drawers.
5. Global notification access.

The sidebar should be collapsible.

The main content should use available screen width efficiently.

## 3.2 Sidebar Navigation

Organize navigation into the following sections.

### Overview
- Dashboard.

### Leads Intelligence
- Leads Dashboard.
- Discover Businesses.
- Map Explorer.
- Raw Results.
- Filtered Results.
- Qualified Leads.
- CRM Pipeline.
- Service Catalog.
- Search Presets.

### Startup Intelligence
- Startup Dashboard.
- Discover Startups.
- Startup Database.
- Competitor Research.
- Market Intelligence.
- Watchlists.

### Social Intelligence
- Social Discovery.
- Research Results.
- Platform Sources.

### Automation
- Workflow Builder.
- Active Workflows.
- Scheduler.
- Email Campaigns.
- Approval Queue.
- Execution History.

### Intelligence Infrastructure
- Source Manager.
- Global Search.
- Reports.
- Analytics.

### System
- Notifications.
- Settings.

Navigation should use consistent Lucide icons and clear active states.

Do not show unfinished modules as if they are operational. Planned modules may be marked as coming soon.

# 4. Global Header

The top header should include:

- Current page title or breadcrumb.
- Global search.
- Quick-create action.
- Notification icon with unread count.
- Job activity indicator.
- User profile and settings access.

Global search should allow searching across businesses, contacts, startups, reports, and research history.

Results should be grouped by module.

# 5. Main Dashboard

The dashboard should provide a high-level operational overview.

## 5.1 Summary Cards

Recommended cards:

- Total Businesses Discovered.
- Unique Businesses.
- Qualified Opportunities.
- Verified Contacts.
- Active Workflows.
- Running Jobs.

Cards should display:

- Current value.
- Relevant comparison where data exists.
- Short descriptive label.
- Small trend visualization where useful.

Never display fabricated analytics or hardcoded demo numbers in production.

## 5.2 Analytics Section

Include:

- Business discovery over time.
- Lead qualification trends.
- Source performance.
- Industry distribution.
- Geographic distribution.
- Workflow performance.

Charts must use actual database information.

## 5.3 Activity Feed

Show recent events:

- New businesses discovered.
- Research completed.
- Lead shortlisted.
- Workflow executed.
- Email approved.
- Source failure.
- Export completed.

Each event should link to its relevant record or execution.

## 5.4 Active Jobs

Display:

- Job name.
- Source.
- Progress.
- Status.
- Start time.
- Records processed.
- Error count.
- Cancel or pause action where supported.

Progress must reflect real worker status.

# 6. Leads Intelligence Interface

Leads Intelligence is the primary operational module.

## 6.1 Leads Dashboard

Provide:

- Discovery metrics.
- Qualified opportunity metrics.
- Contact verification statistics.
- Lead conversion metrics.
- Recent businesses.
- Active discovery jobs.
- Source performance.
- Geographic and industry analytics.

Include quick actions:

- Start Discovery.
- Open Map Explorer.
- View Qualified Leads.
- Create Workflow.
- Export Results.

## 6.2 Business Discovery Screen

The discovery screen should contain:

### Search configuration

- Keyword input.
- Industry selector.
- Location input.
- Administrative cascade: country, state, city, locality.
- Geographic radius.
- Area drawing entry: rectangle, polygon, or a saved area chosen from a list.
- Source selection.
- Advanced filters.
- Save Search Preset action.
- Save Area action, keeping the drawn shape itself, not only its text label.

### Discovery controls

- Start Search.
- Pause.
- Resume.
- Cancel.
- View Job Details.

### Results preview

Display:

- Business name.
- Category.
- Location.
- Website availability.
- Phone availability.
- Source.
- Research status.

Allow users to switch to table or map views.

## 6.3 Map Explorer

This must be a dedicated, full-screen interactive map.

Use Leaflet with OpenStreetMap-compatible tile providers.

Features:

- Geographic business markers.
- Marker clustering.
- Zoom and pan.
- Search by location.
- Geographic radius selection.
- Custom area selection where supported.
- Map filters.
- Business preview on marker click.
- Open full business profile.
- Add to shortlist.
- Start discovery for a selected area.

### Map layout

Recommended layout:

- Full map as the main area.
- Collapsible filter panel.
- Optional business result panel.
- Floating map controls.
- Clear selected-business state.

Do not overcrowd the map with every available filter simultaneously.

### Area definition

Three ways to say *where*, all producing the same job payload:

- **Administrative cascade.** Country → State → City → Locality selects each level.
  Country is required; each deeper level is optional. The control shows only the
  levels the current selection makes meaningful, and never offers "Localities"
  before a city is chosen.
- **Centre and radius.** The user drops or drags a centre marker and picks a radius
  chip (1 / 3 / 5 / 10 / 25 km) or types one. The circle redraws live and its
  approximate area in km² is shown, so the scale of the request is visible before
  it is sent.
- **Drawn shape.** A toolbar offers Rectangle and Polygon. Rectangle is drag-to-draw
  and re-editable by its corners. Polygon places a vertex per click, rubber-bands the
  next edge, closes on the first vertex or on double-click, and shows the running
  vertex count. Both shapes expose handles to move and resize, and a control to
  delete and start again.

A draft shape is visually distinct from a saved area. If the shape is larger than
the allowed limit for a single job, say so on the shape itself — "too large for one
request; will be split into N tiles" — with the option to proceed or narrow it.
Never accept an oversized area and quietly search part of it.

### Tiled areas on the map

When a region is grid-divided, the tiles are drawn as a light grid over the shape.
Each tile carries its state by colour and by an icon, never by colour alone:
pending, running, done, failed, empty. Hovering a tile shows records returned and
the error text if it failed. A failed tile stays visible after the job ends; the
user can re-run just that tile.

### Pins, clustering and selection

- Pins are rendered per business, clustered above the configured zoom threshold with
  a count badge; clicking a cluster zooms to its bounds instead of toggling a popup.
- Cluster counts are the number of *records*, and the label distinguishes
  "records" from "businesses" while a deduplication backlog exists.
- One selected pin at a time for the preview; multi-select (for bulk actions and
  export) uses the result panel, Shift-click on pins, or rectangle selection over
  the visible viewport.
- Selected pins keep a persistent visual state that survives filtering, panning and
  switching to the table view.
- Beyond a few thousand visible records, render the viewport only. The record count
  in the panel remains the true total, so a partial render never reads as fewer
  results.

### Marker preview

A compact popover on pin click:

- Name, category, locality or address.
- Website availability and phone availability as present-or-absent, never as a guess.
- Rating and review count where a collected source supplied them.
- Source name and retrieval time, as a link to the provenance detail.
- Actions: open profile, shortlist, add to selection, exclude from results.

The popover is small and non-modal. Anything longer-lived belongs in the profile or
the side panel.

### Filters

The filter panel filters *collected* results, and only offers a field when at least
one enabled source can produce it:

- Category (multi-select).
- Rating, minimum threshold.
- Review count, minimum threshold.
- Website: has one / missing / unknown — three states, because "unknown" is not
  evidence of absence.
- Phone: has one / missing / unknown.

Filtering changes the pins, the result panel, the table and the export selection at
once. The active filter set is shown as removable chips above the map. Filters never
mutate stored records.

### Discovery progress

While a job runs, the map shows a persistent, non-blocking progress strip:

- Status text: `Running — 12 of 40 tiles`.
- Live counters from observed work: sources contacted, records returned, stored,
  rejected, duplicates merged.
- Per-source lines, including failures with the reason the source gave.
- Cancel, which stops after the current tile and keeps stored results.

No percentage bar that moves on a timer. If nothing is known yet, the strip says so.

### Map and results table as one view

- A **Map | Table** segmented control switches the primary surface; **Split** shows
  both, map on the left, table on the right, sharing one result set.
- Filters, sort, selection and viewport ownership are shared state. Selecting a pin
  highlights and scrolls to its row; selecting a row centres and opens its pin.
- "Recenter on results" frames every record in the current filter set.
- The table's bulk-action bar and the map's selection actions call the same
  endpoints, so a shortlist done from the map is visible in the table immediately.

### Saved areas

Saved areas appear in a side list with name, shape type, category, and when they were
last run. From the list a user can load the area onto the map, re-run discovery, view
its job history, rename it, or delete it. Loading a saved area restores its shape and
administrative context exactly as drawn.

### Map Explorer workflows

1. **Discover a locality.** Open Map Explorer → search "Indiranagar, Bengaluru" →
   confirm the resolved area and its bounds → pick category *cafe* → Start
   discovery → watch tiles complete → inspect pins → shortlist three → export the
   selection.
2. **Work a commercial strip.** Draw a rectangle along the road → radius and area
   shown → run discovery over just that shape → filter to "no website" → those are
   the outreach candidates.
3. **A whole city.** Choose city-level administrative scope, which exceeds one
   request → the app states the tile count and the expected request volume → the
   user proceeds or narrows → the job runs, and one throttled tile is retried alone.
4. **Return next week.** Open the saved area → re-run → new businesses are marked
   as new sightings; known ones are not counted as fresh discoveries.
5. **Triage from the table.** Filter the table to "phone missing", select 40 rows,
   switch to the map to see where they cluster, and choose the densest cluster to
   work first.

### States the map must handle

- **Loading tiles**: pins from completed tiles appear while others are pending.
- **Empty**: "No records found by *these* sources in this area", with a link to
  source coverage — never a blank map with no explanation.
- **Partial source failure**: which sources answered, which did not, and what that
  means for coverage.
- **Provider refusal or throttling**: the source's own reason, the retry option, and
  the reminder that the limit exists to keep shared infrastructure usable.
- **Map library unavailable**: the table view still works; the map control is
  disabled with a reason rather than showing an empty pane.
- **Accessibility**: every map action has a table-view equivalent, drawing tools are
  keyboard-operable, and pin state is conveyed by text and icon as well as colour.

## 6.4 Business Profile

Each business should have a dedicated profile page or detailed side panel.

Sections:

**Overview**
- Business name.
- Category.
- Location.
- Description.
- Website.
- Public contact information.

**Online Presence**
- Website condition.
- Social profiles.
- Public directory presence.
- Digital presence observations.

**Service Opportunities**
- Relevant services.
- Individual opportunity scores.
- Evidence and reasoning.
- Qualification status.

**Contacts**
- Public contact details.
- Verification status.
- Source URL.
- Verification date.

**Research History**
- Previous enrichment.
- Discovery sources.
- Retrieval timestamps.

**CRM**
- Current stage.
- Tags.
- Notes.
- Follow-up date.
- Activity timeline.

**Actions**
- Shortlist.
- Change stage.
- Add note.
- Export.
- Archive.
- Delete.

## 6.5 Results Management

Provide separate screens or tabs for:

- Raw Results.
- Filtered Results.
- Qualified Leads.

Use a reusable data table component.

Table capabilities:

- Sorting.
- Filtering.
- Column visibility.
- Column resizing where practical.
- Pagination.
- Row selection.
- Bulk actions.
- Search.
- Export.

Bulk actions should include:

- Shortlist.
- Add tags.
- Change CRM stage.
- Archive.
- Delete.
- Export.
- Add to outreach workflow.

Use confirmation dialogs for destructive operations.

## 6.6 Service Catalog

A dedicated configuration interface.

Users should be able to:

- Create a service.
- Edit a service.
- Disable a service.
- Define ideal customer profiles.
- Set qualification criteria.
- Configure opportunity scoring weights.
- Define required and preferred signals.

Example service card:

- Service name.
- Description.
- Active status.
- Qualification profile.
- Scoring configuration.
- Number of matching businesses.

## 6.7 CRM Pipeline

Use a drag-and-drop Kanban interface.

Each card should show:

- Business name.
- Industry.
- Location.
- Opportunity score.
- Current service.
- Last activity.
- Next follow-up.

Allow:

- Moving cards between stages.
- Opening business profiles.
- Adding notes.
- Setting follow-up dates.
- Filtering by service, tag, and date.

Also provide an optional table view.

# 7. Startup Intelligence Interface

Startup Intelligence should have its own research-oriented experience.

It should use the same visual design system but have distinct page layouts.

## 7.1 Startup Dashboard

Display:

- Total startups discovered.
- New products discovered.
- Industries monitored.
- Competitors tracked.
- Recent pricing changes.
- Active watchlists.

Charts:

- Startup discovery trends.
- Industry distribution.
- Geographic distribution.
- Product launch activity.

## 7.2 Startup Discovery

Search controls:

- Keywords.
- Industry.
- Country.
- Date range.
- Funding stage where available.
- Discovery sources.
- Custom filters.

Results should include:

- Startup name.
- Website.
- Industry.
- Product description.
- Founder information where available.
- Launch information.
- Source.
- Last researched date.

## 7.3 Startup Profile

Sections:

- Company overview.
- Product information.
- Founder information.
- Pricing.
- Revenue intelligence.
- Product updates.
- Competitors.
- Market positioning.
- Research history.
- Source evidence.
- Notes and watchlist controls.

Revenue classification must be clearly visible:

- Verified.
- Founder Reported.
- Estimated.
- Not Available.

Estimated values must display methodology and assumptions.

## 7.4 Competitor Research

Allow users to:

- Add companies to competitor lists.
- Compare products.
- Compare pricing.
- Monitor public changes.
- Add research notes.
- Generate comparison reports.

## 7.5 Watchlists

Users can create named watchlists.

Each watchlist should display:

- Number of tracked companies.
- Recent changes.
- Last research date.
- Configured monitoring schedule.
- Latest alerts.

# 8. Social Intelligence Interface

## 8.1 Social Discovery

Provide a configuration screen containing:

- Platform selector.
- Search keywords.
- Hashtags.
- Public usernames or profiles.
- Date filters.
- Geographic filters where available.
- Requested fields.
- Collection limits.

## 8.2 Research Results

Display records with:

- Platform.
- Public profile or content reference.
- Text or description where permitted.
- Published date where available.
- Engagement information where available.
- Source link.
- Retrieval date.

Show unavailable or restricted data honestly.

## 8.3 Platform Source Status

Display:

- Platform.
- Connection or adapter status.
- Supported collection methods.
- Last successful run.
- Last error.
- Access limitations.

# 9. Automation Interface

## 9.1 Workflow Dashboard

Display:

- Active workflows.
- Paused workflows.
- Successful executions.
- Failed executions.
- Pending approvals.

Each workflow card should show:

- Name.
- Purpose.
- Trigger.
- Last execution.
- Next scheduled execution.
- Current status.

## 9.2 Workflow Builder

Use a visual step-based workflow editor.

Recommended workflow blocks:

1. Trigger.
2. Discovery.
3. Research.
4. Qualification.
5. Shortlisting.
6. Email Generation.
7. Approval.
8. Sending.
9. Reply Tracking.

Users should be able to configure each block.

Provide validation before activation.

The editor must not permit invalid or incomplete workflows to run.

## 9.3 Scheduler

Provide:

- Schedule name.
- Workflow selection.
- Recurrence configuration.
- Timezone.
- Start date.
- End date.
- Next run.
- Last run.
- Enable/disable.
- Pause/resume.
- Run now.

Use a calendar and list view where useful.

## 9.4 Approval Queue

Display generated emails awaiting human approval.

Each item should include:

- Recipient.
- Business.
- Subject.
- Email body.
- Generation context.
- Supporting business evidence.
- Approve.
- Edit.
- Reject.

Never send an email merely because it was generated.

## 9.5 Email Campaigns

Show:

- Campaign name.
- Target audience.
- Sending status.
- Total recipients.
- Sent.
- Delivered where available.
- Bounced.
- Replies.
- Unsubscribed.

Provide campaign details and execution history.

# 10. Source Manager Interface

A dedicated source management dashboard.

Display sources grouped by discovery category:

- Search.
- Geographic.
- Social.
- Startup.
- Public directories.
- Custom integrations.

Each source card or row should show:

- Name.
- Source category.
- Enabled/disabled.
- Health.
- Last successful run.
- Last error.
- Available usage/quota.
- Geographic coverage.
- Data freshness.
- Limitations.

Actions:

- Enable.
- Disable.
- Configure.
- Test connection.
- View history.

Source failure must not make the entire discovery platform unusable.

# 11. Global Search

Global search should be available from the application header.

Features:

- Instant search suggestions.
- Grouped results.
- Recent searches.
- Search history.
- Keyboard-friendly navigation.
- Filters by module and category.

Search categories:

- Businesses.
- Contacts.
- Startups.
- Reports.
- Research history.

Provide advanced search within individual modules.

# 12. Reports and Analytics

Create a central reporting interface.

Users should be able to:

- Select report category.
- Choose date range.
- Apply filters.
- View charts and summaries.
- Export CSV.
- Export PDF.

Report categories:

- Leads performance.
- Source performance.
- Contact verification.
- CRM conversion.
- Campaign performance.
- Startup discovery.
- Market trends.

Reports must be generated from real stored data.

# 13. Notifications

Use a notification drawer or dedicated notification centre.

Categories:

- Job updates.
- Source alerts.
- New opportunities.
- Workflow events.
- Email replies.
- Pending approvals.
- System alerts.

Support:

- Read/unread state.
- Mark all as read.
- Open related record.
- Notification preferences.

Email notification delivery is optional for the initial release.

# 14. Settings

Organize settings into clear sections.

### General
- Profile.
- Application preferences.
- Theme.
- Timezone.

### Data
- Retention.
- Import/export.
- Backup information.

### Integrations
- Google Sheets.
- Gmail.
- Other supported providers.

### Sources
- Source configurations.
- Provider settings.

### Services
- Service Catalog.
- Qualification criteria.
- Scoring weights.

### Automation
- Workflow preferences.
- Sending limits.
- Approval policies.

### Security
- Password and sessions.
- Secret management.
- Audit history.

Secrets must never be displayed in plaintext after being saved.

# 15. Interaction Design

## 15.1 Buttons

Use clear visual hierarchy:

- Primary: purple filled.
- Secondary: neutral surface with border.
- Destructive: red semantic styling.
- Ghost: transparent with hover background.

Avoid ambiguous labels.

## 15.2 Forms

Forms should:

- Use descriptive labels.
- Explain optional fields.
- Validate inputs.
- Show errors near the relevant field.
- Preserve valid input after failed submission.
- Provide clear success feedback.

## 15.3 Modals and Drawers

Use modals for:

- Confirmations.
- Short forms.
- Small configuration tasks.

Use drawers or full pages for:

- Complex business details.
- Long research forms.
- Detailed configuration.
- Multi-section editing.

## 15.4 Loading States

Provide:

- Skeleton loading.
- Inline progress.
- Clear processing indicators.
- Empty states.
- Error states.

Never leave users staring at a blank screen during processing.

## 15.5 Feedback

Every important action must provide feedback.

Examples:

- Search started.
- Export queued.
- Record shortlisted.
- Workflow paused.
- Settings saved.
- Source connection failed.

Do not display success messages before the backend confirms success.

# 16. Responsive Design

Desktop is the primary design target.

Support:

- Desktop.
- Laptop.
- Tablet.
- Mobile.

On smaller screens:

- Collapse sidebar into a mobile navigation drawer.
- Convert complex tables into responsive layouts.
- Keep primary actions accessible.
- Simplify map controls.
- Avoid horizontal overflow.
- Preserve readable typography.

The platform should remain usable on mobile, even if some advanced operations are desktop-oriented.

# 17. Accessibility

Requirements:

- Keyboard navigation.
- Visible focus states.
- Semantic HTML.
- Appropriate labels.
- Accessible contrast.
- Screen-reader-friendly controls.
- Accessible dialogs.
- Non-color indicators for statuses.

Do not communicate important information through color alone.

# 18. Animation and Motion

Use subtle motion only where it improves feedback.

Examples:

- Sidebar collapse.
- Modal transitions.
- Dropdown appearance.
- Card hover.
- Loading indicators.
- Progress changes.
- Kanban card movement.

Respect reduced-motion preferences.

Avoid excessive animated backgrounds and distracting effects.

# 19. Design Implementation Rules

1. Build reusable design components.
2. Centralize design tokens.
3. Keep page layouts consistent.
4. Use real backend data.
5. Never hardcode production analytics.
6. Implement real interactions for every visible control.
7. Provide empty, loading, error, and success states.
8. Use consistent icons.
9. Avoid unnecessary decorative elements.
10. Keep advanced settings out of the main user workflow.
11. Use confirmation for destructive actions.
12. Ensure accessibility and responsive behavior.
13. Avoid duplicating components across modules.
14. Do not make unfinished features appear functional.
15. Maintain a premium, restrained visual style.

# 20. UI Acceptance Criteria

The design is considered successfully implemented when:

- Navigation works across all implemented modules.
- Dashboard metrics are database-driven.
- Global search returns grouped results.
- Discovery forms work.
- Map Explorer displays real business locations.
- An area can be drawn, saved, and re-opened exactly as drawn.
- Rectangle, polygon, and radius selection each start a real discovery job.
- Tiled jobs show per-tile state, including failed tiles, and cancel between tiles.
- Map and table share one filter set, one selection, and one export.
- Marker previews name the source and retrieval time of the record.
- An area with no results explains which sources were asked, rather than showing an
  empty map as if the market were empty.
- Business profiles show collected information and provenance.
- Results tables support filtering and bulk operations.
- CRM supports stage changes.
- Startup screens display actual startup research.
- Workflow screens reflect real execution state.
- Source Manager displays real source health.
- Notifications open relevant records.
- Theme switching works.
- Responsive layouts remain usable.
- Every interactive control performs its intended action.
- Loading, empty, error, and success states are present.

---

**End of design.md v1.0**