"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { Header } from "@/components/layout/header";
import { Card, CardTitle, EmptyState } from "@/components/ui/card";
import { useSession } from "@/components/providers/session-provider";
import { api } from "@/lib/api/client";
import type {
  ActivityList,
  BusinessDetail,
  Note,
  Opportunity,
  OpportunityList,
  Pipeline,
  ServiceList,
  Tag,
} from "@/lib/api/types";

export function BusinessProfile() {
  const { id } = useParams<{ id: string }>();
  if (!id) return null;
  return <Profile id={id} />;
}

function Profile({ id }: { id: string }) {
  const { csrf, user } = useSession();
  const queryClient = useQueryClient();
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const detail = useQuery({
    queryKey: ["business", id],
    queryFn: () => api.get<BusinessDetail>(`/businesses/${id}`),
  });

  const business = detail.data;

  async function invalidate() {
    await queryClient.invalidateQueries({ queryKey: ["business", id] });
  }

  if (!user) return null;

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <Header
        title={business?.name ?? "Business"}
        subtitle={
          business
            ? `${business.primary_category ?? "no category"} · ${business.city ?? "no city"}`
            : "Loading profile…"
        }
      />

      <main className="flex-1 space-y-4 overflow-y-auto p-4">
        {detail.isError && (
          <p className="text-sm text-[var(--color-error)]">
            Profile could not be loaded: {errorMessage(detail.error)}
          </p>
        )}

        {!detail.isPending && !business && (
          <EmptyState
            title="Not found"
            description="This record does not exist or is not yours."
            action={
              <Link className={buttonClass(false)} href="/leads">
                Back to leads
              </Link>
            }
          />
        )}

        {(notice || error) && (
          <div className="rounded-md border border-border bg-[var(--color-surface)] p-3 text-sm">
            {error && <p className="text-[var(--color-error)]">{error}</p>}
            {notice && <p className="text-[var(--color-muted)]">{notice}</p>}
          </div>
        )}

        {business && (
          <>
            <Overview business={business} onChanged={invalidate} onError={setError} />

            <div className="grid gap-4 lg:grid-cols-2">
              <Qualification
                businessId={id}
                csrf={csrf}
                onError={setError}
                onNotice={setNotice}
              />
              <CrmPanel
                businessId={id}
                csrf={csrf}
                onChanged={invalidate}
                onError={setError}
              />
            </div>

            <div className="grid gap-4 lg:grid-cols-2">
              <NotesPanel businessId={id} csrf={csrf} onError={setError} />
              <TagsPanel businessId={id} csrf={csrf} onError={setError} />
            </div>
          </>
        )}
      </main>
    </div>
  );
}

