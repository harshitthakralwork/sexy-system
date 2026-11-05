"use client";

import { useEffect, useRef } from "react";
import { useTheme } from "@/components/providers/theme-provider";

interface Particle {
  x: number;
  y: number;
  radius: number;
  vx: number;
  vy: number;
  color: string;
  alpha: number;
  pulseSpeed: number;
}

export function LiquidGlassBackground() {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const { theme } = useTheme();

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let animationFrameId: number;
    let width = (canvas.width = window.innerWidth);
    let height = (canvas.height = window.innerHeight);

    const handleResize = () => {
      if (!canvas) return;
      width = canvas.width = window.innerWidth;
      height = canvas.height = window.innerHeight;
    };
    window.addEventListener("resize", handleResize);

    const isLight = theme === "light";
    const colors = isLight
      ? [
          "rgba(168, 85, 247, 0.45)", // violet
          "rgba(0, 212, 255, 0.40)",  // cyan
          "rgba(244, 114, 182, 0.35)", // rose
          "rgba(99, 102, 241, 0.35)",  // indigo
        ]
      : [
          "rgba(0, 212, 255, 0.55)",  // cyan
          "rgba(168, 85, 247, 0.50)", // violet
          "rgba(255, 120, 73, 0.40)", // neon orange
          "rgba(56, 189, 248, 0.45)", // sky
        ];

    // Create drifting caustic particles
    const particleCount = Math.min(Math.floor((width * height) / 32000), 45);
    const particles: Particle[] = Array.from({ length: particleCount }, () => ({
      x: Math.random() * width,
      y: Math.random() * height,
      radius: Math.random() * 3.5 + 1.2,
      vx: (Math.random() - 0.5) * 0.45,
      vy: (Math.random() - 0.5) * 0.45,
      color: colors[Math.floor(Math.random() * colors.length)],
      alpha: Math.random() * 0.6 + 0.2,
      pulseSpeed: Math.random() * 0.02 + 0.005,
    }));

    // Large floating ambient caustic orbs
    const orbs = [
      { x: width * 0.15, y: height * 0.2, r: 320, vx: 0.18, vy: 0.12, color: colors[0] },
      { x: width * 0.85, y: height * 0.75, r: 360, vx: -0.15, vy: -0.16, color: colors[1] },
      { x: width * 0.5, y: height * 0.45, r: 280, vx: 0.12, vy: -0.14, color: colors[2] },
    ];

    let step = 0;
    const render = () => {
      step++;
      ctx.clearRect(0, 0, width, height);

      // 1. Draw large ambient luminous caustic gradients
      for (const orb of orbs) {
        orb.x += orb.vx;
        orb.y += orb.vy;
        if (orb.x < -orb.r) orb.x = width + orb.r;
        if (orb.x > width + orb.r) orb.x = -orb.r;
        if (orb.y < -orb.r) orb.y = height + orb.r;
        if (orb.y > height + orb.r) orb.y = -orb.r;

        const grad = ctx.createRadialGradient(orb.x, orb.y, 0, orb.x, orb.y, orb.r);
        grad.addColorStop(0, orb.color);
        grad.addColorStop(0.7, orb.color.replace(/[\d\.]+\)$/, "0.08)"));
        grad.addColorStop(1, "transparent");
        ctx.fillStyle = grad;
        ctx.beginPath();
        ctx.arc(orb.x, orb.y, orb.r, 0, Math.PI * 2);
        ctx.fill();
      }

      // 2. Draw drifting particles with glowing halo
      for (const p of particles) {
        p.x += p.vx;
        p.y += p.vy;

        if (p.x < 0) p.x = width;
        if (p.x > width) p.x = 0;
        if (p.y < 0) p.y = height;
        if (p.y > height) p.y = 0;

        const pulsingAlpha = Math.sin(step * p.pulseSpeed) * 0.25 + p.alpha;
        ctx.fillStyle = p.color.replace(/[\d\.]+\)$/, `${Math.max(0.05, pulsingAlpha)})`);
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2);
        ctx.fill();
      }

      animationFrameId = requestAnimationFrame(render);
    };

    render();

    return () => {
      window.removeEventListener("resize", handleResize);
      cancelAnimationFrame(animationFrameId);
    };
  }, [theme]);

  const isLight = theme === "light";

  return (
    <div className="pointer-events-none fixed inset-0 -z-30 overflow-hidden select-none">
      {/* Dynamic Base Gradient */}
      <div
        className={`absolute inset-0 transition-colors duration-500 ${
          isLight
            ? "bg-gradient-to-br from-[#f8fafc] via-[#f1f5f9] to-[#e2e8f0]"
            : "bg-gradient-to-br from-[#06070a] via-[#090b12] to-[#040508]"
        }`}
      />

      {/* HTML5 Canvas for real-time drifting particles & caustics */}
      <canvas ref={canvasRef} className="absolute inset-0 h-full w-full opacity-70" />

      {/* Floating 3D Liquid Glass Pills (Inspired by Liquid Glass UI Kit Image 1) */}
      <div className="absolute inset-0 overflow-hidden">
        {/* Floating pill 1: Primary Glass Button pill */}
        <div
          className={`absolute left-[7%] top-[14%] flex items-center gap-2 rounded-full px-4 py-2 border backdrop-blur-2xl shadow-xl transition-all duration-700 animate-float-slow ${
            isLight
              ? "bg-white/60 border-purple-400/40 text-purple-700 shadow-[0_12px_32px_rgba(168,85,247,0.18)]"
              : "bg-purple-950/25 border-purple-400/30 text-purple-300 shadow-[0_0_28px_rgba(168,85,247,0.22)]"
          }`}
          style={{ transform: "rotate(-6deg)" }}
        >
          <span className="h-2 w-2 rounded-full bg-purple-400 shadow-[0_0_8px_#a855f7] animate-pulse" />
          <span className="text-[11px] font-semibold tracking-wide">Primary Glass</span>
        </div>

        {/* Floating pill 2: Cyan Secondary Glass pill */}
        <div
          className={`absolute right-[9%] top-[22%] flex items-center gap-2 rounded-full px-4 py-2 border backdrop-blur-2xl shadow-xl transition-all duration-700 animate-float-reverse ${
            isLight
              ? "bg-white/60 border-cyan-400/40 text-cyan-700 shadow-[0_12px_32px_rgba(0,212,255,0.18)]"
              : "bg-cyan-950/25 border-cyan-400/30 text-cyan-300 shadow-[0_0_28px_rgba(0,212,255,0.22)]"
          }`}
          style={{ transform: "rotate(4deg)", animationDelay: "1.2s" }}
        >
          <span className="h-2 w-2 rounded-full bg-cyan-400 shadow-[0_0_8px_#00d4ff] animate-pulse" />
          <span className="text-[11px] font-semibold tracking-wide">Secondary Glass</span>
        </div>

        {/* Floating pill 3: Glass search badge */}
        <div
          className={`absolute left-[18%] bottom-[12%] flex items-center gap-2 rounded-full px-3.5 py-1.5 border backdrop-blur-2xl shadow-xl transition-all duration-700 animate-float-slow ${
            isLight
              ? "bg-white/70 border-slate-300/60 text-slate-700 shadow-[0_12px_24px_rgba(0,0,0,0.06)]"
              : "bg-white/[0.05] border-white/20 text-white/70 shadow-[0_0_20px_rgba(255,255,255,0.08)]"
          }`}
          style={{ transform: "rotate(3deg)", animationDelay: "2.4s" }}
        >
          <span className="text-[10px] font-medium">Search radar…</span>
          <span className="flex h-4 w-4 items-center justify-center rounded-full bg-cyan-500/20 text-[9px] font-bold text-cyan-300">
            +
          </span>
        </div>

        {/* Floating glass droplet 4 */}
        <div
          className={`absolute right-[14%] bottom-[16%] flex h-9 w-9 items-center justify-center rounded-full border backdrop-blur-3xl shadow-xl transition-all duration-700 animate-float-reverse ${
            isLight
              ? "bg-white/70 border-pink-400/30 text-pink-600 shadow-[0_8px_24px_rgba(244,114,182,0.2)]"
              : "bg-pink-950/30 border-pink-400/30 text-pink-300 shadow-[0_0_24px_rgba(244,114,182,0.25)]"
          }`}
          style={{ animationDelay: "0.8s" }}
        >
          <span className="h-3 w-3 rounded-full bg-pink-400/80 shadow-[0_0_8px_#f472b6]" />
        </div>
      </div>

      {/* Frosted Vignette & Fine Noise */}
      <div
        className={`absolute inset-0 transition-opacity duration-500 ${
          isLight
            ? "bg-radial-gradient from-transparent via-white/10 to-white/40 opacity-80"
            : "bg-radial-gradient from-transparent via-black/20 to-black/60 opacity-90"
        }`}
      />
    </div>
  );
}
