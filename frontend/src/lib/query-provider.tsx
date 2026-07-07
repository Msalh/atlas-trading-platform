"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";

export function QueryProvider({ children }: { children: React.ReactNode }) {
  // Sprint 2 uses polling (refetchInterval per query), not a WebSocket/SSE push -
  // this strategy's signal frequency is low enough that a few-second poll is
  // indistinguishable from "live" for a human trader, and it keeps this sprint's
  // scope to REST only. A push-based transport (SSE, building on the EventBus
  // already in atlas/events/) is a natural, well-scoped later sprint if/when
  // sub-second latency actually matters.
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 2_000,
            refetchOnWindowFocus: true,
          },
        },
      }),
  );

  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
