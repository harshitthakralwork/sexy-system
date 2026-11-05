"use client";

import { useTheme } from "@/components/providers/theme-provider";

export function LiquidGlassBackground() {
  const { theme } = useTheme();
  const isLight = theme === "light";

  return (
    <div className="pointer-events-none fixed inset-0 -z-30 overflow-hidden select-none">
      {/* 1. Dynamic Base Gradient */}
      <div
        className={`absolute inset-0 transition-colors duration-700 ${
          isLight
            ? "bg-gradient-to-br from-[#f8fafc] via-[#f1f5f9] to-[#e2e8f0]"
            : "bg-gradient-to-br from-[#06070a] via-[#090b12] to-[#040508]"
        }`}
      />

      {/* 2. Hardware-accelerated CSS Caustic Orbs (Zero GPU spike) */}
      <div className="absolute inset-0 overflow-hidden">
        {/* Violet Caustic Glow */}
        <div
          className={`absolute -left-[10%] top-[5%] h-[38rem] w-[38rem] rounded-full blur-[140px] transition-all duration-1000 ${
            isLight
              ? "bg-purple-300/35"
              : "bg-purple-600/18"
          } animate-caustic-1`}
          style={{ willChange: "transform" }}
        />

        {/* Cyan Caustic Glow */}
        <div
          className={`absolute -right-[10%] top-[40%] h-[42rem] w-[42rem] rounded-full blur-[150px] transition-all duration-1000 ${
            isLight
              ? "bg-cyan-300/35"
              : "bg-cyan-500/18"
          } animate-caustic-2`}
          style={{ willChange: "transform" }}
        />

        {/* Neon Amber Accent */}
        <div
          className={`absolute left-[40%] -bottom-[10%] h-[32rem] w-[32rem] rounded-full blur-[160px] transition-all duration-1000 ${
            isLight
              ? "bg-amber-200/30"
              : "bg-[#FF7849]/12"
          }`}
        />
      </div>

      {/* 3. Floating 3D Liquid Glass Pills (Matching Liquid Glass UI Kit) */}
      <div className="absolute inset-0 overflow-hidden">
        {/* Floating pill 1: Primary Glass Button pill */}
        <div
          className={`absolute left-[6%] top-[12%] flex items-center gap-2 rounded-full px-4 py-2 border backdrop-blur-2xl shadow-xl transition-all duration-700 animate-float-slow ${
            isLight
              ? "bg-white/70 border-purple-400/40 text-purple-700 shadow-[0_12px_32px_rgba(168,85,247,0.14)]"
              : "bg-purple-950/30 border-purple-400/30 text-purple-300 shadow-[0_0_28px_rgba(168,85,247,0.22)]"
          }`}
          style={{ transform: "rotate(-6deg)" }}
        >
          <span className="h-2 w-2 rounded-full bg-purple-400 shadow-[0_0_8px_#a855f7] animate-pulse" />
          <span className="text-[11px] font-semibold tracking-wide">Primary Glass</span>
        </div>

        {/* Floating pill 2: Cyan Secondary Glass pill */}
        <div
          className={`absolute right-[8%] top-[18%] flex items-center gap-2 rounded-full px-4 py-2 border backdrop-blur-2xl shadow-xl transition-all duration-700 animate-float-reverse ${
            isLight
              ? "bg-white/70 border-cyan-400/40 text-cyan-700 shadow-[0_12px_32px_rgba(0,212,255,0.14)]"
              : "bg-cyan-950/30 border-cyan-400/30 text-cyan-300 shadow-[0_0_28px_rgba(0,212,255,0.22)]"
          }`}
          style={{ transform: "rotate(4deg)", animationDelay: "1.2s" }}
        >
          <span className="h-2 w-2 rounded-full bg-cyan-400 shadow-[0_0_8px_#00d4ff] animate-pulse" />
          <span className="text-[11px] font-semibold tracking-wide">Secondary Glass</span>
        </div>

        {/* Floating pill 3: Glass search badge */}
        <div
          className={`absolute left-[16%] bottom-[10%] flex items-center gap-2 rounded-full px-3.5 py-1.5 border backdrop-blur-2xl shadow-xl transition-all duration-700 animate-float-slow ${
            isLight
              ? "bg-white/80 border-slate-300/60 text-slate-700 shadow-[0_12px_24px_rgba(0,0,0,0.06)]"
              : "bg-white/[0.05] border-white/20 text-white/70 shadow-[0_0_20px_rgba(255,255,255,0.08)]"
          }`}
          style={{ transform: "rotate(3deg)", animationDelay: "2.4s" }}
        >
          <span className="text-[10px] font-medium">Search radar…</span>
          <span className="flex h-4 w-4 items-center justify-center rounded-full bg-cyan-500/20 text-[9px] font-bold text-cyan-400">
            +
          </span>
        </div>

        {/* Floating glass droplet 4 */}
        <div
          className={`absolute right-[12%] bottom-[14%] flex h-9 w-9 items-center justify-center rounded-full border backdrop-blur-3xl shadow-xl transition-all duration-700 animate-float-reverse ${
            isLight
              ? "bg-white/80 border-pink-400/30 text-pink-600 shadow-[0_8px_24px_rgba(244,114,182,0.18)]"
              : "bg-pink-950/30 border-pink-400/30 text-pink-300 shadow-[0_0_24px_rgba(244,114,182,0.25)]"
          }`}
          style={{ animationDelay: "0.8s" }}
        >
          <span className="h-3 w-3 rounded-full bg-pink-400/80 shadow-[0_0_8px_#f472b6]" />
        </div>
      </div>

      {/* 4. Fine frosted ambient overlay */}
      <div
        className={`absolute inset-0 transition-opacity duration-700 ${
          isLight
            ? "bg-radial-gradient from-transparent via-white/5 to-white/30 opacity-70"
            : "bg-radial-gradient from-transparent via-black/10 to-black/50 opacity-80"
        }`}
      />
    </div>
  );
}
