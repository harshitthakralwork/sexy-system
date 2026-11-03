"use client";

import { Bell, Moon, Search, Sun } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { useSession } from "@/components/providers/session-provider";
import { useTheme } from "@/components/providers/theme-provider";
import { useBackendStatus } from "@/hooks/use-backend-status";
import { cn } from "@/lib/utils";

const STATE_LABEL: Record<string, string> = {
  online: "All Systems Healthy",
  degraded: "API up, dependency down",
  offline: "API unreachable",
  checking: "Checking health",
};

function StatusPill() {
  const status = useBackendStatus();

  const tone =
    status.state === "online"
      ? "text-[var(--color-success)] bg-[var(--color-success)]/10 border-[var(--color-success)]/30"
      : status.state === "degraded"
        ? "text-[var(--color-warning)] bg-[var(--color-warning)]/10 border-[var(--color-warning)]/30"
        : status.state === "offline"
          ? "text-[var(--color-error)] bg-[var(--color-error)]/10 border-[var(--color-error)]/30"
          : "text-[var(--color-muted)] bg-[var(--color-muted)]/10 border-[var(--color-border)]";

  const failed = (status.ready?.components ?? []).filter((c) => !c.ok).map((c) => c.name);

  return (
    <Link
      href="/sources"
      className={cn(
        "hidden items-center gap-2 rounded-full border px-2.5 py-1 text-xs font-medium transition-colors hover:opacity-90 sm:flex",
        tone
      )}
      title={
        status.state === "offline"
          ? (status.error ?? "Start the backend with ./scripts/dev-backend.ps1")
          : failed.length
            ? `Unavailable: ${failed.join(", ")}`
            : "PostgreSQL, Celery/Worker, and Redis are verified."
      }
    >
      <span
        className={cn(
          "h-2 w-2 rounded-full",
          status.state === "online"
            ? "animate-pulse bg-[var(--color-success)]"
            : status.state === "degraded"
              ? "bg-[var(--color-warning)]"
              : status.state === "offline"
                ? "bg-[var(--color-error)]"
                : "bg-[var(--color-muted)]"
        )}
      />
      <span>{STATE_LABEL[status.state]}</span>
    </Link>
  );
}

export function Header({ title, subtitle }: { title: string; subtitle?: string }) {
  const { theme, toggleTheme } = useTheme();

  function triggerSearch() {
    window.dispatchEvent(new CustomEvent("open-command-palette"));
  }

  return (
    <header className="flex items-center justify-between gap-4 border-b border-border bg-[var(--color-surface)]/90 px-6 py-3 backdrop-blur-md">
      <div className="min-w-0">
        <h1 className="truncate text-base font-semibold leading-tight tracking-tight sm:text-lg">
          {title}
        </h1>
        {subtitle && <p className="truncate text-xs text-[var(--color-muted)]">{subtitle}</p>}
      </div>

      <div className="flex shrink-0 items-center gap-3">
        <StatusPill />

        {/* Global Search / Command Bar Trigger */}
        <button
          type="button"
          onClick={triggerSearch}
          className="flex items-center gap-2 rounded-lg border border-border bg-[var(--color-background)] px-3 py-1.5 text-xs text-[var(--color-muted)] transition-all hover:border-[var(--color-primary)] hover:text-[var(--color-foreground)]"
          title="Open Quick Search & Command Palette (Ctrl+K / ⌘K)"
        >
          <Search size={14} className="text-[var(--color-muted)]" aria-hidden />
          <span className="hidden sm:inline">Quick Jump...</span>
          <kbd className="rounded bg-[var(--color-surface-elevated)] px-1.5 py-0.5 text-[10px] font-mono text-[var(--color-muted)]">
            ⌘K
          </kbd>
        </button>

        {/* Notifications Shortcut */}
        <Link
          href="/notifications"
          className="relative rounded-lg p-2 text-[var(--color-muted)] transition-colors hover:bg-[var(--color-surface-elevated)] hover:text-[var(--color-foreground)]"
          title="Notification Center"
          aria-label="Notification Center"
        >
          <Bell size={16} />
        </Link>

        {/* Theme Toggle */}
        <button
          type="button"
          onClick={toggleTheme}
          className="rounded-lg p-2 text-[var(--color-muted)] transition-colors hover:bg-[var(--color-surface-elevated)] hover:text-[var(--color-foreground)]"
          aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
          title={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
        >
          {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
        </button>

        <div className="h-4 w-px bg-border" />

        <UserMenu />
      </div>
    </header>
  );
}

function UserMenu() {
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
    : "U";

  return (
    <div className="flex items-center gap-2.5">
      <div
        className="flex h-7 w-7 items-center justify-center rounded-full bg-[var(--color-primary)]/20 font-semibold text-[11px] text-[var(--color-secondary)] ring-1 ring-[var(--color-primary)]/40"
        title={user.email}
      >
        {initials}
      </div>
      <span className="hidden max-w-[120px] truncate text-xs font-medium sm:inline" title={user.email}>
        {user.display_name}
      </span>
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
        className="rounded-lg border border-border px-2.5 py-1 text-xs font-medium text-[var(--color-muted)] transition-colors hover:bg-[var(--color-surface-elevated)] hover:text-[var(--color-foreground)] disabled:opacity-60"
      >
        {busy ? "..." : "Sign out"}
      </button>
    </div>
  );
}
