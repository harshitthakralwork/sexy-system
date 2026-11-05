"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { Header } from "@/components/layout/header";
import { Card, EmptyState } from "@/components/ui/card";
import { useSession } from "@/components/providers/session-provider";
import { api } from "@/lib/api/client";
import type { AnalyticsBucket, AnalyticsOut, SavedReport, SavedReportList } from "@/lib/api/types";

const BUCKET_KEYS = [
  "businesses_by_website_status",
  "businesses_by_lifecycle",
  "discovery_jobs_by_status",
  "social_by_classification",
  "social_by_platform",
  "social_by_track_type",
] as const;

type BucketKey = (typeof BUCKET_KEYS)[number];

interface Section {
  key: BucketKey;
  label: string;
  /** Where the count came from, so the number can be traced to a surface. */
  href: string;
  linkLabel: string;
}

const SECTIONS: Section[] = [
  {
    key: "businesses_by_website_status",
    label: "Leads by website status",
    href: "/leads",
    linkLabel: "Leads",
  },
  { key: "businesses_by_lifecycle", label: "Leads by lifecycle", href: "/leads", linkLabel: "Leads" },
  {
    key: "discovery_jobs_by_status",
    label: "Discovery jobs by status",
    href: "/leads",
    linkLabel: "Runs",
  },
  {
    key: "social_by_classification",
    label: "Social results by classification",
    href: "/intelligence/demand",
    linkLabel: "Demand signals",
  },
  { key: "social_by_platform", label: "Social results by source", href: "/social/sources", linkLabel: "Sources" },
  {
    key: "social_by_track_type",
    label: "Social results by track",
    href: "/intelligence/tracks",
    linkLabel: "Tracks",
  },
];

const REPORT_TYPES = ["analytics", "leads", "social"];

function apiBase(): string {
  return process.env.NEXT_PUBLIC_API_BASE_URL ?? "/api/v1";
}

function buttonClass(active: boolean): string {
  return [
    "rounded-full border px-3 py-1.5 text-xs font-semibold transition-all disabled:opacity-40 cursor-pointer",
    active
      ? "refraction-glass-btn border-cyan-400/40 bg-cyan-500/20 text-cyan-200 shadow-[0_0_15px_rgba(0,212,255,0.25)] hover:bg-cyan-500/30 hover:text-white"
      : "border-white/10 bg-white/[0.04] text-white/70 hover:border-white/25 hover:text-white hover:bg-white/[0.08]",
  ].join(" ");
}

export function AnalyticsView() {
  const { user } = useSession();
  const summary = useQuery({
    queryKey: ["analytics"],
    queryFn: () => api.get<AnalyticsOut>("/analytics"),
  });

  if (!user) return null;

  const data = summary.data;
  const totalBucketed = data
    ? BUCKET_KEYS.reduce((sum, key) => sum + data[key].reduce((n, b) => n + b.count, 0), 0)
    : 0;

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <Header
        title="Analytics"
        subtitle="Counts over the rows you own — every figure is a group-by, never a sample"
      />
      <main className="flex-1 overflow-y-auto scroll-smooth p-4 lg:p-6">
        {summary.isError && (
          <p className="mb-3 text-sm text-[var(--color-error)]">
            {summary.error instanceof Error ? summary.error.message : "Analytics failed to load"}
          </p>
        )}
        {data && (
          <div className="flex flex-wrap items-center gap-3">
            <Card className="flex-1">
              <p className="text-xs uppercase tracking-wide text-[var(--color-muted)]">Leads</p>
              <p className="mt-1 text-2xl font-semibold">{data.leads_total}</p>
              <p className="mt-1 text-xs text-[var(--color-muted)]">
                counted from your non-deleted businesses
              </p>
            </Card>
            <a className={buttonClass(true)} href={`${apiBase()}/analytics/export`}>
              Export CSV
            </a>
          </div>
        )}

        {data && totalBucketed === 0 && data.leads_total === 0 ? (
          <div className="mt-4">
            <EmptyState
              title="No data to count yet"
              description="Run a discovery job or a social track; the numbers below fill in from what you collect."
            />
          </div>
        ) : (
          <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {SECTIONS.map((section) => (
              <BucketCard
                key={section.key}
                section={section}
                buckets={data ? data[section.key] : []}
              />
            ))}
          </div>
        )}

        {data && (
        <p className="mt-4 rounded-lg border border-white/[0.06] bg-white/[0.02] px-3 py-2 text-xs text-white/45">
            Generated {new Date(data.generated_at).toLocaleString()} ·{" "}
            {BUCKET_KEYS.length} data groups
          </p>
        )}

        <ReportsPanel />
      </main>
    </div>
  );
}

