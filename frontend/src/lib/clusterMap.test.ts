import { describe, expect, it } from "vitest";
import {
  ACCEL_MAX,
  AGE_CEIL_MONTHS,
  SHARE_CEIL,
  SHARE_FLOOR,
  accelZ,
  ageX,
  distance,
  nestSeries,
  normaliseCoords,
  place,
  projectToSpace,
  shareY,
  type Vec3,
} from "./clusterMap";

/** A 1024-dim vector that only uses its first dimensions. */
function pad(coords: number[], dim = 1024): number[] {
  const v = new Array(dim).fill(0);
  coords.forEach((c, i) => (v[i] = c));
  return v;
}

const CUBE = [
  [0, 0, 0],
  [1, 0, 0],
  [0, 2, 0],
  [0, 0, 3],
  [1, 1, 1],
  [-2, 1, 0.5],
];

describe("projectToSpace", () => {
  it("loses nothing when the data really is three-dimensional", () => {
    const p = projectToSpace(CUBE.map((c) => pad(c)));
    expect(p.shepard).toBeGreaterThan(0.9999);
    expect(p.varShare).toBeGreaterThan(0.9999);
    // and the distances themselves survive, not just their ordering
    for (let i = 0; i < CUBE.length; i++) {
      for (let j = i + 1; j < CUBE.length; j++) {
        const orig = distance(CUBE[i] as Vec3, CUBE[j] as Vec3);
        expect(distance(p.coords[i], p.coords[j])).toBeCloseTo(orig, 4);
      }
    }
  });

  it("is deterministic — same input, identical coordinates", () => {
    const vs = CUBE.map((c) => pad(c));
    expect(projectToSpace(vs).coords).toEqual(projectToSpace(vs).coords);
  });

  it("keeps two groups apart", () => {
    const vs = [
      pad([10, 0, 0]),
      pad([10.1, 0.1, 0]),
      pad([9.9, -0.1, 0]),
      pad([-10, 0, 0]),
      pad([-10.1, 0.1, 0]),
      pad([-9.9, -0.1, 0]),
    ];
    const { coords } = projectToSpace(vs);
    const within = distance(coords[0], coords[1]);
    const across = distance(coords[0], coords[3]);
    expect(across).toBeGreaterThan(within * 10);
  });

  it("does not claim fidelity it cannot have: an 8-point simplex in 1024 dims", () => {
    // Eight orthonormal basis vectors are all equally far apart. Three axes
    // cannot reproduce that, and the measure has to say so instead of
    // reporting a perfect correlation against a constant.
    const vs = Array.from({ length: 8 }, (_, i) => {
      const v = new Array(1024).fill(0);
      v[i] = 1;
      return v;
    });
    const p = projectToSpace(vs);
    expect(p.shepard).toBeLessThan(0.5);
    expect(p.varShare).toBeLessThan(0.6);
  });

  it("survives degenerate inputs", () => {
    expect(projectToSpace([]).coords).toEqual([]);
    expect(projectToSpace([pad([1, 2, 3])]).coords).toHaveLength(1);
  });
});

describe("normaliseCoords", () => {
  it("scales uniformly, so distance ratios are untouched", () => {
    const coords: Vec3[] = [
      [0, 0, 0],
      [4, 0, 0],
      [0, 8, 0],
    ];
    const out = normaliseCoords(coords);
    let max = 0;
    for (const c of out) for (const v of c) max = Math.max(max, Math.abs(v));
    expect(max).toBeCloseTo(1, 10);
    const before = distance(coords[0], coords[1]) / distance(coords[0], coords[2]);
    const after = distance(out[0], out[1]) / distance(out[0], out[2]);
    expect(after).toBeCloseTo(before, 10);
  });
});

describe("nestSeries", () => {
  const totals = new Array(36).fill(1000);

  it("counts the trailing twelve months as a share per 10,000", () => {
    const hits = new Array(36).fill(0);
    for (let j = 12; j < 24; j++) hits[j] = 1; // one lookalike a month, year two
    const s = nestSeries(hits, totals, 12);
    expect(s[23].hits).toBe(12);
    expect(s[23].share).toBeCloseTo((12 / 12000) * 10000, 10); // = 10
    expect(s[11].share).toBe(0);
  });

  it("caps growth when the preceding window is empty", () => {
    const hits = new Array(36).fill(0);
    for (let j = 12; j < 24; j++) hits[j] = 1;
    const s = nestSeries(hits, totals, 12);
    expect(s[23].accel).toBe(ACCEL_MAX); // nothing before it: no ratio exists
    expect(s[11].accel).toBe(null); // window empty on both sides
  });

  it("measures a doubling as a doubling", () => {
    const hits = new Array(36).fill(0);
    for (let j = 12; j < 24; j++) hits[j] = 1;
    for (let j = 24; j < 36; j++) hits[j] = 2;
    const s = nestSeries(hits, totals, 12);
    expect(s[35].accel).toBeCloseTo(2, 10);
  });

  it("normalises against the corpus, not against raw counts", () => {
    // The pocket doubles its count while the corpus doubles too: unchanged.
    const hits = new Array(36).fill(0);
    const tot = new Array(36).fill(1000);
    for (let j = 12; j < 24; j++) hits[j] = 1;
    for (let j = 24; j < 36; j++) {
      hits[j] = 2;
      tot[j] = 2000;
    }
    const s = nestSeries(hits, tot, 12);
    expect(s[35].accel).toBeCloseTo(1, 10);
  });

  it("dates the age from the pocket's first datable month", () => {
    const s = nestSeries(new Array(36).fill(1), totals, 6);
    expect(s[5].age).toBe(null);
    expect(s[6].age).toBe(0);
    expect(s[10].age).toBe(4);
  });
});

