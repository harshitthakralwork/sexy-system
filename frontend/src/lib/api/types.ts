/** Shapes returned by the backend. Kept narrow and mirrored in Pydantic. */

export interface RuntimeInfo {
  app_name: string;
  environment: string;
  api_version: string;
  default_region: string;
  execution_model: string;
  ai_enabled: boolean;
  registration_open: boolean;
  modules_enabled: string[];
}

export interface ComponentState {
  name: string;
  ok: boolean;
  detail: string | null;
}

export interface ReadyResponse {
  status: "ok" | "degraded";
  components: ComponentState[];
}

export interface AuthUser {
  id: string;
  email: string;
  display_name: string;
  is_active: boolean;
}

export interface SessionInfo {
  authenticated: boolean;
  user: AuthUser | null;
  csrf_token: string | null;
}

export interface LoginPayload {
  email: string;
  password: string;
}

/** The single error envelope the API uses (see app/core/exceptions.py). */
export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    correlation_id: string | null;
    details?: Record<string, unknown>;
  };
}

/** Geographic scope of a discovery request, in the shape the user produced it. */
export type AreaGeometry =
  | { shape_type: "circle"; latitude: number; longitude: number; radius_km: number }
  | { shape_type: "rectangle"; rectangle: [number, number, number, number] }
  | { shape_type: "polygon"; polygon: [number, number][] }
  | { shape_type: "administrative"; bbox: [number, number, number, number] };

export interface SearchArea {
  id: string;
  name: string;
  module: string;
  shape_type: AreaGeometry["shape_type"];
  area_km2: number;
  center_latitude: number | null;
  center_longitude: number | null;
  radius_m: number | null;
  bbox_west: number;
  bbox_south: number;
  bbox_east: number;
  bbox_north: number;
  polygon: [number, number][] | null;
  admin_country: string | null;
  admin_city: string | null;
  admin_locality: string | null;
  categories: string[];
  last_run_at: string | null;
  created_at: string;
}

export interface JobTotals {
  discovered: number;
  processed: number;
  rejected: number;
  stored_new: number;
  review_pairs: number;
  units_total: number;
  units_done: number;
  units_failed: number;
  units_truncated: number;
}

export interface SourceSummary {
  slug: string;
  units: number;
  items_returned: number;
  units_failed: number;
  units_truncated: number;
  failed: boolean;
  last_classification: string | null;
  last_reason: string | null;
}

export interface JobReport {
  totals: JobTotals;
  sources: SourceSummary[];
  area?: { shape_type: string; area_km2: number; bbox: number[] } | null;
  known_records_reseen?: number;
  skipped_provenance?: number;
  failure_summary?: string;
}

export interface DiscoveryJob {
  id: string;
  job_type: string;
  status: string;
  execution_target: string;
  progress_percent: number;
  total_records: number;
  processed_records: number;
  failed_records: number;
  area_id: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  error_details: Record<string, unknown> | null;
  report: JobReport | null;
}

export interface TileBatch {
  id: string;
  batch_number: number;
  unit_kind: string;
  tile_key: string | null;
  status: string;
  records_expected: number;
  records_processed: number;
  retry_count: number;
  truncated: boolean;
  bounds: { west: number; south: number; east: number; north: number } | null;
  error_details: Record<string, unknown> | null;
}

export interface MapPin {
  id: string;
  name: string;
  latitude: number;
  longitude: number;
  primary_category: string | null;
  website_status: string;
  has_phone: boolean;
  rating: number | null;
  review_count: number | null;
  discovered_at: string;
}

export interface ViewportResponse {
  items: MapPin[];
  total_in_viewport: number;
  returned: number;
  truncated: boolean;
  bbox: number[];
}

// --- Leads intelligence (Phase 2) -------------------------------------------

