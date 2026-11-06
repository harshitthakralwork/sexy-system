"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Search,
  Flame,
  ExternalLink,
  RefreshCw,
  X,
  CheckCircle2,
  AlertCircle,
  Clock,
  ChevronRight,
  User,
  MessageSquare,
  Share2,
  Download,
} from "lucide-react";

import { Header } from "@/components/layout/header";
import { AppFooter } from "@/components/layout/app-footer";
import { useSession } from "@/components/providers/session-provider";
import { api } from "@/lib/api/client";
import type { PostItem, PostListResponse, PostAnnotation } from "@/lib/api/types";
import { cn } from "@/lib/utils";

const CATEGORIES = [
  "All Categories",
  "Service needed",
  "Freelancer hiring",
  "Vendor search",
  "Recommendation request",
  "Project help",
  "Job hiring",
  "General discussion",
  "Not relevant",
];

const PLATFORMS = [
  { id: "all",        label: "All Platforms" },
  { id: "x",          label: "X (Twitter)"   },
  { id: "facebook",   label: "Facebook"      },
  { id: "instagram",  label: "Instagram"     },
];

const SERVICE_TAGS = [
  { id: "all",             label: "All Services"   },
  { id: "web-development", label: "Web Dev"        },
  { id: "mobile-app",      label: "Mobile Apps"    },
  { id: "ai-automation",   label: "AI & Automation"},
  { id: "seo-marketing",   label: "SEO & Growth"   },
  { id: "ui-ux-design",    label: "UI / UX"        },
  { id: "local-services",  label: "Local Services" },
];

const LEAD_STAGES = [
  { id: "new",           label: "New Lead",       cls: "bg-white/10 text-white/60 border-white/15"             },
  { id: "contacted",     label: "Contacted",      cls: "bg-sky-500/15 text-sky-300 border-sky-400/30"          },
  { id: "qualified",     label: "Qualified",      cls: "bg-emerald-500/15 text-emerald-300 border-emerald-400/30"},
  { id: "proposal_sent", label: "Proposal Sent",  cls: "bg-amber-500/15 text-amber-300 border-amber-400/30"    },
  { id: "closed_won",    label: "Won (Client)",   cls: "bg-lime-500/15 text-lime-300 border-lime-400/30"       },
  { id: "closed_lost",   label: "Lost / Closed",  cls: "bg-rose-500/15 text-rose-300 border-rose-400/30"       },
];

// ── Shared select style ───────────────────────────────────────────────────────
const selectCls =
  "rounded-xl border border-white/[0.14] bg-[#1a1a1a] text-[#f3f4f6] px-3 py-1.5 text-xs focus:outline-none focus:border-blue-500 cursor-pointer transition-all";

