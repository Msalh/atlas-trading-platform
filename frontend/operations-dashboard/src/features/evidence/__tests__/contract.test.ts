import {
  SNAPSHOT_API_SCHEMA_VERSION,
  SNAPSHOT_CORRELATION_HEADER,
  SNAPSHOT_DEFAULT_PAGE_SIZE,
  SNAPSHOT_MAX_CURSOR_LENGTH,
  SNAPSHOT_PAGE_SIZES,
  SNAPSHOT_READER_ROUTES,
} from "../contract";
import {
  SYNTHETIC_CORRELATION_ID,
  SYNTHETIC_DIGEST,
  SYNTHETIC_OPAQUE_CURSOR,
  SYNTHETIC_SNAPSHOT_ID,
  emptySnapshotListFixture,
  snapshotDetailFixture,
  snapshotErrorFixtures,
  snapshotIntegrityFixture,
  snapshotListFixture,
  snapshotMetadataFixture,
} from "../__fixtures__/snapshotApi";

const UUID_V7 =
  /^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const SHA256_HEX = /^[0-9a-f]{64}$/;

describe("frozen Phase 17E reader contract", () => {
  it("allowlists only the four approved reader routes", () => {
    expect(Object.keys(SNAPSHOT_READER_ROUTES)).toEqual([
      "list",
      "detail",
      "metadata",
      "integrity",
    ]);
    expect(SNAPSHOT_READER_ROUTES.list).toBe("/api/v1/snapshots");
    expect(SNAPSHOT_READER_ROUTES.detail(SYNTHETIC_SNAPSHOT_ID)).toBe(
      `/api/v1/snapshots/${SYNTHETIC_SNAPSHOT_ID}`,
    );
    expect(SNAPSHOT_READER_ROUTES.metadata(SYNTHETIC_SNAPSHOT_ID)).toBe(
      `/api/v1/snapshots/${SYNTHETIC_SNAPSHOT_ID}/metadata`,
    );
    expect(SNAPSHOT_READER_ROUTES.integrity(SYNTHETIC_SNAPSHOT_ID)).toBe(
      `/api/v1/snapshots/${SYNTHETIC_SNAPSHOT_ID}/integrity`,
    );
    expect(JSON.stringify(SNAPSHOT_READER_ROUTES)).not.toContain("capture");
  });

  it("freezes list bounds, opaque cursor handling, and correlation header", () => {
    expect(SNAPSHOT_PAGE_SIZES).toEqual([25, 50, 100]);
    expect(SNAPSHOT_DEFAULT_PAGE_SIZE).toBe(50);
    expect(SNAPSHOT_MAX_CURSOR_LENGTH).toBe(1024);
    expect(SNAPSHOT_CORRELATION_HEADER).toBe("X-Correlation-ID");
    expect(SYNTHETIC_OPAQUE_CURSOR).toBe(
      "fixture-opaque-cursor.do-not-decode",
    );
  });

  it("uses only synthetic, schema-versioned metadata", () => {
    expect(snapshotMetadataFixture.schema_version).toBe(
      SNAPSHOT_API_SCHEMA_VERSION,
    );
    expect(snapshotMetadataFixture.snapshot_id).toMatch(UUID_V7);
    expect(snapshotMetadataFixture.evidence_digest).toMatch(SHA256_HEX);
    expect(snapshotMetadataFixture.market_data_provider).toBe(
      "synthetic-provider",
    );
    expect(JSON.stringify(snapshotMetadataFixture).toLowerCase()).not.toContain(
      "tradingview",
    );
  });

  it("represents bounded list and empty-list contracts", () => {
    expect(snapshotListFixture.items).toHaveLength(1);
    expect(snapshotListFixture.next_cursor).toBe(SYNTHETIC_OPAQUE_CURSOR);
    expect(emptySnapshotListFixture).toEqual({
      schema_version: SNAPSHOT_API_SCHEMA_VERSION,
      items: [],
      next_cursor: null,
    });
  });

  it("labels the detail fixture as semantic transport data", () => {
    expect(snapshotDetailFixture.schema_version).toBe(
      SNAPSHOT_API_SCHEMA_VERSION,
    );
    expect(snapshotDetailFixture.snapshot.snapshot_schema_version).toBe(
      "trader_now_snapshot.v1",
    );
    expect(snapshotDetailFixture.snapshot.canonicalization_profile).toBe(
      "atlas-jcs.v1",
    );
    expect(snapshotDetailFixture.snapshot.snapshot_id).toBe(
      SYNTHETIC_SNAPSHOT_ID,
    );
  });

  it("binds successful integrity to the same identity and digest", () => {
    expect(snapshotIntegrityFixture).toEqual({
      schema_version: SNAPSHOT_API_SCHEMA_VERSION,
      snapshot_id: SYNTHETIC_SNAPSHOT_ID,
      evidence_digest: SYNTHETIC_DIGEST,
      valid: true,
    });
  });

  it("freezes sanitized typed failure fixtures", () => {
    expect(snapshotErrorFixtures.notFound.code).toBe("snapshot_not_found");
    expect(snapshotErrorFixtures.integrityFailure.code).toBe(
      "snapshot_integrity_failed",
    );
    expect(snapshotErrorFixtures.unavailable.code).toBe(
      "snapshot_store_unavailable",
    );
    for (const error of Object.values(snapshotErrorFixtures)) {
      expect(error.schema_version).toBe(SNAPSHOT_API_SCHEMA_VERSION);
      expect(error.correlation_id).toBe(SYNTHETIC_CORRELATION_ID);
      expect(JSON.stringify(error).toLowerCase()).not.toMatch(
        /postgres|database_url|bearer|password|private host/,
      );
    }
  });

  it("contains no canonical byte or capture fixture", () => {
    const allFixtures = JSON.stringify({
      snapshotListFixture,
      snapshotDetailFixture,
      snapshotIntegrityFixture,
      snapshotErrorFixtures,
    }).toLowerCase();
    expect(allFixtures).not.toContain("canonical_bytes");
    expect(allFixtures).not.toContain("canonical_download");
    expect(allFixtures).not.toContain("operator_token");
    expect(allFixtures).not.toContain("reader_token");
  });
});
