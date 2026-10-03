"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ALL_BITS,
  FOCAL,
  NEAR,
  NO_NEST,
  countActive,
  nestColor,
  panBy,
  pickNearest,
  pickRing,
  projectPoint,
  screenToWorld,
  unpack,
  flowArcs,
  withoutHistory,
  viewRadius,
  zoomAt,
  type CloudData,
  type CloudFilter,
  type CloudMeta,
  type LayoutView,
  layoutView,
  MATCH_MEANING,
  MATCH_TEXT,
  type SearchMode,
  decodeSearchBody,
  matchWeight,
  type Vec3,
  type View,
} from "@/lib/spaceCloud";
import { VERTICALS } from "@/lib/types";

/**
 * Stage 3 of the signal space: the sampled signals themselves, ~108,000 points.
 *
 * WebGL2 by hand, no library — for the same reason stages 1 and 2 are plain
 * SVG: one buffer, one shader, a rotation and a perspective divide. The vertex
 * shader is the GPU twin of `projectPoint` / `pointState` in lib/spaceCloud.ts
 * and MUST stay line-for-line equal to them: picking runs on the CPU, and a
 * point drawn where the CPU does not expect it would open the wrong article.
 *
 * Additive blending on the dark ground turns overlap into brightness, so the
 * density of the cloud is visible without a separate density estimate.
 */

const TIER_COLOR: Record<string, string> = {
  science: "#a78bfa",
  patent: "#60a5fa",
  funding: "#f0a13a",
  market: "#d4ff3a",
};
const NONE_COLOR = "#8a8d82";
const TIER_LABEL: Record<string, string> = {
  science: "research",
  patent: "patents",
  funding: "funding",
  market: "market",
};
const MONTHS_PER_SEC = 6;
/** How long the cursor must rest on a point before its title appears. */
const TOOLTIP_DELAY_MS = 1000;
/** Near points are drawn larger, but never more than this — with the pivot at
 *  the rim of the cloud the perspective scale can reach FOCAL / NEAR ≈ 14. */
const MAX_POINT_SCALE = 2.5;

type ColorBy = "tier" | "vertical" | "nest";

function hex(h: string): [number, number, number] {
  const n = parseInt(h.replace("#", ""), 16);
  return [((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255];
}

const VERT_SRC = `#version 300 es
in vec3 aPos;
in vec4 aMeta; // month, tier, vertical, nest
in vec2 aHit;   // x: 0 = sample, else MATCH_* flags of a search match; y: opacity factor
uniform float uYaw, uPitch, uRadius, uFocal, uMonthEnd, uWindowLen, uNest, uGhosts, uDpr, uAlpha;
uniform float uNear, uSearch, uMaxScale, uHitSize, uGhostAlpha, uBaseSize, uMatchColor;
uniform vec3 uCenter;
uniform vec2 uViewport;
uniform int uTierMask, uVertMask, uColorBy;
uniform vec3 uTierColors[5];
uniform vec3 uVertColors[9];
out vec4 vColor;

vec3 hsl(float h, float s, float l) {
  vec3 k = mod(vec3(0.0, 8.0, 4.0) + h * 12.0, 12.0);
  float a = s * min(l, 1.0 - l);
  return l - a * max(vec3(-1.0), min(min(k - 3.0, 9.0 - k), vec3(1.0)));
}

void main() {
  int tier = int(aMeta.y + 0.5);
  int vert = int(aMeta.z + 0.5);
  // pointState(): filters remove, the month window only dims
  float state = 2.0;
  if (((uTierMask >> tier) & 1) == 0 || ((uVertMask >> vert) & 1) == 0) state = 0.0;
  else if (uNest >= 0.0 && abs(aMeta.w - uNest) > 0.5) state = 1.0;
  else if (uSearch > 0.5 && aHit.x < 0.5) state = 1.0;
  else if (!(aMeta.x <= uMonthEnd && aMeta.x > uMonthEnd - uWindowLen)) state = 1.0;
  if (state < 0.5 || (state < 1.5 && uGhosts < 0.5)) {
    gl_Position = vec4(2.0, 2.0, 2.0, 1.0);
    gl_PointSize = 0.0;
    vColor = vec4(0.0);
    return;
  }
  // projectPoint(): pivot first, then yaw about y, pitch about x, perspective
  vec3 p = aPos - uCenter;
  float cy = cos(uYaw), sy = sin(uYaw);
  float x1 = p.x * cy + p.z * sy;
  float z1 = -p.x * sy + p.z * cy;
  float cp = cos(uPitch), sp = sin(uPitch);
  float y2 = p.y * cp - z1 * sp;
  float z2 = p.y * sp + z1 * cp;
  if (uFocal + z2 <= uNear) { // behind the near plane: would come out mirrored
    gl_Position = vec4(2.0, 2.0, 2.0, 1.0);
    gl_PointSize = 0.0;
    vColor = vec4(0.0);
    return;
  }
  float scale = uFocal / (uFocal + z2);
  gl_Position = vec4(x1 * uRadius * scale / (uViewport.x * 0.5),
                     y2 * uRadius * scale / (uViewport.y * 0.5), 0.0, 1.0);
  vec3 c;
  if (uColorBy == 0) c = uTierColors[tier];
  else if (uColorBy == 1) c = uVertColors[vert];
  else c = aMeta.w > 65534.5 ? vec3(0.32) : hsl(mod(aMeta.w * 137.508, 360.0) / 360.0, 0.65, 0.62);
  // "Both" search: a match is coloured by where it came from, not by its tier
  if (uMatchColor > 0.5 && aHit.x > 0.5) {
    int m = int(aHit.x + 0.5);
    c = m == 3 ? vec3(0.831, 1.0, 0.227) : (m == 1 ? vec3(0.957, 0.957, 0.933) : vec3(0.31, 0.82, 1.0));
  }
  // (not "active": that is a reserved word in GLSL ES 3.0)
  bool inWindow = state > 1.5;
  // With a search running every lit point is a match: drawn larger, with its
  // own size and opacity (both fall with the number of matches, see hitStyle),
  // and the context fades further — or a handful of matches disappears among
  // 100,000 context points, while thousands would melt into white.
  bool searching = uSearch > 0.5;
  gl_PointSize = (inWindow ? (searching ? uHitSize : uBaseSize) : uBaseSize * 0.57) * min(scale, uMaxScale) * uDpr;
  // a vector-only match fades with its rank (aHit.y, see matchWeight)
  vColor = vec4(c, inWindow ? uAlpha * (aHit.x > 0.5 ? aHit.y : 1.0) : (searching ? 0.5 * uGhostAlpha : uGhostAlpha));
}`;

const FRAG_SRC = `#version 300 es
precision mediump float;
in vec4 vColor;
out vec4 outColor;
void main() {
  vec2 d = gl_PointCoord - 0.5;
  float r = dot(d, d);
  if (r > 0.25) discard;
  float a = vColor.a * smoothstep(0.25, 0.1, r);
  outColor = vec4(vColor.rgb * a, a);
}`;

/** One set of points on the GPU: the sample, or the matches of a search. */
interface Layer {
  vao: WebGLVertexArrayObject;
  bufs: WebGLBuffer[];
  n: number;
}

interface Gl {
  gl: WebGL2RenderingContext;
  prog: WebGLProgram;
  loc: Record<string, WebGLUniformLocation | null>;
  sample: Layer;
  hits: Layer | null;
}

function compile(gl: WebGL2RenderingContext, type: number, src: string): WebGLShader {
  const s = gl.createShader(type)!;
  gl.shaderSource(s, src);
  gl.compileShader(s);
  if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) {
    throw new Error(gl.getShaderInfoLog(s) || "shader compile failed");
  }
  return s;
}

/**
 * Upload a point set. `hit` is the aHit attribute (2 floats per point): null
 * for the sample (context while a search runs, all zero), otherwise the match
 * flags and opacity factor of each search match.
 */
function makeLayer(
  gl: WebGL2RenderingContext,
  prog: WebGLProgram,
  d: CloudData,
  hit: Float32Array | null
): Layer {
  const vao = gl.createVertexArray()!;
  gl.bindVertexArray(vao);
  const attrib = (name: string, data: Float32Array, size: number): WebGLBuffer => {
    const buf = gl.createBuffer()!;
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, data, gl.STATIC_DRAW);
    const loc = gl.getAttribLocation(prog, name);
    gl.enableVertexAttribArray(loc);
    gl.vertexAttribPointer(loc, size, gl.FLOAT, false, 0, 0);
    return buf;
  };
  const meta = new Float32Array(d.n * 4);
  for (let i = 0; i < d.n; i++) {
    meta[i * 4] = d.month[i];
    meta[i * 4 + 1] = d.tier[i];
    meta[i * 4 + 2] = d.vertical[i];
    meta[i * 4 + 3] = d.nest[i];
  }
  const bufs = [
    attrib("aPos", d.pos, 3),
    attrib("aMeta", meta, 4),
    attrib("aHit", hit ?? new Float32Array(d.n * 2), 2),
  ];
  gl.bindVertexArray(null);
  return { vao, bufs, n: d.n };
}

