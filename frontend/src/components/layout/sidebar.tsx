"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Bell,
  Grid3X3,
  Settings,
  X,
  ChevronRight,
  PanelLeftClose,
  PanelLeftOpen,
  Moon,
  Sun,
} from "lucide-react";
import { useState, useEffect } from "react";

import { navigation } from "./navigation";
import { cn } from "@/lib/utils";
import { useSession } from "@/components/providers/session-provider";
import { useTaskActivity } from "@/components/providers/task-activity-provider";
import { useTheme } from "@/components/providers/theme-provider";

export function Sidebar() {
  const pathname = usePathname();
  const { user } = useSession();
  const { theme, toggleTheme } = useTheme();
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

  return (
    <>
      {/* ── Primary Vertical Rail ── */}
      <aside
        className={cn(
          "relative z-30 m-0 mr-0 flex h-full flex-col overflow-hidden rounded-none border border-[var(--color-border)] bg-[var(--color-sidebar)]/90 shadow-[0_18px_42px_rgba(0,0,0,0.28)] backdrop-blur-xl",
          "transition-all duration-300 ease-[cubic-bezier(0.22,1,0.36,1)] select-none",
          expanded ? "w-[248px]" : "w-[68px]"
        )}
        aria-label="Primary navigation rail"
      >
        {/* Brand */}
        <div
          className={cn(
            "flex h-[64px] shrink-0 items-center border-b border-[var(--color-border)] px-4",
            expanded ? "justify-between" : "justify-center"
          )}
        >
          <Link
            href="/dashboard"
            className="flex items-center gap-3 group"
            title="SparkXFlow Nexus dashboard"
          >
            <div className="relative flex h-9 w-9 shrink-0 items-center justify-center overflow-hidden rounded-lg border border-[var(--color-border-highlight)] bg-[var(--color-surface)] transition-transform duration-300 ease-[cubic-bezier(0.22,1,0.36,1)] group-hover:scale-105">
              <Image
                src="/logo.png"
                alt="SparkXFlow Nexus"
                width={36}
                height={36}
                className="h-full w-full object-cover"
                priority
              />
            </div>
            {expanded && (
              <div className="truncate">
                <span className="block text-sm font-semibold tracking-tight text-[var(--color-foreground)]">
                  SparkXFlow
                </span>
                <span className="block text-[9px] font-semibold tracking-[0.18em] text-[var(--color-muted)] uppercase">
                  Nexus OS
                </span>
              </div>
            )}
          </Link>
        </div>

        {/* ── Nav Items ── */}
        <nav className="flex-1 overflow-y-auto px-3 py-3 space-y-1 scrollbar-none">
          {navigation.map((section) => {
            const sectionOpen = openSections[section.title] ?? false;
            return (
              <div key={section.title} className="mb-3">
                {expanded && (
                  <button
                    className="flex w-full items-center justify-between px-2 py-1.5 text-[10px] font-bold uppercase tracking-[0.14em] text-[#737373] hover:text-[#a3a3a3] transition-colors"
                    onClick={() => setOpenSections((current) => ({ ...current, [section.title]: !sectionOpen }))}
                    type="button"
                  >
                    <span>{section.title}</span>
                    <ChevronRight className={cn("transition-transform text-[#666666]", sectionOpen && "rotate-90")} size={12} />
                  </button>
                )}
                {(sectionOpen || !expanded) && (
                  <div className="space-y-1 mt-0.5">
                    {section.items.map((item) => {
                      const Icon = item.icon;
                      const active = pathname === item.href || (item.href !== "/dashboard" && pathname.startsWith(item.href));
                      const task = getTaskForHref(item.href);

                      return (
                        <Link
                          key={`${section.title}-${item.href}`}
                          href={item.href}
                          className={cn(
                            "group relative flex items-center gap-3 rounded-lg text-xs font-medium transition-all duration-300 ease-[cubic-bezier(0.22,1,0.36,1)]",
                            expanded ? "px-3 py-2" : "mx-auto h-10 w-10 justify-center",
                            active
                              ? "border border-[var(--color-primary)]/35 bg-[var(--color-primary)]/12 font-semibold text-[var(--color-primary)]"
                              : "text-[var(--color-muted)] hover:bg-white/[0.06] hover:text-[var(--color-foreground)]"
                          )}
                          title={item.label}
                        >
                          <div className="relative shrink-0 flex items-center justify-center">
                            <Icon
                              size={16}
                              className={active ? "text-[var(--color-primary)]" : "text-[var(--color-muted-dim)] transition-colors group-hover:text-[var(--color-foreground)]"}
                            />
                            {!expanded && task && (
                              <span className="absolute -top-1 -right-1 flex h-2.5 w-2.5">
                                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75" />
                                <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-blue-500 shadow-[0_0_6px_#3b82f6]" />
                              </span>
                            )}
                          </div>

                          {expanded && <span className="truncate flex-1">{item.label}</span>}

                          {/* Task running indicator */}
                          {expanded && task && (
                            <div
                              className="ml-auto flex items-center shrink-0 pl-1"
                              title={`${task.label || "Task running"} in background…`}
                            >
                              <div className="relative flex h-3.5 w-3.5 items-center justify-center">
                                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400/40" />
                                <svg
                                  className="animate-spin h-3.5 w-3.5 text-blue-400"
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
                                    className="opacity-100"
                                    fill="currentColor"
                                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                                  />
                                </svg>
                              </div>
                            </div>
                          )}

                          {!expanded && (
                            <span className="pointer-events-none absolute left-[calc(100%+10px)] z-50 hidden whitespace-nowrap rounded-lg border border-[#333333] bg-[#1c1c1c] px-2.5 py-1.5 text-xs text-white shadow-xl group-hover:block">
                              {item.label} {task ? " (Running…)" : ""}
                            </span>
                          )}
                        </Link>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </nav>

        {/* ── Bottom System Controls ── */}
        <div className="space-y-1 p-2.5 border-t border-[#262626]">
          {/* Notifications */}
          <Link
            href="/notifications"
            className={cn(
              "group relative flex items-center gap-3 rounded-xl w-full",
              "text-[#888888] hover:bg-[#202020] hover:text-[#f3f4f6] transition-all duration-150",
              expanded ? "px-3 py-2" : "h-10 w-10 justify-center mx-auto"
            )}
            title="Notifications"
          >
            <div className="relative shrink-0">
              <Bell size={16} className="group-hover:text-blue-400 transition-colors" />
              <span className="absolute -top-1 -right-1 h-2 w-2 rounded-full bg-blue-500" />
            </div>
            {expanded && <span className="truncate text-xs font-medium">Notifications</span>}
          </Link>

          {/* Settings */}
          <Link
            href="/settings"
            className={cn(
              "group flex items-center gap-3 rounded-xl w-full",
              "text-[#888888] hover:bg-[var(--color-surface-elevated)] hover:text-[var(--color-foreground)] transition-all duration-150",
              expanded ? "px-3 py-2" : "h-10 w-10 justify-center mx-auto"
            )}
            title="Settings & Data Management"
          >
            <Settings size={16} className="shrink-0" />
            {expanded && <span className="truncate text-xs font-medium">Settings</span>}
          </Link>

          {/* Theme Toggle Button */}
          <button
            type="button"
            onClick={toggleTheme}
            className={cn(
              "group flex items-center gap-3 rounded-xl w-full",
              "text-[#888888] hover:bg-[var(--color-surface-elevated)] hover:text-[var(--color-foreground)] transition-all duration-150 cursor-pointer",
              expanded ? "px-3 py-2" : "h-10 w-10 justify-center mx-auto"
            )}
            title={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
          >
            {theme === "dark" ? (
              <Sun size={16} className="shrink-0 text-amber-400" />
            ) : (
              <Moon size={16} className="shrink-0 text-blue-500" />
            )}
            {expanded && (
              <span className="truncate text-xs font-medium">
                {theme === "dark" ? "Light Mode" : "Dark Mode"}
              </span>
            )}
          </button>

          {/* User Profile Capsule */}
          {user && (
            expanded ? (
              <div className="mt-2 mb-1 flex items-center gap-2.5 rounded-xl px-3 py-2 bg-[var(--color-surface-elevated)] border border-[var(--color-border)]">
                <div className="relative flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-blue-600 text-[10px] font-extrabold text-white overflow-hidden border border-white/20">
                  <Image
                    src="/user-avatar.jpg"
                    alt={user.display_name || "User Avatar"}
                    fill
                    sizes="28px"
                    className="object-cover"
                  />
                </div>
                <div className="min-w-0 flex-1 truncate">
                  <span className="block truncate text-xs font-bold text-[var(--color-foreground)] leading-tight">
                    {user.display_name || user.email.split("@")[0]}
                  </span>
                  <span className="block text-[9px] font-medium text-emerald-400 leading-tight">
                    Verified Account
                  </span>
                </div>
              </div>
            ) : (
              <div
                className="mt-2 mb-1 flex items-center justify-center"
                title={user.display_name || user.email}
              >
                <div className="relative flex h-8 w-8 shrink-0 items-center justify-center rounded-lg overflow-hidden border border-[var(--color-border)]">
                  <Image
                    src="/user-avatar.jpg"
                    alt={user.display_name || "User Avatar"}
                    fill
                    sizes="32px"
                    className="object-cover"
                  />
                </div>
              </div>
            )
          )}

          {/* Collapse/Expand */}
          <button
            type="button"
            onClick={() => setExpanded((prev) => !prev)}
            className={cn(
              "group flex items-center gap-2 rounded-xl w-full",
              "text-[#737373] hover:text-[#f3f4f6] hover:bg-[#202020] transition-all duration-150",
              expanded ? "px-3 py-2 justify-start" : "h-9 w-9 justify-center mx-auto"
            )}
            title={expanded ? "Collapse Rail" : "Expand Rail"}
          >
            {expanded ? (
              <>
                <PanelLeftClose size={15} className="shrink-0" />
                <span className="text-xs font-medium">Collapse</span>
              </>
            ) : (
              <PanelLeftOpen size={15} />
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
