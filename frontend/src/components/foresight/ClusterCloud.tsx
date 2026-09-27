"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ALL_BITS,
  FOCAL,
  NO_NEST,
  countActive,
  nestColor,
  pickNearest,
  projectPoint,
  unpack,
  viewRadius,
  type CloudData,
  type CloudFilter,
  type CloudMeta,
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

type ColorBy = "tier" | "vertical" | "nest";

function hex(h: string): [number, number, number] {
  const n = parseInt(h.replace("#", ""), 16);
  return [((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255];
}

const VERT_SRC = `#version 300 es
in vec3 aPos;
in vec4 aMeta; // month, tier, vertical, nest
uniform float uYaw, uPitch, uRadius, uFocal, uMonthEnd, uWindowLen, uNest, uGhosts, uDpr, uAlpha;
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
  else if (!(aMeta.x <= uMonthEnd && aMeta.x > uMonthEnd - uWindowLen)) state = 1.0;
  if (state < 0.5 || (state < 1.5 && uGhosts < 0.5)) {
    gl_Position = vec4(2.0, 2.0, 2.0, 1.0);
    gl_PointSize = 0.0;
    vColor = vec4(0.0);
    return;
  }
  // projectPoint(): yaw about y, then pitch about x, then perspective
  float cy = cos(uYaw), sy = sin(uYaw);
  float x1 = aPos.x * cy + aPos.z * sy;
  float z1 = -aPos.x * sy + aPos.z * cy;
  float cp = cos(uPitch), sp = sin(uPitch);
  float y2 = aPos.y * cp - z1 * sp;
  float z2 = aPos.y * sp + z1 * cp;
  float scale = uFocal / (uFocal + z2);
  gl_Position = vec4(x1 * uRadius * scale / (uViewport.x * 0.5),
                     y2 * uRadius * scale / (uViewport.y * 0.5), 0.0, 1.0);
  vec3 c;
  if (uColorBy == 0) c = uTierColors[tier];
  else if (uColorBy == 1) c = uVertColors[vert];
  else c = aMeta.w > 65534.5 ? vec3(0.32) : hsl(mod(aMeta.w * 137.508, 360.0) / 360.0, 0.65, 0.62);
  // (not "active": that is a reserved word in GLSL ES 3.0)
  bool inWindow = state > 1.5;
  gl_PointSize = (inWindow ? 2.8 : 1.6) * scale * uDpr;
  vColor = vec4(c, inWindow ? uAlpha : 0.045);
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

interface Gl {
  gl: WebGL2RenderingContext;
  prog: WebGLProgram;
  loc: Record<string, WebGLUniformLocation | null>;
  n: number;
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
  const vao = gl.createVertexArray();
  gl.bindVertexArray(vao);

  const posBuf = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, posBuf);
  gl.bufferData(gl.ARRAY_BUFFER, d.pos, gl.STATIC_DRAW);
  const aPos = gl.getAttribLocation(prog, "aPos");
  gl.enableVertexAttribArray(aPos);
  gl.vertexAttribPointer(aPos, 3, gl.FLOAT, false, 0, 0);

  const meta = new Float32Array(d.n * 4);
  for (let i = 0; i < d.n; i++) {
    meta[i * 4] = d.month[i];
    meta[i * 4 + 1] = d.tier[i];
    meta[i * 4 + 2] = d.vertical[i];
    meta[i * 4 + 3] = d.nest[i];
  }
  const metaBuf = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, metaBuf);
  gl.bufferData(gl.ARRAY_BUFFER, meta, gl.STATIC_DRAW);
  const aMeta = gl.getAttribLocation(prog, "aMeta");
  gl.enableVertexAttribArray(aMeta);
  gl.vertexAttribPointer(aMeta, 4, gl.FLOAT, false, 0, 0);

  gl.enable(gl.BLEND);
  gl.blendFunc(gl.ONE, gl.ONE); // additive: overlap becomes brightness
  gl.disable(gl.DEPTH_TEST);

  const names = [
    "uYaw", "uPitch", "uRadius", "uFocal", "uMonthEnd", "uWindowLen", "uNest", "uGhosts",
    "uDpr", "uAlpha", "uViewport", "uTierMask", "uVertMask", "uColorBy", "uTierColors", "uVertColors",
  ];
  const loc: Record<string, WebGLUniformLocation | null> = {};
  for (const u of names) loc[u] = gl.getUniformLocation(prog, u);
  return { gl, prog, loc, n: d.n };
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
}

function fmtMonth(m: string | undefined): string {
  if (!m) return "";
  const [y, mm] = m.split("-");
  const names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return `${names[Number(mm) - 1] ?? mm} ${y}`;
}

export default function ClusterCloud({ meta }: { meta: CloudMeta }) {
  const lastMonth = Math.max(0, meta.months.length - 1);
  const [data, setData] = useState<CloudData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [yaw, setYaw] = useState(0.6);
  const [pitch, setPitch] = useState(0.3);
  const [zoom, setZoom] = useState(1);
  const [spin, setSpin] = useState(true);
  const [playing, setPlaying] = useState(false);
  const [monthEnd, setMonthEnd] = useState(lastMonth);
  const [windowLen, setWindowLen] = useState(12);
  const [ghosts, setGhosts] = useState(true);
  const [showNests, setShowNests] = useState(true);
  const [colorBy, setColorBy] = useState<ColorBy>("tier");
  const [tierMask, setTierMask] = useState(ALL_BITS);
  const [vertMask, setVertMask] = useState(ALL_BITS);
  const [nestSel, setNestSel] = useState(-1);
  const [hover, setHover] = useState(-1);
  const [selected, setSelected] = useState(-1);
  const [detail, setDetail] = useState<PointDetail | null>(null);
  const [size, setSize] = useState({ w: 900, h: 560 });

  const wrapRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const glRef = useRef<Gl | null>(null);
  const drag = useRef<{ x: number; y: number; moved: boolean } | null>(null);
  const pickFrame = useRef(0);

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

  // ---- data: fetched only now that the Cloud view is open
  useEffect(() => {
    let cancelled = false;
    fetch(`/api/foresight/space/points?run=${meta.runId}`)
      .then((r) => {
        if (!r.ok) throw new Error(`points request failed (${r.status})`);
        return r.arrayBuffer();
      })
      .then((buf) => {
        if (!cancelled) setData(unpack(buf, meta.coordRange));
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
  }, [meta.runId, meta.coordRange]);

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
    () => ({ yaw, pitch, zoom, width: size.w, height: size.h }),
    [yaw, pitch, zoom, size]
  );
  const filter: CloudFilter = useMemo(
    () => ({ tierMask, verticalMask: vertMask, monthEnd, windowLen, nest: nestSel }),
    [tierMask, vertMask, monthEnd, windowLen, nestSel]
  );

  const active = useMemo(() => (data ? countActive(data, filter) : 0), [data, filter]);
  // Additive blending turns overlap into brightness — which saturates to white
  // when every month is lit at once (108k points). The per-point opacity
  // therefore falls with the number of lit points, so a 3-month window and the
  // whole archive both keep a readable density gradient.
  const alpha = Math.min(0.6, Math.max(0.035, 0.5 * Math.pow(7200 / Math.max(1, active), 0.7)));

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
    gl.drawArrays(gl.POINTS, 0, g.n);
  }, [data, view, yaw, pitch, size, monthEnd, windowLen, nestSel, ghosts, tierMask, vertMask, colorBy, tierColors, vertColors, alpha]);

  // ---- clocks: spin and play
  useEffect(() => {
    if (!spin) return;
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
  }, [spin]);

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

  // ---- pointer: drag turns, a still click picks, hovering highlights
  const localXY = (e: React.PointerEvent) => {
    const r = canvasRef.current!.getBoundingClientRect();
    return { x: e.clientX - r.left, y: e.clientY - r.top };
  };

  const onPointerDown = useCallback((e: React.PointerEvent<HTMLCanvasElement>) => {
    drag.current = { x: e.clientX, y: e.clientY, moved: false };
    e.currentTarget.setPointerCapture(e.pointerId);
  }, []);

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
        setYaw((y) => y + dx * 0.008);
        setPitch((p) => Math.max(-1.3, Math.min(1.3, p + dy * 0.006)));
        drag.current = { x: e.clientX, y: e.clientY, moved: d.moved };
        return;
      }
      if (!data || spin) return; // picking a moving target helps no one
      const { x, y } = localXY(e);
      cancelAnimationFrame(pickFrame.current);
      pickFrame.current = requestAnimationFrame(() => setHover(pickNearest(data, filter, view, x, y)));
    },
    [data, spin, filter, view]
  );

  const onPointerUp = useCallback(
    (e: React.PointerEvent<HTMLCanvasElement>) => {
      const d = drag.current;
      drag.current = null;
      if (!d || d.moved || !data) return;
      const { x, y } = localXY(e);
      const i = pickNearest(data, filter, view, x, y, 8);
      setSelected(i);
      setDetail(null);
      if (i >= 0) {
        setSpin(false);
        fetch(`/api/foresight/space/point?id=${data.trendId[i]}`)
          .then((r) => (r.ok ? r.json() : null))
          .then((j: PointDetail | null) => setDetail(j))
          .catch(() => setDetail(null));
      }
    },
    [data, filter, view]
  );


  // ---- overlay: nest rings and the marked point, in CSS pixels
  const rings = useMemo(() => {
    const maxM = Math.max(1, ...meta.nests.map((n) => n.members));
    return meta.nests
      .map((n, k) => ({ n, k, p: projectPoint(n.x, n.y, n.z, view) }))
      .filter((r) => r.n.members > 0)
      .map((r) => ({ ...r, radius: 5 + 14 * Math.sqrt(r.n.members / maxM) }));
  }, [meta.nests, view]);
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
  const mark = selected >= 0 ? selected : hover;
  const markPos =
    data && mark >= 0
      ? projectPoint(data.pos[mark * 3], data.pos[mark * 3 + 1], data.pos[mark * 3 + 2], view)
      : null;

  const btn = (on: boolean) =>
    `font-mono text-[10px] uppercase tracking-[0.14em] px-3 py-1.5 border transition-colors ${
      on ? "text-accent border-accent bg-accent/10" : "text-muted border-border hover:text-paper"
    }`;
  const chip = (on: boolean) =>
    `font-mono text-[10px] uppercase tracking-[0.1em] px-2 py-1 border transition-colors ${
      on ? "text-paper border-border bg-card" : "text-muted/60 border-border/50 line-through"
    }`;

  const selTier = data && selected >= 0 ? tierByCode[data.tier[selected]] : null;
  const selNest = data && selected >= 0 && data.nest[selected] !== NO_NEST ? meta.nests[data.nest[selected]] : null;
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
          className={btn(false)}
          onClick={() => {
            setYaw(0.6);
            setPitch(0.3);
            setZoom(1);
          }}
        >
          Reset view
        </button>
        <button type="button" className={btn(false)} onClick={() => setZoom((z) => Math.min(3, z * 1.25))}>
          +
        </button>
        <button type="button" className={btn(false)} onClick={() => setZoom((z) => Math.max(0.4, z / 1.25))}>
          −
        </button>
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
                className="block w-full touch-none select-none cursor-grab"
                onPointerDown={onPointerDown}
                onPointerMove={onPointerMove}
                onPointerUp={onPointerUp}
                onPointerCancel={() => (drag.current = null)}
                onPointerLeave={() => setHover(-1)}
              />
              <svg
                className="absolute inset-0 pointer-events-none"
                width={size.w}
                height={size.h}
                viewBox={`0 0 ${size.w} ${size.h}`}
              >
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
                          strokeOpacity={on ? 1 : 0.55}
                          strokeWidth={on ? 2 : 1}
                        />
                        {/* Hit area: an invisible 10 px band on the ring line. An
                            unfilled circle only takes clicks on its 1 px stroke, so
                            the ring was nearly unclickable; filling it instead
                            would steal the points inside from the canvas picker. */}
                        <circle
                          cx={r.p.sx}
                          cy={r.p.sy}
                          r={r.radius * r.p.scale}
                          fill="none"
                          stroke="transparent"
                          strokeWidth={10}
                          style={{ pointerEvents: "stroke" }}
                          className="cursor-pointer"
                          onClick={() => setNestSel((s) => (s === r.k ? -1 : r.k))}
                        >
                          <title>{`${r.n.name} — ${r.n.members} sampled signals`}</title>
                        </circle>
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
                {data
                  ? `${active.toLocaleString("en-US")} of ${data.n.toLocaleString("en-US")} sampled signals in the window`
                  : "loading 1.7 MB of points…"}
              </div>
            </>
          )}
        </div>

        <div className="border border-border bg-card/30 p-4">
          {selected >= 0 && data ? (
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
              <p className="font-sans text-[13px] text-text leading-relaxed">
                {meta.nPoints.toLocaleString("en-US")} signals, {meta.perMonth} from every one of the{" "}
                {meta.months.length} months — so brightness shows what a month was{" "}
                <span className="text-paper">made of</span>, never how much there was. Bright
                points are the window, faint ones the rest of the archive for context.
              </p>
              <p className="font-sans text-[12px] text-muted leading-relaxed mt-3">
                Rings are the pockets from the emerging layer, placed in the same cloud; click one
                to light up its members. Only {nestMembers.toLocaleString("en-US")} of the sampled
                signals fall inside any pocket — pockets are dense corners of the last 90 days,
                the cloud spans fifteen years. Drag to turn (it stops the spin), click a point to
                open it.
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
              nearest 10 kept:{" "}
              <span className="text-paper">{(meta.neighbourKeep * 100).toFixed(0)} %</span>
            </div>
            <div>
              trustworthiness: <span className="text-paper">{meta.trustworthiness.toFixed(3)}</span>
            </div>
            <div>
              PCA-50 variance: <span className="text-paper">{(meta.pcaVariance * 100).toFixed(0)} %</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex gap-2">
      <dt className="text-muted uppercase tracking-[0.1em] w-[90px] shrink-0">{k}</dt>
      <dd className="text-text">{v}</dd>
    </div>
  );
}