export interface Business {
  id: string;
  name: string;
  primary_category: string | null;
  website_url: string | null;
  website_status: string;
  phone: string | null;
  email: string | null;
  city: string | null;
  state: string | null;
  country: string | null;
  address: string | null;
  latitude: number | null;
  longitude: number | null;
  description: string | null;
  lifecycle_status: string;
  first_discovered_at: string | null;
  last_researched_at: string | null;
}

export interface BusinessList {
  items: Business[];
  total: number;
  limit: number;
  offset: number;
}

export interface Contact {
  id: string;
  contact_type: string | null;
  full_name: string | null;
  email: string | null;
  phone: string | null;
  verification_status: string;
  verification_date: string | null;
  source_url: string | null;
}

export interface BusinessDetail extends Business {
  contacts: Contact[];
  crm_stage: string | null;
  source_slugs: string[];
  source_urls: string[];
  signals: Record<string, unknown>;
}

export interface ActionOut {
  id: string;
  message: string;
  crm_stage: string | null;
}

export interface Note {
  id: string;
  business_id: string;
  content: string;
  created_at: string;
  updated_at: string;
}

export interface Tag {
  id: string;
  name: string;
  color: string | null;
}

export interface Service {
  id: string;
  name: string;
  slug: string;
  description: string | null;
  is_active: boolean;
}

export interface ServiceList {
  items: Service[];
  total: number;
}

export interface Rule {
  id: string;
  rule_name: string;
  signal_key: string;
  weight: number;
  operator: string;
  threshold: unknown;
  is_required: boolean;
  is_active: boolean;
}

export interface Profile {
  id: string;
  service_id: string;
  name: string;
  qualification_threshold: number;
  is_active: boolean;
  version: number;
  rules: Rule[];
}

export interface ServiceDetail extends Service {
  profiles: Profile[];
}

export interface Evidence {
  id: string;
  evidence_type: string;
  description: string;
  source_url: string | null;
  evidence_value: Record<string, unknown> | null;
  score_contribution: number;
  confidence: number | null;
  observed_at: string;
}

export interface Opportunity {
  id: string;
  business_id: string;
  service_id: string;
  service_profile_id: string;
  score: number;
  confidence: number;
  status: string;
  evidence_summary: string | null;
  missing_information: string[];
  profile_version: number;
  evaluated_at: string;
  evidence: Evidence[];
}

export interface OpportunityList {
  items: Opportunity[];
  total: number;
}

export interface Stage {
  id: string;
  name: string;
  position: number;
  color: string | null;
  is_terminal: boolean;
  is_active: boolean;
}

export interface Pipeline {
  id: string;
  name: string;
  is_default: boolean;
  stages: Stage[];
}

export interface BoardCard {
  business_id: string;
  name: string;
  primary_category: string | null;
  city: string | null;
  website_status: string;
  stage_id: string;
  stage_name: string;
  next_follow_up_at: string | null;
}

export interface Board {
  stages: Stage[];
  cards: BoardCard[];
}

export interface Activity {
  id: string;
  business_id: string;
  activity_type: string;
  title: string;
  description: string | null;
  occurred_at: string;
}

export interface ActivityList {
  items: Activity[];
  total: number;
  limit: number;
  offset: number;
}

// --- Startup intelligence (Phase 3) -----------------------------------------

