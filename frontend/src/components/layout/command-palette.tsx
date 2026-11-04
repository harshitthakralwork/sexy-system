"use client";

import Image from "next/image";
import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  BarChart3,
  Bell,
  Bookmark,
  Briefcase,
  Building2,
  CalendarClock,
  CheckSquare,
  Compass,
  FolderKanban,
  Globe,
  LayoutDashboard,
  ListChecks,
  Mail,
  MapPinned,
  Radar,
  Search,
  Settings,
  Shield,
  Sparkles,
  Target,
  Users,
  Workflow,
  X,
  type LucideIcon,
} from "lucide-react";

interface CommandItem {
  id: string;
  title: string;
  subtitle: string;
  category: "Quick Actions" | "Leads Intelligence" | "Startups" | "Social & Demand" | "Automation" | "System";
  href: string;
  icon: LucideIcon;
  badge?: string;
}

const COMMAND_ITEMS: CommandItem[] = [
  // Quick Actions
  {
    id: "action-discover-leads",
    title: "Launch Business Discovery",
    subtitle: "Sweep a geographic area using web scrapers and OSM",
    category: "Quick Actions",
    href: "/leads/discover",
    icon: Compass,
    badge: "Action",
  },
  {
    id: "action-open-map",
    title: "Explore Map Grid",
    subtitle: "Visual density and local market discovery map",
    category: "Quick Actions",
    href: "/leads/map",
    icon: MapPinned,
    badge: "Action",
  },
  {
    id: "action-social-query",
    title: "New Social Research Query",
    subtitle: "Search public discussions on 12 indexed platforms",
    category: "Quick Actions",
    href: "/social",
    icon: Globe,
    badge: "Action",
  },
  {
    id: "action-new-track",
    title: "Create Intelligence Track",
    subtitle: "Automated recurring demand and competitor radar",
    category: "Quick Actions",
    href: "/intelligence/tracks",
    icon: Target,
    badge: "Action",
  },
  {
    id: "action-new-workflow",
    title: "Create Automation Workflow",
    subtitle: "Define qualification, draft and sending pipelines",
    category: "Quick Actions",
    href: "/automation/workflows",
    icon: Workflow,
    badge: "Action",
  },
  {
    id: "action-email-campaign",
    title: "Dispatch Email Outreach",
    subtitle: "Review campaign drafts and approval queues",
    category: "Quick Actions",
    href: "/email",
    icon: Mail,
    badge: "Action",
  },

  // Leads
  {
    id: "leads-overview",
    title: "Leads Overview",
    subtitle: "High-level metrics, health and active pipeline stats",
    category: "Leads Intelligence",
    href: "/leads",
    icon: Radar,
  },
  {
    id: "leads-discover",
    title: "Discover Businesses",
    subtitle: "Launch autonomous discovery jobs & check status",
    category: "Leads Intelligence",
    href: "/leads/discover",
    icon: Compass,
  },
  {
    id: "leads-map",
    title: "Map Explorer",
    subtitle: "Interactive spatial map with density filters",
    category: "Leads Intelligence",
    href: "/leads/map",
    icon: MapPinned,
  },
  {
    id: "leads-raw",
    title: "Raw Lead Ingestion",
    subtitle: "Browse unscored discovered rows with CSV export",
    category: "Leads Intelligence",
    href: "/leads/raw",
    icon: ListChecks,
  },
  {
    id: "leads-qualified",
    title: "Qualified Leads",
    subtitle: "Deterministic rule-scored businesses ready for outreach",
    category: "Leads Intelligence",
    href: "/leads/qualified",
    icon: CheckSquare,
  },
  {
    id: "leads-crm",
    title: "CRM Pipeline Board",
    subtitle: "12-stage visual Kanban pipeline with stage transitions",
    category: "Leads Intelligence",
    href: "/leads/crm",
    icon: FolderKanban,
  },
  {
    id: "leads-services",
    title: "Service Catalog",
    subtitle: "Manage target agency service offerings and value props",
    category: "Leads Intelligence",
    href: "/leads/services",
    icon: Briefcase,
  },

  // Startups
  {
    id: "startups-dashboard",
    title: "Startup Radar",
    subtitle: "Venture discovery, tech stacks, and funding data",
    category: "Startups",
    href: "/startups",
    icon: Sparkles,
  },
  {
    id: "startups-discover",
    title: "Discover Startups",
    subtitle: "Search early-stage startups with stage/industry filters",
    category: "Startups",
    href: "/startups/discover",
    icon: Compass,
  },
  {
    id: "startups-watchlists",
    title: "Startup Watchlists",
    subtitle: "Curated lists and competitor tracking buckets",
    category: "Startups",
    href: "/startups/watchlists",
    icon: Users,
  },

  // Social & Demand
  {
    id: "social-research",
    title: "Social Intelligence Hub",
    subtitle: "Cross-platform research across 12 social engines",
    category: "Social & Demand",
    href: "/social",
    icon: Globe,
  },
  {
    id: "intel-overview",
    title: "Intelligence Tracks Overview",
    subtitle: "Multi-channel demand & business signal feed",
    category: "Social & Demand",
    href: "/intelligence",
    icon: LayoutDashboard,
  },
  {
    id: "intel-demand",
    title: "Demand Signals",
    subtitle: "High-intent buyer signals and hiring demands",
    category: "Social & Demand",
    href: "/intelligence/demand",
    icon: Target,
  },
  {
    id: "intel-business",
    title: "Competitor & Market Intel",
    subtitle: "Corporate updates, tech stack changes, announcements",
    category: "Social & Demand",
    href: "/intelligence/business",
    icon: Building2,
  },
  {
    id: "intel-saved",
    title: "Saved Signals",
    subtitle: "Shortlisted social content and lead conversion candidates",
    category: "Social & Demand",
    href: "/intelligence/saved",
    icon: Bookmark,
  },
  {
    id: "intel-sources",
    title: "Social Source Health",
    subtitle: "Connection metrics for all 12 platform connectors",
    category: "Social & Demand",
    href: "/social/sources",
    icon: Shield,
  },

  // Automation
  {
    id: "auto-workflows",
    title: "Workflow Builder",
    subtitle: "Autonomous pipelines: discover -> score -> draft -> send",
    category: "Automation",
    href: "/automation/workflows",
    icon: Workflow,
  },
  {
    id: "auto-scheduler",
    title: "Automation Scheduler",
    subtitle: "Cron and interval jobs for unattended sweeps",
    category: "Automation",
    href: "/automation/scheduler",
    icon: CalendarClock,
  },
  {
    id: "auto-approvals",
    title: "Human Approval Queue",
    subtitle: "Safeguard gate before automated outreach dispatch",
    category: "Automation",
    href: "/automation/approvals",
    icon: CheckSquare,
  },
  {
    id: "auto-email",
    title: "Email Outreach Manager",
    subtitle: "Campaign logs, message states, and suppression list",
    category: "Automation",
    href: "/email",
    icon: Mail,
  },

  // System
  {
    id: "sys-dashboard",
    title: "Mission Control Dashboard",
    subtitle: "System health, live counters, and high-level KPIs",
    category: "System",
    href: "/dashboard",
    icon: LayoutDashboard,
  },
  {
    id: "sys-analytics",
    title: "Full Analytics & Reports",
    subtitle: "Cross-platform charts, breakdowns, and report exports",
    category: "System",
    href: "/analytics",
    icon: BarChart3,
  },
  {
    id: "sys-sources",
    title: "Source Manager",
    subtitle: "Provider registry, health tests, and usage telemetry",
    category: "System",
    href: "/sources",
    icon: Shield,
  },
  {
    id: "sys-notifications",
    title: "Notification Center",
    subtitle: "High-priority system alerts and completion notices",
    category: "System",
    href: "/notifications",
    icon: Bell,
  },
  {
    id: "sys-settings",
    title: "Settings & Configuration",
    subtitle: "Profile, security, region and API keys",
    category: "System",
    href: "/settings",
    icon: Settings,
  },
];

