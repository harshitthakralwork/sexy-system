"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { Header } from "@/components/layout/header";
import { Card, EmptyState } from "@/components/ui/card";
import { useSession } from "@/components/providers/session-provider";
import { api } from "@/lib/api/client";
import type { Startup, StartupList } from "@/lib/api/types";

const PAGE_SIZE = 25;

const STATUS_TONE: Record<string, string> = {
  active: "text-[var(--color-success)]",
  acquired: "text-[var(--color-warning)]",
  shutdown: "text-[var(--color-error)]",
  unknown: "text-[var(--color-muted)]",
};

/** The startup table: real rows, real filters, create and soft-delete. */
export function StartupsDashboard() {
  const { csrf, user } = useSession();
  const queryClient = useQueryClient();

  const [query, setQuery] = useState("");
  const [appliedQuery, setAppliedQuery] = useState("");
  const [industry, setIndustry] = useState("");
  const [fundingStage, setFundingStage] = useState("");
  const [status, setStatus] = useState("");
  const [offset, setOffset] = useState(0);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const params = useMemo(() => {
    const search = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(offset) });
    if (appliedQuery) search.set("query", appliedQuery);
    if (industry) search.set("industry", industry);
    if (fundingStage) search.set("funding_stage", fundingStage);
    if (status) search.set("status", status);
    return search.toString();
  }, [appliedQuery, industry, fundingStage, status, offset]);

  const listing = useQuery({
    queryKey: ["startups", params],
    queryFn: () => api.get<StartupList>(`/startups?${params}`),
  });

  const total = listing.data?.total ?? 0;
  const rows = listing.data?.items ?? [];
  const pageStart = total === 0 ? 0 : offset + 1;
  const pageEnd = Math.min(offset + PAGE_SIZE, total);

  function applyFilters() {
    setAppliedQuery(query.trim());
    setOffset(0);
  }

  async function invalidate() {
    await queryClient.invalidateQueries({ queryKey: ["startups"] });
  }

  if (!user) return null;

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <Header
        title="Startups"
        subtitle={listing.data ? `${total} startups match your filters` : "Track and research startups"}
      />

      <main className="flex-1 overflow-y-auto p-4">
        <Card>
          <div className="flex flex-wrap items-end gap-3">
            <label className="min-w-40 flex-1 text-sm">
              <span className="text-[var(--color-muted)]">Search</span>
              <input
                className="mt-1 w-full rounded-md border border-border bg-[var(--color-background)] px-2 py-1.5"
                placeholder="name, industry, city"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") applyFilters();
                }}
              />
            </label>
            <label className="text-sm">
              <span className="text-[var(--color-muted)]">Industry</span>
              <input
                className="mt-1 w-36 rounded-md border border-border bg-[var(--color-background)] px-2 py-1.5"
                value={industry}
                onChange={(event) => setIndustry(event.target.value)}
              />
            </label>
            <label className="text-sm">
              <span className="text-[var(--color-muted)]">Funding stage</span>
              <input
                className="mt-1 w-36 rounded-md border border-border bg-[var(--color-background)] px-2 py-1.5"
                value={fundingStage}
                onChange={(event) => setFundingStage(event.target.value)}
              />
            </label>
            <label className="text-sm">
              <span className="text-[var(--color-muted)]">Status</span>
              <select
                className="mt-1 w-32 rounded-md border border-border bg-[var(--color-background)] px-2 py-1.5"
                value={status}
                onChange={(event) => setStatus(event.target.value)}
              >
                <option value="">any</option>
                <option value="active">active</option>
                <option value="acquired">acquired</option>
                <option value="shutdown">shutdown</option>
                <option value="unknown">unknown</option>
              </select>
            </label>
            <button className={buttonClass(false)} onClick={applyFilters} type="button">
              Apply
            </button>
          </div>
        </Card>

        {(notice || error) && (
          <div className="mt-3 text-sm">
            {error && <p className="text-[var(--color-error)]">{error}</p>}
            {notice && <p className="text-[var(--color-muted)]">{notice}</p>}
          </div>
        )}

        <div className="mt-4">
          <CreateForm
            csrf={csrf}
            onCreated={async (message) => {
              setNotice(message);
              await invalidate();
            }}
            onError={setError}
          />
        </div>

        {listing.isError && (
          <div className="mt-4 text-sm text-[var(--color-error)]">
            Startups could not be loaded: {errorMessage(listing.error)}
          </div>
        )}

        {!listing.isPending && rows.length === 0 && !listing.isError && (
          <div className="mt-4">
            <EmptyState
              title="No startups yet"
              description="Add a startup above to begin tracking it. Each startup keeps its own founders, products, revenue evidence, competitors and research."
            />
          </div>
        )}

        {rows.length > 0 && (
          <div className="mt-4 overflow-x-auto rounded-lg border border-border">
            <table className="w-full min-w-[760px] text-sm">
              <thead>
                <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-[var(--color-muted)]">
                  <th className="px-3 py-2">Name</th>
                  <th className="px-3 py-2">Industry</th>
                  <th className="px-3 py-2">Funding stage</th>
                  <th className="px-3 py-2">Status</th>
                  <th className="px-3 py-2">Source</th>
                  <th className="px-3 py-2" />
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <StartupRow
                    key={row.id}
                    startup={row}
                    csrf={csrf}
                    onDeleted={async () => {
                      setNotice("Startup deleted.");
                      await invalidate();
                    }}
                    onError={setError}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}

        {total > PAGE_SIZE && (
          <div className="mt-3 flex items-center justify-between text-sm text-[var(--color-muted)]">
            <span>
              Showing {pageStart}–{pageEnd} of {total}
            </span>
            <div className="flex gap-2">
              <button
                className={buttonClass(false)}
                disabled={offset === 0}
                onClick={() => setOffset((value) => Math.max(0, value - PAGE_SIZE))}
                type="button"
              >
                Previous
              </button>
              <button
                className={buttonClass(false)}
                disabled={offset + PAGE_SIZE >= total}
                onClick={() => setOffset((value) => value + PAGE_SIZE)}
                type="button"
              >
                Next
              </button>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

function CreateForm({
  csrf,
  onCreated,
  onError,
}: {
  csrf: string | null;
  onCreated: (message: string) => Promise<void>;
  onError: (message: string) => void;
}) {
  const [name, setName] = useState("");
  const [websiteUrl, setWebsiteUrl] = useState("");
  const [industry, setIndustry] = useState("");
  const [fundingStage, setFundingStage] = useState("");
  const [status, setStatus] = useState("unknown");
  const [busy, setBusy] = useState(false);

  async function submit() {
    if (!name.trim()) return;
    setBusy(true);
    try {
      const created = await api.post<Startup>(
        "/startups",
        {
          name: name.trim(),
          website_url: websiteUrl.trim() || null,
          industry: industry.trim() || null,
          funding_stage: fundingStage.trim() || null,
          status,
        },
        csrf,
      );
      setName("");
      setWebsiteUrl("");
      setIndustry("");
      setFundingStage("");
      setStatus("unknown");
      await onCreated(`Added ${created.name}.`);
    } catch (caught) {
      onError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--color-muted)]">
        Add a startup
      </h3>
      <div className="mt-2 flex flex-wrap items-end gap-3">
        <label className="min-w-40 flex-1 text-sm">
          <span className="text-[var(--color-muted)]">Name</span>
          <input
            className="mt-1 w-full rounded-md border border-border bg-[var(--color-background)] px-2 py-1.5"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="e.g. Zerodha"
          />
        </label>
        <label className="min-w-52 flex-1 text-sm">
          <span className="text-[var(--color-muted)]">Website</span>
          <input
            className="mt-1 w-full rounded-md border border-border bg-[var(--color-background)] px-2 py-1.5"
            value={websiteUrl}
            onChange={(event) => setWebsiteUrl(event.target.value)}
            placeholder="https://zerodha.com"
          />
        </label>
        <label className="text-sm">
          <span className="text-[var(--color-muted)]">Industry</span>
          <input
            className="mt-1 w-36 rounded-md border border-border bg-[var(--color-background)] px-2 py-1.5"
            value={industry}
            onChange={(event) => setIndustry(event.target.value)}
          />
        </label>
        <label className="text-sm">
          <span className="text-[var(--color-muted)]">Funding stage</span>
          <input
            className="mt-1 w-32 rounded-md border border-border bg-[var(--color-background)] px-2 py-1.5"
            value={fundingStage}
            onChange={(event) => setFundingStage(event.target.value)}
          />
        </label>
        <label className="text-sm">
          <span className="text-[var(--color-muted)]">Status</span>
          <select
            className="mt-1 w-32 rounded-md border border-border bg-[var(--color-background)] px-2 py-1.5"
            value={status}
            onChange={(event) => setStatus(event.target.value)}
          >
            <option value="unknown">unknown</option>
            <option value="active">active</option>
            <option value="acquired">acquired</option>
            <option value="shutdown">shutdown</option>
          </select>
        </label>
        <button className={buttonClass(true)} disabled={busy || !name.trim()} onClick={submit} type="button">
          {busy ? "Adding…" : "Add"}
        </button>
      </div>
    </Card>
  );
}

function StartupRow({
  startup,
  csrf,
  onDeleted,
  onError,
}: {
  startup: Startup;
  csrf: string | null;
  onDeleted: () => Promise<void>;
  onError: (message: string) => void;
}) {
  const [busy, setBusy] = useState(false);

  async function remove() {
    setBusy(true);
    try {
      await api.delete(`/startups/${startup.id}`, csrf);
      await onDeleted();
    } catch (caught) {
      onError(errorMessage(caught));
      setBusy(false);
    }
  }

  return (
    <tr className="border-b border-border/60 hover:bg-[var(--color-surface)]">
      <td className="px-3 py-2">
        <Link
          className="font-medium text-[var(--color-foreground)] underline-offset-2 hover:underline"
          href={`/startups/${startup.id}`}
        >
          {startup.name}
        </Link>
        {startup.normalized_domain && (
          <span className="ml-2 text-xs text-[var(--color-muted)]">{startup.normalized_domain}</span>
        )}
      </td>
      <td className="px-3 py-2 text-[var(--color-muted)]">{startup.industry ?? "—"}</td>
      <td className="px-3 py-2 text-[var(--color-muted)]">{startup.funding_stage ?? "—"}</td>
      <td className="px-3 py-2">
        <span className={STATUS_TONE[startup.status] ?? "text-[var(--color-muted)]"}>
          {startup.status}
        </span>
      </td>
      <td className="px-3 py-2 text-[var(--color-muted)]">{startup.source_slug ?? "manual"}</td>
      <td className="px-3 py-2 text-right">
        <button className={buttonClass(false)} disabled={busy} onClick={remove} type="button">
          {busy ? "Deleting…" : "Delete"}
        </button>
      </td>
    </tr>
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
