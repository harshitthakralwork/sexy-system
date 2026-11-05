import type { ApiErrorBody } from "./types";

export function getApiBase(): string {
  if (process.env.NEXT_PUBLIC_API_BASE_URL) {
    return process.env.NEXT_PUBLIC_API_BASE_URL;
  }
  if (typeof window !== "undefined") {
    return `${window.location.protocol}//${window.location.hostname}:8000/api/v1`;
  }
  return "http://localhost:8000/api/v1";
}

export function getApiOrigin(): string {
  const browserOrigin = typeof window !== "undefined" ? window.location.origin : "http://localhost:3000";
  return new URL(getApiBase(), browserOrigin).origin;
}

// Discovery and public-page enrichment can legitimately take tens of seconds.
// A short global deadline makes completed backend jobs look like client failures.
const DEFAULT_TIMEOUT_MS = 60_000;

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly correlationId: string | null;
  readonly details?: Record<string, unknown>;

  constructor(status: number, body: ApiErrorBody | null, fallbackMessage: string) {
    super(body?.error?.message ?? fallbackMessage);
    this.name = "ApiError";
    this.status = status;
    this.code = body?.error?.code ?? "request_failed";
    this.correlationId = body?.error?.correlation_id ?? null;
    this.details = body?.error?.details;
    Object.setPrototypeOf(this, ApiError.prototype);
  }
}

export function isApiError(err: unknown): err is ApiError {
  return (
    err instanceof ApiError ||
    (typeof err === "object" &&
      err !== null &&
      "status" in err &&
      typeof (err as { status: unknown }).status === "number")
  );
}

interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  body?: unknown;
  signal?: AbortSignal;
  timeoutMs?: number;
  headers?: Record<string, string>;
  /** Send the body as multipart instead of JSON. */
  form?: FormData;
}

async function request<T>(
  base: string,
  path: string,
  options: RequestOptions,
): Promise<T> {
  const { method = "GET", body, form, signal, timeoutMs = DEFAULT_TIMEOUT_MS, headers } = options;

  const timeout = AbortSignal.timeout(timeoutMs);
  const response = await fetch(`${base}${path}`, {
    method,
    // The session cookie is the credential. Anything that can read it can act
    // as the user, which is why it is HttpOnly and why these requests must not
    // be sent from a page the operator did not open.
    credentials: "include",
    headers: form
      ? headers
      : { "Content-Type": "application/json", ...headers },
    body: form ?? (body === undefined ? undefined : JSON.stringify(body)),
    // A hung request would otherwise leave a panel spinning with no message, so
    // every call is bounded. Caller cancellation and our timeout both apply.
    signal: signal ? AbortSignal.any([signal, timeout]) : timeout,
    // Correlation ids are minted by the backend and echoed back. The client does
    // not invent them, so a user-reported id always exists server-side too.
  });

  if (!response.ok) {
    let parsed: ApiErrorBody | null = null;
    try {
      parsed = (await response.json()) as ApiErrorBody;
    } catch {
      parsed = null;
    }
    throw new ApiError(response.status, parsed, `${method} ${path} failed`);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

function getEffectiveCsrf(explicit?: string | null): string | undefined {
  if (explicit) return explicit;
  if (typeof document === "undefined") return undefined;
  const match = document.cookie.match(/(?:^|;\s*)sparkx_csrf=([^;]+)/);
  if (!match) return undefined;
  const rawCookie = decodeURIComponent(match[1]);
  return rawCookie.split(".")[0];
}

/** Versioned application API (`/api/v1/...`). */
export const api = {
  get: <T>(path: string, signal?: AbortSignal) =>
    request<T>(getApiBase(), path, { method: "GET", signal }),
  post: <T>(path: string, body?: unknown, csrf?: string | null, timeoutMs?: number, signal?: AbortSignal) => {
    const token = getEffectiveCsrf(csrf);
    return request<T>(getApiBase(), path, {
      method: "POST",
      body,
      timeoutMs,
      signal,
      headers: token ? { "X-CSRF-Token": token } : undefined,
    });
  },
  patch: <T>(path: string, body?: unknown, csrf?: string | null) => {
    const token = getEffectiveCsrf(csrf);
    return request<T>(getApiBase(), path, {
      method: "PATCH",
      body,
      headers: token ? { "X-CSRF-Token": token } : undefined,
    });
  },
  put: <T>(path: string, body?: unknown, csrf?: string | null) => {
    const token = getEffectiveCsrf(csrf);
    return request<T>(getApiBase(), path, {
      method: "PUT",
      body,
      headers: token ? { "X-CSRF-Token": token } : undefined,
    });
  },
  delete: <T>(path: string, csrf?: string | null) => {
    const token = getEffectiveCsrf(csrf);
    return request<T>(getApiBase(), path, {
      method: "DELETE",
      headers: token ? { "X-CSRF-Token": token } : undefined,
    });
  },
  /**
   * A multipart upload. The `Content-Type` header is left to the browser: it
   * has to carry the multipart boundary, and setting it by hand produces a
   * body the server cannot parse.
   */
  upload: <T>(path: string, form: FormData, csrf?: string | null, timeoutMs?: number) => {
    const token = getEffectiveCsrf(csrf);
    return request<T>(getApiBase(), path, {
      method: "POST",
      form,
      timeoutMs,
      headers: token ? { "X-CSRF-Token": token } : undefined,
    });
  },
  /**
   * Fetch a file the API produced. The bytes come back here so the caller can
   * save them: a plain link would not carry the session cookie across origins
   * on every browser.
   */
  download: async (path: string, timeoutMs = 60_000): Promise<Blob> => {
    const response = await fetch(`${getApiBase()}${path}`, {
      credentials: "include",
      signal: AbortSignal.timeout(timeoutMs),
    });
    if (!response.ok) {
      let parsed: ApiErrorBody | null = null;
      try {
        parsed = (await response.json()) as ApiErrorBody;
      } catch {
        parsed = null;
      }
      throw new ApiError(response.status, parsed, `${path} failed`);
    }
    return await response.blob();
  },
};

/** Service endpoints outside the versioned API — health and readiness. */
export const infra = {
  get: <T>(path: string, signal?: AbortSignal) =>
    request<T>(getApiOrigin(), path, { method: "GET", signal }),
};
