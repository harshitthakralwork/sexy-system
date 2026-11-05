"use client";

import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { Header } from "@/components/layout/header";
import { EmptyState } from "@/components/ui/card";
import { useSession } from "@/components/providers/session-provider";
import { api } from "@/lib/api/client";
import type {
  ExportCatalogue,
  ExportJob,
  ExportJobList,
  ExportModule,
  ImportJob,
  ImportJobList,
  ImportVocabulary,
} from "@/lib/api/types";

const FILTER_LABELS: Record<string, string> = {
  query: "Search text",
  city: "City",
  country: "Country",
  category: "Category",
  website_status: "Website status",
  has_phone: "Has a phone number",
  shortlisted_only: "Shortlisted only",
  platform: "Platform",
  content_type: "Content type",
  track_type: "Track type",
  classification: "Classification",
  needs_review: "Needs review",
  saved_only: "Saved only",
  min_confidence: "Minimum confidence",
  industry: "Industry",
  funding_stage: "Funding stage",
  status: "Status",
};

const STRATEGY_COPY: Record<string, string> = {
  skip: "Skip rows that match a record you already have",
  merge: "Fill the empty fields of a matching record",
  create: "Create a second record even when one matches",
};

const STATUS_COPY: Record<string, string> = {
  queued: "Queued",
  running: "Running",
  completed: "Completed",
  failed: "Failed",
  pending: "Awaiting a mapping",
};

function statusClass(status: string): string {
  if (status === "completed") return "text-[var(--color-success)]";
  if (status === "failed") return "text-[var(--color-error)]";
  if (status === "running" || status === "queued") return "text-[var(--color-muted)]";
  return "text-[var(--color-muted)]";
}

function buttonClass(active: boolean): string {
  return [
    "rounded-full border px-2.5 py-1 text-xs font-medium transition-all disabled:opacity-40 cursor-pointer",
    active
      ? "border-cyan-400/40 bg-cyan-500/15 text-cyan-200 shadow-[0_0_10px_rgba(0,212,255,0.12)]"
      : "border-white/[0.08] bg-white/[0.03] text-white/50 hover:border-white/20 hover:text-white/80",
  ].join(" ");
}

function primaryBtnClass(): string {
  return "refraction-glass-btn rounded-full px-5 py-2 text-sm font-bold text-white shadow-[0_0_22px_rgba(0,212,255,0.18)] disabled:opacity-40 cursor-pointer";
}

function fieldClass(): string {
  return "refraction-glass-input mt-1 w-full rounded-[10px] px-2.5 py-1.5 text-xs";
}

function whenSet(value: string | null | undefined): string {
  return value ? new Date(value).toLocaleString() : "never";
}

export function DataView() {
  const { user } = useSession();
  if (!user) return null;

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <Header
        title="Workspace settings"
        subtitle="Export, import, and control the data in this workspace"
      />
      <main className="flex-1 space-y-6 overflow-y-auto p-4">
        <ExportPanel />
        <ImportPanel />
      </main>
    </div>
  );
}

// --- Export ------------------------------------------------------------------

