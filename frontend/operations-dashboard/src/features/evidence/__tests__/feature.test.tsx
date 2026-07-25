import { vi } from "vitest";
import { isEvidenceBrowserEnabled } from "../feature";

const notFound = vi.fn(() => {
  throw new Error("NEXT_NOT_FOUND");
});

vi.mock("next/navigation", () => ({ notFound }));

describe("Evidence page feature boundary", () => {
  beforeEach(() => {
    notFound.mockClear();
  });

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

  it("rejects direct detail access while disabled without making a request", async () => {
    process.env.EVIDENCE_BROWSER_ENABLED = "false";
    const fetchMock = vi.spyOn(globalThis, "fetch");
    const { default: SnapshotDetailPage } = await import(
      "@/app/evidence/[snapshotId]/page"
    );
    await expect(
      SnapshotDetailPage({
        params: Promise.resolve({
          snapshotId: "019b1111-2222-7333-8444-555555555555",
        }),
      }),
    ).rejects.toThrow("NEXT_NOT_FOUND");
    expect(notFound).toHaveBeenCalledOnce();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("rejects malformed detail identity before rendering the client", async () => {
    process.env.EVIDENCE_BROWSER_ENABLED = "true";
    const fetchMock = vi.spyOn(globalThis, "fetch");
    const { default: SnapshotDetailPage } = await import(
      "@/app/evidence/[snapshotId]/page"
    );
    await expect(
      SnapshotDetailPage({
        params: Promise.resolve({ snapshotId: "../capture" }),
      }),
    ).rejects.toThrow("NEXT_NOT_FOUND");
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
