import Link from "next/link";
import { getRadarData } from "@/lib/foresight";
import { getEvidence, getRadar, listRadars } from "@/lib/radar";
import { VERTICALS } from "@/lib/types";
import TrendRadar from "@/components/foresight/TrendRadar";
import HorizonBoard from "@/components/foresight/HorizonBoard";
import RadarSelector from "@/components/foresight/RadarSelector";
import ForesightCta from "@/components/ForesightCta";
import TierGate from "@/components/TierGate";
import { parseRadarParams } from "@/lib/radar-params";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Horizon Radar — Catandary Trends",
  description:
    "Technology fields placed on strategic horizons — H1 act, H2 build, H3 watch — per dimension and jurisdiction, with the evidence behind every placement.",
};

/**
 * The radar as a strategic instrument: a chosen set of technology fields, each
 * placed on H1/H2/H3 per dimension and jurisdiction, every cell carrying its
 * reasoning and sources (docs/radar_redesign_proposal.md).
 *
 * The previous lead-time radar stays reachable at ?view=evidence. Its rings
 * encode which *source pool* a cluster's signals came from, which is a corpus
 * partition rather than a maturity statement — it is kept as a corpus overview,
 * not as the default reading.
 */
export default async function RadarPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const raw = await searchParams;
  const params = parseRadarParams(raw);
  const wantEvidenceView = raw.view === "evidence";
  const radars = await listRadars();
  const requestedRadar =
    typeof raw.radar === "string" ? raw.radar : radars[0]?.slug ?? null;

  const view = !wantEvidenceView && requestedRadar ? await getRadar(requestedRadar) : null;

  // Resolve every cell's evidence once, server-side, so the client component
  // never has to fetch.
  let evidenceMap: Record<
    number,
    { id: number; title: string; source_url: string | null; source_name: string | null }
  > = {};
  if (view) {
    const ids = [...new Set(view.cells.flatMap((c) => c.evidence))];
    const items = await getEvidence(ids);
    evidenceMap = Object.fromEntries(items.map((i) => [i.id, i]));
  }

  const asOf = (iso: string | null) =>
    iso
      ? new Date(iso.replace(" ", "T") + "Z").toLocaleDateString("en-US", {
          month: "short",
          day: "numeric",
          year: "numeric",
        })
      : null;

  const chip = (active: boolean) =>
    `font-mono text-[10px] uppercase tracking-[0.14em] px-3 py-1.5 border transition-colors ${
      active
        ? "text-accent border-accent bg-accent/10"
        : "text-muted border-border hover:text-paper"
    }`;

  // ---- Query mode: the user brought their own topic ------------------------
  // Rendered before the saved-radar branch because `q` wins over `radar`
  // (parseRadarParams enforces the same precedence).
  // Der Freitext-Query-Pfad ist am 2026-08-02 entfallen (Owner-Entscheidung).
  // Eine getippte Query definiert ihr Feld über Wörter: sie trennt benachbarte
  // Technologien schlecht, und was sie eingesammelt hat, bleibt für den Leser
  // unsichtbar. Radare werden jetzt aus den Trendclustern der Foresight-Analyse
  // gespeist — die sind über die Lage im Embedding-Raum definiert, also disjunkt,
  // und bringen ihre eigenen Belege mit (pipeline/radar_clusters.py).

  // ---- Horizon radar (default) --------------------------------------------
  if (view) {
    const placed = view.cells.filter((c) => c.effective).length;
    return (
      <div className="rdr">
        {/* Masthead: an instrument plate, not a page header */}
        <header className="rdr-head">
          <div className="rdr-plate">
            <span className="rdr-eyebrow">Foresight · Instrument 01</span>
            <h1 className="rdr-title">
              The horizon <em>arc</em>
            </h1>
            <p className="rdr-lede">
              {view.config.description ??
                "Technology fields placed on strategic horizons per dimension and jurisdiction."}{" "}
              A field rarely sits on one horizon: it can be technologically ready,
              blocked by regulation in one market, and already on sale in another.
            </p>
          </div>
          <dl className="rdr-specs">
            <div>
              <dt>Fields</dt>
              <dd>{view.scopes.length}</dd>
            </div>
            <div>
              <dt>Dimensions</dt>
              <dd>{view.dimensions.length}</dd>
            </div>
            <div>
              <dt>Placements</dt>
              <dd>{placed}</dd>
            </div>
            <div>
              <dt>Signals</dt>
              <dd>{view.n_signals.toLocaleString("en-US")}</dd>
            </div>
            <div>
              <dt>Reading</dt>
              <dd>{asOf(view.generated) ?? "—"}</dd>
            </div>
          </dl>
        </header>

        <RadarSelector radars={radars} current={view.config.slug} />


        <TierGate
          need="starter"
          feature="The full horizon arc"
          benefit={`Starter opens all ${view.scopes.length} technology fields across every dimension and jurisdiction — each placement with its reasoning and its sources.`}
          teaser={
            <div>
              <HorizonBoard
                view={{ ...view, scopes: view.scopes.slice(0, 3) }}
                evidence={evidenceMap}
              />
              <p className="rdr-note">
                Free preview — {Math.min(3, view.scopes.length)} of{" "}
                {view.scopes.length} fields
              </p>
            </div>
          }
        >
          <HorizonBoard view={view} evidence={evidenceMap} />
        </TierGate>

        {/* Method footer — the honest small print, set as a spec sheet */}
        <section className="rdr-method">
          <h2 className="rdr-method-h">How a placement is made</h2>
          <div className="rdr-method-grid">
            <div>
              <span className="rdr-method-k">Technology</span>
              <p>
                From the patent record — takeoff years per CPC class, used only
                where the lead-time is flagged reliable. Otherwise the signal mix,
                capped at H2: scale and cost maturity are not readable from
                signals.
              </p>
            </div>
            <div>
              <span className="rdr-method-k">Regulatory</span>
              <p>
                Approval milestones attributed to the <em>named authority</em> —
                FDA to the US, EFSA to the EU — never to the company&apos;s home
                country. A consultation is not an open route to market.
              </p>
            </div>
            <div>
              <span className="rdr-method-k">Market</span>
              <p>
                Product launches in that jurisdiction, with retail and scale
                markers.{" "}
                {view.config.regulated
                  ? "In this regulated domain the market cannot be rated ahead of its approval — without a licence there is no lawful market."
                  : "No approval coupling in this domain."}
              </p>
            </div>
            <div>
              <span className="rdr-method-k">Silence</span>
              <p>
                Where evidence is too thin, the cell stays empty. A dash is a
                statement: the corpus does not support a call.
              </p>
            </div>
          </div>
          <p className="rdr-method-foot">
            <Link href="/trends/foresight/radar?view=evidence">
              Signal-source overview (the corpus map) →
            </Link>
          </p>
        </section>

        <div className="rdr-cta">
          <ForesightCta />
        </div>

        <style>{`
          .rdr { max-width: 78rem; margin: 0 auto; padding: 2.5rem 1.25rem 4rem; }
          .rdr-head { display: grid; grid-template-columns: minmax(0,1fr) auto; gap: 2.5rem; align-items: end; padding-bottom: 1.6rem; margin-bottom: 1.4rem; border-bottom: 1px solid var(--color-border); }
          @media (max-width: 900px) { .rdr-head { grid-template-columns: 1fr; align-items: start; gap: 1.6rem; } }
          .rdr-eyebrow { font-family: var(--font-mono); font-size: 9.5px; letter-spacing: .3em; text-transform: uppercase; color: var(--color-accent); display: block; margin-bottom: 1rem; }
          .rdr-title { font-family: var(--font-display); font-size: clamp(2.6rem, 6.5vw, 4.6rem); line-height: .98; letter-spacing: -.025em; color: var(--color-paper); margin: 0 0 1.1rem; }
          .rdr-title em { font-style: italic; color: var(--color-accent); }
          .rdr-lede { font-size: 1.02rem; line-height: 1.65; color: var(--color-text); max-width: 42em; margin: 0; }
          .rdr-specs { display: grid; grid-template-columns: repeat(5, auto); gap: 0 1.6rem; margin: 0; }
          @media (max-width: 900px) { .rdr-specs { grid-template-columns: repeat(3, auto); gap: 1rem 1.6rem; } }
          .rdr-specs dt { font-family: var(--font-mono); font-size: 8.5px; letter-spacing: .2em; text-transform: uppercase; color: var(--color-muted); }
          .rdr-specs dd { font-family: var(--font-mono); font-size: 1.15rem; color: var(--color-paper); margin: .3rem 0 0; font-variant-numeric: tabular-nums; }

          .rdr-tabs { display: flex; flex-wrap: wrap; gap: .35rem; margin-bottom: 1.6rem; }
          .rdr-tab { font-family: var(--font-mono); font-size: 10px; letter-spacing: .16em; text-transform: uppercase; padding: .45rem .9rem; border: 1px solid var(--color-border); color: var(--color-muted); text-decoration: none; transition: color .18s, border-color .18s; }
          .rdr-tab:hover { color: var(--color-paper); border-color: var(--color-paper); }
          .rdr-tab.is-on { color: var(--color-accent); border-color: var(--color-accent); background: color-mix(in srgb, var(--color-accent) 8%, transparent); }

          .rdr-note { margin-top: .8rem; font-family: var(--font-mono); font-size: 9px; letter-spacing: .16em; text-transform: uppercase; color: var(--color-muted); }

          .rdr-method { margin-top: 3.5rem; padding-top: 1.6rem; border-top: 1px solid var(--color-border); }
          .rdr-method-h { font-family: var(--font-mono); font-size: 9.5px; letter-spacing: .26em; text-transform: uppercase; color: var(--color-muted); margin: 0 0 1.4rem; font-weight: 400; }
          .rdr-method-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(15rem, 1fr)); gap: 1.6rem 2rem; }
          .rdr-method-k { display: block; font-family: var(--font-mono); font-size: 9px; letter-spacing: .2em; text-transform: uppercase; color: var(--color-accent); margin-bottom: .5rem; }
          .rdr-method-grid p { font-size: .84rem; line-height: 1.6; color: var(--color-muted); margin: 0; }
          .rdr-method-grid em { color: var(--color-text); font-style: italic; }
          .rdr-method-foot { margin: 1.8rem 0 0; font-family: var(--font-mono); font-size: 10px; letter-spacing: .14em; text-transform: uppercase; }
          .rdr-method-foot a { color: var(--color-accent); text-decoration: none; }
          .rdr-method-foot a:hover { text-decoration: underline; }
          .rdr-cta { margin-top: 3rem; }
        `}</style>
      </div>
    );
  }

  // ---- Legacy evidence/lead-time view -------------------------------------
  const requestedVertical =
    typeof raw.vertical === "string" ? raw.vertical.toUpperCase() : null;
  const data = await getRadarData(requestedVertical);
  const FREE_PREVIEW = 8;
  const previewBlips = data.blips
    .slice()
    .sort((a, b) => b.sov_delta_pp - a.sov_delta_pp)
    .slice(0, FREE_PREVIEW);

  return (
    <div className="mx-auto max-w-6xl px-4 py-8">
      <div className="mb-8">
        <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-accent mb-4">
          —— Foresight · Signal sources
        </div>
        <h1 className="font-display text-4xl md:text-[52px] leading-[1.05] tracking-tight text-paper mb-4">
          Where the <span className="italic">signals</span> come from
        </h1>
        <p className="font-sans text-text text-lg leading-relaxed max-w-2xl">
          A corpus overview: each dot is an automatically discovered cluster,
          placed by the kind of source its signals came from — research on the
          rim, trade press at the centre. This is a map of our evidence base, not
          a maturity judgement.
          {data.generated ? (
            <span className="text-muted"> Updated {asOf(data.generated)}.</span>
          ) : null}
        </p>
        {radars.length > 0 && (
          <p className="mt-3 font-mono text-[10px] uppercase tracking-[0.14em]">
            <Link href="/trends/foresight/radar" className="text-accent hover:underline">
              ← Back to the horizon radar
            </Link>
          </p>
        )}
      </div>

      <div className="mb-8 flex flex-wrap gap-1">
        <Link href="/trends/foresight/radar?view=evidence" className={chip(!requestedVertical)}>
          All industries
        </Link>
        {VERTICALS.map((v) => (
          <Link
            key={v.id}
            href={`/trends/foresight/radar?view=evidence&vertical=${v.id}`}
            className={chip(requestedVertical === v.id)}
            style={
              requestedVertical === v.id
                ? { color: v.color, borderColor: v.color }
                : undefined
            }
          >
            {v.label}
          </Link>
        ))}
      </div>

      {data.blips.length > 0 ? (
        <TierGate
          need="starter"
          feature="The full signal-source view"
          benefit={`Starter places all ${data.blips.length} clusters of this view — every industry, every source stage, with the evidence one click away.`}
          teaser={
            <div>
              <TrendRadar blips={previewBlips} vertical={requestedVertical} />
              <p className="mt-3 font-mono text-[10px] uppercase tracking-[0.14em] text-muted">
                Free preview — the {Math.min(FREE_PREVIEW, data.blips.length)} fastest-rising of{" "}
                {data.blips.length} clusters
              </p>
            </div>
          }
        >
          <TrendRadar blips={data.blips} vertical={requestedVertical} />
        </TierGate>
      ) : (
        <div className="border border-border bg-card/40 p-8 text-center">
          <p className="font-display text-[22px] text-paper">Radar is warming up</p>
          <p className="mx-auto mt-2 max-w-md text-sm text-muted leading-relaxed">
            The snapshots behind this view are still being built. In the meantime,
            explore the same trends grouped by momentum in the cluster view.
          </p>
          <Link
            href="/trends/foresight/clusters"
            className="mt-4 inline-block font-mono text-[11px] uppercase tracking-[0.14em] text-accent hover:underline"
          >
            Open the cluster explorer →
          </Link>
        </div>
      )}

      <div className="mt-12">
        <ForesightCta />
      </div>
    </div>
  );
}
