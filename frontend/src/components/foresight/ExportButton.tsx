"use client";

import { useState } from "react";

/**
 * CSV/print export control for a foresight scope (Epic W3.7). Downloads via
 * fetch so an error becomes a readable message instead of navigating the
 * browser onto raw JSON (KEY-08 / ARCH-15).
 */
export default function ExportButton({ scope }: { scope: string }) {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const params = scope.startsWith("vertical:")
    ? `vertical=${scope.slice("vertical:".length)}`
    : `scope=${scope}`;

  async function download() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/foresight/export?${params}&format=csv`);
      if (!res.ok) {
        setError("Export failed — please try again in a moment.");
        return;
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `catandary-foresight-${scope.replace(":", "-")}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      setError("Export failed — please check your connection and try again.");
    } finally {
      setBusy(false);
    }
  }

  const btn =
    "border border-border-strong px-3 py-1.5 font-mono text-[11px] uppercase tracking-[0.12em] text-paper hover:border-accent transition-colors disabled:opacity-60";

  return (
    <div>
      <div className="flex gap-2">
        <button onClick={download} disabled={busy} className={btn}>
          {busy ? "Preparing…" : "Download CSV"}
        </button>
        <button onClick={() => window.print()} className={btn}>
          Print / PDF
        </button>
      </div>
      {error && (
        <p role="alert" className="mt-2 text-[12px] leading-[1.4] text-warn">
          {error}
        </p>
      )}
    </div>
  );
}
