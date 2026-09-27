/**
 * Coordinates for the signal-space view (/trends/foresight/map).
 *
 * Two coordinate sources, one renderer:
 *
 *  1. MAP — the 1024-dim nest centroids projected onto three axes by classical
 *     MDS (equivalently: PCA of the centroids, since the centroids are already
 *     L2-normalised). The axes carry no unit and are deliberately never
 *     labelled, because they mean nothing. What the projection DOES carry is
 *     measured and printed next to the picture: the Shepard correlation between
 *     the 1024-dim pairwise distances and the projected ones, and the share of
 *     centroid variance the three axes hold. A map at r = 0.6 is a navigation
 *     aid, not a measurement, and the page has to say so rather than let a
 *     pretty cloud imply precision.
 *
 *  2. AXES — three quantities that mean something on their own: how long the
 *     pocket has been datable, how loud it is per 10,000 signals of the same
 *     month, and whether that share is rising or falling. Here the point MOVES
 *     from month to month, so the animation is a trajectory instead of a
 *     breathing map — which is what the product is actually about.
 *
 * Everything here is pure and deterministic: same input, same picture, every
 * render. The eigenvector search uses a fixed start vector and a fixed sign
 * convention for exactly that reason. tests in clusterMap.test.ts pin both.
 */

export type Vec3 = [number, number, number];

export type SpaceMode = "map" | "axes";

export interface Projection {
  /** One point per input vector, in the order given. */
  coords: Vec3[];
  /** Pearson r between the 1024-dim pairwise distances and the projected ones.
   *  The measured price of showing 1024 dimensions as three. */
  shepard: number;
  /** Share of the centroids' total variance carried by the three axes. */
  varShare: number;
  /** Share of each pocket's NEIGHBOUR_K nearest neighbours in 1024 dims that
   *  are still among its nearest on the map. This is the number a map is
   *  actually used against: "are the things next to each other related?" */
  neighbourKeep: number;
  /** The three eigenvalues, largest first (diagnostics). */
  eigen: number[];
}

const EIG_ITERS = 600;
const EIG_EPS = 1e-13;

function dot(a: ArrayLike<number>, b: ArrayLike<number>, d: number): number {
  let s = 0;
  for (let j = 0; j < d; j++) s += a[j] * b[j];
  return s;
}

function norm2(v: Float64Array): number {
  let s = 0;
  for (let i = 0; i < v.length; i++) s += v[i] * v[i];
  return Math.sqrt(s);
}

/** Gram matrix of the column-centred vectors, plus its trace (= total variance). */
function gram(vectors: number[][]): { G: Float64Array; n: number; trace: number } {
  const n = vectors.length;
  const d = vectors[0]?.length ?? 0;
  const mean = new Float64Array(d);
  for (const v of vectors) for (let j = 0; j < d; j++) mean[j] += v[j];
  for (let j = 0; j < d; j++) mean[j] /= n || 1;
  const B: Float64Array[] = vectors.map((v) => {
    const r = new Float64Array(d);
    for (let j = 0; j < d; j++) r[j] = v[j] - mean[j];
    return r;
  });
  const G = new Float64Array(n * n);
  let trace = 0;
  for (let i = 0; i < n; i++) {
    for (let k = i; k < n; k++) {
      const s = dot(B[i], B[k], d);
      G[i * n + k] = s;
      G[k * n + i] = s;
    }
    trace += G[i * n + i];
  }
  return { G, n, trace };
}

/** Subtract the components along already-found eigenvectors, then normalise. */
function orthonormalise(v: Float64Array, basis: Float64Array[]): boolean {
  for (const b of basis) {
    const p = dot(v, b, v.length);
    for (let i = 0; i < v.length; i++) v[i] -= p * b[i];
  }
  const nrm = norm2(v);
  if (!(nrm > 1e-12)) return false;
  for (let i = 0; i < v.length; i++) v[i] /= nrm;
  return true;
}

