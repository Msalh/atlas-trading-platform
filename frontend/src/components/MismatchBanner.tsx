// UI v2, architecture §8. Every FROZEN panel is manifest-locked - it always
// renders the identity embedded in its own snapshot envelope, never the
// live selector's value - and compares that identity against the live
// selector on every render. On a mismatch, no frozen numbers render at all
// under this banner (the caller is responsible for hiding its own content;
// see isSymbolTimeframeMismatch below for the same check without the UI),
// and neither selector is switched automatically.

export interface MismatchBannerProps {
  frozenSymbol: string;
  frozenTimeframe: string;
  liveSymbol: string;
  liveTimeframe: string;
}

export function isSymbolTimeframeMismatch(
  frozenSymbol: string,
  frozenTimeframe: string,
  liveSymbol: string,
  liveTimeframe: string,
): boolean {
  return frozenSymbol !== liveSymbol || frozenTimeframe !== liveTimeframe;
}

export function MismatchBanner({ frozenSymbol, frozenTimeframe, liveSymbol, liveTimeframe }: MismatchBannerProps) {
  if (!isSymbolTimeframeMismatch(frozenSymbol, frozenTimeframe, liveSymbol, liveTimeframe)) return null;

  return (
    <div role="status" className="rounded-lg border border-warn/40 bg-warn/10 p-3 text-sm text-warn">
      <p>
        Frozen research baseline is available for {frozenSymbol} / {frozenTimeframe}.
      </p>
      <p>
        Current live selection: <span className="font-mono">{liveSymbol}</span> /{" "}
        <span className="font-mono">{liveTimeframe}</span>.
      </p>
    </div>
  );
}
