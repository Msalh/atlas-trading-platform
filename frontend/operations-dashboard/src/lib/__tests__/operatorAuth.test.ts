import { hasValidOperatorAuthorization } from "@/lib/operatorAuth";

describe("operator authentication", () => {
  beforeEach(() => {
    process.env.OPERATOR_USERNAME = "operator";
    process.env.OPERATOR_PASSWORD = "correct-horse";
  });

  it("requires the configured credentials", () => {
    expect(hasValidOperatorAuthorization(null)).toBe(false);
    expect(hasValidOperatorAuthorization("Basic !!!")).toBe(false);
    expect(hasValidOperatorAuthorization(`Basic ${Buffer.from("operator:wrong").toString("base64")}`)).toBe(false);
    expect(hasValidOperatorAuthorization(`Basic ${Buffer.from("operator:correct-horse").toString("base64")}`)).toBe(true);
  });

  it("fails closed when configuration is absent", () => {
    delete process.env.OPERATOR_PASSWORD;
    expect(hasValidOperatorAuthorization(`Basic ${Buffer.from("operator:correct-horse").toString("base64")}`)).toBe(false);
  });
});
