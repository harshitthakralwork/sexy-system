"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { Header } from "@/components/layout/header";
import { Card, CardTitle, EmptyState } from "@/components/ui/card";
import { useSession } from "@/components/providers/session-provider";
import { api } from "@/lib/api/client";
import type { ServiceDetail, ServiceList, Service } from "@/lib/api/types";

/** Service catalog: the rules a business is scored against, not a static list. */
export function ServiceCatalog() {
  const { csrf, user } = useSession();
  const queryClient = useQueryClient();

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const listing = useQuery({
    queryKey: ["services"],
    queryFn: () => api.get<ServiceList>("/services"),
  });

  const createService = useMutation({
    mutationFn: () =>
      api.post<Service>(
        "/services",
        { name: name.trim(), description: description.trim() || null },
        csrf,
      ),
    onSuccess: (created) => {
      setName("");
      setDescription("");
      setNotice(`Service "${created.name}" created.`);
      queryClient.invalidateQueries({ queryKey: ["services"] });
    },
    onError: (caught) => setError(errorMessage(caught)),
  });

  if (!user) return null;

  const services = listing.data?.items ?? [];

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <Header
        title="Service Catalog"
        subtitle={
          listing.data
            ? `${services.length} services define how businesses are qualified`
            : "Loading catalog…"
        }
      />

      <main className="flex-1 overflow-y-auto p-4">
        <Card>
          <CardTitle>New service</CardTitle>
          <p className="mt-1 text-xs text-[var(--color-muted)]">
            A service carries one or more scoring profiles. Qualification uses the active
            profile&apos;s rules — deterministic, never a model opinion.
          </p>
          <div className="mt-3 flex flex-wrap items-end gap-3">
            <label className="min-w-52 flex-1 text-sm">
              <span className="text-[var(--color-muted)]">Name</span>
              <input
                className="mt-1 w-full rounded-md border border-border bg-[var(--color-background)] px-2 py-1.5"
                placeholder="e.g. Social Media Management"
                value={name}
                onChange={(event) => setName(event.target.value)}
              />
            </label>
            <label className="min-w-52 flex-1 text-sm">
              <span className="text-[var(--color-muted)]">Description</span>
              <input
                className="mt-1 w-full rounded-md border border-border bg-[var(--color-background)] px-2 py-1.5"
                value={description}
                onChange={(event) => setDescription(event.target.value)}
              />
            </label>
            <button
              className={buttonClass(false)}
              disabled={!name.trim() || createService.isPending}
              onClick={() => createService.mutate()}
              type="button"
            >
              Create service
            </button>
          </div>
          {(notice || error) && (
            <div className="mt-3 text-sm">
              {error && <p className="text-[var(--color-error)]">{error}</p>}
              {notice && <p className="text-[var(--color-muted)]">{notice}</p>}
            </div>
          )}
        </Card>

        {listing.isError && (
          <div className="mt-4 text-sm text-[var(--color-error)]">
            Catalog could not be loaded: {errorMessage(listing.error)}
          </div>
        )}

        {!listing.isPending && services.length === 0 && !listing.isError && (
          <div className="mt-4">
            <EmptyState
              title="No services defined"
              description="The backend seeds a default web-presence service on first load, so an empty catalog means the backend is unreachable."
            />
          </div>
        )}

        <div className="mt-4 space-y-3">
          {services.map((service) => (
            <ServiceCard
              key={service.id}
              serviceId={service.id}
              expanded={expanded === service.id}
              onToggle={() => setExpanded((current) => (current === service.id ? null : service.id))}
            />
          ))}
        </div>
      </main>
    </div>
  );
}

