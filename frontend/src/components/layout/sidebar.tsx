"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ChevronsLeft, ChevronsRight, Zap } from "lucide-react";
import { useState } from "react";

import { navigation } from "./navigation";
import { cn } from "@/lib/utils";

export function Sidebar() {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);

  return (
    <aside
      className={cn(
        "flex h-full flex-col border-r border-border bg-[var(--color-sidebar)] transition-[width] duration-200",
        collapsed ? "w-[68px]" : "w-[248px]",
      )}
      aria-label="Primary navigation"
    >
      <div className="flex items-center gap-2 px-4 py-5">
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-[var(--color-primary)] text-white">
          <Zap size={16} aria-hidden />
        </span>
        {!collapsed && (
          <span className="truncate">
            <span className="block text-sm font-semibold leading-tight">SparkXFlow</span>
            <span className="block text-xs text-[var(--color-muted)]">Nexus</span>
          </span>
        )}
      </div>

      <nav className="flex-1 overflow-y-auto px-2 pb-4">
        {navigation.map((section) => (
          <div key={section.title} className="mb-4">
            {!collapsed && (
              <p className="px-2 pb-1 text-[11px] font-semibold uppercase tracking-wide text-[var(--color-muted)]">
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
                      {/* Rendered as a button, not a link: navigating to an unbuilt
                          module would imply it works. */}
                      <button
                        type="button"
                        disabled
                        title={`${item.label} — not built yet`}
                        aria-label={`${item.label} (not available yet)`}
                        className="flex w-full cursor-not-allowed items-center gap-2.5 rounded-md px-2 py-1.5 text-sm text-[var(--color-muted)] opacity-60"
                      >
                        <Icon size={16} className="shrink-0" aria-hidden />
                        {!collapsed && <span className="truncate">{item.label}</span>}
                        {!collapsed && (
                          <span className="ml-auto rounded bg-[var(--color-surface)] px-1.5 py-0.5 text-[10px]">
                            soon
                          </span>
                        )}
                      </button>
                    </li>
                  );
                }

                return (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      aria-current={active ? "page" : undefined}
                      className={cn(
                        "flex items-center gap-2.5 rounded-md px-2 py-1.5 text-sm transition-colors",
                        active
                          ? "bg-[var(--color-surface)] font-medium text-[var(--color-foreground)]"
                          : "text-[var(--color-muted)] hover:bg-[var(--color-surface)] hover:text-[var(--color-foreground)]",
                      )}
                    >
                      <Icon size={16} className="shrink-0" aria-hidden />
                      {!collapsed && <span className="truncate">{item.label}</span>}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>

      <div className="border-t border-border p-2">
        <button
          type="button"
          onClick={() => setCollapsed((value) => !value)}
          className="flex w-full items-center justify-center gap-2 rounded-md px-2 py-2 text-xs text-[var(--color-muted)] hover:bg-[var(--color-surface)]"
          aria-expanded={!collapsed}
        >
          {collapsed ? <ChevronsRight size={16} /> : <ChevronsLeft size={16} />}
          {!collapsed && <span>Collapse</span>}
        </button>
      </div>
    </aside>
  );
}
