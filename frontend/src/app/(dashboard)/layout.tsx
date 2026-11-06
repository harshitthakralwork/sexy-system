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
      <div className="astra-shell relative isolate flex h-screen overflow-hidden text-[var(--color-foreground)] select-none">
        {/* Subtle Matte Background */}
        <LiquidGlassBackground />

        {/* Sidebar */}
        <Sidebar />

        {/* Main Workspace Surface */}
        <div className="astra-workspace flex min-w-0 flex-1 flex-col overflow-hidden">
          {children}
        </div>
        <CommandPalette />
      </div>
    </TaskActivityProvider>
  );
}
