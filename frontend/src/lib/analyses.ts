import fs from "node:fs";
import path from "node:path";
import { isPublicMode } from "./publicMode";
import { isStaticExport } from "./renderMode";
import yaml from "js-yaml";

/**
 * Analysis content source (issue #93, Etappe 2 — "The Analyse-Strecke").
 *
 * Analyses are hand-written Markdown files in the repo, not a DB table (the
 * whole point per #93: "Analyse schreiben, committen, live. Kein Admin-UI zu
 * bauen, Versionierung kommt aus git"). This module owns frontmatter parsing
 * and listing; Markdown body rendering lives in `lib/markdown.ts` +
 * `components/MarkdownBody.tsx`.
 *
 * Content lives at `frontend/content/analyses/*.md` (colocated with the app
 * that reads it at build/request time via `fs`, same reasoning as keeping
 * `sources.yaml`-style config next to its reader) — not `frontend/src/...`
 * (not source code) and not the repo-root `docs/` (that's project docs, not
 * published product content).
 *
 * The frontmatter parser reuses `js-yaml` (already a dependency, used for
 * `sources.yaml` in `lib/db.ts`) rather than hand-rolling a YAML subset
 * parser: zero new dependencies, and it correctly handles the quoted
 * strings / trailing `# comments` the spec's own frontmatter example uses,
 * which a naive line-splitter would need to special-case anyway.
 */

const CONTENT_DIR = path.join(process.cwd(), "content", "analyses");
const IMAGE_DIR = path.join(process.cwd(), "public", "analyses");

export interface AnalysisFrontmatter {
  slug: string;
  title: string;
  /** ISO date (YYYY-MM-DD) — publish date. */
  date: string;
  teaser: string;
  /** Bare filename; resolved against `frontend/public/analyses/`. */
  image: string;
  /** ISO date (YYYY-MM-DD) — the corpus snapshot this was built from, not the publish date. */
  corpus_asof: string;
  author: string;
  /** true = never listed on /analysis, never rendered at /analysis/[slug] (404). */
  draft: boolean;
}

export interface Analysis extends AnalysisFrontmatter {
  /** Raw Markdown body (frontmatter stripped), untrimmed rendering is the caller's job. */
  body: string;
}

export interface RawAnalysisFile {
  /** For error messages and slug-collision reporting only. */
  filename: string;
  raw: string;
}

const FRONTMATTER_RE = /^---\r?\n([\s\S]*?)\r?\n---\r?\n?([\s\S]*)$/;

const REQUIRED_STRING_FIELDS = [
  "slug",
  "title",
  "teaser",
  "image",
  "author",
] as const;

function toIsoDate(value: unknown, field: string, filename: string): string {
  // js-yaml parses an unquoted `YYYY-MM-DD` scalar as a JS Date (YAML 1.1
  // timestamp type) rather than leaving it as a string — normalize back to
  // the ISO date string the rest of the app expects.
  if (value instanceof Date) {
    return value.toISOString().slice(0, 10);
  }
  if (typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return value;
  }
  throw new Error(
    `${filename}: frontmatter field "${field}" must be an ISO date (YYYY-MM-DD), got ${JSON.stringify(value)}`
  );
}

export function parseAnalysisFile({ filename, raw }: RawAnalysisFile): Analysis {
  const match = FRONTMATTER_RE.exec(raw);
  if (!match) {
    throw new Error(`${filename}: missing YAML frontmatter (expected a leading "---" ... "---" block)`);
  }
  const [, yamlBlock, body] = match;

  let parsed: unknown;
  try {
    parsed = yaml.load(yamlBlock);
  } catch (err) {
    throw new Error(`${filename}: invalid YAML frontmatter — ${(err as Error).message}`);
  }
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    throw new Error(`${filename}: frontmatter must be a YAML mapping`);
  }
  const fm = parsed as Record<string, unknown>;

  for (const field of REQUIRED_STRING_FIELDS) {
    const value = fm[field];
    if (typeof value !== "string" || value.trim() === "") {
      throw new Error(
        `${filename}: frontmatter field "${field}" is required and must be a non-empty string`
      );
    }
  }

  const image = fm.image as string;
  if (image.includes("/") || image.includes("\\") || image.includes("..")) {
    throw new Error(
      `${filename}: "image" must be a bare filename with no path segments, got ${JSON.stringify(image)}`
    );
  }

  const draftRaw = fm.draft;
  if (draftRaw !== undefined && typeof draftRaw !== "boolean") {
    throw new Error(`${filename}: frontmatter field "draft" must be a boolean if present`);
  }

  return {
    slug: fm.slug as string,
    title: fm.title as string,
    date: toIsoDate(fm.date, "date", filename),
    teaser: fm.teaser as string,
    image,
    corpus_asof: toIsoDate(fm.corpus_asof, "corpus_asof", filename),
    author: fm.author as string,
    draft: draftRaw === true,
    body: body.trim(),
  };
}

