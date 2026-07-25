import { render, screen } from "@testing-library/react";
import { DashboardNavigation } from "@/components/DashboardNavigation";

describe("dashboard navigation", () => {
  it("hides Evidence when the server-side feature is disabled", () => {
    render(<DashboardNavigation evidenceEnabled={false} />);
    expect(
      screen.getByRole("navigation", { name: "Primary" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Operations" })).toHaveAttribute(
      "href",
      "/",
    );
    expect(
      screen.queryByRole("link", { name: "Evidence" }),
    ).not.toBeInTheDocument();
  });

  it("shows the Evidence navigation entry only when enabled", () => {
    render(<DashboardNavigation evidenceEnabled />);
    expect(screen.getByRole("link", { name: "Evidence" })).toHaveAttribute(
      "href",
      "/evidence",
    );
  });
});
