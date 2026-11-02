"use client";

import { Header } from "@/components/layout/header";
import { Card, CardFootnote, CardTitle, CardValue, EmptyState } from "@/components/ui/card";
import { useBackendStatus } from "@/hooks/use-backend-status";

export function DashboardView() {
  const status = useBackendStatus();
  const components = status.ready?.components ?? [];

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <Header
        title="Dashboard"
        subtitle={
          status.info
            ? `${status.info.app_name} · ${status.info.environment} · region ${status.info.default_region}`
            : "Backend not reachable"
        }
      />

      <main className="flex-1 space-y-8 overflow-y-auto p-6">
        <section>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--color-muted)]">
            System status
          </h2>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <Card>
              <CardTitle>API</CardTitle>
              <CardValue>{status.state === "online" ? "Connected" : status.state}</CardValue>
              <CardFootnote>
                {status.state === "offline"
                  ? "Run ./scripts/dev-backend.ps1"
                  : `${status.info?.modules_enabled.length ?? 0} modules mounted`}
              </CardFootnote>
            </Card>

            <Card>
              <CardTitle>Execution model</CardTitle>
              <CardValue>{status.info?.execution_model ?? "—"}</CardValue>
              <CardFootnote>
                Local-first. Hybrid worker dispatch deferred per IMPLEMENTATION_PLAN.md.
              </CardFootnote>
            </Card>

            <Card>
              <CardTitle>AI layer</CardTitle>
              <CardValue>
                {status.info ? (status.info.ai_enabled ? "Enabled" : "Disabled") : "—"}
              </CardValue>
              <CardFootnote>
                Disabled means scoring runs on deterministic rules only — by design, not as a fault.
              </CardFootnote>
            </Card>

            <Card>
              <CardTitle>Dependencies</CardTitle>
              {components.length === 0 ? (
                <>
                  <CardValue>Unknown</CardValue>
                  <CardFootnote>Readiness endpoint not reachable.</CardFootnote>
                </>
              ) : (
                <ul className="mt-2 space-y-1.5">
                  {components.map((component) => (
                    <li key={component.name} className="flex items-center justify-between text-sm">
                      {/* Label carries the state; colour is decoration, not the message. */}
                      <span className="capitalize">{component.name}</span>
                      <span
                        className={
                          component.ok
                            ? "text-[var(--color-success)]"
                            : "text-[var(--color-error)]"
                        }
                      >
                        {component.ok
                          ? "Up"
                          : `Down${component.detail ? ` (${component.detail})` : ""}`}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </div>
        </section>

        <section>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--color-muted)]">
            Leads Intelligence
          </h2>
          <EmptyState
            title="No businesses discovered yet"
            description="Discovery is being wired to the database. This panel is empty because
              there is nothing stored yet — showing sample numbers would make the dashboard lie."
          />
        </section>
      </main>
    </div>
  );
}
