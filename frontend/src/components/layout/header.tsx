"use client";

import { Bell, Moon, Search, Sun } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { useSession } from "@/components/providers/session-provider";
import { useTheme } from "@/components/providers/theme-provider";
import { useBackendStatus } from "@/hooks/use-backend-status";
import { cn } from "@/lib/utils";

const STATE_LABEL: Record<string, string> = {
  online: "Engine Active",
  degraded: "Degraded Mode",
  offline: "API Offline",
  checking: "Connecting…",
};

function StatusBadge() {
  const status = useBackendStatus();

  const isOnline = status.state === "online";
  const isDegraded = status.state === "degraded";

  return (
    <Link
      href="/sources"
      className="hidden items-center gap-2 rounded-full refraction-glass-btn px-3.5 py-1.5 text-xs font-medium text-white/80 shadow-sm transition-all sm:flex"
      title="Infrastructure & Source Health"
    >
      <span
        className={cn(
          "h-2 w-2 rounded-full",
          isOnline
            ? "bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.8)]"
            : isDegraded
              ? "bg-amber-400"
              : "bg-rose-400"
        )}
      />
      <span className="text-[11px] font-semibold tracking-wide text-white">
        {STATE_LABEL[status.state]}
      </span>
    </Link>
  );
}

export function Header({ title, subtitle }: { title: string; subtitle?: string }) {
  const { toggleTheme } = useTheme();
  function triggerSearch() {
    window.dispatchEvent(new CustomEvent("open-command-palette"));
  }

  return (
    <header className="mx-3 mt-3 flex h-[68px] shrink-0 items-center justify-between gap-4 rounded-[26px] refraction-glass-card border-white/20 px-5 shadow-2xl backdrop-blur-3xl sm:px-6">
      {/* Page Title & Subtitle */}
      <div className="min-w-0">
        <h1 className="truncate text-xl font-bold tracking-tight text-white sm:text-2xl font-sans">
          {title}
        </h1>
        {subtitle && (
          <p className="truncate text-xs font-medium text-white/60 mt-0.5">
            {subtitle}
          </p>
        )}
      </div>

      {/* Top Right Actions */}
      <div className="flex shrink-0 items-center gap-3">
        <StatusBadge />

        {/* Global Search / Command Bar Trigger */}
        <button
          type="button"
          onClick={triggerSearch}
          className="refraction-glass-btn flex items-center gap-2.5 rounded-full px-3.5 py-1.5 text-xs text-white/70 shadow-sm transition-all hover:text-white"
          title="Search Anything (⌘K)"
        >
          <Search size={14} className="text-cyan-400" aria-hidden />
          <span className="hidden sm:inline font-medium">Search...</span>
          <kbd className="rounded-full bg-white/10 px-2 py-0.5 text-[10px] font-mono text-white/80">
            ⌘K
          </kbd>
        </button>

        <button
          type="button"
          onClick={toggleTheme}
          className="refraction-glass-btn relative flex h-9 w-9 items-center justify-center rounded-full text-white/70 shadow-sm transition-colors hover:text-white"
          title="Toggle color theme"
          aria-label="Toggle color theme"
        >
          <Moon className="theme-icon-light" size={16} />
          <Sun className="theme-icon-dark" size={16} />
        </button>

        {/* Notification Bell */}
        <Link
          href="/notifications"
          className="refraction-glass-btn relative flex h-9 w-9 items-center justify-center rounded-full text-white/70 shadow-sm transition-colors hover:text-white"
          title="Notifications & Alerts"
        >
          <Bell size={16} />
          <span className="absolute top-1.5 right-1.5 h-2 w-2 rounded-full bg-[#FF7849]" />
        </Link>

        {/* User Avatar Capsule */}
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
    : "H";

  return (
    <div className="flex items-center gap-2">
      {/* Stylized Avatar Frame (Matching Image 2's gold/amber avatar ring) */}
      <div
        className="relative flex h-9 w-9 items-center justify-center rounded-full bg-gradient-to-tr from-[var(--color-primary)] to-[var(--color-secondary)] border-2 border-white/50 shadow-md font-bold text-xs text-white"
        title={user.email}
      >
        <span>{initials}</span>
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
        className="hidden sm:inline-flex rounded-full border border-[var(--color-border)] bg-[var(--color-surface)]/70 px-3 py-1.5 text-xs font-semibold text-[var(--color-muted)] hover:border-[var(--color-border-highlight)] hover:text-[var(--color-foreground)] transition-all disabled:opacity-50"
      >
        {busy ? "..." : "Sign out"}
      </button>
    </div>
  );
}
