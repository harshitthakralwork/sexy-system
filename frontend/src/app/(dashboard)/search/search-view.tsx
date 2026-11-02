"use client";

import { useState } from "react";
import Link from "next/link";

import { Header } from "@/components/layout/header";
import { Card, EmptyState } from "@/components/ui/card";
import { useSession } from "@/components/providers/session-provider";
import { api } from "@/lib/api/client";
import type { GlobalSearchItem, GlobalSearchOut, SearchGroup } from "@/lib/api/types";

const GROUP_LABELS: Record<string, string> = {
  businesses: "Leads",
  startups: "Startups",
  social_results: "Social intelligence",
  saved: "Saved items",
  tracks: "Discovery tracks",
};

// Where each kind links to, so a hit is actionable rather than a dead label.
function itemHref(kind: string, id: string): string | null {
  switch (kind) {
    case "business":
      return `/leads/${id}`;
    case "startup":
      return `/startups/${id}`;
    case "track":
      return "/intelligence/tracks";
    case "saved":
      return "/intelligence/saved";
    case "social_result":
      return "/intelligence/demand";
    default:
      return null;
  }
}

export function SearchView() {
  const { user } = useSession();
  const [term, setTerm] = useState("");
  const [submitted, setSubmitted] = useState("");
  const [data, setData] = useState<GlobalSearchOut | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function runSearch(next: string) {
    const q = next.trim();
    setSubmitted(q);
    if (!q) {
      setData(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      setData(await api.get<GlobalSearchOut>(`/search?q=${encodeURIComponent(q)}&limit=10`));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Search failed");
    } finally {
      setLoading(false);
    }
  }

  if (!user) return null;

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <Header title="Global Search" subtitle="One query across your leads, startups and social intelligence" />
      <main className="flex-1 overflow-y-auto p-4">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void runSearch(term);
          }}
          className="flex items-center gap-2"
        >
          <input
            className="w-full rounded-md border border-border bg-[var(--color-background)] px-3 py-2 text-sm"
            placeholder="Search everything you own…"
            value={term}
            onChange={(e) => setTerm(e.target.value)}
          />
          <button
            type="submit"
            className="rounded-md border border-[var(--color-primary)] bg-[var(--color-primary)] px-4 py-2 text-sm text-white disabled:opacity-50"
            disabled={loading || !term.trim()}
          >
            {loading ? "Searching…" : "Search"}
          </button>
        </form>

        {error && <p className="mt-3 text-sm text-[var(--color-error)]">{error}</p>}

        {submitted && !loading && data && (
          <p className="mt-3 text-sm text-[var(--color-muted)]">
            {data.total} match{data.total === 1 ? "" : "es"} for &ldquo;{submitted}&rdquo;
          </p>
        )}

        {submitted && !loading && data && data.total === 0 && (
          <div className="mt-4">
            <EmptyState title="No matches" description="Nothing you own matches this term yet." />
          </div>
        )}

        <div className="mt-4 space-y-4">
          {data &&
            Object.entries(data.groups).map(([key, group]) =>
              group.items.length > 0 ? (
                <GroupCard key={key} label={GROUP_LABELS[key] ?? key} group={group} />
              ) : null,
            )}
        </div>
      </main>
    </div>
  );
}

function GroupCard({ label, group }: { label: string; group: SearchGroup }) {
  return (
    <Card>
      <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--color-muted)]">
        {label} · {group.total}
      </h3>
      <ul className="mt-2 space-y-1.5">
        {group.items.map((item: GlobalSearchItem) => {
          const href = itemHref(item.kind, item.id);
          return (
            <li key={`${item.kind}-${item.id}`} className="text-sm">
              {href ? (
                <Link href={href} className="hover:text-[var(--color-primary)]">
                  <span className="font-medium">{item.title}</span>
                </Link>
              ) : item.url ? (
                <a href={item.url} target="_blank" rel="noreferrer" className="hover:text-[var(--color-primary)]">
                  <span className="font-medium">{item.title}</span>
                </a>
              ) : (
                <span className="font-medium">{item.title}</span>
              )}
              <span className="ml-2 text-xs text-[var(--color-muted)]">
                {item.subtitle}
                {item.confidence != null ? ` · ${item.confidence}%` : ""}
              </span>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}