export function PostExplorerView() {
  const { user, csrf } = useSession();
  const queryClient = useQueryClient();

  const [searchTerm,         setSearchTerm]         = useState("");
  const [selectedCategory,   setSelectedCategory]   = useState("All Categories");
  const [selectedPlatform,   setSelectedPlatform]   = useState("all");
  const [selectedServiceTag, setSelectedServiceTag] = useState("all");
  const [selectedLeadStatus, setSelectedLeadStatus] = useState("all");
  const [isHotOnly,          setIsHotOnly]          = useState(false);
  const [retrievalStatus,    setRetrievalStatus]    = useState("all");
  const [minScore,           setMinScore]           = useState<number>(0);
  const [sortBy]                                 = useState("discovered_at");
  const [sortDesc]                               = useState(true);
  const [page,               setPage]               = useState(0);
  const pageSize = 20;

  const [selectedPostIds, setSelectedPostIds] = useState<Set<string>>(new Set());
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [activePost,      setActivePost]      = useState<PostItem | null>(null);
  const [drawerTab,       setDrawerTab]       = useState<"provenance" | "annotation">("provenance");

  const [editAnnotation, setEditAnnotation] = useState<PostAnnotation>({
    lead_status: "new",
    is_hot: false,
    follow_up_date: null,
    user_note: "",
    quoted_customer_need: "",
    services_to_sell: [],
    is_saved: false,
  });

  const { data, isLoading, isFetching } = useQuery({
    queryKey: [
      "social-posts", searchTerm, selectedCategory, selectedPlatform,
      selectedServiceTag, selectedLeadStatus, isHotOnly, retrievalStatus,
      minScore, sortBy, sortDesc, page,
    ],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (searchTerm.trim())               params.set("q",                searchTerm.trim());
      if (selectedCategory !== "All Categories") params.set("intent",     selectedCategory);
      if (selectedPlatform !== "all")      params.set("platform",         selectedPlatform);
      if (selectedServiceTag !== "all")    params.set("service_tag",      selectedServiceTag);
      if (selectedLeadStatus !== "all")    params.set("lead_status",      selectedLeadStatus);
      if (isHotOnly)                       params.set("is_hot",           "true");
      if (retrievalStatus !== "all")       params.set("retrieval_status", retrievalStatus);
      if (minScore > 0)                    params.set("min_confidence",   (minScore / 100).toFixed(2));
      params.set("sort_by",   sortBy);
      params.set("sort_desc", String(sortDesc));
      params.set("limit",     String(pageSize));
      params.set("offset",    String(page * pageSize));
      return api.get<PostListResponse>(`/social/posts?${params.toString()}`);
    },
    enabled: !!user,
  });

  const handleOpenPost = (post: PostItem) => {
    setActivePost(post);
    setEditAnnotation({
      lead_status:          post.user_annotation?.lead_status          || "new",
      is_hot:               post.user_annotation?.is_hot               || false,
      follow_up_date:       post.user_annotation?.follow_up_date       || null,
      user_note:            post.user_annotation?.user_note            || "",
      quoted_customer_need: post.user_annotation?.quoted_customer_need || "",
      services_to_sell:     post.user_annotation?.services_to_sell     || [],
      is_saved:             post.user_annotation?.is_saved             || false,
    });
  };

  const updateAnnotationMutation = useMutation({
    mutationFn: async ({ postId, annotation }: { postId: string; annotation: PostAnnotation }) =>
      api.patch<PostAnnotation>(`/social/posts/${postId}/annotation`, annotation, csrf),
    onSuccess: (updatedAnnotation) => {
      queryClient.invalidateQueries({ queryKey: ["social-posts"] });
      queryClient.invalidateQueries({ queryKey: ["leads-dashboard"] });
      if (activePost) setActivePost({ ...activePost, user_annotation: updatedAnnotation });
    },
  });

  const retryFetchMutation = useMutation({
    mutationFn: async (postId: string) =>
      api.post<PostItem>(`/social/posts/${postId}/retry-fetch`, {}, csrf),
    onSuccess: (updatedPost) => {
      queryClient.invalidateQueries({ queryKey: ["social-posts"] });
      setActivePost(updatedPost);
    },
  });

  const bulkActionMutation = useMutation({
    mutationFn: async ({ action, value }: { action: string; value?: string }) =>
      api.post(`/social/posts/bulk-action`, { post_ids: Array.from(selectedPostIds), action, value }, csrf),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["social-posts"] });
      queryClient.invalidateQueries({ queryKey: ["leads-dashboard"] });
      setSelectedPostIds(new Set());
    },
  });

  const toggleSelectPost = (id: string) => {
    setSelectedPostIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (!data?.items) return;
    if (selectedPostIds.size === data.items.length) setSelectedPostIds(new Set());
    else setSelectedPostIds(new Set(data.items.map((p) => p.id)));
  };

  const handleExportCSV = () => {
    if (!data?.items) return;
    const items = selectedPostIds.size > 0
      ? data.items.filter((p) => selectedPostIds.has(p.id))
      : data.items;
    const headers = ["ID","Platform","Author","Title / Snippet","Category","Client Score","Lead Status","Is Hot","URL","Discovered At"];
    const rows = items.map((p) => [
      p.id, p.platform,
      p.author_name || p.author_username || "Anonymous",
      `"${(p.page_title || p.search_snippet || "").replace(/"/g, '""')}"`,
      p.classification_category || "Unclassified",
      p.classification_score ?? "N/A",
      p.user_annotation?.lead_status || "new",
      p.user_annotation?.is_hot ? "Yes" : "No",
      p.original_url || p.canonical_url || "",
      p.first_discovered_at,
    ]);
    const csv  = "data:text/csv;charset=utf-8," + [headers.join(","), ...rows.map((r) => r.join(","))].join("\n");
    const link = document.createElement("a");
    link.setAttribute("href", encodeURI(csv));
    link.setAttribute("download", `posts_intelligence_${new Date().toISOString().slice(0, 10)}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const handleDeleteSelected = async () => {
    if (selectedPostIds.size === 0 || !window.confirm(`Delete ${selectedPostIds.size} selected posts?`)) return;
    setDeleteBusy(true);
    try {
      await api.post("/social/posts/bulk-action", { post_ids: Array.from(selectedPostIds), action: "delete" }, csrf);
      setSelectedPostIds(new Set());
      await queryClient.invalidateQueries({ queryKey: ["social-posts"] });
    } finally {
      setDeleteBusy(false);
    }
  };

  const handleDeleteAll = async () => {
    if (!window.confirm("Delete all discovered posts? This cannot be undone.")) return;
    setDeleteBusy(true);
    try {
      await api.post("/social/posts/bulk-action", { post_ids: [], action: "delete_all" }, csrf);
      setSelectedPostIds(new Set());
      await queryClient.invalidateQueries({ queryKey: ["social-posts"] });
    } finally {
      setDeleteBusy(false);
    }
  };

  if (!user) return null;

  return (
    <div className="flex min-h-0 flex-1 flex-col bg-transparent text-white">
      <Header title="Lead & Post Intelligence" subtitle="Post Explorer" />

      <main className="flex-1 overflow-y-auto p-4 sm:p-6">
        <div className="mx-auto max-w-7xl space-y-4">

          {/* ── Filter Bar ── */}
          <div className="refraction-glass-card rounded-[24px] p-5 space-y-4 animate-slide-up">
            <div className="flex flex-col md:flex-row gap-3 items-stretch md:items-center justify-between">
              {/* Search */}
              <div className="relative flex-1">
                <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-white/35" />
                <input
                  type="text"
                  placeholder="Search intent keywords, client problems, job posts…"
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="refraction-glass-input w-full rounded-[14px] pl-10 pr-4 py-2.5 text-sm"
                />
              </div>

              {/* Quick actions */}
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setIsHotOnly(!isHotOnly)}
                  className={cn(
                    "refraction-glass-btn flex items-center gap-1.5 rounded-full px-4 py-2 text-xs font-semibold transition-all",
                    isHotOnly
                      ? "border-rose-500/40 bg-rose-500/20 text-rose-300 shadow-[0_0_18px_rgba(248,113,113,0.25)]"
                      : "text-white/60 hover:text-white"
                  )}
                >
                  <Flame className={cn("w-3.5 h-3.5", isHotOnly ? "text-rose-400" : "")} />
                  Hot Leads
                </button>
                <button
                  type="button"
                  onClick={handleExportCSV}
                  className="refraction-glass-btn flex items-center gap-1.5 rounded-full px-4 py-2 text-xs font-semibold text-white/60 hover:text-white"
                >
                  <Download className="w-3.5 h-3.5" />
                  Export
                </button>
                <button type="button" disabled={deleteBusy || selectedPostIds.size === 0} onClick={handleDeleteSelected} className="refraction-glass-btn rounded-full px-4 py-2 text-xs font-semibold text-rose-300 disabled:opacity-40">
                  Delete selected ({selectedPostIds.size})
                </button>
                <button type="button" disabled={deleteBusy} onClick={handleDeleteAll} className="refraction-glass-btn rounded-full px-4 py-2 text-xs font-semibold text-rose-300 disabled:opacity-40">
                  Delete all
                </button>
              </div>
            </div>

            {/* Filter selects */}
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2.5 pt-2 border-t border-white/[0.07]">
              <select value={selectedCategory} onChange={(e) => setSelectedCategory(e.target.value)} className={selectCls}>
                {CATEGORIES.map((c) => <option key={c} value={c} className="bg-[#1a1a1a] text-[#f3f4f6]">{c}</option>)}
              </select>
              <select value={selectedPlatform} onChange={(e) => setSelectedPlatform(e.target.value)} className={selectCls}>
                {PLATFORMS.map((p) => <option key={p.id} value={p.id} className="bg-[#1a1a1a] text-[#f3f4f6]">{p.label}</option>)}
              </select>
              <select value={selectedLeadStatus} onChange={(e) => setSelectedLeadStatus(e.target.value)} className={selectCls}>
                <option value="all" className="bg-[#1a1a1a] text-[#f3f4f6]">All Lead Stages</option>
                {LEAD_STAGES.map((s) => <option key={s.id} value={s.id} className="bg-[#1a1a1a] text-[#f3f4f6]">{s.label}</option>)}
              </select>
              <select value={selectedServiceTag} onChange={(e) => setSelectedServiceTag(e.target.value)} className={selectCls}>
                {SERVICE_TAGS.map((t) => <option key={t.id} value={t.id} className="bg-[#1a1a1a] text-[#f3f4f6]">{t.label}</option>)}
              </select>
              <select value={retrievalStatus} onChange={(e) => setRetrievalStatus(e.target.value)} className={selectCls}>
                <option value="all" className="bg-[#1a1a1a] text-[#f3f4f6]">All Retrieval</option>
                <option value="full_text" className="bg-[#1a1a1a] text-[#f3f4f6]">Full Text</option>
                <option value="snippet_only" className="bg-[#1a1a1a] text-[#f3f4f6]">Snippet Only</option>
                <option value="blocked" className="bg-[#1a1a1a] text-[#f3f4f6]">Blocked</option>
                <option value="failed" className="bg-[#1a1a1a] text-[#f3f4f6]">Failed</option>
              </select>
              <div className="refraction-glass-input flex items-center gap-1.5 rounded-[12px] px-2.5 py-1 text-xs text-white/50">
                <span className="shrink-0">Score:</span>
                <input
                  type="range" min="0" max="100" step="5"
                  value={minScore}
                  onChange={(e) => setMinScore(Number(e.target.value))}
                  className="w-full accent-[#FF7849] h-1.5 cursor-pointer"
                />
                <span className="font-mono text-white/80 shrink-0 w-7 text-right">{minScore}+</span>
              </div>
            </div>
          </div>

          {/* ── Bulk Action Strip ── */}
          {selectedPostIds.size > 0 && (
            <div className="refraction-glass-card rounded-[18px] px-5 py-3 flex items-center justify-between border-[#FF7849]/30 shadow-[0_0_24px_rgba(255,120,73,0.15)] animate-slide-up">
              <span className="text-xs font-semibold text-white/70">
                {selectedPostIds.size} post{selectedPostIds.size > 1 ? "s" : ""} selected
              </span>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => bulkActionMutation.mutate({ action: "mark_hot", value: "true" })}
                  className="refraction-glass-btn inline-flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-xs font-semibold text-rose-300 border-rose-500/30"
                >
                  <Flame className="w-3 h-3" /> Mark Hot
                </button>
                <button
                  type="button"
                  onClick={() => bulkActionMutation.mutate({ action: "set_lead_status", value: "qualified" })}
                  className="refraction-glass-btn rounded-full px-3.5 py-1.5 text-xs font-semibold text-emerald-300 border-emerald-500/30"
                >
                  Qualify
                </button>
                <button
                  type="button"
                  onClick={() => bulkActionMutation.mutate({ action: "set_lead_status", value: "contacted" })}
                  className="refraction-glass-btn rounded-full px-3.5 py-1.5 text-xs font-semibold text-sky-300 border-sky-500/30"
                >
                  Contacted
                </button>
                <button
                  type="button"
                  onClick={() => setSelectedPostIds(new Set())}
                  className="text-xs text-white/35 hover:text-white px-2 transition-colors"
                >
                  Clear
                </button>
              </div>
            </div>
          )}

          {/* ── Posts Table ── */}
          <div className="refraction-glass-card rounded-[24px] overflow-hidden animate-slide-up" style={{ animationDelay: "60ms" }}>
            {/* Table header */}
            <div className="px-5 py-3.5 border-b border-white/[0.07] flex items-center gap-3 bg-white/[0.02]">
              <input
                type="checkbox"
                checked={!!data?.items?.length && selectedPostIds.size === data.items.length}
                onChange={toggleSelectAll}
                className="rounded border-white/20 accent-[#FF7849] cursor-pointer"
              />
              <span className="text-[10px] font-bold uppercase tracking-widest text-white/40">
                Discovered Posts ({data?.total ?? 0})
              </span>
              {isFetching && (
                <span className="ml-auto flex items-center gap-1.5 text-[11px] text-white/40 animate-pulse">
                  <RefreshCw className="w-3 h-3 animate-spin text-[#FF7849]" /> Updating…
                </span>
              )}
            </div>

            {isLoading ? (
              <div className="p-10 space-y-2.5">
                {[0,1,2,3,4].map((i) => (
                  <div key={i} className="skeleton h-16 w-full" style={{ animationDelay: `${i * 60}ms` }} />
                ))}
              </div>
            ) : !data?.items?.length ? (
              <div className="p-12 text-center">
                <p className="text-sm text-white/70 font-medium">No posts matched your filters</p>
                <p className="text-xs text-white/35 mt-1">Try relaxing category or search keyword constraints.</p>
              </div>
            ) : (
              <div className="divide-y divide-white/[0.05]">
                {data.items.map((post, i) => {
                  const isSelected = selectedPostIds.has(post.id);
                  const leadStage  = LEAD_STAGES.find((s) => s.id === post.user_annotation?.lead_status) || LEAD_STAGES[0];

                  return (
                    <div
                      key={post.id}
                      className={cn(
                        "p-4 flex items-start gap-3.5 transition-colors animate-slide-up",
                        isSelected ? "bg-white/[0.045]" : "hover:bg-white/[0.025]"
                      )}
                      style={{ animationDelay: `${i * 25}ms` }}
                    >
                      <input
                        type="checkbox"
                        checked={isSelected}
                        onChange={() => toggleSelectPost(post.id)}
                        className="mt-1 rounded border-white/20 accent-[#FF7849] cursor-pointer shrink-0"
                      />

                      <div className="flex-1 min-w-0 space-y-2">
                        {/* Badge row */}
                        <div className="flex flex-wrap items-center gap-2 text-xs">
                          <span className="px-2 py-0.5 rounded-full text-[9px] font-bold uppercase tracking-wider border border-white/15 bg-white/[0.06] text-white/70">
                            {post.platform}
                          </span>
                          <span className={cn(
                            "px-2 py-0.5 rounded-full font-medium text-[10px] border",
                            (post.classification_score ?? 0) >= 60
                              ? "bg-emerald-500/15 text-emerald-300 border-emerald-500/30"
                              : "bg-white/[0.04] text-white/40 border-white/10"
                          )}>
                            {post.classification_category || "Unclassified"} · {post.classification_score ?? "—"}
                          </span>
                          <span className={cn("px-2 py-0.5 rounded-full text-[10px] font-semibold border", leadStage.cls)}>
                            {leadStage.label}
                          </span>
                          {post.user_annotation?.is_hot && (
                            <span className="flex items-center gap-0.5 text-xs text-rose-400 font-bold">
                              <Flame className="w-3 h-3 fill-rose-500 text-rose-500" /> Hot
                            </span>
                          )}
                          {post.retrieval_status === "full_text" ? (
                            <span className="text-[10px] text-emerald-400 flex items-center gap-1 font-mono">
                              <CheckCircle2 className="w-3 h-3" /> Full Text
                            </span>
                          ) : (
                            <span className="text-[10px] text-white/35 flex items-center gap-1 font-mono">
                              <Clock className="w-3 h-3" /> Snippet Only
                            </span>
                          )}
                          <span className="text-[10px] text-white/35 flex items-center gap-1 ml-auto">
                            <User className="w-3 h-3 opacity-60" />
                            {post.author_name || post.author_username || "Anonymous"}
                          </span>
                        </div>

                        {/* Title + snippet */}
                        <div onClick={() => handleOpenPost(post)} className="cursor-pointer group">
                          {post.page_title && (
                            <h4 className="text-sm font-semibold text-white group-hover:text-[#FF7849] transition-colors line-clamp-1">
                              {post.page_title}
                            </h4>
                          )}
                          <p className="text-xs text-white/45 line-clamp-2 mt-0.5 group-hover:text-white/70 transition-colors">
                            {post.search_snippet || post.extracted_full_text || "No preview snippet available."}
                          </p>
                        </div>

                        {/* Footer */}
                        <div className="flex flex-wrap items-center gap-3 pt-0.5 text-[10px] text-white/35">
                          {post.service_tags?.map((tag) => (
                            <span key={tag} className="bg-white/[0.04] px-2 py-0.5 rounded border border-white/[0.07]">
                              #{tag}
                            </span>
                          ))}
                          <div className="flex items-center gap-3 ml-auto">
                            {post.comments_count !== null && (
                              <span className="flex items-center gap-1"><MessageSquare className="w-3 h-3" /> {post.comments_count}</span>
                            )}
                            {post.reactions_count !== null && (
                              <span className="flex items-center gap-1"><Share2 className="w-3 h-3" /> {post.reactions_count}</span>
                            )}
                            <button
                              type="button"
                              onClick={() => handleOpenPost(post)}
                              className="refraction-glass-btn inline-flex items-center gap-1 rounded-full px-3 py-1 text-[10px] font-bold text-[#FF7849] hover:text-orange-300"
                            >
                              Inspect <ChevronRight className="w-3 h-3" />
                            </button>
                          </div>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}

            {/* Pagination */}
            {!!data?.total && data.total > pageSize && (
              <div className="px-5 py-3.5 border-t border-white/[0.07] flex items-center justify-between text-xs text-white/40 bg-white/[0.015]">
                <span>
                  Showing {page * pageSize + 1}–{Math.min((page + 1) * pageSize, data.total)} of {data.total}
                </span>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    disabled={page === 0}
                    onClick={() => setPage(page - 1)}
                    className="refraction-glass-btn rounded-full px-4 py-1.5 text-xs font-semibold text-white/70 hover:text-white disabled:opacity-35"
                  >
                    Previous
                  </button>
                  <button
                    type="button"
                    disabled={(page + 1) * pageSize >= data.total}
                    onClick={() => setPage(page + 1)}
                    className="refraction-glass-btn rounded-full px-4 py-1.5 text-xs font-semibold text-white/70 hover:text-white disabled:opacity-35"
                  >
                    Next
                  </button>
                </div>
              </div>
            )}
          </div>
          <AppFooter />
        </div>
      </main>

      {/* ── Detail Drawer ── */}
      {activePost && (
        <div className="fixed inset-0 z-50 overflow-hidden bg-black/55 backdrop-blur-sm flex justify-end">
          <div className="w-full max-w-2xl refraction-glass-card border-l border-white/[0.14] h-full flex flex-col shadow-2xl animate-slide-up" style={{ borderRadius: 0 }}>

            {/* Drawer header */}
            <div className="px-5 py-4 border-b border-white/[0.08] flex items-start justify-between">
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <span className="px-2 py-0.5 rounded-full text-[9px] font-bold uppercase tracking-wider border border-white/15 bg-white/[0.06] text-white/70">
                    {activePost.platform}
                  </span>
                  <span className="text-[10px] text-white/35 font-mono">ID: {activePost.external_id}</span>
                </div>
                <h3 className="text-sm font-bold text-white line-clamp-1">
                  {activePost.page_title || "Discovered Post Details"}
                </h3>
              </div>
              <button
                type="button"
                onClick={() => setActivePost(null)}
                className="p-1.5 text-white/40 hover:text-white rounded-lg hover:bg-white/[0.08] transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Drawer tabs */}
            <div className="flex border-b border-white/[0.07] px-5 gap-6 text-xs font-semibold">
              {(["provenance", "annotation"] as const).map((tab) => (
                <button
                  key={tab}
                  type="button"
                  onClick={() => setDrawerTab(tab)}
                  className={cn(
                    "py-3 border-b-2 transition-colors capitalize",
                    drawerTab === tab
                      ? "border-[#FF7849] text-white"
                      : "border-transparent text-white/40 hover:text-white"
                  )}
                >
                  {tab === "annotation" ? "CRM & Sales Annotation" : "Post Provenance & Full Text"}
                </button>
              ))}
            </div>

            {/* Drawer body */}
            <div className="flex-1 overflow-y-auto p-6 space-y-6 text-sm">
              {drawerTab === "provenance" ? (
                <>
                  {/* Source block */}
                  <Section label="Source & Provenance">
                    <div className="space-y-2.5 text-xs">
                      <Row label="Original URL">
                        {activePost.original_url ? (
                          <a href={activePost.original_url} target="_blank" rel="noopener noreferrer"
                            className="text-[#FF7849] hover:underline flex items-center gap-1 truncate max-w-xs">
                            {activePost.original_url} <ExternalLink className="w-3 h-3 shrink-0" />
                          </a>
                        ) : <span className="text-white/35">Unknown</span>}
                      </Row>
                      <Row label="Author">
                        <span>{activePost.author_name || activePost.author_username || "Anonymous"}</span>
                      </Row>
                      <Row label="Discovered At">
                        <span className="font-mono">{new Date(activePost.first_discovered_at).toLocaleString()}</span>
                      </Row>
                      <Row label="Extraction Method">
                        <span className="font-mono text-emerald-400">{activePost.extraction_method || "searxng_snippet"}</span>
                      </Row>
                    </div>
                  </Section>

                  {/* Snippet */}
                  <Section label="Search Engine Snippet" badge={<Badge color="amber">From search result</Badge>}>
                    <pre className="refraction-glass-input rounded-[14px] p-3 text-xs text-white/55 font-mono leading-relaxed whitespace-pre-wrap">
                      {activePost.search_snippet || "No snippet returned by search engine."}
                    </pre>
                  </Section>

                  {/* Full text */}
                  <Section
                    label="Extracted Full Text"
                    badge={
                      <div className="flex items-center gap-2">
                        {activePost.retrieval_status === "full_text" ? (
                          <Badge color="emerald"><CheckCircle2 className="w-3 h-3" /> Direct page fetch</Badge>
                        ) : (
                          <Badge color="rose"><AlertCircle className="w-3 h-3" /> {activePost.retrieval_status}</Badge>
                        )}
                        <button
                          type="button"
                          disabled={retryFetchMutation.isPending}
                          onClick={() => retryFetchMutation.mutate(activePost.id)}
                          className="refraction-glass-btn inline-flex items-center gap-1 rounded-full px-3 py-1 text-[10px] font-semibold text-white/70 hover:text-white"
                        >
                          <RefreshCw className={cn("w-3 h-3", retryFetchMutation.isPending && "animate-spin")} />
                          Fetch Page
                        </button>
                      </div>
                    }
                  >
                    <div className="refraction-glass-input rounded-[14px] p-4 text-xs text-white/70 leading-relaxed whitespace-pre-wrap max-h-64 overflow-y-auto">
                      {activePost.extracted_full_text || (
                        <div className="text-center py-4 text-white/35 space-y-1">
                          <p>Full text has not been extracted.</p>
                          <p className="text-[10px]">Reason: {activePost.retrieval_error || "Platform login wall or snippet-only result."}</p>
                        </div>
                      )}
                    </div>
                  </Section>

                  {/* Scoring */}
                  <Section label="Scoring & Evidence Breakdown">
                    <div className="space-y-2.5 text-xs">
                      <Row label="Potential Client Score">
                        <span className="font-bold text-[#FF7849] font-mono text-sm">
                          {activePost.classification_score ?? "—"} / 100
                        </span>
                      </Row>
                      <Row label="Intent Category">
                        <span className="font-medium">{activePost.classification_category || "Unclassified"}</span>
                      </Row>
                      <div className="pt-2 border-t border-white/[0.07]">
                        <span className="text-white/35 text-[10px]">Matched Buying Phrases:</span>
                        <div className="flex flex-wrap gap-1.5 mt-1.5">
                          {activePost.matched_phrases?.length ? (
                            activePost.matched_phrases.map((term, i) => (
                              <span key={i} className="px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-300 text-[10px] border border-emerald-400/30">
                                &quot;{term}&quot;
                              </span>
                            ))
                          ) : (
                            <span className="text-xs text-white/35">None matched</span>
                          )}
                        </div>
                      </div>
                    </div>
                  </Section>
                </>
              ) : (
                /* Annotation tab */
                <div className="space-y-5">
                  <div className="rounded-[14px] border border-sky-500/30 bg-sky-500/[0.08] px-4 py-3 text-xs text-sky-200">
                    <p className="font-semibold">User-Owned Sales Annotation</p>
                    <p className="text-sky-300/70 mt-0.5">
                      Stored in your private annotation layer — never overwritten by background sweeps.
                    </p>
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-[10px] font-bold uppercase tracking-widest text-white/40 mb-1.5">CRM Lead Stage</label>
                      <select
                        value={editAnnotation.lead_status}
                        onChange={(e) => setEditAnnotation({ ...editAnnotation, lead_status: e.target.value })}
                        className={cn(selectCls, "w-full")}
                      >
                        {LEAD_STAGES.map((s) => <option key={s.id} value={s.id} className="bg-[#1a1a1a] text-[#f3f4f6]">{s.label}</option>)}
                      </select>
                    </div>

                    <div>
                      <label className="block text-[10px] font-bold uppercase tracking-widest text-white/40 mb-1.5">Hot Lead Status</label>
                      <button
                        type="button"
                        onClick={() => setEditAnnotation({ ...editAnnotation, is_hot: !editAnnotation.is_hot })}
                        className={cn(
                          "refraction-glass-btn w-full rounded-[14px] py-2 px-3 text-xs font-semibold flex items-center justify-center gap-1.5 transition-all",
                          editAnnotation.is_hot
                            ? "border-rose-500/40 bg-rose-500/20 text-rose-300 shadow-[0_0_16px_rgba(248,113,113,0.2)]"
                            : "text-white/55 hover:text-white"
                        )}
                      >
                        <Flame className={cn("w-4 h-4", editAnnotation.is_hot ? "text-rose-400" : "")} />
                        {editAnnotation.is_hot ? "🔥 Hot Lead" : "Standard Priority"}
                      </button>
                    </div>
                  </div>

                  <div>
                    <label className="block text-[10px] font-bold uppercase tracking-widest text-white/40 mb-1.5">Quoted Customer Need</label>
                    <textarea
                      rows={2}
                      value={editAnnotation.quoted_customer_need || ""}
                      onChange={(e) => setEditAnnotation({ ...editAnnotation, quoted_customer_need: e.target.value })}
                      placeholder='"Need an automated scraping tool for local plumbers before next month"'
                      className="refraction-glass-input w-full rounded-[14px] p-3 text-xs resize-none"
                    />
                  </div>

                  <div>
                    <label className="block text-[10px] font-bold uppercase tracking-widest text-white/40 mb-1.5">Private Sales Notes</label>
                    <textarea
                      rows={4}
                      value={editAnnotation.user_note || ""}
                      onChange={(e) => setEditAnnotation({ ...editAnnotation, user_note: e.target.value })}
                      placeholder="Conversation notes, pricing discussed, next follow-up agenda…"
                      className="refraction-glass-input w-full rounded-[14px] p-3 text-xs resize-none"
                    />
                  </div>

                  <div className="pt-1">
                    <button
                      type="button"
                      disabled={updateAnnotationMutation.isPending}
                      onClick={() => updateAnnotationMutation.mutate({ postId: activePost.id, annotation: editAnnotation })}
                      className="refraction-glass-btn w-full rounded-full py-2.5 text-xs font-bold text-white flex items-center justify-center gap-2 shadow-[0_0_24px_rgba(255,120,73,0.25)] hover:shadow-[0_0_36px_rgba(255,120,73,0.40)] border-[#FF7849]/40 hover:border-[#FF7849]/70"
                    >
                      {updateAnnotationMutation.isPending ? (
                        <><RefreshCw className="w-3.5 h-3.5 animate-spin" /> Saving…</>
                      ) : "Save Annotation Changes"}
                    </button>
                    {updateAnnotationMutation.isSuccess && (
                      <p className="text-center text-xs text-emerald-400 mt-2 font-medium">✓ Saved successfully</p>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Small helpers ─────────────────────────────────────────────────────────────

function Section({
  label,
  badge,
  children,
}: {
  label: string;
  badge?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <label className="text-[10px] font-bold uppercase tracking-widest text-white/40">{label}</label>
        {badge}
      </div>
      {children}
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 rounded-[10px] border border-white/[0.07] bg-white/[0.025] px-3 py-2">
      <span className="text-white/40 shrink-0">{label}:</span>
      <div className="text-white/80 font-medium text-right">{children}</div>
    </div>
  );
}

function Badge({ color, children }: { color: "amber" | "emerald" | "rose"; children: React.ReactNode }) {
  const cls = {
    amber:   "text-amber-300  bg-amber-500/15  border-amber-400/30",
    emerald: "text-emerald-300 bg-emerald-500/15 border-emerald-400/30",
    rose:    "text-rose-300   bg-rose-500/15   border-rose-400/30",
  }[color];
  return (
    <span className={cn("inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full border", cls)}>
      {children}
    </span>
  );
}
