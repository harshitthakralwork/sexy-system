"use client";

import { useState, type FormEvent, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Database, ExternalLink, FileUp, Globe2, LoaderCircle, ShieldCheck, X } from "lucide-react";

import { Header } from "@/components/layout/header";
import { AppFooter } from "@/components/layout/app-footer";
import { useSession } from "@/components/providers/session-provider";
import { Card, EmptyState } from "@/components/ui/card";
import { api } from "@/lib/api/client";
import type {
  VerifiedProspectingLeadList,
  VerifiedProspectingRun,
} from "@/lib/api/types";

const ACTIVE_RUNS = new Set(["queued", "running"]);

export function VerifiedProspectingView() {
  const { csrf, user } = useSession();
  const queryClient = useQueryClient();
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const runs = useQuery({
    queryKey: ["verified-prospecting", "runs"],
    queryFn: () => api.get<VerifiedProspectingRun[]>("/verified-prospecting/runs"),
    refetchInterval: (query) =>
      (query.state.data ?? []).some((run) => ACTIVE_RUNS.has(run.status)) ? 2_500 : false,
  });

  const activeRunId = selectedRunId ?? runs.data?.[0]?.id ?? null;
  const selectedRun = runs.data?.find((run) => run.id === activeRunId) ?? null;
  const leads = useQuery({
    queryKey: ["verified-prospecting", "leads", activeRunId],
    queryFn: () => api.get<VerifiedProspectingLeadList>(`/verified-prospecting/runs/${activeRunId}/leads`),
    enabled: Boolean(activeRunId),
    refetchInterval: () => (selectedRun && ACTIVE_RUNS.has(selectedRun.status) ? 2_500 : false),
  });

  async function refresh() {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["verified-prospecting", "runs"] }),
      queryClient.invalidateQueries({ queryKey: ["verified-prospecting", "leads"] }),
    ]);
  }

  if (!user) return null;

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <Header title="Verified web prospects" subtitle="Separate public-web research. Your Local Business Finder data is untouched." />

      <main className="flex-1 overflow-y-auto p-4">
        <div className="grid gap-4 xl:grid-cols-[minmax(0,1.35fr)_minmax(320px,0.65fr)]">
          <Card className="border-cyan-300/20">
            <div className="flex gap-3">
              <div className="grid size-10 shrink-0 place-items-center rounded-2xl border border-cyan-300/25 bg-cyan-400/10 text-cyan-200">
                <Globe2 size={19} />
              </div>
              <div>
                <p className="text-sm font-semibold text-white">Public web discovery</p>
                <p className="mt-1 text-xs leading-5 text-white/60">
                  SearXNG finds public pages; each result is then read with the existing safe public-page fetcher. Login pages, CAPTCHAs and private sources are not used.
                </p>
              </div>
            </div>
            <WebRunForm
              csrf={csrf}
              onStarted={async (run) => {
                setSelectedRunId(run.id);
                setError(null);
                setNotice("Web prospecting run started. Results will appear as public pages are verified.");
                await refresh();
              }}
              onError={setError}
            />
          </Card>

          <Card>
            <div className="flex gap-3">
              <div className="grid size-10 shrink-0 place-items-center rounded-2xl border border-violet-300/25 bg-violet-400/10 text-violet-200">
                <Database size={19} />
              </div>
              <div>
                <p className="text-sm font-semibold text-white">Import an OSM city extract</p>
                <p className="mt-1 text-xs leading-5 text-white/60">
                  Upload a small <code>.osm</code> XML extract you already have. It adds a separate, evidence-backed run and never changes old business records.
                </p>
              </div>
            </div>
            <OsmImportForm
              csrf={csrf}
              onStarted={async (run) => {
                setSelectedRunId(run.id);
                setError(null);
                setNotice("OSM import started. The source file stays in memory only for this run.");
                await refresh();
              }}
              onError={setError}
            />
          </Card>
        </div>

        {(notice || error) && (
          <div className="mt-3 text-sm">
            {error && <p className="text-[var(--color-error)]">{error}</p>}
            {notice && <p className="text-cyan-100/80">{notice}</p>}
          </div>
        )}

        <div className="mt-4 grid gap-4 xl:grid-cols-[360px_minmax(0,1fr)]">
          <Card className="min-h-[320px]">
            <div className="flex items-center justify-between gap-2">
              <div>
                <p className="text-xs font-semibold uppercase tracking-wider text-white/50">Research runs</p>
                <p className="mt-1 text-xs text-white/55">Each run is isolated from the legacy finder.</p>
              </div>
              {runs.isFetching && <LoaderCircle className="animate-spin text-cyan-200" size={16} />}
            </div>
            {(runs.data ?? []).length === 0 && !runs.isPending ? (
              <div className="mt-4"><EmptyState title="No verified runs yet" description="Start a public-web run or import a small OSM XML extract." /></div>
            ) : (
              <div className="mt-4 space-y-2">
                {(runs.data ?? []).map((run) => (
                  <button
                    key={run.id}
                    type="button"
                    onClick={() => setSelectedRunId(run.id)}
                    className={`w-full rounded-2xl border p-3 text-left transition ${activeRunId === run.id ? "border-cyan-300/45 bg-cyan-300/10" : "border-white/10 bg-white/[0.025] hover:border-white/25"}`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <p className="text-sm font-semibold text-white">{run.niche}</p>
                        <p className="mt-0.5 text-xs text-white/55">{run.city} · {run.source_kind === "osm_extract" ? "OSM extract" : "Public web"}</p>
                      </div>
                      <RunBadge status={run.status} />
                    </div>
                    <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-white/10">
                      <div className="h-full rounded-full bg-cyan-300 transition-all" style={{ width: `${run.progress_percent}%` }} />
                    </div>
                    <p className="mt-2 text-xs text-white/55">{run.stage} · {run.saved_count} saved</p>
                  </button>
                ))}
              </div>
            )}
          </Card>

          <Card className="min-h-[420px]">
            {!selectedRun ? (
              <EmptyState title="Select a run" description="This results table only displays evidence created by the new Verified Web Prospecting flow." />
            ) : (
              <RunResults
                run={selectedRun}
                total={leads.data?.total ?? 0}
                leads={leads.data?.items ?? []}
                busy={leads.isPending || leads.isFetching}
                csrf={csrf}
                onCancelled={async () => {
                  setNotice("Cancellation requested. The runner will stop after its current page.");
                  await refresh();
                }}
                onError={setError}
              />
            )}
          </Card>
          <AppFooter />
        </div>
      </main>
    </div>
  );
}