function dropLayer(gl: WebGL2RenderingContext, l: Layer | null): void {
  if (!l) return;
  gl.deleteVertexArray(l.vao);
  for (const b of l.bufs) gl.deleteBuffer(b);
}

function setupGl(canvas: HTMLCanvasElement, d: CloudData): Gl {
  const gl = canvas.getContext("webgl2", { antialias: false, premultipliedAlpha: true });
  if (!gl) throw new Error("WebGL2 is not available in this browser");
  const prog = gl.createProgram()!;
  gl.attachShader(prog, compile(gl, gl.VERTEX_SHADER, VERT_SRC));
  gl.attachShader(prog, compile(gl, gl.FRAGMENT_SHADER, FRAG_SRC));
  gl.linkProgram(prog);
  if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) {
    throw new Error(gl.getProgramInfoLog(prog) || "shader link failed");
  }
  gl.useProgram(prog);
  gl.enable(gl.BLEND);
  gl.blendFunc(gl.ONE, gl.ONE); // additive: overlap becomes brightness
  gl.disable(gl.DEPTH_TEST);

  const names = [
    "uYaw", "uPitch", "uRadius", "uFocal", "uMonthEnd", "uWindowLen", "uNest", "uGhosts",
    "uDpr", "uAlpha", "uViewport", "uTierMask", "uVertMask", "uColorBy", "uTierColors", "uVertColors",
    "uCenter", "uNear", "uSearch", "uMaxScale", "uHitSize", "uGhostAlpha", "uBaseSize", "uMatchColor",
  ];
  const loc: Record<string, WebGLUniformLocation | null> = {};
  for (const u of names) loc[u] = gl.getUniformLocation(prog, u);
  return { gl, prog, loc, sample: makeLayer(gl, prog, d, null), hits: null };
}

interface PointDetail {
  id: number;
  title: string;
  source_name: string | null;
  source_url: string | null;
  slug: string | null;
  status: string | null;
  date: string | null;
  vertical: string | null;
  signal_type: string | null;
  history?: { layer: string; cited: boolean; weight: number | null };
}

function fmtMonth(m: string | undefined): string {
  if (!m) return "";
  const [y, mm] = m.split("-");
  const names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return `${names[Number(mm) - 1] ?? mm} ${y}`;
}

