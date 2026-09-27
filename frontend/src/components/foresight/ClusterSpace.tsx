"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ACCEL_TICKS,
  AGE_TICKS,
  NEIGHBOUR_K,
  SHARE_TICKS,
  TRAIL,
  accelZ,
  ageX,
  nestSeries,
  place,
  shareY,
  type SeriesPoint,
  type SpaceMode,
  type Vec3,
} from "@/lib/clusterMap";
import type { TierName } from "@/lib/emerging";

/**
 * The signal space, drawn in three dimensions and walked month by month.
 *
 * Two views of the same pockets, because they answer different questions:
 *
 *   MAP    — where a pocket sits in the embedding space. Positions are fixed,
 *            the sizes breathe over the months, so attention moves across a
 *            stable landscape. The axes carry no unit and are not labelled;
 *            what the projection cost is printed above the picture instead.
 *   AXES   — how old a pocket is, how loud it is per 10,000 signals of the same
 *            month, and whether that share is rising. Here the pocket MOVES, so
 *            a month step is a step along its trajectory.
 *
 * No 3D library: at 55-94 points the whole renderer is a rotation matrix, a
 * perspective divide and a depth sort, and every trail is one <path> rather than
 * twelve segments — which keeps the drag and the auto-spin smooth without
 * pulling WebGL (and 150 KB of it) into a page that owns 250 SVG nodes.
 */

export interface SpaceNestView {
  id: number;
  name: string;
  sub: string | null;
  tier: TierName | null;
  /** Index into `months` of the first datable month, null when undatable. */
  firstIndex: number | null;
  /** Lookalikes per month, same length as `months`. */
  hits: number[];
  size: number;
  cohesion: number;
  nSources: number;
  topSource: string | null;
  topSourceShare: number;
  taggedShare: number;
  establishedShare: number;
  firstMonth: string | null;
  ageMonths: number | null;
  noveltyLift: number | null;
  reps: { title: string; url: string | null; source: string | null; date: string | null }[];
}

interface Props {
  months: string[];
  totals: number[];
  nests: SpaceNestView[];
  /** Normalised map coordinates, aligned with `nests`. */
  coords: Vec3[];
  /** Leading months that exist only to fill the trailing windows. */
  warmup: number;
  projection: { shepard: number; varShare: number; neighbourKeep: number };
}

const TIER_COLOR: Record<TierName, string> = {
  science: "#a78bfa",
  patent: "#60a5fa",
  funding: "#f0a13a",
  market: "#d4ff3a",
};
const NO_TIER = "#8a8d82";

const W = 900;
const H = 600;
const CX = W / 2;
const CY = H / 2 + 10;
const FOCAL = 3.4;
const MONTHS_PER_SEC = 5;

function tierColor(t: TierName | null): string {
  return t ? TIER_COLOR[t] : NO_TIER;
}

/** Yaw around the vertical axis, then pitch — enough for a cloud, and cheap. */
function rotate(p: Vec3, yaw: number, pitch: number): Vec3 {
  const [x, y, z] = p;
  const cy = Math.cos(yaw);
  const sy = Math.sin(yaw);
  const x1 = x * cy + z * sy;
  const z1 = -x * sy + z * cy;
  const cp = Math.cos(pitch);
  const sp = Math.sin(pitch);
  return [x1, y * cp - z1 * sp, y * sp + z1 * cp];
}

interface Screen {
  sx: number;
  sy: number;
  depth: number;
  scale: number;
}

function toScreen(p: Vec3, yaw: number, pitch: number, radius: number): Screen {
  const [x, y, z] = rotate(p, yaw, pitch);
  const scale = FOCAL / (FOCAL + z);
  return { sx: CX + x * radius * scale, sy: CY - y * radius * scale, depth: z, scale };
}

const CUBE_EDGES: [Vec3, Vec3][] = (() => {
  const c: Vec3[] = [];
  for (const x of [-1, 1]) for (const y of [-1, 1]) for (const z of [-1, 1]) c.push([x, y, z]);
  const e: [Vec3, Vec3][] = [];
  for (let i = 0; i < c.length; i++) {
    for (let j = i + 1; j < c.length; j++) {
      let same = 0;
      for (let k = 0; k < 3; k++) if (c[i][k] === c[j][k]) same++;
      if (same === 2) e.push([c[i], c[j]]);
    }
  }
  return e;
})();

function fmtMonth(m: string): string {
  const [y, mm] = m.split("-");
  const names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return `${names[Number(mm) - 1] ?? mm} ${y}`;
}

