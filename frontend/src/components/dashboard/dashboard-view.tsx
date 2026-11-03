"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  Compass,
  Globe,
  MapPinned,
  Radar,
  Search,
  Server,
  Sparkles,
  Workflow,
} from "lucide-react";

import { Header } from "@/components/layout/header";
import { Card, CardFootnote, CardTitle, CardValue, EmptyState } from "@/components/ui/card";
import { useSession } from "@/components/providers/session-provider";
import { useBackendStatus } from "@/hooks/use-backend-status";
import { api } from "@/lib/api/client";
import type { AnalyticsBucket, AnalyticsOut, DiscoveryJob } from "@/lib/api/types";

function bucketCount(buckets: AnalyticsBucket[], key: string): number | null {
  const hit = buckets.find((bucket) => bucket.key === key);
  return hit ? hit.count : null;
}

function sumCounts(buckets: AnalyticsBucket[]): number {
  return buckets.reduce((total, bucket) => total + bucket.count, 0);
}

function isEmptySurface(data: AnalyticsOut): boolean {
  return (
    data.leads_total === 0 &&
    sumCounts(data.social_by_platform) === 0 &&
    sumCounts(data.startups_by_funding_stage) === 0 &&
    sumCounts(data.discovery_jobs_by_status) === 0
  );
}

