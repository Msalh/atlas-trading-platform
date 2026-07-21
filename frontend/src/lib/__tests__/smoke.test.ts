import { describe, expect, it } from "vitest";

describe("vitest harness", () => {
  it("runs a basic assertion", () => {
    expect(1 + 1).toBe(2);
  });
});