/**
 * Top-k eigenvectors of a small symmetric matrix by power iteration with
 * Gram-Schmidt deflation. n is the nest count (19-94 in practice), so this is
 * microseconds — and unlike a library call it is byte-identical on every
 * render, which is the only property the page needs from it.
 */
function topEigen(G: Float64Array, n: number, k: number): { vecs: Float64Array[]; vals: number[] } {
  const vecs: Float64Array[] = [];
  const vals: number[] = [];
  for (let c = 0; c < k; c++) {
    const v = new Float64Array(n);
    // Fixed, non-degenerate start: never orthogonal to the leading eigenvector
    // for real data, and identical on every call (no Math.random anywhere).
    for (let i = 0; i < n; i++) v[i] = Math.sin((i + 1) * (c + 1) * 1.7) + 0.1;
    if (!orthonormalise(v, vecs)) {
      vecs.push(v);
      vals.push(0);
      continue;
    }
    let val = 0;
    for (let it = 0; it < EIG_ITERS; it++) {
      const w = new Float64Array(n);
      for (let i = 0; i < n; i++) {
        let s = 0;
        for (let j = 0; j < n; j++) s += G[i * n + j] * v[j];
        w[i] = s;
      }
      if (!orthonormalise(w, vecs)) break;
      let delta = 0;
      for (let i = 0; i < n; i++) delta = Math.max(delta, Math.abs(w[i] - v[i]));
      v.set(w);
      if (delta < EIG_EPS) break;
    }
    // Rayleigh quotient on the converged vector.
    let gv = 0;
    for (let i = 0; i < n; i++) {
      let s = 0;
      for (let j = 0; j < n; j++) s += G[i * n + j] * v[j];
      gv += v[i] * s;
    }
    val = gv;
    // Sign convention: the largest-magnitude component is positive. Power
    // iteration is free to converge to -v, which would mirror the cloud
    // between two renders of the same data.
    let big = 0;
    for (let i = 1; i < n; i++) if (Math.abs(v[i]) > Math.abs(v[big])) big = i;
    if (v[big] < 0) for (let i = 0; i < n; i++) v[i] = -v[i];
    vecs.push(v);
    vals.push(val);
  }
  return { vecs, vals };
}

function pearson(a: number[], b: number[]): number {
  const n = a.length;
  if (n < 2) return 1;
  let ma = 0;
  let mb = 0;
  for (let i = 0; i < n; i++) {
    ma += a[i];
    mb += b[i];
  }
  ma /= n;
  mb /= n;
  let sab = 0;
  let sa = 0;
  let sb = 0;
  for (let i = 0; i < n; i++) {
    const da = a[i] - ma;
    const db = b[i] - mb;
    sab += da * db;
    sa += da * da;
    sb += db * db;
  }
  // Degenerate cases are not "perfect": when the original distances are all
  // equal there is no ordering to preserve, and a projection that nonetheless
  // spreads them out has invented the structure rather than kept it.
  if (sa === 0 && sb === 0) return 1;
  const den = Math.sqrt(sa * sb);
  return den > 0 ? sab / den : 0;
}

export function distance(a: Vec3, b: Vec3): number {
  return Math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2);
}

