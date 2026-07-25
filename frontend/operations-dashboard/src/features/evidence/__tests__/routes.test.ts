import * as detailRoute from "@/app/api/evidence/snapshots/[snapshotId]/route";
import * as integrityRoute from "@/app/api/evidence/snapshots/[snapshotId]/integrity/route";
import * as metadataRoute from "@/app/api/evidence/snapshots/[snapshotId]/metadata/route";
import * as listRoute from "@/app/api/evidence/snapshots/route";
import {
  SYNTHETIC_SNAPSHOT_ID,
  snapshotDetailFixture,
  snapshotIntegrityFixture,
  snapshotListFixture,
  snapshotMetadataFixture,
} from "../__fixtures__/snapshotApi";

function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

describe("purpose-specific Evidence BFF routes", () => {
  beforeEach(() => {
    process.env.EVIDENCE_BROWSER_ENABLED = "true";
    process.env.SNAPSHOT_API_INTERNAL_URL = "http://snapshot-api.internal";
    process.env.SNAPSHOT_READER_API_TOKEN = "synthetic-reader-token";
    vi.restoreAllMocks();
  });

  afterEach(() => {
    delete process.env.EVIDENCE_BROWSER_ENABLED;
    delete process.env.SNAPSHOT_API_INTERNAL_URL;
    delete process.env.SNAPSHOT_READER_API_TOKEN;
  });

  it("exports GET only for every route", () => {
    for (const route of [
      listRoute,
      detailRoute,
      metadataRoute,
      integrityRoute,
    ]) {
      expect(Object.keys(route).sort()).toEqual(["GET", "dynamic"]);
    }
  });

  it("forwards each route through its exact reader operation", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse(snapshotListFixture))
      .mockResolvedValueOnce(jsonResponse(snapshotDetailFixture))
      .mockResolvedValueOnce(jsonResponse(snapshotMetadataFixture))
      .mockResolvedValueOnce(jsonResponse(snapshotIntegrityFixture));
    const context = { params: Promise.resolve({ snapshotId: SYNTHETIC_SNAPSHOT_ID }) };

    expect(
      (
        await listRoute.GET(
          new Request("http://dashboard.local/api/evidence/snapshots"),
        )
      ).status,
    ).toBe(200);
    expect(
      (
        await detailRoute.GET(
          new Request("http://dashboard.local/detail"),
          context,
        )
      ).status,
    ).toBe(200);
    expect(
      (
        await metadataRoute.GET(
          new Request("http://dashboard.local/metadata"),
          context,
        )
      ).status,
    ).toBe(200);
    expect(
      (
        await integrityRoute.GET(
          new Request("http://dashboard.local/integrity"),
          context,
        )
      ).status,
    ).toBe(200);
    expect(fetchMock).toHaveBeenCalledTimes(4);
    expect(
      fetchMock.mock.calls.every(
        ([, init]) =>
          init?.method === "GET" &&
          String(new Headers(init.headers).get("authorization")).startsWith(
            "Bearer ",
          ),
      ),
    ).toBe(true);
  });
});
