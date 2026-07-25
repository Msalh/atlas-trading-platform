import { fireEvent, render, screen, within } from "@testing-library/react";
import { SemanticEvidence } from "@/components/SemanticEvidence";
import { SemanticJson } from "@/components/SemanticJson";
import {
  SYNTHETIC_SNAPSHOT_ID,
  snapshotDetailFixture,
} from "@/features/evidence/__fixtures__/snapshotApi";
import { projectSemanticSnapshot } from "@/features/evidence/semanticProjection";

function maliciousProjection() {
  const value = structuredClone(snapshotDetailFixture) as unknown as Record<
    string,
    unknown
  >;
  const snapshot = value.snapshot as Record<string, unknown>;
  const evidence = snapshot.evidence as Record<string, unknown>;
  const rules = evidence.rules as Record<string, unknown>;
  const facts = rules.facts as Array<Record<string, unknown>>;
  const trust = evidence.trust as Record<string, unknown>;
  facts[0].fact_id =
    '<img src=x onerror="alert(1)">';
  facts[0].reason =
    "[click](https://example.invalid) <script>alert(1)</script>";
  trust.reason_codes = ["safe\u202Etxt"];
  return projectSemanticSnapshot(value, SYNTHETIC_SNAPSHOT_ID);
}

describe("semantic evidence presentation", () => {
  it("renders untrusted values only as text without HTML, Markdown, or URL activation", () => {
    const projection = maliciousProjection();
    const { container } = render(
      <SemanticEvidence evidence={projection.evidence} />,
    );

    expect(screen.getByText('<img src=x onerror="alert(1)">')).toBeInTheDocument();
    expect(container).toHaveTextContent(
      "[click](https://example.invalid) <script>alert(1)</script>",
    );
    expect(screen.getByText("safe<U+202E>txt")).toBeInTheDocument();
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("a")).toBeNull();
    expect(container.textContent).not.toContain("\u202E");
  });

  it("keeps semantic JSON collapsed, keyboard operable, and explicitly non-canonical", () => {
    const projection = maliciousProjection();
    render(<SemanticJson formattedJson={projection.formattedJson} />);

    expect(screen.getByText("Semantic snapshot JSON is not canonical bytes."))
      .toBeInTheDocument();
    expect(screen.getByText("It is not the stored canonical payload."))
      .toBeInTheDocument();
    expect(screen.queryByLabelText("Semantic snapshot JSON content")).toBeNull();

    const button = screen.getByRole("button", { name: "Show semantic JSON" });
    button.focus();
    fireEvent.click(button);
    expect(button).toHaveAttribute("aria-expanded", "true");
    const content = screen.getByLabelText("Semantic snapshot JSON content");
    expect(() => JSON.parse(content.textContent ?? "")).not.toThrow();
    expect(content).toHaveAttribute("tabindex", "0");
    expect(within(content).queryByRole("link")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Hide semantic JSON" }));
    expect(screen.queryByLabelText("Semantic snapshot JSON content")).toBeNull();
  });

  it("does not place evidence values in accessible labels", () => {
    const projection = maliciousProjection();
    const { container } = render(
      <SemanticEvidence evidence={projection.evidence} />,
    );
    expect(
      [...container.querySelectorAll("[aria-label]")].every(
        (element) => !element.getAttribute("aria-label")?.includes("alert(1)"),
      ),
    ).toBe(true);
  });
});
