"use client";

import Link from "next/link";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, Check, CheckCheck, Clock, ArrowRight } from "lucide-react";

import { Header } from "@/components/layout/header";
import { AppFooter } from "@/components/layout/app-footer";
import { Card, EmptyState } from "@/components/ui/card";
import { useSession } from "@/components/providers/session-provider";
import { api, isApiError } from "@/lib/api/client";
import type { NotificationItem } from "@/lib/api/types";

export function NotificationsView() {
  const { csrf } = useSession();
  const queryClient = useQueryClient();

  const [filter, setFilter] = useState<"all" | "unread">("all");
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const notificationsQuery = useQuery({
    queryKey: ["notifications", filter],
    queryFn: () =>
      api.get<NotificationItem[]>(
        `/notifications?limit=100${filter === "unread" ? "&unread_only=true" : ""}`
      ),
    refetchInterval: 10_000,
  });

  const markReadMutation = useMutation({
    mutationFn: (id: string) => api.post(`/notifications/${id}/read`, undefined, csrf),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["notifications"] });
    },
    onError: (err) => {
      setError(isApiError(err) ? err.message : "Failed to mark as read");
    },
  });

  const markAllReadMutation = useMutation({
    mutationFn: () => api.post("/notifications/read-all", undefined, csrf),
    onSuccess: () => {
      setNotice("All notifications marked as read.");
      queryClient.invalidateQueries({ queryKey: ["notifications"] });
    },
    onError: (err) => {
      setError(isApiError(err) ? err.message : "Failed to mark all as read");
    },
  });

  const items = notificationsQuery.data ?? [];
  const unreadCount = items.filter((n) => !n.is_read).length;

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <Header
        title="Notifications"
        subtitle={
          notificationsQuery.data
            ? `${items.length} system, discovery, and demand intelligence alerts`
            : "Loading notifications…"
        }
      />

      <main className="flex-1 overflow-y-auto p-4 space-y-4">
        {notice && (
          <div className="flex items-center gap-2 rounded-md border border-[var(--color-primary)]/40 bg-[var(--color-primary)]/10 px-4 py-2 text-xs text-[var(--color-foreground)]">
            <Check size={14} className="text-[var(--color-primary)]" />
            <span>{notice}</span>
          </div>
        )}

        {error && (
          <div className="flex items-center gap-2 rounded-md border border-[var(--color-error)]/40 bg-[var(--color-error)]/10 px-4 py-2 text-xs text-[var(--color-error)]">
            <span>{error}</span>
          </div>
        )}

        {/* Action Header */}
        <Card>
          <div className="flex flex-wrap items-center justify-between gap-3 text-xs">
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setFilter("all")}
                className={`rounded-full border px-3.5 py-1.5 text-xs font-semibold transition-all ${
                  filter === "all"
                    ? "refraction-glass-btn border-cyan-400/40 bg-cyan-500/20 text-cyan-200 shadow-[0_0_12px_rgba(0,212,255,0.2)]"
                    : "border-white/10 bg-white/[0.04] text-white/70 hover:border-white/20 hover:text-white"
                }`}
              >
                All Notifications ({items.length})
              </button>
              <button
                type="button"
                onClick={() => setFilter("unread")}
                className={`rounded-full border px-3.5 py-1.5 text-xs font-semibold transition-all ${
                  filter === "unread"
                    ? "refraction-glass-btn border-cyan-400/40 bg-cyan-500/20 text-cyan-200 shadow-[0_0_12px_rgba(0,212,255,0.2)]"
                    : "border-white/10 bg-white/[0.04] text-white/70 hover:border-white/20 hover:text-white"
                }`}
              >
                Unread Only ({unreadCount})
              </button>
            </div>

            {unreadCount > 0 && (
              <button
                type="button"
                onClick={() => markAllReadMutation.mutate()}
                disabled={markAllReadMutation.isPending}
                className="flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-xs text-[var(--color-muted)] hover:text-[var(--color-foreground)] hover:bg-[var(--color-surface)]"
              >
                <CheckCheck size={14} />
                <span>Mark All as Read</span>
              </button>
            )}
          </div>
        </Card>

        {/* Notifications list */}
        <Card>
          {notificationsQuery.isLoading ? (
            <div className="py-12 text-center text-xs text-[var(--color-muted)]">
              Loading notification feed…
            </div>
          ) : items.length === 0 ? (
            <EmptyState
              title={filter === "unread" ? "No unread notifications" : "No notifications yet"}
              description="System alerts, discovery sweep finishes, and demand intelligence triggers will appear here."
            />
          ) : (
            <div className="divide-y divide-border/60">
              {items.map((n) => {
                const isDemand = n.notification_type.includes("demand");
                const isSystem = n.notification_type.includes("system");

                return (
                  <div
                    key={n.id}
                    className={`flex items-start justify-between gap-4 py-3.5 px-2 transition-colors ${
                      !n.is_read ? "bg-[var(--color-primary)]/[0.04]" : "hover:bg-[var(--color-surface)]/40"
                    }`}
                  >
                    <div className="flex items-start gap-3">
                      <div
                        className={`p-2 rounded-lg mt-0.5 ${
                          isDemand
                            ? "bg-purple-500/10 text-purple-400"
                            : isSystem
                            ? "bg-[var(--color-warning)]/10 text-[var(--color-warning)]"
                            : "bg-[var(--color-primary)]/10 text-[var(--color-primary)]"
                        }`}
                      >
                        <Bell size={16} />
                      </div>

                      <div className="space-y-1">
                        <div className="flex items-center gap-2">
                          <span
                            className={`text-xs font-semibold ${
                              !n.is_read ? "text-[var(--color-foreground)]" : "text-[var(--color-muted)]"
                            }`}
                          >
                            {n.title}
                          </span>
                          {!n.is_read && (
                            <span className="h-1.5 w-1.5 rounded-full bg-[var(--color-primary)] inline-block" />
                          )}
                          <span className="rounded bg-[var(--color-surface)] px-1.5 py-0.2 text-[10px] text-[var(--color-muted)]">
                            {n.notification_type}
                          </span>
                        </div>

                        <p className="text-xs text-[var(--color-muted)] leading-relaxed">{n.message}</p>

                        <div className="flex items-center gap-3 pt-1 text-[11px] text-[var(--color-muted)]">
                          <span className="flex items-center gap-1">
                            <Clock size={11} />
                            <span>
                              {new Date(n.created_at).toLocaleString(undefined, {
                                month: "short",
                                day: "numeric",
                                hour: "2-digit",
                                minute: "2-digit",
                              })}
                            </span>
                          </span>

                          {n.related_entity_type === "business" && n.related_entity_id && (
                            <Link
                              href={`/leads/${n.related_entity_id}`}
                              className="flex items-center gap-1 text-[var(--color-primary)] hover:underline"
                            >
                              <span>View Business</span>
                              <ArrowRight size={11} />
                            </Link>
                          )}
                          {n.related_entity_type === "social_content" && (
                            <Link
                              href="/intelligence/demand"
                              className="flex items-center gap-1 text-[var(--color-primary)] hover:underline"
                            >
                              <span>View Demand Signal</span>
                              <ArrowRight size={11} />
                            </Link>
                          )}
                        </div>
                      </div>
                    </div>

                    {!n.is_read && (
                      <button
                        type="button"
                        onClick={() => markReadMutation.mutate(n.id)}
                        className="rounded p-1 text-[var(--color-muted)] hover:text-[var(--color-foreground)] hover:bg-[var(--color-surface)] shrink-0"
                        title="Mark as read"
                      >
                        <Check size={14} />
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </Card>
        <AppFooter />
      </main>
    </div>
  );
}
