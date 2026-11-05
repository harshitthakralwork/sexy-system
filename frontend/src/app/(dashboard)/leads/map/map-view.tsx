"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { BriefcaseBusiness, Download, ExternalLink, Globe2, GlobeX, ListFilter, MapPinned, Sparkles, Trash2, X } from "lucide-react";

import { Header } from "@/components/layout/header";
import { Card, EmptyState } from "@/components/ui/card";
import { useSession } from "@/components/providers/session-provider";
import { useTaskActivity } from "@/components/providers/task-activity-provider";
import { api, getApiBase } from "@/lib/api/client";
import type { Business, BusinessList } from "@/lib/api/types";

type WebsiteRank = "potential" | "without-first" | "has-first" | "name";

const INDIA_NICHE_OPTIONS = [
  ["🔧 Plumbers", "plumbers"], ["⚡ Electricians", "electricians"], ["❄️ AC & HVAC repair", "AC repair"],
  ["🏠 Interior designers", "interior designers"], ["🏗️ Construction companies", "construction companies"], ["🏢 Real-estate agents", "real estate agents"],
  ["☀️ Solar installers", "solar installers"], ["🧹 Cleaning services", "cleaning services"], ["🚚 Movers & packers", "movers and packers"], ["🚗 Car repair garages", "car repair"],
  ["🦷 Dentists", "dentists"], ["🏥 Clinics", "clinics"], ["🧘 Physiotherapists", "physiotherapists"], ["💇 Salons & barbers", "salons"], ["💆 Spas", "spas"],
  ["🏋️ Gyms & fitness", "gyms"], ["🍽️ Restaurants", "restaurants"], ["☕ Cafes", "cafes"], ["🧁 Bakeries", "bakeries"], ["💍 Jewelry stores", "jewelry stores"],
  ["💒 Wedding planners", "wedding planners"], ["📸 Photographers", "photographers"], ["🎓 Coaching institutes", "coaching institutes"], ["👨‍🏫 Tutors", "tutors"],
  ["⚖️ Law firms", "law firms"], ["📊 CA & accounting firms", "CA firms"], ["💼 Recruitment agencies", "recruitment agencies"], ["💻 IT consultants", "IT consultants"],
  ["🏭 Manufacturers", "manufacturers"], ["📦 Wholesalers & distributors", "wholesalers"], ["🛋️ Furniture stores", "furniture stores"], ["👗 Fashion boutiques", "fashion boutiques"],
] as const;

const TARGET_CITY_OPTIONS = [
  ["🇮🇳 Bengaluru", "Bengaluru"], ["🇮🇳 Mumbai", "Mumbai"], ["🇮🇳 Delhi NCR", "Delhi NCR"], ["🇮🇳 Hyderabad", "Hyderabad"],
  ["🇮🇳 Pune", "Pune"], ["🇮🇳 Chennai", "Chennai"], ["🇮🇳 Ahmedabad", "Ahmedabad"], ["🇮🇳 Jaipur", "Jaipur"],
  ["🇮🇳 Chandigarh", "Chandigarh"], ["🇮🇳 Surat", "Surat"], ["🇮🇳 Indore", "Indore"], ["🇮🇳 Lucknow", "Lucknow"],
  ["🇮🇳 Kochi", "Kochi"], ["🇮🇳 Goa", "Goa"], ["🇮🇳 Noida", "Noida"], ["🇮🇳 Gurugram", "Gurugram"],
  ["🇺🇸 New York", "New York"], ["🇺🇸 Los Angeles", "Los Angeles"], ["🇺🇸 San Francisco", "San Francisco"], ["🇺🇸 Chicago", "Chicago"],
  ["🇨🇦 Toronto", "Toronto"], ["🇬🇧 London", "London"], ["🇦🇺 Sydney", "Sydney"], ["🇦🇪 Dubai", "Dubai"],
  ["🇸🇬 Singapore", "Singapore"], ["🇩🇪 Berlin", "Berlin"], ["🇳🇱 Amsterdam", "Amsterdam"], ["🇫🇷 Paris", "Paris"],
  ["🇮🇪 Dublin", "Dublin"], ["🇳🇿 Auckland", "Auckland"], ["🇿🇦 Cape Town", "Cape Town"], ["🌍 Remote / Global", "Global"],
] as const;

