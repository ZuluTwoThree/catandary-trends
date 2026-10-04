"""HTML/PDF der Field-Watch-Blätter (Wochenblatt, Trajectory Sheet, Feldprobe).

Druckformat A4, helle Fläche, IBM Plex (Google Fonts, Fallback System). Die
Diagramme sind inline-SVG ohne Bibliothek; je Ebene eine feste Farbe
(Wissenschaft blau, Patente orange, Förderung aqua, Markt gelb — Palette
gegen weiße Fläche validiert, Tabellen als Relief). PDF über das Playwright-
Chromium, das die Frontend-Tests ohnehin installiert haben
(`FIELD_WATCH_CHROME` überschreibt den Pfad).

Die Zahlen stammen nie aus einem Modell. Geschriebene Abschnitte (Owner 2026-10-04):
Einordnung (Abschnitt 7), Rechtsrahmen (Anhang A) und im Wochenblatt „Was hinter der
Bewegung steckt". Ihr Text kommt vom Analysten — aus `fields/<kunde>.yaml`
(`reading:`/`regulatory:`) oder als umgeschriebener Entwurf (`status: rewritten`,
`pipeline/field_drafts.py`). Maschinelle Entwürfe (`status: draft`) erscheinen nur im
Entwurfsblatt (`--draft`): rotes Badge, Wasserzeichen auf jeder Seite, Quellen und
Prüfhinweise in Anhang B, Fußtext „nicht zur Auslieferung". Jeder Abschnitt trägt, wer
ihn geschrieben hat.
"""
from __future__ import annotations

import glob
import html as _html
import json
import os
import re
import subprocess
from pathlib import Path

from pipeline.field_watch import TIER_LABELS, TIERS

COLORS = {"science": "#2a78d6", "patent": "#eb6834", "funding": "#1baf7a", "market": "#eda100"}
LABELS = TIER_LABELS

