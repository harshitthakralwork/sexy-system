"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  AlertTriangle,
  Check,
  ChevronDown,
  Clock3,
  Database,
  Gauge,
  Globe2,
  History,
  Power,
  RefreshCw,
  Search,
  ShieldCheck,
  WifiOff,
} from "lucide-react";

import { Header } from "@/components/layout/header";
import { AppFooter } from "@/components/layout/app-footer";
import { Card, EmptyState } from "@/components/ui/card";
import { useSession } from "@/components/providers/session-provider";
import { api } from "@/lib/api/client";
import type { SourceHistory, SourceItem, SourceList, SourceTestResult } from "@/lib/api/types";

const CATEGORY_LABELS: Record<string, string> = {
  search: "Search",
  geographic: "Geographic",
  social: "Social",
  startup: "Startup",
  directory: "Public directories",
  import: "Imported files",
};

const HEALTH_COPY: Record<string, string> = {
  working: "Answering",
  degraded: "Degraded",
  failed: "Failing",
  unknown: "Never probed",
};

function healthTone(status: string): string {
  if (status === "working") {
    return "border-emerald-400/40 bg-emerald-500/15 text-emerald-300 shadow-[0_0_12px_rgba(52,211,153,0.25)]";
  }
  if (status === "failed") {
    return "border-rose-400/40 bg-rose-500/15 text-rose-300 shadow-[0_0_12px_rgba(244,63,94,0.25)]";
  }
  if (status === "degraded") {
    return "border-amber-400/40 bg-amber-500/15 text-amber-300 shadow-[0_0_12px_rgba(251,191,36,0.25)]";
  }
  return "border-white/15 bg-white/5 text-white/60";
}

function HealthIcon({ status, className = "size-4" }: { status: string; className?: string }) {
  if (status === "working") return <Check className={className} />;
  if (status === "failed") return <WifiOff className={className} />;
  if (status === "degraded") return <AlertTriangle className={className} />;
  return <Clock3 className={className} />;
}

function buttonClass(active: boolean): string {
  return [
    "rounded-full border px-3.5 py-1.5 text-xs font-semibold transition-all disabled:opacity-50",
    active
      ? "refraction-glass-btn border-cyan-400/40 bg-cyan-500/20 text-cyan-200 shadow-[0_0_15px_rgba(0,212,255,0.3)]"
      : "border-white/15 bg-white/[0.04] text-white/70 hover:border-white/30 hover:text-white hover:bg-white/[0.08]",
  ].join(" ");
}

function whenSet(value: string | null | undefined): string {
  return value ? new Date(value).toLocaleString() : "never";
}

