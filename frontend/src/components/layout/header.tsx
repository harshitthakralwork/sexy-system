"use client";

import Image from "next/image";
import { Bell, Moon, Search, Sun, Activity, Plus } from "lucide-react";
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
        "hidden items-center gap-2 rounded-lg px-2.5 py-1 text-xs font-medium border sm:flex transition-all",
        isOnline
          ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-400"
          : isDegraded
            ? "bg-purple-500/10 border-purple-500/20 text-purple-400"
            : "bg-red-500/10 border-red-500/20 text-red-400"
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
  const { theme, toggleTheme } = useTheme();

  function triggerSearch() {
    window.dispatchEvent(new CustomEvent("open-command-palette"));
  }

  return (
    <header className="liquid-glass-panel mx-2 mt-2 flex min-h-14 shrink-0 items-center justify-between gap-3 px-4 py-2.5 lg:mx-3 lg:px-5">

      {/* Page title */}
      <div className="min-w-0">
        <h1 className="truncate text-sm font-semibold text-[var(--color-foreground)]">{title}</h1>
        {subtitle && (
          <div className="flex items-center gap-1.5 mt-0.5">
            <span className="h-1.5 w-1.5 rounded-full bg-[var(--color-primary)]" />
            <p className="truncate text-[11px] font-medium text-[var(--color-muted)]">{subtitle}</p>
          </div>
        )}
      </div>

      {/* Right Controls */}
      <div className="flex shrink-0 items-center gap-2.5">
        <StatusBadge />

        {/* New Discovery Action Button */}
        <Link
          href="/leads/discover"
          className="hidden sm:inline-flex items-center gap-1.5 rounded-lg bg-[var(--color-primary)] px-3 py-2 text-xs font-semibold text-black transition-all duration-300 ease-[cubic-bezier(0.22,1,0.36,1)] hover:bg-[var(--color-primary-hover)] hover:-translate-y-px active:scale-[0.98] cursor-pointer"
          title="New Discovery Sweep"
        >
          <Plus size={13} />
          <span>New discovery</span>
        </Link>

        {/* Search trigger */}
        <button
          type="button"
          onClick={triggerSearch}
          className="group flex items-center gap-2 rounded-lg border border-[var(--color-border)] bg-black/20 px-3 py-2 text-xs text-[var(--color-muted)] transition-all duration-300 ease-[cubic-bezier(0.22,1,0.36,1)] hover:border-[var(--color-primary)]/50 hover:text-[var(--color-foreground)] cursor-pointer"
          title="Search Leads... (⌘K)"
        >
          <Search size={13} className="text-[var(--color-muted)] transition-colors group-hover:text-[var(--color-primary)]" aria-hidden />
          <span className="hidden sm:inline font-medium">Search leads...</span>
          <kbd className="rounded bg-[var(--color-surface-elevated)] px-1.5 py-0.5 text-[9px] font-mono text-[var(--color-muted)] border border-[var(--color-border)]">
            ⌘K
          </kbd>
        </button>

        {/* Dark / Light Mode Toggle */}
        <button
          type="button"
          onClick={toggleTheme}
          className="relative flex h-9 w-9 items-center justify-center rounded-lg border border-[var(--color-border)] bg-black/20 text-[var(--color-muted)] transition-all duration-300 ease-[cubic-bezier(0.22,1,0.36,1)] hover:border-[var(--color-primary)]/50 hover:text-[var(--color-foreground)] cursor-pointer"
          title={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
          aria-label="Toggle dark/light mode"
        >
          {theme === "dark" ? (
            <Sun size={14} className="text-amber-400" />
          ) : (
            <Moon size={14} className="text-blue-500" />
          )}
        </button>

        {/* Notifications */}
        <Link
          href="/notifications"
          className="relative flex h-9 w-9 items-center justify-center rounded-lg border border-[var(--color-border)] bg-black/20 text-[var(--color-muted)] transition-all duration-300 ease-[cubic-bezier(0.22,1,0.36,1)] hover:border-[var(--color-primary)]/50 hover:text-[var(--color-foreground)] cursor-pointer"
          title="Notifications & Alerts"
        >
          <Bell size={14} />
          <span className="absolute right-1.5 top-1.5 h-1.5 w-1.5 rounded-full bg-[var(--color-primary)]" />
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

  return (
    <div className="flex items-center gap-2">
      <div
        className="relative flex h-9 w-9 items-center justify-center overflow-hidden rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-elevated)] cursor-default select-none"
        title={user.email}
      >
        <Image
          src="/user-avatar.jpg"
          alt={user.display_name || "User Avatar"}
          fill
        sizes="36px"
          className="object-cover"
        />
      </div>

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
        className="hidden sm:inline-flex rounded-lg border border-[var(--color-border)] bg-black/20 px-3 py-2 text-xs font-medium text-[var(--color-muted)] transition-all duration-300 ease-[cubic-bezier(0.22,1,0.36,1)] hover:border-[var(--color-primary)]/50 hover:text-[var(--color-foreground)] disabled:opacity-50 cursor-pointer"
      >
        {busy ? "…" : "Sign out"}
      </button>
    </div>
  );
}
