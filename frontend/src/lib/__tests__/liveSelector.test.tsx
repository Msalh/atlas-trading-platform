import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { LiveSelectorProvider, useLiveSelector } from "@/lib/liveSelector";

function Probe() {
  const { symbol, timeframe, setSymbol, setTimeframe } = useLiveSelector();
  return (
    <div>
      <span data-testid="symbol">{symbol}</span>
      <span data-testid="timeframe">{timeframe}</span>
      <button onClick={() => setSymbol("ESU6")}>set symbol</button>
      <button onClick={() => setTimeframe("1m")}>set timeframe</button>
    </div>
  );
}

describe("LiveSelectorProvider / useLiveSelector", () => {
  it("provides default symbol/timeframe values", () => {
    render(
      <LiveSelectorProvider>
        <Probe />
      </LiveSelectorProvider>,
    );
    expect(screen.getByTestId("symbol")).toHaveTextContent("MNQU6");
    expect(screen.getByTestId("timeframe")).toHaveTextContent("5m");
  });

  it("updates symbol/timeframe and shares the new value with every consumer", async () => {
    const user = userEvent.setup();
    render(
      <LiveSelectorProvider>
        <Probe />
        <Probe />
      </LiveSelectorProvider>,
    );

    await user.click(screen.getAllByText("set symbol")[0]);
    for (const el of screen.getAllByTestId("symbol")) {
      expect(el).toHaveTextContent("ESU6");
    }

    await user.click(screen.getAllByText("set timeframe")[0]);
    for (const el of screen.getAllByTestId("timeframe")) {
      expect(el).toHaveTextContent("1m");
    }
  });

  it("throws when used outside a LiveSelectorProvider", () => {
    function Bare() {
      useLiveSelector();
      return null;
    }
    expect(() => render(<Bare />)).toThrow(/must be used within a LiveSelectorProvider/);
  });
});
