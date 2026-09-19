import json, sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from render_common import *

def main(sheet_path, fw_path, out_path):
    d = json.load(open(sheet_path)); fw = json.load(open(fw_path))["fields"][0]
    f = d["field"]; q = d["quant"]; ser = d["series"]; year_now = 2026
    cn = next((n for o, n in d["offices"] if o == "CN"), 0)
    cn_share = round(100 * cn / d["patents_5y"]) if d["patents_5y"] else 0
    sci_n = sum(x["n"] for x in ser["science"] if x["y"] >= 2010); pat_n = sum(x["n"] for x in ser["patent"])
    k_by = q["K_by_year"]; k_pts = [(str(k["year"]), k["K"]) for k in k_by]
    first_incomplete = next((i for i, k in enumerate(k_by) if not k["complete"]), None)
    def series_block(t, y0):
        pts = [(str(x["y"])[2:], x["per10k"]) for x in ser[t] if x["y"] >= y0 and not (x["y"] == year_now and t == "science")]
        partial = pts and ser[t][-1]["y"] == year_now and t != "science"
        return f'''<div class="panel nobreak"><div class="t"><span class="dot" style="background:{COLORS[t]}"></span>{LABELS[t]} <span class="muted small">· je 10.000 Signale der Ebene und Jahr</span></div>
        {bars_svg(pts, COLORS[t], width=330, height=84, label_every=4 if len(pts) > 14 else 2, partial_last=partial)}
        <div class="small">n gesamt {fmt(sum(x["n"] for x in ser[t] if x["y"] >= y0))} · Fenster {y0}–{year_now}{" · 2026 unvollständig" if partial else " · 2026 ohne Anteil (Nenner unvollständig)"}</div></div>'''
    # Jahres-Tabelle (kompakt)
    yrs = [2008, 2010, 2012, 2014, 2016, 2018, 2020, 2021, 2022, 2023, 2024, 2025, 2026]
    def row(t):
        m = {x["y"]: x for x in ser[t]}
        return "".join(f'<td class="num">{fmt(m[y]["n"]) if y in m else "—"}</td>' for y in yrs)
    tbl = f'''<table><tr><th>Ebene (n je Jahr)</th>{"".join(f'<th class="num">{y}</th>' for y in yrs)}</tr>
    {"".join(f'<tr><td><span class="dot" style="background:{COLORS[t]}"></span> {LABELS[t]}</td>{row(t)}</tr>' for t in TIERS)}</table>'''
    # Quartale (Field-Watch-Rechnung, Panel)
    qrows = ""
    for t in TIERS:
        qs = fw["quarterly"][t]
        qrows += f'<tr><td><span class="dot" style="background:{COLORS[t]}"></span> {LABELS[t]}</td>' + "".join(
            f'<td class="num">{fmt(x["n"])}<br><span class="muted">{(fmt(x["per10k"]) if x["per10k"] is not None else "—") + (f" ({x['panel_n']})" if x["panel_n"] != x["n"] else "")}</span></td>' for x in qs) + "</tr>"
    qhead = "".join(f'<th class="num">{x["q"][2:].replace("-", " ")}</th>' for x in fw["quarterly"]["market"])
    # Akteure
    ass = "".join(f'<tr><td>{esc(a["name"].title() if a["name"].isupper() else a["name"])}</td><td class="num">{fmt(a["n"])}</td></tr>' for a in d["assignees"][:10])
    CPC_FALLBACK = {"Y02E": "Emissionsminderung bei Energieerzeugung/-speicherung (Tag)", "Y02W": "Abfallwirtschaft, Recycling (Tag)", "Y02P": "Klimaschutz in Produktion/Verarbeitung (Tag)", "Y02T": "Verkehr (Tag)", "Y02A": "Klimaanpassung (Tag)", "G06F": "Digitale Datenverarbeitung", "G01R": "Messung elektrischer Größen", "H02J": "Netze, Laden, Energieverteilung"}
    for s_ in d["subclasses"]: s_["title"] = s_["title"] or CPC_FALLBACK.get(s_["sub"], "")
    subs = "".join(f'<tr><td class="mono">{esc(s["sub"])}</td><td>{esc(s["title"][:70])}</td><td class="num">{fmt(s["n"])}</td></tr>' for s in d["subclasses"][:7])
    offices = ", ".join(f"{o} {fmt(n)}" for o, n in d["offices"])
    press = "".join(f'<li>{esc(a["name"])} <span class="m">×{a["n90"]}{" · neu diese Woche" if a["new"] and a["week"] else ""}</span></li>' for a in fw["actors"][:10])
    works = "".join(f'<li>{esc(w["title"])} <span class="m">{w["year"]} · {esc(w["type"])} · {fmt(w["cited_by_count"])} Zitationen{" · FWCI " + fmt(round(w["fwci"],1)) if w.get("fwci") else ""}</span></li>' for w in d["top_works"][:5])
    lands = "".join(f'<li>{esc((l["title"] or l["pub_number"]).title() if (l["title"] or "").isupper() else (l["title"] or l["pub_number"]))} <span class="m">{esc(l["pub_number"])} · {str(l["published"])[:4]} · {fmt(l["cited_by"])}× im Korpus zitiert</span></li>' for l in d["landmarks"][:5])
    nests = "".join(f'''<li><b>{esc(n["label"])}</b> <span class="m">{esc(n["scope"])} · {fmt(n["size"])} Dokumente · Kohäsion {fmt(round(n["cohesion"],2))} · seit {esc(n["first_month"])} ({n["age_months"]} Monate) · Neuheits-Hebel {fmt(round(n["novelty_lift"],2))} · Ebenenfolge {esc(" → ".join(LABELS.get(t, t) for t in n["tier_order"]))}{" · Wissenschaft→Markt " + str(n["science_to_market_months"]) + " Monate" if n.get("science_to_market_months") else ""}</span><br><span class="small">{esc("; ".join((n["rep_titles"] or [])[:2]))}</span></li>''' for n in fw["nests"])
    sigs = lambda t, k: "".join(f'<li>{esc(x["title"])} <span class="m">{x["date"]} · {esc(x["source"])}</span></li>' for x in fw["top"][t][:k])
    body = f'''
<div class="head"><div><div class="brand">Catandary Foresight</div><div class="kicker">Technology Trajectory Sheet · Muster</div></div>
<div class="small" style="text-align:right">Stand {d["measured_on"]}<br>Kunde: {esc(f["customer"])}<br><span class="badge gray">Beispiel zur Demonstration</span></div></div>
<div style="margin:14pt 0 6pt"><div class="kicker">Feld</div><h1>{esc(f["name"])}</h1><div class="muted">{esc(f["name_en"])} · Suchbegriffe: {esc(", ".join(f["terms"]))}</div></div>
<p>Dieses Blatt <b>misst</b> ein Technologiefeld über vier Ebenen — Wissenschaft, Patent, Förderung, Markt — aus dem Catandary-Korpus (21,9 M datierte Signale seit 1990, 45,5 M Forschungswerke seit 2010, 18,7 M Patente mit Zitationsgraph). Jede Zahl ist ein Abfrageergebnis mit n, Fenster und Methode (Abschnitt 8). Es enthält keine Prognose und keine Empfehlung; die Einordnung in Abschnitt 7 ist der einzige geschriebene Teil.</p>

<h2>1 · Auf einen Blick</h2>
<div class="tiles">
<div class="tile"><div class="v">{fmt(pat_n)}</div><div class="l">Patente, die das Feld im Titel/Abstract nennen</div><div class="n">1990–2026 · zwei Wellen: 2008–2012 und 2021–</div></div>
<div class="tile"><div class="v">{fmt(q["K_median"])} %/a</div><div class="l">Verbesserungsrate, Median (SPNP-Methode)</div><div class="n">Klasse {esc(q["selection"][0])} · {fmt(q["n_patents"])} Patente im Graph · kalibriert bis ~2019</div></div>
<div class="tile"><div class="v">{fmt(q["cycle_time_years"])} Jahre</div><div class="l">Zykluszeit (Alter der rückwärts zitierten Patente)</div><div class="n">{fmt(q["cycle_time_edges"])} datierte Zitationskanten · Anmeldungen ab {q["cycle_time_since"]}</div></div>
<div class="tile"><div class="v">{fmt(sci_n)}</div><div class="l">Forschungswerke im Feld</div><div class="n">2010–2026 · Anteil je 10.000 Werke von 0,6 (2010) auf 5,2 (2025)</div></div>
<div class="tile"><div class="v">{cn_share} %</div><div class="l">der Anmeldungen 2021–2026 aus China (CN)</div><div class="n">{fmt(d["patents_5y"])} Anmeldungen · {offices}</div></div>
<div class="tile"><div class="v">{d["takeoff"]["patent"]} → {d["takeoff"]["market"]}</div><div class="l">Take-off Patent → Markt (Ramp-Regel)</div><div class="n">Markt-Take-off liegt am Fensterrand (Marktebene ab 2020) — kein Vorlauf berichtbar</div></div>
</div>

<h2>2 · Reifegrad-Karte (Patentgraph)</h2>
<div class="grid2">
<div class="panel nobreak"><div class="t"><span class="dot" style="background:{COLORS["patent"]}"></span>Verbesserungsrate K(t), %/Jahr · 5-Jahres-Fenster</div>
{line_svg(k_pts, COLORS["patent"], width=330, height=120, unit=" %", partial_from=first_incomplete)}
<div class="small">Gestrichelt: Fenster noch unvollständig (Zitationen laufen nach). Die Rate fiel von {fmt(k_by[0]["K"])} % (2006) auf {fmt(min(k["K"] for k in k_by))} % (2016) und steigt seither wieder — die zweite Patentwelle. Absolutwerte sind nur bis ~2019 kalibriert, spätere Jahre tragen die Richtung.</div></div>
<div class="panel nobreak"><div class="t">Kennzahlen des Graphen</div>
<table><tr><td>Gemessene CPC-Klasse</td><td class="num">{esc(q["selection"][0])}</td></tr>
<tr><td>Auflösung</td><td class="num small">{esc(q["resolved_via"])}</td></tr>
<tr><td>Patente in der Klasse / im Graph</td><td class="num">16.047 / {fmt(q["n_patents"])}</td></tr>
<tr><td>K, Median über die Historie</td><td class="num">{fmt(q["K_median"])} %/a</td></tr>
<tr><td>K, jüngstes Fenster (2026, unvollständig)</td><td class="num">{fmt(k_by[-1]["K"])} %/a</td></tr>
<tr><td>Zykluszeit</td><td class="num">{fmt(q["cycle_time_years"])} a</td></tr>
<tr><td>Zentralitäts-Peak (Kohorte)</td><td class="num">{q["centrality_peak_year"]} · n={q["centrality_peak_n"]}</td></tr>
<tr><td>Lesart des Werkzeugs</td><td class="num small">langsam · Median ~{fmt(q["K_median"])} %/a · Richtung {"unbestimmt" if q["direction"] == "uncertain" else esc(q["direction"])}</td></tr></table>
<div class="small">Zentralität: die Anmeldungen, auf denen das Feld heute aufbaut, sind älter als die laufende Welle — die Kohorte {q["centrality_peak_year"]} ist die meistverknüpfte.</div></div>
</div>

<h2>3 · Vier Ebenen über die Zeit</h2>
<p class="small">Anteil je 10.000 Signale der jeweiligen Ebene und Jahr — das nimmt die eigene Sammelrampe heraus. Wissenschaft aus dem Forschungskorpus (ab 2010), Patente aus dem Volltextindex (ab 1990), Förderung und Markt aus dem Signalkorpus (Marktebene erst ab 2020 in Breite). Kein Anteil, wenn der Nenner unter 30 liegt.</p>
<div class="grid2">{series_block("science", 2010)}{series_block("patent", 2000)}{series_block("funding", 2018)}{series_block("market", 2020)}</div>
{tbl}
<p class="small"><b>Take-off je Ebene</b> (erstes Jahr mit ≥ 15 % des Spitzenjahres, mind. 3): Wissenschaft {d["takeoff"]["science"]} (Fensterrand), Patente <b>{d["takeoff"]["patent"]}</b>, Förderung {d["takeoff"]["funding"] or "— (3 Signale insgesamt)"}, Markt {d["takeoff"]["market"]} (Fensterrand). Erstauftritt: Patente {d["first"]["patent"]}, Wissenschaft {d["first"]["science"]}.</p>

<h2>4 · Bewegung, letzte 12 Quartale</h2>
<p class="small">Zählung auf einem <b>festen Quellenpanel</b> (nur Quellen, die in den ersten und letzten vier Quartalen des Fensters geliefert haben; Wissenschaft {fw["panel_size"]["science"]}, Förderung {fw["panel_size"]["funding"]}, Markt {fw["panel_size"]["market"]} Quellen) — Zahl oben = rohe Treffer, grau = je 10.000 Panel-Signale der Ebene. Patente: Publikationsdatum, letztes Quartal unvollständig.</p>
<table><tr><th>Ebene</th>{qhead}</tr>{qrows}</table>
<div class="grid4" style="page-break-inside:avoid">{"".join(f'<div class="panel"><div class="t"><span class="dot" style="background:{COLORS[t]}"></span>{LABELS[t]}</div>{bars_svg([(x["q"][2:].replace("-Q", "/"), x["per10k"]) for x in fw["quarterly"][t]], COLORS[t], width=150, height=64, label_every=4, partial_last=(t == "patent"))}</div>' for t in TIERS)}</div>

<h2>5 · Wer bewegt das Feld</h2>
<div class="grid2">
<div><h3>Patentanmelder 2021–2026 (Anmeldungen mit Feldbegriff)</h3><table><tr><th>Anmelder</th><th class="num">Anm.</th></tr>{ass}</table>
<div class="small">{fmt(d["patents_with_assignee_5y"])} von {fmt(d["patents_5y"])} Anmeldungen tragen einen Anmelder (BDDS-Stammdaten); Namen unnormalisiert, Tochtergesellschaften getrennt gezählt.</div></div>
<div><h3>Technische Klassen dieser Anmeldungen (CPC-Subklassen)</h3><table><tr><th>Klasse</th><th>Titel</th><th class="num">Anm.</th></tr>{subs}</table>
<div class="small">Y02W/B09B/C02F = Recycling und Abfallbehandlung, Y02E = Energiespeicher-Tag. Die Welle 2021– ist überwiegend eine Recycling- und Materialwelle, nicht eine Zellchemie-Welle.</div></div>
</div>
<div class="grid2">
<div><h3>Meistzitierte Forschungswerke seit 2018</h3><ul class="sig">{works}</ul></div>
<div><h3>Im Korpus meistzitierte Patente mit Feldbegriff</h3><ul class="sig">{lands}</ul><div class="small">Zitationen innerhalb des eigenen Graphen; bevorzugt ältere Anmeldungen.</div></div>
</div>
<h3>Akteure in Fachpresse und Förderung, letzte 90 Tage — Untergrenze</h3>
<ul class="sig">{press}</ul>
<div class="small">{fw["actors_total"]} extrahierte Namen aus {fmt(fw["signals_90d"])} Signalen ({fw["sources_90d"]} Quellen; größte: {esc(fw["top_source"][0])} mit {fw["top_source"][1]} %). Nur 13 % der Fachpresse-Zeilen tragen einen extrahierten Namen — eine Untergrenze, kein Zensus.</div>

<h2>6 · Nester und Neuheit</h2>
<p class="small">Dichte neue Themen im Signalraum (90-Tage-Schnitt, Kohäsion ≥ 0,75), dann rückwärts über den Bestand gezählt: Erstauftritt je Ebene, Alter, Neuheits-Hebel. Treffer = Nest-Titel oder repräsentative Titel nennen einen Feldbegriff.</p>
<ul class="sig">{nests or "<li>Kein Nest des letzten Laufs (16.09.2026) nennt das Feld — das Feld bildet im 90-Tage-Schnitt keinen eigenen dichten Kern.</li>"}</ul>
<h3>Signale der Woche {json.load(open(fw_path))["week"]}</h3>
<div class="grid2"><div><div class="t small"><b>Markt</b></div><ul class="sig">{sigs("market", 4)}</ul></div><div><div class="t small"><b>Wissenschaft</b></div><ul class="sig">{sigs("science", 3)}</ul></div></div>

<h2>7 · Einordnung</h2>
<p><span class="badge">Entwurf · vom Analysten freizugeben</span> <span class="small">Im Kundenblatt ist dies der einzige geschriebene Abschnitt; er nennt nur Zahlen aus den Abschnitten 1–6.</span></p>
<p>Das Feld zeigt im Patentgraph zwei Wellen: 2008–2012 (Anteil bis 4,9 je 10.000, K bis 9,2 %/a) und ab 2021 (Anteil 6,8 je 10.000 im unvollständigen Jahr 2026, K wieder steigend auf 6,8 %/a). Die zweite Welle ist zu {cn_share} % chinesisch und nach CPC-Klassen überwiegend Recycling und Materialrückgewinnung (Y02W, B09B, C02F), getragen von den Brunp-Gesellschaften, Wanrun, Svolt und Hochschulen. Die Forschung wächst seit 2023 überproportional (Anteil 1,5 → 5,2 je 10.000). Auf der Marktebene ist das Feld in der Fachpresse seit 2024 sichtbarer (22 bzw. 31 Signale/Jahr, Q3 2026 mit 17 Treffern das stärkste Quartal), mit Schwerpunkt Großspeicher-Projekte. Die Förderebene ist im Korpus leer (3 Signale seit 2023) — das ist eine Aussage über die Register NSF/NIH/CORDIS/SEC, nicht über das Feld.</p>

<h2>8 · Wo die Evidenz dünn ist</h2>
<div class="thin"><table>
<tr><th>Zelle</th><th>Befund</th><th>Folge für die Lesart</th></tr>
<tr><td>Förderung</td><td>3 Signale seit 2023</td><td>Keine Aussage zur öffentlichen Förderung; die Register decken LFP kaum.</td></tr>
<tr><td>Markt vor 2020</td><td>Marktebene erst ab 2020 in Breite (Archiv-Backfill)</td><td>Markt-Take-off 2020 ist ein Fensterrand, kein Ereignis; Vorlauf Patent→Markt nicht berichtbar.</td></tr>
<tr><td>Wissenschaft 2026</td><td>Korpus-Nenner nur bis Sync-Stand</td><td>2026 ohne Anteilswert; nur rohe Zahl (369 bis September).</td></tr>
<tr><td>Verbesserungsrate</td><td>kalibriert bis ~2019; Fenster ab 2020 unvollständig</td><td>Spätere K-Werte als Richtung lesen, nicht als Größe.</td></tr>
<tr><td>Anmelder</td><td>{fmt(d["patents_with_assignee_5y"])}/{fmt(d["patents_5y"])} mit Namen, unnormalisiert</td><td>Rangfolge robust für die Spitze, Konzernzuordnung von Hand prüfen.</td></tr>
<tr><td>Akteure Presse</td><td>Extraktion nur im Artikelpfad (13 % der Zeilen)</td><td>Liste ist Untergrenze.</td></tr>
<tr><td>Regulatorik / Kalender</td><td>nicht Teil der Messung</td><td>Rechtsrahmen wird auf Wunsch als gekennzeichneter Rahmen ergänzt (Web-Recherche).</td></tr>
</table></div>

<h2>9 · Methodik und Nachrechnen</h2>
<table>
<tr><th>Größe</th><th>Datenquelle</th><th>Regel</th></tr>
<tr><td>Patente mit Feldbegriff</td><td>Volltextindex 19,8 M Patente (BDDS), Titel+Abstract</td><td>Phrasen-Treffer einer der Suchbegriffe; je Publikationsjahr; Anteil = je 10.000 Patente des Jahres</td></tr>
<tr><td>Verbesserungsrate K</td><td>Patentgraph (patent_cpc × patent_links), Klasse {esc(q["selection"][0])}</td><td>SPNP-Zentralität je Anmeldung, 5-Jahres-Fenster, K aus der Steigung; Median über vollständige Fenster (peer-reviewte Methode Singh/Triulzi/Magee 2021)</td></tr>
<tr><td>Zykluszeit</td><td>Zitationskanten der Klasse, Anmeldungen ab {q["cycle_time_since"]}</td><td>Median (Anmeldejahr − Anmeldejahr des zitierten Patents), n = {fmt(q["cycle_time_edges"])}</td></tr>
<tr><td>Forschung</td><td>Forschungskorpus (OpenAlex-Auszug), 45,5 M Werke ab 2010</td><td>Phrasen-Treffer; Anteil je 10.000 Werke des Jahres; Zitationen = cited_by_count</td></tr>
<tr><td>Förderung / Markt</td><td>Signalkorpus (658 Quellen: Fachpresse, Presseverteiler, Marken, Register)</td><td>Phrasen-Treffer in Titel/Teaser/Tags; Ebene nach Quellentyp; Anteil je 10.000 Signale der Ebene</td></tr>
<tr><td>Quartale</td><td>wie oben, festes Quellenpanel</td><td>Quelle im Panel, wenn sie in den ersten und letzten 4 Quartalen geliefert hat</td></tr>
<tr><td>Take-off</td><td>Jahresreihe je Ebene</td><td>erstes Jahr mit ≥ 15 % des Spitzenjahres und mind. 3 Treffern</td></tr>
<tr><td>Nester</td><td>emerging_nests, Lauf vom 16.09.2026</td><td>k-Means im Signalraum, Kohäsion ≥ 0,75, Archiv-Scan je Monat und Ebene</td></tr>
</table>
<div class="foot"><b>Kennzeichnung:</b> Alle Zahlen sind deterministische Abfragen des Catandary-Korpus (kein Sprachmodell beteiligt). Abschnitt 7 ist ein geschriebener Text — in diesem Muster maschinell aus den Messwerten vorformuliert und als Entwurf gekennzeichnet; im Kundenblatt schreibt und verantwortet ihn der Analyst. Alle Zählungen sind Korpus-Messungen, keine Marktstatistik; ein Patent belegt eine beanspruchte Erfindung, kein Produkt. Datenfenster ab 1990. Die Verbesserungsrate ist eine relative Entwicklung, keine Früherkennung. Volltexte fremder Quellen verlassen die Plattform nicht (§ 44b UrhG). · Catandary · catandary.de/trends/methodology</div>
'''
    open(out_path, "w").write(page(f"Technology Trajectory Sheet — {f['name']}", body))
    print("written", out_path)

if __name__ == "__main__":
    main(*sys.argv[1:])
