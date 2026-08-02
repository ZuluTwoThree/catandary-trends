import Link from "next/link";
import type { RadarConfigMeta } from "@/lib/radar-shared";

/**
 * Der Selektor über den Radaren.
 *
 * Eine flache Reiterleiste trug drei Radare. Sie trägt keine dreißig: seit die
 * Radare aus den Trendclustern kommen, gibt es eine je Vertikale UND eine je
 * Mega-Trend. Ohne Gruppierung wäre die Leiste eine Wortwolke.
 *
 * Die zwei Familien sind keine Kosmetik, sondern zwei Leserichtungen. Ein
 * Vertikalen-Radar fragt „was passiert in meiner Branche?"; ein
 * Mega-Trend-Radar fragt „woraus besteht diese große Bewegung, und wie reif ist
 * jeder Teil?". Dieselbe Engine, zwei Schnitte durch denselben Signalraum.
 */

const FAMILY: { key: string; title: string; blurb: string }[] = [
  {
    key: "vertical",
    title: "By industry",
    blurb: "The clusters of one vertical's signal space — what is moving in a sector.",
  },
  {
    key: "mega",
    title: "By mega-trend",
    blurb: "What a long-range movement is actually made of, and how far each part has come.",
  },
  {
    key: "other",
    title: "Cross-industry",
    blurb: "The whole corpus at once.",
  },
];

function family(slug: string): string {
  if (slug.startsWith("cl-mega-")) return "mega";
  if (slug.startsWith("cl-vertical-")) return "vertical";
  return "other";
}

/** „cl-mega-clean-energy-transition" → „Clean Energy Transition" */
function pretty(r: RadarConfigMeta): string {
  return r.name.replace(/\s*·\s*Trend clusters$/i, "");
}

export default function RadarSelector({
  radars,
  current,
}: {
  radars: RadarConfigMeta[];
  current: string;
}) {
  const groups = FAMILY.map((f) => ({
    ...f,
    items: radars.filter((r) => family(r.slug) === f.key),
  })).filter((g) => g.items.length);

  return (
    <nav className="rsel" aria-label="Radar">
      {groups.map((g) => (
        <section key={g.key} className="rsel-g">
          <div className="rsel-head">
            <h2 className="rsel-t">{g.title}</h2>
            <p className="rsel-b">{g.blurb}</p>
          </div>
          <div className="rsel-items">
            {g.items.map((r) => (
              <Link
                key={r.slug}
                href={`/trends/foresight/radar?radar=${r.slug}`}
                className={`rsel-i ${r.slug === current ? "is-on" : ""}`}
                aria-current={r.slug === current ? "page" : undefined}
              >
                {pretty(r)}
              </Link>
            ))}
          </div>
        </section>
      ))}

      <style>{`
        .rsel { display: grid; gap: 1.1rem; margin-bottom: 1.8rem; }
        .rsel-head { display: flex; flex-wrap: wrap; align-items: baseline; gap: .7rem; margin-bottom: .5rem; }
        .rsel-t { font-family: var(--font-mono); font-size: 9px; letter-spacing: .22em; text-transform: uppercase; color: var(--color-accent); margin: 0; font-weight: 400; }
        .rsel-b { font-size: .78rem; color: var(--color-muted); margin: 0; }
        .rsel-items { display: flex; flex-wrap: wrap; gap: .3rem; }
        .rsel-i { font-family: var(--font-mono); font-size: 9.5px; letter-spacing: .12em; text-transform: uppercase; padding: .4rem .7rem; border: 1px solid var(--color-border); color: var(--color-muted); text-decoration: none; transition: color .18s, border-color .18s; }
        .rsel-i:hover { color: var(--color-paper); border-color: var(--color-paper); }
        .rsel-i.is-on { color: var(--color-accent); border-color: var(--color-accent); background: color-mix(in srgb, var(--color-accent) 8%, transparent); }
      `}</style>
    </nav>
  );
}
