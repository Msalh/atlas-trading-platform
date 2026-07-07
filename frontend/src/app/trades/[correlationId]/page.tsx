import { TradeDetailView } from "@/components/TradeDetailView";

export default async function TradeDetailPage({
  params,
}: {
  params: Promise<{ correlationId: string }>;
}) {
  const { correlationId } = await params;
  return <TradeDetailView correlationId={correlationId} />;
}
