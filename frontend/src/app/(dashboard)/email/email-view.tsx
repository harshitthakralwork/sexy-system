"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { Header } from "@/components/layout/header";
import { Card, EmptyState } from "@/components/ui/card";
import { useSession } from "@/components/providers/session-provider";
import { api } from "@/lib/api/client";
import type {
  Campaign,
  CampaignList,
  EmailAccount,
  EmailAccountList,
  EmailMessage,
  EmailMessageList,
  SendResult,
  SuppressionEntry,
  SuppressionList,
} from "@/lib/api/types";

type Tab = "messages" | "accounts" | "campaigns" | "suppression";

const TABS: { key: Tab; label: string }[] = [
  { key: "messages", label: "Messages" },
  { key: "accounts", label: "Accounts" },
  { key: "campaigns", label: "Campaigns" },
  { key: "suppression", label: "Suppression" },
];

export function EmailView() {
  const { user } = useSession();
  const [tab, setTab] = useState<Tab>("messages");

  if (!user) return null;

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <Header
        title="Email Outreach"
        subtitle="Accounts, drafts, approvals and sending — with an approval gate"
      />

      <main className="flex-1 overflow-y-auto p-4">
        <div className="flex flex-wrap gap-1 border-b border-border">
          {TABS.map((entry) => (
            <button
              key={entry.key}
              type="button"
              onClick={() => setTab(entry.key)}
              className={
                tab === entry.key
                  ? "rounded-t-md border border-b-0 border-border bg-[var(--color-surface)] px-3 py-2 text-xs font-medium"
                  : "rounded-t-md px-3 py-2 text-xs text-[var(--color-muted)] hover:text-[var(--color-foreground)]"
              }
            >
              {entry.label}
            </button>
          ))}
        </div>

        <div className="mt-4">
          {tab === "messages" && <MessagesPanel />}
          {tab === "accounts" && <AccountsPanel />}
          {tab === "campaigns" && <CampaignsPanel />}
          {tab === "suppression" && <SuppressionPanel />}
        </div>
      </main>
    </div>
  );
}

