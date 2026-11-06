"use client";

import { useQuery } from "@tanstack/react-query";

import { Header } from "@/components/layout/header";
import { AppFooter } from "@/components/layout/app-footer";
import { Card, EmptyState } from "@/components/ui/card";
import { useSession } from "@/components/providers/session-provider";
import { api } from "@/lib/api/client";
import type { SocialPlatform } from "@/lib/api/types";

/** Source Manager (read-only): what each connector can and cannot actually do. */
export function SourcesView() {
  const { user } = useSession();
  const platforms = useQuery({
    queryKey: ["social", "platforms"],
    queryFn: () => api.get<SocialPlatform[]>("/social/platforms"),
  });

  if (!user) return null;
  const rows = platforms.data ?? [];

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <Header title="Sources" subtitle="Connector health, capabilities and honest limitations" />
      <main className="flex-1 overflow-y-auto p-4">
        {platforms.isPending ? (
          <EmptyState title="Loading sources…" description="" />
        ) : (
          <div className="grid gap-3 md:grid-cols-2">
            {rows.map((p) => (
              <Card key={p.slug}>
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium">{p.name}</span>
                  <span className={healthTone(p.health_status)}>{p.is_enabled ? p.health_status : "disabled"}</span>
                </div>
                <p className="mt-1 text-xs text-[var(--color-muted)]">
                  {String(p.capabilities.access_method ?? (p.is_enabled ? "permitted access" : "no permitted access"))}
                </p>
                {Object.values(p.limitations).some(Boolean) && (
                  <ul className="mt-2 space-y-0.5">
                    {Object.entries(p.limitations).map(([key, value]) => (
                      <li key={key} className="text-xs text-[var(--color-muted)]">
                        <span className="font-medium">{key}:</span> {String(value)}
                      </li>
                    ))}
                  </ul>
                )}
                <p className="mt-2 text-xs text-[var(--color-muted)]">
                  last run {p.last_run_at ? new Date(p.last_run_at).toLocaleString() : "never"}
                </p>
                {p.last_error && <p className="mt-1 text-xs text-[var(--color-error)]">last error: {p.last_error}</p>}
              </Card>
            ))}
          </div>
        )}
        <p className="mt-3 text-xs text-[var(--color-muted)]">
          Enabling or fully configuring a source is an operator action (its access terms and any
          required credentials are set server-side); a connector that cannot be reached is shown as
          disabled or failed rather than presented as working.
        </p>
        <AppFooter />
      </main>
    </div>
  );
}

function healthTone(status: string): string {
  if (status === "working") return "text-xs text-[var(--color-success)]";
  if (status === "failed") return "text-xs text-[var(--color-error)]";
  if (status === "degraded") return "text-xs text-[var(--color-warning)]";
  return "text-xs text-[var(--color-muted)]";
}
