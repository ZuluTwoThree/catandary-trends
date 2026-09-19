"""Gemeinsame HTML/SVG-Bausteine für Sheet und Field Watch (Druck, helle Fläche)."""
import html

COLORS = {"science": "#2a78d6", "patent": "#eb6834", "funding": "#1baf7a", "market": "#eda100"}
LABELS = {"science": "Wissenschaft", "patent": "Patente", "funding": "Förderung", "market": "Markt"}
TIERS = ("science", "patent", "funding", "market")

CSS = """
@page { size: A4; margin: 16mm 14mm 18mm 14mm; }
:root { --ink:#0a0c0a; --ink2:#4a4d48; --ink3:#7a7d78; --line:#d9dbd6; --paper:#ffffff; --accent:#d4ff3a; --accent-ink:#2d3a00; }
* { box-sizing: border-box; }
body { font-family: "IBM Plex Sans", "Helvetica Neue", Arial, sans-serif; color: var(--ink); background: var(--paper); margin: 0; font-size: 10.5pt; line-height: 1.42; }
h1,h2,h3 { font-family: "IBM Plex Serif", Georgia, serif; font-weight: 600; letter-spacing: -0.01em; margin: 0; }
h1 { font-size: 24pt; line-height: 1.15; }
h2 { font-size: 14.5pt; margin: 18pt 0 6pt; padding-top: 6pt; border-top: 2px solid var(--ink); page-break-after: avoid; }
h3 { page-break-after: avoid; }
h3 { font-size: 11pt; margin: 10pt 0 4pt; }
p { margin: 4pt 0 6pt; }
.mono { font-family: "IBM Plex Mono", "SFMono-Regular", Menlo, monospace; }
.small { font-size: 8.5pt; color: var(--ink2); }
.muted { color: var(--ink3); }
.kicker { font-family: "IBM Plex Mono", Menlo, monospace; font-size: 8pt; text-transform: uppercase; letter-spacing: .12em; color: var(--ink2); }
.head { display: flex; justify-content: space-between; align-items: flex-start; gap: 16pt; border-bottom: 2px solid var(--ink); padding-bottom: 8pt; }
.brand { font-family: "IBM Plex Serif", Georgia, serif; font-size: 11pt; font-weight: 600; }
.badge { display: inline-block; background: var(--accent); color: var(--accent-ink); font-family: "IBM Plex Mono", Menlo, monospace; font-size: 7.5pt; padding: 2px 6px; letter-spacing: .06em; text-transform: uppercase; }
.badge.gray { background: #e9ebe6; color: var(--ink2); }
.tiles { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8pt; margin: 10pt 0; }
.tile { border: 1px solid var(--line); padding: 8pt 9pt; }
.tile .v { font-family: "IBM Plex Serif", Georgia, serif; font-size: 20pt; font-weight: 600; line-height: 1.1; }
.tile .l { font-size: 8.5pt; color: var(--ink2); margin-top: 2pt; }
.tile .n { font-family: "IBM Plex Mono", Menlo, monospace; font-size: 7.5pt; color: var(--ink3); margin-top: 3pt; }
table { border-collapse: collapse; width: 100%; font-size: 8.8pt; margin: 4pt 0 8pt; }
th { text-align: left; font-weight: 600; border-bottom: 1px solid var(--ink); padding: 3pt 5pt 3pt 0; vertical-align: bottom; }
td { border-bottom: 1px solid var(--line); padding: 3pt 5pt 3pt 0; vertical-align: top; }
td.num, th.num { text-align: right; font-family: "IBM Plex Mono", Menlo, monospace; font-variant-numeric: tabular-nums; }
.grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 12pt; page-break-inside: avoid; }
.grid4 { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8pt; page-break-inside: avoid; }
.panel { border: 1px solid var(--line); padding: 6pt 8pt; }
.panel .t { font-size: 9pt; font-weight: 600; display: flex; align-items: center; gap: 5pt; }
.dot { width: 8px; height: 8px; display: inline-block; border-radius: 1px; }
.thin { background: #f6f7f4; border-left: 3px solid var(--ink); padding: 6pt 9pt; }
.foot { margin-top: 14pt; padding-top: 6pt; border-top: 1px solid var(--line); font-size: 8pt; color: var(--ink2); }
.pb { page-break-before: always; }
.nobreak { page-break-inside: avoid; }
.sig { margin: 3pt 0; padding-left: 0; list-style: none; }
.sig li { padding: 2pt 0; border-bottom: 1px dotted var(--line); font-size: 9pt; }
.sig .m { font-family: "IBM Plex Mono", Menlo, monospace; font-size: 7.5pt; color: var(--ink3); }
a { color: inherit; text-decoration: none; }
.delta { font-family: "IBM Plex Mono", Menlo, monospace; font-size: 8.5pt; white-space: nowrap; }
.up { color: #2d3a00; background: var(--accent); padding: 0 3px; }
.dn { color: #5a1f00; background: #ffd9c7; padding: 0 3px; }
.flat { color: var(--ink2); background: #e9ebe6; padding: 0 3px; }
"""

import re as _re
def esc(s): return html.escape(_re.sub(r"<[^>]+>", "", str(s if s is not None else "")))

def fmt(n):
    if n is None: return "—"
    if isinstance(n, float): return f"{n:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{n:,}".replace(",", ".")

