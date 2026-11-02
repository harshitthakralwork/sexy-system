"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { Header } from "@/components/layout/header";
import { Card, EmptyState } from "@/components/ui/card";
import { useSession } from "@/components/providers/session-provider";
import { api } from "@/lib/api/client";
import type { Schedule, ScheduleList, Workflow, WorkflowList } from "@/lib/api/types";

export function SchedulesView() {
  const { csrf, user } = useSession();
  const queryClient = useQueryClient();
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const schedules = useQuery({
    queryKey: ["automation", "schedules"],
    queryFn: () => api.get<ScheduleList>("/workflows/schedules?limit=200"),
  });

  async function refresh() {
    await queryClient.invalidateQueries({ queryKey: ["automation", "schedules"] });
  }

  if (!user) return null;

  const rows = schedules.data?.items ?? [];

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <Header
        title="Scheduler"
        subtitle="Run workflows on a recurring cadence — cron or a fixed interval"
      />

      <main className="flex-1 overflow-y-auto p-4">
        <CreateScheduleForm
          csrf={csrf}
          onCreated={async (message) => {
            setNotice(message);
            await refresh();
          }}
          onError={setError}
        />

        {(notice || error) && (
          <div className="mt-3 text-sm">
            {error && <p className="text-[var(--color-error)]">{error}</p>}
            {notice && <p className="text-[var(--color-muted)]">{notice}</p>}
          </div>
        )}

        <div className="mt-4">
          {schedules.isPending ? (
            <EmptyState title="Loading schedules…" description="" />
          ) : rows.length === 0 ? (
            <EmptyState
              title="No schedules yet"
              description="Create one above to run a workflow repeatedly."
            />
          ) : (
            <div className="overflow-x-auto rounded-lg border border-border">
              <table className="w-full min-w-[760px] text-sm">
                <thead>
                  <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-[var(--color-muted)]">
                    <th className="px-3 py-2">Workflow</th>
                    <th className="px-3 py-2">Recurrence</th>
                    <th className="px-3 py-2">Timezone</th>
                    <th className="px-3 py-2">Next run</th>
                    <th className="px-3 py-2">Last run</th>
                    <th className="px-3 py-2" />
                  </tr>
                </thead>
                <tbody>
                  {rows.map((schedule) => (
                    <ScheduleRow
                      key={schedule.id}
                      schedule={schedule}
                      csrf={csrf}
                      onChanged={async (message) => {
                        setNotice(message);
                        await refresh();
                      }}
                      onError={setError}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}

function CreateScheduleForm({
  csrf,
  onCreated,
  onError,
}: {
  csrf: string | null;
  onCreated: (message: string) => Promise<void>;
  onError: (message: string) => void;
}) {
  const workflows = useQuery({
    queryKey: ["automation", "workflows"],
    queryFn: () => api.get<WorkflowList>("/workflows?limit=200"),
  });
  const [workflowId, setWorkflowId] = useState("");
  const [mode, setMode] = useState<"interval" | "cron">("interval");
  const [intervalSeconds, setIntervalSeconds] = useState(3600);
  const [cron, setCron] = useState("0 9 * * *");
  const [timezone, setTimezone] = useState("UTC");
  const [startAt, setStartAt] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit() {
    if (!workflowId) {
      onError("Choose a workflow.");
      return;
    }
    if (!startAt) {
      onError("Choose a start time.");
      return;
    }
    const recurrenceConfig =
      mode === "interval" ? { interval_seconds: intervalSeconds } : { cron: cron.trim() };

    setBusy(true);
    try {
      await api.post<Schedule>(
        "/workflows/schedules",
        {
          workflow_id: workflowId,
          recurrence_config: recurrenceConfig,
          timezone,
          start_at: new Date(startAt).toISOString(),
        },
        csrf,
      );
      setStartAt("");
      await onCreated("Schedule created.");
    } catch (caught) {
      onError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--color-muted)]">
        New schedule
      </h3>
      <div className="mt-2 flex flex-wrap items-end gap-3">
        <label className="text-sm">
          <span className="text-[var(--color-muted)]">Workflow</span>
          <select
            className="mt-1 block w-56 rounded-md border border-border bg-[var(--color-background)] px-2 py-1.5"
            value={workflowId}
            onChange={(event) => setWorkflowId(event.target.value)}
          >
            <option value="">choose…</option>
            {(workflows.data?.items ?? []).map((workflow: Workflow) => (
              <option key={workflow.id} value={workflow.id}>
                {workflow.name}
              </option>
            ))}
          </select>
        </label>
        <label className="text-sm">
          <span className="text-[var(--color-muted)]">Recurrence</span>
          <select
            className="mt-1 block w-28 rounded-md border border-border bg-[var(--color-background)] px-2 py-1.5"
            value={mode}
            onChange={(event) => setMode(event.target.value as "interval" | "cron")}
          >
            <option value="interval">interval</option>
            <option value="cron">cron</option>
          </select>
        </label>
        {mode === "interval" ? (
          <label className="text-sm">
            <span className="text-[var(--color-muted)]">Interval (seconds)</span>
            <input
              className="mt-1 block w-32 rounded-md border border-border bg-[var(--color-background)] px-2 py-1.5"
              type="number"
              min={60}
              value={intervalSeconds}
              onChange={(event) => setIntervalSeconds(Number(event.target.value) || 3600)}
            />
          </label>
        ) : (
          <label className="text-sm">
            <span className="text-[var(--color-muted)]">Cron (5 fields)</span>
            <input
              className="mt-1 block w-40 rounded-md border border-border bg-[var(--color-background)] px-2 py-1.5"
              value={cron}
              onChange={(event) => setCron(event.target.value)}
              placeholder="0 9 * * *"
            />
          </label>
        )}
        <label className="text-sm">
          <span className="text-[var(--color-muted)]">Timezone</span>
          <input
            className="mt-1 block w-32 rounded-md border border-border bg-[var(--color-background)] px-2 py-1.5"
            value={timezone}
            onChange={(event) => setTimezone(event.target.value)}
            placeholder="UTC"
          />
        </label>
        <label className="text-sm">
          <span className="text-[var(--color-muted)]">Start at</span>
          <input
            className="mt-1 block w-44 rounded-md border border-border bg-[var(--color-background)] px-2 py-1.5"
            type="datetime-local"
            value={startAt}
            onChange={(event) => setStartAt(event.target.value)}
          />
        </label>
        <button
          className={buttonClass(true)}
          disabled={busy || !workflowId || !startAt}
          onClick={submit}
          type="button"
        >
          {busy ? "Creating…" : "Create"}
        </button>
      </div>
    </Card>
  );
}

function ScheduleRow({
  schedule,
  csrf,
  onChanged,
  onError,
}: {
  schedule: Schedule;
  csrf: string | null;
  onChanged: (message: string) => Promise<void>;
  onError: (message: string) => void;
}) {
  const [running, setRunning] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const recurrence =
    "interval_seconds" in schedule.recurrence_config
      ? `every ${String(schedule.recurrence_config.interval_seconds)}s`
      : `cron ${String(schedule.recurrence_config.cron)}`;

  async function runNow() {
    setRunning(true);
    try {
      await api.post(`/workflows/schedules/${schedule.id}/run`, undefined, csrf);
      await onChanged("Schedule triggered. Next run time advanced.");
    } catch (caught) {
      onError(errorMessage(caught));
    } finally {
      setRunning(false);
    }
  }

  async function remove() {
    setDeleting(true);
    try {
      await api.delete(`/workflows/schedules/${schedule.id}`, csrf);
      await onChanged("Schedule deleted.");
    } catch (caught) {
      onError(errorMessage(caught));
      setDeleting(false);
    }
  }

  return (
    <tr className="border-b border-border/60 hover:bg-[var(--color-surface-elevated)]">
      <td className="px-3 py-2 text-[var(--color-muted)]">{shortId(schedule.workflow_id)}</td>
      <td className="px-3 py-2">{recurrence}</td>
      <td className="px-3 py-2 text-[var(--color-muted)]">{schedule.timezone}</td>
      <td className="px-3 py-2 text-[var(--color-muted)]">
        {schedule.next_run_at ? new Date(schedule.next_run_at).toLocaleString() : "—"}
      </td>
      <td className="px-3 py-2 text-[var(--color-muted)]">
        {schedule.last_run_at ? new Date(schedule.last_run_at).toLocaleString() : "never"}
      </td>
      <td className="px-3 py-2 text-right">
        <button className={buttonClass(false)} disabled={running} onClick={runNow} type="button">
          {running ? "Running…" : "Run now"}
        </button>{" "}
        <button className={buttonClass(false)} disabled={deleting} onClick={remove} type="button">
          {deleting ? "Deleting…" : "Delete"}
        </button>
      </td>
    </tr>
  );
}

function shortId(id: string): string {
  return id.slice(0, 8);
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
