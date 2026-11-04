"use client";

import Image from "next/image";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

import { useSession } from "@/components/providers/session-provider";
import { api } from "@/lib/api/client";
import type { RuntimeInfo } from "@/lib/api/types";

export function LoginView() {
  const router = useRouter();
  const { state, login } = useSession();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [mode, setMode] = useState<"login" | "register">("login");
  const [registrationOpen, setRegistrationOpen] = useState(false);

  useEffect(() => {
    if (state === "signedIn") router.replace("/dashboard");
  }, [state, router]);

  // The signup affordance follows the server's setting rather than assuming it,
  // so a closed instance never shows a form that cannot work.
  useEffect(() => {
    let active = true;
    api
      .get<RuntimeInfo>("/info")
      .then((info) => active && setRegistrationOpen(info.registration_open))
      .catch(() => active && setRegistrationOpen(false));
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
          router.replace("/dashboard");
        }
      } else {
        await api.post("/auth/register", {
          email,
          password,
          display_name: email.split("@")[0] ?? "Operator",
        });
        const result = await login({ email, password });
        if (!result.ok) {
          setError(result.error);
        } else {
          router.replace("/dashboard");
        }
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-[var(--color-background)] p-6">
      <div className="w-full max-w-sm rounded-3xl border border-white/10 bg-[#2D2A2E] p-8 shadow-2xl">
        <div className="flex items-center gap-3.5 mb-6">
          <div className="relative h-12 w-12 shrink-0 rounded-2xl overflow-hidden border border-white/10 shadow-md">
            <Image
              src="/logo.png"
              alt="SparkXFlow Nexus"
              width={48}
              height={48}
              className="h-full w-full object-cover"
              priority
            />
          </div>
          <div>
            <h1 className="text-xl font-extrabold text-white tracking-tight">SparkXFlow Nexus</h1>
            <p className="text-xs text-[var(--color-muted)] font-medium">
              {mode === "login" ? "Sign in to Mission Control" : "Create the first account"}
            </p>
          </div>
        </div>

        <form className="mt-5 space-y-3" onSubmit={submit}>
          <label className="block text-sm">
            <span className="text-[var(--color-muted)]">Email</span>
            <input
              type="email"
              required
              autoComplete="username"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              className="mt-1 w-full rounded-md border border-border bg-[var(--color-background)] px-3 py-2 text-sm"
            />
          </label>

          <label className="block text-sm">
            <span className="text-[var(--color-muted)]">Password</span>
            <input
              type="password"
              required
              minLength={mode === "register" ? 12 : 1}
              autoComplete={mode === "register" ? "new-password" : "current-password"}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className="mt-1 w-full rounded-md border border-border bg-[var(--color-background)] px-3 py-2 text-sm"
            />
            {mode === "register" && (
              <span className="mt-1 block text-xs text-[var(--color-muted)]">
                At least 12 characters.
              </span>
            )}
          </label>

          {error && (
            <p
              role="alert"
              className="rounded-md border border-[var(--color-error)] px-3 py-2 text-sm text-[var(--color-error)]"
            >
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={busy}
            className="w-full rounded-md bg-[var(--color-primary)] px-3 py-2 text-sm font-medium text-white disabled:opacity-60"
          >
            {busy ? "Working…" : mode === "login" ? "Sign in" : "Create account"}
          </button>
        </form>

        {registrationOpen && (
          <button
            type="button"
            onClick={() => {
              setMode(mode === "login" ? "register" : "login");
              setError(null);
            }}
            className="mt-4 w-full text-xs text-[var(--color-muted)] underline-offset-2 hover:underline"
          >
            {mode === "login" ? "Create an account instead" : "Back to sign in"}
          </button>
        )}
      </div>
    </main>
  );
}
