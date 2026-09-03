import Link from "next/link";
import { notFound } from "next/navigation";
import MarkdownBody from "@/components/MarkdownBody";
import { canManageDossiers } from "@/lib/dossier-access";
import {
  getDossier,
  getOrderForVersion,
  listVersions,
} from "@/lib/dossiers";
import { approveAction } from "../actions";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Dossier",
  robots: { index: false, follow: false },
};

/**
 * Owner-only reading view for one dossier series: the report of a chosen
 * version, the agent's end-control next to it, and every earlier version one
 * click away — a dossier is a dated document, and "what changed since the
 * last run" is itself the signal the versioning exists for.
 */
export default async function DossierPage({
  params,
  searchParams,
}: {
  params: Promise<{ slug: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  if (!canManageDossiers()) notFound();

  const { slug } = await params;
  if (!/^[a-z0-9-]{1,80}$/.test(slug)) notFound();
  const sp = await searchParams;
  const requested = typeof sp.v === "string" ? Number(sp.v) : NaN;
  const version = Number.isInteger(requested) && requested > 0 ? requested : undefined;

  const doc = await getDossier(slug, version);
  if (!doc) notFound();
  const [versions, order] = await Promise.all([
    listVersions(slug),
    getOrderForVersion(slug, doc.version),
  ]);
  const check = order?.check ?? null;

  return (
    <div className="mx-auto max-w-3xl px-4 py-10">
      <header className="border-b border-border pb-6">
        <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-accent">
          Scouting dossier · owner only
        </p>
        <h1 className="mt-3 font-display text-[32px] leading-[1.15] text-paper">
          {doc.topic || doc.slug}
        </h1>
        <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 font-mono text-[11px] text-muted">
          <span className="text-paper">v{doc.version}</span>
          {doc.createdAt && <span>{doc.createdAt.slice(0, 16).replace("T", " ")}</span>}
          {doc.model && <span>{doc.model} · local</span>}
          <span className="ml-auto flex gap-2">
            {versions.map((v) => (
              <Link
                key={v.version}
                href={`/trends/dossiers/${slug}?v=${v.version}`}
                className={
                  v.version === doc.version
                    ? "text-accent"
                    : "text-muted hover:text-paper"
                }
              >
                v{v.version}
              </Link>
            ))}
          </span>
        </div>
        <p className="mt-4 text-[13px] leading-[1.6] text-muted">{doc.question}</p>
      </header>

      {check && (
        <aside className="mt-6 border border-border p-4">
          <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted">
            Agent end-control{" "}
            {check.ok ? (
              <span className="text-accent">clean</span>
            ) : (
              <span className="text-warn">{check.findings.length} finding(s)</span>
            )}
            <span className="text-muted">
              {" "}
              · {check.cited}/{check.sources} sources cited · {check.words} words
              {check.open_questions > 0 && ` · ${check.open_questions} open question(s)`}
            </span>
          </p>
          {check.findings.length > 0 && (
            <ul className="mt-2 list-disc pl-5 font-mono text-[11px] leading-[1.7] text-warn">
              {check.findings.map((f, i) => (
                <li key={i}>{f}</li>
              ))}
            </ul>
          )}
          {order?.status === "review" && (
            <form action={approveAction} className="mt-3">
              <input type="hidden" name="id" value={order.id} />
              <input type="hidden" name="slug" value={slug} />
              <button className="border border-accent px-3 py-1.5 font-mono text-[10px] uppercase tracking-[0.16em] text-accent hover:bg-accent hover:text-ink">
                Sign off this version
              </button>
            </form>
          )}
          {order?.status === "done" && (
            <p className="mt-2 font-mono text-[10px] uppercase tracking-[0.14em] text-paper">
              Signed off
            </p>
          )}
        </aside>
      )}

      <article className="mt-8">
        <MarkdownBody source={doc.reportMd} />
      </article>

      <footer className="mt-10 border-t border-border pt-4">
        <Link
          href="/trends/dossiers"
          className="font-mono text-[11px] uppercase tracking-[0.14em] text-muted hover:text-paper"
        >
          ← Dossier desk
        </Link>
      </footer>
    </div>
  );
}