def bars_svg(points, color, width=300, height=70, label_every=None, title=None, unit="", partial_last=False, annotate=True):
    """Dünne Balken, 4px-Radius am Datenende, Grundlinie; points = [(label, value|None)]."""
    vals = [v for _, v in points if v is not None]
    if not vals: return f'<svg width="{width}" height="{height}"><text x="0" y="14" font-size="8" fill="#7a7d78">keine Daten</text></svg>'
    mx = max(vals) or 1
    n = len(points); pad_l, pad_b, pad_t = 2, 14, 10
    w = (width - pad_l) / n; bw = max(2, w * 0.68)
    out = [f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" font-family="IBM Plex Mono, Menlo, monospace" font-size="7">']
    base = height - pad_b
    out.append(f'<line x1="{pad_l}" y1="{base}" x2="{width}" y2="{base}" stroke="#d9dbd6" stroke-width="1"/>')
    peak_i = max(range(n), key=lambda i: (points[i][1] or -1))
    for i, (lab, v) in enumerate(points):
        x = pad_l + i * w + (w - bw) / 2
        if v is None:
            out.append(f'<text x="{x + bw/2:.1f}" y="{base - 2}" text-anchor="middle" fill="#b0b3ad" font-size="6">·</text>')
        else:
            h = 0 if mx == 0 else (base - pad_t) * v / mx
            y = base - h
            op = ' opacity="0.45"' if (partial_last and i == n - 1) else ""
            out.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{h:.1f}" rx="2" fill="{color}"{op}/>')
            if annotate and (i == peak_i or i == n - 1) and v:
                out.append(f'<text x="{x + bw/2:.1f}" y="{y - 2:.1f}" text-anchor="middle" fill="#4a4d48">{fmt(v)}{unit}</text>')
        if label_every and (i % label_every == 0 or i == n - 1):
            out.append(f'<text x="{x + bw/2:.1f}" y="{height - 3}" text-anchor="middle" fill="#7a7d78">{esc(lab)}</text>')
    out.append("</svg>")
    return "".join(out)

def line_svg(points, color, width=420, height=120, unit="", partial_from=None):
    vals = [v for _, v in points if v is not None]
    if not vals: return ""
    mx, mn = max(vals), min(vals); mn = min(mn, 0) if mn > 0 and mn < mx * 0.3 else mn
    span = (mx - mn) or 1
    n = len(points); pl, pr, pt, pb = 26, 8, 10, 16
    xs = lambda i: pl + i * (width - pl - pr) / max(1, n - 1)
    ys = lambda v: pt + (height - pt - pb) * (1 - (v - mn) / span)
    out = [f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" font-family="IBM Plex Mono, Menlo, monospace" font-size="7">']
    for g in (mn, (mn + mx) / 2, mx):
        out.append(f'<line x1="{pl}" y1="{ys(g):.1f}" x2="{width - pr}" y2="{ys(g):.1f}" stroke="#e5e7e2" stroke-width="1"/>')
        out.append(f'<text x="{pl - 4}" y="{ys(g) + 2.5:.1f}" text-anchor="end" fill="#7a7d78">{fmt(round(g, 1))}</text>')
    solid, dashed = [], []
    for i, (lab, v) in enumerate(points):
        if v is None: continue
        (dashed if (partial_from is not None and i >= partial_from) else solid).append((i, v))
    if dashed and solid: dashed.insert(0, solid[-1])
    for seg, dash in ((solid, ""), (dashed, ' stroke-dasharray="3 3"')):
        if len(seg) >= 2:
            d = " ".join(f"{'M' if k == 0 else 'L'}{xs(i):.1f},{ys(v):.1f}" for k, (i, v) in enumerate(seg))
            out.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="2" stroke-linejoin="round"{dash}/>')
    for i, v in solid + dashed:
        out.append(f'<circle cx="{xs(i):.1f}" cy="{ys(v):.1f}" r="2.6" fill="{color}" stroke="#fff" stroke-width="1"/>')
    for i, (lab, v) in enumerate(points):
        if i % 2 == 0 or i == n - 1:
            out.append(f'<text x="{xs(i):.1f}" y="{height - 4}" text-anchor="middle" fill="#7a7d78">{esc(lab)}</text>')
    last = [(i, v) for i, (l, v) in enumerate(points) if v is not None][-1]
    out.append(f'<text x="{xs(last[0]) + 4:.1f}" y="{ys(last[1]) - 5:.1f}" fill="#4a4d48">{fmt(last[1])}{unit}</text>')
    out.append("</svg>")
    return "".join(out)

def delta_badge(this, med):
    if med in (None, 0):
        return f'<span class="delta flat">{fmt(this)} · kein Vergleich</span>' if not this else f'<span class="delta up">{fmt(this)} · Median 0</span>'
    d = round(100 * (this - med) / med)
    cls = "up" if d >= 25 else ("dn" if d <= -25 else "flat")
    sign = "+" if d > 0 else ""
    return f'<span class="delta {cls}">{fmt(this)} vs. {fmt(med)} · {sign}{d} %</span>'

def page(title, body, subtitle=""):
    return f"""<!doctype html><html lang="de"><head><meta charset="utf-8"><title>{esc(title)}</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Serif:wght@400;600&display=swap">
<style>{CSS}</style></head><body>{body}</body></html>"""
