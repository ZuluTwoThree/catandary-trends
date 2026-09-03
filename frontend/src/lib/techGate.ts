/**
 * Query-quality gate of the Technology tool (#67) — presentation helpers.
 *
 * The analyze API returns `gate` from pipeline/query_gate.py: a three-way verdict
 * (ok | ambiguous | off_topic) plus, for off_topic, 2–3 nearest real fields as
 * suggestions and, for ambiguous, the field clusters the user chooses from BEFORE
 * any number is produced. Pure functions — tested in techGate.test.ts.
 */

export type GateVerdict = "ok" | "ambiguous" | "off_topic";

export interface GateSuggestion { symbol: string; label: string; dist?: number | null }
export interface GateCluster {
  subclass: string;
  label: string;
  detail?: string;
  symbols: string[];
  n?: number;
  source?: "words" | "embedding";
}
export interface Gate {
  verdict: GateVerdict;
  reason?: string | null;
  suggestions?: GateSuggestion[];
  clusters?: GateCluster[];
}

/** Minimum phrase length the API accepts — a suggestion must be re-queryable. */
const MIN_QUERY = 4;
const MAX_QUERY = 200;

/**
 * Verdict of an analysis payload. Backward compatible with payloads that only
 * carry the old boolean `off_topic` (e.g. cached responses from before #67).
 */
export function gateVerdict(res: { off_topic?: boolean; gate?: Gate | null }): GateVerdict {
  const v = res.gate?.verdict;
  if (v === "ok" || v === "ambiguous" || v === "off_topic") return v;
  return res.off_topic ? "off_topic" : "ok";
}

/** Headline for an off-topic answer — honest, no number, no blame. */
export function offTopicHeadline(query: string | undefined): string {
  const q = (query || "").trim();
  return q
    ? `We don't see a technology signature for “${q}”.`
    : "We don't see a technology signature for that phrase.";
}

/**
 * Suggestion phrases for the off-topic answer: unique, re-queryable labels
 * (within the API's length bounds), at most `max`, in the API's distance order.
 */
export function suggestionQueries(gate: Gate | null | undefined, max = 3): string[] {
  const out: string[] = [];
  const seen = new Set<string>();
  for (const s of gate?.suggestions ?? []) {
    const label = (s.label || "").replace(/\s+/g, " ").trim();
    const key = label.toLowerCase();
    if (label.length < MIN_QUERY || seen.has(key)) continue;
    seen.add(key);
    out.push(label.length > MAX_QUERY ? label.slice(0, MAX_QUERY).trim() : label);
    if (out.length >= max) break;
  }
  return out;
}

/**
 * Choices for the ambiguous answer: clusters with at least one class, one per
 * subclass, the lexical ("words") field first, at most `max`.
 */
export function clusterChoices(gate: Gate | null | undefined, max = 4): GateCluster[] {
  const out: GateCluster[] = [];
  const seen = new Set<string>();
  const all = gate?.clusters ?? [];
  const ordered = [...all.filter((c) => c.source === "words"), ...all.filter((c) => c.source !== "words")];
  for (const c of ordered) {
    if (!c.symbols?.length || !c.subclass || seen.has(c.subclass)) continue;
    seen.add(c.subclass);
    out.push(c);
    if (out.length >= max) break;
  }
  return out;
}

/** One-line label for a cluster button: "Computing arrangements … · G06N · 4 classes". */
export function clusterHeadline(c: GateCluster): string {
  const label = (c.label || c.subclass).replace(/\s+/g, " ").trim();
  const n = c.symbols?.length ?? 0;
  return `${label} · ${c.subclass} · ${n} ${n === 1 ? "class" : "classes"}`;
}

/** Why the user is being asked — "words" clusters vs the embedding's field. */
export function clusterHint(c: GateCluster): string {
  return c.source === "words"
    ? "what the words of your phrase point to in patent titles"
    : "what the closest patent classes are about";
}
