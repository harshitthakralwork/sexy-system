"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { Header } from "@/components/layout/header";
import { Card, EmptyState } from "@/components/ui/card";
import { useSession } from "@/components/providers/session-provider";
import { api } from "@/lib/api/client";
import type { Approval, ApprovalList } from "@/lib/api/types";

const STATUSES = ["", "pending", "approved", "rejected"] as const;

export function ApprovalsView() {
  const { csrf, user } = useSession();
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const approvals = useQuery({
    queryKey: ["automation", "approvals", statusFilter],
    queryFn: () =>
      api.get<ApprovalList>(
        `/workflows/approvals?limit=200${statusFilter ? `&status=${statusFilter}` : ""}`,
      ),
  });

  async function refresh() {
    await queryClient.invalidateQueries({ queryKey: ["automation", "approvals"] });
  }

  if (!user) return null;

  const rows = approvals.data?.items ?? [];
  const pendingCount = rows.filter((row) => row.status === "pending").length;

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <Header
        title="Approval Queue"
        subtitle="Review AI-drafted outreach before anything is sent"
      />

      <main className="flex-1 overflow-y-auto p-4">
        <Card>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--color-muted)]">
                Approvals
              </h3>
              <select
                className="rounded-md border border-border bg-[var(--color-background)] px-2 py-1 text-xs"
                value={statusFilter}
                onChange={(event) => setStatusFilter(event.target.value)}
              >
                {STATUSES.map((status) => (
                  <option key={status} value={status}>
                    {status || "all"}
                  </option>
                ))}
              </select>
            </div>
            {statusFilter === "" || statusFilter === "pending" ? (
              <span className="text-xs text-[var(--color-muted)]">
                {pendingCount} awaiting review
              </span>
            ) : null}
          </div>

          {(notice || error) && (
            <div className="mt-2 text-sm">
              {error && <p className="text-[var(--color-error)]">{error}</p>}
              {notice && <p className="text-[var(--color-muted)]">{notice}</p>}
            </div>
          )}

          {approvals.isPending ? (
            <EmptyState title="Loading approvals…" description="" />
          ) : rows.length === 0 ? (
            <EmptyState
              title="No approvals"
              description="Approvals appear here when a workflow drafts an email for a lead."
            />
          ) : (
            <div className="mt-3 space-y-3">
              {rows.map((approval) => (
                <ApprovalCard
                  key={approval.id}
                  approval={approval}
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
        </Card>
      </main>
    </div>
  );
}

function ApprovalCard({
  approval,
  csrf,
  onChanged,
  onError,
}: {
  approval: Approval;
  csrf: string | null;
  onChanged: (message: string) => Promise<void>;
  onError: (message: string) => void;
}) {
  const [busy, setBusy] = useState<"approved" | "rejected" | null>(null);
  const recipient = String(approval.original_content.recipient_email ?? "");
  const subject = String(approval.original_content.subject ?? "");
  const body = String(approval.original_content.body ?? "");

  async function review(decision: "approved" | "rejected") {
    setBusy(decision);
    try {
      await api.post(
        `/workflows/approvals/${approval.id}/review`,
        { decision },
        csrf,
      );
      await onChanged(`Approval ${decision}.`);
    } catch (caught) {
      onError(errorMessage(caught));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="rounded-lg border border-border p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium">{recipient || "unknown recipient"}</span>
          <StatusBadge status={approval.status} />
        </div>
        <span className="text-xs text-[var(--color-muted)]">
          {new Date(approval.created_at).toLocaleString()}
        </span>
      </div>
      {subject && <p className="mt-1 text-sm">{subject}</p>}
      {body && (
        <p className="mt-1 whitespace-pre-wrap text-xs text-[var(--color-muted)]">
          {body.slice(0, 400)}
          {body.length > 400 ? "…" : ""}
        </p>
      )}
      {approval.status === "pending" && (
        <div className="mt-3 flex gap-2">
          <button
            className={buttonClass(true)}
            disabled={busy !== null}
            onClick={() => review("approved")}
            type="button"
          >
            {busy === "approved" ? "Approving…" : "Approve"}
          </button>
          <button
            className={buttonClass(false)}
            disabled={busy !== null}
            onClick={() => review("rejected")}
            type="button"
          >
            {busy === "rejected" ? "Rejecting…" : "Reject"}
          </button>
        </div>
      )}
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const tone =
    status === "approved"
      ? "text-[var(--color-success)]"
      : status === "rejected"
        ? "text-[var(--color-error)]"
        : "text-[var(--color-muted)]";
  return <span className={`text-xs ${tone}`}>{status}</span>;
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
