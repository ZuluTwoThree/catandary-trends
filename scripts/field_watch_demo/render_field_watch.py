import json, sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from render_common import *

def field_block(f, weeks, idx):
    wk = f["week"]
    tiles = "".join(f'''<div class="tile"><div class="t" style="display:flex;align-items:center;gap:5pt;font-size:9pt;font-weight:600"><span class="dot" style="background:{COLORS[t]}"></span>{LABELS[t]}</div>
      <div style="margin:4pt 0 2pt">{delta_badge(wk[t]["n"], wk[t]["median4"])}</div>
      {bars_svg([(w[-3:], v) for w, v in zip(weeks, f["weekly"][t])], COLORS[t], width=150, height=52, label_every=7, annotate=False)}
      <div class="n">diese Woche vs. Median der 4 Vorwochen · 8 Wochen</div></div>''' for t in TIERS)
    qpan = "".join(f'''<div class="panel"><div class="t"><span class="dot" style="background:{COLORS[t]}"></span>{LABELS[t]} <span class="muted small">je 10.000</span></div>
      {bars_svg([(x["q"][2:].replace("-Q", "/"), x["per10k"]) for x in f["quarterly"][t]], COLORS[t], width=150, height=58, label_every=4, partial_last=True)}
      <div class="n small mono">{" · ".join(fmt(x["n"]) for x in f["quarterly"][t][-4:])} (n, letzte 4 Q.)</div></div>''' for t in TIERS)
    def sigs(t, k):
        xs = f["top"][t][:k]
        if not xs: return '<li class="muted">keine Signale dieser Ebene in der Woche</li>'
        return "".join(f'<li>{esc(x["title"])} <span class="m">{x["date"][5:]} · {esc(x["source"])}</span></li>' for x in xs)
    new = [a for a in f["actors"] if a["new"] and a["week"]]
    seen = [a for a in f["actors"] if not (a["new"] and a["week"])]
    actors = ("".join(f'<li><b>{esc(a["name"])}</b> <span class="m">neu · erstmals diese Woche</span></li>' for a in new[:6]) +
              "".join(f'<li>{esc(a["name"])} <span class="m">×{a["n90"]} in 90 Tagen{" · auch diese Woche" if a["week"] else ""}</span></li>' for a in seen[:6]))
    nests = "".join(f'''<li><b>{esc(n["label"])}</b> <span class="m">{esc(n["scope"])} · {fmt(n["size"])} Dok. · seit {esc(n["first_month"])} · Neuheits-Hebel {fmt(round(n["novelty_lift"],2))} · {esc(" → ".join(LABELS.get(t, t) for t in n["tier_order"]))}</span></li>''' for n in f["nests"]) or '<li class="muted">kein Nest des letzten Laufs (16.09.) nennt das Feld</li>'
    thin = []
    for t in TIERS:
        tot4 = sum(f["weekly"][t][-4:])
        if tot4 < 5: thin.append(f"{LABELS[t]}: {tot4} Signale in 4 Wochen")
    if f["top_source"] and f["top_source"][1] >= 40: thin.append(f'Quellenkonzentration: {esc(f["top_source"][0])} liefert {f["top_source"][1]} % der Presse-Signale (90 Tage)')
    thin.append(f'Akteure: {f["actors_total"]} extrahierte Namen aus {fmt(f["signals_90d"])} Signalen — Untergrenze')
    return f'''
<div class="{"pb" if idx else ""}"><div class="kicker">Feld {idx + 1} von 3</div><h1 style="font-size:19pt">{esc(f["name"])}</h1>
<div class="small muted">Suchbegriffe: {esc(", ".join(f["terms"]))} · {f["sources_90d"]} Quellen in 90 Tagen · Patente 3 Jahre: {fmt(f["patents_total_window"])}</div></div>
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

def main(fw_path, out_path, customer):
    d = json.load(open(fw_path))
    weeks = d["weeks"]
    blocks = "".join(field_block(f, weeks, i) for i, f in enumerate(d["fields"]))
    summary_rows = "".join(f'<tr><td><b>{esc(f["name"])}</b></td>' + "".join(f'<td>{delta_badge(f["week"][t]["n"], f["week"][t]["median4"])}</td>' for t in TIERS) + f'<td class="num">{f["actors_new_week"]}</td><td class="num">{len(f["nests"])}</td></tr>' for f in d["fields"])
    body = f'''
