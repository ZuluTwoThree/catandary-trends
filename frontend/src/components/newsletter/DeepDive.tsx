import Link from "next/link";
import { safeHref } from "@/lib/safeHref";
import { linkPrefetch } from "@/lib/renderMode";
import {
  deepDiveDeskPath,
  type DeepDiveCitation,
  type DeepDiveKind,
  type NewsletterDeepDive,
} from "@/lib/newsletterEditions";

/**
 * "Deep Dive of the Week" (#96) — the researcher-backed section of a weekly
 * briefing. Two faces of the same record:
 *
 *   DeepDiveSection   the public render, used ONLY when the honesty gate
 *                     passed and the run was live (lib/newsletterEditions.ts
 *                     isPublicDeepDive — the caller decides, this component
 *                     trusts it). Every citation link carries the evidence-
 *                     kind badge of the dossier source it points at; the
 *                     footer names the corpus snapshot and the dossier.
 *   DeepDiveOwnerNote the owner-instance note for a dry run / a failed gate:
 *                     theme, gate verdict, audit numbers, desk link, and the
 *                     condensate as a preview. Never rendered in the static
 *                     export (EditionBody checks isStaticExport) and never
 *                     delivered under PUBLIC_MODE (the API route strips it).
 *
 * No hooks — renders in the client page and in the export's server pages.
 */

const KIND_LABEL: Record<DeepDiveKind, string> = {
  article: "article",
  signal: "signal",
  paper: "paper",
  patent: "patent",
  web: "web",
};

const KIND_TITLE: Record<DeepDiveKind, string> = {
  article: "A written-up article in the Catandary corpus",
  signal: "A captured signal — headline and source, not written up",
  paper: "A work from the internal research corpus",
  patent: "A filing from the internal patent corpus — a claimed invention, never a working product",
  web: "A web page fetched in full to close a gap",
};

const LINK_SPLIT_RE = /(\[[^\]]+\]\([^)\s]+\))/g;
const LINK_RE = /^\[([^\]]+)\]\(([^)\s]+)\)$/;

function KindBadge({ kind }: { kind: DeepDiveKind }) {
  return (
    <sup
      title={KIND_TITLE[kind]}
      className="ml-1 inline-block align-baseline border border-border px-1 py-px font-mono text-[8px] uppercase tracking-[0.12em] text-muted leading-none"
    >
      {KIND_LABEL[kind]}
    </sup>
  );
}

/** One paragraph of the condensate: links become anchors with a kind badge. */
function CitedText({
  text,
  byUrl,
}: {
  text: string;
  byUrl: ReadonlyMap<string, DeepDiveCitation>;
}) {
  const parts = text.split(LINK_SPLIT_RE);
  return (
    <>
      {parts.map((part, i) => {
        const m = LINK_RE.exec(part);
        if (!m) return <span key={i}>{part}</span>;
        const href = safeHref(m[2]);
        const cite = byUrl.get(m[2]) ?? (href ? byUrl.get(href) : undefined);
        if (!href) return <span key={i}>{m[1]}</span>;
        const badge = cite ? <KindBadge kind={cite.kind} /> : null;
        if (/^https?:\/\//i.test(href)) {
          return (
            <span key={i}>
              <a href={href} rel="noopener noreferrer" className="text-accent hover:underline transition-colors">
                {m[1]}
              </a>
              {badge}
            </span>
          );
        }
        return (
          <span key={i}>
            <Link prefetch={linkPrefetch()} href={href} className="text-accent hover:underline transition-colors">
              {m[1]}
            </Link>
            {badge}
          </span>
        );
      })}
    </>
  );
}

function citationIndex(dd: NewsletterDeepDive): Map<string, DeepDiveCitation> {
  const byUrl = new Map<string, DeepDiveCitation>();
  for (const c of dd.citations ?? []) if (c?.url) byUrl.set(c.url, c);
  return byUrl;
}

function DeepDiveBody({ dd }: { dd: NewsletterDeepDive }) {
  const byUrl = citationIndex(dd);
  const paragraphs = (dd.body_md ?? "")
    .split(/\n\s*\n/)
    .map((p) => p.trim())
    .filter(Boolean);
  return (
    <>
      {paragraphs.map((para, i) => (
        <p key={i} className="font-sans text-text leading-[1.75] mb-4 last:mb-0">
          <CitedText text={para} byUrl={byUrl} />
        </p>
      ))}
    </>
  );
}

function kindMix(dd: NewsletterDeepDive): string {
  const counts = new Map<DeepDiveKind, number>();
  for (const c of dd.citations ?? []) counts.set(c.kind, (counts.get(c.kind) ?? 0) + 1);
  return (Object.keys(KIND_LABEL) as DeepDiveKind[])
    .filter((k) => counts.get(k))
    .map((k) => `${counts.get(k)} ${KIND_LABEL[k]}${counts.get(k) === 1 ? "" : "s"}`)
    .join(" · ");
}

function modelName(v: string | null | undefined): string {
  if (!v) return "local model";
  return v.replace(/\.gguf$/i, "");
}

