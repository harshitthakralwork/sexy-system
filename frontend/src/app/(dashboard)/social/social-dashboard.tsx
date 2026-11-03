"use client";

import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { Header } from "@/components/layout/header";
import { Card, EmptyState } from "@/components/ui/card";
import { useSession } from "@/components/providers/session-provider";
import { api } from "@/lib/api/client";
import type {
  SocialContent,
  SocialContentList,
  SocialPlatform,
  SocialResearchQuery,
  SocialResearchQueryList,
  SocialRun,
} from "@/lib/api/types";

const PAGE_SIZE = 25;
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
  const [offset, setOffset] = useState(0);

  const contentParams = useMemo(() => {
    const search = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(offset) });
    if (platformFilter) search.set("platform_slug", platformFilter);
    if (typeFilter) search.set("content_type", typeFilter);
    if (appliedText) search.set("query", appliedText);
    return search.toString();
  }, [platformFilter, typeFilter, appliedText, offset]);

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
    setOffset(0);
  }

  if (!user) return null;

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <Header
        title="Social Intelligence"
        subtitle="Research public conversation on permitted platforms, honestly"
      />

      <main className="flex-1 overflow-y-auto p-4">
        <Card>
          <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--color-muted)]">
            Platform catalogue
          </h3>
          <p className="mt-1 text-sm text-[var(--color-muted)]">
            Cross-platform social intelligence engine. Query public discussions, developer communities, and dorking feeds across all indexed platforms.
          </p>
          <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {(platforms.data ?? []).map((platform) => (
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
                            setNotice(
                              `Run complete: ${run.collected} collected, ${run.stored_new} new, ${run.duplicates} duplicates.`,
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
              <a
                className="rounded-md border border-border px-2.5 py-1.5 text-xs text-[var(--color-muted)] hover:border-[var(--color-primary)]"
                href={`${process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000/api/v1"}/social/content/export?platform_slug=${encodeURIComponent(
                  platformFilter,
                )}&content_type=${encodeURIComponent(typeFilter)}&query=${encodeURIComponent(appliedText)}`}
              >
                Export CSV
              </a>
            </div>

            <div className="mt-2 flex flex-wrap items-end gap-3">
              <label className="text-sm">
                <span className="text-[var(--color-muted)]">Platform</span>
                <select
                  className="mt-1 w-40 rounded-md border border-border bg-[var(--color-background)] px-2 py-1.5"
                  value={platformFilter}
                  onChange={(event) => {
                    setPlatformFilter(event.target.value);
                    setOffset(0);
                  }}
                >
                  <option value="">any</option>
                  {(platforms.data ?? []).map((platform) => (
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
                  onChange={(event) => {
                    setTypeFilter(event.target.value);
                    setOffset(0);
                  }}
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

            {totalContent > PAGE_SIZE && (
              <div className="mt-3 flex items-center justify-between text-sm text-[var(--color-muted)]">
                <span>
                  Showing {totalContent === 0 ? 0 : offset + 1}–
                  {Math.min(offset + PAGE_SIZE, totalContent)} of {totalContent}
                </span>
                <div className="flex gap-2">
                  <button
                    className={buttonClass(false)}
                    disabled={offset === 0}
                    onClick={() => setOffset((value) => Math.max(0, value - PAGE_SIZE))}
                    type="button"
                  >
                    Previous
                  </button>
                  <button
                    className={buttonClass(false)}
                    disabled={offset + PAGE_SIZE >= totalContent}
                    onClick={() => setOffset((value) => value + PAGE_SIZE)}
                    type="button"
                  >
                    Next
                  </button>
                </div>
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
  return (
    <div className="rounded-md border border-border p-3">
      <div className="flex items-center justify-between">
        <span className="font-medium">{platform.name}</span>
        <span
          className={`text-xs ${platform.is_enabled ? "text-[var(--color-success)]" : "text-[var(--color-muted)]"}`}
        >
          {platform.is_enabled ? "available" : "restricted"}
        </span>
      </div>
      <p className="mt-1 text-xs text-[var(--color-muted)]">
        {firstLimitation ?? (platform.is_enabled ? "Permitted public access." : "No permitted access.")}
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
  const [platformSlug, setPlatformSlug] = useState("reddit");
  const [kind, setKind] = useState("search");
  const [primary, setPrimary] = useState("");
  const [terms, setTerms] = useState("");
  const [sort, setSort] = useState("relevance");
  const [limit, setLimit] = useState(25);
  const [busy, setBusy] = useState(false);

  const primaryLabel =
    kind === "search" ? "Search terms" : kind === "subreddit" ? "Subreddit" : "Username";
  const primaryPlaceholder =
    kind === "search" ? "fintech india" : kind === "subreddit" ? "IndiaBusiness" : "someuser";

  async function submit() {
    if (!primary.trim()) return;
    const queryConfig: Record<string, unknown> = { kind, sort, limit };
    if (kind === "search") queryConfig.q = primary.trim();
    else if (kind === "subreddit") {
      queryConfig.subreddit = primary.trim();
      if (terms.trim()) queryConfig.q = terms.trim();
    } else queryConfig.username = primary.trim();

    setBusy(true);
    try {
      const created = await api.post<SocialResearchQuery>(
        "/social/research-queries",
        { platform_slug: platformSlug, query_config: queryConfig },
        csrf,
      );
      setPrimary("");
      setTerms("");
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
        <label className="text-sm">
          <span className="text-[var(--color-muted)]">Kind</span>
          <select
            className="mt-1 w-32 rounded-md border border-border bg-[var(--color-background)] px-2 py-1.5"
            value={kind}
            onChange={(event) => setKind(event.target.value)}
          >
            <option value="search">keyword</option>
            <option value="subreddit">subreddit</option>
            <option value="user">username</option>
          </select>
        </label>
        <label className="min-w-44 flex-1 text-sm">
          <span className="text-[var(--color-muted)]">{primaryLabel}</span>
          <input
            className="mt-1 w-full rounded-md border border-border bg-[var(--color-background)] px-2 py-1.5"
            value={primary}
            onChange={(event) => setPrimary(event.target.value)}
            placeholder={primaryPlaceholder}
          />
        </label>
        {kind === "subreddit" && (
          <label className="min-w-40 flex-1 text-sm">
            <span className="text-[var(--color-muted)]">Search terms (optional)</span>
            <input
              className="mt-1 w-full rounded-md border border-border bg-[var(--color-background)] px-2 py-1.5"
              value={terms}
              onChange={(event) => setTerms(event.target.value)}
            />
          </label>
        )}
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
        {content.published_at ? new Date(content.published_at).toLocaleDateString() : "—"}
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
