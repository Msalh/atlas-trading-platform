import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import "./globals.css";
import { QueryProvider } from "@/lib/query-provider";
import { LiveUpdatesProvider } from "@/lib/live-updates";
import { LiveSelectorProvider } from "@/lib/liveSelector";
import { HeaderStatusDot } from "@/components/HeaderStatusDot";
import { HeaderKillSwitchDot } from "@/components/HeaderKillSwitchDot";
import { AppNav } from "@/components/AppNav";

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
                <div className="mx-auto max-w-6xl px-6 pt-4">
                  <div className="flex items-center justify-between gap-4 pb-3">
                    <Link href="/" className="flex items-center gap-2">
                      <span className="text-lg font-semibold tracking-tight">Atlas</span>
                      <span className="rounded border border-border bg-surface-raised px-1.5 py-0.5 text-[11px] leading-none text-muted">
                        MNQU6 · ICT_Funded_v1
                      </span>
                    </Link>
                    <div className="flex items-center gap-4">
                      <HeaderKillSwitchDot />
                      <HeaderStatusDot />
                    </div>
                  </div>
                  <AppNav />
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