function BucketCard({ section, buckets }: { section: Section; buckets: AnalyticsBucket[] }) {
  const max = buckets.reduce((n, b) => Math.max(n, b.count), 0);
  const total = buckets.reduce((n, b) => n + b.count, 0);
  return (
    <Card>
      <div className="flex items-baseline justify-between gap-2">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--color-muted)]">
          {section.label}
        </h3>
        <span className="text-xs text-[var(--color-muted)]">{total}</span>
      </div>
      {buckets.length === 0 ? (
        <p className="mt-2 text-sm text-[var(--color-muted)]">Nothing recorded yet.</p>
      ) : (
        <ul className="mt-2 space-y-2">
          {buckets.map((bucket) => (
            <li key={bucket.key}>
              <div className="flex items-baseline justify-between gap-2 text-sm">
                <span className="truncate">{bucket.key}</span>
                <span className="tabular-nums text-[var(--color-muted)]">{bucket.count}</span>
              </div>
              <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-[var(--color-surface-raised,rgba(139,92,246,0.15))]">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-cyan-400 to-sky-500 shadow-[0_0_8px_rgba(0,212,255,0.4)]"
                  style={{ width: `${max ? (bucket.count / max) * 100 : 0}%` }}
                />
              </div>
            </li>
          ))}
        </ul>
      )}
      <a
        className="mt-3 inline-block text-xs text-[var(--color-muted)] hover:text-[var(--color-primary)]"
        href={section.href}
      >
        Open {section.linkLabel}
      </a>
    </Card>
  );
}

function ReportsPanel() {
  const { csrf } = useSession();
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [reportType, setReportType] = useState("analytics");
  const [error, setError] = useState<string | null>(null);

  const reports = useQuery({
    queryKey: ["analytics-reports"],
    queryFn: () => api.get<SavedReportList>("/analytics/reports?limit=50"),
  });

  const save = useMutation({
    mutationFn: () =>
      api.post<SavedReport>(
        "/analytics/reports",
        { name: name.trim(), report_type: reportType },
        csrf,
      ),
    onSuccess: async () => {
      setName("");
      setError(null);
      await queryClient.invalidateQueries({ queryKey: ["analytics-reports"] });
    },
    onError: (caught) =>
      setError(caught instanceof Error ? caught.message : "Could not save the report"),
  });

  const remove = useMutation({
    mutationFn: (id: string) => api.delete(`/analytics/reports/${id}`, csrf),
    onSuccess: async () => {
      setError(null);
      await queryClient.invalidateQueries({ queryKey: ["analytics-reports"] });
    },
    onError: (caught) =>
      setError(caught instanceof Error ? caught.message : "Could not delete the report"),
  });

  const rows = reports.data?.items ?? [];

  return (
    <section className="mt-8 scroll-mt-6 rounded-2xl border border-white/[0.1] bg-black/20 p-4 lg:p-5" id="saved-reports">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div><h2 className="text-base font-semibold">Saved reports</h2>
      <p className="mt-1 text-xs text-[var(--color-muted)]">
        A report stores the counts as they were at capture time, so it does not drift when new data
        arrives.
      </p>
        </div><span className="rounded-full border border-white/10 bg-white/[0.04] px-2.5 py-1 text-[10px] uppercase tracking-wide text-white/45">Saved counts</span>
      </div>
      {error && <p className="mt-2 text-sm text-[var(--color-error)]">{error}</p>}

      <div className="mt-4 grid gap-3 sm:grid-cols-[minmax(0,1fr)_180px_auto] sm:items-end">
        <label className="text-sm">
          <span className="text-[var(--color-muted)]">Name</span>
          <input
            className="mt-1 w-full rounded-xl border border-white/10 bg-[var(--color-background)] px-3 py-2"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Week 1 funnel"
          />
        </label>
        <label className="text-sm">
          <span className="text-[var(--color-muted)]">Type</span>
          <select
            className="mt-1 block w-full rounded-xl border border-white/10 bg-[var(--color-background)] px-3 py-2"
            value={reportType}
            onChange={(e) => setReportType(e.target.value)}
          >
            {REPORT_TYPES.map((type) => (
              <option key={type} value={type}>
                {type}
              </option>
            ))}
          </select>
        </label>
        <button
          className={buttonClass(true)}
          disabled={!name.trim() || save.isPending}
          onClick={() => save.mutate()}
          type="button"
        >
          {save.isPending ? "Saving…" : "Save current numbers"}
        </button>
      </div>

      <div className="mt-3 space-y-2">
        {reports.isPending ? (
          <p className="text-sm text-[var(--color-muted)]">Loading reports…</p>
        ) : rows.length === 0 ? (
          <EmptyState
            title="No saved reports"
            description="Save the numbers above to keep a point-in-time record."
          />
        ) : (
          rows.map((report) => (
            <Card key={report.id} className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-sm font-medium">{report.name}</p>
                <p className="text-xs text-[var(--color-muted)]">
                  {report.report_type} · captured{" "}
                  {report.captured_at ? new Date(report.captured_at).toLocaleString() : "—"}
                  {snapshotLeads(report) !== null && ` · ${snapshotLeads(report)} leads`}
                </p>
              </div>
              <div className="flex items-center gap-2">
                <a className={buttonClass(false)} href={`${apiBase()}/analytics/reports/${report.id}/export`}>
                  Export
                </a>
                <button
                  className={buttonClass(false)}
                  disabled={remove.isPending}
                  onClick={() => remove.mutate(report.id)}
                  type="button"
                >
                  Delete
                </button>
              </div>
            </Card>
          ))
        )}
      </div>
    </section>
  );
}

function snapshotLeads(report: SavedReport): number | null {
  const value = report.snapshot["leads_total"];
  return typeof value === "number" ? value : null;
}
