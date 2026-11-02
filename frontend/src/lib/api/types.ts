/** Shapes returned by the backend. Kept narrow and mirrored in Pydantic. */

export interface RuntimeInfo {
  app_name: string;
  environment: string;
  api_version: string;
  default_region: string;
  execution_model: string;
  ai_enabled: boolean;
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

/** The single error envelope the API uses (see app/core/exceptions.py). */
export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    correlation_id: string | null;
    details?: Record<string, unknown>;
  };
}
