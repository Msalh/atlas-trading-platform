import { AccountBalanceCard } from "@/components/AccountBalanceCard";
import { DailyLossCard } from "@/components/DailyLossCard";
import { DrawdownCard } from "@/components/DrawdownCard";
import { ExposureCard } from "@/components/ExposureCard";
import { KillSwitchBanner } from "@/components/KillSwitchBanner";

export default function AccountPage() {
  return (
    <div className="space-y-6">
      <KillSwitchBanner />
      <AccountBalanceCard />
      <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
        <DailyLossCard />
        <DrawdownCard />
      </div>
      <ExposureCard />
      <p className="text-xs text-muted">
        Display only - nothing on this page blocks order execution or enforces any limit.
        The webhook / PickMyTrade relay path is unaffected by anything shown here.
      </p>
    </div>
  );
}