CSS = """
@page { size: A4; margin: 16mm 14mm 18mm 14mm; }
:root { --ink:#0a0c0a; --ink2:#4a4d48; --ink3:#7a7d78; --line:#d9dbd6; --paper:#ffffff; --accent:#d4ff3a; --accent-ink:#2d3a00; }
* { box-sizing: border-box; }
body { font-family: "IBM Plex Sans", "Helvetica Neue", Arial, sans-serif; color: var(--ink); background: var(--paper); margin: 0; font-size: 10.5pt; line-height: 1.42; }
h1,h2,h3 { font-family: "IBM Plex Serif", Georgia, serif; font-weight: 600; letter-spacing: -0.01em; margin: 0; }
h1 { font-size: 24pt; line-height: 1.15; }
h2 { font-size: 14.5pt; margin: 18pt 0 6pt; padding-top: 6pt; border-top: 2px solid var(--ink); page-break-after: avoid; }
h3 { font-size: 11pt; margin: 10pt 0 4pt; page-break-after: avoid; }
p { margin: 4pt 0 6pt; }
.mono { font-family: "IBM Plex Mono", "SFMono-Regular", Menlo, monospace; }
.small { font-size: 8.5pt; color: var(--ink2); }
.muted { color: var(--ink3); }
.kicker { font-family: "IBM Plex Mono", Menlo, monospace; font-size: 8pt; text-transform: uppercase; letter-spacing: .12em; color: var(--ink2); }
.head { display: flex; justify-content: space-between; align-items: flex-start; gap: 16pt; border-bottom: 2px solid var(--ink); padding-bottom: 8pt; }
.brand { font-family: "IBM Plex Serif", Georgia, serif; font-size: 11pt; font-weight: 600; }
.badge { display: inline-block; background: var(--accent); color: var(--accent-ink); font-family: "IBM Plex Mono", Menlo, monospace; font-size: 7.5pt; padding: 2px 6px; letter-spacing: .06em; text-transform: uppercase; }
.badge.gray { background: #e9ebe6; color: var(--ink2); }
.tiles { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8pt; margin: 10pt 0; page-break-inside: avoid; }
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
.wm { position: fixed; top: 42%; left: -10%; right: -10%; text-align: center; transform: rotate(-28deg); font: 600 44pt "IBM Plex Sans", Arial, sans-serif; color: rgba(200, 40, 30, .13); z-index: 9; pointer-events: none; }
.badge.draft { background: #c8281e; color: #fff; }
.draftbox { border: 2px dashed #c8281e; padding: 4pt 9pt; margin: 6pt 0; }
.written h4, .written h5 { font-family: "IBM Plex Serif", Georgia, serif; font-size: 10.5pt; margin: 8pt 0 3pt; }
.written ul, .written ol { margin: 3pt 0 6pt 14pt; padding: 0; }
.written li { margin: 1pt 0; }
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


def esc(s) -> str:
    return _html.escape(re.sub(r"<[^>]+>", "", str(s if s is not None else "")))


def fmt(n) -> str:
    if n is None:
        return "—"
    if isinstance(n, float):
        return f"{n:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{n:,}".replace(",", ".")


def bars_svg(points, color, width=300, height=70, label_every=None, unit="", partial_last=False, annotate=True) -> str:
    """Dünne Balken auf Grundlinie, Spitze und letzter Wert beschriftet; points = [(label, value|None)]."""
    vals = [v for _, v in points if v is not None]
    if not vals:
        return f'<svg width="{width}" height="{height}"><text x="0" y="14" font-size="8" fill="#7a7d78">keine Daten</text></svg>'
    mx = max(vals) or 1
    n = len(points)
    pad_l, pad_b, pad_t = 2, 14, 10
    w = (width - pad_l) / n
    bw = max(2, w * 0.68)
    base = height - pad_b
    out = [f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" font-family="IBM Plex Mono, Menlo, monospace" font-size="7">',
           f'<line x1="{pad_l}" y1="{base}" x2="{width}" y2="{base}" stroke="#d9dbd6" stroke-width="1"/>']
    peak_i = max(range(n), key=lambda i: (points[i][1] if points[i][1] is not None else -1))
    for i, (lab, v) in enumerate(points):
        x = pad_l + i * w + (w - bw) / 2
        if v is None:
            out.append(f'<text x="{x + bw / 2:.1f}" y="{base - 2}" text-anchor="middle" fill="#b0b3ad" font-size="6">·</text>')
        else:
            h = (base - pad_t) * v / mx
            y = base - h
            op = ' opacity="0.45"' if (partial_last and i == n - 1) else ""
            out.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{h:.1f}" rx="2" fill="{color}"{op}/>')
            if annotate and (i == peak_i or i == n - 1) and v:
                out.append(f'<text x="{x + bw / 2:.1f}" y="{y - 2:.1f}" text-anchor="middle" fill="#4a4d48">{fmt(v)}{unit}</text>')
        if label_every and (i % label_every == 0 or i == n - 1):
            out.append(f'<text x="{x + bw / 2:.1f}" y="{height - 3}" text-anchor="middle" fill="#7a7d78">{esc(lab)}</text>')
    out.append("</svg>")
    return "".join(out)


def line_svg(points, color, width=420, height=120, unit="", partial_from=None) -> str:
    vals = [v for _, v in points if v is not None]
    if not vals:
        return ""
    mx, mn = max(vals), min(vals)
    mn = 0 if 0 < mn < mx * 0.3 else mn
    span = (mx - mn) or 1
    n = len(points)
    pl, pr, pt, pb = 26, 8, 10, 16

    def xs(i):
        return pl + i * (width - pl - pr) / max(1, n - 1)

    def ys(v):
        return pt + (height - pt - pb) * (1 - (v - mn) / span)

    out = [f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" font-family="IBM Plex Mono, Menlo, monospace" font-size="7">']
    for g in (mn, (mn + mx) / 2, mx):
        out.append(f'<line x1="{pl}" y1="{ys(g):.1f}" x2="{width - pr}" y2="{ys(g):.1f}" stroke="#e5e7e2" stroke-width="1"/>')
        out.append(f'<text x="{pl - 4}" y="{ys(g) + 2.5:.1f}" text-anchor="end" fill="#7a7d78">{fmt(round(g, 1))}</text>')
    solid, dashed = [], []
    for i, (_, v) in enumerate(points):
        if v is None:
            continue
        (dashed if (partial_from is not None and i >= partial_from) else solid).append((i, v))
    if dashed and solid:
        dashed.insert(0, solid[-1])
    for seg, dash in ((solid, ""), (dashed, ' stroke-dasharray="3 3"')):
        if len(seg) >= 2:
            d = " ".join(f"{'M' if k == 0 else 'L'}{xs(i):.1f},{ys(v):.1f}" for k, (i, v) in enumerate(seg))
            out.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="2" stroke-linejoin="round"{dash}/>')
    for i, v in solid + dashed:
        out.append(f'<circle cx="{xs(i):.1f}" cy="{ys(v):.1f}" r="2.6" fill="{color}" stroke="#fff" stroke-width="1"/>')
    for i, (lab, _) in enumerate(points):
        if i % 2 == 0 or i == n - 1:
            out.append(f'<text x="{xs(i):.1f}" y="{height - 4}" text-anchor="middle" fill="#7a7d78">{esc(lab)}</text>')
    last = [(i, v) for i, (_, v) in enumerate(points) if v is not None][-1]
    out.append(f'<text x="{xs(last[0]) + 4:.1f}" y="{ys(last[1]) - 5:.1f}" fill="#4a4d48">{fmt(last[1])}{unit}</text>')
    out.append("</svg>")
    return "".join(out)


def delta_badge(this, med) -> str:
    if not med:
        return (f'<span class="delta up">{fmt(this)} · Median 0</span>' if this
                else '<span class="delta flat">0 · kein Vergleich</span>')
    d = round(100 * (this - med) / med)
    cls = "up" if d >= 25 else ("dn" if d <= -25 else "flat")
    return f'<span class="delta {cls}">{fmt(this)} vs. {fmt(med)} · {"+" if d > 0 else ""}{d} %</span>'


def page(title: str, body: str) -> str:
    return (f'<!doctype html><html lang="de"><head><meta charset="utf-8"><title>{esc(title)}</title>'
            '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500'
            '&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Serif:wght@400;600&display=swap">'
            f"<style>{CSS}</style></head><body>{body}</body></html>")


def _head(kicker: str, right: str, sample: bool) -> str:
    badge = '<br><span class="badge gray">Beispiel zur Demonstration</span>' if sample else ""
    return (f'<div class="head"><div><div class="brand">Catandary Foresight</div><div class="kicker">{esc(kicker)}</div></div>'
            f'<div class="small" style="text-align:right">{right}{badge}</div></div>')


FOOT_COMMON = ("Alle Zählungen sind Korpus-Messungen, keine Marktstatistik; ein Patent belegt eine beanspruchte Erfindung, "
               "kein Produkt. Die Verbesserungsrate ist eine relative Entwicklung, keine Früherkennung. Rechtsrahmen und "
               "Termine sind nicht Teil der Messung. Volltexte fremder Quellen verlassen die Plattform nicht (§ 44b UrhG); "
               "Links führen zur Originalquelle. · Catandary · catandary.de/trends/methodology#field-method")


WATERMARK = '<div class="wm">ENTWURF — nicht zur Auslieferung</div>'


def written(yaml_text: str = "", draft: dict | None = None, markdown: bool = True) -> tuple[str, str | None]:
    """Ein geschriebener Abschnitt → (html, Zustand). Zustand: analyst (Kundendatei),
    rewritten (umgeschriebener Entwurf), draft (maschinell), None (nichts da)."""
    from pipeline.field_drafts import md_to_html
    if yaml_text:
        body = md_to_html(yaml_text) if markdown else f"<p>{esc(yaml_text)}</p>"
        return (f'<p><span class="badge">vom Analysten geschrieben</span></p><div class="written">{body}</div>', "analyst")
    if not draft:
        return "", None
    model = esc(draft.get("model") or "Sprachmodell")
    created = esc(str(draft.get("created") or "")[:10])
    if draft["status"] == "rewritten":
        return (f'<p><span class="badge">vom Analysten geschrieben</span> <span class="small">auf Grundlage eines '
                f'maschinellen Rechercheentwurfs ({created})</span></p><div class="written">{md_to_html(draft["body"])}</div>',
                "rewritten")
    return (f'<p><span class="badge draft">Entwurf · maschinell · vor Auslieferung umschreiben</span> '
            f'<span class="small">{model}, {created} · Quellen und Prüfhinweise im Anhang</span></p>'
            f'<div class="written draftbox">{md_to_html(draft["body"])}</div>', "draft")


def written_note(label: str, state: str | None) -> str:
    if state == "analyst":
        return f" {label} ist vom Analysten geschrieben und verantwortet."
    if state == "rewritten":
        return f" {label} ist vom Analysten geschrieben und verantwortet, auf Grundlage eines maschinellen Rechercheentwurfs."
    if state == "draft":
        return f" {label} ist ein maschineller ENTWURF und nicht zur Auslieferung bestimmt."
    return ""


def draft_annex(drafts: list[tuple[str, dict]], title: str = "Anhang B · Quellen und Prüfhinweise der Entwürfe") -> str:
    """Nur im Entwurfsblatt: je Entwurf Quellen des Laufs und deterministische Prüfhinweise."""
    from pipeline.field_drafts import review_hints
    parts = []
    for label, dr in drafts:
        side = dr.get("sidecar") or {}
        srcs = side.get("sources") or []
        hints = review_hints(dr["body"], srcs, side.get("measurement"))
        lis = "".join(f'<li><a href="{esc(x.get("url"))}">{esc(x.get("title") or x.get("url"))}</a></li>'
                      for x in srcs if str(x.get("url") or "").startswith("http"))
        hl = "".join(f"<li>{esc(h)}</li>" for h in hints) or '<li class="muted">keine Auffälligkeiten gefunden (das ersetzt keine Prüfung)</li>'
        path = str(dr.get("path", ""))
        path = path.split("/data/field_watch/", 1)[-1] if "/data/field_watch/" in path else path
        parts.append(f'<h3>{esc(label)}</h3><div class="small">Datei: <span class="mono">data/field_watch/{esc(path)}</span> · '
                     f'Modell {esc(dr.get("model") or "?")} · {len(srcs)} Quellen</div>'
                     f'<div class="small"><b>Prüfhinweise</b></div><ul class="sig">{hl}</ul>'
                     f'<div class="small"><b>Quellen des Laufs</b></div><ul class="sig">{lis or "<li class=muted>keine</li>"}</ul>')
    if not parts:
        return ""
    return (f'<h2 class="pb">{esc(title)}</h2><p class="small">Nur im Entwurfsblatt. Zum Ausliefern: Entwurf umschreiben, '
            f'im Kopf der Datei <span class="mono">status: rewritten</span> setzen, Blatt ohne <span class="mono">--draft</span> neu bauen.</p>'
            + "".join(parts))


# ---------------------------------------------------------------------------
# Wochenblatt
# ---------------------------------------------------------------------------
def _field_week_block(f: dict, weeks: list[str], idx: int, total: int, panel_size: dict, note_html: str = "") -> str:
    wk = f["week"]
    tiles = "".join(
        f'<div class="tile"><div style="display:flex;align-items:center;gap:5pt;font-size:9pt;font-weight:600">'
        f'<span class="dot" style="background:{COLORS[t]}"></span>{LABELS[t]}</div>'
        f'<div style="margin:4pt 0 2pt">{delta_badge(wk[t]["n"], wk[t]["median4"])}</div>'
        f'{bars_svg([(w[-3:], v) for w, v in zip(weeks, f["weekly"][t])], COLORS[t], width=150, height=52, label_every=7, annotate=False)}'
        f'<div class="n">diese Woche vs. Median der 4 Vorwochen · 8 Wochen</div></div>' for t in TIERS)
    qpan = "".join(
        f'<div class="panel"><div class="t"><span class="dot" style="background:{COLORS[t]}"></span>{LABELS[t]} <span class="muted small">je 10.000</span></div>'
        f'{bars_svg([(x["q"][2:].replace("-Q", "/"), x["per10k"]) for x in f["quarterly"][t]], COLORS[t], width=150, height=58, label_every=4, partial_last=True)}'
        f'<div class="n small mono">{" · ".join(fmt(x["n"]) for x in f["quarterly"][t][-4:])} (n, letzte 4 Q.)</div></div>' for t in TIERS)

    def sigs(t, k):
        xs = f["top"][t][:k]
        if not xs:
            return '<li class="muted">keine Signale dieser Ebene in der Woche</li>'
        return "".join(f'<li><a href="{esc(x["url"])}">{esc(x["title"])}</a> <span class="m">{x["date"][5:]} · {esc(x["source"])}</span></li>' for x in xs)

    new = [a for a in f["actors"] if a["new"] and a["week"]]
    seen = [a for a in f["actors"] if not (a["new"] and a["week"])]
    actors = ("".join(f'<li><b>{esc(a["name"])}</b> <span class="m">neu · erstmals diese Woche</span></li>' for a in new[:6])
              + "".join(f'<li>{esc(a["name"])} <span class="m">×{a["n90"]} in 90 Tagen{" · auch diese Woche" if a["week"] else ""}</span></li>' for a in seen[:6]))
    nests = "".join(
        f'<li><b>{esc(n["label"])}</b> <span class="m">{esc(n["scope"])} · {fmt(n["size"])} Dok. · seit {esc(n["first_month"])} · '
        f'Neuheits-Hebel {fmt(round(n["novelty_lift"] or 0, 2))} · {esc(" → ".join(LABELS.get(t, t) for t in n["tier_order"]))}</span></li>'
        for n in f["nests"]) or '<li class="muted">kein Nest des letzten Laufs nennt das Feld</li>'
    thin = [f"{LABELS[t]}: {sum(f['weekly'][t][-4:])} Signale in 4 Wochen" for t in TIERS if sum(f["weekly"][t][-4:]) < 5]
    if f["top_source"] and f["top_source"][1] >= 40:
        thin.append(f'Quellenkonzentration: {esc(f["top_source"][0])} liefert {f["top_source"][1]} % der Presse-Signale (90 Tage)')
    thin.append(f'Akteure: {f["actors_total"]} extrahierte Namen aus {fmt(f["signals_90d"])} Signalen — Untergrenze')
    cpc = f' · CPC-Anker {esc(", ".join(f["cpc"]))}' if f.get("cpc") else ""
    return f'''
<div class="{"pb" if idx else ""}"><div class="kicker">Feld {idx + 1} von {total}</div><h1 style="font-size:19pt">{esc(f["name"])}</h1>
<div class="small muted">Suchbegriffe: {esc(", ".join(f["terms"]))}{cpc} · {f["sources_90d"]} Quellen in 90 Tagen · Patente im Fenster: {fmt(f["patents_window"])}</div></div>
{('<h3>Was hinter der Bewegung steckt</h3>' + note_html) if note_html else ""}
<h3>Diese Woche je Ebene</h3>
<div class="grid4">{tiles}</div>
<h3>Bewegung, 12 Quartale — festes Quellenpanel</h3>
<div class="grid4">{qpan}</div>
<div class="grid2" style="margin-top:8pt">
<div><h3>Signale der Woche · Markt</h3><ul class="sig">{sigs("market", 5)}</ul></div>
<div><h3>Wissenschaft</h3><ul class="sig">{sigs("science", 3)}</ul><h3>Patente</h3><ul class="sig">{sigs("patent", 2)}</ul><h3>Förderung</h3><ul class="sig">{sigs("funding", 2)}</ul></div>
</div>
<div class="grid2">
<div><h3>Akteure (Presse + Förderung, 90 Tage)</h3><ul class="sig">{actors or '<li class="muted">keine extrahierten Namen</li>'}</ul></div>
<div><h3>Nester im Signalraum</h3><ul class="sig">{nests}</ul>
<h3>Wo die Evidenz dünn ist</h3><div class="thin small">{"<br>".join(thin)}</div></div>
</div>'''


def render_week(d: dict, customer: str, sample: bool = False, notes: dict | None = None) -> str:
    """`notes` = {feld_slug: Entwurf/umgeschriebener Entwurf} (pipeline/field_drafts.load_section)."""
    weeks = d["weeks"]
    total = len(d["fields"])
    notes = notes or {}
    rendered = {slug: written(draft=n) for slug, n in notes.items() if n}
    states = {st for _, st in rendered.values() if st}
    blocks = "".join(_field_week_block(f, weeks, i, total, d["panel_size"], rendered.get(f.get("slug"), ("", None))[0])
                     for i, f in enumerate(d["fields"]))
    rows = "".join(
        f'<tr><td><b>{esc(f["name"])}</b></td>' + "".join(f'<td>{delta_badge(f["week"][t]["n"], f["week"][t]["median4"])}</td>' for t in TIERS)
        + f'<td class="num">{f["actors_new_week"]}</td><td class="num">{len(f["nests"])}</td></tr>' for f in d["fields"])
    ps = d["panel_size"]
    body = f'''
{_head("Field Watch · Wochenblatt", f'Woche {d["week"]} · {d["week_start"][8:]}.{d["week_start"][5:7]}.–{d["week_end"][8:]}.{d["week_end"][5:7]}.{d["week_end"][:4]} · Stand {d["measured_on"]}<br>Kunde: {esc(customer)}' + ('<br><span class="badge draft">Entwurf</span>' if "draft" in states else ''), sample)}
<h2 style="border:0;margin-top:12pt">Lage der Woche — {total} Felder</h2>
<p class="small">Je Feld und Ebene: Signale dieser Woche gegen den Median der vier Vorwochen. Grün = mindestens +25 %, rot = mindestens −25 %, grau = im Band oder kein Vergleich möglich. Kleine Zahlen sind normal — die Woche zeigt Bewegung, das Quartal zeigt Richtung.</p>
<table><tr><th>Feld</th>{"".join(f'<th><span class="dot" style="background:{COLORS[t]}"></span> {LABELS[t]}</th>' for t in TIERS)}<th class="num">neue Akteure</th><th class="num">Nester</th></tr>{rows}</table>
{blocks}
<h2>Methodik</h2>
<table>
<tr><th>Größe</th><th>Regel</th></tr>
<tr><td>Treffer</td><td>Phrasen-Treffer der Suchbegriffe in Titel/Teaser/Tags des Signalkorpus; Patente über den Volltextindex (Titel + Abstract, Publikationsdatum)</td></tr>
<tr><td>Ebene</td><td>nach Quellentyp: Forschung (OpenAlex-Sweeps, Preprint-Server, Journale), Patentämter, Förderregister (NSF/NIH/CORDIS/UKRI/SEC Form D; Presse-Meldungen zu Finanzierungsrunden zählen hier), Markt (Fachpresse, Presseverteiler, Marken)</td></tr>
<tr><td>Woche</td><td>ISO-Woche Mo–So; Vergleich gegen den Median der vier Vorwochen; Patente erscheinen mit Verzug (Sweep dienstags)</td></tr>
<tr><td>Quartale</td><td>festes Quellenpanel (Quelle in den ersten UND letzten vier Quartalen des 12-Quartals-Fensters aktiv: Wissenschaft {ps.get("science", 0)}, Förderung {ps.get("funding", 0)}, Markt {ps.get("market", 0)} Quellen); Anteil je 10.000 Panel-Signale der Ebene; laufendes Quartal unvollständig</td></tr>
<tr><td>Akteure</td><td>im Artikelpfad extrahierte Marken/Firmen der Markt- und Förderebene, 90 Tage; „neu" = in den 90 Tagen davor nicht gesehen. Untergrenze: nur 13 % der Presse-Zeilen tragen einen Namen</td></tr>
<tr><td>Nester</td><td>dichte Themen des 90-Tage-Schnitts (k-Means, Kohäsion ≥ 0,75, jüngster Lauf je Scope), Treffer über Nest-Titel/repräsentative Titel</td></tr>
<tr><td>Quartals-Scorecard</td><td>alle 13 Wochen ein Trajectory Sheet je Feld: Reifegrad-Karte (Patentgraph), Take-off je Ebene, Anmelder-Rangliste</td></tr>
</table>
{draft_annex([(f'Was hinter der Bewegung steckt — {x["name"]}', notes[x["slug"]]) for x in d["fields"] if notes.get(x.get("slug")) and notes[x["slug"]]["status"] == "draft"], "Anhang · Quellen und Prüfhinweise der Entwürfe")}
<div class="foot"><b>Kennzeichnung:</b> {week_label(states)} {FOOT_COMMON}</div>{WATERMARK if "draft" in states else ""}'''
    return page(f"Field Watch {d['week']} — {customer}{' — ENTWURF' if 'draft' in states else ''}", body)


def week_label(states: set) -> str:
    if not states:
        return "Dieses Blatt enthält ausschließlich deterministische Abfragen des Catandary-Korpus; kein Sprachmodell hat Text erzeugt."
    base = "Alle Zahlen sind deterministische Abfragen des Catandary-Korpus (kein Sprachmodell beteiligt)."
    if "draft" in states:
        return base + " Die Notizen „Was hinter der Bewegung steckt\" sind maschinelle ENTWÜRFE — dieses Blatt ist nicht zur Auslieferung bestimmt."
    if "rewritten" in states:
        return base + " Die Notizen „Was hinter der Bewegung steckt\" sind vom Analysten geschrieben und verantwortet, auf Grundlage maschineller Rechercheentwürfe."
    return base + " Die Notizen „Was hinter der Bewegung steckt\" sind vom Analysten geschrieben und verantwortet."


# ---------------------------------------------------------------------------
# Trajectory Sheet
# ---------------------------------------------------------------------------
def _series_block(ser: dict, t: str, y0: int, year_now: int, n_total: int) -> str:
    pts = [(str(x["y"])[2:], x["per10k"]) for x in ser[t] if x["y"] >= y0]
    partial = t != "science"
    note = " · laufendes Jahr unvollständig" if partial else " · laufendes Jahr ohne Anteil (Nenner unvollständig)"
    return (f'<div class="panel nobreak"><div class="t"><span class="dot" style="background:{COLORS[t]}"></span>{LABELS[t]} '
            f'<span class="muted small">· je 10.000 Signale der Ebene und Jahr</span></div>'
            f'{bars_svg(pts, COLORS[t], width=330, height=84, label_every=4 if len(pts) > 14 else 2, partial_last=partial)}'
            f'<div class="small">n {fmt(n_total)} · Fenster {y0}–{year_now}{note}</div></div>')


def render_sheet(d: dict, week: dict | None, customer: str, sample: bool = False,
                 drafts: dict | None = None) -> str:
    """`drafts` = {"reading": …, "regulatory": …} aus pipeline/field_drafts.load_section."""
    f = d["field"]
    drafts = drafts or {}
    q = d.get("quant")
    ser = d["series"]
    year_now = int(d["measured_on"][:4])
    sci_from, mkt_from = d["science_from"], d["market_from"]
    sci_n = sum(x["n"] for x in ser["science"] if x["y"] >= sci_from)
    pat_n = d["totals"]["patent"]
    off = dict(d["offices"])
    top_office = max(off, key=off.get) if off else None
    top_share = round(100 * off[top_office] / d["patents_5y"]) if top_office and d["patents_5y"] else None
    offices = ", ".join(f"{o} {fmt(n)}" for o, n in d["offices"])
    tk = d["takeoff"]

    def tk_txt(t):
        v = tk[t]
        if v is None:
            return "—"
        edge = (t == "science" and v <= sci_from + 1) or (t == "market" and v <= mkt_from) or (t == "funding" and v <= 2010)
        return f"{v}{'*' if edge else ''}"

    # Kacheln
    if q and q.get("K_median") is not None:
        k_tile = (f'<div class="tile"><div class="v">{fmt(q["K_median"])} %/a</div><div class="l">Verbesserungsrate, Median (SPNP-Methode)</div>'
                  f'<div class="n">CPC {esc(", ".join(q["codes"]))} · {fmt(q["n_patents"])} Patente im Graph · kalibriert bis ~2019</div></div>')
    else:
        k_tile = ('<div class="tile"><div class="v">—</div><div class="l">Verbesserungsrate</div>'
                  f'<div class="n">{"kein CPC-Anker gesetzt" if not (q and q.get("codes")) else "zu wenige Patente im Graph"}</div></div>')
    ct = (q or {}).get("cycle_time") or {}
    ct_tile = (f'<div class="tile"><div class="v">{fmt(ct["years"])} Jahre</div><div class="l">Zykluszeit (Alter der rückwärts zitierten Patente)</div>'
               f'<div class="n">{fmt(ct["edges"])} datierte Zitationskanten · Anmeldungen ab {ct.get("since")}</div></div>'
               if ct.get("years") else
               f'<div class="tile"><div class="v">—</div><div class="l">Zykluszeit</div><div class="n">{esc(ct.get("reason") or "kein CPC-Anker gesetzt")}</div></div>')
    sci_first = next((x["per10k"] for x in ser["science"] if x["y"] >= sci_from and x["per10k"]), None)
    sci_last = next((x["per10k"] for x in reversed(ser["science"]) if x["per10k"]), None)
    tiles = f'''<div class="tiles">
<div class="tile"><div class="v">{fmt(pat_n)}</div><div class="l">Patente, die das Feld im Titel/Abstract nennen</div><div class="n">1990–{year_now} · Erstauftritt {d["first"]["patent"] or "—"} · Take-off {tk_txt("patent")}</div></div>
{k_tile}
{ct_tile}
<div class="tile"><div class="v">{fmt(sci_n)}</div><div class="l">Forschungswerke im Feld</div><div class="n">{sci_from}–{year_now} · Anteil je 10.000 Werke {fmt(sci_first)} → {fmt(sci_last)}</div></div>
<div class="tile"><div class="v">{top_share if top_share is not None else "—"} %</div><div class="l">der Anmeldungen der letzten 5 Jahre aus {esc(top_office or "—")}</div><div class="n">{fmt(d["patents_5y"])} Anmeldungen · {esc(offices) or "—"}</div></div>
<div class="tile"><div class="v">{tk_txt("science")} · {tk_txt("market")}</div><div class="l">Take-off Wissenschaft · Markt (Ramp-Regel)</div><div class="n">* = Fensterrand (Beginn der Datenreihe, kein Ereignis; kein Vorlauf berichtbar)</div></div>
</div>'''
    # Reifegrad
    if q and q.get("K_by_year"):
        kb = q["K_by_year"]
        first_incomplete = next((i for i, k in enumerate(kb) if not k["complete"]), None)
        peak = q.get("centrality_peak") or {}
        reif = f'''<div class="grid2">
<div class="panel nobreak"><div class="t"><span class="dot" style="background:{COLORS["patent"]}"></span>Verbesserungsrate K(t), %/Jahr · 5-Jahres-Fenster</div>
{line_svg([(str(k["year"]), k["K"]) for k in kb], COLORS["patent"], width=330, height=120, unit=" %", partial_from=first_incomplete)}
<div class="small">Gestrichelt: Fenster noch unvollständig (Zitationen laufen nach). Spanne {fmt(min(k["K"] for k in kb))}–{fmt(max(k["K"] for k in kb))} %/a; Absolutwerte nur bis ~2019 kalibriert, spätere Jahre tragen die Richtung.</div></div>
<div class="panel nobreak"><div class="t">Kennzahlen des Graphen</div>
<table><tr><td>CPC-Anker</td><td class="num">{esc(", ".join(q["codes"]))}</td></tr>
<tr><td>Patente im Graph</td><td class="num">{fmt(q["n_patents"])}</td></tr>
<tr><td>K, Median über die Historie</td><td class="num">{fmt(q["K_median"])} %/a</td></tr>
<tr><td>K, jüngstes Fenster ({kb[-1]["year"]}{"" if kb[-1]["complete"] else ", unvollständig"})</td><td class="num">{fmt(kb[-1]["K"])} %/a</td></tr>
<tr><td>Zykluszeit</td><td class="num">{fmt(ct.get("years")) + " a" if ct.get("years") else esc(ct.get("reason") or "—")}</td></tr>
<tr><td>Zentralitäts-Peak (Kohorte)</td><td class="num">{(str(peak["year"]) + " · n=" + fmt(peak["n"])) if peak else "—"}</td></tr>
<tr><td>Richtung (Werkzeug)</td><td class="num small">{esc({"accelerating": "beschleunigt", "decelerating": "verlangsamt", "stable": "stabil", "uncertain": "unbestimmt"}.get(q.get("direction") or "uncertain", q.get("direction")))}</td></tr></table>
{"<div class='small'>Die Anmeldungen, auf denen das Feld heute aufbaut, sind älter als die laufende Welle — die Kohorte " + str(peak["year"]) + " ist die meistverknüpfte.</div>" if peak and peak.get("falling") else ""}</div>
</div>'''
    else:
        reif = ('<div class="thin small">Kein Reifegradblock: für dieses Feld ist kein CPC-Anker gesetzt (oder der Graph enthält zu wenige '
                'Patente). Der Anker wird im Setup mit dem Kunden festgelegt.</div>')
    yrs = [y for y in (2008, 2010, 2012, 2014, 2016, 2018, 2020, 2021, 2022, 2023, 2024, 2025, 2026) if y <= year_now]

    def row(t):
        m = {x["y"]: x for x in ser[t]}
        return "".join(f'<td class="num">{fmt(m[y]["n"]) if y in m else "—"}</td>' for y in yrs)

    tbl = (f'<table><tr><th>Ebene (n je Jahr)</th>{"".join(f"<th class=num>{y}</th>" for y in yrs)}</tr>'
           + "".join(f'<tr><td><span class="dot" style="background:{COLORS[t]}"></span> {LABELS[t]}</td>{row(t)}</tr>' for t in TIERS) + "</table>")
    # Quartale (aus dem Wochenblatt-Lauf)
    quart = ""
    if week:
        wf = next((x for x in week["fields"] if x["slug"] == f["slug"]), None)
        if wf:
            qhead = "".join(f'<th class="num">{x["q"][2:].replace("-", " ")}</th>' for x in wf["quarterly"]["market"])
            qrows = "".join(
                f'<tr><td><span class="dot" style="background:{COLORS[t]}"></span> {LABELS[t]}</td>'
                + "".join(f'<td class="num">{fmt(x["n"])}<br><span class="muted">{(fmt(x["per10k"]) if x["per10k"] is not None else "—")}'
                          f'{(" (" + str(x["panel_n"]) + ")") if x["panel_n"] != x["n"] else ""}</span></td>' for x in wf["quarterly"][t]) + "</tr>"
                for t in TIERS)
            ps = week["panel_size"]
            press = "".join(f'<li>{esc(a["name"])} <span class="m">×{a["n90"]}{" · neu diese Woche" if a["new"] and a["week"] else ""}</span></li>' for a in wf["actors"][:10])
            nests = "".join(
                f'<li><b>{esc(n["label"])}</b> <span class="m">{esc(n["scope"])} · {fmt(n["size"])} Dokumente · Kohäsion {fmt(round(n["cohesion"] or 0, 2))} · seit {esc(n["first_month"])} '
                f'({n["age_months"]} Monate) · Neuheits-Hebel {fmt(round(n["novelty_lift"] or 0, 2))} · Ebenenfolge {esc(" → ".join(LABELS.get(t, t) for t in n["tier_order"]))}</span>'
                f'<br><span class="small">{esc("; ".join(n["rep_titles"][:2]))}</span></li>' for n in wf["nests"])
            sigs = lambda t, k: "".join(f'<li><a href="{esc(x["url"])}">{esc(x["title"])}</a> <span class="m">{x["date"]} · {esc(x["source"])}</span></li>' for x in wf["top"][t][:k])  # noqa: E731
            quart = f'''
<h2>4 · Bewegung, letzte 12 Quartale</h2>
<p class="small">Zählung auf einem <b>festen Quellenpanel</b> (Quellen, die in den ersten und letzten vier Quartalen des Fensters geliefert haben; Wissenschaft {ps.get("science", 0)}, Förderung {ps.get("funding", 0)}, Markt {ps.get("market", 0)} Quellen) — Zahl oben = rohe Treffer, grau = je 10.000 Panel-Signale der Ebene (in Klammern die Panel-Treffer, wenn sie abweichen). Patente: Publikationsdatum, letztes Quartal unvollständig.</p>
<table><tr><th>Ebene</th>{qhead}</tr>{qrows}</table>
<div class="grid4">{"".join(f'<div class="panel"><div class="t"><span class="dot" style="background:{COLORS[t]}"></span>{LABELS[t]}</div>{bars_svg([(x["q"][2:].replace("-Q", "/"), x["per10k"]) for x in wf["quarterly"][t]], COLORS[t], width=150, height=64, label_every=4, partial_last=True)}</div>' for t in TIERS)}</div>
<h3>Akteure in Fachpresse und Förderung, letzte 90 Tage — Untergrenze</h3>
<ul class="sig">{press or '<li class="muted">keine extrahierten Namen</li>'}</ul>
<div class="small">{wf["actors_total"]} extrahierte Namen aus {fmt(wf["signals_90d"])} Signalen ({wf["sources_90d"]} Quellen{"; größte: " + esc(wf["top_source"][0]) + " mit " + str(wf["top_source"][1]) + " %" if wf["top_source"] else ""}). Nur 13 % der Fachpresse-Zeilen tragen einen extrahierten Namen — eine Untergrenze, kein Zensus.</div>
<h2>6 · Nester und Neuheit</h2>
<p class="small">Dichte neue Themen im Signalraum (90-Tage-Schnitt, Kohäsion ≥ 0,75), dann rückwärts über den Bestand gezählt: Erstauftritt je Ebene, Alter, Neuheits-Hebel. Treffer = Nest-Titel oder repräsentative Titel nennen einen Feldbegriff.</p>
<ul class="sig">{nests or "<li>Kein Nest des letzten Laufs nennt das Feld — das Feld bildet im 90-Tage-Schnitt keinen eigenen dichten Kern.</li>"}</ul>
<h3>Signale der Woche {esc(week["week"])}</h3>
<div class="grid2"><div><div class="small"><b>Markt</b></div><ul class="sig">{sigs("market", 4)}</ul></div><div><div class="small"><b>Wissenschaft</b></div><ul class="sig">{sigs("science", 3)}</ul></div></div>'''
    ass = "".join(f'<tr><td>{esc(a["name"].title() if a["name"].isupper() else a["name"])}</td><td class="num">{fmt(a["n"])}</td></tr>' for a in d["assignees"][:10])
    subs = "".join(f'<tr><td class="mono">{esc(s["sub"])}</td><td>{esc((s["title"] or "")[:70])}</td><td class="num">{fmt(s["n"])}</td></tr>' for s in d["subclasses"][:7])
    works = "".join(f'<li>{esc(w["title"])} <span class="m">{w["year"]} · {esc(w["type"])} · {fmt(w["cited_by_count"])} Zitationen{" · FWCI " + fmt(round(w["fwci"], 1)) if w.get("fwci") else ""}</span></li>' for w in d["top_works"][:5])
    lands = "".join(
        f'<li>{esc((l["title"] or l["pub_number"]).title() if (l["title"] or "").isupper() else (l["title"] or l["pub_number"]))} '
        f'<span class="m">{esc(l["pub_number"])} · {str(l["published"])[:4]} · {fmt(l["cited_by"])}× im Korpus zitiert</span></li>' for l in d["landmarks"][:5])
    r_html, r_state = written(f.get("reading") or "", drafts.get("reading"), markdown=False)
    g_html, g_state = written(f.get("regulatory") or "", drafts.get("regulatory"))
    reading = (f'<h2>7 · Einordnung</h2>{r_html}<p class="small">Nennt nur Zahlen aus den Abschnitten 1–6.</p>'
               if r_state else "")
    regulatory = (f'<h2 class="pb">Anhang A · Rechtsrahmen</h2><p class="small">Nicht Teil der Messung: geschriebener '
                  f'Überblick über geltendes Recht und laufende Vorhaben, jede Aussage mit Quelle. Keine Rechtsberatung.</p>{g_html}'
                  if g_state else "")
    draft_mode = "draft" in (r_state, g_state)
    annex_b = draft_annex([(lbl, dr) for lbl, dr, st in (("Abschnitt 7 · Einordnung", drafts.get("reading"), r_state),
                                                          ("Anhang A · Rechtsrahmen", drafts.get("regulatory"), g_state))
                           if st == "draft"])
    written_parts = [x for x, st in (("die Einordnung in Abschnitt 7", r_state), ("der Rechtsrahmen in Anhang A", g_state)) if st]
    intro_written = ("" if not written_parts else
                     f"; {written_parts[0]} ist der einzige geschriebene Teil" if len(written_parts) == 1 else
                     f"; geschriebene Teile sind {written_parts[0]} und {written_parts[1]}")
    thin_rows = []
    for t in TIERS:
        if d["totals"][t] < 5:
            thin_rows.append((LABELS[t], f'{d["totals"][t]} Signale im gesamten Fenster', "Keine Aussage auf dieser Ebene möglich."))
    thin_rows.append(("Markt vor 2020", "Marktebene erst ab 2020 in Breite (Archiv-Backfill)", "Ein Markt-Take-off 2020 ist ein Fensterrand, kein Ereignis; Vorlauf zum Markt nicht berichtbar."))
    thin_rows.append(("Wissenschaft, laufendes Jahr", "Korpus-Nenner nur bis zum Sync-Stand", "Laufendes Jahr ohne Anteilswert, nur rohe Zahl."))
    if q and q.get("K_median") is not None:
        thin_rows.append(("Verbesserungsrate", "kalibriert bis ~2019; jüngere Fenster unvollständig", "Spätere K-Werte als Richtung lesen, nicht als Größe."))
    thin_rows.append(("Anmelder", f'{fmt(d["patents_with_assignee_5y"])}/{fmt(d["patents_5y"])} mit Namen, unnormalisiert', "Rangfolge robust für die Spitze, Konzernzuordnung von Hand prüfen."))
    thin_rows.append(("Akteure Presse", "Extraktion nur im Artikelpfad (13 % der Zeilen)", "Liste ist Untergrenze."))
    thin_rows.append(("Regulatorik / Kalender", "nicht Teil der Messung",
                      "Rechtsrahmen in Anhang A (geschrieben, nicht gemessen)." if g_state else "Rechtsrahmen auf Wunsch als gekennzeichneter Anhang."))
    thin = "".join(f"<tr><td>{esc(a)}</td><td>{esc(b)}</td><td>{esc(c)}</td></tr>" for a, b, c in thin_rows)
    cpc_txt = ", ".join(f["cpc"]) if f.get("cpc") else "kein Anker"
    body = f'''
{_head("Technology Trajectory Sheet", f'Stand {d["measured_on"]}<br>Kunde: {esc(customer)}' + ('<br><span class="badge draft">Entwurf</span>' if draft_mode else ''), sample)}
<div style="margin:14pt 0 6pt"><div class="kicker">Feld</div><h1>{esc(f["name"])}</h1><div class="muted">{esc(f.get("name_en") or "")} · Suchbegriffe: {esc(", ".join(f["terms"]))} · CPC-Anker: {esc(cpc_txt)}</div></div>
<p>Dieses Blatt <b>misst</b> ein Technologiefeld über vier Ebenen — Wissenschaft, Patent, Förderung, Markt — aus dem Catandary-Korpus (21,9 M datierte Signale seit 1990, 45,5 M Forschungswerke seit 2010, 18,7 M Patente mit Zitationsgraph). Jede Zahl ist ein Abfrageergebnis mit n, Fenster und Methode (letzter Abschnitt). Es enthält keine Prognose und keine Empfehlung{intro_written}.</p>
<h2>1 · Auf einen Blick</h2>
{tiles}
<h2>2 · Reifegrad-Karte (Patentgraph)</h2>
{reif}
<h2>3 · Vier Ebenen über die Zeit</h2>
<p class="small">Anteil je 10.000 Signale der jeweiligen Ebene und Jahr — das nimmt die eigene Sammelrampe heraus. Wissenschaft aus dem Forschungskorpus (ab {sci_from}), Patente aus dem Volltextindex (ab 1990), Förderung und Markt aus dem Signalkorpus (Marktebene erst ab {mkt_from} in Breite). Kein Anteil, wenn der Nenner unter 30 liegt.</p>
<div class="grid2">{_series_block(ser, "science", sci_from, year_now, sci_n)}{_series_block(ser, "patent", 2000, year_now, sum(x["n"] for x in ser["patent"] if x["y"] >= 2000))}{_series_block(ser, "funding", 2018, year_now, sum(x["n"] for x in ser["funding"] if x["y"] >= 2018))}{_series_block(ser, "market", mkt_from, year_now, sum(x["n"] for x in ser["market"] if x["y"] >= mkt_from))}</div>
{tbl}
<p class="small"><b>Take-off je Ebene</b> (erstes Jahr mit ≥ 15 % des Spitzenjahres, mind. 3; * = Fensterrand): Wissenschaft {tk_txt("science")}, Patente <b>{tk_txt("patent")}</b>, Förderung {tk_txt("funding")}, Markt {tk_txt("market")}. Erstauftritt: Patente {d["first"]["patent"] or "—"}, Wissenschaft {d["first"]["science"] or "—"}.</p>
{quart}
<h2>5 · Wer bewegt das Feld</h2>
<div class="grid2">
<div><h3>Patentanmelder, letzte 5 Jahre (Anmeldungen mit Feldbegriff)</h3><table><tr><th>Anmelder</th><th class="num">Anm.</th></tr>{ass or "<tr><td colspan=2 class=muted>keine</td></tr>"}</table>
<div class="small">{fmt(d["patents_with_assignee_5y"])} von {fmt(d["patents_5y"])} Anmeldungen tragen einen Anmelder (BDDS-Stammdaten); Namen unnormalisiert, Tochtergesellschaften getrennt gezählt.</div></div>
<div><h3>Technische Klassen dieser Anmeldungen (CPC-Subklassen)</h3><table><tr><th>Klasse</th><th>Titel</th><th class="num">Anm.</th></tr>{subs or "<tr><td colspan=3 class=muted>keine</td></tr>"}</table></div>
</div>
<div class="grid2">
<div><h3>Meistzitierte Forschungswerke, letzte 8 Jahre</h3><ul class="sig">{works or '<li class="muted">keine</li>'}</ul></div>
<div><h3>Im Korpus meistzitierte Patente mit Feldbegriff</h3><ul class="sig">{lands or '<li class="muted">keine</li>'}</ul><div class="small">Zitationen innerhalb des eigenen Graphen; bevorzugt ältere Anmeldungen.</div></div>
</div>
{reading}
<h2>8 · Wo die Evidenz dünn ist</h2>
<div class="thin"><table><tr><th>Zelle</th><th>Befund</th><th>Folge für die Lesart</th></tr>{thin}</table></div>
<h2>9 · Methodik und Nachrechnen</h2>
<table>
<tr><th>Größe</th><th>Datenquelle</th><th>Regel</th></tr>
<tr><td>Patente mit Feldbegriff</td><td>Volltextindex (BDDS), Titel+Abstract</td><td>Phrasen-Treffer einer der Suchbegriffe; je Publikationsjahr; Anteil = je 10.000 Patente des Jahres</td></tr>
<tr><td>Verbesserungsrate K</td><td>Patentgraph (patent_cpc × patent_links), CPC-Anker {esc(cpc_txt)}</td><td>SPNP-Zentralität je Anmeldung, 5-Jahres-Fenster, K aus der Steigung; Median über vollständige Fenster (peer-reviewte Methode Singh/Triulzi/Magee 2021)</td></tr>
<tr><td>Zykluszeit</td><td>Zitationskanten der Anker-Klassen, Anmeldungen ab {ct.get("since") or 2015}</td><td>Median (Anmeldejahr − Anmeldejahr des zitierten Patents); unter 200 Kanten nicht berichtet</td></tr>
<tr><td>Forschung</td><td>Forschungskorpus (OpenAlex-Auszug), 45,5 M Werke ab {sci_from}</td><td>Phrasen-Treffer; Anteil je 10.000 Werke des Jahres; Zitationen = cited_by_count</td></tr>
<tr><td>Förderung / Markt</td><td>Signalkorpus (658 Quellen: Fachpresse, Presseverteiler, Marken, Register)</td><td>Phrasen-Treffer in Titel/Teaser/Tags; Ebene nach Quellentyp; Anteil je 10.000 Signale der Ebene</td></tr>
<tr><td>Quartale</td><td>wie oben, festes Quellenpanel</td><td>Quelle im Panel, wenn sie in den ersten und letzten 4 Quartalen geliefert hat</td></tr>
<tr><td>Take-off</td><td>Jahresreihe je Ebene</td><td>erstes Jahr mit ≥ 15 % des Spitzenjahres und mind. 3 Treffern</td></tr>
<tr><td>Nester</td><td>emerging_nests, jüngster Lauf je Scope</td><td>k-Means im Signalraum, Kohäsion ≥ 0,75, Archiv-Scan je Monat und Ebene</td></tr>
</table>
{regulatory}
{annex_b}
<div class="foot"><b>Kennzeichnung:</b> Alle Zahlen sind deterministische Abfragen des Catandary-Korpus (kein Sprachmodell beteiligt).{written_note("Abschnitt 7", r_state)}{written_note("Anhang A", g_state)}{" Dieses Blatt ist ein ENTWURF und nicht zur Auslieferung bestimmt." if draft_mode else ""} {FOOT_COMMON}</div>{WATERMARK if draft_mode else ""}'''
    return page(f"Technology Trajectory Sheet — {f['name']}{' — ENTWURF' if draft_mode else ''}", body)


# ---------------------------------------------------------------------------
# Feldprobe (Seite 1 + Anker-Vorschlag)
# ---------------------------------------------------------------------------
def render_probe(d: dict, requester: str = "") -> str:
    """Seite 1 des Sheets fuer eine Phrase, plus die Kandidatenklassen."""
    sheet_html = render_sheet(d, None, requester or "Feldprobe", sample=False)
    # Seite 1 = alles bis zur Reifegrad-Karte; darunter der Anker-Block
    cut = sheet_html.index("<h2>2 · Reifegrad-Karte")
    p = d.get("probe") or {}
    cands = "".join(
        f'<tr><td class="mono">{esc(c["symbol"])}</td><td>{esc((c.get("title") or "")[:80])}</td><td class="num">{fmt(c.get("n"))}</td><td>{"vorgeschlagen" if c.get("default") else ""}</td></tr>'
        for c in p.get("candidates") or [])
    anchor = (f'<h2>Anker für die Messung</h2><p class="small">Gate der Technologie-Suche: <b>{esc(p.get("gate") or "—")}</b> · verwendet: {esc(", ".join(p.get("anchor_used") or []) or "kein Anker (Reifegrad nicht gerechnet)")}. '
              f'Der Analyst wählt die Klassen im Setup; der Kunde gibt sie frei.</p>'
              + (f'<table><tr><th>CPC</th><th>Titel</th><th class="num">Patente</th><th></th></tr>{cands}</table>' if cands else ""))
    foot = f'<div class="foot"><b>Kennzeichnung:</b> deterministische Abfragen des Catandary-Korpus, kein Modelltext. {FOOT_COMMON}</div></body></html>'
    return sheet_html[:cut].replace("Technology Trajectory Sheet", "Feldprobe · Seite 1 des Trajectory Sheet", 1) + anchor + foot


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------
def chrome_path() -> str | None:
    env = os.environ.get("FIELD_WATCH_CHROME")
    if env and Path(env).exists():
        return env
    pats = [str(Path.home() / ".cache/ms-playwright/chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell"),
            str(Path.home() / ".cache/ms-playwright/chromium-*/chrome-linux/chrome"),
            "/usr/bin/chromium", "/usr/bin/chromium-browser", "/usr/bin/google-chrome"]
    for pat in pats:
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[-1]
    return None


def to_pdf(html_path: Path, pdf_path: Path, timeout: int = 120) -> bool:
    ch = chrome_path()
    if not ch:
        return False
    cmd = [ch, "--headless", "--no-sandbox", "--disable-gpu", "--no-pdf-header-footer",
           f"--print-to-pdf={pdf_path}", str(html_path)]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=timeout)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"PDF fehlgeschlagen ({type(exc).__name__}): {getattr(exc, 'stderr', b'')[-300:]}") from exc
    return pdf_path.exists()


def render_client_index(customer: str, entries: list[dict]) -> str:
    """Kundenseite: Liste der Blätter (neueste zuerst), fuer trends/clients/<kunde>/."""
    rows = "".join(f'<li><a href="{esc(e["file"])}">{esc(e["label"])}</a> <span class="m">{esc(e["date"])}</span></li>' for e in entries)
    body = (f'{_head("Field Watch · Kundenbereich", esc(customer), False)}<h2 style="border:0">Ihre Blätter</h2>'
            f'<ul class="sig">{rows or "<li class=muted>noch keine Blätter</li>"}</ul>'
            f'<div class="foot">Zugang nur mit Kennwort; keine Analyse, kein Tracking. Fragen: contact@catandary.de</div>')
    return page(f"Field Watch — {customer}", body).replace("<head>", '<head><meta name="robots" content="noindex, nofollow">', 1)


def dump_json(obj, path: Path) -> None:
    path.write_text(json.dumps(obj, default=str, ensure_ascii=False, indent=1), encoding="utf-8")
