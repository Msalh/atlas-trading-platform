import { TraderNowDashboard } from "@/components/TraderNowDashboard";
import { AdvisoryAnalysisCard } from "@/components/AdvisoryAnalysisCard";

export default function MarketViewPage() {
  return (
    <div className="space-y-4">
      <TraderNowDashboard />
      <AdvisoryAnalysisCard />
    </div>
  );
}
