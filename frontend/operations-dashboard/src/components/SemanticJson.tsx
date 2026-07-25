"use client";

import { useState } from "react";

export function SemanticJson({ formattedJson }: { formattedJson: string }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <section aria-labelledby="semantic-json-title" className="mt-6">
      <h2 id="semantic-json-title" className="text-lg font-semibold">
        Semantic snapshot JSON
      </h2>
      <div className="mt-2 max-w-4xl text-sm text-[var(--muted)]">
        <p>Semantic snapshot JSON is not canonical bytes.</p>
        <p>It is not the stored canonical payload.</p>
        <p>It must not be used as proof of byte-level equality.</p>
        <p>Indexed metadata remains separate and non-authoritative.</p>
      </div>
      <button
        aria-controls="semantic-json-content"
        aria-expanded={expanded}
        className="mt-3 rounded border border-[var(--border)] px-3 py-2 text-sm font-medium focus:outline focus:outline-2 focus:outline-offset-2 focus:outline-[var(--healthy)]"
        onClick={() => setExpanded((current) => !current)}
        type="button"
      >
        {expanded ? "Hide semantic JSON" : "Show semantic JSON"}
      </button>
      {expanded && (
        <pre
          aria-label="Semantic snapshot JSON content"
          className="mt-3 max-h-[36rem] max-w-full overflow-auto whitespace-pre-wrap break-all rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4 font-mono text-xs"
          id="semantic-json-content"
          tabIndex={0}
        >
          {formattedJson}
        </pre>
      )}
    </section>
  );
}
