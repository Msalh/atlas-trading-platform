import { readSnapshotIntegrity } from "@/features/evidence/server/snapshotReader";

export const dynamic = "force-dynamic";

export async function GET(
  request: Request,
  context: { params: Promise<{ snapshotId: string }> },
) {
  const { snapshotId } = await context.params;
  return readSnapshotIntegrity(request, snapshotId);
}
