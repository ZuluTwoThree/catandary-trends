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
  /** Every signal of the window placed into the cloud (all_points); 0 = none. */
  nAll: number;
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
  /** Draw this layer only as context (a search is running and its matches
   *  are a separate layer). Filtered points stay removed; everything else is
   *  dimmed, never dropped, so the matches read against the whole cloud. */
  contextOnly?: boolean;
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
  if (f.contextOnly) return 1;
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

export type Vec3 = [number, number, number];

export interface View {
  yaw: number;
  pitch: number;
  zoom: number;
  width: number;
  height: number;
  /** The pivot: the world point in the middle of the screen, which turning and
   *  zooming happen around. Default: the origin of the cloud. */
  center?: Vec3;
}

export const ZOOM_MIN = 0.15;
/** The coordinates are 16-bit over about ±1.5 units; at ×50 that grid is 0.55 px
 *  on screen, at ~×90 points would visibly snap to it. */
export const ZOOM_MAX = 50;
/** Points nearer to the camera than this (in depth units, FOCAL away) are not
 *  drawn and cannot be picked. Moving the pivot to the rim of the cloud brings
 *  far points round behind the camera, where the perspective divide would flip
 *  them into mirror images. */
export const NEAR = 0.25;

const ORIGIN: Vec3 = [0, 0, 0];

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
): { sx: number; sy: number; scale: number; depth: number; visible: boolean } {
  const c = v.center ?? ORIGIN;
  x -= c[0];
  y -= c[1];
  z -= c[2];
  const cy = Math.cos(v.yaw);
  const sy = Math.sin(v.yaw);
  const x1 = x * cy + z * sy;
  const z1 = -x * sy + z * cy;
  const cp = Math.cos(v.pitch);
  const sp = Math.sin(v.pitch);
  const y2 = y * cp - z1 * sp;
  const z2 = y * sp + z1 * cp;
  const visible = FOCAL + z2 > NEAR;
  const scale = FOCAL / Math.max(FOCAL + z2, NEAR);
  const r = viewRadius(v);
  return {
    sx: v.width / 2 + x1 * r * scale,
    sy: v.height / 2 - y2 * r * scale,
    scale,
    depth: z2,
    visible,
  };
}

/**
 * The world-space offset that appears as (dx, dy) screen pixels in the plane
 * through the pivot. That plane sits at depth 0, where the perspective scale
 * is exactly 1, so this is the inverse rotation of (dx, -dy, 0) / radius — the
 * transpose of the yaw-then-pitch rotation in projectPoint.
 */
export function screenToWorld(dx: number, dy: number, v: View): Vec3 {
  const r = viewRadius(v);
  const a = dx / r;
  const b = -dy / r;
  const cp = Math.cos(v.pitch);
  const sp = Math.sin(v.pitch);
  const y = b * cp; // + z2 * sp, z2 = 0
  const z1 = -b * sp; // + z2 * cp
  const cy = Math.cos(v.yaw);
  const sy = Math.sin(v.yaw);
  return [a * cy - z1 * sy, y, a * sy + z1 * cy];
}

function add(a: Vec3, b: Vec3, k = 1): Vec3 {
  return [a[0] + k * b[0], a[1] + k * b[1], a[2] + k * b[2]];
}

/**
 * Zoom by `factor` so that the pivot-plane point under the cursor (mx, my)
 * stays under the cursor — what a mouse wheel is expected to do. The zoom is
 * clamped to [ZOOM_MIN, ZOOM_MAX]; the pivot moves by the factor actually
 * applied, so hitting the limit never makes the picture jump.
 */
export function zoomAt(v: View, factor: number, mx: number, my: number): { zoom: number; center: Vec3 } {
  const zoom = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, v.zoom * factor));
  const f = zoom / v.zoom;
  const off = screenToWorld(mx - v.width / 2, my - v.height / 2, v);
  return { zoom, center: add(v.center ?? ORIGIN, off, 1 - 1 / f) };
}

