"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Bell,
  Grid3X3,
  Search,
  Settings,
  X,
  ChevronRight,
  PanelLeftClose,
  PanelLeftOpen,
} from "lucide-react";
import { useState, useEffect } from "react";

import { navigation } from "./navigation";
import { cn } from "@/lib/utils";
import { useTaskActivity } from "@/components/providers/task-activity-provider";

export function Sidebar() {
  const pathname = usePathname();
  const { getTaskForHref, isTaskRunning } = useTaskActivity();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [expanded, setExpanded] = useState(true);
  const [openSections, setOpenSections] = useState<Record<string, boolean>>({
    Overview: true,
    "Find prospects": true,
    "Demand research": true,
    Workspace: true,
  });

  // Automatically keep a section open if an active task is running inside it
  useEffect(() => {
    navigation.forEach((section) => {
      const hasActive = section.items.some((item) => isTaskRunning(item.href));
      if (hasActive) {
        setOpenSections((prev) => ({ ...prev, [section.title]: true }));
      }
    });
  }, [isTaskRunning]);

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
      {/* ── Primary Vertical Rail ── */}
      <aside
        className={cn(
          "relative z-30 flex h-full flex-col overflow-hidden",
          "refraction-glass-card rounded-[28px] border-white/[0.18] shadow-2xl",
          "transition-all duration-300 ease-[cubic-bezier(0.16,1,0.3,1)] select-none m-2 sm:m-3",
          expanded ? "w-[252px]" : "w-[72px]"
        )}
        aria-label="Primary navigation rail"
      >
        {/* Brand */}
        <div
          className={cn(
            "flex h-[68px] shrink-0 items-center border-b border-slate-300/40 dark:border-white/[0.08] px-3",
            expanded ? "justify-between" : "justify-center"
          )}
        >
          <Link
            href="/dashboard"
            className="flex items-center gap-3 group"
            title="SparkXFlow Nexus dashboard"
          >
            <div className="relative flex h-10 w-10 shrink-0 items-center justify-center rounded-[14px] overflow-hidden border border-white/20 dark:border-white/10 shadow-lg shadow-black/20 dark:shadow-black/50 transition-transform duration-200 group-hover:scale-105">
              <Image
                src="/logo.png"
                alt="SparkXFlow Nexus"
                width={40}
                height={40}
                className="h-full w-full object-cover"
                priority
              />
            </div>
            {expanded && (
              <div className="truncate">
                <span className="block text-sm font-extrabold tracking-tight text-slate-900 dark:text-white">
                  SparkXFlow
                </span>
                <span className="block text-[9px] font-bold tracking-[0.2em] text-[#FF7849] uppercase">
                  Nexus OS
                </span>
              </div>
            )}
          </Link>
        </div>

        {/* ── Nav Items ── */}
        <nav className="flex-1 overflow-y-auto px-2.5 py-3 space-y-0.5 scrollbar-none">
          {/* Every feature is available in this rail; no separate All Modules drawer required. */}
          <div className="mt-3 border-t border-slate-300/40 dark:border-white/[0.08] pt-3">
            {navigation.map((section) => {
              const sectionOpen = openSections[section.title] ?? false;
              return <div key={section.title} className="mb-2">
                {expanded && <button className="flex w-full items-center justify-between px-2 py-1 text-[9px] font-bold uppercase tracking-[0.16em] text-[#FF7849]" onClick={() => setOpenSections((current) => ({ ...current, [section.title]: !sectionOpen }))} type="button"><span>{section.title}</span><ChevronRight className={cn("transition-transform", sectionOpen && "rotate-90")} size={12} /></button>}
                {(sectionOpen || !expanded) && <div className="space-y-0.5">{section.items.map((item) => {
                  const Icon = item.icon;
                  const active = pathname === item.href || (item.href !== "/dashboard" && pathname.startsWith(item.href));
                  const task = getTaskForHref(item.href);

                  return (
                    <Link
                      key={`${section.title}-${item.href}`}
                      href={item.href}
                      className={cn(
                        "group relative flex items-center gap-3 rounded-[12px] text-xs font-medium transition-all",
                        expanded ? "px-3 py-2" : "mx-auto h-10 w-10 justify-center",
                        active
                          ? "border border-cyan-500/30 dark:border-white/[0.16] bg-cyan-500/15 dark:bg-white/[0.1] text-cyan-900 dark:text-white shadow-[0_0_15px_rgba(0,212,255,0.12)] font-semibold"
                          : "text-slate-600 dark:text-white/50 hover:bg-slate-900/5 dark:hover:bg-white/[0.055] hover:text-slate-950 dark:hover:text-white"
                      )}
                      title={item.label}
                    >
                      <div className="relative shrink-0 flex items-center justify-center">
                        <Icon
                          size={16}
                          className={active ? "text-cyan-600 dark:text-cyan-300" : "text-slate-500 dark:text-white/40 group-hover:text-slate-900 dark:group-hover:text-white"}
                        />
                        {!expanded && task && (
                          <span className="absolute -top-1 -right-1 flex h-2.5 w-2.5">
                            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-75" />
                            <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-cyan-400 shadow-[0_0_8px_rgba(0,212,255,0.9)]" />
                          </span>
                        )}
                      </div>

                      {expanded && <span className="truncate flex-1">{item.label}</span>}

                      {/* AI LLM-style pulsating spinner indicator when background task is running */}
                      {expanded && task && (
                        <div
                          className="ml-auto flex items-center shrink-0 pl-1.5"
                          title={`${task.label || "Task running"} in background…`}
                        >
                          <span className="relative flex h-3.5 w-3.5 items-center justify-center">
                            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400/40" />
                            <svg
                              className="animate-spin h-3.5 w-3.5 text-cyan-400 drop-shadow-[0_0_8px_rgba(0,212,255,0.85)]"
                              xmlns="http://www.w3.org/2000/svg"
                              fill="none"
                              viewBox="0 0 24 24"
                            >
                              <circle
                                className="opacity-25"
                                cx="12"
                                cy="12"
                                r="10"
                                stroke="currentColor"
                                strokeWidth="3"
                              />
                              <path
                                className="opacity-95"
                                fill="currentColor"
                                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                              />
                            </svg>
                          </span>
                        </div>
                      )}

                      {!expanded && (
                        <span className="pointer-events-none absolute left-[calc(100%+10px)] z-50 hidden whitespace-nowrap rounded-lg border border-white/10 bg-[#171923]/95 px-2.5 py-1.5 text-xs text-white shadow-xl group-hover:block">
                          {item.label} {task ? " (Running…)" : ""}
                        </span>
                      )}
                    </Link>
                  );
                })}</div>}
              </div>;
            })}
          </div>
        </nav>

        {/* ── Bottom System Controls ── */}
        <div className="space-y-1 p-2.5 border-t border-white/[0.07]">

          {/* Search */}
          <button
            type="button"
            onClick={triggerSearch}
            className={cn(
              "group flex items-center gap-3 rounded-[14px] w-full",
              "text-white/45 hover:bg-white/[0.055] hover:text-white transition-all duration-200",
              expanded ? "px-3 py-2.5" : "h-10 w-10 justify-center mx-auto"
            )}
            title="Global Search (⌘K)"
          >
            <Search size={16} className="shrink-0 group-hover:text-cyan-400 transition-colors" />
            {expanded && (
              <div className="flex-1 flex items-center justify-between text-xs font-medium">
                <span>Search...</span>
                <kbd className="rounded-md bg-white/[0.07] px-1.5 py-0.5 text-[9px] font-mono border border-white/[0.10]">⌘K</kbd>
              </div>
            )}
          </button>

          {/* Notifications */}
          <Link
            href="/notifications"
            className={cn(
              "group relative flex items-center gap-3 rounded-[14px] w-full",
              "text-slate-600 dark:text-white/45 hover:bg-slate-900/5 dark:hover:bg-white/[0.055] hover:text-slate-900 dark:hover:text-white transition-all duration-200",
              expanded ? "px-3 py-2.5" : "h-10 w-10 justify-center mx-auto"
            )}
            title="Notifications"
          >
            <div className="relative shrink-0">
              <Bell size={16} className="group-hover:text-amber-500 dark:group-hover:text-amber-300 transition-colors" />
              <span className="absolute -top-1 -right-1 h-2 w-2 rounded-full bg-[#FF7849] ring-1 ring-[#06070a] animate-glow-breathe" />
            </div>
            {expanded && <span className="truncate text-xs font-medium">Notifications</span>}
          </Link>

          {/* Settings */}
          <Link
            href="/settings"
            className={cn(
              "group flex items-center gap-3 rounded-[14px] w-full",
              "text-slate-600 dark:text-white/45 hover:bg-slate-900/5 dark:hover:bg-white/[0.055] hover:text-slate-900 dark:hover:text-white transition-all duration-200",
              expanded ? "px-3 py-2.5" : "h-10 w-10 justify-center mx-auto"
            )}
            title="Settings & Data Management"
          >
            <Settings size={16} className="shrink-0 group-hover:rotate-45 transition-transform duration-300" />
            {expanded && <span className="truncate text-xs font-medium">Settings</span>}
          </Link>

          {/* Collapse/Expand */}
          <button
            type="button"
            onClick={() => setExpanded((prev) => !prev)}
            className={cn(
              "group flex items-center gap-2 rounded-[14px] w-full",
              "text-slate-500 dark:text-white/30 hover:text-slate-900 dark:hover:text-white/70 hover:bg-slate-900/5 dark:hover:bg-white/[0.04] transition-all duration-200",
              expanded ? "px-3 py-2 justify-start" : "h-9 w-9 justify-center mx-auto"
            )}
            title={expanded ? "Collapse Rail" : "Expand Rail"}
          >
            {expanded ? (
              <>
                <PanelLeftClose size={14} />
                <span className="text-[10px] font-medium">Collapse</span>
              </>
            ) : (
              <PanelLeftOpen size={14} />
            )}
          </button>
        </div>
      </aside>

      {/* ── All Modules Flyout Drawer ── */}
      {drawerOpen && (
        <div className="fixed inset-0 z-50 flex">
          {/* Backdrop */}
          <div
            className="fixed inset-0 bg-black/55 backdrop-blur-sm"
            onClick={() => setDrawerOpen(false)}
          />

          {/* Panel */}
          <div className="relative ml-[78px] flex h-full w-[360px] max-w-[85vw] flex-col border-r border-white/[0.10] bg-[#111318]/95 backdrop-blur-2xl shadow-2xl z-10 animate-slide-up">

            {/* Drawer Header */}
            <div className="flex items-center justify-between border-b border-white/[0.08] px-5 py-4">
              <div className="flex items-center gap-2.5">
                <Grid3X3 size={16} className="text-[#FF7849]" />
                <h2 className="text-sm font-bold tracking-tight text-white">All Modules & Tools</h2>
              </div>
              <button
                type="button"
                onClick={() => setDrawerOpen(false)}
                className="rounded-lg p-1.5 text-white/40 hover:bg-white/[0.08] hover:text-white transition-colors"
              >
                <X size={16} />
              </button>
            </div>

            {/* Route List */}
            <div className="flex-1 overflow-y-auto px-4 py-4 space-y-5">
              {navigation.map((section) => (
                <div key={section.title} className="space-y-1.5">
                  <h3 className="px-2 text-[9px] font-bold uppercase tracking-[0.18em] text-[#FF7849]/80">
                    {section.title}
                  </h3>
                  <div className="space-y-0.5">
                    {section.items.map((item) => {
                      const Icon = item.icon;
                      const active = pathname === item.href;

                      return (
                        <Link
                          key={item.href}
                          href={item.href}
                          onClick={() => setDrawerOpen(false)}
                          className={cn(
                            "flex items-center justify-between rounded-[12px] px-3 py-2 text-xs font-medium transition-all duration-150",
                            active
                              ? "bg-white/[0.09] text-white border border-white/[0.12]"
                              : "text-white/50 hover:bg-white/[0.05] hover:text-white"
                          )}
                        >
                          <div className="flex items-center gap-2.5 truncate">
                            <Icon
                              size={14}
                              className={active ? "text-[#FF7849]" : "text-white/40"}
                            />
                            <span className="truncate">{item.label}</span>
                          </div>
                          <ChevronRight size={12} className="text-white/25 shrink-0" />
                        </Link>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>

            {/* Footer */}
            <div className="border-t border-white/[0.07] p-4 bg-black/20 text-center">
              <p className="text-[10px] text-white/35">
                Press <kbd className="rounded bg-white/[0.08] px-1 py-0.5 font-mono text-[9px] border border-white/[0.10]">⌘K</kbd> to jump anywhere instantly.
              </p>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
