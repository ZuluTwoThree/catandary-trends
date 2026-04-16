"use client";

import { useRouter, useSearchParams } from "next/navigation";

export default function Pagination({
  total,
  page,
  perPage,
}: {
  total: number;
  page: number;
  perPage: number;
}) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const totalPages = Math.ceil(total / perPage);

  if (totalPages <= 1) return null;

  function goToPage(p: number) {
    const params = new URLSearchParams(searchParams.toString());
    if (p <= 1) {
      params.delete("page");
    } else {
      params.set("page", String(p));
    }
    router.push(`/trends?${params.toString()}`);
  }

  const btnBase =
    "font-mono text-[10px] uppercase tracking-[0.14em] transition-colors disabled:opacity-30 disabled:cursor-not-allowed";

  return (
    <div className="flex items-center justify-center gap-2 mt-12 pt-6 border-t border-border">
      <button
        onClick={() => goToPage(page - 1)}
        disabled={page <= 1}
        className={`${btnBase} px-3 py-2 border border-border text-muted hover:text-paper hover:border-accent/40`}
      >
        ← Previous
      </button>

      <div className="flex items-center gap-1">
        {Array.from({ length: totalPages }, (_, i) => i + 1)
          .filter((p) => p === 1 || p === totalPages || Math.abs(p - page) <= 2)
          .reduce<number[]>((acc, p) => {
            if (acc.length > 0 && p - acc[acc.length - 1] > 1) {
              acc.push(-1);
            }
            acc.push(p);
            return acc;
          }, [])
          .map((p, i) =>
            p === -1 ? (
              <span
                key={`ellipsis-${i}`}
                className="px-2 font-mono text-[10px] text-muted"
              >
                …
              </span>
            ) : (
              <button
                key={p}
                onClick={() => goToPage(p)}
                className={`${btnBase} w-9 h-9 inline-flex items-center justify-center border ${
                  p === page
                    ? "bg-accent text-ink border-accent"
                    : "border-border text-muted hover:text-paper hover:border-accent/40"
                }`}
              >
                {p}
              </button>
            )
          )}
      </div>

      <button
        onClick={() => goToPage(page + 1)}
        disabled={page >= totalPages}
        className={`${btnBase} px-3 py-2 border border-border text-muted hover:text-paper hover:border-accent/40`}
      >
        Next →
      </button>
    </div>
  );
}
