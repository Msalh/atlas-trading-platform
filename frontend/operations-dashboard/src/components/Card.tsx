import type { ReactNode } from "react";

export function Card({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4">
      <h2 className="mb-4 text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">
        {title}
      </h2>
      <dl className="grid gap-3">{children}</dl>
    </section>
  );
}

export function Field({ label, children, mono = false }: {
  label: string; children: ReactNode; mono?: boolean;
}) {
  return (
    <div className="flex min-w-0 items-start justify-between gap-4 border-b border-[var(--border)] pb-2 last:border-0 last:pb-0">
      <dt className="text-sm text-[var(--muted)]">{label}</dt>
      <dd className={`min-w-0 break-words text-right text-sm ${mono ? "mono" : ""}`}>
        {children ?? "—"}
      </dd>
    </div>
  );
}
