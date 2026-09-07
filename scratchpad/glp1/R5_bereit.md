# Runde 5 — Web-Schicht auf Augenhöhe, bereit für deinen Lauf

Stand 2026-09-07 · Branch `dev` · kein Dossier-Lauf gestartet, keine GPU berührt.
Commits: `4fea4ca` (Kern), `f222403` (Tests + Dossier-Ansicht), `ea7d16c` (Filter-Fix
aus der Probe), `373d5a8` (Akteure vor Wirkstoffen in der Markt-Welle) und der
Doku-Commit mit dieser Datei plus `docs/corpus_research_sketch.md`.

Alles betrifft `scripts/corpus_research.py`; die Defaults ziehen
`scripts/dossier_worker.py` und die Dossier-Ansicht im Frontend mit.

---

## 1. Budget und Tiefe — Ziel 40–60 gelesene Seiten

| Stelle | vorher | jetzt |
|---|---|---|
| `--web-steps` / `--web-sources` | 8 / 12 | **14 / 32** |
| Recht/IP-Sweep | 6 Muster × 2 Treffer, 8 Volltexte | **8 × 3, 12 Volltexte** |
| Markt/Erstattung | 6 × 2, 8 Volltexte | **8 × 3, 12 Volltexte** |
| Wirkstoff/IP (neu) | — | **3 Entitäten × 4 Muster × 2, 8 Volltexte** |
| Akteur/Ereignis (neu) | — | **4 Entitäten × 4 Muster × 2, 8 Volltexte** |
| Abdeckungs-Sweep | 2 Treffer je offener Frage | **4** |
| Lese-Auffangnetz | 6 Seiten, 1 je Frage | **12 Seiten, 2 je Frage** |

Obergrenze: **44 feste Suchanfragen** plus Agentenstufe, **40 Volltexte** aus den festen
Richtungen plus bis zu 12 (Auffangnetz) und ~8 (Agentenstufe). Nach robots/403 landet das
real im Zielband 40–60. Die globalen Kappen liegen bewusst auf `Muster × per_pattern`,
damit die späten Muster (EFSA, EU-Recht) nicht von den frühen ausgehungert werden.

Relevanzfilter **vor** dem Abruf (`web_relevant`): Titel, Snippet oder URL muss einen
Themen- oder Entitätsbegriff tragen. Zwei Sicherungen dagegen, dass der Filter selbst
zum Verlustgrund wird: Registerseiten (Rang 0) sind ausgenommen, und eine
**Rückfallschwelle** lässt den bestplatzierten Treffer herein, wenn eine Anfrage sonst
komplett verstummt.

**Kein stilles Verwerfen mehr** (der Askea-Fehler): jeder am Budget verworfene Treffer
wird gezählt, in den Evidenznotizen im Klartext benannt und im Coverage-Anhang wie in
der Dossier-Ansicht ausgewiesen.

## 2. Query-Vielfalt — die zweite Welle aus dem eigenen Katalog

`harvest_entities()` zieht **deterministisch** (kein Modell-Hop) Akteure aus Titeln und
Snippets des bisherigen Materials: 1- bis 3-Gramme aus Großschreibungsläufen mit
Dokumentfrequenz ≥ 2 (Title-Case-Füllwörter wie „Wins", „Court Battle" und Outlet-Namen
fallen raus), dazu Wirkstoffnamen an ihren INN-Endungen. Geerntet wird **zweimal**: vor
der ersten Welle (aus dem Korpus — damit der Filter der ersten Welle die Akteure schon
kennt) und danach noch einmal über dem gesamten Material.

Neue Vorlagen:

* **Wirkstoff/IP** (`SUBSTANCE_LEGAL_PATTERNS`, je Wirkstoff):
  `"<W>" SPC supplementary protection certificate` ·
  `supplementary protection certificate <W> expiry` ·
  `<W> patent expiry Europe` · `<W> court ruling generic`
* **Akteur/Ereignis** (`ENTITY_MARKET_PATTERNS`, je Entität):
  `<E> acquisition deal agreement announcement` · `<E> reimbursement pricing decision` ·
  `<E> phase 3 trial results readout` · `<E> revenue guidance quarterly results`

Themen-Vorlagen erweitert: Recht 6 → 8 (u. a. `"{t}" SPC …`, `{t} patent expiry Europe
generic entry`), Markt 6 → 8 (Lieferengpass/Kapazität, Generika-/Biosimilar-Eintritt).

## 3. Register-/Rechtsabfragen und Domain-Priorisierung

`source_rank()`: Rang 0 = Register/Behörde/Gericht/Gesetzgeber (EPO, Espacenet, EMA,
FDA, NICE/NHS, rechtspraak.nl, curia, legifrance, G-BA, SEC … plus die Endungen `.gov`,
`.europa.eu`, `.gouv.fr`, `.gov.uk`, `.bund.de`, …), Rang 1 = eigene Seite einer
bekannten Entität (Domain trägt den Namen → Firmen-Newsroom, ohne Firmenliste), Rang 2 =
Sekundärpresse. `rank_hits()` liest Primärquellen zuerst — das Lesebudget geht also
zuerst an Register und Behörden.

### Ergebnis der Probe (6 echte Suchanfragen, Limit war 10)

Die vier Wirkstoffmuster gegen „semaglutide" erreichen **alle drei** Belege, an denen
jede Jury das Dossier hat scheitern lassen:

