import { describe, expect, it } from "vitest";
import {
  ALL_BITS,
  FOCAL,
  NEAR,
  NO_NEST,
  ZOOM_MAX,
  ZOOM_MIN,
  panBy,
  pickRing,
  collectRecords,
  findSorted,
  recordIds,
  screenToWorld,
  zoomAt,
  RECORD_BYTES,
  countActive,
  pickNearest,
  pointState,
  projectPoint,
  unpack,
  type CloudData,
  type CloudFilter,
  type View,
} from "./spaceCloud";

/**
 * Written by pipeline/signal_space.py.pack() — three points:
 *   (-1.5, 0, 1.5)  month 0   tier 1 vertical 2 nest none  id 17
 *   (0.25,-0.75,1)  month 7   tier 4 vertical 8 nest 3     id 123456
 *   (1.5, 1.5,-1.5) month 179 tier 0 vertical 0 nest 0     id 4294967295
 * If the Python layout changes, this blob stops decoding — which is the point.
 */
const PY_BLOB =
  "00000080ffff00000102ffff110000005595004054d507000408030040e20100ffffffff0000b30000000000ffffffff";

function fromHex(h: string): ArrayBuffer {
  const b = new Uint8Array(h.length / 2);
  for (let i = 0; i < b.length; i++) b[i] = parseInt(h.slice(i * 2, i * 2 + 2), 16);
  return b.buffer;
}

const STEP = (2 * 1.5) / 65535;

describe("unpack", () => {
  it("decodes the blob the Python side wrote, field by field", () => {
    const d = unpack(fromHex(PY_BLOB), 1.5);
    expect(d.n).toBe(3);
    const want = [
      [-1.5, 0, 1.5],
      [0.25, -0.75, 1.0],
      [1.5, 1.5, -1.5],
    ];
    want.forEach((p, i) =>
      p.forEach((v, k) => expect(Math.abs(d.pos[i * 3 + k] - v)).toBeLessThanOrEqual(STEP))
    );
    expect(Array.from(d.month)).toEqual([0, 7, 179]);
    expect(Array.from(d.tier)).toEqual([1, 4, 0]);
    expect(Array.from(d.vertical)).toEqual([2, 8, 0]);
    expect(Array.from(d.nest)).toEqual([NO_NEST, 3, 0]);
    expect(Array.from(d.trendId)).toEqual([17, 123456, 4294967295]);
  });

  it("refuses a blob that is not whole records", () => {
    expect(() => unpack(new ArrayBuffer(RECORD_BYTES + 3), 1)).toThrow();
  });
});

function cloud(points: { p: [number, number, number]; month: number; tier?: number; vertical?: number; nest?: number }[]): CloudData {
  const n = points.length;
  const d: CloudData = {
    n,
    pos: new Float32Array(n * 3),
    month: new Uint16Array(n),
    tier: new Uint8Array(n),
    vertical: new Uint8Array(n),
    nest: new Uint16Array(n),
    trendId: new Uint32Array(n),
  };
  points.forEach((q, i) => {
    d.pos.set(q.p, i * 3);
    d.month[i] = q.month;
    d.tier[i] = q.tier ?? 1;
    d.vertical[i] = q.vertical ?? 1;
    d.nest[i] = q.nest ?? NO_NEST;
    d.trendId[i] = i + 1;
  });
  return d;
}

const ALL: CloudFilter = { tierMask: ALL_BITS, verticalMask: ALL_BITS, monthEnd: 11, windowLen: 12, nest: -1 };

describe("pointState", () => {
  const d = cloud([
    { p: [0, 0, 0], month: 11 },
    { p: [0, 0, 0], month: 0 },
    { p: [0, 0, 0], month: 12 },
    { p: [0, 0, 0], month: 11, tier: 3 },
    { p: [0, 0, 0], month: 11, nest: 5 },
  ]);

  it("dims what lies outside the month window instead of dropping it", () => {
    expect(pointState(d, 0, ALL)).toBe(2);
    expect(pointState(d, 1, ALL)).toBe(2); // window 0..11 inclusive
    expect(pointState(d, 2, ALL)).toBe(1); // after the window: context
    expect(pointState(d, 1, { ...ALL, windowLen: 3 })).toBe(1);
  });

  it("removes filtered tiers entirely", () => {
    expect(pointState(d, 3, { ...ALL, tierMask: ALL_BITS & ~(1 << 3) })).toBe(0);
    expect(pointState(d, 0, { ...ALL, tierMask: ALL_BITS & ~(1 << 3) })).toBe(2);
  });

  it("keeps only the picked nest active", () => {
    expect(pointState(d, 4, { ...ALL, nest: 5 })).toBe(2);
    expect(pointState(d, 0, { ...ALL, nest: 5 })).toBe(1);
    expect(countActive(d, { ...ALL, nest: 5 })).toBe(1);
  });
});