function fmtShare(v: number): string {
  if (v >= 100) return v.toFixed(0);
  if (v >= 10) return v.toFixed(1);
  return v.toFixed(2);
}

function fmtRatio(v: number | null): string {
  if (v == null) return "no basis";
  if (v >= 1) return `×${v >= 10 ? v.toFixed(0) : v.toFixed(2)}`;
  return `×${v.toFixed(2)}`;
}

export default function ClusterSpace({
  months,
  totals,
  nests,
  coords,
  warmup,
  projection,
}: Props) {
  const [mode, setMode] = useState<SpaceMode>("axes");
  const [idx, setIdx] = useState(months.length - 1);
  const [playing, setPlaying] = useState(false);
  const [spin, setSpin] = useState(true);
  const [trails, setTrails] = useState(true);
  const [yaw, setYaw] = useState(0.6);
  const [pitch, setPitch] = useState(0.35);
  const [zoom, setZoom] = useState(1);
  const [selected, setSelected] = useState<number | null>(null);
  const [hover, setHover] = useState<number | null>(null);
  const drag = useRef<{ x: number; y: number } | null>(null);

  const series = useMemo<SeriesPoint[][]>(
    () => nests.map((n) => nestSeries(n.hits, totals, n.firstIndex)),
    [nests, totals]
  );

  // One size scale for the whole animation. A per-frame maximum would make
  // every month look equally busy, which is the opposite of the point.
  const maxShare = useMemo(() => {
    let m = 0;
    for (const s of series) for (let j = warmup; j < s.length; j++) m = Math.max(m, s[j].share);
    return m || 1;
  }, [series, warmup]);

  const radius = 200 * zoom;

  useEffect(() => {
    if (!playing) return;
    let raf = 0;
    let last = performance.now();
    const step = (t: number) => {
      const dt = (t - last) / 1000;
      if (dt >= 1 / MONTHS_PER_SEC) {
        last = t;
        setIdx((i) => (i >= months.length - 1 ? warmup : i + 1));
      }
      raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [playing, months.length, warmup]);

  useEffect(() => {
    if (!spin) return;
    let raf = 0;
    let last = performance.now();
    const step = (t: number) => {
      const dt = (t - last) / 1000;
      last = t;
      setYaw((y) => y + dt * 0.18);
      raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [spin]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA")) return;
      if (e.key === "ArrowRight") setIdx((i) => Math.min(months.length - 1, i + 1));
      else if (e.key === "ArrowLeft") setIdx((i) => Math.max(warmup, i - 1));
      else return;
      e.preventDefault();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [months.length, warmup]);

  const onPointerDown = useCallback((e: React.PointerEvent<SVGSVGElement>) => {
    drag.current = { x: e.clientX, y: e.clientY };
    setSpin(false);
    e.currentTarget.setPointerCapture(e.pointerId);
  }, []);

  const onPointerMove = useCallback((e: React.PointerEvent<SVGSVGElement>) => {
    const d = drag.current;
    if (!d) return;
    setYaw((y) => y + (e.clientX - d.x) * 0.008);
    setPitch((p) => Math.max(-1.2, Math.min(1.2, p + (e.clientY - d.y) * 0.006)));
    drag.current = { x: e.clientX, y: e.clientY };
  }, []);

  const onPointerUp = useCallback(() => {
    drag.current = null;
  }, []);

  // ---- what is on screen in this month
  const placed = useMemo(() => {
    const out = nests
      .map((n, i) => {
        const p = place(mode, idx, series[i], coords[i], n.id);
        if (!p) return null;
        const scr = toScreen(p.pos, yaw, pitch, radius);
        return { nest: n, point: p, scr, color: tierColor(n.tier), i };
      })
      .filter((x): x is NonNullable<typeof x> => x !== null);
    // far first, so the near pockets end up on top and take the mouse
    return out.sort((a, b) => b.scr.depth - a.scr.depth);
  }, [nests, mode, idx, series, coords, yaw, pitch, radius]);

  const trailPaths = useMemo(() => {
    if (!trails || mode !== "axes") return new Map<number, string>();
    const out = new Map<number, string>();
    nests.forEach((n, i) => {
      // Months in which the pocket was silent sit on the axis floor; joining
      // them would draw a line right across the cube that says nothing. The
      // path breaks instead, so a trail only ever shows movement that happened.
      let d = "";
      let open = false;
      let drawn = 0;
      for (let j = Math.max(warmup, idx - TRAIL); j <= idx; j++) {
        const p = place(mode, j, series[i], coords[i], n.id);
        if (!p || p.share <= 0) {
          open = false;
          continue;
        }
        const s = toScreen(p.pos, yaw, pitch, radius);
        d += `${open ? "L" : "M"}${s.sx.toFixed(1)},${s.sy.toFixed(1)}`;
        open = true;
        drawn++;
      }
      if (drawn > 1) out.set(n.id, d);
    });
    return out;
  }, [trails, mode, nests, idx, series, coords, yaw, pitch, radius, warmup]);

  const cube = useMemo(
    () =>
      CUBE_EDGES.map(([a, b]) => {
        const sa = toScreen(a, yaw, pitch, radius);
        const sb = toScreen(b, yaw, pitch, radius);
        return { x1: sa.sx, y1: sa.sy, x2: sb.sx, y2: sb.sy };
      }),
    [yaw, pitch, radius]
  );

  // Ticks sit on the three edges meeting at the (-1,-1,-1) corner.
  const ticks = useMemo(() => {
    if (mode !== "axes") return [];
    const out: { sx: number; sy: number; label: string; axis: number; title?: boolean }[] = [];
    const add = (pos: Vec3, label: string, axis: number, title = false) => {
      const s = toScreen(pos, yaw, pitch, radius);
      out.push({ sx: s.sx, sy: s.sy, label, axis, title });
    };
    // Age runs along the bottom-front edge, growth along the bottom-left one.
    // They share a corner, so their labels are offset in different directions.
    for (const m of AGE_TICKS) add([ageX(m), -1, -1], m === 0 ? "new" : `${m / 12}y`, 0);
    for (const v of SHARE_TICKS) add([-1, shareY(v), -1], fmtShare(v), 1);
    // Growth sits on the FAR bottom edge, not on the one next to age: the two
    // edges that share the front corner project almost collinear at most
    // viewing angles, and the two tick rows then interleave into mush.
    for (const v of ACCEL_TICKS) add([1, -1, accelZ(v)], v === 1 ? "flat" : `×${v}`, 2);
    add([1.18, -1, -1], "older →", 0, true);
    add([-1, 1.12, -1], "↑ share /10k", 1, true);
    add([1, -1, 1.18], "growth →", 2, true);
    return out;
  }, [mode, yaw, pitch, radius]);

  const active = selected ?? hover;
  const activeNest = nests.find((n) => n.id === active) ?? null;
  const activeSeries = activeNest ? series[nests.indexOf(activeNest)][idx] : null;

  // Names only for the loudest few, and only where they do not land on top of
  // a name already placed — six overlapping labels read as none.
  const labelled = useMemo(() => {
    const ids = new Set<number>();
    const taken: { sx: number; sy: number }[] = [];
    for (const p of [...placed].sort((a, b) => b.point.share - a.point.share)) {
      if (ids.size >= 7) break;
      // Compare where the LABEL lands, not where the dot is, and reserve the
      // width a 34-character name actually takes at 10px mono.
      const ly = p.scr.sy - 6 - 17 * Math.sqrt(Math.min(p.point.share / maxShare, 1)) * p.scr.scale;
      if (taken.some((t) => Math.abs(t.sx - p.scr.sx) < 150 && Math.abs(t.sy - ly) < 26)) continue;
      taken.push({ sx: p.scr.sx, sy: ly });
      ids.add(p.nest.id);
    }
    if (active != null) ids.add(active);
    return ids;
  }, [placed, active, maxShare]);

  const month = months[idx] ?? "";
  const datable = placed.length;

  const btn = (on: boolean) =>
    `font-mono text-[10px] uppercase tracking-[0.14em] px-3 py-1.5 border transition-colors ${
      on ? "text-accent border-accent bg-accent/10" : "text-muted border-border hover:text-paper"
    }`;

  return (
    <div>
      {/* controls */}
      <div className="flex flex-wrap items-center gap-2 mb-3">
        <button type="button" className={btn(mode === "axes")} onClick={() => setMode("axes")}>
          Measured axes
        </button>
        <button type="button" className={btn(mode === "map")} onClick={() => setMode("map")}>
          Map
        </button>
        <span className="w-4" />
        <button type="button" className={btn(playing)} onClick={() => setPlaying((p) => !p)}>
          {playing ? "Pause" : "Play"}
        </button>
        <button type="button" className={btn(spin)} onClick={() => setSpin((s) => !s)}>
          Spin
        </button>
        {mode === "axes" && (
          <button type="button" className={btn(trails)} onClick={() => setTrails((t) => !t)}>
            Trails
          </button>
        )}
        <button
          type="button"
          className={btn(false)}
          onClick={() => {
            setYaw(0.6);
            setPitch(0.35);
            setZoom(1);
          }}
        >
          Reset view
        </button>
        <button type="button" className={btn(false)} onClick={() => setZoom((z) => Math.min(2, z * 1.2))}>
          +
        </button>
        <button type="button" className={btn(false)} onClick={() => setZoom((z) => Math.max(0.5, z / 1.2))}>
          −
        </button>
      </div>

      <div className="flex items-center gap-3 mb-4">
        <input
          type="range"
          min={warmup}
          max={months.length - 1}
          value={idx}
          onChange={(e) => {
            setPlaying(false);
            setIdx(Number(e.target.value));
          }}
          className="flex-1 accent-accent"
          aria-label="month"
        />
        <span className="font-mono text-xs text-paper w-28 text-right">{fmtMonth(month)}</span>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_320px] gap-4">
        <div className="border border-border bg-ink/40">
          <svg
            viewBox={`0 0 ${W} ${H}`}
            className="w-full h-auto touch-none select-none cursor-grab"
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={onPointerUp}
            onPointerCancel={onPointerUp}
          >
            {mode === "axes" &&
              cube.map((e, i) => (
                <line
                  key={i}
                  x1={e.x1}
                  y1={e.y1}
                  x2={e.x2}
                  y2={e.y2}
                  stroke="#2a2d28"
                  strokeWidth={1}
                />
              ))}
            {ticks.map((t, i) => (
              <text
                key={i}
                x={t.sx}
                y={t.sy}
                dx={t.axis === 1 ? -8 : t.axis === 2 ? 8 : 0}
                dy={t.axis === 1 ? 3 : t.axis === 2 ? -4 : 14}
                textAnchor={t.axis === 1 ? "end" : t.axis === 2 ? "start" : "middle"}
                className="font-mono"
                fontSize={t.title ? 10 : 9}
                fill={t.title ? "#c8cabf" : "#8a8d82"}
              >
                {t.label}
              </text>
            ))}
            {[...trailPaths].map(([id, d]) => (
              <path
                key={id}
                d={d}
                fill="none"
                stroke={tierColor(nests.find((n) => n.id === id)?.tier ?? null)}
                strokeWidth={id === active ? 2 : 1}
                opacity={id === active ? 0.85 : 0.13}
              />
            ))}
            {placed.map((p) => {
              const r = 3 + 17 * Math.sqrt(Math.min(p.point.share / maxShare, 1));
              const isActive = p.nest.id === active;
              return (
                <circle
                  key={p.nest.id}
                  cx={p.scr.sx}
                  cy={p.scr.sy}
                  r={Math.max(2, r * p.scr.scale)}
                  fill={p.color}
                  fillOpacity={isActive ? 0.95 : 0.34 + 0.3 * (p.scr.scale - 0.7)}
                  stroke={isActive ? "#f4f4ee" : p.color}
                  strokeWidth={isActive ? 1.5 : 0.6}
                  onMouseEnter={() => setHover(p.nest.id)}
                  onMouseLeave={() => setHover((h) => (h === p.nest.id ? null : h))}
                  onClick={() => setSelected((s) => (s === p.nest.id ? null : p.nest.id))}
                  className="cursor-pointer"
                />
              );
            })}
            {placed
              .filter((p) => labelled.has(p.nest.id))
              .map((p) => (
                <text
                  key={`l${p.nest.id}`}
                  x={p.scr.sx}
                  y={p.scr.sy - 6 - 17 * Math.sqrt(Math.min(p.point.share / maxShare, 1)) * p.scr.scale}
                  textAnchor="middle"
                  className="font-mono pointer-events-none"
                  fontSize={10}
                  fill={p.nest.id === active ? "#f4f4ee" : "#8a8d82"}
                >
                  {p.nest.name.length > 34 ? p.nest.name.slice(0, 33) + "…" : p.nest.name}
                </text>
              ))}
            {mode === "axes" && (
              <g className="font-mono" fontSize={10} fill="#8a8d82">
                <text x={12} y={20}>age of the pocket · share per 10,000 signals · growth over the previous year</text>
              </g>
            )}
          </svg>
        </div>

        {/* panel */}
        <div className="border border-border bg-card/30 p-4">
          {activeNest ? (
            <div>
              <div className="font-display text-lg text-paper leading-snug">{activeNest.name}</div>
              {activeNest.sub && (
                <div className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted mt-1">
                  measured: {activeNest.sub}
                </div>
              )}
              <dl className="mt-3 space-y-1 font-mono text-[11px]">
                <Row k="month" v={fmtMonth(month)} />
                <Row
                  k="share"
                  v={`${fmtShare(activeSeries?.share ?? 0)} / 10k (${activeSeries?.hits ?? 0} signals)`}
                />
                <Row k="growth" v={fmtRatio(activeSeries?.accel ?? null)} />
                <Row
                  k="age"
                  v={
                    activeSeries?.age == null
                      ? "not datable yet"
                      : `${activeSeries.age} months (from ${activeNest.firstMonth})`
                  }
                />
                <Row k="pocket" v={`${activeNest.size} members, cohesion ${activeNest.cohesion.toFixed(2)}`} />
                <Row
                  k="sources"
                  v={`${activeNest.nSources}${
                    activeNest.topSource
                      ? `, largest ${activeNest.topSource} ${(activeNest.topSourceShare * 100).toFixed(0)} %`
                      : ""
                  }`}
                />
                <Row k="classified" v={`${(activeNest.taggedShare * 100).toFixed(0)} % of members`} />
                <Row k="established sources" v={`${(activeNest.establishedShare * 100).toFixed(0)} %`} />
              </dl>
              {activeNest.establishedShare < 0.5 && (
                <p className="font-sans text-[11px] text-muted mt-3 leading-relaxed">
                  Fewer than half its members come from sources we already read two
                  years ago — this pocket&apos;s age may be a fact about our
                  subscriptions rather than about the world.
                </p>
              )}
              {activeNest.reps.length > 0 && (
                <ul className="mt-3 space-y-2">
                  {activeNest.reps.slice(0, 3).map((r, i) => (
                    <li key={i} className="font-sans text-[11px] text-text leading-snug">
                      {r.url ? (
                        <a href={r.url} target="_blank" rel="noopener noreferrer" className="hover:text-accent">
                          {r.title}
                        </a>
                      ) : (
                        r.title
                      )}
                      <span className="text-muted">
                        {r.source ? ` — ${r.source}` : ""}
                        {r.date ? ` · ${r.date}` : ""}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
              {selected != null && (
                <button
                  type="button"
                  className="mt-4 font-mono text-[10px] uppercase tracking-[0.14em] text-muted hover:text-accent"
                  onClick={() => setSelected(null)}
                >
                  clear selection
                </button>
              )}
            </div>
          ) : (
            <div>
              <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-accent mb-2">
                {mode === "axes" ? "What you are looking at" : "What this map is"}
              </div>
              <p className="font-sans text-[13px] text-text leading-relaxed">
                {mode === "axes" ? (
                  <>
                    Every pocket sits at its age, its share of the month&apos;s
                    signals, and its growth over the preceding year. Step through
                    the months and the pockets travel: up means it is being written
                    about more than the corpus grew, right means it has been around
                    longer.
                  </>
                ) : (
                  <>
                    Each pocket sits where its centroid lands when 1,024 dimensions
                    are pressed into three. The position never moves; the size is
                    its share of that month. Neighbours are related more often than
                    not — but the axes have no meaning and the distances are only
                    indicative, which is what the two numbers above quantify.
                  </>
                )}
              </p>
              <p className="font-sans text-[12px] text-muted leading-relaxed mt-3">
                {datable} of {nests.length} pockets are datable in {fmtMonth(month)}.
                Hover a point for its numbers, click to keep it. Drag to turn the
                space, arrow keys step a month.
              </p>
              {mode === "map" && (
                <p className="font-mono text-[11px] text-muted mt-3 leading-relaxed">
                  Shepard r {projection.shepard.toFixed(2)} · {(projection.varShare * 100).toFixed(0)} %
                  of variance · {(projection.neighbourKeep * 100).toFixed(0)} % of the{" "}
                  {NEIGHBOUR_K} nearest neighbours survive
                </p>
              )}
            </div>
          )}
          <div className="mt-5 pt-4 border-t border-border flex flex-wrap gap-x-4 gap-y-1">
            {(Object.keys(TIER_COLOR) as TierName[]).map((t) => (
              <span key={t} className="font-mono text-[10px] uppercase tracking-[0.1em] text-muted">
                <span
                  className="inline-block w-2 h-2 mr-1.5 align-middle"
                  style={{ background: TIER_COLOR[t] }}
                />
                {t === "science" ? "research" : t}
              </span>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex gap-2">
      <dt className="text-muted uppercase tracking-[0.1em] w-[110px] shrink-0">{k}</dt>
      <dd className="text-text">{v}</dd>
    </div>
  );
}
