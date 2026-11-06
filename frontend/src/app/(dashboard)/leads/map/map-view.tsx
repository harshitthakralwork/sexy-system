"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  Bookmark,
  BriefcaseBusiness,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Download,
  ExternalLink,
  Globe2,
  GlobeX,
  HelpCircle,
  Info,
  Layers,
  ListFilter,
  MapPinned,
  PauseCircle,
  RefreshCw,
  RotateCcw,
  ShieldCheck,
  Trash2,
  X,
} from "lucide-react";

import { Header } from "@/components/layout/header";
import { AppFooter } from "@/components/layout/app-footer";
import { Card, EmptyState } from "@/components/ui/card";
import { useSession } from "@/components/providers/session-provider";
import { useTaskActivity } from "@/components/providers/task-activity-provider";
import { api, getApiBase } from "@/lib/api/client";
import type { Business, BusinessList, ScanRun, ScanRunList } from "@/lib/api/types";

type WebsiteRank = "potential" | "without-first" | "has-first" | "name";
type FilterTab =
  | "all"
  | "verified_website"
  | "no_website"
  | "google_maps_only"
  | "has_phone"
  | "has_email"
  | "high_potential"
  | "needs_review";

type FilterPreset = {
  id: string;
  name: string;
  niche: string;
  city: string;
  filters: FilterTab[];
  rank: WebsiteRank;
};

const INDIA_NICHE_OPTIONS = [
  ["🔧 Plumbers", "plumbers"],
  ["⚡ Electricians", "electricians"],
  ["❄️ AC & HVAC repair", "AC repair"],
  ["🏠 Interior designers", "interior designers"],
  ["🏗️ Construction companies", "construction companies"],
  ["🏢 Real-estate agents", "real estate agents"],
  ["☀️ Solar installers", "solar installers"],
  ["🧹 Cleaning services", "cleaning services"],
  ["🚚 Movers & packers", "movers and packers"],
  ["🚗 Car repair garages", "car repair"],
  ["🦷 Dentists", "dentists"],
  ["🏥 Clinics", "clinics"],
  ["🧘 Physiotherapists", "physiotherapists"],
  ["💇 Salons & barbers", "salons"],
  ["💆 Spas", "spas"],
  ["🏋️ Gyms & fitness", "gyms"],
  ["🍽️ Restaurants", "restaurants"],
  ["☕ Cafes", "cafes"],
  ["🧁 Bakeries", "bakeries"],
  ["💍 Jewelry stores", "jewelry stores"],
  ["💒 Wedding planners", "wedding planners"],
  ["📸 Photographers", "photographers"],
  ["🎓 Coaching institutes", "coaching institutes"],
  ["👨‍🏫 Tutors", "tutors"],
  ["⚖️ Law firms", "law firms"],
  ["📊 CA & accounting firms", "CA firms"],
  ["💼 Recruitment agencies", "recruitment agencies"],
  ["💻 IT consultants", "IT consultants"],
  ["🏭 Manufacturers", "manufacturers"],
  ["📦 Wholesalers & distributors", "wholesalers"],
  ["🛋️ Furniture stores", "furniture stores"],
  ["👗 Fashion boutiques", "fashion boutiques"],
] as const;

const TARGET_CITY_OPTIONS = [
  ["🇮🇳 Bengaluru", "Bengaluru"],
  ["🇮🇳 Mumbai", "Mumbai"],
  ["🇮🇳 Delhi NCR", "Delhi NCR"],
  ["🇮🇳 Hyderabad", "Hyderabad"],
  ["🇮🇳 Pune", "Pune"],
  ["🇮🇳 Chennai", "Chennai"],
  ["🇮🇳 Ahmedabad", "Ahmedabad"],
  ["🇮🇳 Jaipur", "Jaipur"],
  ["🇮🇳 Chandigarh", "Chandigarh"],
  ["🇮🇳 Surat", "Surat"],
  ["🇮🇳 Indore", "Indore"],
  ["🇮🇳 Lucknow", "Lucknow"],
  ["🇮🇳 Kochi", "Kochi"],
  ["🇮🇳 Goa", "Goa"],
  ["🇮🇳 Noida", "Noida"],
  ["🇮🇳 Gurugram", "Gurugram"],
  ["🇺🇸 New York", "New York"],
  ["🇺🇸 Los Angeles", "Los Angeles"],
  ["🇺🇸 San Francisco", "San Francisco"],
  ["🇺🇸 Chicago", "Chicago"],
  ["🇨🇦 Toronto", "Toronto"],
  ["🇬🇧 London", "London"],
  ["🇦🇺 Sydney", "Sydney"],
  ["🇦🇪 Dubai", "Dubai"],
  ["🇸🇬 Singapore", "Singapore"],
  ["🇩🇪 Berlin", "Berlin"],
  ["🇳🇱 Amsterdam", "Amsterdam"],
  ["🇫🇷 Paris", "Paris"],
  ["🇮🇪 Dublin", "Dublin"],
  ["🇳🇿 Auckland", "Auckland"],
  ["🇿🇦 Cape Town", "Cape Town"],
  ["🌍 Remote / Global", "Global"],
] as const;

const SCAN_STAGES: Array<{ key: string; label: string }> = [
  { key: "planning", label: "1. Planning" },
  { key: "source_discovery", label: "2. Discovery" },
  { key: "page_verification", label: "3. Page Verification" },
  { key: "contact_page_checks", label: "4. Contact Checks" },
  { key: "deduplication", label: "5. Deduplication" },
  { key: "saving", label: "6. Saving" },
];

function potentialClient(business: Business) {
  let score = 0;
  const reasons: string[] = [];
  if (!business.website_url) {
    score += 35;
    reasons.push("No website listed");
  }
  if (business.phone) {
    score += 20;
    reasons.push("Public phone");
  }
  if (business.email) {
    score += 10;
    reasons.push("Public email");
  }
  if (business.rating != null && business.rating >= 4) {
    score += 10;
    reasons.push(`${business.rating.toFixed(1)}★ rating`);
  }
  if (business.review_count != null && business.review_count >= 10) {
    score += business.review_count <= 500 ? 15 : 10;
    reasons.push(`${business.review_count.toLocaleString()} reviews`);
  }
  if (business.address) {
    score += 10;
    reasons.push("Street address");
  }
  score = Math.min(score, 100);
  return {
    score,
    label: score >= 70 ? "High" : score >= 45 ? "Medium" : "Low",
    reasons,
  } as const;
}

