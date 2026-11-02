import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";

import "./globals.css";

import { QueryProvider } from "@/components/providers/query-provider";
import { SessionProvider } from "@/components/providers/session-provider";
import { ThemeProvider } from "@/components/providers/theme-provider";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "SparkXFlow Nexus",
  description: "Business and market intelligence platform",
};

export const viewport: Viewport = {
  themeColor: "#09090f",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" data-theme="dark" suppressHydrationWarning>
      <body className={`${geistSans.variable} ${geistMono.variable}`}>
        {/* Theme is applied by the provider on mount; the html attribute above is
            the dark default so the first paint does not flash light. */}
        <ThemeProvider>
          <QueryProvider>
            <SessionProvider>{children}</SessionProvider>
          </QueryProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