function ExportPanel() {
  const { csrf } = useSession();
  const queryClient = useQueryClient();
  const [moduleKey, setModuleKey] = useState<string>("");
  const [format, setFormat] = useState<string>("csv");
  const [filters, setFilters] = useState<Record<string, string>>({});
  // null means "every column". An empty array would be sent as no selection,
  // which the API reads as every column too — so clearing the last column
  // returns to the same state rather than claiming to export nothing.
  const [fields, setFields] = useState<string[] | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const catalogue = useQuery({
    queryKey: ["exports", "catalogue"],
    queryFn: () => api.get<ExportCatalogue>("/exports/catalogue"),
  });

  const modules = catalogue.data?.modules ?? [];
  const selected: ExportModule | undefined =
    modules.find((entry) => entry.key === moduleKey) ?? modules[0];

  const jobs = useQuery({
    queryKey: ["exports"],
    queryFn: () => api.get<ExportJobList>("/exports"),
    refetchInterval: (query) => {
      const items = query.state.data?.items ?? [];
      return items.some((job) => job.status === "queued" || job.status === "running")
        ? 1500
        : false;
    },
    // A run finishes whether or not this tab is on screen. Without this the
    // page would keep saying "Queued" to an operator looking at another tab.
    refetchIntervalInBackground: true,
  });

  const create = useMutation({
    mutationFn: () =>
      api.post<ExportJob>(
        "/exports",
        {
          module: selected?.key ?? moduleKey,
          format,
          filters: Object.fromEntries(
            Object.entries(filters).filter(([, value]) => value !== ""),
          ),
          selected_fields: fields ?? undefined,
        },
        csrf,
      ),
    onSuccess: async () => {
      setMessage("Queued. The file appears when the run finishes.");
      await queryClient.invalidateQueries({ queryKey: ["exports"] });
    },
    onError: (caught) => setMessage(caught instanceof Error ? caught.message : "Export failed"),
  });

  const remove = useMutation({
    mutationFn: (id: string) => api.delete<ExportJob>(`/exports/${id}`, csrf),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["exports"] });
    },
    onError: (caught) => setMessage(caught instanceof Error ? caught.message : "Delete failed"),
  });

  const pickModule = (key: string) => {
    setModuleKey(key);
    setFilters({});
    setFields(null);
  };

  const toggleField = (column: string) => {
    if (!selected) return;
    const all = selected.columns;
    if (fields === null) {
      setFields(all.filter((entry) => entry !== column));
      return;
    }
    const next = fields.includes(column)
      ? fields.filter((entry) => entry !== column)
      : [...fields, column];
    setFields(next.length === 0 ? null : next);
  };

  return (
    <div className="refraction-glass-card rounded-[20px] p-5 space-y-4">
      <div>
        <h2 className="text-sm font-medium">Export</h2>
        <p className="text-xs text-[var(--color-muted)]">
          A file of what this account holds, produced in the background. Files expire;
          the history of what was exported stays.
        </p>
      </div>

      {catalogue.isError && (
        <p className="text-sm text-[var(--color-error)]">
          {catalogue.error instanceof Error ? catalogue.error.message : "Catalogue failed to load"}
        </p>
      )}

      {catalogue.isPending && !catalogue.isError && (
        <p className="text-xs text-[var(--color-muted)]">Reading the catalogue…</p>
      )}

      {selected && (
        <div className="grid gap-3 lg:grid-cols-2">
          <label className="block text-xs">
            <span className="text-[var(--color-muted)]">What to export</span>
            <select
              className={fieldClass()}
              value={selected.key}
              onChange={(event) => pickModule(event.target.value)}
            >
              {modules.map((entry) => (
                <option key={entry.key} value={entry.key}>
                  {entry.label}
                </option>
              ))}
            </select>
          </label>

          <label className="block text-xs">
            <span className="text-[var(--color-muted)]">Format</span>
            <select
              className={fieldClass()}
              value={format}
              onChange={(event) => setFormat(event.target.value)}
            >
              {(catalogue.data?.formats ?? ["csv"]).map((entry) => (
                <option key={entry} value={entry}>
                  {entry.toUpperCase()}
                </option>
              ))}
            </select>
          </label>
        </div>
      )}

      {selected && selected.filters.length > 0 && (
        <div>
          <p className="text-xs font-medium text-[var(--color-muted)]">Filters</p>
          <p className="text-xs text-[var(--color-muted)]">
            Leave a filter empty to include every record.
          </p>
          <div className="mt-2 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {selected.filters.map((key) => {
              const isBoolean = selected.boolean_filters.includes(key);
              const isNumeric = selected.numeric_filters.includes(key);
              return (
                <label key={key} className="block text-xs">
                  <span className="text-[var(--color-muted)]">
                    {FILTER_LABELS[key] ?? key.replace(/_/g, " ")}
                  </span>
                  {isBoolean ? (
                    <select
                      className={fieldClass()}
                      value={filters[key] ?? ""}
                      onChange={(event) =>
                        setFilters((current) => ({ ...current, [key]: event.target.value }))
                      }
                    >
                      <option value="">Any</option>
                      <option value="true">Yes</option>
                      <option value="false">No</option>
                    </select>
                  ) : (
                    <input
                      className={fieldClass()}
                      type={isNumeric ? "number" : "text"}
                      step={isNumeric ? "0.05" : undefined}
                      value={filters[key] ?? ""}
                      onChange={(event) =>
                        setFilters((current) => ({ ...current, [key]: event.target.value }))
                      }
                    />
                  )}
                </label>
              );
            })}
          </div>
        </div>
      )}

      {selected && selected.columns.length > 0 && (
        <div>
          <p className="text-xs font-medium text-[var(--color-muted)]">Columns</p>
          <p className="text-xs text-[var(--color-muted)]">
            Every column is included unless you clear it.
          </p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {selected.columns.map((column) => {
              const on = fields === null || fields.includes(column);
              return (
                <button
                  key={column}
                  className={buttonClass(on)}
                  type="button"
                  onClick={() => toggleField(column)}
                >
                  {column}
                </button>
              );
            })}
          </div>
          {fields !== null && (
            <button
              className="mt-2 text-xs text-[var(--color-muted)] underline"
              type="button"
              onClick={() => setFields(null)}
            >
              Include every column again
            </button>
          )}
        </div>
      )}

      <div className="flex items-center gap-2">
        <button
          className={primaryBtnClass()}
          disabled={create.isPending || !selected}
          type="button"
          onClick={() => create.mutate()}
        >
          {create.isPending ? "Queueing…" : "Create export"}
        </button>
        {message && <p className="text-xs text-[var(--color-muted)]">{message}</p>}
      </div>

      <div className="border-t border-white/[0.06] pt-3">
        <p className="text-xs font-medium text-[var(--color-muted)]">Recent exports</p>
        {jobs.isError && (
          <p className="mt-1 text-xs text-[var(--color-error)]">
            {jobs.error instanceof Error ? jobs.error.message : "Exports failed to load"}
          </p>
        )}
        {!jobs.isError && jobs.data && jobs.data.items.length === 0 && (
          <p className="mt-1 text-xs text-[var(--color-muted)]">Nothing exported yet.</p>
        )}
        <ul className="mt-2 space-y-2">
          {jobs.data?.items.map((job) => (
            <ExportRow key={job.id} job={job} onDelete={() => remove.mutate(job.id)} />
          ))}
        </ul>
      </div>
    </div>
  );
}

