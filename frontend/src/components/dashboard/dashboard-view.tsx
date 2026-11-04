"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Building2, CheckCircle2, Compass, Globe2, MapPinned, Radar, Server, Sparkles, Workflow } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Header } from "@/components/layout/header";
import { useSession } from "@/components/providers/session-provider";
import { EmptyState } from "@/components/ui/card";
import { useBackendStatus } from "@/hooks/use-backend-status";
import { api } from "@/lib/api/client";
import type { AnalyticsBucket, AnalyticsOut, DiscoveryJob } from "@/lib/api/types";
import { cn } from "@/lib/utils";

interface JobListResponse { items: DiscoveryJob[]; total: number }
function sumCounts(buckets: AnalyticsBucket[]): number { return buckets.reduce((total, bucket) => total + bucket.count, 0); }

const actions = [
  { title: "Discover businesses", description: "Run a targeted lead search", href: "/leads/discover", icon: Compass, color: "bg-emerald-600/10 text-emerald-700 border-emerald-700/15" },
  { title: "Find local clients", description: "Search by niche and city", href: "/leads/map", icon: MapPinned, color: "bg-sky-600/10 text-sky-700 border-sky-700/15" },
  { title: "Research demand", description: "Inspect public buyer signals", href: "/intelligence/demand", icon: Radar, color: "bg-violet-600/10 text-violet-700 border-violet-700/15" },
  { title: "Build outreach", description: "Create a safe approval workflow", href: "/automation/workflows", icon: Workflow, color: "bg-orange-600/10 text-orange-700 border-orange-700/15" },
] as const;

