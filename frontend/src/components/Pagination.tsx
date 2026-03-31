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

  return (
    <div className="flex items-center justify-center gap-2 mt-10">
      <button
        onClick={() => goToPage(page - 1)}
        disabled={page <= 1}
        className="px-3 py-1.5 rounded-lg text-sm border border-border bg-card text-muted hover:text-foreground hover:border-accent/30 transition-all disabled:opacity-30 disabled:cursor-not-allowed"
      >
        &larr; Zurück
      </button>

      <div className="flex items-center gap-1">
        {Array.from({ length: totalPages }, (_, i) => i + 1)
          .filter((p) => p === 1 || p === totalPages || Math.abs(p - page) <= 2)
          .reduce<number[]>((acc, p) => {
            if (acc.length > 0 && p - acc[acc.length - 1] > 1) {
              acc.push(-1); // ellipsis marker
            }
            acc.push(p);
            return acc;
          }, [])
          .map((p, i) =>
            p === -1 ? (
              <span key={`ellipsis-${i}`} className="px-2 text-muted">
                ...
              </span>
            ) : (
              <button
                key={p}
                onClick={() => goToPage(p)}
                className={`w-9 h-9 rounded-lg text-sm font-medium transition-all ${
                  p === page
                    ? "bg-accent text-background"
                    : "border border-border bg-card text-muted hover:text-foreground hover:border-accent/30"
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
        className="px-3 py-1.5 rounded-lg text-sm border border-border bg-card text-muted hover:text-foreground hover:border-accent/30 transition-all disabled:opacity-30 disabled:cursor-not-allowed"
      >
        Weiter &rarr;
      </button>
    </div>
  );
}
