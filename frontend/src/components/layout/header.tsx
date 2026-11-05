"use client";

import { Bell, Moon, Search, Sun, Activity } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { useSession } from "@/components/providers/session-provider";
import { useTheme } from "@/components/providers/theme-provider";
import { useBackendStatus } from "@/hooks/use-backend-status";
import { cn } from "@/lib/utils";

const STATE_LABEL: Record<string, string> = {
  online:   "Engine Active",
  degraded: "Degraded Mode",
  offline:  "API Offline",
  checking: "Connecting…",
};

function StatusBadge() {
  const status = useBackendStatus();

  const isOnline   = status.state === "online";
  const isDegraded = status.state === "degraded";

  return (
    <Link
      href="/sources"
      className={cn(
        "hidden items-center gap-2 rounded-full px-3.5 py-1.5 text-xs font-semibold shadow-sm transition-all sm:flex",
        isOnline
          ? "liquid-badge-emerald"
          : isDegraded
            ? "liquid-badge-amber"
            : "liquid-badge-rose"
      )}
      title="Infrastructure & Source Health"
    >
      {/* Animated status dot */}
      <span className="relative flex h-2 w-2">
        <span
          className={cn(
            "absolute inline-flex h-full w-full rounded-full opacity-75 animate-ping",
            isOnline ? "bg-emerald-400" : isDegraded ? "bg-amber-400" : "bg-rose-400"
          )}
        />
        <span
          className={cn(
            "relative inline-flex h-2 w-2 rounded-full",
            isOnline
              ? "bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.9)]"
              : isDegraded
                ? "bg-amber-400"
                : "bg-rose-400"
          )}
        />
      </span>
      <span className="text-[11px] font-bold tracking-wide">
        {STATE_LABEL[status.state]}
      </span>
      <Activity
        size={11}
        className={cn(
          "transition-colors",
          isOnline ? "text-emerald-300" : isDegraded ? "text-amber-300" : "text-rose-300"
        )}
      />
    </Link>
  );
}

export function Header({ title, subtitle }: { title: string; subtitle?: string }) {
  const { toggleTheme } = useTheme();

  function triggerSearch() {
    window.dispatchEvent(new CustomEvent("open-command-palette"));
  }

  return (
    <header className="mx-3 mt-3 flex h-[64px] shrink-0 items-center justify-between gap-4 rounded-[24px] liquid-glass-panel px-5 shadow-2xl sm:px-6">

      {/* Page Title */}
      <div className="min-w-0">
        <h1 className="truncate text-lg font-extrabold tracking-tight text-[var(--color-foreground)] sm:text-xl font-sans">
          {title}
        </h1>
        {subtitle && (
          <p className="truncate text-[11px] font-medium text-[var(--color-muted)] mt-0.5">{subtitle}</p>
        )}
      </div>

      {/* Right Controls */}
      <div className="flex shrink-0 items-center gap-2.5">
        <StatusBadge />

        {/* Search trigger */}
        <button
          type="button"
          onClick={triggerSearch}
          className="liquid-btn-secondary group flex items-center gap-2.5 rounded-full px-4 py-1.5 text-xs text-[var(--color-muted)] transition-all hover:text-[var(--color-foreground)] cursor-pointer"
          title="Search Anything (⌘K)"
        >
          <Search size={13} className="text-cyan-400 group-hover:scale-110 transition-transform" aria-hidden />
          <span className="hidden sm:inline font-medium">Search...</span>
          <kbd className="rounded-full bg-white/[0.08] dark:bg-white/[0.08] px-2 py-0.5 text-[9px] font-mono text-[var(--color-foreground)] border border-white/[0.12]">
            ⌘K
          </kbd>
        </button>

        {/* Theme toggle */}
        <button
          type="button"
          onClick={toggleTheme}
          className="liquid-btn-secondary relative flex h-9 w-9 items-center justify-center rounded-full text-[var(--color-muted)] shadow-sm transition-all hover:text-[var(--color-foreground)] hover:rotate-12 cursor-pointer"
          title="Toggle color theme"
          aria-label="Toggle color theme"
        >
          <Moon className="theme-icon-light" size={15} />
          <Sun  className="theme-icon-dark"  size={15} />
        </button>

        {/* Notifications */}
        <Link
          href="/notifications"
          className="liquid-btn-secondary relative flex h-9 w-9 items-center justify-center rounded-full text-[var(--color-muted)] shadow-sm transition-all hover:text-amber-400 cursor-pointer"
          title="Notifications & Alerts"
        >
          <Bell size={15} />
          {/* Breathing pulse dot */}
          <span className="absolute top-1.5 right-1.5 h-2 w-2 rounded-full bg-[#FF7849] shadow-[0_0_6px_rgba(255,120,73,0.7)] animate-glow-breathe" />
        </Link>

        {/* User avatar capsule */}
        <UserCapsule />
      </div>
    </header>
  );
}

function UserCapsule() {
  const { user, logout } = useSession();
  const [busy, setBusy] = useState(false);

  if (!user) return null;

  const initials = user.display_name
    ? user.display_name
        .split(" ")
        .map((n) => n[0])
        .slice(0, 2)
        .join("")
        .toUpperCase()
    : "?";

  return (
    <div className="flex items-center gap-2">
      {/* Avatar with glow ring */}
      <div
        className={cn(
          "relative flex h-9 w-9 items-center justify-center rounded-full",
          "bg-gradient-to-tr from-cyan-500 via-sky-400 to-indigo-500",
          "border-2 border-white/30 shadow-[0_0_16px_rgba(0,212,255,0.40)]",
          "font-extrabold text-xs text-white cursor-default select-none"
        )}
        title={user.email}
      >
        {initials}
        {/* Outer pulse ring */}
        <span className="absolute inset-0 rounded-full border-2 border-cyan-400/30 animate-ping opacity-50 pointer-events-none" />
      </div>

      {/* Sign out button */}
      <button
        type="button"
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          try {
            await logout();
          } finally {
            setBusy(false);
          }
        }}
        className={cn(
          "hidden sm:inline-flex rounded-full liquid-btn-secondary px-4 py-1.5 text-xs font-bold text-[var(--color-muted)]",
          "hover:text-rose-400 hover:border-rose-400/40 hover:shadow-[0_0_16px_rgba(248,113,113,0.20)]",
          "transition-all disabled:opacity-50 cursor-pointer"
        )}
      >
        {busy ? "…" : "Sign out"}
      </button>
    </div>
  );
}
