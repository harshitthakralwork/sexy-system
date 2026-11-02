"use client";

import { useQuery } from "@tanstack/react-query";

import { api, infra } from "@/lib/api/client";
import type { ReadyResponse, RuntimeInfo } from "@/lib/api/types";

export type BackendState = "online" | "degraded" | "offline" | "checking";

export interface BackendStatus {
  state: BackendState;
  info?: RuntimeInfo;
  ready?: ReadyResponse;
  error?: string;
}

/**
 * Polls readiness and runtime info so the header can state, truthfully, whether
 * the backend and its dependencies are reachable.
 *
 * The API is unauthenticated for these two endpoints on purpose. Once auth lands
 * in Phase 1, a 401 here must map to "signed out", not "offline".
 */
export function useBackendStatus(): BackendStatus {
  const info = useQuery({
    queryKey: ["runtime-info"],
    queryFn: () => api.get<RuntimeInfo>("/info"),
    retry: false,
  });

  const ready = useQuery({
    queryKey: ["health-ready"],
    queryFn: () => infra.get<ReadyResponse>("/health/ready"),
    retry: false,
    refetchInterval: 30_000,
  });

  const isPending = info.isPending || ready.isPending;
  const failed = info.isError || ready.isError;

  if (isPending) return { state: "checking" };

  if (failed) {
    return {
      state: "offline",
      error: info.isError ? String(info.error.message) : String(ready.error?.message ?? ""),
    };
  }

  const components = ready.data?.components ?? [];
  const degraded = components.some((component) => !component.ok);

  return {
    state: degraded ? "degraded" : "online",
    info: info.data,
    ready: ready.data,
  };
}
