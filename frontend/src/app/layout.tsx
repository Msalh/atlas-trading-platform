import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import "./globals.css";
import { QueryProvider } from "@/lib/query-provider";
import { LiveUpdatesProvider } from "@/lib/live-updates";
import { LiveSelectorProvider } from "@/lib/liveSelector";
import { HeaderStatusDot } from "@/components/HeaderStatusDot";
import { HeaderKillSwitchDot } from "@/components/HeaderKillSwitchDot";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Atlas — MNQU6 ICT_Funded_v1",
  description: "Live trade lifecycle for the Atlas AI trading platform.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col bg-background text-foreground">
        <QueryProvider>
          <LiveUpdatesProvider>
            <LiveSelectorProvider>
              <header className="border-b border-border bg-surface">
                <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
                  <div className="flex items-baseline gap-6">
                    <Link href="/" className="flex items-baseline gap-2">
                      <span className="text-lg font-semibold tracking-tight">Atlas</span>
                      <span className="text-sm text-muted">MNQU6 · ICT_Funded_v1</span>
                    </Link>
                    <nav className="flex flex-wrap items-baseline gap-4 text-sm text-muted">
                      <Link href="/" className="hover:text-foreground">Dashboard</Link>
                      <Link href="/account" className="hover:text-foreground">Account</Link>
                      <Link href="/analytics" className="hover:text-foreground">Analytics</Link>
                      <Link href="/ai" className="hover:text-foreground">AI</Link>
                      <Link href="/activity" className="hover:text-foreground">Activity</Link>
                      <Link href="/rule-engine" className="hover:text-foreground">Rule Engine</Link>
                      <span className="text-border">|</span>
                      <Link href="/market-view" className="hover:text-foreground">Market View</Link>
                      <Link href="/active-setups" className="hover:text-foreground">Active Setups</Link>
                      <Link href="/timeline" className="hover:text-foreground">Timeline</Link>
                      <Link href="/episodes" className="hover:text-foreground">Episode Inspector</Link>
                      <Link href="/research" className="hover:text-foreground">Statistical Baseline</Link>
                      <Link href="/dataset-health" className="hover:text-foreground">Dataset Health</Link>
                      <span className="text-border">|</span>
                      <Link href="/research-ops" className="hover:text-foreground">Research Overview</Link>
                      <Link href="/research-ops/leaderboard" className="hover:text-foreground">Leaderboard</Link>
                      <Link href="/research-ops/snapshot" className="hover:text-foreground">Snapshot Explorer</Link>
                      <Link href="/research-ops/promotion/queue" className="hover:text-foreground">Promotion Queue</Link>
                      <Link href="/research-ops/promotion/history" className="hover:text-foreground">Promotion History</Link>
                      <Link href="/research-ops/run-center" className="hover:text-foreground">Run Center</Link>
                    </nav>
                  </div>
                  <div className="flex items-center gap-4">
                    <HeaderKillSwitchDot />
                    <HeaderStatusDot />
                  </div>
                </div>
              </header>
              <main className="mx-auto w-full max-w-6xl flex-1 px-6 py-8">{children}</main>
              <footer className="border-t border-border px-6 py-4 text-center text-xs text-muted">
                Atlas AI Trading Platform — Sprint 7
              </footer>
            </LiveSelectorProvider>
          </LiveUpdatesProvider>
        </QueryProvider>
      </body>
    </html>
  );
}
