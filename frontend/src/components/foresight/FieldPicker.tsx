"use client";

import { useEffect, useMemo, useState } from "react";

/**
 * Die Auswahl der Interessensfelder — der erste Arbeitsschritt, nicht eine
 * Einstellung im Hintergrund.
 *
 * Ein Nutzer beobachtet nie alles. 388.285 TECH-Signale, 259 Cluster, 21
 * Mega-Trends: was davon auf den Tisch kommt, entscheidet er, bevor er das
 * erste Signal sieht. Das ist auch die erste Relevanzaussage, die er trifft —
 * nur eben grob und schnell.
 *
 * Drei Flughöhen nebeneinander, weil sie verschiedene Fragen beantworten:
 * die **Branche** („was passiert in meinem Sektor"), der **Mega-Trend**
 * („woraus besteht diese Bewegung"), das **Cluster** („dieses eine Feld").
 * Blechschmidt (S. 106) warnt ausdrücklich davor, die Flughöhe zu verwechseln —
 * ein Radar aus konkreten Technologien taugt nicht für die Vorstandsdiskussion.
 */

type Entry = {
  field_key: string;
  label: string;
  n: number;
  group: string;
  chosen: boolean;
  momentum?: string;
  delta?: number;
  reps?: string[];
};

type Catalog = { vertical: Entry[]; mega: Entry[]; cluster: Entry[] };

const KINDS: { key: keyof Catalog; label: string; blurb: string }[] = [
  { key: "vertical", label: "Branchen", blurb: "Der ganze Signalraum eines Sektors." },
  { key: "mega", label: "Mega-Trends", blurb: "Eine langfristige Bewegung als Ganzes." },
  { key: "cluster", label: "Cluster", blurb: "Ein konkretes Feld, aus den Signalen entstanden." },
];

