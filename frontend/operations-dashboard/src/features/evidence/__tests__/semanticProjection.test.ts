import {
  SYNTHETIC_SNAPSHOT_ID,
  snapshotDetailFixture,
} from "../__fixtures__/snapshotApi";
import {
  SEMANTIC_LIMITS,
  SemanticProjectionError,
  projectSemanticSnapshot,
  safeSemanticText,
  semanticJsonIsValid,
} from "../semanticProjection";

function fixture(): Record<string, unknown> {
  return structuredClone(snapshotDetailFixture) as unknown as Record<
    string,
    unknown
  >;
}

function object(value: unknown): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error("test fixture path is not an object");
  }
  return value as Record<string, unknown>;
}

function snapshot(value: Record<string, unknown>) {
  return object(value.snapshot);
}

function evidence(value: Record<string, unknown>) {
  return object(snapshot(value).evidence);
}

function expectProjectionError(
  value: unknown,
  code: SemanticProjectionError["code"],
  expectedSnapshotId = SYNTHETIC_SNAPSHOT_ID,
) {
  try {
    projectSemanticSnapshot(value, expectedSnapshotId);
    throw new Error("projection unexpectedly succeeded");
  } catch (error) {
    expect(error).toBeInstanceOf(SemanticProjectionError);
    expect((error as SemanticProjectionError).code).toBe(code);
  }
}

describe("semantic evidence projection", () => {
  it("projects the frozen allowlist and emits deterministic valid semantic JSON", () => {
    const first = projectSemanticSnapshot(
      snapshotDetailFixture,
      SYNTHETIC_SNAPSHOT_ID,
    );
    const second = projectSemanticSnapshot(
      snapshotDetailFixture,
      SYNTHETIC_SNAPSHOT_ID,
    );

    expect(first).toEqual(second);
    expect(first.evidence.identity.product).toBe("MNQ");
    expect(first.evidence.rules.facts[0]?.id).toBe("synthetic_fact");
    expect(semanticJsonIsValid(first.formattedJson)).toEqual(
      snapshotDetailFixture.snapshot,
    );
    expect(first.formattedJson).not.toContain('"schema_version": "snapshot_api.v1"');
    expect(first.formattedJson).not.toContain('"market_data_provider"');
  });

  it("fails closed for unsupported schemas, identity mismatch, and unknown fields", () => {
    const unsupported = fixture();
    snapshot(unsupported).snapshot_schema_version = "future.v2";
    expectProjectionError(unsupported, "unsupported_snapshot_schema");

    expectProjectionError(
      snapshotDetailFixture,
      "invalid_semantic_response",
      "019b1111-2222-7333-8444-777777777777",
    );

    const unknown = fixture();
    snapshot(unknown).unapproved = "field";
    expectProjectionError(unknown, "invalid_semantic_response");

    const hybrid = fixture();
    hybrid.ok = false;
    hybrid.code = "snapshot_integrity_failed";
    expectProjectionError(hybrid, "invalid_semantic_response");
  });

  it("preserves null and unavailable states explicitly", () => {
    const value = fixture();
    object(evidence(value).context).data = null;
    evidence(value).source_trust = null;
    evidence(value).risk = null;
    object(evidence(value).availability).context = {
      status: "unavailable",
      reason_codes: ["no_context"],
    };

    const projection = projectSemanticSnapshot(value, SYNTHETIC_SNAPSHOT_ID);
    expect(projection.evidence.context.quality).toBeNull();
    expect(projection.evidence.sourceTrust).toBeNull();
    expect(projection.evidence.risk).toBeNull();
    expect(projection.evidence.availability).toContainEqual({
      name: "Context",
      status: "unavailable",
      reasonCodes: ["no_context"],
    });
  });

  it.each([
    ["overlong string", () => "x".repeat(SEMANTIC_LIMITS.maximumStringLength + 1)],
    ["oversized array", () => Array(SEMANTIC_LIMITS.maximumArrayItems + 1).fill(null)],
  ])("rejects %s content", (_name, content) => {
    const value = fixture();
    object(evidence(value).context).data = { quality: "ok", content: content() };
    expectProjectionError(value, "semantic_content_limit_exceeded");
  });

  it("rejects excessive depth, node count, formatted size, cycles, and invalid scalars", () => {
    const deep = fixture();
    let node: Record<string, unknown> = {};
    object(evidence(deep).context).data = node;
    for (let index = 0; index < SEMANTIC_LIMITS.maximumDepth + 2; index += 1) {
      node.next = {};
      node = node.next as Record<string, unknown>;
    }
    expectProjectionError(deep, "semantic_content_limit_exceeded");

    const manyNodes = fixture();
    object(evidence(manyNodes).context).data = Object.fromEntries(
      Array.from({ length: 2_600 }, (_, index) => [`k${index}`, index]),
    );
    expectProjectionError(manyNodes, "semantic_content_limit_exceeded");

    const hugeFormatted = fixture();
    object(evidence(hugeFormatted).context).data = {
      quality: "ok",
      blocks: Array(500).fill("x".repeat(1_100)),
    };
    expectProjectionError(hugeFormatted, "semantic_content_limit_exceeded");

    const cyclic = fixture();
    object(evidence(cyclic).context).data = cyclic;
    expectProjectionError(cyclic, "invalid_semantic_response");

    const scalar = fixture();
    evidence(scalar).identity = "not-an-object";
    expectProjectionError(scalar, "invalid_semantic_response");
  });

  it("makes bidirectional controls visible while preserving valid JSON semantics", () => {
    const value = fixture();
    object(evidence(value).trust).reason_codes = ["safe\u202Etxt"];
    const projection = projectSemanticSnapshot(value, SYNTHETIC_SNAPSHOT_ID);

    expect(safeSemanticText("safe\u202Etxt")).toBe("safe<U+202E>txt");
    expect(projection.formattedJson).toContain("safe\\u202etxt");
    const parsed = object(semanticJsonIsValid(projection.formattedJson));
    const parsedEvidence = object(parsed.evidence);
    const parsedTrust = object(parsedEvidence.trust);
    expect(parsedTrust.reason_codes).toEqual(["safe\u202Etxt"]);
  });

  it("preserves escaped characters and special Unicode as plain JSON data", () => {
    const value = fixture();
    const rules = object(evidence(value).rules);
    const facts = rules.facts as Array<Record<string, unknown>>;
    facts[0].value = 'quote"\nemoji😀\\slash';

    const projection = projectSemanticSnapshot(value, SYNTHETIC_SNAPSHOT_ID);
    const parsed = object(semanticJsonIsValid(projection.formattedJson));
    const parsedRules = object(object(parsed.evidence).rules);
    const parsedFacts = parsedRules.facts as Array<Record<string, unknown>>;
    expect(parsedFacts[0].value).toBe('quote"\nemoji😀\\slash');
  });
});
