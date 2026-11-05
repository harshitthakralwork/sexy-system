"use client";

import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { Header } from "@/components/layout/header";
import { Card, EmptyState } from "@/components/ui/card";
import { useSession } from "@/components/providers/session-provider";
import { api } from "@/lib/api/client";
import type { IntelligenceList, IntelligenceResult } from "@/lib/api/types";

const PAGE_SIZE = 25;

/** Shared Demand / Business Intelligence results browser over real stored data. */
export function IntelligenceView({ trackType }: { trackType: "demand" | "business" }) {
  const { csrf } = useSession();
  const queryClient = useQueryClient();

  const [platformFilter, setPlatformFilter] = useState("");
  const [classification, setClassification] = useState("");
  const [minConfidence, setMinConfidence] = useState("");
  const [needsReview, setNeedsReview] = useState(false);
  const [savedOnly, setSavedOnly] = useState(false);
  const [text, setText] = useState("");
  const [applied, setApplied] = useState("");
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const params = useMemo(() => {
    const search = new URLSearchParams({
      track_type: trackType,
      limit: String(PAGE_SIZE),
      offset: String(offset),
    });
    if (platformFilter) search.set("platform_slug", platformFilter);
    if (classification.trim()) search.set("classification", classification.trim());
    if (minConfidence) search.set("min_confidence", minConfidence);
    if (needsReview) search.set("needs_review", "true");
    if (savedOnly) search.set("saved_only", "true");
    if (applied) search.set("query", applied);
    return search.toString();
  }, [trackType, platformFilter, classification, minConfidence, needsReview, savedOnly, applied, offset]);

  const results = useQuery({
    queryKey: ["intelligence", trackType, params],
    queryFn: () => api.get<IntelligenceList>(`/social/results?${params}`),
  });

  const platforms = useQuery({
    queryKey: ["social", "platforms"],
    queryFn: () => api.get<{ slug: string; name: string; is_enabled: boolean }[]>("/social/platforms"),
  });

  const total = results.data?.total ?? 0;
  const rows = results.data?.items ?? [];
  const enabledPlatforms = (platforms.data ?? []).filter((p) => p.is_enabled);

  // Which of the shown rows are already saved (for the toggle label).
  const savedList = useQuery({
    queryKey: ["intelligence-saved"],
    queryFn: () => api.get<{ content_id: string }[]>("/social/saved?limit=500"),
  });
  const savedIds = new Set((savedList.data ?? []).map((s) => s.content_id));

  const title = trackType === "demand" ? "Demand Intelligence" : "Business Intelligence";
  const subtitle =
    trackType === "demand"
      ? "Public conversations where someone appears to need a service"
      : "Companies, startups and commercial signals worth researching";

  async function toggleSave(result: IntelligenceResult) {
    try {
      if (savedIds.has(result.id)) {
        await api.delete(`/social/results/${result.id}/save`, csrf);
      } else {
        await api.post(`/social/results/${result.id}/save`, { note: null, tags: [] }, csrf);
      }
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["intelligence"] }),
        queryClient.invalidateQueries({ queryKey: ["intelligence-saved"] }),
      ]);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Save failed");
    }
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <Header title={title} subtitle={subtitle} />
      <main className="flex-1 overflow-y-auto p-4">
        <Card>
          <div className="flex flex-wrap items-end gap-3">
            <label className="text-sm">
              <span className="text-[var(--color-muted)]">Platform</span>
              <select
                className="mt-1 w-40 rounded-md border border-border bg-[var(--color-background)] px-2 py-1.5"
                value={platformFilter}
                onChange={(e) => {
                  setPlatformFilter(e.target.value);
                  setOffset(0);
                }}
              >
                <option value="">any</option>
                {enabledPlatforms.map((p) => (
                  <option key={p.slug} value={p.slug}>
                    {p.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="text-sm">
              <span className="text-[var(--color-muted)]">Classification</span>
              <input
                className="mt-1 w-40 rounded-md border border-border bg-[var(--color-background)] px-2 py-1.5"
                value={classification}
                onChange={(e) => setClassification(e.target.value)}
                placeholder={trackType === "demand" ? "Agency Search" : "Startup"}
              />
            </label>
            <label className="text-sm">
              <span className="text-[var(--color-muted)]">Min confidence</span>
              <input
                className="mt-1 w-24 rounded-md border border-border bg-[var(--color-background)] px-2 py-1.5"
                type="number"
                min={0}
                max={100}
                value={minConfidence}
                onChange={(e) => setMinConfidence(e.target.value)}
              />
            </label>
            <label className="min-w-44 flex-1 text-sm">
              <span className="text-[var(--color-muted)]">Search text</span>
              <input
                className="mt-1 w-full rounded-md border border-border bg-[var(--color-background)] px-2 py-1.5"
                value={text}
                onChange={(e) => setText(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    setApplied(text.trim());
                    setOffset(0);
                  }
                }}
              />
            </label>
            <label className="flex items-center gap-1.5 text-sm">
              <input
                type="checkbox"
                checked={needsReview}
                onChange={(e) => {
                  setNeedsReview(e.target.checked);
                  setOffset(0);
                }}
              />
              needs review
            </label>
            <label className="flex items-center gap-1.5 text-sm">
              <input
                type="checkbox"
                checked={savedOnly}
                onChange={(e) => {
                  setSavedOnly(e.target.checked);
                  setOffset(0);
                }}
              />
              saved only
            </label>
            <button className={buttonClass(false)} onClick={() => { setApplied(text.trim()); setOffset(0); }} type="button">
              Apply
            </button>
            <a
              className={buttonClass(false)}
              href={`${apiBase()}/social/results/export?track_type=${trackType}`}
            >
              Export CSV
            </a>
          </div>

          {error && <p className="mt-2 text-sm text-[var(--color-error)]">{error}</p>}
          {results.isError && (
            <p className="mt-2 text-sm text-[var(--color-error)]">
              Results could not be loaded: {results.error instanceof Error ? results.error.message : ""}
            </p>
          )}
        </Card>

        <div className="mt-4">
          {results.isPending ? (
            <EmptyState title="Loading…" description="" />
          ) : rows.length === 0 ? (
            <EmptyState
              title={trackType === "demand" ? "No demand signals yet" : "No business signals yet"}
              description="Create a discovery track and run it; results appear here."
            />
          ) : (
            <div className="space-y-3">
              {rows.map((result) => (
                <ResultCard
                  key={result.id}
                  result={result}
                  saved={savedIds.has(result.id)}
                  onToggleSave={() => toggleSave(result)}
                />
              ))}
            </div>
          )}

          {total > PAGE_SIZE && (
            <div className="mt-3 flex items-center justify-between text-sm text-[var(--color-muted)]">
              <span>
                Showing {total === 0 ? 0 : offset + 1}–{Math.min(offset + PAGE_SIZE, total)} of {total}
              </span>
              <div className="flex gap-2">
                <button className={buttonClass(false)} disabled={offset === 0} onClick={() => setOffset((v) => Math.max(0, v - PAGE_SIZE))} type="button">
                  Previous
                </button>
                <button className={buttonClass(false)} disabled={offset + PAGE_SIZE >= total} onClick={() => setOffset((v) => v + PAGE_SIZE)} type="button">
                  Next
                </button>
              </div>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}

function ResultCard({
  result,
  saved,
  onToggleSave,
}: {
  result: IntelligenceResult;
  saved: boolean;
  onToggleSave: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const confidence = result.confidence_score ?? 0;
  const preview = (result.content_text ?? result.snippet ?? "").slice(0, 220);

  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs uppercase text-[var(--color-muted)]">{result.platform_slug}</span>
            <span className="font-medium">{result.classification ?? "Unclassified"}</span>
            <span className={`text-xs ${confidence >= 50 ? "text-[var(--color-success)]" : "text-[var(--color-muted)]"}`}>
              {confidence}% confidence
            </span>
            {result.needs_review && (
              <span className="rounded bg-[var(--color-surface-elevated)] px-1.5 py-0.5 text-[10px] text-[var(--color-warning)]">
                needs review
              </span>
            )}
            <span className="text-[10px] text-[var(--color-muted)]">{result.retrieval_status}</span>
          </div>
          <p className="mt-1 text-sm">{result.title || preview || "(no text captured)"}</p>
          {preview && result.title && <p className="mt-1 text-xs text-[var(--color-muted)]">{preview}</p>}
          {result.matched_terms.length > 0 && (
            <p className="mt-1 text-xs text-[var(--color-muted)]">matched: {result.matched_terms.join(", ")}</p>
          )}
          <p className="mt-1 text-xs text-[var(--color-muted)]">
            discovered {result.discovered_at ? new Date(result.discovered_at).toLocaleString() : "—"}
            {result.published_at ? ` · published ${new Date(result.published_at).toLocaleDateString()}` : ""}
            {result.source_attribution.length > 1 ? ` · ${result.source_attribution.length} sources` : ""}
          </p>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-2">
          <div className="flex gap-2">
            <button className={buttonClass(false)} onClick={() => setExpanded((v) => !v)} type="button">
              {expanded ? "Hide" : "Evidence"}
            </button>
            <button className={buttonClass(!saved)} onClick={onToggleSave} type="button">
              {saved ? "Saved" : "Save"}
            </button>
          </div>
          {result.content_url && (
            <a
              className="text-xs text-[var(--color-primary)] underline-offset-2 hover:underline"
              href={result.content_url}
              target="_blank"
              rel="noreferrer"
            >
              Open source
            </a>
          )}
        </div>
      </div>
      {expanded && (
        <div className="mt-3 border-t border-border pt-2">
          {result.evidence.length === 0 ? (
            <p className="text-xs text-[var(--color-muted)]">No contributing evidence recorded.</p>
          ) : (
            <ul className="space-y-1">
              {result.evidence.map((e, i) => (
                <li key={i} className="text-xs text-[var(--color-muted)]">
                  <span className="font-medium">{String(e.rule ?? "")}</span>
                  {e.matched ? ` → ${JSON.stringify(e.matched)}` : ""}
                  {e.contribution != null ? ` (${String(e.contribution)})` : ""}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </Card>
  );
}

function apiBase(): string {
  return process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000/api/v1";
}

function buttonClass(active: boolean): string {
  return [
    "rounded-full border px-3 py-1.5 text-xs font-semibold transition-all disabled:opacity-40 cursor-pointer",
    active
      ? "refraction-glass-btn border-cyan-400/40 bg-cyan-500/20 text-cyan-200 shadow-[0_0_15px_rgba(0,212,255,0.25)] hover:bg-cyan-500/30 hover:text-white"
      : "border-white/10 bg-white/[0.04] text-white/70 hover:border-white/25 hover:text-white hover:bg-white/[0.08]",
  ].join(" ");
}
