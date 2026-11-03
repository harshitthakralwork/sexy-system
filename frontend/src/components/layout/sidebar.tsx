"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ChevronsLeft, ChevronsRight, Search, Zap } from "lucide-react";
import { useState } from "react";

import { navigation } from "./navigation";
import { cn } from "@/lib/utils";

export function Sidebar() {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);

  function triggerSearch() {
    window.dispatchEvent(new CustomEvent("open-command-palette"));
  }

  return (
    <aside
      className={cn(
        "flex h-full flex-col border-r border-border bg-[var(--color-sidebar)] transition-[width] duration-200 select-none",
        collapsed ? "w-[68px]" : "w-[256px]"
      )}
      aria-label="Primary navigation"
    >
      {/* Brand Header */}
      <div className="flex items-center justify-between px-4 py-4 border-b border-border/60">
        <Link href="/dashboard" className="flex items-center gap-2.5 group">
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[var(--color-primary)] text-white shadow-md shadow-[var(--color-primary)]/20 transition-transform group-hover:scale-105">
            <Zap size={16} aria-hidden />
          </span>
          {!collapsed && (
            <span className="truncate">
              <span className="block text-sm font-bold tracking-tight text-[var(--color-foreground)]">
                SparkXFlow
              </span>
              <span className="block text-[11px] font-medium text-[var(--color-primary)] uppercase tracking-wider">
                Nexus
              </span>
            </span>
          )}
        </Link>
      </div>

      {/* Quick Jump Bar */}
      {!collapsed && (
        <div className="px-3 pt-3">
          <button
            type="button"
            onClick={triggerSearch}
            className="flex w-full items-center justify-between rounded-lg border border-border/80 bg-[var(--color-surface)]/70 px-2.5 py-1.5 text-xs text-[var(--color-muted)] transition-all hover:border-[var(--color-primary)]/60 hover:text-[var(--color-foreground)] shadow-xs"
          >
            <div className="flex items-center gap-2">
              <Search size={13} />
              <span>Jump to feature...</span>
            </div>
            <kbd className="rounded bg-[var(--color-surface-elevated)] px-1.5 py-0.5 text-[10px] font-mono">
              ⌘K
            </kbd>
          </button>
        </div>
      )}

      {/* Navigation Links */}
      <nav className="flex-1 overflow-y-auto px-2.5 py-3 scrollbar-thin">
        {navigation.map((section) => (
          <div key={section.title} className="mb-4">
            {!collapsed && (
              <p className="px-2 pb-1.5 text-[10px] font-bold uppercase tracking-wider text-[var(--color-muted)]/80">
                {section.title}
              </p>
            )}
            <ul className="space-y-0.5">
              {section.items.map((item) => {
                const Icon = item.icon;
                const active = pathname === item.href;

                if (!item.available) {
                  return (
                    <li key={item.href}>
                      <button
                        type="button"
                        disabled
                        title={`${item.label} — upcoming`}
                        className="flex w-full cursor-not-allowed items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-xs text-[var(--color-muted)] opacity-50"
                      >
                        <Icon size={15} className="shrink-0" aria-hidden />
                        {!collapsed && <span className="truncate">{item.label}</span>}
                      </button>
                    </li>
                  );
                }

                return (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      aria-current={active ? "page" : undefined}
                      title={collapsed ? item.label : undefined}
                      className={cn(
                        "flex items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-xs font-medium transition-all",
                        active
                          ? "bg-[var(--color-primary)]/15 text-[var(--color-foreground)] border-l-2 border-[var(--color-primary)] pl-2 font-semibold shadow-xs"
                          : "text-[var(--color-muted)] hover:bg-[var(--color-surface)] hover:text-[var(--color-foreground)]"
                      )}
                    >
                      <Icon
                        size={15}
                        className={cn(
                          "shrink-0 transition-colors",
                          active ? "text-[var(--color-primary)]" : "text-[var(--color-muted)]"
                        )}
                        aria-hidden
                      />
                      {!collapsed && <span className="truncate">{item.label}</span>}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>

      {/* Collapse Footer */}
      <div className="border-t border-border p-2">
        <button
          type="button"
          onClick={() => setCollapsed((value) => !value)}
          className="flex w-full items-center justify-center gap-2 rounded-lg px-2 py-1.5 text-xs text-[var(--color-muted)] transition-colors hover:bg-[var(--color-surface)] hover:text-[var(--color-foreground)]"
          aria-expanded={!collapsed}
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {collapsed ? <ChevronsRight size={15} /> : <ChevronsLeft size={15} />}
          {!collapsed && <span>Collapse Sidebar</span>}
        </button>
      </div>
    </aside>
  );
}
