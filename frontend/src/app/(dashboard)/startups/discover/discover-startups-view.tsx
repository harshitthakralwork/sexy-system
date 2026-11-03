"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Search,
  Plus,
  ExternalLink,
  MapPin,
  CheckCircle,
  AlertCircle,
  Sparkles,
} from "lucide-react";

import { Header } from "@/components/layout/header";
import { Card, CardTitle, EmptyState } from "@/components/ui/card";
import { useSession } from "@/components/providers/session-provider";
import { api, isApiError } from "@/lib/api/client";
import type { Startup, StartupList, Watchlist } from "@/lib/api/types";

const INDUSTRIES = ["All", "AI/ML", "Fintech", "SaaS", "DevTools", "Healthtech", "Climate", "E-commerce"];
const STAGES = ["All", "Pre-seed", "Seed", "Series A", "Series B", "Bootstrapped"];

export function DiscoverStartupsView() {
  const { csrf } = useSession();
  const queryClient = useQueryClient();

  const [query, setQuery] = useState("");
  const [appliedQuery, setAppliedQuery] = useState("");
  const [selectedIndustry, setSelectedIndustry] = useState("All");
  const [selectedStage, setSelectedStage] = useState("All");

  // Ingest modal/drawer state
  const [showAddForm, setShowAddForm] = useState(false);
  const [newName, setNewName] = useState("");
  const [newWebsite, setNewWebsite] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [newIndustry, setNewIndustry] = useState("AI/ML");
  const [newStage, setNewStage] = useState("Seed");
  const [newCity, setNewCity] = useState("");
  const [newCountry, setNewCountry] = useState("US");

  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const params = useMemo(() => {
    const search = new URLSearchParams({ limit: "50", offset: "0" });
    if (appliedQuery) search.set("query", appliedQuery);
    if (selectedIndustry !== "All") search.set("industry", selectedIndustry);
    if (selectedStage !== "All") search.set("funding_stage", selectedStage);
    return search.toString();
  }, [appliedQuery, selectedIndustry, selectedStage]);

  const startupsQuery = useQuery({
    queryKey: ["discover-startups", params],
    queryFn: () => api.get<StartupList>(`/startups?${params}`),
  });

  const watchlistsQuery = useQuery({
    queryKey: ["watchlists"],
    queryFn: () => api.get<Watchlist[]>("/startups/watchlists"),
  });

  const addStartup = useMutation({
    mutationFn: async () => {
      setError(null);
      return api.post<Startup>(
        "/startups",
        {
          name: newName.trim(),
          website_url: newWebsite.trim() || null,
          description: newDesc.trim() || null,
          industry: newIndustry,
          funding_stage: newStage,
          city: newCity.trim() || null,
          country: newCountry.trim() || null,
        },
        csrf
      );
    },
    onSuccess: (created) => {
      setNotice(`Startup "${created.name}" added to intelligence registry.`);
      setShowAddForm(false);
      setNewName("");
      setNewWebsite("");
      setNewDesc("");
      queryClient.invalidateQueries({ queryKey: ["discover-startups"] });
      queryClient.invalidateQueries({ queryKey: ["startups"] });
    },
    onError: (err) => {
      setError(isApiError(err) ? err.message : "Failed to add startup");
    },
  });

  async function addToWatchlist(startupId: string, watchlistId: string) {
    try {
      setError(null);
      await api.post(`/startups/watchlists/${watchlistId}/items`, { startup_id: startupId }, csrf);
      setNotice("Added to watchlist.");
      queryClient.invalidateQueries({ queryKey: ["watchlists"] });
    } catch (caught) {
      setError(isApiError(caught) ? caught.message : "Failed to add to watchlist");
    }
  }

  const startups = startupsQuery.data?.items ?? [];
  const watchlists = watchlistsQuery.data ?? [];

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <Header
        title="Discover Startups"
        subtitle="Venture intelligence radar: discover high-growth startups, funding signals, and tech stacks"
      />

      <main className="flex-1 overflow-y-auto p-4 space-y-6">
        {notice && (
          <div className="flex items-center gap-2 rounded-md border border-[var(--color-primary)]/40 bg-[var(--color-primary)]/10 px-4 py-2.5 text-xs text-[var(--color-foreground)]">
            <CheckCircle size={15} className="text-[var(--color-primary)]" />
            <span>{notice}</span>
          </div>
        )}

        {error && (
          <div className="flex items-center gap-2 rounded-md border border-[var(--color-error)]/40 bg-[var(--color-error)]/10 px-4 py-2.5 text-xs text-[var(--color-error)]">
            <AlertCircle size={15} />
            <span>{error}</span>
          </div>
        )}

        {/* Action & Filter Header */}
        <Card>
          <div className="flex flex-wrap items-center justify-between gap-4 pb-3 border-b border-border">
            <div className="flex items-center gap-2">
              <Sparkles className="text-[var(--color-primary)]" size={18} />
              <CardTitle>Startup Radar &amp; Discovery Filter</CardTitle>
            </div>
            <button
              type="button"
              onClick={() => setShowAddForm((s) => !s)}
              className="flex items-center gap-1.5 rounded-md bg-[var(--color-primary)] px-3 py-1.5 text-xs font-medium text-white hover:opacity-90 transition-opacity"
            >
              <Plus size={14} />
              <span>Ingest / Track Startup</span>
            </button>
          </div>

          {/* Add form drawer */}
          {showAddForm && (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                addStartup.mutate();
              }}
              className="mt-4 p-4 rounded-lg border border-border/80 bg-[var(--color-surface)]/40 space-y-3"
            >
              <p className="text-xs font-semibold text-[var(--color-foreground)]">Track New Venture</p>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
                <div>
                  <label className="block text-[var(--color-muted)] mb-1">Company Name *</label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. Nexus AI"
                    value={newName}
                    onChange={(e) => setNewName(e.target.value)}
                    className="w-full rounded border border-border bg-[var(--color-background)] px-2.5 py-1.5 text-xs"
                  />
                </div>
                <div>
                  <label className="block text-[var(--color-muted)] mb-1">Website URL</label>
                  <input
                    type="url"
                    placeholder="https://example.com"
                    value={newWebsite}
                    onChange={(e) => setNewWebsite(e.target.value)}
                    className="w-full rounded border border-border bg-[var(--color-background)] px-2.5 py-1.5 text-xs"
                  />
                </div>
                <div>
                  <label className="block text-[var(--color-muted)] mb-1">Industry</label>
                  <select
                    value={newIndustry}
                    onChange={(e) => setNewIndustry(e.target.value)}
                    className="w-full rounded border border-border bg-[var(--color-background)] px-2.5 py-1.5 text-xs"
                  >
                    {INDUSTRIES.filter((i) => i !== "All").map((i) => (
                      <option key={i} value={i}>{i}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-[var(--color-muted)] mb-1">Funding Stage</label>
                  <select
                    value={newStage}
                    onChange={(e) => setNewStage(e.target.value)}
                    className="w-full rounded border border-border bg-[var(--color-background)] px-2.5 py-1.5 text-xs"
                  >
                    {STAGES.filter((s) => s !== "All").map((s) => (
                      <option key={s} value={s}>{s}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-[var(--color-muted)] mb-1">City</label>
                  <input
                    type="text"
                    placeholder="e.g. Austin, London"
                    value={newCity}
                    onChange={(e) => setNewCity(e.target.value)}
                    className="w-full rounded border border-border bg-[var(--color-background)] px-2.5 py-1.5 text-xs"
                  />
                </div>
                <div>
                  <label className="block text-[var(--color-muted)] mb-1">Country</label>
                  <input
                    type="text"
                    placeholder="e.g. US, UK, DE"
                    value={newCountry}
                    onChange={(e) => setNewCountry(e.target.value)}
                    className="w-full rounded border border-border bg-[var(--color-background)] px-2.5 py-1.5 text-xs"
                  />
                </div>
                <div className="md:col-span-3">
                  <label className="block text-[var(--color-muted)] mb-1">Description / Value Prop</label>
                  <input
                    type="text"
                    placeholder="What problem does this startup solve?"
                    value={newDesc}
                    onChange={(e) => setNewDesc(e.target.value)}
                    className="w-full rounded border border-border bg-[var(--color-background)] px-2.5 py-1.5 text-xs"
                  />
                </div>
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowAddForm(false)}
                  className="rounded border border-border px-3 py-1 text-xs text-[var(--color-muted)] hover:bg-[var(--color-surface)]"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={addStartup.isPending || !newName.trim()}
                  className="rounded bg-[var(--color-primary)] px-4 py-1 text-xs font-medium text-white hover:opacity-90 disabled:opacity-50"
                >
                  {addStartup.isPending ? "Ingesting…" : "Save Startup"}
                </button>
              </div>
            </form>
          )}

          {/* Search bar & quick filters */}
          <div className="mt-4 space-y-3">
            <div className="flex gap-2">
              <div className="relative flex-1">
                <input
                  type="text"
                  placeholder="Search startups by name, keyword, or value proposition…"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && setAppliedQuery(query.trim())}
                  className="w-full rounded-md border border-border bg-[var(--color-background)] px-3 py-1.5 pl-8 text-xs text-[var(--color-foreground)] placeholder:text-[var(--color-muted)] focus:outline-none focus:border-[var(--color-primary)]"
                />
                <Search size={14} className="absolute left-2.5 top-2 text-[var(--color-muted)]" />
              </div>
              <button
                type="button"
                onClick={() => setAppliedQuery(query.trim())}
                className="rounded-md bg-[var(--color-primary)] px-4 py-1.5 text-xs font-medium text-white hover:opacity-90"
              >
                Search
              </button>
            </div>

            {/* Industry Pills */}
            <div className="flex flex-wrap items-center gap-1.5 pt-1">
              <span className="text-[11px] text-[var(--color-muted)] mr-1">Industry:</span>
              {INDUSTRIES.map((ind) => (
                <button
                  key={ind}
                  type="button"
                  onClick={() => setSelectedIndustry(ind)}
                  className={`rounded-full px-2.5 py-0.5 text-[11px] transition-colors ${
                    selectedIndustry === ind
                      ? "bg-[var(--color-primary)] text-white font-medium"
                      : "bg-[var(--color-surface)] text-[var(--color-muted)] hover:text-[var(--color-foreground)]"
                  }`}
                >
                  {ind}
                </button>
              ))}
            </div>

            {/* Stage Pills */}
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-[11px] text-[var(--color-muted)] mr-1">Stage:</span>
              {STAGES.map((stg) => (
                <button
                  key={stg}
                  type="button"
                  onClick={() => setSelectedStage(stg)}
                  className={`rounded-full px-2.5 py-0.5 text-[11px] transition-colors ${
                    selectedStage === stg
                      ? "bg-[var(--color-primary)] text-white font-medium"
                      : "bg-[var(--color-surface)] text-[var(--color-muted)] hover:text-[var(--color-foreground)]"
                  }`}
                >
                  {stg}
                </button>
              ))}
            </div>
          </div>
        </Card>

        {/* Startups Grid */}
        <div>
          {startupsQuery.isLoading ? (
            <div className="py-16 text-center text-xs text-[var(--color-muted)]">
              Scanning startup intelligence registry…
            </div>
          ) : startups.length === 0 ? (
            <Card>
              <EmptyState
                title="No startups found matching criteria"
                description="Try selecting 'All' filters or track a new startup using the button above."
              />
            </Card>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {startups.map((st: Startup) => (
                <Card key={st.id} className="flex flex-col justify-between hover:border-[var(--color-primary)]/40 transition-colors">
                  <div>
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <Link
                          href={`/startups/${st.id}`}
                          className="text-sm font-semibold text-[var(--color-foreground)] hover:text-[var(--color-primary)] hover:underline"
                        >
                          {st.name}
                        </Link>
                        {st.website_url && (
                          <div className="flex items-center gap-1 text-[11px] text-[var(--color-muted)] mt-0.5">
                            <a
                              href={st.website_url}
                              target="_blank"
                              rel="noreferrer noopener"
                              className="inline-flex items-center gap-1 hover:text-[var(--color-primary)]"
                            >
                              <span className="truncate max-w-[160px]">{st.website_url.replace(/^https?:\/\//, "")}</span>
                              <ExternalLink size={10} />
                            </a>
                          </div>
                        )}
                      </div>

                      <span className="inline-flex px-2 py-0.5 rounded-full text-[10px] font-medium bg-[var(--color-primary)]/10 text-[var(--color-primary)]">
                        {st.funding_stage || "Early"}
                      </span>
                    </div>

                    <p className="mt-2.5 text-xs text-[var(--color-muted)] line-clamp-2">
                      {st.description || "High-growth venture tracked in intelligence feed."}
                    </p>

                    <div className="mt-3 flex flex-wrap items-center gap-2 text-[11px] text-[var(--color-muted)]">
                      {st.industry && (
                        <span className="rounded bg-[var(--color-surface)] px-1.5 py-0.5">
                          {st.industry}
                        </span>
                      )}
                      {st.city && (
                        <span className="flex items-center gap-1">
                          <MapPin size={10} />
                          <span>{st.city}</span>
                        </span>
                      )}
                    </div>
                  </div>

                  <div className="mt-4 pt-3 border-t border-border/60 flex items-center justify-between">
                    <Link
                      href={`/startups/${st.id}`}
                      className="text-xs font-medium text-[var(--color-primary)] hover:underline"
                    >
                      View Intelligence &rarr;
                    </Link>

                    {watchlists.length > 0 && (
                      <div className="flex items-center gap-1">
                        <select
                          defaultValue=""
                          onChange={(e) => {
                            if (e.target.value) {
                              addToWatchlist(st.id, e.target.value);
                              e.target.value = "";
                            }
                          }}
                          className="rounded border border-border bg-[var(--color-background)] px-2 py-0.5 text-[10px] text-[var(--color-muted)] hover:text-[var(--color-foreground)]"
                        >
                          <option value="" disabled>+ Watchlist</option>
                          {watchlists.map((w) => (
                            <option key={w.id} value={w.id}>{w.name}</option>
                          ))}
                        </select>
                      </div>
                    )}
                  </div>
                </Card>
              ))}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
