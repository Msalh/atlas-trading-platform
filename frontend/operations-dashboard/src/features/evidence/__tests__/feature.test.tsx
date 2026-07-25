import { vi } from "vitest";
import { isEvidenceBrowserEnabled } from "../feature";

const notFound = vi.fn(() => {
  throw new Error("NEXT_NOT_FOUND");
});

vi.mock("next/navigation", () => ({ notFound }));

describe("Evidence page feature boundary", () => {
  afterEach(() => {
    delete process.env.EVIDENCE_BROWSER_ENABLED;
    vi.restoreAllMocks();
  });

  it("requires an exact true feature value", () => {
    expect(isEvidenceBrowserEnabled()).toBe(false);
    process.env.EVIDENCE_BROWSER_ENABLED = "TRUE";
    expect(isEvidenceBrowserEnabled()).toBe(false);
    process.env.EVIDENCE_BROWSER_ENABLED = "true";
    expect(isEvidenceBrowserEnabled()).toBe(true);
  });

  it("rejects direct page access without making a Snapshot request", async () => {
    process.env.EVIDENCE_BROWSER_ENABLED = "false";
    const fetchMock = vi.spyOn(globalThis, "fetch");
    const { default: EvidencePage } = await import("@/app/evidence/page");
    expect(() => EvidencePage()).toThrow("NEXT_NOT_FOUND");
    expect(notFound).toHaveBeenCalledOnce();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
