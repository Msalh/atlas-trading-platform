import { act, render, screen, waitFor } from "@testing-library/react";
import { SnapshotDetail } from "@/components/SnapshotDetail";
import {
  SYNTHETIC_SECOND_SNAPSHOT_ID,
  SYNTHETIC_SNAPSHOT_ID,
  snapshotDetailFixture,
  snapshotMetadataFixture,
} from "@/features/evidence/__fixtures__/snapshotApi";

function response(body: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

function detailFor(snapshotId: string, schema = "trader_now_snapshot.v1") {
  return {
    ...snapshotDetailFixture,
    snapshot: {
      ...snapshotDetailFixture.snapshot,
      snapshot_id: snapshotId,
      snapshot_schema_version: schema,
    },
  };
}

function metadataFor(snapshotId: string, instrument = "MNQ") {
  return {
    ...snapshotMetadataFixture,
    snapshot_id: snapshotId,
    economic_instrument: instrument,
  };
}

describe("Snapshot detail header and indexed metadata", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("loads only purpose-specific local detail and metadata routes", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockReturnValueOnce(response(snapshotDetailFixture))
      .mockReturnValueOnce(response(snapshotMetadataFixture));
    render(<SnapshotDetail snapshotId={SYNTHETIC_SNAPSHOT_ID} />);

    expect(
      screen.getByRole("heading", { name: "Snapshot Detail", level: 1 }),
    ).toHaveFocus();
    expect(screen.getByRole("status")).toHaveTextContent(
      "Loading snapshot header and indexed metadata",
    );
    expect(
      await screen.findByRole("region", { name: "Snapshot header" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("region", { name: "Indexed metadata" }),
    ).toBeInTheDocument();
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      `/api/evidence/snapshots/${SYNTHETIC_SNAPSHOT_ID}`,
      `/api/evidence/snapshots/${SYNTHETIC_SNAPSHOT_ID}/metadata`,
    ]);
    expect(
      fetchMock.mock.calls.every(
        ([url, init]) =>
          String(url).startsWith("/api/evidence/") &&
          init?.method === "GET" &&
          init.cache === "no-store",
      ),
    ).toBe(true);
  });

  it("presents supported header fields and non-authoritative metadata wording", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockReturnValueOnce(response(snapshotDetailFixture))
      .mockReturnValueOnce(response(snapshotMetadataFixture));
    render(<SnapshotDetail snapshotId={SYNTHETIC_SNAPSHOT_ID} />);

    await screen.findByRole("region", { name: "Indexed metadata" });
    expect(screen.getAllByText(SYNTHETIC_SNAPSHOT_ID).length).toBeGreaterThan(0);
    expect(screen.getByText("trader_now_snapshot.v1")).toBeInTheDocument();
    expect(
      screen.getByText("synthetic-provider:SYNTHETIC:MNQ-CONTINUOUS"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Indexed metadata is for lookup and display."),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Indexed metadata is non-authoritative/),
    ).toHaveTextContent(
      "Evidence authority remains governed by the frozen Phase 17 snapshot contract.",
    );
    expect(
      screen.getByText(/A metadata disagreement is never silently normalized/),
    ).toBeInTheDocument();
    expect(screen.queryByText("synthetic_fact")).not.toBeInTheDocument();
    expect(
      screen.queryByText("Semantic snapshot JSON"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText(/canonical bytes|stored payload/i),
    ).not.toBeInTheDocument();
  });

  it("provides keyboard-safe return navigation and responsive metadata grids", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockReturnValueOnce(response(snapshotDetailFixture))
      .mockReturnValueOnce(response(snapshotMetadataFixture));
    const { container } = render(
      <SnapshotDetail snapshotId={SYNTHETIC_SNAPSHOT_ID} />,
    );
    const back = screen.getByRole("link", { name: "Back to Evidence" });
    expect(back).toHaveAttribute("href", "/evidence");
    back.focus();
    expect(back).toHaveFocus();
    await screen.findByRole("region", { name: "Indexed metadata" });
    expect(
      [...container.querySelectorAll("div")].some((element) =>
        element.className.includes("lg:grid-cols-2"),
      ),
    ).toBe(true);
    expect(
      [...container.querySelectorAll("dl")].some((element) =>
        element.className.includes("sm:grid-cols-2"),
      ),
    ).toBe(true);
  });

  it.each([
    [
      404,
      "snapshot_not_found",
      "Snapshot not found",
      "The requested snapshot is not available.",
    ],
    [
      401,
      "dashboard_authentication_required",
      "Authentication required",
      "Dashboard authentication is required.",
    ],
    [
      502,
      "snapshot_upstream_authorization_failed",
      "Access denied",
      "The reader is not authorized",
    ],
    [
      409,
      "snapshot_integrity_failed",
      "Snapshot unavailable",
      "integrity-related failure",
    ],
    [
      503,
      "snapshot_service_unavailable",
      "Snapshot unavailable",
      "temporarily unavailable",
    ],
  ])(
    "shows a safe distinct error for %s/%s",
    async (status, code, title, message) => {
      vi.spyOn(globalThis, "fetch")
        .mockReturnValueOnce(
          response(
            {
              ok: false,
              code,
              correlation_id: "synthetic-correlation",
            },
            status,
          ),
        )
        .mockReturnValueOnce(response(snapshotMetadataFixture));
      render(<SnapshotDetail snapshotId={SYNTHETIC_SNAPSHOT_ID} />);

      const alert = await screen.findByRole("alert");
      expect(alert).toHaveTextContent(title);
      expect(alert).toHaveTextContent(message);
      expect(screen.queryByText("Indexed metadata")).not.toBeInTheDocument();
      expect(screen.queryByText("synthetic_fact")).not.toBeInTheDocument();
    },
  );

  it("distinguishes unsupported schema from integrity failure", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockReturnValueOnce(response(detailFor(SYNTHETIC_SNAPSHOT_ID, "future.v2")))
      .mockReturnValueOnce(response(snapshotMetadataFixture));
    render(<SnapshotDetail snapshotId={SYNTHETIC_SNAPSHOT_ID} />);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Unsupported snapshot schema");
    expect(alert).not.toHaveTextContent("integrity-related failure");
  });

  it("rejects detail identity mismatch without rendering metadata", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockReturnValueOnce(response(detailFor(SYNTHETIC_SECOND_SNAPSHOT_ID)))
      .mockReturnValueOnce(response(snapshotMetadataFixture));
    render(<SnapshotDetail snapshotId={SYNTHETIC_SNAPSHOT_ID} />);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Unexpected response",
    );
    expect(screen.queryByText("Indexed metadata")).not.toBeInTheDocument();
  });

  it("prevents an older selection from replacing a newer snapshot", async () => {
    const firstDetail = deferred<Response>();
    const firstMetadata = deferred<Response>();
    const secondDetail = deferred<Response>();
    const secondMetadata = deferred<Response>();
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockReturnValueOnce(firstDetail.promise)
      .mockReturnValueOnce(firstMetadata.promise)
      .mockReturnValueOnce(secondDetail.promise)
      .mockReturnValueOnce(secondMetadata.promise);
    const { rerender } = render(
      <SnapshotDetail snapshotId={SYNTHETIC_SNAPSHOT_ID} />,
    );
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const firstSignal = fetchMock.mock.calls[0][1]?.signal;

    rerender(<SnapshotDetail snapshotId={SYNTHETIC_SECOND_SNAPSHOT_ID} />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(4));
    expect(firstSignal?.aborted).toBe(true);

    await act(async () => {
      secondDetail.resolve(
        await response(detailFor(SYNTHETIC_SECOND_SNAPSHOT_ID)),
      );
      secondMetadata.resolve(
        await response(
          metadataFor(SYNTHETIC_SECOND_SNAPSHOT_ID, "NEW SELECTION"),
        ),
      );
    });
    expect(await screen.findByText("NEW SELECTION")).toBeInTheDocument();

    await act(async () => {
      firstDetail.resolve(await response(snapshotDetailFixture));
      firstMetadata.resolve(await response(snapshotMetadataFixture));
    });
    expect(screen.getByText("NEW SELECTION")).toBeInTheDocument();
    expect(screen.queryByText("MNQ")).not.toBeInTheDocument();
  });
});