export default function ClusterCloud({ meta }: { meta: CloudMeta }) {
  const lastMonth = Math.max(0, meta.months.length - 1);
  const [rawData, setData] = useState<CloudData | null>(null);
  // The history sample (03.10.): patents 1990-2022 and research 2010-2022 drawn
  // into the cloud from history_vectors. Hiding it rebuilds the point set without
  // them (rare, so a CPU copy is fine) — the layout itself does not change.
  const [showPast, setShowPast] = useState(true);
  const data = useMemo(
    () => (rawData && !showPast ? withoutHistory(rawData) : rawData),
    [rawData, showPast]
  );
  const [showFlows, setShowFlows] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [yaw, setYaw] = useState(0.6);
  const [pitch, setPitch] = useState(0.3);
  // zoom and pivot change together (zoom toward the cursor moves both)
  const [cam, setCam] = useState<{ zoom: number; center: Vec3 }>({ zoom: 1, center: [0, 0, 0] });
  const [spin, setSpin] = useState(true);
  const [playing, setPlaying] = useState(false);
  const [monthEnd, setMonthEnd] = useState(lastMonth);
  const [windowLen, setWindowLen] = useState(12);
  const [ghosts, setGhosts] = useState(true);
  const [showNests, setShowNests] = useState(true);
  // The sample (600 a month) defines the layout; "All signals" draws every signal
  // of the window placed into it (1.5M, ~24 MB) — then brightness is volume.
  // Default on since 28.09. (owner: the cloud should show every signal); a run
  // without placed signals falls back to the sample.
  const [everything, setEverything] = useState(meta.nAll > 0);
  const loaded = useRef(new Map<string, CloudData>());
  // Two arrangements of the same points (since 28.09.): the default groups by
  // topic across tiers, the second keeps the writing-style continents of 27.09.
  const [altLayout, setAltLayout] = useState(false);
  const L = useMemo(() => layoutView(meta, altLayout), [meta, altLayout]);
  const [colorBy, setColorBy] = useState<ColorBy>("tier");
  const [tierMask, setTierMask] = useState(ALL_BITS);
  const [vertMask, setVertMask] = useState(ALL_BITS);
  const [nestSel, setNestSel] = useState(-1);
  const [hover, setHover] = useState(-1);
  const [selected, setSelected] = useState(-1);
  const [detail, setDetail] = useState<PointDetail | null>(null);
  const [size, setSize] = useState({ w: 900, h: 560 });
  const [hovering, setHovering] = useState(false);
  const [tip, setTip] = useState<{ x: number; y: number; title: string; sub: string } | null>(null);
  const [hoverRing, setHoverRing] = useState(-1);
  const [query, setQuery] = useState("");
  // A search is a second point layer: every match in the whole corpus, placed
  // in this cloud (not only the ~6 % of them that are in the sample).
  const [hitData, setHitData] = useState<CloudData | null>(null);
  const [searchInfo, setSearchInfo] = useState<{
    outside: number;
    bySource: { text: number; research: number; patents: number; meaning?: number };
    failed: string[];
    mode: SearchMode;
    kinds: { text: number; meaning: number; both: number };
    simRange: [number, number] | null;
  } | null>(null);
  // Keyword search, vector search ("meaning": the N nearest signals), or both.
  const [searchMode, setSearchMode] = useState<SearchMode>("both");
  const [meaningN, setMeaningN] = useState<number>(1000);
  const [searchNote, setSearchNote] = useState<string | null>(null);

  const wrapRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const glRef = useRef<Gl | null>(null);
  const drag = useRef<{ x: number; y: number; moved: boolean; pan: boolean } | null>(null);
  const pickFrame = useRef(0);
  const tipTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const tipTarget = useRef("");
  const details = useRef(new Map<number, PointDetail>());
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const searchSeq = useRef(0);
  const searchOn = useRef(false);

  // code -> name tables stored with the run, turned into shader colour arrays
  const tierByCode = useMemo(() => {
    const out: (string | null)[] = [null, null, null, null, null];
    for (const [code, name] of Object.entries(meta.tierCodes)) out[Number(code)] = name;
    return out;
  }, [meta.tierCodes]);
  const vertByCode = useMemo(() => {
    const out: (string | null)[] = new Array(9).fill(null);
    for (const [code, name] of Object.entries(meta.verticalCodes)) out[Number(code)] = name;
    return out;
  }, [meta.verticalCodes]);
  const tierColors = useMemo(
    () => new Float32Array(tierByCode.flatMap((t) => hex(t ? TIER_COLOR[t] ?? NONE_COLOR : NONE_COLOR))),
    [tierByCode]
  );
  const vertColors = useMemo(
    () =>
      new Float32Array(
        vertByCode.flatMap((v) => hex(VERTICALS.find((x) => x.id === v)?.color ?? NONE_COLOR))
      ),
    [vertByCode]
  );

  // ---- data: fetched only now that the Cloud view is open (and the full set
  // only when asked for); both sets stay in memory, so switching back is instant
  useEffect(() => {
    let cancelled = false;
    const key = `${meta.runId}:${everything ? "all" : "sample"}:${L.key}`;
    const reset = () => {
      // indices point into the previous set
      setSelected(-1);
      setHover(-1);
      setDetail(null);
    };
    const have = loaded.current.get(key);
    if (have) {
      queueMicrotask(() => {
        if (cancelled) return;
        reset();
        setData(have);
      });
      return () => {
        cancelled = true;
      };
    }
    queueMicrotask(() => {
      if (cancelled) return;
      reset();
      setData(null);
    });
    fetch(
      `/api/foresight/space/points?run=${meta.runId}${everything ? "&all=1" : ""}${L.key ? "&layout=alt" : ""}`
    )
      .then((r) => {
        if (!r.ok) throw new Error(`points request failed (${r.status})`);
        return r.arrayBuffer();
      })
      .then((buf) => {
        const d = unpack(buf, L.coordRange);
        loaded.current.set(key, d);
        if (!cancelled) setData(d);
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
  }, [meta.runId, L.key, L.coordRange, everything]);

  // indices of the previous point set mean nothing in the new one
  useEffect(() => {
    queueMicrotask(() => {
      setSelected(-1);
      setHover(-1);
      setDetail(null);
    });
  }, [showPast]);

  // ---- canvas follows its container
  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const w = Math.max(320, Math.round(entries[0].contentRect.width));
      setSize({ w, h: Math.round(w * 0.62) });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // ---- GL objects, once per dataset
  useEffect(() => {
    if (!data || !canvasRef.current) return;
    try {
      glRef.current = setupGl(canvasRef.current, data);
    } catch (e) {
      queueMicrotask(() => setError(e instanceof Error ? e.message : String(e)));
    }
    return () => {
      glRef.current = null;
    };
  }, [data]);

  const view: View = useMemo(
    () => ({ yaw, pitch, zoom: cam.zoom, center: cam.center, width: size.w, height: size.h }),
    [yaw, pitch, cam, size]
  );
  // the wheel listener is attached once and reads the current view from here
  const viewRef = useRef(view);
  useEffect(() => {
    viewRef.current = view;
  }, [view]);
  // The sample draws as context while a search runs; picking, tooltip, click and
  // double-click then work on the matches (`layer`), never on the context.
  const filter: CloudFilter = useMemo(
    () => ({ tierMask, verticalMask: vertMask, monthEnd, windowLen, nest: nestSel, contextOnly: !!hitData }),
    [tierMask, vertMask, monthEnd, windowLen, nestSel, hitData]
  );
  const hitFilter: CloudFilter = useMemo(() => ({ ...filter, contextOnly: false }), [filter]);
  const layer = hitData ?? data;
  const layerFilter = hitData ? hitFilter : filter;

  const active = useMemo(() => (layer ? countActive(layer, layerFilter) : 0), [layer, layerFilter]);
  // Additive blending turns overlap into brightness — which saturates to white
  // when every month is lit at once (108k points). The per-point opacity
  // therefore falls with the number of lit points, so a 3-month window and the
  // whole archive both keep a readable density gradient.
  const alpha = hitData
    ? Math.min(0.85, Math.max(0.06, 0.55 * Math.pow(1500 / Math.max(1, active), 0.6)))
    : Math.min(0.6, Math.max(everything ? 0.012 : 0.035, 0.5 * Math.pow(7200 / Math.max(1, active), 0.7)));
  // Context (out-of-window) points: 14x as many with every signal loaded. The
  // floor stays above what an 8-bit framebuffer still adds up (~1/255 per point).
  const ghostAlpha = everything ? 0.012 : 0.045;
  const baseSize = everything ? 2.0 : 2.8;
  // a few matches large, tens of thousands small — each stays a point
  const hitSize = Math.min(6, Math.max(2.8, 5.5 * Math.pow(2000 / Math.max(1, active), 0.25)));

  // ---- search matches into their GPU buffer (declared before the draw effect,
  // so a new result is uploaded before the frame that shows it)
  useEffect(() => {
    const g = glRef.current;
    if (!g) return;
    dropLayer(g.gl, g.hits);
    let attr: Float32Array | null = null;
    if (hitData) {
      attr = new Float32Array(hitData.n * 2);
      const [hi, lo] = searchInfo?.simRange ?? [1, 0];
      for (let i = 0; i < hitData.n; i++) {
        const m = hitData.match ? hitData.match[i] : MATCH_TEXT;
        attr[i * 2] = m || MATCH_TEXT;
        attr[i * 2 + 1] = matchWeight(hitData.sim ? hitData.sim[i] : 0, m, lo, hi);
      }
    }
    g.hits = hitData && attr ? makeLayer(g.gl, g.prog, hitData, attr) : null;
  }, [data, hitData, searchInfo]);

  // ---- draw whenever anything visible changes
  useEffect(() => {
    const g = glRef.current;
    const canvas = canvasRef.current;
    if (!g || !canvas) return;
    const dpr = window.devicePixelRatio || 1;
    const W = Math.round(size.w * dpr);
    const H = Math.round(size.h * dpr);
    if (canvas.width !== W || canvas.height !== H) {
      canvas.width = W;
      canvas.height = H;
    }
    const { gl, loc } = g;
    gl.viewport(0, 0, W, H);
    gl.clearColor(0.039, 0.047, 0.039, 1);
    gl.clear(gl.COLOR_BUFFER_BIT);
    gl.uniform1f(loc.uYaw, yaw);
    gl.uniform1f(loc.uPitch, pitch);
    gl.uniform1f(loc.uRadius, viewRadius(view));
    gl.uniform1f(loc.uFocal, FOCAL);
    gl.uniform1f(loc.uMonthEnd, monthEnd);
    gl.uniform1f(loc.uWindowLen, windowLen);
    gl.uniform1f(loc.uNest, nestSel);
    gl.uniform1f(loc.uGhosts, ghosts ? 1 : 0);
    gl.uniform1f(loc.uDpr, dpr);
    gl.uniform1f(loc.uAlpha, alpha);
    gl.uniform2f(loc.uViewport, size.w, size.h);
    gl.uniform1i(loc.uTierMask, tierMask);
    gl.uniform1i(loc.uVertMask, vertMask);
    gl.uniform1i(loc.uColorBy, colorBy === "tier" ? 0 : colorBy === "vertical" ? 1 : 2);
    gl.uniform3fv(loc.uTierColors, tierColors);
    gl.uniform3fv(loc.uVertColors, vertColors);
    gl.uniform3f(loc.uCenter, cam.center[0], cam.center[1], cam.center[2]);
    gl.uniform1f(loc.uNear, NEAR);
    gl.uniform1f(loc.uSearch, hitData ? 1 : 0);
    gl.uniform1f(loc.uMaxScale, MAX_POINT_SCALE);
    gl.uniform1f(loc.uHitSize, hitSize);
    gl.uniform1f(loc.uMatchColor, hitData && searchInfo?.mode === "both" ? 1 : 0);
    gl.uniform1f(loc.uGhostAlpha, ghostAlpha);
    gl.uniform1f(loc.uBaseSize, baseSize);
    gl.bindVertexArray(g.sample.vao);
    gl.drawArrays(gl.POINTS, 0, g.sample.n);
    if (g.hits) {
      gl.bindVertexArray(g.hits.vao);
      gl.drawArrays(gl.POINTS, 0, g.hits.n);
    }
    gl.bindVertexArray(null);
  }, [data, view, yaw, pitch, cam, size, monthEnd, windowLen, nestSel, ghosts, tierMask, vertMask, colorBy, tierColors, vertColors, alpha, hitSize, hitData, ghostAlpha, baseSize, searchInfo]);

  // ---- clocks: spin and play
  // The spin pauses while the cursor rests on the canvas: it is there to show
  // depth when nobody is looking closely, and a moving target cannot be read,
  // hovered or clicked.
  useEffect(() => {
    if (!spin || hovering) return;
    let raf = 0;
    let last = performance.now();
    const step = (t: number) => {
      const dt = (t - last) / 1000;
      last = t;
      setYaw((y) => y + dt * 0.15);
      raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [spin, hovering]);

  useEffect(() => {
    if (!playing) return;
    let raf = 0;
    let last = performance.now();
    const step = (t: number) => {
      if ((t - last) / 1000 >= 1 / MONTHS_PER_SEC) {
        last = t;
        setMonthEnd((m) => (m >= lastMonth ? Math.min(lastMonth, windowLen - 1) : m + 1));
      }
      raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [playing, lastMonth, windowLen]);

  // ---- nest rings in CSS pixels: drawn by the SVG overlay, hit on the CPU
  const rings = useMemo(() => {
    const maxM = Math.max(1, ...L.nests.map((n) => n.members));
    return L.nests
      .map((n, k) => ({ n, k, p: projectPoint(n.x, n.y, n.z, view) }))
      .filter((r) => r.n.members > 0 && r.p.visible)
      .map((r) => ({
        ...r,
        p: { ...r.p, scale: Math.min(r.p.scale, MAX_POINT_SCALE) },
        radius: 5 + 14 * Math.sqrt(r.n.members / maxM),
      }));
  }, [L.nests, view]);
  // Names for the largest pockets only, and only where they do not land on a
  // name already placed — the rings crowd at the research/market seam.
  const labelled = useMemo(() => {
    const ids = new Set<number>();
    const taken: { x: number; y: number }[] = [];
    for (const r of [...rings].sort((a, b) => b.n.members - a.n.members)) {
      if (ids.size >= 6) break;
      const y = r.p.sy - r.radius * r.p.scale - 4;
      if (taken.some((t) => Math.abs(t.x - r.p.sx) < 170 && Math.abs(t.y - y) < 16)) continue;
      taken.push({ x: r.p.sx, y });
      ids.add(r.k);
    }
    return ids;
  }, [rings]);
  // Citation flows between pockets: arcs from the citing pocket to the cited one,
  // drawn only between rings that are on screen.
  const arcs = useMemo(() => {
    if (!showFlows || !showNests || !meta.flows?.pairs.length) return [];
    const at = new Map(rings.map((r) => [r.k, { sx: r.p.sx, sy: r.p.sy }]));
    const pairs =
      nestSel >= 0 ? meta.flows.pairs.filter(([a, b]) => a === nestSel || b === nestSel) : meta.flows.pairs;
    return flowArcs(pairs, at, { top: nestSel >= 0 ? 24 : 40 });
  }, [showFlows, showNests, meta.flows, rings, nestSel]);
  const ringHits = useMemo(
    () => (showNests ? rings.map((r) => ({ sx: r.p.sx, sy: r.p.sy, r: r.radius * r.p.scale })) : []),
    [rings, showNests]
  );

  // ---- details for the panel and the tooltip, fetched once per signal
  const loadDetail = useCallback(
    (i: number): Promise<PointDetail | null> => {
      if (!layer) return Promise.resolve(null);
      const id = layer.trendId[i];
      const hit = details.current.get(id);
      if (hit) return Promise.resolve(hit);
      return fetch(`/api/foresight/space/point?id=${id}`)
        .then((r) => (r.ok ? (r.json() as Promise<PointDetail>) : null))
        .then((d) => {
          if (d) details.current.set(id, d);
          return d;
        })
        .catch(() => null);
    },
    [layer]
  );

  const hideTip = useCallback(() => {
    if (tipTimer.current) clearTimeout(tipTimer.current);
    tipTimer.current = null;
    tipTarget.current = "";
    setTip(null);
  }, []);

  /** Start the one-second clock for whatever is under the cursor ("p<i>" for a
   *  signal, "r<k>" for a ring, "" for nothing); something else restarts it. */
  const scheduleTip = useCallback(
    (key: string, x: number, y: number, load: () => Promise<{ title: string; sub: string } | null>) => {
      if (key === tipTarget.current) return;
      hideTip();
      if (!key) return;
      tipTarget.current = key;
      tipTimer.current = setTimeout(() => {
        load().then((t) => {
          if (t && tipTarget.current === key) setTip({ x, y, ...t });
        });
      }, TOOLTIP_DELAY_MS);
    },
    [hideTip]
  );

  // ---- pointer: drag turns, Shift/right/middle-drag moves, a still click
  // picks, a resting cursor shows the title, double-click re-centres
  const localXY = (e: { clientX: number; clientY: number }) => {
    const r = canvasRef.current!.getBoundingClientRect();
    return { x: e.clientX - r.left, y: e.clientY - r.top };
  };

  const onPointerDown = useCallback(
    (e: React.PointerEvent<HTMLCanvasElement>) => {
      const pan = e.shiftKey || e.button === 1 || e.button === 2;
      drag.current = { x: e.clientX, y: e.clientY, moved: false, pan };
      hideTip();
      e.currentTarget.setPointerCapture(e.pointerId);
    },
    [hideTip]
  );

  const onPointerMove = useCallback(
    (e: React.PointerEvent<HTMLCanvasElement>) => {
      const d = drag.current;
      if (d) {
        const dx = e.clientX - d.x;
        const dy = e.clientY - d.y;
        if (Math.abs(dx) + Math.abs(dy) > 2) {
          d.moved = true;
          setSpin(false);
        }
        if (d.pan) {
          setCam((c) => ({ ...c, center: panBy({ ...viewRef.current, zoom: c.zoom, center: c.center }, dx, dy) }));
        } else {
          setYaw((y) => y + dx * 0.008);
          setPitch((p) => Math.max(-1.3, Math.min(1.3, p + dy * 0.006)));
        }
        drag.current = { ...d, x: e.clientX, y: e.clientY };
        return;
      }
      if (!data) return;
      const { x, y } = localXY(e);
      cancelAnimationFrame(pickFrame.current);
      pickFrame.current = requestAnimationFrame(() => {
        const g = pickRing(ringHits, x, y);
        if (g >= 0) {
          const n = rings[g].n;
          setHover(-1);
          setHoverRing(rings[g].k);
          scheduleTip(`r${rings[g].k}`, x, y, () =>
            Promise.resolve({
              title: n.name,
              sub: `pocket · ${n.members.toLocaleString("en-US")} sampled signals · click to light up, double-click to centre`,
            })
          );
          return;
        }
        setHoverRing(-1);
        const i = pickNearest(layer!, layerFilter, view, x, y);
        setHover(i);
        scheduleTip(i >= 0 ? `p${i}` : "", x, y, () =>
          loadDetail(i).then((d) =>
            d
              ? { title: d.title, sub: [d.source_name, d.date, matchLabel(layer, i)].filter(Boolean).join(" · ") }
              : null
          )
        );
      });
    },
    [data, layer, layerFilter, view, scheduleTip, ringHits, rings, loadDetail]
  );

  const onPointerUp = useCallback(
    (e: React.PointerEvent<HTMLCanvasElement>) => {
      const d = drag.current;
      drag.current = null;
      if (!d || d.moved || d.pan || !layer || e.button !== 0) return;
      const { x, y } = localXY(e);
      const g = pickRing(ringHits, x, y);
      if (g >= 0) {
        if (e.detail > 1) return; // the second click of a double-click
        const k = rings[g].k;
        setNestSel((cur) => (cur === k ? -1 : k));
        return;
      }
      const i = pickNearest(layer, layerFilter, view, x, y, 8);
      setSelected(i);
      setDetail(null);
      if (i >= 0) {
        setSpin(false);
        loadDetail(i).then((dd) => setDetail(dd));
      }
    },
    [layer, layerFilter, view, loadDetail, ringHits, rings]
  );

  /** Double-click: the point under the cursor becomes the pivot — or, over
   *  empty space, the spot on the pivot plane. Zoom then goes in there. */
  const onDoubleClick = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      if (!data) return;
      const { x, y } = localXY(e);
      const g = pickRing(ringHits, x, y);
      if (g >= 0) {
        const n = rings[g].n;
        setCam((c) => ({ ...c, center: [n.x, n.y, n.z] }));
        return;
      }
      const i = layer ? pickNearest(layer, layerFilter, view, x, y, 10) : -1;
      if (layer && i >= 0) {
        setCam((c) => ({ ...c, center: [layer.pos[i * 3], layer.pos[i * 3 + 1], layer.pos[i * 3 + 2]] }));
      } else {
        const w = screenToWorld(x - view.width / 2, y - view.height / 2, view);
        setCam((c) => ({ ...c, center: [c.center[0] + w[0], c.center[1] + w[1], c.center[2] + w[2]] }));
      }
    },
    [data, layer, layerFilter, view, ringHits, rings]
  );

  // ---- mouse wheel: zoom toward the cursor. A native listener, because React
  // registers wheel handlers as passive and the page would scroll along.
  useEffect(() => {
    const el = canvasRef.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const r = el.getBoundingClientRect();
      const mx = e.clientX - r.left;
      const my = e.clientY - r.top;
      const dy = e.deltaMode === 1 ? e.deltaY * 16 : e.deltaY;
      const f = Math.exp(-dy * 0.0015);
      setCam((c) => zoomAt({ ...viewRef.current, zoom: c.zoom, center: c.center }, f, mx, my));
      hideTip();
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [error, hideTip]);

  const zoomButton = (factor: number) =>
    setCam((c) => zoomAt({ ...view, zoom: c.zoom, center: c.center }, factor, view.width / 2, view.height / 2));

  // ---- search: the feed's full-text search over the WHOLE corpus (titles,
  // summaries, tags, research and patent abstracts); every match comes back as
  // a placed point, not only the ~6 % of them that happen to be in the sample.
  const runSearch = useCallback(
    (text: string, lv: LayoutView = L, mode: SearchMode = searchMode, n: number = meaningN) => {
      const qtext = text.trim();
      const seq = ++searchSeq.current;
      // any selection belongs to the layer that is about to change
      setSelected(-1);
      setDetail(null);
      setHover(-1);
      if (qtext.length < 2 || !data) {
        searchOn.current = false;
        setHitData(null);
        setSearchInfo(null);
        setSearchNote(null);
        return;
      }
      setSearchNote("searching…");
      fetch(
        `/api/foresight/space/search?run=${meta.runId}&q=${encodeURIComponent(qtext)}` +
          `${lv.key ? "&layout=alt" : ""}&mode=${mode}&n=${n}`
      )
        .then(async (r) => {
          if (!r.ok) {
            const j = (await r.json().catch(() => ({}))) as { error?: string };
            throw new Error(j.error ?? `search failed (${r.status})`);
          }
          const sim = (r.headers.get("X-Sim") ?? "").split(",").filter(Boolean).map(Number);
          const info = {
            outside: Number(r.headers.get("X-Outside") ?? 0),
            bySource: JSON.parse(r.headers.get("X-Sources") ?? "{}"),
            failed: (r.headers.get("X-Failed") ?? "").split(",").filter(Boolean),
            mode,
            kinds: JSON.parse(r.headers.get("X-Kinds") ?? '{"text":0,"meaning":0,"both":0}'),
            simRange: sim.length === 2 ? ([sim[0], sim[1]] as [number, number]) : null,
          };
          return { buf: await r.arrayBuffer(), info };
        })
        .then(({ buf, info }) => {
          if (seq !== searchSeq.current) return; // a newer query is on its way
          const body = decodeSearchBody(buf);
          const hitsLayer: CloudData = { ...unpack(body.records, lv.coordRange), sim: body.sim, match: body.match };
          // A NEW search opens the window to every month, so all matches are
          // visible at once; narrowing it (and Play) is then the owner's move.
          // Refining the query keeps whatever window was chosen meanwhile.
          if (!searchOn.current) setWindowLen(meta.months.length);
          searchOn.current = true;
          setHitData(hitsLayer.n ? hitsLayer : null);
          setSearchInfo(info);
          setSearchNote(hitsLayer.n ? null : "no matches");
        })
        .catch((e: unknown) => {
          if (seq === searchSeq.current) setSearchNote(e instanceof Error ? e.message : "search failed");
        });
    },
    [data, meta.runId, meta.months.length, L, searchMode, meaningN]
  );

  const onQuery = (v: string) => {
    setQuery(v);
    if (searchTimer.current) clearTimeout(searchTimer.current);
    searchTimer.current = setTimeout(() => runSearch(v), 350);
  };

  const mark = selected >= 0 ? selected : hover;
  const markProj =
    layer && mark >= 0 && mark < layer.n
      ? projectPoint(layer.pos[mark * 3], layer.pos[mark * 3 + 1], layer.pos[mark * 3 + 2], view)
      : null;
  const markPos = markProj && markProj.visible ? markProj : null;

  const btn = (on: boolean) =>
    `font-mono text-[10px] uppercase tracking-[0.14em] px-3 py-1.5 border transition-colors ${
      on ? "text-accent border-accent bg-accent/10" : "text-muted border-border hover:text-paper"
    }`;
  const chip = (on: boolean) =>
    `font-mono text-[10px] uppercase tracking-[0.1em] px-2 py-1 border transition-colors ${
      on ? "text-paper border-border bg-card" : "text-muted/60 border-border/50 line-through"
    }`;

  const sel = layer && selected >= 0 && selected < layer.n ? selected : -1;
  const selTier = layer && sel >= 0 ? tierByCode[layer.tier[sel]] : null;
  const selNest = layer && sel >= 0 && layer.nest[sel] !== NO_NEST ? meta.nests[layer.nest[sel]] : null;
  const nestMembers = useMemo(
    () => (data ? Array.from(data.nest).filter((x) => x !== NO_NEST).length : 0),
    [data]
  );

  return (
    <div>
      <div className="flex flex-wrap items-center gap-2 mb-3">
        <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted mr-1">colour</span>
        {(["tier", "vertical", "nest"] as ColorBy[]).map((c) => (
          <button key={c} type="button" className={btn(colorBy === c)} onClick={() => setColorBy(c)}>
            {c === "tier" ? "Tier" : c === "vertical" ? "Vertical" : "Nest"}
          </button>
        ))}
        <span className="w-3" />
        <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted mr-1">window</span>
        {[3, 12, meta.months.length].map((w) => (
          <button key={w} type="button" className={btn(windowLen === w)} onClick={() => setWindowLen(w)}>
            {w === meta.months.length ? "all" : `${w} mo`}
          </button>
        ))}
        <span className="w-3" />
        <button type="button" className={btn(playing)} onClick={() => setPlaying((p) => !p)}>
          {playing ? "Pause" : "Play"}
        </button>
        <button type="button" className={btn(spin)} onClick={() => setSpin((s) => !s)}>
          Spin
        </button>
        <button type="button" className={btn(ghosts)} onClick={() => setGhosts((g) => !g)}>
          Context
        </button>
        <button
          type="button"
          className={btn(showNests)}
          onClick={() => {
            // Hiding the rings also drops a picked pocket: with no ring left to
            // click, the filter could not be undone from the picture.
            if (showNests) setNestSel(-1);
            setShowNests((v) => !v);
          }}
        >
          Nests
        </button>
        <button
          type="button"
          className={btn(everything)}
          disabled={meta.nAll === 0}
          title={
            meta.nAll > 0
              ? `draw all ${meta.nAll.toLocaleString("en-US")} signals of the window instead of the ${meta.nPoints.toLocaleString("en-US")}-signal sample (~${Math.round((meta.nAll * 16) / 1e6)} MB)`
              : "this run did not place every signal — recompute the cloud"
          }
          onClick={() => setEverything((v) => !v)}
        >
          All signals
        </button>
        {meta.nHistoryAll + meta.nHistory > 0 && (
          <button
            type="button"
            className={btn(showPast)}
            title="patents 1990-2022 and research 2010-2022 from the history sample (2,000 a month and tier, plus the patents the signal space cites)"
            onClick={() => setShowPast((v) => !v)}
          >
            Past sample
          </button>
        )}
        {!!meta.flows?.pairs.length && (
          <button
            type="button"
            className={btn(showFlows)}
            title={`${meta.flows.edges.toLocaleString("en-US")} patent citations between ${meta.flows.patents_in_nests.toLocaleString("en-US")} patents inside pockets`}
            onClick={() => setShowFlows((v) => !v)}
          >
            Citation flows
          </button>
        )}
        {meta.alt && (
          <>
            <span className="w-3" />
            <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted mr-1">layout</span>
            {[false, true].map((a) => {
              const name = a ? meta.alt!.layout : meta.layout;
              return (
                <button
                  key={name}
                  type="button"
                  className={btn(altLayout === a)}
                  title={
                    name === "topic"
                      ? "each tier's typical wording removed first — one topic from research, patents and press lands together"
                      : "the embedding as it is — research, patents, funding and press form their own continents"
                  }
                  onClick={() => {
                    if (altLayout === a) return;
                    // the matches are placed per layout: fetch them again in the new one
                    if (searchOn.current && query.trim().length >= 2) runSearch(query, layoutView(meta, a));
                    setAltLayout(a);
                  }}
                >
                  {name === "topic" ? "Topic" : "Style"}
                </button>
              );
            })}
          </>
        )}
        <button
          type="button"
          className={btn(false)}
          onClick={() => {
            setYaw(0.6);
            setPitch(0.3);
            setCam({ zoom: 1, center: [0, 0, 0] });
          }}
        >
          Reset view
        </button>
        <button type="button" className={btn(false)} onClick={() => zoomButton(1.25)}>
          +
        </button>
        <button type="button" className={btn(false)} onClick={() => zoomButton(1 / 1.25)}>
          −
        </button>
        <span className="font-mono text-[10px] text-muted w-10">
          ×{cam.zoom < 10 ? cam.zoom.toFixed(1) : cam.zoom.toFixed(0)}
        </span>
      </div>

      <div className="flex flex-wrap items-center gap-1.5 mb-3">
        <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted mr-1">show</span>
        {tierByCode.map((t, code) =>
          t ? (
            <button
              key={`t${code}`}
              type="button"
              className={chip(Boolean((tierMask >> code) & 1))}
              onClick={() => setTierMask((m) => m ^ (1 << code))}
            >
              <span className="inline-block w-2 h-2 mr-1 align-middle" style={{ background: TIER_COLOR[t] }} />
              {TIER_LABEL[t] ?? t}
            </button>
          ) : null
        )}
        <span className="w-2" />
        {vertByCode.map((v, code) =>
          v ? (
            <button
              key={`v${code}`}
              type="button"
              className={chip(Boolean((vertMask >> code) & 1))}
              onClick={() => setVertMask((m) => m ^ (1 << code))}
            >
              {v}
            </button>
          ) : null
        )}
        <span className="flex-1" />
        <div className="flex flex-wrap items-center gap-2">
          {(["text", "meaning", "both"] as SearchMode[]).map((m) => (
            <button
              key={m}
              type="button"
              className={btn(searchMode === m)}
              title={
                m === "text"
                  ? "keyword search: the words occur in the title, summary, tags or abstract"
                  : m === "meaning"
                    ? "vector search: the signals nearest in meaning — a ranking, not a set"
                    : "keyword and vector search together, coloured by where a match came from"
              }
              onClick={() => {
                if (searchMode === m) return;
                setSearchMode(m);
                if (searchOn.current && query.trim().length >= 2) runSearch(query, L, m, meaningN);
              }}
            >
              {m === "text" ? "Text" : m === "meaning" ? "Meaning" : "Both"}
            </button>
          ))}
          {searchMode !== "text" &&
            [250, 500, 1000].map((k) => (
              <button
                key={k}
                type="button"
                className={btn(meaningN === k)}
                title={`the ${k.toLocaleString("en-US")} nearest signals (pgvector returns at most 1,000 per query)`}
                onClick={() => {
                  if (meaningN === k) return;
                  setMeaningN(k);
                  if (searchOn.current && query.trim().length >= 2) runSearch(query, L, searchMode, k);
                }}
              >
                {k.toLocaleString("en-US")}
              </button>
            ))}
          <input
            type="search"
            value={query}
            onChange={(e) => onQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                if (searchTimer.current) clearTimeout(searchTimer.current);
                runSearch(query);
              }
            }}
            placeholder={
              searchMode === "text"
                ? 'search words, e.g. solar panel or "solar panel"'
                : "search by meaning, e.g. PV module recycling — any language"
            }
            aria-label="search the signals in the cloud"
            className="w-72 bg-ink border border-border px-2 py-1 font-mono text-[11px] text-paper placeholder:text-muted/70 focus:border-accent outline-none"
          />
          {hitData && searchInfo && (
            <span
              className="font-mono text-[10px] text-accent whitespace-nowrap"
              title={
                `before de-duplication: ${searchInfo.bySource.text.toLocaleString("en-US")} in titles/summaries/tags, ` +
                `${searchInfo.bySource.research.toLocaleString("en-US")} in research abstracts, ` +
                `${searchInfo.bySource.patents.toLocaleString("en-US")} in patent abstracts` +
                (searchInfo.bySource.meaning
                  ? `, ${searchInfo.bySource.meaning.toLocaleString("en-US")} nearest by meaning`
                  : "")
              }
            >
              {hitData.n.toLocaleString("en-US")} {hitData.n === 1 ? "match" : "matches"}
              {searchInfo.outside > 0 && (
                <span className="text-muted"> · {searchInfo.outside.toLocaleString("en-US")} before the window</span>
              )}
            </span>
          )}
          {hitData && searchInfo && searchInfo.mode === "both" && (
            <span className="font-mono text-[10px] text-muted whitespace-nowrap">
              <Dot c="#d4ff3a" /> both {searchInfo.kinds.both.toLocaleString("en-US")} · <Dot c="#f4f4ee" /> text{" "}
              {searchInfo.kinds.text.toLocaleString("en-US")} · <Dot c="#4fd1ff" /> meaning{" "}
              {searchInfo.kinds.meaning.toLocaleString("en-US")}
            </span>
          )}
          {hitData && searchInfo?.simRange && (
            <span
              className="font-mono text-[10px] text-muted whitespace-nowrap"
              title="cosine similarity of the nearest and of the last returned signal — the scale differs from query to query, so read it as a range, not a grade"
            >
              similarity {searchInfo.simRange[0].toFixed(2)}–{searchInfo.simRange[1].toFixed(2)}
            </span>
          )}
          {searchInfo && searchInfo.failed.length > 0 && (
            <span className="font-mono text-[10px] text-warn whitespace-nowrap">
              partial — {searchInfo.failed.join(", ")} failed
            </span>
          )}
          {searchNote && (
            <span className="font-mono text-[10px] text-muted whitespace-nowrap">{searchNote}</span>
          )}
        </div>
        {(tierMask !== ALL_BITS || vertMask !== ALL_BITS) && (
          <button
            type="button"
            className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted hover:text-accent ml-2"
            onClick={() => {
              setTierMask(ALL_BITS);
              setVertMask(ALL_BITS);
            }}
          >
            show all
          </button>
        )}
      </div>

      <div className="flex items-center gap-3 mb-4">
        <input
          type="range"
          min={0}
          max={lastMonth}
          value={monthEnd}
          onChange={(e) => {
            setPlaying(false);
            setMonthEnd(Number(e.target.value));
          }}
          className="flex-1 accent-accent"
          aria-label="last month of the window"
        />
        <span className="font-mono text-xs text-paper w-44 text-right">
          {windowLen >= meta.months.length
            ? "all months"
            : `${fmtMonth(meta.months[Math.max(0, monthEnd - windowLen + 1)])} – ${fmtMonth(meta.months[monthEnd])}`}
        </span>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_320px] gap-4">
        <div ref={wrapRef} className="relative border border-border bg-ink">
          {error ? (
            <div className="p-8 font-sans text-sm text-text">
              The cloud could not be drawn: {error}
            </div>
          ) : (
            <>
              <canvas
                ref={canvasRef}
                style={{ width: size.w, height: size.h }}
                className={`block w-full touch-none select-none ${
                  hover >= 0 || hoverRing >= 0 ? "cursor-pointer" : "cursor-grab"
                }`}
                onPointerDown={onPointerDown}
                onPointerMove={onPointerMove}
                onPointerUp={onPointerUp}
                onPointerCancel={() => (drag.current = null)}
                onPointerEnter={() => setHovering(true)}
                onPointerLeave={() => {
                  setHovering(false);
                  setHover(-1);
                  setHoverRing(-1);
                  hideTip();
                }}
                onDoubleClick={onDoubleClick}
                onContextMenu={(e) => e.preventDefault()}
              />
              <svg
                className="absolute inset-0 pointer-events-none"
                width={size.w}
                height={size.h}
                viewBox={`0 0 ${size.w} ${size.h}`}
              >
                {arcs.map((a) => (
                  <g key={`f${a.from}-${a.to}`}>
                    <path d={a.d} fill="none" stroke="#7fd6ff" strokeOpacity={0.45} strokeWidth={a.width} />
                    <path
                      d="M0,0 L-7,-3.5 L-7,3.5 Z"
                      fill="#7fd6ff"
                      fillOpacity={0.7}
                      transform={`translate(${a.hx.toFixed(1)},${a.hy.toFixed(1)}) rotate(${((a.angle * 180) / Math.PI).toFixed(1)})`}
                    />
                  </g>
                ))}
                {showNests &&
                  rings.map((r) => {
                    const on = nestSel === r.k;
                    const [cr, cg, cb] = nestColor(r.k);
                    const col =
                      colorBy === "nest"
                        ? `rgb(${Math.round(cr * 255)},${Math.round(cg * 255)},${Math.round(cb * 255)})`
                        : "#c8cabf";
                    return (
                      <g key={r.n.id}>
                        <circle
                          cx={r.p.sx}
                          cy={r.p.sy}
                          r={r.radius * r.p.scale}
                          fill="none"
                          stroke={on ? "#d4ff3a" : col}
                          strokeOpacity={on || hoverRing === r.k ? 1 : 0.55}
                          strokeWidth={on || hoverRing === r.k ? 2 : 1}
                        />
                        {(labelled.has(r.k) || on) && (
                          <text
                            x={r.p.sx}
                            y={r.p.sy - r.radius * r.p.scale - 4}
                            textAnchor="middle"
                            className="font-mono"
                            fontSize={10}
                            fill={on ? "#d4ff3a" : "#c8cabf"}
                          >
                            {r.n.name.length > 30 ? r.n.name.slice(0, 29) + "…" : r.n.name}
                          </text>
                        )}
                      </g>
                    );
                  })}
                {markPos && (
                  <circle cx={markPos.sx} cy={markPos.sy} r={6} fill="none" stroke="#f4f4ee" strokeWidth={1.5} />
                )}
              </svg>
              <div className="absolute left-3 top-2 font-mono text-[10px] text-muted pointer-events-none">
                {!data
                  ? everything
                    ? `loading ${Math.round((meta.nAll * 16) / 1e6)} MB — all ${meta.nAll.toLocaleString("en-US")} signals…`
                    : `loading ${((meta.nPoints * 16) / 1e6).toFixed(1)} MB of points…`
                  : hitData
                    ? `${active.toLocaleString("en-US")} of ${hitData.n.toLocaleString("en-US")} matches in the window`
                    : `${active.toLocaleString("en-US")} of ${data.n.toLocaleString("en-US")} ${everything ? "" : "sampled "}signals in the window`}
              </div>
              {tip && (
                <div
                  className="absolute pointer-events-none z-10 max-w-[280px] border border-border bg-card/95 px-3 py-2 shadow-lg"
                  style={{
                    left: tip.x + 300 > size.w ? tip.x - 292 : tip.x + 12,
                    top: tip.y + 90 > size.h ? tip.y - 70 : tip.y + 12,
                  }}
                >
                  <div className="font-sans text-[12px] leading-snug text-paper">{tip.title}</div>
                  {tip.sub && <div className="mt-1 font-mono text-[10px] text-muted">{tip.sub}</div>}
                </div>
              )}
            </>
          )}
        </div>

        <div className="border border-border bg-card/30 p-4">
          {sel >= 0 && layer ? (
            <div>
              <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-accent mb-2">
                Signal
              </div>
              {detail ? (
                <>
                  <div className="font-display text-base text-paper leading-snug">
                    {detail.status === "published" && detail.slug ? (
                      <a href={`/trends/${detail.slug}`} className="hover:text-accent">
                        {detail.title}
                      </a>
                    ) : detail.source_url ? (
                      <a href={detail.source_url} target="_blank" rel="noopener noreferrer" className="hover:text-accent">
                        {detail.title}
                      </a>
                    ) : (
                      detail.title
                    )}
                  </div>
                  <dl className="mt-3 space-y-1 font-mono text-[11px]">
                    <Row k="source" v={detail.source_name ?? "—"} />
                    <Row k="date" v={detail.date ?? "—"} />
                    <Row k="tier" v={selTier ? TIER_LABEL[selTier] ?? selTier : "none"} />
                    <Row k="vertical" v={detail.vertical ?? "—"} />
                    <Row k="signal type" v={detail.signal_type ?? "—"} />
                    <Row k="status" v={detail.status ?? "—"} />
                    <Row k="nest" v={selNest ? selNest.name : "none"} />
                    {detail.history && (
                      <Row
                        k="history"
                        v={
                          detail.history.layer.startsWith("cited")
                            ? "cited by a patent in the signal space"
                            : `sample · stands for ~${Math.round(detail.history.weight ?? 1).toLocaleString("en-US")} documents of its month` +
                              (detail.history.cited ? " · also cited" : "")
                        }
                      />
                    )}
                    {matchLabel(layer, sel) && <Row k="match" v={matchLabel(layer, sel)} />}
                  </dl>
                </>
              ) : (
                <p className="font-sans text-[12px] text-muted">loading…</p>
              )}
              <button
                type="button"
                className="mt-4 font-mono text-[10px] uppercase tracking-[0.14em] text-muted hover:text-accent"
                onClick={() => {
                  setSelected(-1);
                  setDetail(null);
                }}
              >
                clear selection
              </button>
            </div>
          ) : (
            <div>
              <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-accent mb-2">
                What you are looking at
              </div>
              {everything ? (
                <p className="font-sans text-[13px] text-text leading-relaxed">
                  All {data ? data.n.toLocaleString("en-US") : meta.nAll.toLocaleString("en-US")} signals
                  of the {meta.months.length} months, each placed into the layout the{" "}
                  {meta.nPoints.toLocaleString("en-US")}-signal sample defines — so here brightness{" "}
                  <span className="text-paper">is volume</span>, and the collection ramp of 2025/26
                  (far more sources, far more rows a month) outshines the early years. For what a
                  month was made of, switch back to the sample. Bright points are the window,
                  faint ones the rest of the archive for context.
                </p>
              ) : (
                <p className="font-sans text-[13px] text-text leading-relaxed">
                  {meta.nPoints.toLocaleString("en-US")} signals, {meta.perMonth} from every one of the{" "}
                  {meta.months.length} months — so brightness shows what a month was{" "}
                  <span className="text-paper">made of</span>, never how much there was. Bright
                  points are the window, faint ones the rest of the archive for context.
                  {meta.nAll > 0 && (
                    <> “All signals” draws every one of the {meta.nAll.toLocaleString("en-US")} instead.</>
                  )}
                </p>
              )}
              <p className="font-sans text-[12px] text-muted leading-relaxed mt-3">
                {L.layout === "topic" ? (
                  <>
                    <span className="text-paper">Topic layout:</span>{" "}before projecting, each tier&apos;s
                    typical wording (its mean vector) is taken out, so a subject from research, patents,
                    funding and the trade press lands in one region. Measured: a search term&apos;s
                    matches are 0.34 of each other&apos;s nearest neighbours instead of 0.21.
                    {meta.alt && <> Switch to <span className="text-paper">Style</span> to see the tiers apart.</>}
                  </>
                ) : (
                  <>
                    <span className="text-paper">Style layout:</span>{" "}the embedding as it is. It encodes how
                    a text is written as much as what it is about, so research, patents, funding and the
                    trade press form their own continents, even on the same subject.
                    {meta.alt && <> Switch to <span className="text-paper">Topic</span> to bring one subject together.</>}
                  </>
                )}
              </p>
              <p className="font-sans text-[12px] text-muted leading-relaxed mt-3">
                Rings are the pockets from the emerging layer, placed in the same cloud; click one
                to light up its members. Only {nestMembers.toLocaleString("en-US")} of the{" "}
                {everything ? "" : "sampled "}signals fall inside any pocket — pockets are dense corners of the last 90 days,
                the cloud spans fifteen years.
              </p>
              {meta.nHistoryAll + meta.nHistory > 0 && (
                <p className="font-sans text-[12px] text-muted leading-relaxed mt-3">
                  <span className="text-paper">Past sample:</span>{" "}before 2023 our own intake is thin, so
                  patents (from 1990) and research (from 2010) come from a uniform sample of the archive —
                  2,000 a month and tier — plus every patent that a patent in the signal space cites
                  ({meta.nHistoryAll.toLocaleString("en-US")} placed, {meta.nHistory.toLocaleString("en-US")} in the
                  drawn sample). One past point stands for many documents of its month; read past density as
                  composition, not volume.
                </p>
              )}
              {!!meta.flows?.pairs.length && (
                <p className="font-sans text-[12px] text-muted leading-relaxed mt-3">
                  <span className="text-paper">Citation flows:</span>{" "}an arc runs from a pocket whose patents
                  cite to the pocket they cite — the newer builds on the older. Counted over{" "}
                  {meta.flows.patents_in_nests.toLocaleString("en-US")} patents inside pockets (
                  {meta.flows.edges.toLocaleString("en-US")} citations); citations within a pocket are not drawn.
                  Click a ring to see only its flows.
                </p>
              )}
              <p className="font-sans text-[12px] text-muted leading-relaxed mt-3">
                Drag to turn · Shift-drag or right-drag to move · wheel to zoom toward the
                cursor · double-click a point (or a ring) to make it the centre. Rest on a point
                for a second to see its title, click it to open it. The spin pauses while the
                cursor is on the cloud.
              </p>
              {nestSel >= 0 && meta.nests[nestSel] && (
                <p className="font-mono text-[11px] text-accent mt-3">
                  pocket: {meta.nests[nestSel].name} ·{" "}
                  <button type="button" className="underline" onClick={() => setNestSel(-1)}>
                    clear
                  </button>
                </p>
              )}
            </div>
          )}
          <div className="mt-5 pt-4 border-t border-border font-mono text-[11px] text-muted space-y-1">
            <div>
              layout: <span className="text-paper">{L.layout === "topic" ? "topic" : "writing style"}</span>
            </div>
            <div>
              nearest 10 kept:{" "}
              <span className="text-paper">{(L.neighbourKeep * 100).toFixed(0)} %</span>
            </div>
            <div>
              trustworthiness: <span className="text-paper">{L.trustworthiness.toFixed(3)}</span>
            </div>
            {L.pcaVariance != null ? (
              <div>
                PCA-50 variance: <span className="text-paper">{(L.pcaVariance * 100).toFixed(0)} %</span>
              </div>
            ) : (
              <div>
                input: <span className="text-paper">all 1,024 dims, cosine</span>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function Dot({ c }: { c: string }) {
  return <span className="inline-block w-2 h-2 rounded-full align-middle mr-0.5" style={{ background: c }} />;
}

/** "text", "meaning 0.72", "text + meaning 0.72" — or "" outside a search. */
function matchLabel(d: CloudData | null, i: number): string {
  if (!d || !d.match || i < 0 || i >= d.n) return "";
  const m = d.match[i];
  const s = d.sim && m & MATCH_MEANING ? ` ${d.sim[i].toFixed(2)}` : "";
  if (m === (MATCH_TEXT | MATCH_MEANING)) return `text + meaning${s}`;
  if (m & MATCH_MEANING) return `meaning${s}`;
  return m & MATCH_TEXT ? "text" : "";
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex gap-2">
      <dt className="text-muted uppercase tracking-[0.1em] w-[90px] shrink-0">{k}</dt>
      <dd className="text-text">{v}</dd>
    </div>
  );
}
