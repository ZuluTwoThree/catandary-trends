"use client";

import { useEffect, useState } from "react";

/**
 * “Where else” — discovery across the topics you did not choose.
 *
 * This is the payoff of the rating run and the strongest onboarding moment:
 * a user rates ONE topic to the end, and the tool shows them where their
 * interest also lives — in clusters, mega-trends and industries they never
 * picked.
 *
 * It only works because the interest model is global and knows no topic
 * boundaries (see pipeline/instrument.py). Measured on the first real set:
 * “air-based protein” surfaced in TECH as a patent, under the Clean Energy
 * mega-trend as packaging research, and in the cluster “Venture Capital · AI”
 * as “The Industrialization of Atmospheric Nutrition”.
 */

type Hit = {
  id: number; title: string; sim: number;
  source: string | null; url: string | null; type: string; date: string;
};
type Group = {
  kind: "cluster" | "mega" | "vertical";
  field_key: string; label: string | null;
  on_table: boolean; n: number; top_sim: number; hits: Hit[];
};

const KIND_LABEL = { vertical: "Industry", mega: "Mega-trend", cluster: "Cluster" };

export default function Discovery({ onAdd }: { onAdd: () => void }) {
  const [data, setData] = useState<{
    ready: boolean; n_hits?: number; new_groups?: number; groups: Group[];
    model?: { n: number; positives: number };
  } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [open, setOpen] = useState(false);

  async function load() {
    const r = await fetch("/api/foresight/instrument?what=discover");
    const d = await r.json();
    if (!d?.error) setData(d);
  }
  useEffect(() => {
    if (open && !data) void load();
  }, [open, data]);

  async function add(g: Group) {
    setBusy(g.field_key);
    await fetch("/api/foresight/instrument", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ add: g.field_key, label: g.label ?? g.field_key }),
    });
    setBusy(null);
    setData(null);
    await load();
    onAdd();
  }

  const fresh = (data?.groups ?? []).filter((g) => !g.on_table);

  return (
    <section className="dc">
      <div className="dc-head">
        <span className="dc-k">Where else</span>
        {data?.ready ? (
          <span className="dc-n">
            {data.n_hits} matches in your interest · {data.new_groups} topics
            not on your table
          </span>
        ) : (
          <span className="dc-n">learned from your ratings</span>
        )}
        <button className="dc-toggle" onClick={() => setOpen(!open)}>
          {open ? "close" : "look"}
        </button>
      </div>

      {open ? (
        !data ? (
          <p className="dc-msg">Sweeping the corpus…</p>
        ) : !data.ready ? (
          <p className="dc-msg">
            Not enough ratings yet. From 25 ratings with at least 5 high ones,
            the tool can find your interest again across the rest of the corpus.
          </p>
        ) : (
          <>
            <p className="dc-lede">
              Your interest profile knows no topic boundaries. These clusters,
              mega-trends and industries carry signals in your interest even
              though you never chose them.
            </p>
            <div className="dc-groups">
              {fresh.slice(0, 9).map((g) => (
                <article key={g.field_key} className="dc-g">
                  <div className="dc-g-head">
                    <span className="dc-g-kind">{KIND_LABEL[g.kind]}</span>
                    <h4>{g.label}</h4>
                    <span className="dc-g-n">{g.n} matches</span>
                  </div>
                  <ul>
                    {g.hits.map((h) => (
                      <li key={h.id}>
                        <span className="dc-sim">{h.sim.toFixed(2)}</span>
                        {h.url ? (
                          <a href={h.url} target="_blank" rel="noreferrer">
                            {h.title}
                          </a>
                        ) : (
                          <span>{h.title}</span>
                        )}
                      </li>
                    ))}
                  </ul>
                  <button
                    className="dc-add"
                    onClick={() => void add(g)}
                    disabled={busy === g.field_key}
                  >
                    put on the table
                  </button>
                </article>
              ))}
            </div>
          </>
        )
      ) : null}

      <style>{`
        .dc { border-bottom: 1px solid var(--color-border); padding: 1.2rem 0; }
        .dc-head { display: flex; align-items: baseline; gap: 1rem; }
        .dc-k { font-family: var(--font-mono); font-size: 9px; letter-spacing: .22em; text-transform: uppercase; color: #e8503a; }
        .dc-n { font-family: var(--font-mono); font-size: 9px; letter-spacing: .1em; text-transform: uppercase; color: var(--color-muted); }
        .dc-toggle { margin-left: auto; font-family: var(--font-mono); font-size: 9px; letter-spacing: .16em; text-transform: uppercase; padding: .3rem .7rem; border: 1px solid #e8503a; background: transparent; color: #e8503a; cursor: pointer; }
        .dc-toggle:hover { background: #e8503a; color: var(--color-ink); }
        .dc-msg, .dc-lede { font-size: .82rem; color: var(--color-muted); max-width: 50em; line-height: 1.6; margin: .8rem 0 0; }
        .dc-groups { display: grid; grid-template-columns: repeat(auto-fill, minmax(19rem, 1fr)); gap: .8rem; margin-top: 1rem; }
        .dc-g { border: 1px solid var(--color-border); border-top: 2px solid #e8503a; padding: .7rem .8rem; display: grid; gap: .4rem; align-content: start; }
        .dc-g-head { display: grid; gap: .1rem; }
        .dc-g-kind { font-family: var(--font-mono); font-size: 8px; letter-spacing: .18em; text-transform: uppercase; color: var(--color-muted); }
        .dc-g h4 { margin: 0; font-size: .9rem; font-weight: 400; color: var(--color-paper); line-height: 1.25; }
        .dc-g-n { font-family: var(--font-mono); font-size: 8.5px; letter-spacing: .12em; text-transform: uppercase; color: #e8503a; }
        .dc-g ul { list-style: none; margin: 0; padding: 0; display: grid; gap: .25rem; }
        .dc-g li { display: grid; grid-template-columns: 2.2rem 1fr; gap: .4rem; font-size: .76rem; line-height: 1.35; }
        .dc-sim { font-family: var(--font-mono); font-size: 8.5px; color: var(--color-muted); }
        .dc-g a { color: var(--color-text); text-decoration: none; border-bottom: 1px solid transparent; }
        .dc-g a:hover { border-color: var(--color-accent); color: var(--color-paper); }
        .dc-add { margin-top: .2rem; justify-self: start; font-family: var(--font-mono); font-size: 8.5px; letter-spacing: .14em; text-transform: uppercase; padding: .3rem .6rem; border: 1px solid var(--color-border); background: transparent; color: var(--color-muted); cursor: pointer; }
        .dc-add:hover { border-color: var(--color-accent); color: var(--color-accent); }
      `}</style>
    </section>
  );
}
