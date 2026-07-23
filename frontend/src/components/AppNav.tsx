"use client";

// UX Sprint - Navigation Simplification. Replaces layout.tsx's own
// previously-inline, 18-link flat nav row. Frontend-only: every route
// below is unchanged from before this sprint - this component only
// changes where/how each one is reached, never what it does.
//
// Trading and Research are direct links (not dropdown triggers) per the
// approved design - clicking either navigates immediately (to
// /market-view and /research-ops respectively), and reveals a persistent
// secondary nav row for that section for as long as the current page
// belongs to it. Only "More" is an actual dropdown, for the four
// secondary/developer-tool pages that don't need permanent top-level
// space: Episode Inspector, Statistical Baseline, Dataset Health,
// Activity.
//
// Split into two components: AppNav (outer, reads the route, computes
// which section is active) and AppNavMenus (inner, owns the More/mobile
// open/closed state, `key={pathname}`-ed by its parent). Keying the
// stateful child by pathname is React's own documented, compiler-safe way
// to "reset state when a derived value changes" - it remounts fresh (menus
// closed) on every navigation via ordinary unmount/mount, never a
// setState-in-effect or a ref read during render (both flagged by this
// project's stricter react-hooks lint rules, tuned for React Compiler
// compatibility).

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";

interface NavLink {
  href: string;
  label: string;
}

const TRADING_SECTION_LINKS: NavLink[] = [
  { href: "/market-view", label: "Market View" },
  { href: "/rule-engine", label: "Rule Engine" },
  { href: "/active-setups", label: "Active Setups" },
  { href: "/timeline", label: "Timeline" },
];

const RESEARCH_SECTION_LINKS: NavLink[] = [
  { href: "/research-ops", label: "Overview" },
  { href: "/research-ops/leaderboard", label: "Leaderboard" },
  { href: "/research-ops/snapshot", label: "Snapshot Explorer" },
  { href: "/research-ops/promotion/queue", label: "Promotion Queue" },
  { href: "/research-ops/promotion/history", label: "Promotion History" },
  { href: "/research-ops/run-center", label: "Run Center" },
];

const MORE_LINKS: NavLink[] = [
  { href: "/episodes", label: "Episode Inspector" },
  { href: "/research", label: "Statistical Baseline" },
  { href: "/dataset-health", label: "Dataset Health" },
  { href: "/activity", label: "Activity" },
];

const TRADING_PATHS = TRADING_SECTION_LINKS.map((l) => l.href);
const MORE_PATHS = MORE_LINKS.map((l) => l.href);

function isExact(pathname: string, href: string): boolean {
  return pathname === href;
}

function linkClass(active: boolean): string {
  return `hover:text-foreground ${active ? "text-foreground font-medium" : "text-muted"}`;
}

function NavLinkItem({ href, label, active }: { href: string; label: string; active: boolean }) {
  return (
    <Link href={href} className={linkClass(active)} aria-current={active ? "page" : undefined}>
      {label}
    </Link>
  );
}

export function AppNav() {
  const pathname = usePathname();
  const isTrading = TRADING_PATHS.includes(pathname);
  const isResearch = pathname.startsWith("/research-ops");
  const isMore = MORE_PATHS.includes(pathname);

  return (
    <div className="pb-4">
      <AppNavMenus key={pathname} pathname={pathname} isTrading={isTrading} isResearch={isResearch} isMore={isMore} />

      {isTrading && (
        <nav className="mt-3 flex flex-wrap items-baseline gap-4 border-t border-border pt-3 text-xs" aria-label="Trading">
          {TRADING_SECTION_LINKS.map((link) => (
            <NavLinkItem key={link.href} href={link.href} label={link.label} active={isExact(pathname, link.href)} />
          ))}
        </nav>
      )}
      {isResearch && (
        <nav className="mt-3 flex flex-wrap items-baseline gap-4 border-t border-border pt-3 text-xs" aria-label="Research">
          {RESEARCH_SECTION_LINKS.map((link) => (
            <NavLinkItem key={link.href} href={link.href} label={link.label} active={isExact(pathname, link.href)} />
          ))}
        </nav>
      )}
    </div>
  );
}

