"use client";

import Image from "next/image";
import { Eye, EyeOff, LockKeyhole, UserRound } from "lucide-react";
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
    api.get<{ allow_registration: boolean }>("/auth/status")
      .then((res) => { if (active) setRegistrationOpen(Boolean(res.allow_registration)); })
      .catch(() => { if (active) setRegistrationOpen(false); });
    return () => { active = false; };
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      if (mode === "login") {
        const result = await login({ email, password });
        if (!result.ok) setError(result.error);
        else {
          if (rememberMe) window.localStorage.setItem("sparkx_login_id", email);
          else window.localStorage.removeItem("sparkx_login_id");
          router.replace("/dashboard");
        }
      } else {
        await api.post("/auth/register", { email, password, display_name: email.split("@")[0] || "Operator" });
        const result = await login({ email, password });
        if (!result.ok) setError(result.error);
        else {
          if (rememberMe) window.localStorage.setItem("sparkx_login_id", email);
          router.replace("/dashboard");
        }
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Authentication failed. Check the account details and try again.");
    } finally {
      setBusy(false);
    }
  }

  const isLogin = mode === "login";
  return (
    <main className="auth-page">
      <Image alt="" aria-hidden className="auth-page__image" fill priority sizes="100vw" src="/chromatic-refraction-bg.jpg" />
      <div className="auth-page__veil" />
      <div aria-hidden className="auth-page__aurora">
        <span className="auth-page__orb auth-page__orb--one" />
        <span className="auth-page__orb auth-page__orb--two" />
        <span className="auth-page__orb auth-page__orb--three" />
      </div>
      <section aria-labelledby="auth-title" className="auth-panel">
        <div className="auth-brand">
          <div className="auth-brand__logo"><Image alt="SparkXFlow Nexus" fill priority sizes="36px" src="/logo.png" /></div>
          <div>
            <p className="auth-brand__name">SparkXFlow Nexus</p>
            <p className="auth-brand__label">Prospecting workspace</p>
          </div>
          <span className="auth-brand__state"><span aria-hidden /> Secure access</span>
        </div>

        <header className="auth-heading">
          <p className="auth-heading__eyebrow">Workspace access</p>
          <h1 id="auth-title">{isLogin ? "Welcome back" : "Create your account"}</h1>
          <p>{isLogin ? "Sign in to review your public prospect research." : "Set up an account for this private workspace."}</p>
        </header>

        <form className="auth-form" onSubmit={submit}>
          <label className="auth-field">
            <span>Email or local ID</span>
            <span className="auth-field__control">
              <UserRound aria-hidden size={18} />
              <input autoComplete="username" onChange={(event) => setEmail(event.target.value)} placeholder="Enter your email or ID" required type="text" value={email} />
            </span>
          </label>
          <label className="auth-field">
            <span>Password</span>
            <span className="auth-field__control">
              <LockKeyhole aria-hidden size={18} />
              <input autoComplete={isLogin ? "current-password" : "new-password"} minLength={isLogin ? 1 : 12} onChange={(event) => setPassword(event.target.value)} placeholder="Enter your password" required type={showPassword ? "text" : "password"} value={password} />
              <button aria-label={showPassword ? "Hide password" : "Show password"} className="auth-field__reveal" onClick={() => setShowPassword((current) => !current)} type="button">
                {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </span>
          </label>

          <div className="auth-options">
            <label><input checked={rememberMe} onChange={(event) => setRememberMe(event.target.checked)} type="checkbox" /> Remember this ID</label>
            <span>Private workspace</span>
          </div>

          {error && <p className="auth-error" role="alert">{error}</p>}

          <button className="auth-submit" disabled={busy} type="submit">
            {busy ? (isLogin ? "Signing in…" : "Creating account…") : (isLogin ? "Sign in" : "Create account")}
          </button>

          <p className="auth-switch">
            {isLogin ? "Need an account?" : "Already have an account?"}{" "}
            {isLogin && registrationOpen ? (
              <button onClick={() => { setError(null); setMode("register"); }} type="button">Create one</button>
            ) : !isLogin ? (
              <button onClick={() => { setError(null); setMode("login"); }} type="button">Sign in</button>
            ) : (
              <span>Ask the workspace owner.</span>
            )}
          </p>
        </form>

        <footer className="auth-footer">Developed by Harshit</footer>
      </section>
    </main>
  );
}
