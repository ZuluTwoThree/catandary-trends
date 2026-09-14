import Link from "next/link";
import { notFound } from "next/navigation";
import MarkdownBody from "@/components/MarkdownBody";
import { canManageDossiers } from "@/lib/dossier-access";
import { getAdvisoryNote, PROFILE_FIELDS } from "@/lib/advisory";
import { approveAdvisoryAction, requeueAdvisoryAction, withdrawAdvisoryAction } from "../../../actions";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Advisory note",
  robots: { index: false, follow: false },
};

/**
 * One advisory note (the Advisor, 2026-09-14): the client profile and scope
 * it was written for, the deterministic check and the reader's verdict, the
 * note itself, and the release — approval by a person is the only way a note
 * becomes deliverable (approved_at), mirroring the newsletter rule.
 */
export default async function AdvisoryNotePage({
  params,
}: {
  params: Promise<{ slug: string; id: string }>;
}) {
  if (!canManageDossiers()) notFound();
  const { slug, id } = await params;
  const noteId = Number(id);
  if (!Number.isInteger(noteId) || noteId <= 0) notFound();
  const note = await getAdvisoryNote(noteId);
  if (!note || note.dossierSlug !== slug) notFound();
  const check = note.check;

  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      <Link
        href={`/trends/dossiers/${slug}`}
        className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted hover:text-accent"
      >
        ← Dossier {slug} · v{note.dossierVersion}
      </Link>
      <header className="mt-3">
        <span className="eyebrow">Advisory note #{note.id}</span>
        <h1 className="mt-3 font-display text-[28px] leading-tight text-paper">
          Options for this client — {note.status}
        </h1>
        <p className="mt-2 font-sans text-sm text-text">
          <span className="text-muted">Scope:</span> {note.scope}
        </p>
        <dl className="mt-3 grid grid-cols-1 gap-x-6 gap-y-1 font-sans text-[13px] md:grid-cols-2">
          {PROFILE_FIELDS.filter(([k]) => note.profile[k]).map(([k, label]) => (
            <div key={k} className="flex gap-2">
              <dt className="shrink-0 font-mono text-[10px] uppercase tracking-[0.14em] text-muted">{label}</dt>
              <dd className="text-text">{note.profile[k]}</dd>
            </div>
          ))}
        </dl>
        <p className="mt-2 font-mono text-[10px] uppercase tracking-[0.14em] text-muted">
          {note.model ?? "—"}
          {check?.seconds != null && ` · ${Math.round(check.seconds / 60)} min`}
          {note.approvedAt && ` · approved ${note.approvedAt.slice(0, 16).replace("T", " ")} by ${note.approvedBy}`}
        </p>
      </header>

      {note.status === "failed" && (
        <aside className="mt-6 border border-warn/40 p-4 font-mono text-[11px] text-warn">
          Run failed: {note.error ?? "unknown error"}
          <form action={requeueAdvisoryAction} className="mt-3">
            <input type="hidden" name="id" value={note.id} />
            <input type="hidden" name="slug" value={slug} />
            <button className="border border-accent px-3 py-1.5 font-mono text-[10px] uppercase tracking-[0.16em] text-accent hover:bg-accent hover:text-ink">
              Run again
            </button>
          </form>
        </aside>
      )}

      {(note.status === "queued" || note.status === "running") && (
        <aside className="mt-6 border border-border p-4 font-mono text-[11px] text-muted">
          {note.status === "running" ? "The Advisor is thinking — reload in a few minutes." : "Queued — start it from the dossier page."}
        </aside>
      )}

      {check && (
        <aside className="mt-6 border border-border p-4">
          <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted">
            Check{" "}
            {check.ok ? <span className="text-accent">clean</span> : <span className="text-warn">objections</span>}
            {check.reader_ok !== null && (
              <>
                {" · reader "}
                {check.reader_ok ? <span className="text-accent">no major objection</span> : <span className="text-warn">objects</span>}
              </>
            )}
            <span className="text-muted">
              {" "}· {check.cited} sources cited · {check.words} words
            </span>
          </p>
          {check.findings.length > 0 && (
            <ul className="mt-2 list-disc pl-5 font-mono text-[11px] leading-[1.7] text-warn">
              {check.findings.map((f, i) => (
                <li key={i}>{f}</li>
              ))}
            </ul>
          )}
          {note.status === "review" && (
            <form action={approveAdvisoryAction} className="mt-4 flex flex-wrap items-end gap-3">
              <input type="hidden" name="id" value={note.id} />
              <input type="hidden" name="slug" value={slug} />
              <label className="block">
                <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">Approval note (optional)</span>
                <input
                  name="note"
                  maxLength={2000}
                  className="mt-1 block w-72 border border-border-strong bg-transparent px-3 py-2 text-[13px] text-paper focus:border-accent focus:outline-none"
                />
              </label>
              <button className="border border-accent px-3 py-2 font-mono text-[10px] uppercase tracking-[0.16em] text-accent hover:bg-accent hover:text-ink">
                Approve for delivery
              </button>
              <button
                formAction={withdrawAdvisoryAction}
                className="border border-border-strong px-3 py-2 font-mono text-[10px] uppercase tracking-[0.16em] text-muted hover:text-warn"
              >
                Discard
              </button>
            </form>
          )}
          {note.status === "approved" && (
            <form action={withdrawAdvisoryAction} className="mt-4">
              <input type="hidden" name="id" value={note.id} />
              <input type="hidden" name="slug" value={slug} />
              <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-paper">
                Approved for delivery{note.approvalNote ? ` — “${note.approvalNote}”` : ""}
              </p>
              <button className="mt-2 border border-border-strong px-3 py-1.5 font-mono text-[10px] uppercase tracking-[0.16em] text-muted hover:text-warn">
                Withdraw approval
              </button>
            </form>
          )}
        </aside>
      )}

      {note.noteMd && (
        <article className="mt-8">
          <MarkdownBody source={note.noteMd} />
        </article>
      )}
    </div>
  );
}
