"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { Header } from "@/components/layout/header";
import { Card, EmptyState } from "@/components/ui/card";
import { useSession } from "@/components/providers/session-provider";
import { api } from "@/lib/api/client";
import type { ActionOut, Business, BusinessList } from "@/lib/api/types";

const PAGE_SIZE = 25;
const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000/api/v1";

/** The standalone results table: real rows, real filters, real pagination. */
export function LeadsList() {
  const { csrf, user } = useSession();
  const queryClient = useQueryClient();

  const [query, setQuery] = useState("");
  const [appliedQuery, setAppliedQuery] = useState("");
  const [city, setCity] = useState("");
  const [websiteStatus, setWebsiteStatus] = useState("");
  const [hasPhone, setHasPhone] = useState("");
  const [offset, setOffset] = useState(0);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const params = useMemo(() => {
    const search = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(offset) });
    if (appliedQuery) search.set("query", appliedQuery);
    if (city) search.set("city", city);
    if (websiteStatus) search.set("website_status", websiteStatus);
    if (hasPhone) search.set("has_phone", hasPhone);
    return search.toString();
  }, [appliedQuery, city, websiteStatus, hasPhone, offset]);

  const listing = useQuery({
    queryKey: ["businesses", params],
    queryFn: () => api.get<BusinessList>(`/businesses?${params}`),
  });

  const total = listing.data?.total ?? 0;
  const rows = listing.data?.items ?? [];
  const pageEnd = Math.min(offset + PAGE_SIZE, total);
  const pageStart = total === 0 ? 0 : offset + 1;

  function applyFilters() {
    setAppliedQuery(query.trim());
    setOffset(0);
  }

  async function shortlist(id: string) {
    try {
      await api.post(`/businesses/${id}/shortlist`, undefined, csrf);
      setNotice("Shortlisted.");
      await listing.refetch();
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }

  function exportCsv() {
    const search = new URLSearchParams();
    if (appliedQuery) search.set("query", appliedQuery);
    if (city) search.set("city", city);
    if (websiteStatus) search.set("website_status", websiteStatus);
    // A download from the API origin, not a Next.js route navigation.
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination
    window.location.href = `${API_BASE}/businesses/export?${search.toString()}`;
  }

  async function invalidate() {
    await queryClient.invalidateQueries({ queryKey: ["businesses"] });
  }

  if (!user) return null;

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <Header
        title="Leads"
        subtitle={listing.data ? `${total} records match your filters` : "Discover and qualify businesses"}
      />

      <main className="flex-1 overflow-y-auto p-4">
        <Card>
          <div className="flex flex-wrap items-end gap-3">
            <label className="min-w-40 flex-1 text-sm">
              <span className="text-[var(--color-muted)]">Search</span>
              <input
                className="mt-1 w-full rounded-md border border-border bg-[var(--color-background)] px-2 py-1.5"
                placeholder="name, domain, city, category"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") applyFilters();
                }}
              />
            </label>
            <label className="text-sm">
              <span className="text-[var(--color-muted)]">City</span>
              <input
                className="mt-1 w-40 rounded-md border border-border bg-[var(--color-background)] px-2 py-1.5"
                value={city}
                onChange={(event) => setCity(event.target.value)}
              />
            </label>
            <label className="text-sm">
              <span className="text-[var(--color-muted)]">Website</span>
              <select
                className="mt-1 w-36 rounded-md border border-border bg-[var(--color-background)] px-2 py-1.5"
                value={websiteStatus}
                onChange={(event) => setWebsiteStatus(event.target.value)}
              >
                <option value="">any</option>
                <option value="available">has one</option>
                <option value="missing">known missing</option>
                <option value="inaccessible">unreachable</option>
                <option value="unknown">not checked</option>
              </select>
            </label>
            <label className="text-sm">
              <span className="text-[var(--color-muted)]">Phone</span>
              <select
                className="mt-1 w-32 rounded-md border border-border bg-[var(--color-background)] px-2 py-1.5"
                value={hasPhone}
                onChange={(event) => setHasPhone(event.target.value)}
              >
                <option value="">any</option>
                <option value="true">has one</option>
                <option value="false">none reported</option>
              </select>
            </label>
            <div className="flex gap-2">
              <button className={buttonClass(false)} onClick={applyFilters} type="button">
                Apply
              </button>
              <button className={buttonClass(false)} onClick={exportCsv} type="button">
                Export CSV
              </button>
            </div>
          </div>

          {(notice || error) && (
            <div className="mt-3 text-sm">
              {error && <p className="text-[var(--color-error)]">{error}</p>}
              {notice && <p className="text-[var(--color-muted)]">{notice}</p>}
            </div>
          )}
        </Card>

        {listing.isError && (
          <div className="mt-4 text-sm text-[var(--color-error)]">
            Leads could not be loaded: {errorMessage(listing.error)}
          </div>
        )}

        {!listing.isPending && rows.length === 0 && !listing.isError && (
          <div className="mt-4">
            <EmptyState
              title="No leads yet"
              description="Run a discovery from Map Explorer to fill this table. It shows your stored records, nothing more."
            />
          </div>
        )}

        {rows.length > 0 && (
          <div className="mt-4 overflow-x-auto rounded-lg border border-border">
            <table className="w-full min-w-[720px] text-sm">
              <thead>
                <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-[var(--color-muted)]">
                  <th className="px-3 py-2">Name</th>
                  <th className="px-3 py-2">Category</th>
                  <th className="px-3 py-2">City</th>
                  <th className="px-3 py-2">Website</th>
                  <th className="px-3 py-2">Phone</th>
                  <th className="px-3 py-2">Stage</th>
                  <th className="px-3 py-2" />
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <LeadRow
                    key={row.id}
                    business={row}
                    onShortlist={() => shortlist(row.id)}
                    onMutated={invalidate}
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

function LeadRow({
  business,
  onShortlist,
  onMutated,
}: {
  business: Business;
  onShortlist: () => Promise<void>;
  onMutated: () => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);

  return (
    <tr className="border-b border-border/60 hover:bg-[var(--color-surface)]">
      <td className="px-3 py-2">
        <Link
          className="font-medium text-[var(--color-foreground)] underline-offset-2 hover:underline"
          href={`/leads/${business.id}`}
        >
          {business.name}
        </Link>
      </td>
      <td className="px-3 py-2 text-[var(--color-muted)]">{business.primary_category ?? "—"}</td>
      <td className="px-3 py-2 text-[var(--color-muted)]">{business.city ?? "—"}</td>
      <td className="px-3 py-2">
        <WebsiteCell
          url={business.website_url}
          status={business.website_status}
        />
      </td>
      <td className="px-3 py-2 text-[var(--color-muted)]">{business.phone ?? "none reported"}</td>
      <td className="px-3 py-2 text-[var(--color-muted)]">
        <StagePill businessId={business.id} />
      </td>
      <td className="px-3 py-2 text-right">
        <button
          className={buttonClass(false)}
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            try {
              await onShortlist();
              await onMutated();
            } finally {
              setBusy(false);
            }
          }}
          type="button"
        >
          Shortlist
        </button>
      </td>
    </tr>
  );
}

