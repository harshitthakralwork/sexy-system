"use client";

import { useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { Sidebar } from "@/components/layout/sidebar";
import { useSession } from "@/components/providers/session-provider";

export default function DashboardLayout({ children }: { children: ReactNode }) {
  const router = useRouter();
  const { state } = useSession();

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

  return (
    <div className="flex h-screen overflow-hidden bg-[var(--color-background)]">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">{children}</div>
    </div>
  );
}
