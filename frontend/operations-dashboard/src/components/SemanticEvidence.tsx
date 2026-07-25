import {
  safeSemanticText,
  type AvailabilityProjection,
  type SemanticEvidenceProjection,
  type SemanticScalar,
} from "@/features/evidence/semanticProjection";

function value(value: SemanticScalar) {
  return (
    <span className="break-all whitespace-pre-wrap">
      {safeSemanticText(value)}
    </span>
  );
}

function reasons(items: readonly string[]) {
  return items.length === 0
    ? "None"
    : items.map((item) => safeSemanticText(item)).join(", ");
}

function Availability({ item }: { item: AvailabilityProjection }) {
  return (
    <div className="rounded border border-[var(--border)] p-3">
      <span className="text-xs text-[var(--muted)]">{item.name}</span>
      <p className="mt-1 break-all text-sm">{safeSemanticText(item.status)}</p>
      <p className="mt-1 break-all text-xs text-[var(--muted)]">
        {reasons(item.reasonCodes)}
      </p>
    </div>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <details
      className="rounded-lg border border-[var(--border)] bg-[var(--surface)]"
      open
    >
      <summary className="cursor-pointer px-4 py-3 text-sm font-semibold focus:outline focus:outline-2 focus:outline-offset-2 focus:outline-[var(--healthy)]">
        {title}
      </summary>
      <div className="border-t border-[var(--border)] p-4">{children}</div>
    </details>
  );
}

