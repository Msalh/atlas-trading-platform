import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { EvidenceList } from "@/components/EvidenceList";
import {
  SYNTHETIC_DIGEST,
  SYNTHETIC_OPAQUE_CURSOR,
  SYNTHETIC_SECOND_SNAPSHOT_ID,
  emptySnapshotListFixture,
  snapshotListFixture,
  snapshotMetadataFixture,
} from "@/features/evidence/__fixtures__/snapshotApi";
import type { SnapshotListResponse } from "@/features/evidence/contract";

function response(body: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

function page(
  label: string,
  snapshotId: string,
  nextCursor: string | null,
): SnapshotListResponse {
  return {
    schema_version: "snapshot_private_api.v1",
    items: [
      {
        ...snapshotMetadataFixture,
        snapshot_id: snapshotId,
        economic_instrument: label,
        evidence_digest: SYNTHETIC_DIGEST,
      },
    ],
    next_cursor: nextCursor,
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

describe("Evidence list", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders an accessible, responsive list from synthetic metadata", async () => {
    vi.spyOn(globalThis, "fetch").mockReturnValue(
      response(snapshotListFixture),
    );
    render(<EvidenceList />);

    expect(
      screen.getByRole("heading", { name: "Snapshot Evidence", level: 1 }),
    ).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Snapshots" })).toHaveAttribute(
      "aria-busy",
      "true",
    );
    expect(screen.getByRole("status")).toHaveTextContent(
      "Loading snapshot evidence",
    );

    expect(await screen.findByText("MNQ")).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Snapshot list" })).toBeInTheDocument();
    expect(screen.getByLabelText("Page size")).toHaveValue("50");
    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Next" })).toBeEnabled();
    expect(screen.queryByRole("link", { name: /snapshot/i })).not.toBeInTheDocument();
    expect(
      screen.getByRole("region", { name: "Snapshots" }),
    ).toHaveAttribute("aria-busy", "false");
  });

  it("uses an in-memory opaque cursor stack for Next and Previous", async () => {
    const secondPage = page(
      "SECOND PAGE",
      SYNTHETIC_SECOND_SNAPSHOT_ID,
      "second-page-server-cursor",
    );
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockReturnValueOnce(response(snapshotListFixture))
      .mockReturnValueOnce(response(secondPage))
      .mockReturnValueOnce(response(snapshotListFixture));
    render(<EvidenceList />);
    await screen.findByText("MNQ");

    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(await screen.findByText("SECOND PAGE")).toBeInTheDocument();
    expect(screen.getByText("Page 2")).toBeInTheDocument();
    expect(fetchMock.mock.calls[1][0]).toBe(
      `/api/evidence/snapshots?limit=50&cursor=${encodeURIComponent(SYNTHETIC_OPAQUE_CURSOR)}`,
    );

    fireEvent.click(screen.getByRole("button", { name: "Previous" }));
    await waitFor(() => expect(screen.getByText("MNQ")).toBeInTheDocument());
    expect(screen.getByText("Page 1")).toBeInTheDocument();
    expect(fetchMock.mock.calls[2][0]).toBe(
      "/api/evidence/snapshots?limit=50",
    );
  });

  it("clears cursor history for page-size changes and Latest", async () => {
    const secondPage = page(
      "SECOND PAGE",
      SYNTHETIC_SECOND_SNAPSHOT_ID,
      "next-cursor",
    );
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockReturnValueOnce(response(snapshotListFixture))
      .mockReturnValueOnce(response(secondPage))
      .mockReturnValueOnce(response(snapshotListFixture))
      .mockReturnValueOnce(response(snapshotListFixture));
    render(<EvidenceList />);
    await screen.findByText("MNQ");

    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    await screen.findByText("SECOND PAGE");
    fireEvent.change(screen.getByLabelText("Page size"), {
      target: { value: "25" },
    });
    await waitFor(() =>
      expect(fetchMock.mock.calls[2][0]).toBe(
        "/api/evidence/snapshots?limit=25",
      ),
    );
    expect(screen.getByText("Page 1")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "Latest" }));
    await waitFor(() =>
      expect(fetchMock.mock.calls[3][0]).toBe(
        "/api/evidence/snapshots?limit=25",
      ),
    );
    expect(screen.getByText("Page 1")).toBeInTheDocument();
  });

  it("supports manual refresh without changing the current page", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockReturnValueOnce(response(snapshotListFixture))
      .mockReturnValueOnce(response(snapshotListFixture));
    render(<EvidenceList />);
    await screen.findByText("MNQ");
    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(fetchMock.mock.calls[1][0]).toBe(
      "/api/evidence/snapshots?limit=50",
    );
    expect(screen.getByText("Page 1")).toBeInTheDocument();
  });

  it("shows empty and safe list-level error states", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockReturnValueOnce(response(emptySnapshotListFixture))
      .mockReturnValueOnce(
        response(
          {
            ok: false,
            code: "snapshot_service_unavailable",
            correlation_id: "synthetic-correlation",
          },
          503,
        ),
      );
    const { unmount } = render(<EvidenceList />);
    expect(await screen.findByText("No snapshots available")).toBeInTheDocument();
    unmount();

    render(<EvidenceList />);
    expect(
      await screen.findByRole("alert", { name: "" }),
    ).toHaveTextContent("The evidence list is temporarily unavailable.");
    expect(
      screen.queryByText(/postgres|bearer|private-database/i),
    ).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("prevents stale out-of-order responses from replacing Latest", async () => {
    const stale = deferred<Response>();
    const latest = deferred<Response>();
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockReturnValueOnce(response(snapshotListFixture))
      .mockReturnValueOnce(stale.promise)
      .mockReturnValueOnce(latest.promise);
    render(<EvidenceList />);
    await screen.findByText("MNQ");

    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    fireEvent.click(screen.getByRole("button", { name: "Latest" }));
    expect(fetchMock).toHaveBeenCalledTimes(3);

    await act(async () => {
      stale.resolve(
        await response(
          page("STALE RESULT", SYNTHETIC_SECOND_SNAPSHOT_ID, null),
        ),
      );
    });
    expect(screen.queryByText("STALE RESULT")).not.toBeInTheDocument();

    await act(async () => {
      latest.resolve(
        await response(
          page("LATEST RESULT", snapshotMetadataFixture.snapshot_id, null),
        ),
      );
    });
    expect(await screen.findByText("LATEST RESULT")).toBeInTheDocument();
    expect(screen.queryByText("STALE RESULT")).not.toBeInTheDocument();
    expect(screen.getByText("Page 1")).toBeInTheDocument();
  });

  it("prevents stale Next from replacing a newer Previous request", async () => {
    const staleNext = deferred<Response>();
    const previous = deferred<Response>();
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockReturnValueOnce(response(snapshotListFixture))
      .mockReturnValueOnce(staleNext.promise)
      .mockReturnValueOnce(previous.promise);
    render(<EvidenceList />);
    await screen.findByText("MNQ");

    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    fireEvent.click(screen.getByRole("button", { name: "Previous" }));
    expect(fetchMock).toHaveBeenCalledTimes(3);

    await act(async () => {
      previous.resolve(
        await response(
          page("PREVIOUS RESULT", snapshotMetadataFixture.snapshot_id, null),
        ),
      );
    });
    expect(await screen.findByText("PREVIOUS RESULT")).toBeInTheDocument();

    await act(async () => {
      staleNext.resolve(
        await response(
          page("STALE NEXT", SYNTHETIC_SECOND_SNAPSHOT_ID, null),
        ),
      );
    });
    expect(screen.queryByText("STALE NEXT")).not.toBeInTheDocument();
    expect(screen.getByText("PREVIOUS RESULT")).toBeInTheDocument();
    expect(screen.getByText("Page 1")).toBeInTheDocument();
  });

  it("prevents stale Next from replacing a newer page-size request", async () => {
    const staleNext = deferred<Response>();
    const resized = deferred<Response>();
    vi.spyOn(globalThis, "fetch")
      .mockReturnValueOnce(response(snapshotListFixture))
      .mockReturnValueOnce(staleNext.promise)
      .mockReturnValueOnce(resized.promise);
    render(<EvidenceList />);
    await screen.findByText("MNQ");

    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    fireEvent.change(screen.getByLabelText("Page size"), {
      target: { value: "100" },
    });

    await act(async () => {
      resized.resolve(
        await response(
          page("RESIZED RESULT", snapshotMetadataFixture.snapshot_id, null),
        ),
      );
    });
    expect(await screen.findByText("RESIZED RESULT")).toBeInTheDocument();

    await act(async () => {
      staleNext.resolve(
        await response(
          page("STALE NEXT", SYNTHETIC_SECOND_SNAPSHOT_ID, null),
        ),
      );
    });
    expect(screen.queryByText("STALE NEXT")).not.toBeInTheDocument();
    expect(screen.getByText("RESIZED RESULT")).toBeInTheDocument();
    expect(screen.getByText("Page 1")).toBeInTheDocument();
    expect(screen.getByLabelText("Page size")).toHaveValue("100");
  });
});
