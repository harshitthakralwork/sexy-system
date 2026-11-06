"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, isApiError } from "@/lib/api/client";
import type { DiscoveryJob, ScanRun } from "@/lib/api/types";
import { useSession } from "./session-provider";

export interface ActiveTask {
  id: string;
  href: string; // e.g. "/leads/map", "/leads/discover"
  label: string;
  stage?: string;
  progress?: number;
  startedAt: number;
}

export interface LocalSearchState {
  isRunning: boolean;
  activeScanId: string | null;
  activeScan: ScanRun | null;
  niche: string;
  city: string;
  stage: string;
  progress: number;
  error: string | null;
  notice: string | null;
  start: (niche: string, city: string, country?: string) => Promise<boolean>;
  cancel: () => Promise<void>;
  resume: (scanId?: string) => Promise<boolean>;
}

function getScanStageLabel(stage: string, status: string): string {
  if (status === "cancellation_requested") return "Stopping scan gracefully…";
  switch (stage) {
    case "planning":
      return "Generating niche aliases & partitioning localities…";
    case "source_discovery":
      return "Querying permitted public sources & directories…";
    case "page_verification":
      return "Verifying public websites & schema.org metadata…";
    case "contact_page_checks":
      return "Checking contact and about pages for phones/emails…";
    case "deduplication":
      return "Strict multi-signal deduplication & merging provenance…";
    case "saving":
      return "Saving verified business leads…";
    case "completed":
      return "Scan completed";
    default:
      return stage || "Executing scan units…";
  }
}

interface TaskActivityContextValue {
  activeTasks: ActiveTask[];
  isTaskRunning: (href: string) => boolean;
  getTaskForHref: (href: string) => ActiveTask | undefined;
  startTask: (href: string, label: string, taskId?: string) => string;
  updateTask: (taskIdOrHref: string, updates: Partial<Omit<ActiveTask, "id" | "href">>) => void;
  endTask: (taskIdOrHref: string) => void;
  localSearch: LocalSearchState;
}

const TaskActivityContext = createContext<TaskActivityContextValue | null>(null);

