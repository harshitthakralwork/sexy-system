"use client";

import Image from "next/image";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { BarChart3, Bell, Compass, Globe, LayoutDashboard, ListChecks, MapPinned, Radar, Search, Settings, Shield, Target, X, type LucideIcon } from "lucide-react";

interface CommandItem {
  id: string;
  title: string;
  subtitle: string;
  category: "Quick actions" | "Prospecting" | "Demand research" | "Workspace";
  href: string;
  icon: LucideIcon;
  badge?: string;
}

const COMMAND_ITEMS: CommandItem[] = [
  { id: "action-local-search", title: "Find local businesses", subtitle: "Search public business records by niche and city", category: "Quick actions", href: "/leads/map", icon: MapPinned, badge: "Start" },
  { id: "action-social-query", title: "Research public demand", subtitle: "Search permitted public discussions", category: "Quick actions", href: "/social", icon: Globe, badge: "Start" },
  { id: "action-new-track", title: "Create discovery track", subtitle: "Monitor a public demand or business search", category: "Quick actions", href: "/intelligence/tracks", icon: Target, badge: "Start" },
  { id: "leads-map", title: "Local business finder", subtitle: "Search, score, filter, and export local prospects", category: "Prospecting", href: "/leads/map", icon: MapPinned },
  { id: "leads-results", title: "Lead results", subtitle: "Review collected businesses and public contact evidence", category: "Prospecting", href: "/leads/raw", icon: ListChecks },
  { id: "leads-discover", title: "Business discovery", subtitle: "Launch and review targeted discovery runs", category: "Prospecting", href: "/leads/discover", icon: Compass },
  { id: "social-research", title: "Social research", subtitle: "Search public posts from configured sources", category: "Demand research", href: "/social", icon: Globe },
  { id: "intel-demand", title: "Demand signals", subtitle: "Review public posts with buyer intent", category: "Demand research", href: "/intelligence/demand", icon: Target },
  { id: "intel-tracks", title: "Discovery tracks", subtitle: "Manage recurring public-source searches", category: "Demand research", href: "/intelligence/tracks", icon: Radar },
  { id: "intel-posts", title: "Post explorer", subtitle: "Filter collected public posts and source evidence", category: "Demand research", href: "/intelligence/posts", icon: Search },
  { id: "sys-dashboard", title: "Dashboard", subtitle: "See current prospecting and source activity", category: "Workspace", href: "/dashboard", icon: LayoutDashboard },
  { id: "sys-analytics", title: "Analytics", subtitle: "Review saved counts and recent activity", category: "Workspace", href: "/analytics", icon: BarChart3 },
  { id: "sys-sources", title: "Source health", subtitle: "Test public data sources and inspect their status", category: "Workspace", href: "/sources", icon: Shield },
  { id: "sys-alerts", title: "Alerts", subtitle: "Discovery results, source failures, and demand triggers", category: "Workspace", href: "/notifications", icon: Bell },
  { id: "sys-settings", title: "Settings", subtitle: "Manage profile, preferences, and data options", category: "Workspace", href: "/settings", icon: Settings },
];