function ServiceCard({
  serviceId,
  expanded,
  onToggle,
}: {
  serviceId: string;
  expanded: boolean;
  onToggle: () => void;
}) {
  const detail = useQuery({
    queryKey: ["service-detail", serviceId],
    queryFn: () => api.get<ServiceDetail>(`/services/${serviceId}`),
    enabled: expanded,
  });

  if (!expanded) {
    return (
      <Card className="flex items-center justify-between">
        <ServiceSummary serviceId={serviceId} />
        <button className={buttonClass(false)} onClick={onToggle} type="button">
          Details
        </button>
      </Card>
    );
  }

  if (detail.isPending) {
    return (
      <Card>
        <ServiceSummary serviceId={serviceId} />
        <p className="mt-3 text-sm text-[var(--color-muted)]">Loading profiles…</p>
      </Card>
    );
  }

  if (detail.isError) {
    return (
      <Card>
        <ServiceSummary serviceId={serviceId} />
        <p className="mt-3 text-sm text-[var(--color-error)]">
          {errorMessage(detail.error)}
        </p>
        <button className={`${buttonClass(false)} mt-3`} onClick={onToggle} type="button">
          Close
        </button>
      </Card>
    );
  }

  const service = detail.data;
  const profiles = service?.profiles ?? [];

  return (
    <Card>
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-medium">{service?.name}</h3>
          {service?.description && (
            <p className="mt-0.5 text-xs text-[var(--color-muted)]">{service.description}</p>
          )}
        </div>
        <button className={buttonClass(false)} onClick={onToggle} type="button">
          Close
        </button>
      </div>

      {profiles.length === 0 && (
        <p className="mt-3 text-sm text-[var(--color-muted)]">
          No scoring profiles defined for this service.
        </p>
      )}

      {profiles.map((profile) => (
        <section key={profile.id} className="mt-4 rounded-md border border-border p-3">
          <div className="flex items-center justify-between">
            <h4 className="text-sm font-medium">
              {profile.name}
              <span className="ml-2 text-xs text-[var(--color-muted)]">v{profile.version}</span>
            </h4>
            <span className="text-xs text-[var(--color-muted)]">
              qualifies at score ≥ {profile.qualification_threshold}
            </span>
          </div>
          <table className="mt-2 w-full text-xs">
            <thead>
              <tr className="border-b border-border text-left uppercase tracking-wide text-[var(--color-muted)]">
                <th className="py-1 pr-2">Rule</th>
                <th className="py-1 pr-2">Signal</th>
                <th className="py-1 pr-2">Weight</th>
                <th className="py-1">Condition</th>
              </tr>
            </thead>
            <tbody>
              {profile.rules.map((rule) => (
                <tr key={rule.id} className="border-b border-border/50">
                  <td className="py-1 pr-2">{rule.rule_name}</td>
                  <td className="py-1 pr-2 font-mono text-[var(--color-muted)]">{rule.signal_key}</td>
                  <td className="py-1 pr-2">{rule.weight}</td>
                  <td className="py-1">
                    {rule.operator} {String(rule.threshold)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ))}
    </Card>
  );
}

/** Summary shown while collapsed; refetches the list-level data, never the detail. */
function ServiceSummary({ serviceId }: { serviceId: string }) {
  const listing = useQuery({
    queryKey: ["services"],
    queryFn: () => api.get<ServiceList>("/services"),
  });
  const service = (listing.data?.items ?? []).find((item) => item.id === serviceId);

  if (!service) return null;

  return (
    <div>
      <h3 className="text-sm font-medium">{service.name}</h3>
      {service.description && (
        <p className="mt-0.5 text-xs text-[var(--color-muted)]">{service.description}</p>
      )}
      <p className="mt-1 text-xs text-[var(--color-muted)]">
        slug: {service.slug}
        {service.is_active ? "" : " · inactive"}
      </p>
    </div>
  );
}

function buttonClass(active: boolean): string {
  return [
    "rounded-full border px-3 py-1.5 text-xs font-semibold transition-all disabled:opacity-40 cursor-pointer",
    active
      ? "refraction-glass-btn border-cyan-400/40 bg-cyan-500/20 text-cyan-200 shadow-[0_0_15px_rgba(0,212,255,0.25)] hover:bg-cyan-500/30 hover:text-white"
      : "border-white/10 bg-white/[0.04] text-white/70 hover:border-white/25 hover:text-white hover:bg-white/[0.08]",
  ].join(" ");
}

function errorMessage(caught: unknown): string {
  if (caught instanceof Error) return caught.message;
  return "Something went wrong.";
}