export function DashboardView() {
  const { user } = useSession();
  const status = useBackendStatus();
  const [filterMode, setFilterMode] = useState<"all" | "completed" | "running">("all");
  const summary = useQuery({ queryKey: ["analytics"], queryFn: () => api.get<AnalyticsOut>("/analytics") });
  const recentJobs = useQuery({ queryKey: ["discovery", "jobs", "recent"], queryFn: () => api.get<JobListResponse | DiscoveryJob[]>("/discovery/jobs?limit=6") });
  const data = summary.data;
  const jobs = Array.isArray(recentJobs.data) ? recentJobs.data : Array.isArray(recentJobs.data?.items) ? recentJobs.data.items : [];
  const filteredJobs = jobs.filter((job) => filterMode === "completed" ? job.status === "completed" : filterMode === "running" ? job.status === "running" || job.status === "pending" : true);
  const metrics = [
    { label: "Businesses", value: data?.leads_total ?? 0, icon: Building2, tone: "bg-emerald-600/10 text-emerald-700" },
    { label: "Discovery runs", value: sumCounts(data?.discovery_jobs_by_status ?? []), icon: Compass, tone: "bg-sky-600/10 text-sky-700" },
    { label: "Social signals", value: sumCounts(data?.social_by_platform ?? []), icon: Globe2, tone: "bg-violet-600/10 text-violet-700" },
    { label: "Startups", value: sumCounts(data?.startups_by_funding_stage ?? []), icon: Sparkles, tone: "bg-orange-600/10 text-orange-700" },
  ];
  const components = status.ready?.components ?? [];
  const healthyComponents = components.filter((component) => component.ok).length;
  const firstName = user?.display_name?.split(" ")[0] ?? "there";

  return (
    <div className="flex min-h-0 flex-1 flex-col bg-transparent">
      <Header title="Dashboard" subtitle="Real data, recent activity and direct access to your tools" />
      <main className="flex-1 overflow-y-auto p-4 sm:p-6">
        <div className="mx-auto max-w-[1480px] space-y-5">
          <section className="grid gap-5 xl:grid-cols-[minmax(0,1.45fr)_minmax(320px,.55fr)]">
            <div className="rounded-[30px] border border-[var(--color-border)] bg-[var(--color-card)] p-6 shadow-[0_18px_50px_rgba(45,48,43,0.10)] backdrop-blur-2xl sm:p-8">
              <div className="flex flex-col justify-between gap-6 sm:flex-row sm:items-start">
                <div>
                  <div className="inline-flex items-center gap-2 rounded-full bg-emerald-700/10 px-3 py-1 text-xs font-semibold text-emerald-800"><Sparkles size={13} /> Welcome, {firstName}</div>
                  <h2 className="mt-4 text-3xl font-extrabold tracking-[-0.04em] text-[var(--color-foreground)] sm:text-4xl">What do you want to do?</h2>
                  <p className="mt-2 max-w-2xl text-sm leading-6 text-[var(--color-muted)]">Start a search, inspect local opportunities, research demand or build outreach from one place.</p>
                </div>
                <Link className="inline-flex shrink-0 items-center gap-2 rounded-full bg-[var(--color-primary)] px-5 py-2.5 text-sm font-bold text-white shadow-lg shadow-emerald-900/10 transition hover:bg-[var(--color-primary-hover)]" href="/leads/discover">New discovery <ArrowRight size={15} /></Link>
              </div>
              <div className="mt-7 grid gap-3 sm:grid-cols-2">
                {actions.map((action) => {
                  const Icon = action.icon;
                  return <Link key={action.href} href={action.href} className="group flex items-center gap-4 rounded-[22px] border border-[var(--color-border)] bg-[var(--color-surface)]/80 p-4 transition hover:-translate-y-0.5 hover:border-[var(--color-border-highlight)] hover:bg-[var(--color-surface-elevated)]">
                    <span className={cn("flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl border", action.color)}><Icon size={20} /></span>
                    <span className="min-w-0 flex-1"><span className="block text-sm font-bold text-[var(--color-foreground)]">{action.title}</span><span className="mt-0.5 block text-xs text-[var(--color-muted)]">{action.description}</span></span>
                    <ArrowRight className="text-[var(--color-muted-dim)] transition group-hover:translate-x-0.5 group-hover:text-[var(--color-primary)]" size={16} />
                  </Link>;
                })}
              </div>
            </div>

            <aside className="rounded-[30px] border border-[var(--color-border)] bg-[var(--color-card)] p-6 shadow-[0_18px_50px_rgba(45,48,43,0.10)] backdrop-blur-2xl">
              <div className="flex items-center justify-between">
                <div><p className="text-xs font-bold uppercase tracking-[0.14em] text-[var(--color-muted)]">System status</p><h3 className="mt-1 text-xl font-extrabold text-[var(--color-foreground)]">{healthyComponents}/{components.length || 0} services ready</h3></div>
                <span className={cn("flex h-11 w-11 items-center justify-center rounded-2xl", status.state === "online" ? "bg-emerald-600/10 text-emerald-700" : "bg-amber-600/10 text-amber-700")}><Server size={20} /></span>
              </div>
              <div className="mt-5 space-y-2">
                {components.length === 0 ? <p className="rounded-2xl bg-[var(--color-surface)] p-4 text-sm text-[var(--color-muted)]">Checking backend services…</p> : components.map((component) => <div key={component.name} className="flex items-center justify-between rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)]/70 px-4 py-3"><span className="text-sm font-semibold capitalize text-[var(--color-foreground)]">{component.name}</span><span className={cn("inline-flex items-center gap-1.5 text-xs font-bold", component.ok ? "text-emerald-700" : "text-red-700")}><CheckCircle2 size={14} />{component.ok ? "Ready" : "Issue"}</span></div>)}
              </div>
              <Link href="/sources" className="mt-4 inline-flex items-center gap-1.5 text-sm font-bold text-[var(--color-primary)] hover:underline">Open source health <ArrowRight size={14} /></Link>
            </aside>
          </section>

          <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {metrics.map((metric) => {
              const Icon = metric.icon;
              return <div key={metric.label} className="rounded-[24px] border border-[var(--color-border)] bg-[var(--color-card)] p-5 shadow-[0_12px_30px_rgba(45,48,43,0.08)] backdrop-blur-xl">
                <div className="flex items-center justify-between"><span className="text-xs font-bold uppercase tracking-[0.12em] text-[var(--color-muted)]">{metric.label}</span><span className={cn("flex h-9 w-9 items-center justify-center rounded-xl", metric.tone)}><Icon size={17} /></span></div>
                <p className="mt-4 text-3xl font-extrabold tracking-tight text-[var(--color-foreground)]">{summary.isPending ? "—" : metric.value.toLocaleString()}</p><p className="mt-1 text-xs text-[var(--color-muted)]">Current stored total</p>
              </div>;
            })}
          </section>

          <section className="rounded-[30px] border border-[var(--color-border)] bg-[var(--color-card)] p-5 shadow-[0_18px_50px_rgba(45,48,43,0.09)] backdrop-blur-2xl sm:p-6">
            <div className="flex flex-col gap-4 border-b border-[var(--color-border)] pb-5 sm:flex-row sm:items-center sm:justify-between">
              <div><h3 className="text-lg font-extrabold text-[var(--color-foreground)]">Recent discovery runs</h3><p className="mt-1 text-xs text-[var(--color-muted)]">Actual worker activity and collected-record counts</p></div>
              <div className="flex flex-wrap gap-2">
                {(["all", "completed", "running"] as const).map((filter) => <button key={filter} type="button" onClick={() => setFilterMode(filter)} className={cn("rounded-full border px-3.5 py-1.5 text-xs font-bold capitalize transition", filterMode === filter ? "border-[var(--color-primary)] bg-[var(--color-primary)] text-white" : "border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-muted)] hover:text-[var(--color-foreground)]")}>{filter}</button>)}
                <Link href="/leads/discover" className="rounded-full border border-[var(--color-border)] bg-[var(--color-surface-elevated)] px-3.5 py-1.5 text-xs font-bold text-[var(--color-foreground)]">New run +</Link>
              </div>
            </div>
            <div className="mt-4 space-y-2">
              {recentJobs.isPending && <p className="py-10 text-center text-sm text-[var(--color-muted)]">Loading recent runs…</p>}
              {!recentJobs.isPending && filteredJobs.length === 0 && <EmptyState title="No runs in this view" description="Start a discovery run or change the status filter." action={<Link href="/leads/discover" className="rounded-full bg-[var(--color-primary)] px-4 py-2 text-xs font-bold text-white">Start discovery</Link>} />}
              {filteredJobs.map((job) => <div key={job.id} className="grid gap-3 rounded-[20px] border border-[var(--color-border)] bg-[var(--color-surface)]/70 p-4 sm:grid-cols-[minmax(0,1fr)_auto_auto_auto] sm:items-center">
                <div className="min-w-0"><div className="flex items-center gap-2"><Compass className="shrink-0 text-[var(--color-primary)]" size={16} /><span className="truncate text-sm font-bold text-[var(--color-foreground)]">{job.job_type === "discover_area" ? "Geographic area discovery" : job.job_type}</span></div><p className="mt-1 text-xs text-[var(--color-muted)]">{new Date(job.created_at).toLocaleString()}</p></div>
                <span className={cn("w-fit rounded-full px-2.5 py-1 text-[11px] font-bold capitalize", job.status === "completed" ? "bg-emerald-600/10 text-emerald-700" : job.status === "failed" ? "bg-red-600/10 text-red-700" : "bg-sky-600/10 text-sky-700")}>{job.status}</span>
                <div className="text-xs text-[var(--color-muted)]"><strong className="mr-1 text-[var(--color-foreground)]">{job.processed_records}</strong>records</div>
                <Link href="/leads/raw" className="inline-flex items-center gap-1 text-xs font-bold text-[var(--color-primary)]">View <ArrowRight size={13} /></Link>
              </div>)}
            </div>
          </section>
        </div>
      </main>
    </div>
  );
}
