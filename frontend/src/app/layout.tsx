import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import "./globals.css";
import { QueryProvider } from "@/lib/query-provider";
import { LiveUpdatesProvider } from "@/lib/live-updates";
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
            <header className="border-b border-border bg-surface">
              <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
                <div className="flex items-baseline gap-6">
                  <Link href="/" className="flex items-baseline gap-2">
                    <span className="text-lg font-semibold tracking-tight">Atlas</span>
                    <span className="text-sm text-muted">MNQU6 · ICT_Funded_v1</span>
                  </Link>
                  <nav className="flex items-baseline gap-4 text-sm text-muted">
                    <Link href="/" className="hover:text-foreground">Dashboard</Link>
                    <Link href="/account" className="hover:text-foreground">Account</Link>
                    <Link href="/analytics" className="hover:text-foreground">Analytics</Link>
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
              Atlas AI Trading Platform — Sprint 5
            </footer>
          </LiveUpdatesProvider>
        </QueryProvider>
      </body>
    </html>
  );
}
