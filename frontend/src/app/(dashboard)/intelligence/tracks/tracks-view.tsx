"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { Header } from "@/components/layout/header";
import { Card, EmptyState } from "@/components/ui/card";
import { useSession } from "@/components/providers/session-provider";
import { api } from "@/lib/api/client";
import type { DiscoveryRun, DiscoveryRunList, Track, TrackList } from "@/lib/api/types";

const csv = (value: string) =>
  value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);

export function TracksView() {
  const { csrf, user } = useSession();
  const queryClient = useQueryClient();
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const tracks = useQuery({
    queryKey: ["intelligence", "tracks"],
    queryFn: () => api.get<TrackList>("/social/tracks?limit=200"),
  });

  const platforms = useQuery({
    queryKey: ["social", "platforms"],
    queryFn: () => api.get<{ slug: string; name: string; is_enabled: boolean }[]>("/social/platforms"),
  });

  async function refresh() {
    await queryClient.invalidateQueries({ queryKey: ["intelligence", "tracks"] });
  }

  if (!user) return null;
  const rows = tracks.data?.items ?? [];
  const enabledPlatforms = (platforms.data ?? []).filter((p) => p.is_enabled);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <Header title="Discovery Tracks" subtitle="Configure, run and schedule demand and business searches" />
      <main className="flex-1 overflow-y-auto p-4">
        <CreateTrackForm
          csrf={csrf}
          platforms={enabledPlatforms}
          onCreated={async (message) => {
            setNotice(message);
            await refresh();
          }}
          onError={setError}
        />

        {(notice || error) && (
          <div className="mt-3 text-sm">
            {error && <p className="text-[var(--color-error)]">{error}</p>}
            {notice && <p className="text-[var(--color-muted)]">{notice}</p>}
          </div>
        )}

        <div className="mt-4">
          {tracks.isPending ? (
            <EmptyState title="Loading tracks…" description="" />
          ) : rows.length === 0 ? (
            <EmptyState title="No tracks yet" description="Create one above to start discovering." />
          ) : (
            <div className="space-y-3">
              {rows.map((track) => (
                <TrackCard
                  key={track.id}
                  track={track}
                  csrf={csrf}
                  onChanged={async (message) => {
                    setNotice(message);
                    await refresh();
                  }}
                  onError={setError}
                />
              ))}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}

function CreateTrackForm({
  csrf,
  platforms,
  onCreated,
  onError,
}: {
  csrf: string | null;
  platforms: { slug: string; name: string }[];
  onCreated: (message: string) => Promise<void>;
  onError: (message: string) => void;
}) {
  const [name, setName] = useState("");
  const [trackType, setTrackType] = useState("demand");
  const [keywords, setKeywords] = useState("");
  const [selected, setSelected] = useState<string[]>(["facebook"]);
  const [schedule, setSchedule] = useState<"none" | "interval" | "cron">("none");
  const [intervalSeconds, setIntervalSeconds] = useState(3600);
  const [cron, setCron] = useState("0 9 * * *");
  const [busy, setBusy] = useState(false);

  function togglePlatform(slug: string) {
    setSelected((current) => (current.includes(slug) ? current.filter((s) => s !== slug) : [...current, slug]));
  }

  async function submit() {
    if (!name.trim() || selected.length === 0) {
      onError("A track needs a name and at least one source.");
      return;
    }
    const sourceConfig: Record<string, unknown> = {};
    let frequencyConfig: Record<string, unknown> | null = null;
    if (schedule === "interval") frequencyConfig = { interval_seconds: intervalSeconds };
    else if (schedule === "cron") frequencyConfig = { cron: cron.trim() };

    setBusy(true);
    try {
      await api.post(
        "/social/tracks",
        {
          name: name.trim(),
          track_type: trackType,
          keywords: csv(keywords),
          platforms: selected,
          source_config: sourceConfig,
          frequency_config: frequencyConfig,
        },
        csrf,
      );
      setName("");
      setKeywords("");
      await onCreated("Track created.");
    } catch (caught) {
      onError(caught instanceof Error ? caught.message : "Create failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--color-muted)]">New track</h3>
      <div className="mt-2 flex flex-wrap items-end gap-3">
        <label className="min-w-48 flex-1 text-sm">
          <span className="text-[var(--color-muted)]">Name</span>
          <input className="mt-1 w-full rounded-md border border-border bg-[var(--color-background)] px-2 py-1.5" value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label className="text-sm">
          <span className="text-[var(--color-muted)]">Type</span>
          <select className="mt-1 w-32 rounded-md border border-border bg-[var(--color-background)] px-2 py-1.5" value={trackType} onChange={(e) => setTrackType(e.target.value)}>
            <option value="demand">demand</option>
            <option value="business">business</option>
          </select>
        </label>
        <label className="min-w-48 flex-1 text-sm">
          <span className="text-[var(--color-muted)]">Keywords (comma-separated)</span>
          <input className="mt-1 w-full rounded-md border border-border bg-[var(--color-background)] px-2 py-1.5" value={keywords} onChange={(e) => setKeywords(e.target.value)} placeholder="looking for web agency, need a developer" />
        </label>
      </div>

      <div className="mt-3">
        <span className="text-xs text-[var(--color-muted)]">Sources</span>
        <div className="mt-1 flex flex-wrap gap-3">
          {platforms.map((p) => (
            <label key={p.slug} className="flex items-center gap-1.5 text-sm">
              <input type="checkbox" checked={selected.includes(p.slug)} onChange={() => togglePlatform(p.slug)} />
              {p.name}
            </label>
          ))}
        </div>
      </div>

      <div className="mt-3 flex flex-wrap items-end gap-3">
        <label className="text-sm">
          <span className="text-[var(--color-muted)]">Schedule</span>
          <select className="mt-1 w-28 rounded-md border border-border bg-[var(--color-background)] px-2 py-1.5" value={schedule} onChange={(e) => setSchedule(e.target.value as "none" | "interval" | "cron")}>
            <option value="none">manual</option>
            <option value="interval">interval</option>
            <option value="cron">cron</option>
          </select>
        </label>
        {schedule === "interval" && (
          <label className="text-sm">
            <span className="text-[var(--color-muted)]">Every (seconds)</span>
            <input className="mt-1 w-28 rounded-md border border-border bg-[var(--color-background)] px-2 py-1.5" type="number" min={60} value={intervalSeconds} onChange={(e) => setIntervalSeconds(Number(e.target.value) || 3600)} />
          </label>
        )}
        {schedule === "cron" && (
          <label className="text-sm">
            <span className="text-[var(--color-muted)]">Cron</span>
            <input className="mt-1 w-40 rounded-md border border-border bg-[var(--color-background)] px-2 py-1.5" value={cron} onChange={(e) => setCron(e.target.value)} />
          </label>
        )}
        <button className={buttonClass(true)} disabled={busy || !name.trim() || selected.length === 0} onClick={submit} type="button">
          {busy ? "Creating…" : "Create track"}
        </button>
      </div>
    </Card>
  );
}

function TrackCard({
  track,
  csrf,
  onChanged,
  onError,
}: {
  track: Track;
  csrf: string | null;
  onChanged: (message: string) => Promise<void>;
  onError: (message: string) => void;
}) {
  const queryClient = useQueryClient();
  const [showRuns, setShowRuns] = useState(false);
  const [running, setRunning] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const runs = useQuery({
    queryKey: ["intelligence", "runs", track.id],
    queryFn: () => api.get<DiscoveryRunList>(`/social/tracks/${track.id}/runs?limit=10`),
    enabled: showRuns,
  });

  async function runNow() {
    setRunning(true);
    try {
      await api.post(`/social/tracks/${track.id}/run`, undefined, csrf);
      setShowRuns(true);
      await queryClient.invalidateQueries({ queryKey: ["intelligence", "runs", track.id] });
      await onChanged("Run started; refresh Runs to see the result.");
    } catch (caught) {
      onError(caught instanceof Error ? caught.message : "Run failed");
    } finally {
      setRunning(false);
    }
  }

  async function togglePause() {
    try {
      await api.patch("/social/tracks/" + track.id, { is_paused: !track.is_paused }, csrf);
      await onChanged(track.is_paused ? "Track resumed." : "Track paused.");
    } catch (caught) {
      onError(caught instanceof Error ? caught.message : "Update failed");
    }
  }

  async function remove() {
    setDeleting(true);
    try {
      await api.delete(`/social/tracks/${track.id}`, csrf);
      await onChanged("Track deleted.");
    } catch (caught) {
      onError(caught instanceof Error ? caught.message : "Delete failed");
      setDeleting(false);
    }
  }

  const terms = [...track.keywords, ...track.exact_phrases].slice(0, 4).join(", ");
  const scheduleLabel = track.frequency_config
    ? "interval_seconds" in track.frequency_config
      ? `every ${track.frequency_config.interval_seconds}s`
      : `cron ${String(track.frequency_config.cron ?? "")}`
    : "manual";

  return (
    <Card>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="font-medium">{track.name}</span>
            <span className="rounded bg-[var(--color-surface-elevated)] px-1.5 py-0.5 text-[10px] text-[var(--color-muted)]">{track.track_type}</span>
            {track.is_paused && <span className="text-[10px] text-[var(--color-warning)]">paused</span>}
          </div>
          <p className="mt-1 text-xs text-[var(--color-muted)]">
            sources: {track.platforms.join(", ") || "none"} · {scheduleLabel} · next{" "}
            {track.next_run_at ? new Date(track.next_run_at).toLocaleString() : "—"}
          </p>
          {terms && <p className="mt-1 text-xs text-[var(--color-muted)]">terms: {terms}</p>}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button className={buttonClass(true)} disabled={running || track.platforms.length === 0} onClick={runNow} type="button">
            {running ? "Running…" : "Run now"}
          </button>
          <button className={buttonClass(false)} onClick={togglePause} type="button">
            {track.is_paused ? "Resume" : "Pause"}
          </button>
          <button className={buttonClass(false)} onClick={() => setShowRuns((v) => !v)} type="button">
            {showRuns ? "Hide runs" : "Runs"}
          </button>
          <button className={buttonClass(false)} disabled={deleting} onClick={remove} type="button">
            {deleting ? "Deleting…" : "Delete"}
          </button>
        </div>
      </div>

      {showRuns && (
        <div className="mt-3 overflow-x-auto rounded-lg border border-border">
          <table className="w-full min-w-[640px] text-sm">
            <thead>
              <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-[var(--color-muted)]">
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2">Trigger</th>
                <th className="px-3 py-2">New</th>
                <th className="px-3 py-2">Dupes</th>
                <th className="px-3 py-2">When</th>
              </tr>
            </thead>
            <tbody>
              {(runs.data?.items ?? []).map((run: DiscoveryRun) => (
                <tr key={run.id} className="border-b border-border/60">
                  <td className="px-3 py-2">
                    <span className={statusTone(run.status)}>{run.status}</span>
                  </td>
                  <td className="px-3 py-2 text-[var(--color-muted)]">{run.trigger_type}</td>
                  <td className="px-3 py-2">{run.stored_new}</td>
                  <td className="px-3 py-2">{run.duplicates}</td>
                  <td className="px-3 py-2 text-[var(--color-muted)]">{new Date(run.created_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {(runs.data?.items ?? []).length === 0 && (
            <p className="px-3 py-2 text-xs text-[var(--color-muted)]">No runs yet.</p>
          )}
        </div>
      )}
    </Card>
  );
}

function statusTone(status: string): string {
  if (status === "completed") return "text-[var(--color-success)]";
  if (status === "failed") return "text-[var(--color-error)]";
  if (status === "completed_with_warnings") return "text-[var(--color-warning)]";
  return "text-[var(--color-muted)]";
}

function buttonClass(active: boolean): string {
  return [
    "rounded-full border px-3 py-1.5 text-xs font-semibold transition-all disabled:opacity-40 cursor-pointer",
    active
      ? "refraction-glass-btn border-cyan-400/40 bg-cyan-500/20 text-cyan-200 shadow-[0_0_15px_rgba(0,212,255,0.25)] hover:bg-cyan-500/30 hover:text-white"
      : "border-white/10 bg-white/[0.04] text-white/70 hover:border-white/25 hover:text-white hover:bg-white/[0.08]",
  ].join(" ");
}
