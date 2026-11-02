"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { Header } from "@/components/layout/header";
import { Card, CardTitle, EmptyState } from "@/components/ui/card";
import { useSession } from "@/components/providers/session-provider";
import { api } from "@/lib/api/client";
import type {
  StartupDetail,
  StartupList,
  Watchlist,
} from "@/lib/api/types";

const CLASSIFICATION_LABEL: Record<string, string> = {
  verified: "Verified",
  founder_reported: "Founder-reported",
  estimated: "Estimated",
  not_available: "Not available",
};

export function StartupProfile() {
  const { id } = useParams<{ id: string }>();
  if (!id) return null;
  return <Profile id={id} />;
}

function Profile({ id }: { id: string }) {
  const { csrf, user } = useSession();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);

  const detail = useQuery({
    queryKey: ["startup", id],
    queryFn: () => api.get<StartupDetail>(`/startups/${id}`),
  });

  const startup = detail.data;

  async function invalidate() {
    await queryClient.invalidateQueries({ queryKey: ["startup", id] });
  }

  if (!user) return null;

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <Header
        title={startup?.name ?? "Startup"}
        subtitle={
          startup
            ? `${startup.industry ?? "no industry"} · ${startup.funding_stage ?? "no stage"}`
            : "Loading profile…"
        }
      />

      <main className="flex-1 space-y-4 overflow-y-auto p-4">
        {detail.isError && (
          <p className="text-sm text-[var(--color-error)]">
            Profile could not be loaded: {errorMessage(detail.error)}
          </p>
        )}

        {!detail.isPending && !startup && (
          <EmptyState
            title="Not found"
            description="This startup does not exist or is not yours."
            action={
              <Link className={buttonClass(false)} href="/startups">
                Back to startups
              </Link>
            }
          />
        )}

        {error && (
          <div className="rounded-md border border-border bg-[var(--color-surface)] p-3 text-sm">
            <p className="text-[var(--color-error)]">{error}</p>
          </div>
        )}

        {startup && (
          <>
            <Overview
              startup={startup}
              csrf={csrf}
              onChanged={invalidate}
              onError={setError}
            />

            <div className="grid gap-4 lg:grid-cols-2">
              <RevenuePanel startupId={id} revenue={startup.revenue} csrf={csrf} onChanged={invalidate} onError={setError} />
              <CompetitorsPanel startupId={id} competitors={startup.competitors} csrf={csrf} onChanged={invalidate} onError={setError} />
            </div>

            <div className="grid gap-4 lg:grid-cols-2">
              <FoundersPanel startupId={id} founders={startup.founders} csrf={csrf} onChanged={invalidate} onError={setError} />
              <ProductsPanel startupId={id} products={startup.products} csrf={csrf} onChanged={invalidate} onError={setError} />
            </div>

            <ResearchPanel startupId={id} research={startup.research} csrf={csrf} onChanged={invalidate} onError={setError} />
            <WatchlistsPanel startupId={id} names={startup.watchlists} csrf={csrf} onChanged={invalidate} onError={setError} />
          </>
        )}
      </main>
    </div>
  );
}

