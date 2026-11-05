"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { CheckSquare, Search, Download, ExternalLink, Mail, FolderKanban, Phone, MapPin, ArrowRight } from "lucide-react";

import { Header } from "@/components/layout/header";
import { Card, EmptyState } from "@/components/ui/card";
import { api, getApiBase } from "@/lib/api/client";
import type { Business, BusinessList } from "@/lib/api/types";

const PAGE_SIZE = 25;

export function QualifiedLeadsView() {
  const [query, setQuery] = useState("");
  const [appliedQuery, setAppliedQuery] = useState("");
  const [city, setCity] = useState("");
  const [offset, setOffset] = useState(0);

  const params = useMemo(() => {
    const search = new URLSearchParams({
      limit: String(PAGE_SIZE),
      offset: String(offset),
      shortlisted_only: "true",
    });
    if (appliedQuery) search.set("query", appliedQuery);
    if (city) search.set("city", city);
    return search.toString();
  }, [appliedQuery, city, offset]);

  const listing = useQuery({
    queryKey: ["qualified-businesses", params],
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

  function exportCsv() {
    const search = new URLSearchParams({ shortlisted_only: "true" });
    if (appliedQuery) search.set("query", appliedQuery);
    if (city) search.set("city", city);
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination
    window.location.href = `${getApiBase()}/businesses/export?${search.toString()}`;
  }

  // Count leads with phone
  const withPhone = rows.filter((r) => Boolean(r.phone)).length;

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <Header
        title="Qualified Leads"
        subtitle={
          listing.data
            ? `${total.toLocaleString()} shortlisted businesses ready for CRM pipeline progression and outreach`
            : "Loading qualified leads…"
        }
      />

      <main className="flex-1 overflow-y-auto p-4 space-y-4">
        {/* Metrics Bar */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <Card>
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-[var(--color-muted)]">Total Qualified</p>
                <p className="text-xl font-bold text-[var(--color-foreground)] mt-1">{total}</p>
              </div>
              <div className="p-2 rounded-lg bg-[var(--color-primary)]/10 text-[var(--color-primary)]">
                <CheckSquare size={20} />
              </div>
            </div>
            <p className="text-[11px] text-[var(--color-muted)] mt-2">Shortlisted across all discovery sweeps</p>
          </Card>

          <Card>
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-[var(--color-muted)]">With Contact Phone</p>
                <p className="text-xl font-bold text-[var(--color-foreground)] mt-1">{withPhone}</p>
              </div>
              <div className="p-2 rounded-lg bg-[var(--color-success)]/10 text-[var(--color-success)]">
                <Phone size={20} />
              </div>
            </div>
            <p className="text-[11px] text-[var(--color-muted)] mt-2">Direct telephone contact available</p>
          </Card>

          <Card>
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-[var(--color-muted)]">CRM Pipeline Ready</p>
                <p className="text-xl font-bold text-[var(--color-foreground)] mt-1">100%</p>
              </div>
              <div className="p-2 rounded-lg bg-blue-500/10 text-blue-400">
                <FolderKanban size={20} />
              </div>
            </div>
            <Link
              href="/leads/crm"
              className="inline-flex items-center gap-1 text-[11px] text-[var(--color-primary)] hover:underline mt-2"
            >
              <span>Open CRM Board</span>
              <ArrowRight size={11} />
            </Link>
          </Card>
        </div>

        {/* Filter Bar */}
        <Card>
          <div className="flex flex-wrap items-end gap-3 text-xs">
            <div className="min-w-48 flex-1">
              <label className="block text-[var(--color-muted)] mb-1">Search Qualified</label>
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

            <div className="w-40">
              <label className="block text-[var(--color-muted)] mb-1">City</label>
              <input
                type="text"
                placeholder="Any city"
                value={city}
                onChange={(e) => setCity(e.target.value)}
                className="w-full rounded-md border border-border bg-[var(--color-background)] px-2.5 py-1.5 text-xs text-[var(--color-foreground)] focus:outline-none focus:border-[var(--color-primary)]"
              />
            </div>

            <button
              type="button"
              onClick={applyFilters}
              className="refraction-glass-btn rounded-full border border-cyan-400/40 bg-cyan-500/20 px-4 py-1.5 text-xs font-bold text-cyan-200 shadow-[0_0_12px_rgba(0,212,255,0.2)] hover:bg-cyan-500/30 hover:text-white transition-all cursor-pointer"
            >
              Filter Leads
            </button>

            <button
              type="button"
              onClick={exportCsv}
              className="flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-xs text-[var(--color-muted)] hover:text-[var(--color-foreground)] hover:bg-[var(--color-surface)] ml-auto"
            >
              <Download size={13} />
              <span>Export Qualified CSV</span>
            </button>
          </div>
        </Card>

        {/* Qualified Leads Table */}
        <Card>
          {listing.isLoading ? (
            <div className="py-12 text-center text-xs text-[var(--color-muted)]">
              Loading qualified leads…
            </div>
          ) : rows.length === 0 ? (
            <EmptyState
              title="No qualified leads yet"
              description="To qualify leads, browse Raw Results or Map Explorer and click 'Qualify' or 'Shortlist' on high-value business sightings."
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-border text-[var(--color-muted)]">
                    <th className="py-2.5 px-3 font-medium">Business / Opportunity</th>
                    <th className="py-2.5 px-3 font-medium">Category</th>
                    <th className="py-2.5 px-3 font-medium">Location</th>
                    <th className="py-2.5 px-3 font-medium">Website</th>
                    <th className="py-2.5 px-3 font-medium">Phone</th>
                    <th className="py-2.5 px-3 font-medium">Status</th>
                    <th className="py-2.5 px-3 font-medium text-right">Outreach Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/60">
                  {rows.map((b: Business) => (
                    <tr key={b.id} className="hover:bg-[var(--color-surface)]/50">
                      <td className="py-2.5 px-3">
                        <Link
                          href={`/leads/${b.id}`}
                          className="font-medium text-[var(--color-foreground)] hover:text-[var(--color-primary)] hover:underline"
                        >
                          {b.name}
                        </Link>
                      </td>

                      <td className="py-2.5 px-3 text-[var(--color-muted)]">
                        {b.primary_category || "General"}
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
                        {b.website_url ? (
                          <a
                            href={b.website_url}
                            target="_blank"
                            rel="noreferrer noopener"
                            className="inline-flex items-center gap-1 text-[var(--color-primary)] hover:underline"
                          >
                            <span className="truncate max-w-[120px]">
                              {b.website_url.replace(/^https?:\/\//, "").replace(/\/.*$/, "")}
                            </span>
                            <ExternalLink size={10} />
                          </a>
                        ) : (
                          <span className="text-[var(--color-warning)] text-[11px]">No website</span>
                        )}
                      </td>

                      <td className="py-2.5 px-3 text-[var(--color-muted)] font-mono text-[11px]">
                        {b.phone || "—"}
                      </td>

                      <td className="py-2.5 px-3">
                        <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-medium bg-[var(--color-success)]/10 text-[var(--color-success)]">
                          {b.lifecycle_status || "qualified"}
                        </span>
                      </td>

                      <td className="py-2.5 px-3 text-right space-x-2">
                        <Link
                          href={`/email?business_id=${b.id}`}
                          className="refraction-glass-btn inline-flex items-center gap-1 rounded-full border border-cyan-400/40 bg-cyan-500/20 px-3 py-1 text-[11px] font-semibold text-cyan-200 shadow-[0_0_10px_rgba(0,212,255,0.2)] hover:bg-cyan-500/30 hover:text-white transition-all"
                        >
                          <Mail size={11} />
                          <span>Outreach</span>
                        </Link>

                        <Link
                          href={`/leads/${b.id}`}
                          className="inline-flex items-center gap-1 rounded border border-border px-2 py-1 text-[11px] text-[var(--color-muted)] hover:text-[var(--color-foreground)] hover:bg-[var(--color-surface)]"
                        >
                          <span>Profile</span>
                        </Link>
                      </td>
                    </tr>
                  ))}
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
