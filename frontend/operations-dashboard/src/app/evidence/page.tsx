import { notFound } from "next/navigation";
import { EvidenceList } from "@/components/EvidenceList";
import { isEvidenceBrowserEnabled } from "@/features/evidence/feature";

export const dynamic = "force-dynamic";

export default function EvidencePage() {
  if (!isEvidenceBrowserEnabled()) notFound();
  return <EvidenceList />;
}