function StagePill({ businessId }: { businessId: string }) {
  const { data } = useQuery({
    queryKey: ["business-stage", businessId],
    queryFn: () => api.get<ActionOut>(`/businesses/${businessId}/stage`),
  });
  const stage = data?.crm_stage;
  return stage ? (
    <span className="rounded bg-[var(--color-surface-elevated)] px-1.5 py-0.5 text-xs">{stage}</span>
  ) : (
    <span className="text-xs text-[var(--color-muted)]">—</span>
  );
}

/**
 * The address the operator gave us, plus what we know about it.
 *
 * The status alone is not enough: an imported record carries a website but has
 * never been probed, so "unknown" would hide the only thing the row has. The
 * status stays visible because "we have not checked" and "there is none" are
 * different facts.
 */
function WebsiteCell({ url, status }: { url: string | null; status: string }) {
  const safe = url && /^https?:\/\//i.test(url) ? url : null;
  return (
    <div className="flex flex-col gap-0.5">
      {safe ? (
        <a
          className="text-[var(--color-foreground)] underline-offset-2 hover:underline"
          href={safe}
          rel="noopener noreferrer"
          target="_blank"
        >
          {safe.replace(/^https?:\/\//i, "")}
        </a>
      ) : (
        <span className="text-[var(--color-muted)]">{url ?? "none reported"}</span>
      )}
      <span
        className={
          status === "missing"
            ? "text-xs text-[var(--color-warning)]"
            : status === "available"
              ? "text-xs text-[var(--color-success)]"
              : "text-xs text-[var(--color-muted)]"
        }
      >
        {status}
      </span>
    </div>
  );
}

function buttonClass(active: boolean): string {
  return [
    "rounded-md border px-2.5 py-1.5 text-xs transition-colors disabled:opacity-50",
    active
      ? "border-[var(--color-primary)] bg-[var(--color-primary)] text-white"
      : "border-border text-[var(--color-muted)] hover:border-[var(--color-primary)]",
  ].join(" ");
}

function errorMessage(caught: unknown): string {
  if (caught instanceof Error) return caught.message;
  return "Something went wrong.";
}
