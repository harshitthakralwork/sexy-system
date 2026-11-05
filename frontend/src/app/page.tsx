"use client";

import Image from "next/image";
import Link from "next/link";
import { useState } from "react";
import {
  Radar,
  Sparkles,
  ArrowRight,
  ShieldCheck,
  Search,
  ExternalLink,
  Flame,
  CheckCircle2,
  Cpu,
  Workflow,
  Globe2,
} from "lucide-react";
import { useSession } from "@/components/providers/session-provider";

export default function HomePage() {
  const { state } = useSession();
  const [activeQuery, setActiveQuery] = useState("looking for B2B web design agency in Austin");
  const [selectedTag, setSelectedTag] = useState("Service needed");

  const sampleQueries = [
    { text: "looking for B2B web design agency in Austin", category: "Service needed" },
    { text: "need freelance full-stack engineer for MVP", category: "Freelancer hiring" },
    { text: "recommend reliable commercial HVAC contractor", category: "Recommendation request" },
    { text: "best CRM vendor for small legal team", category: "Vendor search" },
  ];

  return (
    <div className="relative isolate min-h-screen overflow-x-hidden bg-[#06070a] text-white selection:bg-cyan-500/30 selection:text-cyan-200">
      {/* 1. Animated Chromatic Liquid Background */}
      <div className="fixed inset-0 -z-30 overflow-hidden pointer-events-none">
        <Image
          src="/chromatic-refraction-bg.jpg"
          alt="Chromatic Liquid Background"
          fill
          priority
          sizes="100vw"
          className="object-cover object-center animate-liquid-float scale-110 opacity-70"
        />
        <div className="absolute inset-0 bg-gradient-to-b from-[#06070a]/60 via-[#06070a]/40 to-[#06070a]/90" />
      </div>

      {/* 2. Floating Chromatic Caustic Light Orbs */}
      <div className="pointer-events-none fixed -left-32 top-1/4 h-[38rem] w-[38rem] rounded-full bg-cyan-500/20 blur-[130px] animate-caustic-1 -z-20" />
      <div className="pointer-events-none fixed -right-32 bottom-1/4 h-[42rem] w-[42rem] rounded-full bg-fuchsia-500/20 blur-[140px] animate-caustic-2 -z-20" />
      <div className="pointer-events-none fixed left-1/3 top-10 h-80 w-80 rounded-full bg-amber-500/15 blur-[100px] -z-20" />

      {/* 3. Top Frosted Glass Navigation Bar */}
      <header className="sticky top-0 z-50 w-full border-b border-white/10 bg-black/25 backdrop-blur-2xl">
        <div className="mx-auto flex h-20 max-w-7xl items-center justify-between px-6 sm:px-8">
          <Link href="/" className="flex items-center gap-3 group">
            <div className="relative h-9 w-9 rounded-xl overflow-hidden border border-white/20 bg-white/10 shadow-inner transition-transform group-hover:scale-105">
              <Image
                src="/logo.png"
                alt="SparkXFlow Nexus"
                fill
                sizes="36px"
                className="object-cover"
              />
            </div>
            <div className="flex flex-col">
              <span className="text-sm font-bold tracking-wider uppercase text-white">
                SparkXFlow <span className="text-cyan-400">Nexus</span>
              </span>
              <span className="text-[10px] tracking-widest uppercase text-white/50">
                Lead & Post Intelligence
              </span>
            </div>
          </Link>

          <nav className="hidden md:flex items-center gap-8 text-xs font-semibold uppercase tracking-wider text-white/70">
            <Link href="#features" className="hover:text-white transition-colors">
              Engines
            </Link>
            <Link href="#intelligence" className="hover:text-white transition-colors">
              Intent AI
            </Link>
            <Link href="#preview" className="hover:text-white transition-colors">
              Live Preview
            </Link>
            <Link href="/intelligence/posts" className="hover:text-cyan-400 transition-colors">
              Post Explorer
            </Link>
          </nav>

          <div className="flex items-center gap-3">
            {state === "signedIn" ? (
              <Link
                href="/dashboard"
                className="refraction-glass-btn inline-flex items-center gap-2 rounded-full px-5 py-2.5 text-xs font-bold text-white uppercase tracking-wider"
              >
                <span>Mission Control</span>
                <ArrowRight size={14} className="text-cyan-400" />
              </Link>
            ) : (
              <>
                <Link
                  href="/login"
                  className="rounded-full px-4 py-2 text-xs font-semibold text-white/80 hover:text-white transition-colors"
                >
                  Sign In
                </Link>
                <Link
                  href="/login"
                  className="refraction-glass-btn inline-flex items-center gap-2 rounded-full px-5 py-2.5 text-xs font-bold text-white uppercase tracking-wider"
                >
                  <span>Launch Nexus</span>
                  <ArrowRight size={14} className="text-cyan-400" />
                </Link>
              </>
            )}
          </div>
        </div>
      </header>

      {/* 4. Hero Section */}
      <section className="relative pt-16 pb-24 sm:pt-24 sm:pb-32 px-6 sm:px-8">
        <div className="mx-auto max-w-7xl text-center space-y-8">
          {/* Top Pill Status Badge */}
          <div className="inline-flex items-center gap-2.5 rounded-full px-4 py-1.5 refraction-glass-card border-white/20 text-xs font-semibold text-cyan-300 shadow-lg">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-cyan-500" />
            </span>
            <span>Local & Public Autonomous Lead Intelligence Platform</span>
            <span className="text-white/40">|</span>
            <span className="text-white/80">Zero Hallucinations</span>
          </div>

          {/* Main Title */}
          <h1 className="mx-auto max-w-5xl text-4xl sm:text-6xl lg:text-7xl font-extrabold tracking-tight text-white leading-[1.1]">
            Turn Public Conversations & Maps into{" "}
            <span className="bg-gradient-to-r from-cyan-400 via-sky-300 to-fuchsia-400 bg-clip-text text-transparent">
              High-Intent Pipelines
            </span>
          </h1>

          {/* Subtitle */}
          <p className="mx-auto max-w-2xl text-base sm:text-lg text-white/70 leading-relaxed font-normal">
            Continuous, compliance-first business discovery across self-hosted SearXNG, Reddit RSS/JSON,
            LinkedIn public snippets, Google Maps, and directories. Deterministic scoring with zero fake data.
          </p>

          {/* CTAs */}
          <div className="flex flex-wrap items-center justify-center gap-4 pt-2">
            <Link
              href="/dashboard"
              className="refraction-glass-btn inline-flex items-center gap-2.5 rounded-full px-8 py-3.5 text-sm font-bold text-white shadow-[0_0_30px_rgba(0,212,255,0.25)] hover:shadow-[0_0_45px_rgba(0,212,255,0.45)]"
            >
              <Sparkles size={16} className="text-cyan-400" />
              <span>Enter Mission Control</span>
              <ArrowRight size={16} />
            </Link>

            <Link
              href="/intelligence/posts"
              className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/5 px-7 py-3.5 text-sm font-semibold text-white/90 hover:bg-white/10 hover:border-white/30 backdrop-blur-xl transition-all"
            >
              <Radar size={16} className="text-violet-400" />
              <span>Explore Demand Posts</span>
            </Link>
          </div>

          {/* Interactive Search Bar Simulation */}
          <div className="mx-auto max-w-3xl pt-8">
            <div className="relative rounded-full refraction-glass-card p-2 sm:p-2.5 flex items-center gap-3 border-white/25 shadow-2xl">
              <div className="flex items-center justify-center pl-4 text-cyan-400">
                <Search size={20} />
              </div>
              <input
                type="text"
                value={activeQuery}
                onChange={(e) => setActiveQuery(e.target.value)}
                placeholder="Search any intent: 'need web design in Chicago', 'commercial plumbing vendor'..."
                className="w-full bg-transparent text-sm sm:text-base text-white placeholder-white/40 focus:outline-none"
              />
              <Link
                href={`/leads/discover?query=${encodeURIComponent(activeQuery)}`}
                className="refraction-glass-btn shrink-0 rounded-full px-5 sm:px-6 py-2.5 text-xs sm:text-sm font-bold text-white flex items-center gap-2"
              >
                <span>Run Signal Scan</span>
                <ArrowRight size={14} className="text-cyan-400" />
              </Link>
            </div>

            {/* Quick intent tags */}
            <div className="mt-3 flex flex-wrap items-center justify-center gap-2 text-xs text-white/60">
              <span className="text-white/40">Try queries:</span>
              {sampleQueries.map((item) => (
                <button
                  key={item.text}
                  type="button"
                  onClick={() => {
                    setActiveQuery(item.text);
                    setSelectedTag(item.category);
                  }}
                  className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-[11px] text-white/70 hover:border-white/25 hover:text-white transition-colors"
                >
                  {item.text}
                </button>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* 5. Centerpiece Showcase: Glassmorphic UI Card (Direct Reference to Image ca611a47) */}
      <section id="preview" className="relative py-12 px-6 sm:px-8">
        <div className="mx-auto max-w-6xl">
          <div className="text-center mb-10 space-y-2">
            <h2 className="text-2xl sm:text-3xl font-extrabold text-white tracking-tight">
              Evidence-First Lead & Post Intelligence
            </h2>
            <p className="text-sm text-white/65 max-w-xl mx-auto">
              Every lead card includes exact source provenance, classification rules, confidence scores,
              and strict separation of user notes.
            </p>
          </div>

          {/* Reference-Styled Blur Glass Card Container */}
          <div className="relative mx-auto max-w-3xl rounded-[2.5rem] refraction-glass-card p-6 sm:p-10 shadow-2xl transition-all duration-300">
            {/* Top Bar of Glass Card */}
            <div className="flex flex-wrap items-center justify-between gap-4 border-b border-white/10 pb-6 mb-6">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-cyan-500/20 border border-cyan-400/30 text-cyan-300">
                  <Flame size={20} />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-bold text-white">Live Demand Signal</span>
                    <span className="rounded-full bg-rose-500/20 border border-rose-400/30 px-2 py-0.5 text-[10px] font-bold text-rose-300">
                      HOT LEAD
                    </span>
                  </div>
                  <span className="text-xs text-white/50">Discovered 14m ago via Reddit JSON</span>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <span className="rounded-full bg-cyan-500/15 border border-cyan-400/25 px-3 py-1 text-xs font-semibold text-cyan-300">
                  {selectedTag}
                </span>
                <span className="rounded-full bg-white/10 border border-white/15 px-2.5 py-1 text-xs font-mono font-bold text-emerald-400">
                  Score 92/100
                </span>
              </div>
            </div>

            {/* Content Body */}
            <div className="space-y-4">
              <div className="space-y-1">
                <h3 className="text-lg font-bold text-white tracking-tight">
                  &ldquo;Looking for an agency or senior freelancer to rebuild our B2B SaaS platform in Next.js&rdquo;
                </h3>
                <p className="text-xs text-white/70 leading-relaxed font-sans">
                  We recently secured seed funding and our current PHP prototype cannot scale. Need a team or contractor
                  experienced in Next.js, FastAPI, and PostgreSQL. Budget is $15k-$25k with immediate start.
                </p>
              </div>

              {/* Extraction Evidence Grid */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 pt-2">
                <div className="rounded-2xl border border-white/10 bg-white/5 p-3">
                  <span className="block text-[10px] font-semibold uppercase text-white/45">Platform</span>
                  <span className="text-xs font-bold text-white">Reddit · r/startups</span>
                </div>
                <div className="rounded-2xl border border-white/10 bg-white/5 p-3">
                  <span className="block text-[10px] font-semibold uppercase text-white/45">Retrieval Status</span>
                  <span className="text-xs font-bold text-emerald-400 flex items-center gap-1">
                    <CheckCircle2 size={12} /> full_text
                  </span>
                </div>
                <div className="rounded-2xl border border-white/10 bg-white/5 p-3">
                  <span className="block text-[10px] font-semibold uppercase text-white/45">Confidence</span>
                  <span className="text-xs font-bold text-cyan-300">95% High</span>
                </div>
                <div className="rounded-2xl border border-white/10 bg-white/5 p-3">
                  <span className="block text-[10px] font-semibold uppercase text-white/45">Services Match</span>
                  <span className="text-xs font-bold text-violet-300">Web Dev, Next.js</span>
                </div>
              </div>

              {/* Provenance Footer */}
              <div className="mt-4 flex flex-wrap items-center justify-between gap-3 pt-4 border-t border-white/10 text-xs">
                <div className="flex items-center gap-2 text-white/60">
                  <span className="font-semibold text-white/80">u/tech_founder_24</span>
                  <span>·</span>
                  <span className="truncate max-w-[220px]">https://reddit.com/r/startups/comments/18...</span>
                </div>
                <div className="flex items-center gap-2">
                  <Link
                    href="/intelligence/posts"
                    className="refraction-glass-btn rounded-full px-4 py-1.5 text-xs font-bold text-white flex items-center gap-1.5"
                  >
                    <span>View in Explorer</span>
                    <ExternalLink size={12} className="text-cyan-400" />
                  </Link>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* 6. Feature Grid with Frosted Glass Panels */}
      <section id="features" className="relative py-20 px-6 sm:px-8 border-t border-white/10">
        <div className="mx-auto max-w-7xl">
          <div className="text-center max-w-3xl mx-auto mb-16 space-y-3">
            <span className="text-xs font-bold uppercase tracking-widest text-cyan-400">
              System Capabilities
            </span>
            <h2 className="text-3xl sm:text-4xl font-extrabold text-white tracking-tight">
              Engineered for Real Signals, Not Synthetic Noise
            </h2>
            <p className="text-sm sm:text-base text-white/65">
              Built on transparent, verifiable ingestion pipelines. No fake numbers, no bypass tricks,
              and 100% auditable provenance.
            </p>
          </div>

          <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-4">
            {/* Card 1 */}
            <div className="rounded-[2rem] refraction-glass-card p-6 border-white/15 space-y-4 hover:border-cyan-400/40 transition-colors">
              <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-cyan-500/15 border border-cyan-400/30 text-cyan-300">
                <Globe2 size={24} />
              </div>
              <h3 className="text-base font-bold text-white">Multi-Engine Discovery</h3>
              <p className="text-xs text-white/65 leading-relaxed">
                Federates SearXNG, Reddit JSON/RSS, LinkedIn site dorking, Google Maps public business records,
                and local directories into a normalized stream.
              </p>
            </div>

            {/* Card 2 */}
            <div className="rounded-[2rem] refraction-glass-card p-6 border-white/15 space-y-4 hover:border-violet-400/40 transition-colors">
              <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-violet-500/15 border border-violet-400/30 text-violet-300">
                <Cpu size={24} />
              </div>
              <h3 className="text-base font-bold text-white">Deterministic Intent AI</h3>
              <p className="text-xs text-white/65 leading-relaxed">
                8 rule-backed intent categories with positive and negative phrase penalties. Generic discussions
                are filtered out so you only see genuine buying demand.
              </p>
            </div>

            {/* Card 3 */}
            <div className="rounded-[2rem] refraction-glass-card p-6 border-white/15 space-y-4 hover:border-emerald-400/40 transition-colors">
              <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-emerald-500/15 border border-emerald-400/30 text-emerald-300">
                <ShieldCheck size={24} />
              </div>
              <h3 className="text-base font-bold text-white">SSRF Guard & Compliance</h3>
              <p className="text-xs text-white/65 leading-relaxed">
                Strict private IP isolation, canonical URL normalization, redirect destination verification,
                and respect for public robots headers.
              </p>
            </div>

            {/* Card 4 */}
            <div className="rounded-[2rem] refraction-glass-card p-6 border-white/15 space-y-4 hover:border-amber-400/40 transition-colors">
              <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-amber-500/15 border border-amber-400/30 text-amber-300">
                <Workflow size={24} />
              </div>
              <h3 className="text-base font-bold text-white">Audited CRM & Outreach</h3>
              <p className="text-xs text-white/65 leading-relaxed">
                User notes, hot/cold status, and follow-up dates remain strictly user-owned and will never be
                overwritten by automated re-enrichment runs.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* 7. Live Metrics Strip */}
      <section className="relative py-12 px-6 sm:px-8 border-t border-white/10 bg-black/40 backdrop-blur-2xl">
        <div className="mx-auto max-w-7xl grid grid-cols-2 md:grid-cols-4 gap-6 text-center">
          <div>
            <div className="text-3xl sm:text-4xl font-extrabold text-cyan-400">5</div>
            <div className="mt-1 text-xs font-semibold uppercase tracking-wider text-white/60">
              Discovery Engines
            </div>
          </div>
          <div>
            <div className="text-3xl sm:text-4xl font-extrabold text-white">100%</div>
            <div className="mt-1 text-xs font-semibold uppercase tracking-wider text-white/60">
              Deterministic Rules
            </div>
          </div>
          <div>
            <div className="text-3xl sm:text-4xl font-extrabold text-emerald-400">0</div>
            <div className="mt-1 text-xs font-semibold uppercase tracking-wider text-white/60">
              Hallucinated Values
            </div>
          </div>
          <div>
            <div className="text-3xl sm:text-4xl font-extrabold text-fuchsia-400">100%</div>
            <div className="mt-1 text-xs font-semibold uppercase tracking-wider text-white/60">
              Self-Hosted Local
            </div>
          </div>
        </div>
      </section>

      {/* 8. Bottom CTA Banner */}
      <section className="relative py-20 px-6 sm:px-8 text-center">
        <div className="mx-auto max-w-4xl rounded-[3rem] refraction-glass-card p-10 sm:p-14 border-white/20 shadow-2xl space-y-6">
          <h2 className="text-3xl sm:text-4xl font-extrabold text-white tracking-tight">
            Ready to deploy your intelligence engine?
          </h2>
          <p className="text-sm sm:text-base text-white/70 max-w-xl mx-auto">
            Access your Mission Control dashboard, run ad-hoc searches, or monitor live social signals.
          </p>
          <div className="pt-2 flex flex-wrap items-center justify-center gap-4">
            <Link
              href="/login"
              className="refraction-glass-btn inline-flex items-center gap-2 rounded-full px-8 py-3.5 text-sm font-bold text-white shadow-[0_0_30px_rgba(0,212,255,0.3)]"
            >
              <span>Launch Mission Control</span>
              <ArrowRight size={16} className="text-cyan-400" />
            </Link>
          </div>
        </div>
      </section>

      {/* 9. Minimalist Glass Footer */}
      <footer className="border-t border-white/10 py-8 px-6 sm:px-8 text-center text-xs text-white/45">
        <div className="mx-auto max-w-7xl flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <span className="font-semibold text-white/80">SparkXFlow Nexus</span>
            <span>·</span>
            <span>Local & Public Intelligence Platform</span>
          </div>
          <div className="flex items-center gap-6">
            <Link href="/dashboard" className="hover:text-white transition-colors">
              Dashboard
            </Link>
            <Link href="/intelligence/posts" className="hover:text-white transition-colors">
              Post Explorer
            </Link>
            <Link href="/sources" className="hover:text-white transition-colors">
              Source Health
            </Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
