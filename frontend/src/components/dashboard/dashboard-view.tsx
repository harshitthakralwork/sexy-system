"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";

import { Header } from "@/components/layout/header";
import { Card, CardFootnote, CardTitle, CardValue, EmptyState } from "@/components/ui/card";
import { useBackendStatus } from "@/hooks/use-backend-status";
import { api } from "@/lib/api/client";
import type { AnalyticsBucket, AnalyticsOut } from "@/lib/api/types";

/** The count for one key in a bucket list, or null when that key is absent. */
function bucketCount(buckets: AnalyticsBucket[], key: string): number | null {
  const hit = buckets.find((bucket) => bucket.key === key);
  return hit ? hit.count : null;
}

function sumCounts(buckets: AnalyticsBucket[]): number {
  return buckets.reduce((total, bucket) => total + bucket.count, 0);
}

/** True only when the operator genuinely has nothing to show. */
function isEmptySurface(data: AnalyticsOut): boolean {
  return (
    data.leads_total === 0 &&
    sumCounts(data.social_by_platform) === 0 &&
    sumCounts(data.startups_by_funding_stage) === 0 &&
    sumCounts(data.discovery_jobs_by_status) === 0
  );
}

export function DashboardView() {
  const status = useBackendStatus();
  const components = status.ready?.components ?? [];
  // Same aggregate the Analytics page reads, so the two can never disagree.
  const summary = useQuery({
    queryKey: ["analytics"],
    queryFn: () => api.get<AnalyticsOut>("/analytics"),
  });
  const data = summary.data;

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
          <div className="mb-3 flex items-baseline justify-between gap-3">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-[var(--color-muted)]">
              Your data
            </h2>
            <Link
              className="text-xs text-[var(--color-muted)] hover:text-[var(--color-primary)]"
              href="/analytics"
            >
              Full analytics
            </Link>
          </div>
          {summary.isError && (
            <EmptyState
              title="Counts unavailable"
              description={
                summary.error instanceof Error
                  ? summary.error.message
                  : "The analytics endpoint did not answer."
              }
            />
          )}
          {summary.isPending && (
            <p className="text-sm text-[var(--color-muted)]">Reading your rows…</p>
          )}
          {data && isEmptySurface(data) && (
            <EmptyState
              title="Nothing collected yet"
              description="Run a discovery job or a social track. This panel is empty because there is
                nothing stored yet — showing sample numbers would make the dashboard lie."
            />
          )}
          {data && !isEmptySurface(data) && (
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <StatCard
                title="Leads"
                href="/leads"
                value={data.leads_total}
                footnote={
                  `active ${bucketCount(data.businesses_by_lifecycle, "active") ?? 0}` +
                  ` · archived ${bucketCount(data.businesses_by_lifecycle, "archived") ?? 0}`
                }
              />
              <StatCard
                title="Discovery jobs"
                href="/leads"
                value={sumCounts(data.discovery_jobs_by_status)}
                footnote={
                  `completed ${bucketCount(data.discovery_jobs_by_status, "completed") ?? 0}` +
                  ` · failed ${bucketCount(data.discovery_jobs_by_status, "failed") ?? 0}`
                }
              />
              <StatCard
                title="Social results"
                href="/intelligence"
                value={sumCounts(data.social_by_platform)}
                footnote={`${
                  bucketCount(data.social_by_classification, "Unclassified") ?? 0
                } unclassified`}
              />
              <StatCard
                title="Startups"
                href="/startups"
                value={sumCounts(data.startups_by_funding_stage)}
                footnote={
                  data.startups_by_funding_stage[0]
                    ? `most common stage: ${data.startups_by_funding_stage[0].key}`
                    : "none tracked"
                }
              />
            </div>
          )}
        </section>
      </main>
    </div>
  );
}

function StatCard({
  title,
  href,
  value,
  footnote,
}: {
  title: string;
  href: string;
  value: number;
  footnote: string;
}) {
  return (
    <Card>
      <CardTitle>{title}</CardTitle>
      <CardValue>
        <Link className="hover:text-[var(--color-primary)]" href={href}>
          {value}
        </Link>
      </CardValue>
      <CardFootnote>{footnote}</CardFootnote>
    </Card>
  );
}
