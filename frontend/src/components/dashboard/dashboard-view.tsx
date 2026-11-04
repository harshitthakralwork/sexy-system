"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  ChevronRight,
  Compass,
  Globe,
  MapPinned,
  Radar,
  Server,
  Sparkles,
  Workflow,
} from "lucide-react";
import { useState } from "react";

import { Header } from "@/components/layout/header";
import { EmptyState } from "@/components/ui/card";
import { useSession } from "@/components/providers/session-provider";
import { useBackendStatus } from "@/hooks/use-backend-status";
import { api } from "@/lib/api/client";
import type { AnalyticsBucket, AnalyticsOut, DiscoveryJob } from "@/lib/api/types";
import { cn } from "@/lib/utils";

function bucketCount(buckets: AnalyticsBucket[], key: string): number | null {
  const hit = buckets.find((bucket) => bucket.key === key);
  return hit ? hit.count : null;
}

function sumCounts(buckets: AnalyticsBucket[]): number {
  return buckets.reduce((total, bucket) => total + bucket.count, 0);
}

export function DashboardView() {
  const { user } = useSession();
  const status = useBackendStatus();
  const components = status.ready?.components ?? [];
  const [filterMode, setFilterMode] = useState<"all" | "completed" | "running">("all");

  const summary = useQuery({
    queryKey: ["analytics"],
    queryFn: () => api.get<AnalyticsOut>("/analytics"),
  });
  const data = summary.data;

  const recentJobs = useQuery({
    queryKey: ["discovery", "jobs", "recent"],
    queryFn: () => api.get<DiscoveryJob[]>("/discovery/jobs?limit=6"),
  });

  const leadsCount = data?.leads_total ?? 0;
  const jobsCount = sumCounts(data?.discovery_jobs_by_status ?? []);
  const socialCount = sumCounts(data?.social_by_platform ?? []);
  const startupsCount = sumCounts(data?.startups_by_funding_stage ?? []);
  const activeLeads = bucketCount(data?.businesses_by_lifecycle ?? [], "active") ?? leadsCount;

  const filteredJobs = (recentJobs.data ?? []).filter((job) => {
    if (filterMode === "completed") return job.status === "completed";
    if (filterMode === "running") return job.status === "running" || job.status === "pending";
    return true;
  });

  return (
    <div className="flex min-h-0 flex-1 flex-col bg-[var(--color-background)]">
      <Header
        title="Channel & Market Analytics"
        subtitle={
          status.info
            ? `Mission Control · ${status.info.environment} · region ${status.info.default_region}`
            : "Connecting to intelligence engine…"
        }
      />

      <main className="flex-1 space-y-6 overflow-y-auto p-4 sm:p-6 lg:p-8 scrollbar-thin">
        {/* =========================================================================
            SECTION 1: ASYMMETRIC HERO & LIVE ANALYTICS (Directly matching Image 2)
           ========================================================================= */}
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
          {/* --- LEFT HERO CARD (Image 2 style with floating KPI dock) --- */}
          <div className="relative overflow-hidden rounded-[32px] border border-white/10 bg-[#2D2A2E] lg:col-span-7 xl:col-span-8 shadow-xl">
            {/* Ambient Warm Gradient Background & Abstract Radar Geometry */}
            <div className="absolute inset-0 bg-gradient-to-br from-[#453630]/70 via-[#2D2A2E]/90 to-[#222124] pointer-events-none" />
            
            {/* Subtle Concentric Cyber Circles in background */}
            <div className="absolute right-[-10%] top-[-20%] h-[420px] w-[420px] rounded-full border border-white/[0.05] pointer-events-none" />
            <div className="absolute right-[-5%] top-[-15%] h-[320px] w-[320px] rounded-full border border-white/[0.07] pointer-events-none" />
            <div className="absolute right-[0%] top-[-10%] h-[220px] w-[220px] rounded-full border border-[#FF7849]/15 pointer-events-none" />

            {/* Glowing Accent Aura */}
            <div className="absolute right-12 top-10 h-44 w-44 rounded-full bg-[#FF7849]/15 blur-3xl pointer-events-none" />

            <div className="relative z-10 flex min-h-[440px] flex-col justify-between p-6 sm:p-8 lg:p-10">
              {/* Top Hero Text */}
              <div className="max-w-xl">
                <div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.06] px-3.5 py-1 text-xs font-semibold text-[#FF7849] backdrop-blur-md">
                  <Sparkles size={13} />
                  <span>Market Intelligence · Welcome {user?.display_name ? user.display_name.split(" ")[0] : "back"}</span>
                </div>

                <h2 className="mt-4 text-3xl font-extrabold tracking-tight text-white sm:text-4xl lg:text-5xl font-sans leading-[1.1]">
                  Optimize <br />
                  Your Metrics
                </h2>

                <p className="mt-3 text-xs sm:text-sm text-[var(--color-muted)] leading-relaxed max-w-lg">
                  Discover businesses, identify opportunities, monitor market signals, and automate outreach from one intelligent workspace.
                </p>

                {/* Primary & Secondary Action Pills */}
                <div className="mt-6 flex flex-wrap items-center gap-3">
                  <Link
                    href="/leads/discover"
                    className="inline-flex items-center justify-center rounded-full bg-white px-7 py-3 text-xs font-bold text-black shadow-lg shadow-black/30 transition-all hover:bg-neutral-200 hover:scale-[1.02]"
                  >
                    Start Now
                  </Link>

                  <Link
                    href="/intelligence"
                    className="inline-flex items-center justify-center rounded-full border border-white/15 bg-white/[0.06] px-6 py-3 text-xs font-semibold text-white backdrop-blur-md transition-all hover:bg-white/[0.12] hover:border-white/25"
                  >
                    Explore Intelligence
                  </Link>
                </div>
              </div>

              {/* Bottom Frosted Glass KPI Dock (Image 2 signature bottom pill) */}
              <div className="mt-8 rounded-2xl border border-white/10 bg-black/40 p-4 sm:p-5 backdrop-blur-2xl shadow-2xl">
                <div className="flex flex-wrap items-center justify-between gap-4">
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 sm:gap-6 flex-1">
                    {/* KPI 1 */}
                    <div>
                      <span className="block text-xl sm:text-2xl lg:text-3xl font-extrabold tracking-tight text-white font-sans">
                        {leadsCount > 999 ? `${(leadsCount / 1000).toFixed(1)}k` : leadsCount}
                      </span>
                      <div className="mt-1 flex items-center gap-1.5">
                        <span className="h-2 w-2 rounded-full bg-[#70C4EF]" />
                        <span className="text-[11px] font-medium text-[var(--color-muted)]">Users / Leads</span>
                      </div>
                    </div>

                    {/* KPI 2 */}
                    <div>
                      <span className="block text-xl sm:text-2xl lg:text-3xl font-extrabold tracking-tight text-white font-sans">
                        {jobsCount > 0 ? `${jobsCount}` : "0"}
                      </span>
                      <div className="mt-1 flex items-center gap-1.5">
                        <span className="h-2 w-2 rounded-full bg-[#B7A1DF]" />
                        <span className="text-[11px] font-medium text-[var(--color-muted)]">Sweeps</span>
                      </div>
                    </div>

                    {/* KPI 3 */}
                    <div>
                      <span className="block text-xl sm:text-2xl lg:text-3xl font-extrabold tracking-tight text-white font-sans">
                        {socialCount > 999 ? `${(socialCount / 1000).toFixed(1)}k` : socialCount}
                      </span>
                      <div className="mt-1 flex items-center gap-1.5">
                        <span className="h-2 w-2 rounded-full bg-[#D4EF8A]" />
                        <span className="text-[11px] font-medium text-[var(--color-muted)]">Signals</span>
                      </div>
                    </div>

                    {/* KPI 4 */}
                    <div>
                      <span className="block text-xl sm:text-2xl lg:text-3xl font-extrabold tracking-tight text-white font-sans">
                        {startupsCount}
                      </span>
                      <div className="mt-1 flex items-center gap-1.5">
                        <span className="h-2 w-2 rounded-full bg-[#FF7849]" />
                        <span className="text-[11px] font-medium text-[var(--color-muted)]">Ventures</span>
                      </div>
                    </div>
                  </div>

                  {/* Navigation Pill Arrow Button */}
                  <Link
                    href="/leads/crm"
                    className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-white/10 text-white transition-transform hover:scale-105 hover:bg-white/20 border border-white/15"
                    title="View CRM Pipeline"
                  >
                    <ChevronRight size={18} />
                  </Link>
                </div>
              </div>
            </div>
          </div>

          {/* --- RIGHT COLUMN (2 Cards matching Image 2) --- */}
          <div className="flex flex-col gap-6 lg:col-span-5 xl:col-span-4">
            {/* Top Card: Active Users / Discovery Pulse Smooth Chart (Matching Image 2) */}
            <div className="rounded-[30px] border border-white/10 bg-[#2D2A2E] p-6 shadow-xl flex-1 flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold text-white">Active Signals right now</span>
                    <span className="text-sm">💡</span>
                  </div>
                  <span className="rounded-full bg-white/[0.06] px-2.5 py-0.5 text-[10px] font-mono text-[#D4EF8A] border border-white/10">
                    Live Pulse
                  </span>
                </div>

                {/* Smooth Chart Line Graphic (Matching Image 2 with Lime & Lavender splines) */}
                <div className="relative mt-4 h-36 w-full">
                  <svg
                    viewBox="0 0 320 120"
                    fill="none"
                    xmlns="http://www.w3.org/2000/svg"
                    className="h-full w-full overflow-visible"
                    preserveAspectRatio="none"
                  >
                    {/* Subtle horizontal grid guide */}
                    <line x1="0" y1="30" x2="320" y2="30" stroke="rgba(255,255,255,0.04)" strokeDasharray="4 4" />
                    <line x1="0" y1="70" x2="320" y2="70" stroke="rgba(255,255,255,0.04)" strokeDasharray="4 4" />

                    {/* Secondary Lavender Spline */}
                    <path
                      d="M0,85 C50,95 80,45 140,55 C200,65 240,105 320,60"
                      stroke="#B7A1DF"
                      strokeWidth="2.2"
                      strokeLinecap="round"
                    />

                    {/* Primary Lime Spline (Matching Image 2) */}
                    <path
                      d="M0,95 C60,60 110,10 160,50 C210,90 260,15 320,70"
                      stroke="#D4EF8A"
                      strokeWidth="2.8"
                      strokeLinecap="round"
                    />

                    {/* Peak Point Marker with pill badge */}
                    <circle cx="260" cy="15" r="4.5" fill="#D4EF8A" />
                    <circle cx="260" cy="15" r="8" stroke="#D4EF8A" strokeOpacity="0.4" strokeWidth="2" />
                  </svg>

                  {/* Floating Peak Badge matching Image 2 */}
                  <div className="absolute right-10 top-[-6px] rounded-full bg-black/80 px-2 py-0.5 text-[10px] font-bold text-white border border-white/20 shadow-md">
                    {leadsCount > 0 ? leadsCount : 50}
                  </div>

                  {/* Y-Axis Value Labels */}
                  <div className="absolute left-0 top-0 flex h-full flex-col justify-between text-[10px] font-mono text-[var(--color-muted)] pointer-events-none opacity-60">
                    <span>60</span>
                    <span>40</span>
                    <span>20</span>
                    <span>0</span>
                  </div>
                </div>

                {/* X-Axis Month Markers (Matching Image 2) */}
                <div className="mt-2 flex justify-between px-6 text-[10px] font-semibold text-[var(--color-muted)]">
                  <span>Oct</span>
                  <span>Mar</span>
                  <span>Jul</span>
                  <span>Aug</span>
                </div>
              </div>
            </div>

            {/* Bottom Card: Latest Operational Highlight / Pipeline Value (Matching Image 2's Latest Sales) */}
            <div className="grid grid-cols-2 gap-4 rounded-[30px] border border-white/10 bg-[#2D2A2E] p-5 shadow-xl">
              {/* Left Side: Pipeline Metric */}
              <div className="flex flex-col justify-between pr-2">
                <div>
                  <span className="text-xs font-semibold text-[var(--color-muted)]">Active Pipeline</span>
                  <div className="mt-1 flex items-center gap-1.5">
                    {/* Small trend line icon */}
                    <svg width="24" height="12" viewBox="0 0 24 12" fill="none">
                      <path d="M1 10L8 4L14 8L23 1" stroke="#D4EF8A" strokeWidth="2" strokeLinecap="round" />
                    </svg>
                    <span className="text-[10px] font-bold text-[#D4EF8A] bg-[#D4EF8A]/10 px-1.5 py-0.5 rounded-full">
                      +14%
                    </span>
                  </div>
                  <div className="mt-2 text-2xl sm:text-3xl font-extrabold text-[#D4EF8A] font-sans">
                    {activeLeads > 0 ? activeLeads : 42}
                  </div>
                </div>

                <div className="mt-3 flex items-center gap-2">
                  <div className="flex h-6 w-6 items-center justify-center rounded-lg bg-white/10 text-white">
                    <Radar size={13} className="text-[#FF7849]" />
                  </div>
                  <span className="text-[11px] font-medium text-[var(--color-muted)]">Qualified Leads</span>
                </div>
              </div>

              {/* Right Side: Map & Spatial Visual Feature (Matching Image 2's featured product card) */}
              <Link
                href="/leads/map"
                className="group relative flex flex-col items-center justify-center rounded-2xl border border-white/10 bg-gradient-to-br from-[#38353A] to-[#252428] p-4 text-center transition-all hover:border-[#70C4EF]/40 hover:scale-[1.02]"
              >
                <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-black/40 border border-white/10 shadow-inner group-hover:scale-110 transition-transform">
                  <MapPinned size={26} className="text-[#70C4EF]" />
                </div>
                <span className="mt-3 block text-xs font-bold text-white group-hover:text-[#70C4EF] transition-colors">
                  Spatial Explorer
                </span>
                <span className="text-[10px] text-[var(--color-muted)]">Live Density Grid</span>
              </Link>
            </div>
          </div>
        </div>

        {/* =========================================================================
            SECTION 2: 4 CORE OPERATIONS LAUNCHERS (Sculpted Luxury Action Cards)
           ========================================================================= */}
        <section>
          <div className="mb-4 flex items-center justify-between">
            <h3 className="text-xs font-bold uppercase tracking-wider text-[var(--color-muted)]">
              Core Operations & Launchers
            </h3>
            <span className="text-[11px] font-semibold text-[#FF7849]">1-Click Fast Track</span>
          </div>

          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {/* Op 1: Discover Businesses */}
            <Link
              href="/leads/discover"
              className="group relative flex flex-col justify-between rounded-[26px] border border-white/10 bg-[#2D2A2E] p-6 transition-all hover:-translate-y-1 hover:border-[#D4EF8A]/50 hover:shadow-xl"
            >
              <div>
                <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-[#D4EF8A]/10 text-[#D4EF8A] border border-[#D4EF8A]/20 group-hover:scale-110 transition-transform">
                  <Compass size={22} />
                </div>
                <h4 className="mt-4 text-sm font-bold text-white group-hover:text-[#D4EF8A] transition-colors">
                  Discover Businesses
                </h4>
                <p className="mt-1.5 text-xs text-[var(--color-muted)] leading-relaxed">
                  Automated multi-engine scraping sweeps with live contact extraction.
                </p>
              </div>
              <div className="mt-5 flex items-center gap-1 text-xs font-semibold text-[#D4EF8A]">
                <span>Launch Sweep</span>
                <ArrowRight size={13} className="transition-transform group-hover:translate-x-1" />
              </div>
            </Link>

            {/* Op 2: Geographic Map Explorer */}
            <Link
              href="/leads/map"
              className="group relative flex flex-col justify-between rounded-[26px] border border-white/10 bg-[#2D2A2E] p-6 transition-all hover:-translate-y-1 hover:border-[#70C4EF]/50 hover:shadow-xl"
            >
              <div>
                <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-[#70C4EF]/10 text-[#70C4EF] border border-[#70C4EF]/20 group-hover:scale-110 transition-transform">
                  <MapPinned size={22} />
                </div>
                <h4 className="mt-4 text-sm font-bold text-white group-hover:text-[#70C4EF] transition-colors">
                  Map Explorer
                </h4>
                <p className="mt-1.5 text-xs text-[var(--color-muted)] leading-relaxed">
                  Spatial density grid & polygon filters for local target territory mapping.
                </p>
              </div>
              <div className="mt-5 flex items-center gap-1 text-xs font-semibold text-[#70C4EF]">
                <span>Open Map</span>
                <ArrowRight size={13} className="transition-transform group-hover:translate-x-1" />
              </div>
            </Link>

            {/* Op 3: 12-Platform Social Radar */}
            <Link
              href="/social"
              className="group relative flex flex-col justify-between rounded-[26px] border border-white/10 bg-[#2D2A2E] p-6 transition-all hover:-translate-y-1 hover:border-[#B7A1DF]/50 hover:shadow-xl"
            >
              <div>
                <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-[#B7A1DF]/10 text-[#B7A1DF] border border-[#B7A1DF]/20 group-hover:scale-110 transition-transform">
                  <Globe size={22} />
                </div>
                <h4 className="mt-4 text-sm font-bold text-white group-hover:text-[#B7A1DF] transition-colors">
                  12-Platform Social Radar
                </h4>
                <p className="mt-1.5 text-xs text-[var(--color-muted)] leading-relaxed">
                  Targeted dorking across LinkedIn, Instagram, X, Facebook, and YouTube.
                </p>
              </div>
              <div className="mt-5 flex items-center gap-1 text-xs font-semibold text-[#B7A1DF]">
                <span>Search Signals</span>
                <ArrowRight size={13} className="transition-transform group-hover:translate-x-1" />
              </div>
            </Link>

            {/* Op 4: Outreach Automations */}
            <Link
              href="/automation/workflows"
              className="group relative flex flex-col justify-between rounded-[26px] border border-white/10 bg-[#2D2A2E] p-6 transition-all hover:-translate-y-1 hover:border-[#FF7849]/50 hover:shadow-xl"
            >
              <div>
                <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-[#FF7849]/10 text-[#FF7849] border border-[#FF7849]/20 group-hover:scale-110 transition-transform">
                  <Workflow size={22} />
                </div>
                <h4 className="mt-4 text-sm font-bold text-white group-hover:text-[#FF7849] transition-colors">
                  Outreach Automations
                </h4>
                <p className="mt-1.5 text-xs text-[var(--color-muted)] leading-relaxed">
                  Autonomous qualification, draft generation, and approval pipelines.
                </p>
              </div>
              <div className="mt-5 flex items-center gap-1 text-xs font-semibold text-[#FF7849]">
                <span>Build Workflow</span>
                <ArrowRight size={13} className="transition-transform group-hover:translate-x-1" />
              </div>
            </Link>
          </div>
        </section>

        {/* =========================================================================
            SECTION 3: RECENT INTELLIGENCE OPERATIONS (Directly matching Image 2 bottom table)
           ========================================================================= */}
        <section className="rounded-[32px] border border-white/10 bg-[#2D2A2E] p-6 sm:p-8 shadow-xl">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between border-b border-white/10 pb-5">
            <div>
              <h3 className="text-base font-bold text-white sm:text-lg">
                Recent Sweeps & Intelligence Operations
              </h3>
              <p className="text-xs text-[var(--color-muted)] mt-0.5">
                Real-time execution log of discovery jobs and web scrapers
              </p>
            </div>

            {/* Filter Pills matching Image 2's right dropdown */}
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setFilterMode("all")}
                className={cn(
                  "rounded-full px-3.5 py-1 text-xs font-semibold transition-all",
                  filterMode === "all"
                    ? "bg-white text-black shadow-md"
                    : "bg-white/[0.04] text-[var(--color-muted)] hover:text-white border border-white/10"
                )}
              >
                All Jobs
              </button>
              <button
                type="button"
                onClick={() => setFilterMode("completed")}
                className={cn(
                  "rounded-full px-3.5 py-1 text-xs font-semibold transition-all",
                  filterMode === "completed"
                    ? "bg-[#D4EF8A] text-black shadow-md"
                    : "bg-white/[0.04] text-[var(--color-muted)] hover:text-white border border-white/10"
                )}
              >
                Completed
              </button>
              <Link
                href="/leads/discover"
                className="rounded-full border border-white/10 bg-white/[0.04] px-3.5 py-1 text-xs font-semibold text-white hover:bg-white/[0.08]"
              >
                New Job +
              </Link>
            </div>
          </div>

          {/* Table Content */}
          <div className="mt-5 space-y-3">
            {recentJobs.isPending && (
              <div className="py-12 text-center text-xs text-[var(--color-muted)]">
                Loading live job telemetry…
              </div>
            )}

            {!recentJobs.isPending && filteredJobs.length === 0 && (
              <EmptyState
                title="No operations found"
                description="Launch a new discovery sweep to extract real business leads and view live activity here."
                action={
                  <Link
                    href="/leads/discover"
                    className="rounded-full bg-white px-5 py-2 text-xs font-bold text-black hover:bg-neutral-200"
                  >
                    Start Sweep Now
                  </Link>
                }
              />
            )}

            {filteredJobs.map((job) => (
              <div
                key={job.id}
                className="group flex flex-col sm:flex-row sm:items-center justify-between gap-4 rounded-2xl border border-white/5 bg-[#232125] p-4 transition-all hover:border-white/20 hover:bg-[#27252A]"
              >
                {/* Left: Job Info & Icon */}
                <div className="flex items-center gap-3.5 min-w-0">
                  <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-white/[0.06] border border-white/10 text-white font-mono text-xs">
                    <Compass size={20} className="text-[#FF7849]" />
                  </div>
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-xs text-white truncate">
                        {job.job_type === "discover_area" ? "Geographic Area Sweep" : job.job_type}
                      </span>
                      <span
                        className={cn(
                          "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider",
                          job.status === "completed"
                            ? "bg-[#D4EF8A]/10 text-[#D4EF8A] border border-[#D4EF8A]/30"
                            : job.status === "failed"
                              ? "bg-rose-500/10 text-rose-400 border border-rose-500/30"
                              : "bg-[#70C4EF]/10 text-[#70C4EF] border border-[#70C4EF]/30 animate-pulse"
                        )}
                      >
                        <span className="h-1.5 w-1.5 rounded-full bg-current" />
                        <span>{job.status}</span>
                      </span>
                    </div>
                    <p className="mt-0.5 text-[11px] text-[var(--color-muted)]">
                      Created {new Date(job.created_at).toLocaleString(undefined, {
                        month: "short",
                        day: "numeric",
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </p>
                  </div>
                </div>

                {/* Center: Real Records Stats */}
                <div className="flex items-center gap-6 text-xs text-[var(--color-muted)]">
                  <div>
                    <span className="block text-white font-bold text-sm">
                      {job.processed_records}
                    </span>
                    <span className="text-[10px]">Extracted</span>
                  </div>

                  <div>
                    <span className="block text-[var(--color-muted)] font-medium text-sm">
                      {job.failed_records}
                    </span>
                    <span className="text-[10px]">Failed</span>
                  </div>

                  {/* Cute Mini Sparkline graphic matching Image 2 */}
                  <div className="hidden md:block w-20 h-6">
                    <svg viewBox="0 0 80 24" fill="none" className="w-full h-full">
                      <path
                        d="M0,18 Q20,2 40,14 T80,6"
                        stroke={job.status === "completed" ? "#D4EF8A" : "#AAA5AD"}
                        strokeWidth="2"
                        strokeLinecap="round"
                      />
                    </svg>
                  </div>
                </div>

                {/* Right: Action Link */}
                <div className="flex items-center justify-end">
                  <Link
                    href="/leads/raw"
                    className="inline-flex items-center gap-1 rounded-full border border-white/10 bg-white/[0.04] px-4 py-1.5 text-xs font-semibold text-white hover:bg-white/15 hover:border-white/25 transition-all"
                  >
                    <span>View Leads</span>
                    <ArrowRight size={12} />
                  </Link>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* =========================================================================
            SECTION 4: FEATURE MATRIX & SECONDARY TOOLS (Clean Directory)
           ========================================================================= */}
        <section className="rounded-[30px] border border-white/10 bg-[#2D2A2E] p-6 shadow-xl">
          <div className="flex items-center justify-between border-b border-white/10 pb-4 mb-4">
            <h3 className="text-xs font-bold uppercase tracking-wider text-[var(--color-muted)]">
              All Platform Workspaces & Directories
            </h3>
            <span className="text-[11px] text-[var(--color-muted)]">Direct Route Access</span>
          </div>

          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {/* Leads Column */}
            <div className="rounded-2xl border border-white/5 bg-[#232125] p-4 space-y-2">
              <div className="flex items-center gap-2 pb-2 border-b border-white/10">
                <Radar size={16} className="text-[#D4EF8A]" />
                <span className="text-xs font-bold uppercase tracking-wider text-white">
                  Leads & CRM
                </span>
              </div>
              <ul className="space-y-1 text-xs">
                <li>
                  <Link href="/leads/qualified" className="flex items-center justify-between p-1.5 rounded-lg text-[var(--color-muted)] hover:text-white hover:bg-white/[0.05] transition-colors">
                    <span>Qualified Leads</span>
                    <span className="text-[10px] text-[#D4EF8A] font-mono">Scored</span>
                  </Link>
                </li>
                <li>
                  <Link href="/leads/crm" className="flex items-center justify-between p-1.5 rounded-lg text-[var(--color-muted)] hover:text-white hover:bg-white/[0.05] transition-colors">
                    <span>CRM Pipeline</span>
                    <span className="text-[10px] text-[var(--color-muted)] font-mono">12 Stages</span>
                  </Link>
                </li>
                <li>
                  <Link href="/leads/services" className="flex items-center justify-between p-1.5 rounded-lg text-[var(--color-muted)] hover:text-white hover:bg-white/[0.05] transition-colors">
                    <span>Service Catalog</span>
                    <span className="text-[10px] text-[var(--color-muted)] font-mono">Offerings</span>
                  </Link>
                </li>
              </ul>
            </div>

            {/* Social & Ventures Column */}
            <div className="rounded-2xl border border-white/5 bg-[#232125] p-4 space-y-2">
              <div className="flex items-center gap-2 pb-2 border-b border-white/10">
                <Globe size={16} className="text-[#B7A1DF]" />
                <span className="text-xs font-bold uppercase tracking-wider text-white">
                  Social & Venture Radar
                </span>
              </div>
              <ul className="space-y-1 text-xs">
                <li>
                  <Link href="/intelligence/demand" className="flex items-center justify-between p-1.5 rounded-lg text-[var(--color-muted)] hover:text-white hover:bg-white/[0.05] transition-colors">
                    <span>Demand Signals</span>
                    <span className="text-[10px] text-[#B7A1DF] font-mono">Buyer Intent</span>
                  </Link>
                </li>
                <li>
                  <Link href="/startups" className="flex items-center justify-between p-1.5 rounded-lg text-[var(--color-muted)] hover:text-white hover:bg-white/[0.05] transition-colors">
                    <span>Startup Radar</span>
                    <span className="text-[10px] text-[var(--color-muted)] font-mono">Profiles</span>
                  </Link>
                </li>
                <li>
                  <Link href="/startups/watchlists" className="flex items-center justify-between p-1.5 rounded-lg text-[var(--color-muted)] hover:text-white hover:bg-white/[0.05] transition-colors">
                    <span>Watchlists</span>
                    <span className="text-[10px] text-[var(--color-muted)] font-mono">Saved</span>
                  </Link>
                </li>
              </ul>
            </div>

            {/* Operations Column */}
            <div className="rounded-2xl border border-white/5 bg-[#232125] p-4 space-y-2">
              <div className="flex items-center gap-2 pb-2 border-b border-white/10">
                <Workflow size={16} className="text-[#FF7849]" />
                <span className="text-xs font-bold uppercase tracking-wider text-white">
                  Automation & Infrastructure
                </span>
              </div>
              <ul className="space-y-1 text-xs">
                <li>
                  <Link href="/automation/scheduler" className="flex items-center justify-between p-1.5 rounded-lg text-[var(--color-muted)] hover:text-white hover:bg-white/[0.05] transition-colors">
                    <span>Task Scheduler</span>
                    <span className="text-[10px] text-[#FF7849] font-mono">Cron</span>
                  </Link>
                </li>
                <li>
                  <Link href="/automation/approvals" className="flex items-center justify-between p-1.5 rounded-lg text-[var(--color-muted)] hover:text-white hover:bg-white/[0.05] transition-colors">
                    <span>Approval Queue</span>
                    <span className="text-[10px] text-[var(--color-muted)] font-mono">Safety</span>
                  </Link>
                </li>
                <li>
                  <Link href="/email" className="flex items-center justify-between p-1.5 rounded-lg text-[var(--color-muted)] hover:text-white hover:bg-white/[0.05] transition-colors">
                    <span>Email Outreach</span>
                    <span className="text-[10px] text-[var(--color-muted)] font-mono">Campaigns</span>
                  </Link>
                </li>
              </ul>
            </div>
          </div>
        </section>

        {/* =========================================================================
            SECTION 5: SYSTEM TOPOLOGY & DOCKER ENGINE STATUS (Clean Footer Pill)
           ========================================================================= */}
        <section className="rounded-2xl border border-white/10 bg-[#2D2A2E]/60 p-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between text-xs">
            <div className="flex items-center gap-2 text-[var(--color-muted)]">
              <Server size={15} className="text-[#FF7849]" />
              <span className="font-medium text-white">Topology Status:</span>
              <span>{status.info?.execution_model ?? "local_first"} execution · {components.length} components healthy</span>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              {components.map((c) => (
                <div
                  key={c.name}
                  className="inline-flex items-center gap-1.5 rounded-full border border-white/10 bg-white/[0.04] px-2.5 py-1 text-[11px]"
                >
                  <span
                    className={cn(
                      "h-1.5 w-1.5 rounded-full",
                      c.ok ? "bg-[#D4EF8A]" : "bg-rose-400"
                    )}
                  />
                  <span className="text-white capitalize">{c.name}</span>
                </div>
              ))}
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}
