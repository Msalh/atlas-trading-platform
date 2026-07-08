import { AICopilotPanel } from "@/components/AICopilotPanel";
import { AiNotesTimeline } from "@/components/AiNotesTimeline";
import { AiReportsPanel } from "@/components/AiReportsPanel";

export default function AiPage() {
  return (
    <div className="space-y-6">
      <AICopilotPanel />
      <AiReportsPanel />
      <AiNotesTimeline />
      <p className="text-xs text-muted">
        Advisory only - AI scoring, review, and reports never block or affect order
        execution. Entry scoring and post-trade review run automatically in the
        background on entry/exit; reports are generated on demand above.
      </p>
    </div>
  );
}
