"use client";

import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  Building2,
  CheckCircle2,
  Compass,
  Globe2,
  ListChecks,
  MapPinned,
  Radar,
  Server,
  Sparkles,
  TrendingUp,
  XCircle,
  Clock,
} from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Header } from "@/components/layout/header";
import { MapIntelligenceView } from "@/components/map/map-intelligence-view";
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
    glow: "group-hover:shadow-[0_0_28px_rgba(52,211,153,0.35)]",
    hoverBorder: "hover:border-emerald-400/30",
  },
  {
    title: "Find local clients",
    description: "Search by niche and city",
    href: "/leads/map",
    icon: MapPinned,
    color: "bg-sky-500/15 text-sky-300 border-sky-400/30",
    glow: "group-hover:shadow-[0_0_28px_rgba(56,189,248,0.35)]",
    hoverBorder: "hover:border-sky-400/30",
  },
  {
    title: "Research demand",
    description: "Inspect public buyer signals",
    href: "/intelligence/demand",
    icon: Radar,
    color: "bg-violet-500/15 text-violet-300 border-violet-400/30",
    glow: "group-hover:shadow-[0_0_28px_rgba(192,132,252,0.35)]",
    hoverBorder: "hover:border-violet-400/30",
  },
  {
    title: "Review lead results",
    description: "Filter and export collected prospects",
    href: "/leads/raw",
    icon: ListChecks,
    color: "bg-orange-500/15 text-orange-300 border-orange-400/30",
    glow: "group-hover:shadow-[0_0_28px_rgba(255,120,73,0.35)]",
    hoverBorder: "hover:border-orange-400/30",
  },
] as const;

// ─── KPI Card ───────────────────────────────────────────────────────────────

function KpiCard({
  label,
  value,
  icon: Icon,
  tone,
  glowClass,
  loading,
  delay = 0,
}: {
  label: string;
  value: number;
  icon: React.ElementType;
  tone: string;
  glowClass: string;
  loading: boolean;
  delay?: number;
}) {
  return (
    <div
      className={cn(
        "refraction-glass-card rounded-[26px] p-5 flex flex-col gap-4",
        "hover:-translate-y-0.5 transition-all duration-300 cursor-default",
        glowClass,
        "animate-slide-up"
      )}
      style={{ animationDelay: `${delay}ms` }}
    >
      <div className="flex items-center justify-between">
        <span className="text-[10px] font-bold uppercase tracking-widest text-white/45">
          {label}
        </span>

        {/* Icon with pulsing ring */}
        <div className="relative flex items-center justify-center">
          <span
            className={cn(
              "absolute h-9 w-9 rounded-xl opacity-0",
              loading ? "" : "animate-pulse-ring",
              tone.split(" ")[0] // grab the bg- token
            )}
          />
          <span
            className={cn(
              "relative flex h-9 w-9 items-center justify-center rounded-xl border",
              tone
            )}
          >
            <Icon size={16} />
          </span>
        </div>
      </div>

      {loading ? (
        <div className="skeleton h-8 w-24" />
      ) : (
        <div className="flex items-end gap-2">
          <p className="text-3xl font-extrabold tracking-tight text-white leading-none font-sans">
            {value.toLocaleString()}
          </p>
          <span className="mb-0.5 flex items-center gap-0.5 text-[10px] font-bold text-emerald-400">
            <TrendingUp size={10} />
            Live
          </span>
        </div>
      )}

      <p className="text-[10px] text-white/35 font-medium">Total stored</p>
    </div>
  );
}

// ─── Job Status Badge ────────────────────────────────────────────────────────

function JobBadge({ status }: { status: string }) {
  const map: Record<string, { cls: string; icon: React.ElementType; label: string }> = {
    completed: {
      cls: "bg-emerald-500/15 border-emerald-400/30 text-emerald-300",
      icon: CheckCircle2,
      label: "Completed",
    },
    failed: {
      cls: "bg-red-500/15 border-red-400/30 text-red-300",
      icon: XCircle,
      label: "Failed",
    },
  };
  const cfg = map[status] ?? {
    cls: "bg-sky-500/15 border-sky-400/30 text-sky-300",
    icon: Clock,
    label: status.charAt(0).toUpperCase() + status.slice(1),
  };
  const Icon = cfg.icon;

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 w-fit rounded-full px-3 py-1 text-[10px] font-bold border",
        cfg.cls
      )}
    >
      <Icon size={11} />
      {cfg.label}
    </span>
  );
}

