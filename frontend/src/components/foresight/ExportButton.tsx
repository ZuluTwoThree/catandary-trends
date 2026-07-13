"use client";

/** Small CSV/print export control for a foresight scope (Epic W3.7). */
export default function ExportButton({ scope }: { scope: string }) {
  const params = scope.startsWith("vertical:")
    ? `vertical=${scope.slice("vertical:".length)}`
    : `scope=${scope}`;
  return (
    <div className="flex gap-2">
      <a
        href={`/api/foresight/export?${params}&format=csv`}
        className="rounded-lg border border-current/20 px-3 py-1.5 text-sm hover:bg-current/5"
      >
        Download CSV
      </a>
      <button
        onClick={() => window.print()}
        className="rounded-lg border border-current/20 px-3 py-1.5 text-sm hover:bg-current/5"
      >
        Print / PDF
      </button>
    </div>
  );
}