export function DashboardView() {
  const { user } = useSession();
  const status = useBackendStatus();
  const components = status.ready?.components ?? [];

  const summary = useQuery({
    queryKey: ["analytics"],
    queryFn: () => api.get<AnalyticsOut>("/analytics"),
  });
  const data = summary.data;

  const recentJobs = useQuery({
    queryKey: ["discovery", "jobs", "recent"],
    queryFn: () => api.get<DiscoveryJob[]>("/discovery/jobs?limit=5"),
  });

  return (
    <div className="flex min-h-0 flex-1 flex-col bg-[var(--color-background)]">
      <Header
        title="Mission Control"
        subtitle={
          status.info
            ? `${status.info.app_name} · ${status.info.environment} · region ${status.info.default_region}`
            : "Connecting to intelligence engine…"
        }
      />

      <main className="flex-1 space-y-8 overflow-y-auto p-4 sm:p-6 scrollbar-thin">
        {/* Welcome & Launchpad Header */}
        <div className="relative overflow-hidden rounded-2xl border border-[var(--color-border)] bg-gradient-to-r from-[var(--color-surface)] via-[var(--color-surface)] to-[var(--color-primary)]/10 p-5 sm:p-7 shadow-sm">
          <div className="relative z-10 flex flex-col justify-between gap-4 md:flex-row md:items-center">
            <div>
              <div className="inline-flex items-center gap-2 rounded-full border border-[var(--color-primary)]/30 bg-[var(--color-primary)]/10 px-3 py-1 text-xs font-semibold text-[var(--color-secondary)]">
                <Sparkles size={12} />
                <span>Next-Gen Market & Lead Intelligence</span>
              </div>
              <h1 className="mt-2 text-xl font-bold tracking-tight text-[var(--color-foreground)] sm:text-2xl">
                Welcome back{user?.display_name ? `, ${user.display_name.split(" ")[0]}` : ""} 👋
              </h1>
              <p className="mt-1 max-w-2xl text-xs text-[var(--color-muted)] sm:text-sm">
                Unified operations cockpit for local business discovery, venture intelligence, 12-platform social listening, and autonomous outreach workflows.
              </p>
            </div>

            <div className="flex flex-wrap items-center gap-2.5">
              <button
                type="button"
                onClick={() => window.dispatchEvent(new CustomEvent("open-command-palette"))}
                className="flex items-center gap-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-elevated)] px-3 py-2 text-xs font-medium text-[var(--color-foreground)] shadow-xs hover:border-[var(--color-primary)]"
              >
                <Search size={14} className="text-[var(--color-muted)]" />
                <span>Search Everything</span>
                <kbd className="rounded bg-[var(--color-surface)] px-1.5 py-0.5 text-[10px] font-mono text-[var(--color-muted)]">
                  ⌘K
                </kbd>
              </button>
              <Link
                href="/leads/discover"
                className="inline-flex items-center gap-2 rounded-lg bg-[var(--color-primary)] px-4 py-2 text-xs font-semibold text-white shadow-md shadow-[var(--color-primary)]/20 transition-all hover:bg-[var(--color-primary-hover)] hover:shadow-lg"
              >
                <Compass size={14} />
                <span>Start Discovery Sweep</span>
              </Link>
            </div>
          </div>
        </div>

        {/* 4 Prime Operational Action Launchers */}
        <section>
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-xs font-bold uppercase tracking-wider text-[var(--color-muted)]">
              Core Operations & Launchers
            </h2>
            <span className="text-xs text-[var(--color-muted)]">1-Click Fast Track</span>
          </div>

          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Link
              href="/leads/discover"
              className="group relative flex flex-col justify-between overflow-hidden rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4 transition-all hover:-translate-y-0.5 hover:border-[var(--color-primary)] hover:shadow-md"
            >
              <div>
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-emerald-500/10 text-emerald-500 ring-1 ring-emerald-500/20 group-hover:scale-105 transition-transform">
                  <Compass size={20} />
                </div>
                <h3 className="mt-3 text-sm font-semibold text-[var(--color-foreground)] group-hover:text-[var(--color-primary)]">
                  Discover Businesses
                </h3>
                <p className="mt-1 text-xs text-[var(--color-muted)]">
                  Execute automated web & map scraping sweeps across specified regions.
                </p>
              </div>
              <div className="mt-4 flex items-center gap-1 text-xs font-medium text-emerald-500">
                <span>Launch Sweep</span>
                <ArrowRight size={13} className="transition-transform group-hover:translate-x-1" />
              </div>
            </Link>

            <Link
              href="/leads/map"
              className="group relative flex flex-col justify-between overflow-hidden rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4 transition-all hover:-translate-y-0.5 hover:border-[var(--color-primary)] hover:shadow-md"
            >
              <div>
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-sky-500/10 text-sky-500 ring-1 ring-sky-500/20 group-hover:scale-105 transition-transform">
                  <MapPinned size={20} />
                </div>
                <h3 className="mt-3 text-sm font-semibold text-[var(--color-foreground)] group-hover:text-[var(--color-primary)]">
                  Geographic Map Explorer
                </h3>
                <p className="mt-1 text-xs text-[var(--color-muted)]">
                  Interactive density grid & spatial explorer for target market analysis.
                </p>
              </div>
              <div className="mt-4 flex items-center gap-1 text-xs font-medium text-sky-500">
                <span>Open Map</span>
                <ArrowRight size={13} className="transition-transform group-hover:translate-x-1" />
              </div>
            </Link>

            <Link
              href="/social"
              className="group relative flex flex-col justify-between overflow-hidden rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4 transition-all hover:-translate-y-0.5 hover:border-[var(--color-primary)] hover:shadow-md"
            >
              <div>
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-purple-500/10 text-purple-500 ring-1 ring-purple-500/20 group-hover:scale-105 transition-transform">
                  <Globe size={20} />
                </div>
                <h3 className="mt-3 text-sm font-semibold text-[var(--color-foreground)] group-hover:text-[var(--color-primary)]">
                  12-Platform Social Radar
                </h3>
                <p className="mt-1 text-xs text-[var(--color-muted)]">
                  Dorking & syndication listening across LinkedIn, X, Reddit, Instagram, etc.
                </p>
              </div>
              <div className="mt-4 flex items-center gap-1 text-xs font-medium text-purple-500">
                <span>Search Signals</span>
                <ArrowRight size={13} className="transition-transform group-hover:translate-x-1" />
              </div>
            </Link>

            <Link
              href="/automation/workflows"
              className="group relative flex flex-col justify-between overflow-hidden rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4 transition-all hover:-translate-y-0.5 hover:border-[var(--color-primary)] hover:shadow-md"
            >
              <div>
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-amber-500/10 text-amber-500 ring-1 ring-amber-500/20 group-hover:scale-105 transition-transform">
                  <Workflow size={20} />
                </div>
                <h3 className="mt-3 text-sm font-semibold text-[var(--color-foreground)] group-hover:text-[var(--color-primary)]">
                  Outreach Automations
                </h3>
                <p className="mt-1 text-xs text-[var(--color-muted)]">
                  Autonomous pipelines: lead qualification, draft generation, and approval sending.
                </p>
              </div>
              <div className="mt-4 flex items-center gap-1 text-xs font-medium text-amber-500">
                <span>Build Workflow</span>
                <ArrowRight size={13} className="transition-transform group-hover:translate-x-1" />
              </div>
            </Link>
          </div>
        </section>

        {/* Real Data Telemetry Grid */}
        <section>
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-xs font-bold uppercase tracking-wider text-[var(--color-muted)]">
              Intelligence Telemetry & Metrics
            </h2>
            <Link
              className="text-xs font-medium text-[var(--color-primary)] hover:underline flex items-center gap-1"
              href="/analytics"
            >
              <span>Full Analytics</span>
              <ArrowRight size={12} />
            </Link>
          </div>

          {summary.isPending && (
            <div className="rounded-xl border border-border bg-[var(--color-surface)] p-8 text-center text-xs text-[var(--color-muted)]">
              Reading live database rows…
            </div>
          )}

          {data && isEmptySurface(data) && (
            <EmptyState
              title="No intelligence stored yet"
              description="Your database is clean. Launch your first business discovery sweep or create a social research query to populate real-time analytics."
              action={
                <Link
                  href="/leads/discover"
                  className="rounded-lg bg-[var(--color-primary)] px-4 py-2 text-xs font-medium text-white hover:opacity-90"
                >
                  Start First Sweep
                </Link>
              }
            />
          )}

          {data && !isEmptySurface(data) && (
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <Card className="hover:border-[var(--color-primary)]/40 transition-colors">
                <div className="flex items-center justify-between">
                  <CardTitle>Businesses & Leads</CardTitle>
                  <Radar size={16} className="text-emerald-500" />
                </div>
                <CardValue>
                  <Link className="hover:text-[var(--color-primary)]" href="/leads">
                    {data.leads_total}
                  </Link>
                </CardValue>
                <CardFootnote>
                  {`${bucketCount(data.businesses_by_lifecycle, "active") ?? 0} active · `}
                  <Link href="/leads/crm" className="text-[var(--color-primary)] hover:underline">
                    View CRM Board →
                  </Link>
                </CardFootnote>
              </Card>

              <Card className="hover:border-[var(--color-primary)]/40 transition-colors">
                <div className="flex items-center justify-between">
                  <CardTitle>Discovery Jobs</CardTitle>
                  <Compass size={16} className="text-sky-500" />
                </div>
                <CardValue>
                  <Link className="hover:text-[var(--color-primary)]" href="/leads/discover">
                    {sumCounts(data.discovery_jobs_by_status)}
                  </Link>
                </CardValue>
                <CardFootnote>
                  {`${bucketCount(data.discovery_jobs_by_status, "completed") ?? 0} completed · `}
                  {`${bucketCount(data.discovery_jobs_by_status, "failed") ?? 0} failed`}
                </CardFootnote>
              </Card>

              <Card className="hover:border-[var(--color-primary)]/40 transition-colors">
                <div className="flex items-center justify-between">
                  <CardTitle>Social Signals</CardTitle>
                  <Globe size={16} className="text-purple-500" />
                </div>
                <CardValue>
                  <Link className="hover:text-[var(--color-primary)]" href="/intelligence">
                    {sumCounts(data.social_by_platform)}
                  </Link>
                </CardValue>
                <CardFootnote>
                  {`${bucketCount(data.social_by_classification, "Unclassified") ?? 0} unclassified · `}
                  <Link href="/social" className="text-[var(--color-primary)] hover:underline">
                    Explore →
                  </Link>
                </CardFootnote>
              </Card>

              <Card className="hover:border-[var(--color-primary)]/40 transition-colors">
                <div className="flex items-center justify-between">
                  <CardTitle>Tracked Startups</CardTitle>
                  <Sparkles size={16} className="text-amber-500" />
                </div>
                <CardValue>
                  <Link className="hover:text-[var(--color-primary)]" href="/startups">
                    {sumCounts(data.startups_by_funding_stage)}
                  </Link>
                </CardValue>
                <CardFootnote>
                  {data.startups_by_funding_stage[0]
                    ? `Top stage: ${data.startups_by_funding_stage[0].key}`
                    : "No stage recorded"}
                </CardFootnote>
              </Card>
            </div>
          )}
        </section>

        {/* Live Discovery Jobs & Execution Feed */}
        <section>
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-xs font-bold uppercase tracking-wider text-[var(--color-muted)]">
              Recent Discovery Jobs & Status
            </h2>
            <Link
              href="/leads/discover"
              className="text-xs font-medium text-[var(--color-primary)] hover:underline"
            >
              View All Jobs →
            </Link>
          </div>

          <div className="overflow-hidden rounded-xl border border-border bg-[var(--color-surface)]">
            {recentJobs.isPending && (
              <div className="p-6 text-center text-xs text-[var(--color-muted)]">
                Loading job history…
              </div>
            )}

            {recentJobs.data && recentJobs.data.length === 0 && (
              <div className="p-8 text-center">
                <p className="text-sm font-medium text-[var(--color-foreground)]">No discovery runs yet</p>
                <p className="mt-1 text-xs text-[var(--color-muted)]">
                  Launch a job to scan local businesses, extract contacts, and verify websites.
                </p>
                <Link
                  href="/leads/discover"
                  className="mt-3 inline-block rounded-lg bg-[var(--color-primary)] px-3 py-1.5 text-xs font-medium text-white hover:opacity-90"
                >
                  Launch First Job
                </Link>
              </div>
            )}

            {recentJobs.data && recentJobs.data.length > 0 && (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="border-b border-border bg-[var(--color-surface-elevated)]/60 text-[var(--color-muted)]">
                    <tr>
                      <th className="px-4 py-3 font-semibold uppercase tracking-wider">Job Type</th>
                      <th className="px-4 py-3 font-semibold uppercase tracking-wider">Status</th>
                      <th className="px-4 py-3 font-semibold uppercase tracking-wider">Processed</th>
                      <th className="px-4 py-3 font-semibold uppercase tracking-wider">Failed</th>
                      <th className="px-4 py-3 font-semibold uppercase tracking-wider">Created</th>
                      <th className="px-4 py-3 font-semibold uppercase tracking-wider text-right">Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {recentJobs.data.map((job) => (
                      <tr key={job.id} className="hover:bg-[var(--color-surface-elevated)]/40 transition-colors">
                        <td className="px-4 py-3 font-medium text-[var(--color-foreground)]">
                          <span className="font-mono">{job.job_type}</span>
                        </td>
                        <td className="px-4 py-3">
                          <span
                            className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-semibold ${
                              job.status === "completed"
                                ? "bg-emerald-500/10 text-emerald-500 border border-emerald-500/30"
                                : job.status === "failed"
                                  ? "bg-rose-500/10 text-rose-500 border border-rose-500/30"
                                  : "bg-blue-500/10 text-blue-500 border border-blue-500/30 animate-pulse"
                            }`}
                          >
                            <span className="h-1.5 w-1.5 rounded-full bg-current" />
                            <span className="capitalize">{job.status}</span>
                          </span>
                        </td>
                        <td className="px-4 py-3 text-[var(--color-foreground)]">
                          {job.processed_records}
                        </td>
                        <td className="px-4 py-3 text-[var(--color-muted)]">
                          {job.failed_records}
                        </td>
                        <td className="px-4 py-3 text-[var(--color-muted)]">
                          {new Date(job.created_at).toLocaleString(undefined, {
                            month: "short",
                            day: "numeric",
                            hour: "2-digit",
                            minute: "2-digit",
                          })}
                        </td>
                        <td className="px-4 py-3 text-right">
                          <Link
                            href="/leads/raw"
                            className="font-medium text-[var(--color-primary)] hover:underline"
                          >
                            View Leads →
                          </Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </section>

        {/* Feature Directory / MVP Navigation Grid */}
        <section>
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-xs font-bold uppercase tracking-wider text-[var(--color-muted)]">
              Feature Matrix & Workspace Shortcuts
            </h2>
            <span className="text-xs text-[var(--color-muted)]">Direct Access</span>
          </div>

          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {/* Leads Column */}
            <div className="rounded-xl border border-border bg-[var(--color-surface)] p-4 space-y-2.5">
              <div className="flex items-center gap-2 pb-2 border-b border-border/60">
                <Radar size={16} className="text-emerald-500" />
                <h3 className="text-xs font-bold uppercase tracking-wider text-[var(--color-foreground)]">
                  Leads & Local Market
                </h3>
              </div>
              <ul className="space-y-1.5 text-xs">
                <li>
                  <Link href="/leads/discover" className="flex items-center justify-between rounded-lg p-1.5 hover:bg-[var(--color-surface-elevated)] transition-colors">
                    <span className="font-medium">Discover Businesses</span>
                    <span className="text-[11px] text-[var(--color-muted)]">Sweeper</span>
                  </Link>
                </li>
                <li>
                  <Link href="/leads/map" className="flex items-center justify-between rounded-lg p-1.5 hover:bg-[var(--color-surface-elevated)] transition-colors">
                    <span className="font-medium">Map Explorer</span>
                    <span className="text-[11px] text-[var(--color-muted)]">Density Grid</span>
                  </Link>
                </li>
                <li>
                  <Link href="/leads/raw" className="flex items-center justify-between rounded-lg p-1.5 hover:bg-[var(--color-surface-elevated)] transition-colors">
                    <span className="font-medium">Raw Lead Ingestion</span>
                    <span className="text-[11px] text-[var(--color-muted)]">CSV Exports</span>
                  </Link>
                </li>
                <li>
                  <Link href="/leads/qualified" className="flex items-center justify-between rounded-lg p-1.5 hover:bg-[var(--color-surface-elevated)] transition-colors">
                    <span className="font-medium">Qualified Leads</span>
                    <span className="text-[11px] text-[var(--color-muted)]">Rule Scored</span>
                  </Link>
                </li>
                <li>
                  <Link href="/leads/crm" className="flex items-center justify-between rounded-lg p-1.5 hover:bg-[var(--color-surface-elevated)] transition-colors">
                    <span className="font-medium">CRM Pipeline</span>
                    <span className="text-[11px] text-[var(--color-muted)]">12 Stages</span>
                  </Link>
                </li>
              </ul>
            </div>

            {/* Social & Startups Column */}
            <div className="rounded-xl border border-border bg-[var(--color-surface)] p-4 space-y-2.5">
              <div className="flex items-center gap-2 pb-2 border-b border-border/60">
                <Globe size={16} className="text-purple-500" />
                <h3 className="text-xs font-bold uppercase tracking-wider text-[var(--color-foreground)]">
                  Social & Venture Radar
                </h3>
              </div>
              <ul className="space-y-1.5 text-xs">
                <li>
                  <Link href="/social" className="flex items-center justify-between rounded-lg p-1.5 hover:bg-[var(--color-surface-elevated)] transition-colors">
                    <span className="font-medium">Social Intelligence Hub</span>
                    <span className="text-[11px] text-[var(--color-muted)]">12 Platforms</span>
                  </Link>
                </li>
                <li>
                  <Link href="/intelligence/demand" className="flex items-center justify-between rounded-lg p-1.5 hover:bg-[var(--color-surface-elevated)] transition-colors">
                    <span className="font-medium">Demand Signals</span>
                    <span className="text-[11px] text-[var(--color-muted)]">Buyer Intent</span>
                  </Link>
                </li>
                <li>
                  <Link href="/intelligence/tracks" className="flex items-center justify-between rounded-lg p-1.5 hover:bg-[var(--color-surface-elevated)] transition-colors">
                    <span className="font-medium">Discovery Tracks</span>
                    <span className="text-[11px] text-[var(--color-muted)]">Automated</span>
                  </Link>
                </li>
                <li>
                  <Link href="/startups/discover" className="flex items-center justify-between rounded-lg p-1.5 hover:bg-[var(--color-surface-elevated)] transition-colors">
                    <span className="font-medium">Discover Startups</span>
                    <span className="text-[11px] text-[var(--color-muted)]">Venture</span>
                  </Link>
                </li>
                <li>
                  <Link href="/startups/watchlists" className="flex items-center justify-between rounded-lg p-1.5 hover:bg-[var(--color-surface-elevated)] transition-colors">
                    <span className="font-medium">Startup Watchlists</span>
                    <span className="text-[11px] text-[var(--color-muted)]">Buckets</span>
                  </Link>
                </li>
              </ul>
            </div>

            {/* Automation & Infrastructure Column */}
            <div className="rounded-xl border border-border bg-[var(--color-surface)] p-4 space-y-2.5">
              <div className="flex items-center gap-2 pb-2 border-b border-border/60">
                <Workflow size={16} className="text-amber-500" />
                <h3 className="text-xs font-bold uppercase tracking-wider text-[var(--color-foreground)]">
                  Automation & Operations
                </h3>
              </div>
              <ul className="space-y-1.5 text-xs">
                <li>
                  <Link href="/automation/workflows" className="flex items-center justify-between rounded-lg p-1.5 hover:bg-[var(--color-surface-elevated)] transition-colors">
                    <span className="font-medium">Workflow Builder</span>
                    <span className="text-[11px] text-[var(--color-muted)]">Pipelines</span>
                  </Link>
                </li>
                <li>
                  <Link href="/automation/scheduler" className="flex items-center justify-between rounded-lg p-1.5 hover:bg-[var(--color-surface-elevated)] transition-colors">
                    <span className="font-medium">Task Scheduler</span>
                    <span className="text-[11px] text-[var(--color-muted)]">Cron Sweeps</span>
                  </Link>
                </li>
                <li>
                  <Link href="/automation/approvals" className="flex items-center justify-between rounded-lg p-1.5 hover:bg-[var(--color-surface-elevated)] transition-colors">
                    <span className="font-medium">Approval Queue</span>
                    <span className="text-[11px] text-[var(--color-muted)]">Safeguard</span>
                  </Link>
                </li>
                <li>
                  <Link href="/email" className="flex items-center justify-between rounded-lg p-1.5 hover:bg-[var(--color-surface-elevated)] transition-colors">
                    <span className="font-medium">Email Outreach</span>
                    <span className="text-[11px] text-[var(--color-muted)]">Campaigns</span>
                  </Link>
                </li>
                <li>
                  <Link href="/sources" className="flex items-center justify-between rounded-lg p-1.5 hover:bg-[var(--color-surface-elevated)] transition-colors">
                    <span className="font-medium">Source Manager</span>
                    <span className="text-[11px] text-[var(--color-muted)]">Health Audit</span>
                  </Link>
                </li>
              </ul>
            </div>
          </div>
        </section>

        {/* System & Dependency Health Strip */}
        <section className="rounded-xl border border-border bg-[var(--color-surface)] p-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-3">
              <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-[var(--color-surface-elevated)] text-[var(--color-primary)]">
                <Server size={16} />
              </span>
              <div>
                <h3 className="text-xs font-semibold text-[var(--color-foreground)]">
                  Infrastructure Health & Execution Topology
                </h3>
                <p className="text-[11px] text-[var(--color-muted)]">
                  {status.info?.execution_model ?? "local_first"} execution · {components.length} components monitored
                </p>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-3">
              {components.map((c) => (
                <div
                  key={c.name}
                  className="flex items-center gap-2 rounded-lg border border-border/80 bg-[var(--color-surface-elevated)]/60 px-2.5 py-1 text-xs"
                >
                  <span
                    className={`h-2 w-2 rounded-full ${
                      c.ok ? "bg-emerald-500" : "bg-rose-500"
                    }`}
                  />
                  <span className="capitalize font-medium text-[var(--color-foreground)]">
                    {c.name}
                  </span>
                  <span className="text-[11px] text-[var(--color-muted)]">
                    {c.ok ? "Healthy" : c.detail ?? "Down"}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}
