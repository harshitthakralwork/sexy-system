"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

type Theme = "dark" | "light";

interface ThemeContextValue {
  theme: Theme;
  setTheme: (theme: Theme) => void;
  toggleTheme: () => void;
  hoverEffects: boolean;
  setHoverEffects: (enabled: boolean) => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);
// Version the preference because the redesigned control-panel theme changes
// the product default from dark to light. Users can still switch it back.
const STORAGE_KEY = "sparkx.theme.v2";
const HOVER_STORAGE_KEY = "sparkx.hover-effects.v1";

function readStoredTheme(): Theme {
  if (typeof window === "undefined") return "dark";
  const stored = window.localStorage.getItem(STORAGE_KEY);
  return stored === "light" ? "light" : "dark";
}

function readStoredHoverEffects(): boolean {
  if (typeof window === "undefined") return false;
  return window.localStorage.getItem(HOVER_STORAGE_KEY) !== "off";
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  // Read once during initialisation rather than in an effect: the effect path
  // would render the wrong theme for a frame and then re-render.
  const [theme, setThemeState] = useState<Theme>(readStoredTheme);
  const [hoverEffects, setHoverEffectsState] = useState(readStoredHoverEffects);

  // The effect writes to two systems outside React (document attribute and
  // storage), which is exactly what an effect is for.
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    if (theme === "dark") {
      document.documentElement.classList.add("dark");
      document.documentElement.classList.remove("light");
    } else {
      document.documentElement.classList.add("light");
      document.documentElement.classList.remove("dark");
    }
    window.localStorage.setItem(STORAGE_KEY, theme);
  }, [theme]);

  useEffect(() => {
    document.documentElement.classList.toggle("hover-effects-on", hoverEffects);
    document.documentElement.classList.toggle("hover-effects-off", !hoverEffects);
    window.localStorage.setItem(HOVER_STORAGE_KEY, hoverEffects ? "on" : "off");
  }, [hoverEffects]);

  const setTheme = useCallback((next: Theme) => setThemeState(next), []);
  const toggleTheme = useCallback(
    () => setThemeState((current) => (current === "dark" ? "light" : "dark")),
    [],
  );
  const setHoverEffects = useCallback((enabled: boolean) => setHoverEffectsState(enabled), []);

  const value = useMemo(() => ({ theme, setTheme, toggleTheme, hoverEffects, setHoverEffects }), [theme, setTheme, toggleTheme, hoverEffects, setHoverEffects]);

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const context = useContext(ThemeContext);
  if (!context) throw new Error("useTheme must be used inside ThemeProvider");
  return context;
}