/** Drag the picture by (dx, dy) pixels: the pivot moves the opposite way. */
export function panBy(v: View, dx: number, dy: number): Vec3 {
  return add(v.center ?? ORIGIN, screenToWorld(dx, dy, v), -1);
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
  // projectPoint() inlined: with every signal loaded (1.5M) an object per point
  // made each hover frame allocate 1.5M results. Same arithmetic, same order.
  const c = v.center ?? ORIGIN;
  const cy = Math.cos(v.yaw);
  const sy = Math.sin(v.yaw);
  const cp = Math.cos(v.pitch);
  const sp = Math.sin(v.pitch);
  const r = viewRadius(v);
  const hw = v.width / 2;
  const hh = v.height / 2;
  let best = -1;
  let bestD = maxPx * maxPx;
  let bestDepth = Infinity;
  for (let i = 0; i < d.n; i++) {
    if (pointState(d, i, f) !== 2) continue;
    const x = d.pos[i * 3] - c[0];
    const y = d.pos[i * 3 + 1] - c[1];
    const z = d.pos[i * 3 + 2] - c[2];
    const x1 = x * cy + z * sy;
    const z1 = -x * sy + z * cy;
    const y2 = y * cp - z1 * sp;
    const z2 = y * sp + z1 * cp;
    if (!(FOCAL + z2 > NEAR)) continue;
    const scale = FOCAL / (FOCAL + z2);
    const dx = hw + x1 * r * scale - px;
    const dy = hh - y2 * r * scale - py;
    const dd = dx * dx + dy * dy;
    if (dd < bestD || (dd === bestD && z2 < bestDepth)) {
      best = i;
      bestD = dd;
      bestDepth = z2;
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

/**
 * The ring (pocket) whose outline passes within `band` px of (x, y), nearest
 * outline first; -1 if none. Rings are hit on the CPU like the points, so the
 * SVG overlay never takes a pointer event — a drag that starts on a ring still
 * turns or moves the cloud.
 */
export function pickRing(
  rings: { sx: number; sy: number; r: number }[],
  x: number,
  y: number,
  band = 5
): number {
  let best = -1;
  let bestD = band;
  rings.forEach((g, k) => {
    const d = Math.abs(Math.hypot(g.sx - x, g.sy - y) - g.r);
    if (d <= bestD) {
      best = k;
      bestD = d;
    }
  });
  return best;
}

// ------------------------------------------------------------ placed signals
//
// Since 27.09. (evening) every signal of the window is placed into the cloud,
// in a second blob sorted by trend id (pipeline/signal_space.py place_all). A
// search returns the full-corpus matches; these helpers find their records.

/** trend_id of every record, in blob order (ascending for the placed blob). */
export function recordIds(buf: Uint8Array): Uint32Array {
  const n = Math.floor(buf.byteLength / RECORD_BYTES);
  const dv = new DataView(buf.buffer, buf.byteOffset, buf.byteLength);
  const out = new Uint32Array(n);
  for (let i = 0; i < n; i++) out[i] = dv.getUint32(i * RECORD_BYTES + 12, true);
  return out;
}

/** Index of `id` in an ascending Uint32Array, or -1. */
export function findSorted(ids: Uint32Array, id: number): number {
  let lo = 0;
  let hi = ids.length - 1;
  while (lo <= hi) {
    const mid = (lo + hi) >>> 1;
    const v = ids[mid];
    if (v === id) return mid;
    if (v < id) lo = mid + 1;
    else hi = mid - 1;
  }
  return -1;
}

/**
 * The records of `wanted` trend ids, packed back to back (same 16-byte layout,
 * so the browser decodes them with `unpack`). `missing` counts ids that have no
 * place in the cloud — matches outside its time window.
 */
export function collectRecords(
  buf: Uint8Array,
  ids: Uint32Array,
  wanted: Iterable<number>
): { records: Uint8Array; found: number; missing: number } {
  const hits: number[] = [];
  let missing = 0;
  for (const id of wanted) {
    const k = findSorted(ids, id);
    if (k < 0) missing++;
    else hits.push(k);
  }
  hits.sort((a, b) => a - b);
  const out = new Uint8Array(hits.length * RECORD_BYTES);
  hits.forEach((k, j) =>
    out.set(buf.subarray(k * RECORD_BYTES, (k + 1) * RECORD_BYTES), j * RECORD_BYTES)
  );
  return { records: out, found: hits.length, missing };
}
