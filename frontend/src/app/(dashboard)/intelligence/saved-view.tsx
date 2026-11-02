"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";

import { Header } from "@/components/layout/header";
import { Card, EmptyState } from "@/components/ui/card";
import { useSession } from "@/components/providers/session-provider";
import { api } from "@/lib/api/client";
import type { IntelligenceList } from "@/lib/api/types";

export function SavedView() {
  const { csrf, user } = useSession();
  const queryClient = useQueryClient();

  const saved = useQuery({
    queryKey: ["intelligence", "saved-results"],
    queryFn: () => api.get<IntelligenceList>("/social/results?saved_only=true&limit=200"),
  });

  async function unsave(contentId: string) {
    try {
      await api.delete(`/social/results/${contentId}/save`, csrf);
      await queryClient.invalidateQueries({ queryKey: ["intelligence"] });
    } catch {
      /* surfaced via refetch */
    }
  }

  if (!user) return null;
  const rows = saved.data?.items ?? [];

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <Header title="Saved Items" subtitle="Opportunities and companies you chose to keep" />
      <main className="flex-1 overflow-y-auto p-4">
        {saved.isPending ? (
          <EmptyState title="Loading…" description="" />
        ) : rows.length === 0 ? (
          <EmptyState title="Nothing saved yet" description="Save a result from Demand or Business Intelligence." />
        ) : (
          <div className="space-y-3">
            {rows.map((result) => (
              <Card key={result.id}>
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-xs uppercase text-[var(--color-muted)]">{result.platform_slug}</span>
                      <span className="font-medium">{result.classification ?? "Unclassified"}</span>
                      <span className="text-xs text-[var(--color-muted)]">{result.confidence_score ?? 0}%</span>
                    </div>
                    <p className="mt-1 text-sm">{result.title || (result.content_text ?? "").slice(0, 220)}</p>
                    {result.content_url && (
                      <a className="mt-1 inline-block text-xs text-[var(--color-primary)] hover:underline" href={result.content_url} target="_blank" rel="noreferrer">
                        Open source
                      </a>
                    )}
                  </div>
                  <button
                    className="rounded-md border border-border px-2.5 py-1.5 text-xs text-[var(--color-muted)] hover:border-[var(--color-primary)]"
                    onClick={() => unsave(result.id)}
                    type="button"
                  >
                    Remove
                  </button>
                </div>
              </Card>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
