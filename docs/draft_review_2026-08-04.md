# Durchsicht der Review-Warteschlange, 2026-08-04 (#71)

Anlass: Der Owner hat begonnen, die Warteschlange manuell abzuarbeiten (16 Artikel
am 03.08.), und die Beobachtung geäußert, Fehler seien häufiger, wenn der
Originalartikel kürzer ist als der Entwurf.

## Die Hypothese trifft so nicht zu — die Ursache lag im Detektor

Die Hold-Rate ist über alle Längenverhältnisse hinweg flach (0,9–1,5 %). Innerhalb
der gehaltenen Artikel liegen die mit kurzer Quelle etwas höher (1,08 beanstandete
Tokens gegenüber 0,77), aber das erklärt die Warteschlange nicht.

Die eigentliche Ursache: **von 135 gehaltenen Artikeln waren 72 gar nicht falsch.**
Der Grounding-Gate hatte drei blinde Stellen, die er als Fabrikation meldete.

| Blinde Stelle | Beispiel | befreit |
|---|---|---|
| CJK-Quellen: `\b` findet zwischen Ziffer und CJK-Zeichen keine Grenze, die Zahl blieb unsichtbar | „140以上の通貨" → Body „140 currencies" | 34 |
| Quelle nennt die Zahl als **Wort**, Body als Ziffer | „Around half of melanomas" → „50% of cases"; „halbe Milliarde" → „€500 million" | 34 |
| Ziffern in **Eigennamen** | `COVID-19`, `LTG-001`, `PAC-3` | 4 |

Behoben in `pipeline/grounding.py` und dem TS-Port `frontend/src/lib/grounding.ts`
(Commits 2a290b7, 1ebdee8 auf main; 86e2513, 80e3cf2 auf dev). Beide Implementierungen
sind per Differenztest über alle 135 Live-Artikel als deckungsgleich verifiziert.

Wichtig für die Schärfe des Gates: wortimplizierte Zahlen matchen **nur exakt** und
speisen die Substring-Toleranz nicht — sonst würde eine aus „fünf" implizierte „5"
jedes „150" durchwinken. Die Namensregel greift nur bei großgeschriebenem Präfix,
damit „the under-25 demographic" beanstandet bleibt (dort ist die Zahl echt erfunden).
Drei Tests halten genau diese Grenzen fest.

## Entscheidungen über den Restbestand

### Verworfen: 14 abgeschnittene Entwürfe

Bodies, die mitten im Satz enden — teils nach 90 Zeichen. Defekte Generierungen,
kein inhaltliches Problem. Die Signale bleiben in `raw_entries` erhalten.

`1129352, 1128452, 1128131, 1128041, 1127579, 1127323, 1124387, 1122816, 1122542,
1122337, 1120355, 1119703, 1118948, 1115336`

### Verworfen: nachweislich erfundene Spezifika

Bei diesen steht die Zahl (bzw. der Fakt) **nicht** im vollen Quelltext und lässt
sich auch nicht daraus ableiten. Umkehrbar über die DB, falls eine Einschätzung
nicht geteilt wird.

| ID | Erfindung | Quelle sagt |
|---|---|---|
| 1131338 | „under-25 demographic" | nur „young adults living with their parents" |
| 1130452 | „ChatGPT **Plus**" | Revolut bietet ChatGPT **Go** — falsches Produkt |
| 1129653 | „70 percent surge … viral social media post" | X-Fab investiert 400 Mio. € in Erfurt; nichts davon |
| 1126892 | „surpassed 200,000 points" | Quelle nennt keine einzige Zahl |
| 1126859 | „strongest recorded in 150 years" | „strongest on record" |
| 1126317 | „values Aypa Power at $7 billion" | keine Bewertung genannt |
| 1124820 | „valuing the firm at $700 million" | nur $40 Mio. Investment |
| 1125666 | „80 % … 85 %" | beide Werte fehlen |
| 1123821 | DOI „10.1088" + „Nature Communication" | DOI ist 10.1038, Journal ist Nature Communications |
| 1122541 | „9.000 t, 10 % unter 10.000-t-Schnitt" | keine Erntemengen genannt |
| 1120348 | „12-month median" | Vergleichswert fehlt |
| 1131064 | „30 % threshold" | Quelle: 26 % Ist, 37 %, 50 % Wachstum |

