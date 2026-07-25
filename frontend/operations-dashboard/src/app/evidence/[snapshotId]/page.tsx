import { notFound } from "next/navigation";
import { SnapshotDetail } from "@/components/SnapshotDetail";
import { isEvidenceBrowserEnabled } from "@/features/evidence/feature";
import { isSnapshotId } from "@/features/evidence/contract";

export const dynamic = "force-dynamic";

export default async function SnapshotDetailPage({
  params,
}: {
  params: Promise<{ snapshotId: string }>;
}) {
  if (!isEvidenceBrowserEnabled()) notFound();
  const { snapshotId } = await params;
  if (!isSnapshotId(snapshotId)) notFound();
  return <SnapshotDetail snapshotId={snapshotId} />;
}
