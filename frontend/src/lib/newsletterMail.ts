import { execFile } from "node:child_process";
import path from "node:path";
import { repoRoot } from "./researchPulseWorker";

/**
 * The recipient's mail, rendered for the release view (owner mandate
 * 2026-09-06).
 *
 * The email template lives in Python (pipeline/newsletter_generator.py
 * generate_html — inline styles, tables, the site's palette) and the sender
 * mails exactly that. A second implementation in TSX would drift, and the
 * copy the owner reads before releasing would be the wrong one. So this
 * shells out to the read-only CLI `python -m pipeline.newsletter_preview`
 * (argv, no shell, no send path in that module) and the page shows its output
 * in a sandboxed iframe.
 *
 * The only difference to the delivered mail is the per-recipient unsubscribe
 * link, which renders as a placeholder — see render_email_html() in
 * pipeline/newsletter_sender.py, which both paths go through.
 *
 * Server-side only (node:child_process).
 */

export type MailPreview =
  | { ok: true; html: string }
  | { ok: false; error: string };

const TIMEOUT_MS = 60_000;
const MAX_BUFFER = 8 * 1024 * 1024;

export async function renderEditionMail(year: number, week: number): Promise<MailPreview> {
  if (!Number.isInteger(year) || !Number.isInteger(week)) {
    return { ok: false, error: "bad edition key" };
  }
  const root = repoRoot();
  const py = path.join(root, ".venv", "bin", "python");
  try {
    const html = await new Promise<string>((resolve, reject) => {
      execFile(
        py,
        ["-m", "pipeline.newsletter_preview", "--year", String(year), "--week", String(week)],
        { cwd: root, timeout: TIMEOUT_MS, maxBuffer: MAX_BUFFER },
        (err, stdout, stderr) => {
          if (err) return reject(new Error(String(stderr || err.message).trim()));
          resolve(stdout);
        }
      );
    });
    if (!html.trim()) return { ok: false, error: "the renderer produced nothing" };
    return { ok: true, html };
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    // Last lines only: a Python traceback is long and the useful part is at
    // the end, and this string is shown to the owner on the page.
    return { ok: false, error: msg.split("\n").slice(-4).join("\n").slice(0, 800) };
  }
}