export function SemanticEvidence({
  evidence,
}: {
  evidence: SemanticEvidenceProjection;
}) {
  return (
    <section aria-labelledby="semantic-evidence-title" className="mt-6">
      <h2 id="semantic-evidence-title" className="text-lg font-semibold">
        Structured semantic evidence
      </h2>
      <p className="mt-2 max-w-4xl text-sm text-[var(--muted)]">
        Human-readable, allowlisted fields from the semantic snapshot response.
        This presentation does not add trading conclusions.
      </p>
      <div className="mt-4 grid gap-3 lg:grid-cols-2">
        <Section title="Identity and trust">
          <dl className="grid gap-3 sm:grid-cols-2">
            <Field label="Product">{value(evidence.identity.product)}</Field>
            <Field label="Timeframe">{value(evidence.identity.timeframe)}</Field>
            <Field label="Strategy">
              {value(evidence.identity.strategyId)}
            </Field>
            <Field label="Strategy version">
              {value(evidence.identity.strategyVersion)}
            </Field>
            <Field label="Trust">{value(evidence.trust.status)}</Field>
            <Field label="Trust reasons">
              {reasons(evidence.trust.reasonCodes)}
            </Field>
            <Field label="Evaluated">{value(evidence.evaluatedAt)}</Field>
            <Field label="Input snapshot">
              {value(evidence.inputSnapshotAt)}
            </Field>
          </dl>
        </Section>

        <Section title="Availability">
          <ul className="grid list-none gap-2 p-0 sm:grid-cols-2">
            {evidence.availability.map((item) => (
              <li key={item.name}>
                <Availability item={item} />
              </li>
            ))}
          </ul>
        </Section>

        <Section title="Market and source trust">
          <dl className="grid gap-3 sm:grid-cols-2">
            <Field label="Market status">{value(evidence.market.status)}</Field>
            <Field label="Market reasons">
              {reasons(evidence.market.reasonCodes)}
            </Field>
            <Field label="Economic instrument">
              {value(evidence.market.economicInstrument)}
            </Field>
            <Field label="Market data series">
              {value(
                evidence.market.provider && evidence.market.seriesSymbol
                  ? `${evidence.market.provider}:${evidence.market.seriesSymbol}`
                  : null,
              )}
            </Field>
            <Field label="Series type">
              {value(evidence.market.seriesType)}
            </Field>
            <Field label="Latest closed">
              {value(evidence.market.latestClosedAt)}
            </Field>
            <Field label="Bars">{value(evidence.market.barCount)}</Field>
            <Field label="Source trust">
              {value(evidence.sourceTrust?.overall ?? null)}
            </Field>
            <Field label="Freshness">
              {value(evidence.sourceTrust?.freshnessStatus ?? null)}
            </Field>
            <Field label="Structural validity">
              {value(evidence.sourceTrust?.structuralValidity ?? null)}
            </Field>
          </dl>
        </Section>

        <Section title="Rules">
          <Availability item={evidence.rules.availability} />
          {evidence.rules.facts.length === 0 ? (
            <p className="mt-3 text-sm text-[var(--muted)]">
              No rule facts were returned.
            </p>
          ) : (
            <ul className="mt-3 grid list-none gap-2 p-0">
              {evidence.rules.facts.map((fact) => (
                <li
                  className="rounded border border-[var(--border)] p-3 text-sm"
                  key={fact.id}
                >
                  <p className="break-all font-mono">{safeSemanticText(fact.id)}</p>
                  <p className="mt-1">
                    {safeSemanticText(fact.status)} · {value(fact.value)}
                  </p>
                  <p className="mt-1 break-all text-xs text-[var(--muted)]">
                    {safeSemanticText(fact.definitionVersion)}
                    {fact.reason ? ` · ${safeSemanticText(fact.reason)}` : ""}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </Section>

        <Section title="Setups and interpretations">
          <Availability item={evidence.setups.availability} />
          <ul className="mt-3 grid list-none gap-2 p-0">
            {evidence.setups.setups.map((setup) => (
              <li
                className="rounded border border-[var(--border)] p-3 text-sm"
                key={setup.id}
              >
                <p className="break-all font-mono">
                  {safeSemanticText(setup.id)}
                </p>
                <p className="mt-1">
                  {safeSemanticText(setup.status)} ·{" "}
                  {setup.detected ? "Detected" : "Not detected"} ·{" "}
                  {safeSemanticText(setup.severity)}
                </p>
              </li>
            ))}
          </ul>
          <Availability item={evidence.interpretations.availability} />
          <ul className="mt-3 grid list-none gap-2 p-0">
            {evidence.interpretations.interpretations.map((item, index) => (
              <li
                className="rounded border border-[var(--border)] p-3 text-sm"
                key={`${item.setupId}-${index}`}
              >
                <p className="break-all font-mono">
                  {safeSemanticText(item.setupId)}
                </p>
                <p className="mt-1">
                  {safeSemanticText(item.direction)} ·{" "}
                  {item.detected ? "Detected" : "Not detected"}
                </p>
                <p className="mt-1 break-all text-xs text-[var(--muted)]">
                  {reasons(item.reasonCodes)}
                </p>
              </li>
            ))}
          </ul>
        </Section>

        <Section title="Context">
          <Availability item={evidence.context.availability} />
          <dl className="mt-3 grid gap-3 sm:grid-cols-2">
            <Field label="Quality">{value(evidence.context.quality)}</Field>
            <Field label="Session phase">
              {value(evidence.context.sessionPhase)}
            </Field>
            <Field label="Volatility regime">
              {value(evidence.context.volatilityRegime)}
            </Field>
          </dl>
        </Section>

        <Section title="Strategy">
          <Availability item={evidence.strategy.availability} />
          <ul className="mt-3 grid list-none gap-2 p-0">
            {evidence.strategy.decisions.map((decision, index) => (
              <li
                className="rounded border border-[var(--border)] p-3 text-sm"
                key={`${decision.strategyId}-${index}`}
              >
                <p className="break-all font-mono">
                  {safeSemanticText(decision.strategyId)}@
                  {safeSemanticText(decision.strategyVersion)}
                </p>
                <p className="mt-1">
                  {safeSemanticText(decision.direction)} ·{" "}
                  {safeSemanticText(decision.disposition)}
                </p>
                <p className="mt-1">
                  Confidence: {value(decision.confidence)}
                </p>
                <p className="mt-1 break-all text-xs text-[var(--muted)]">
                  {reasons(decision.reasonCodes)}
                </p>
              </li>
            ))}
          </ul>
        </Section>

        <Section title="Risk and decision">
          {evidence.risk ? (
            <dl className="grid gap-3 sm:grid-cols-2">
              <Field label="Risk status">{value(evidence.risk.status)}</Field>
              <Field label="Primary reason">
                {value(evidence.risk.primaryReason)}
              </Field>
              <Field label="Requested quantity">
                {value(evidence.risk.requestedQuantity)}
              </Field>
              <Field label="Approved quantity">
                {value(evidence.risk.approvedQuantity)}
              </Field>
              <Field label="Contributing reasons">
                {reasons(evidence.risk.contributingReasons)}
              </Field>
            </dl>
          ) : (
            <p className="text-sm text-[var(--muted)]">
              Risk projection is not present.
            </p>
          )}
          <dl className="mt-3 grid gap-3 sm:grid-cols-2">
            <Field label="Decision availability">
              {value(evidence.decision.availability)}
            </Field>
            <Field label="Decision state">
              {value(evidence.decision.state)}
            </Field>
          </dl>
        </Section>
      </div>
    </section>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <dt className="text-xs text-[var(--muted)]">{label}</dt>
      <dd className="mt-1 min-w-0 break-all text-sm">{children}</dd>
    </div>
  );
}