/** Classical MDS of the centroids onto three axes, with its own error measured. */
export function projectToSpace(vectors: number[][]): Projection {
  if (vectors.length === 0)
    return { coords: [], shepard: 1, varShare: 1, neighbourKeep: 1, eigen: [] };
  const { G, n, trace } = gram(vectors);
  const k = Math.min(3, n);
  const { vecs, vals } = topEigen(G, n, k);
  const coords: Vec3[] = [];
  for (let i = 0; i < n; i++) {
    const p: Vec3 = [0, 0, 0];
    for (let c = 0; c < k; c++) p[c] = vecs[c][i] * Math.sqrt(Math.max(vals[c], 0));
    coords.push(p);
  }
  // Both error measures come off the same two distance matrices. The original
  // distances follow from the Gram matrix (d^2 = Gii + Gjj - 2Gij), so the
  // 1024-dim vectors are never touched again.
  const D0: number[][] = [];
  const D1: number[][] = [];
  const orig: number[] = [];
  const proj: number[] = [];
  for (let i = 0; i < n; i++) {
    D0.push(new Array(n).fill(0));
    D1.push(new Array(n).fill(0));
  }
  for (let i = 0; i < n; i++) {
    for (let j = i + 1; j < n; j++) {
      const d2 = G[i * n + i] + G[j * n + j] - 2 * G[i * n + j];
      const a = Math.sqrt(Math.max(d2, 0));
      const b = distance(coords[i], coords[j]);
      D0[i][j] = D0[j][i] = a;
      D1[i][j] = D1[j][i] = b;
      orig.push(a);
      proj.push(b);
    }
  }
  const varShare = trace > 0 ? vals.reduce((s, v) => s + Math.max(v, 0), 0) / trace : 1;
  return {
    coords,
    shepard: pearson(orig, proj),
    varShare,
    neighbourKeep: neighbourKeep(D0, D1, NEIGHBOUR_K),
    eigen: vals,
  };
}

/** How many of the k nearest neighbours survive the projection, averaged. */
export const NEIGHBOUR_K = 5;

export function neighbourKeep(D0: number[][], D1: number[][], k: number): number {
  const n = D0.length;
  if (n <= 1) return 1;
  const kk = Math.min(k, n - 1);
  const nearest = (D: number[][], i: number) =>
    D[i]
      .map((d, j) => [d, j] as [number, number])
      .filter(([, j]) => j !== i)
      // ties broken by index, so the measure cannot depend on sort stability
      .sort((a, b) => a[0] - b[0] || a[1] - b[1])
      .slice(0, kk)
      .map(([, j]) => j);
  let sum = 0;
  for (let i = 0; i < n; i++) {
    const a = new Set(nearest(D0, i));
    let hit = 0;
    for (const j of nearest(D1, i)) if (a.has(j)) hit++;
    sum += hit / kk;
  }
  return sum / n;
}

/**
 * Scale the whole cloud into the unit cube — ONE factor for all three axes.
 * Per-axis normalisation would stretch the shape and turn a thin sheet into a
 * ball, which is precisely the distortion the Shepard number is there to bound.
 */
export function normaliseCoords(coords: Vec3[], quantile = 1): Vec3[] {
  // One outlier pocket can shrink everything else to a dot, so the reference
  // may be a quantile of the per-point extents rather than the maximum. Points
  // beyond it simply leave the frame — which is the correct picture of an
  // outlier, and still one factor for all three axes.
  const extents = coords.map((c) => Math.max(Math.abs(c[0]), Math.abs(c[1]), Math.abs(c[2])));
  extents.sort((a, b) => a - b);
  const q = Math.max(0, Math.min(1, quantile));
  const ref = extents.length
    ? extents[Math.min(extents.length - 1, Math.round(q * (extents.length - 1)))]
    : 0;
  const f = ref > 0 ? 1 / ref : 1;
  return coords.map((c) => [c[0] * f, c[1] * f, c[2] * f] as Vec3);
}

// --------------------------------------------------------------- trajectories

/** Months in a trailing window. A single month is noise at this granularity. */
export const TRAIL = 12;
/** Cap for the growth ratio when the preceding window is empty (no ratio exists). */
export const ACCEL_MAX = 8;
/** Shares below this are drawn at the axis floor instead of falling off a log scale. */
export const SHARE_FLOOR = 0.05;
export const SHARE_CEIL = 400;
export const AGE_CEIL_MONTHS = 300;

export const AGE_TICKS = [0, 12, 24, 60, 120, 240];
export const SHARE_TICKS = [0.1, 1, 10, 100];
export const ACCEL_TICKS = [0.25, 0.5, 1, 2, 4];

export interface SeriesPoint {
  /** Lookalikes per 10,000 corpus signals, over the trailing 12 months. */
  share: number;
  /** Raw lookalike count in the same window (what the share is made of). */
  hits: number;
  /** Trailing share over the share of the 12 months before it. null = no basis. */
  accel: number | null;
  /** Months since the pocket's first datable month, null before it existed. */
  age: number | null;
}

