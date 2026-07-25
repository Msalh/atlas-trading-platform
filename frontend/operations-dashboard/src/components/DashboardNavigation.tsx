import Link from "next/link";

export function DashboardNavigation({
  evidenceEnabled,
}: {
  evidenceEnabled: boolean;
}) {
  return (
    <nav
      aria-label="Primary"
      className="border-b border-[var(--border)] bg-[var(--surface)]"
    >
      <div className="mx-auto flex max-w-7xl items-center gap-5 px-4 py-3 text-sm sm:px-6">
        <Link className="font-medium text-[var(--text)]" href="/">
          Operations
        </Link>
        {evidenceEnabled && (
          <Link className="font-medium text-[var(--text)]" href="/evidence">
            Evidence
          </Link>
        )}
      </div>
    </nav>
  );
}
