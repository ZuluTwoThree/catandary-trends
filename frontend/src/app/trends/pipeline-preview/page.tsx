import { readFile } from "node:fs/promises";
import path from "node:path";
import { notFound } from "next/navigation";

export const dynamic = "force-dynamic";

/**
 * Internal selective-content-generation preview (issue #12) — dev/demo only.
 *
 * Content generation on the 30B is the pipeline bottleneck. The selective gate
 * (STAGE6_MIN_SCORE) writes an article only for survivors above a CRS-score bar
 * and keeps the rest as foresight signals (still embedded/classified, still in
 * the clusters). This page shows, on the real feed, where the bar falls and what
 * it buys. Reads frontend/public/pipeline_preview.json (git-ignored). 404s
 * without it, so it never renders on prod.
 */

interface Data {
  threshold: number;
  total: number;
  below: number;
  pct_below: number;
  hist: { bin_lo: number; n: number }[];
  sec_per_article: number;
  cycle_size: number;
  cycle_saved_min: number;
}

async function load(): Promise<Data | null> {
  try {
    const p = path.join(process.cwd(), "public", "pipeline_preview.json");
    return JSON.parse(await readFile(p, "utf8"));
  } catch {
    return null;
  }
}

export default async function PipelinePreviewPage() {
  const d = await load();
  if (!d) notFound();
  const maxN = Math.max(...d.hist.map((h) => h.n), 1);
  const keptPct = Math.round(100 - d.pct_below);

  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-accent mb-3">
        —— Internal · Pipeline throughput (#12)
      </div>
      <h1 className="font-display text-3xl md:text-4xl text-paper mb-4">
        Selective generation: focus the feed, scale the sources
      </h1>
      <p className="font-sans text-text leading-relaxed max-w-3xl mb-8">
        Writing an article on the 30B is the pipeline&apos;s slowest step
        (~{d.sec_per_article}s each). The gate writes one only for trends above a quality-score
        bar and keeps the rest as foresight signals — they still carry an embedding and
        classification and still power the clusters, they just don&apos;t get a written page. Off by
        default; here is the effect of a{" "}
        <span className="text-paper">{d.threshold.toFixed(2)}</span> bar on the current feed.
      </p>

      <div className="grid grid-cols-3 gap-3 mb-10">
        {[
          [`${keptPct}%`, "kept as articles (top-scored)"],
          [`${d.pct_below}%`, "become foresight signals"],
          [`~${d.cycle_saved_min} min`, `saved per ${d.cycle_size}-article cycle`],
        ].map(([v, label]) => (
          <div key={label} className="border border-border bg-card/40 px-4 py-3">
            <div className="font-display text-2xl text-paper tabular-nums">{v}</div>
            <div className="font-mono text-[9px] uppercase tracking-[0.12em] text-muted mt-1">
              {label}
            </div>
          </div>
        ))}
      </div>

      <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-accent mb-4">
        —— Feed by trend score · colour splits at the {d.threshold.toFixed(2)} cutoff
      </div>
      <div className="flex items-end gap-1.5 h-56 border-b border-border pb-0">
        {d.hist.map((h, i) => {
          const kept = h.bin_lo >= d.threshold;
          // draw the cutoff on the left edge of the first kept bin
          const isCutoffEdge = kept && (i === 0 || d.hist[i - 1].bin_lo < d.threshold);
          return (
            <div
              key={h.bin_lo}
              className={`flex-1 flex flex-col items-center justify-end h-full ${
                isCutoffEdge ? "border-l border-dashed border-accent/60" : ""
              }`}
            >
              <div
                className={`w-full ${kept ? "bg-accent/70" : "bg-muted/30"}`}
                style={{ height: `${(h.n / maxN) * 100}%` }}
                title={`score ${h.bin_lo.toFixed(2)}–${(h.bin_lo + 0.05).toFixed(2)}: ${h.n.toLocaleString("en-US")}`}
              />
              <div className={`font-mono text-[8px] mt-1 ${isCutoffEdge ? "text-accent" : "text-muted"}`}>
                {h.bin_lo.toFixed(2)}
              </div>
            </div>
          );
        })}
      </div>
      <div className="flex items-center gap-5 mt-4 font-mono text-[10px] uppercase tracking-[0.12em] text-muted">
        <span className="flex items-center gap-2">
          <span className="inline-block w-3 h-3 bg-accent/70" /> written as articles ({keptPct}%)
        </span>
        <span className="flex items-center gap-2">
          <span className="inline-block w-3 h-3 bg-muted/30" /> kept as foresight signals ({d.pct_below}%)
        </span>
      </div>

      <p className="font-sans text-sm text-muted mt-8 max-w-3xl leading-relaxed">
        The trade-off is deliberate: a narrower, higher-value article feed and headroom to add
        more sources within the same GPU budget, at the cost of not writing pages for the
        lowest-scored trends. Tunable via <span className="text-paper">STAGE6_MIN_SCORE</span>{" "}
        (0 = write everything, today&apos;s behaviour).
      </p>
    </div>
  );
}