function prefixSums(xs: number[], n: number): Float64Array {
  const c = new Float64Array(n + 1);
  for (let i = 0; i < n; i++) c[i + 1] = c[i] + (xs[i] || 0);
  return c;
}

/**
 * The per-month trajectory of one pocket.
 *
 * `totals` is the corpus per month AS THE SNAPSHOT SAW IT — normalising against
 * today's corpus would make every pocket look like it is fading, because the
 * newest months have grown since the run while the pocket's counts have not.
 * The share is the same unit the Field Watch sheets use (per 10,000 signals of
 * the month), for the same reason: raw counts measure our own intake ramp.
 */
export function nestSeries(
  hits: number[],
  totals: number[],
  firstIndex: number | null
): SeriesPoint[] {
  const n = Math.min(hits.length, totals.length);
  const cumH = prefixSums(hits, n);
  const cumT = prefixSums(totals, n);
  const win = (cum: Float64Array, a: number, b: number) => cum[b + 1] - cum[Math.max(a, 0)];
  const out: SeriesPoint[] = [];
  for (let j = 0; j < n; j++) {
    const h = win(cumH, j - TRAIL + 1, j);
    const t = win(cumT, j - TRAIL + 1, j);
    const share = t > 0 ? (h / t) * 10_000 : 0;
    let accel: number | null = null;
    const pj = j - TRAIL;
    if (pj >= 0) {
      const ph = win(cumH, pj - TRAIL + 1, pj);
      const pt = win(cumT, pj - TRAIL + 1, pj);
      const prev = pt > 0 ? (ph / pt) * 10_000 : 0;
      accel = prev > 0 ? share / prev : share > 0 ? ACCEL_MAX : null;
    }
    out.push({
      share,
      hits: h,
      accel,
      age: firstIndex == null || j < firstIndex ? null : j - firstIndex,
    });
  }
  return out;
}

function clamp(x: number, lo: number, hi: number): number {
  return x < lo ? lo : x > hi ? hi : x;
}

/** Age on a log axis: the first two years deserve the room, not year 24. */
export function ageX(months: number): number {
  const v = Math.log1p(clamp(months, 0, AGE_CEIL_MONTHS)) / Math.log1p(AGE_CEIL_MONTHS);
  return v * 2 - 1;
}

/** Share on a log axis — pockets span three orders of magnitude. */
export function shareY(share: number): number {
  const s = clamp(share, SHARE_FLOOR, SHARE_CEIL);
  const v = Math.log10(s / SHARE_FLOOR) / Math.log10(SHARE_CEIL / SHARE_FLOOR);
  return v * 2 - 1;
}

/** Growth as log2 of the ratio: 0 is "unchanged", +1 a doubling, -1 a halving. */
export function accelZ(accel: number | null): number {
  if (accel == null) return 0;
  return clamp(Math.log2(clamp(accel, 1 / ACCEL_MAX, ACCEL_MAX)) / 3, -1, 1);
}

export interface Placed extends SeriesPoint {
  id: number;
  pos: Vec3;
}

/**
 * Where a pocket sits in month `j`.
 *
 * MAP mode: the position is fixed (it is the pocket's place in the embedding
 * space), only the size breathes — so the animation shows attention moving
 * across a stable landscape. AXES mode: the position itself is the measurement,
 * so the pocket travels and a trail can be drawn behind it. A pocket with no
 * datable history yet has no place on the age axis and is left out.
 */
export function place(
  mode: SpaceMode,
  j: number,
  series: SeriesPoint[],
  coord: Vec3 | undefined,
  id: number
): Placed | null {
  const s = series[j];
  if (!s) return null;
  if (mode === "map") {
    if (!coord) return null;
    return { id, pos: coord, ...s };
  }
  if (s.age == null) return null;
  return { id, pos: [ageX(s.age), shareY(s.share), accelZ(s.accel)], ...s };
}
