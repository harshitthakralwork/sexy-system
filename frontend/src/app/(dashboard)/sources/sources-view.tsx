"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { Header } from "@/components/layout/header";
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
};

const HEALTH_COPY: Record<string, string> = {
  working: "Answering",
  degraded: "Degraded",
  failed: "Failing",
  unknown: "Never probed",
};

function healthClass(status: string): string {
  if (status === "working") return "text-[var(--color-success)]";
  if (status === "failed") return "text-[var(--color-error)]";
  if (status === "degraded") return "text-[var(--color-warning,--color-primary)]";
  return "text-[var(--color-muted)]";
}

function buttonClass(active: boolean): string {
  return [
    "rounded-md border px-2.5 py-1.5 text-xs transition-colors disabled:opacity-50",
    active
      ? "border-[var(--color-primary)] bg-[var(--color-primary)] text-white"
      : "border-border text-[var(--color-muted)] hover:border-[var(--color-primary)]",
  ].join(" ");
}

function whenSet(value: string | null | undefined): string {
  return value ? new Date(value).toLocaleString() : "never";
}

export function SourcesView() {
  const { user } = useSession();
  const sources = useQuery({
    queryKey: ["sources"],
    queryFn: () => api.get<SourceList>("/sources"),
  });

  if (!user) return null;

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <Header
        title="Source Manager"
        subtitle="Every provider this build can actually query, with its real limits"
      />
      <main className="flex-1 overflow-y-auto p-4">
        {sources.isError && (
          <p className="mb-3 text-sm text-[var(--color-error)]">
            {sources.error instanceof Error ? sources.error.message : "Sources failed to load"}
          </p>
        )}
        <p className="mb-4 text-xs text-[var(--color-muted)]">
          Restricted platforms — LinkedIn, X, Instagram, Facebook, YouTube — are listed under
          Social &rsaquo; Sources with their actual access terms. They appear here only once a
          compliant connector exists, so a card never implies an ability the provider withholds.
        </p>
        {sources.isPending && !sources.isError && (
          <EmptyState title="Reading the registry…" description="" />
        )}
        {sources.data && sources.data.total === 0 && (
          <EmptyState
            title="No sources registered"
            description="The registry fills itself from the adapters this build ships with."
          />
        )}
        <div className="space-y-6">
          {sources.data?.groups.map((group) => (
            <section key={group.category}>
              <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-[var(--color-muted)]">
                {CATEGORY_LABELS[group.category] ?? group.category} · {group.items.length}
              </h2>
              <div className="grid gap-3 lg:grid-cols-2 2xl:grid-cols-3">
                {group.items.map((source) => (
                  <SourceCard key={source.id} source={source} />
                ))}
              </div>
            </section>
          ))}
        </div>
      </main>
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
    <Card className="flex flex-col gap-2">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h3 className="text-sm font-medium">{source.name}</h3>
          <p className="text-xs text-[var(--color-muted)]">
            {source.slug} · {source.adapter_key}
          </p>
        </div>
        <span className={`text-xs font-medium ${healthClass(source.health_status)}`}>
          {HEALTH_COPY[source.health_status] ?? source.health_status}
        </span>
      </div>

      {source.last_error && (
        <p className="text-xs text-[var(--color-error)]">Last error: {source.last_error}</p>
      )}
      {probe && (
        <p className="text-xs text-[var(--color-muted)]">
          Probe: {probe.status}
          {probe.detail ? ` — ${probe.detail}` : ""}
          {probe.response_time_ms != null ? ` (${probe.response_time_ms} ms)` : ""}
        </p>
      )}

      <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
        <dt className="text-[var(--color-muted)]">Use for your account</dt>
        <dd>{source.enabled_for_user ? "Enabled" : "Disabled"}</dd>
        <dt className="text-[var(--color-muted)]">Provider-wide</dt>
        <dd>{source.globally_enabled ? "Enabled" : "Disabled"}</dd>
        <dt className="text-[var(--color-muted)]">Last successful run</dt>
        <dd>{whenSet(source.last_successful_run_at)}</dd>
        <dt className="text-[var(--color-muted)]">Last probe</dt>
        <dd>
          {whenSet(source.last_check_at)}
          {source.last_check_response_ms != null ? ` · ${source.last_check_response_ms} ms` : ""}
        </dd>
        <dt className="text-[var(--color-muted)]">Runs recorded</dt>
        <dd>{source.runs_recorded}</dd>
        <dt className="text-[var(--color-muted)]">Requests made</dt>
        <dd>{source.requests_count}</dd>
        <dt className="text-[var(--color-muted)]">Records returned</dt>
        <dd>{source.records_returned}</dd>
        <dt className="text-[var(--color-muted)]">Records accepted</dt>
        <dd>{source.records_accepted ?? "not reported per source"}</dd>
      </dl>

      <div className="text-xs">
        <p className="text-[var(--color-muted)]">Coverage</p>
        <p>{String(source.coverage["geographic_coverage"] ?? "not stated")}</p>
      </div>
      <div className="text-xs">
        <p className="text-[var(--color-muted)]">Limitations</p>
        <ul className="list-disc space-y-0.5 pl-4">
          <li>{String(source.limitations["rate_limit_notes"] ?? "no rate limit stated")}</li>
          <li>{String(source.limitations["terms_notes"] ?? "no terms stated")}</li>
        </ul>
      </div>

      {feeds.length > 0 && (
        <div className="text-xs">
          <p className="text-[var(--color-muted)]">Your feeds</p>
          <ul className="list-disc pl-4">
            {feeds.map((feed) => (
              <li key={String(feed)} className="truncate">
                {String(feed)}
              </li>
            ))}
          </ul>
        </div>
      )}
      {typeof note === "string" && note && (
        <p className="text-xs text-[var(--color-muted)]">Note: {note}</p>
      )}

      {error && <p className="text-xs text-[var(--color-error)]">{error}</p>}

      <div className="mt-auto flex flex-wrap items-center gap-2">
        <button
          className={buttonClass(!source.enabled_for_user)}
          disabled={toggle.isPending}
          onClick={() => toggle.mutate()}
          type="button"
        >
          {source.enabled_for_user ? "Disable" : "Enable"}
        </button>
        <button
          className={buttonClass(false)}
          disabled={test.isPending}
          onClick={() => test.mutate()}
          type="button"
        >
          {test.isPending ? "Testing…" : "Test connection"}
        </button>
        <button className={buttonClass(false)} onClick={() => setOpen(!open)} type="button">
          {open ? "Hide history" : "View history"}
        </button>
      </div>

      {source.adapter_key === "rss" && <FeedConfig source={source} />}

      {open && (
        <div className="rounded-md border border-border p-2">
          {history.isError && (
            <p className="text-xs text-[var(--color-error)]">
              {history.error instanceof Error ? history.error.message : "History failed to load"}
            </p>
          )}
          {!history.isError && (history.isPending || !history.data) && (
            <p className="text-xs text-[var(--color-muted)]">Loading…</p>
          )}
          {history.data && (
            <>
              <p className="text-xs font-medium text-[var(--color-muted)]">
                Probes ({history.data.checks.length})
              </p>
              {history.data.checks.length === 0 ? (
                <p className="text-xs text-[var(--color-muted)]">Never probed.</p>
              ) : (
                <ul className="mt-1 space-y-0.5 text-xs">
                  {history.data.checks.map((check) => (
                    <li key={check.id}>
                      {new Date(check.checked_at).toLocaleString()} · {check.status}
                      {check.error_message ? ` — ${check.error_message}` : ""}
                    </li>
                  ))}
                </ul>
              )}
              <p className="mt-2 text-xs font-medium text-[var(--color-muted)]">
                Runs ({history.data.runs.length})
              </p>
              {history.data.runs.length === 0 ? (
                <p className="text-xs text-[var(--color-muted)]">No recorded runs.</p>
              ) : (
                <ul className="mt-1 space-y-0.5 text-xs">
                  {history.data.runs.map((run) => (
                    <li key={run.id}>
                      {new Date(run.measured_at).toLocaleString()} · {run.requests_count} req ·{" "}
                      {run.records_returned} returned
                      {run.records_accepted != null ? ` · ${run.records_accepted} accepted` : ""}
                    </li>
                  ))}
                </ul>
              )}
            </>
          )}
        </div>
      )}
    </Card>
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
    <div className="rounded-md border border-border p-2">
      <label className="text-xs">
        <span className="text-[var(--color-muted)]">Feed URLs (one per line, http(s) only)</span>
        <textarea
          className="mt-1 h-20 w-full rounded-md border border-border bg-[var(--color-background)] px-2 py-1.5 text-xs"
          value={value}
          onChange={(event) => setValue(event.target.value)}
        />
      </label>
      {message && <p className="mt-1 text-xs text-[var(--color-muted)]">{message}</p>}
      <button
        className={`${buttonClass(true)} mt-2`}
        disabled={save.isPending}
        onClick={() => save.mutate()}
        type="button"
      >
        {save.isPending ? "Saving…" : "Save feeds"}
      </button>
    </div>
  );
}
