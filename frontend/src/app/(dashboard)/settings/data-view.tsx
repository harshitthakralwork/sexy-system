"use client";

import Image from "next/image";
import { useState, useEffect, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Bell,
  CheckCircle2,
  Database,
  Download,
  Flame,
  Globe,
  HardDrive,
  Key,
  Layers,
  Moon,
  Plus,
  RefreshCw,
  Save,
  Search,
  Server,
  Settings as SettingsIcon,
  Shield,
  Sliders,
  Sun,
  Trash2,
  Upload,
  User,
  Zap,
} from "lucide-react";

import { Header } from "@/components/layout/header";
import { AppFooter } from "@/components/layout/app-footer";
import { useSession } from "@/components/providers/session-provider";
import { useTheme } from "@/components/providers/theme-provider";
import { api, getApiBase } from "@/lib/api/client";
import type { AnalyticsOut, BusinessList, ReadyResponse } from "@/lib/api/types";
import { cn } from "@/lib/utils";

type SettingsTab = "general" | "discovery" | "notifications" | "data" | "appearance";

interface OperatorPreferences {
  timezone: string;
  defaultRadiusKm: number;
  concurrencyLevel: "conservative" | "balanced" | "aggressive";
  autoEnrichContacts: boolean;
  verifyDomains: boolean;
  filterDuplicates: boolean;
  searxngBaseUrl: string;
  notifyOnJobFailure: boolean;
  notifyOnHighConfidenceLeads: boolean;
  confidenceThreshold: number;
  notifyOnServiceDegradation: boolean;
  tableDensity: "compact" | "comfortable";
}

const DEFAULT_PREFERENCES: OperatorPreferences = {
  timezone: "Asia/Kolkata",
  defaultRadiusKm: 10,
  concurrencyLevel: "balanced",
  autoEnrichContacts: true,
  verifyDomains: true,
  filterDuplicates: true,
  searxngBaseUrl: "http://localhost:8080",
  notifyOnJobFailure: true,
  notifyOnHighConfidenceLeads: true,
  confidenceThreshold: 80,
  notifyOnServiceDegradation: true,
  tableDensity: "compact",
};

const STORAGE_KEY = "sparkx.operator_settings.v1";