function Overview({
  business,
  onChanged,
  onError,
}: {
  business: BusinessDetail;
  onChanged: () => Promise<void>;
  onError: (message: string) => void;
}) {
  const { csrf } = useSession();

  async function act(path: string) {
    try {
      await api.post(path, undefined, csrf);
      await onChanged();
    } catch (caught) {
      onError(errorMessage(caught));
    }
  }

  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-base font-semibold">{business.name}</h2>
          {business.description && (
            <p className="mt-1 text-sm text-[var(--color-muted)]">{business.description}</p>
          )}
          <dl className="mt-3 grid gap-x-6 gap-y-1 text-sm sm:grid-cols-2">
            <Field label="Website" value={business.website_url ?? "none reported"} />
            <Field label="Website status" value={business.website_status} />
            <Field label="Phone" value={business.phone ?? "none reported"} />
            <Field label="Email" value={business.email ?? "none reported"} />
            <Field label="Address" value={business.address ?? "—"} />
            <Field
              label="CRM stage"
              value={business.crm_stage ?? "not in pipeline"}
            />
            <Field label="Sources" value={business.source_slugs.join(", ") || "—"} />
            <Field
              label="First discovered"
              value={business.first_discovered_at ? new Date(business.first_discovered_at).toLocaleDateString() : "—"}
            />
          </dl>
        </div>
        <div className="flex flex-col gap-2">
          <button className={buttonClass(false)} onClick={() => act(`/businesses/${business.id}/shortlist`)} type="button">
            Shortlist
          </button>
          <button className={buttonClass(false)} onClick={() => act(`/businesses/${business.id}/archive`)} type="button">
            Archive
          </button>
        </div>
      </div>

      {business.contacts.length > 0 && (
        <div className="mt-4 border-t border-border pt-3">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--color-muted)]">
            Contacts
          </h3>
          <ul className="mt-2 space-y-1 text-sm">
            {business.contacts.map((contact) => (
              <li key={contact.id} className="flex flex-wrap gap-3">
                <span className="text-[var(--color-muted)]">{contact.contact_type ?? "contact"}</span>
                <span>{contact.email ?? contact.phone ?? contact.full_name ?? "—"}</span>
                <span className="text-[var(--color-muted)]">({contact.verification_status})</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  );
}

function Qualification({
  businessId,
  csrf,
  onError,
  onNotice,
}: {
  businessId: string;
  csrf: string | null;
  onError: (message: string) => void;
  onNotice: (message: string) => void;
}) {
  const queryClient = useQueryClient();

  const services = useQuery({
    queryKey: ["services"],
    queryFn: () => api.get<ServiceList>("/services"),
  });

  const opportunities = useQuery({
    queryKey: ["opportunities", businessId],
    queryFn: () => api.get<OpportunityList>(`/services/opportunities?business_id=${businessId}`),
  });

  const qualify = useMutation({
    mutationFn: (serviceId: string) =>
      api.post<Opportunity>(`/services/${serviceId}/qualify/${businessId}`, undefined, csrf),
    onSuccess: (opportunity) => {
      onNotice(
        opportunity.status === "qualified"
          ? `Qualified at ${opportunity.score}/100.`
          : `Not qualified (${opportunity.score}/100).`,
      );
      queryClient.invalidateQueries({ queryKey: ["opportunities", businessId] });
    },
    onError: (caught) => onError(errorMessage(caught)),
  });

  const byService = useMemo(() => {
    const map = new Map<string, Opportunity>();
    for (const opportunity of opportunities.data?.items ?? []) {
      map.set(opportunity.service_id, opportunity);
    }
    return map;
  }, [opportunities.data]);

  return (
    <Card>
      <CardTitle>Qualification</CardTitle>
      <p className="mt-1 text-xs text-[var(--color-muted)]">
        Score is deterministic — derived from the stored rules and observed signals, not a model
        opinion.
      </p>

      {(services.data?.items ?? []).map((service) => {
        const opportunity = byService.get(service.id);
        return (
          <div className="mt-3 rounded-md border border-border p-3" key={service.id}>
            <div className="flex items-center justify-between gap-2">
              <div className="min-w-0">
                <p className="text-sm font-medium">{service.name}</p>
                <p className="truncate text-xs text-[var(--color-muted)]">
                  {service.description ?? service.slug}
                </p>
              </div>
              <button
                className={buttonClass(false)}
                disabled={qualify.isPending}
                onClick={() => qualify.mutate(service.id)}
                type="button"
              >
                {opportunity ? "Re-run" : "Qualify"}
              </button>
            </div>

            {opportunity && (
              <div className="mt-2 space-y-1 text-sm">
                <p className="flex items-center gap-2">
                  <span className="font-semibold">{opportunity.score}/100</span>
                  <span
                    className={
                      opportunity.status === "qualified"
                        ? "text-[var(--color-success)]"
                        : "text-[var(--color-muted)]"
                    }
                  >
                    {opportunity.status}
                  </span>
                  <span className="text-xs text-[var(--color-muted)]">
                    {opportunity.confidence}% signals observed
                  </span>
                </p>
                {opportunity.missing_information.length > 0 && (
                  <p className="text-xs text-[var(--color-warning)]">
                    Not observed: {opportunity.missing_information.join(", ")}
                  </p>
                )}
                <ul className="mt-1 space-y-0.5 border-t border-border/60 pt-1">
                  {opportunity.evidence.map((row) => (
                    <li className="flex justify-between gap-2 text-xs text-[var(--color-muted)]" key={row.id}>
                      <span className="truncate">{row.description}</span>
                      <span className="shrink-0">+{row.score_contribution}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        );
      })}

      {(services.data?.items ?? []).length === 0 && (
        <p className="mt-2 text-xs text-[var(--color-muted)]">No services configured.</p>
      )}
    </Card>
  );
}

function CrmPanel({
  businessId,
  csrf,
  onChanged,
  onError,
}: {
  businessId: string;
  csrf: string | null;
  onChanged: () => Promise<void>;
  onError: (message: string) => void;
}) {
  const queryClient = useQueryClient();

  const pipelines = useQuery({
    queryKey: ["crm-pipelines"],
    queryFn: () => api.get<Pipeline[]>("/crm/pipelines"),
  });

  const activities = useQuery({
    queryKey: ["activities", businessId],
    queryFn: () => api.get<ActivityList>(`/crm/activities?business_id=${businessId}&limit=10`),
  });

  const stages = pipelines.data?.[0]?.stages ?? [];

  const move = useMutation({
    mutationFn: (stageName: string) =>
      api.post(`/businesses/${businessId}/stage/${encodeURIComponent(stageName)}`, undefined, csrf),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["activities", businessId] });
      onChanged();
    },
    onError: (caught) => onError(errorMessage(caught)),
  });

  return (
    <Card>
      <CardTitle>CRM</CardTitle>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <select
          className="rounded-md border border-border bg-[var(--color-background)] px-2 py-1.5 text-sm"
          defaultValue=""
          onChange={(event) => {
            if (event.target.value) move.mutate(event.target.value);
          }}
        >
          <option disabled value="">
            Move to stage…
          </option>
          {stages.map((stage) => (
            <option key={stage.id} value={stage.name}>
              {stage.name}
            </option>
          ))}
        </select>
        {move.isPending && <span className="text-xs text-[var(--color-muted)]">Moving…</span>}
      </div>

      <h3 className="mt-3 text-xs font-semibold uppercase tracking-wide text-[var(--color-muted)]">
        Activity
      </h3>
      {(activities.data?.items ?? []).length === 0 ? (
        <p className="mt-1 text-xs text-[var(--color-muted)]">No activity yet.</p>
      ) : (
        <ul className="mt-2 space-y-1.5 text-sm">
          {(activities.data?.items ?? []).map((activity) => (
            <li className="flex justify-between gap-2" key={activity.id}>
              <span className="truncate">{activity.title}</span>
              <span className="shrink-0 text-xs text-[var(--color-muted)]">
                {new Date(activity.occurred_at).toLocaleDateString()}
              </span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function NotesPanel({
  businessId,
  csrf,
  onError,
}: {
  businessId: string;
  csrf: string | null;
  onError: (message: string) => void;
}) {
  const queryClient = useQueryClient();
  const [content, setContent] = useState("");

  const notes = useQuery({
    queryKey: ["notes", businessId],
    queryFn: () => api.get<Note[]>(`/businesses/${businessId}/notes`),
  });

  const addNote = useMutation({
    mutationFn: () => api.post<Note>(`/businesses/${businessId}/notes`, { content }, csrf),
    onSuccess: () => {
      setContent("");
      queryClient.invalidateQueries({ queryKey: ["notes", businessId] });
    },
    onError: (caught) => onError(errorMessage(caught)),
  });

  return (
    <Card>
      <CardTitle>Notes</CardTitle>
      <div className="mt-2 flex gap-2">
        <textarea
          className="min-h-16 flex-1 rounded-md border border-border bg-[var(--color-background)] px-2 py-1.5 text-sm"
          placeholder="Add a note about this lead…"
          value={content}
          onChange={(event) => setContent(event.target.value)}
        />
        <button
          className={buttonClass(false)}
          disabled={!content.trim() || addNote.isPending}
          onClick={() => addNote.mutate()}
          type="button"
        >
          Add
        </button>
      </div>
      {(notes.data ?? []).length === 0 ? (
        <p className="mt-2 text-xs text-[var(--color-muted)]">No notes yet.</p>
      ) : (
        <ul className="mt-2 space-y-2">
          {(notes.data ?? []).map((note) => (
            <li className="rounded-md border border-border/60 p-2 text-sm" key={note.id}>
              <p className="whitespace-pre-wrap">{note.content}</p>
              <p className="mt-1 text-xs text-[var(--color-muted)]">
                {new Date(note.created_at).toLocaleString()}
              </p>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function TagsPanel({
  businessId,
  csrf,
  onError,
}: {
  businessId: string;
  csrf: string | null;
  onError: (message: string) => void;
}) {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState("");

  const current = useQuery({
    queryKey: ["business-tags", businessId],
    queryFn: () => api.get<Tag[]>(`/businesses/${businessId}/tags`),
  });

  const allTags = useQuery({
    queryKey: ["all-tags"],
    queryFn: () => api.get<Tag[]>("/businesses/tags"),
  });

  const names = (current.data ?? []).map((tag) => tag.name);

  const save = useMutation({
    mutationFn: (next: string[]) => api.put<Tag[]>(`/businesses/${businessId}/tags`, { names: next }, csrf),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["business-tags", businessId] }),
    onError: (caught) => onError(errorMessage(caught)),
  });

  function toggle(tag: string) {
    const next = names.includes(tag) ? names.filter((name) => name !== tag) : [...names, tag];
    save.mutate(next);
  }

  function addDraft() {
    const name = draft.trim();
    if (!name) return;
    setDraft("");
    save.mutate([...names, name]);
  }

  return (
    <Card>
      <CardTitle>Tags</CardTitle>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {(allTags.data ?? []).map((tag) => (
          <button
            className={`rounded-full border px-2.5 py-1 text-xs ${
              names.includes(tag.name)
                ? "border-[var(--color-primary)] bg-[var(--color-primary)] text-white"
                : "border-border text-[var(--color-muted)] hover:border-[var(--color-primary)]"
            }`}
            key={tag.id}
            onClick={() => toggle(tag.name)}
            type="button"
          >
            {tag.name}
          </button>
        ))}
        {!(allTags.data ?? []).length && (
          <span className="text-xs text-[var(--color-muted)]">No tags yet.</span>
        )}
      </div>
      <div className="mt-2 flex gap-2">
        <input
          className="flex-1 rounded-md border border-border bg-[var(--color-background)] px-2 py-1.5 text-sm"
          placeholder="New tag"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") addDraft();
          }}
        />
        <button className={buttonClass(false)} disabled={!draft.trim()} onClick={addDraft} type="button">
          Add
        </button>
      </div>
    </Card>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-[var(--color-muted)]">{label}</dt>
      <dd className="truncate">{value || "—"}</dd>
    </div>
  );
}

function buttonClass(active: boolean): string {
  return [
    "rounded-md border px-2.5 py-1.5 text-xs transition-colors disabled:opacity-50",
    active
      ? "border-[var(--color-primary)] bg-[var(--color-primary)] text-white"
      : "border-border text-[var(--color-muted)] hover:border-[var(--color-primary)]",
  ].join(" ");
}

function errorMessage(caught: unknown): string {
  if (caught instanceof Error) return caught.message;
  return "Something went wrong.";
}