function WebRunForm({ csrf, onStarted, onError }: { csrf: string | null; onStarted: (run: VerifiedProspectingRun) => Promise<void>; onError: (message: string) => void }) {
  const [niche, setNiche] = useState("");
  const [city, setCity] = useState("");
  const [maxCandidates, setMaxCandidates] = useState(20);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!niche.trim() || !city.trim()) return;
    setBusy(true);
    try {
      const run = await api.post<VerifiedProspectingRun>("/verified-prospecting/runs", { niche: niche.trim(), city: city.trim(), max_candidates: maxCandidates }, csrf, 20_000);
      await onStarted(run);
    } catch (caught) {
      onError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="mt-4 grid gap-3 sm:grid-cols-[1fr_1fr_110px_auto]" onSubmit={submit}>
      <Field label="Niche"><input value={niche} onChange={(event) => setNiche(event.target.value)} placeholder="e.g. wedding photographers" className={inputClass} /></Field>
      <Field label="City"><input value={city} onChange={(event) => setCity(event.target.value)} placeholder="e.g. Jaipur" className={inputClass} /></Field>
      <Field label="Pages"><input type="number" min={1} max={50} value={maxCandidates} onChange={(event) => setMaxCandidates(clamp(Number(event.target.value) || 20, 1, 50))} className={inputClass} /></Field>
      <button type="submit" disabled={busy || !niche.trim() || !city.trim()} className={primaryButton}>{busy ? "Starting…" : "Start run"}</button>
    </form>
  );
}

