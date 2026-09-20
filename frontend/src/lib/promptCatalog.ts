/**
 * LLM system-instruction catalogue for /trends/ops/prompts (owner page).
 * Node-only: runs `python -m pipeline.prompt_catalog --json` next to this
 * frontend so the page always shows the prompts the code actually sends.
 * Cached in-process for 60 s (the Python imports behind the catalog take ~1 s).
 */
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

export interface PromptEntry {
  key: string;
  group: string;
  title: string;
  function: string;
  model: string;
  trigger: string;
  symbol: string;
  file: string;
  line: number;
  system: string;
  user_template: string;
  user_template_kind: "rendered" | "source" | "";
  notes: string[];
  error: string;
}

export interface PromptCatalog {
  groups: { key: string; title: string }[];
  entries: PromptEntry[];
}

const TTL_MS = 60_000;
let cache: { at: number; data: PromptCatalog } | null = null;

function repoRoot(): string {
  return process.env.PROMPT_CATALOG_ROOT || path.resolve(process.cwd(), "..");
}

export function loadPromptCatalog(): { data: PromptCatalog | null; error: string | null; cachedAt: Date | null } {
  const now = Date.now();
  if (cache && now - cache.at < TTL_MS) return { data: cache.data, error: null, cachedAt: new Date(cache.at) };
  const root = repoRoot();
  const py = path.join(root, ".venv", "bin", "python");
  if (!fs.existsSync(py)) return { data: cache?.data ?? null, error: `python not found: ${py}`, cachedAt: cache ? new Date(cache.at) : null };
  try {
    const out = execFileSync(py, ["-m", "pipeline.prompt_catalog", "--json"], {
      cwd: root, encoding: "utf-8", timeout: 30_000, maxBuffer: 16 * 1024 * 1024,
      stdio: ["ignore", "pipe", "pipe"],
    });
    const data = JSON.parse(out) as PromptCatalog;
    cache = { at: now, data };
    return { data, error: null, cachedAt: new Date(now) };
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    return { data: cache?.data ?? null, error: msg.slice(0, 400), cachedAt: cache ? new Date(cache.at) : null };
  }
}

/** Entries grouped in catalogue order; groups without entries are dropped. */
export function groupEntries(cat: PromptCatalog): { key: string; title: string; entries: PromptEntry[] }[] {
  return cat.groups
    .map((g) => ({ ...g, entries: cat.entries.filter((e) => e.group === g.key) }))
    .filter((g) => g.entries.length > 0);
}
