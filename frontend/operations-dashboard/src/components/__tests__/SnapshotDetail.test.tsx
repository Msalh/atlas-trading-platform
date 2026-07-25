import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { SnapshotDetail } from "@/components/SnapshotDetail";
import {
  SYNTHETIC_DIGEST,
  SYNTHETIC_SECOND_SNAPSHOT_ID,
  SYNTHETIC_SNAPSHOT_ID,
  snapshotDetailFixture,
  snapshotIntegrityFixture,
  snapshotMetadataFixture,
} from "@/features/evidence/__fixtures__/snapshotApi";

const THIRD_SNAPSHOT_ID = "019b1111-2222-7333-8444-777777777777";

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

function detailFor(
  snapshotId: string,
  schema = "trader_now_snapshot.v1",
  digest = SYNTHETIC_DIGEST,
) {
  return {
    ...snapshotDetailFixture,
    snapshot: {
      ...snapshotDetailFixture.snapshot,
      integrity: {
        algorithm: "sha256",
        evidence_digest: digest,
      },
      snapshot_id: snapshotId,
      snapshot_schema_version: schema,
    },
  };
}

function metadataFor(
  snapshotId: string,
  instrument = "MNQ",
  digest = SYNTHETIC_DIGEST,
) {
  return {
    ...snapshotMetadataFixture,
    snapshot_id: snapshotId,
    economic_instrument: instrument,
    evidence_digest: digest,
  };
}

function integrityFor(snapshotId: string, digest = SYNTHETIC_DIGEST) {
  return {
    ...snapshotIntegrityFixture,
    snapshot_id: snapshotId,
    evidence_digest: digest,
  };
}

function safeError(code: string) {
  return {
    ok: false,
    code,
    correlation_id: "synthetic-correlation",
  };
}

function successFetch(snapshotId = SYNTHETIC_SNAPSHOT_ID) {
  return vi
    .spyOn(globalThis, "fetch")
    .mockReturnValueOnce(response(detailFor(snapshotId)))
    .mockReturnValueOnce(response(metadataFor(snapshotId)))
    .mockReturnValueOnce(response(integrityFor(snapshotId)));
}

function expectNoEvidence() {
  expect(screen.queryByText("Indexed metadata")).not.toBeInTheDocument();
  expect(
    screen.queryByText("Structured semantic evidence"),
  ).not.toBeInTheDocument();
  expect(screen.queryByText("Semantic snapshot JSON")).not.toBeInTheDocument();
  expect(screen.queryByText("synthetic_fact")).not.toBeInTheDocument();
}

function pressTabFrom(element: HTMLElement) {
  fireEvent.keyDown(element, { key: "Tab" });
  const next = [...document.querySelectorAll<HTMLElement>("a[href],button")]
    .filter((candidate) => !candidate.hasAttribute("disabled"))
    .find(
      (candidate) =>
        (element.compareDocumentPosition(candidate) &
          Node.DOCUMENT_POSITION_FOLLOWING) !==
        0,
    );
  next?.focus();
  fireEvent.keyUp(element, { key: "Tab" });
}

