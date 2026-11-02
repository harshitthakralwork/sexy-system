"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { Header } from "@/components/layout/header";
import { Card, EmptyState } from "@/components/ui/card";
import { useSession } from "@/components/providers/session-provider";
import { api } from "@/lib/api/client";
import type {
  Execution,
  Workflow,
  WorkflowList,
  WorkflowStepDef,
} from "@/lib/api/types";

const STEP_TYPES = ["qualify", "shortlist", "email_draft", "send"] as const;

export function WorkflowsView() {
  const { csrf, user } = useSession();
  const queryClient = useQueryClient();
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const workflows = useQuery({
    queryKey: ["automation", "workflows"],
    queryFn: () => api.get<WorkflowList>("/workflows?limit=200"),
  });

  async function refresh() {
    await queryClient.invalidateQueries({ queryKey: ["automation", "workflows"] });
  }

  if (!user) return null;

  const rows = workflows.data?.items ?? [];

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <Header
        title="Workflow Builder"
        subtitle="Automate qualification, shortlisting and outreach — one step at a time"
      />

      <main className="flex-1 overflow-y-auto p-4">
        <CreateWorkflowForm
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
          {workflows.isPending ? (
            <EmptyState title="Loading workflows…" description="" />
          ) : rows.length === 0 ? (
            <EmptyState
              title="No workflows yet"
              description="Create one above to start automating your lead pipeline."
            />
          ) : (
            <div className="space-y-3">
              {rows.map((workflow) => (
                <WorkflowCard
                  key={workflow.id}
                  workflow={workflow}
                  csrf={csrf}
                  onChanged={async (message) => {
                    setNotice(message);
                    await refresh();
                  }}
                  onError={setError}
                />
              ))}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}

interface StepDraft {
  key: string;
  type: string;
  configText: string;
}

function CreateWorkflowForm({
  csrf,
  onCreated,
  onError,
}: {
  csrf: string | null;
  onCreated: (message: string) => Promise<void>;
  onError: (message: string) => void;
}) {
  const [name, setName] = useState("");
  const [module, setModule] = useState("leads");
  const [steps, setSteps] = useState<StepDraft[]>([
    { key: "shortlist", type: "shortlist", configText: '{"only_qualified": false}' },
  ]);
  const [busy, setBusy] = useState(false);

  function updateStep(index: number, patch: Partial<StepDraft>) {
    setSteps((current) => current.map((step, i) => (i === index ? { ...step, ...patch } : step)));
  }

  function addStep() {
    setSteps((current) => [...current, { key: "", type: "email_draft", configText: "" }]);
  }

  function removeStep(index: number) {
    setSteps((current) => current.filter((_, i) => i !== index));
  }

  async function submit() {
    const parsedSteps: WorkflowStepDef[] = [];
    for (const step of steps) {
      if (!step.key.trim()) {
        onError("Every step needs a key.");
        return;
      }
      let config: Record<string, unknown> = {};
      if (step.configText.trim()) {
        try {
          config = JSON.parse(step.configText);
        } catch {
          onError(`Step "${step.key}" has invalid JSON config.`);
          return;
        }
      }
      parsedSteps.push({ key: step.key.trim(), type: step.type, config });
    }
    if (parsedSteps.length === 0) {
      onError("Add at least one step.");
      return;
    }

    setBusy(true);
    try {
      const created = await api.post<Workflow>(
        "/workflows",
        { name: name.trim(), module, steps: parsedSteps },
        csrf,
      );
      setName("");
      setSteps([{ key: "shortlist", type: "shortlist", configText: '{"only_qualified": false}' }]);
      await onCreated(`Created workflow "${created.name}" (v${created.version}).`);
    } catch (caught) {
      onError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--color-muted)]">
        New workflow
      </h3>
      <div className="mt-2 flex flex-wrap items-end gap-3">
        <label className="min-w-48 flex-1 text-sm">
          <span className="text-[var(--color-muted)]">Name</span>
          <input
            className="mt-1 w-full rounded-md border border-border bg-[var(--color-background)] px-2 py-1.5"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Qualify and draft outreach"
          />
        </label>
        <label className="text-sm">
          <span className="text-[var(--color-muted)]">Module</span>
          <input
            className="mt-1 w-32 rounded-md border border-border bg-[var(--color-background)] px-2 py-1.5"
            value={module}
            onChange={(event) => setModule(event.target.value)}
          />
        </label>
      </div>

      <div className="mt-3">
        <p className="text-xs text-[var(--color-muted)]">Steps (run in order)</p>
        <div className="mt-2 space-y-2">
          {steps.map((step, index) => (
            <div key={index} className="flex flex-wrap items-center gap-2">
              <input
                className="w-32 rounded-md border border-border bg-[var(--color-background)] px-2 py-1.5 text-sm"
                value={step.key}
                onChange={(event) => updateStep(index, { key: event.target.value })}
                placeholder="step key"
              />
              <select
                className="w-36 rounded-md border border-border bg-[var(--color-background)] px-2 py-1.5 text-sm"
                value={step.type}
                onChange={(event) => updateStep(index, { type: event.target.value })}
              >
                {STEP_TYPES.map((type) => (
                  <option key={type} value={type}>
                    {type}
                  </option>
                ))}
              </select>
              <input
                className="min-w-48 flex-1 rounded-md border border-border bg-[var(--color-background)] px-2 py-1.5 text-sm"
                value={step.configText}
                onChange={(event) => updateStep(index, { configText: event.target.value })}
                placeholder='config JSON, e.g. {"service_name": "websites"}'
              />
              <button
                className={buttonClass(false)}
                disabled={steps.length === 1}
                onClick={() => removeStep(index)}
                type="button"
              >
                Remove
              </button>
            </div>
          ))}
        </div>
        <button className={`${buttonClass(false)} mt-2`} onClick={addStep} type="button">
          Add step
        </button>
      </div>

      <div className="mt-4">
        <button
          className={buttonClass(true)}
          disabled={busy || !name.trim()}
          onClick={submit}
          type="button"
        >
          {busy ? "Creating…" : "Create workflow"}
        </button>
      </div>
    </Card>
  );
}

function WorkflowCard({
  workflow,
  csrf,
  onChanged,
  onError,
}: {
  workflow: Workflow;
  csrf: string | null;
  onChanged: (message: string) => Promise<void>;
  onError: (message: string) => void;
}) {
  const queryClient = useQueryClient();
  const [running, setRunning] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [businessIds, setBusinessIds] = useState("");
  const [showExecutions, setShowExecutions] = useState(false);

  const executions = useQuery({
    queryKey: ["automation", "executions", workflow.id],
    queryFn: () => api.get<{ items: Execution[]; total: number }>(
      `/workflows/${workflow.id}/executions?limit=50`,
    ),
    enabled: showExecutions,
  });

  async function run() {
    const ids = businessIds
      .split(",")
      .map((value) => value.trim())
      .filter(Boolean);
    setRunning(true);
    try {
      await api.post(
        `/workflows/${workflow.id}/run`,
        { input_data: { business_ids: ids } },
        csrf,
      );
      setBusinessIds("");
      await onChanged("Run started. Refreshing executions…");
      setShowExecutions(true);
      await queryClient.invalidateQueries({ queryKey: ["automation", "executions", workflow.id] });
    } catch (caught) {
      onError(errorMessage(caught));
    } finally {
      setRunning(false);
    }
  }

  async function remove() {
    setDeleting(true);
    try {
      await api.delete(`/workflows/${workflow.id}`, csrf);
      await onChanged(`Deleted workflow "${workflow.name}".`);
    } catch (caught) {
      onError(errorMessage(caught));
      setDeleting(false);
    }
  }

  const stepNames = workflow.workflow_definition.steps.map((step) => step.type).join(" → ");

  return (
    <Card>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <span className="font-medium">{workflow.name}</span>
            <span className="rounded bg-[var(--color-surface-elevated)] px-1.5 py-0.5 text-[10px] text-[var(--color-muted)]">
              v{workflow.version}
            </span>
            <span
              className={`text-[10px] uppercase ${
                workflow.status === "active" ? "text-[var(--color-success)]" : "text-[var(--color-muted)]"
              }`}
            >
              {workflow.status}
            </span>
          </div>
          <p className="mt-1 text-xs text-[var(--color-muted)]">{stepNames || "no steps"}</p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <input
            className="w-64 rounded-md border border-border bg-[var(--color-background)] px-2 py-1 text-xs"
            placeholder="business ids (comma-separated, optional)"
            value={businessIds}
            onChange={(event) => setBusinessIds(event.target.value)}
          />
          <button className={buttonClass(true)} disabled={running} onClick={run} type="button">
            {running ? "Running…" : "Run"}
          </button>
          <button
            className={buttonClass(false)}
            onClick={() => setShowExecutions((value) => !value)}
            type="button"
          >
            {showExecutions ? "Hide runs" : "Runs"}
          </button>
          <button className={buttonClass(false)} disabled={deleting} onClick={remove} type="button">
            {deleting ? "Deleting…" : "Delete"}
          </button>
        </div>
      </div>

      {showExecutions && (
        <div className="mt-3 overflow-x-auto rounded-lg border border-border">
          <table className="w-full min-w-[640px] text-sm">
            <thead>
              <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-[var(--color-muted)]">
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2">Trigger</th>
                <th className="px-3 py-2">Started</th>
                <th className="px-3 py-2">Completed</th>
                <th className="px-3 py-2" />
              </tr>
            </thead>
            <tbody>
              {(executions.data?.items ?? []).map((execution) => (
                <ExecutionRow key={execution.id} execution={execution} />
              ))}
            </tbody>
          </table>
          {(executions.data?.items ?? []).length === 0 && (
            <p className="px-3 py-2 text-xs text-[var(--color-muted)]">No runs yet.</p>
          )}
        </div>
      )}
    </Card>
  );
}

function ExecutionRow({ execution }: { execution: Execution }) {
  const [expanded, setExpanded] = useState(false);

  const detail = useQuery({
    queryKey: ["automation", "execution", execution.id],
    queryFn: () => api.get<Execution>(`/workflows/executions/${execution.id}`),
    enabled: expanded,
  });

  return (
    <>
      <tr className="border-b border-border/60 align-top hover:bg-[var(--color-surface-elevated)]">
        <td className="px-3 py-2">
          <span
            className={`text-xs ${
              execution.status === "completed"
                ? "text-[var(--color-success)]"
                : execution.status === "failed"
                  ? "text-[var(--color-error)]"
                  : "text-[var(--color-muted)]"
            }`}
          >
            {execution.status}
          </span>
        </td>
        <td className="px-3 py-2 text-[var(--color-muted)]">{execution.trigger_type}</td>
        <td className="px-3 py-2 text-[var(--color-muted)]">
          {execution.started_at ? new Date(execution.started_at).toLocaleString() : "—"}
        </td>
        <td className="px-3 py-2 text-[var(--color-muted)]">
          {execution.completed_at ? new Date(execution.completed_at).toLocaleString() : "—"}
        </td>
        <td className="px-3 py-2 text-right">
          <button
            className={buttonClass(false)}
            onClick={() => setExpanded((value) => !value)}
            type="button"
          >
            {expanded ? "Hide steps" : "Steps"}
          </button>
        </td>
      </tr>
      {expanded && (
        <tr className="border-b border-border/60 bg-[var(--color-surface-elevated)]/40">
          <td className="px-3 py-2" colSpan={5}>
            {detail.isPending ? (
              <span className="text-xs text-[var(--color-muted)]">Loading steps…</span>
            ) : (
              <ul className="space-y-1">
                {(detail.data?.steps ?? []).map((step) => (
                  <li key={step.id} className="flex items-center gap-2 text-xs">
                    <span
                      className={`${
                        step.status === "completed"
                          ? "text-[var(--color-success)]"
                          : step.status === "failed"
                            ? "text-[var(--color-error)]"
                            : "text-[var(--color-muted)]"
                      }`}
                    >
                      {step.status}
                    </span>
                    <span className="text-[var(--color-muted)]">
                      {step.step_key} ({step.step_type})
                    </span>
                    {step.error_details && (
                      <span className="text-[var(--color-error)]">
                        {String(step.error_details.reason ?? "")}
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </td>
        </tr>
      )}
    </>
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