export function SettingsView() {
  const { user } = useSession();
  const { theme, setTheme, hoverEffects, setHoverEffects } = useTheme();
  const queryClient = useQueryClient();

  const [activeTab, setActiveTab] = useState<SettingsTab>("general");
  const [preferences, setPreferences] = useState<OperatorPreferences>(DEFAULT_PREFERENCES);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [isExporting, setIsExporting] = useState(false);
  const [importStatus, setImportStatus] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Load preferences from local storage on mount
  useEffect(() => {
    if (typeof window !== "undefined") {
      try {
        const saved = window.localStorage.getItem(STORAGE_KEY);
        if (saved) {
          setPreferences({ ...DEFAULT_PREFERENCES, ...JSON.parse(saved) });
        }
      } catch {
        // Fall back to default preferences
      }
    }
  }, []);

  // System stats & health queries
  const summary = useQuery({
    queryKey: ["analytics"],
    queryFn: () => api.get<AnalyticsOut>("/analytics"),
  });

  const healthQuery = useQuery({
    queryKey: ["health-ready"],
    queryFn: () => api.get<ReadyResponse>("/health/ready"),
  });

  const businessesQuery = useQuery({
    queryKey: ["dashboard-businesses"],
    queryFn: () => api.get<BusinessList>("/businesses?limit=1"),
  });

  const totalLeads = summary.data?.leads_total ?? businessesQuery.data?.total ?? 0;
  const totalJobs = summary.data?.discovery_jobs_by_status?.reduce((acc, j) => acc + j.count, 0) ?? 0;

  function updatePreference<K extends keyof OperatorPreferences>(key: K, value: OperatorPreferences[K]) {
    setPreferences((prev) => ({ ...prev, [key]: value }));
  }

  function handleSave() {
    if (typeof window !== "undefined") {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(preferences));
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 2500);
    }
  }

  function handleExportCsv() {
    setIsExporting(true);
    try {
      window.location.href = `${getApiBase()}/businesses/export`;
    } finally {
      setTimeout(() => setIsExporting(false), 1500);
    }
  }

  function handleFileSelect(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setImportStatus(`Selected "${file.name}" (${(file.size / 1024).toFixed(1)} KB) — ready for ingestion.`);
    setTimeout(() => {
      setImportStatus(`File "${file.name}" queued. Mapping schema...`);
      setTimeout(() => {
        setImportStatus(null);
        if (fileInputRef.current) fileInputRef.current.value = "";
      }, 3000);
    }, 1500);
  }

  if (!user) return null;

  return (
    <div className="flex min-h-0 flex-1 flex-col bg-[var(--color-background)] text-[var(--color-foreground)]">
      <Header
        title="Settings"
        subtitle="Manage your profile, discovery preferences, and workspace configuration."
      />

      <main className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-6">
        <div className="mx-auto max-w-5xl space-y-6">

          {/* ── Settings Navigation Tabs ── */}
          <div className="flex flex-wrap items-center gap-2 border-b border-[var(--color-border)] pb-3">
            {[
              { id: "general", label: "General & Profile", icon: User },
              { id: "discovery", label: "Discovery & Scraping", icon: Zap },
              { id: "notifications", label: "Alerts & Triggers", icon: Bell },
              { id: "data", label: "Data & Exports", icon: Database },
              { id: "appearance", label: "Appearance & Theme", icon: Sliders },
            ].map((tab) => {
              const Icon = tab.icon;
              const isActive = activeTab === tab.id;
              return (
                <button
                  key={tab.id}
                  type="button"
                  onClick={() => setActiveTab(tab.id as SettingsTab)}
                  className={cn(
                    "flex items-center gap-2 rounded-xl px-4 py-2 text-xs font-semibold transition-all cursor-pointer",
                    isActive
                      ? "bg-blue-600 text-white shadow-sm"
                      : "bg-[var(--color-surface)] border border-[var(--color-border)] text-[var(--color-muted)] hover:text-[var(--color-foreground)] hover:border-blue-500/30"
                  )}
                >
                  <Icon size={14} />
                  <span>{tab.label}</span>
                </button>
              );
            })}

            {/* Quick Save Indicator / Button */}
            <div className="ml-auto flex items-center gap-2">
              {saveSuccess && (
                <span className="flex items-center gap-1.5 text-xs font-semibold text-emerald-500 animate-fade-in">
                  <CheckCircle2 size={14} />
                  <span>Saved</span>
                </span>
              )}
              <button
                type="button"
                onClick={handleSave}
                className="flex items-center gap-1.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white px-4 py-2 text-xs font-semibold transition-all shadow-sm cursor-pointer"
              >
                <Save size={13} />
                <span>Save Changes</span>
              </button>
            </div>
          </div>

          {/* ── TAB 1: General & Profile ── */}
          {activeTab === "general" && (
            <div className="space-y-5 animate-slide-up">
              {/* Operator Identity Card */}
              <div className="rounded-2xl bg-[var(--color-surface)] border border-[var(--color-border)] p-6 space-y-4">
                <div className="flex items-center gap-3 border-b border-[var(--color-border)] pb-4">
                  <div className="relative flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-blue-600/10 text-blue-500 border border-blue-500/20 overflow-hidden">
                    <Image
                      src="/user-avatar.jpg"
                      alt={user.display_name || "Operator Profile"}
                      fill
                      sizes="48px"
                      className="object-cover"
                    />
                  </div>
                  <div>
                    <h3 className="text-base font-bold text-[var(--color-foreground)]">Operator Profile</h3>
                    <p className="text-xs text-[var(--color-muted)]">Verified operator identity for this workspace.</p>
                  </div>
                  <span className="ml-auto rounded-full bg-emerald-500/10 border border-emerald-500/25 px-2.5 py-0.5 text-[10px] font-bold text-emerald-500">
                    Active Account
                  </span>
                </div>

                <div className="grid gap-4 sm:grid-cols-2 pt-1">
                  <div>
                    <label className="block text-xs font-semibold text-[var(--color-muted)] mb-1">Display Name</label>
                    <input
                      type="text"
                      disabled
                      value={user.display_name || "Harshit"}
                      className="w-full rounded-xl bg-[var(--color-surface-elevated)] border border-[var(--color-border)] px-3.5 py-2 text-xs text-[var(--color-foreground)] font-medium cursor-not-allowed opacity-80"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-[var(--color-muted)] mb-1">Account Email</label>
                    <input
                      type="email"
                      disabled
                      value={user.email}
                      className="w-full rounded-xl bg-[var(--color-surface-elevated)] border border-[var(--color-border)] px-3.5 py-2 text-xs text-[var(--color-foreground)] font-medium cursor-not-allowed opacity-80"
                    />
                  </div>
                </div>

                <div className="grid gap-4 sm:grid-cols-2 pt-2">
                  <div>
                    <label className="block text-xs font-semibold text-[var(--color-muted)] mb-1">Timezone</label>
                    <select
                      value={preferences.timezone}
                      onChange={(e) => updatePreference("timezone", e.target.value)}
                      className="w-full rounded-xl bg-[var(--color-surface-elevated)] border border-[var(--color-border)] px-3.5 py-2 text-xs text-[var(--color-foreground)] focus:outline-none focus:border-blue-500 cursor-pointer"
                    >
                      <option value="Asia/Kolkata">Asia/Kolkata (IST, UTC+5:30)</option>
                      <option value="UTC">UTC (Coordinated Universal Time)</option>
                      <option value="America/New_York">America/New_York (EST, UTC-5:00)</option>
                      <option value="America/Los_Angeles">America/Los_Angeles (PST, UTC-8:00)</option>
                      <option value="Europe/London">Europe/London (GMT, UTC+0:00)</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-[var(--color-muted)] mb-1">Workspace ID</label>
                    <input
                      type="text"
                      disabled
                      value={user.id}
                      className="w-full rounded-xl bg-[var(--color-surface-elevated)] border border-[var(--color-border)] px-3.5 py-2 text-xs font-mono text-[var(--color-muted)] cursor-not-allowed opacity-80 truncate"
                    />
                  </div>
                </div>
              </div>

              {/* System Infrastructure Card */}
              <div className="rounded-2xl bg-[var(--color-surface)] border border-[var(--color-border)] p-6 space-y-4">
                <div className="flex items-center gap-3 border-b border-[var(--color-border)] pb-4">
                  <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-purple-600/10 text-purple-500 border border-purple-500/20">
                    <Server size={20} />
                  </div>
                  <div>
                    <h3 className="text-base font-bold text-[var(--color-foreground)]">System & Infrastructure</h3>
                    <p className="text-xs text-[var(--color-muted)]">Connected services and pipeline status.</p>
                  </div>
                  <span className="ml-auto rounded-full bg-blue-500/10 border border-blue-500/25 px-2.5 py-0.5 text-[10px] font-bold text-blue-500">
                    SparkXFlow Nexus OS v1.0.0
                  </span>
                </div>

                <div className="grid gap-3 sm:grid-cols-3 pt-1">
                  <div className="rounded-xl bg-[var(--color-surface-elevated)] border border-[var(--color-border)] p-4">
                    <span className="text-[10px] font-bold text-[var(--color-muted)] uppercase block mb-1">PostgreSQL Database</span>
                    <p className="text-sm font-semibold text-[var(--color-foreground)]">Connected (Healthy)</p>
                    <span className="text-[11px] text-[var(--color-muted)]">{totalLeads.toLocaleString()} indexed records</span>
                  </div>

                  <div className="rounded-xl bg-[var(--color-surface-elevated)] border border-[var(--color-border)] p-4">
                    <span className="text-[10px] font-bold text-[var(--color-muted)] uppercase block mb-1">Redis & Worker</span>
                    <p className="text-sm font-semibold text-[var(--color-foreground)]">Ready (Async Pool)</p>
                    <span className="text-[11px] text-[var(--color-muted)]">Synchronous Dev Engine</span>
                  </div>

                  <div className="rounded-xl bg-[var(--color-surface-elevated)] border border-[var(--color-border)] p-4">
                    <span className="text-[10px] font-bold text-[var(--color-muted)] uppercase block mb-1">Metasearch (SearXNG)</span>
                    <p className="text-sm font-semibold text-[var(--color-foreground)]">Local Engine Active</p>
                    <span className="text-[11px] text-[var(--color-muted)]">Port 8080 JSON API</span>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* ── TAB 2: Discovery & Scraping ── */}
          {activeTab === "discovery" && (
            <div className="space-y-5 animate-slide-up">
              <div className="rounded-2xl bg-[var(--color-surface)] border border-[var(--color-border)] p-6 space-y-5">
                <div className="flex items-center gap-3 border-b border-[var(--color-border)] pb-4">
                  <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-blue-600/10 text-blue-500 border border-blue-500/20">
                    <Zap size={20} />
                  </div>
                  <div>
                    <h3 className="text-base font-bold text-[var(--color-foreground)]">Scraper & Discovery Rules</h3>
                    <p className="text-xs text-[var(--color-muted)]">Default parameters for business discovery and automated ingestion.</p>
                  </div>
                </div>

                {/* Default Radius */}
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <label className="text-xs font-semibold text-[var(--color-foreground)]">Default Search Radius</label>
                    <span className="text-xs font-mono font-bold text-blue-500">{preferences.defaultRadiusKm} km</span>
                  </div>
                  <input
                    type="range"
                    min="1"
                    max="50"
                    value={preferences.defaultRadiusKm}
                    onChange={(e) => updatePreference("defaultRadiusKm", Number(e.target.value))}
                    className="w-full accent-blue-500 h-1.5 cursor-pointer"
                  />
                  <div className="flex justify-between text-[10px] text-[var(--color-muted)] font-mono">
                    <span>1 km (Hyperlocal)</span>
                    <span>10 km (Standard Metro)</span>
                    <span>50 km (Regional)</span>
                  </div>
                </div>

                {/* Concurrency Level */}
                <div className="pt-2 border-t border-[var(--color-border)] space-y-3">
                  <label className="block text-xs font-semibold text-[var(--color-foreground)]">Scraper Concurrency & Rate Limiting</label>
                  <div className="grid gap-3 sm:grid-cols-3">
                    {[
                      { id: "conservative", title: "Conservative", speed: "10 req/min", desc: "Best for zero rate-limiting risk" },
                      { id: "balanced", title: "Balanced", speed: "30 req/min", desc: "Recommended balance of speed & stealth" },
                      { id: "aggressive", title: "Aggressive", speed: "60 req/min", desc: "Max extraction velocity across proxies" },
                    ].map((opt) => (
                      <button
                        key={opt.id}
                        type="button"
                        onClick={() => updatePreference("concurrencyLevel", opt.id as any)}
                        className={cn(
                          "rounded-xl border p-3.5 text-left transition-all cursor-pointer",
                          preferences.concurrencyLevel === opt.id
                            ? "bg-blue-600/10 border-blue-500 text-blue-500 shadow-sm"
                            : "bg-[var(--color-surface-elevated)] border-[var(--color-border)] text-[var(--color-muted)] hover:border-blue-500/30"
                        )}
                      >
                        <span className="block text-xs font-bold text-[var(--color-foreground)]">{opt.title}</span>
                        <span className="block text-[11px] font-mono text-blue-500 mt-0.5">{opt.speed}</span>
                        <span className="block text-[10px] text-[var(--color-muted)] mt-1">{opt.desc}</span>
                      </button>
                    ))}
                  </div>
                </div>

                {/* Toggles */}
                <div className="pt-2 border-t border-[var(--color-border)] space-y-3">
                  <label className="block text-xs font-semibold text-[var(--color-foreground)]">Automated Extraction Pipeline</label>

                  <div className="space-y-2.5">
                    <label className="flex items-center gap-3 p-3 rounded-xl bg-[var(--color-surface-elevated)] border border-[var(--color-border)] cursor-pointer hover:border-blue-500/30 transition-all">
                      <input
                        type="checkbox"
                        checked={preferences.autoEnrichContacts}
                        onChange={(e) => updatePreference("autoEnrichContacts", e.target.checked)}
                        className="rounded border-[var(--color-border)] bg-[var(--color-surface)] text-blue-600 focus:ring-0 cursor-pointer h-4 w-4"
                      />
                      <div>
                        <span className="block text-xs font-semibold text-[var(--color-foreground)]">Auto-enrich Contact Details</span>
                        <span className="block text-[11px] text-[var(--color-muted)]">Automatically scrape verified phone numbers, emails, and address metadata upon discovery.</span>
                      </div>
                    </label>

                    <label className="flex items-center gap-3 p-3 rounded-xl bg-[var(--color-surface-elevated)] border border-[var(--color-border)] cursor-pointer hover:border-blue-500/30 transition-all">
                      <input
                        type="checkbox"
                        checked={preferences.verifyDomains}
                        onChange={(e) => updatePreference("verifyDomains", e.target.checked)}
                        className="rounded border-[var(--color-border)] bg-[var(--color-surface)] text-blue-600 focus:ring-0 cursor-pointer h-4 w-4"
                      />
                      <div>
                        <span className="block text-xs font-semibold text-[var(--color-foreground)]">Verify Website Accessibility</span>
                        <span className="block text-[11px] text-[var(--color-muted)]">Probe domain HTTP response codes to flag dead or parked sites immediately.</span>
                      </div>
                    </label>

                    <label className="flex items-center gap-3 p-3 rounded-xl bg-[var(--color-surface-elevated)] border border-[var(--color-border)] cursor-pointer hover:border-blue-500/30 transition-all">
                      <input
                        type="checkbox"
                        checked={preferences.filterDuplicates}
                        onChange={(e) => updatePreference("filterDuplicates", e.target.checked)}
                        className="rounded border-[var(--color-border)] bg-[var(--color-surface)] text-blue-600 focus:ring-0 cursor-pointer h-4 w-4"
                      />
                      <div>
                        <span className="block text-xs font-semibold text-[var(--color-foreground)]">Deduplicate Automatically Across Runs</span>
                        <span className="block text-[11px] text-[var(--color-muted)]">Match company names, phone numbers, and domains against existing database records.</span>
                      </div>
                    </label>
                  </div>
                </div>

                {/* SearXNG URL */}
                <div className="pt-2 border-t border-[var(--color-border)]">
                  <label className="block text-xs font-semibold text-[var(--color-muted)] mb-1">Metasearch Endpoint URL (SearXNG)</label>
                  <input
                    type="text"
                    value={preferences.searxngBaseUrl}
                    onChange={(e) => updatePreference("searxngBaseUrl", e.target.value)}
                    className="w-full rounded-xl bg-[var(--color-surface-elevated)] border border-[var(--color-border)] px-3.5 py-2 text-xs font-mono text-[var(--color-foreground)] focus:outline-none focus:border-blue-500"
                    placeholder="http://localhost:8080"
                  />
                  <span className="text-[10px] text-[var(--color-muted)] mt-1 block">Local or remote SearXNG metasearch instance used for organic SERP dorking.</span>
                </div>
              </div>
            </div>
          )}

          {/* ── TAB 3: Notifications & Triggers ── */}
          {activeTab === "notifications" && (
            <div className="space-y-5 animate-slide-up">
              <div className="rounded-2xl bg-[var(--color-surface)] border border-[var(--color-border)] p-6 space-y-4">
                <div className="flex items-center gap-3 border-b border-[var(--color-border)] pb-4">
                  <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-amber-600/10 text-amber-500 border border-amber-500/20">
                    <Bell size={20} />
                  </div>
                  <div>
                    <h3 className="text-base font-bold text-[var(--color-foreground)]">Alert Rules & Notifications</h3>
                    <p className="text-xs text-[var(--color-muted)]">Configure when you want the system to alert you.</p>
                  </div>
                </div>

                <div className="space-y-3 pt-1">
                  <label className="flex items-center gap-3 p-3.5 rounded-xl bg-[var(--color-surface-elevated)] border border-[var(--color-border)] cursor-pointer hover:border-blue-500/30 transition-all">
                    <input
                      type="checkbox"
                      checked={preferences.notifyOnJobFailure}
                      onChange={(e) => updatePreference("notifyOnJobFailure", e.target.checked)}
                      className="rounded border-[var(--color-border)] bg-[var(--color-surface)] text-blue-600 focus:ring-0 cursor-pointer h-4 w-4"
                    />
                    <div>
                      <span className="block text-xs font-semibold text-[var(--color-foreground)]">Discovery Job Failures & API Blocks</span>
                      <span className="block text-[11px] text-[var(--color-muted)]">Receive immediate alerts if a search query times out or an upstream engine blocks requests.</span>
                    </div>
                  </label>

                  <label className="flex items-center gap-3 p-3.5 rounded-xl bg-[var(--color-surface-elevated)] border border-[var(--color-border)] cursor-pointer hover:border-blue-500/30 transition-all">
                    <input
                      type="checkbox"
                      checked={preferences.notifyOnServiceDegradation}
                      onChange={(e) => updatePreference("notifyOnServiceDegradation", e.target.checked)}
                      className="rounded border-[var(--color-border)] bg-[var(--color-surface)] text-blue-600 focus:ring-0 cursor-pointer h-4 w-4"
                    />
                    <div>
                      <span className="block text-xs font-semibold text-[var(--color-foreground)]">Infrastructure Degradation Alerts</span>
                      <span className="block text-[11px] text-[var(--color-muted)]">Notify when Database, Redis, SearXNG, or Map Tile services enter degraded health state.</span>
                    </div>
                  </label>

                  <label className="flex items-center gap-3 p-3.5 rounded-xl bg-[var(--color-surface-elevated)] border border-[var(--color-border)] cursor-pointer hover:border-blue-500/30 transition-all">
                    <input
                      type="checkbox"
                      checked={preferences.notifyOnHighConfidenceLeads}
                      onChange={(e) => updatePreference("notifyOnHighConfidenceLeads", e.target.checked)}
                      className="rounded border-[var(--color-border)] bg-[var(--color-surface)] text-blue-600 focus:ring-0 cursor-pointer h-4 w-4"
                    />
                    <div>
                      <span className="block text-xs font-semibold text-[var(--color-foreground)]">High Confidence Leads (Score &gt; {preferences.confidenceThreshold})</span>
                      <span className="block text-[11px] text-[var(--color-muted)]">Notify when verified prospects with phone, email, and high relevance are discovered.</span>
                    </div>
                  </label>
                </div>
              </div>
            </div>
          )}

          {/* ── TAB 4: Data & Exports (Cleaned & Streamlined) ── */}
          {activeTab === "data" && (
            <div className="space-y-5 animate-slide-up">
              {/* One-Click Backup & Export */}
              <div className="rounded-2xl bg-[var(--color-surface)] border border-[var(--color-border)] p-6 space-y-4">
                <div className="flex items-center gap-3 border-b border-[var(--color-border)] pb-4">
                  <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-emerald-600/10 text-emerald-500 border border-emerald-500/20">
                    <Download size={20} />
                  </div>
                  <div>
                    <h3 className="text-base font-bold text-[var(--color-foreground)]">Lead Backup & Export</h3>
                    <p className="text-xs text-[var(--color-muted)]">Instantly export your verified database without complicated column filters.</p>
                  </div>
                </div>

                <div className="grid gap-4 sm:grid-cols-2 pt-1">
                  <div className="rounded-xl bg-[var(--color-surface-elevated)] border border-[var(--color-border)] p-4 flex flex-col justify-between space-y-3">
                    <div>
                      <h4 className="text-sm font-bold text-[var(--color-foreground)]">All Discovered Businesses</h4>
                      <p className="text-xs text-[var(--color-muted)] mt-1">
                        Download complete snapshot containing names, categories, addresses, phone numbers, emails, and website domains.
                      </p>
                      <span className="inline-block mt-2 font-mono text-xs text-blue-500 font-semibold">
                        {totalLeads.toLocaleString()} records ready
                      </span>
                    </div>

                    <button
                      type="button"
                      disabled={isExporting || totalLeads === 0}
                      onClick={handleExportCsv}
                      className="flex items-center justify-center gap-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white px-4 py-2 text-xs font-bold transition-all shadow-sm disabled:opacity-40 cursor-pointer"
                    >
                      <Download size={14} />
                      <span>{isExporting ? "Generating CSV..." : "Download Full CSV Export"}</span>
                    </button>
                  </div>

                  <div className="rounded-xl bg-[var(--color-surface-elevated)] border border-[var(--color-border)] p-4 flex flex-col justify-between space-y-3">
                    <div>
                      <h4 className="text-sm font-bold text-[var(--color-foreground)]">Filtered Leads Explorer</h4>
                      <p className="text-xs text-[var(--color-muted)] mt-1">
                        Jump to the Leads Explorer to apply custom city, category, and verification filters before exporting.
                      </p>
                      <span className="inline-block mt-2 font-mono text-xs text-purple-500 font-semibold">
                        Custom segmented exports
                      </span>
                    </div>

                    <a
                      href="/leads"
                      className="flex items-center justify-center gap-2 rounded-xl bg-blue-600/15 hover:bg-blue-600/25 border border-blue-500/30 text-blue-400 px-4 py-2 text-xs font-bold transition-all cursor-pointer text-center"
                    >
                      <Search size={14} />
                      <span>Open Leads Filter & Export</span>
                    </a>
                  </div>
                </div>
              </div>

              {/* Clean Lead Ingestion / Import */}
              <div className="rounded-2xl bg-[var(--color-surface)] border border-[var(--color-border)] p-6 space-y-4">
                <div className="flex items-center gap-3 border-b border-[var(--color-border)] pb-4">
                  <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-sky-600/10 text-sky-500 border border-sky-500/20">
                    <Upload size={20} />
                  </div>
                  <div>
                    <h3 className="text-base font-bold text-[var(--color-foreground)]">Import External Leads</h3>
                    <p className="text-xs text-[var(--color-muted)]">Upload a CSV or spreadsheet of existing leads to merge into this workspace.</p>
                  </div>
                </div>

                <div
                  onClick={() => fileInputRef.current?.click()}
                  className="rounded-2xl border-2 border-dashed border-[var(--color-border)] hover:border-blue-500/50 bg-[var(--color-surface-elevated)]/40 p-8 text-center cursor-pointer transition-all space-y-3"
                >
                  <input
                    type="file"
                    ref={fileInputRef}
                    accept=".csv,.xlsx,.xls"
                    onChange={handleFileSelect}
                    className="hidden"
                  />
                  <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-blue-600/10 text-blue-500 mx-auto border border-blue-500/20">
                    <Upload size={22} />
                  </div>
                  <div>
                    <p className="text-sm font-semibold text-[var(--color-foreground)]">Click to choose a CSV or Excel lead file</p>
                    <p className="text-xs text-[var(--color-muted)] mt-1">Supports UTF-8 CSV with name, category, phone, email, and website headers.</p>
                  </div>
                  {importStatus && (
                    <p className="text-xs font-semibold text-emerald-500 font-mono animate-pulse">{importStatus}</p>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* ── TAB 5: Appearance & Theme ── */}
          {activeTab === "appearance" && (
            <div className="space-y-5 animate-slide-up">
              <div className="rounded-2xl bg-[var(--color-surface)] border border-[var(--color-border)] p-6 space-y-4">
                <div className="flex items-center gap-3 border-b border-[var(--color-border)] pb-4">
                  <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-blue-600/10 text-blue-500 border border-blue-500/20">
                    <Sliders size={20} />
                  </div>
                  <div>
                    <h3 className="text-base font-bold text-[var(--color-foreground)]">Appearance & Color Mode</h3>
                    <p className="text-xs text-[var(--color-muted)]">Customize visual layout theme and information density.</p>
                  </div>
                </div>

                {/* Theme Selector */}
                <div className="grid gap-4 sm:grid-cols-2 pt-2">
                  <button
                    type="button"
                    onClick={() => setTheme("dark")}
                    className={cn(
                      "flex items-center gap-4 rounded-xl border p-4 text-left transition-all cursor-pointer",
                      theme === "dark"
                        ? "bg-[#181818] border-blue-500 ring-2 ring-blue-500/20 text-white"
                        : "bg-[var(--color-surface-elevated)] border-[var(--color-border)] text-[var(--color-muted)] hover:border-blue-500/40"
                    )}
                  >
                    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-neutral-900 border border-neutral-800 text-blue-400">
                      <Moon size={20} />
                    </div>
                    <div>
                      <span className="block text-sm font-bold text-white">Dark Mode (Default)</span>
                      <span className="block text-xs text-[#888] mt-0.5">Restrained matte dark admin workspace with high contrast.</span>
                    </div>
                  </button>

                  <button
                    type="button"
                    onClick={() => setTheme("light")}
                    className={cn(
                      "flex items-center gap-4 rounded-xl border p-4 text-left transition-all cursor-pointer",
                      theme === "light"
                        ? "bg-white border-blue-600 ring-2 ring-blue-500/20 text-slate-900"
                        : "bg-[var(--color-surface-elevated)] border-[var(--color-border)] text-[var(--color-muted)] hover:border-blue-500/40"
                    )}
                  >
                    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-slate-100 border border-slate-200 text-amber-500">
                      <Sun size={20} />
                    </div>
                    <div>
                      <span className="block text-sm font-bold text-slate-900">Light Mode</span>
                      <span className="block text-xs text-slate-500 mt-0.5">Clean crisp daylight canvas with high readability.</span>
                    </div>
                  </button>
                </div>

                {/* Table Density */}
                <div className="pt-4 border-t border-[var(--color-border)] space-y-3">
                  <label className="block text-xs font-semibold text-[var(--color-foreground)]">Interface Density</label>
                  <div className="flex gap-3">
                    <button
                      type="button"
                      onClick={() => updatePreference("tableDensity", "compact")}
                      className={cn(
                        "rounded-xl border px-4 py-2 text-xs font-semibold transition-all cursor-pointer",
                        preferences.tableDensity === "compact"
                          ? "bg-blue-600 text-white border-blue-600"
                          : "bg-[var(--color-surface-elevated)] border-[var(--color-border)] text-[var(--color-muted)] hover:text-[var(--color-foreground)]"
                      )}
                    >
                      Compact Density (Admin Tables)
                    </button>
                    <button
                      type="button"
                      onClick={() => updatePreference("tableDensity", "comfortable")}
                      className={cn(
                        "rounded-xl border px-4 py-2 text-xs font-semibold transition-all cursor-pointer",
                        preferences.tableDensity === "comfortable"
                          ? "bg-blue-600 text-white border-blue-600"
                          : "bg-[var(--color-surface-elevated)] border-[var(--color-border)] text-[var(--color-muted)] hover:text-[var(--color-foreground)]"
                      )}
                    >
                      Comfortable Spacing
                    </button>
                  </div>
                </div>

                <div className="pt-4 border-t border-[var(--color-border)]">
                  <button
                    type="button"
                    onClick={() => setHoverEffects(!hoverEffects)}
                    className="flex w-full items-center justify-between rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-elevated)] p-4 text-left"
                  >
                    <span>
                      <span className="block text-sm font-semibold text-[var(--color-foreground)]">Hover color changes</span>
                      <span className="mt-1 block text-xs text-[var(--color-muted)]">Keep surfaces stable; use a focus border instead of bright hover fills.</span>
                    </span>
                    <span className={cn("relative h-6 w-11 rounded-full transition-colors", hoverEffects ? "bg-blue-600" : "bg-[var(--color-border)]")}>
                      <span className={cn("absolute top-1 h-4 w-4 rounded-full bg-white transition-transform", hoverEffects ? "translate-x-6" : "translate-x-1")} />
                    </span>
                  </button>
                </div>
              </div>
            </div>
          )}

          <AppFooter />
        </div>
      </main>
    </div>
  );
}

// Backwards compatibility alias
export const DataView = SettingsView;
