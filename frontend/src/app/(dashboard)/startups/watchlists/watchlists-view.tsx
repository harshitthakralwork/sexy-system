"use client";

import Link from "next/link";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { Header } from "@/components/layout/header";
import { AppFooter } from "@/components/layout/app-footer";
import { Card, CardTitle, EmptyState } from "@/components/ui/card";
import { useSession } from "@/components/providers/session-provider";
import { api } from "@/lib/api/client";
import type { Watchlist } from "@/lib/api/types";

export function WatchlistsView() {
  const { csrf, user } = useSession();
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const watchlists = useQuery({
    queryKey: ["watchlists"],
    queryFn: () => api.get<Watchlist[]>("/startups/watchlists"),
  });

  async function invalidate() {
    await queryClient.invalidateQueries({ queryKey: ["watchlists"] });
  }

  async function create() {
    if (!name.trim()) return;
    setBusy(true);
    try {
      await api.post(
        "/startups/watchlists",
        { name: name.trim(), description: description.trim() || null },
        csrf,
      );
      setName("");
      setDescription("");
      await invalidate();
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  async function remove(watchlistId: string) {
    try {
      await api.delete(`/startups/watchlists/${watchlistId}`, csrf);
      setNotice("Watchlist deleted.");
      await invalidate();
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }

  if (!user) return null;

  const items = watchlists.data ?? [];

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <Header
        title="Watchlists"
        subtitle={items.length ? `${items.length} watchlists` : "Group startups to track them together"}
      />

      <main className="flex-1 overflow-y-auto p-4">
        <Card>
          <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--color-muted)]">
            New watchlist
          </h3>
          <div className="mt-2 flex flex-wrap items-end gap-3">
            <label className="min-w-40 flex-1 text-sm">
              <span className="text-[var(--color-muted)]">Name</span>
              <input
                className="mt-1 w-full rounded-md border border-border bg-[var(--color-background)] px-2 py-1.5"
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="e.g. Fintech challengers"
              />
            </label>
            <label className="min-w-52 flex-1 text-sm">
              <span className="text-[var(--color-muted)]">Description</span>
              <input
                className="mt-1 w-full rounded-md border border-border bg-[var(--color-background)] px-2 py-1.5"
                value={description}
                onChange={(event) => setDescription(event.target.value)}
              />
            </label>
            <button className={buttonClass(true)} disabled={busy || !name.trim()} onClick={create} type="button">
              {busy ? "Creating…" : "Create"}
            </button>
          </div>
        </Card>

        {(notice || error) && (
          <div className="mt-3 text-sm">
            {error && <p className="text-[var(--color-error)]">{error}</p>}
            {notice && <p className="text-[var(--color-muted)]">{notice}</p>}
          </div>
        )}

        {watchlists.isError && (
          <div className="mt-4 text-sm text-[var(--color-error)]">
            Watchlists could not be loaded: {errorMessage(watchlists.error)}
          </div>
        )}

        {!watchlists.isPending && items.length === 0 && !watchlists.isError && (
          <div className="mt-4">
            <EmptyState
              title="No watchlists yet"
              description="Create one above, then add startups from their profile pages."
            />
          </div>
        )}

        <div className="mt-4 grid gap-4 md:grid-cols-2">
          {items.map((watchlist) => (
            <Card key={watchlist.id}>
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <CardTitle>{watchlist.name}</CardTitle>
                  {watchlist.description && (
                    <p className="mt-1 text-xs text-[var(--color-muted)]">{watchlist.description}</p>
                  )}
                  <p className="mt-2 text-xs text-[var(--color-muted)]">
                    {watchlist.items.length} startup{watchlist.items.length === 1 ? "" : "s"}
                  </p>
                </div>
                <button className={buttonClass(false)} onClick={() => remove(watchlist.id)} type="button">
                  Delete
                </button>
              </div>
              <ul className="mt-3 space-y-1 text-sm">
                {watchlist.items.map((startup) => (
                  <li key={startup.id}>
                    <Link
                      className="underline-offset-2 hover:underline"
                      href={`/startups/${startup.id}`}
                    >
                      {startup.name}
                    </Link>
                  </li>
                ))}
              </ul>
            </Card>
          ))}
        </div>
        <AppFooter />
      </main>
    </div>
  );
}

function buttonClass(active: boolean): string {
  return [
    "rounded-full border px-3 py-1.5 text-xs font-semibold transition-all disabled:opacity-40 cursor-pointer",
    active
      ? "refraction-glass-btn border-cyan-400/40 bg-cyan-500/20 text-cyan-200 shadow-[0_0_15px_rgba(0,212,255,0.25)] hover:bg-cyan-500/30 hover:text-white"
      : "border-white/10 bg-white/[0.04] text-white/70 hover:border-white/25 hover:text-white hover:bg-white/[0.08]",
  ].join(" ");
}

function errorMessage(caught: unknown): string {
  if (caught instanceof Error) return caught.message;
  return "Something went wrong.";
}