export default function FieldPicker({
  onChange,
}: {
  onChange: () => void;
}) {
  const [cat, setCat] = useState<Catalog | null>(null);
  const [kind, setKind] = useState<keyof Catalog>("cluster");
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [openList, setOpenList] = useState(false);

  async function load() {
    const r = await fetch("/api/foresight/instrument?what=catalog");
    const d = await r.json();
    if (!d?.error) setCat(d.catalog);
  }

  useEffect(() => {
    void load();
  }, []);

  const chosen = useMemo(() => {
    if (!cat) return [];
    return [...cat.vertical, ...cat.mega, ...cat.cluster].filter((e) => e.chosen);
  }, [cat]);

  const list = useMemo(() => {
    if (!cat) return [];
    const needle = q.trim().toLowerCase();
    return cat[kind].filter(
      (e) =>
        !e.chosen &&
        (!needle ||
          e.label.toLowerCase().includes(needle) ||
          e.group.toLowerCase().includes(needle))
    );
  }, [cat, kind, q]);

  const grouped = useMemo(() => {
    const out = new Map<string, Entry[]>();
    for (const e of list) {
      const g = out.get(e.group) ?? [];
      g.push(e);
      out.set(e.group, g);
    }
    return [...out.entries()].slice(0, 40);
  }, [list]);

  async function toggle(e: Entry) {
    setBusy(e.field_key);
    await fetch("/api/foresight/instrument", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(
        e.chosen
          ? { remove: e.field_key }
          : { add: e.field_key, label: e.label }
      ),
    });
    setBusy(null);
    await load();
    onChange();
  }

  return (
    <section className="fp" aria-label="Interessensfelder">
      <div className="fp-head">
        <span className="fp-k">Ihre Felder</span>
        <span className="fp-n">
          {chosen.length
            ? `${chosen.length} auf dem Tisch`
            : "noch keins gewählt"}
        </span>
        <button className="fp-toggle" onClick={() => setOpenList(!openList)}>
          {openList ? "Katalog schließen" : "Felder hinzufügen"}
        </button>
      </div>

      {chosen.length ? (
        <div className="fp-chosen">
          {chosen.map((e) => (
            <button
              key={e.field_key}
              className="fp-tag"
              onClick={() => void toggle(e)}
              disabled={busy === e.field_key}
              title="Vom Tisch nehmen"
            >
              <span>{e.label}</span>
              <em>{e.n.toLocaleString("de-DE")}</em>
              <i aria-hidden="true">✕</i>
            </button>
          ))}
        </div>
      ) : (
        <p className="fp-empty">
          Wählen Sie die Felder, die Sie beobachten wollen. Ein Nutzer
          interessiert sich selten für alle Vertikalen — die Auswahl ist bereits
          Ihre erste, grobe Relevanzaussage.
        </p>
      )}

      {openList && cat ? (
        <div className="fp-cat">
          <div className="fp-kinds">
            {KINDS.map((k) => (
              <button
                key={k.key}
                className={`fp-kind ${kind === k.key ? "is-on" : ""}`}
                onClick={() => setKind(k.key)}
              >
                {k.label}
                <em>{cat[k.key].filter((e) => !e.chosen).length}</em>
              </button>
            ))}
            <input
              className="fp-search"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="filtern…"
              aria-label="Katalog filtern"
            />
          </div>
          <p className="fp-blurb">{KINDS.find((k) => k.key === kind)!.blurb}</p>

          <div className="fp-groups">
            {grouped.map(([g, entries]) => (
              <div key={g} className="fp-group">
                <h4>{g}</h4>
                <ul>
                  {entries.slice(0, 12).map((e) => (
                    <li key={e.field_key}>
                      <button
                        className="fp-add"
                        onClick={() => void toggle(e)}
                        disabled={busy === e.field_key}
                      >
                        <span className="fp-add-l">{e.label}</span>
                        <span className="fp-add-m">
                          {e.n.toLocaleString("de-DE")} Signale
                          {e.momentum && e.momentum !== "unknown"
                            ? ` · ${
                                e.momentum === "rising"
                                  ? "↑"
                                  : e.momentum === "declining"
                                    ? "↓"
                                    : "→"
                              } ${e.delta! > 0 ? "+" : ""}${e.delta} pp`
                            : ""}
                        </span>
                        {e.reps?.length ? (
                          <span className="fp-add-r">{e.reps[0]}</span>
                        ) : null}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      <style>{`
        .fp { border-bottom: 1px solid var(--color-border); padding: 1.4rem 0 1.2rem; }
        .fp-head { display: flex; align-items: baseline; gap: 1rem; margin-bottom: .7rem; }
        .fp-k { font-family: var(--font-mono); font-size: 9px; letter-spacing: .22em; text-transform: uppercase; color: var(--color-accent); }
        .fp-n { font-family: var(--font-mono); font-size: 9px; letter-spacing: .12em; text-transform: uppercase; color: var(--color-muted); }
        .fp-toggle { margin-left: auto; font-family: var(--font-mono); font-size: 9px; letter-spacing: .16em; text-transform: uppercase; padding: .35rem .8rem; border: 1px solid var(--color-accent); background: transparent; color: var(--color-accent); cursor: pointer; }
        .fp-toggle:hover { background: var(--color-accent); color: var(--color-ink); }
        .fp-empty { font-size: .84rem; color: var(--color-muted); max-width: 48em; line-height: 1.6; margin: 0; }
        .fp-chosen { display: flex; flex-wrap: wrap; gap: .35rem; }
        .fp-tag { display: inline-flex; align-items: baseline; gap: .5rem; padding: .3rem .55rem; border: 1px solid var(--color-accent); background: color-mix(in srgb, var(--color-accent) 10%, transparent); color: var(--color-paper); font-size: .78rem; cursor: pointer; }
        .fp-tag em { font-style: normal; font-family: var(--font-mono); font-size: 8px; color: var(--color-muted); }
        .fp-tag i { font-style: normal; color: var(--color-muted); font-size: 9px; }
        .fp-tag:hover { border-color: #e8503a; }
        .fp-tag:hover i { color: #e8503a; }

        .fp-cat { margin-top: 1.1rem; border: 1px solid var(--color-border); padding: .9rem 1rem; background: var(--color-card); }
        .fp-kinds { display: flex; flex-wrap: wrap; gap: .35rem; align-items: center; }
        .fp-kind { display: inline-flex; align-items: baseline; gap: .4rem; font-family: var(--font-mono); font-size: 9px; letter-spacing: .14em; text-transform: uppercase; padding: .35rem .7rem; border: 1px solid var(--color-border); background: transparent; color: var(--color-muted); cursor: pointer; }
        .fp-kind.is-on { color: var(--color-accent); border-color: var(--color-accent); }
        .fp-kind em { font-style: normal; font-size: 8px; opacity: .7; }
        .fp-search { margin-left: auto; background: transparent; border: 1px solid var(--color-border); color: var(--color-paper); padding: .3rem .5rem; font-size: .8rem; min-width: 10rem; }
        .fp-search:focus { outline: none; border-color: var(--color-accent); }
        .fp-blurb { font-size: .76rem; color: var(--color-muted); margin: .5rem 0 .8rem; }

        .fp-groups { display: grid; grid-template-columns: repeat(auto-fill, minmax(17rem, 1fr)); gap: 1rem; max-height: 26rem; overflow-y: auto; }
        .fp-group h4 { font-family: var(--font-mono); font-size: 8.5px; letter-spacing: .18em; text-transform: uppercase; color: var(--color-muted); margin: 0 0 .35rem; font-weight: 400; }
        .fp-group ul { list-style: none; margin: 0; padding: 0; display: grid; gap: 2px; }
        .fp-add { width: 100%; text-align: left; display: grid; gap: .1rem; padding: .35rem .45rem; border: 1px solid transparent; border-left: 1px solid var(--color-border); background: transparent; cursor: pointer; }
        .fp-add:hover { border-color: var(--color-accent); background: color-mix(in srgb, var(--color-accent) 7%, transparent); }
        .fp-add-l { font-size: .8rem; color: var(--color-paper); line-height: 1.25; }
        .fp-add-m { font-family: var(--font-mono); font-size: 8px; letter-spacing: .08em; text-transform: uppercase; color: var(--color-muted); }
        .fp-add-r { font-size: .72rem; color: var(--color-muted); font-style: italic; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
      `}</style>
    </section>
  );
}
