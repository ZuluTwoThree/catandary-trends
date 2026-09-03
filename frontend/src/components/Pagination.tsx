"use client";

import { useSearchParams } from "next/navigation";
import PaginationNav from "./PaginationNav";

/**
 * Pagination of the search-param feed (/trends?…&page=n): every href keeps
 * the current query string and only changes `page`. The markup lives in
 * PaginationNav (shared with the static listing routes).
 */
export default function Pagination({
  total,
  page,
  perPage,
}: {
  total: number;
  page: number;
  perPage: number;
}) {
  const searchParams = useSearchParams();
  const totalPages = Math.ceil(total / perPage);

  function hrefFor(p: number): string {
    const params = new URLSearchParams(searchParams.toString());
    if (p <= 1) params.delete("page");
    else params.set("page", String(p));
    const qs = params.toString();
    return `/trends${qs ? `?${qs}` : ""}`;
  }

  return <PaginationNav page={page} totalPages={totalPages} hrefFor={hrefFor} />;
}