function AppNavMenus({
  pathname,
  isTrading,
  isResearch,
  isMore,
}: {
  pathname: string;
  isTrading: boolean;
  isResearch: boolean;
  isMore: boolean;
}) {
  const [moreOpen, setMoreOpen] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const moreContainerRef = useRef<HTMLDivElement>(null);
  const moreButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!moreOpen) return;
    function handlePointerDown(event: MouseEvent) {
      if (moreContainerRef.current && !moreContainerRef.current.contains(event.target as Node)) {
        setMoreOpen(false);
      }
    }
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setMoreOpen(false);
        moreButtonRef.current?.focus();
      }
    }
    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [moreOpen]);

  return (
    <>
      <div className="flex items-center justify-between gap-4">
        <nav className="hidden md:flex items-baseline gap-5 text-sm" aria-label="Primary">
          <NavLinkItem href="/" label="Dashboard" active={isExact(pathname, "/")} />
          <NavLinkItem href="/market-view" label="Trading" active={isTrading} />
          <NavLinkItem href="/research-ops" label="Research" active={isResearch} />
          <NavLinkItem href="/analytics" label="Analytics" active={isExact(pathname, "/analytics")} />
          <NavLinkItem href="/ai" label="AI" active={isExact(pathname, "/ai")} />
          <NavLinkItem href="/account" label="Account" active={isExact(pathname, "/account")} />
          <div className="relative" ref={moreContainerRef}>
            <button
              ref={moreButtonRef}
              type="button"
              aria-haspopup="menu"
              aria-expanded={moreOpen}
              onClick={() => setMoreOpen((open) => !open)}
              className={`flex items-center gap-1 ${linkClass(isMore)}`}
            >
              More <span aria-hidden="true">▾</span>
            </button>
            {moreOpen && (
              <div
                role="menu"
                aria-label="More"
                className="absolute right-0 z-10 mt-2 w-48 rounded-lg border border-border bg-surface-raised py-1 shadow-lg"
              >
                {MORE_LINKS.map((link) => (
                  <Link
                    key={link.href}
                    href={link.href}
                    role="menuitem"
                    aria-current={isExact(pathname, link.href) ? "page" : undefined}
                    className={`block px-3 py-2 text-sm hover:bg-surface hover:text-foreground ${
                      isExact(pathname, link.href) ? "text-foreground" : "text-muted"
                    }`}
                    onClick={() => setMoreOpen(false)}
                  >
                    {link.label}
                  </Link>
                ))}
              </div>
            )}
          </div>
        </nav>

        <button
          type="button"
          aria-haspopup="menu"
          aria-expanded={mobileOpen}
          onClick={() => setMobileOpen((open) => !open)}
          className="md:hidden text-sm text-muted hover:text-foreground"
        >
          {mobileOpen ? "Close ✕" : "Menu ☰"}
        </button>
      </div>

      {mobileOpen && (
        <nav className="md:hidden mt-3 flex flex-col gap-3 border-t border-border pt-3 text-sm" aria-label="Primary (mobile)">
          <NavLinkItem href="/" label="Dashboard" active={isExact(pathname, "/")} />
          <div>
            <NavLinkItem href="/market-view" label="Trading" active={isTrading} />
            <div className="ml-4 mt-1 flex flex-col gap-1">
              {TRADING_SECTION_LINKS.map((link) => (
                <NavLinkItem key={link.href} href={link.href} label={link.label} active={isExact(pathname, link.href)} />
              ))}
            </div>
          </div>
          <div>
            <NavLinkItem href="/research-ops" label="Research" active={isResearch} />
            <div className="ml-4 mt-1 flex flex-col gap-1">
              {RESEARCH_SECTION_LINKS.map((link) => (
                <NavLinkItem key={link.href} href={link.href} label={link.label} active={isExact(pathname, link.href)} />
              ))}
            </div>
          </div>
          <NavLinkItem href="/analytics" label="Analytics" active={isExact(pathname, "/analytics")} />
          <NavLinkItem href="/ai" label="AI" active={isExact(pathname, "/ai")} />
          <NavLinkItem href="/account" label="Account" active={isExact(pathname, "/account")} />
          <div>
            <span className="text-muted">More</span>
            <div className="ml-4 mt-1 flex flex-col gap-1">
              {MORE_LINKS.map((link) => (
                <NavLinkItem key={link.href} href={link.href} label={link.label} active={isExact(pathname, link.href)} />
              ))}
            </div>
          </div>
        </nav>
      )}
    </>
  );
}