function ExportRow({ job, onDelete }: { job: ExportJob; onDelete: () => void }) {
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  const save = async () => {
    setBusy(true);
    setNote(null);
    try {
      const blob = await api.download(`/exports/${job.id}/download`);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `sparkxflow-${job.module}-${job.id}.${job.export_format}`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
    } catch (caught) {
      setNote(caught instanceof Error ? caught.message : "Download failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <li className="rounded-[14px] border border-white/[0.07] bg-white/[0.03] p-3 text-xs">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span>
          {job.module} · {job.export_format.toUpperCase()} ·{" "}
          <span className={statusClass(job.status)}>{STATUS_COPY[job.status] ?? job.status}</span>
        </span>
        <span className="text-[var(--color-muted)]">
          {job.total_records != null ? `${job.total_records} records` : "count not reported"} ·{" "}
          {whenSet(job.created_at)}
        </span>
      </div>
      {job.expires_at && job.downloadable && (
        <p className="mt-1 text-[var(--color-muted)]">Available until {whenSet(job.expires_at)}</p>
      )}
      {job.error_details && (
        <p className="mt-1 text-[var(--color-error)]">
          {String(job.error_details["reason"] ?? "The export failed")}
        </p>
      )}
      {note && <p className="mt-1 text-[var(--color-error)]">{note}</p>}
      <div className="mt-2 flex items-center gap-2">
        {job.downloadable && (
          <button className={buttonClass(false)} disabled={busy} type="button" onClick={save}>
            {busy ? "Saving…" : "Download"}
          </button>
        )}
        <button className={buttonClass(false)} type="button" onClick={onDelete}>
          Remove file
        </button>
      </div>
    </li>
  );
}

// --- Import ------------------------------------------------------------------

function ImportPanel() {
  const { csrf } = useSession();
  const queryClient = useQueryClient();
  const fileInput = useRef<HTMLInputElement>(null);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [strategy, setStrategy] = useState<string>("skip");
  const [pending, setPending] = useState<ImportJob | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const vocabulary = useQuery({
    queryKey: ["imports", "vocabulary"],
    queryFn: () => api.get<ImportVocabulary>("/imports/vocabulary"),
  });

  const jobs = useQuery({
    queryKey: ["imports"],
    queryFn: () => api.get<ImportJobList>("/imports"),
    refetchInterval: (query) => {
      const items = query.state.data?.items ?? [];
      return items.some((job) => job.status === "queued" || job.status === "running")
        ? 1500
        : false;
    },
    refetchIntervalInBackground: true,
  });

  const upload = useMutation({
    mutationFn: async (file: File) => {
      const form = new FormData();
      form.append("file", file);
      return api.upload<ImportJob>("/imports", form, csrf, 60_000);
    },
    onSuccess: (job) => {
      setPending(job);
      setMapping(job.suggested_mapping);
      setMessage("Nothing has been written yet. Confirm the mapping below.");
    },
    onError: (caught) => setMessage(caught instanceof Error ? caught.message : "Upload failed"),
  });

  const run = useMutation({
    mutationFn: (jobId: string) =>
      api.post<ImportJob>(
        `/imports/${jobId}/run`,
        {
          mapping: Object.fromEntries(
            Object.entries(mapping).filter(([, field]) => field !== ""),
          ),
          duplicate_strategy: strategy,
        },
        csrf,
      ),
    onSuccess: async () => {
      setPending(null);
      setMapping({});
      setMessage("Import started.");
      await queryClient.invalidateQueries({ queryKey: ["imports"] });
    },
    onError: (caught) => setMessage(caught instanceof Error ? caught.message : "Import failed"),
  });

  const remove = useMutation({
    mutationFn: (id: string) => api.delete<ImportJob>(`/imports/${id}`, csrf),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["imports"] });
    },
    onError: (caught) => setMessage(caught instanceof Error ? caught.message : "Delete failed"),
  });

  const fields = vocabulary.data?.fields ?? [];
  const mappedFields = Object.values(mapping).filter(Boolean);

  return (
    <div className="refraction-glass-card rounded-[20px] p-5 space-y-4">
      <div>
        <h2 className="text-sm font-medium">Import</h2>
        <p className="text-xs text-[var(--color-muted)]">
          A CSV or Excel file of your own leads. The file is read, nothing is written
          until you confirm what each column means, and every imported record points
          back at the file it came from.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <input
          ref={fileInput}
          className="text-xs"
          type="file"
          accept=".csv,.xlsx"
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) upload.mutate(file);
            event.target.value = "";
          }}
        />
        {upload.isPending && <span className="text-xs text-[var(--color-muted)]">Uploading…</span>}
      </div>

      {message && <p className="text-xs text-[var(--color-muted)]">{message}</p>}

      {pending && (
        <div className="space-y-3 rounded-[14px] border border-white/[0.07] bg-white/[0.03] p-3">
          <div>
            <p className="text-xs font-medium">{pending.file_name}</p>
            <p className="text-xs text-[var(--color-muted)]">
              {pending.total_rows} rows · {pending.columns.length} columns
            </p>
          </div>

          <div>
            <p className="text-xs font-medium text-[var(--color-muted)]">Column mapping</p>
            <p className="text-xs text-[var(--color-muted)]">
              Say what each column is. A file needs at least a name or a website column.
            </p>
            <div className="mt-2 grid gap-2 sm:grid-cols-2">
              {pending.columns.map((column) => (
                <label key={column} className="block text-xs">
                  <span className="text-[var(--color-muted)]">{column}</span>
                  <select
                    className={fieldClass()}
                    value={mapping[column] ?? ""}
                    onChange={(event) =>
                      setMapping((current) => ({ ...current, [column]: event.target.value }))
                    }
                  >
                    <option value="">Ignore this column</option>
                    {fields.map((field) => (
                      <option key={field.key} value={field.key}>
                        {field.label}
                      </option>
                    ))}
                  </select>
                </label>
              ))}
            </div>
          </div>

          <label className="block text-xs">
            <span className="text-[var(--color-muted)]">When a row matches a record you have</span>
            <select
              className={fieldClass()}
              value={strategy}
              onChange={(event) => setStrategy(event.target.value)}
            >
              {(vocabulary.data?.duplicate_strategies ?? ["skip"]).map((entry) => (
                <option key={entry} value={entry}>
                  {STRATEGY_COPY[entry] ?? entry}
                </option>
              ))}
            </select>
          </label>

          <div className="flex items-center gap-2">
            <button
              className={primaryBtnClass()}
              disabled={run.isPending || mappedFields.length === 0}
              type="button"
              onClick={() => run.mutate(pending.id)}
            >
              {run.isPending ? "Starting…" : "Run import"}
            </button>
            <button
              className={buttonClass(false)}
              type="button"
              onClick={() => {
                setPending(null);
                setMapping({});
              }}
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      <div className="border-t border-white/[0.06] pt-3">
        <p className="text-xs font-medium text-[var(--color-muted)]">Recent imports</p>
        {jobs.isError && (
          <p className="mt-1 text-xs text-[var(--color-error)]">
            {jobs.error instanceof Error ? jobs.error.message : "Imports failed to load"}
          </p>
        )}
        {!jobs.isError && jobs.data && jobs.data.items.length === 0 && (
          <EmptyState
            title="No file imported yet"
            description="Upload a CSV or Excel file to bring your own leads in."
          />
        )}
        <ul className="mt-2 space-y-2">
          {jobs.data?.items.map((job) => (
            <ImportRow key={job.id} job={job} onDelete={() => remove.mutate(job.id)} />
          ))}
        </ul>
      </div>
    </div>
  );
}

