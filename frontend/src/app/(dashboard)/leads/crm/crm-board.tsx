"use client";

import Link from "next/link";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { Header } from "@/components/layout/header";
import { Card } from "@/components/ui/card";
import { useSession } from "@/components/providers/session-provider";
import { api } from "@/lib/api/client";
import type { Board } from "@/lib/api/types";

export function CrmBoard() {
  const { csrf, user } = useSession();
  const queryClient = useQueryClient();
  const [newStage, setNewStage] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const board = useQuery({
    queryKey: ["crm-board"],
    queryFn: () => api.get<Board>("/crm/board"),
  });

  const move = useMutation({
    mutationFn: ({ businessId, stage }: { businessId: string; stage: string }) =>
      api.post(`/businesses/${businessId}/stage/${encodeURIComponent(stage)}`, undefined, csrf),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["crm-board"] }),
    onError: (caught) => setError(errorMessage(caught)),
  });

  const createStage = useMutation({
    mutationFn: () => api.post("/crm/stages", { name: newStage.trim() }, csrf),
    onSuccess: () => {
      setNewStage("");
      queryClient.invalidateQueries({ queryKey: ["crm-board"] });
      setNotice(`Stage "${newStage.trim()}" added.`);
    },
    onError: (caught) => setError(errorMessage(caught)),
  });

  const cardsByStage = new Map<string, Board["cards"]>();
  for (const stage of board.data?.stages ?? []) {
    cardsByStage.set(stage.id, []);
  }
  for (const card of board.data?.cards ?? []) {
    const bucket = cardsByStage.get(card.stage_id);
    if (bucket) bucket.push(card);
    else cardsByStage.set(card.stage_id, [card]);
  }

  if (!user) return null;

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <Header
        title="CRM Pipeline"
        subtitle={
          board.data
            ? `${board.data.cards.length} businesses across ${board.data.stages.length} stages`
            : "Loading pipeline…"
        }
      />

      <main className="flex-1 overflow-hidden p-4">
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <input
            className="w-56 rounded-md border border-border bg-[var(--color-surface)] px-2 py-1.5 text-sm"
            placeholder="New stage name"
            value={newStage}
            onChange={(event) => setNewStage(event.target.value)}
          />
          <button
            className={buttonClass(false)}
            disabled={!newStage.trim() || createStage.isPending}
            onClick={() => createStage.mutate()}
            type="button"
          >
            Add stage
          </button>
          {notice && <span className="text-xs text-[var(--color-muted)]">{notice}</span>}
          {error && <span className="text-xs text-[var(--color-error)]">{error}</span>}
        </div>

        {board.isError && (
          <p className="text-sm text-[var(--color-error)]">
            Pipeline could not be loaded: {errorMessage(board.error)}
          </p>
        )}

        {!board.isPending && !board.isError && (
          <div className="flex h-full gap-3 overflow-x-auto pb-2">
            {(board.data?.stages ?? []).map((stage) => (
              <Column
                key={stage.id}
                name={stage.name}
                cards={cardsByStage.get(stage.id) ?? []}
                onMove={(businessId, target) => move.mutate({ businessId, stage: target })}
              />
            ))}
          </div>
        )}
      </main>
    </div>
  );
}

function Column({
  name,
  cards,
  onMove,
}: {
  name: string;
  cards: Board["cards"];
  onMove: (businessId: string, stage: string) => void;
}) {
  return (
    <section className="flex w-64 shrink-0 flex-col rounded-lg border border-border bg-[var(--color-surface)]">
      <header className="border-b border-border px-3 py-2">
        <h2 className="text-sm font-medium">
          {name}
          <span className="ml-2 text-xs text-[var(--color-muted)]">{cards.length}</span>
        </h2>
      </header>
      <div className="flex-1 space-y-2 overflow-y-auto p-2">
        {cards.length === 0 && (
          <p className="px-1 py-2 text-center text-xs text-[var(--color-muted)]">Empty</p>
        )}
        {cards.map((card) => (
          <Card className="p-3" key={card.business_id}>
            <Link
              className="text-sm font-medium underline-offset-2 hover:underline"
              href={`/leads/${card.business_id}`}
            >
              {card.name}
            </Link>
            <p className="mt-0.5 text-xs text-[var(--color-muted)]">
              {card.primary_category ?? "no category"} · {card.city ?? "no city"}
            </p>
            <div className="mt-2 flex items-center justify-between gap-2">
              <span className="text-xs text-[var(--color-muted)]">website {card.website_status}</span>
              <select
                className="rounded border border-border bg-[var(--color-background)] px-1 py-0.5 text-xs"
                defaultValue=""
                onChange={(event) => {
                  if (event.target.value) onMove(card.business_id, event.target.value);
                }}
                aria-label={`Move ${card.name}`}
              >
                <option disabled value="">
                  move…
                </option>
                {(["New", "Researched", "Qualified", "Shortlisted", "Contacted", "Follow-up", "Interested", "Meeting Scheduled", "Proposal Sent", "Won", "Lost", "Archived"]).map((stageName) => (
                  <option key={stageName} value={stageName}>
                    {stageName}
                  </option>
                ))}
              </select>
            </div>
          </Card>
        ))}
      </div>
    </section>
  );
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