function potentialClient(business: Business) {
  let score = 0;
  const reasons: string[] = [];
  if (!business.website_url) { score += 35; reasons.push("No website found"); }
  if (business.phone) { score += 20; reasons.push("Phone available"); }
  if (business.email) { score += 10; reasons.push("Email available"); }
  if (business.rating != null && business.rating >= 4) { score += 10; reasons.push(`${business.rating.toFixed(1)}★ rating`); }
  if (business.review_count != null && business.review_count >= 10) {
    score += business.review_count <= 500 ? 15 : 10;
    reasons.push(`${business.review_count.toLocaleString()} reviews`);
  }
  if (business.address) { score += 10; reasons.push("Address available"); }
  score = Math.min(score, 100);
  return { score, label: score >= 70 ? "High" : score >= 45 ? "Medium" : "Low", reasons } as const;
}

/** Evidence-first local finder: absent contact/review values remain absent. */
export function MapIntelligenceView() {
  const { csrf, user } = useSession();
  const queryClient = useQueryClient();
  const { localSearch } = useTaskActivity();

  const [niche, setNiche] = useState("");
  const [city, setCity] = useState("");
  const [applied, setApplied] = useState({ niche: "", city: "" });
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [deleting, setDeleting] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [searchError, setSearchError] = useState<string | null>(null);

  const crawling = localSearch.isRunning;
  const crawlProgress = localSearch.progress;
  const crawlStage = localSearch.stage;

  // Restore fields from active background search if present
  useEffect(() => {
    if (localSearch.isRunning) {
      if (localSearch.niche && !niche) setNiche(localSearch.niche);
      if (localSearch.city && !city) setCity(localSearch.city);
    }
  }, [localSearch.isRunning, localSearch.niche, localSearch.city, niche, city]);

  const [websiteFilter, setWebsiteFilter] = useState<"all" | "has" | "without">("all");
  const [websiteRank, setWebsiteRank] = useState<WebsiteRank>("potential");
  const [potentialOnly, setPotentialOnly] = useState(false);

  const params = useMemo(() => {
    const search = new URLSearchParams({ limit: "500", sort: "name", descending: "false" });
    if (applied.niche) search.set("query", applied.niche);
    if (applied.city) search.set("city", applied.city);
    return search.toString();
  }, [applied]);
  const businesses = useQuery({
    queryKey: ["local-business-finder", params],
    queryFn: () => api.get<BusinessList>(`/businesses?${params}`),
    enabled: Boolean(user),
  });

  const allRows = businesses.data?.items ?? [];
  const rows = [...allRows]
    .filter((item) => {
      if (websiteFilter === "has") return Boolean(item.website_url);
      if (websiteFilter === "without") return !item.website_url;
      return true;
    })
    .filter((item) => !potentialOnly || potentialClient(item).score >= 45)
    .sort((left, right) => {
      if (websiteRank === "potential") {
        const scoreDifference = potentialClient(right).score - potentialClient(left).score;
        if (scoreDifference !== 0) return scoreDifference;
      }
      const leftHasWebsite = left.website_url ? 1 : 0;
      const rightHasWebsite = right.website_url ? 1 : 0;
      if (websiteRank === "has-first" && leftHasWebsite !== rightHasWebsite) {
        return rightHasWebsite - leftHasWebsite;
      }
      if (websiteRank === "without-first" && leftHasWebsite !== rightHasWebsite) {
        return leftHasWebsite - rightHasWebsite;
      }
      return left.name.localeCompare(right.name);
    });
  const noWebsite = allRows.filter((item) => !item.website_url).length;
  const percent = allRows.length ? Math.round((noWebsite / allRows.length) * 100) : 0;
  const exportParams = new URLSearchParams();
  if (applied.niche) exportParams.set("query", applied.niche);
  if (applied.city) exportParams.set("city", applied.city);

  async function search() {
    const cleanNiche = niche.trim();
    const cleanCity = city.trim();
    if (cleanNiche.length < 2 || cleanCity.length < 2) {
      setSearchError("Enter both a niche and a city (at least 2 characters each).");
      return;
    }
    setSearchError(null);
    setNotice(null);
    const ok = await localSearch.start(cleanNiche, cleanCity);
    if (ok) {
      setApplied({ niche: cleanNiche, city: cleanCity });
      await queryClient.invalidateQueries({ queryKey: ["local-business-finder"] });
    }
  }

  function cancelSearch() {
    localSearch.cancel();
  }


  if (!user) return null;

  async function removeSelected() {
    const ids = [...selected];
    if (!ids.length || !window.confirm(`Delete ${ids.length} selected businesses?`)) return;
    await remove({ ids, delete_all: false });
  }

  async function removeAll() {
    if (!window.confirm(`Delete all ${businesses.data?.total ?? 0} business records?`)) return;
    await remove({ ids: [], delete_all: true });
  }

  async function remove(payload: { ids: string[]; delete_all: boolean }) {
    setDeleting(true);
    setNotice(null);
    try {
      const result = await api.post<{ deleted: number }>("/businesses/bulk-delete", payload, csrf);
      setSelected(new Set());
      setNotice(`${result.deleted} businesses deleted.`);
      await businesses.refetch();
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <Header title="Local Business Finder" subtitle="Contacts, reviews and map locations from collected evidence" />
      <main className="flex-1 overflow-y-auto p-4 lg:p-6">
        <div className="mx-auto max-w-[1500px] space-y-4">
          <Card className="relative z-30">
            <h1 className="text-xl font-semibold">Find local businesses</h1>
            <p className="mt-1 text-sm text-[var(--color-muted)]">
              Search records collected from permitted public sources. Missing values are never guessed.
            </p>
            <div className="mt-5 grid gap-3 md:grid-cols-2">
              <SearchInput icon={BriefcaseBusiness} tone="orange" label="Niche" listId="india-niches" onChange={setNiche} onSearch={search} placeholder="Choose a niche or type your own…" value={niche} />
              <SearchInput icon={MapPinned} tone="cyan" label="City" listId="target-cities" onChange={setCity} onSearch={search} placeholder="Choose a city or type your own…" value={city} />
            </div>
            <div className="mt-3 flex gap-2">
              <button className="refraction-glass-btn flex-1 rounded-full border border-cyan-400/40 bg-cyan-500/20 px-4 py-2.5 text-sm font-bold text-cyan-200 shadow-[0_0_18px_rgba(0,212,255,0.25)] hover:bg-cyan-500/30 hover:text-white disabled:opacity-40 transition-all cursor-pointer" disabled={crawling} onClick={search} type="button">
                {crawling ? "Searching public sources…" : "Search"}
              </button>
              {crawling && <button className="rounded-full border border-[var(--color-error)]/60 px-4 py-2.5 text-sm font-semibold text-[var(--color-error)] hover:bg-[var(--color-error)]/10" onClick={cancelSearch} type="button">Cancel</button>}
            </div>
            {crawling && (
              <div className="mt-3 rounded-xl border border-white/10 bg-white/[0.03] p-3" role="status" aria-live="polite">
                <div className="mb-1.5 flex justify-between text-xs text-[var(--color-muted)]"><span>{crawlStage}</span><span>{crawlProgress}%</span></div>
                <div className="h-2 overflow-hidden rounded-full bg-white/10"><div className="h-full rounded-full bg-cyan-400 transition-all duration-500" style={{ width: `${crawlProgress}%` }} /></div>
              </div>
            )}
            {(searchError || localSearch.error) && <p className="mt-2 text-sm text-[var(--color-error)]">{searchError || localSearch.error}</p>}
            {(notice || localSearch.notice) && <p className="mt-2 text-sm text-cyan-300">{notice || localSearch.notice}</p>}
            <p className="mt-2 text-xs text-[var(--color-muted)]">
              No Google API key is used. Map links open a normal Google Maps browser search.
            </p>
          </Card>

          <Card className="relative z-10">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold">{businesses.data?.total ?? 0} businesses found, {noWebsite} with no website ({percent}%)</h2>
                <p className="text-xs text-[var(--color-muted)]">Showing up to 500 matches. Phone, email and reviews are source-reported only.</p>
              </div>
              <div className="flex flex-wrap gap-2">
                <button className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-error)]/50 px-3 py-2 text-sm text-[var(--color-error)] transition hover:bg-[var(--color-error)]/10 disabled:opacity-40" disabled={!selected.size || deleting} onClick={removeSelected} type="button"><Trash2 size={14} /> Delete selected ({selected.size})</button>
                <button className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-2 text-sm text-[var(--color-muted)] transition hover:border-[var(--color-error)] hover:text-[var(--color-error)] disabled:opacity-40" disabled={!businesses.data?.total || deleting} onClick={removeAll} type="button"><Trash2 size={14} /> Delete all</button>
                <a className="refraction-glass-btn inline-flex items-center gap-1.5 rounded-full border border-cyan-400/40 bg-cyan-500/20 px-3.5 py-2 text-sm font-bold text-cyan-200 shadow-[0_0_15px_rgba(0,212,255,0.2)] hover:bg-cyan-500/30 hover:text-white transition-all" href={`${getApiBase()}/businesses/export?${exportParams.toString()}`}><Download size={14} /> Download CSV</a>
              </div>
            </div>
            {notice && <p className="mt-3 text-sm text-[var(--color-success)]">{notice}</p>}
            <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-white/10 bg-white/[0.02] p-3">
              <div className="flex flex-wrap items-center gap-2">
                <span className="mr-1 inline-flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-[var(--color-muted)]"><ListFilter size={14} /> Filter</span>
                {([['all', 'All', null], ['has', 'Has website', Globe2], ['without', 'No website', GlobeX]] as const).map(([value, label, Icon]) => (
                  <button
                    className={`inline-flex items-center gap-1.5 rounded-full border px-3.5 py-1.5 text-sm font-semibold transition-all ${websiteFilter === value ? "refraction-glass-btn border-cyan-400/40 bg-cyan-500/20 text-cyan-200 shadow-[0_0_12px_rgba(0,212,255,0.2)]" : "border-white/10 bg-white/[0.04] text-white/70 hover:border-white/25 hover:text-white"}`}
                    key={value}
                    onClick={() => { setWebsiteFilter(value); setSelected(new Set()); }}
                    type="button"
                  >
                    {Icon ? <Icon size={14} /> : null}{label}
                  </button>
                ))}
                <button
                  aria-pressed={potentialOnly}
                  className={`inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-sm font-semibold transition ${potentialOnly ? "border-[var(--color-success)] bg-[var(--color-success)]/10 text-[var(--color-success)]" : "border-border text-[var(--color-muted)] hover:border-[var(--color-success)]/60"}`}
                  onClick={() => { setPotentialOnly((current) => !current); setSelected(new Set()); }}
                  type="button"
                >
                  <Sparkles size={14} /> Potential clients
                </button>
              </div>
              <label className="text-sm">
                <span className="mr-2 text-xs font-medium uppercase tracking-wide text-[var(--color-muted)]">Rank by</span>
                <select
                  className="rounded-lg border border-border bg-[var(--color-surface)] px-3 py-1.5"
                  onChange={(event) => setWebsiteRank(event.target.value as WebsiteRank)}
                  value={websiteRank}
                >
                  <option value="potential">Potential score</option>
                  <option value="without-first">No website first</option>
                  <option value="has-first">Has website first</option>
                  <option value="name">Name A–Z</option>
                </select>
              </label>
              <span className="rounded-full bg-[var(--color-surface)] px-3 py-1.5 text-xs text-[var(--color-muted)]">
                Showing {rows.length} of {allRows.length} loaded businesses
              </span>
            </div>
            {businesses.isError && <p className="mt-4 text-sm text-[var(--color-error)]">Results could not be loaded: {errorMessage(businesses.error)}</p>}
            {!businesses.isPending && rows.length === 0 && !businesses.isError && <EmptyState title="No matching businesses" description="Run discovery first, or change the niche and city filters." />}
            {rows.length > 0 && (
              <div className="mt-4 overflow-x-auto rounded-xl border border-border">
                <table className="w-full min-w-[1240px] text-sm">
                  <thead className="sticky top-0 z-10 bg-[var(--color-surface)]"><tr className="border-b border-border text-left text-xs uppercase tracking-wide text-[var(--color-muted)]">
                    <th className="px-3 py-3"><input className="h-4 w-4 accent-[var(--color-primary)]" aria-label="Select all visible businesses" checked={rows.length > 0 && rows.every((row) => selected.has(row.id))} onChange={(event) => setSelected(event.target.checked ? new Set(rows.map((row) => row.id)) : new Set())} type="checkbox" /></th>
                    {['Name','Potential','Phone','Email','Rating','Reviews','Address','Website','Maps'].map((label) => <th className="px-3 py-3" key={label}>{label}</th>)}
                  </tr></thead>
                  <tbody>{rows.map((business) => <BusinessRow business={business} checked={selected.has(business.id)} key={business.id} onChecked={(checked) => setSelected((current) => { const next = new Set(current); if (checked) next.add(business.id); else next.delete(business.id); return next; })} />)}</tbody>
                </table>
              </div>
            )}
          </Card>
        </div>
      </main>
    </div>
  );
}

