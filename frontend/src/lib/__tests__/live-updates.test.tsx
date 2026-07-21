import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { LiveUpdatesProvider } from "@/lib/live-updates";

// Production hardening: EventSource must connect same-origin to this app's own
// /api/stream route (app/api/stream/route.ts) - never directly to the backend, and
// never with an api_key (or any) query parameter, which is exactly the leak this
// change closes (previously visible in Railway's own access logs on every page
// load). jsdom has no native EventSource, so a minimal stub captures the
// constructor argument without needing a real connection.
class FakeEventSource {
  static instances: FakeEventSource[] = [];
  url: string;
  onerror: (() => void) | null = null;
  onopen: (() => void) | null = null;
  private listeners: Record<string, Array<(event: unknown) => void>> = {};

  constructor(url: string) {
    this.url = url;
    FakeEventSource.instances.push(this);
  }

  addEventListener(type: string, callback: (event: unknown) => void) {
    (this.listeners[type] ??= []).push(callback);
  }

  close() {}
}

function renderProvider() {
  const client = new QueryClient();
  return render(
    <QueryClientProvider client={client}>
      <LiveUpdatesProvider>
        <div>child</div>
      </LiveUpdatesProvider>
    </QueryClientProvider>,
  );
}

describe("LiveUpdatesProvider", () => {
  const originalEventSource = global.EventSource;

  beforeEach(() => {
    FakeEventSource.instances = [];
    // @ts-expect-error - jsdom has no native EventSource; a minimal stub is enough
    // to observe what URL the provider connects to.
    global.EventSource = FakeEventSource;
  });

  afterEach(() => {
    global.EventSource = originalEventSource;
  });

  it("connects to the same-origin /api/stream route, not the backend directly", () => {
    renderProvider();
    expect(FakeEventSource.instances).toHaveLength(1);
    expect(FakeEventSource.instances[0].url).toBe("/api/stream");
  });

  it("never includes an api_key or any query string in the constructed URL", () => {
    renderProvider();
    const { url } = FakeEventSource.instances[0];
    expect(url).not.toContain("api_key");
    expect(url).not.toContain("?");
    expect(url).not.toContain("NEXT_PUBLIC");
  });
});