function MessagesPanel() {
  const { csrf } = useSession();
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const messages = useQuery({
    queryKey: ["email", "messages", statusFilter],
    queryFn: () =>
      api.get<EmailMessageList>(
        `/email/messages?limit=100${statusFilter ? `&status=${statusFilter}` : ""}`,
      ),
  });

  async function refresh() {
    await queryClient.invalidateQueries({ queryKey: ["email", "messages"] });
  }

  const rows = messages.data?.items ?? [];

  return (
    <div className="space-y-4">
      <CreateDraftForm
        csrf={csrf}
        onCreated={async (message) => {
          setNotice(message);
          await refresh();
        }}
        onError={setError}
      />

      {(notice || error) && (
        <div className="text-sm">
          {error && <p className="text-[var(--color-error)]">{error}</p>}
          {notice && <p className="text-[var(--color-muted)]">{notice}</p>}
        </div>
      )}

      <Card>
        <div className="flex items-center gap-3">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--color-muted)]">
            Messages
          </h3>
          <select
            className="rounded-md border border-border bg-[var(--color-background)] px-2 py-1 text-xs"
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value)}
          >
            <option value="">all statuses</option>
            {[
              "draft",
              "pending_approval",
              "approved",
              "rejected",
              "sent",
              "failed",
              "suppressed",
            ].map((status) => (
              <option key={status} value={status}>
                {status}
              </option>
            ))}
          </select>
        </div>

        {messages.isPending ? (
          <EmptyState title="Loading messages…" description="" />
        ) : rows.length === 0 ? (
          <EmptyState
            title="No messages"
            description="Create a draft above, or run an email-draft workflow."
          />
        ) : (
          <div className="mt-3 overflow-x-auto rounded-lg border border-border">
            <table className="w-full min-w-[820px] text-sm">
              <thead>
                <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-[var(--color-muted)]">
                  <th className="px-3 py-2">Recipient</th>
                  <th className="px-3 py-2">Subject</th>
                  <th className="px-3 py-2">Status</th>
                  <th className="px-3 py-2">Updated</th>
                  <th className="px-3 py-2" />
                </tr>
              </thead>
              <tbody>
                {rows.map((message) => (
                  <MessageRow
                    key={message.id}
                    message={message}
                    csrf={csrf}
                    onChanged={async (text) => {
                      setNotice(text);
                      await refresh();
                    }}
                    onError={setError}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}

function CreateDraftForm({
  csrf,
  onCreated,
  onError,
}: {
  csrf: string | null;
  onCreated: (message: string) => Promise<void>;
  onError: (message: string) => void;
}) {
  const [recipient, setRecipient] = useState("");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit() {
    if (!recipient.trim()) {
      onError("A recipient email is required.");
      return;
    }
    setBusy(true);
    try {
      await api.post<EmailMessage>(
        "/email/messages",
        { recipient_email: recipient.trim(), subject, body },
        csrf,
      );
      setRecipient("");
      setSubject("");
      setBody("");
      await onCreated("Draft created.");
    } catch (caught) {
      onError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--color-muted)]">
        New draft
      </h3>
      <div className="mt-2 flex flex-wrap items-end gap-3">
        <label className="min-w-48 flex-1 text-sm">
          <span className="text-[var(--color-muted)]">Recipient</span>
          <input
            className="mt-1 w-full rounded-md border border-border bg-[var(--color-background)] px-2 py-1.5"
            value={recipient}
            onChange={(event) => setRecipient(event.target.value)}
            placeholder="owner@business.in"
          />
        </label>
        <label className="min-w-48 flex-1 text-sm">
          <span className="text-[var(--color-muted)]">Subject</span>
          <input
            className="mt-1 w-full rounded-md border border-border bg-[var(--color-background)] px-2 py-1.5"
            value={subject}
            onChange={(event) => setSubject(event.target.value)}
          />
        </label>
      </div>
      <label className="mt-2 block text-sm">
        <span className="text-[var(--color-muted)]">Body</span>
        <textarea
          className="mt-1 w-full rounded-md border border-border bg-[var(--color-background)] px-2 py-1.5"
          rows={3}
          value={body}
          onChange={(event) => setBody(event.target.value)}
        />
      </label>
      <button
        className={`${buttonClass(true)} mt-3`}
        disabled={busy || !recipient.trim()}
        onClick={submit}
        type="button"
      >
        {busy ? "Creating…" : "Create draft"}
      </button>
    </Card>
  );
}

function MessageRow({
  message,
  csrf,
  onChanged,
  onError,
}: {
  message: EmailMessage;
  csrf: string | null;
  onChanged: (text: string) => Promise<void>;
  onError: (message: string) => void;
}) {
  const [busy, setBusy] = useState<string | null>(null);
  const [showEvents, setShowEvents] = useState(false);

  async function act(action: "approve" | "send") {
    setBusy(action);
    try {
      if (action === "approve") {
        await api.post(`/email/messages/${message.id}/approve`, undefined, csrf);
        await onChanged("Message approved.");
      } else {
        const result = await api.post<SendResult>(
          `/email/messages/${message.id}/send`,
          undefined,
          csrf,
        );
        await onChanged(
          result.status === "sent"
            ? "Message sent."
            : `Send not completed (${result.status}${result.error ? `: ${result.error}` : ""}).`,
        );
      }
    } catch (caught) {
      onError(errorMessage(caught));
    } finally {
      setBusy(null);
    }
  }

  const canApprove = message.status === "draft" || message.status === "pending_approval";
  const canSend = message.status === "approved";

  return (
    <>
      <tr className="border-b border-border/60 align-top hover:bg-[var(--color-surface-elevated)]">
        <td className="px-3 py-2">{message.recipient_email}</td>
        <td className="max-w-[280px] px-3 py-2 text-[var(--color-muted)]">
          {message.subject ?? "—"}
        </td>
        <td className="px-3 py-2">
          <span className={`text-xs ${statusTone(message.status)}`}>{message.status}</span>
        </td>
        <td className="px-3 py-2 text-[var(--color-muted)]">
          {new Date(message.created_at).toLocaleString()}
        </td>
        <td className="px-3 py-2 text-right">
          <div className="flex items-center justify-end gap-2">
            <button
              className={buttonClass(false)}
              onClick={() => setShowEvents((value) => !value)}
              type="button"
            >
              {showEvents ? "Hide events" : "Events"}
            </button>
            {canApprove && (
              <button
                className={buttonClass(false)}
                disabled={busy !== null}
                onClick={() => act("approve")}
                type="button"
              >
                {busy === "approve" ? "Approving…" : "Approve"}
              </button>
            )}
            {canSend && (
              <button
                className={buttonClass(true)}
                disabled={busy !== null}
                onClick={() => act("send")}
                type="button"
              >
                {busy === "send" ? "Sending…" : "Send"}
              </button>
            )}
          </div>
        </td>
      </tr>
      {showEvents && (
        <tr className="border-b border-border/60 bg-[var(--color-surface-elevated)]/40">
          <td className="px-3 py-2" colSpan={5}>
            <EventList messageId={message.id} />
          </td>
        </tr>
      )}
    </>
  );
}

function EventList({ messageId }: { messageId: string }) {
  const events = useQuery({
    queryKey: ["email", "events", messageId],
    queryFn: () => api.get<{ id: string; event_type: string; occurred_at: string }[]>(
      `/email/messages/${messageId}/events`,
    ),
  });

  if (events.isPending) return <span className="text-xs text-[var(--color-muted)]">Loading…</span>;
  const rows = events.data ?? [];
  if (rows.length === 0) {
    return <span className="text-xs text-[var(--color-muted)]">No events yet.</span>;
  }
  return (
    <ul className="space-y-1">
      {rows.map((event) => (
        <li key={event.id} className="text-xs text-[var(--color-muted)]">
          {event.event_type} — {new Date(event.occurred_at).toLocaleString()}
        </li>
      ))}
    </ul>
  );
}

function AccountsPanel() {
  const { csrf } = useSession();
  const queryClient = useQueryClient();
  const [email, setEmail] = useState("");
  const [provider, setProvider] = useState("smtp");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const accounts = useQuery({
    queryKey: ["email", "accounts"],
    queryFn: () => api.get<EmailAccountList>("/email/accounts"),
  });

  async function refresh() {
    await queryClient.invalidateQueries({ queryKey: ["email", "accounts"] });
  }

  async function create() {
    if (!email.trim()) return;
    setBusy(true);
    try {
      await api.post<EmailAccount>(
        "/email/accounts",
        { provider, email_address: email.trim() },
        csrf,
      );
      setEmail("");
      setNotice("Account added.");
      await refresh();
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  async function markConnected(id: string) {
    try {
      await api.patch(`/email/accounts/${id}`, { status: "connected" }, csrf);
      setNotice("Account marked connected.");
      await refresh();
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }

  async function remove(id: string) {
    try {
      await api.delete(`/email/accounts/${id}`, csrf);
      setNotice("Account deleted.");
      await refresh();
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }

  const rows = accounts.data?.items ?? [];

  return (
    <div className="space-y-4">
      <Card>
        <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--color-muted)]">
          Add a sending account
        </h3>
        <p className="mt-1 text-xs text-[var(--color-muted)]">
          Credentials live outside the database (secret_reference). SMTP sends through your own
          server; Gmail OAuth needs client credentials configured on the backend.
        </p>
        <div className="mt-2 flex flex-wrap items-end gap-3">
          <label className="text-sm">
            <span className="text-[var(--color-muted)]">Provider</span>
            <select
              className="mt-1 block w-36 rounded-md border border-border bg-[var(--color-background)] px-2 py-1.5"
              value={provider}
              onChange={(event) => setProvider(event.target.value)}
            >
              <option value="smtp">smtp</option>
              <option value="gmail_oauth">gmail_oauth</option>
            </select>
          </label>
          <label className="min-w-48 flex-1 text-sm">
            <span className="text-[var(--color-muted)]">Email address</span>
            <input
              className="mt-1 w-full rounded-md border border-border bg-[var(--color-background)] px-2 py-1.5"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </label>
          <button
            className={buttonClass(true)}
            disabled={busy || !email.trim()}
            onClick={create}
            type="button"
          >
            {busy ? "Adding…" : "Add"}
          </button>
        </div>
      </Card>

      {(notice || error) && (
        <div className="text-sm">
          {error && <p className="text-[var(--color-error)]">{error}</p>}
          {notice && <p className="text-[var(--color-muted)]">{notice}</p>}
        </div>
      )}

      <Card>
        <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--color-muted)]">
          Accounts
        </h3>
        {rows.length === 0 ? (
          <EmptyState title="No accounts" description="Add one above to enable sending." />
        ) : (
          <div className="mt-2 overflow-x-auto rounded-lg border border-border">
            <table className="w-full min-w-[640px] text-sm">
              <thead>
                <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-[var(--color-muted)]">
                  <th className="px-3 py-2">Provider</th>
                  <th className="px-3 py-2">Address</th>
                  <th className="px-3 py-2">Status</th>
                  <th className="px-3 py-2" />
                </tr>
              </thead>
              <tbody>
                {rows.map((account) => (
                  <tr key={account.id} className="border-b border-border/60">
                    <td className="px-3 py-2">{account.provider}</td>
                    <td className="px-3 py-2">{account.email_address}</td>
                    <td className="px-3 py-2">
                      <span className={`text-xs ${statusTone(account.status)}`}>
                        {account.status}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-right">
                      {account.status !== "connected" && (
                        <button
                          className={buttonClass(false)}
                          onClick={() => markConnected(account.id)}
                          type="button"
                        >
                          Mark connected
                        </button>
                      )}{" "}
                      <button
                        className={buttonClass(false)}
                        onClick={() => remove(account.id)}
                        type="button"
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}

function CampaignsPanel() {
  const { csrf } = useSession();
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const campaigns = useQuery({
    queryKey: ["email", "campaigns"],
    queryFn: () => api.get<CampaignList>("/email/campaigns"),
  });

  async function refresh() {
    await queryClient.invalidateQueries({ queryKey: ["email", "campaigns"] });
  }

  async function create() {
    if (!name.trim()) return;
    setBusy(true);
    try {
      await api.post<Campaign>("/email/campaigns", { name: name.trim() }, csrf);
      setName("");
      setNotice("Campaign created.");
      await refresh();
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: string) {
    try {
      await api.delete(`/email/campaigns/${id}`, csrf);
      setNotice("Campaign deleted.");
      await refresh();
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }

  const rows = campaigns.data?.items ?? [];

  return (
    <div className="space-y-4">
      <Card>
        <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--color-muted)]">
          New campaign
        </h3>
        <div className="mt-2 flex flex-wrap items-end gap-3">
          <label className="min-w-48 flex-1 text-sm">
            <span className="text-[var(--color-muted)]">Name</span>
            <input
              className="mt-1 w-full rounded-md border border-border bg-[var(--color-background)] px-2 py-1.5"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Q4 outreach"
            />
          </label>
          <button
            className={buttonClass(true)}
            disabled={busy || !name.trim()}
            onClick={create}
            type="button"
          >
            {busy ? "Creating…" : "Create"}
          </button>
        </div>
      </Card>

      {(notice || error) && (
        <div className="text-sm">
          {error && <p className="text-[var(--color-error)]">{error}</p>}
          {notice && <p className="text-[var(--color-muted)]">{notice}</p>}
        </div>
      )}

      <Card>
        <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--color-muted)]">
          Campaigns
        </h3>
        {rows.length === 0 ? (
          <EmptyState title="No campaigns" description="Create one above." />
        ) : (
          <div className="mt-2 overflow-x-auto rounded-lg border border-border">
            <table className="w-full min-w-[480px] text-sm">
              <thead>
                <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-[var(--color-muted)]">
                  <th className="px-3 py-2">Name</th>
                  <th className="px-3 py-2">Status</th>
                  <th className="px-3 py-2" />
                </tr>
              </thead>
              <tbody>
                {rows.map((campaign) => (
                  <tr key={campaign.id} className="border-b border-border/60">
                    <td className="px-3 py-2">{campaign.name}</td>
                    <td className="px-3 py-2">
                      <span className={`text-xs ${statusTone(campaign.status)}`}>
                        {campaign.status}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-right">
                      <button
                        className={buttonClass(false)}
                        onClick={() => remove(campaign.id)}
                        type="button"
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}

function SuppressionPanel() {
  const { csrf } = useSession();
  const queryClient = useQueryClient();
  const [email, setEmail] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const suppression = useQuery({
    queryKey: ["email", "suppression"],
    queryFn: () => api.get<SuppressionList>("/email/suppression?limit=200"),
  });

  async function refresh() {
    await queryClient.invalidateQueries({ queryKey: ["email", "suppression"] });
  }

  async function add() {
    if (!email.trim()) return;
    setBusy(true);
    try {
      await api.post<SuppressionEntry>(
        "/email/suppression",
        { email_address: email.trim(), reason: reason.trim() || null },
        csrf,
      );
      setEmail("");
      setReason("");
      setNotice("Address suppressed.");
      await refresh();
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: string) {
    try {
      await api.delete(`/email/suppression/${id}`, csrf);
      setNotice("Suppression removed.");
      await refresh();
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }

  const rows = suppression.data?.items ?? [];

  return (
    <div className="space-y-4">
      <Card>
        <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--color-muted)]">
          Suppress an address
        </h3>
        <p className="mt-1 text-xs text-[var(--color-muted)]">
          Suppressed addresses can never be emailed — drafts and sends are refused.
        </p>
        <div className="mt-2 flex flex-wrap items-end gap-3">
          <label className="min-w-48 flex-1 text-sm">
            <span className="text-[var(--color-muted)]">Email address</span>
            <input
              className="mt-1 w-full rounded-md border border-border bg-[var(--color-background)] px-2 py-1.5"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </label>
          <label className="min-w-40 text-sm">
            <span className="text-[var(--color-muted)]">Reason</span>
            <input
              className="mt-1 w-full rounded-md border border-border bg-[var(--color-background)] px-2 py-1.5"
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              placeholder="bounced"
            />
          </label>
          <button
            className={buttonClass(true)}
            disabled={busy || !email.trim()}
            onClick={add}
            type="button"
          >
            {busy ? "Adding…" : "Add"}
          </button>
        </div>
      </Card>

      {(notice || error) && (
        <div className="text-sm">
          {error && <p className="text-[var(--color-error)]">{error}</p>}
          {notice && <p className="text-[var(--color-muted)]">{notice}</p>}
        </div>
      )}

      <Card>
        <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--color-muted)]">
          Suppression list
        </h3>
        {rows.length === 0 ? (
          <EmptyState title="No suppressed addresses" description="" />
        ) : (
          <div className="mt-2 overflow-x-auto rounded-lg border border-border">
            <table className="w-full min-w-[480px] text-sm">
              <thead>
                <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-[var(--color-muted)]">
                  <th className="px-3 py-2">Address</th>
                  <th className="px-3 py-2">Reason</th>
                  <th className="px-3 py-2" />
                </tr>
              </thead>
              <tbody>
                {rows.map((entry) => (
                  <tr key={entry.id} className="border-b border-border/60">
                    <td className="px-3 py-2">{entry.email_address}</td>
                    <td className="px-3 py-2 text-[var(--color-muted)]">{entry.reason ?? "—"}</td>
                    <td className="px-3 py-2 text-right">
                      <button
                        className={buttonClass(false)}
                        onClick={() => remove(entry.id)}
                        type="button"
                      >
                        Remove
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}

function statusTone(status: string): string {
  if (status === "sent" || status === "connected" || status === "active") {
    return "text-[var(--color-success)]";
  }
  if (status === "failed" || status === "rejected" || status === "bounced") {
    return "text-[var(--color-error)]";
  }
  return "text-[var(--color-muted)]";
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
