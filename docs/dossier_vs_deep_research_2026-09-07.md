# Dossier vs. Deep Research — Stand der Zielerreichung (2026-09-07)

> **Feature entfernt 2026-09-19** (Owner: „Das Feature trägt nicht"), s. CLAUDE.md, Abschnitt „Scouting-Dossiers — entfernt". Dieses Dokument bleibt als Historie; Code-Stand davor: Tag `archive/dossiers-2026-09-19`.

**Ziel (Owner, 2026-09-07):** Das Dossier-Tool (`scripts/corpus_research.py`,
Owner-Desk `/trends/dossiers`) soll zu einem gewählten Thema im Blindgutachten
besser bewertet werden als ein Deep Research mit Sonnet 5. Testthema GLP-1.
Nachweis: direkter Vergleich Dossier (Repo-Stand) · Dossier (zielorientierte
Überarbeitung) · Deep Research (Sonnet).

**Ergebnis:** Nicht erreicht. Der Owner hat den Stand am 2026-09-07 abgenommen
(„Ich akzeptiere den aktuellen Stand auch wenn das Ziel noch nicht erreicht
ist"); das Ziel ist nicht mehr aktuell, die Arbeit ist als **Feature in
Development** gemergt. Wiederaufnahme: GitHub-Issue #100.

Diese Datei ist der Anknüpfungspunkt in ein paar Wochen. Sie beschreibt, was
gebaut wurde, was die Gutachten sagen, warum es nicht reichte, und womit man
weitermacht — inklusive Kommandos und Dateien.

---

## 1. Messverfahren

- **Blindgutachten:** Ein Subagent (Claude, general-purpose, mit WebFetch)
  bekommt zwei anonymisierte Dokumente (Buchstaben zufällig vergeben,
  Schlüssel getrennt abgelegt) und bewertet nach festem Protokoll:
  Beleg-Stichprobe (je 5 zufällige Quellen abgerufen und geprüft),
  Quellenqualität, Entscheidungstauglichkeit (fünf Felder je Option),
  Zeitliche Einordnung, Alleinstellung, sieben Kriterien 1–10, Sieger.
  Kriterien: Belegbarkeit · Spezifität · Handlungsrelevanz (EU-Mittelstand) ·
  Abdeckung Wissenschaft/Patente/Förderung/Markt · Zeitliche Einordnung ·
  Ehrlichkeit über Grenzen · Struktur.
- **Vergleichstext:** `scratchpad/glp1/C_sonnet.md` — Deep Research (Sonnet 5)
  zur identischen Frage, 2.833 Wörter.
- **Frage** (alle Läufe identisch): *Where does GLP-1 / incretin technology
  stand today, and what should a mid-sized European company in food,
  nutrition or health technology do about it in the next 12 months? Cover:
  what is actually moving across science, patents, funding and market
  signals; who the movers are; which claims the evidence supports and which
  it does not; what the timing looks like; and where the risks and open
  questions are.*
- **Jury-nahe Messung ohne Modell:** `scratchpad/glp1/jury_metrics.py`
  (einschlägige Zukunftstermine, Akteure mit Zahl im selben Satz, Zahlensätze,
  bezifferte Aufwandsfelder, Kettenabdeckung). Sie misst, was die Jury
  bewertet — nicht die Faktenquote, die von 0,94 auf 4,15 stieg, während die
  Jury die Spezifität senkte.
- **Gutachterstreuung:** Derselbe Sonnet-Text bekam 7,43 · 6,9 · 6,3 · 6,9 —
  ±0,6 sind Rauschen. Ein Sieg muss deutlich sein.

## 2. Verlauf und Scores

| Lauf | Dossier-ID | Gutachten | Dossier : Vergleich | Was neu war |
|---|---|---|---|---|
| Runden 1–9 (B-Serie) | #17–#27 | jury_1–14 | 3,7 … 5,4 gegen eigene Vorläufe und Web-Recherche | Gliederung, Rechts-/Markt-/Förder-Sweeps, Entitäten-Wellen, Kalenderpflicht, Platzhalter-Regeln, Quellenrang, Faktenquote |
| DR1 | #25 | jury_15 | **5,4 : 4,9** (gegen eigenen Vorlauf) | DR-Modus: Primärquellen zuerst, Faktenzettel, Modellkarten-Sampling |
| DR1 | #25 | jury_16 | 5,57 : 7,43 | erster Vergleich gegen Sonnet |
| DR2 | #28 (glp1-dr2) | jury_17 | 5,7 : 6,9 | Denken (reasoning) im Schreibschritt, Förder-Sweep, R10/R12-Regeln |
| DR3 | #28 (glp1-dr3) | jury_18 | 5,9 : 6,3 | R13: Entitäten-Hygiene, Katalysator-Sweep, Kalender-Kandidaten, Aufwands-Anker, presence_penalty 0,5, kein Denken |
| DR4 | #29 (glp1-dr4) | jury_19 | 5,7 : 6,9 | R14: Akteur-Landkarte, Absatz-Streichung + Reparatur, Themenprofil + Rückgrat je Vertikale, Evidenzbank statt Rohdump |

Kriterien der letzten drei Gutachten (Dossier : Sonnet):

| Kriterium | jury_17 | jury_18 | jury_19 |
|---|---|---|---|
| Belegbarkeit | 6 : 6 | 7 : 5 | — : 5 |
| Spezifität | 5 : 8 | 5 : 8 | 5 : 9 |
| Handlungsrelevanz | 6 : 7 | 6 : 5 | 6 : 5 |
| Abdeckung | 5 : 8 | 5 : 8 | 5 : 9 |
| Zeitliche Einordnung | 3 : 7 | 5 : 6 | 4 : 7 |
| Ehrlichkeit | 8 : 6 | 8 : 5 | 8 : 6 |
| Struktur | 7 : 6 | 5 : 7 | 6 : 7 |

Lesart: Belegbarkeit, Ehrlichkeit, Struktur, Handlungsrelevanz liegen seit
DR3 auf oder über Sonnet-Niveau. **Spezifität, Abdeckung, Zeit** sind in vier
Läufen nicht über 5/5/5 hinausgekommen — dort steckt der ganze Abstand.

## 3. Was gebaut wurde (alles auf `dev`, seit 2026-09-07 gemergt)

Vollständige Rundenchronik: `docs/agentic_dossiers.md` (Runden 5–14). Kurz:

**Beschaffung (funktioniert, seit DR3 messbar):**
- Feste Sweep-Wellen mit eigenem Budget und Protokoll: Recht/IP, Markt/
  Erstattung, Förderung, Katalysatoren (Termine), Substanz/IP je Wirkstoff,
  Akteur/Ereignis je Entität.
- Entitäten-Ernte aus Titeln, Snippets und Volltexten gelesener Seiten;
  Stoffklassen, Abschnittsmarken, generische Wörter gefiltert; voller Name
  vor Kurzform (`harvest_entities`, `_prefer_longest`).
- Themenneutrale Suchrichtungen (R14-3): themenunabhängiger Kern +
  kuratiertes Rückgrat je Catandary-Vertikale (`VERTICAL_SETS`, Vertikale
  deterministisch aus der Mehrheit der `vertical`-Felder der nächsten
  Korpus-Treffer plus Stichwortvotum) + Modellprofil (`TopicProfile`:
  Regulatoren, Ereignistypen, Rechts-/Marktfragen, Perspektiven,
  Akteur-Saatgut; gefiltert gegen Verweigerungen, Kategorielabels, Echo der
  Leitfrage). Probe ohne Lauf: `scripts/dossier_topic_probe.py "<Thema>"`.
- Primärquellen-Lesen nach Rang (`read_primary_first`), Faktenzettel
  (`harvest_facts`: datierte Einzelaussagen mit Akteur, jede gegen den
  Quelltext geprüft; relative Zeitangaben verworfen), Kalender-Kandidaten
  (`calendar_candidates`: Zukunftsdatum + Vorwärtswort + Themenbezug, gegen
  den Stichtag gerechnet, URLs entfernt, max. zwei Zeilen je Quelle),
  Aufwands-Anker (`effort_anchors`: Beträge/Verfahrensdauern aus Förder-,
  Rechts-, Katalysatorseiten), Akteur-Landkarte (`actor_map`).

**Schreiben und Prüfen:**
- Ein Schreibaufruf mit verbindlicher Gliederung (Kurzfassung · Was sich
  bewegt mit Pflicht-Akteurtabelle · Recht/IP · Kalender · Nicht-Gestütztes ·
  Optionen mit fünf Feldern · Offene Fragen), Sampling nach Modellkarte
  (temp 0,7 / top_p 0,80 / top_k 20, presence_penalty 0,5 statt 1,5),
  `enable_thinking: false`.
- Deterministische Prüfung (`pipeline/dossier_structure.py`): Gliederung,
  Kalenderzeilen (Datum, Beleg, Themenbezug im Ereignis, Quellenvielfalt),
  Akteurzeilen, Platzhalter (auch Satzform, auch selbst widerrufene Zahlen),
  Bruchstücke, Zitatprüfung (Zahlen und Subjekte gegen die zitierte Seite),
  Quellenrang, Faktenquote. Genau **ein** Revisionsauftrag aus den Befunden.
- Nach der Revision: Reparatur je Satz (`repair_sentences`, M7), dann
  mechanische Streichung auf Absatzebene (`drop_unverified` +
  `_mend_paragraphs`, abkürzungsfester Satzsplit), Zitat-Kanonisierung,
  Coverage-/Prüfanhang.

**Modellparameter (Qwen3.8-27B, llama.cpp, Q4):** Denken wurde in Runde 11
ausprobiert — es traf ausschließlich den Schreibschritt (alle anderen
Aufrufe sind schema-gebunden und nicht-denkend), kostete einen Lauf
(Zeitlimit) und spülte eine abgeschnittene Denkspur in den Text; seither
aus. `presence_penalty` 0,5, weil 1,5 die Wiederholung besteuert, von der
eine Faktentabelle lebt.

## 4. Warum es nicht reicht — Diagnose

1. **Der Ein-Aufruf-Schreiber ist der Engpass.** Seit DR3 liefert die
   Beschaffung (DR4: 49 geprüfte Fakten aus 20 Quellen, 28 Kalender-
   Kandidaten, 8 Wirkstoffe, 9 Landkartenzeilen). Der Bericht wurde trotzdem
   kürzer und zahlenärmer (DR4: 1.911 Wörter, 15 Zahlensätze; DR3: 2.926 /
   28; Sonnet: 1.997 / 25). Je mehr Banken der Prompt trägt, desto knapper
   schreibt das 4-Bit-27B. Der Deep-Research-Text gewinnt genau dort: zwölf
   Wirkstoffe mit Phase, Endpunkt, Zahl; SEC-verifizierte Umsätze;
   Warenkorbdaten.
2. **„Jüngste Aussage je Akteur" hebt Pressemeldungs-Trivia über Substanz.**
   DR4s erster Entscheidungssatz war eine 21 Monate alte FDA-Generika-
   Zulassung („today"). Die Landkarte braucht einen Substanzfilter
   (Studienzahl, Prozent, Betrag vor Zulassungsroutine) und ein Zeitfenster.
3. **Kalender:** nackte Jahreszahl des laufenden Jahres gilt als offen (Indien/
   China-Ablauf war im März 2026), Dubletten über Zeilen werden nicht
   erkannt, fachfremde Wirkstoffe (SGLT2) rutschen mit.
4. **Aufwand:** Förderobergrenzen und fremde Finanzierungsrunden sind keine
   übertragbaren Kosten. Es gibt keine Suchrichtung nach **Kosten**
   (Rezeptur, EFSA-Dossier, Linienumbau).
5. **Rechtswissen im Optionsschritt fehlt:** EIC-Grant nur für KMU ≤ 250
   Mitarbeiter; Rx-Werbeverbot gegenüber Verbrauchern (RL 2001/83/EG). Das
   Rückgrat kennt Instrumente, nicht deren Anwendungsbereich.
6. **Was funktioniert und bleiben soll:** Primäranteil 50–75 % mit
   Kennzeichnung, Claims-Regime (VO 1924/2006) im Zentrum, Optionen mit fünf
   Feldern, ehrliche Offene-Fragen-Liste, eigene Korpus-/Patentmessung als
   Alleinstellung.

## 5. Wiederaufnahme — was als Nächstes zu tun wäre

In dieser Reihenfolge, jeder Punkt einzeln prüfbar:

1. **Kapitelweises Schreiben** (WebWeaver/Co-STORM, Muster M4 der
   Harness-Sichtung `scratchpad/glp1/harness_survey.md`): je Pflichtkapitel
   ein Schreibaufruf mit *nur* seiner Evidenzbank (Recht ← Sweep-Protokoll
   Recht; Kalender ← Kandidaten; Was sich bewegt ← Landkarte + Faktenzettel;
   Optionen ← Anker + Rechtsprotokoll) und Wortbudget; Kurzfassung zuletzt
   aus den fertigen Kapiteln. Prüfung und Streichung bleiben, wie sie sind.
   Erwartung: Spezifität und Abdeckung, weil der Schreiber je Kapitel 4k
   statt 80k Token Belege sieht.
2. **Landkarte mit Substanzfilter**: Zeilen mit Prozent/Betrag/n vor
   Zulassungsroutinen; Zeitfenster 18 Monate; keine Pressemeldungs-
   Überschriften als Aussage.
3. **Kalender**: Jahr-ohne-Monat im laufenden Jahr nur mit Quartal/Monat;
   Dubletten über normalisierte Ereignisse; Wirkstoffklasse gegen das Thema
   prüfen.
4. **Kosten-Sweep** für die Aufwands-Anker (`"{t} development cost per
   product"`, `"EFSA health claim dossier cost"`, `"reformulation cost per
   SKU"`) und Anker nur aus Kostenaussagen.
5. **Anwendungsbereich von Instrumenten** im Rückgrat (Adressatenklasse,
   Verbotsnormen) und ein Optionsfilter dagegen.
6. **Themenneutralität belegen**: ein voller DR-Lauf zu einem Nicht-Pharma-
   Thema (Vorschlag: „solid-state batteries", Probe liefert QuantumScape/
   Solid Power/Toyota/Samsung SDI als Saatgut, ECO+TECH-Rückgrat) mit
   Blindgutachten gegen ein Deep Research zum selben Thema.

Kosten je Iteration: Lauf ~30 min GPU (27B exklusiv), Gutachten ~10 min
Subagent (~180k Token), Doku/Commit ~10 min.

## 6. Kommandos und Dateien

```bash
# Auftrag anlegen (DR-Modus) und Lauf starten
.venv/bin/python - <<'PY'
from pipeline.db import get_connection
with get_connection() as c:
    c.execute("insert into dossier_orders (slug, topic, question, params_json, status) "
              "values (%s,%s,%s,%s,'queued')",
              ("glp1-dr5", "GLP-1 and incretin technology", "<Frage>", '{"dr": true}'))
PY
DOSSIER_DR=1 LLAMACPP_TIMEOUT=1200 nohup .venv/bin/python -m scripts.dossier_worker --order <ID> \
    > scratchpad/glp1/DR5_run.log 2>&1 &

# Dokument und Anhang auf die Platte, Messung, Blindpaar
.venv/bin/python scratchpad/glp1/extract.py <dossiers.id> DR5
.venv/bin/python scratchpad/glp1/jury_metrics.py scratchpad/glp1/DR5_final.md scratchpad/glp1/C_sonnet.md
# Blindpaar: zwei Dateien report_<X>.md / report_<Y>.md mit zufälligen Buchstaben + Schlüsseldatei,
# Gutachter-Subagent mit dem Protokoll aus Abschnitt 1 (Vorlage: Prompt in dieser Session, Ergebnis jury_19.md)

# Themenneutralitäts-Probe ohne Lauf (Profil gegen den laufenden llama-server)
.venv/bin/python scripts/dossier_topic_probe.py "solid-state batteries" --brave --read 5
```

| Was | Wo |
|---|---|
| Läufe (Bericht/Anhang/Protokoll) | `scratchpad/glp1/DR{,2,3,4}_final.md`, `*_annex.md`, `*_run.md`, `*_run.log` |
| Gutachten | `scratchpad/glp1/jury_1.md … jury_19.md` (Blindschlüssel im Session-Scratchpad `blind*_key.txt`) |
| Vergleichstext | `scratchpad/glp1/C_sonnet.md` |
| Messung | `scratchpad/glp1/jury_metrics.py`, `metrics.py` |
| Harness-Sichtung | `scratchpad/glp1/harness_survey.md` |
| Rundenchronik | `docs/agentic_dossiers.md` (Runden 5–14) |
| Code | `scripts/corpus_research.py` (Sweeps, Profil, Faktenzettel, Kandidaten, Landkarte, Reparatur), `pipeline/dossier_structure.py` (Prüfung, Streichung), `pipeline/dossier_check.py`, `scripts/dossier_worker.py`, `pipeline/llamacpp_client.py` (Sampling, `enable_thinking`) |
| Tests | `tests/test_dossier_dr_mode.py` (136), `tests/test_dossier_decision.py` |
| Desk | `/trends/dossiers` (Owner-Instanz :3001/:3004), Dossiers #25–#29 im Status `review` |

## 7. Status-Markierung

Der DR-Modus ist **Feature in Development**: lauffähig, getestet (1.447
pytest), per `params = {"dr": true}` bzw. `DOSSIER_DR=1` einschaltbar, im
Desk nicht als Schalter exponiert, Default aus. Der Standardpfad des
Dossier-Tools (ohne DR) ist davon unberührt.
