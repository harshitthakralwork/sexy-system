"use client";

import { useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { CommandPalette } from "@/components/layout/command-palette";
import { Sidebar } from "@/components/layout/sidebar";
import { useSession } from "@/components/providers/session-provider";
import { TaskActivityProvider } from "@/components/providers/task-activity-provider";
import { LiquidGlassBackground } from "@/components/ui/liquid-glass-background";

export default function DashboardLayout({ children }: { children: ReactNode }) {
  const router = useRouter();
  const { state, error } = useSession();

  useEffect(() => {
    if (state === "signedOut") router.replace("/login");
  }, [state, router]);

  if (state === "checking") {
    return (
      <div className="flex h-screen items-center justify-center bg-[var(--color-background)] text-sm text-[var(--color-muted)]">
        Checking your session…
      </div>
    );
  }

  if (state === "signedOut") {
    return null;
  }

  if (state === "error") {
    return (
      <div className="flex h-screen overflow-hidden bg-[var(--color-background)]">
        <Sidebar />
        <div className="flex min-w-0 flex-1 flex-col items-center justify-center gap-3 p-6 text-center">
          <div className="max-w-md rounded-2xl border border-red-500/30 bg-red-950/20 p-6 backdrop-blur-xl">
            <h2 className="text-base font-semibold text-red-400">API Connection Error</h2>
            <p className="mt-2 text-xs text-white/60">
              {error ?? "Unable to reach the backend service on http://127.0.0.1:8002."}
            </p>
            <button
              type="button"
              onClick={() => window.location.reload()}
              className="mt-4 rounded-full border border-cyan-500/30 bg-cyan-600/20 px-5 py-2 text-xs font-semibold text-cyan-300 hover:bg-cyan-600/30"
            >
              Retry Connection
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <TaskActivityProvider>
      <div className="dashboard-shell relative isolate flex h-screen overflow-hidden bg-[#06070a] text-[var(--color-foreground)] transition-colors duration-300">
        {/* Animated Liquid Glass Background with moving particles, caustics & 3D floating glass elements */}
        <LiquidGlassBackground />

        {/* Subtle blurred ambient light blooms in deep cyan, violet, and restrained pink around edges */}
        <div className="pointer-events-none absolute -left-20 -top-20 h-[40rem] w-[40rem] rounded-full bg-cyan-500/15 blur-[160px] -z-10 animate-caustic-1" />
        <div className="pointer-events-none absolute -right-20 -bottom-20 h-[44rem] w-[44rem] rounded-full bg-violet-600/16 blur-[170px] -z-10 animate-caustic-2" />
        <div className="pointer-events-none absolute right-1/4 -top-24 h-[32rem] w-[32rem] rounded-full bg-pink-500/10 blur-[150px] -z-10" />
        <div className="pointer-events-none absolute left-1/3 -bottom-24 h-[36rem] w-[36rem] rounded-full bg-cyan-600/10 blur-[160px] -z-10" />

        {/* Layered Dark Frosted Glass Shell (28px radius) */}
        <Sidebar />
        <div className="flex min-w-0 flex-1 flex-col overflow-hidden liquid-glass-shell m-2 sm:m-3 transition-colors duration-300">
          {children}
        </div>
        <CommandPalette />
      </div>
    </TaskActivityProvider>
  );
}
