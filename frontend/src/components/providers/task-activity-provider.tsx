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
import { useSession } from "./session-provider";

export interface ActiveTask {
  id: string;
  href: string; // e.g. "/leads/map", "/leads/discover"
  label: string;
  stage?: string;
  progress?: number;
  startedAt: number;
}

interface LocalSearchState {
  isRunning: boolean;
  niche: string;
  city: string;
  stage: string;
  progress: number;
  error: string | null;
  notice: string | null;
  start: (niche: string, city: string) => Promise<boolean>;
  cancel: () => void;
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
  const crawlControllerRef = useRef<AbortController | null>(null);

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
    async (niche: string, city: string): Promise<boolean> => {
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
      setLocalStage("Preparing public searches…");
      setLocalError(null);
      setLocalNotice(null);

      const controller = new AbortController();
      crawlControllerRef.current = controller;

      // Register the task on the sidebar for /leads/map
      startTask("/leads/map", `Searching ${cleanNiche} in ${cleanCity}`, "local-search");

      try {
        const result = await api.post<{ total_found: number; stored_new: number }>(
          "/discovery/local-search",
          { niche: cleanNiche, city: cleanCity },
          csrf,
          120_000,
          controller.signal
        );

        setLocalProgress(100);
        setLocalStage("Search complete");
        setLocalNotice(`Crawler found ${result.total_found}; ${result.stored_new} new businesses stored.`);
        await queryClient.invalidateQueries({ queryKey: ["local-business-finder"] });
        await queryClient.invalidateQueries({ queryKey: ["raw-businesses"] });
        return true;
      } catch (caught) {
        if (controller.signal.aborted) {
          setLocalError("Search cancelled.");
        } else {
          setLocalError(isApiError(caught) ? caught.message : "Search failed");
        }
        return false;
      } finally {
        setLocalRunning(false);
        crawlControllerRef.current = null;
        endTask("/leads/map");
      }
    },
    [csrf, queryClient, startTask, endTask]
  );

  const cancelLocalSearch = useCallback(() => {
    crawlControllerRef.current?.abort();
    setLocalRunning(false);
    endTask("/leads/map");
  }, [endTask]);

  // Smooth simulated progress ticker for local search
  useEffect(() => {
    if (!localRunning) return;
    const timer = window.setInterval(() => {
      setLocalProgress((current) => Math.min(92, current + 3));
      setLocalStage((current) => {
        if (current.includes("Preparing")) return "Searching public indexes…";
        if (current.includes("indexes")) return "Checking public business pages…";
        return "Normalising listings and saving results…";
      });
    }, 1800);
    return () => window.clearInterval(timer);
  }, [localRunning]);

  // Sync simulated progress to task object
  useEffect(() => {
    if (localRunning) {
      updateTask("/leads/map", { progress: localProgress, stage: localStage });
    }
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
          niche: localNiche,
          city: localCity,
          stage: localStage,
          progress: localProgress,
          error: localError,
          notice: localNotice,
          start: startLocalSearch,
          cancel: cancelLocalSearch,
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
