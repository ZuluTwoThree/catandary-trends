import Link from "next/link";
import { linkPrefetch } from "@/lib/renderMode";
import { pageWindow } from "@/lib/staticListing";

/**
 * The pagination markup, shared by the search-param feed (Pagination.tsx,
 * hrefs carry the query string) and the static listing (StaticFeed.tsx,
 * hrefs are /trends/page/<n>). Real links (KEY-09) inside a labelled nav
 * landmark with aria-current on the active page (A11Y-09); the arrows
 * additionally carry rel=prev/next.
 */
export default function PaginationNav({
  page,
  totalPages,
  hrefFor,
}: {
  page: number;
  totalPages: number;
  hrefFor: (page: number) => string;
}) {
  if (totalPages <= 1) return null;

  const base =
    "font-mono text-[10px] uppercase tracking-[0.14em] transition-colors";
  const enabled = "text-muted hover:text-paper hover:border-accent/40";
  const disabled = "opacity-30 pointer-events-none";
  const pages = pageWindow(page, totalPages);

  return (
    <nav
      aria-label="Pagination"
      className="flex items-center justify-center gap-2 mt-12 pt-6 border-t border-border"
    >
      <Link
        prefetch={linkPrefetch()}
        href={hrefFor(page - 1)}
        rel={page > 1 ? "prev" : undefined}
        aria-disabled={page <= 1 || undefined}
        tabIndex={page <= 1 ? -1 : undefined}
        className={`${base} px-3 py-2 border border-border ${page <= 1 ? disabled : enabled}`}
      >
        ← Previous
      </Link>

      <div className="flex items-center gap-1">
        {pages.map((p, i) =>
          p === -1 ? (
            <span
              key={`ellipsis-${i}`}
              className="px-2 font-mono text-[10px] text-muted"
              aria-hidden="true"
            >
              …
            </span>
          ) : (
            <Link
              prefetch={linkPrefetch()}
              key={p}
              href={hrefFor(p)}
              aria-current={p === page ? "page" : undefined}
              aria-label={`Page ${p}`}
              className={`${base} w-9 h-9 inline-flex items-center justify-center border ${
                p === page
                  ? "bg-accent text-ink border-accent"
                  : `border-border ${enabled}`
              }`}
            >
              {p}
            </Link>
          )
        )}
      </div>

      <Link
        prefetch={linkPrefetch()}
        href={hrefFor(page + 1)}
        rel={page < totalPages ? "next" : undefined}
        aria-disabled={page >= totalPages || undefined}
        tabIndex={page >= totalPages ? -1 : undefined}
        className={`${base} px-3 py-2 border border-border ${
          page >= totalPages ? disabled : enabled
        }`}
      >
        Next →
      </Link>
    </nav>
  );
}
