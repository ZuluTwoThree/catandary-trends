---
name: field-setup
description: Map a customer's technology field to Field Watch / Trajectory Sheet search phrases and CPC anchors (fields/<customer>.yaml), with corpus counts per tier and an owner checklist. Use when a new customer field, a field probe, or a "Feld einrichten" request comes up.
---

# Feld einrichten (Field Watch / Trajectory Sheet)

Ziel: eine Kundenphrase („Präzisionsfermentation", „LFP-Zellen") wird zu einem Feld in
`fields/<kunde>.yaml` — Suchphrasen (Englisch, `phraseto_tsquery`) + CPC-Anker. Das Mapping
macht der Owner, der Kunde gibt es frei; es steht auf jedem Blatt. Du bereitest nur vor.

## Werkzeuge

- MCP `catandary-corpus` (`.mcp.json`): `term_counts`, `search_signals`, `search_patents`,
  `search_research`, `field_probe`, `tir_block`, `field_list`.
- Optional der Modell-Vorschlag: `scripts/field_research.py setup "<phrase>"` (GPU-Handover;
  schreibt einen YAML-Entwurf mit Zählung nach `data/field_watch/_owner/drafts/setup/`).
- CPC-Vorschlag mit GPU: `scripts/field_watch.py --probe "<phrase>"`.

## Ablauf

1. **Phrase zerlegen:** Kernbegriff, Synonyme, Produktkategorien, Verfahren, eindeutige
   Abkürzungen. Englisch, 2–4 Wörter je Phrase. Mehrdeutige Kürzel (z. B. „LFP" allein) nur
   als Teil einer Phrase.
2. **Zählen:** `term_counts` mit allen Kandidaten. Eine Phrase trägt, wenn sie in mindestens
   zwei Ebenen Treffer hat oder in einer Ebene deutlich (≥ 20). Unter 5 Treffern gesamt: raus.
3. **Gegenprobe auf Fehltreffer:** für jede starke Phrase `search_signals` (mode text, limit 10)
   und `search_patents` (limit 10) — passen die Titel zum Feld? Phrasen, die fremde Felder
   ziehen, streichen oder verengen.
4. **CPC-Anker:** aus `search_patents`-Treffern die häufigen Klassen notieren, dann
   `tir_block` für 1–3 Kandidaten. Ein Anker taugt, wenn `n_patents` ≥ 300 und die Klassen
   inhaltlich passen. Sonst kein Anker (Reifegradblock bleibt leer — das Blatt sagt es).
5. **Feldprobe:** `field_probe` mit Phrase, Begriffen und Anker → Take-off je Ebene, Summen.
   Unplausible Sprünge = meist eine zu breite Phrase.
6. **Vorlage:** YAML-Block für `fields/<kunde>.yaml` (Format wie `fields/example.yaml`) plus
   Tabelle Begriff × Ebene, gestrichene Begriffe mit Grund, Anker mit `n_patents`.

## Regeln

- Nichts in `fields/<kunde>.yaml` schreiben, ohne dass der Owner es freigibt.
- Keine Zahl ohne Werkzeugaufruf; Zählungen sind Korpus-Messungen, keine Marktstatistik.
- Kundendateien sind gitignored — nie committen.