/** Provenance footer: what this text is a snapshot OF. */
function Provenance({ dd }: { dd: NewsletterDeepDive }) {
  const mix = kindMix(dd);
  return (
    <div className="mt-5 pt-3 border-t border-dashed border-border font-mono text-[10px] uppercase tracking-[0.12em] text-muted leading-[1.9]">
      {dd.corpus_asof ? <>Corpus snapshot {dd.corpus_asof} · </> : null}
      {(dd.citations?.length ?? 0) > 0 ? <>{dd.citations?.length} sources cited{mix ? ` (${mix})` : ""} · </> : null}
      research {modelName(dd.models?.research)} · text {modelName(dd.models?.condense)} · strictly local
      {dd.dossier_slug ? (
        <>
          {" "}
          · dossier {dd.dossier_slug}
          {dd.dossier_version ? ` v${dd.dossier_version}` : ""}
        </>
      ) : null}
    </div>
  );
}

/* ---------- public ---------- */

export function DeepDiveSection({ dd, index }: { dd: NewsletterDeepDive; index: string }) {
  return (
    <section className="mb-12">
      <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted mb-4">
        {index} — Deep Dive of the Week
      </div>
      <div className="border border-border border-l-[3px] border-l-accent bg-card/40 px-5 py-5">
        {dd.theme_name ? (
          <h2 className="font-display text-[22px] leading-[1.25] text-paper mb-4">{dd.theme_name}</h2>
        ) : null}
        <DeepDiveBody dd={dd} />
        <Provenance dd={dd} />
      </div>
    </section>
  );
}

/* ---------- owner ---------- */

function GateChips({ gates }: { gates: Record<string, boolean> }) {
  const entries = Object.entries(gates);
  if (entries.length === 0) return null;
  return (
    <ul className="flex flex-wrap gap-2 mt-3">
      {entries.map(([k, ok]) => (
        <li
          key={k}
          className={`border px-2 py-0.5 font-mono text-[9px] uppercase tracking-[0.12em] ${
            ok ? "border-border text-muted" : "border-warn text-warn"
          }`}
        >
          {ok ? "ok" : "fail"} · {k.replace(/_/g, " ")}
        </li>
      ))}
    </ul>
  );
}

function num(v: unknown): string {
  return typeof v === "number" ? String(v) : "—";
}

export function DeepDiveOwnerNote({ dd, index }: { dd: NewsletterDeepDive; index: string }) {
  const desk = deepDiveDeskPath(dd);
  const audit = (dd.audit ?? {}) as Record<string, unknown>;
  const reasons = [...(dd.gate_reasons ?? []), ...(dd.condensate_check?.reasons ?? [])];
  const status = dd.status ?? (dd.gate_passed ? "ok" : "gate_failed");
  const verdict = dd.gate_passed ? "gate passed" : status === "ok" ? "ok" : status.replace(/_/g, " ");

  return (
    <section className="mb-12" data-owner-note="deep-dive-dry-run">
      <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted mb-4">
        {index} — Deep Dive · owner note
      </div>
      <div className="border border-dashed border-warn/70 bg-card/40 px-5 py-5">
        <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
          <h2 className="font-display text-[20px] leading-[1.25] text-paper">
            Deep-Dive Dry-Run <span className="text-muted">— not public</span>
          </h2>
          <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-warn">
            {dd.dry_run === false ? "live run · " : "dry run · "}
            {verdict}
          </span>
        </div>
        <p className="font-sans text-[13px] text-muted leading-[1.6] mt-2">
          {dd.theme_name ? (
            <>
              Theme <span className="text-paper">{dd.theme_name}</span>
              {typeof dd.words === "number" && dd.words > 0 ? <> · {dd.words} words</> : null}
              {typeof dd.seconds === "number" ? <> · {Math.round(dd.seconds / 60)} min</> : null}
              {dd.generated_at ? <> · {dd.generated_at.slice(0, 16).replace("T", " ")} UTC</> : null}
            </>
          ) : (
            <>No eligible theme this week{dd.error ? ` — ${dd.error}` : ""}.</>
          )}
          {desk ? (
            <>
              {" "}
              ·{" "}
              <Link prefetch={linkPrefetch()} href={desk} className="text-accent hover:underline">
                Open the dossier in the desk →
              </Link>
            </>
          ) : null}
        </p>
        {dd.gates ? <GateChips gates={dd.gates} /> : null}
        {dd.audit ? (
          <p className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted mt-3 leading-[1.9]">
            audit: {num(audit.supported)} supported · {num(audit.contradictions)} contradictions ·{" "}
            {num(audit.cited)} of {num(audit.sources)} sources cited · {num(audit.stripped)} stripped ·{" "}
            {num(audit.dossier_ungrounded)} ungrounded figures · canonical{" "}
            {typeof audit.canonical_rate === "number" ? `${Math.round(audit.canonical_rate * 100)}%` : "—"}
          </p>
        ) : null}
        {reasons.length > 0 ? (
          <ul className="mt-3 space-y-1 font-sans text-[13px] text-text leading-[1.55] list-disc pl-5">
            {reasons.map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
        ) : null}
        {dd.error && dd.theme_name ? (
          <p className="font-sans text-[13px] text-warn mt-3">{dd.error}</p>
        ) : null}
        {dd.body_md ? (
          <div className="mt-5 pt-5 border-t border-dashed border-border">
            <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted mb-3">
              Condensate preview
            </div>
            <DeepDiveBody dd={dd} />
            <Provenance dd={dd} />
          </div>
        ) : null}
      </div>
    </section>
  );
}