### Verworfen: erfundene Zeithorizonte

Der Schluss-Satz des Modells setzt eine Jahreszahl, die die Quelle nicht nennt —
formal eine Prognose, gelesen wird sie als Fakt. Für ein Produkt, das mit
Belegbarkeit wirbt, ist das genau der Fall, für den der Gate existiert.

`1129176 (2030), 1128953 (2029), 1126798 (2026/27), 1124092 (2027), 1123594 (2026),
1123452 (2040), 1122649 (2025), 1121581 (2025)`

### Bleibt zur Sichtung: korrekte Ableitungen

Diese sind **richtig**, der Gate kann die Herleitung nur nicht sehen. Sie bleiben
bewusst in der Warteschlange — Veröffentlichen ist eine redaktionelle Entscheidung,
keine automatische.

| ID | beanstandet | Herleitung |
|---|---|---|
| 1129238 | 200 MW | 300 MW gesamt − 100 MW erste Stufe |
| 1127797 | 420 MWh | 500 MWh gesamt − 80 MWh Kalifornien |
| 1123265 | 100.000 Token | 372k − 272k |
| 1127583 | 23 weitere | 25 Unterzeichner − 2 namentlich genannte |
| 1129121 | 2031 | „in five years", Artikel von 2026 |
| 1126322 | 2050 | „in the next 24 years", Artikel von 2026 |
| 1125438 | 0,4 % | 67,8 % → 68,2 % |
| 1124657 | 24 Stunden | „daily" |
| 1115654 | Round of 16 | „Achtelfinale" |
| 1119395 | $1 Mrd. | „unicorn" ist definitorisch $1 Mrd. |
| 1122354 | 60 % | $100 Mrd. Peak → $40 Mrd. |

Ob diese Klassen (Differenzrechnung, Zeitableitung, Definitionswissen) automatisch
erkannt werden sollen, ist bewusst **offen gelassen**: Arithmetik-Erkennung würde
auch erfundene Zahlen durchwinken, die zufällig einer Differenz entsprechen. Der
Preis wären ein paar Handgriffe pro Woche gegen ein messbar stumpferes Gate.

## Erwartete Wirkung auf den Morgenbetrieb

Die Warteschlange war über rund drei Wochen auf 135 gewachsen (~6 pro Nacht). Mit
den drei Fixes fallen etwa die Hälfte der Neuzugänge weg, der Zulauf liegt damit
bei rund 3 pro Nacht — innerhalb des angepeilten Rahmens von 5–20 Artikeln, die
sich morgens in einem Durchgang erledigen lassen.

`trends.reviewed_at` (Migration `scripts/migrate_reviewed_at.py`) hält ab sofort
beide Entscheidungen fest, Veröffentlichen wie Verwerfen — vorher hinterließ eine
Ablehnung überhaupt keine Spur und der Fortschritt war nicht messbar.

---

## Nachtrag 2026-08-05: drei weitere Fehlalarm-Klassen

Aus dem ersten Nachtlauf nach den Fixes (5 Holds) meldete der Owner Artikel, die
an Abkürzungen und Datumsformaten hängen blieben. Alle drei waren derselbe Typ —
der Gate sieht eine Ziffernfolge, die keine Messgröße ist oder nur anders
geschrieben steht als in der Quelle.

| Klasse | Beispiel | Ursache |
|---|---|---|
| Ziffern **kleben** an einem Namen | `CO2`, `B2B`, `Inspire360`, `PM2.5` | Die Namensregel vom 04.08. verlangte einen Bindestrich (`COVID-19`) |
| Dasselbe Datum, zwei Schreibweisen | Quelle „04 August 2026" ↔ Body „August 4, 2026" | Führende Nullen wurden nicht normalisiert; ein Tag ist mit 1–2 Zeichen zu kurz für die Substring-Toleranz |
| **Mittelpunkt** als Dezimaltrenner | The Lancet: „13·4%" (U+00B7) ↔ Body „13.4%" | Dieselbe Familie wie die deutschen Komma/Punkt-Unterschiede |

