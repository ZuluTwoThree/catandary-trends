import Link from "next/link";
import type { TrendTechMatch } from "@/lib/technology";
import { isPublicMode } from "@/lib/publicMode";

/** "FOODS OR FOODSTUFFS; PREPARATION THEREOF (…)" → "Foods or foodstuffs".
 *  Inlined here (not imported from lib/technology) so this client-rendered
 *  component never pulls the pg-backed module into the browser bundle. */
function prettyCpcTitle(m: Pick<TrendTechMatch, "title" | "curated_name">, maxLen = 72): string {
  if (m.curated_name) return m.curated_name;
  // first clause only, before ';' or a parenthetical/brace cross-ref block
  let t = m.title.split(/[;({]/)[0];
  t = t.replace(/,?\s*NOT OTHERWISE PROVIDED FOR/gi, "");
  t = t.replace(/^INDEXING SCHEME[S]?\s+(RELATING TO|ASSOCIATED WITH)\s+/i, "");
  t = t.replace(/[{}]/g, "").replace(/\s+/g, " ").trim();
  // CPC captions are ALL-CAPS, so we can't infer acronyms from the source
  // casing. Lowercase everything, then re-uppercase a small allowlist of real
  // acronyms only.
  const ACRONYMS = new Set(["ai", "ict", "dna", "rna", "led", "ev", "iot", "gps", "rf", "uv", "3d"]);
  t = t
    .toLowerCase()
    .replace(/[a-z0-9]+/g, (w) => (ACRONYMS.has(w) ? w.toUpperCase() : w));
  t = t.charAt(0).toUpperCase() + t.slice(1);
  // hard length cap so a long legal caption never blows out the line
  if (t.length > maxLen) t = t.slice(0, maxLen - 1).replace(/[\s,]+\S*$/, "") + "…";
  return t;
}

/**
 * Technology context block on a trend article (#28).
 *
 * Plain-language bridge from one everyday trend signal to the technology
 * backbone: which patent-classification field the signal maps to (embedding
 * projection), how fast that field iterates, and how far research ran ahead
 * of the market — with the Technology Explorer one click away. Renders
 * nothing when the trend has no confident technology match (cultural /
 * lifestyle signals), so it never shows weak claims.
 *
 * PUBLIC_MODE=1 (#93 Etappe 1): the block's own "Explore this technology"
 * link goes straight to /trends/foresight/technology, which 404s under that
 * flag (proxy.ts) — and the block exists specifically to lead into that
 * explorer, so it renders nothing rather than a teaser with a dead end.
 * Unset/0 changes nothing.
 */
export default function TechContext({ matches }: { matches: TrendTechMatch[] }) {
  if (isPublicMode()) return null;
  if (matches.length === 0) return null;
  const top = matches[0];
  const topName = prettyCpcTitle(top);
  // only surface a second axis as "convergence" when it is genuinely close —
  // near-gate matches (0.5–0.55) are too loose to claim the signal spans them
  const also = matches.slice(1).filter((m) => m.dist < 0.48);

  const facts: { label: string; value: string }[] = [];
  if (top.lead_years != null && top.lead_years > 0) {
    facts.push({
      label: "Lead time",
      value: `Research ran ~${Math.round(top.lead_years)} years ahead of the market in this field`,
    });
  }
  if (top.tir_pct != null) {
    facts.push({
      label: "Improvement rate",
      value: `Field improves an estimated ~${Math.round(top.tir_pct)}% per year`,
    });
  }
  if (top.siblings > 1) {
    facts.push({
      label: "Corpus",
      value: `${top.siblings.toLocaleString("en-US")} signals in our corpus share this technology field`,
    });
  }

  return (
    <div className="mt-10 border border-border bg-card/40 p-5">
      <div className="flex items-baseline justify-between gap-4 mb-3">
        <div className="font-mono text-[9px] uppercase tracking-[0.18em] text-muted">
          Technology Context
        </div>
        <div className="font-mono text-[9px] uppercase tracking-[0.14em] text-muted/70">
          Powered by Catandary Foresight
        </div>
      </div>

      <p className="font-sans text-sm text-text leading-relaxed">
        This signal maps to the technology field{" "}
        <span className="text-paper font-medium">{topName}</span>
        <span className="font-mono text-[10px] text-muted"> · patent class {top.symbol}</span>
        {also.length > 0 && (
          <>
            {" "}
            — also spans {also.map((m, i) => (
              <span key={m.symbol}>
                {i > 0 && ", "}
                <span className="text-paper">{prettyCpcTitle(m, 36)}</span>
              </span>
            ))}
          </>
        )}
      </p>

      {facts.length > 0 && (
        <ul className="mt-3 space-y-1.5">
          {facts.map((f) => (
            <li key={f.label} className="flex items-baseline gap-2 font-sans text-sm text-text">
              <span className="inline-block w-1.5 h-1.5 mt-1 bg-accent shrink-0" aria-hidden="true" />
              {f.value}
            </li>
          ))}
        </ul>
      )}

      <div className="mt-4">
        <Link
          href={
            top.curated_name
              ? `/trends/foresight/technology#${top.symbol}`
              : "/trends/foresight/technology"
          }
          className="font-mono text-[10px] uppercase tracking-[0.14em] text-accent hover:underline"
        >
          Explore this technology →
        </Link>
      </div>
    </div>
  );
}