export function CommandPalette() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [selectedIndex, setSelectedIndex] = useState(0);

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key === "k") {
        event.preventDefault();
        setOpen((previous) => !previous);
      }
      if (event.key === "Escape") setOpen(false);
    }
    function handleCustomOpen() { setOpen(true); }
    window.addEventListener("keydown", handleKeyDown);
    window.addEventListener("open-command-palette", handleCustomOpen);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      window.removeEventListener("open-command-palette", handleCustomOpen);
    };
  }, []);

  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) return COMMAND_ITEMS;
    return COMMAND_ITEMS.filter((item) => item.title.toLowerCase().includes(query) || item.subtitle.toLowerCase().includes(query) || item.category.toLowerCase().includes(query));
  }, [search]);

  function navigateTo(href: string) {
    setOpen(false);
    setSearch("");
    router.push(href);
  }

  function handleInputKeyDown(event: React.KeyboardEvent) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setSelectedIndex((previous) => (previous + 1 < filtered.length ? previous + 1 : 0));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setSelectedIndex((previous) => (previous - 1 >= 0 ? previous - 1 : filtered.length - 1));
    } else if (event.key === "Enter" && filtered[selectedIndex]) {
      event.preventDefault();
      navigateTo(filtered[selectedIndex].href);
    }
  }

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/65 p-4 pt-[12vh] backdrop-blur-sm" onClick={() => setOpen(false)} role="dialog" aria-modal="true" aria-label="Command palette">
      <div className="w-full max-w-2xl overflow-hidden rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] shadow-2xl ring-1 ring-white/10" onClick={(event) => event.stopPropagation()}>
        <div className="flex items-center gap-3 border-b border-[var(--color-border)] px-4 py-3.5">
          <Search size={18} className="shrink-0 text-[var(--color-muted)]" aria-hidden />
          <input type="text" autoFocus className="flex-1 bg-transparent text-sm text-[var(--color-foreground)] placeholder-[var(--color-muted)] focus:outline-none" placeholder="Search a feature or action…" value={search} onChange={(event) => { setSearch(event.target.value); setSelectedIndex(0); }} onKeyDown={handleInputKeyDown} />
          {search && <button type="button" onClick={() => { setSearch(""); setSelectedIndex(0); }} className="rounded p-1 text-[var(--color-muted)] hover:text-[var(--color-foreground)]" aria-label="Clear search"><X size={14} /></button>}
          <kbd className="hidden rounded bg-[var(--color-surface-elevated)] px-2 py-0.5 text-[11px] font-medium text-[var(--color-muted)] sm:inline-block">ESC</kbd>
        </div>
        <div className="max-h-[60vh] overflow-y-auto p-2 scrollbar-thin">
          {filtered.length === 0 ? <div className="py-12 text-center"><p className="text-sm font-medium text-[var(--color-foreground)]">No matching feature found</p><p className="mt-1 text-xs text-[var(--color-muted)]">Try “business”, “local”, “demand”, or “source”.</p></div> : (
            <div className="space-y-1">
              {filtered.map((item, index) => {
                const Icon = item.icon;
                const selected = index === selectedIndex;
                return <button key={item.id} type="button" onClick={() => navigateTo(item.href)} onMouseEnter={() => setSelectedIndex(index)} className={`flex w-full items-center gap-3.5 rounded-lg px-3 py-2.5 text-left text-sm transition-colors ${selected ? "bg-[var(--color-primary)]/15 text-[var(--color-foreground)] ring-1 ring-[var(--color-primary)]/40" : "text-[var(--color-muted)] hover:bg-[var(--color-surface-elevated)] hover:text-[var(--color-foreground)]"}`}>
                  <span className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-md ${selected ? "bg-cyan-500/25 text-cyan-200 border border-cyan-400/40 shadow-[0_0_10px_rgba(0,212,255,0.25)]" : "bg-[var(--color-surface-elevated)] text-[var(--color-muted)]"}`}><Icon size={16} /></span>
                  <span className="min-w-0 flex-1"><span className="flex items-center gap-2"><span className="truncate font-medium text-[var(--color-foreground)]">{item.title}</span>{item.badge && <span className="rounded bg-[var(--color-primary)]/20 px-1.5 py-0.5 text-[10px] font-semibold text-[var(--color-secondary)]">{item.badge}</span>}<span className="ml-auto text-[11px] text-[var(--color-muted)]">{item.category}</span></span><span className="block truncate text-xs text-[var(--color-muted)]">{item.subtitle}</span></span>
                </button>;
              })}
            </div>
          )}
        </div>
        <div className="flex items-center justify-between border-t border-[var(--color-border)] bg-[var(--color-surface-elevated)]/50 px-4 py-2 text-[11px] text-[var(--color-muted)]"><div className="flex items-center gap-3"><span><kbd className="rounded bg-[var(--color-surface)] px-1.5 py-0.5 font-mono">↑↓</kbd> to navigate</span><span><kbd className="rounded bg-[var(--color-surface)] px-1.5 py-0.5 font-mono">↵</kbd> to open</span></div><div className="flex items-center gap-1.5 font-semibold text-white"><Image src="/logo.png" alt="SparkXFlow" width={14} height={14} className="rounded-sm" /><span>SparkXFlow Nexus</span></div></div>
      </div>
    </div>
  );
}
