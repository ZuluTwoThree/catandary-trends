"use client";

import { useCallback, useEffect, useState } from "react";

/**
 * Naming the topics you care about — the first act of work, not a setting.
 *
 * Until 2026-08-07 this was a catalogue of 253 clusters, 21 mega-trends and 8
 * verticals. That asked the wrong question: a user knows *what* interests them
 * ("GLP-1", "dairy", "robotics") but not what our clustering decided to call
 * it. So the primary way in is now a search box over the whole curated signal
 * space, and the catalogue is the secondary path for people who would rather
 * browse.
 *
 * Every field carries its hit count and — where the shape of its history allows
 * it — a first maturity reading, so the choice is informed before a single
 * signal is rated.
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

type Search = {
  query: string;
  field_key: string;
  n: number;
  months: number;
  stage: string | null;
  stage_reason: string | null;
  preview: { id: number; title: string; source: string | null; date: string }[];
};

const STAGE_EN: Record<string, string> = {
  emerging: "Emerging",
  volatile: "Volatile",
  maturing: "Maturing",
  established: "Established",
};

const KINDS: { key: keyof Catalog; label: string; blurb: string }[] = [
  { key: "vertical", label: "Industries", blurb: "A whole sector's signal space." },
  { key: "mega", label: "Mega-trends", blurb: "One long-range movement, entire." },
  { key: "cluster", label: "Clusters", blurb: "A concrete field, grown from the signals." },
];

const EXAMPLES = ["GLP-1", "robotics", "dairy", "LLM", "precision fermentation"];

export default function FieldPicker({ onChange }: { onChange: () => void }) {
  const [cat, setCat] = useState<Catalog | null>(null);
  const [chosen, setChosen] = useState<Entry[]>([]);
  const [q, setQ] = useState("");
  const [found, setFound] = useState<Search | null>(null);
  const [searching, setSearching] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [browse, setBrowse] = useState(false);
  const [kind, setKind] = useState<keyof Catalog | null>(null);
  const [filter, setFilter] = useState("");

  const load = useCallback(async () => {
    const r = await fetch("/api/foresight/instrument?what=catalog");
    const d = await r.json();
    if (d?.error) return;
    setCat(d.catalog);
    const all = [...d.catalog.vertical, ...d.catalog.mega, ...d.catalog.cluster];
    setChosen(all.filter((e: Entry) => e.chosen));
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function runSearch(term: string) {
    const t = term.trim();
    if (t.length < 2) return;
    setSearching(true);
    setFound(null);
    const r = await fetch(
      `/api/foresight/instrument?what=search&q=${encodeURIComponent(t)}`
    );
    const d = await r.json();
    setSearching(false);
    if (!d?.error) setFound(d);
  }

  async function add(key: string, label: string) {
    setBusy(key);
    await fetch("/api/foresight/instrument", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ add: key, label }),
    });
    setBusy(null);
    setFound(null);
    setQ("");
    await load();
    onChange();
  }

  async function remove(key: string) {
    setBusy(key);
    await fetch("/api/foresight/instrument", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ remove: key }),
    });
    setBusy(null);
    await load();
    onChange();
  }

  const browseList =
    cat && kind
      ? cat[kind].filter(
          (e) =>
            !e.chosen &&
            (!filter ||
              e.label.toLowerCase().includes(filter.toLowerCase()) ||
              e.group.toLowerCase().includes(filter.toLowerCase()))
        )
      : [];
  const grouped = new Map<string, Entry[]>();
  for (const e of browseList) {
    grouped.set(e.group, [...(grouped.get(e.group) ?? []), e]);
  }

  return (
    <section className="fp" aria-label="Your topics">
      <div className="fp-head">
        <span className="fp-k">Your topics</span>
        <span className="fp-n">
          {chosen.length ? `${chosen.length} on the table` : "none chosen yet"}
        </span>
        <button className="fp-toggle" onClick={() => setBrowse(!browse)}>
          {browse ? "close catalogue" : "browse instead"}
        </button>
      </div>

      {/* Primary way in: name the topic */}
      <form
        className="fp-searchbar"
        onSubmit={(e) => {
          e.preventDefault();
          void runSearch(q);
        }}
      >
        <input
          className="fp-input"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Name a topic you follow — GLP-1, robotics, dairy, LLM…"
          maxLength={80}
          aria-label="Search the signal space"
        />
        <button className="fp-go" type="submit" disabled={q.trim().length < 2}>
          {searching ? "searching…" : "search"}
        </button>
      </form>

      {!found && !searching ? (
        <p className="fp-hint">
          Searches the whole curated signal space — 1.13 million signals across
          every source. Try{" "}
          {EXAMPLES.map((x, i) => (
            <span key={x}>
              <button
                className="fp-eg"
                onClick={() => {
                  setQ(x);
                  void runSearch(x);
                }}
              >
                {x}
              </button>
              {i < EXAMPLES.length - 1 ? " · " : ""}
            </span>
          ))}
        </p>
      ) : null}

      {found ? (
        <div className="fp-found">
          <div className="fp-found-head">
            <h3>
              “{found.query}” — {found.n.toLocaleString("en-US")} signals
            </h3>
            {found.stage ? (
              <span className="fp-stage">
                first reading: {STAGE_EN[found.stage]}
              </span>
            ) : (
              <span className="fp-stage fp-stage-none">
                no clear shape yet — will default to Volatile
              </span>
            )}
            <button
              className="fp-take"
              disabled={found.n < 10 || busy === found.field_key}
              onClick={() => void add(found.field_key, found.query)}
            >
              rate these signals →
            </button>
          </div>
          {found.stage_reason ? (
            <p className="fp-reason">{found.stage_reason}</p>
          ) : null}
          <ul className="fp-preview">
            {found.preview.map((p) => (
              <li key={p.id}>
                <span>{p.date}</span>
                {p.title}
              </li>
            ))}
          </ul>
          {found.n < 10 ? (
            <p className="fp-reason">
              Too few signals to rate meaningfully. Try a broader word.
            </p>
          ) : null}
        </div>
      ) : null}

      {chosen.length ? (
        <div className="fp-chosen">
          {chosen.map((e) => (
            <button
              key={e.field_key}
              className="fp-tag"
              onClick={() => void remove(e.field_key)}
              disabled={busy === e.field_key}
              title="Take off the table"
            >
              <span>{e.label}</span>
              <em>{e.n.toLocaleString("en-US")}</em>
              <i aria-hidden="true">✕</i>
            </button>
          ))}
        </div>
      ) : null}

      {browse && cat ? (
        <div className="fp-cat">
          {!kind ? (
            <div className="fp-ask">
              <p className="fp-ask-q">Which altitude do you want to browse?</p>
              <div className="fp-ask-opts">
                {KINDS.map((k) => (
                  <button
                    key={k.key}
                    className="fp-ask-o"
                    onClick={() => setKind(k.key)}
                  >
                    <span className="fp-ask-l">{k.label}</span>
                    <span className="fp-ask-n">
                      {cat[k.key].filter((e) => !e.chosen).length} to choose from
                    </span>
                    <span className="fp-ask-b">{k.blurb}</span>
                  </button>
                ))}
              </div>
              <p className="fp-ask-note">
                They answer different questions and mix freely — but should not
                be confused: a radar of concrete technologies is no basis for a
                strategy discussion, and a whole industry is none for picking a
                technology.
              </p>
            </div>
          ) : (
            <>
              <div className="fp-kinds">
                <button
                  className="fp-kind"
                  onClick={() => {
                    setKind(null);
                    setFilter("");
                  }}
                >
                  ← altitude
                </button>
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
                  value={filter}
                  onChange={(e) => setFilter(e.target.value)}
                  placeholder="filter…"
                  aria-label="Filter catalogue"
                />
              </div>
              <div className="fp-groups">
                {[...grouped.entries()].slice(0, 40).map(([g, entries]) => (
                  <div key={g} className="fp-group">
                    <h4>{g}</h4>
                    <ul>
                      {entries.slice(0, 12).map((e) => (
                        <li key={e.field_key}>
                          <button
                            className="fp-add"
                            onClick={() => void add(e.field_key, e.label)}
                            disabled={busy === e.field_key}
                          >
                            <span className="fp-add-l">{e.label}</span>
                            <span className="fp-add-m">
                              {e.n.toLocaleString("en-US")} signals
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
                          </button>
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      ) : null}

      <style>{`
        .fp { border-bottom: 1px solid var(--color-border); padding: 1.4rem 0 1.2rem; }
        .fp-head { display: flex; align-items: baseline; gap: 1rem; margin-bottom: .8rem; }
        .fp-k { font-family: var(--font-mono); font-size: 9px; letter-spacing: .22em; text-transform: uppercase; color: var(--color-accent); }
        .fp-n { font-family: var(--font-mono); font-size: 9px; letter-spacing: .12em; text-transform: uppercase; color: var(--color-muted); }
        .fp-toggle { margin-left: auto; font-family: var(--font-mono); font-size: 9px; letter-spacing: .16em; text-transform: uppercase; padding: .3rem .7rem; border: 1px solid var(--color-border); background: transparent; color: var(--color-muted); cursor: pointer; }
        .fp-toggle:hover { color: var(--color-paper); border-color: var(--color-paper); }

        .fp-searchbar { display: flex; gap: .4rem; }
        .fp-input { flex: 1; min-width: 0; background: transparent; border: 1px solid var(--color-border); border-bottom-width: 2px; color: var(--color-paper); padding: .7rem .85rem; font-size: 1rem; font-family: var(--font-sans); }
        .fp-input:focus { outline: none; border-color: var(--color-accent); }
        .fp-input::placeholder { color: var(--color-muted); }
        .fp-go { font-family: var(--font-mono); font-size: 9.5px; letter-spacing: .18em; text-transform: uppercase; padding: 0 1.3rem; border: 1px solid var(--color-accent); background: var(--color-accent); color: var(--color-ink); font-weight: 600; cursor: pointer; }
        .fp-go:disabled { opacity: .35; cursor: not-allowed; }
        .fp-hint { font-size: .8rem; color: var(--color-muted); margin: .6rem 0 0; line-height: 1.6; }
        .fp-eg { background: none; border: none; border-bottom: 1px dashed var(--color-accent); color: var(--color-accent); cursor: pointer; padding: 0; font: inherit; }

        .fp-found { margin-top: 1rem; border: 1px solid var(--color-border); border-left: 2px solid var(--color-accent); padding: .8rem 1rem; }
        .fp-found-head { display: flex; flex-wrap: wrap; align-items: baseline; gap: .9rem; }
        .fp-found-head h3 { margin: 0; font-size: 1rem; font-weight: 400; color: var(--color-paper); }
        .fp-stage { font-family: var(--font-mono); font-size: 9px; letter-spacing: .14em; text-transform: uppercase; color: var(--color-accent); }
        .fp-stage-none { color: #e8503a; }
        .fp-take { margin-left: auto; font-family: var(--font-mono); font-size: 9.5px; letter-spacing: .16em; text-transform: uppercase; padding: .4rem .9rem; border: 1px solid var(--color-accent); background: transparent; color: var(--color-accent); cursor: pointer; }
        .fp-take:hover:not(:disabled) { background: var(--color-accent); color: var(--color-ink); }
        .fp-take:disabled { opacity: .35; cursor: not-allowed; }
        .fp-reason { font-size: .76rem; color: var(--color-muted); margin: .5rem 0 0; line-height: 1.5; max-width: 56em; }
        .fp-preview { list-style: none; margin: .6rem 0 0; padding: 0; display: grid; gap: .18rem; }
        .fp-preview li { display: grid; grid-template-columns: 6rem 1fr; gap: .6rem; font-size: .78rem; color: var(--color-text); line-height: 1.35; }
        .fp-preview span { font-family: var(--font-mono); font-size: 8.5px; letter-spacing: .06em; color: var(--color-muted); }

        .fp-chosen { display: flex; flex-wrap: wrap; gap: .35rem; margin-top: 1rem; }
        .fp-tag { display: inline-flex; align-items: baseline; gap: .5rem; padding: .3rem .55rem; border: 1px solid var(--color-accent); background: color-mix(in srgb, var(--color-accent) 10%, transparent); color: var(--color-paper); font-size: .78rem; cursor: pointer; }
        .fp-tag em { font-style: normal; font-family: var(--font-mono); font-size: 8px; color: var(--color-muted); }
        .fp-tag i { font-style: normal; color: var(--color-muted); font-size: 9px; }
        .fp-tag:hover { border-color: #e8503a; }
        .fp-tag:hover i { color: #e8503a; }

        .fp-cat { margin-top: 1.1rem; border: 1px solid var(--color-border); padding: .9rem 1rem; background: var(--color-card); }
        .fp-ask-q { font-size: 1rem; color: var(--color-paper); margin: 0 0 .8rem; }
        .fp-ask-opts { display: grid; grid-template-columns: repeat(auto-fit, minmax(13rem, 1fr)); gap: .5rem; }
        .fp-ask-o { display: grid; gap: .25rem; text-align: left; padding: .85rem 1rem; border: 1px solid var(--color-border); background: transparent; cursor: pointer; transition: border-color .16s, transform .16s; }
        .fp-ask-o:hover { border-color: var(--color-accent); transform: translateY(-2px); }
        .fp-ask-l { font-size: .92rem; color: var(--color-paper); }
        .fp-ask-n { font-family: var(--font-mono); font-size: 8.5px; letter-spacing: .14em; text-transform: uppercase; color: var(--color-accent); }
        .fp-ask-b { font-size: .76rem; color: var(--color-muted); line-height: 1.45; }
        .fp-ask-note { font-size: .74rem; color: var(--color-muted); margin: .9rem 0 0; max-width: 52em; line-height: 1.55; }
        .fp-kinds { display: flex; flex-wrap: wrap; gap: .35rem; align-items: center; }
        .fp-kind { display: inline-flex; align-items: baseline; gap: .4rem; font-family: var(--font-mono); font-size: 9px; letter-spacing: .14em; text-transform: uppercase; padding: .35rem .7rem; border: 1px solid var(--color-border); background: transparent; color: var(--color-muted); cursor: pointer; }
        .fp-kind.is-on { color: var(--color-accent); border-color: var(--color-accent); }
        .fp-kind em { font-style: normal; font-size: 8px; opacity: .7; }
        .fp-search { margin-left: auto; background: transparent; border: 1px solid var(--color-border); color: var(--color-paper); padding: .3rem .5rem; font-size: .8rem; min-width: 10rem; }
        .fp-search:focus { outline: none; border-color: var(--color-accent); }
        .fp-groups { display: grid; grid-template-columns: repeat(auto-fill, minmax(17rem, 1fr)); gap: 1rem; max-height: 24rem; overflow-y: auto; margin-top: .8rem; }
        .fp-group h4 { font-family: var(--font-mono); font-size: 8.5px; letter-spacing: .18em; text-transform: uppercase; color: var(--color-muted); margin: 0 0 .35rem; font-weight: 400; }
        .fp-group ul { list-style: none; margin: 0; padding: 0; display: grid; gap: 2px; }
        .fp-add { width: 100%; text-align: left; display: grid; gap: .1rem; padding: .35rem .45rem; border: 1px solid transparent; border-left: 1px solid var(--color-border); background: transparent; cursor: pointer; }
        .fp-add:hover { border-color: var(--color-accent); background: color-mix(in srgb, var(--color-accent) 7%, transparent); }
        .fp-add-l { font-size: .8rem; color: var(--color-paper); line-height: 1.25; }
        .fp-add-m { font-family: var(--font-mono); font-size: 8px; letter-spacing: .08em; text-transform: uppercase; color: var(--color-muted); }
      `}</style>
    </section>
  );
}
