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
