"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Search,
  Filter,
  Flame,
  ExternalLink,
  RefreshCw,
  X,
  CheckCircle2,
  AlertCircle,
  Clock,
  Sparkles,
  ChevronRight,
  User,
  MessageSquare,
  Share2,
  FileText,
  SlidersHorizontal,
  ChevronDown,
  Layers,
  ArrowUpDown,
  Download,
  Building,
} from "lucide-react";

import { Header } from "@/components/layout/header";
import { Card, CardFootnote, EmptyState } from "@/components/ui/card";
import { useSession } from "@/components/providers/session-provider";
import { api } from "@/lib/api/client";
import type { PostItem, PostListResponse, PostAnnotation } from "@/lib/api/types";

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
  { id: "all", label: "All Platforms" },
  { id: "reddit", label: "Reddit" },
  { id: "linkedin", label: "LinkedIn" },
  { id: "justdial", label: "Justdial" },
  { id: "hackernews", label: "Hacker News" },
  { id: "x", label: "X (Twitter)" },
  { id: "facebook", label: "Facebook" },
  { id: "instagram", label: "Instagram" },
];

const SERVICE_TAGS = [
  { id: "all", label: "All Services" },
  { id: "web-development", label: "Web Development" },
  { id: "mobile-app", label: "Mobile Apps" },
  { id: "ai-automation", label: "AI & Automation" },
  { id: "seo-marketing", label: "SEO & Growth" },
  { id: "ui-ux-design", label: "UI / UX Design" },
  { id: "local-services", label: "Local Services" },
];

const LEAD_STAGES = [
  { id: "new", label: "New Lead", color: "text-slate-400 bg-slate-800/60" },
  { id: "contacted", label: "Contacted", color: "text-blue-400 bg-blue-900/40" },
  { id: "qualified", label: "Qualified", color: "text-emerald-400 bg-emerald-900/40" },
  { id: "proposal_sent", label: "Proposal Sent", color: "text-amber-400 bg-amber-900/40" },
  { id: "closed_won", label: "Won (Client)", color: "text-lime-400 bg-lime-900/40" },
  { id: "closed_lost", label: "Lost / Closed", color: "text-rose-400 bg-rose-900/40" },
];