function OsmImportForm({ csrf, onStarted, onError }: { csrf: string | null; onStarted: (run: VerifiedProspectingRun) => Promise<void>; onError: (message: string) => void }) {
  const [city, setCity] = useState("");
  const [niche, setNiche] = useState("local businesses");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!city.trim() || !file) return;
    const form = new FormData();
    form.set("city", city.trim());
    form.set("niche", niche.trim() || "local businesses");
    form.set("file", file);
    setBusy(true);
    try {
      const run = await api.upload<VerifiedProspectingRun>("/verified-prospecting/osm-import", form, csrf, 30_000);
      await onStarted(run);
    } catch (caught) {
      onError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="mt-4 grid gap-3 sm:grid-cols-2" onSubmit={submit}>
      <Field label="City"><input value={city} onChange={(event) => setCity(event.target.value)} placeholder="e.g. Jaipur" className={inputClass} /></Field>
      <Field label="Niche label"><input value={niche} onChange={(event) => setNiche(event.target.value)} className={inputClass} /></Field>
      <label className="sm:col-span-2">
        <span className="mb-1 block text-xs font-medium text-white/65">OSM XML file (max 25 MB)</span>
        <span className="flex cursor-pointer items-center gap-2 rounded-xl border border-dashed border-white/20 bg-white/[0.025] px-3 py-2.5 text-sm text-white/65 hover:border-violet-300/45">
          <FileUp size={16} className="text-violet-200" />
          {file?.name ?? "Choose a .osm file"}
          <input type="file" accept=".osm,application/xml,text/xml" className="sr-only" onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
        </span>
      </label>
      <button type="submit" disabled={busy || !city.trim() || !file} className={`${primaryButton} justify-self-start`}>{busy ? "Importing…" : "Import extract"}</button>
    </form>
  );
}

