"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useMemo, type ReactNode } from "react";

import { ApiError, api } from "@/lib/api/client";
import type { AuthUser, LoginPayload, SessionInfo } from "@/lib/api/types";

interface SessionValue {
  user: AuthUser | null;
  csrf: string | null;
  /** `checking` means the first response has not arrived; it is not "signed out". */
  state: "checking" | "signedIn" | "signedOut";
  error: string | null;
  login: (payload: LoginPayload) => Promise<{ ok: boolean; error: string | null }>;
  logout: () => Promise<void>;
}

const SessionContext = createContext<SessionValue | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const router = useRouter();

  // A 401 here is an expected answer, not a failure to retry: it is the reason
  // the app shows a login screen.
  const session = useQuery({
    queryKey: ["session"],
    queryFn: () => api.get<SessionInfo>("/auth/session"),
    retry: false,
    staleTime: 60_000,
  });

  const signedOut = session.isError && session.error instanceof ApiError && session.error.status === 401;

  const login = useMutation({
    mutationFn: (payload: LoginPayload) => api.post<SessionInfo>("/auth/login", payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["session"] }),
  });

  const submit = useCallback(
    async (payload: LoginPayload) => {
      try {
        await login.mutateAsync(payload);
        return { ok: true, error: null };
      } catch (cause) {
        // The backend returns the same message for an unknown email and a wrong
        // password. Surfacing it verbatim keeps the UI from becoming an
        // account-enumeration oracle.
        const message = cause instanceof ApiError ? cause.message : "Sign-in failed";
        return { ok: false, error: message };
      }
    },
    [login],
  );

  const logout = useCallback(async () => {
    const csrf = session.data?.csrf_token ?? null;
    try {
      await api.post("/auth/logout", undefined, csrf);
    } finally {
      queryClient.removeQueries({ queryKey: ["session"] });
      queryClient.clear();
      router.replace("/login");
    }
  }, [queryClient, router, session.data?.csrf_token]);

  const value = useMemo<SessionValue>(
    () => ({
      user: session.data?.user ?? null,
      csrf: session.data?.csrf_token ?? null,
      state: session.isPending ? "checking" : signedOut ? "signedOut" : "signedIn",
      error: login.isError ? "Sign-in failed" : null,
      login: submit,
      logout,
    }),
    [session.isPending, session.data, signedOut, login.isError, submit, logout],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionValue {
  const context = useContext(SessionContext);
  if (!context) throw new Error("useSession must be used inside SessionProvider");
  return context;
}
