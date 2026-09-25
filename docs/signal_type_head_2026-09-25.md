# Signaltyp-Head — Messbericht 2026-09-25 (#110)

**Anlass.** Seit der Hybrid-Klassifikation (#41, 14.07.2026) kommt der
Signaltyp auf dem Distill-Pfad allein aus der Quellenart; jede Presse-Meldung
wurde `market_shift`. Vorher (LLM-Pfad, 8B bzw. Anthropic-Backfill) gab es
für Presse fünf Klassen. Die Regression fiel bei der Richter-Stichprobe vom
24.09. auf (Partnerschaftsmeldungen als „kein Signal" beanstandet, weil als
Marktverschiebung geschrieben).

**Gebaut.** `scripts/train_signal_type_head.py` — ein fünfter Distill-Head
(`models/distill/signal_type.joblib`), dieselbe Technik wie die vier
bestehenden (SGD log-loss auf L2-normierten 4096er-Embeddings), eigenes
Skript, die vier anderen Heads bleiben unberührt. Verdrahtet in
`DistillClassifier` (liefert `signal_type` + `signal_type_confidence`, None
ohne Datei) und `llm_processor._distill_signal_type(entry, pred)` — auch
`scripts/signal_batch.py` nutzt jetzt diese eine Funktion statt einer Kopie.
Regel bleibt für patent/research/funding; der Head entscheidet nur Presse,
nur mit `DISTILL_SIGNAL_TYPE=1`, nur ab `DISTILL_SIGNAL_TYPE_MIN_CONF`.

## Teacher

Presse-Zeilen (trade_media / press_wire / brand, ohne Patentnummer) mit
Embedding, angelegt vor dem 14.07.2026, Label in den fünf Presse-Klassen:

| Klasse | Zeilen |
|---|---|
| market_shift | 393.307 |
| product_launch | 69.853 |
| regulation | 67.552 |
| partnership | 13.369 |
| consumer_behavior | 8.883 |
| **gesamt** | **552.964** (Training 497.668, Holdout 55.296) |

Laden 288 s (Server-Cursor, 9 GB RAM), Training je Variante ~95 s, CPU.

## Holdout

| Klasse | plain P / R / F1 | balanced P / R / F1 |
|---|---|---|
| market_shift | 0,85 / 0,94 / 0,89 | 0,92 / 0,81 / 0,86 |
| product_launch | 0,77 / 0,62 / 0,69 | 0,67 / 0,79 / 0,72 |
| regulation | 0,76 / 0,55 / 0,64 | 0,62 / 0,76 / 0,68 |
| partnership | 0,77 / 0,37 / 0,50 | 0,46 / 0,83 / 0,59 |
| consumer_behavior | 0,77 / 0,24 / 0,36 | 0,38 / 0,76 / 0,51 |
| Genauigkeit / Makro-F1 | 0,829 / 0,616 | 0,800 / 0,672 |

Gewählt: **balanced** (höherer Makro-F1; die plain-Variante fände von den
seltenen Klassen nur ein Viertel bis ein Drittel). Die geringere Präzision der
kleinen Klassen fängt der Konfidenz-Boden ab:

| Konfidenz ≥ | Anteil der Zeilen | Genauigkeit |
|---|---|---|
| 0,5 | 92 % | 0,83 |
| **0,6** | **76 %** | **0,88** |
| 0,7 | 61 % | 0,92 |
| 0,8 | 44 % | 0,95 |

## Was der Head auf den Presse-Zeilen seit dem 14.07. vergeben würde

48.217 Zeilen, alle heute `market_shift`:

| Boden | market_shift | regulation | product_launch | partnership | consumer_behavior | Head greift |
|---|---|---|---|---|---|---|
| keiner | 43 % | 24 % | 21 % | 7,3 % | 4,4 % | 100 % |
| 0,5 | 52 % | 22 % | 17 % | 5,6 % | 3,2 % | 86 % |
| **0,6** | **64 %** | **18 %** | **13 %** | **3,6 %** | **1,8 %** | **67 %** |
| 0,7 | 75 % | 14 % | 8,6 % | 1,5 % | 0,7 % | 48 % |
| historisch (vor 14.07.) | 71 % | 12 % | 13 % | 2,4 % | 1,6 % | — |

Bei 0,6 liegt die Verteilung am nächsten an der historischen; deshalb ist 0,6
der Default. Ohne Boden überzeichnet die balanced-Variante regulation und
partnership (das ist der Preis für Recall 0,76–0,83).

Titel-Stichproben je Klasse (höchste Konfidenz, published) in
`data/signal_type_head_report.md`: product_launch = Fahrzeug-Debüts und
Produkteinführungen, regulation = Gerichtsurteile, EPA/FDA, Klagen,
partnership = Partnerschaften **und Übernahmen** (so hatte auch der 8B
gelabelt), consumer_behavior = Gen-Z-Verhalten, Umfragen, Adoption.

## Offen (Owner)

1. **Einschalten** — `DISTILL_SIGNAL_TYPE=1` in `scheduled_cycle.sh` und
   `weekly_ingesters.sh` (Cron-Pfad → Merge nach `main` mit Wirkliste), Head
   nach `~/projects/catandary-trends/models/distill/` kopieren.
2. **Bestand nachziehen** (Stufe 2): die 48 k Presse-Zeilen seit dem 14.07.
   gebatcht neu labeln; dabei `SIGNAL_TYPE_FRAMING` **nicht** rückwirkend —
   die Artikel sind geschrieben.
3. Frontend (Stufe 3) ist auf `dev` gebaut: Label auf der Karte, `signal` im
   Suchindex, Chip-Gruppe in der Export-Suche.
