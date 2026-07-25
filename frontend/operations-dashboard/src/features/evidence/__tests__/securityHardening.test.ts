import { readFileSync } from "node:fs";
import { join } from "node:path";

const root = process.cwd();
const clientFiles = [
  "src/components/EvidenceList.tsx",
  "src/components/SnapshotDetail.tsx",
  "src/components/SemanticEvidence.tsx",
  "src/components/SemanticJson.tsx",
  "src/features/evidence/clientTransport.ts",
  "src/features/evidence/useEvidenceList.ts",
  "src/features/evidence/useSnapshotDetail.ts",
];
const runtimeFiles = [
  ...clientFiles,
  "src/features/evidence/contract.ts",
  "src/features/evidence/feature.ts",
  "src/features/evidence/semanticProjection.ts",
  "src/features/evidence/server/snapshotReader.ts",
];

function contents(files: readonly string[]): string {
  return files
    .map((file) => readFileSync(join(root, file), "utf8"))
    .join("\n");
}

describe("Evidence Browser source hygiene", () => {
  it("keeps server-only configuration out of all client modules", () => {
    expect(contents(clientFiles)).not.toMatch(
      /SNAPSHOT_API_INTERNAL_URL|SNAPSHOT_READER_API_TOKEN|OPERATOR_PASSWORD|TRADER_NOW_API_KEY/,
    );
  });

  it("contains no evidence logging, analytics, metrics, or unsafe rendering", () => {
    expect(contents(runtimeFiles)).not.toMatch(
      /console\.(log|info|warn|error)|dangerouslySetInnerHTML|innerHTML\s*=|analytics\.|metrics\.|canonical_bytes|canonical_download/,
    );
  });

  it("contains no public environment variable dependency", () => {
    expect(contents(runtimeFiles)).not.toContain("NEXT_PUBLIC_");
  });
});
