"use client";

import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { Header } from "@/components/layout/header";
import { Card, EmptyState } from "@/components/ui/card";
import { useSession } from "@/components/providers/session-provider";
import { api, getApiBase } from "@/lib/api/client";
import type {
  SocialContent,
  SocialContentList,
  SocialPlatform,
  SocialResearchQuery,
  SocialResearchQueryList,
  SocialRun,
} from "@/lib/api/types";

const VALID_SORTS = ["relevance", "hot", "new", "top", "comments"];

/** Social Intelligence: platform catalogue, research queries and results. */
export function SocialDashboard() {
  const { csrf, user } = useSession();
  const queryClient = useQueryClient();

  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Content filters
  const [platformFilter, setPlatformFilter] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [textQuery, setTextQuery] = useState("");
  const [appliedText, setAppliedText] = useState("");
  const [deletingAll, setDeletingAll] = useState(false);

  const contentParams = useMemo(() => {
    const search = new URLSearchParams({ all_results: "true" });
    if (platformFilter) search.set("platform_slug", platformFilter);
    if (typeFilter) search.set("content_type", typeFilter);
    if (appliedText) search.set("query", appliedText);
    return search.toString();
  }, [platformFilter, typeFilter, appliedText]);

  const platforms = useQuery({
    queryKey: ["social", "platforms"],
    queryFn: () => api.get<SocialPlatform[]>("/social/platforms"),
  });

  const queries = useQuery({
    queryKey: ["social", "research-queries"],
    queryFn: () => api.get<SocialResearchQueryList>("/social/research-queries?limit=100"),
  });

  const content = useQuery({
    queryKey: ["social", "content", contentParams],
    queryFn: () => api.get<SocialContentList>(`/social/content?${contentParams}`),
  });

  const enabledPlatforms = (platforms.data ?? []).filter((p) => p.is_enabled);
  const totalContent = content.data?.total ?? 0;
  const rows = content.data?.items ?? [];

  async function invalidateContent() {
    await queryClient.invalidateQueries({ queryKey: ["social", "content"] });
  }

  async function invalidateQueries() {
    await queryClient.invalidateQueries({ queryKey: ["social", "research-queries"] });
  }

  function applyTextFilter() {
    setAppliedText(textQuery.trim());
  }

  async function deleteAllContent() {
    if (!window.confirm(`Delete all ${totalContent} collected results? This cannot be undone.`)) {
      return;
    }
    setDeletingAll(true);
    setError(null);
    try {
      const result = await api.delete<{ deleted: number }>("/social/content", csrf);
      setNotice(`${result.deleted} collected results deleted.`);
      await invalidateContent();
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setDeletingAll(false);
    }
  }

  if (!user) return null;

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <Header
        title="Social Intelligence"
        subtitle="Search public posts from configured sources"
      />

      <main className="flex-1 overflow-y-auto p-4">
        <Card>
          <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--color-muted)]">
            Platform catalogue
          </h3>
          <p className="mt-1 text-sm text-[var(--color-muted)]">
            Search public posts, developer communities, and indexed pages from the sources below.
          </p>
          <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {enabledPlatforms.map((platform) => (
              <PlatformCard key={platform.slug} platform={platform} />
            ))}
          </div>
        </Card>

        <div className="mt-4">
          <CreateQueryForm
            csrf={csrf}
            platforms={enabledPlatforms}
            onCreated={async (message) => {
              setNotice(message);
              await invalidateQueries();
            }}
            onError={setError}
          />
        </div>

        {(notice || error) && (
          <div className="mt-3 text-sm">
            {error && <p className="text-[var(--color-error)]">{error}</p>}
            {notice && <p className="text-[var(--color-muted)]">{notice}</p>}
          </div>
        )}

        <div className="mt-4">
          <Card>
            <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--color-muted)]">
              Research queries
            </h3>
            {(queries.data?.items ?? []).length === 0 ? (
              <EmptyState
                title="No research queries yet"
                description="Create one above, then run it to collect public posts."
              />
            ) : (
              <div className="mt-2 overflow-x-auto rounded-lg border border-border">
                <table className="w-full min-w-[720px] text-sm">
                  <thead>
                    <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-[var(--color-muted)]">
                      <th className="px-3 py-2">Platform</th>
                      <th className="px-3 py-2">Query</th>
                      <th className="px-3 py-2">Last run</th>
                      <th className="px-3 py-2" />
                    </tr>
                  </thead>
                  <tbody>
                    {(queries.data?.items ?? []).map((query) => (
                      <QueryRow
                        key={query.id}
                        query={query}
                        csrf={csrf}
                        onChanged={async (run) => {
                          if (run.status === "deleted") {
                            setNotice("Research query deleted.");
                          } else if (run.status === "completed") {
                            // A previous platform/text filter can hide the rows just collected.
                            // Clear it after a run so the operator sees the run's actual output.
                            setPlatformFilter("");
                            setTypeFilter("");
                            setTextQuery("");
                            setAppliedText("");
                            setNotice(
                              run.collected > 0
                                ? `Run complete: ${run.collected} collected, ${run.stored_new} new, ${run.duplicates} duplicates.`
                                : "Run completed, but the source returned 0 public results for this query. Try broader terms or another platform.",
                            );
                          } else {
                            setNotice(`Run failed: ${run.error ?? "unknown error"}`);
                          }
                          await Promise.all([invalidateQueries(), invalidateContent()]);
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

        <div className="mt-4">
          <Card>
            <div className="flex flex-wrap items-end justify-between gap-3">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--color-muted)]">
                Collected content
              </h3>
              <div className="flex items-center gap-2">
                <span className="text-xs text-[var(--color-muted)]">{totalContent} results</span>
                <a
                  className="rounded-md border border-border px-2.5 py-1.5 text-xs text-[var(--color-muted)] hover:border-[var(--color-primary)]"
                  href={`${getApiBase()}/social/content/export?platform_slug=${encodeURIComponent(
                    platformFilter,
                  )}&content_type=${encodeURIComponent(typeFilter)}&query=${encodeURIComponent(appliedText)}`}
                >
                  Export CSV
                </a>
                <button
                  className="rounded-md border border-[var(--color-error)] px-2.5 py-1.5 text-xs text-[var(--color-error)] disabled:cursor-not-allowed disabled:opacity-50"
                  disabled={totalContent === 0 || deletingAll}
                  onClick={deleteAllContent}
                  type="button"
                >
                  {deletingAll ? "Deleting…" : "Delete all results"}
                </button>
              </div>
            </div>

            <div className="mt-2 flex flex-wrap items-end gap-3">
              <label className="text-sm">
                <span className="text-[var(--color-muted)]">Platform</span>
                <select
                  className="mt-1 w-40 rounded-md border border-border bg-[var(--color-background)] px-2 py-1.5"
                  value={platformFilter}
                  onChange={(event) => setPlatformFilter(event.target.value)}
                >
                  <option value="">any</option>
                  {enabledPlatforms.map((platform) => (
                    <option key={platform.slug} value={platform.slug}>
                      {platform.name}
                    </option>
                  ))}
                </select>
              </label>
              <label className="text-sm">
                <span className="text-[var(--color-muted)]">Type</span>
                <select
                  className="mt-1 w-32 rounded-md border border-border bg-[var(--color-background)] px-2 py-1.5"
                  value={typeFilter}
                  onChange={(event) => setTypeFilter(event.target.value)}
                >
                  <option value="">any</option>
                  <option value="post">post</option>
                  <option value="comment">comment</option>
                  <option value="profile">profile</option>
                  <option value="other">other</option>
                </select>
              </label>
              <label className="min-w-40 flex-1 text-sm">
                <span className="text-[var(--color-muted)]">Search text</span>
                <input
                  className="mt-1 w-full rounded-md border border-border bg-[var(--color-background)] px-2 py-1.5"
                  value={textQuery}
                  onChange={(event) => setTextQuery(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") applyTextFilter();
                  }}
                />
              </label>
              <button className={buttonClass(false)} onClick={applyTextFilter} type="button">
                Apply
              </button>
            </div>

            {content.isError && (
              <p className="mt-3 text-sm text-[var(--color-error)]">
                Content could not be loaded: {errorMessage(content.error)}
              </p>
            )}

            {!content.isPending && rows.length === 0 && !content.isError && (
              <div className="mt-3">
                <EmptyState
                  title="No collected content"
                  description="Run a research query to collect public posts here."
                />
              </div>
            )}

            {rows.length > 0 && (
              <div className="mt-3 overflow-x-auto rounded-lg border border-border">
                <table className="w-full min-w-[860px] text-sm">
                  <thead>
                    <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-[var(--color-muted)]">
                      <th className="px-3 py-2">Platform</th>
                      <th className="px-3 py-2">Author</th>
                      <th className="px-3 py-2">Text</th>
                      <th className="px-3 py-2">Published</th>
                      <th className="px-3 py-2" />
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((item) => (
                      <ContentRow
                        key={item.id}
                        content={item}
                        csrf={csrf}
                        onChanged={async (message) => {
                          setNotice(message);
                          await invalidateContent();
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
      </main>
    </div>
  );
}

function PlatformCard({ platform }: { platform: SocialPlatform }) {
  const firstLimitation = Object.values(platform.limitations).find(
    (value): value is string => typeof value === "string" && value.length > 0,
  );
  const status = !platform.is_enabled
    ? { label: "restricted", tone: "text-[var(--color-muted)]" }
    : platform.health_status === "working"
      ? { label: "working", tone: "text-[var(--color-success)]" }
      : platform.health_status === "failed"
        ? { label: "failing", tone: "text-[var(--color-error)]" }
        : platform.health_status === "degraded"
          ? { label: "degraded", tone: "text-[var(--color-warning)]" }
          : { label: "not tested", tone: "text-[var(--color-muted)]" };
  return (
    <div className="rounded-md border border-border p-3">
      <div className="flex items-center justify-between">
        <span className="font-medium">{platform.name}</span>
        <span className={`text-xs ${status.tone}`}>{status.label}</span>
      </div>
      <p className="mt-1 text-xs text-[var(--color-muted)]">
        {platform.last_error ??
          firstLimitation ??
          (platform.is_enabled ? "Connector installed; run a query to test it." : "No permitted access.")}
      </p>
    </div>
  );
}

function CreateQueryForm({
  csrf,
  platforms,
  onCreated,
  onError,
}: {
  csrf: string | null;
  platforms: SocialPlatform[];
  onCreated: (message: string) => Promise<void>;
  onError: (message: string) => void;
}) {
  const [platformSlug, setPlatformSlug] = useState("facebook");
  const [primary, setPrimary] = useState("");
  const [sort, setSort] = useState("relevance");
  const [limit, setLimit] = useState(25);
  const [busy, setBusy] = useState(false);

  async function submit() {
    if (!primary.trim()) return;
    const queryConfig: Record<string, unknown> = { kind: "keyword", q: primary.trim(), sort, limit };

    setBusy(true);
    try {
      const created = await api.post<SocialResearchQuery>(
        "/social/research-queries",
        { platform_slug: platformSlug, query_config: queryConfig },
        csrf,
      );
      setPrimary("");
      await onCreated(`Created research query on ${created.platform_slug}.`);
    } catch (caught) {
      onError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--color-muted)]">
        Create a research query
      </h3>
      <div className="mt-2 flex flex-wrap items-end gap-3">
        <label className="text-sm">
          <span className="text-[var(--color-muted)]">Platform</span>
          <select
            className="mt-1 w-36 rounded-md border border-border bg-[var(--color-background)] px-2 py-1.5"
            value={platformSlug}
            onChange={(event) => setPlatformSlug(event.target.value)}
          >
            {platforms.map((platform) => (
              <option key={platform.slug} value={platform.slug}>
                {platform.name}
              </option>
            ))}
          </select>
        </label>
        <label className="min-w-44 flex-1 text-sm">
          <span className="text-[var(--color-muted)]">Search terms</span>
          <input
            className="mt-1 w-full rounded-md border border-border bg-[var(--color-background)] px-2 py-1.5"
            value={primary}
            onChange={(event) => setPrimary(event.target.value)}
            placeholder="web design agency india"
          />
        </label>
        <label className="text-sm">
          <span className="text-[var(--color-muted)]">Sort</span>
          <select
            className="mt-1 w-28 rounded-md border border-border bg-[var(--color-background)] px-2 py-1.5"
            value={sort}
            onChange={(event) => setSort(event.target.value)}
          >
            {VALID_SORTS.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>
        <label className="text-sm">
          <span className="text-[var(--color-muted)]">Limit</span>
          <input
            className="mt-1 w-20 rounded-md border border-border bg-[var(--color-background)] px-2 py-1.5"
            type="number"
            min={1}
            max={100}
            value={limit}
            onChange={(event) => setLimit(Number(event.target.value) || 25)}
          />
        </label>
        <button
          className={buttonClass(true)}
          disabled={busy || !primary.trim() || platforms.length === 0}
          onClick={submit}
          type="button"
        >
          {busy ? "Creating…" : "Create"}
        </button>
      </div>
    </Card>
  );
}

function QueryRow({
  query,
  csrf,
  onChanged,
  onError,
}: {
  query: SocialResearchQuery;
  csrf: string | null;
  onChanged: (run: SocialRun) => Promise<void>;
  onError: (message: string) => void;
}) {
  const [running, setRunning] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const summary = describeConfig(query.query_config);

  async function run() {
    setRunning(true);
    try {
      const result = await api.post<SocialRun>(
        `/social/research-queries/${query.id}/run`,
        undefined,
        csrf,
        60_000,
      );
      await onChanged(result);
    } catch (caught) {
      onError(errorMessage(caught));
    } finally {
      setRunning(false);
    }
  }

  async function remove() {
    setDeleting(true);
    try {
      await api.delete(`/social/research-queries/${query.id}`, csrf);
      await onChanged({ query_id: query.id, platform_slug: query.platform_slug, status: "deleted", collected: 0, stored_new: 0, duplicates: 0, error: null });
    } catch (caught) {
      onError(errorMessage(caught));
      setDeleting(false);
    }
  }

  return (
    <tr className="border-b border-border/60 hover:bg-[var(--color-surface)]">
      <td className="px-3 py-2">{query.platform_slug}</td>
      <td className="px-3 py-2 text-[var(--color-muted)]">{summary}</td>
      <td className="px-3 py-2">
        {query.last_run_status ? (
          <span
            className={`text-xs ${query.last_run_status === "completed" ? "text-[var(--color-success)]" : "text-[var(--color-error)]"}`}
          >
            {query.last_run_status}
          </span>
        ) : (
          <span className="text-xs text-[var(--color-muted)]">never run</span>
        )}
      </td>
      <td className="px-3 py-2 text-right">
        <button className={buttonClass(false)} disabled={running} onClick={run} type="button">
          {running ? "Running…" : "Run"}
        </button>{" "}
        <button className={buttonClass(false)} disabled={deleting} onClick={remove} type="button">
          {deleting ? "Deleting…" : "Delete"}
        </button>
      </td>
    </tr>
  );
}

function ContentRow({
  content,
  csrf,
  onChanged,
  onError,
}: {
  content: SocialContent;
  csrf: string | null;
  onChanged: (message: string) => Promise<void>;
  onError: (message: string) => void;
}) {
  const [deleting, setDeleting] = useState(false);
  const [linking, setLinking] = useState(false);
  const [businessId, setBusinessId] = useState("");

  async function remove() {
    setDeleting(true);
    try {
      await api.delete(`/social/content/${content.id}`, csrf);
      await onChanged("Content deleted.");
    } catch (caught) {
      onError(errorMessage(caught));
      setDeleting(false);
    }
  }

  async function link() {
    if (!businessId.trim()) return;
    setLinking(true);
    try {
      await api.post(
        `/social/content/${content.id}/link`,
        { business_id: businessId.trim() },
        csrf,
      );
      setBusinessId("");
      await onChanged("Linked to business.");
    } catch (caught) {
      onError(errorMessage(caught));
      setLinking(false);
    }
  }

  const snippet = (content.content_text ?? "").slice(0, 140);

  return (
    <tr className="border-b border-border/60 align-top hover:bg-[var(--color-surface)]">
      <td className="px-3 py-2">{content.platform_slug}</td>
      <td className="px-3 py-2 text-[var(--color-muted)]">{content.author_username ?? "—"}</td>
      <td className="max-w-[360px] px-3 py-2">
        {content.content_url ? (
          <a
            className="text-[var(--color-foreground)] underline-offset-2 hover:underline"
            href={content.content_url}
            target="_blank"
            rel="noreferrer"
          >
            {snippet || content.content_url}
          </a>
        ) : (
          snippet || "—"
        )}
      </td>
      <td className="px-3 py-2 text-[var(--color-muted)]">
        {content.published_at ? new Date(content.published_at).toLocaleDateString() : "Not provided"}
      </td>
      <td className="px-3 py-2 text-right">
        <div className="flex items-center justify-end gap-2">
          <input
            className="w-36 rounded-md border border-border bg-[var(--color-background)] px-2 py-1 text-xs"
            placeholder="business id"
            value={businessId}
            onChange={(event) => setBusinessId(event.target.value)}
          />
          <button
            className={buttonClass(false)}
            disabled={linking || !businessId.trim()}
            onClick={link}
            type="button"
          >
            {linking ? "Linking…" : "Link"}
          </button>
          <button className={buttonClass(false)} disabled={deleting} onClick={remove} type="button">
            {deleting ? "Deleting…" : "Delete"}
          </button>
        </div>
      </td>
    </tr>
  );
}

function describeConfig(config: Record<string, unknown>): string {
  const kind = String(config.kind ?? "search");
  if (kind === "search") return `keyword: ${String(config.q ?? "")}`;
  if (kind === "subreddit") {
    const sub = String(config.subreddit ?? "");
    const q = config.q ? `, q: ${String(config.q)}` : "";
    return `r/${sub}${q}`;
  }
  return `user: ${String(config.username ?? "")}`;
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
