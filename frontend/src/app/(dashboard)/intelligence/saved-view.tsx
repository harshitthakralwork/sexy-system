"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { Header } from "@/components/layout/header";
import { Card, EmptyState } from "@/components/ui/card";
import { useSession } from "@/components/providers/session-provider";
import { api } from "@/lib/api/client";
import type { IntelligenceList, IntelligenceResult, SavedItem } from "@/lib/api/types";

export function SavedView() {
  const { csrf, user } = useSession();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const savedResults = useQuery({
    queryKey: ["intelligence", "saved-results"],
    queryFn: () => api.get<IntelligenceList>("/social/results?saved_only=true&limit=200"),
  });
  const savedMeta = useQuery({
    queryKey: ["intelligence-saved"],
    queryFn: () => api.get<SavedItem[]>("/social/saved?limit=500"),
  });

  async function refresh() {
    await queryClient.invalidateQueries({ queryKey: ["intelligence"] });
    await queryClient.invalidateQueries({ queryKey: ["intelligence-saved"] });
  }

  async function unsave(contentId: string) {
    try {
      await api.delete(`/social/results/${contentId}/save`, csrf);
      await refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unsave failed");
    }
  }

  async function convert(result: IntelligenceResult) {
    try {
      const out = await api.post<{ business_id: string; message: string }>(
        `/social/results/${result.id}/convert`,
        undefined,
        csrf,
      );
      setNotice(out.message);
      await refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Convert failed");
    }
  }

  if (!user) return null;
  const metaByContent = new Map((savedMeta.data ?? []).map((s) => [s.content_id, s]));
  const rows = savedResults.data?.items ?? [];

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <Header title="Saved Items" subtitle="Curated opportunities and companies — annotate, export, convert" />
      <main className="flex-1 overflow-y-auto p-4">
        {(notice || error) && (
          <div className="mb-3 text-sm">
            {error && <p className="text-[var(--color-error)]">{error}</p>}
            {notice && <p className="text-[var(--color-muted)]">{notice}</p>}
          </div>
        )}
        <a
          className={buttonClass(false)}
          href={`${apiBase()}/social/results/export?saved_only=true`}
        >
          Export saved CSV
        </a>
        <div className="mt-3">
          {savedResults.isPending ? (
            <EmptyState title="Loading…" description="" />
          ) : rows.length === 0 ? (
            <EmptyState title="Nothing saved yet" description="Save a result from Demand or Business Intelligence." />
          ) : (
            <div className="space-y-3">
              {rows.map((result) => (
                <SavedCard
                  key={result.id}
                  result={result}
                  meta={metaByContent.get(result.id)}
                  csrf={csrf}
                  onUnsave={() => unsave(result.id)}
                  onConvert={() => convert(result)}
                  onSaved={refresh}
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

function SavedCard({
  result,
  meta,
  csrf,
  onUnsave,
  onConvert,
  onSaved,
  onError,
}: {
  result: IntelligenceResult;
  meta?: SavedItem;
  csrf: string | null;
  onUnsave: () => void;
  onConvert: () => void;
  onSaved: () => Promise<void>;
  onError: (message: string) => void;
}) {
  const [note, setNote] = useState(meta?.note ?? "");
  const [tags, setTags] = useState((meta?.tags ?? []).join(", "));
  const [saving, setSaving] = useState(false);

  async function saveMeta() {
    setSaving(true);
    try {
      await api.post(
        `/social/results/${result.id}/save`,
        { note: note.trim() || null, tags: tags.split(",").map((t) => t.trim()).filter(Boolean) },
        csrf,
      );
      await onSaved();
    } catch (caught) {
      onError(caught instanceof Error ? caught.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs uppercase text-[var(--color-muted)]">{result.platform_slug}</span>
            <span className="font-medium">{result.classification ?? "Unclassified"}</span>
            <span className="text-xs text-[var(--color-muted)]">{result.confidence_score ?? 0}%</span>
            {meta?.converted_business_id && (
              <span className="rounded bg-[var(--color-surface-elevated)] px-1.5 py-0.5 text-[10px] text-[var(--color-success)]">
                converted
              </span>
            )}
          </div>
          <p className="mt-1 text-sm">{result.title || (result.content_text ?? "").slice(0, 220)}</p>
          {result.content_url && (
            <a className="mt-1 inline-block text-xs text-[var(--color-primary)] hover:underline" href={result.content_url} target="_blank" rel="noreferrer">
              Open source
            </a>
          )}
        </div>
        <div className="flex shrink-0 gap-2">
          <button className={buttonClass(false)} onClick={onConvert} type="button">
            Convert to lead
          </button>
          <button className={buttonClass(false)} onClick={onUnsave} type="button">
            Remove
          </button>
        </div>
      </div>
      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        <label className="text-sm">
          <span className="text-[var(--color-muted)]">Note</span>
          <input className="mt-1 w-full rounded-md border border-border bg-[var(--color-background)] px-2 py-1.5" value={note} onChange={(e) => setNote(e.target.value)} />
        </label>
        <label className="text-sm">
          <span className="text-[var(--color-muted)]">Tags (comma-separated)</span>
          <input className="mt-1 w-full rounded-md border border-border bg-[var(--color-background)] px-2 py-1.5" value={tags} onChange={(e) => setTags(e.target.value)} />
        </label>
      </div>
      <button className={`${buttonClass(true)} mt-2`} disabled={saving} onClick={saveMeta} type="button">
        {saving ? "Saving…" : "Save note & tags"}
      </button>
    </Card>
  );
}

function apiBase(): string {
  return process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";
}

function buttonClass(active: boolean): string {
  return [
    "rounded-md border px-2.5 py-1.5 text-xs transition-colors disabled:opacity-50",
    active
      ? "border-[var(--color-primary)] bg-[var(--color-primary)] text-white"
      : "border-border text-[var(--color-muted)] hover:border-[var(--color-primary)]",
  ].join(" ");
}
