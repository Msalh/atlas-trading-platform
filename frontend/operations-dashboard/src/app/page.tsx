import { OperationsDashboard } from "@/components/OperationsDashboard";

// Nonce-based CSP requires request-time rendering so Next can apply the
// per-request nonce supplied by src/proxy.ts to its framework scripts.
export const dynamic = "force-dynamic";

export default function Page() {
  return <OperationsDashboard />;
}
