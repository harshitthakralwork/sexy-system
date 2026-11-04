"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  Radar,
  Flame,
  Search,
  Filter,
  ArrowUpRight,
  Sparkles,
  Layers,
  CheckCircle2,
  Calendar,
  ExternalLink,
  ChevronRight,
  TrendingUp,
  BarChart2,
  Clock,
  Compass,
} from "lucide-react";

import { Header } from "@/components/layout/header";
import { Card, CardFootnote } from "@/components/ui/card";
import { useSession } from "@/components/providers/session-provider";
import { api } from "@/lib/api/client";
import type { LeadsDashboardResponse } from "@/lib/api/types";

export function OverviewView() {
  const { user } = useSession();

  const { data: dashboard, isLoading } = useQuery({
    queryKey: ["leads-dashboard"],
    queryFn: () => api.get<LeadsDashboardResponse>("/social/leads-dashboard"),
    enabled: !!user,
  });

  if (!user) return null;

  const totalDemand = dashboard?.demand_posts_found ?? 0;
  const highConfidence = dashboard?.high_confidence_leads ?? 0;
  const postsDiscovered = dashboard?.posts_discovered ?? 0;
  const duplicatesRemoved = dashboard?.duplicates_removed ?? 0;
  const scheduledRuns = dashboard?.scheduled_runs ?? 0;

  return (
    <div className="min-h-screen bg-[#252527] text-[#F8F5F4]">
      <Header title="Social & Demand Intelligence" subtitle="Lead & Post Mission Control" />

      <main className="p-6 max-w-7xl mx-auto space-y-6">
        {/* Top Hero Banner & Quick Actions */}
        <div className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-[#363437] via-[#2A2A2C] to-[#1E1E20] border border-white/10 p-6 md:p-8 shadow-2xl">
          <div className="relative z-10 max-w-2xl space-y-3">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-[#FF7849]/15 border border-[#FF7849]/30 text-[#FF7849] text-xs font-semibold">
              <Sparkles className="w-3.5 h-3.5" /> Next-Gen Lead & Post Intelligence
            </div>
            <h1 className="text-2xl md:text-3xl font-extrabold text-[#F8F5F4] tracking-tight">
              Real-time Demand Radar & Client Intent
            </h1>
            <p className="text-sm text-[#AAA5AD] leading-relaxed">
              Discover active client problems, hiring requests, and RFP signals across Reddit, LinkedIn, Justdial, and public directories without credential automation or fabricated metrics.
            </p>
            <div className="flex flex-wrap items-center gap-3 pt-2">
              <Link
                href="/intelligence/posts"
                className="px-4 py-2.5 bg-[#FF7849] hover:bg-[#FF7849]/90 text-white rounded-xl text-xs font-bold transition shadow-lg flex items-center gap-2"
              >
                <Search className="w-4 h-4" /> Open Post Explorer
              </Link>
              <Link
                href="/intelligence/tracks"
                className="px-4 py-2.5 bg-[#252527] hover:bg-white/10 border border-white/15 text-[#F8F5F4] rounded-xl text-xs font-semibold transition flex items-center gap-2"
              >
                <Radar className="w-4 h-4 text-[#D4EF8A]" /> Configure Tracks
              </Link>
              <Link
                href="/leads/discover"
                className="px-4 py-2.5 bg-[#252527] hover:bg-white/10 border border-white/15 text-[#F8F5F4] rounded-xl text-xs font-semibold transition flex items-center gap-2"
              >
                <Compass className="w-4 h-4 text-[#B7A1DF]" /> Discover Local Businesses
              </Link>
            </div>
          </div>
        </div>

        {/* 5 Key Metric Cards */}
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          <div className="bg-[#363437] border border-white/10 rounded-2xl p-4 shadow-lg space-y-1">
            <span className="text-xs uppercase tracking-wider text-[#AAA5AD] font-semibold">Demand Posts</span>
            <div className="text-2xl font-extrabold text-[#FF7849] font-mono">
              {isLoading ? "..." : totalDemand}
            </div>
            <p className="text-[11px] text-[#AAA5AD]">Active buyer signals</p>
          </div>

          <div className="bg-[#363437] border border-white/10 rounded-2xl p-4 shadow-lg space-y-1">
            <span className="text-xs uppercase tracking-wider text-[#AAA5AD] font-semibold">High-Intent Leads</span>
            <div className="text-2xl font-extrabold text-[#D4EF8A] font-mono">
              {isLoading ? "..." : highConfidence}
            </div>
            <p className="text-[11px] text-[#AAA5AD]">Score &ge; 70 / 100</p>
          </div>

          <div className="bg-[#363437] border border-white/10 rounded-2xl p-4 shadow-lg space-y-1">
            <span className="text-xs uppercase tracking-wider text-[#AAA5AD] font-semibold">Posts Discovered</span>
            <div className="text-2xl font-extrabold text-[#B7A1DF] font-mono">
              {isLoading ? "..." : postsDiscovered}
            </div>
            <p className="text-[11px] text-[#AAA5AD]">In persistent storage</p>
          </div>

          <div className="bg-[#363437] border border-white/10 rounded-2xl p-4 shadow-lg space-y-1">
            <span className="text-xs uppercase tracking-wider text-[#AAA5AD] font-semibold">Duplicates Pruned</span>
            <div className="text-2xl font-extrabold text-[#F8F5F4] font-mono">
              {isLoading ? "..." : duplicatesRemoved}
            </div>
            <p className="text-[11px] text-[#AAA5AD]">Canonical normalization</p>
          </div>

          <div className="bg-[#363437] border border-white/10 rounded-2xl p-4 shadow-lg space-y-1 col-span-2 md:col-span-1">
            <span className="text-xs uppercase tracking-wider text-[#AAA5AD] font-semibold">Active Schedules</span>
            <div className="text-2xl font-extrabold text-blue-400 font-mono">
              {isLoading ? "..." : scheduledRuns}
            </div>
            <p className="text-[11px] text-[#AAA5AD]">Recurring track runs</p>
          </div>
        </div>

        {/* Middle Two-Column Grid: 7-Day Activity & Category Breakdown */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* 7-Day Discovery Trend (Real DB timestamps) */}
          <div className="bg-[#363437] border border-white/10 rounded-2xl p-5 shadow-lg space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-bold text-[#F8F5F4]">7-Day Post Discovery Velocity</h3>
                <p className="text-xs text-[#AAA5AD]">Honest count of posts ingested per day</p>
              </div>
              <BarChart2 className="w-4 h-4 text-[#D4EF8A]" />
            </div>

            <div className="pt-4 flex items-end justify-between gap-2 h-44 border-b border-white/10 pb-2">
              {dashboard?.posts_per_day?.map((day) => {
                const maxVal = Math.max(...(dashboard.posts_per_day.map((d) => d.count) || [1]), 1);
                const heightPct = Math.round((day.count / maxVal) * 100);

                return (
                  <div key={day.date} className="flex-1 flex flex-col items-center gap-1.5 h-full justify-end group">
                    <span className="text-[10px] font-mono text-[#AAA5AD] opacity-0 group-hover:opacity-100 transition">
                      {day.count}
                    </span>
                    <div
                      style={{ height: `${Math.max(heightPct, 6)}%` }}
                      className="w-full max-w-[32px] rounded-t-lg bg-gradient-to-t from-[#FF7849]/40 to-[#FF7849] group-hover:from-[#D4EF8A]/60 group-hover:to-[#D4EF8A] transition-all duration-300"
                    />
                    <span className="text-[10px] font-mono text-[#AAA5AD] truncate w-full text-center">
                      {day.date.slice(5)}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Classification Distribution */}
          <div className="bg-[#363437] border border-white/10 rounded-2xl p-5 shadow-lg space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-bold text-[#F8F5F4]">Intent Category Breakdown</h3>
                <p className="text-xs text-[#AAA5AD]">Deterministic classification across stored posts</p>
              </div>
              <Layers className="w-4 h-4 text-[#B7A1DF]" />
            </div>

            <div className="space-y-2.5 pt-1">
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
                          <span className="text-[#F8F5F4]">{cat}</span>
                          <span className="text-[#AAA5AD] font-mono">
                            {count} ({pct}%)
                          </span>
                        </div>
                        <div className="w-full bg-[#252527] h-2 rounded-full overflow-hidden">
                          <div
                            style={{ width: `${pct}%` }}
                            className="bg-[#FF7849] h-full rounded-full transition-all duration-500"
                          />
                        </div>
                      </div>
                    );
                  })
              ) : (
                <div className="py-10 text-center text-xs text-[#AAA5AD]">
                  No classified post data yet. Run a discovery track to see distribution.
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Latest Demand Posts Table */}
        <div className="bg-[#363437] border border-white/10 rounded-2xl overflow-hidden shadow-xl">
          <div className="p-4 border-b border-white/10 flex items-center justify-between bg-white/[0.02]">
            <div className="flex items-center gap-2">
              <Flame className="w-4 h-4 text-rose-400" />
              <h3 className="text-sm font-bold text-[#F8F5F4]">Latest High-Intent Demand Posts</h3>
            </div>
            <Link
              href="/intelligence/posts"
              className="text-xs font-semibold text-[#FF7849] hover:underline flex items-center gap-1"
            >
              View all in Post Explorer <ChevronRight className="w-3.5 h-3.5" />
            </Link>
          </div>

          <div className="divide-y divide-white/5">
            {dashboard?.latest_demand_posts?.length ? (
              dashboard.latest_demand_posts.map((post) => (
                <div key={post.id} className="p-4 flex items-center justify-between gap-4 hover:bg-white/[0.02] transition">
                  <div className="space-y-1 min-w-0 flex-1">
                    <div className="flex items-center gap-2 text-xs">
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider bg-white/10 text-white">
                        {post.platform}
                      </span>
                      <span className="text-xs font-semibold text-[#D4EF8A]">
                        {post.classification_category}
                      </span>
                      {post.classification_score !== null && (
                        <span className="text-[11px] font-mono text-[#AAA5AD]">
                          Score: {post.classification_score}/100
                        </span>
                      )}
                      {post.user_annotation?.is_hot && (
                        <span className="text-xs text-rose-400 font-bold flex items-center gap-0.5">
                          <Flame className="w-3 h-3 fill-rose-500" /> Hot
                        </span>
                      )}
                    </div>

                    <p className="text-xs text-[#F8F5F4] line-clamp-1 font-medium">
                      {post.page_title || post.search_snippet || "Untitled Post"}
                    </p>
                    <p className="text-[11px] text-[#AAA5AD] line-clamp-1">
                      {post.search_snippet || post.extracted_full_text}
                    </p>
                  </div>

                  <Link
                    href={`/intelligence/posts?q=${encodeURIComponent(post.page_title || post.author_name || "")}`}
                    className="px-3 py-1.5 bg-[#252527] hover:bg-white/10 border border-white/10 rounded-xl text-xs font-semibold text-[#F8F5F4] transition shrink-0 flex items-center gap-1"
                  >
                    Inspect <ArrowUpRight className="w-3.5 h-3.5 text-[#AAA5AD]" />
                  </Link>
                </div>
              ))
            ) : (
              <div className="p-10 text-center text-xs text-[#AAA5AD]">
                No demand posts discovered yet. Configure a Discovery Track to sweep Reddit, LinkedIn, or directories.
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