export function SourcesView() {
  const { user } = useSession();
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [categoryFilter, setCategoryFilter] = useState("all");
  const sources = useQuery({
    queryKey: ["sources"],
    queryFn: () => api.get<SourceList>("/sources"),
  });

  const allSources = useMemo(
    () => sources.data?.groups.flatMap((group) => group.items) ?? [],
    [sources.data],
  );
  const counts = useMemo(
    () => ({
      working: allSources.filter((source) => source.health_status === "working").length,
      attention: allSources.filter((source) => ["failed", "degraded"].includes(source.health_status)).length,
      unknown: allSources.filter((source) => source.health_status === "unknown").length,
      enabled: allSources.filter((source) => source.enabled_for_user).length,
    }),
    [allSources],
  );
  const categories = useMemo(
    () => Array.from(new Set(allSources.map((source) => source.category))),
    [allSources],
  );
  const filteredGroups = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return (sources.data?.groups ?? [])
      .filter((group) => categoryFilter === "all" || group.category === categoryFilter)
      .map((group) => ({
        ...group,
        items: group.items.filter((source) => {
          const matchesStatus =
            statusFilter === "all" ||
            (statusFilter === "attention"
              ? ["failed", "degraded"].includes(source.health_status)
              : source.health_status === statusFilter);
          const matchesQuery =
            !normalizedQuery ||
            `${source.name} ${source.slug} ${source.adapter_key} ${source.description ?? ""}`
              .toLowerCase()
              .includes(normalizedQuery);
          return matchesStatus && matchesQuery;
        }),
      }))
      .filter((group) => group.items.length > 0);
  }, [categoryFilter, query, sources.data, statusFilter]);

  if (!user) return null;

  return (
    <div className="flex min-h-0 flex-1 flex-col text-white">
      <Header
        title="Source Manager"
        subtitle="Every provider this build can actually query, with its real limits"
      />
      <main className="flex-1 overflow-y-auto px-4 pb-10 pt-4 sm:px-6">
        {sources.isError && (
          <p className="mb-3 text-sm text-rose-400">
            {sources.error instanceof Error ? sources.error.message : "Sources failed to load"}
          </p>
        )}

        {/* 4 Top Health Metric Tiles */}
        <section className="mb-5 grid gap-3.5 sm:grid-cols-2 xl:grid-cols-4">
          <HealthMetric
            icon={ShieldCheck}
            label="Answering"
            value={counts.working}
            detail={`of ${allSources.length} registered`}
            tone="emerald"
          />
          <HealthMetric
            icon={AlertTriangle}
            label="Needs attention"
            value={counts.attention}
            detail="failed or degraded"
            tone="amber"
          />
          <HealthMetric
            icon={Clock3}
            label="Not tested"
            value={counts.unknown}
            detail="run a connection test"
            tone="slate"
          />
          <HealthMetric
            icon={Power}
            label="Enabled"
            value={counts.enabled}
            detail="for your account"
            tone="sky"
          />
        </section>

        {/* Extraction Engine & Reporting Cards */}
        <div className="mb-5 grid gap-3.5 xl:grid-cols-[1.35fr_.65fr]">
          <PublicPageFetchCard />
          <Card className="relative overflow-hidden p-5 hover:border-white/30">
            <div className="absolute -right-10 -top-12 size-36 rounded-full bg-cyan-500/10 blur-3xl" />
            <div className="relative flex items-start gap-3.5">
              <span className="grid size-10 shrink-0 place-items-center rounded-2xl border border-cyan-400/30 bg-cyan-500/15 text-cyan-300">
                <ShieldCheck className="size-5" />
              </span>
              <div>
                <h2 className="text-sm font-bold text-white">Honest source reporting</h2>
                <p className="mt-1.5 text-xs leading-5 text-white/70">
                  “Answering” only appears after a successful live probe. Restricted platforms stay in Social Sources until a compliant connector exists.
                </p>
              </div>
            </div>
          </Card>
        </div>

        {/* Search & Category Filter Capsule with Deep Dark Glass */}
        <section className="mb-6 rounded-[26px] refraction-glass-card p-4.5 border-white/15 shadow-2xl bg-[rgba(14,18,30,0.68)]">
          <div className="flex flex-col gap-3 xl:flex-row xl:items-center">
            <label className="relative min-w-0 flex-1">
              <Search className="pointer-events-none absolute left-4 top-1/2 size-4 -translate-y-1/2 text-cyan-400" />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search providers, adapters or capabilities…"
                className="h-11 w-full rounded-2xl border border-white/15 bg-black/45 pl-11 pr-4 text-sm text-white placeholder-white/40 outline-none transition focus:border-cyan-400/60 focus:bg-black/65 shadow-inner"
              />
            </label>
            <div className="flex gap-2 overflow-x-auto pb-1 xl:pb-0">
              {[
                ["all", "All"],
                ["working", "Answering"],
                ["attention", "Needs attention"],
                ["unknown", "Not tested"],
              ].map(([value, label]) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => setStatusFilter(value)}
                  className={`whitespace-nowrap rounded-full px-4 py-2 text-xs font-bold transition-all ${
                    statusFilter === value
                      ? "border border-cyan-400/40 bg-cyan-500/20 text-cyan-200 shadow-[0_0_15px_rgba(0,212,255,0.3)]"
                      : "border border-white/10 bg-white/[0.04] text-white/65 hover:border-white/20 hover:text-white"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
          <div className="mt-3.5 flex gap-2 overflow-x-auto border-t border-white/10 pt-3.5">
            <CategoryChip
              active={categoryFilter === "all"}
              onClick={() => setCategoryFilter("all")}
              label="All categories"
            />
            {categories.map((category) => (
              <CategoryChip
                key={category}
                active={categoryFilter === category}
                onClick={() => setCategoryFilter(category)}
                label={CATEGORY_LABELS[category] ?? category}
              />
            ))}
          </div>
        </section>

        {sources.isPending && !sources.isError && (
          <EmptyState title="Reading the registry…" description="" />
        )}
        {sources.data && sources.data.total === 0 && (
          <EmptyState
            title="No sources registered"
            description="The registry fills itself from the adapters this build ships with."
          />
        )}
        {sources.data && filteredGroups.length === 0 && (
          <EmptyState title="No matching sources" description="Clear a filter or search for another provider." />
        )}

        {/* Source Categories and Grid */}
        <div className="space-y-8">
          {filteredGroups.map((group) => (
            <section key={group.category}>
              <div className="mb-4 flex items-center gap-3">
                <span className="inline-flex items-center gap-2 rounded-full border border-cyan-400/30 bg-cyan-500/10 px-3.5 py-1 text-xs font-bold uppercase tracking-wider text-cyan-300">
                  <span>{CATEGORY_LABELS[group.category] ?? group.category}</span>
                  <span className="rounded-full bg-cyan-400/20 px-2 py-0.5 text-[10px] text-cyan-200">
                    {group.items.length}
                  </span>
                </span>
                <span className="h-px flex-1 bg-white/10" />
              </div>
              <div className="grid gap-3.5 lg:grid-cols-2 2xl:grid-cols-3">
                {group.items.map((source) => (
                  <SourceCard key={source.id} source={source} />
                ))}
              </div>
            </section>
          ))}
          <AppFooter />
        </div>
      </main>
    </div>
  );
}

function HealthMetric({
  icon: Icon,
  label,
  value,
  detail,
  tone,
}: {
  icon: typeof Activity;
  label: string;
  value: number;
  detail: string;
  tone: "emerald" | "amber" | "slate" | "sky";
}) {
  const tones = {
    emerald: "border-emerald-400/30 bg-emerald-500/15 text-emerald-300 shadow-[0_0_12px_rgba(52,211,153,0.2)]",
    amber: "border-amber-400/30 bg-amber-500/15 text-amber-300 shadow-[0_0_12px_rgba(251,191,36,0.2)]",
    slate: "border-violet-400/40 bg-violet-500/20 text-violet-300 shadow-[0_0_12px_rgba(167,139,250,0.3)]",
    sky: "border-sky-400/30 bg-sky-500/15 text-sky-300 shadow-[0_0_12px_rgba(56,189,248,0.2)]",
  };
  return (
    <Card className="flex items-center gap-4 !p-4.5 hover:border-white/30">
      <span className={`grid size-11 shrink-0 place-items-center rounded-2xl border ${tones[tone]}`}>
        <Icon className="size-5" />
      </span>
      <div className="min-w-0">
        <p className="text-xs font-semibold text-white/60">{label}</p>
        <p className="mt-0.5 text-2xl font-extrabold tracking-tight text-white font-sans">{value}</p>
        <p className="truncate text-[0.68rem] text-white/45">{detail}</p>
      </div>
    </Card>
  );
}

function CategoryChip({
  active,
  onClick,
  label,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`whitespace-nowrap rounded-full border px-3.5 py-1.5 text-xs font-medium transition-all ${
        active
          ? "border-cyan-400/40 bg-cyan-500/20 text-cyan-200 shadow-[0_0_12px_rgba(0,212,255,0.25)]"
          : "border-white/15 bg-white/[0.04] text-white/65 hover:border-white/25 hover:text-white"
      }`}
    >
      {label}
    </button>
  );
}

function PublicPageFetchCard() {
  const health = useQuery({
    queryKey: ["public-page-fetch", "health"],
    queryFn: () =>
      api.get<{
        status: string;
        method: string;
        access: string;
        limits: { max_response_bytes: number; max_redirects: number };
      }>("/discovery/public-page-fetch/health"),
  });

  return (
    <Card className="relative overflow-hidden p-5 hover:border-white/30">
      <div className="absolute -left-12 -top-16 size-44 rounded-full bg-cyan-500/10 blur-3xl" />
      <div className="relative flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <span className="grid size-10 shrink-0 place-items-center rounded-2xl border border-cyan-400/30 bg-cyan-500/15 text-cyan-300">
            <Globe2 className="size-5" />
          </span>
          <div>
            <p className="text-[0.65rem] font-bold uppercase tracking-wider text-cyan-400">
              Extraction engine
            </p>
            <h2 className="mt-1 text-base font-bold text-white">Public Page Fetch</h2>
            <p className="mt-1 text-xs leading-5 text-white/70">
              Reads public SearXNG and directory pages for structured business evidence.
            </p>
          </div>
        </div>
        <span
          className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-[0.7rem] font-bold ${
            health.data?.status === "ok" ? healthTone("working") : healthTone("unknown")
          }`}
        >
          {health.isPending ? (
            <RefreshCw className="size-3 animate-spin" />
          ) : (
            <HealthIcon status={health.data?.status === "ok" ? "working" : "unknown"} className="size-3" />
          )}
          {health.isPending ? "Checking" : health.data?.status === "ok" ? "Ready" : "Unavailable"}
        </span>
      </div>
      {health.data && (
        <div className="relative mt-4 grid gap-2 sm:grid-cols-3">
          <MiniFact label="Method" value={health.data.method} />
          <MiniFact label="Access" value={health.data.access} />
          <MiniFact
            label="Safety limit"
            value={`${Math.round(health.data.limits.max_response_bytes / 100_000) / 10} MB · ${health.data.limits.max_redirects} redirects`}
          />
        </div>
      )}
      {health.isError && <p className="mt-3 text-xs text-rose-400">Public fetch health could not be read.</p>}
    </Card>
  );
}

