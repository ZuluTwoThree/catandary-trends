/**
 * The signal cloud (/trends/foresight/map, view "Cloud") — everything that can
 * be decided without a browser: decoding the packed blob, which points are
 * active in a month window, the screen projection used for picking, and the
 * picking itself. The WebGL shader in ClusterCloud.tsx mirrors `projectPoint`
 * and `pointState` line for line; the vitests pin the JS side.
 *
 * Blob layout (pipeline/signal_space.py PACK_DTYPE, 16 bytes per point, all
 * little-endian — read explicitly as such, never via a platform-endian view):
 *
 *   0 x u16 · 2 y u16 · 4 z u16 · 6 month u16 · 8 tier u8 · 9 vertical u8 ·
 *   10 nest u16 (0xFFFF = none) · 12 trend_id u32
 */

export const RECORD_BYTES = 16;
export const NO_NEST = 0xffff;

export interface CloudNest {
  id: number;
  name: string;
  tier: string | null;
  x: number;
  y: number;
  z: number;
  members: number;
}

export interface CloudMeta {
  runId: number;
  createdAt: string;
  nPoints: number;
  perMonth: number;
  months: string[];
  coordRange: number;
  pcaVariance: number;
  neighbourKeep: number;
  trustworthiness: number;
  durationS: number;
  emergingRunId: number | null;
  nests: CloudNest[];
  /** code -> name, as stored with the run (so decoding never drifts). */
  tierCodes: Record<string, string>;
  verticalCodes: Record<string, string>;
}

export interface CloudData {
  n: number;
  /** x,y,z interleaved, dequantised. */
  pos: Float32Array;
  month: Uint16Array;
  tier: Uint8Array;
  vertical: Uint8Array;
  nest: Uint16Array;
  trendId: Uint32Array;
}

export function dequantise(q: number, range: number): number {
  return (q / 65535) * (2 * range) - range;
}

export function unpack(buf: ArrayBuffer, range: number): CloudData {
  if (buf.byteLength % RECORD_BYTES !== 0) {
    throw new Error(`blob of ${buf.byteLength} bytes is not a whole number of ${RECORD_BYTES}-byte records`);
  }
  const n = buf.byteLength / RECORD_BYTES;
  const dv = new DataView(buf);
  const out: CloudData = {
    n,
    pos: new Float32Array(n * 3),
    month: new Uint16Array(n),
    tier: new Uint8Array(n),
    vertical: new Uint8Array(n),
    nest: new Uint16Array(n),
    trendId: new Uint32Array(n),
  };
  for (let i = 0; i < n; i++) {
    const o = i * RECORD_BYTES;
    out.pos[i * 3] = dequantise(dv.getUint16(o, true), range);
    out.pos[i * 3 + 1] = dequantise(dv.getUint16(o + 2, true), range);
    out.pos[i * 3 + 2] = dequantise(dv.getUint16(o + 4, true), range);
    out.month[i] = dv.getUint16(o + 6, true);
    out.tier[i] = dv.getUint8(o + 8);
    out.vertical[i] = dv.getUint8(o + 9);
    out.nest[i] = dv.getUint16(o + 10, true);
    out.trendId[i] = dv.getUint32(o + 12, true);
  }
  return out;
}

// ------------------------------------------------------------ what is shown

export interface CloudFilter {
  /** Bit i set = tier code i shown. Code 0 is "no tier". */
  tierMask: number;
  /** Bit i set = vertical code i shown. Code 0 is "no vertical". */
  verticalMask: number;
  /** Month index of the window's last month, and its length in months. */
  monthEnd: number;
  windowLen: number;
  /** Nest index the owner picked, or -1. */
  nest: number;
}

export const ALL_BITS = 0xffff;

/**
 * 0 = hidden (filtered out), 1 = context (outside the month window, drawn as
 * a faint ghost if ghosts are on), 2 = active. Filters remove a point
 * entirely; the window only dims it — so the shape of the whole cloud stays
 * readable while a month is being looked at.
 */
export function pointState(
  d: CloudData,
  i: number,
  f: CloudFilter
): 0 | 1 | 2 {
  if (!((f.tierMask >> d.tier[i]) & 1)) return 0;
  if (!((f.verticalMask >> d.vertical[i]) & 1)) return 0;
  if (f.nest >= 0 && d.nest[i] !== f.nest) return 1;
  const m = d.month[i];
  return m <= f.monthEnd && m > f.monthEnd - f.windowLen ? 2 : 1;
}

export function countActive(d: CloudData, f: CloudFilter): number {
  let c = 0;
  for (let i = 0; i < d.n; i++) if (pointState(d, i, f) === 2) c++;
  return c;
}

// --------------------------------------------------------------- projection

/** Same camera as ClusterSpace.tsx, so the three views turn alike. */
export const FOCAL = 3.4;

export interface View {
  yaw: number;
  pitch: number;
  zoom: number;
  width: number;
  height: number;
}

/** Radius of the unit cube on screen, in CSS pixels. */
export function viewRadius(v: View): number {
  return 0.42 * Math.min(v.width, v.height) * v.zoom;
}

/**
 * Screen position of a point (CSS pixels, origin top-left) and its perspective
 * scale. MUST stay identical to the vertex shader in ClusterCloud.tsx — picking
 * a point the GPU drew somewhere else would open the wrong article.
 */
export function projectPoint(
  x: number,
  y: number,
  z: number,
  v: View
): { sx: number; sy: number; scale: number; depth: number } {
  const cy = Math.cos(v.yaw);
  const sy = Math.sin(v.yaw);
  const x1 = x * cy + z * sy;
  const z1 = -x * sy + z * cy;
  const cp = Math.cos(v.pitch);
  const sp = Math.sin(v.pitch);
  const y2 = y * cp - z1 * sp;
  const z2 = y * sp + z1 * cp;
  const scale = FOCAL / (FOCAL + z2);
  const r = viewRadius(v);
  return { sx: v.width / 2 + x1 * r * scale, sy: v.height / 2 - y2 * r * scale, scale, depth: z2 };
}

/**
 * The active point nearest to (px, py) within `maxPx`, preferring the one in
 * front when two are equally close. -1 when nothing is near. One pass over
 * the cloud: ~108k projections, about a millisecond.
 */
export function pickNearest(
  d: CloudData,
  f: CloudFilter,
  v: View,
  px: number,
  py: number,
  maxPx = 6
): number {
  let best = -1;
  let bestD = maxPx * maxPx;
  let bestDepth = Infinity;
  for (let i = 0; i < d.n; i++) {
    if (pointState(d, i, f) !== 2) continue;
    const p = projectPoint(d.pos[i * 3], d.pos[i * 3 + 1], d.pos[i * 3 + 2], v);
    const dx = p.sx - px;
    const dy = p.sy - py;
    const dd = dx * dx + dy * dy;
    if (dd < bestD || (dd === bestD && p.depth < bestDepth)) {
      best = i;
      bestD = dd;
      bestDepth = p.depth;
    }
  }
  return best;
}

/** A stable colour for nest k — golden-angle hues, so neighbours differ. */
export function nestColor(k: number): [number, number, number] {
  const h = ((k * 137.508) % 360) / 360;
  return hslToRgb(h, 0.65, 0.62);
}

function hslToRgb(h: number, s: number, l: number): [number, number, number] {
  const f = (n: number) => {
    const k = (n + h * 12) % 12;
    const a = s * Math.min(l, 1 - l);
    return l - a * Math.max(-1, Math.min(k - 3, 9 - k, 1));
  };
  return [f(0), f(8), f(4)];
}
