"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  Radar,
  Flame,
  Search,
  ArrowUpRight,
  Sparkles,
  Layers,
  ChevronRight,
  BarChart2,
  Compass,
} from "lucide-react";

import { Header } from "@/components/layout/header";
import { AppFooter } from "@/components/layout/app-footer";
import { useSession } from "@/components/providers/session-provider";
import { api } from "@/lib/api/client";
import type { LeadsDashboardResponse } from "@/lib/api/types";
import { cn } from "@/lib/utils";

export function OverviewView() {
  const { user } = useSession();

  const { data: dashboard, isLoading } = useQuery({
    queryKey: ["leads-dashboard"],
    queryFn: () => api.get<LeadsDashboardResponse>("/social/leads-dashboard"),
    enabled: !!user,
  });

  if (!user) return null;

  const totalDemand     = dashboard?.demand_posts_found   ?? 0;
  const highConfidence  = dashboard?.high_confidence_leads ?? 0;
  const postsDiscovered = dashboard?.posts_discovered      ?? 0;
  const duplicatesRemoved = dashboard?.duplicates_removed  ?? 0;
  const scheduledRuns   = dashboard?.scheduled_runs        ?? 0;

  const metrics = [
    { label: "Demand Posts",     value: totalDemand,       tone: "text-[#FF7849]", bg: "bg-orange-500/15 border-orange-400/30",  sub: "Active buyer signals"       },
    { label: "High-Intent Leads",value: highConfidence,    tone: "text-emerald-300",bg: "bg-emerald-500/15 border-emerald-400/30",sub: "Score ≥ 70 / 100"           },
    { label: "Posts Discovered", value: postsDiscovered,   tone: "text-violet-300", bg: "bg-violet-500/15 border-violet-400/30",  sub: "In persistent storage"      },
    { label: "Duplicates Pruned",value: duplicatesRemoved, tone: "text-white",      bg: "bg-white/10 border-white/20",             sub: "Canonical normalization"    },
    { label: "Active Schedules", value: scheduledRuns,     tone: "text-sky-300",    bg: "bg-sky-500/15 border-sky-400/30",         sub: "Recurring track runs"       },
  ];

  return (
    <div className="flex min-h-0 flex-1 flex-col bg-transparent text-white">
      <Header title="Social & Demand Intelligence" subtitle="Lead & Post Mission Control" />

      <main className="flex-1 overflow-y-auto p-4 sm:p-6">
        <div className="mx-auto max-w-7xl space-y-5">

          {/* ── Hero Banner ── */}
          <div className="refraction-glass-card relative overflow-hidden rounded-[28px] p-6 md:p-8 animate-slide-up">
            {/* Ambient blobs */}
            <div className="pointer-events-none absolute -right-24 -top-24 h-72 w-72 rounded-full bg-orange-500/10 blur-[80px]" />
            <div className="pointer-events-none absolute -left-16 -bottom-16 h-56 w-56 rounded-full bg-violet-500/10 blur-[70px]" />

            <div className="relative z-10 max-w-2xl space-y-3">
              <div className="inline-flex items-center gap-2 rounded-full border border-[#FF7849]/30 bg-[#FF7849]/10 px-3.5 py-1 text-[#FF7849] text-xs font-semibold">
                <Sparkles className="w-3.5 h-3.5" />
                Next-Gen Lead & Post Intelligence
              </div>
              <h1 className="text-2xl md:text-3xl font-extrabold text-white tracking-tight">
                Real-time Demand Radar & Client Intent
              </h1>
              <p className="text-sm text-white/55 leading-relaxed">
                Discover active client problems, hiring requests, and RFP signals across Reddit, LinkedIn, Justdial, and public directories.
              </p>
              <div className="flex flex-wrap items-center gap-3 pt-2">
                <Link
                  href="/intelligence/posts"
                  className="refraction-glass-btn inline-flex items-center gap-2 rounded-full px-5 py-2.5 text-xs font-bold text-white shadow-[0_0_28px_rgba(255,120,73,0.30)] hover:shadow-[0_0_40px_rgba(255,120,73,0.50)]"
                >
                  <Search className="w-4 h-4 text-[#FF7849]" />
                  Open Post Explorer
                </Link>
                <Link
                  href="/intelligence/tracks"
                  className="refraction-glass-btn inline-flex items-center gap-2 rounded-full px-5 py-2.5 text-xs font-semibold text-white/80 hover:text-white"
                >
                  <Radar className="w-4 h-4 text-emerald-400" />
                  Configure Tracks
                </Link>
                <Link
                  href="/leads/discover"
                  className="refraction-glass-btn inline-flex items-center gap-2 rounded-full px-5 py-2.5 text-xs font-semibold text-white/80 hover:text-white"
                >
                  <Compass className="w-4 h-4 text-violet-400" />
                  Discover Businesses
                </Link>
              </div>
            </div>
          </div>

          {/* ── KPI Metrics ── */}
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            {metrics.map((m, i) => (
              <div
                key={m.label}
                className={cn(
                  "refraction-glass-card rounded-[22px] p-4 space-y-2 animate-slide-up",
                  "hover:-translate-y-0.5 transition-all duration-200"
                )}
                style={{ animationDelay: `${i * 50}ms` }}
              >
                <span className={cn("text-[9px] uppercase tracking-widest font-bold text-white/40")}>{m.label}</span>
                <div className={cn("text-2xl font-extrabold font-mono", m.tone)}>
                  {isLoading ? <span className="skeleton h-7 w-16 block" /> : m.value.toLocaleString()}
                </div>
                <p className="text-[10px] text-white/35 font-medium">{m.sub}</p>
              </div>
            ))}
          </div>

          {/* ── Charts Row ── */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">

            {/* 7-Day chart */}
            <div className="refraction-glass-card rounded-[24px] p-5 space-y-4 animate-slide-up" style={{ animationDelay: "100ms" }}>
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-bold text-white">7-Day Post Discovery Velocity</h3>
                  <p className="text-xs text-white/40 mt-0.5">Posts ingested per day</p>
                </div>
                <BarChart2 className="w-4 h-4 text-emerald-400" />
              </div>

              <div className="flex items-end justify-between gap-2 h-40 border-b border-white/[0.08] pb-2">
                {dashboard?.posts_per_day?.map((day) => {
                  const maxVal = Math.max(...(dashboard.posts_per_day.map((d) => d.count) || [1]), 1);
                  const heightPct = Math.round((day.count / maxVal) * 100);
                  return (
                    <div key={day.date} className="flex-1 flex flex-col items-center gap-1.5 h-full justify-end group">
                      <span className="text-[9px] font-mono text-white/40 opacity-0 group-hover:opacity-100 transition">
                        {day.count}
                      </span>
                      <div
                        style={{ height: `${Math.max(heightPct, 6)}%` }}
                        className="w-full max-w-[28px] rounded-t-lg bg-gradient-to-t from-[#FF7849]/30 to-[#FF7849] group-hover:from-emerald-400/40 group-hover:to-emerald-400 transition-all duration-300"
                      />
                      <span className="text-[9px] font-mono text-white/35 truncate w-full text-center">
                        {day.date.slice(5)}
                      </span>
                    </div>
                  );
                }) ?? (
                  <p className="text-xs text-white/35 mx-auto self-center">No data yet</p>
                )}
              </div>
            </div>

            {/* Classification breakdown */}
            <div className="refraction-glass-card rounded-[24px] p-5 space-y-4 animate-slide-up" style={{ animationDelay: "140ms" }}>
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-bold text-white">Intent Category Breakdown</h3>
                  <p className="text-xs text-white/40 mt-0.5">Deterministic classification across stored posts</p>
                </div>
                <Layers className="w-4 h-4 text-violet-400" />
              </div>

              <div className="space-y-2.5">
                {dashboard?.classification_distribution &&
                Object.keys(dashboard.classification_distribution).length > 0 ? (
                  Object.entries(dashboard.classification_distribution)
                    .sort((a, b) => b[1] - a[1])
                    .slice(0, 6)
                    .map(([cat, count]) => {
                      const total = postsDiscovered || 1;
                      const pct = Math.round((count / total) * 100);
                      return (
                        <div key={cat} className="space-y-1">
                          <div className="flex justify-between text-xs font-medium">
                            <span className="text-white/80">{cat}</span>
                            <span className="text-white/40 font-mono">{count} ({pct}%)</span>
                          </div>
                          <div className="job-progress-track">
                            <div className="job-progress-fill animate-fill-sweep" style={{ width: `${pct}%` }} />
                          </div>
                        </div>
                      );
                    })
                ) : (
                  <div className="py-10 text-center text-xs text-white/35">
                    No classified post data yet. Run a discovery track to see distribution.
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* ── Latest Demand Posts ── */}
          <div className="refraction-glass-card rounded-[24px] overflow-hidden animate-slide-up" style={{ animationDelay: "180ms" }}>
            <div className="px-5 py-4 border-b border-white/[0.08] flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Flame className="w-4 h-4 text-rose-400" />
                <h3 className="text-sm font-bold text-white">Latest High-Intent Demand Posts</h3>
              </div>
              <Link
                href="/intelligence/posts"
                className="inline-flex items-center gap-1 text-xs font-semibold text-[#FF7849] hover:text-orange-300 transition-colors"
              >
                View all <ChevronRight className="w-3.5 h-3.5" />
              </Link>
            </div>

            <div className="divide-y divide-white/[0.05]">
              {dashboard?.latest_demand_posts?.length ? (
                dashboard.latest_demand_posts.map((post, i) => (
                  <div
                    key={post.id}
                    className="p-4 flex items-center justify-between gap-4 hover:bg-white/[0.03] transition-colors animate-slide-up"
                    style={{ animationDelay: `${i * 30}ms` }}
                  >
                    <div className="space-y-1 min-w-0 flex-1">
                      <div className="flex items-center gap-2 text-xs flex-wrap">
                        <span className="px-2 py-0.5 rounded-full text-[9px] font-bold uppercase tracking-wider border border-white/15 bg-white/[0.06] text-white/70">
                          {post.platform}
                        </span>
                        <span className="text-xs font-semibold text-emerald-400">
                          {post.classification_category}
                        </span>
                        {post.classification_score !== null && (
                          <span className="text-[10px] font-mono text-white/35">
                            Score: {post.classification_score}/100
                          </span>
                        )}
                        {post.user_annotation?.is_hot && (
                          <span className="text-xs text-rose-400 font-bold flex items-center gap-0.5">
                            <Flame className="w-3 h-3 fill-rose-500" /> Hot
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-white/80 line-clamp-1 font-medium">
                        {post.page_title || post.search_snippet || "Untitled Post"}
                      </p>
                      <p className="text-[10px] text-white/40 line-clamp-1">
                        {post.search_snippet || post.extracted_full_text}
                      </p>
                    </div>

                    <Link
                      href={`/intelligence/posts?q=${encodeURIComponent(post.page_title || post.author_name || "")}`}
                      className="refraction-glass-btn inline-flex items-center gap-1.5 shrink-0 rounded-full px-3.5 py-1.5 text-xs font-semibold text-white/70 hover:text-white"
                    >
                      Inspect <ArrowUpRight className="w-3.5 h-3.5" />
                    </Link>
                  </div>
                ))
              ) : (
                <div className="p-10 text-center text-xs text-white/35">
                  No demand posts discovered yet. Configure a Discovery Track to sweep Reddit, LinkedIn, or directories.
                </div>
              )}
            </div>
          </div>

          <AppFooter />
        </div>
      </main>
    </div>
  );
}