// ─── Job Row ─────────────────────────────────────────────────────────────────

function JobRow({ job, index }: { job: DiscoveryJob; index: number }) {
  const isRunning = job.status === "running" || job.status === "pending";

  return (
    <div
      className={cn(
        "group grid gap-3 rounded-[18px] border border-white/[0.08] bg-white/[0.025]",
        "p-4 backdrop-blur-sm hover:bg-white/[0.055] hover:border-white/20",
        "transition-all duration-200 animate-slide-up",
        "sm:grid-cols-[minmax(0,1fr)_auto_auto_auto] sm:items-center"
      )}
      style={{ animationDelay: `${index * 40}ms` }}
    >
      {/* Info */}
      <div className="min-w-0 space-y-1.5">
        <div className="flex items-center gap-2">
          <Compass
            className={cn(
              "shrink-0 transition-colors",
              isRunning ? "text-sky-400 animate-glow-breathe" : "text-cyan-400/70"
            )}
            size={15}
          />
          <span className="truncate text-sm font-bold text-white group-hover:text-cyan-200 transition-colors">
            {job.job_type === "discover_area" ? "Geographic area discovery" : job.job_type}
          </span>
        </div>
        <p className="text-[11px] text-white/40 font-medium pl-5">
          {new Date(job.created_at).toLocaleString()}
        </p>

        {/* Running progress bar */}
        {isRunning && (
          <div className="job-progress-track ml-5">
            <div className="job-progress-fill indeterminate" />
          </div>
        )}
      </div>

      <JobBadge status={job.status} />

      <div className="text-xs text-white/55">
        <strong className="mr-1 text-white font-mono text-sm">
          {job.processed_records.toLocaleString()}
        </strong>
        records
      </div>

      <Link
        href="/leads/raw"
        className="inline-flex items-center gap-1 text-xs font-bold text-cyan-400 hover:text-cyan-200 transition-colors group/link"
      >
        <span>View</span>
        <ArrowRight
          size={12}
          className="transition-transform group-hover/link:translate-x-0.5"
        />
      </Link>
    </div>
  );
}

