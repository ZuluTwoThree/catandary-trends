import { readFile } from "node:fs/promises";
import path from "node:path";
import { notFound } from "next/navigation";

export const dynamic = "force-dynamic";

/**
 * Internal content-quality A/B preview (issue #11) — dev/demo only.
 *
 * Renders the before (current prompt, A) vs after (signal-type framing +
 * concreteness, B) bodies from scripts/ab_test_prompt.py in real article
 * styling, so the content-quality change is visible as UX rather than as a
 * score table. Reads frontend/public/quality_preview.json (git-ignored, not
 * shipped). 404s when that file is absent, so it never renders on prod.
 */

interface Scores {
  fidelity: number;
  specificity: number;
  originality: number;
  cliche_freedom: number;
}
interface Item {
  id: number;
  signal_type: string;
  vertical: string;
  source_title: string;
  a_title: string;
  a_body: string;
  b_title: string;
  b_body: string;
  winner: string;
  judge_reason: string;
  scores: { a: Scores; b: Scores };
}
interface Report {
  n: number;
  judged: number;
  wins: { a: number; b: number; tie: number };
  b_win_rate: number;
  mean_a: Scores;
  mean_b: Scores;
}
interface Held {
  id: number;
  title: string;
  flagged: string[];
  source_title: string;
  body: string;
}

/** Highlight the fabricated tokens inside the held body. */
function markFabrications(body: string, flagged: string[]) {
  if (!flagged.length) return body;
  const esc = flagged.map((f) => f.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  const parts = body.split(new RegExp(`(${esc.join("|")})`, "g"));
  const flagSet = new Set(flagged);
  return parts.map((p, i) =>
    flagSet.has(p) ? (
      <mark key={i} className="bg-warn/25 text-warn px-0.5">
        {p}
      </mark>
    ) : (
      <span key={i}>{p}</span>
    )
  );
}

async function load(): Promise<{
  generated: Report;
  items: Item[];
  held?: Held[];
  gate?: { held: number; total: number };
} | null> {
  try {
    const p = path.join(process.cwd(), "public", "quality_preview.json");
    return JSON.parse(await readFile(p, "utf8"));
  } catch {
    return null;
  }
}

const DIMS: [keyof Scores, string][] = [
  ["fidelity", "Source fidelity"],
  ["specificity", "Specificity"],
  ["originality", "Originality"],
  ["cliche_freedom", "Cliché-free"],
];

function Delta({ a, b }: { a: number; b: number }) {
  const d = Math.round((b - a) * 100) / 100;
  const col = d > 0 ? "text-accent" : d < 0 ? "text-warn" : "text-muted";
  return <span className={`${col} tabular-nums`}>{d > 0 ? `+${d}` : d}</span>;
}

export default async function QualityPreviewPage() {
  // Internal QA page — never expose on the public production site, even if a
  // preview JSON happens to be present. Viewable only on a dev build.
  if (process.env.NODE_ENV === "production") notFound();
  const data = await load();
  if (!data) notFound();
  const { generated: r, items, held, gate } = data;

  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-accent mb-3">
        —— Internal · Content quality (#11)
      </div>
      <h1 className="font-display text-3xl md:text-4xl text-paper mb-4">
        Trustworthy briefs: no invented figures, sharper writing
      </h1>
      <p className="font-sans text-text leading-relaxed max-w-3xl mb-6">
        Two changes to how trend articles are written. First and most important — an
        <span className="text-paper"> integrity gate</span> that stops any article containing a
        number or date the source never stated from being auto-published. Second, a revised prompt
        that makes the writing read a little sharper. Measured with an independent Claude judge over{" "}
        {r.judged} trends; the reliable gains are fidelity and cliché-freedom (below), while overall
        preference was a wash ({r.wins.b}–{r.wins.a}) — the prompt is a modest polish, the gate is
        the real win.
      </p>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-10">
        {DIMS.map(([k, label]) => (
          <div key={k} className="border border-border bg-card/40 px-4 py-3">
            <div className="font-mono text-[9px] uppercase tracking-[0.14em] text-muted mb-1">
              {label}
            </div>
            <div className="font-display text-lg text-paper tabular-nums">
              {r.mean_a[k]} → {r.mean_b[k]}{" "}
              <span className="text-sm">
                <Delta a={r.mean_a[k]} b={r.mean_b[k]} />
              </span>
            </div>
          </div>
        ))}
      </div>

      {held && held.length > 0 && gate && (
        <div className="mb-12 border border-warn/30 bg-warn/[0.03] p-5">
          <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-warn mb-2">
            —— Integrity gate: fabricated specifics held for review
          </div>
          <p className="font-sans text-text leading-relaxed max-w-3xl mb-5">
            The model sees only the source excerpt, so any number or date it adds that
            isn&apos;t in the source is invented. The gate holds these drafts for review instead
            of auto-publishing them —{" "}
            <span className="text-paper">
              {gate.held} of {gate.total} high-confidence drafts
            </span>{" "}
            on the current corpus. Below, the invented tokens are highlighted.
          </p>
          <div className="space-y-4">
            {held.map((h) => (
              <div key={h.id} className="border-l-2 border-warn/40 pl-4">
                <p className="font-sans text-xs text-muted italic mb-1">
                  Source: {h.source_title}
                </p>
                <p className="font-sans text-[14px] leading-[1.7] text-text/85">
                  {markFabrications(h.body, h.flagged)}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-accent mb-4">
        —— Sharper briefs: before vs after
      </div>
      <div className="space-y-10">
        {[...items]
          .sort((a, b) => (a.winner === "b" ? 0 : 1) - (b.winner === "b" ? 0 : 1))
          .map((it) => (
          <div key={it.id} className="border-t border-border pt-6">
            <div className="flex flex-wrap items-center gap-3 mb-1">
              <span className="font-mono text-[9px] uppercase tracking-[0.16em] text-muted">
                {it.signal_type} · {it.vertical}
              </span>
              <span
                className={`font-mono text-[9px] uppercase tracking-[0.14em] px-2 py-0.5 border ${
                  it.winner === "b"
                    ? "text-accent border-accent/50 bg-accent/5"
                    : "text-muted border-border"
                }`}
              >
                judge picked {it.winner.toUpperCase()}
              </span>
            </div>
            <p className="font-sans text-xs text-muted italic mb-4 max-w-3xl">
              Source: {it.source_title}
            </p>
            <div className="grid md:grid-cols-2 gap-5">
              <div>
                <div className="font-mono text-[9px] uppercase tracking-[0.18em] text-muted mb-2">
                  A · current
                </div>
                <p className="font-sans text-[15px] leading-[1.7] text-text/85">{it.a_body}</p>
              </div>
              <div className="md:border-l md:border-border md:pl-5">
                <div className="font-mono text-[9px] uppercase tracking-[0.18em] text-accent mb-2">
                  B · signal-type + concreteness
                </div>
                <p className="font-sans text-[15px] leading-[1.7] text-paper">{it.b_body}</p>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