| Anfrage | Fundstelle |
|---|---|
| `semaglutide patent expiry Europe` | „The compound patent … **EP 1 863 839** — expired in March 2026" (techtimes.com) |
| `"semaglutide" SPC supplementary protection certificate` | „SPC extending the patent term by five years **until 2031**" (patentlawyermagazine.com); dazu die Novo-Nordisk-Mitteilung zum SPC-Verletzungsurteil (globenewswire.com) |
| `semaglutide court ruling generic` | „**District Court of The Hague** … preliminary injunction on August 5" (techtimes.com, kffhealthnews zum Indien-Urteil) |
| `supplementary protection certificate semaglutide expiry` | Zeitleisten je Markt (formblends, drugdiscoverytrends: Kanada-Register mit Ablaufdatum) |

Die beiden **themenbasierten Gegenproben** (`"GLP-1 receptor agonist" SPC …` und
`GLP-1 receptor agonist patent expiry Europe generic entry`) erreichten **keinen** dieser
Belege — nur Übersichtsartikel und Fachliteratur. Der fehlende Hebel war also der
**Wirkstoffname**, nicht die Suchmenge. Das ist der ehrliche Befund: Runde 1–4 hätten mit
mehr Budget allein nichts gefunden.

**Nebenbefund, der die Probe wertvoll gemacht hat:** der frische Relevanzfilter hätte die
Seite mit dem entscheidenden Befund („Novo received a patent … SPC until 2031") verworfen
— sie sagt „Novo", der Filter kannte „novo nordisk". Behoben mit `entity_terms()`
(Einzeltoken jeder Entität, ohne Füllwörter); nachgerechnet über alle 36 Treffer der
Probe: **36/36 zugelassen**, darunter alle drei Belege. Commit `ea7d16c`.

## 4. Fetch-Robustheit

`fetch_web_page_status()` gibt jetzt `(Text, Grund)` zurück, `fetch_log` im Ledger hält
je Treffer `fetched` / `robots` / `blocked` (401/403/429/451) / `timeout` / `too_short` /
`tdm` / `budget`. Der Coverage-Anhang und die Dossier-Ansicht zeigen die Gründe.
**Der Produktions-UA bleibt** (`CRAWLER_USER_AGENT`) — eine Botsperre wird ausgewiesen,
nicht umgangen; die Seite bleibt unzitierbar.

Gegenprobe: die drei Schlüsselseiten oben sind mit dem Produktions-UA abrufbar
(`fetched`, je 2.400 Zeichen; enthalten „EP 1 863 839", „2031", „Hague", „SPC").

## 5. Kein Aufblähen des Berichts

Die Längenbremse (2.200–2.800 Wörter Fließtext) ist **unverändert**. Damit die
Zusatzmenge trotzdem ankommt:

* gefetchte Seiten gehen als **Schlüsselpassagen** (`key_passages()`, ~1.200 Zeichen:
  Absätze mit Themenbegriffen und Zahlen, Lead immer dabei) in die Evidenznotizen — der
  Volltext bleibt an der Quelle, wo die Beleg-Verifikation ihn Satz für Satz prüft;
* Audit und Bericht bekommen ein eigenes Evidenzbudget (**78k statt 30k Zeichen**), die
  Agenten-Hops nicht. Ohne das hätte der FIFO-Verwurf ausgerechnet die Recht-/Markt-
  Volltexte zuerst weggeworfen — sie laufen als erste.

---

## Dein Kommando

Voraussetzung wie immer: llama-server mit dem 27B auf :8090 (der Handover in
`dossier_worker.py` macht das selbst; direkt aufgerufen musst du swappen).

```bash
cd /home/dirk/projects/ct-dev
.venv/bin/python -m scripts.corpus_research \
  --foresight "GLP-1 receptor agonist" \
  --quant \
  --slug glp1-r5 \
  --out data/dossiers/glp1_r5.md \
  -v > data/dossiers/glp1_r5.log 2>&1
```

Die neuen Kappen sind **Defaults** — nichts zusätzlich zu setzen. Wer sie explizit
sehen will: `--web-steps 14 --web-sources 32`.

Zum Vergleichen des alten Verhaltens: `--web-steps 8 --web-sources 12` (die zweite Welle
und die Filter laufen dann trotzdem — der echte Vorher-Stand ist `git show 21b3059`).

### Worauf du im Log achten kannst

* `entities from the corpus catalog: …` und `entities after the first wave: …` — wenn
  dort keine Wirkstoffe stehen, greift die Wirkstoff-Welle nicht (dann fällt sie auf die
  allgemeinen Entitäten zurück).
* `second wave: +N substance/IP, +M entity/event source(s)`
* je Sweep-Zeile: `… hit(s), N admitted, M read, K dropped (budget J)`
* im Dossier unten: „Research coverage" nennt jetzt je Zeile auch die nicht
  aufgenommenen Treffer und die Lesehindernisse.

### Risiken, die du kennen solltest

1. **Laufzeit.** ~44 feste Suchanfragen à 1,1 s Drossel plus bis zu ~60 Abrufe: der Lauf
   wird grob 5–10 Minuten länger als Runde 4.
2. **Brave-Kontingent.** Ein Lauf verbraucht jetzt ~50–60 Anfragen statt ~20.
3. **Prefill.** Audit- und Berichts-Prompt tragen bis zu 78k Zeichen Evidenz (~20k Token)
   — im 262k-Kontext des 27B unkritisch, aber spürbar in der Vorlaufzeit dieser Hops.
4. **Entitäts-Ernte ist heuristisch.** Bei einem Thema mit dünnem Korpusmaterial können
   die Entitäten mager oder schief ausfallen; die Wellen laufen dann kleiner, nicht
   falsch. Was geerntet wurde, steht im Log.
5. **Die zwei strukturellen Verlustgründe bleiben offen** (Rechtsstatus als Datenquelle
   statt Suchergebnis, CPC-Unschärfe bei Wirkstoffen). Diese Runde adressiert nur den
   dritten. Erwartung entsprechend kalibrieren.
