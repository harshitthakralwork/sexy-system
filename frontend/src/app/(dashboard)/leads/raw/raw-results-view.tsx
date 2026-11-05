"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Search, Download, Star, ExternalLink, MapPin, CheckCircle, Trash2 } from "lucide-react";

import { Header } from "@/components/layout/header";
import { Card, EmptyState } from "@/components/ui/card";
import { useSession } from "@/components/providers/session-provider";
import { api, getApiBase, isApiError } from "@/lib/api/client";
import type { Business, BusinessList } from "@/lib/api/types";

const PAGE_SIZE = 25;

export function RawResultsView() {
  const { csrf } = useSession();
  const queryClient = useQueryClient();

  const [query, setQuery] = useState("");
  const [appliedQuery, setAppliedQuery] = useState("");
  const [city, setCity] = useState("");
  const [websiteStatus, setWebsiteStatus] = useState("");
  const [hasPhone, setHasPhone] = useState("");
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [deleting, setDeleting] = useState(false);
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
    queryKey: ["raw-businesses", params],
    queryFn: () => api.get<BusinessList>(`/businesses?${params}`),
  });

  const total = listing.data?.total ?? 0;
  const rows = listing.data?.items ?? [];
  const pageStart = total === 0 ? 0 : offset + 1;
  const pageEnd = Math.min(offset + PAGE_SIZE, total);

  function applyFilters() {
    setAppliedQuery(query.trim());
    setOffset(0);
  }

  async function saveProspect(id: string, name: string) {
    try {
      setError(null);
      await api.post(`/businesses/${id}/shortlist`, undefined, csrf);
      setNotice(`"${name}" saved as a prospect.`);
      await queryClient.invalidateQueries({ queryKey: ["raw-businesses"] });
    } catch (caught) {
      setError(isApiError(caught) ? caught.message : "Failed to save prospect");
    }
  }

  async function removeSelected() {
    const ids = [...selected];
    if (!ids.length || !window.confirm(`Delete ${ids.length} selected businesses?`)) return;
    await remove({ ids, delete_all: false });
  }

  async function removeAll() {
    if (!window.confirm(`Delete all ${total.toLocaleString()} business records?`)) return;
    await remove({ ids: [], delete_all: true });
  }

  async function remove(payload: { ids: string[]; delete_all: boolean }) {
    setDeleting(true);
    setNotice(null);
    setError(null);
    try {
      const result = await api.post<{ deleted: number }>("/businesses/bulk-delete", payload, csrf);
      setSelected(new Set());
      setNotice(`${result.deleted} businesses deleted.`);
      await queryClient.invalidateQueries({ queryKey: ["raw-businesses"] });
    } catch (caught) {
      setError(isApiError(caught) ? caught.message : "Failed to delete businesses");
    } finally {
      setDeleting(false);
    }
  }

  async function deleteSingle(id: string, name: string) {
    if (!window.confirm(`Delete "${name}"?`)) return;
    try {
      setError(null);
      await api.delete(`/businesses/${id}`, csrf);
      setSelected((prev) => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
      setNotice(`"${name}" deleted.`);
      await queryClient.invalidateQueries({ queryKey: ["raw-businesses"] });
    } catch (caught) {
      setError(isApiError(caught) ? caught.message : "Failed to delete business");
    }
  }

  function exportCsv() {
    const search = new URLSearchParams();
    if (appliedQuery) search.set("query", appliedQuery);
    if (city) search.set("city", city);
    if (websiteStatus) search.set("website_status", websiteStatus);
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination
    window.location.href = `${getApiBase()}/businesses/export?${search.toString()}`;
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <Header
        title="Lead results"
        subtitle={
          listing.data
            ? `${total.toLocaleString()} collected businesses with public-source evidence`
            : "Loading collected prospects…"
        }
      />

      <main className="flex-1 overflow-y-auto p-4 space-y-4">
        {notice && (
          <div className="flex items-center gap-2 rounded-md border border-[var(--color-primary)]/40 bg-[var(--color-primary)]/10 px-4 py-2 text-xs text-[var(--color-foreground)]">
            <CheckCircle size={14} className="text-[var(--color-primary)]" />
            <span>{notice}</span>
          </div>
        )}

        {error && (
          <div className="flex items-center gap-2 rounded-md border border-[var(--color-error)]/40 bg-[var(--color-error)]/10 px-4 py-2 text-xs text-[var(--color-error)]">
            <span>{error}</span>
          </div>
        )}

        {/* Filter Bar */}
        <Card>
          <div className="flex flex-wrap items-end gap-3 text-xs">
            <div className="min-w-48 flex-1">
              <label className="block text-[var(--color-muted)] mb-1">Search Raw Ingestion</label>
              <div className="relative">
                <input
                  type="text"
                  placeholder="Filter by business name, domain, category…"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && applyFilters()}
                  className="w-full rounded-md border border-border bg-[var(--color-background)] px-2.5 py-1.5 pl-8 text-xs text-[var(--color-foreground)] placeholder:text-[var(--color-muted)] focus:outline-none focus:border-[var(--color-primary)]"
                />
                <Search size={14} className="absolute left-2.5 top-2 text-[var(--color-muted)]" />
              </div>
            </div>

            <div className="w-36">
              <label className="block text-[var(--color-muted)] mb-1">City</label>
              <input
                type="text"
                placeholder="Any city"
                value={city}
                onChange={(e) => setCity(e.target.value)}
                className="w-full rounded-md border border-border bg-[var(--color-background)] px-2.5 py-1.5 text-xs text-[var(--color-foreground)] focus:outline-none focus:border-[var(--color-primary)]"
              />
            </div>

            <div className="w-36">
              <label className="block text-[var(--color-muted)] mb-1">Website Status</label>
              <select
                value={websiteStatus}
                onChange={(e) => setWebsiteStatus(e.target.value)}
                className="w-full rounded-md border border-border bg-[var(--color-background)] px-2.5 py-1.5 text-xs text-[var(--color-foreground)] focus:outline-none focus:border-[var(--color-primary)]"
              >
                <option value="">All statuses</option>
                <option value="available">Available (has site)</option>
                <option value="missing">Missing site (opportunity)</option>
                <option value="inaccessible">Inaccessible / broken</option>
                <option value="unknown">Unchecked</option>
              </select>
            </div>

            <div className="w-32">
              <label className="block text-[var(--color-muted)] mb-1">Phone</label>
              <select
                value={hasPhone}
                onChange={(e) => setHasPhone(e.target.value)}
                className="w-full rounded-md border border-border bg-[var(--color-background)] px-2.5 py-1.5 text-xs text-[var(--color-foreground)] focus:outline-none focus:border-[var(--color-primary)]"
              >
                <option value="">Either</option>
                <option value="true">Has phone</option>
                <option value="false">No phone</option>
              </select>
            </div>

            <button
              type="button"
              onClick={applyFilters}
              className="refraction-glass-btn rounded-full border border-cyan-400/40 bg-cyan-500/20 px-4 py-1.5 text-xs font-bold text-cyan-200 shadow-[0_0_12px_rgba(0,212,255,0.2)] hover:bg-cyan-500/30 hover:text-white transition-all cursor-pointer"
            >
              Apply Filters
            </button>

            <div className="flex items-center gap-2 ml-auto">
              <button
                type="button"
                disabled={!selected.size || deleting}
                onClick={removeSelected}
                className="inline-flex items-center gap-1.5 rounded-md border border-[var(--color-error)]/50 px-3 py-1.5 text-xs text-[var(--color-error)] transition hover:bg-[var(--color-error)]/10 disabled:opacity-40 cursor-pointer"
              >
                <Trash2 size={13} />
                <span>Delete selected ({selected.size})</span>
              </button>

              <button
                type="button"
                disabled={!total || deleting}
                onClick={removeAll}
                className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-xs text-[var(--color-muted)] transition hover:border-[var(--color-error)] hover:text-[var(--color-error)] disabled:opacity-40 cursor-pointer"
              >
                <Trash2 size={13} />
                <span>Delete all</span>
              </button>

              <button
                type="button"
                onClick={exportCsv}
                className="flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-xs text-[var(--color-muted)] hover:text-[var(--color-foreground)] hover:bg-[var(--color-surface)]"
              >
                <Download size={13} />
                <span>Export Raw CSV</span>
              </button>
            </div>
          </div>
        </Card>

        {/* Results Table */}
        <Card>
          {listing.isLoading ? (
            <div className="py-12 text-center text-xs text-[var(--color-muted)]">
              Loading raw sightings…
            </div>
          ) : rows.length === 0 ? (
            <EmptyState
              title="No raw results found"
              description="No business records matched your filter criteria or no scrapers have run yet."
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-border text-[var(--color-muted)]">
                    <th className="py-2.5 px-3 w-8">
                      <input
                        type="checkbox"
                        aria-label="Select all visible businesses"
                        checked={rows.length > 0 && rows.every((b: Business) => selected.has(b.id))}
                        onChange={(e) =>
                          setSelected(
                            e.target.checked
                              ? new Set([...selected, ...rows.map((b: Business) => b.id)])
                              : new Set(Array.from(selected).filter((id) => !rows.some((b: Business) => b.id === id)))
                          )
                        }
                        className="h-3.5 w-3.5 rounded accent-[var(--color-primary)] cursor-pointer"
                      />
                    </th>
                    <th className="py-2.5 px-3 font-medium">Business / Entity</th>
                    <th className="py-2.5 px-3 font-medium">Category</th>
                    <th className="py-2.5 px-3 font-medium">Location</th>
                    <th className="py-2.5 px-3 font-medium">Website &amp; Status</th>
                    <th className="py-2.5 px-3 font-medium">Phone</th>
                    <th className="py-2.5 px-3 font-medium">Discovered</th>
                    <th className="py-2.5 px-3 font-medium text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/60">
                  {rows.map((b: Business) => {
                    const isChecked = selected.has(b.id);
                    const statusColor =
                      b.website_status === "available"
                        ? "text-[var(--color-success)] bg-[var(--color-success)]/10"
                        : b.website_status === "missing"
                        ? "text-[var(--color-warning)] bg-[var(--color-warning)]/10"
                        : "text-[var(--color-muted)] bg-[var(--color-muted)]/10";

                    return (
                      <tr key={b.id} className={`hover:bg-[var(--color-surface)]/50 ${isChecked ? "bg-cyan-500/[0.04]" : ""}`}>
                        <td className="py-2.5 px-3">
                          <input
                            type="checkbox"
                            aria-label={`Select ${b.name}`}
                            checked={isChecked}
                            onChange={(e) => {
                              const next = new Set(selected);
                              if (e.target.checked) next.add(b.id);
                              else next.delete(b.id);
                              setSelected(next);
                            }}
                            className="h-3.5 w-3.5 rounded accent-[var(--color-primary)] cursor-pointer"
                          />
                        </td>
                        <td className="py-2.5 px-3">
                          <Link
                            href={`/leads/${b.id}`}
                            className="font-medium text-[var(--color-foreground)] hover:text-[var(--color-primary)] hover:underline"
                          >
                            {b.name}
                          </Link>
                        </td>

                        <td className="py-2.5 px-3 text-[var(--color-muted)]">
                          {b.primary_category || "Uncategorized"}
                        </td>

                        <td className="py-2.5 px-3 text-[var(--color-muted)]">
                          {b.city ? (
                            <span className="flex items-center gap-1">
                              <MapPin size={11} />
                              <span>{b.city}</span>
                            </span>
                          ) : (
                            "—"
                          )}
                        </td>

                        <td className="py-2.5 px-3">
                          <div className="flex items-center gap-1.5">
                            <span className={`inline-flex px-1.5 py-0.5 rounded text-[10px] ${statusColor}`}>
                              {b.website_status}
                            </span>
                            {b.website_url && (
                              <a
                                href={b.website_url}
                                target="_blank"
                                rel="noreferrer noopener"
                                className="text-[var(--color-muted)] hover:text-[var(--color-foreground)]"
                              >
                                <ExternalLink size={12} />
                              </a>
                            )}
                          </div>
                        </td>

                        <td className="py-2.5 px-3 text-[var(--color-muted)] font-mono text-[11px]">
                          {b.phone || "—"}
                        </td>

                        <td className="py-2.5 px-3 text-[var(--color-muted)]">
                          {b.first_discovered_at
                            ? new Date(b.first_discovered_at).toLocaleDateString(undefined, {
                                month: "short",
                                day: "numeric",
                              })
                            : "—"}
                        </td>

                        <td className="py-2.5 px-3 text-right">
                          <div className="inline-flex items-center gap-1.5">
                            <button
                              type="button"
                              onClick={() => saveProspect(b.id, b.name)}
                              className="refraction-glass-btn inline-flex items-center gap-1 rounded-full border border-cyan-400/40 bg-cyan-500/15 px-3 py-1 text-[11px] font-semibold text-cyan-200 shadow-[0_0_10px_rgba(0,212,255,0.15)] hover:bg-cyan-500/25 hover:text-white transition-all cursor-pointer"
                            >
                              <Star size={11} />
                              <span>Save prospect</span>
                            </button>
                            <button
                              type="button"
                              onClick={() => deleteSingle(b.id, b.name)}
                              className="inline-flex items-center justify-center h-6 w-6 rounded-md text-[var(--color-muted)] hover:text-[var(--color-error)] hover:bg-[var(--color-error)]/10 transition cursor-pointer"
                              title="Delete business"
                              aria-label={`Delete ${b.name}`}
                            >
                              <Trash2 size={13} />
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>

              {/* Pagination footer */}
              <div className="flex items-center justify-between border-t border-border pt-3 mt-2 text-xs text-[var(--color-muted)]">
                <span>
                  Showing {pageStart}–{pageEnd} of {total.toLocaleString()} records
                </span>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    disabled={offset === 0}
                    onClick={() => setOffset((o) => Math.max(0, o - PAGE_SIZE))}
                    className="rounded border border-border px-2.5 py-1 hover:bg-[var(--color-surface)] disabled:opacity-40"
                  >
                    Previous
                  </button>
                  <button
                    type="button"
                    disabled={pageEnd >= total}
                    onClick={() => setOffset((o) => o + PAGE_SIZE)}
                    className="rounded border border-border px-2.5 py-1 hover:bg-[var(--color-surface)] disabled:opacity-40"
                  >
                    Next
                  </button>
                </div>
              </div>
            </div>
          )}
        </Card>
      </main>
    </div>
  );
}