function SearchInput({ icon: Icon, label, listId, onChange, onSearch, placeholder, tone, value }: { icon: typeof BriefcaseBusiness; label: string; listId?: string; onChange: (value: string) => void; onSearch: () => void; placeholder: string; tone: "orange" | "cyan"; value: string }) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const options = listId === "india-niches" ? INDIA_NICHE_OPTIONS : TARGET_CITY_OPTIONS;
  const filteredOptions = options.filter(([optionLabel, optionValue]) => `${optionLabel} ${optionValue}`.toLowerCase().includes(value.toLowerCase())).slice(0, 12);
  const accent = tone === "orange" ? "text-orange-300 border-orange-300/30 focus-within:border-orange-300/70 focus-within:ring-orange-300/20" : "text-cyan-300 border-cyan-300/30 focus-within:border-cyan-300/70 focus-within:ring-cyan-300/20";

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    if (open) {
      document.addEventListener("mousedown", handleClickOutside);
      return () => document.removeEventListener("mousedown", handleClickOutside);
    }
  }, [open]);

  return (
    <div ref={containerRef} className={`relative ${open ? "z-50" : "z-20"} text-sm`}>
      <div className={`mb-1.5 flex items-center gap-2 font-semibold ${accent.split(" ")[0]}`}>
        <span className="flex h-6 w-6 items-center justify-center rounded-lg bg-white/[0.06]"><Icon size={14} /></span>
        <span>{label}</span>
        <span className="text-[10px] font-normal text-white/35">{label === "Niche" ? "What service?" : "Where?"}</span>
      </div>
      <div className={`flex items-center rounded-xl border bg-black/40 px-3 transition-all focus-within:ring-4 ${accent}`}>
        <input
          className="w-full bg-transparent py-2.5 text-sm text-white outline-none placeholder:text-white/35"
          onFocus={() => setOpen(true)}
          onChange={(event) => { onChange(event.target.value); setOpen(true); }}
          onKeyDown={(event) => {
            if (event.key === "Enter") { setOpen(false); onSearch(); }
            if (event.key === "Escape") setOpen(false);
          }}
          placeholder={placeholder}
          value={value}
        />
        {value && (
          <button aria-label={`Clear ${label}`} className="mr-1 rounded-md p-1 text-white/45 transition hover:bg-white/10 hover:text-white" onClick={(event) => { event.preventDefault(); onChange(""); setOpen(false); }} type="button">
            <X size={14} />
          </button>
        )}
        {listId && (
          <button aria-label={`Show ${label} suggestions`} className="px-1 text-xs text-white/40 hover:text-white cursor-pointer" onClick={() => setOpen((current) => !current)} type="button">
            ⌄
          </button>
        )}
      </div>
      {open && listId && filteredOptions.length > 0 && (
        <div className="absolute left-0 right-0 top-[4.65rem] z-50 max-h-72 overflow-y-auto rounded-xl border border-white/20 bg-[#121624]/98 p-1.5 shadow-[0_24px_60px_rgba(0,0,0,0.85)] backdrop-blur-2xl">
          {filteredOptions.map(([optionLabel, optionValue]) => (
            <button className="flex w-full items-center justify-between rounded-lg px-3 py-2.5 text-left text-sm text-white/80 transition hover:bg-white/10 hover:text-white cursor-pointer" key={optionValue} onClick={() => { onChange(optionValue); setOpen(false); }} type="button">
              <span className="font-medium text-white">{optionLabel}</span>
              <span className="text-[10px] text-white/40">{optionValue}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function BusinessRow({ business, checked, onChecked }: { business: Business; checked: boolean; onChecked: (checked: boolean) => void }) {
  const address = business.address ?? ([business.city, business.state, business.country].filter(Boolean).join(", ") || "—");
  const potential = potentialClient(business);
  const highlight = potential.label === "High" ? "border-l-2 border-l-[var(--color-success)] bg-[var(--color-success)]/[0.055]" : potential.label === "Medium" ? "border-l-2 border-l-[var(--color-warning)] bg-[var(--color-warning)]/[0.035]" : "";
  return <tr className={`border-b border-border/60 align-top hover:bg-[var(--color-surface)] ${highlight}`}>
    <td className="px-3 py-3"><input className="h-4 w-4 accent-[var(--color-primary)]" aria-label={`Select ${business.name}`} checked={checked} onChange={(event) => onChecked(event.target.checked)} type="checkbox" /></td>
    <td className="px-3 py-3 font-medium">{business.name}</td>
    <td className="max-w-[240px] px-3 py-3">
      <div className="flex items-center gap-2"><span className={`rounded-full px-2 py-0.5 text-[11px] font-bold ${potential.label === "High" ? "bg-[var(--color-success)]/15 text-[var(--color-success)]" : potential.label === "Medium" ? "bg-[var(--color-warning)]/15 text-[var(--color-warning)]" : "bg-[var(--color-surface)] text-[var(--color-muted)]"}`}>{potential.label}</span><span className="font-mono text-xs font-semibold">{potential.score}/100</span></div>
      <div className="mt-1 text-xs leading-5 text-[var(--color-muted)]">{potential.reasons.length ? potential.reasons.slice(0, 3).join(" · ") : "Not enough signals"}</div>
    </td>
    <td className="px-3 py-3">{business.phone ?? "—"}</td><td className="px-3 py-3">{business.email ?? "—"}</td>
    <td className="px-3 py-3">{business.rating != null ? `${business.rating.toFixed(1)} ★` : "—"}</td><td className="px-3 py-3">{business.review_count ?? "—"}</td><td className="max-w-xs px-3 py-3 text-[var(--color-muted)]">{address}</td>
    <td className="px-3 py-3">{business.website_url ? <a className="text-[var(--color-info)] hover:underline" href={business.website_url} rel="noreferrer" target="_blank">Website</a> : <span className="text-[var(--color-muted)]">No website</span>}</td>
    <td className="px-3 py-3"><a className="inline-flex items-center gap-1 rounded-md border border-border px-2 py-1 text-xs text-[var(--color-info)] transition hover:border-[var(--color-info)]" href={mapsUrl(business)} rel="noreferrer" target="_blank">Open profile <ExternalLink size={12} /></a></td>
  </tr>;
}

function mapsUrl(business: Business): string {
  const storedUrl = business.enrichment.google_maps_url;
  if (typeof storedUrl === "string" && storedUrl.startsWith("https://www.google.com/maps")) {
    return storedUrl;
  }
  const query = [business.name, business.address, business.city, business.state, business.country].filter(Boolean).join(" ");
  return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(query)}`;
}

function errorMessage(value: unknown): string { return value instanceof Error ? value.message : "Something went wrong."; }
