"use client";

import { useQuery } from "@tanstack/react-query";
import {
  Award,
  Building,
  Building2,
  CheckCircle2,
  Crosshair,
  Database,
  Download,
  ExternalLink,
  HelpCircle,
  Layers,
  Mail,
  MapPin,
  MoreHorizontal,
  Phone,
  Plus,
  RefreshCw,
  Search,
  Server,
  Sparkles,
  TrendingUp,
  Users,
  Utensils,
  XCircle,
  AlertCircle,
  Radio,
  ArrowRight,
} from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { useMemo, useState } from "react";

import { Header } from "@/components/layout/header";
import { AppFooter } from "@/components/layout/app-footer";
import { useSession } from "@/components/providers/session-provider";
import { api } from "@/lib/api/client";
import type { AnalyticsOut, Business, BusinessList, ReadyResponse } from "@/lib/api/types";
import { cn } from "@/lib/utils";

export function DashboardView() {
  const { user } = useSession();

  // Filters state
  const [marketFilter, setMarketFilter] = useState("all");
  const [businessTypeFilter, setBusinessTypeFilter] = useState("all");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  // ── 1. Live Backend Queries ──────────────────────────────────────────────
  const summary = useQuery({
    queryKey: ["analytics"],
    queryFn: () => api.get<AnalyticsOut>("/analytics"),
  });

  const businessesQuery = useQuery({
    queryKey: ["dashboard-businesses"],
    queryFn: () => api.get<BusinessList>("/businesses?limit=25"),
  });

  const healthQuery = useQuery({
    queryKey: ["health-ready"],
    queryFn: () => api.get<ReadyResponse>("/health/ready"),
    refetchInterval: 30000,
  });

  const rawItems = businessesQuery.data?.items ?? [];
  const leadsTotal = summary.data?.leads_total ?? businessesQuery.data?.total ?? 0;

  // ── 2. Dynamic Metric Calculations ───────────────────────────────────────
  const crmStages = summary.data?.crm_by_stage ?? [];
  const totalProspects = useMemo(() => {
    return crmStages.reduce((acc, s) => acc + s.count, 0);
  }, [crmStages]);

  const qualifiedLeads = useMemo(() => {
    const qualifiedStage = crmStages.find((s) =>
      s.key.toLowerCase().includes("qualif")
    )?.count;
    if (qualifiedStage !== undefined) return qualifiedStage;
    return (
      summary.data?.opportunities_by_status?.reduce((acc, o) => acc + o.count, 0) ?? 0
    );
  }, [crmStages, summary.data?.opportunities_by_status]);

  // ── 3. Dynamic Discovery Intelligence ────────────────────────────────────
  // Top Markets from real discovered businesses
  const topMarkets = useMemo(() => {
    const counts: Record<string, number> = {};
    rawItems.forEach((b) => {
      const city = b.city?.trim() || "Unassigned";
      counts[city] = (counts[city] || 0) + 1;
    });
    const total = rawItems.length || 1;
    return Object.entries(counts)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 4)
      .map(([market, count], idx) => ({
        rank: idx + 1,
        market,
        count,
        percent: Math.round((count / total) * 100),
      }));
  }, [rawItems]);

  // Lifecycle breakdown from backend analytics
  const lifecycleBreakdown = useMemo(() => {
    const list = summary.data?.businesses_by_lifecycle ?? [];
    const maxCount = Math.max(...list.map((l) => l.count), 1);
    const colors = ["bg-blue-600", "bg-blue-500", "bg-sky-500", "bg-cyan-500"];
    return list.slice(0, 4).map((item, idx) => ({
      name: item.key.charAt(0).toUpperCase() + item.key.slice(1),
      count: item.count,
      score: Math.min(100, Math.round((item.count / maxCount) * 100)),
      color: colors[idx % colors.length],
    }));
  }, [summary.data?.businesses_by_lifecycle]);

  // Top categories from real discovered businesses
  const topCategories = useMemo(() => {
    const counts: Record<string, number> = {};
    rawItems.forEach((b) => {
      const cat = b.primary_category?.trim() || "General Business";
      counts[cat] = (counts[cat] || 0) + 1;
    });
    const total = rawItems.length || 1;
    return Object.entries(counts)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 4)
      .map(([label, count]) => ({
        label,
        count,
        percent: `${Math.round((count / total) * 100)}%`,
      }));
  }, [rawItems]);

  // Donut chart calculation from CRM stages or lifecycle
  const donutSegments = useMemo(() => {
    const items =
      crmStages.length > 0
        ? crmStages
        : summary.data?.businesses_by_lifecycle ?? [];
    const sum = items.reduce((acc, i) => acc + i.count, 0);
    if (sum === 0) return [];

    let currentOffset = 0;
    const colors = ["#2563eb", "#38bdf8", "#8b5cf6", "#10b981"];
    return items.slice(0, 3).map((item, idx) => {
      const share = Math.round((item.count / sum) * 100);
      const seg = {
        label: item.key.charAt(0).toUpperCase() + item.key.slice(1),
        count: item.count,
        percent: share,
        strokeDasharray: `${share}, 100`,
        strokeDashoffset: -currentOffset,
        color: colors[idx % colors.length],
      };
      currentOffset += share;
      return seg;
    });
  }, [crmStages, summary.data?.businesses_by_lifecycle]);

  // ── 4. Dynamic Discovery Jobs / Source Activity ──────────────────────────
  const jobsByStatus = summary.data?.discovery_jobs_by_status ?? [];
  const totalJobs = useMemo(
    () => jobsByStatus.reduce((acc, j) => acc + j.count, 0),
    [jobsByStatus]
  );
  const completedJobs =
    jobsByStatus.find((j) => j.key === "completed")?.count ?? 0;
  const runningJobs = jobsByStatus.find((j) => j.key === "running")?.count ?? 0;
  const failedJobs = jobsByStatus.find((j) => j.key === "failed")?.count ?? 0;
  const successRate =
    totalJobs > 0 ? Math.round((completedJobs / totalJobs) * 100) : 0;

  // ── 5. Discovered Businesses Filtering ───────────────────────────────────
  const uniqueCities = useMemo(() => {
    const set = new Set<string>();
    rawItems.forEach((b) => {
      if (b.city) set.add(b.city);
    });
    return Array.from(set).sort();
  }, [rawItems]);

  const uniqueCategories = useMemo(() => {
    const set = new Set<string>();
    rawItems.forEach((b) => {
      if (b.primary_category) set.add(b.primary_category);
    });
    return Array.from(set).sort();
  }, [rawItems]);

  const filteredBusinesses = useMemo(() => {
    return rawItems.filter((b) => {
      if (marketFilter !== "all" && b.city !== marketFilter) return false;
      if (
        businessTypeFilter !== "all" &&
        b.primary_category !== businessTypeFilter
      )
        return false;
      return true;
    });
  }, [rawItems, marketFilter, businessTypeFilter]);

  // Main page preview limit: only 5 items as requested
  const displayedBusinesses = useMemo(() => {
    return filteredBusinesses.slice(0, 5);
  }, [filteredBusinesses]);

  const toggleSelectAll = () => {
    if (selectedIds.size === displayedBusinesses.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(displayedBusinesses.map((r) => r.id)));
    }
  };

  const toggleSelect = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return (
    <div className="astra-dashboard flex min-h-0 flex-1 flex-col text-[var(--color-foreground)]">
      <Header
        title="Dashboard"
        subtitle="Local-business discovery & live pipeline intelligence."
      />

      <main className="flex-1 overflow-y-auto px-2 py-3 sm:px-3 sm:py-4 space-y-4">
        <div className="mx-auto max-w-none space-y-4">

          {/* ── Top Metric Cards (3 KPI Cards + 1 Primary CTA) ── */}
          <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-[1fr_1fr_1fr_1.28fr]">
            {/* Card 1: Discovered businesses */}
            <div className="flex min-h-[132px] items-center justify-between rounded-xl bg-[var(--color-surface)] border border-[var(--color-border)] p-5 shadow-sm">
              <div className="space-y-1">
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[var(--color-surface-elevated)] border border-[var(--color-border)] text-blue-500">
                    <Building size={19} />
                  </div>
                  <div>
                    <span className="block text-xs font-medium text-[var(--color-muted)]">
                      Discovered businesses
                    </span>
                    <p className="text-2xl font-bold tracking-tight text-[var(--color-foreground)] font-sans">
                      {businessesQuery.isLoading ? (
                        <span className="inline-block h-7 w-20 animate-pulse rounded bg-[var(--color-surface-elevated)]" />
                      ) : (
                        leadsTotal.toLocaleString()
                      )}
                    </p>
                  </div>
                </div>
                <p className="text-[11px] font-medium text-[var(--color-muted)] pl-1 pt-1">
                  Total indexed records in workspace
                </p>
              </div>

              {/* Status Indicator */}
              <div className="flex flex-col items-end justify-center">
                <span className="flex h-2.5 w-2.5 relative">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-40" />
                  <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-blue-500" />
                </span>
                <span className="text-[10px] text-[var(--color-muted)] mt-1 font-mono">Live</span>
              </div>
            </div>

            {/* Card 2: Active prospects */}
            <div className="flex min-h-[132px] items-center justify-between rounded-xl bg-[var(--color-surface)] border border-[var(--color-border)] p-5 shadow-sm">
              <div className="space-y-1">
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[var(--color-surface-elevated)] border border-[var(--color-border)] text-sky-500">
                    <Users size={19} />
                  </div>
                  <div>
                    <span className="block text-xs font-medium text-[var(--color-muted)]">
                      Active prospects
                    </span>
                    <p className="text-2xl font-bold tracking-tight text-[var(--color-foreground)] font-sans">
                      {summary.isLoading ? (
                        <span className="inline-block h-7 w-16 animate-pulse rounded bg-[var(--color-surface-elevated)]" />
                      ) : (
                        totalProspects.toLocaleString()
                      )}
                    </p>
                  </div>
                </div>
                <p className="text-[11px] font-medium text-[var(--color-muted)] pl-1 pt-1">
                  Tracked across pipeline stages
                </p>
              </div>

              <div className="flex flex-col items-end justify-center">
                <span className="h-2.5 w-2.5 rounded-full bg-sky-500" />
                <span className="text-[10px] text-[var(--color-muted)] mt-1 font-mono">Pipeline</span>
              </div>
            </div>

            {/* Card 3: Qualified leads */}
            <div className="flex min-h-[132px] items-center justify-between rounded-xl bg-[var(--color-surface)] border border-[var(--color-border)] p-5 shadow-sm">
              <div className="space-y-1">
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[var(--color-surface-elevated)] border border-[var(--color-border)] text-emerald-500">
                    <Award size={19} />
                  </div>
                  <div>
                    <span className="block text-xs font-medium text-[var(--color-muted)]">
                      Qualified leads
                    </span>
                    <p className="text-2xl font-bold tracking-tight text-[var(--color-foreground)] font-sans">
                      {summary.isLoading ? (
                        <span className="inline-block h-7 w-14 animate-pulse rounded bg-[var(--color-surface-elevated)]" />
                      ) : (
                        qualifiedLeads.toLocaleString()
                      )}
                    </p>
                  </div>
                </div>
                <p className="text-[11px] font-medium text-[var(--color-muted)] pl-1 pt-1">
                  High-intent conversion opportunities
                </p>
              </div>

              <div className="flex flex-col items-end justify-center">
                <span className="h-2.5 w-2.5 rounded-full bg-emerald-500" />
                <span className="text-[10px] text-[var(--color-muted)] mt-1 font-mono">Verified</span>
              </div>
            </div>

            {/* Compact source health summary */}
            <div className="min-h-[132px] rounded-xl bg-[var(--color-surface)] border border-[var(--color-border)] p-4 shadow-sm">
              <div className="mb-3 flex items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <Layers size={16} className="text-blue-500" />
                  <span className="text-xs font-bold text-[var(--color-foreground)]">Source health</span>
                </div>
                <span className="text-[10px] text-emerald-500">{healthQuery.data?.status === "ok" ? "Operational" : "Checking"}</span>
              </div>
              <div className="grid grid-cols-2 gap-2 text-[10px]">
                {(healthQuery.data?.components ?? [
                  { name: "database", ok: true },
                  { name: "redis", ok: true },
                  { name: "worker", ok: true },
                  { name: "searxng", ok: true },
                ]).slice(0, 4).map((comp) => (
                  <div key={comp.name} className="flex min-w-0 items-center justify-between gap-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-elevated)]/60 px-2 py-1.5">
                    <span className="flex min-w-0 items-center gap-1.5 text-[var(--color-muted)]">
                      <span className={cn("h-1.5 w-1.5 shrink-0 rounded-full", comp.ok ? "bg-emerald-500" : "bg-amber-500")} />
                      <span className="truncate">{comp.name === "database" ? "PostgreSQL" : comp.name === "searxng" ? "SearXNG" : comp.name}</span>
                    </span>
                    <span className={cn("shrink-0 text-[9px] font-semibold", comp.ok ? "text-emerald-500" : "text-amber-500")}>{comp.ok ? "Ready" : "Check"}</span>
                  </div>
                ))}
              </div>
            </div>
          </section>

          {/* ── Middle Section: Discovery Intelligence (Left) + Map (Right) ── */}
          <section className="grid gap-5 xl:grid-cols-[minmax(0,1.45fr)_minmax(500px,1.55fr)]">

            {/* Left: Discovery Intelligence Card */}
            <div className="min-h-[390px] rounded-xl bg-[var(--color-surface)] border border-[var(--color-border)] p-4 sm:p-5 space-y-4">
              {/* Header */}
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between border-b border-[var(--color-border)] pb-4">
                <div className="flex items-center gap-3">
                  <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-blue-500/10 text-blue-500 border border-blue-500/20">
                    <Crosshair size={18} />
                  </div>
                  <div>
                    <h3 className="text-base font-bold text-[var(--color-foreground)] tracking-tight">
                      Discovery Intelligence
                    </h3>
                    <p className="text-xs text-[var(--color-muted)]">
                      Market distribution, lifecycle stages, and pipeline qualification.
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-2 text-xs text-[var(--color-muted)]">
                  <Radio size={14} className="text-emerald-500 animate-pulse" />
                  <span>Real-time aggregations</span>
                </div>
              </div>

              {/* 4 Analytics Columns Grid */}
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">

                {/* 1. Market Opportunity */}
                <div className="space-y-3">
                  <h4 className="text-xs font-semibold text-[var(--color-muted)]">
                    Top Markets <span className="text-[var(--color-muted-dim)] font-normal">(Discovered)</span>
                  </h4>
                  {topMarkets.length === 0 ? (
                    <div className="rounded-lg bg-[var(--color-surface-elevated)]/50 border border-[var(--color-border)] p-4 text-center">
                      <p className="text-xs text-[var(--color-muted)]">No market locations discovered yet.</p>
                    </div>
                  ) : (
                    <div className="space-y-2.5 text-xs">
                      <div className="grid grid-cols-[20px_1fr_auto_auto] gap-2 text-[10px] font-bold text-[var(--color-muted)] uppercase pb-1 border-b border-[var(--color-border)]">
                        <span>#</span>
                        <span>Market</span>
                        <span className="text-right">Count</span>
                        <span className="text-right">Share</span>
                      </div>

                      {topMarkets.map((row) => (
                        <div key={row.market} className="grid grid-cols-[20px_1fr_auto_auto] gap-2 items-center">
                          <span className="font-mono text-[var(--color-muted)] font-bold">{row.rank}</span>
                          <span className="font-semibold text-[var(--color-foreground)] truncate">{row.market}</span>
                          <span className="text-[var(--color-muted)] text-right font-mono">{row.count}</span>
                          <span className="text-emerald-500 font-bold text-right font-mono">
                            {row.percent}%
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* 2. Lifecycle Stages */}
                <div className="space-y-3">
                  <h4 className="text-xs font-semibold text-[var(--color-muted)] flex items-center gap-1">
                    <span>Lifecycle Stages</span>
                    <HelpCircle size={11} className="text-[var(--color-muted)]" />
                  </h4>
                  {lifecycleBreakdown.length === 0 ? (
                    <div className="rounded-lg bg-[var(--color-surface-elevated)]/50 border border-[var(--color-border)] p-4 text-center">
                      <p className="text-xs text-[var(--color-muted)]">Awaiting lifecycle events.</p>
                    </div>
                  ) : (
                    <div className="space-y-3 pt-1">
                      {lifecycleBreakdown.map((item) => (
                        <div key={item.name} className="space-y-1">
                          <div className="flex items-center justify-between text-xs">
                            <span className="text-[var(--color-muted)] truncate">{item.name}</span>
                            <span className="font-mono font-bold text-[var(--color-foreground)] text-xs">{item.count}</span>
                          </div>
                          <div className="h-2 w-full rounded-full bg-[var(--color-surface-elevated)] overflow-hidden">
                            <div
                              className={cn("h-full rounded-full transition-all duration-500", item.color)}
                              style={{ width: `${item.score}%` }}
                            />
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* 3. Top Categories */}
                <div className="space-y-3">
                  <h4 className="text-xs font-semibold text-[var(--color-muted)]">
                    Top Categories <span className="text-[10px] text-[var(--color-muted-dim)] font-normal">(Discovered)</span>
                  </h4>
                  {topCategories.length === 0 ? (
                    <div className="rounded-lg bg-[var(--color-surface-elevated)]/50 border border-[var(--color-border)] p-4 text-center">
                      <p className="text-xs text-[var(--color-muted)]">Categories populate from discoveries.</p>
                    </div>
                  ) : (
                    <div className="space-y-3 pt-1">
                      {topCategories.map((cat) => (
                        <div key={cat.label} className="flex items-center justify-between text-xs">
                          <span className="truncate text-[var(--color-foreground)] font-medium">{cat.label}</span>
                          <span className="font-mono font-bold text-[var(--color-foreground)] pl-2">{cat.percent}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* 4. CRM / Lead Distribution Donut */}
                <div className="space-y-3">
                  <h4 className="text-xs font-semibold text-[var(--color-muted)]">
                    Lead Pipeline
                  </h4>
                  <div className="flex items-center gap-4 pt-1">
                    {/* SVG Donut */}
                    <div className="relative flex h-24 w-24 shrink-0 items-center justify-center">
                      <svg viewBox="0 0 36 36" className="h-full w-full -rotate-90">
                        <path
                          className="text-[var(--color-surface-elevated)]"
                          strokeWidth="4.5"
                          stroke="currentColor"
                          fill="none"
                          d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                        />
                        {donutSegments.map((seg, i) => (
                          <path
                            key={i}
                            stroke={seg.color}
                            strokeDasharray={seg.strokeDasharray}
                            strokeDashoffset={seg.strokeDashoffset}
                            strokeWidth="4.5"
                            fill="none"
                            d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                          />
                        ))}
                      </svg>
                      <div className="absolute inset-0 flex flex-col items-center justify-center text-center">
                        <span className="text-[11px] font-bold text-[var(--color-foreground)] font-mono leading-none">
                          {totalProspects > 0 ? totalProspects.toLocaleString() : leadsTotal.toLocaleString()}
                        </span>
                        <span className="text-[9px] text-[var(--color-muted)] mt-0.5">leads</span>
                      </div>
                    </div>

                    {/* Donut Legend */}
                    <div className="space-y-1.5 text-[11px] min-w-0">
                      {donutSegments.length === 0 ? (
                        <p className="text-[10px] text-[var(--color-muted)]">No leads tracked in pipeline yet.</p>
                      ) : (
                        donutSegments.map((seg, i) => (
                          <div key={i} className="flex items-center gap-1.5">
                            <span
                              className="h-2 w-2 rounded-full shrink-0"
                              style={{ backgroundColor: seg.color }}
                            />
                            <span className="text-[var(--color-muted)] truncate">{seg.label}</span>
                            <span className="font-bold font-mono text-[var(--color-foreground)] ml-auto pl-1">
                              {seg.percent}%
                            </span>
                          </div>
                        ))
                      )}
                    </div>
                  </div>
                </div>

              </div>
            </div>

            {/* Right: Source Health & Source Activity */}
            <div className="space-y-5">

              {/* Source Health Card (Live Monitoring) */}
              <div className="hidden rounded-xl bg-[var(--color-surface)] border border-[var(--color-border)] p-5 space-y-3.5">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Layers size={16} className="text-blue-500" />
                    <h3 className="text-sm font-bold text-[var(--color-foreground)]">System & Discovery Health</h3>
                  </div>

                  <span className="text-[10px] text-[var(--color-muted)] font-mono">
                    {healthQuery.data?.status === "ok" ? "All Systems Operational" : "Probing Services..."}
                  </span>
                </div>

                <div className="space-y-2.5 pt-1">
                  {(healthQuery.data?.components ?? [
                    { name: "database", ok: true, detail: "Primary datastore" },
                    { name: "redis", ok: true, detail: "Cache & coordination" },
                    { name: "worker", ok: true, detail: "Job processor" },
                    { name: "searxng", ok: true, detail: "Metasearch engine" },
                    { name: "osm_imagery", ok: true, detail: "Map tile services" },
                  ]).map((comp) => {
                    const displayName =
                      comp.name === "database"
                        ? "PostgreSQL Database"
                        : comp.name === "redis"
                        ? "Redis Coordination"
                        : comp.name === "worker"
                        ? "Async Task Worker"
                        : comp.name === "searxng"
                        ? "SearXNG Metasearch"
                        : comp.name === "osm_imagery"
                        ? "OSM Map & Imagery"
                        : comp.name;

                    return (
                      <div key={comp.name} className="flex items-center justify-between text-xs py-0.5">
                        <div className="flex items-center gap-2 min-w-0">
                          {comp.ok ? (
                            <CheckCircle2 size={13} className="text-emerald-500 shrink-0" />
                          ) : (
                            <AlertCircle size={13} className="text-amber-500 shrink-0" />
                          )}
                          <span className="font-medium text-[var(--color-foreground)] truncate">
                            {displayName}
                          </span>
                        </div>

                        <div className="flex items-center gap-2">
                          <span
                            className={cn(
                              "rounded-full px-2 py-0.5 text-[10px] font-semibold border",
                              comp.ok
                                ? "bg-emerald-500/10 border-emerald-500/25 text-emerald-500"
                                : "bg-amber-500/10 border-amber-500/25 text-amber-500"
                            )}
                          >
                            {comp.ok ? "Ready" : "Degraded"}
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Map Explorer replaces the low-value activity panel. */}
              <Link
                href="/leads/map"
                className="group relative block min-h-[460px] overflow-hidden rounded-xl border-0 bg-[var(--color-surface)] shadow-sm"
                title="Open Interactive Map Explorer"
                aria-label="Open Global Map Explorer"
              >
                <Image
                  src="/map-explorer-global.png"
                  alt="Map Explorer preview"
                  fill
                  sizes="(max-width: 1280px) 100vw, 420px"
                  priority
                  className="object-cover transition-transform duration-500 group-hover:scale-105"
                />
                <div className="absolute inset-0 bg-gradient-to-t from-[#071225]/95 via-[#071225]/35 to-transparent" />
                <div className="absolute left-3 top-3 rounded-md border border-violet-300/40 bg-[#071225]/85 px-2.5 py-1 text-[10px] font-semibold text-white shadow-lg backdrop-blur-sm">
                  <span className="mr-1.5 inline-block h-1.5 w-1.5 rounded-full bg-violet-400" />10 km radius
                </div>
              </Link>

            </div>

          </section>

          {/* ── Bottom Section: Discovered Businesses Table ── */}
          <section className="rounded-xl bg-[var(--color-surface)] border border-[var(--color-border)] p-5 space-y-4">
            {/* Header + Filters */}
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between border-b border-[var(--color-border)] pb-4">
              <div className="flex items-center gap-2">
                <Building size={17} className="text-blue-500" />
                <h3 className="text-sm font-bold text-[var(--color-foreground)]">
                  Discovered businesses{" "}
                  <span className="text-[var(--color-muted)] font-normal">
                    ({leadsTotal.toLocaleString()})
                  </span>
                </h3>
              </div>

              {/* Filters & Export */}
              <div className="flex flex-wrap items-center gap-2">
                {/* Location Filter */}
                <select
                  value={marketFilter}
                  onChange={(e) => setMarketFilter(e.target.value)}
                  className="rounded-lg bg-[var(--color-surface-elevated)] border border-[var(--color-border)] px-3 py-1.5 text-xs text-[var(--color-foreground)] focus:outline-none focus:border-blue-500 cursor-pointer"
                >
                  <option value="all">Location: All markets</option>
                  {uniqueCities.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>

                {/* Category Filter */}
                <select
                  value={businessTypeFilter}
                  onChange={(e) => setBusinessTypeFilter(e.target.value)}
                  className="rounded-lg bg-[var(--color-surface-elevated)] border border-[var(--color-border)] px-3 py-1.5 text-xs text-[var(--color-foreground)] focus:outline-none focus:border-blue-500 cursor-pointer"
                >
                  <option value="all">Category: All types</option>
                  {uniqueCategories.map((cat) => (
                    <option key={cat} value={cat}>
                      {cat}
                    </option>
                  ))}
                </select>

                <Link
                  href="/leads"
                  className="flex items-center gap-1.5 rounded-lg bg-blue-600/10 hover:bg-blue-600/20 border border-blue-500/25 px-3 py-1.5 text-xs font-semibold text-blue-500 transition-colors"
                >
                  <Search size={12} />
                  <span>Explore All Leads</span>
                </Link>
              </div>
            </div>

            {/* Table */}
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-[var(--color-border)] text-[11px] font-semibold text-[var(--color-muted)] uppercase tracking-wider">
                    <th className="py-2.5 px-3 w-8">
                      <input
                        type="checkbox"
                        checked={
                          displayedBusinesses.length > 0 &&
                          selectedIds.size === displayedBusinesses.length
                        }
                        onChange={toggleSelectAll}
                        className="rounded border-[var(--color-border)] bg-[var(--color-surface)] text-blue-600 focus:ring-0 focus:ring-offset-0 cursor-pointer"
                      />
                    </th>
                    <th className="py-2.5 px-3">Business name</th>
                    <th className="py-2.5 px-3">Category</th>
                    <th className="py-2.5 px-3">Location</th>
                    <th className="py-2.5 px-3">Website / Source</th>
                    <th className="py-2.5 px-3">Contact info</th>
                    <th className="py-2.5 px-3">Status</th>
                    <th className="py-2.5 px-3 text-right">Actions</th>
                  </tr>
                </thead>

                <tbody className="divide-y divide-[var(--color-border)]">
                  {businessesQuery.isLoading ? (
                    <tr>
                      <td colSpan={8} className="py-12 text-center">
                        <div className="flex flex-col items-center justify-center space-y-2">
                          <RefreshCw size={20} className="animate-spin text-blue-500" />
                          <span className="text-xs text-[var(--color-muted)]">Loading workspace businesses...</span>
                        </div>
                      </td>
                    </tr>
                  ) : filteredBusinesses.length === 0 ? (
                    <tr>
                      <td colSpan={8} className="py-14 text-center">
                        <div className="flex flex-col items-center justify-center max-w-sm mx-auto space-y-3">
                          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-[var(--color-surface-elevated)] text-[var(--color-muted)] border border-[var(--color-border)]">
                            <Building2 size={24} />
                          </div>
                          <div className="space-y-1">
                            <h4 className="text-sm font-semibold text-[var(--color-foreground)]">No businesses discovered yet</h4>
                            <p className="text-xs text-[var(--color-muted)]">
                              Launch a discovery sweep using Overpass or SearXNG to populate your lead database.
                            </p>
                          </div>
                          <Link
                            href="/leads/discover"
                            className="inline-flex items-center gap-2 rounded-lg bg-blue-600 hover:bg-blue-500 px-4 py-2 text-xs font-semibold text-white transition-colors"
                          >
                            <Plus size={14} />
                            <span>Start Business Discovery</span>
                          </Link>
                        </div>
                      </td>
                    </tr>
                  ) : (
                    displayedBusinesses.map((row) => {
                      const isSelected = selectedIds.has(row.id);
                      const locationStr =
                        [row.city, row.state].filter(Boolean).join(", ") ||
                        row.country ||
                        "—";
                      const hostname = row.website_url
                        ? (() => {
                            try {
                              return new URL(row.website_url).hostname.replace(
                                /^www\./,
                                ""
                              );
                            } catch {
                              return "Website";
                            }
                          })()
                        : null;

                      return (
                        <tr
                          key={row.id}
                          className={cn(
                            "hover:bg-[var(--color-surface-elevated)]/60 transition-colors group",
                            isSelected && "bg-blue-500/10"
                          )}
                        >
                          <td className="py-3 px-3">
                            <input
                              type="checkbox"
                              checked={isSelected}
                              onChange={() => toggleSelect(row.id)}
                              className="rounded border-[var(--color-border)] bg-[var(--color-surface)] text-blue-600 focus:ring-0 focus:ring-offset-0 cursor-pointer"
                            />
                          </td>

                          <td className="py-3 px-3">
                            <Link
                              href={`/leads/${row.id}`}
                              className="font-semibold text-[var(--color-foreground)] hover:text-blue-500 transition-colors inline-block max-w-xs truncate"
                              title={row.name}
                            >
                              {row.name}
                            </Link>
                          </td>

                          <td className="py-3 px-3 text-[var(--color-muted)] max-w-[160px] truncate">
                            {row.primary_category || "Uncategorized"}
                          </td>

                          <td className="py-3 px-3">
                            <div className="flex items-center gap-1 text-[var(--color-muted)]">
                              <MapPin size={12} className="text-[var(--color-muted)] shrink-0" />
                              <span className="truncate max-w-[140px]">{locationStr}</span>
                            </div>
                          </td>

                          <td className="py-3 px-3">
                            {row.website_url ? (
                              <a
                                href={row.website_url}
                                target="_blank"
                                rel="noreferrer"
                                className="flex items-center gap-1 text-blue-500 hover:text-blue-600 dark:text-blue-400 dark:hover:text-blue-300 hover:underline max-w-[150px] truncate"
                              >
                                <span className="truncate">{hostname}</span>
                                <ExternalLink size={10} className="shrink-0" />
                              </a>
                            ) : (
                              <span className="text-[var(--color-muted)]">—</span>
                            )}
                          </td>

                          <td className="py-3 px-3">
                            <div className="flex items-center gap-2.5">
                              {row.phone ? (
                                <span title={`Phone: ${row.phone}`}>
                                  <Phone size={13} className="text-emerald-500" />
                                </span>
                              ) : (
                                <span className="text-[var(--color-muted)]">—</span>
                              )}
                              {row.email ? (
                                <span title={`Email: ${row.email}`}>
                                  <Mail size={13} className="text-emerald-500" />
                                </span>
                              ) : (
                                <span className="text-[var(--color-muted)]">—</span>
                              )}
                            </div>
                          </td>

                          <td className="py-3 px-3">
                            <span
                              className={cn(
                                "rounded-full px-2.5 py-0.5 text-[10px] font-semibold border inline-block capitalize",
                                row.lifecycle_status === "customer"
                                  ? "bg-emerald-500/10 border-emerald-500/25 text-emerald-500"
                                  : row.lifecycle_status === "prospect" || row.lifecycle_status === "lead"
                                  ? "bg-blue-500/10 border-blue-500/25 text-blue-500"
                                  : "bg-[var(--color-surface-elevated)] border-[var(--color-border)] text-[var(--color-muted)]"
                              )}
                            >
                              {row.lifecycle_status || "Discovered"}
                            </span>
                          </td>

                          <td className="py-3 px-3 text-right">
                            <Link
                              href={`/leads/${row.id}`}
                              className="text-[var(--color-muted)] hover:text-blue-500 transition-colors inline-block p-1"
                              title="View details"
                            >
                              <MoreHorizontal size={14} />
                            </Link>
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>

            {/* Table Footer: Clean preview limit & direct link to CRM */}
            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[var(--color-border)] px-4 py-3 bg-[var(--color-surface-elevated)]/30 text-xs text-[var(--color-muted)]">
              <span className="font-medium">
                Showing top {displayedBusinesses.length} recent discoveries{" "}
                <span className="text-[var(--color-muted)]/75">
                  (of {leadsTotal.toLocaleString()} total indexed)
                </span>
              </span>
              <Link
                href="/leads"
                className="inline-flex items-center gap-1.5 font-semibold text-blue-500 hover:text-blue-400 hover:underline transition-colors"
              >
                <span>Explore all {leadsTotal.toLocaleString()} leads</span>
                <ArrowRight size={13} />
              </Link>
            </div>
          </section>

          {/* ── Footer ── */}
          <AppFooter />

        </div>
      </main>
    </div>
  );
}
