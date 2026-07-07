import { AnalyticsSummaryCards } from "@/components/AnalyticsSummaryCards";
import { BreakdownSection } from "@/components/BreakdownSection";
import { DrawdownChart } from "@/components/DrawdownChart";
import { EquityCurveChart } from "@/components/EquityCurveChart";

export default function AnalyticsPage() {
  return (
    <div className="space-y-6">
      <AnalyticsSummaryCards />
      <EquityCurveChart />
      <DrawdownChart />
      <BreakdownSection />
    </div>
  );
}
