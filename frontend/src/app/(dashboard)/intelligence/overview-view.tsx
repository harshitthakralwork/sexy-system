"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";

import { Header } from "@/components/layout/header";
import { Card, CardValue, CardFootnote, EmptyState } from "@/components/ui/card";
import { useSession } from "@/components/providers/session-provider";
import { api } from "@/lib/api/client";
import type { IntelligenceList, SavedItem, TrackList } from "@/lib/api/types";

function useTotal(track: Record<string, string>) {
  return useQuery({
    queryKey: ["intelligence", "overview", "total", track],
    queryFn: async () => {
      const search = new URLSearchParams({ limit: "1", ...track });
      const res = await api.get<IntelligenceList>(`/social/results?${search.toString()}`);
      return res.total;
    },
  });
}

export function OverviewView() {
  const { user } = useSession();

  const demand = useTotal({ track_type: "demand" });
  const business = useTotal({ track_type: "business" });
  const highConfidence = useTotal({ min_confidence: "70" });
  const needsReview = useTotal({ needs_review: "true" });

  const tracks = useQuery({
    queryKey: ["intelligence", "tracks"],
    queryFn: () => api.get<TrackList>("/social/tracks?limit=1"),
  });
  const saved = useQuery({
    queryKey: ["intelligence-saved"],
    queryFn: () => api.get<SavedItem[]>("/social/saved?limit=500"),
  });
  const breakdown = useQuery({
    queryKey: ["intelligence", "overview", "breakdown"],
    queryFn: () => api.get<IntelligenceList>("/social/results?limit=200"),
  });

  const { byPlatform, byClassification } = useMemo(() => {
    const items = breakdown.data?.items ?? [];
    const platform = new Map<string, number>();
    const classification = new Map<string, number>();
    for (const item of items) {
      platform.set(item.platform_slug ?? "unknown", (platform.get(item.platform_slug ?? "unknown") ?? 0) + 1);
      const key = item.classification ?? "Unclassified";
      classification.set(key, (classification.get(key) ?? 0) + 1);
    }
    return {
      byPlatform: [...platform.entries()].sort((a, b) => b[1] - a[1]),
      byClassification: [...classification.entries()].sort((a, b) => b[1] - a[1]),
    };
  }, [breakdown.data]);

  if (!user) return null;

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <Header title="Intelligence Overview" subtitle="What discovery has actually collected — from real queries" />
      <main className="flex-1 overflow-y-auto p-4">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <Card>
            <CardFootnote>Demand signals</CardFootnote>
            <CardValue>{demand.data ?? "—"}</CardValue>
          </Card>
          <Card>
            <CardFootnote>Business signals</CardFootnote>
            <CardValue>{business.data ?? "—"}</CardValue>
          </Card>
          <Card>
            <CardFootnote>High-confidence (≥70)</CardFootnote>
            <CardValue>{highConfidence.data ?? "—"}</CardValue>
          </Card>
          <Card>
            <CardFootnote>Needs review</CardFootnote>
            <CardValue>{needsReview.data ?? "—"}</CardValue>
          </Card>
          <Card>
            <CardFootnote>Discovery tracks</CardFootnote>
            <CardValue>{tracks.data?.total ?? "—"}</CardValue>
          </Card>
          <Card>
            <CardFootnote>Saved items</CardFootnote>
            <CardValue>{saved.data?.length ?? "—"}</CardValue>
          </Card>
        </div>

        <p className="mt-2 text-xs text-[var(--color-muted)]">
          Counts reflect stored records only. The totals below summarize up to the 200 most recent results,
          labelled by platform and classification.
        </p>

        <div className="mt-4 grid gap-3 lg:grid-cols-2">
          <Card>
            <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--color-muted)]">
              By platform
            </h3>
            {byPlatform.length === 0 ? (
              <EmptyState title="No results yet" description="Create and run a discovery track." />
            ) : (
              <ul className="mt-2 space-y-1 text-sm">
                {byPlatform.map(([slug, count]) => (
                  <li key={slug} className="flex justify-between">
                    <span>{slug}</span>
                    <span className="text-[var(--color-muted)]">{count}</span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
          <Card>
            <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--color-muted)]">
              By classification
            </h3>
            {byClassification.length === 0 ? (
              <EmptyState title="No classified results yet" description="" />
            ) : (
              <ul className="mt-2 space-y-1 text-sm">
                {byClassification.map(([name, count]) => (
                  <li key={name} className="flex justify-between">
                    <span>{name}</span>
                    <span className="text-[var(--color-muted)]">{count}</span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      </main>
    </div>
  );
}
