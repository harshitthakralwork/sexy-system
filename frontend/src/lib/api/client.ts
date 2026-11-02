import type { ApiErrorBody } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";
const API_ORIGIN = new URL(API_BASE).origin;
const DEFAULT_TIMEOUT_MS = 8000;

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
  }
}

interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  body?: unknown;
  signal?: AbortSignal;
  timeoutMs?: number;
}

async function request<T>(base: string, path: string, options: RequestOptions): Promise<T> {
  const { method = "GET", body, signal, timeoutMs = DEFAULT_TIMEOUT_MS } = options;

  const timeout = AbortSignal.timeout(timeoutMs);
  const response = await fetch(`${base}${path}`, {
    method,
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
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

/** Versioned application API (`/api/v1/...`). */
export const api = {
  get: <T>(path: string, signal?: AbortSignal) =>
    request<T>(API_BASE, path, { method: "GET", signal }),
  post: <T>(path: string, body?: unknown) => request<T>(API_BASE, path, { method: "POST", body }),
  patch: <T>(path: string, body?: unknown) => request<T>(API_BASE, path, { method: "PATCH", body }),
  delete: <T>(path: string) => request<T>(API_BASE, path, { method: "DELETE" }),
};

/** Service endpoints outside the versioned API — health and readiness. */
export const infra = {
  get: <T>(path: string, signal?: AbortSignal) =>
    request<T>(API_ORIGIN, path, { method: "GET", signal }),
};
