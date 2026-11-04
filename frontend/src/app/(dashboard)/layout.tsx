"use client";

import { useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { CommandPalette } from "@/components/layout/command-palette";
import { Sidebar } from "@/components/layout/sidebar";
import { useSession } from "@/components/providers/session-provider";

export default function DashboardLayout({ children }: { children: ReactNode }) {
  const router = useRouter();
  const { state, error } = useSession();

  // The gate is a convenience, not the control. The backend refuses
  // unauthenticated data regardless of what is rendered here; this only stops
  // the shell from flashing an empty dashboard at someone who must sign in.
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
          <div className="max-w-md rounded-lg border border-[var(--color-error)]/30 bg-[var(--color-error)]/10 p-6">
            <h2 className="text-base font-semibold text-[var(--color-error)]">API Connection Error</h2>
            <p className="mt-2 text-xs text-[var(--color-muted)]">
              {error ?? "Unable to reach the backend service on http://127.0.0.1:8000."}
            </p>
            <button
              type="button"
              onClick={() => window.location.reload()}
              className="mt-4 rounded border border-[var(--color-primary)] bg-[var(--color-primary)] px-4 py-1.5 text-xs text-white hover:opacity-90"
            >
              Retry Connection
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="dashboard-shell flex h-screen overflow-hidden bg-transparent">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden rounded-[32px] border border-[var(--color-border)] bg-[var(--color-shell)] shadow-[0_24px_80px_rgba(31,34,31,0.18)] backdrop-blur-xl">{children}</div>
      <CommandPalette />
    </div>
  );
}
