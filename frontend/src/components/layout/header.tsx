"use client";

import { Monitor, Moon, Sun } from "lucide-react";

import { useBackendStatus } from "@/hooks/use-backend-status";
import { cn } from "@/lib/utils";
import { useTheme } from "@/components/providers/theme-provider";

const STATE_LABEL: Record<string, string> = {
  online: "API connected",
  degraded: "API up, dependency down",
  offline: "API unreachable",
  checking: "Checking connection",
};

function StatusPill() {
  const status = useBackendStatus();

  const tone =
    status.state === "online"
      ? "text-[var(--color-success)]"
      : status.state === "degraded"
        ? "text-[var(--color-warning)]"
        : status.state === "offline"
          ? "text-[var(--color-error)]"
          : "text-[var(--color-muted)]";

  const failed = (status.ready?.components ?? []).filter((c) => !c.ok).map((c) => c.name);

  return (
    <span
      className={cn("status-dot text-xs font-medium", tone)}
      title={
        status.state === "offline"
          ? (status.error ?? "Start the backend with ./scripts/dev-backend.ps1")
          : failed.length
            ? `Unavailable: ${failed.join(", ")}`
            : STATE_LABEL[status.state]
      }
    >
      {STATE_LABEL[status.state]}
    </span>
  );
}

export function Header({ title, subtitle }: { title: string; subtitle?: string }) {
  const { theme, toggleTheme } = useTheme();

  return (
    <header className="flex items-center justify-between gap-4 border-b border-border bg-[var(--color-surface)] px-6 py-3">
      <div className="min-w-0">
        <h1 className="truncate text-lg font-semibold leading-tight">{title}</h1>
        {subtitle && <p className="truncate text-xs text-[var(--color-muted)]">{subtitle}</p>}
      </div>

      <div className="flex shrink-0 items-center gap-4">
        <StatusPill />

        {/* Global search is Phase 2. It is absent rather than a dead input. */}
        <span className="hidden items-center gap-2 rounded-md border border-border px-3 py-1.5 text-xs text-[var(--color-muted)] md:flex">
          <Monitor size={14} aria-hidden />
          Global search — Phase 2
        </span>

        <button
          type="button"
          onClick={toggleTheme}
          className="rounded-md p-2 text-[var(--color-muted)] hover:bg-[var(--color-surface-elevated)] hover:text-[var(--color-foreground)]"
          aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
        >
          {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
        </button>
      </div>
    </header>
  );
}