/** Parses every file and throws on any duplicate `slug` — before draft filtering, since a
 *  collision between two files is a repo-integrity bug regardless of draft status. */
function parseAndValidate(files: RawAnalysisFile[]): Analysis[] {
  const parsed = files.map((f) => ({ filename: f.filename, analysis: parseAnalysisFile(f) }));

  const seenBy = new Map<string, string>(); // slug -> first filename that claimed it
  for (const { filename, analysis } of parsed) {
    const existing = seenBy.get(analysis.slug);
    if (existing) {
      throw new Error(
        `Duplicate analysis slug "${analysis.slug}": defined in both ${existing} and ${filename}`
      );
    }
    seenBy.set(analysis.slug, filename);
  }

  return parsed.map((p) => p.analysis);
}

export interface AnalysisQuery {
  /** Owner preview only (`showDrafts()`): list/render `draft: true` files too.
   *  Never true under PUBLIC_MODE or in the static export. */
  includeDrafts?: boolean;
}

/** Drafts are visible on the owner instance so a person can read a piece at
 *  its final URL before flipping `draft` — the same pattern as the newsletter
 *  Deep-Dive dry-run. The public site and the export never see them. */
export function showDrafts(): boolean {
  return !isPublicMode() && !isStaticExport();
}

/** Published (non-draft) analyses, newest `date` first (drafts too with `includeDrafts`). */
export function buildAnalysisList(files: RawAnalysisFile[], opts: AnalysisQuery = {}): Analysis[] {
  return parseAndValidate(files)
    .filter((a) => opts.includeDrafts || !a.draft)
    .sort((a, b) => (a.date < b.date ? 1 : a.date > b.date ? -1 : 0));
}

/** A single analysis by slug — null both when the slug doesn't exist AND when it is a draft
 *  ("draft: true wird nirgends gelistet/gerendert", #93 — a draft 404s exactly like a miss). */
export function findAnalysisBySlug(
  files: RawAnalysisFile[],
  slug: string,
  opts: AnalysisQuery = {}
): Analysis | null {
  const found = parseAndValidate(files).find((a) => a.slug === slug);
  if (!found || (found.draft && !opts.includeDrafts)) return null;
  return found;
}

function readContentFiles(): RawAnalysisFile[] {
  if (!fs.existsSync(CONTENT_DIR)) return [];
  return fs
    .readdirSync(CONTENT_DIR)
    .filter((f) => f.endsWith(".md"))
    .map((filename) => ({
      filename,
      raw: fs.readFileSync(path.join(CONTENT_DIR, filename), "utf-8"),
    }));
}

export function getAllAnalyses(opts: AnalysisQuery = {}): Analysis[] {
  return buildAnalysisList(readContentFiles(), opts);
}

export function getAnalysisBySlug(slug: string, opts: AnalysisQuery = {}): Analysis | null {
  return findAnalysisBySlug(readContentFiles(), slug, opts);
}

/** Whether the frontmatter's `image` file actually exists under `public/analyses/`.
 *  Callers use this to decide between the analysis's own OG image and the site default. */
export function analysisImageExists(image: string): boolean {
  try {
    return fs.existsSync(path.join(IMAGE_DIR, image));
  } catch {
    return false;
  }
}

export function analysisImagePath(image: string): string {
  return `/analyses/${image}`;
}

/** "12 September 2026" — parsed as UTC so a date-only ISO string never shifts a day
 *  depending on the server's local timezone. */
export function formatAnalysisDate(iso: string): string {
  const d = new Date(`${iso}T00:00:00Z`);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-US", {
    day: "numeric",
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  });
}