describe("Snapshot detail integrity gate", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("suppresses all evidence while requesting three purpose-specific local routes", async () => {
    const detail = deferred<Response>();
    const metadata = deferred<Response>();
    const integrity = deferred<Response>();
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockReturnValueOnce(detail.promise)
      .mockReturnValueOnce(metadata.promise)
      .mockReturnValueOnce(integrity.promise);
    render(<SnapshotDetail snapshotId={SYNTHETIC_SNAPSHOT_ID} />);

    expect(screen.getByRole("status")).toHaveTextContent(
      "Verifying snapshot integrity",
    );
    expectNoEvidence();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      `/api/evidence/snapshots/${SYNTHETIC_SNAPSHOT_ID}`,
      `/api/evidence/snapshots/${SYNTHETIC_SNAPSHOT_ID}/metadata`,
      `/api/evidence/snapshots/${SYNTHETIC_SNAPSHOT_ID}/integrity`,
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

  it("renders all authority boundaries only after same-identity digest verification", async () => {
    successFetch();
    render(<SnapshotDetail snapshotId={SYNTHETIC_SNAPSHOT_ID} />);

    expect(
      await screen.findByRole("region", {
        name: "Verified canonical evidence",
      }),
    ).toHaveTextContent("Evidence digest verified by the Snapshot API.");
    const metadata = screen.getByRole("region", { name: "Indexed metadata" });
    const header = screen.getByRole("region", { name: "Snapshot header" });
    expect(within(header).queryByText("Evidence digest")).not.toBeInTheDocument();
    expect(within(metadata).getByText("Evidence digest")).toBeInTheDocument();
    expect(screen.getByText("Structured semantic evidence")).toBeInTheDocument();
    expect(screen.getByText("Semantic snapshot JSON")).toBeInTheDocument();
    expect(
      screen.getByText("Semantic snapshot JSON is not canonical bytes."),
    ).toBeInTheDocument();
  });

  it("preserves heading focus, logical keyboard navigation, and responsive layout", async () => {
    successFetch();
    const { container } = render(
      <SnapshotDetail snapshotId={SYNTHETIC_SNAPSHOT_ID} />,
    );
    const heading = screen.getByRole("heading", {
      name: "Snapshot Detail",
      level: 1,
    });
    const back = screen.getByRole("link", { name: "Back to Evidence" });
    expect(heading).toHaveFocus();
    pressTabFrom(heading);
    expect(back).toHaveFocus();
    await screen.findByRole("region", { name: "Indexed metadata" });
    expect(
      [...container.querySelectorAll("div")].some((element) =>
        element.className.includes("lg:grid-cols-2"),
      ),
    ).toBe(true);
  });

  it.each([
    [409, "snapshot_integrity_failed", "Integrity verification failed"],
    [401, "dashboard_authentication_required", "Authentication required"],
    [403, "snapshot_upstream_authorization_failed", "Access denied"],
    [404, "snapshot_not_found", "Snapshot not found"],
    [504, "snapshot_upstream_timeout", "Integrity verification timed out"],
    [503, "snapshot_service_unavailable", "Integrity verification unavailable"],
    [502, "unexpected_snapshot_response", "Malformed verification response"],
  ])(
    "maps integrity %s/%s to a distinct fail-closed state",
    async (status, code, title) => {
      vi.spyOn(globalThis, "fetch")
        .mockReturnValueOnce(response(snapshotDetailFixture))
        .mockReturnValueOnce(response(snapshotMetadataFixture))
        .mockReturnValueOnce(response(safeError(code), status));
      render(<SnapshotDetail snapshotId={SYNTHETIC_SNAPSHOT_ID} />);

      expect(await screen.findByRole("alert")).toHaveTextContent(title);
      expectNoEvidence();
    },
  );

  it("distinguishes unsupported schema from failed integrity", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockReturnValueOnce(
        response(detailFor(SYNTHETIC_SNAPSHOT_ID, "future.v2")),
      )
      .mockReturnValueOnce(response(snapshotMetadataFixture))
      .mockReturnValueOnce(response(snapshotIntegrityFixture));
    render(<SnapshotDetail snapshotId={SYNTHETIC_SNAPSHOT_ID} />);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Unsupported snapshot schema");
    expect(alert).not.toHaveTextContent("Integrity verification failed");
    expectNoEvidence();
  });

  it.each([
    [
      "integrity identity",
      integrityFor(SYNTHETIC_SECOND_SNAPSHOT_ID),
      "Malformed verification response",
    ],
    [
      "integrity schema",
      { ...snapshotIntegrityFixture, schema_version: "future.v2" },
      "Malformed verification response",
    ],
    [
      "integrity validity",
      { ...snapshotIntegrityFixture, valid: false },
      "Malformed verification response",
    ],
    [
      "integrity extra fields",
      { ...snapshotIntegrityFixture, unapproved: "field" },
      "Malformed verification response",
    ],
  ])("rejects malformed %s without partial evidence", async (_case, body, title) => {
    vi.spyOn(globalThis, "fetch")
      .mockReturnValueOnce(response(snapshotDetailFixture))
      .mockReturnValueOnce(response(snapshotMetadataFixture))
      .mockReturnValueOnce(response(body));
    render(<SnapshotDetail snapshotId={SYNTHETIC_SNAPSHOT_ID} />);

    expect(await screen.findByRole("alert")).toHaveTextContent(title);
    expectNoEvidence();
  });

  it("distinguishes indexed metadata disagreement from integrity failure", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockReturnValueOnce(response(snapshotDetailFixture))
      .mockReturnValueOnce(
        response(metadataFor(SYNTHETIC_SNAPSHOT_ID, "WRONG SNAPSHOT")),
      )
      .mockReturnValueOnce(response(snapshotIntegrityFixture));
    render(<SnapshotDetail snapshotId={SYNTHETIC_SNAPSHOT_ID} />);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Indexed metadata disagreement",
    );
    expectNoEvidence();
  });

  it("rejects detail identity mismatch after integrity success", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockReturnValueOnce(response(detailFor(SYNTHETIC_SECOND_SNAPSHOT_ID)))
      .mockReturnValueOnce(response(snapshotMetadataFixture))
      .mockReturnValueOnce(response(snapshotIntegrityFixture));
    render(<SnapshotDetail snapshotId={SYNTHETIC_SNAPSHOT_ID} />);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Malformed verification response",
    );
    expectNoEvidence();
  });

  it("classifies metadata snapshot identity mismatch as disagreement", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockReturnValueOnce(response(snapshotDetailFixture))
      .mockReturnValueOnce(response(metadataFor(SYNTHETIC_SECOND_SNAPSHOT_ID)))
      .mockReturnValueOnce(response(snapshotIntegrityFixture));
    render(<SnapshotDetail snapshotId={SYNTHETIC_SNAPSHOT_ID} />);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Indexed metadata disagreement",
    );
    expectNoEvidence();
  });

  it("rejects metadata digest disagreement without normalizing it", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockReturnValueOnce(response(snapshotDetailFixture))
      .mockReturnValueOnce(
        response(metadataFor(SYNTHETIC_SNAPSHOT_ID, "MNQ", "b".repeat(64))),
      )
      .mockReturnValueOnce(response(snapshotIntegrityFixture));
    render(<SnapshotDetail snapshotId={SYNTHETIC_SNAPSHOT_ID} />);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Indexed metadata disagreement",
    );
    expectNoEvidence();
  });

  it("rejects semantic transport digest disagreement as failed integrity", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockReturnValueOnce(
        response(
          detailFor(
            SYNTHETIC_SNAPSHOT_ID,
            "trader_now_snapshot.v1",
            "b".repeat(64),
          ),
        ),
      )
      .mockReturnValueOnce(response(snapshotMetadataFixture))
      .mockReturnValueOnce(response(snapshotIntegrityFixture));
    render(<SnapshotDetail snapshotId={SYNTHETIC_SNAPSHOT_ID} />);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Integrity verification failed",
    );
    expectNoEvidence();
  });

  it("immediately suppresses verified evidence during refresh and keeps it hidden on failure", async () => {
    const fetchMock = successFetch();
    fetchMock
      .mockReturnValueOnce(response(snapshotDetailFixture))
      .mockReturnValueOnce(response(snapshotMetadataFixture))
      .mockReturnValueOnce(
        response(safeError("snapshot_integrity_failed"), 409),
      );
    render(<SnapshotDetail snapshotId={SYNTHETIC_SNAPSHOT_ID} />);
    await screen.findByText("Structured semantic evidence");

    fireEvent.click(
      screen.getByRole("button", { name: "Refresh integrity and evidence" }),
    );
    expect(screen.getByRole("status")).toHaveTextContent(
      "Verifying snapshot integrity",
    );
    expectNoEvidence();
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Integrity verification failed",
    );
    expectNoEvidence();
  });

  it.each(["late_success", "late_failure"])(
    "suppresses Snapshot A %s after Snapshot B verifies",
    async (lateResult) => {
      const first = [
        deferred<Response>(),
        deferred<Response>(),
        deferred<Response>(),
      ];
      const second = [
        deferred<Response>(),
        deferred<Response>(),
        deferred<Response>(),
      ];
      const fetchMock = vi.spyOn(globalThis, "fetch");
      [...first, ...second].forEach((item) =>
        fetchMock.mockReturnValueOnce(item.promise),
      );
      const { rerender } = render(
        <SnapshotDetail snapshotId={SYNTHETIC_SNAPSHOT_ID} />,
      );
      await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
      const firstSignal = fetchMock.mock.calls[0][1]?.signal;
      rerender(<SnapshotDetail snapshotId={SYNTHETIC_SECOND_SNAPSHOT_ID} />);
      await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(6));
      expect(firstSignal?.aborted).toBe(true);

      await act(async () => {
        second[0].resolve(
          await response(detailFor(SYNTHETIC_SECOND_SNAPSHOT_ID)),
        );
        second[1].resolve(
          await response(metadataFor(SYNTHETIC_SECOND_SNAPSHOT_ID)),
        );
        second[2].resolve(
          await response(integrityFor(SYNTHETIC_SECOND_SNAPSHOT_ID)),
        );
      });
      await screen.findByText("Structured semantic evidence");

      await act(async () => {
        first[0].resolve(await response(snapshotDetailFixture));
        first[1].resolve(await response(snapshotMetadataFixture));
        first[2].resolve(
          lateResult === "late_success"
            ? await response(snapshotIntegrityFixture)
            : await response(safeError("snapshot_integrity_failed"), 409),
        );
      });
      expect(screen.getByText("Structured semantic evidence")).toBeInTheDocument();
      expect(
        screen.getAllByText(SYNTHETIC_SECOND_SNAPSHOT_ID).length,
      ).toBeGreaterThan(0);
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    },
  );

  it("binds rapid three-snapshot out-of-order responses to the latest selection", async () => {
    const requests = Array.from({ length: 9 }, () => deferred<Response>());
    const fetchMock = vi.spyOn(globalThis, "fetch");
    requests.forEach((item) => fetchMock.mockReturnValueOnce(item.promise));
    const { rerender } = render(
      <SnapshotDetail snapshotId={SYNTHETIC_SNAPSHOT_ID} />,
    );
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    rerender(<SnapshotDetail snapshotId={SYNTHETIC_SECOND_SNAPSHOT_ID} />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(6));
    rerender(<SnapshotDetail snapshotId={THIRD_SNAPSHOT_ID} />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(9));

    await act(async () => {
      requests[8].resolve(await response(integrityFor(THIRD_SNAPSHOT_ID)));
      requests[6].resolve(await response(detailFor(THIRD_SNAPSHOT_ID)));
      requests[7].resolve(await response(metadataFor(THIRD_SNAPSHOT_ID)));
    });
    await screen.findByText("Structured semantic evidence");

    await act(async () => {
      requests[3].resolve(
        await response(detailFor(SYNTHETIC_SECOND_SNAPSHOT_ID)),
      );
      requests[4].resolve(
        await response(metadataFor(SYNTHETIC_SECOND_SNAPSHOT_ID)),
      );
      requests[5].resolve(
        await response(integrityFor(SYNTHETIC_SECOND_SNAPSHOT_ID)),
      );
      requests[0].resolve(await response(snapshotDetailFixture));
      requests[1].resolve(await response(snapshotMetadataFixture));
      requests[2].resolve(
        await response(safeError("snapshot_integrity_failed"), 409),
      );
    });
    expect(screen.getAllByText(THIRD_SNAPSHOT_ID).length).toBeGreaterThan(0);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
