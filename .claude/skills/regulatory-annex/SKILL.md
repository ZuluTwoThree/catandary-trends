---
name: regulatory-annex
description: Research and draft the "Anhang A · Rechtsrahmen" (legal framework annex) of a Trajectory Sheet for a customer field from EU/German primary legal sources, article by article, with a source per statement. Use when a regulatory annex, Rechtsrahmen, or legal overview for a field is requested or a machine draft of it must be checked.
---

# Rechtsrahmen-Anhang (Trajectory Sheet, Anhang A)

Der Anhang ist **geschrieben, nicht gemessen**, und wird vom Owner verantwortet. Ein
maschineller Entwurf (`scripts/field_research.py regulatory <kunde> <feld>`) ist Material,
kein Ergebnis. Diese Anleitung gilt für das Prüfen eines Entwurfs ebenso wie für einen
Anhang von Hand. Grundlage: `docs/dossier_manual_run_2026-09-19.md` (was im Handdurchgang trug).

## Werkzeuge (MCP `catandary-corpus`)

- `eurlex_search(keywords)` — Rechtsakte mit allen Stichwörtern im Titel, Grundrechtsakte zuerst.
- `fetch_url(url, terms=[…])` — EUR-Lex über Cellar, artikelweise geschnitten um die Begriffe;
  gesetze-im-internet.de ebenso. Konform (Bot-Kennung, robots, TDM); kein Text = Grund steht dabei.
- `web_search(query, domains=[…])` — nur mit Domainfilter auf die Quellklasse.

## Ablauf

1. **Pflichtpunkte** festlegen: geltende Rechtsakte · Zulassung/Verfahren · Kennzeichnung ·
   laufende Vorhaben und Fristen · nationale Umsetzung (DE). Je Punkt, was der Kunde wissen muss.
2. **Quellklasse vor Suche:** je Punkt die autoritative Klasse benennen (EUR-Lex, Agentur wie
   EFSA/ECHA/EMA, Bundesgesetz, Normungsgremium). Offene Websuche liefert sonst Blogs.
3. **Rechtsakte finden:** `eurlex_search` mit Rechtsbegriffen, nicht mit Technikbegriffen
   (für Präzisionsfermentation: „novel food", „food enzymes", „genetically modified food").
4. **Artikelweise lesen:** `fetch_url` je Rechtsakt mit den Begriffen des Pflichtpunkts.
   Definitionen, Ausnahmen und Übergangsfristen stehen oft in Artikeln, die keine
   Zusammenfassung erwähnt — sie lesen, nicht raten.
5. **Zwei Seiten je Herstelleraussage:** eine Aussage nur von einer Produkt-/Preisseite gilt
   als Marketing, bis eine zweite Seite desselben Hauses (Doku, FAQ, Vertrag) sie trägt.
6. **Nicht erreichbare Primärquellen** (interaktive Portale, TDM-Vorbehalt) als solche nennen:
   „Primärquelle nicht abrufbar, übereinstimmend in n Sekundärquellen".
7. **Schreiben** im Format des Entwurfs (## Geltende Rechtsakte · ## Zulassung und Verfahren ·
   ## Kennzeichnung und Angaben · ## Laufende Vorhaben und Fristen · ## Offene Punkte für den
   Analysten), jede Aussage mit `[Kurzname](URL)`, Rechtsakte mit Nummer, Datum, Artikel.

## Einen maschinellen Entwurf prüfen

- Anhang B des Entwurfsblatts (`scripts/field_watch.py <kunde> --sheet <feld> --draft`) listet
  **Prüfhinweise**: Links ohne Quelle im Lauf, Rechtsakt-Nummern, die nicht zur verlinkten
  CELEX passen. Jeden Hinweis klären.
- Jede Aussage am Link nachlesen (`fetch_url` mit den Begriffen der Aussage). Was nicht dasteht, fliegt.
- Danach umschreiben (nicht nur korrigieren), im Kopf `status: rewritten` setzen. Ein fast
  unveränderter Text wird beim Bauen abgelehnt (Ähnlichkeit ≥ 85 %).

## Regeln

- Keine Rechtsberatung, keine Empfehlung, keine Prognose. Der Anhang beschreibt Rechtslage und Quellen.
- Volltexte fremder Quellen gehen nicht ins Blatt; Wortlaut nur als kurzes Zitat mit Artikelangabe.