export function CommandPalette() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [selectedIndex, setSelectedIndex] = useState(0);
  const listRef = useRef<HTMLDivElement>(null);

  // Global keyboard listener for Cmd+K / Ctrl+K
  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key === "k") {
        event.preventDefault();
        setOpen((prev) => !prev);
      }
      if (event.key === "Escape") {
        setOpen(false);
      }
    }

    function handleCustomOpen() {
      setOpen(true);
    }

    window.addEventListener("keydown", handleKeyDown);
    window.addEventListener("open-command-palette", handleCustomOpen);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      window.removeEventListener("open-command-palette", handleCustomOpen);
    };
  }, []);

  // Filtered items
  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return COMMAND_ITEMS;
    return COMMAND_ITEMS.filter(
      (item) =>
        item.title.toLowerCase().includes(q) ||
        item.subtitle.toLowerCase().includes(q) ||
        item.category.toLowerCase().includes(q)
    );
  }, [search]);

  // Navigate on enter / arrow keys
  function handleInputKeyDown(e: React.KeyboardEvent) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelectedIndex((prev) => (prev + 1 < filtered.length ? prev + 1 : 0));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelectedIndex((prev) => (prev - 1 >= 0 ? prev - 1 : filtered.length - 1));
    } else if (e.key === "Enter" && filtered[selectedIndex]) {
      e.preventDefault();
      navigateTo(filtered[selectedIndex].href);
    }
  }

  function navigateTo(href: string) {
    setOpen(false);
    setSearch("");
    router.push(href);
  }

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/65 p-4 pt-[12vh] backdrop-blur-sm transition-all"
      onClick={() => setOpen(false)}
      role="dialog"
      aria-modal="true"
      aria-label="Command palette"
    >
      <div
        className="w-full max-w-2xl overflow-hidden rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] shadow-2xl ring-1 ring-white/10"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Search Input Bar */}
        <div className="flex items-center gap-3 border-b border-[var(--color-border)] px-4 py-3.5">
          <Search size={18} className="shrink-0 text-[var(--color-muted)]" aria-hidden />
          <input
            type="text"
            autoFocus
            className="flex-1 bg-transparent text-sm text-[var(--color-foreground)] placeholder-[var(--color-muted)] focus:outline-none"
            placeholder="Type a feature name or command (e.g. Map, Startups, Outreach)..."
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setSelectedIndex(0);
            }}
            onKeyDown={handleInputKeyDown}
          />
          {search && (
            <button
              type="button"
              onClick={() => {
                setSearch("");
                setSelectedIndex(0);
              }}
              className="rounded p-1 text-[var(--color-muted)] hover:text-[var(--color-foreground)]"
              aria-label="Clear search"
            >
              <X size={14} />
            </button>
          )}
          <kbd className="hidden rounded bg-[var(--color-surface-elevated)] px-2 py-0.5 text-[11px] font-medium text-[var(--color-muted)] sm:inline-block">
            ESC
          </kbd>
        </div>

        {/* Results List */}
        <div
          ref={listRef}
          className="max-h-[60vh] overflow-y-auto p-2 scrollbar-thin"
        >
          {filtered.length === 0 ? (
            <div className="py-12 text-center">
              <p className="text-sm font-medium text-[var(--color-foreground)]">No matching features found</p>
              <p className="mt-1 text-xs text-[var(--color-muted)]">
                Try searching for &quot;leads&quot;, &quot;social&quot;, &quot;email&quot;, or &quot;map&quot;
              </p>
            </div>
          ) : (
            <div className="space-y-1">
              {filtered.map((item, index) => {
                const Icon = item.icon;
                const isSelected = index === selectedIndex;
                return (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => navigateTo(item.href)}
                    onMouseEnter={() => setSelectedIndex(index)}
                    className={`flex w-full items-center gap-3.5 rounded-lg px-3 py-2.5 text-left text-sm transition-colors ${
                      isSelected
                        ? "bg-[var(--color-primary)]/15 text-[var(--color-foreground)] ring-1 ring-[var(--color-primary)]/40"
                        : "text-[var(--color-muted)] hover:bg-[var(--color-surface-elevated)] hover:text-[var(--color-foreground)]"
                    }`}
                  >
                    <span
                      className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-md ${
                        isSelected
                          ? "bg-[var(--color-primary)] text-white shadow-sm"
                          : "bg-[var(--color-surface-elevated)] text-[var(--color-muted)]"
                      }`}
                    >
                      <Icon size={16} />
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="truncate font-medium text-[var(--color-foreground)]">
                          {item.title}
                        </span>
                        {item.badge && (
                          <span className="rounded bg-[var(--color-primary)]/20 px-1.5 py-0.5 text-[10px] font-semibold text-[var(--color-secondary)]">
                            {item.badge}
                          </span>
                        )}
                        <span className="ml-auto text-[11px] text-[var(--color-muted)]">
                          {item.category}
                        </span>
                      </div>
                      <p className="truncate text-xs text-[var(--color-muted)]">{item.subtitle}</p>
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </div>

        {/* Footer shortcuts */}
        <div className="flex items-center justify-between border-t border-[var(--color-border)] bg-[var(--color-surface-elevated)]/50 px-4 py-2 text-[11px] text-[var(--color-muted)]">
          <div className="flex items-center gap-3">
            <span>
              <kbd className="rounded bg-[var(--color-surface)] px-1.5 py-0.5 font-mono">↑↓</kbd> to navigate
            </span>
            <span>
              <kbd className="rounded bg-[var(--color-surface)] px-1.5 py-0.5 font-mono">↵</kbd> to select
            </span>
          </div>
          <div className="flex items-center gap-1.5 font-semibold text-white">
            <Image src="/logo.png" alt="SparkXFlow" width={14} height={14} className="rounded-sm" />
            <span>SparkXFlow Nexus</span>
          </div>
        </div>
      </div>
    </div>
  );
}