export function PostExplorerView() {
  const { user, csrf } = useSession();
  const queryClient = useQueryClient();

  // Filters state
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("All Categories");
  const [selectedPlatform, setSelectedPlatform] = useState("all");
  const [selectedServiceTag, setSelectedServiceTag] = useState("all");
  const [selectedLeadStatus, setSelectedLeadStatus] = useState("all");
  const [isHotOnly, setIsHotOnly] = useState(false);
  const [retrievalStatus, setRetrievalStatus] = useState("all");
  const [minScore, setMinScore] = useState<number>(0);
  const [sortBy, setSortBy] = useState("discovered_at");
  const [sortDesc, setSortDesc] = useState(true);
  const [page, setPage] = useState(0);
  const pageSize = 20;

  // Selection & Drawer state
  const [selectedPostIds, setSelectedPostIds] = useState<Set<string>>(new Set());
  const [activePost, setActivePost] = useState<PostItem | null>(null);
  const [drawerTab, setDrawerTab] = useState<"provenance" | "annotation">("provenance");

  // Local annotation edit state for the active post
  const [editAnnotation, setEditAnnotation] = useState<PostAnnotation>({
    lead_status: "new",
    is_hot: false,
    follow_up_date: null,
    user_note: "",
    quoted_customer_need: "",
    services_to_sell: [],
    is_saved: false,
  });

  // Query posts list
  const { data, isLoading, isFetching } = useQuery({
    queryKey: [
      "social-posts",
      searchTerm,
      selectedCategory,
      selectedPlatform,
      selectedServiceTag,
      selectedLeadStatus,
      isHotOnly,
      retrievalStatus,
      minScore,
      sortBy,
      sortDesc,
      page,
    ],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (searchTerm.trim()) params.set("q", searchTerm.trim());
      if (selectedCategory !== "All Categories") params.set("intent", selectedCategory);
      if (selectedPlatform !== "all") params.set("platform", selectedPlatform);
      if (selectedServiceTag !== "all") params.set("service_tag", selectedServiceTag);
      if (selectedLeadStatus !== "all") params.set("lead_status", selectedLeadStatus);
      if (isHotOnly) params.set("is_hot", "true");
      if (retrievalStatus !== "all") params.set("retrieval_status", retrievalStatus);
      if (minScore > 0) params.set("min_confidence", (minScore / 100).toFixed(2));
      params.set("sort_by", sortBy);
      params.set("sort_desc", String(sortDesc));
      params.set("limit", String(pageSize));
      params.set("offset", String(page * pageSize));

      return api.get<PostListResponse>(`/social/posts?${params.toString()}`);
    },
    enabled: !!user,
  });

  // Open drawer and sync edit state
  const handleOpenPost = (post: PostItem) => {
    setActivePost(post);
    setEditAnnotation({
      lead_status: post.user_annotation?.lead_status || "new",
      is_hot: post.user_annotation?.is_hot || false,
      follow_up_date: post.user_annotation?.follow_up_date || null,
      user_note: post.user_annotation?.user_note || "",
      quoted_customer_need: post.user_annotation?.quoted_customer_need || "",
      services_to_sell: post.user_annotation?.services_to_sell || [],
      is_saved: post.user_annotation?.is_saved || false,
    });
  };

  // Mutation: Update Annotation
  const updateAnnotationMutation = useMutation({
    mutationFn: async ({ postId, annotation }: { postId: string; annotation: PostAnnotation }) => {
      return api.patch<PostAnnotation>(
        `/social/posts/${postId}/annotation`,
        annotation,
        csrf
      );
    },
    onSuccess: (updatedAnnotation) => {
      queryClient.invalidateQueries({ queryKey: ["social-posts"] });
      queryClient.invalidateQueries({ queryKey: ["leads-dashboard"] });
      if (activePost) {
        setActivePost({
          ...activePost,
          user_annotation: updatedAnnotation,
        });
      }
    },
  });

  // Mutation: Retry Page Fetch
  const retryFetchMutation = useMutation({
    mutationFn: async (postId: string) => {
      return api.post<PostItem>(
        `/social/posts/${postId}/retry-fetch`,
        {},
        csrf
      );
    },
    onSuccess: (updatedPost) => {
      queryClient.invalidateQueries({ queryKey: ["social-posts"] });
      setActivePost(updatedPost);
    },
  });

  // Mutation: Bulk Actions
  const bulkActionMutation = useMutation({
    mutationFn: async ({ action, value }: { action: string; value?: string }) => {
      return api.post(
        `/social/posts/bulk-action`,
        {
          post_ids: Array.from(selectedPostIds),
          action,
          value,
        },
        csrf
      );
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["social-posts"] });
      queryClient.invalidateQueries({ queryKey: ["leads-dashboard"] });
      setSelectedPostIds(new Set());
    },
  });

  // Checkbox toggle helpers
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
    if (selectedPostIds.size === data.items.length) {
      setSelectedPostIds(new Set());
    } else {
      setSelectedPostIds(new Set(data.items.map((p) => p.id)));
    }
  };

  const handleExportCSV = () => {
    if (!data?.items) return;
    const itemsToExport = selectedPostIds.size > 0
      ? data.items.filter((p) => selectedPostIds.has(p.id))
      : data.items;

    const headers = [
      "ID",
      "Platform",
      "Author",
      "Title / Snippet",
      "Category",
      "Client Score",
      "Lead Status",
      "Is Hot",
      "URL",
      "Discovered At",
    ];
    const rows = itemsToExport.map((p) => [
      p.id,
      p.platform,
      p.author_name || p.author_username || "Anonymous",
      `"${(p.page_title || p.search_snippet || "").replace(/"/g, '""')}"`,
      p.classification_category || "Unclassified",
      p.classification_score ?? "N/A",
      p.user_annotation?.lead_status || "new",
      p.user_annotation?.is_hot ? "Yes" : "No",
      p.original_url || p.canonical_url || "",
      p.first_discovered_at,
    ]);

    const csvContent = "data:text/csv;charset=utf-8," + [headers.join(","), ...rows.map((e) => e.join(","))].join("\n");
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", `posts_intelligence_${new Date().toISOString().slice(0, 10)}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  if (!user) return null;

  return (
    <div className="min-h-screen bg-[#252527] text-[#F8F5F4]">
      <Header title="Lead & Post Intelligence" subtitle="Post Explorer" />

      <main className="p-6 max-w-7xl mx-auto space-y-6">
        {/* Top Control Bar & Filter Bar */}
        <div className="bg-[#363437] border border-white/10 rounded-2xl p-5 shadow-lg space-y-4">
          <div className="flex flex-col md:flex-row gap-3 items-stretch md:items-center justify-between">
            {/* Search Input */}
            <div className="relative flex-1">
              <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-[#AAA5AD]" />
              <input
                type="text"
                placeholder="Search intent keywords, client problems, job posts..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="w-full pl-10 pr-4 py-2 bg-[#252527] border border-white/10 rounded-xl text-sm text-[#F8F5F4] placeholder-[#AAA5AD]/60 focus:outline-none focus:border-[#FF7849] transition"
              />
            </div>

            {/* Quick Action Buttons */}
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setIsHotOnly(!isHotOnly)}
                className={`flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-semibold border transition ${
                  isHotOnly
                    ? "bg-rose-500/20 text-rose-300 border-rose-500/40"
                    : "bg-[#252527] text-[#AAA5AD] border-white/10 hover:border-white/20"
                }`}
              >
                <Flame className={`w-3.5 h-3.5 ${isHotOnly ? "text-rose-400" : ""}`} />
                Hot Leads
              </button>

              <button
                type="button"
                onClick={handleExportCSV}
                className="flex items-center gap-1.5 px-3.5 py-2 bg-[#252527] hover:bg-white/5 border border-white/10 rounded-xl text-xs font-medium text-[#F8F5F4] transition"
              >
                <Download className="w-3.5 h-3.5 text-[#AAA5AD]" />
                Export CSV
              </button>
            </div>
          </div>

          {/* Secondary Filters Grid */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2.5 pt-2 border-t border-white/5">
            {/* Intent Category */}
            <select
              value={selectedCategory}
              onChange={(e) => setSelectedCategory(e.target.value)}
              className="bg-[#252527] border border-white/10 rounded-lg px-2.5 py-1.5 text-xs text-[#F8F5F4] focus:outline-none focus:border-[#FF7849]"
            >
              {CATEGORIES.map((cat) => (
                <option key={cat} value={cat}>
                  {cat}
                </option>
              ))}
            </select>

            {/* Platform */}
            <select
              value={selectedPlatform}
              onChange={(e) => setSelectedPlatform(e.target.value)}
              className="bg-[#252527] border border-white/10 rounded-lg px-2.5 py-1.5 text-xs text-[#F8F5F4] focus:outline-none focus:border-[#FF7849]"
            >
              {PLATFORMS.map((plat) => (
                <option key={plat.id} value={plat.id}>
                  {plat.label}
                </option>
              ))}
            </select>

            {/* Lead Status */}
            <select
              value={selectedLeadStatus}
              onChange={(e) => setSelectedLeadStatus(e.target.value)}
              className="bg-[#252527] border border-white/10 rounded-lg px-2.5 py-1.5 text-xs text-[#F8F5F4] focus:outline-none focus:border-[#FF7849]"
            >
              <option value="all">All Lead Stages</option>
              {LEAD_STAGES.map((st) => (
                <option key={st.id} value={st.id}>
                  {st.label}
                </option>
              ))}
            </select>

            {/* Service Tag */}
            <select
              value={selectedServiceTag}
              onChange={(e) => setSelectedServiceTag(e.target.value)}
              className="bg-[#252527] border border-white/10 rounded-lg px-2.5 py-1.5 text-xs text-[#F8F5F4] focus:outline-none focus:border-[#FF7849]"
            >
              {SERVICE_TAGS.map((tag) => (
                <option key={tag.id} value={tag.id}>
                  {tag.label}
                </option>
              ))}
            </select>

            {/* Retrieval Status */}
            <select
              value={retrievalStatus}
              onChange={(e) => setRetrievalStatus(e.target.value)}
              className="bg-[#252527] border border-white/10 rounded-lg px-2.5 py-1.5 text-xs text-[#F8F5F4] focus:outline-none focus:border-[#FF7849]"
            >
              <option value="all">All Retrieval Types</option>
              <option value="full_text">Full Text Retrieved</option>
              <option value="snippet_only">Snippet Only</option>
              <option value="blocked">Access Blocked</option>
              <option value="failed">Fetch Failed</option>
            </select>

            {/* Min Client Score */}
            <div className="flex items-center gap-1.5 bg-[#252527] border border-white/10 rounded-lg px-2.5 py-1 text-xs text-[#AAA5AD]">
              <span>Score:</span>
              <input
                type="range"
                min="0"
                max="100"
                step="5"
                value={minScore}
                onChange={(e) => setMinScore(Number(e.target.value))}
                className="w-full accent-[#FF7849] h-1.5"
              />
              <span className="font-mono text-[#F8F5F4]">{minScore}+</span>
            </div>
          </div>
        </div>

        {/* Bulk Action Strip (Visible when items selected) */}
        {selectedPostIds.size > 0 && (
          <div className="bg-[#444044] border border-[#FF7849]/40 rounded-xl px-4 py-2.5 flex items-center justify-between shadow-md animate-fade-in">
            <span className="text-xs font-medium text-[#F8F5F4]">
              {selectedPostIds.size} post(s) selected
            </span>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => bulkActionMutation.mutate({ action: "mark_hot", value: "true" })}
                className="px-2.5 py-1 bg-[#252527] hover:bg-white/10 text-rose-300 border border-rose-500/30 rounded-lg text-xs font-semibold flex items-center gap-1"
              >
                <Flame className="w-3 h-3" /> Mark Hot
              </button>
              <button
                type="button"
                onClick={() => bulkActionMutation.mutate({ action: "set_lead_status", value: "qualified" })}
                className="px-2.5 py-1 bg-[#252527] hover:bg-white/10 text-emerald-300 border border-emerald-500/30 rounded-lg text-xs font-semibold"
              >
                Mark Qualified
              </button>
              <button
                type="button"
                onClick={() => bulkActionMutation.mutate({ action: "set_lead_status", value: "contacted" })}
                className="px-2.5 py-1 bg-[#252527] hover:bg-white/10 text-blue-300 border border-blue-500/30 rounded-lg text-xs font-semibold"
              >
                Mark Contacted
              </button>
              <button
                type="button"
                onClick={() => setSelectedPostIds(new Set())}
                className="px-2 py-1 text-xs text-[#AAA5AD] hover:text-white"
              >
                Clear
              </button>
            </div>
          </div>
        )}

        {/* Posts Content Table / Cards */}
        <div className="bg-[#363437] border border-white/10 rounded-2xl overflow-hidden shadow-xl">
          <div className="p-4 border-b border-white/10 flex items-center justify-between bg-white/[0.02]">
            <div className="flex items-center gap-3">
              <input
                type="checkbox"
                checked={!!data?.items?.length && selectedPostIds.size === data.items.length}
                onChange={toggleSelectAll}
                className="rounded border-white/20 bg-[#252527] text-[#FF7849] focus:ring-0"
              />
              <span className="text-xs font-semibold uppercase tracking-wider text-[#AAA5AD]">
                Discovered Posts ({data?.total ?? 0})
              </span>
            </div>

            {isFetching && (
              <span className="text-xs text-[#AAA5AD] flex items-center gap-1.5 animate-pulse">
                <RefreshCw className="w-3 h-3 animate-spin text-[#FF7849]" /> Updating...
              </span>
            )}
          </div>

          {isLoading ? (
            <div className="p-12 text-center text-sm text-[#AAA5AD]">Loading post signals...</div>
          ) : !data?.items?.length ? (
            <div className="p-12 text-center">
              <p className="text-sm text-[#F8F5F4] font-medium">No posts matched your filters</p>
              <p className="text-xs text-[#AAA5AD] mt-1">Try relaxing category or search keyword constraints.</p>
            </div>
          ) : (
            <div className="divide-y divide-white/5">
              {data.items.map((post) => {
                const isSelected = selectedPostIds.has(post.id);
                const leadStage = LEAD_STAGES.find((s) => s.id === post.user_annotation?.lead_status) || LEAD_STAGES[0];

                return (
                  <div
                    key={post.id}
                    className={`p-4 transition hover:bg-white/[0.03] flex items-start gap-3.5 ${
                      isSelected ? "bg-white/[0.04]" : ""
                    }`}
                  >
                    {/* Checkbox */}
                    <input
                      type="checkbox"
                      checked={isSelected}
                      onChange={() => toggleSelectPost(post.id)}
                      className="mt-1 rounded border-white/20 bg-[#252527] text-[#FF7849] focus:ring-0"
                    />

                    {/* Main content body */}
                    <div className="flex-1 min-w-0 space-y-2">
                      {/* Meta badges row */}
                      <div className="flex flex-wrap items-center gap-2 text-xs">
                        {/* Platform pill */}
                        <span className="px-2 py-0.5 rounded-full font-semibold uppercase tracking-wider text-[10px] bg-white/10 text-[#F8F5F4]">
                          {post.platform}
                        </span>

                        {/* Category & Score */}
                        <span
                          className={`px-2 py-0.5 rounded-full font-medium text-[11px] ${
                            (post.classification_score ?? 0) >= 60
                              ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                              : "bg-white/5 text-[#AAA5AD]"
                          }`}
                        >
                          {post.classification_category || "Unclassified"} • Score {post.classification_score ?? "—"}
                        </span>

                        {/* Lead stage pill */}
                        <span className={`px-2 py-0.5 rounded-full font-semibold text-[10px] ${leadStage.color}`}>
                          {leadStage.label}
                        </span>

                        {/* Hot indicator */}
                        {post.user_annotation?.is_hot && (
                          <span className="flex items-center gap-0.5 text-xs text-rose-400 font-bold">
                            <Flame className="w-3.5 h-3.5 fill-rose-500 text-rose-500" /> Hot Lead
                          </span>
                        )}

                        {/* Full text status */}
                        {post.retrieval_status === "full_text" ? (
                          <span className="text-[10px] text-emerald-400 flex items-center gap-1 font-mono">
                            <CheckCircle2 className="w-3 h-3" /> Full Text
                          </span>
                        ) : (
                          <span className="text-[10px] text-[#AAA5AD] flex items-center gap-1 font-mono">
                            <Clock className="w-3 h-3" /> Snippet Only
                          </span>
                        )}

                        {/* Author */}
                        <span className="text-xs text-[#AAA5AD] flex items-center gap-1 ml-auto">
                          <User className="w-3 h-3 text-[#AAA5AD]/70" />
                          {post.author_name || post.author_username || "Public User"}
                        </span>
                      </div>

                      {/* Snippet / Title Text */}
                      <div
                        onClick={() => handleOpenPost(post)}
                        className="cursor-pointer group"
                      >
                        {post.page_title && (
                          <h4 className="text-sm font-semibold text-[#F8F5F4] group-hover:text-[#FF7849] transition line-clamp-1">
                            {post.page_title}
                          </h4>
                        )}
                        <p className="text-xs text-[#AAA5AD] line-clamp-2 mt-0.5 group-hover:text-[#F8F5F4]/90 transition">
                          {post.search_snippet || post.extracted_full_text || "No preview snippet available."}
                        </p>
                      </div>

                      {/* Footer tags & Truthful counts */}
                      <div className="flex flex-wrap items-center gap-3 pt-1 text-[11px] text-[#AAA5AD]">
                        {/* Service tags */}
                        {post.service_tags?.map((tag) => (
                          <span key={tag} className="bg-white/5 px-2 py-0.5 rounded text-[10px] text-[#AAA5AD]">
                            #{tag}
                          </span>
                        ))}

                        {/* Truthful metrics: null means unknown, not 0 */}
                        <div className="flex items-center gap-3 ml-auto text-xs">
                          {post.comments_count !== null && (
                            <span className="flex items-center gap-1 text-[#AAA5AD]">
                              <MessageSquare className="w-3 h-3" /> {post.comments_count}
                            </span>
                          )}
                          {post.reactions_count !== null && (
                            <span className="flex items-center gap-1 text-[#AAA5AD]">
                              <Share2 className="w-3 h-3" /> {post.reactions_count}
                            </span>
                          )}

                          <button
                            type="button"
                            onClick={() => handleOpenPost(post)}
                            className="px-3 py-1 bg-[#252527] hover:bg-white/10 border border-white/10 rounded-lg text-xs font-semibold text-[#FF7849] transition flex items-center gap-1"
                          >
                            Inspect & Annotate <ChevronRight className="w-3 h-3" />
                          </button>
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {/* Pagination Controls */}
          {!!data?.total && data.total > pageSize && (
            <div className="p-4 border-t border-white/10 flex items-center justify-between text-xs text-[#AAA5AD] bg-white/[0.01]">
              <span>
                Showing {page * pageSize + 1}–{Math.min((page + 1) * pageSize, data.total)} of {data.total}
              </span>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  disabled={page === 0}
                  onClick={() => setPage(page - 1)}
                  className="px-3 py-1.5 bg-[#252527] border border-white/10 rounded-lg text-xs disabled:opacity-40"
                >
                  Previous
                </button>
                <button
                  type="button"
                  disabled={(page + 1) * pageSize >= data.total}
                  onClick={() => setPage(page + 1)}
                  className="px-3 py-1.5 bg-[#252527] border border-white/10 rounded-lg text-xs disabled:opacity-40"
                >
                  Next
                </button>
              </div>
            </div>
          )}
        </div>
      </main>

      {/* Right-Side Slide-Over Drawer */}
      {activePost && (
        <div className="fixed inset-0 z-50 overflow-hidden bg-black/60 backdrop-blur-sm flex justify-end">
          <div className="w-full max-w-2xl bg-[#19191B] border-l border-white/10 h-full flex flex-col shadow-2xl animate-in slide-in-from-right duration-200">
            {/* Drawer Header */}
            <div className="p-5 border-b border-white/10 flex items-start justify-between bg-[#252527]">
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <span className="px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider bg-white/10 text-white">
                    {activePost.platform}
                  </span>
                  <span className="text-xs text-[#AAA5AD] font-mono">
                    ID: {activePost.external_id}
                  </span>
                </div>
                <h3 className="text-base font-semibold text-[#F8F5F4] line-clamp-1">
                  {activePost.page_title || "Discovered Post Details"}
                </h3>
              </div>

              <button
                type="button"
                onClick={() => setActivePost(null)}
                className="p-1.5 text-[#AAA5AD] hover:text-white rounded-lg hover:bg-white/10 transition"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Drawer Tabs */}
            <div className="flex border-b border-white/10 bg-[#252527]/50 px-5 gap-6 text-xs font-semibold">
              <button
                type="button"
                onClick={() => setDrawerTab("provenance")}
                className={`py-3 border-b-2 transition ${
                  drawerTab === "provenance"
                    ? "border-[#FF7849] text-[#F8F5F4]"
                    : "border-transparent text-[#AAA5AD] hover:text-white"
                }`}
              >
                Post Provenance & Full Text
              </button>
              <button
                type="button"
                onClick={() => setDrawerTab("annotation")}
                className={`py-3 border-b-2 transition flex items-center gap-1.5 ${
                  drawerTab === "annotation"
                    ? "border-[#FF7849] text-[#F8F5F4]"
                    : "border-transparent text-[#AAA5AD] hover:text-white"
                }`}
              >
                <Flame className="w-3.5 h-3.5 text-rose-400" />
                CRM & Sales Annotation
              </button>
            </div>

            {/* Drawer Body Scroll */}
            <div className="flex-1 overflow-y-auto p-6 space-y-6 text-sm">
              {drawerTab === "provenance" ? (
                <>
                  {/* Origin & URLs */}
                  <div className="space-y-2">
                    <label className="text-xs font-semibold uppercase tracking-wider text-[#AAA5AD]">
                      Source & Provenance
                    </label>
                    <div className="p-3 bg-[#252527] border border-white/10 rounded-xl space-y-2 text-xs">
                      <div className="flex items-center justify-between">
                        <span className="text-[#AAA5AD]">Original URL:</span>
                        {activePost.original_url ? (
                          <a
                            href={activePost.original_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-[#FF7849] hover:underline flex items-center gap-1 truncate max-w-sm"
                          >
                            {activePost.original_url} <ExternalLink className="w-3 h-3" />
                          </a>
                        ) : (
                          <span className="text-[#AAA5AD]">Unknown / Not provided</span>
                        )}
                      </div>

                      <div className="flex items-center justify-between">
                        <span className="text-[#AAA5AD]">Author:</span>
                        <span className="text-[#F8F5F4] font-medium">
                          {activePost.author_name || activePost.author_username || "Anonymous"}
                        </span>
                      </div>

                      <div className="flex items-center justify-between">
                        <span className="text-[#AAA5AD]">Discovered At:</span>
                        <span className="text-[#F8F5F4] font-mono">
                          {new Date(activePost.first_discovered_at).toLocaleString()}
                        </span>
                      </div>

                      <div className="flex items-center justify-between">
                        <span className="text-[#AAA5AD]">Extraction Method:</span>
                        <span className="font-mono text-emerald-400">
                          {activePost.extraction_method || "searxng_snippet"}
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Search Engine Snippet (Strictly labeled) */}
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <label className="text-xs font-semibold uppercase tracking-wider text-[#AAA5AD]">
                        Search Engine Snippet
                      </label>
                      <span className="text-[10px] text-amber-400 bg-amber-950/40 border border-amber-500/20 px-2 py-0.5 rounded">
                        From search result
                      </span>
                    </div>
                    <div className="p-3 bg-[#252527] border border-white/10 rounded-xl text-xs text-[#AAA5AD] font-mono leading-relaxed whitespace-pre-wrap">
                      {activePost.search_snippet || "No snippet returned by search engine."}
                    </div>
                  </div>

                  {/* Direct Extracted Full Text (Strictly separated) */}
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <label className="text-xs font-semibold uppercase tracking-wider text-[#AAA5AD]">
                        Extracted Full Text
                      </label>
                      <div className="flex items-center gap-2">
                        {activePost.retrieval_status === "full_text" ? (
                          <span className="text-[10px] text-emerald-400 bg-emerald-950/40 border border-emerald-500/20 px-2 py-0.5 rounded flex items-center gap-1">
                            <CheckCircle2 className="w-3 h-3" /> Direct page fetch
                          </span>
                        ) : (
                          <span className="text-[10px] text-rose-400 bg-rose-950/40 border border-rose-500/20 px-2 py-0.5 rounded flex items-center gap-1">
                            <AlertCircle className="w-3 h-3" /> {activePost.retrieval_status}
                          </span>
                        )}

                        <button
                          type="button"
                          disabled={retryFetchMutation.isPending}
                          onClick={() => retryFetchMutation.mutate(activePost.id)}
                          className="px-2.5 py-1 bg-white/10 hover:bg-white/15 rounded text-[11px] font-semibold text-white flex items-center gap-1 transition"
                        >
                          <RefreshCw className={`w-3 h-3 ${retryFetchMutation.isPending ? "animate-spin" : ""}`} />
                          Fetch Page
                        </button>
                      </div>
                    </div>

                    <div className="p-4 bg-[#252527] border border-white/10 rounded-xl text-xs text-[#F8F5F4] leading-relaxed whitespace-pre-wrap max-h-64 overflow-y-auto">
                      {activePost.extracted_full_text ? (
                        activePost.extracted_full_text
                      ) : (
                        <div className="text-center py-4 text-[#AAA5AD]">
                          <p>Full text has not been extracted.</p>
                          <p className="text-[11px] mt-1 text-[#AAA5AD]/70">
                            Reason: {activePost.retrieval_error || "Platform login wall or snippet-only search result."}
                          </p>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Classification & Evidence */}
                  <div className="space-y-2">
                    <label className="text-xs font-semibold uppercase tracking-wider text-[#AAA5AD]">
                      Scoring & Evidence Breakdown
                    </label>
                    <div className="p-3 bg-[#252527] border border-white/10 rounded-xl space-y-2 text-xs">
                      <div className="flex justify-between items-center">
                        <span className="text-[#AAA5AD]">Potential Client Score:</span>
                        <span className="font-bold text-[#FF7849] font-mono text-sm">
                          {activePost.classification_score ?? "—"} / 100
                        </span>
                      </div>
                      <div className="flex justify-between items-center">
                        <span className="text-[#AAA5AD]">Intent Category:</span>
                        <span className="font-medium text-[#F8F5F4]">
                          {activePost.classification_category || "Unclassified"}
                        </span>
                      </div>
                      <div className="flex flex-wrap gap-1.5 pt-2 border-t border-white/5">
                        <span className="text-[#AAA5AD] text-[11px] w-full">Matched Buying Phrases:</span>
                        {activePost.matched_phrases?.length ? (
                          activePost.matched_phrases.map((term, i) => (
                            <span key={i} className="px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 text-[11px]">
                              "{term}"
                            </span>
                          ))
                        ) : (
                          <span className="text-xs text-[#AAA5AD]">None</span>
                        )}
                      </div>
                    </div>
                  </div>
                </>
              ) : (
                /* Annotation & CRM Tab (Human-owned, never overwritten by sweeps) */
                <div className="space-y-5">
                  <div className="p-3.5 bg-blue-950/20 border border-blue-500/30 rounded-xl text-xs text-blue-200">
                    <p className="font-semibold">User-Owned Sales Annotation</p>
                    <p className="text-blue-300/80 mt-0.5">
                      Information entered here is stored in your private annotation layer and is never overwritten by background sweeps or crawlers.
                    </p>
                  </div>

                  {/* Stage & Hot Lead toggle */}
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-xs font-semibold uppercase tracking-wider text-[#AAA5AD] mb-1.5">
                        CRM Lead Stage
                      </label>
                      <select
                        value={editAnnotation.lead_status}
                        onChange={(e) => setEditAnnotation({ ...editAnnotation, lead_status: e.target.value })}
                        className="w-full bg-[#252527] border border-white/10 rounded-xl px-3 py-2 text-xs text-[#F8F5F4] focus:outline-none focus:border-[#FF7849]"
                      >
                        {LEAD_STAGES.map((st) => (
                          <option key={st.id} value={st.id}>
                            {st.label}
                          </option>
                        ))}
                      </select>
                    </div>

                    <div>
                      <label className="block text-xs font-semibold uppercase tracking-wider text-[#AAA5AD] mb-1.5">
                        Hot Lead Status
                      </label>
                      <button
                        type="button"
                        onClick={() => setEditAnnotation({ ...editAnnotation, is_hot: !editAnnotation.is_hot })}
                        className={`w-full py-2 px-3 rounded-xl border text-xs font-semibold flex items-center justify-center gap-1.5 transition ${
                          editAnnotation.is_hot
                            ? "bg-rose-500/20 text-rose-300 border-rose-500/40"
                            : "bg-[#252527] text-[#AAA5AD] border-white/10 hover:border-white/20"
                        }`}
                      >
                        <Flame className={`w-4 h-4 ${editAnnotation.is_hot ? "text-rose-400" : ""}`} />
                        {editAnnotation.is_hot ? "🔥 Marked as Hot Lead" : "Standard Priority"}
                      </button>
                    </div>
                  </div>

                  {/* Quoted Customer Need */}
                  <div>
                    <label className="block text-xs font-semibold uppercase tracking-wider text-[#AAA5AD] mb-1.5">
                      Quoted Customer Problem / Need
                    </label>
                    <textarea
                      rows={2}
                      value={editAnnotation.quoted_customer_need || ""}
                      onChange={(e) => setEditAnnotation({ ...editAnnotation, quoted_customer_need: e.target.value })}
                      placeholder='e.g., "Need an automated scraping tool for local plumbers before next month"'
                      className="w-full bg-[#252527] border border-white/10 rounded-xl p-3 text-xs text-[#F8F5F4] placeholder-[#AAA5AD]/50 focus:outline-none focus:border-[#FF7849]"
                    />
                  </div>

                  {/* Private User Note */}
                  <div>
                    <label className="block text-xs font-semibold uppercase tracking-wider text-[#AAA5AD] mb-1.5">
                      Private Sales / Follow-up Notes
                    </label>
                    <textarea
                      rows={4}
                      value={editAnnotation.user_note || ""}
                      onChange={(e) => setEditAnnotation({ ...editAnnotation, user_note: e.target.value })}
                      placeholder="Add conversation notes, pricing discussed, next follow-up agenda..."
                      className="w-full bg-[#252527] border border-white/10 rounded-xl p-3 text-xs text-[#F8F5F4] placeholder-[#AAA5AD]/50 focus:outline-none focus:border-[#FF7849]"
                    />
                  </div>

                  {/* Save Button */}
                  <div className="pt-2">
                    <button
                      type="button"
                      disabled={updateAnnotationMutation.isPending}
                      onClick={() =>
                        updateAnnotationMutation.mutate({
                          postId: activePost.id,
                          annotation: editAnnotation,
                        })
                      }
                      className="w-full py-2.5 bg-[#FF7849] hover:bg-[#FF7849]/90 text-white rounded-xl text-xs font-bold transition shadow-lg flex items-center justify-center gap-2"
                    >
                      {updateAnnotationMutation.isPending ? (
                        <>
                          <RefreshCw className="w-3.5 h-3.5 animate-spin" /> Saving...
                        </>
                      ) : (
                        "Save Annotation Changes"
                      )}
                    </button>

                    {updateAnnotationMutation.isSuccess && (
                      <p className="text-center text-xs text-emerald-400 mt-2 font-medium">
                        ✓ Annotations saved successfully
                      </p>
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
