"use client";

import Image from "next/image";
import Link from "next/link";
import { ArrowRight, Building, Globe2, MapPin, Phone, Radar, Sparkles, Star } from "lucide-react";

export function MapPreviewBanner() {
  return (
    <div className="relative overflow-hidden rounded-[26px] liquid-glass-panel p-5 sm:p-6 shadow-2xl transition-all">
      {/* Header Info */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-2xl liquid-badge-violet shadow-inner">
            <MapPin size={20} className="text-violet-300" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-base sm:text-lg font-extrabold tracking-tight text-[var(--color-foreground)] font-sans">
                Map Intelligence & Local Discovery
              </h3>
              <span className="liquid-badge-violet px-2.5 py-0.5 text-[10px] font-bold">
                10 km Radar
              </span>
            </div>
            <p className="text-xs text-[var(--color-muted)] font-medium">
              Discover verified businesses with contact info, ratings, and search radius mapping
            </p>
          </div>
        </div>

        <Link
          href="/leads/map"
          className="liquid-btn-primary flex items-center justify-center gap-2 px-5 py-2.5 text-xs font-bold shadow-lg cursor-pointer"
        >
          <span>Open Local Business Finder</span>
          <ArrowRight size={14} className="text-white" />
        </Link>
      </div>

      {/* Static Image Preview of Map (Zero GPU usage) */}
      <Link
        href="/leads/map"
        className="group relative block w-full overflow-hidden rounded-[20px] border border-white/15 dark:border-white/10 shadow-inner cursor-pointer"
      >
        <div className="relative aspect-[21/9] sm:aspect-[2.4/1] w-full max-h-[360px] overflow-hidden">
          <Image
            src="/map-preview.jpg"
            alt="Map Intelligence Radar Preview"
            fill
            sizes="(max-width: 1200px) 100vw, 1200px"
            className="object-cover object-center transition-transform duration-500 group-hover:scale-102"
            priority
          />

          {/* Frosted vignette */}
          <div className="absolute inset-0 bg-gradient-to-t from-black/70 via-black/20 to-transparent pointer-events-none" />

          {/* Hover Overlay Prompt */}
          <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity duration-300 bg-black/40 backdrop-blur-xs">
            <div className="liquid-btn-primary flex items-center gap-2 px-6 py-2.5 text-xs font-bold shadow-2xl">
              <Radar className="h-4 w-4 animate-spin" />
              <span>Click to Launch Live Radar Map →</span>
            </div>
          </div>

          {/* Bottom Callout Info inside preview */}
          <div className="absolute bottom-3 left-3 right-3 flex flex-wrap items-center justify-between gap-2 pointer-events-none">
            <div className="liquid-glass-subcard flex items-center gap-2 px-3 py-1.5 backdrop-blur-md text-xs text-white">
              <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse shadow-[0_0_8px_#34d399]" />
              <span className="font-semibold">Live Satellite Search Ready</span>
              <span className="text-white/40">•</span>
              <span className="text-white/70">Surat, Delhi, Mumbai & Global Metros</span>
            </div>

            <div className="hidden sm:flex items-center gap-3 text-white text-[11px] font-semibold liquid-glass-subcard px-3.5 py-1.5 backdrop-blur-md">
              <span className="flex items-center gap-1 text-purple-300"><Building size={12} /> 480+ Leads</span>
              <span className="flex items-center gap-1 text-sky-300"><Phone size={12} /> Direct Contact</span>
              <span className="flex items-center gap-1 text-amber-300"><Star size={12} /> 4.2+ Rating</span>
            </div>
          </div>
        </div>
      </Link>
    </div>
  );
}

