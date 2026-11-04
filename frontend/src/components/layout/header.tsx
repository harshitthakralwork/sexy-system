"use client";

import { Bell, Search } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { useSession } from "@/components/providers/session-provider";
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
      className="hidden items-center gap-2 rounded-full border border-white/10 bg-white/[0.04] px-3 py-1 text-xs font-medium text-[var(--color-muted)] hover:border-white/20 transition-all sm:flex"
      title="Infrastructure & Source Health"
    >
      <span
        className={cn(
          "h-2 w-2 rounded-full",
          isOnline
            ? "bg-[#D4EF8A] shadow-[0_0_8px_rgba(212,239,138,0.6)]"
            : isDegraded
              ? "bg-[#FFB020]"
              : "bg-[#FF6666]"
        )}
      />
      <span className="text-[11px] font-semibold tracking-wide text-white/90">
        {STATE_LABEL[status.state]}
      </span>
    </Link>
  );
}

export function Header({ title, subtitle }: { title: string; subtitle?: string }) {
  function triggerSearch() {
    window.dispatchEvent(new CustomEvent("open-command-palette"));
  }

  return (
    <header className="flex h-[76px] shrink-0 items-center justify-between gap-4 border-b border-[var(--color-border)] bg-[var(--color-sidebar)]/80 px-6 sm:px-8 backdrop-blur-xl">
      {/* Page Title & Subtitle */}
      <div className="min-w-0">
        <h1 className="truncate text-xl font-bold tracking-tight text-white sm:text-2xl font-sans">
          {title}
        </h1>
        {subtitle && (
          <p className="truncate text-xs font-medium text-[var(--color-muted)] mt-0.5">
            {subtitle}
          </p>
        )}
      </div>

      {/* Top Right Actions (Matching Image 2) */}
      <div className="flex shrink-0 items-center gap-3">
        <StatusBadge />

        {/* Global Search / Command Bar Trigger */}
        <button
          type="button"
          onClick={triggerSearch}
          className="flex items-center gap-2.5 rounded-full border border-white/10 bg-white/[0.04] px-3.5 py-1.5 text-xs text-[var(--color-muted)] transition-all hover:border-white/20 hover:text-white"
          title="Search Anything (⌘K)"
        >
          <Search size={14} className="text-[var(--color-muted)]" aria-hidden />
          <span className="hidden sm:inline font-medium">Search...</span>
          <kbd className="rounded bg-black/40 px-1.5 py-0.5 text-[10px] font-mono text-[var(--color-muted)]">
            ⌘K
          </kbd>
        </button>

        {/* Notification Bell */}
        <Link
          href="/notifications"
          className="relative flex h-9 w-9 items-center justify-center rounded-full border border-white/10 bg-white/[0.04] text-[var(--color-muted)] transition-colors hover:border-white/20 hover:text-white"
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
        className="relative flex h-9 w-9 items-center justify-center rounded-full bg-gradient-to-tr from-[#3A373E] to-[#252428] border-2 border-[#FF7849]/50 shadow-md font-bold text-xs text-white"
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
        className="hidden sm:inline-flex rounded-full border border-white/10 bg-white/[0.04] px-3 py-1.5 text-xs font-semibold text-[var(--color-muted)] hover:border-white/20 hover:text-white transition-all disabled:opacity-50"
      >
        {busy ? "..." : "Sign out"}
      </button>
    </div>
  );
}
