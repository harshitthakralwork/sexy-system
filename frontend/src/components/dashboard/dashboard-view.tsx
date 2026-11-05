"use client";

import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  Building2,
  CheckCircle2,
  Compass,
  Globe2,
  MapPinned,
  Radar,
  Server,
  Sparkles,
  Workflow,
} from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Header } from "@/components/layout/header";
import { useSession } from "@/components/providers/session-provider";
import { EmptyState } from "@/components/ui/card";
import { useBackendStatus } from "@/hooks/use-backend-status";
import { api } from "@/lib/api/client";
import type { AnalyticsBucket, AnalyticsOut, DiscoveryJob } from "@/lib/api/types";
import { cn } from "@/lib/utils";

interface JobListResponse {
  items: DiscoveryJob[];
  total: number;
}

function sumCounts(buckets: AnalyticsBucket[]): number {
  return buckets.reduce((total, bucket) => total + bucket.count, 0);
}

const actions = [
  {
    title: "Discover businesses",
    description: "Run a targeted lead search",
    href: "/leads/discover",
    icon: Compass,
    color: "bg-emerald-500/15 text-emerald-300 border-emerald-400/30",
  },
  {
    title: "Find local clients",
    description: "Search by niche and city",
    href: "/leads/map",
    icon: MapPinned,
    color: "bg-sky-500/15 text-sky-300 border-sky-400/30",
  },
  {
    title: "Research demand",
    description: "Inspect public buyer signals",
    href: "/intelligence/demand",
    icon: Radar,
    color: "bg-violet-500/15 text-violet-300 border-violet-400/30",
  },
  {
    title: "Build outreach",
    description: "Create a safe approval workflow",
    href: "/automation/workflows",
    icon: Workflow,
    color: "bg-orange-500/15 text-orange-300 border-orange-400/30",
  },
] as const;