<div class="head"><div><div class="brand">Catandary Foresight</div><div class="kicker">Field Watch · Wochenblatt · Muster</div></div>
<div class="small" style="text-align:right">Woche {d["week"]} · {d["week_start"][8:]}.{d["week_start"][5:7]}.–{d["week_end"][8:]}.{d["week_end"][5:7]}.{d["week_end"][:4]} · Stand {d["measured_on"]}<br>Kunde: {esc(customer)}<br><span class="badge gray">Beispiel zur Demonstration</span></div></div>
<h2 style="border:0;margin-top:12pt">Lage der Woche — drei Felder</h2>
<p class="small">Je Feld und Ebene: Signale dieser Woche gegen den Median der vier Vorwochen. Grün = mindestens +25 %, rot = mindestens −25 %, grau = im Band oder kein Vergleich möglich. Kleine Zahlen sind normal — die Woche zeigt Bewegung, das Quartal zeigt Richtung.</p>
<table><tr><th>Feld</th>{"".join(f'<th><span class="dot" style="background:{COLORS[t]}"></span> {LABELS[t]}</th>' for t in TIERS)}<th class="num">neue Akteure</th><th class="num">Nester</th></tr>{summary_rows}</table>
{blocks}
<h2>Methodik</h2>
<table>
<tr><th>Größe</th><th>Regel</th></tr>
<tr><td>Treffer</td><td>Phrasen-Treffer der Suchbegriffe in Titel/Teaser/Tags des Signalkorpus (658 Quellen); Patente über den Volltextindex (Titel + Abstract, Publikationsdatum)</td></tr>
<tr><td>Ebene</td><td>nach Quellentyp: Forschung (OpenAlex-Sweeps, Preprint-Server, Journale), Patentämter, Förderregister (NSF/NIH/CORDIS/UKRI/SEC Form D; Presse-Meldungen zu Finanzierungsrunden zählen hier), Markt (Fachpresse, Presseverteiler, Marken)</td></tr>
<tr><td>Woche</td><td>ISO-Woche Mo–So; Vergleich gegen den Median der vier Vorwochen; Patente erscheinen mit Verzug (Sweep dienstags)</td></tr>
<tr><td>Quartale</td><td>festes Quellenpanel (Quelle in den ersten UND letzten vier Quartalen des 12-Quartals-Fensters aktiv); Anteil je 10.000 Panel-Signale der Ebene; laufendes Quartal unvollständig</td></tr>
<tr><td>Akteure</td><td>im Artikelpfad extrahierte Marken/Firmen der Markt- und Förderebene, 90 Tage; „neu" = in den 90 Tagen davor nicht gesehen. Untergrenze: nur 13 % der Presse-Zeilen tragen einen Namen</td></tr>
<tr><td>Nester</td><td>dichte Themen des 90-Tage-Schnitts (k-Means, Kohäsion ≥ 0,75, Lauf 16.09.2026), Treffer über Nest-Titel/repräsentative Titel</td></tr>
<tr><td>Quartals-Scorecard</td><td>alle 13 Wochen: Reifegrad-Karte je Feld (Patentgraph), Take-off je Ebene, Wissenschaft→Markt-Abstand, Anmelder-Rangliste — Format des Technology Trajectory Sheet</td></tr>
</table>
<div class="foot"><b>Kennzeichnung:</b> Dieses Blatt enthält ausschließlich deterministische Abfragen des Catandary-Korpus; kein Sprachmodell hat Text erzeugt. Alle Zählungen sind Korpus-Messungen, keine Marktstatistik. Rechtsrahmen und Termine sind nicht Teil der Messung. Volltexte fremder Quellen verlassen die Plattform nicht (§ 44b UrhG); Links führen zur Originalquelle. · Catandary · catandary.de/trends/methodology</div>'''
    open(out_path, "w").write(page(f"Field Watch {d['week']} — {customer}", body))
    print("written", out_path)

if __name__ == "__main__":
    main(*sys.argv[1:])
