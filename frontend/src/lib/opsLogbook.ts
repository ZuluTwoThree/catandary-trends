/**
 * Ops logbook (#104, Stufe 4): `docs/ops/logbook.md`, versioned in the repo,
 * rendered on /trends/ops. One entry per `##` heading with a fixed head:
 *
 *     ## 2026-09-11 · change · bequiet als zweite GPU eingebunden
 *     ## 2026-09-15 14:00 · plan · Backfill Volltext-Vektoren
 *     duration: 3h
 *     gpu: bequiet
 *     Freitext …
 *     ## 2026-10 · idea · zweite 3090?
 *
 * Kinds: change (happened), plan (dated, shows in the week plan), decision,
 * idea (no firm date). Optional `key: value` lines right under a heading
 * (duration, gpu) feed the week plan; everything else is the body.
 */

export type LogKind = "change" | "plan" | "decision" | "idea";
export const LOG_KINDS: LogKind[] = ["change", "plan", "decision", "idea"];

export interface LogEntry {
  date: string;          // "2026-09-11" or "2026-09" as written
  time: string | null;   // "14:00" or null
  kind: LogKind;
  title: string;
  meta: Record<string, string>;
  body: string;          // markdown without the meta lines
  line: number;
}

const HEAD = /^##\s+(\d{4}-\d{2}(?:-\d{2})?)(?:[ T](\d{2}:\d{2}))?\s+[·•-]\s+(change|plan|decision|idea)\s+[·•-]\s+(.+?)\s*$/;
const META = /^([a-z_]+):\s*(.+?)\s*$/;

export function parseLogbook(text: string): LogEntry[] {
  const lines = text.split("\n");
  const entries: LogEntry[] = [];
  let cur: LogEntry | null = null;
  let inMeta = false;
  const bodyLines: string[] = [];
  const flush = () => {
    if (cur) {
      cur.body = bodyLines.join("\n").trim();
      entries.push(cur);
    }
    bodyLines.length = 0;
  };
  lines.forEach((line, i) => {
    const m = line.match(HEAD);
    if (m) {
      flush();
      cur = { date: m[1], time: m[2] ?? null, kind: m[3] as LogKind, title: m[4], meta: {}, body: "", line: i + 1 };
      inMeta = true;
      return;
    }
    if (!cur) return;
    if (inMeta) {
      const mm = line.match(META);
      if (mm) {
        cur.meta[mm[1]] = mm[2];
        return;
      }
      if (line.trim() !== "") inMeta = false;
    }
    bodyLines.push(line);
  });
  flush();
  return entries;
}

/** Newest first; entries without a day sort as the 1st of their month. */
export function sortLogbook(entries: LogEntry[]): LogEntry[] {
  const key = (e: LogEntry) => `${e.date.length === 7 ? `${e.date}-01` : e.date} ${e.time ?? "00:00"}`;
  return [...entries].sort((a, b) => (key(a) < key(b) ? 1 : key(a) > key(b) ? -1 : 0));
}

/** "3h", "45m", "2h30m", "1d" → milliseconds; null when unparseable. */
export function parseDuration(s: string | undefined): number | null {
  if (!s) return null;
  let ms = 0;
  let any = false;
  for (const m of s.matchAll(/(\d+(?:[.,]\d+)?)\s*(min|d|h|m)(?![a-z])/g)) {
    const v = parseFloat(m[1].replace(",", "."));
    ms += v * (m[2] === "d" ? 86_400_000 : m[2] === "h" ? 3_600_000 : 60_000);
    any = true;
  }
  return any ? ms : null;
}

/** The plan entry's concrete start (local time), or null when it has no day. */
export function planStart(e: LogEntry): Date | null {
  if (e.kind !== "plan" || e.date.length !== 10) return null;
  const [y, mo, d] = e.date.split("-").map(Number);
  const [hh, mi] = (e.time ?? "00:00").split(":").map(Number);
  return new Date(y, mo - 1, d, hh, mi, 0, 0);
}