describe("axis scales", () => {
  it("spans the age axis from birth to the ceiling", () => {
    expect(ageX(0)).toBeCloseTo(-1, 10);
    expect(ageX(AGE_CEIL_MONTHS)).toBeCloseTo(1, 10);
    expect(ageX(1000)).toBeCloseTo(1, 10); // clamped, never off the axis
    // log: the first two years take more room than years 10-25
    expect(ageX(24) - ageX(0)).toBeGreaterThan(ageX(300) - ageX(120));
  });

  it("spans the share axis on a log scale", () => {
    expect(shareY(0)).toBeCloseTo(-1, 10); // floor, not off-axis
    expect(shareY(SHARE_FLOOR)).toBeCloseTo(-1, 10);
    expect(shareY(SHARE_CEIL)).toBeCloseTo(1, 10);
    expect(shareY(10)).toBeGreaterThan(shareY(1));
  });

  it("centres growth at unchanged", () => {
    expect(accelZ(1)).toBeCloseTo(0, 10);
    expect(accelZ(null)).toBe(0);
    expect(accelZ(2)).toBeCloseTo(1 / 3, 10);
    expect(accelZ(0.5)).toBeCloseTo(-1 / 3, 10);
    expect(accelZ(ACCEL_MAX)).toBeCloseTo(1, 10);
    expect(accelZ(100)).toBeCloseTo(1, 10); // clamped
  });
});

describe("place", () => {
  const totals = new Array(24).fill(1000);
  const series = nestSeries(new Array(24).fill(1), totals, 6);

  it("keeps the map position fixed and only the numbers moving", () => {
    const coord: Vec3 = [0.3, -0.2, 0.5];
    const a = place("map", 10, series, coord, 1);
    const b = place("map", 20, series, coord, 1);
    expect(a?.pos).toEqual(coord);
    expect(b?.pos).toEqual(coord);
    expect(b!.hits).toBeGreaterThan(a!.hits);
  });

  it("leaves a pocket off the age axis until it has a history", () => {
    expect(place("axes", 5, series, undefined, 1)).toBe(null);
    expect(place("axes", 6, series, undefined, 1)?.pos[0]).toBeCloseTo(ageX(0), 10);
  });

  it("returns null past the end of the series", () => {
    expect(place("axes", 99, series, undefined, 1)).toBe(null);
    expect(place("map", 99, series, [0, 0, 0], 1)).toBe(null);
  });
});

describe("neighbourKeep", () => {
  it("is 1 when the projection keeps every neighbourhood", () => {
    const p = projectToSpace(CUBE.map((c) => pad(c)));
    expect(p.neighbourKeep).toBeCloseTo(1, 10);
  });

  it("falls well below 1 when three axes cannot hold the structure", () => {
    const vs = Array.from({ length: 12 }, (_, i) => {
      const v = new Array(1024).fill(0);
      v[i] = 1;
      return v;
    });
    expect(projectToSpace(vs).neighbourKeep).toBeLessThan(0.7);
  });
});

describe("normaliseCoords with a quantile", () => {
  it("frames the bulk and lets a single outlier leave the box", () => {
    const coords: Vec3[] = [
      [1, 0, 0],
      [0.9, 0, 0],
      [1.1, 0, 0],
      [40, 0, 0], // the outlier that would otherwise shrink the rest to a dot
    ];
    const out = normaliseCoords(coords, 0.75);
    expect(Math.abs(out[2][0])).toBeLessThanOrEqual(1.0001);
    expect(Math.abs(out[3][0])).toBeGreaterThan(10);
    // still one factor for all axes: ratios untouched
    expect(out[0][0] / out[1][0]).toBeCloseTo(coords[0][0] / coords[1][0], 10);
  });
});