describe("projectPoint", () => {
  const v: View = { yaw: 0, pitch: 0, zoom: 1, width: 800, height: 600 };

  it("puts the origin in the middle and +y up", () => {
    const o = projectPoint(0, 0, 0, v);
    expect(o.sx).toBe(400);
    expect(o.sy).toBe(300);
    expect(projectPoint(0, 1, 0, v).sy).toBeLessThan(300);
  });

  it("draws nearer points larger and further out, as the shader does", () => {
    const near = projectPoint(1, 0, -1, v);
    const far = projectPoint(1, 0, 1, v);
    expect(near.scale).toBeGreaterThan(far.scale);
    expect(near.sx - 400).toBeGreaterThan(far.sx - 400);
  });

  it("turns with the yaw like the SVG views", () => {
    const p = projectPoint(1, 0, 0, { ...v, yaw: Math.PI / 2 });
    expect(p.sx).toBeCloseTo(400, 6); // x rotated into depth
  });
});

describe("pickNearest", () => {
  const v: View = { yaw: 0, pitch: 0, zoom: 1, width: 800, height: 600 };
  const d = cloud([
    { p: [0, 0, 0], month: 11 },
    { p: [0.5, 0, 0], month: 11 },
    { p: [0.5, 0, 0], month: 0, tier: 2 },
  ]);

  it("finds the point under the cursor", () => {
    const at = projectPoint(0.5, 0, 0, v);
    expect(pickNearest(d, ALL, v, at.sx + 2, at.sy)).toBe(1);
  });

  it("returns -1 when nothing is within reach", () => {
    expect(pickNearest(d, ALL, v, 5, 5)).toBe(-1);
  });

  it("never picks a point that is filtered out or only context", () => {
    const at = projectPoint(0.5, 0, 0, v);
    const onlyTier2: CloudFilter = { ...ALL, tierMask: 1 << 2 };
    expect(pickNearest(d, onlyTier2, v, at.sx, at.sy)).toBe(2);
    expect(pickNearest(d, { ...onlyTier2, monthEnd: 11, windowLen: 1 }, v, at.sx, at.sy)).toBe(-1);
  });
});

describe("search: the sample becomes context", () => {
  const d = cloud([
    { p: [0, 0, 0], month: 11 },
    { p: [0.3, 0, 0], month: 11, tier: 3 },
  ]);

  it("dims every sample point while a search layer is shown", () => {
    expect(pointState(d, 0, { ...ALL, contextOnly: true })).toBe(1);
    expect(countActive(d, { ...ALL, contextOnly: true })).toBe(0);
  });

  it("still removes what the owner filtered out", () => {
    expect(pointState(d, 1, { ...ALL, contextOnly: true, tierMask: ALL_BITS & ~(1 << 3) })).toBe(0);
  });

  it("makes nothing in a context layer pickable", () => {
    const v: View = { yaw: 0, pitch: 0, zoom: 1, width: 800, height: 600 };
    const at = projectPoint(0, 0, 0, v);
    expect(pickNearest(d, { ...ALL, contextOnly: true }, v, at.sx, at.sy)).toBe(-1);
  });
});

describe("placed signals: finding search hits", () => {
  // three records with trend ids 5, 9, 40 (ascending, as the placed blob is stored)
  const blob = new Uint8Array(3 * RECORD_BYTES);
  const dv = new DataView(blob.buffer);
  [5, 9, 40].forEach((id, i) => {
    dv.setUint16(i * RECORD_BYTES, 1000 + i, true); // x, to recognise the record
    dv.setUint32(i * RECORD_BYTES + 12, id, true);
  });

  it("reads the trend ids", () => {
    expect(Array.from(recordIds(blob))).toEqual([5, 9, 40]);
  });

  it("binary-searches them", () => {
    const ids = recordIds(blob);
    expect(findSorted(ids, 5)).toBe(0);
    expect(findSorted(ids, 40)).toBe(2);
    expect(findSorted(ids, 7)).toBe(-1);
    expect(findSorted(new Uint32Array(0), 7)).toBe(-1);
  });

  it("collects the matching records and counts what has no place", () => {
    const r = collectRecords(blob, recordIds(blob), [40, 123, 5]);
    expect(r.found).toBe(2);
    expect(r.missing).toBe(1);
    const back = new DataView(r.records.buffer);
    expect(back.getUint32(12, true)).toBe(5); // blob order, not request order
    expect(back.getUint32(RECORD_BYTES + 12, true)).toBe(40);
    expect(back.getUint16(RECORD_BYTES, true)).toBe(1002);
  });
});

