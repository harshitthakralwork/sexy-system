"use client";

import Link from "next/link";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Compass, Play, MapPin, RefreshCw, CheckCircle2, AlertCircle, ArrowRight, Layers } from "lucide-react";

import { Header } from "@/components/layout/header";
import { Card, CardTitle, EmptyState } from "@/components/ui/card";
import { useSession } from "@/components/providers/session-provider";
import { api, isApiError } from "@/lib/api/client";
import type { DiscoveryJob, SearchArea } from "@/lib/api/types";

interface JobListResponse {
  items: DiscoveryJob[];
  total: number;
}

interface AreaListResponse {
  items: SearchArea[];
  total: number;
}

export function DiscoverBusinessesView() {
  const { csrf } = useSession();
  const queryClient = useQueryClient();

  const [query, setQuery] = useState("");
  const [city, setCity] = useState("");
  const [category, setCategory] = useState("all");
  const [selectedSources, setSelectedSources] = useState<string[]>(["overpass", "searxng"]);
  const [selectedAreaId, setSelectedAreaId] = useState<string>("");
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const jobsQuery = useQuery({
    queryKey: ["discovery-jobs"],
    queryFn: () => api.get<JobListResponse>("/discovery/jobs?limit=20"),
    refetchInterval: 4000,
  });

  const areasQuery = useQuery({
    queryKey: ["discovery-areas"],
    queryFn: () => api.get<AreaListResponse>("/discovery/areas"),
  });

  const startSweep = useMutation({
    mutationFn: async () => {
      setError(null);
      setNotice(null);
      const cleanSources = (selectedSources.length > 0 ? selectedSources : ["overpass", "searxng"])
        .map((s) => (s === "osm" ? "overpass" : s))
        .filter((s) => s === "overpass" || s === "searxng");

      const payload: Record<string, unknown> = {
        sources: cleanSources.length > 0 ? cleanSources : ["overpass"],
        country: "IN",
        max_results: 100,
      };

      if (selectedAreaId) {
        payload.area_id = selectedAreaId;
      } else {
        payload.geometry = {
          shape_type: "circle",
          latitude: 28.6139,
          longitude: 77.2090,
          radius_km: 5,
        };
      }

      if (query.trim()) {
        payload.keywords = [query.trim()];
      }
      if (category !== "all") {
        payload.category = category;
      } else if (!query.trim()) {
        payload.category = "amenity=hospital";
      }

      return api.post<DiscoveryJob>("/discovery/jobs", payload, csrf);
    },
    onSuccess: (job) => {
      setNotice(`Discovery sweep queued (ID: ${job.id.slice(0, 8)}). Initializing crawler…`);
      setQuery("");
      queryClient.invalidateQueries({ queryKey: ["discovery-jobs"] });
    },
    onError: (err) => {
      const msg = isApiError(err) ? err.message : "Failed to launch discovery job";
      setError(msg);
    },
  });

  const toggleSource = (source: string) => {
    setSelectedSources((prev) =>
      prev.includes(source) ? prev.filter((s) => s !== source) : [...prev, source]
    );
  };

  const jobs = jobsQuery.data?.items ?? [];
  const areas = areasQuery.data?.items ?? [];

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <Header
        title="Discover Businesses"
        subtitle="Automated lead discovery engine powered by multi-source scrapers and spatial grids"
      />

      <main className="flex-1 overflow-y-auto p-4 space-y-6">
        {notice && (
          <div className="flex items-center gap-2 rounded-md border border-[var(--color-primary)]/40 bg-[var(--color-primary)]/10 px-4 py-2.5 text-sm text-[var(--color-foreground)]">
            <CheckCircle2 size={16} className="text-[var(--color-primary)]" />
            <span>{notice}</span>
          </div>
        )}

        {error && (
          <div className="flex items-center gap-2 rounded-md border border-[var(--color-error)]/40 bg-[var(--color-error)]/10 px-4 py-2.5 text-sm text-[var(--color-error)]">
            <AlertCircle size={16} />
            <span>{error}</span>
          </div>
        )}

        {/* Sweep Launcher Card */}
        <Card>
          <div className="flex items-center justify-between pb-3 border-b border-border">
            <div className="flex items-center gap-2">
              <Compass className="text-[var(--color-primary)]" size={18} />
              <CardTitle>Launch Business Discovery Sweep</CardTitle>
            </div>
            <Link
              href="/leads/map"
              className="flex items-center gap-1.5 text-xs text-[var(--color-primary)] hover:underline"
            >
              <MapPin size={14} />
              <span>Draw custom polygon on Map</span>
            </Link>
          </div>

          <form
            onSubmit={(e) => {
              e.preventDefault();
              startSweep.mutate();
            }}
            className="mt-4 space-y-4"
          >
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <div>
                <label className="block text-xs font-medium text-[var(--color-muted)] mb-1">
                  Search Query / Business Type
                </label>
                <input
                  type="text"
                  placeholder="e.g. Dental Clinics, Bakeries, Tech Agencies"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  className="w-full rounded-md border border-border bg-[var(--color-background)] px-3 py-2 text-sm text-[var(--color-foreground)] placeholder:text-[var(--color-muted)] focus:outline-none focus:border-[var(--color-primary)]"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-[var(--color-muted)] mb-1">
                  Category Filter
                </label>
                <select
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                  className="w-full rounded-md border border-border bg-[var(--color-background)] px-3 py-2 text-sm text-[var(--color-foreground)] focus:outline-none focus:border-[var(--color-primary)]"
                >
                  <option value="all">All Categories</option>
                  <option value="amenity=hospital">Healthcare / Clinics</option>
                  <option value="amenity=restaurant">Food / Restaurants</option>
                  <option value="office=company">Corporate / IT Offices</option>
                  <option value="shop=supermarket">Retail / Stores</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-medium text-[var(--color-muted)] mb-1">
                  Target City or Metro
                </label>
                <input
                  type="text"
                  placeholder="e.g. San Francisco, Austin, London"
                  value={city}
                  onChange={(e) => setCity(e.target.value)}
                  disabled={Boolean(selectedAreaId)}
                  className="w-full rounded-md border border-border bg-[var(--color-background)] px-3 py-2 text-sm text-[var(--color-foreground)] placeholder:text-[var(--color-muted)] focus:outline-none focus:border-[var(--color-primary)] disabled:opacity-50"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-[var(--color-muted)] mb-1">
                  Or Saved Search Area
                </label>
                <select
                  value={selectedAreaId}
                  onChange={(e) => setSelectedAreaId(e.target.value)}
                  className="w-full rounded-md border border-border bg-[var(--color-background)] px-3 py-2 text-sm text-[var(--color-foreground)] focus:outline-none focus:border-[var(--color-primary)]"
                >
                  <option value="">-- Manual City / Coordinates --</option>
                  {areas.map((area) => (
                    <option key={area.id} value={area.id}>
                      {area.name} ({area.shape_type}, {area.area_km2.toFixed(1)} km²)
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="flex flex-wrap items-center justify-between gap-4 pt-2 border-t border-border/50">
              <div className="flex items-center gap-3">
                <span className="text-xs text-[var(--color-muted)]">Active Discovery Sources:</span>
                <label className="flex items-center gap-1.5 text-xs cursor-pointer">
                  <input
                    type="checkbox"
                    checked={selectedSources.includes("overpass")}
                    onChange={() => toggleSource("overpass")}
                    className="rounded border-border accent-[var(--color-primary)]"
                  />
                  <span>OpenStreetMap / Overpass (POI)</span>
                </label>
                <label className="flex items-center gap-1.5 text-xs cursor-pointer">
                  <input
                    type="checkbox"
                    checked={selectedSources.includes("searxng")}
                    onChange={() => toggleSource("searxng")}
                    className="rounded border-border accent-[var(--color-primary)]"
                  />
                  <span>SearXNG (Web Metasearch)</span>
                </label>
              </div>

              <button
                type="submit"
                disabled={startSweep.isPending || (!query && !city && !selectedAreaId)}
                className="refraction-glass-btn flex items-center gap-2 rounded-full border border-cyan-400/40 bg-cyan-500/20 px-5 py-2 text-xs font-bold text-cyan-200 shadow-[0_0_16px_rgba(0,212,255,0.25)] hover:bg-cyan-500/30 hover:text-white disabled:opacity-40 transition-all cursor-pointer"
              >
                {startSweep.isPending ? (
                  <>
                    <RefreshCw size={14} className="animate-spin" />
                    <span>Queuing Sweep…</span>
                  </>
                ) : (
                  <>
                    <Play size={14} />
                    <span>Start Business Discovery</span>
                  </>
                )}
              </button>
            </div>
          </form>
        </Card>

        {/* Discovery Runs Table */}
        <Card>
          <div className="flex items-center justify-between pb-3 border-b border-border">
            <div className="flex items-center gap-2">
              <Layers className="text-[var(--color-primary)]" size={18} />
              <CardTitle>Discovery Jobs &amp; Ingestion Runs</CardTitle>
            </div>
            <button
              type="button"
              onClick={() => jobsQuery.refetch()}
              className="flex items-center gap-1 text-xs text-[var(--color-muted)] hover:text-[var(--color-foreground)]"
            >
              <RefreshCw size={12} className={jobsQuery.isFetching ? "animate-spin" : ""} />
              <span>Refresh</span>
            </button>
          </div>

          {jobsQuery.isLoading ? (
            <div className="py-8 text-center text-xs text-[var(--color-muted)]">
              Loading discovery runs…
            </div>
          ) : jobs.length === 0 ? (
            <EmptyState
              title="No discovery runs yet"
              description="Launch your first business discovery sweep above or draw an area on the Map Explorer."
            />
          ) : (
            <div className="mt-3 overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-border text-[var(--color-muted)]">
                    <th className="py-2 px-3 font-medium">Job ID</th>
                    <th className="py-2 px-3 font-medium">Status</th>
                    <th className="py-2 px-3 font-medium">Progress</th>
                    <th className="py-2 px-3 font-medium">Records Found</th>
                    <th className="py-2 px-3 font-medium">Created</th>
                    <th className="py-2 px-3 font-medium text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/60">
                  {jobs.map((job) => {
                    const isDone = job.status === "completed" || job.status === "finished";
                    const isRunning = job.status === "running" || job.status === "processing";
                    const isFailed = job.status === "failed";

                    return (
                      <tr key={job.id} className="hover:bg-[var(--color-surface)]/50">
                        <td className="py-2.5 px-3 font-mono text-[11px] text-[var(--color-muted)]">
                          {job.id.slice(0, 8)}…
                        </td>
                        <td className="py-2.5 px-3">
                          <span
                            className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-medium ${
                              isDone
                                ? "bg-[var(--color-success)]/10 text-[var(--color-success)]"
                                : isRunning
                                ? "bg-[var(--color-primary)]/10 text-[var(--color-primary)] animate-pulse"
                                : isFailed
                                ? "bg-[var(--color-error)]/10 text-[var(--color-error)]"
                                : "bg-[var(--color-muted)]/10 text-[var(--color-muted)]"
                            }`}
                          >
                            {job.status}
                          </span>
                        </td>
                        <td className="py-2.5 px-3 w-32">
                          <div className="w-full bg-[var(--color-surface)] rounded-full h-1.5 overflow-hidden">
                            <div
                              className="bg-gradient-to-r from-cyan-400 to-sky-500 shadow-[0_0_8px_rgba(0,212,255,0.4)] h-1.5 rounded-full transition-all duration-300"
                              style={{ width: `${Math.max(job.progress_percent || 0, isDone ? 100 : 5)}%` }}
                            />
                          </div>
                          <span className="text-[10px] text-[var(--color-muted)]">
                            {job.progress_percent ?? (isDone ? 100 : 0)}%
                          </span>
                        </td>
                        <td className="py-2.5 px-3 font-medium text-[var(--color-foreground)]">
                          {job.total_records || job.processed_records || 0}
                        </td>
                        <td className="py-2.5 px-3 text-[var(--color-muted)]">
                          {new Date(job.created_at).toLocaleString(undefined, {
                            month: "short",
                            day: "numeric",
                            hour: "2-digit",
                            minute: "2-digit",
                          })}
                        </td>
                        <td className="py-2.5 px-3 text-right space-x-2">
                          <Link
                            href={`/leads?job_id=${job.id}`}
                            className="inline-flex items-center gap-1 text-[var(--color-primary)] hover:underline"
                          >
                            <span>View Leads</span>
                            <ArrowRight size={12} />
                          </Link>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </main>
    </div>
  );
}
