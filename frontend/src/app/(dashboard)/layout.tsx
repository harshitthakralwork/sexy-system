"use client";

import Image from "next/image";
import { useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { CommandPalette } from "@/components/layout/command-palette";
import { Sidebar } from "@/components/layout/sidebar";
import { useSession } from "@/components/providers/session-provider";
import { TaskActivityProvider } from "@/components/providers/task-activity-provider";

export default function DashboardLayout({ children }: { children: ReactNode }) {
  const router = useRouter();
  const { state, error } = useSession();

  useEffect(() => {
    if (state === "signedOut") router.replace("/login");
  }, [state, router]);

  if (state === "checking") {
    return (
      <div className="flex h-screen items-center justify-center bg-[#07080c] text-sm text-white/50">
        Checking your session…
      </div>
    );
  }

  if (state === "signedOut") {
    return null;
  }

  if (state === "error") {
    return (
      <div className="flex h-screen overflow-hidden bg-[#07080c]">
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
      <div className="dashboard-shell relative isolate flex h-screen overflow-hidden bg-[#06070a] text-white">
        {/* 1. Animated Chromatic Liquid Background Layer */}
        <div className="absolute inset-0 -z-30 overflow-hidden pointer-events-none">
          <Image
            src="/chromatic-refraction-bg.jpg"
            alt="Chromatic Liquid Background"
            fill
            priority
            sizes="100vw"
            className="object-cover object-center animate-liquid-float scale-110 opacity-55"
          />
          <div className="absolute inset-0 bg-gradient-to-b from-[#06070a]/50 via-[#06070a]/30 to-[#06070a]/70" />
        </div>

        {/* 2. Floating Chromatic Caustic Light Flares behind Dashboard */}
        <div className="pointer-events-none absolute -left-32 -top-32 h-[42rem] w-[42rem] rounded-full bg-cyan-500/25 blur-[140px] -z-10 animate-caustic-1" />
        <div className="pointer-events-none absolute -right-32 -bottom-32 h-[44rem] w-[44rem] rounded-full bg-purple-500/25 blur-[150px] -z-10 animate-caustic-2" />
        <div className="pointer-events-none absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 h-[48rem] w-[48rem] rounded-full bg-amber-500/15 blur-[160px] -z-10" />

        {/* 3. Translucent Blur Glass Shell */}
        <Sidebar />
        <div className="flex min-w-0 flex-1 flex-col overflow-hidden rounded-[32px] border border-white/15 bg-black/25 shadow-[0_24px_80px_rgba(0,0,0,0.6)] backdrop-blur-3xl m-2 sm:m-3">
          {children}
        </div>
        <CommandPalette />
      </div>
    </TaskActivityProvider>
  );
}
