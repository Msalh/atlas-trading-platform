import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AppNav } from "@/components/AppNav";

const mockUsePathname = vi.fn();
vi.mock("next/navigation", () => ({
  usePathname: () => mockUsePathname(),
}));

function setPathname(pathname: string) {
  mockUsePathname.mockReturnValue(pathname);
}

describe("AppNav", () => {
  beforeEach(() => {
    setPathname("/");
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders all 6 primary destinations plus the More trigger, every one of the 18 routes reachable", () => {
    render(<AppNav />);
    // Primary row (desktop nav, always in the DOM even if visually hidden on mobile widths)
    expect(screen.getByRole("navigation", { name: "Primary" })).toBeInTheDocument();
    for (const [label, href] of [
      ["Dashboard", "/"],
      ["Trading", "/market-view"],
      ["Research", "/research-ops"],
      ["Analytics", "/analytics"],
      ["AI", "/ai"],
      ["Account", "/account"],
    ] as const) {
      const link = screen.getAllByRole("link", { name: label })[0];
      expect(link).toHaveAttribute("href", href);
    }
    expect(screen.getByRole("button", { name: /More/ })).toBeInTheDocument();
  });

  it("opens the More menu on click, exposing all 4 secondary/developer-tool links, and closes on Escape returning focus to the trigger", () => {
    render(<AppNav />);
    const trigger = screen.getByRole("button", { name: /More/ });
    expect(trigger).toHaveAttribute("aria-expanded", "false");

    fireEvent.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    const menu = screen.getByRole("menu", { name: "More" });
    for (const [label, href] of [
      ["Episode Inspector", "/episodes"],
      ["Statistical Baseline", "/research"],
      ["Dataset Health", "/dataset-health"],
      ["Activity", "/activity"],
    ] as const) {
      const link = screen.getByRole("menuitem", { name: label });
      expect(link).toHaveAttribute("href", href);
    }
    expect(menu).toBeInTheDocument();

    fireEvent.keyDown(document, { key: "Escape" });
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    expect(trigger).toHaveFocus();
  });

  it("closes the More menu on an outside click", () => {
    render(<AppNav />);
    const trigger = screen.getByRole("button", { name: /More/ });
    fireEvent.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "true");

    fireEvent.mouseDown(document.body);
    expect(trigger).toHaveAttribute("aria-expanded", "false");
  });

  it("shows the Trading secondary nav (4 links) only when the current page belongs to the Trading section", () => {
    setPathname("/rule-engine");
    render(<AppNav />);
    expect(screen.getByRole("navigation", { name: "Trading" })).toBeInTheDocument();
    for (const [label, href] of [
      ["Market View", "/market-view"],
      ["Rule Engine", "/rule-engine"],
      ["Active Setups", "/active-setups"],
      ["Timeline", "/timeline"],
    ] as const) {
      expect(screen.getByRole("navigation", { name: "Trading" }).querySelector(`a[href="${href}"]`)).toHaveTextContent(label);
    }
    expect(screen.queryByRole("navigation", { name: "Research" })).not.toBeInTheDocument();
  });

  it("shows the Research secondary nav (6 links, labeled Overview not Research Overview) only when the current page belongs to the Research section", () => {
    setPathname("/research-ops/leaderboard");
    render(<AppNav />);
    const researchNav = screen.getByRole("navigation", { name: "Research" });
    expect(researchNav).toBeInTheDocument();
    for (const [label, href] of [
      ["Overview", "/research-ops"],
      ["Leaderboard", "/research-ops/leaderboard"],
      ["Snapshot Explorer", "/research-ops/snapshot"],
      ["Promotion Queue", "/research-ops/promotion/queue"],
      ["Promotion History", "/research-ops/promotion/history"],
      ["Run Center", "/research-ops/run-center"],
    ] as const) {
      expect(researchNav.querySelector(`a[href="${href}"]`)).toHaveTextContent(label);
    }
    expect(screen.queryByRole("navigation", { name: "Trading" })).not.toBeInTheDocument();
  });

  it("shows neither secondary nav on a page outside both sections", () => {
    setPathname("/account");
    render(<AppNav />);
    expect(screen.queryByRole("navigation", { name: "Trading" })).not.toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Research" })).not.toBeInTheDocument();
  });

  it("marks Research as the active primary link and the exact leaf as aria-current on a nested Research page", () => {
    setPathname("/research-ops/snapshot");
    render(<AppNav />);
    const researchPrimaryLink = screen.getAllByRole("link", { name: "Research" })[0];
    expect(researchPrimaryLink).toHaveAttribute("aria-current", "page");
    const snapshotSecondaryLink = screen.getByRole("navigation", { name: "Research" }).querySelector('a[href="/research-ops/snapshot"]');
    expect(snapshotSecondaryLink).toHaveAttribute("aria-current", "page");
    const overviewSecondaryLink = screen.getByRole("navigation", { name: "Research" }).querySelector('a[href="/research-ops"]');
    expect(overviewSecondaryLink).not.toHaveAttribute("aria-current");
  });

  it("toggles the mobile menu, exposing the same 18 destinations in one flat grouped list", () => {
    render(<AppNav />);
    const mobileTrigger = screen.getByRole("button", { name: "Menu ☰" });
    fireEvent.click(mobileTrigger);
    expect(screen.getByRole("navigation", { name: "Primary (mobile)" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Close ✕" })).toBeInTheDocument();
  });
});
