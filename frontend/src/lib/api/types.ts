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