Die Namensregel bleibt eng: die Ziffern müssen **direkt anhängen**. „August 4"
und „Under 25" sind getrennte Tokens und werden weiter geprüft.

**Gegenzug zur Schärfe:** die Substring-Toleranz verlangt jetzt, dass *beide*
Seiten länger als zwei Zeichen sind. Ohne führende Nullen würde ein Quell-„04"
sonst ein erfundenes „400" durchwinken. Das kostet einen zusätzlichen echten
Fund: **#1115523** nennt EU-AI-Act-Strafen (35 Mio. €, 7 % des Weltumsatzes) —
die Quelle enthält keine einzige Zahl. Genau dafür existiert der Gate.

Beanstandete Artikel in der Warteschlange: **30 → 17**. Die drei gemeldeten
Artikel (#1132985, #1132597, #1132593) sind sauber und veröffentlicht.

---

## Nachtrag 2026-08-06: die Verschärfung hätte die Queue wieder wachsen lassen

Anlass war eine Beobachtung des Owners („heute waren es nur wenige Drafts"). Der
Betrieb bestätigt sich: 6 Holds aus 492 Artikeln mit Confidence ≥ 0.85 (1,2 %),
zwischen 20:39 und 20:41 von Hand entschieden — die ganze Warteschlange in zwei
Minuten. Pipeline-Durchsatz normal (881 Trends aus 1.471 Einträgen, rc=0).

Beim Gegenprüfen fiel aber auf, dass die Substring-Verschärfung vom 05.08. einen
Preis hatte: **16 von 3.384** automatisch veröffentlichten Artikeln der letzten
neun Tage wären nach neuem Code beanstandet worden (0,47 %) — die Queue wäre also
langsam wieder gewachsen. Die Ursachen waren erneut Artefakte:

| Klasse | Beispiel | Quelle |
|---|---|---|
| **Bezeichner** mit Leerzeichen | „Scope 1 emissions", „Article 6 market", „MAX 8" | Namensregel verlangt anklebende Ziffern |
| **Abgekürzte Dekade** | Body „the 1980s" ↔ Quelle „the '80s" | — |
| **Skalenwort** | Body „2,500 products" ↔ Quelle „2.5 thousand products" | — |

Die Bezeichner-Liste ist bewusst **explizit** (Scope, Article, Phase, Tier, Level,
Class, Annex, MAX …) statt einer generischen Regel „Großbuchstabe + Leerzeichen +
Zahl". Letztere würde auch „Under 25" und „August 4" entschuldigen — genau die
Fälle, in denen die Zahl eine echte Aussage trägt. Ein Test hält das fest.

Wirkung: 16 → 10 der auto-veröffentlichten Artikel. Die verbliebenen 10 sind
weit überwiegend die bekannte Klasse „erfundene Jahreszahl im Schluss-Satz", die
bewusst beanstandet bleibt.

Parität diesmal über **3.937** Artikel aus neun Tagen verifiziert, null
Abweichungen zwischen Python-Gate und TS-Oberfläche.

---

## Nachtrag 2026-08-12: was mit verworfenen Artikeln geschieht

Auf die Frage des Owners hin nachgesehen — es war nirgends dokumentiert.

**Bisher:** `status='rejected'` + `reviewed_at`, Zeile bleibt dauerhaft in
`trends` (kein Aufräum-Prozess). Aus dem Produkt verschwunden, weil
`buildFilterClauses` (`frontend/src/lib/db.ts:575`) auf `status='published'`
vorbelegt ist. Der `raw_entry` bleibt `processed=true`, es entsteht also kein
neuer Artikel. Zählt weiter in die „analysiert"-Zahl der Methodik-Seite — was
korrekt ist, er *wurde* analysiert.

**Das Problem:** `get_recent_embeddings` hatte keinen Status-Filter. Verworfene
Artikel blieben damit 30 Tage im Duplikat-Vergleich. Beim Review verwerfen wir
aber den *Text*, nicht die *Geschichte* — ein Artikel mit erfundener Zahl
blockierte so die saubere Zweitfassung derselben Meldung. Die Betroffenheit war
fast vollständig auf Handentscheidungen konzentriert: 36 von 37 lagen im
Dedup-Fenster, gegenüber 5 von 136 Sweep-Ablehnungen.

**Gelöst (Owner-Entscheidung):**

1. `get_recent_embeddings` schließt `status='rejected' AND reviewed_at IS NOT
   NULL` aus — nur Handentscheidungen. Advertorial-Sweeps behalten ihre
   Sperrwirkung, dort ist die Quelle das Problem. `reviewed_at` ist der Marker,
   der beide Fälle trennt.

2. Neuer Knopf **„Write again"**, nur bei abgeschnittenen Bodies sichtbar. Er
   legt den alten Artikel still und setzt den `raw_entry` auf unverarbeitet
   zurück, sodass der nächste Nachtlauf ihn komplett neu durch die Pipeline
   schickt. Ein Deckel von zwei Versuchen pro Signal verhindert, dass eine
   Quelle, die immer abbricht, endlos kreist.

   *Warum stillgelegt statt „zurück auf draft":* Bliebe die alte Zeile ein
   Draft, läge ihr Embedding weiter im Dedup-Fenster und würde die
   Neufassung als Duplikat ihrer selbst töten. Beide Änderungen greifen also
   ineinander. Zusätzlich hält die stillgelegte Zeile den Fehlversuch fest.

   Die Reihenfolge der beiden Schreibvorgänge ist die Sicherheitseigenschaft:
   erst stilllegen, dann öffnen. Scheitert der zweite Schritt, ist das Ergebnis
   eine gewöhnliche Ablehnung — nie ein offener Eintrag neben einem lebenden
   Draft, was zwei Artikel aus einem Signal ergäbe.

**Dabei gefunden:** `reviewed_at` fehlte im Schema von `pipeline/db.py`. Die
Spalte kam per Einzelskript in die Live-DB, wurde aber nie in `init_db`
nachgezogen — eine frische Datenbank hatte sie nicht. Mit dem neuen Dedup-Filter
wäre daraus ein harter Fehler des Dedup-Schritts geworden statt eines fehlenden
Features. Spalte jetzt in beiden Schemata plus idempotente Migration
`_migrate_reviewed_at()`, in `init_db` verdrahtet. (Dasselbe Muster wie die
Stripe-Webhook-Lücke vom 19.07.)

Verifiziert gegen die Live-DB in einer Transaktion mit Rollback: Artikel wird
stillgelegt, Eintrag wieder geöffnet, und die Abfrage des Cycles findet ihn
danach tatsächlich wieder. 182 Python- + 143 Frontend-Tests grün.

---

## Nachtrag 2026-08-12: Newsletter-Links zeigen auf die Quelle

Owner-Entscheidung: Ein zitiertes Signal verlinkt die Redaktion, die es
gemeldet hat — nicht unsere eigene Zusammenfassung davon. „So ist das
Versprechen des Newsletters." Deckt sich mit der Repo-Regel
„Quellennennung ist Pflicht" und gilt **dauerhaft**, nicht nur solange
catandary.de/trends noch 404 liefert.

Umgesetzt am **E-Mail-Rand**, nicht in der Speicherung: die Ausgabe speichert
weiterhin relative Markdown-Links (`[Titel](/trends/slug)`), weil die
Archivseite auf der Website dieselbe Zeile rendert und dort interne Navigation
richtig ist. `_md_links_to_html()` schreibt beim Rendern der Mail um:

| Ziel im gespeicherten Text | in der Mail |
|---|---|
| `/trends/<slug>` | die `source_url` des Signals |
| `/trends/mega` | Site-Link, nur solange `PUBLIC_SITE_LIVE=1` |
| `http(s)://…` | unverändert |

Ein Site-Link, der nicht eingelöst werden kann, wird zu **Klartext** statt zu
einem garantierten 404. Der Schalter `PUBLIC_SITE_LIVE` (Standard: aus) steuert
auch den CTA — solange die Seite dunkel ist, zeigt er auf die Landing-Seite,
die tatsächlich antwortet.

Dafür nötig: `source_url` wird jetzt in der Wochenabfrage geladen und in
`trend_refs` mitgeführt. Die bereits gespeicherte KW-32-Ausgabe wurde
nachträglich befüllt (24 von 24 Zitaten), ohne den Fließtext neu zu erzeugen.

**Dabei gefunden:** die Preheader-Zeile — der Vorschautext im Posteingang —
wurde aus dem *rohen* Markdown gebaut und entfernte nur HTML-Tags. Im
Posteingang stand also wörtlich `[Titel](/trends/slug)`. Sie nutzt jetzt den
konvertierten Text. Ein Test hält das fest.

Neun Tests in `tests/test_newsletter_links.py` sichern das Routing ab, inklusive
der Fälle, die leicht zurückfallen: dass die Quelle **auch bei live geschalteter
Seite** gewinnt, und dass ein unbekannter Slug nicht still die URL eines anderen
Signals erbt.

---

## Vorfall 2026-08-17: Nachtlauf durch unsauberen Neustart abgebrochen

Die Maschine startete um **06:21 unsauber neu** — kein `shutdown`-Eintrag in
`last`, letzte Logzeile aus Nullbytes, vorheriger Boot lief seit dem 30.07.
durch. Der 04:00-Lauf war um 06:20:52 noch in der Content-Generierung.

Damit liefen **Stufe 8 (Reclassify) und Stufe 9 (Auto-Publish) nie**:

| | |
|---|---|
| Trends erzeugt | 858 |
| davon veröffentlicht | 0 (sonst ~55 %) |
| unverarbeitete RSS-Einträge | **0** — Ingestion und Generierung waren fertig |
| Drafts gesamt | 10.105 |
| Morgen-Mail | kam nicht, der Wrapper erreichte die Stelle nicht mehr |

Weil nichts unverarbeitet war, wäre ein voller Cycle falsch gewesen: ~3
GPU-Stunden für nichts, mit dem Risiko, Artikel doppelt zu erzeugen. Der
Wiederanlauf `scripts/resume_cycle.sh` macht deshalb **nur die fehlenden
Schlussstufen** — Stage-8-Modell aufsetzen, `reclassify_drafts()`,
`auto_publisher`, `review_notify`, danach das vorgefundene Modell
zurückstellen.

Geplant per einmaligem systemd-Timer auf **18.08. 02:00** (Owner-Entscheidung),
mit Deadline-Riegel **03:45**: `full_cycle_cron.sh` gibt um 04:00 als Erstes
allen VRAM frei und würde einen laufenden Wiederanlauf mitten im Schreiben
töten — sich selbst sauber zu stoppen ist besser als gekillt zu werden.
Trockenlauf sagt 486 Veröffentlichungen, 36 wegen erfundener Zahlen und 4 wegen
abgeschnittener Bodies zurückgehalten.

**Beim Smoke-Test des systemd-Dienstes gefunden:** `config.py` lädt die `.env`
über `load_dotenv()`, das gegen das **aktuelle Verzeichnis** auflöst. Von
woanders gestartet bleibt `DATABASE_URL` leer und die Pipeline fällt still auf
die alte lokale SQLite-Datei zurück — sie liefe komplett durch und meldete
Erfolg, nur gegen die falsche Datenbank (dort 3.564 Drafts statt 10.105).
Das Skript prüft jetzt vor jeder Arbeit `db.USE_POSTGRES` und bricht sonst laut
ab. Beide Richtungen verifiziert.
