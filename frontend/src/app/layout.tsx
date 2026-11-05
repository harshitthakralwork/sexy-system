import type { Metadata, Viewport } from "next";

import "./globals.css";

import { QueryProvider } from "@/components/providers/query-provider";
import { SessionProvider } from "@/components/providers/session-provider";
import { ThemeProvider } from "@/components/providers/theme-provider";

export const metadata: Metadata = {
  title: "SparkXFlow Nexus",
  description: "Find businesses and public demand signals",
  icons: {
    icon: [
      { url: "/favicon.ico", sizes: "any" },
      { url: "/icon.png", type: "image/png" },
    ],
    apple: [
      { url: "/apple-icon.png", type: "image/png" },
    ],
  },
};

export const viewport: Viewport = {
  themeColor: "#d8d2c8",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" data-theme="dark" suppressHydrationWarning>
      <body
        suppressHydrationWarning
        className="font-sans bg-[var(--color-background)] text-[var(--color-foreground)] antialiased selection:bg-[#FF7849]/30 selection:text-white"
      >
        {/* The light control-panel theme is the default; the provider restores
            an explicit dark preference after mount. */}
        <ThemeProvider>
          <QueryProvider>
            <SessionProvider>{children}</SessionProvider>
          </QueryProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
