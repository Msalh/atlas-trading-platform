import { describe, expect, it } from "vitest";
import { liveEpisodesQueryKey } from "@/lib/useLiveEpisodes";

describe("liveEpisodesQueryKey", () => {
  it("produces the identical key for the same (symbol, timeframe, window) regardless of caller", () => {
    // The F4t requirement: whichever component calls useLiveEpisodes, the
    // key must match byte-for-byte so react-query treats them as the same
    // query - simulated here by calling the pure key builder twice, as if
    // from two different components.
    const fromActiveSetupBundle = liveEpisodesQueryKey("MNQU6", "5m", 500);
    const fromTimeline = liveEpisodesQueryKey("MNQU6", "5m", 500);
    expect(fromActiveSetupBundle).toEqual(fromTimeline);
  });

  it("differs when symbol, timeframe, or window differs", () => {
    const base = liveEpisodesQueryKey("MNQU6", "5m", 500);
    expect(liveEpisodesQueryKey("ESU6", "5m", 500)).not.toEqual(base);
    expect(liveEpisodesQueryKey("MNQU6", "1m", 500)).not.toEqual(base);
    expect(liveEpisodesQueryKey("MNQU6", "5m", 250)).not.toEqual(base);
  });
});
