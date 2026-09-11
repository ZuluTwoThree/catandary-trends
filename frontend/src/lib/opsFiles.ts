/**
 * File-backed inputs of the ops page (#104, Stufe 4): the live crontab and the
 * logbook. Node-only (fs/child_process) — keep out of client components.
 */
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

/** Repo root: the frontend runs from `<repo>/frontend`. */
const REPO_ROOT = path.resolve(process.cwd(), "..");
export const LOGBOOK_PATH = path.join(REPO_ROOT, "docs", "ops", "logbook.md");
const CRONTAB_TEMPLATE = path.join(REPO_ROOT, "deploy", "crontab.txt");

/**
 * The installed crontab (`crontab -l`) — what really runs — with the deploy
 * template as fallback when the command is unavailable (tests, containers).
 */
export function readCrontab(): { text: string; source: "crontab" | "template" | "none" } {
  try {
    const text = execFileSync("crontab", ["-l"], { encoding: "utf-8", timeout: 3000, stdio: ["ignore", "pipe", "ignore"] });
    if (text.trim()) return { text, source: "crontab" };
  } catch {
    /* fall through */
  }
  try {
    return { text: fs.readFileSync(CRONTAB_TEMPLATE, "utf-8"), source: "template" };
  } catch {
    return { text: "", source: "none" };
  }
}

export function readLogbook(): string | null {
  try {
    return fs.readFileSync(LOGBOOK_PATH, "utf-8");
  } catch {
    return null;
  }
}