function ImportRow({ job, onDelete }: { job: ImportJob; onDelete: () => void }) {
  const details = job.error_details as
    | {
        created?: number;
        merged?: number;
        duplicates_skipped?: number;
        failed?: number;
        errors?: { row: number; reason: string }[];
        warnings?: { row: number; reason: string }[];
      }
    | null;

  return (
    <li className="rounded-[14px] border border-white/[0.07] bg-white/[0.03] p-3 text-xs">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span>
          {job.file_name} · <span className={statusClass(job.status)}>{STATUS_COPY[job.status] ?? job.status}</span>
        </span>
        <span className="text-[var(--color-muted)]">{whenSet(job.created_at)}</span>
      </div>
      <p className="mt-1 text-[var(--color-muted)]">
        {job.processed_rows} of {job.total_rows} rows processed
        {job.failed_rows > 0 ? ` · ${job.failed_rows} failed` : ""}
      </p>
      {details && (
        <p className="mt-1 text-[var(--color-muted)]">
          {details.created ?? 0} created · {details.merged ?? 0} merged ·{" "}
          {details.duplicates_skipped ?? 0} duplicates skipped
        </p>
      )}
      {details?.errors && details.errors.length > 0 && (
        <ul className="mt-1 list-disc space-y-0.5 pl-4 text-[var(--color-error)]">
          {details.errors.map((entry) => (
            <li key={`${entry.row}-${entry.reason}`}>
              Row {entry.row}: {entry.reason}
            </li>
          ))}
        </ul>
      )}
      {details?.warnings && details.warnings.length > 0 && (
        <ul className="mt-1 list-disc space-y-0.5 pl-4 text-[var(--color-muted)]">
          {details.warnings.map((entry) => (
            <li key={`${entry.row}-${entry.reason}`}>
              Row {entry.row}: {entry.reason}
            </li>
          ))}
        </ul>
      )}
      <div className="mt-2">
        <button className={buttonClass(false)} type="button" onClick={onDelete}>
          Remove file
        </button>
      </div>
    </li>
  );
}
