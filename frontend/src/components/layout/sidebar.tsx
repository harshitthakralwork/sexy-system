"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BarChart3,
  Bell,
  Compass,
  Globe,
  Grid3X3,
  LayoutDashboard,
  MapPinned,
  Search,
  Settings,
  Shield,
  Sparkles,
  Workflow,
  X,
  ChevronRight,
  Layers,
} from "lucide-react";
import { useState, useEffect } from "react";

import { navigation } from "./navigation";
import { cn } from "@/lib/utils";

// Primary rail icons mapped to their main section
const primaryRailItems = [
  { label: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
  { label: "Analytics", href: "/analytics", icon: BarChart3 },
  { label: "Lead Discovery", href: "/leads/discover", icon: Compass },
  { label: "Map Explorer", href: "/leads/map", icon: MapPinned },
  { label: "Social Radar", href: "/social", icon: Globe },
  { label: "Startups", href: "/startups", icon: Sparkles },
  { label: "Automations", href: "/automation/workflows", icon: Workflow },
  { label: "Source Health", href: "/sources", icon: Shield },
];

export function Sidebar() {
  const pathname = usePathname();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [expanded, setExpanded] = useState(true);

  // Close drawer on escape key
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") setDrawerOpen(false);
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  function triggerSearch() {
    window.dispatchEvent(new CustomEvent("open-command-palette"));
  }

  return (
    <>
      {/* Primary Vertical Rail (Inspired by Image 2) */}
      <aside
        className={cn(
          "relative z-30 flex h-full flex-col overflow-hidden rounded-[30px] border border-[var(--color-border)] bg-[var(--color-sidebar)] shadow-[inset_0_1px_0_rgba(255,255,255,0.42),0_24px_70px_rgba(45,48,43,0.16)] backdrop-blur-2xl transition-all duration-300 select-none",
          expanded ? "w-[260px]" : "w-[78px]"
        )}
        aria-label="Primary navigation rail"
      >
        {/* Brand Logo / Emblem */}
        <div className="flex h-[72px] items-center justify-between px-4 border-b border-[var(--color-border)]">
          <Link
            href="/dashboard"
            className="flex items-center gap-3 group mx-auto"
            title="SparkXFlow Nexus — Mission Control"
          >
            {/* Brand Logo with User Emblem */}
            <div className="relative flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl overflow-hidden border border-white/10 shadow-lg shadow-black/40 transition-transform group-hover:scale-105">
              <Image
                src="/logo.png"
                alt="SparkXFlow Nexus"
                width={44}
                height={44}
                className="h-full w-full object-cover"
                priority
              />
            </div>

            {expanded && (
              <div className="truncate">
                <span className="block text-sm font-bold tracking-tight text-[var(--color-foreground)]">
                  SparkXFlow
                </span>
                <span className="block text-[10px] font-semibold tracking-widest text-[#FF7849] uppercase">
                  Nexus OS
                </span>
              </div>
            )}
          </Link>
        </div>

        {/* Center Nav Rail Icons */}
        <nav className="flex-1 space-y-1.5 overflow-y-auto px-3 py-4 scrollbar-none">
          {primaryRailItems.map((item) => {
            const Icon = item.icon;
            const active =
              pathname === item.href ||
              (item.href !== "/dashboard" && pathname.startsWith(item.href));

            return (
              <div key={item.href} className="relative group">
                <Link
                  href={item.href}
                  className={cn(
                    "flex items-center gap-3 rounded-2xl transition-all duration-200",
                    expanded ? "px-3.5 py-2.5 w-full" : "h-12 w-12 justify-center mx-auto",
                    active
                      ? "bg-[var(--color-surface-elevated)] text-[var(--color-foreground)] border border-[var(--color-border-highlight)] shadow-[inset_0_1px_0_rgba(255,255,255,0.4),0_10px_24px_rgba(45,48,43,0.12)]"
                      : "text-[var(--color-muted)] hover:bg-[var(--color-surface)] hover:text-[var(--color-foreground)]"
                  )}
                >
                  <Icon
                    size={20}
                    className={cn(
                      "shrink-0 transition-colors",
                      active ? "text-[var(--color-primary)]" : "text-[var(--color-muted)] group-hover:text-[var(--color-foreground)]"
                    )}
                    aria-hidden
                  />
                  {expanded && (
                    <span className="truncate text-xs font-semibold">{item.label}</span>
                  )}
                </Link>

                {/* Floating Tooltip when collapsed */}
                {!expanded && (
                  <div className="pointer-events-none absolute left-[calc(100%+10px)] top-1/2 -translate-y-1/2 z-50 hidden rounded-xl border border-white/10 bg-[#2C2A2E]/95 px-3 py-1.5 text-xs font-medium text-white shadow-xl backdrop-blur-md group-hover:block whitespace-nowrap">
                    {item.label}
                  </div>
                )}
              </div>
            );
          })}

          {/* Module Drawer Launcher Button */}
          <div className="pt-2">
            <button
              type="button"
              onClick={() => setDrawerOpen(true)}
              className={cn(
                "flex items-center gap-3 rounded-2xl transition-all duration-200 border border-dashed border-white/15 bg-white/[0.03] text-[var(--color-muted)] hover:border-[#FF7849]/50 hover:text-white hover:bg-[#FF7849]/10",
                expanded ? "px-3.5 py-2.5 w-full text-left" : "h-12 w-12 justify-center mx-auto"
              )}
              title="All Modules & Sub-Routes"
            >
              <Grid3X3 size={19} className="shrink-0 text-[#FF7849]" />
              {expanded && (
                <div className="truncate flex-1 flex items-center justify-between">
                  <span className="text-xs font-semibold">All Modules</span>
                  <span className="text-[10px] text-[#FF7849] font-mono">24+</span>
                </div>
              )}
            </button>
          </div>
        </nav>

        {/* Bottom System Controls (Matching Image 2) */}
        <div className="space-y-2 p-3 border-t border-[var(--color-border)]">
          {/* Quick Jump Search Button */}
          <div className="relative group">
            <button
              type="button"
              onClick={triggerSearch}
              className={cn(
                "flex items-center gap-3 rounded-2xl text-[var(--color-muted)] hover:bg-white/[0.06] hover:text-[var(--color-foreground)] transition-colors",
                expanded ? "px-3.5 py-2.5 w-full" : "h-11 w-11 justify-center mx-auto"
              )}
              title="Global Search (⌘K)"
            >
              <Search size={18} className="shrink-0" />
              {expanded && (
                <div className="flex-1 flex items-center justify-between text-xs font-medium">
                  <span>Search...</span>
                  <kbd className="rounded bg-black/40 px-1.5 py-0.5 text-[10px] font-mono">⌘K</kbd>
                </div>
              )}
            </button>
          </div>

          {/* Notification Icon with Warm Orange Dot Badge */}
          <div className="relative group">
            <Link
              href="/notifications"
              className={cn(
                "relative flex items-center gap-3 rounded-2xl text-[var(--color-muted)] hover:bg-white/[0.06] hover:text-[var(--color-foreground)] transition-colors",
                expanded ? "px-3.5 py-2.5 w-full" : "h-11 w-11 justify-center mx-auto"
              )}
              title="Notifications"
            >
              <div className="relative shrink-0">
                <Bell size={18} />
                <span className="absolute -top-1 -right-1 h-2.5 w-2.5 rounded-full bg-[#FF7849] ring-2 ring-[var(--color-sidebar)]" />
              </div>
              {expanded && <span className="truncate text-xs font-medium">Notifications</span>}
            </Link>
          </div>

          {/* Settings */}
          <div className="relative group">
            <Link
              href="/settings"
              className={cn(
                "flex items-center gap-3 rounded-2xl text-[var(--color-muted)] hover:bg-white/[0.06] hover:text-[var(--color-foreground)] transition-colors",
                expanded ? "px-3.5 py-2.5 w-full" : "h-11 w-11 justify-center mx-auto"
              )}
              title="Settings & Data Management"
            >
              <Settings size={18} className="shrink-0" />
              {expanded && <span className="truncate text-xs font-medium">Settings</span>}
            </Link>
          </div>

          {/* Expand/Collapse Rail Toggle */}
          <div className="pt-1">
            <button
              type="button"
              onClick={() => setExpanded((prev) => !prev)}
              className={cn(
                "flex items-center gap-2 rounded-xl text-[11px] text-[var(--color-muted)] hover:text-white transition-colors w-full justify-center py-1.5",
                !expanded && "hover:bg-white/[0.04]"
              )}
              title={expanded ? "Collapse Rail" : "Expand Rail"}
            >
              <Layers size={14} />
              {expanded && <span>Collapse Rail</span>}
            </button>
          </div>
        </div>
      </aside>

      {/* Full Module Explorer Flyout Drawer (Preserves access to all 24+ routes without visual clutter) */}
      {drawerOpen && (
        <div className="fixed inset-0 z-50 flex">
          {/* Backdrop */}
          <div
            className="fixed inset-0 bg-black/60 backdrop-blur-sm transition-opacity"
            onClick={() => setDrawerOpen(false)}
          />

          {/* Slide-out Panel */}
          <div className="relative ml-[78px] flex h-full w-[380px] max-w-[85vw] flex-col border-r border-white/10 bg-[#252428] shadow-2xl z-10 animate-in slide-in-from-left duration-200">
            {/* Drawer Header */}
            <div className="flex items-center justify-between border-b border-white/10 px-6 py-4">
              <div className="flex items-center gap-2.5">
                <Grid3X3 size={18} className="text-[#FF7849]" />
                <h2 className="text-sm font-bold tracking-tight text-white">All Modules & Tools</h2>
              </div>
              <button
                type="button"
                onClick={() => setDrawerOpen(false)}
                className="rounded-lg p-1 text-[var(--color-muted)] hover:bg-white/10 hover:text-white"
              >
                <X size={18} />
              </button>
            </div>

            {/* Categorized Full Route List */}
            <div className="flex-1 overflow-y-auto px-6 py-4 space-y-6 scrollbar-thin">
              {navigation.map((section) => (
                <div key={section.title} className="space-y-2">
                  <h3 className="text-[11px] font-bold uppercase tracking-wider text-[#FF7849]">
                    {section.title}
                  </h3>
                  <div className="space-y-1">
                    {section.items.map((item) => {
                      const Icon = item.icon;
                      const active = pathname === item.href;

                      return (
                        <Link
                          key={item.href}
                          href={item.href}
                          onClick={() => setDrawerOpen(false)}
                          className={cn(
                            "flex items-center justify-between rounded-xl px-3 py-2 text-xs font-medium transition-colors",
                            active
                              ? "bg-[#3A373E] text-white border border-white/10"
                              : "text-[var(--color-muted)] hover:bg-white/[0.06] hover:text-white"
                          )}
                        >
                          <div className="flex items-center gap-2.5 truncate">
                            <Icon
                              size={15}
                              className={active ? "text-[#FF7849]" : "text-[var(--color-muted)]"}
                            />
                            <span className="truncate">{item.label}</span>
                          </div>
                          <ChevronRight size={13} className="text-[var(--color-muted)] opacity-60" />
                        </Link>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>

            {/* Drawer Footer */}
            <div className="border-t border-white/10 p-4 bg-black/20 text-center">
              <p className="text-[11px] text-[var(--color-muted)]">
                Press <kbd className="rounded bg-black/40 px-1 py-0.5 font-mono text-[10px]">⌘K</kbd> to jump anywhere instantly.
              </p>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
