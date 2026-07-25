import { readSnapshotList } from "@/features/evidence/server/snapshotReader";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  return readSnapshotList(request);
}