export function TaskActivityProvider({ children }: { children: ReactNode }) {
  const { csrf, user } = useSession();
  const queryClient = useQueryClient();

  const [activeTasks, setActiveTasks] = useState<ActiveTask[]>([]);

  // Persistent Local Business Search state across tab switches
  const [localRunning, setLocalRunning] = useState(false);
  const [localNiche, setLocalNiche] = useState("");
  const [localCity, setLocalCity] = useState("");
  const [localStage, setLocalStage] = useState("Preparing public searches…");
  const [localProgress, setLocalProgress] = useState(0);
  const [localError, setLocalError] = useState<string | null>(null);
  const [localNotice, setLocalNotice] = useState<string | null>(null);
  const [activeScan, setActiveScan] = useState<ScanRun | null>(null);
  const [activeScanId, setActiveScanId] = useState<string | null>(null);
  const localScanIdRef = useRef<string | null>(null);

  const startTask = useCallback((href: string, label: string, taskId?: string): string => {
    const id = taskId || `task-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
    setActiveTasks((prev) => {
      // Remove any existing task for the same href to avoid duplicate spinners
      const filtered = prev.filter((t) => t.href !== href && t.id !== id);
      return [
        ...filtered,
        {
          id,
          href,
          label,
          startedAt: Date.now(),
        },
      ];
    });
    return id;
  }, []);

  const updateTask = useCallback(
    (taskIdOrHref: string, updates: Partial<Omit<ActiveTask, "id" | "href">>) => {
      setActiveTasks((prev) =>
        prev.map((t) => {
          if (t.id === taskIdOrHref || t.href === taskIdOrHref) {
            return { ...t, ...updates };
          }
          return t;
        })
      );
    },
    []
  );

  const endTask = useCallback((taskIdOrHref: string) => {
    setActiveTasks((prev) => prev.filter((t) => t.id !== taskIdOrHref && t.href !== taskIdOrHref));
  }, []);

  const isTaskRunning = useCallback(
    (href: string): boolean => {
      return activeTasks.some((t) => t.href === href || href.startsWith(t.href));
    },
    [activeTasks]
  );

  const getTaskForHref = useCallback(
    (href: string): ActiveTask | undefined => {
      return activeTasks.find((t) => t.href === href || href.startsWith(t.href));
    },
    [activeTasks]
  );

  // Background execution for Local Business Search (/leads/map)
  const startLocalSearch = useCallback(
    async (niche: string, city: string, country?: string): Promise<boolean> => {
      const cleanNiche = niche.trim();
      const cleanCity = city.trim();
      if (cleanNiche.length < 2 || cleanCity.length < 2) {
        setLocalError("Enter both a niche and a city (at least 2 characters each).");
        return false;
      }

      setLocalRunning(true);
      setLocalNiche(cleanNiche);
      setLocalCity(cleanCity);
      setLocalProgress(5);
      setLocalStage("Planning scan & generating variants…");
      setLocalError(null);
      setLocalNotice(null);

      // Register the task on the sidebar for /leads/map
      startTask("/leads/map", `Scanning ${cleanNiche} in ${cleanCity}`, "local-scan");

      try {
        const scan = await api.post<ScanRun>(
          "/discovery/scans",
          { niche: cleanNiche, city: cleanCity, country: country || "India" },
          csrf
        );
        localScanIdRef.current = scan.id;
        setActiveScanId(scan.id);
        setActiveScan(scan);

        let current = scan;
        while (["queued", "running", "cancellation_requested"].includes(current.status)) {
          setActiveScan(current);
          setLocalProgress(Math.max(1, Math.min(100, Math.round(current.progress_percent || 1))));
          setLocalStage(getScanStageLabel(current.stage, current.status));
          await new Promise((resolve) => window.setTimeout(resolve, 1500));
          if (localScanIdRef.current !== scan.id) return false;
          current = await api.get<ScanRun>(`/discovery/scans/${scan.id}`);
        }

        setActiveScan(current);
        if (current.status === "cancelled") {
          setLocalNotice(`Scan cancelled. ${current.accepted_count} leads saved before cancellation.`);
          return false;
        }
        if (current.status !== "completed") {
          setLocalError(current.error_summary || "Scan stopped before completion.");
          return false;
        }

        setLocalProgress(100);
        setLocalStage("Scan complete");
        setLocalNotice(
          `Discovery complete: ${current.candidate_count} candidates found; ${current.accepted_count} leads verified & accepted (${current.duplicate_count} merged duplicates).`
        );
        await queryClient.invalidateQueries({ queryKey: ["local-business-finder"] });
        await queryClient.invalidateQueries({ queryKey: ["discovery-scans"] });
        return true;
      } catch (caught) {
        setLocalError(isApiError(caught) ? caught.message : "Scan failed");
        return false;
      } finally {
        setLocalRunning(false);
        endTask("/leads/map");
      }
    },
    [csrf, queryClient, startTask, endTask]
  );

  const cancelLocalSearch = useCallback(async () => {
    const scanId = localScanIdRef.current || activeScanId;
    if (!scanId) return;
    try {
      await api.post(`/discovery/scans/${scanId}/cancel`, {}, csrf);
      setLocalStage("Cancellation requested");
      setLocalNotice("Active unit checks will finish, then the scan will stop gracefully.");
    } catch (caught) {
      setLocalError(isApiError(caught) ? caught.message : "Could not cancel this scan.");
    }
  }, [activeScanId, csrf]);

  const resumeLocalSearch = useCallback(
    async (targetScanId?: string): Promise<boolean> => {
      const scanId = targetScanId || activeScanId || localScanIdRef.current;
      if (!scanId) return false;

      setLocalRunning(true);
      setLocalError(null);
      setLocalNotice(null);
      setLocalStage("Resuming scan units…");

      try {
        const resumed = await api.post<ScanRun>(`/discovery/scans/${scanId}/resume`, {}, csrf);
        localScanIdRef.current = resumed.id;
        setActiveScanId(resumed.id);
        setActiveScan(resumed);
        setLocalNiche(resumed.niche);
        setLocalCity(resumed.city);
        startTask("/leads/map", `Resuming scan for ${resumed.niche} in ${resumed.city}`, "local-scan");

        let current = resumed;
        while (["queued", "running", "cancellation_requested"].includes(current.status)) {
          setActiveScan(current);
          setLocalProgress(Math.max(1, Math.min(100, Math.round(current.progress_percent || 1))));
          setLocalStage(getScanStageLabel(current.stage, current.status));
          await new Promise((resolve) => window.setTimeout(resolve, 1500));
          if (localScanIdRef.current !== resumed.id) return false;
          current = await api.get<ScanRun>(`/discovery/scans/${resumed.id}`);
        }

        setActiveScan(current);
        if (current.status === "completed") {
          setLocalProgress(100);
          setLocalStage("Scan complete");
          setLocalNotice(
            `Resumed scan complete: ${current.candidate_count} candidates processed; ${current.accepted_count} leads saved.`
          );
          await queryClient.invalidateQueries({ queryKey: ["local-business-finder"] });
          await queryClient.invalidateQueries({ queryKey: ["discovery-scans"] });
          return true;
        }
        if (current.status === "cancelled") {
          setLocalNotice(`Scan cancelled. ${current.accepted_count} leads preserved.`);
          return false;
        }
        setLocalError(current.error_summary || "Scan stopped before completion.");
        return false;
      } catch (caught) {
        setLocalError(isApiError(caught) ? caught.message : "Failed to resume scan");
        return false;
      } finally {
        setLocalRunning(false);
        endTask("/leads/map");
      }
    },
    [activeScanId, csrf, endTask, queryClient, startTask]
  );

  // Mirror observed server progress into the sidebar task after paint.
  useEffect(() => {
    if (!localRunning) return;
    const timer = window.setTimeout(() => {
      updateTask("/leads/map", { progress: localProgress, stage: localStage });
    }, 0);
    return () => window.clearTimeout(timer);
  }, [localRunning, localProgress, localStage, updateTask]);

  // Automatic detection of active discovery background jobs (/leads/discover)
  const discoveryJobsQuery = useQuery({
    queryKey: ["active-discovery-jobs-poll"],
    queryFn: () =>
      api.get<{ items: Array<{ id: string; status: string; progress_percent?: number }> }>(
        "/discovery/jobs?limit=5"
      ),
    refetchInterval: 4000,
    enabled: Boolean(user),
  });

  useEffect(() => {
    const items = discoveryJobsQuery.data?.items ?? [];
    const runningJob = items.find((j) => j.status === "running" || j.status === "processing");
    const timer = window.setTimeout(() => {
      if (runningJob) {
        startTask(
          "/leads/discover",
          "Running discovery sweep",
          `discovery-${runningJob.id}`
        );
        updateTask(`discovery-${runningJob.id}`, {
          progress: runningJob.progress_percent,
          stage: "Executing search tiles",
        });
      } else {
        endTask("/leads/discover");
      }
    }, 0);
    return () => window.clearTimeout(timer);
  }, [discoveryJobsQuery.data, startTask, updateTask, endTask]);

  return (
    <TaskActivityContext.Provider
      value={{
        activeTasks,
        isTaskRunning,
        getTaskForHref,
        startTask,
        updateTask,
        endTask,
        localSearch: {
          isRunning: localRunning,
          activeScanId,
          activeScan,
          niche: localNiche,
          city: localCity,
          stage: localStage,
          progress: localProgress,
          error: localError,
          notice: localNotice,
          start: startLocalSearch,
          cancel: cancelLocalSearch,
          resume: resumeLocalSearch,
        },
      }}
    >
      {children}
    </TaskActivityContext.Provider>
  );
}

export function useTaskActivity() {
  const ctx = useContext(TaskActivityContext);
  if (!ctx) {
    throw new Error("useTaskActivity must be used within a TaskActivityProvider");
  }
  return ctx;
}

