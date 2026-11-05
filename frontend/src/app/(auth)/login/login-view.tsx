"use client";

import Image from "next/image";
import { Eye, EyeOff, UserRound, Sparkles, Check } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

import { useSession } from "@/components/providers/session-provider";
import { api } from "@/lib/api/client";

export function LoginView() {
  const router = useRouter();
  const { state, login } = useSession();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [rememberMe, setRememberMe] = useState(true);
  const [mode, setMode] = useState<"login" | "register">("login");
  const [registrationOpen, setRegistrationOpen] = useState(false);

  useEffect(() => {
    if (state === "signedIn") router.replace("/dashboard");
  }, [state, router]);

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      const rememberedEmail = window.localStorage.getItem("sparkx_login_id");
      if (rememberedEmail) setEmail(rememberedEmail);
    });
    return () => window.cancelAnimationFrame(frame);
  }, []);

  useEffect(() => {
    let active = true;
    api
      .get<{ allow_registration: boolean }>("/auth/status")
      .then((res) => {
        if (active) setRegistrationOpen(Boolean(res.allow_registration));
      })
      .catch(() => {
        if (active) setRegistrationOpen(false);
      });
    return () => {
      active = false;
    };
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);

    try {
      if (mode === "login") {
        const result = await login({ email, password });
        if (!result.ok) {
          setError(result.error);
        } else {
          if (rememberMe) window.localStorage.setItem("sparkx_login_id", email);
          else window.localStorage.removeItem("sparkx_login_id");
          router.replace("/dashboard");
        }
      } else {
        await api.post("/auth/register", {
          email,
          password,
          display_name: email.split("@")[0] || "Operator",
        });
        const result = await login({ email, password });
        if (!result.ok) {
          setError(result.error);
        } else {
          if (rememberMe) window.localStorage.setItem("sparkx_login_id", email);
          router.replace("/dashboard");
        }
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Authentication failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="relative isolate flex min-h-screen items-center justify-center overflow-hidden px-4 py-8 text-white select-none">
      {/* Animated Chromatic Liquid Background Layer */}
      <div className="absolute inset-0 -z-30 overflow-hidden pointer-events-none">
        <Image
          src="/chromatic-refraction-bg.jpg"
          alt="Chromatic Liquid Background"
          fill
          priority
          sizes="100vw"
          className="object-cover object-center animate-liquid-float scale-110"
        />
        {/* Soft Vignette Overlay to enhance contrast */}
        <div className="absolute inset-0 bg-black/35" />
      </div>

      {/* Floating Caustic Light Flares (Fluid Movement) */}
      <div className="pointer-events-none absolute -left-20 top-1/4 h-[32rem] w-[32rem] rounded-full bg-cyan-500/20 blur-[110px] animate-caustic-1 -z-20" />
      <div className="pointer-events-none absolute -right-20 bottom-1/4 h-[32rem] w-[32rem] rounded-full bg-fuchsia-500/20 blur-[120px] animate-caustic-2 -z-20" />
      <div className="pointer-events-none absolute left-1/3 bottom-10 h-72 w-72 rounded-full bg-amber-500/15 blur-[90px] -z-20" />

      {/* Glassmorphic Container matching Reference Image ca611a47 */}
      <div className="relative w-full max-w-[28rem] rounded-[2.5rem] refraction-glass-card p-8 sm:p-10 shadow-2xl transition-all duration-300">
        
        {/* Top Brand Indicator */}
        <div className="flex items-center justify-between mb-8">
          <div className="flex items-center gap-2.5">
            <div className="relative h-7 w-7 rounded-lg overflow-hidden border border-white/20 bg-white/10 shadow-inner">
              <Image
                src="/logo.png"
                alt="SparkXFlow Nexus"
                fill
                sizes="28px"
                className="object-cover"
              />
            </div>
            <span className="text-xs font-semibold tracking-wider uppercase text-white/70">
              SparkXFlow Nexus
            </span>
          </div>

          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-medium bg-white/10 border border-white/15 text-cyan-300">
            <span className="size-1.5 rounded-full bg-cyan-400 animate-pulse" /> Mission Control
          </span>
        </div>

        {/* Header Block */}
        <div className="mb-7 space-y-1">
          <h1 className="text-3xl sm:text-4xl font-extrabold tracking-tight text-white">
            {mode === "login" ? "Login" : "Sign Up"}
          </h1>
          <p className="text-sm text-white/70 font-medium">
            {mode === "login" ? "Welcome back" : "Create your operator account"}
          </p>
        </div>

        {/* Form Controls */}
        <form className="space-y-4" onSubmit={submit}>
          {/* User Name / Email Input */}
          <div className="relative">
            <input
              type="text"
              required
              autoComplete="username"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="User Name"
              className="w-full h-13 px-4.5 pr-12 rounded-2xl refraction-glass-input text-sm text-white placeholder-white/45 outline-none"
            />
            <UserRound
              aria-hidden="true"
              className="pointer-events-none absolute right-4 top-1/2 -translate-y-1/2 size-5 text-white/50"
              strokeWidth={1.75}
            />
          </div>

          {/* Password Input */}
          <div className="relative">
            <input
              type={showPassword ? "text" : "password"}
              required
              minLength={mode === "register" ? 12 : 1}
              autoComplete={mode === "register" ? "new-password" : "current-password"}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Password"
              className="w-full h-13 px-4.5 pr-12 rounded-2xl refraction-glass-input text-sm text-white placeholder-white/45 outline-none"
            />
            <button
              type="button"
              onClick={() => setShowPassword((prev) => !prev)}
              aria-label={showPassword ? "Hide password" : "Show password"}
              className="absolute right-3.5 top-1/2 -translate-y-1/2 p-1 rounded-lg text-white/50 hover:text-white transition"
            >
              {showPassword ? (
                <EyeOff className="size-5" strokeWidth={1.75} />
              ) : (
                <Eye className="size-5" strokeWidth={1.75} />
              )}
            </button>
          </div>

          {/* Remember me & Mode Info */}
          <div className="flex items-center justify-between text-xs pt-1 pb-1">
            <label className="flex items-center gap-2 cursor-pointer text-white/80 select-none">
              <input
                type="checkbox"
                checked={rememberMe}
                onChange={(e) => setRememberMe(e.target.checked)}
                className="size-4 rounded-md border-white/20 bg-white/10 text-cyan-400 focus:ring-0 cursor-pointer"
              />
              <span className="font-medium">Remember me</span>
            </label>

            {mode === "login" && (
              <span className="text-white/40 text-[11px]">Local Host Mode</span>
            )}
          </div>

          {/* Error Banner */}
          {error && (
            <div className="rounded-xl border border-rose-500/30 bg-rose-950/40 px-3.5 py-2 text-xs text-rose-200">
              {error}
            </div>
          )}

          {/* Submit Action Button */}
          <button
            type="submit"
            disabled={busy}
            className="w-full h-12 mt-2 rounded-2xl refraction-glass-btn text-sm font-semibold tracking-wide flex items-center justify-center gap-2 cursor-pointer disabled:opacity-50"
          >
            {busy ? (
              <span className="size-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            ) : mode === "login" ? (
              "Login"
            ) : (
              "Sign Up"
            )}
          </button>

          {/* Toggle between Login and Signup */}
          <div className="pt-3 text-center text-xs text-white/75">
            {mode === "login" ? (
              <p>
                Don&apos;t have an account?{" "}
                {registrationOpen ? (
                  <button
                    type="button"
                    onClick={() => {
                      setError(null);
                      setMode("register");
                    }}
                    className="font-semibold text-white hover:underline cursor-pointer"
                  >
                    Signup
                  </button>
                ) : (
                  <span className="text-white/40">Registration disabled</span>
                )}
              </p>
            ) : (
              <p>
                Already have an account?{" "}
                <button
                  type="button"
                  onClick={() => {
                    setError(null);
                    setMode("login");
                  }}
                  className="font-semibold text-white hover:underline cursor-pointer"
                >
                  Login
                </button>
              </p>
            )}
          </div>
        </form>
      </div>
    </main>
  );
}