function Overview({
  startup,
  csrf,
  onChanged,
  onError,
}: {
  startup: StartupDetail;
  csrf: string | null;
  onChanged: () => Promise<void>;
  onError: (message: string) => void;
}) {
  const [status, setStatus] = useState(startup.status);
  const [busy, setBusy] = useState(false);

  async function saveStatus() {
    setBusy(true);
    try {
      await api.patch(`/startups/${startup.id}`, { status }, csrf);
      await onChanged();
    } catch (caught) {
      onError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-base font-semibold">{startup.name}</h2>
          {startup.description && (
            <p className="mt-1 text-sm text-[var(--color-muted)]">{startup.description}</p>
          )}
          <dl className="mt-3 grid gap-x-6 gap-y-1 text-sm sm:grid-cols-2">
            <Field label="Website" value={startup.website_url ?? "none reported"} />
            <Field label="Domain" value={startup.normalized_domain ?? "—"} />
            <Field label="Industry" value={startup.industry ?? "—"} />
            <Field label="Country" value={startup.country ?? "—"} />
            <Field label="City" value={startup.city ?? "—"} />
            <Field label="Funding stage" value={startup.funding_stage ?? "—"} />
            <Field
              label="Founded"
              value={startup.founding_date ? new Date(startup.founding_date).toLocaleDateString() : "—"}
            />
            <Field label="Source" value={startup.source_slug ?? "manual"} />
            <Field
              label="Last researched"
              value={startup.last_researched_at ? new Date(startup.last_researched_at).toLocaleDateString() : "never"}
            />
          </dl>
          {startup.source_url && (
            <a
              className="mt-2 inline-block text-xs text-[var(--color-primary)] underline-offset-2 hover:underline"
              href={startup.source_url}
              target="_blank"
              rel="noreferrer"
            >
              {startup.source_url}
            </a>
          )}
        </div>
        <div className="flex items-end gap-2">
          <label className="text-sm">
            <span className="text-[var(--color-muted)]">Status</span>
            <select
              className="mt-1 block w-32 rounded-md border border-border bg-[var(--color-background)] px-2 py-1.5"
              value={status}
              onChange={(event) => setStatus(event.target.value)}
            >
              <option value="unknown">unknown</option>
              <option value="active">active</option>
              <option value="acquired">acquired</option>
              <option value="shutdown">shutdown</option>
            </select>
          </label>
          <button className={buttonClass(false)} disabled={busy} onClick={saveStatus} type="button">
            {busy ? "Saving…" : "Save"}
          </button>
        </div>
      </div>
    </Card>
  );
}

function FoundersPanel({
  startupId,
  founders,
  csrf,
  onChanged,
  onError,
}: {
  startupId: string;
  founders: StartupDetail["founders"];
  csrf: string | null;
  onChanged: () => Promise<void>;
  onError: (message: string) => void;
}) {
  const [name, setName] = useState("");
  const [role, setRole] = useState("");
  const [busy, setBusy] = useState(false);

  async function add() {
    if (!name.trim()) return;
    setBusy(true);
    try {
      await api.post(
        `/startups/${startupId}/founders`,
        { name: name.trim(), role: role.trim() || null },
        csrf,
      );
      setName("");
      setRole("");
      await onChanged();
    } catch (caught) {
      onError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  async function remove(founderId: string) {
    try {
      await api.delete(`/startups/${startupId}/founders/${founderId}`, csrf);
      await onChanged();
    } catch (caught) {
      onError(errorMessage(caught));
    }
  }

  return (
    <Card>
      <CardTitle>Founders</CardTitle>
      <ul className="mt-2 space-y-1 text-sm">
        {founders.length === 0 && <li className="text-[var(--color-muted)]">No founders recorded.</li>}
        {founders.map((founder) => (
          <li key={founder.id} className="flex items-center justify-between gap-3">
            <span>
              <span className="font-medium">{founder.name}</span>
              {founder.role && <span className="ml-2 text-[var(--color-muted)]">{founder.role}</span>}
            </span>
            <button className={buttonClass(false)} onClick={() => remove(founder.id)} type="button">
              Remove
            </button>
          </li>
        ))}
      </ul>
      <div className="mt-3 flex gap-2">
        <input
          className="min-w-0 flex-1 rounded-md border border-border bg-[var(--color-background)] px-2 py-1.5 text-sm"
          placeholder="Name"
          value={name}
          onChange={(event) => setName(event.target.value)}
        />
        <input
          className="w-32 rounded-md border border-border bg-[var(--color-background)] px-2 py-1.5 text-sm"
          placeholder="Role"
          value={role}
          onChange={(event) => setRole(event.target.value)}
        />
        <button className={buttonClass(false)} disabled={busy || !name.trim()} onClick={add} type="button">
          Add
        </button>
      </div>
    </Card>
  );
}

function ProductsPanel({
  startupId,
  products,
  csrf,
  onChanged,
  onError,
}: {
  startupId: string;
  products: StartupDetail["products"];
  csrf: string | null;
  onChanged: () => Promise<void>;
  onError: (message: string) => void;
}) {
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);

  async function add() {
    if (!name.trim()) return;
    setBusy(true);
    try {
      await api.post(`/startups/${startupId}/products`, { name: name.trim() }, csrf);
      setName("");
      await onChanged();
    } catch (caught) {
      onError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  async function remove(productId: string) {
    try {
      await api.delete(`/startups/${startupId}/products/${productId}`, csrf);
      await onChanged();
    } catch (caught) {
      onError(errorMessage(caught));
    }
  }

  return (
    <Card>
      <CardTitle>Products</CardTitle>
      <ul className="mt-2 space-y-1 text-sm">
        {products.length === 0 && <li className="text-[var(--color-muted)]">No products recorded.</li>}
        {products.map((product) => (
          <li key={product.id} className="flex items-center justify-between gap-3">
            <span className="font-medium">{product.name}</span>
            <button className={buttonClass(false)} onClick={() => remove(product.id)} type="button">
              Remove
            </button>
          </li>
        ))}
      </ul>
      <div className="mt-3 flex gap-2">
        <input
          className="min-w-0 flex-1 rounded-md border border-border bg-[var(--color-background)] px-2 py-1.5 text-sm"
          placeholder="Product name"
          value={name}
          onChange={(event) => setName(event.target.value)}
        />
        <button className={buttonClass(false)} disabled={busy || !name.trim()} onClick={add} type="button">
          Add
        </button>
      </div>
    </Card>
  );
}

function RevenuePanel({
  startupId,
  revenue,
  csrf,
  onChanged,
  onError,
}: {
  startupId: string;
  revenue: StartupDetail["revenue"];
  csrf: string | null;
  onChanged: () => Promise<void>;
  onError: (message: string) => void;
}) {
  const [classification, setClassification] = useState("estimated");
  const [amount, setAmount] = useState("");
  const [methodology, setMethodology] = useState("");
  const [busy, setBusy] = useState(false);

  async function add() {
    setBusy(true);
    try {
      await api.post(
        `/startups/${startupId}/revenue`,
        {
          classification,
          amount: amount.trim() ? Number(amount.trim()) : null,
          methodology: methodology.trim() || null,
        },
        csrf,
      );
      setAmount("");
      setMethodology("");
      await onChanged();
    } catch (caught) {
      onError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  async function remove(revenueId: string) {
    try {
      await api.delete(`/startups/${startupId}/revenue/${revenueId}`, csrf);
      await onChanged();
    } catch (caught) {
      onError(errorMessage(caught));
    }
  }

  return (
    <Card>
      <CardTitle>Revenue evidence</CardTitle>
      <ul className="mt-2 space-y-1 text-sm">
        {revenue.length === 0 && (
          <li className="text-[var(--color-muted)]">No revenue observations recorded.</li>
        )}
        {revenue.map((record) => (
          <li key={record.id} className="flex items-center justify-between gap-3">
            <span>
              <span className="font-medium">
                {record.amount != null ? `${record.amount.toLocaleString()} ${record.currency ?? ""}` : "—"}
              </span>
              <span className="ml-2 rounded bg-[var(--color-surface-elevated)] px-1.5 py-0.5 text-xs">
                {CLASSIFICATION_LABEL[record.classification] ?? record.classification}
              </span>
            </span>
            <button className={buttonClass(false)} onClick={() => remove(record.id)} type="button">
              Remove
            </button>
          </li>
        ))}
      </ul>
      <div className="mt-3 flex flex-wrap gap-2">
        <select
          className="w-40 rounded-md border border-border bg-[var(--color-background)] px-2 py-1.5 text-sm"
          value={classification}
          onChange={(event) => setClassification(event.target.value)}
        >
          <option value="verified">Verified</option>
          <option value="founder_reported">Founder-reported</option>
          <option value="estimated">Estimated</option>
          <option value="not_available">Not available</option>
        </select>
        {classification !== "not_available" && (
          <input
            className="w-32 rounded-md border border-border bg-[var(--color-background)] px-2 py-1.5 text-sm"
            placeholder="Amount"
            inputMode="numeric"
            value={amount}
            onChange={(event) => setAmount(event.target.value)}
          />
        )}
        {classification === "estimated" && (
          <input
            className="min-w-40 flex-1 rounded-md border border-border bg-[var(--color-background)] px-2 py-1.5 text-sm"
            placeholder="Methodology (required for estimates)"
            value={methodology}
            onChange={(event) => setMethodology(event.target.value)}
          />
        )}
        <button className={buttonClass(false)} disabled={busy} onClick={add} type="button">
          Add
        </button>
      </div>
    </Card>
  );
}

function CompetitorsPanel({
  startupId,
  competitors,
  csrf,
  onChanged,
  onError,
}: {
  startupId: string;
  competitors: StartupDetail["competitors"];
  csrf: string | null;
  onChanged: () => Promise<void>;
  onError: (message: string) => void;
}) {
  const all = useQuery({
    queryKey: ["startups"],
    queryFn: () => api.get<StartupList>("/startups?limit=500"),
  });

  const [competitorId, setCompetitorId] = useState("");
  const [busy, setBusy] = useState(false);

  const candidates = (all.data?.items ?? []).filter((item) => item.id !== startupId);
  const nameById = new Map(candidates.map((item) => [item.id, item.name]));

  async function add() {
    if (!competitorId) return;
    setBusy(true);
    try {
      await api.post(
        `/startups/${startupId}/competitors`,
        { competitor_startup_id: competitorId, relationship_type: "direct" },
        csrf,
      );
      setCompetitorId("");
      await onChanged();
    } catch (caught) {
      onError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  async function remove(competitorEdgeId: string) {
    try {
      await api.delete(`/startups/${startupId}/competitors/${competitorEdgeId}`, csrf);
      await onChanged();
    } catch (caught) {
      onError(errorMessage(caught));
    }
  }

  return (
    <Card>
      <CardTitle>Competitors</CardTitle>
      <ul className="mt-2 space-y-1 text-sm">
        {competitors.length === 0 && <li className="text-[var(--color-muted)]">No competitors linked.</li>}
        {competitors.map((edge) => (
          <li key={edge.id} className="flex items-center justify-between gap-3">
            <span>{nameById.get(edge.competitor_startup_id) ?? edge.competitor_startup_id}</span>
            <button className={buttonClass(false)} onClick={() => remove(edge.id)} type="button">
              Remove
            </button>
          </li>
        ))}
      </ul>
      <div className="mt-3 flex gap-2">
        <select
          className="min-w-0 flex-1 rounded-md border border-border bg-[var(--color-background)] px-2 py-1.5 text-sm"
          value={competitorId}
          onChange={(event) => setCompetitorId(event.target.value)}
        >
          <option value="">Pick a competitor…</option>
          {candidates.map((candidate) => (
            <option key={candidate.id} value={candidate.id}>
              {candidate.name}
            </option>
          ))}
        </select>
        <button className={buttonClass(false)} disabled={busy || !competitorId} onClick={add} type="button">
          Link
        </button>
      </div>
    </Card>
  );
}

function ResearchPanel({
  startupId,
  research,
  csrf,
  onChanged,
  onError,
}: {
  startupId: string;
  research: StartupDetail["research"];
  csrf: string | null;
  onChanged: () => Promise<void>;
  onError: (message: string) => void;
}) {
  const [type, setType] = useState("competitive_scan");
  const [summary, setSummary] = useState("");
  const [busy, setBusy] = useState(false);

  async function add() {
    if (!summary.trim()) return;
    setBusy(true);
    try {
      await api.post(
        `/startups/${startupId}/research`,
        { research_type: type, summary: summary.trim(), findings: {}, source_references: {} },
        csrf,
      );
      setSummary("");
      await onChanged();
    } catch (caught) {
      onError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  async function remove(researchId: string) {
    try {
      await api.delete(`/startups/${startupId}/research/${researchId}`, csrf);
      await onChanged();
    } catch (caught) {
      onError(errorMessage(caught));
    }
  }

  return (
    <Card>
      <CardTitle>Research notes</CardTitle>
      <ul className="mt-2 space-y-2 text-sm">
        {research.length === 0 && <li className="text-[var(--color-muted)]">No research recorded.</li>}
        {research.map((record) => (
          <li key={record.id} className="flex items-start justify-between gap-3 rounded-md border border-border/60 p-2">
            <div className="min-w-0">
              <span className="text-xs font-semibold uppercase tracking-wide text-[var(--color-muted)]">
                {record.research_type}
              </span>
              <p className="mt-0.5">{record.summary}</p>
            </div>
            <button className={buttonClass(false)} onClick={() => remove(record.id)} type="button">
              Remove
            </button>
          </li>
        ))}
      </ul>
      <div className="mt-3 flex gap-2">
        <select
          className="w-44 rounded-md border border-border bg-[var(--color-background)] px-2 py-1.5 text-sm"
          value={type}
          onChange={(event) => setType(event.target.value)}
        >
          <option value="competitive_scan">Competitive scan</option>
          <option value="revenue_analysis">Revenue analysis</option>
          <option value="market_position">Market position</option>
        </select>
        <input
          className="min-w-0 flex-1 rounded-md border border-border bg-[var(--color-background)] px-2 py-1.5 text-sm"
          placeholder="Summary"
          value={summary}
          onChange={(event) => setSummary(event.target.value)}
        />
        <button className={buttonClass(false)} disabled={busy || !summary.trim()} onClick={add} type="button">
          Add
        </button>
      </div>
    </Card>
  );
}

function WatchlistsPanel({
  startupId,
  names,
  csrf,
  onChanged,
  onError,
}: {
  startupId: string;
  names: string[];
  csrf: string | null;
  onChanged: () => Promise<void>;
  onError: (message: string) => void;
}) {
  const watchlists = useQuery({
    queryKey: ["watchlists"],
    queryFn: () => api.get<Watchlist[]>("/startups/watchlists"),
  });
  const [watchlistId, setWatchlistId] = useState("");
  const [busy, setBusy] = useState(false);

  async function add() {
    if (!watchlistId) return;
    setBusy(true);
    try {
      await api.post(`/startups/watchlists/${watchlistId}/items`, { startup_id: startupId }, csrf);
      setWatchlistId("");
      await onChanged();
    } catch (caught) {
      onError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardTitle>Watchlists</CardTitle>
      <p className="mt-1 text-xs text-[var(--color-muted)]">
        {names.length ? `On: ${names.join(", ")}` : "Not on any watchlist."}
      </p>
      <div className="mt-3 flex gap-2">
        <select
          className="min-w-0 flex-1 rounded-md border border-border bg-[var(--color-background)] px-2 py-1.5 text-sm"
          value={watchlistId}
          onChange={(event) => setWatchlistId(event.target.value)}
        >
          <option value="">Add to a watchlist…</option>
          {(watchlists.data ?? []).map((watchlist) => (
            <option key={watchlist.id} value={watchlist.id}>
              {watchlist.name}
            </option>
          ))}
        </select>
        <button className={buttonClass(false)} disabled={busy || !watchlistId} onClick={add} type="button">
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
      <dd>{value}</dd>
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