export interface Startup {
  id: string;
  name: string;
  website_url: string | null;
  normalized_domain: string | null;
  description: string | null;
  industry: string | null;
  country: string | null;
  city: string | null;
  founding_date: string | null;
  launch_date: string | null;
  funding_stage: string | null;
  status: string;
  source_slug: string | null;
  source_url: string | null;
  first_discovered_at: string;
  last_researched_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface StartupList {
  items: Startup[];
  total: number;
  limit: number;
  offset: number;
}

export interface Founder {
  id: string;
  startup_id: string;
  name: string;
  role: string | null;
  public_profile_url: string | null;
  source_id: string | null;
  created_at: string;
}

export interface StartupProduct {
  id: string;
  startup_id: string;
  name: string;
  description: string | null;
  product_url: string | null;
  category: string | null;
  launch_date: string | null;
  created_at: string;
  updated_at: string;
}

export interface Pricing {
  id: string;
  product_id: string;
  plan_name: string;
  amount: number | null;
  currency: string | null;
  billing_period: string | null;
  pricing_url: string | null;
  observed_at: string;
}

export interface Revenue {
  id: string;
  startup_id: string;
  amount: number | null;
  currency: string | null;
  revenue_period: string | null;
  classification: string;
  methodology: string | null;
  assumptions: Record<string, unknown>;
  confidence: number | null;
  source_url: string | null;
  reported_at: string | null;
  observed_at: string;
}

export interface Competitor {
  id: string;
  startup_id: string;
  competitor_startup_id: string;
  relationship_type: string | null;
  evidence: Record<string, unknown>;
  created_at: string;
}

export interface StartupResearch {
  id: string;
  startup_id: string;
  research_type: string;
  summary: string | null;
  findings: Record<string, unknown>;
  source_references: Record<string, unknown>;
  researched_at: string;
}

export interface StartupDetail extends Startup {
  founders: Founder[];
  products: StartupProduct[];
  revenue: Revenue[];
  competitors: Competitor[];
  research: StartupResearch[];
  watchlists: string[];
}

export interface Watchlist {
  id: string;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
  items: Startup[];
}

// --- Social intelligence (Phase 4) -------------------------------------------

export interface SocialPlatform {
  id: string;
  name: string;
  slug: string;
  adapter_key: string;
  capabilities: Record<string, unknown>;
  limitations: Record<string, unknown>;
  is_enabled: boolean;
  health_status: string;
  last_run_at: string | null;
  last_error: string | null;
}

export interface SocialResearchQuery {
  id: string;
  platform_id: string;
  platform_slug: string;
  query_config: Record<string, unknown>;
  last_run_at: string | null;
  last_run_status: string | null;
  last_run_error: string | null;
  created_at: string;
  updated_at: string;
}

export interface SocialResearchQueryList {
  items: SocialResearchQuery[];
  total: number;
  limit: number;
  offset: number;
}

export interface SocialContent {
  id: string;
  platform_id: string;
  platform_slug: string;
  research_query_id: string | null;
  profile_id: string | null;
  external_id: string;
  content_url: string | null;
  content_type: string;
  content_text: string | null;
  published_at: string | null;
  engagement_data: Record<string, unknown>;
  author_username: string | null;
  author_profile_url: string | null;
  collected_at: string;
}

export interface SocialContentList {
  items: SocialContent[];
  total: number;
  limit: number;
  offset: number;
}

export interface SocialRun {
  query_id: string;
  platform_slug: string;
  status: string;
  collected: number;
  stored_new: number;
  duplicates: number;
  error: string | null;
}

// --- Automation engine (Phase 5) --------------------------------------------

export interface WorkflowStepDef {
  key: string;
  type: string;
  config: Record<string, unknown>;
}

export interface Workflow {
  id: string;
  name: string;
  description: string | null;
  module: string;
  workflow_definition: { steps: WorkflowStepDef[] };
  status: string;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface WorkflowList {
  items: Workflow[];
  total: number;
  limit: number;
  offset: number;
}

export interface StepExecution {
  id: string;
  execution_id: string;
  step_key: string;
  step_type: string;
  status: string;
  input_data: Record<string, unknown>;
  output_data: Record<string, unknown>;
  retry_count: number;
  started_at: string | null;
  completed_at: string | null;
  error_details: Record<string, unknown> | null;
}

export interface Execution {
  id: string;
  workflow_id: string;
  trigger_type: string;
  status: string;
  input_data: Record<string, unknown>;
  output_data: Record<string, unknown>;
  started_at: string | null;
  completed_at: string | null;
  error_details: Record<string, unknown> | null;
  created_at: string;
  steps: StepExecution[] | null;
}

export interface ExecutionList {
  items: Execution[];
  total: number;
  limit: number;
  offset: number;
}

export interface WorkflowRun {
  execution_id: string;
  status: string;
}

export interface Schedule {
  id: string;
  workflow_id: string;
  timezone: string;
  recurrence_config: Record<string, unknown>;
  start_at: string;
  end_at: string | null;
  next_run_at: string | null;
  last_run_at: string | null;
  is_enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface ScheduleList {
  items: Schedule[];
  total: number;
  limit: number;
  offset: number;
}

export interface Approval {
  id: string;
  execution_id: string;
  step_execution_id: string | null;
  approval_type: string;
  status: string;
  original_content: Record<string, unknown>;
  approved_content: Record<string, unknown> | null;
  reviewed_by_user_id: string | null;
  reviewed_at: string | null;
  created_at: string;
}

export interface ApprovalList {
  items: Approval[];
  total: number;
  limit: number;
  offset: number;
}

// --- Email outreach (Phase 5) ------------------------------------------------

export interface EmailAccount {
  id: string;
  provider: string;
  email_address: string;
  secret_reference: string | null;
  status: string;
  connected_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface EmailAccountList {
  items: EmailAccount[];
  total: number;
  limit: number;
  offset: number;
}

export interface Campaign {
  id: string;
  workflow_id: string | null;
  name: string;
  status: string;
  settings: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface CampaignList {
  items: Campaign[];
  total: number;
  limit: number;
  offset: number;
}

export interface EmailMessage {
  id: string;
  campaign_id: string | null;
  email_account_id: string | null;
  business_id: string | null;
  contact_id: string | null;
  workflow_execution_id: string | null;
  recipient_email: string;
  subject: string | null;
  body: string | null;
  status: string;
  provider_message_id: string | null;
  approved_at: string | null;
  sent_at: string | null;
  delivered_at: string | null;
  bounced_at: string | null;
  replied_at: string | null;
  created_at: string;
}

export interface EmailMessageList {
  items: EmailMessage[];
  total: number;
  limit: number;
  offset: number;
}

export interface EmailEvent {
  id: string;
  email_message_id: string;
  event_type: string;
  provider_event_id: string | null;
  event_data: Record<string, unknown>;
  occurred_at: string;
  created_at: string;
}

export interface SuppressionEntry {
  id: string;
  email_address: string;
  normalized_email: string;
  reason: string | null;
  source: string | null;
  created_at: string;
}

export interface SuppressionList {
  items: SuppressionEntry[];
  total: number;
  limit: number;
  offset: number;
}

export interface SendResult {
  message_id: string;
  status: string;
  provider_message_id: string | null;
  error: string | null;
}

// --- Social & Demand Intelligence Engine ------------------------------------

export interface IntelligenceResult {
  id: string;
  platform_id: string;
  platform_slug: string | null;
  external_id: string;
  content_type: string;
  title: string | null;
  snippet: string | null;
  content_text: string | null;
  content_url: string | null;
  canonical_url: string | null;
  published_at: string | null;
  discovered_at: string | null;
  retrieval_status: string | null;
  track_type: string | null;
  classification: string | null;
  confidence_score: number | null;
  classification_method: string | null;
  matched_terms: string[];
  evidence: Record<string, unknown>[];
  needs_review: boolean;
  source_attribution: Record<string, unknown>[];
  author_username: string | null;
  collected_at: string;
}

export interface IntelligenceList {
  items: IntelligenceResult[];
  total: number;
  limit: number;
  offset: number;
}

export interface Track {
  id: string;
  name: string;
  track_type: string;
  keywords: string[];
  exact_phrases: string[];
  excluded_terms: string[];
  hashtags: string[];
  platforms: string[];
  language: string | null;
  geography: string | null;
  source_config: Record<string, unknown>;
  frequency_config: Record<string, unknown> | null;
  max_results_per_run: number;
  is_enabled: boolean;
  is_paused: boolean;
  next_run_at: string | null;
  last_run_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface TrackList {
  items: Track[];
  total: number;
  limit: number;
  offset: number;
}

export interface DiscoveryRun {
  id: string;
  track_id: string | null;
  status: string;
  trigger_type: string;
  started_at: string | null;
  finished_at: string | null;
  sources_attempted: string[];
  queries_attempted: number;
  results_returned: number;
  stored_new: number;
  duplicates: number;
  review_flagged: number;
  classification_counts: Record<string, number>;
  error_summary: string | null;
  duration_ms: number | null;
  created_at: string;
}

export interface DiscoveryRunList {
  items: DiscoveryRun[];
  total: number;
  limit: number;
  offset: number;
}

export interface TrackRun {
  run_id: string;
  status: string;
}

export interface SavedItem {
  id: string;
  content_id: string;
  note: string | null;
  tags: string[];
  converted_business_id: string | null;
  created_at: string;
  updated_at: string;
}

// --- Global Search (master-plan Phase 6) ------------------------------------

export interface GlobalSearchItem {
  kind: string;
  id: string;
  title: string;
  subtitle: string | null;
  url: string | null;
  confidence: number | null;
}

export interface SearchGroup {
  items: GlobalSearchItem[];
  total: number;
}

export interface GlobalSearchOut {
  query: string;
  limit: number;
  offset: number;
  groups: Record<string, SearchGroup>;
  total: number;
}

// --- Analytics & Reports (master-plan #27) ----------------------------------

export interface AnalyticsBucket {
  key: string;
  count: number;
}

export interface AnalyticsOut {
  generated_at: string;
  leads_total: number;
  businesses_by_website_status: AnalyticsBucket[];
  businesses_by_lifecycle: AnalyticsBucket[];
  crm_by_stage: AnalyticsBucket[];
  opportunities_by_status: AnalyticsBucket[];
  discovery_jobs_by_status: AnalyticsBucket[];
  social_by_classification: AnalyticsBucket[];
  social_by_platform: AnalyticsBucket[];
  social_by_track_type: AnalyticsBucket[];
  startups_by_funding_stage: AnalyticsBucket[];
}

export interface SavedReport {
  id: string;
  name: string;
  description: string | null;
  report_type: string;
  snapshot: Record<string, unknown>;
  captured_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface SavedReportList {
  items: SavedReport[];
  total: number;
  limit: number;
  offset: number;
}

// --- Source Manager (master-plan #28) ---------------------------------------

export interface SourceItem {
  id: string;
  slug: string;
  name: string;
  category: string;
  adapter_key: string;
  description: string | null;
  globally_enabled: boolean;
  enabled_for_user: boolean;
  configured_at: string | null;
  configuration: Record<string, unknown>;
  secret_reference: string | null;
  health_status: string;
  last_error: string | null;
  last_check_at: string | null;
  last_check_response_ms: number | null;
  last_check_detail: string | null;
  last_successful_run_at: string | null;
  runs_recorded: number;
  requests_count: number;
  records_returned: number;
  records_accepted: number | null;
  capabilities: Record<string, unknown>;
  limitations: Record<string, unknown>;
  coverage: Record<string, unknown>;
  rate_limit_config: Record<string, unknown>;
}

export interface SourceGroup {
  category: string;
  items: SourceItem[];
}

export interface SourceList {
  groups: SourceGroup[];
  total: number;
}

export interface SourceTestResult {
  slug: string;
  status: string;
  detail: string | null;
  response_time_ms: number | null;
  checked_at: string;
}

export interface HealthCheckRow {
  id: string;
  status: string;
  checked_at: string;
  response_time_ms: number | null;
  error_message: string | null;
}

export interface UsageRecordRow {
  id: string;
  job_id: string | null;
  requests_count: number;
  records_returned: number;
  records_accepted: number | null;
  measured_at: string;
}

export interface SourceHistory {
  slug: string;
  checks: HealthCheckRow[];
  runs: UsageRecordRow[];
}
