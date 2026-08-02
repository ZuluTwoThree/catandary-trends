"use client";

import type { ScopeMeta } from "@/lib/radar-shared";

/**
 * Was ein Feld IST — vor jeder Aussage darüber, wo es steht.
 *
 * Der Grund für dieses Bauteil steht in der Nutzerkritik am Query-Radar: „die
 * Platzierung der Punkte ist nicht intuitiv eindeutig nachvollziehbar durch die
 * genannten Beispiele". Eine Freitext-Query sammelt Signale ein, die der Leser
 * nie zu Gesicht bekommt; die fünf Belege in einer Zelle sind die Auslöser eines
 * Gates, nicht eine Beschreibung des Felds.
 *
 * Ein Cluster kann das beantworten. Seine fünf zentralsten Signale SIND seine
 * Definition — sie liegen dem Schwerpunkt am nächsten, und wer sie liest, weiß
 * sofort, worüber das Radar gleich eine Aussage macht.
 *
 * Dazu der Anteilstrend: steigt oder fällt der Anteil dieses Clusters am
 * Signalaufkommen. Das ist die Richtungsachse — gemessen an unserem eigenen
 * Korpus, nicht als Marktprognose behauptet.
 */

const MOMENTUM: Record<string, { label: string; arrow: string; tone: string }> = {
  rising: { label: "gaining share", arrow: "↑", tone: "up" },
  declining: { label: "losing share", arrow: "↓", tone: "down" },
  stable: { label: "holding share", arrow: "→", tone: "flat" },
  unknown: { label: "too short a series", arrow: "·", tone: "flat" },
};

export default function FieldIdentity({ meta }: { meta: ScopeMeta }) {
  const m = MOMENTUM[meta.momentum ?? "unknown"] ?? MOMENTUM.unknown;
  const delta = meta.sov_delta_pp;

  return (
    <section className="fi" aria-label="What this field is">
      <div className="fi-bar">
        <span className="fi-k">Cluster</span>
        {meta.size ? (
          <span className="fi-v">{meta.size.toLocaleString("en-US")} signals</span>
        ) : null}
        {meta.cohesion ? (
          <span className="fi-v" title="Mean cosine of members to the cluster centre — how tightly the field holds together">
            cohesion {meta.cohesion.toFixed(2)}
          </span>
        ) : null}
        {meta.composition ? (
          <span
            className="fi-v"
            title="What the cluster is made of — a product stream reads differently from a research stream"
          >
            {Math.round((meta.composition.applied ?? 0) * 100)}% applied ·{" "}
            {Math.round((meta.composition.research ?? 0) * 100)}% research
          </span>
        ) : null}
        <span className={`fi-mom is-${m.tone}`}>
          {m.arrow} {m.label}
          {typeof delta === "number" && meta.momentum !== "unknown"
            ? ` ${delta > 0 ? "+" : ""}${delta.toFixed(1)} pp`
            : ""}
        </span>
      </div>

      {meta.rep_titles?.length ? (
        <div className="fi-reps">
          <p className="fi-lead">
            The five signals closest to this cluster&rsquo;s centre — they define
            the field, before anything is claimed about it:
          </p>
          <ul>
            {meta.rep_titles.slice(0, 5).map((t, i) => (
              <li key={i}>{t}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {meta.top_tags?.length ? (
        <p className="fi-tags">
          {meta.top_tags.slice(0, 8).map((t) => (
            <span key={t} className="fi-tag">
              {t}
            </span>
          ))}
        </p>
      ) : null}

      <style>{`
        .fi { border: 1px solid var(--color-border); padding: .85rem 1rem; margin-bottom: 1rem; }
        .fi-bar { display: flex; flex-wrap: wrap; align-items: baseline; gap: .8rem; margin-bottom: .7rem; }
        .fi-k { font-family: var(--font-mono); font-size: 9px; letter-spacing: .2em; text-transform: uppercase; color: var(--color-accent); }
        .fi-v { font-family: var(--font-mono); font-size: 9px; letter-spacing: .12em; text-transform: uppercase; color: var(--color-muted); }
        .fi-mom { margin-left: auto; font-family: var(--font-mono); font-size: 9.5px; letter-spacing: .12em; text-transform: uppercase; }
        .fi-mom.is-up { color: var(--color-accent); }
        .fi-mom.is-down { color: #ff7a59; }
        .fi-mom.is-flat { color: var(--color-muted); }
        .fi-lead { font-size: .78rem; color: var(--color-muted); margin: 0 0 .4rem; }
        .fi-reps ul { margin: 0; padding-left: 1rem; display: grid; gap: .22rem; }
        .fi-reps li { font-size: .82rem; line-height: 1.45; color: var(--color-text); }
        .fi-tags { margin: .7rem 0 0; display: flex; flex-wrap: wrap; gap: .3rem; }
        .fi-tag { font-family: var(--font-mono); font-size: 8.5px; letter-spacing: .1em; text-transform: uppercase; color: var(--color-muted); border: 1px solid var(--color-border); padding: .15rem .35rem; }
      `}</style>
    </section>
  );
}