function RunResults({ run, leads, total, busy, csrf, onCancelled, onError }: { run: VerifiedProspectingRun; leads: VerifiedProspectingLeadList["items"]; total: number; busy: boolean; csrf: string | null; onCancelled: () => Promise<void>; onError: (message: string) => void }) {
  const [cancelling, setCancelling] = useState(false);
  const active = ACTIVE_RUNS.has(run.status);

  async function cancel() {
    setCancelling(true);
    try {
      await api.post<VerifiedProspectingRun>(`/verified-prospecting/runs/${run.id}/cancel`, undefined, csrf);
      await onCancelled();
    } catch (caught) {
      onError(errorMessage(caught));
    } finally {
      setCancelling(false);
    }
  }

  return (
    <>
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-white/10 pb-4">
        <div>
          <div className="flex items-center gap-2"><p className="text-lg font-semibold text-white">{run.niche} in {run.city}</p><RunBadge status={run.status} /></div>
          <p className="mt-1 text-sm text-white/60">{run.stage} · {total} verified entries · {run.candidate_count} public candidates checked</p>
          {run.error_summary && <p className="mt-1 text-xs text-amber-200">{run.error_summary}</p>}
        </div>
        {active && <button type="button" onClick={cancel} disabled={cancelling || run.cancellation_requested} className="inline-flex items-center gap-1.5 rounded-full border border-rose-300/35 px-3 py-2 text-xs font-semibold text-rose-200 hover:bg-rose-400/10 disabled:opacity-50"><X size={14} />{cancelling || run.cancellation_requested ? "Cancelling…" : "Cancel run"}</button>}
      </div>
      <div className="mt-4 h-2 overflow-hidden rounded-full bg-white/10"><div className="h-full rounded-full bg-gradient-to-r from-cyan-300 to-violet-300 transition-all" style={{ width: `${run.progress_percent}%` }} /></div>
      <div className="mt-2 flex justify-between text-xs text-white/55"><span>{run.progress_percent}% complete</span><span>{run.saved_count} saved · {run.failed_count} unreadable</span></div>
      {busy && leads.length === 0 ? <p className="mt-8 text-center text-sm text-white/55">Loading evidence…</p> : leads.length === 0 ? <div className="mt-5"><EmptyState title="No verified prospects yet" description={active ? "The run is still checking public pages. This list updates automatically." : "No usable public business evidence was found for this run."} /></div> : (
        <div className="mt-5 overflow-x-auto rounded-2xl border border-white/10">
          <table className="w-full min-w-[920px] text-sm">
            <thead><tr className="border-b border-white/10 bg-white/[0.03] text-left text-xs uppercase tracking-wide text-white/50"><th className="px-3 py-3">Prospect</th><th className="px-3 py-3">Potential</th><th className="px-3 py-3">Public contact</th><th className="px-3 py-3">Website</th><th className="px-3 py-3">Evidence</th></tr></thead>
            <tbody>{leads.map((lead) => <tr key={lead.id} className="border-b border-white/5 align-top hover:bg-white/[0.025]"><td className="px-3 py-3"><p className="font-medium text-white">{lead.name}</p><p className="mt-1 max-w-[250px] text-xs text-white/50">{lead.address ?? lead.city}</p></td><td className="px-3 py-3"><span className="rounded-full bg-cyan-300/10 px-2 py-1 text-xs font-semibold text-cyan-100">{lead.potential_score}/100</span><p className="mt-2 max-w-44 text-xs leading-5 text-white/55">{lead.score_reasons.join(" · ")}</p></td><td className="px-3 py-3 text-xs leading-5 text-white/70">{lead.public_phone && <p>{lead.public_phone}</p>}{lead.public_email && <p className="break-all">{lead.public_email}</p>}{!lead.public_phone && !lead.public_email && "Not published"}</td><td className="px-3 py-3 text-xs">{lead.website_url ? <a className="inline-flex items-center gap-1 text-cyan-200 hover:text-cyan-100" href={safeHref(lead.website_url)} target="_blank" rel="noreferrer">Open website <ExternalLink size={12} /></a> : <span className="text-white/45">Unknown</span>}</td><td className="px-3 py-3"><a className="inline-flex items-center gap-1 text-xs text-white/65 hover:text-white" href={safeHref(lead.source_url)} target="_blank" rel="noreferrer">Source <ExternalLink size={12} /></a></td></tr>)}</tbody>
          </table>
        </div>
      )}
      <p className="mt-4 flex items-center gap-2 text-xs leading-5 text-white/45"><ShieldCheck size={14} className="shrink-0 text-cyan-200" />Contact fields are only shown when they were publicly present in the source evidence; missing data is not inferred.</p>
    </>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) { return <label><span className="mb-1 block text-xs font-medium text-white/65">{label}</span>{children}</label>; }
function RunBadge({ status }: { status: VerifiedProspectingRun["status"] }) { const tone = status === "completed" ? "bg-emerald-300/10 text-emerald-200" : status === "failed" ? "bg-rose-300/10 text-rose-200" : status === "partial" ? "bg-amber-300/10 text-amber-100" : status === "cancelled" ? "bg-white/10 text-white/60" : "bg-cyan-300/10 text-cyan-100"; return <span className={`rounded-full px-2 py-1 text-[11px] font-semibold capitalize ${tone}`}>{status}</span>; }
function safeHref(url: string): string { return /^https?:\/\//i.test(url) ? url : "#"; }
function clamp(value: number, min: number, max: number): number { return Math.min(max, Math.max(min, value)); }
function errorMessage(caught: unknown): string { return caught instanceof Error ? caught.message : "The request could not be completed."; }

const inputClass = "w-full rounded-xl border border-white/15 bg-black/20 px-3 py-2.5 text-sm text-white outline-none transition placeholder:text-white/35 focus:border-cyan-300/55 focus:ring-2 focus:ring-cyan-300/15";
const primaryButton = "self-end rounded-xl border border-cyan-200/35 bg-cyan-300/15 px-4 py-2.5 text-sm font-semibold text-cyan-50 shadow-[0_0_18px_rgba(34,211,238,0.12)] transition hover:bg-cyan-300/25 disabled:cursor-not-allowed disabled:opacity-45";