function MiniFact({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-white/15 bg-black/60 px-3.5 py-2.5 backdrop-blur-xl shadow-inner">
      <p className="text-[0.62rem] font-bold uppercase tracking-wider text-cyan-400">{label}</p>
      <p className="mt-1 truncate text-xs font-semibold text-white font-mono" title={value}>
        {value}
      </p>
    </div>
  );
}

function SourceCard({ source }: { source: SourceItem }) {
  const { csrf } = useSession();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [probe, setProbe] = useState<SourceTestResult | null>(null);
  const [open, setOpen] = useState(false);

  const refresh = async () => {
    setError(null);
    await queryClient.invalidateQueries({ queryKey: ["sources"] });
  };

  const toggle = useMutation({
    mutationFn: () =>
      api.post<{ slug: string; enabled_for_user: boolean }>(
        `/sources/${source.slug}/${source.enabled_for_user ? "disable" : "enable"}`,
        undefined,
        csrf,
      ),
    onSuccess: refresh,
    onError: (caught) => setError(caught instanceof Error ? caught.message : "Toggle failed"),
  });

  const test = useMutation({
    mutationFn: () => api.post<SourceTestResult>(`/sources/${source.slug}/test`, undefined, csrf),
    onSuccess: async (result) => {
      setProbe(result);
      await refresh();
    },
    onError: (caught) => setError(caught instanceof Error ? caught.message : "Probe failed"),
  });

  const history = useQuery({
    queryKey: ["sources", source.slug, "history"],
    queryFn: () => api.get<SourceHistory>(`/sources/${source.slug}/history?limit=10`),
    enabled: open,
  });

  const feeds = Array.isArray(source.configuration["feed_urls"])
    ? (source.configuration["feed_urls"] as unknown[])
    : [];
  const note = source.configuration["note"];

  return (
    <Card className="group flex flex-col !p-0 border border-white/15 bg-[rgba(14,18,30,0.58)] hover:border-cyan-400/40 transition-all duration-200">
      <div className="flex flex-1 flex-col p-5">
        {/* Source Header */}
        <div className="flex items-start justify-between gap-3">
          <div className="flex min-w-0 items-start gap-3">
            <span
              className={`grid size-10 shrink-0 place-items-center rounded-2xl border ${healthTone(
                source.health_status,
              )}`}
            >
              <HealthIcon status={source.health_status} />
            </span>
            <div className="min-w-0">
              <h3 className="truncate text-sm font-bold text-white" title={source.name}>
                {source.name}
              </h3>
              <p className="mt-0.5 truncate text-[0.68rem] font-medium text-white/50">
                {source.adapter_key} · {source.slug}
              </p>
            </div>
          </div>
          <span
            className={`inline-flex shrink-0 items-center gap-1.5 rounded-full border px-2.5 py-1 text-[0.68rem] font-bold ${healthTone(
              source.health_status,
            )}`}
          >
            {HEALTH_COPY[source.health_status] ?? source.health_status}
          </span>
        </div>

        {source.last_error && (
          <div className="mt-4 flex gap-2 rounded-2xl border border-rose-500/30 bg-rose-500/10 px-3 py-2.5 text-xs text-rose-300">
            <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
            <p className="line-clamp-2">{source.last_error}</p>
          </div>
        )}

        {probe && (
          <p className="mt-3 rounded-xl border border-white/10 bg-black/40 px-3 py-2 text-xs text-white/80">
            Probe: {probe.status}
            {probe.detail ? ` — ${probe.detail}` : ""}
            {probe.response_time_ms != null ? ` (${probe.response_time_ms} ms)` : ""}
          </p>
        )}

        {source.description && !source.last_error && (
          <p className="mt-4 line-clamp-2 text-xs leading-5 text-white/70">
            {source.description}
          </p>
        )}

        {/* 3 Stats Sub-boxes (Runs, Requests, Returned) with Sleek Dark Glass */}
        <div className="mt-4 grid grid-cols-3 overflow-hidden rounded-2xl border border-white/15 bg-black/60 backdrop-blur-xl shadow-inner">
          <SourceStat label="Runs" value={source.runs_recorded} />
          <SourceStat label="Requests" value={source.requests_count} bordered />
          <SourceStat label="Returned" value={source.records_returned} />
        </div>

        {/* Probe Timing & Enabled State */}
        <div className="mt-3.5 flex flex-wrap items-center justify-between gap-2 text-[0.68rem] text-white/55">
          <span className="inline-flex items-center gap-1.5">
            <Clock3 className="size-3.5 text-white/40" />
            Last probe: {whenSet(source.last_check_at)}
            {source.last_check_response_ms != null ? ` · ${source.last_check_response_ms} ms` : ""}
          </span>
          <span
            className={`inline-flex items-center gap-1.5 font-semibold ${
              source.enabled_for_user ? "text-emerald-300" : "text-white/40"
            }`}
          >
            <span
              className={`size-1.5 rounded-full ${
                source.enabled_for_user
                  ? "bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.8)]"
                  : "bg-white/30"
              }`}
            />
            {source.enabled_for_user ? "Enabled" : "Disabled"}
          </span>
        </div>

        {feeds.length > 0 && (
          <div className="text-xs mt-3">
            <p className="text-white/60 font-medium">Your feeds</p>
            <ul className="list-disc pl-4 text-white/70">
              {feeds.map((feed) => (
                <li key={String(feed)} className="truncate">
                  {String(feed)}
                </li>
              ))}
            </ul>
          </div>
        )}

        {typeof note === "string" && note && (
          <p className="text-xs text-white/60 mt-2">Note: {note}</p>
        )}

        {error && <p className="text-xs text-rose-400 mt-2">{error}</p>}

        {source.slug === "file_import" && (
          <p className="text-xs text-white/60 mt-3">
            This source is fed by the files you import. There is no provider behind it, so
            there is nothing to enable or probe &mdash; imported records point at the file
            they came from.
          </p>
        )}

        {/* Action Buttons: Enable/Disable, Test, Details */}
        <div className="mt-auto flex flex-wrap items-center gap-2 pt-5 border-t border-white/10">
          {source.slug !== "file_import" && (
            <>
              <button
                className={buttonClass(!source.enabled_for_user)}
                disabled={toggle.isPending}
                onClick={() => toggle.mutate()}
                type="button"
              >
                <Power className="mr-1 inline size-3" />
                {source.enabled_for_user ? "Disable" : "Enable"}
              </button>
              <button
                className={buttonClass(false)}
                disabled={test.isPending}
                onClick={() => test.mutate()}
                type="button"
              >
                <RefreshCw
                  className={`mr-1 inline size-3 ${test.isPending ? "animate-spin text-cyan-400" : ""}`}
                />
                {test.isPending ? "Testing…" : "Test"}
              </button>
            </>
          )}
          <button
            className={`${buttonClass(false)} ml-auto`}
            onClick={() => setOpen(!open)}
            type="button"
          >
            <ChevronDown
              className={`mr-1 inline size-3 transition-transform ${open ? "rotate-180" : ""}`}
            />
            {open ? "Less" : "Details"}
          </button>
        </div>

        {open && (
          <div className="mt-4 space-y-3 border-t border-white/10 pt-4 text-xs">
            <DetailRow
              icon={Database}
              label="Account / provider"
              value={`${source.enabled_for_user ? "Enabled" : "Disabled"} / ${
                source.globally_enabled ? "Enabled" : "Disabled"
              }`}
            />
            <DetailRow
              icon={Activity}
              label="Last successful run"
              value={whenSet(source.last_successful_run_at)}
            />
            <DetailRow
              icon={Gauge}
              label="Records accepted"
              value={
                source.records_accepted == null
                  ? "Not reported per source"
                  : String(source.records_accepted)
              }
            />
            <DetailRow
              icon={Globe2}
              label="Coverage"
              value={String(source.coverage["geographic_coverage"] ?? "Not stated")}
            />
            <div className="rounded-2xl border border-white/10 bg-black/40 p-3 text-xs backdrop-blur-md">
              <p className="font-bold text-white">Limitations</p>
              <ul className="mt-2 list-disc space-y-1.5 pl-4 leading-5 text-white/70">
                <li>{String(source.limitations["rate_limit_notes"] ?? "No rate limit stated")}</li>
                <li>{String(source.limitations["terms_notes"] ?? "No terms stated")}</li>
              </ul>
            </div>
          </div>
        )}

        {source.adapter_key === "rss" && open && <FeedConfig source={source} />}

        {open && (
          <div className="mt-4 rounded-2xl border border-white/10 bg-black/40 p-3 backdrop-blur-md">
            {history.isError && (
              <p className="text-xs text-rose-400">
                {history.error instanceof Error ? history.error.message : "History failed to load"}
              </p>
            )}
            {!history.isError && (history.isPending || !history.data) && (
              <p className="text-xs text-white/60">Loading…</p>
            )}
            {history.data && (
              <>
                <p className="flex items-center gap-1.5 text-xs font-bold text-white">
                  <History className="size-3.5 text-cyan-400" />
                  Recent probes ({history.data.checks.length})
                </p>
                {history.data.checks.length === 0 ? (
                  <p className="text-xs text-white/50 mt-1">Never probed.</p>
                ) : (
                  <ul className="mt-2 space-y-1 text-[11px] text-white/70">
                    {history.data.checks.map((probeItem) => (
                      <li key={probeItem.id} className="flex items-center gap-2">
                        <span
                          className={`size-1.5 rounded-full ${
                            probeItem.status === "ok" ? "bg-emerald-400" : "bg-rose-400"
                          }`}
                        />
                        <span>{new Date(probeItem.checked_at).toLocaleTimeString()}</span>
                        <span>·</span>
                        <span className="font-semibold">{probeItem.status}</span>
                        {probeItem.response_time_ms != null && (
                          <span className="text-white/45">({probeItem.response_time_ms}ms)</span>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
              </>
            )}
          </div>
        )}
      </div>
    </Card>
  );
}

function SourceStat({
  label,
  value,
  bordered = false,
}: {
  label: string;
  value: number;
  bordered?: boolean;
}) {
  return (
    <div className={`px-3 py-3 text-center ${bordered ? "border-x border-white/10" : ""}`}>
      <p className="text-base font-extrabold tracking-tight text-white font-mono">
        {value.toLocaleString()}
      </p>
      <p className="mt-0.5 text-[0.62rem] font-bold uppercase tracking-wider text-cyan-400">
        {label}
      </p>
    </div>
  );
}

function DetailRow({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof Activity;
  label: string;
  value: string;
}) {
  return (
    <div className="flex items-start gap-2 text-xs">
      <Icon className="mt-0.5 size-3.5 shrink-0 text-cyan-400" />
      <p>
        <span className="text-white/50">{label}: </span>
        <span className="font-semibold text-white">{value}</span>
      </p>
    </div>
  );
}

function FeedConfig({ source }: { source: SourceItem }) {
  const { csrf } = useSession();
  const queryClient = useQueryClient();
  const existing = Array.isArray(source.configuration["feed_urls"])
    ? (source.configuration["feed_urls"] as unknown[]).map(String)
    : [];
  const [value, setValue] = useState(existing.join("\n"));
  const [message, setMessage] = useState<string | null>(null);

  const save = useMutation({
    mutationFn: () =>
      api.put(
        `/sources/${source.slug}/config`,
        { feed_urls: value.split("\n").map((line) => line.trim()).filter(Boolean) },
        csrf,
      ),
    onSuccess: async () => {
      setMessage("Saved. Tracks with no feeds of their own will use these.");
      await queryClient.invalidateQueries({ queryKey: ["sources"] });
    },
    onError: (caught) => setMessage(caught instanceof Error ? caught.message : "Save failed"),
  });

  return (
    <div className="mt-4 rounded-2xl border border-white/10 bg-black/40 p-3.5 backdrop-blur-md">
      <label className="text-xs">
        <span className="text-white/60 font-medium">Feed URLs (one per line, http(s) only)</span>
        <textarea
          className="mt-1.5 h-20 w-full rounded-xl border border-white/15 bg-white/[0.04] px-3 py-2 text-xs text-white placeholder-white/40 outline-none focus:border-cyan-400/50"
          value={value}
          onChange={(event) => setValue(event.target.value)}
        />
      </label>
      {message && <p className="mt-1 text-xs text-emerald-300">{message}</p>}
      <button
        className={`${buttonClass(true)} mt-2.5`}
        disabled={save.isPending}
        onClick={() => save.mutate()}
        type="button"
      >
        {save.isPending ? "Saving…" : "Save feeds"}
      </button>
    </div>
  );
}
