# Ops-Logbuch

Protokoll und Planung von Läufen und Hardware — angezeigt auf `/trends/ops`
(#104). Ein Eintrag = eine `##`-Überschrift mit festem Kopf:

    ## <Datum> · <Art> · <Titel>

Datum `YYYY-MM-DD`, optional mit Uhrzeit `YYYY-MM-DD HH:MM`; für Ideen ohne
Termin reicht `YYYY-MM`. Arten: **change** (ist passiert), **plan** (mit Datum —
erscheint im Wochenplan der Seite), **decision**, **idea**. Direkt unter der
Überschrift dürfen `schlüssel: wert`-Zeilen stehen, die der Wochenplan liest:
`duration: 3h` (auch `45m`, `2h30m`, `1d`) und `gpu: local|bequiet`. Danach
Freitext in Markdown. Neueste Einträge oben ist Konvention, die Seite sortiert
selbst. Bearbeiten im Editor, committen — keine zweite Wahrheit in der DB.

## 2026-09 · plan · Backfill Volltext-Vektoren, 1,7 Mio Einträge
duration: 16h
gpu: bequiet

Termin offen (Owner: grünes Licht nach einer sauberen Nacht mit allen drei
neuen Funktionen). Nur im bequiet-Fenster (01:00–17:00), geschätzt zwei bis drei
Fenster — mit Tag und Uhrzeit im Kopf erscheint der Eintrag im Wochenplan. Vorher:
eine saubere Nacht mit Batch 3000 und ein Blick auf die Ops-Seite, ob der
09:00-Lauf remote lief. `scripts/embed_full_text_gpu.py --limit 0 --apply`
(oder in Portionen mit `--limit 300000`). Danach `compare_vector_spaces.py
--kind patent` — der A/B-Test, den der Owner sich gemerkt haben will.

## 2026-09 · plan · bequiet von Ollama auf llama.cpp umstellen
gpu: bequiet

Drei Punkte, die dann anstehen: (1) `pipeline/remote_gpu.embed_batch_remote`
von `/api/embed` auf `/v1/embeddings` — llama.cpp holt kein Modell bei Bedarf,
das Embedding-Modell muss dort VORHER geladen sein; (2) den llama-server auf
bequiet mit `--host` an die Tailnet-Adresse binden; (3) die
Modell-Identitätsprüfung (`/v1/models`, wie lokal seit #98) auch für bequiet
aktivieren — sonst dasselbe Loch wie am 05.09.: ein Server, der auf alles mit
200 OK antwortet. Der Ops-Sampler ist schon backend-neutral (`/health` oder
`/api/ps`), an der Seite ändert sich nichts.

## 2026-09-11 · change · Ops-Dashboard: Sampler, Laufprotokoll, Seite
Stufen 1–3 von #104. Timer misst minütlich (`ops_samples`), alle Wrapper und
Python-Crons protokollieren ihre Läufe (`ops_events`), `/trends/ops` zeigt es.
SMART freigeschaltet: alle vier Platten PASSED. Die Lexar NM790 meldet „240
Betriebsstunden" — das ist KEINE Stundenzahl: sie steckt seit der
Ubuntu-Installation am 13.05.2026 im Rechner (120 Tage, Uptime allein > 600 h).
Der Maxio-Controller zählt in einer anderen Einheit; für die Beurteilung dieser
Platte gelten Verschleiß (1 %), Reserve (100 %) und Medienfehler (0), nicht die
Betriebsstunden.

## 2026-09-11 · change · Cycle-Batch 600 → 3000, Embedding-Tageslimit 30.000
Nachtlauf soll einen normalen Tag in EINEM Durchgang schaffen (vorher jede
Nacht ein zweiter Lauf mit einem kompletten Stage-8-Pass, ~28 min). Embedding
09:00 auf 30.000, damit der Samstag (Wochen-Ingester) in einem Lauf durchgeht.
Erste Nacht mit beidem: 12.09.

## 2026-09-10 · change · RTX 5080 auf bequiet als zweite GPU
Tailnet 100.119.239.40, Ollama auf :11434, 16 GB (13,9 frei am Sperrbildschirm).
Owner-Fenster 01:00–17:00. Gemessen: 12,4 Texte/s gegen 6,6/s lokal, cos 0,9995
zwischen beiden — Vektorräume austauschbar. Der 09:00-Lauf am 11.09. lief komplett
dort: 19.294 Vektoren in 29 min, die 3090 blieb unberührt.

## 2026-09-10 · decision · Volltext-Aufbewahrung 14 Tage → 60 Monate
§44b Abs. 2 S. 2 UrhG nennt keine Frist, sondern bindet sie an den Zweck;
dokumentierter Zweck ist die längsschnittliche Trendanalyse. Nachhollauf holte
32.234 von 34.484 gelöschten Volltexten zurück.