describe("navigation: pivot, pan, zoom at the cursor", () => {
  const angles = [
    [0, 0],
    [0.6, 0.3],
    [-1.1, 0.9],
    [2.5, -0.7],
  ];

  it("puts the pivot in the middle of the screen", () => {
    const v: View = { yaw: 0.6, pitch: 0.3, zoom: 2, width: 800, height: 600, center: [0.4, -0.2, 0.7] };
    const p = projectPoint(0.4, -0.2, 0.7, v);
    expect(p.sx).toBeCloseTo(400, 9);
    expect(p.sy).toBeCloseTo(300, 9);
  });

  it("screenToWorld is the exact inverse of the projection in the pivot plane", () => {
    for (const [yaw, pitch] of angles) {
      const v: View = { yaw, pitch, zoom: 1.7, width: 910, height: 564, center: [0.1, 0.2, -0.3] };
      const w = screenToWorld(123, -45, v);
      const p = projectPoint(0.1 + w[0], 0.2 + w[1], -0.3 + w[2], v);
      expect(p.sx).toBeCloseTo(455 + 123, 6);
      expect(p.sy).toBeCloseTo(282 - 45, 6);
      expect(p.depth).toBeCloseTo(0, 9);
    }
  });

  it("zoomAt keeps the point under the cursor where it is", () => {
    for (const [yaw, pitch] of angles) {
      const v: View = { yaw, pitch, zoom: 1.3, width: 910, height: 564, center: [0, 0.1, 0] };
      const mx = 700;
      const my = 120;
      const w = screenToWorld(mx - 455, my - 282, v);
      const target: [number, number, number] = [w[0], 0.1 + w[1], w[2]];
      const next = zoomAt(v, 4, mx, my);
      const p = projectPoint(...target, { ...v, ...next });
      expect(next.zoom).toBeCloseTo(5.2, 9);
      expect(p.sx).toBeCloseTo(mx, 6);
      expect(p.sy).toBeCloseTo(my, 6);
    }
  });

  it("zooming at the screen centre leaves the pivot alone (the + and − buttons)", () => {
    const v: View = { yaw: 0.6, pitch: 0.3, zoom: 1, width: 800, height: 600, center: [0.2, 0.3, 0.4] };
    const next = zoomAt(v, 1.25, 400, 300);
    expect(next.center).toEqual([0.2, 0.3, 0.4]);
  });

  it("clamps the zoom and does not move the picture once the limit is reached", () => {
    const v: View = { yaw: 0, pitch: 0, zoom: ZOOM_MAX, width: 800, height: 600, center: [0, 0, 0] };
    const next = zoomAt(v, 3, 100, 100);
    expect(next.zoom).toBe(ZOOM_MAX);
    next.center.forEach((c) => expect(c).toBeCloseTo(0, 12));
    expect(zoomAt({ ...v, zoom: ZOOM_MIN }, 0.1, 400, 300).zoom).toBe(ZOOM_MIN);
  });

  it("panBy moves the content with the drag", () => {
    for (const [yaw, pitch] of angles) {
      const v: View = { yaw, pitch, zoom: 2, width: 800, height: 600, center: [0, 0, 0] };
      const before = projectPoint(0, 0, 0, v);
      const moved = projectPoint(0, 0, 0, { ...v, center: panBy(v, 30, -20) });
      expect(moved.sx - before.sx).toBeCloseTo(30, 6);
      expect(moved.sy - before.sy).toBeCloseTo(-20, 6);
    }
  });

  it("hides and never picks what has come round behind the camera", () => {
    const v: View = { yaw: 0, pitch: 0, zoom: 1, width: 800, height: 600, center: [0, 0, 0] };
    const behind = projectPoint(0, 0, -(FOCAL - NEAR / 2), v);
    expect(behind.visible).toBe(false);
    const d = cloud([{ p: [0, 0, -(FOCAL - NEAR / 2)], month: 11 }]);
    expect(pickNearest(d, ALL, v, behind.sx, behind.sy, 50)).toBe(-1);
  });
});

describe("pickRing", () => {
  const rings = [
    { sx: 100, sy: 100, r: 10 },
    { sx: 104, sy: 100, r: 20 },
  ];

  it("hits the outline, not the inside", () => {
    expect(pickRing(rings, 110, 100)).toBe(0); // on ring 0's outline
    expect(pickRing(rings, 100, 100)).toBe(-1); // centre of ring 0: free for the points
  });

  it("prefers the nearer outline when two are in reach", () => {
    expect(pickRing(rings, 124, 100)).toBe(1);
    expect(pickRing(rings, 111, 100)).toBe(0);
  });

  it("returns -1 far from every ring", () => {
    expect(pickRing(rings, 300, 300)).toBe(-1);
  });
});