function sourceKinds(business: Business): Set<string> {
  const kinds = new Set<string>();
  const enrichment = business.enrichment || {};
  const listings = enrichment.source_listing_urls;
  if (Array.isArray(listings)) {
    for (const listing of listings) {
      if (typeof listing !== "object" || listing === null) continue;
      const kind = (listing as Record<string, unknown>).kind;
      if (typeof kind === "string" && kind) kinds.add(kind);
    }
  }
  if (typeof enrichment.google_maps_url === "string") kinds.add("google_maps");
  if (typeof enrichment.justdial_url === "string") kinds.add("justdial");
  return kinds;
}

function isGoogleMapsOnly(business: Business): boolean {
  const kinds = sourceKinds(business);
  return kinds.size === 1 && kinds.has("google_maps");
}

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

  const [activeFilters, setActiveFilters] = useState<Set<FilterTab>>(new Set());
  const [websiteRank, setWebsiteRank] = useState<WebsiteRank>("potential");
  const [inspectingBusiness, setInspectingBusiness] = useState<Business | null>(null);
  const [showLimitations, setShowLimitations] = useState(false);
  const [showCoverageTable, setShowCoverageTable] = useState(true);
  const [presetName, setPresetName] = useState("");
  const [presets, setPresets] = useState<FilterPreset[]>([]);

  const crawling = localSearch.isRunning;
  const crawlProgress = localSearch.progress;
  const crawlStage = localSearch.stage;

  useEffect(() => {
    try {
      const stored = window.localStorage.getItem("sparkx.local-business-presets.v1");
      if (stored) setPresets(JSON.parse(stored) as FilterPreset[]);
    } catch {
      setPresets([]);
    }
  }, []);

  function persistPresets(next: FilterPreset[]) {
    setPresets(next);
    window.localStorage.setItem("sparkx.local-business-presets.v1", JSON.stringify(next));
  }

  function savePreset() {
    const name = presetName.trim();
    if (!name) return;
    const next: FilterPreset = {
      id: crypto.randomUUID(),
      name,
      niche: applied.niche || niche.trim(),
      city: applied.city || city.trim(),
      filters: [...activeFilters],
      rank: websiteRank,
    };
    persistPresets([next, ...presets.filter((item) => item.name.toLowerCase() !== name.toLowerCase())].slice(0, 12));
    setPresetName("");
    setNotice(`Saved filter preset “${name}”.`);
  }

  function applyPreset(preset: FilterPreset) {
    setNiche(preset.niche);
    setCity(preset.city);
    setApplied({ niche: preset.niche, city: preset.city });
    setActiveFilters(new Set(preset.filters));
    setWebsiteRank(preset.rank);
    setSelected(new Set());
    setNotice(`Applied filter preset “${preset.name}”.`);
  }

  // Restore fields from active background search if present
  useEffect(() => {
    if (!localSearch.isRunning) return;
    const frame = requestAnimationFrame(() => {
      if (localSearch.niche && !niche) setNiche(localSearch.niche);
      if (localSearch.city && !city) setCity(localSearch.city);
    });
    return () => cancelAnimationFrame(frame);
  }, [localSearch.isRunning, localSearch.niche, localSearch.city, niche, city]);

  // Query recent scan runs to display durable status & coverage
  const scansQuery = useQuery({
    queryKey: ["discovery-scans"],
    queryFn: () => api.get<ScanRunList>("/discovery/scans?limit=5"),
    enabled: Boolean(user),
  });

  const activeScan: ScanRun | null =
    localSearch.activeScan ||
    (scansQuery.data?.items && scansQuery.data.items.length > 0
      ? scansQuery.data.items[0]
      : null);

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

  const allRows = useMemo(() => businesses.data?.items ?? [], [businesses.data?.items]);

  const rows = useMemo(() => {
    return [...allRows]
      .filter((item) => {
        if (!activeFilters.size) return true;
        if (activeFilters.has("verified_website") && (!item.website_url || item.website_status !== "available")) return false;
        if (activeFilters.has("no_website") && item.website_url) return false;
        if (activeFilters.has("google_maps_only") && !isGoogleMapsOnly(item)) return false;
        if (activeFilters.has("has_phone") && !item.phone) return false;
        if (activeFilters.has("has_email") && !item.email) return false;
        if (activeFilters.has("high_potential") && potentialClient(item).score < 70) return false;
        if (activeFilters.has("needs_review") && item.enrichment?.completeness_status !== "needs_review") return false;
        return true;
      })
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
  }, [allRows, activeFilters, websiteRank]);

  const verifiedWebsiteCount = allRows.filter((i) => i.website_url && i.website_status === "available").length;
  const noWebsiteCount = allRows.filter((i) => !i.website_url).length;
  const googleMapsOnlyCount = allRows.filter(isGoogleMapsOnly).length;
  const hasPhoneCount = allRows.filter((i) => Boolean(i.phone)).length;
  const hasEmailCount = allRows.filter((i) => Boolean(i.email)).length;
  const highPotentialCount = allRows.filter((i) => potentialClient(i).score >= 70).length;

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
      await scansQuery.refetch();
    }
  }

  function cancelSearch() {
    localSearch.cancel();
  }

  async function resumeScan(scanId: string) {
    setSearchError(null);
    setNotice(null);
    const ok = await localSearch.resume(scanId);
    if (ok) {
      await queryClient.invalidateQueries({ queryKey: ["local-business-finder"] });
      await scansQuery.refetch();
    }
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
      <Header
        subtitle="Evidence-first local business discovery with field provenance and source coverage"
        title="Local Business Finder"
      />
      <main className="flex-1 overflow-y-auto p-4 lg:p-6">
        <div className="w-full space-y-4">
          {/* Top Discovery Card */}
          <Card className="relative z-30">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h1 className="text-xl font-semibold">Resumable Public Lead Discovery</h1>
                <p className="mt-1 text-sm text-[var(--color-muted)]">
                  Discovers local businesses from permitted public sources. Absent contact fields are never guessed.
                </p>
              </div>
              <button
                className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-white/[0.03] px-3 py-1.5 text-xs text-white/70 hover:bg-white/[0.08] hover:text-white transition"
                onClick={() => setShowLimitations((prev) => !prev)}
                type="button"
              >
                <HelpCircle size={14} />
                <span>Source Limitations & Policies</span>
                {showLimitations ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
              </button>
            </div>

            {/* Honest Limitations Collapsible Section */}
            {showLimitations && (
              <div className="mt-4 rounded-xl border border-white/10 bg-[#0c101c] p-4 text-xs text-white/80 space-y-3">
                <div className="flex items-center gap-2 font-semibold text-cyan-300">
                  <ShieldCheck size={16} />
                  <span>Honest Source Capabilities & Boundaries</span>
                </div>
                <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4">
                  <div className="rounded-lg border border-white/5 bg-white/[0.02] p-3 space-y-1.5">
                    <div className="font-semibold text-white">SearXNG (Indexed Web)</div>
                    <p className="text-[var(--color-muted)]">
                      Indexed web search for domain discovery. Honors robots.txt and HTTP status codes. Never bypasses CAPTCHAs or private indices.
                    </p>
                  </div>
                  <div className="rounded-lg border border-white/5 bg-white/[0.02] p-3 space-y-1.5">
                    <div className="font-semibold text-white">Google Maps (Public Listings)</div>
                    <p className="text-[var(--color-muted)]">
                      Reads public places, verified official website links, ratings, and coordinates. Does not scrape private APIs or defeat rate limits.
                    </p>
                  </div>
                  <div className="rounded-lg border border-white/5 bg-white/[0.02] p-3 space-y-1.5">
                    <div className="font-semibold text-white">Public Directories (Justdial / Yelp)</div>
                    <p className="text-[var(--color-muted)]">
                      Reads public HTML listing pages. If a directory masks contact details behind login walls or OTPs, fields are honestly marked not verified.
                    </p>
                  </div>
                  <div className="rounded-lg border border-white/5 bg-white/[0.02] p-3 space-y-1.5">
                    <div className="font-semibold text-white">Website & Contact Page Audits</div>
                    <p className="text-[var(--color-muted)]">
                      Audits homepage + up to 2 contact/about pages for Schema.org and mailto/tel tags. Never assumes a missing site without evidence.
                    </p>
                  </div>
                </div>
              </div>
            )}

            <div className="mt-5 grid gap-3 md:grid-cols-2">
              <SearchInput
                icon={BriefcaseBusiness}
                label="Niche"
                listId="india-niches"
                onChange={setNiche}
                onSearch={search}
                placeholder="Choose a niche or type your own…"
                tone="orange"
                value={niche}
              />
              <SearchInput
                icon={MapPinned}
                label="City"
                listId="target-cities"
                onChange={setCity}
                onSearch={search}
                placeholder="Choose a city or type your own…"
                tone="cyan"
                value={city}
              />
            </div>

            <div className="mt-3 flex gap-2">
              <button
                className="refraction-glass-btn flex-1 rounded-full border border-cyan-400/40 bg-cyan-500/20 px-4 py-2.5 text-sm font-bold text-cyan-200 shadow-[0_0_18px_rgba(0,212,255,0.25)] hover:bg-cyan-500/30 hover:text-white disabled:opacity-40 transition-all cursor-pointer"
                disabled={crawling}
                onClick={search}
                type="button"
              >
                {crawling ? (
                  <span className="inline-flex items-center gap-2">
                    <RefreshCw className="animate-spin" size={16} /> Scanning public sources…
                  </span>
                ) : (
                  "Start Public Scan"
                )}
              </button>
              {crawling && (
                <button
                  className="rounded-full border border-[var(--color-error)]/60 px-4 py-2.5 text-sm font-semibold text-[var(--color-error)] hover:bg-[var(--color-error)]/10"
                  onClick={cancelSearch}
                  type="button"
                >
                  <PauseCircle className="mr-1.5 inline" size={16} /> Pause / Cancel
                </button>
              )}
            </div>

            {/* Real Progress & Pipeline Stage Tracker */}
            {crawling && (
              <div className="mt-4 rounded-xl border border-white/10 bg-white/[0.03] p-4" role="status" aria-live="polite">
                <div className="mb-2 flex items-center justify-between text-xs">
                  <span className="font-semibold text-cyan-300">{crawlStage}</span>
                  <span className="font-mono text-cyan-200">{crawlProgress}%</span>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-white/10">
                  <div
                    className="h-full rounded-full bg-gradient-to-r from-cyan-400 to-blue-500 transition-all duration-500"
                    style={{ width: `${crawlProgress}%` }}
                  />
                </div>
                {/* Visual Pipeline Stages */}
                <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6 text-[11px]">
                  {SCAN_STAGES.map((s) => {
                    const currentStageKey = activeScan?.stage || "";
                    const isDone = activeScan?.status === "completed";
                    const isCurrent = currentStageKey === s.key;
                    return (
                      <div
                        key={s.key}
                        className={`rounded-lg border px-2 py-1.5 text-center transition ${
                          isDone || isCurrent
                            ? "border-cyan-400/40 bg-cyan-500/15 text-cyan-200 font-semibold"
                            : "border-white/5 bg-white/[0.02] text-white/40"
                        }`}
                      >
                        {s.label}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {(searchError || localSearch.error) && (
              <p className="mt-2 text-sm text-[var(--color-error)] flex items-center gap-1.5">
                <AlertCircle size={14} /> {searchError || localSearch.error}
              </p>
            )}
            {(notice || localSearch.notice) && (
              <p className="mt-2 text-sm text-cyan-300 flex items-center gap-1.5">
                <CheckCircle2 size={14} /> {notice || localSearch.notice}
              </p>
            )}
          </Card>

          {/* Source Coverage & Scan Execution Stats */}
          {activeScan && (
            <Card className="relative z-20">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex items-center gap-3">
                  <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-cyan-500/15 text-cyan-300">
                    <Layers size={18} />
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <h2 className="text-base font-semibold">
                        Scan Run: {activeScan.niche} in {activeScan.city}
                      </h2>
                      <span
                        className={`rounded-full px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wider ${
                          activeScan.status === "completed"
                            ? "bg-[var(--color-success)]/15 text-[var(--color-success)]"
                            : activeScan.status === "running"
                              ? "bg-cyan-500/20 text-cyan-300 animate-pulse"
                              : activeScan.status === "cancelled"
                                ? "bg-[var(--color-warning)]/15 text-[var(--color-warning)]"
                                : "bg-white/10 text-white/70"
                        }`}
                      >
                        {activeScan.status}
                      </span>
                    </div>
                    <p className="text-xs text-[var(--color-muted)]">
                      Created {new Date(activeScan.created_at).toLocaleTimeString()} · Retries: {activeScan.retries} · Units: {activeScan.units?.length || 0}
                    </p>
                  </div>
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  {(activeScan.status === "cancelled" || activeScan.status === "failed") && (
                    <button
                      className="inline-flex items-center gap-1.5 rounded-lg border border-cyan-400/40 bg-cyan-500/15 px-3 py-1.5 text-xs font-semibold text-cyan-200 hover:bg-cyan-500/25 transition"
                      onClick={() => resumeScan(activeScan.id)}
                      type="button"
                    >
                      <RotateCcw size={14} /> Resume Incomplete Units
                    </button>
                  )}
                  <a
                    className="inline-flex items-center gap-1.5 rounded-lg border border-white/15 bg-white/[0.04] px-3 py-1.5 text-xs font-semibold text-white/80 hover:bg-white/[0.08] hover:text-white transition"
                    href={`${getApiBase()}/discovery/scans/${activeScan.id}/export`}
                  >
                    <Download size={14} /> Export Scan Evidence CSV
                  </a>
                  <button
                    className="rounded-lg border border-white/10 p-1.5 text-white/60 hover:text-white"
                    onClick={() => setShowCoverageTable((prev) => !prev)}
                    title="Toggle coverage details"
                    type="button"
                  >
                    {showCoverageTable ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                  </button>
                </div>
              </div>

              {/* Metric Counters */}
              <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
                <div className="rounded-xl border border-white/5 bg-white/[0.02] p-3 text-center">
                  <div className="text-xs text-[var(--color-muted)]">Candidates Discovered</div>
                  <div className="mt-1 font-mono text-xl font-bold text-white">{activeScan.candidate_count}</div>
                </div>
                <div className="rounded-xl border border-white/5 bg-white/[0.02] p-3 text-center">
                  <div className="text-xs text-[var(--color-muted)]">Verified & Accepted</div>
                  <div className="mt-1 font-mono text-xl font-bold text-[var(--color-success)]">{activeScan.accepted_count}</div>
                </div>
                <div className="rounded-xl border border-white/5 bg-white/[0.02] p-3 text-center">
                  <div className="text-xs text-[var(--color-muted)]">Merged Duplicates</div>
                  <div className="mt-1 font-mono text-xl font-bold text-cyan-300">{activeScan.duplicate_count}</div>
                </div>
                <div className="rounded-xl border border-white/5 bg-white/[0.02] p-3 text-center">
                  <div className="text-xs text-[var(--color-muted)]">Rejected / Out-of-Scope</div>
                  <div className="mt-1 font-mono text-xl font-bold text-white/50">{activeScan.rejected_count}</div>
                </div>
              </div>

              {/* Source Coverage Table */}
              {showCoverageTable && activeScan.source_coverage && Object.keys(activeScan.source_coverage).length > 0 && (
                <div className="mt-4 overflow-x-auto rounded-xl border border-white/10 bg-black/20">
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="border-b border-white/10 text-white/50 uppercase tracking-wider">
                        <th className="px-3 py-2.5">Source Adapter</th>
                        <th className="px-3 py-2.5">Queries Run</th>
                        <th className="px-3 py-2.5">Pages Checked</th>
                        <th className="px-3 py-2.5">Candidates Found</th>
                        <th className="px-3 py-2.5">Accepted</th>
                        <th className="px-3 py-2.5">Duplicates</th>
                        <th className="px-3 py-2.5">Errors</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-white/5">
                      {Object.entries(activeScan.source_coverage).map(([src, stats]) => (
                        <tr key={src} className="hover:bg-white/[0.02]">
                          <td className="px-3 py-2 font-medium capitalize text-white">{src.replace("_", " ")}</td>
                          <td className="px-3 py-2 font-mono text-white/70">{stats.queries_run}</td>
                          <td className="px-3 py-2 font-mono text-white/70">{stats.pages_checked}</td>
                          <td className="px-3 py-2 font-mono text-cyan-300 font-bold">{stats.candidates_found}</td>
                          <td className="px-3 py-2 font-mono text-[var(--color-success)]">{stats.accepted}</td>
                          <td className="px-3 py-2 font-mono text-white/70">{stats.duplicates}</td>
                          <td className="px-3 py-2 font-mono text-white/50">{stats.errors}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>
          )}

          {/* Results and Filters Card */}
          <Card className="relative z-10">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold">
                  {businesses.data?.total ?? 0} businesses in workspace
                </h2>
                <p className="text-xs text-[var(--color-muted)]">
                  {verifiedWebsiteCount} with website · {noWebsiteCount} with no website · {googleMapsOnlyCount} from Google Maps only
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-error)]/50 px-3 py-2 text-sm text-[var(--color-error)] transition hover:bg-[var(--color-error)]/10 disabled:opacity-40"
                  disabled={!selected.size || deleting}
                  onClick={removeSelected}
                  type="button"
                >
                  <Trash2 size={14} /> Delete selected ({selected.size})
                </button>
                <button
                  className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-2 text-sm text-[var(--color-muted)] transition hover:border-[var(--color-error)] hover:text-[var(--color-error)] disabled:opacity-40"
                  disabled={!businesses.data?.total || deleting}
                  onClick={removeAll}
                  type="button"
                >
                  <Trash2 size={14} /> Delete all
                </button>
                <a
                  className="refraction-glass-btn inline-flex items-center gap-1.5 rounded-full border border-cyan-400/40 bg-cyan-500/20 px-3.5 py-2 text-sm font-bold text-cyan-200 shadow-[0_0_15px_rgba(0,212,255,0.2)] hover:bg-cyan-500/30 hover:text-white transition-all"
                  href={`${getApiBase()}/businesses/export?${exportParams.toString()}`}
                >
                  <Download size={14} /> Export Leads CSV
                </a>
              </div>
            </div>

            {/* Filter Tabs & Rank By */}
            <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-white/10 bg-white/[0.02] p-3">
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="mr-1 inline-flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-[var(--color-muted)]">
                  <ListFilter size={14} /> Filter
                </span>
                {(
                  [
                    ["all", `All (${allRows.length})`],
                    ["verified_website", `Has Website (${verifiedWebsiteCount})`],
                    ["no_website", `No Website (${noWebsiteCount})`],
                    ["has_phone", `Has Phone (${hasPhoneCount})`],
                    ["has_email", `Has Email (${hasEmailCount})`],
                    ["high_potential", `High Potential (${highPotentialCount})`],
                    ["needs_review", "Needs Review"],
                  ] as const
                ).map(([key, label]) => (
                  <button
                    key={key}
                    className={`rounded-full border px-3 py-1 text-xs font-semibold transition-all ${
                      key === "all" ? !activeFilters.size : activeFilters.has(key)
                        ? "refraction-glass-btn border-cyan-400/40 bg-cyan-500/20 text-cyan-200 shadow-[0_0_12px_rgba(0,212,255,0.2)]"
                        : "border-white/10 bg-white/[0.03] text-white/70 hover:border-white/20 hover:text-white"
                    }`}
                    onClick={() => {
                      if (key === "all") {
                        setActiveFilters(new Set());
                        setSelected(new Set());
                        return;
                      }
                      setActiveFilters((current) => {
                        const next = new Set(current);
                        if (next.has(key)) next.delete(key);
                        else next.add(key);
                        return next;
                      });
                      setSelected(new Set());
                    }}
                    type="button"
                  >
                    {label}
                  </button>
                ))}
                <span className="mx-1 hidden h-5 w-px bg-white/15 sm:block" aria-hidden="true" />
                <button
                  className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-semibold transition-all duration-300 ease-[cubic-bezier(0.22,1,0.36,1)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-300/70 ${
                    activeFilters.has("google_maps_only")
                      ? "border-blue-300/50 bg-blue-400/15 text-blue-100 shadow-[0_0_12px_rgba(96,165,250,0.18)]"
                      : "border-white/10 bg-white/[0.03] text-white/70 hover:border-blue-300/40 hover:text-blue-100"
                  }`}
                  onClick={() => {
                    setActiveFilters((current) => {
                      const next = new Set(current);
                      if (next.has("google_maps_only")) next.delete("google_maps_only");
                      else next.add("google_maps_only");
                      return next;
                    });
                    setSelected(new Set());
                  }}
                  type="button"
                >
                  <MapPinned size={13} /> Google Maps only ({googleMapsOnlyCount})
                </button>
              </div>

              <div className="flex items-center gap-3">
                <label className="text-xs text-[var(--color-muted)] flex items-center gap-2">
                  <span className="uppercase tracking-wide font-medium">Rank by</span>
                  <select
                    className="rounded-lg border border-border bg-[var(--color-surface)] px-2.5 py-1 text-xs text-white"
                    onChange={(event) => setWebsiteRank(event.target.value as WebsiteRank)}
                    value={websiteRank}
                  >
                    <option value="potential">Potential score</option>
                    <option value="without-first">No website first</option>
                    <option value="has-first">Has website first</option>
                    <option value="name">Name A–Z</option>
                  </select>
                </label>
                <span className="rounded-full bg-white/[0.04] px-2.5 py-1 text-xs text-[var(--color-muted)]">
                  Showing {rows.length} of {allRows.length}
                </span>
              </div>
            </div>

            <div className="mt-3 flex flex-wrap items-center gap-2 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-elevated)]/45 p-2.5">
              <Bookmark size={14} className="text-[var(--color-primary)]" />
              <input
                aria-label="Preset name"
                className="min-w-[150px] flex-1 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-2.5 py-1.5 text-xs text-[var(--color-foreground)] outline-none focus:border-[var(--color-primary)]"
                onChange={(event) => setPresetName(event.target.value)}
                onKeyDown={(event) => { if (event.key === "Enter") savePreset(); }}
                placeholder="Name this filter preset…"
                value={presetName}
              />
              <button
                className="rounded-lg border border-[var(--color-primary)]/45 px-2.5 py-1.5 text-xs font-semibold text-[var(--color-primary)] hover:border-[var(--color-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-primary)]/40"
                disabled={!presetName.trim()}
                onClick={savePreset}
                type="button"
              >
                Save preset
              </button>
              {presets.map((preset) => (
                <span key={preset.id} className="inline-flex items-center gap-1 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-2 py-1">
                  <button className="text-xs text-[var(--color-muted)] hover:text-[var(--color-foreground)]" onClick={() => applyPreset(preset)} type="button">{preset.name}</button>
                  <button aria-label={`Delete ${preset.name}`} className="text-[var(--color-muted)] hover:text-[var(--color-error)]" onClick={() => persistPresets(presets.filter((item) => item.id !== preset.id))} type="button"><X size={12} /></button>
                </span>
              ))}
            </div>

            {businesses.isError && (
              <p className="mt-4 text-sm text-[var(--color-error)]">
                Results could not be loaded: {errorMessage(businesses.error)}
              </p>
            )}

            {!businesses.isPending && rows.length === 0 && !businesses.isError && (
              <EmptyState
                description="Run a public scan above, or select a different filter tab."
                title="No matching businesses"
              />
            )}

            {/* Evidence-First Leads Table */}
            {rows.length > 0 && (
              <div className="mt-4 overflow-x-auto rounded-xl border border-border">
                <table className="w-full min-w-[1280px] text-sm">
                  <thead className="sticky top-0 z-10 bg-[var(--color-surface)]">
                    <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-[var(--color-muted)]">
                      <th className="px-3 py-3">
                        <input
                          aria-label="Select all visible businesses"
                          checked={rows.length > 0 && rows.every((row) => selected.has(row.id))}
                          className="h-4 w-4 accent-[var(--color-primary)]"
                          onChange={(event) =>
                            setSelected(event.target.checked ? new Set(rows.map((row) => row.id)) : new Set())
                          }
                          type="checkbox"
                        />
                      </th>
                      <th className="px-3 py-3">Business</th>
                      <th className="px-3 py-3">Potential</th>
                      <th className="px-3 py-3">Phone</th>
                      <th className="px-3 py-3">Email</th>
                      <th className="px-3 py-3">Rating</th>
                      <th className="px-3 py-3">Reviews</th>
                      <th className="px-3 py-3">Street Address</th>
                      <th className="px-3 py-3">Official Website</th>
                      <th className="px-3 py-3">Source Listing</th>
                      <th className="px-3 py-3 text-right">Provenance</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((business) => (
                      <BusinessRow
                        business={business}
                        checked={selected.has(business.id)}
                        key={business.id}
                        onChecked={(checked) =>
                          setSelected((current) => {
                            const next = new Set(current);
                            if (checked) next.add(business.id);
                            else next.delete(business.id);
                            return next;
                          })
                        }
                        onInspect={() => setInspectingBusiness(business)}
                      />
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>

          {/* "Why this lead" Provenance Inspection Modal */}
          {inspectingBusiness && (
            <ProvenanceModal
              business={inspectingBusiness}
              onClose={() => setInspectingBusiness(null)}
            />
          )}

          <AppFooter />
        </div>
      </main>
    </div>
  );
}

function SearchInput({
  icon: Icon,
  label,
  listId,
  onChange,
  onSearch,
  placeholder,
  tone,
  value,
}: {
  icon: typeof BriefcaseBusiness;
  label: string;
  listId?: string;
  onChange: (value: string) => void;
  onSearch: () => void;
  placeholder: string;
  tone: "orange" | "cyan";
  value: string;
}) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const options = listId === "india-niches" ? INDIA_NICHE_OPTIONS : TARGET_CITY_OPTIONS;
  const filteredOptions = options
    .filter(([optionLabel, optionValue]) =>
      `${optionLabel} ${optionValue}`.toLowerCase().includes(value.toLowerCase())
    )
    .slice(0, 12);
  const accent =
    tone === "orange"
      ? "text-orange-300 border-orange-300/30 focus-within:border-orange-300/70 focus-within:ring-orange-300/20"
      : "text-cyan-300 border-cyan-300/30 focus-within:border-cyan-300/70 focus-within:ring-cyan-300/20";

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
        <span className="flex h-6 w-6 items-center justify-center rounded-lg bg-white/[0.06]">
          <Icon size={14} />
        </span>
        <span>{label}</span>
        <span className="text-[10px] font-normal text-white/35">
          {label === "Niche" ? "What service?" : "Where?"}
        </span>
      </div>
      <div className={`flex items-center rounded-xl border bg-black/40 px-3 transition-all focus-within:ring-4 ${accent}`}>
        <input
          className="w-full bg-transparent py-2.5 text-sm text-white outline-none placeholder:text-white/35"
          onChange={(event) => {
            onChange(event.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              setOpen(false);
              onSearch();
            }
            if (event.key === "Escape") setOpen(false);
          }}
          placeholder={placeholder}
          value={value}
        />
        {value && (
          <button
            aria-label={`Clear ${label}`}
            className="mr-1 rounded-md p-1 text-white/45 transition hover:bg-white/10 hover:text-white"
            onClick={(event) => {
              event.preventDefault();
              onChange("");
              setOpen(false);
            }}
            type="button"
          >
            <X size={14} />
          </button>
        )}
        {listId && (
          <button
            aria-label={`Show ${label} suggestions`}
            className="px-1 text-xs text-white/40 hover:text-white cursor-pointer"
            onClick={() => setOpen((current) => !current)}
            type="button"
          >
            ⌄
          </button>
        )}
      </div>
      {open && listId && filteredOptions.length > 0 && (
        <div className="absolute left-0 right-0 top-[4.65rem] z-50 max-h-72 overflow-y-auto rounded-xl border border-white/20 bg-[#121624]/98 p-1.5 shadow-[0_24px_60px_rgba(0,0,0,0.85)] backdrop-blur-2xl">
          {filteredOptions.map(([optionLabel, optionValue]) => (
            <button
              key={optionValue}
              className="flex w-full items-center justify-between rounded-lg px-3 py-2.5 text-left text-sm text-white/80 transition hover:bg-white/10 hover:text-white cursor-pointer"
              onClick={() => {
                onChange(optionValue);
                setOpen(false);
              }}
              type="button"
            >
              <span className="font-medium text-white">{optionLabel}</span>
              <span className="text-[10px] text-white/40">{optionValue}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function BusinessRow({
  business,
  checked,
  onChecked,
  onInspect,
}: {
  business: Business;
  checked: boolean;
  onChecked: (checked: boolean) => void;
  onInspect: () => void;
}) {
  const potential = potentialClient(business);
  const completeness = completenessStatus(business);
  const highlight =
    potential.label === "High"
      ? "border-l-2 border-l-[var(--color-success)] bg-[var(--color-success)]/[0.055]"
      : potential.label === "Medium"
        ? "border-l-2 border-l-[var(--color-warning)] bg-[var(--color-warning)]/[0.035]"
        : "";

  return (
    <tr className={`border-b border-border/60 align-top hover:bg-[var(--color-surface)] ${highlight}`}>
      <td className="px-3 py-3">
        <input
          aria-label={`Select ${business.name}`}
          checked={checked}
          className="h-4 w-4 accent-[var(--color-primary)]"
          onChange={(event) => onChecked(event.target.checked)}
          type="checkbox"
        />
      </td>
      <td className="px-3 py-3 font-medium">
        <div>{business.name}</div>
        <CompletenessBadge value={completeness} />
      </td>
      <td className="max-w-[200px] px-3 py-3">
        <div className="flex items-center gap-2">
          <span
            className={`rounded-full px-2 py-0.5 text-[11px] font-bold ${
              potential.label === "High"
                ? "bg-[var(--color-success)]/15 text-[var(--color-success)]"
                : potential.label === "Medium"
                  ? "bg-[var(--color-warning)]/15 text-[var(--color-warning)]"
                  : "bg-[var(--color-surface)] text-[var(--color-muted)]"
            }`}
          >
            {potential.label}
          </span>
          <span className="font-mono text-xs font-semibold">{potential.score}/100</span>
        </div>
        <div className="mt-1 text-xs leading-4 text-[var(--color-muted)]">
          {potential.reasons.length ? potential.reasons.slice(0, 2).join(" · ") : "Few signals"}
        </div>
      </td>
      <td className="px-3 py-3">
        <EvidenceValue status={fieldStatus(business, "phone")} value={business.phone} />
      </td>
      <td className="px-3 py-3">
        <EvidenceValue status={fieldStatus(business, "email")} value={business.email} />
      </td>
      <td className="px-3 py-3">
        <EvidenceValue
          status={fieldStatus(business, "rating")}
          value={business.rating != null ? `${business.rating.toFixed(1)} ★` : null}
        />
      </td>
      <td className="px-3 py-3">
        <EvidenceValue
          status={fieldStatus(business, "review_count")}
          value={business.review_count != null ? business.review_count.toLocaleString() : null}
        />
      </td>
      <td className="max-w-xs px-3 py-3 text-[var(--color-muted)]">
        <EvidenceValue status={fieldStatus(business, "address")} value={business.address} />
      </td>
      <td className="px-3 py-3">
        {business.website_url ? (
          <a
            className="inline-flex items-center gap-1 text-[var(--color-info)] hover:underline"
            href={business.website_url}
            rel="noreferrer"
            target="_blank"
          >
            Visit <ExternalLink size={11} />
          </a>
        ) : (
          <span className="inline-flex items-center gap-1 text-xs text-[var(--color-warning)]">
            <GlobeX size={12} /> No website
          </span>
        )}
      </td>
      <td className="px-3 py-3">
        <a
          className="inline-flex items-center gap-1 rounded-md border border-border px-2 py-1 text-xs text-[var(--color-info)] transition hover:border-[var(--color-info)]"
          href={listingLink(business).url}
          rel="noreferrer"
          target="_blank"
        >
          {listingLink(business).label} <ExternalLink size={11} />
        </a>
      </td>
      <td className="px-3 py-3 text-right">
        <button
          className="inline-flex items-center gap-1 rounded-lg border border-cyan-400/30 bg-cyan-500/10 px-2.5 py-1 text-xs font-semibold text-cyan-200 hover:bg-cyan-500/20 hover:text-white transition"
          onClick={onInspect}
          type="button"
        >
          <Info size={12} /> Why this lead?
        </button>
      </td>
    </tr>
  );
}

function ProvenanceModal({
  business,
  onClose,
}: {
  business: Business;
  onClose: () => void;
}) {
  const potential = potentialClient(business);
  const enrichment = business.enrichment || {};
  const provenance = (enrichment.field_provenance as Record<
    string,
    {
      confidence?: number;
      extraction_method?: string;
      source_type?: string;
    }
  >) || {};
  const listingUrls = (enrichment.source_listing_urls as Array<{ kind: string; label: string; url: string }>) || [];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="relative max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-2xl border border-white/20 bg-[#101424] p-6 shadow-2xl space-y-5">
        <div className="flex items-start justify-between">
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-xl font-bold text-white">{business.name}</h3>
              <CompletenessBadge value={completenessStatus(business)} />
            </div>
            <p className="mt-1 text-xs text-[var(--color-muted)]">
              {business.address || `${business.city || ""}, ${business.country || ""}`}
            </p>
          </div>
          <button
            aria-label="Close"
            className="rounded-lg p-1.5 text-white/50 hover:bg-white/10 hover:text-white"
            onClick={onClose}
            type="button"
          >
            <X size={18} />
          </button>
        </div>

        {/* Potential Score Breakdown */}
        <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-cyan-300">
              Agency Lead Potential Score
            </span>
            <span className="font-mono text-lg font-bold text-white">{potential.score}/100</span>
          </div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {potential.reasons.map((r) => (
              <span
                key={r}
                className="rounded-md border border-cyan-400/30 bg-cyan-500/10 px-2 py-0.5 text-xs text-cyan-200"
              >
                + {r}
              </span>
            ))}
          </div>
        </div>

        {/* Verified Action Links */}
        <div className="space-y-2">
          <div className="text-xs font-semibold uppercase tracking-wider text-white/60">
            Source Action Links
          </div>
          <div className="flex flex-wrap gap-2">
            {business.website_url && (
              <a
                className="inline-flex items-center gap-1.5 rounded-lg border border-cyan-400/40 bg-cyan-500/15 px-3 py-1.5 text-xs font-semibold text-cyan-200 hover:bg-cyan-500/25"
                href={business.website_url}
                rel="noreferrer"
                target="_blank"
              >
                <Globe2 size={13} /> Visit Official Website <ExternalLink size={12} />
              </a>
            )}
            {Boolean(enrichment.justdial_url) && (
              <a
                className="inline-flex items-center gap-1.5 rounded-lg border border-orange-400/40 bg-orange-500/15 px-3 py-1.5 text-xs font-semibold text-orange-200 hover:bg-orange-500/25"
                href={enrichment.justdial_url as string}
                rel="noreferrer"
                target="_blank"
              >
                Open Justdial <ExternalLink size={12} />
              </a>
            )}
            {Boolean(enrichment.google_maps_url) && (
              <a
                className="inline-flex items-center gap-1.5 rounded-lg border border-blue-400/40 bg-blue-500/15 px-3 py-1.5 text-xs font-semibold text-blue-200 hover:bg-blue-500/25"
                href={enrichment.google_maps_url as string}
                rel="noreferrer"
                target="_blank"
              >
                Open Maps <ExternalLink size={12} />
              </a>
            )}
            {listingUrls
              .filter(
                (l) =>
                  l.url !== enrichment.justdial_url && l.url !== enrichment.google_maps_url
              )
              .map((l) => (
                <a
                  key={l.url}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-white/20 bg-white/[0.05] px-3 py-1.5 text-xs text-white/80 hover:bg-white/10 hover:text-white"
                  href={l.url}
                  rel="noreferrer"
                  target="_blank"
                >
                  {l.label} <ExternalLink size={12} />
                </a>
              ))}
          </div>
        </div>

        {/* Field-Level Provenance Table */}
        <div className="space-y-2">
          <div className="text-xs font-semibold uppercase tracking-wider text-white/60">
            Field-Level Provenance & Evidence
          </div>
          <div className="overflow-x-auto rounded-xl border border-white/10 bg-black/30">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-white/10 text-white/50 uppercase tracking-wider">
                  <th className="px-3 py-2.5">Field</th>
                  <th className="px-3 py-2.5">Value</th>
                  <th className="px-3 py-2.5">Source Adapter</th>
                  <th className="px-3 py-2.5">Extraction Method</th>
                  <th className="px-3 py-2.5">Confidence</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {[
                  ["Phone", business.phone, provenance.phone],
                  ["Email", business.email, provenance.email],
                  ["Website", business.website_url, provenance.website],
                  ["Address", business.address, provenance.address],
                  ["Rating", business.rating != null ? `${business.rating} ★` : null, provenance.rating],
                  ["Reviews", business.review_count, provenance.review_count],
                ].map(([fieldName, val, prov]) => {
                  if (!val && !prov) return null;
                  const evidence =
                    typeof prov === "object" && prov !== null
                      ? prov
                      : undefined;
                  const source = evidence?.source_type || "public_discovery";
                  const method = evidence?.extraction_method || "direct";
                  const conf =
                    evidence?.confidence != null
                      ? `${Math.round(evidence.confidence * 100)}%`
                      : "—";
                  return (
                    <tr key={fieldName as string} className="hover:bg-white/[0.02]">
                      <td className="px-3 py-2 font-medium text-white">{fieldName as string}</td>
                      <td className="max-w-[200px] truncate px-3 py-2 font-mono text-cyan-200">
                        {String(val || "—")}
                      </td>
                      <td className="px-3 py-2">
                        <span className="rounded bg-white/[0.06] px-1.5 py-0.5 capitalize text-white/80">
                          {source.replace("_", " ")}
                        </span>
                      </td>
                      <td className="px-3 py-2 font-mono text-white/60">{method}</td>
                      <td className="px-3 py-2 font-mono text-[var(--color-success)]">{conf}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>

        <div className="pt-2 text-right">
          <button
            className="rounded-lg border border-white/20 bg-white/10 px-4 py-2 text-xs font-semibold text-white hover:bg-white/20 transition"
            onClick={onClose}
            type="button"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}

type EvidenceField = "phone" | "email" | "address" | "rating" | "review_count" | "website" | "social_links";

function fieldStatus(business: Business, field: EvidenceField): string {
  const statuses = business.enrichment?.field_status as Record<string, unknown> | undefined;
  if (!statuses || typeof statuses !== "object") return "not_verified";
  const value = statuses[field];
  return typeof value === "string" ? value : "not_verified";
}

function completenessStatus(business: Business): "complete" | "partial" | "needs_review" {
  const value = business.enrichment?.completeness_status;
  return value === "complete" || value === "needs_review" ? value : "partial";
}

function EvidenceValue({ value, status }: { value: string | number | null | undefined; status: string }) {
  if (value !== null && value !== undefined && value !== "") return <>{value}</>;
  const labels: Record<string, string> = {
    not_found_after_public_page_check: "Checked — not found",
    inaccessible: "Check failed",
    not_verified: "Not verified",
  };
  return <span className="text-xs text-[var(--color-muted)]">{labels[status] ?? "Not verified"}</span>;
}

function CompletenessBadge({ value }: { value: "complete" | "partial" | "needs_review" }) {
  const classes =
    value === "complete"
      ? "bg-[var(--color-success)]/15 text-[var(--color-success)]"
      : value === "needs_review"
        ? "bg-[var(--color-warning)]/15 text-[var(--color-warning)]"
        : "bg-white/[0.06] text-[var(--color-muted)]";
  const label = value === "complete" ? "Complete" : value === "needs_review" ? "Needs review" : "Partial";
  return (
    <span className={`mt-1 inline-flex rounded-full px-2 py-0.5 text-[10px] font-semibold ${classes}`}>
      {label}
    </span>
  );
}

function listingLink(business: Business): { label: string; url: string } {
  const enrichment = business.enrichment || {};
  const website = business.website_url?.replace(/\/$/, "");
  const justdialUrl = enrichment.justdial_url;
  if (
    typeof justdialUrl === "string" &&
    justdialUrl.startsWith("https://") &&
    justdialUrl.replace(/\/$/, "") !== website
  ) {
    return { label: "Open Justdial", url: justdialUrl };
  }
  const listings = enrichment.source_listing_urls;
  if (Array.isArray(listings)) {
    const source = listings.find((value) => typeof value === "object" && value !== null) as
      | Record<string, unknown>
      | undefined;
    const sourceUrl = source?.url;
    if (
      typeof sourceUrl === "string" &&
      sourceUrl.startsWith("https://") &&
      sourceUrl.replace(/\/$/, "") !== website
    ) {
      const sourceLabel = source?.label;
      return {
        label: typeof sourceLabel === "string" ? `Open ${sourceLabel}` : "Open listing",
        url: sourceUrl,
      };
    }
  }
  const storedUrl = enrichment.google_maps_url;
  if (
    typeof storedUrl === "string" &&
    storedUrl.startsWith("https://www.google.com/maps") &&
    storedUrl.replace(/\/$/, "") !== website
  ) {
    return { label: "Open Maps", url: storedUrl };
  }
  const query = [business.name, business.address, business.city, business.state, business.country]
    .filter(Boolean)
    .join(" ");
  return {
    label: "Search Maps",
    url: `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(query)}`,
  };
}

function errorMessage(value: unknown): string {
  return value instanceof Error ? value.message : "Something went wrong.";
}