export function DashboardView() {
  const { user } = useSession();
  const status = useBackendStatus();
  const [filterMode, setFilterMode] = useState<"all" | "completed" | "running">("all");

  const summary = useQuery({
    queryKey: ["analytics"],
    queryFn: () => api.get<AnalyticsOut>("/analytics"),
  });

  const recentJobs = useQuery({
    queryKey: ["discovery", "jobs", "recent"],
    queryFn: () => api.get<JobListResponse | DiscoveryJob[]>("/discovery/jobs?limit=6"),
  });

  const data = summary.data;
  const jobs = Array.isArray(recentJobs.data)
    ? recentJobs.data
    : Array.isArray(recentJobs.data?.items)
      ? recentJobs.data.items
      : [];

  const filteredJobs = jobs.filter((job) =>
    filterMode === "completed"
      ? job.status === "completed"
      : filterMode === "running"
        ? job.status === "running" || job.status === "pending"
        : true
  );

  const metrics = [
    {
      label: "Businesses",
      value: data?.leads_total ?? 0,
      icon: Building2,
      tone: "bg-emerald-500/20 text-emerald-300 border border-emerald-400/30",
    },
    {
      label: "Discovery runs",
      value: sumCounts(data?.discovery_jobs_by_status ?? []),
      icon: Compass,
      tone: "bg-sky-500/20 text-sky-300 border border-sky-400/30",
    },
    {
      label: "Social signals",
      value: sumCounts(data?.social_by_platform ?? []),
      icon: Globe2,
      tone: "bg-violet-500/20 text-violet-300 border border-violet-400/30",
    },
    {
      label: "Startups",
      value: sumCounts(data?.startups_by_funding_stage ?? []),
      icon: Sparkles,
      tone: "bg-orange-500/20 text-orange-300 border border-orange-400/30",
    },
  ];

  const components = status.ready?.components ?? [];
  const healthyComponents = components.filter((component) => component.ok).length;
  const firstName = user?.display_name?.split(" ")[0] ?? "there";

  return (
    <div className="flex min-h-0 flex-1 flex-col bg-transparent text-white">
      <Header title="Dashboard" subtitle="Real data, recent activity and direct access to your tools" />

      <main className="flex-1 overflow-y-auto p-4 sm:p-6">
        <div className="mx-auto max-w-[1480px] space-y-6">
          {/* Top Section: Action Center + System Status */}
          <section className="grid gap-6 xl:grid-cols-[minmax(0,1.45fr)_minmax(320px,.55fr)]">
            {/* Primary Action Card with Frosted Glass */}
            <div className="refraction-glass-card rounded-[32px] p-6 sm:p-8 transition-all">
              <div className="flex flex-col justify-between gap-6 sm:flex-row sm:items-start">
                <div>
                  <div className="inline-flex items-center gap-2 rounded-full border border-emerald-400/30 bg-emerald-500/15 px-3.5 py-1 text-xs font-semibold text-emerald-300 shadow-sm">
                    <Sparkles size={13} className="text-emerald-300" />
                    <span>Welcome, {firstName}</span>
                  </div>
                  <h2 className="mt-4 text-3xl sm:text-4xl font-extrabold tracking-tight text-white">
                    What do you want to do?
                  </h2>
                  <p className="mt-2 max-w-2xl text-sm leading-relaxed text-white/70">
                    Start a search, inspect local opportunities, research demand or build outreach from one place.
                  </p>
                </div>

                <Link
                  href="/leads/discover"
                  className="refraction-glass-btn inline-flex shrink-0 items-center gap-2 rounded-full px-6 py-2.5 text-sm font-bold text-white shadow-[0_0_25px_rgba(0,212,255,0.25)] hover:shadow-[0_0_35px_rgba(0,212,255,0.45)]"
                >
                  <span>New discovery</span>
                  <ArrowRight size={15} className="text-cyan-400" />
                </Link>
              </div>

              {/* 4 Action Pills */}
              <div className="mt-8 grid gap-3 sm:grid-cols-2">
                {actions.map((action) => {
                  const Icon = action.icon;
                  return (
                    <Link
                      key={action.href}
                      href={action.href}
                      className="group flex items-center gap-4 rounded-[22px] border border-white/10 bg-white/[0.04] p-4.5 backdrop-blur-xl transition-all duration-200 hover:-translate-y-0.5 hover:border-white/25 hover:bg-white/[0.08] shadow-lg"
                    >
                      <span
                        className={cn(
                          "flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl border shadow-inner",
                          action.color
                        )}
                      >
                        <Icon size={20} />
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block text-sm font-bold text-white group-hover:text-cyan-300 transition-colors">
                          {action.title}
                        </span>
                        <span className="mt-0.5 block text-xs text-white/60">
                          {action.description}
                        </span>
                      </span>
                      <ArrowRight
                        className="text-white/30 transition group-hover:translate-x-1 group-hover:text-cyan-400"
                        size={16}
                      />
                    </Link>
                  );
                })}
              </div>
            </div>

            {/* Aside: System Status Card with Frosted Glass */}
            <aside className="refraction-glass-card rounded-[32px] p-6 sm:p-7 flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-[11px] font-bold uppercase tracking-wider text-white/50">
                      System status
                    </p>
                    <h3 className="mt-1 text-xl font-extrabold text-white">
                      {healthyComponents}/{components.length || 0} services ready
                    </h3>
                  </div>
                  <span
                    className={cn(
                      "flex h-11 w-11 items-center justify-center rounded-2xl border",
                      status.state === "online"
                        ? "bg-emerald-500/15 border-emerald-400/30 text-emerald-300"
                        : "bg-amber-500/15 border-amber-400/30 text-amber-300"
                    )}
                  >
                    <Server size={20} />
                  </span>
                </div>

                <div className="mt-6 space-y-2.5">
                  {components.length === 0 ? (
                    <p className="rounded-2xl border border-white/10 bg-white/[0.03] p-4 text-xs text-white/50">
                      Checking backend services…
                    </p>
                  ) : (
                    components.map((component) => (
                      <div
                        key={component.name}
                        className="flex items-center justify-between rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-3 backdrop-blur-md"
                      >
                        <span className="text-xs font-semibold capitalize text-white/90">
                          {component.name}
                        </span>
                        <span
                          className={cn(
                            "inline-flex items-center gap-1.5 text-[11px] font-bold px-2 py-0.5 rounded-full border",
                            component.ok
                              ? "bg-emerald-500/15 border-emerald-400/30 text-emerald-300"
                              : "bg-red-500/15 border-red-400/30 text-red-300"
                          )}
                        >
                          <CheckCircle2 size={12} />
                          {component.ok ? "Ready" : "Issue"}
                        </span>
                      </div>
                    ))
                  )}
                </div>
              </div>

              <Link
                href="/sources"
                className="mt-6 inline-flex items-center gap-1.5 text-xs font-bold text-cyan-400 hover:text-cyan-300 transition-colors"
              >
                <span>Open source health</span>
                <ArrowRight size={14} />
              </Link>
            </aside>
          </section>

          {/* 4 Frosted Glass Metric KPI Cards */}
          <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {metrics.map((metric) => {
              const Icon = metric.icon;
              return (
                <div
                  key={metric.label}
                  className="refraction-glass-card rounded-[26px] p-5.5 hover:border-white/30 transition-all duration-200"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] font-bold uppercase tracking-wider text-white/50">
                      {metric.label}
                    </span>
                    <span
                      className={cn(
                        "flex h-9 w-9 items-center justify-center rounded-xl",
                        metric.tone
                      )}
                    >
                      <Icon size={17} />
                    </span>
                  </div>
                  <p className="mt-4 text-3xl font-extrabold tracking-tight text-white font-sans">
                    {summary.isPending ? "—" : metric.value.toLocaleString()}
                  </p>
                  <p className="mt-1 text-xs text-white/45">Current stored total</p>
                </div>
              );
            })}
          </section>

          {/* Bottom Table: Recent Discovery Runs in Frosted Glass */}
          <section className="refraction-glass-card rounded-[32px] p-6 sm:p-7">
            <div className="flex flex-col gap-4 border-b border-white/10 pb-5 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h3 className="text-lg font-extrabold text-white">Recent discovery runs</h3>
                <p className="mt-1 text-xs text-white/55">
                  Actual worker activity and collected-record counts
                </p>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                {(["all", "completed", "running"] as const).map((filter) => (
                  <button
                    key={filter}
                    type="button"
                    onClick={() => setFilterMode(filter)}
                    className={cn(
                      "rounded-full px-4 py-1.5 text-xs font-bold capitalize transition-all",
                      filterMode === filter
                        ? "border border-cyan-400/40 bg-cyan-500/20 text-cyan-200 shadow-[0_0_20px_rgba(0,212,255,0.3)]"
                        : "border border-white/10 bg-white/[0.04] text-white/60 hover:text-white hover:border-white/20"
                    )}
                  >
                    {filter}
                  </button>
                ))}

                <Link
                  href="/leads/discover"
                  className="refraction-glass-btn rounded-full px-4 py-1.5 text-xs font-bold text-white flex items-center gap-1.5"
                >
                  <span>New run +</span>
                </Link>
              </div>
            </div>

            <div className="mt-5 space-y-2.5">
              {recentJobs.isPending && (
                <p className="py-10 text-center text-xs text-white/50">Loading recent runs…</p>
              )}

              {!recentJobs.isPending && filteredJobs.length === 0 && (
                <EmptyState
                  title="No runs in this view"
                  description="Start a discovery run or change the status filter."
                  action={
                    <Link
                      href="/leads/discover"
                      className="refraction-glass-btn rounded-full px-5 py-2 text-xs font-bold text-white"
                    >
                      Start discovery
                    </Link>
                  }
                />
              )}

              {filteredJobs.map((job) => (
                <div
                  key={job.id}
                  className="grid gap-3 rounded-[20px] border border-white/10 bg-white/[0.03] p-4 backdrop-blur-md hover:bg-white/[0.06] hover:border-white/25 transition-all sm:grid-cols-[minmax(0,1fr)_auto_auto_auto] sm:items-center"
                >
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <Compass className="shrink-0 text-cyan-400" size={16} />
                      <span className="truncate text-sm font-bold text-white">
                        {job.job_type === "discover_area"
                          ? "Geographic area discovery"
                          : job.job_type}
                      </span>
                    </div>
                    <p className="mt-1 text-xs text-white/50">
                      {new Date(job.created_at).toLocaleString()}
                    </p>
                  </div>

                  <span
                    className={cn(
                      "w-fit rounded-full px-3 py-1 text-[11px] font-bold capitalize border",
                      job.status === "completed"
                        ? "bg-emerald-500/15 border-emerald-400/30 text-emerald-300"
                        : job.status === "failed"
                          ? "bg-red-500/15 border-red-400/30 text-red-300"
                          : "bg-sky-500/15 border-sky-400/30 text-sky-300"
                    )}
                  >
                    {job.status}
                  </span>

                  <div className="text-xs text-white/60">
                    <strong className="mr-1 text-white font-mono">{job.processed_records}</strong>
                    records
                  </div>

                  <Link
                    href="/leads/raw"
                    className="inline-flex items-center gap-1 text-xs font-bold text-cyan-400 hover:text-cyan-300 transition-colors"
                  >
                    <span>View</span>
                    <ArrowRight size={13} />
                  </Link>
                </div>
              ))}
            </div>
          </section>
        </div>
      </main>
    </div>
  );
}
