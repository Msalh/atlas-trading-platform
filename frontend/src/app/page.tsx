import { ConnectionStatusPanel } from "@/components/ConnectionStatusPanel";
import { CurrentPositionCard } from "@/components/CurrentPositionCard";
import { StatsSummaryCard } from "@/components/StatsSummaryCard";
import { TradeHistoryTable } from "@/components/TradeHistoryTable";

export default function DashboardPage() {
  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
      <div className="space-y-6 lg:col-span-2">
        <CurrentPositionCard />
        <TradeHistoryTable />
      </div>
      <div className="space-y-6">
        <ConnectionStatusPanel />
        <StatsSummaryCard />
      </div>
    </div>
  );
}