// ─── Main Dashboard View ─────────────────────────────────────────────────────

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
      glowClass: "hover:kpi-glow-emerald",
    },
    {
      label: "Discovery runs",
      value: sumCounts(data?.discovery_jobs_by_status ?? []),
      icon: Compass,
      tone: "bg-sky-500/20 text-sky-300 border border-sky-400/30",
      glowClass: "hover:kpi-glow-sky",
    },
    {
      label: "Social signals",
      value: sumCounts(data?.social_by_platform ?? []),
      icon: Globe2,
      tone: "bg-violet-500/20 text-violet-300 border border-violet-400/30",
      glowClass: "hover:kpi-glow-violet",
    },
    {
      label: "Startups",
      value: sumCounts(data?.startups_by_funding_stage ?? []),
      icon: Sparkles,
      tone: "bg-orange-500/20 text-orange-300 border border-orange-400/30",
      glowClass: "hover:kpi-glow-orange",
    },
  ];

  const components = status.ready?.components ?? [];
  const healthyComponents = components.filter((c) => c.ok).length;
  const firstName = user?.display_name?.split(" ")[0] ?? "there";

  return (
    <div className="flex min-h-0 flex-1 flex-col bg-transparent text-white">
      <Header title="Dashboard" subtitle="Real data, recent activity and direct access to your tools" />

      <main className="flex-1 overflow-y-auto p-4 sm:p-6">
        <div className="mx-auto max-w-[1480px] space-y-5">

          {/* ── Top Section: Welcome + System Status ── */}
          <section className="grid gap-5 xl:grid-cols-[minmax(0,1.45fr)_minmax(300px,.55fr)]">

            {/* Welcome / Quick Actions card */}
            <div className="refraction-glass-card rounded-[28px] p-6 sm:p-8 animate-slide-up">
              <div className="flex flex-col justify-between gap-5 sm:flex-row sm:items-start">
                <div>
                  <div className="inline-flex items-center gap-2 rounded-full border border-emerald-400/30 bg-emerald-500/15 px-3.5 py-1 text-xs font-semibold text-emerald-300 shadow-sm">
                    <Sparkles size={12} className="text-emerald-300" />
                    <span>Welcome back, {firstName}</span>
                  </div>
                  <h2 className="mt-4 text-3xl sm:text-4xl font-extrabold tracking-tight text-white leading-tight">
                    What do you want<br className="hidden sm:block" /> to do today?
                  </h2>
                  <p className="mt-2 max-w-2xl text-sm leading-relaxed text-white/60">
                    Start a search, inspect local opportunities, research demand or build outreach — all from one place.
                  </p>
                </div>

                <Link
                  href="/leads/discover"
                  className="refraction-glass-btn inline-flex shrink-0 items-center gap-2 rounded-full px-6 py-2.5 text-sm font-bold text-white shadow-[0_0_28px_rgba(0,212,255,0.22)] hover:shadow-[0_0_40px_rgba(0,212,255,0.45)] group"
                >
                  <span>New discovery</span>
                  <ArrowRight
                    size={14}
                    className="text-cyan-400 transition-transform group-hover:translate-x-0.5"
                  />
                </Link>
              </div>

              {/* 4 Action Pills */}
              <div className="mt-7 grid gap-3 sm:grid-cols-2">
                {actions.map((action) => {
                  const Icon = action.icon;
                  return (
                    <Link
                      key={action.href}
                      href={action.href}
                      className={cn(
                        "group flex items-center gap-4 rounded-[20px] border border-white/[0.08]",
                        "bg-white/[0.03] p-4 backdrop-blur-xl",
                        "transition-all duration-200 hover:-translate-y-0.5 hover:border-white/20 hover:bg-white/[0.07]",
                        action.glow
                      )}
                    >
                      <span
                        className={cn(
                          "flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl border",
                          "shadow-inner transition-transform group-hover:scale-110",
                          action.color
                        )}
                      >
                        <Icon size={19} />
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block text-sm font-bold text-white group-hover:text-cyan-200 transition-colors">
                          {action.title}
                        </span>
                        <span className="mt-0.5 block text-xs text-white/50">
                          {action.description}
                        </span>
                      </span>
                      <ArrowRight
                        className="text-white/25 transition-all group-hover:translate-x-1 group-hover:text-cyan-400"
                        size={15}
                      />
                    </Link>
                  );
                })}
              </div>
            </div>

            {/* System Status card */}
            <aside
              className="refraction-glass-card rounded-[28px] p-6 sm:p-7 flex flex-col justify-between animate-slide-up"
              style={{ animationDelay: "60ms" }}
            >
              <div>
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-[10px] font-bold uppercase tracking-widest text-white/40">
                      System status
                    </p>
                    <h3 className="mt-1 text-xl font-extrabold text-white">
                      {healthyComponents}/{components.length || 0}{" "}
                      <span className="text-white/60 font-semibold text-base">services ready</span>
                    </h3>
                  </div>
                  <div className="relative">
                    {/* Pulsing ring on icon */}
                    <span
                      className={cn(
                        "absolute inset-0 rounded-2xl animate-pulse-ring",
                        status.state === "online"
                          ? "bg-emerald-400/40"
                          : "bg-amber-400/40"
                      )}
                    />
                    <span
                      className={cn(
                        "relative flex h-11 w-11 items-center justify-center rounded-2xl border",
                        status.state === "online"
                          ? "bg-emerald-500/15 border-emerald-400/30 text-emerald-300"
                          : "bg-amber-500/15 border-amber-400/30 text-amber-300"
                      )}
                    >
                      <Server size={19} />
                    </span>
                  </div>
                </div>

                <div className="mt-5 space-y-2">
                  {components.length === 0 ? (
                    <>
                      {[0, 1, 2].map((i) => (
                        <div key={i} className="skeleton h-11 w-full" style={{ animationDelay: `${i * 120}ms` }} />
                      ))}
                    </>
                  ) : (
                    components.map((component, i) => (
                      <div
                        key={component.name}
                        className={cn(
                          "flex items-center justify-between rounded-[14px] border border-white/[0.08]",
                          "bg-white/[0.025] px-4 py-2.5 backdrop-blur-sm animate-slide-up"
                        )}
                        style={{ animationDelay: `${i * 40}ms` }}
                      >
                        <span className="text-xs font-semibold capitalize text-white/80">
                          {component.name}
                        </span>
                        <span
                          className={cn(
                            "inline-flex items-center gap-1.5 text-[10px] font-bold px-2.5 py-1 rounded-full border",
                            component.ok
                              ? "bg-emerald-500/15 border-emerald-400/30 text-emerald-300"
                              : "bg-red-500/15 border-red-400/30 text-red-300"
                          )}
                        >
                          {component.ok ? (
                            <CheckCircle2 size={11} />
                          ) : (
                            <XCircle size={11} />
                          )}
                          {component.ok ? "Ready" : "Issue"}
                        </span>
                      </div>
                    ))
                  )}
                </div>
              </div>

              <Link
                href="/sources"
                className="mt-6 group inline-flex items-center gap-1.5 text-xs font-bold text-cyan-400 hover:text-cyan-200 transition-colors"
              >
                <span>Open source health</span>
                <ArrowRight
                  size={13}
                  className="transition-transform group-hover:translate-x-0.5"
                />
              </Link>
            </aside>
          </section>

          {/* ── KPI Cards ── */}
          <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {metrics.map((metric, i) => (
              <KpiCard
                key={metric.label}
                label={metric.label}
                value={metric.value}
                icon={metric.icon}
                tone={metric.tone}
                glowClass={metric.glowClass}
                loading={summary.isPending}
                delay={i * 50}
              />
            ))}
          </section>

          {/* ── Interactive Map Intelligence Preview (Direct Access to Local Business Radar) ── */}
          <section className="animate-slide-up" style={{ animationDelay: "140ms" }}>
            <MapIntelligenceView embedded={true} />
          </section>

          {/* ── Recent Discovery Runs ── */}
          <section
            className="refraction-glass-card rounded-[28px] p-6 sm:p-7 animate-slide-up"
            style={{ animationDelay: "180ms" }}
          >
            {/* Header row */}
            <div className="flex flex-col gap-4 border-b border-white/[0.08] pb-5 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h3 className="text-base font-extrabold text-white">Recent discovery runs</h3>
                <p className="mt-0.5 text-xs text-white/45 font-medium">
                  Worker activity and collected-record counts
                </p>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                {(["all", "completed", "running"] as const).map((filter) => (
                  <button
                    key={filter}
                    type="button"
                    onClick={() => setFilterMode(filter)}
                    className={cn(
                      "rounded-full px-4 py-1.5 text-[11px] font-bold capitalize transition-all duration-200",
                      filterMode === filter
                        ? "border border-cyan-400/40 bg-cyan-500/20 text-cyan-200 shadow-[0_0_18px_rgba(0,212,255,0.28)]"
                        : "border border-white/[0.08] bg-white/[0.03] text-white/50 hover:text-white hover:border-white/20"
                    )}
                  >
                    {filter}
                  </button>
                ))}

                <Link
                  href="/leads/discover"
                  className="refraction-glass-btn rounded-full px-4 py-1.5 text-[11px] font-bold text-white flex items-center gap-1.5"
                >
                  <span>New run</span>
                  <span className="text-cyan-400">+</span>
                </Link>
              </div>
            </div>

            {/* Job list */}
            <div className="mt-4 space-y-2.5">
              {recentJobs.isPending && (
                <div className="space-y-2.5">
                  {[0, 1, 2].map((i) => (
                    <div key={i} className="skeleton h-16 w-full" style={{ animationDelay: `${i * 80}ms` }} />
                  ))}
                </div>
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

              {filteredJobs.map((job, i) => (
                <JobRow key={job.id} job={job} index={i} />
              ))}
            </div>
          </section>

        </div>
      </main>
    </div>
  );
}
