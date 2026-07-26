import { describe, expect, it, vi } from "vitest";
import { fetchTraderNow, isTraderNowResponse } from "@/lib/traderNowApi";
import { traderNowFixture } from "@/test/traderNowFixture";

describe("TraderNowResponse v2 contract", () => {
  it("accepts the exact frozen response", () => {
    expect(isTraderNowResponse(traderNowFixture())).toBe(true);
  });

  it.each([
    ["wrong schema", { schema_version: "trader_now_response.v3" }],
    ["missing section", { context: undefined }],
    ["unexpected field", { extra: "leak" }],
    ["invented decision", { decision: { availability: "available", state: "ENTER" } }],
  ])("rejects %s", (_label, changes) => {
    expect(isTraderNowResponse({ ...traderNowFixture(), ...changes })).toBe(false);
  });

  it("uses only the explicit same-origin BFF route and approved identity", async () => {
    const fetchMock = vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify(traderNowFixture()), { status: 200 }),
    );
    await fetchTraderNow();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/proxy/trader-now?symbol=MNQ&timeframe=5m&strategy_id=displacement_volume_context",
      { cache: "no-store" },
    );
  });
});
