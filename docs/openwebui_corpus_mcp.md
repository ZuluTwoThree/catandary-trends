# Catandary-Korpus-MCP in Open WebUI einrichten

Stand 06.10.2026 · Open WebUI 0.11.4 auf der Workstation · Dienst `catandary-corpus-mcp` aus `main` (`4b7efa5`)

## Wie es zusammenhängt

| Teil | Wo | Rolle |
|---|---|---|
| Open WebUI | Workstation, `:8080` (Tailnet: `https://kiworkstation.tail678c6e.ts.net:8443`) | Oberfläche, führt die Werkzeugaufrufe aus |
| Korpus-MCP | Workstation, `http://127.0.0.1:8096/mcp` (nur lokal) | 16 lesende Werkzeuge auf die Catandary-Datenbank + konforme Websuche + Belegprüfung |
| Modell (z. B. Nemotron) | bequietUbuntu, `:8090` | entscheidet, welche Werkzeuge es aufruft, und schreibt die Antwort |

Das Modell sieht die Datenbank nie direkt, nur die Werkzeugergebnisse im Gespräch.

## Voraussetzungen

- Dienst läuft: `systemctl --user status catandary-corpus-mcp` → `active (running)`
- Token: Datei `catandary-corpus-mcp-token.txt` (per Taildrop gekommen) bzw. auf der Workstation
  `~/.config/catandary/corpus_mcp.token`. **Nicht in Chats, Tickets oder das Repo kopieren.**

## 1 · Werkzeugserver eintragen

1. Open WebUI öffnen und als Admin anmelden.
2. Unten links auf den Namen → **Admin Panel** (*Admin-Bereich*) → **Settings** (*Einstellungen*)
   → Reiter **External Tools** (*Externe Werkzeuge*, je nach Sprache auch *Tool-Server*).
3. **+** bzw. **Add Connection** (*Verbindung hinzufügen*).
4. Ausfüllen:

   | Feld | Wert |
   |---|---|
   | Type | **MCP** · **Streamable HTTP** (*Streambares HTTP*) — nicht „OpenAPI" |
   | URL | `http://127.0.0.1:8096/mcp` |
   | Auth | **Bearer** |
   | Key | Inhalt der Token-Datei (eine Zeile, ohne Leerzeichen/Zeilenumbruch) |
   | ID / Name | `catandary-corpus` / `Catandary Korpus` |
   | Description | Catandary-Trendkorpus: Signale, Forschung, Patente, Field-Watch-Messungen, konforme Websuche |
   | Visibility / Access | **Private** bzw. nur Admin — `fetch_url` und `web_search` holen Seiten aus dem Netz |

5. **Verify Connection** (*Verbindung prüfen*) → „Connection successful" → **Save**.

`127.0.0.1` ist richtig: Open WebUI läuft auf derselben Maschine und ruft den Server serverseitig auf.

## 2 · Modell einstellen

1. **Workspace** → **Models** → das Modell (z. B. Nemotron von bequietUbuntu) → bearbeiten.
2. Unter **Tools**: `Catandary Korpus` anhaken (dann ist es in jedem Chat mit diesem Modell an).
3. **Advanced Params** (*Erweiterte Parameter*) → **Function Calling** → **Native**.
4. Optional: Systemanweisung eintragen (z. B. „Technology Trend & Intelligence Expert", siehe unten).
5. Speichern.

Ohne Schritt 2 lässt sich das Werkzeug je Chat zuschalten: im Eingabefeld **+** bzw. das
Werkzeug-Symbol → `Catandary Korpus` aktivieren.

## 3 · Probe

Neuer Chat mit dem Modell, Frage:

> Wie viele Treffer hat der Catandary-Korpus zu „precision fermentation" je Ebene? Nutze term_counts.

Erwartet: ein Werkzeugaufruf `term_counts` wird angezeigt, danach Zahlen je Ebene
(science, patent, funding, market). Danach z. B.:

> Zeig mir die drei neuesten Marktsignale zu solid-state batteries mit Quelle.

## Werkzeuge

`research_facets` · `term_counts` · `search_research` · `search_patents` · `search_signals` ·
`get_signal` · `field_list` · `field_week` · `field_sheet` · `field_probe` · `tir_block` ·
`emerging_nests` · `web_search` · `fetch_url` · `eurlex_search` · `verify_report` — alles lesend.
`field_sheet` und `field_week` brauchen Minuten; solange ist der Dienst belegt.

**Seit 08.10.:**
- **Eingrenzen:** `research_facets` zeigt, in welchen Fachgebieten die Treffer einer Phrase
  liegen („electrolyzed water": Biotechnologie 242, Pflanzen 86, Energie 79 … Food Science 55).
  `term_counts` und `search_research` nehmen `subfields`/`fields` (OpenAlex), `term_counts`
  und `search_patents` CPC-Präfixe (`cpc`, z. B. `A23`), `term_counts` eine `vertical` für
  Markt/Förderung. Beispiel: „electrolyzed water" ungefiltert 953 Arbeiten / 3.429 Patente,
  eingegrenzt (Food Science, A23) 55 / 284.
- **Belegprüfung:** `verify_report` prüft einen Berichtsentwurf deterministisch gegen die
  Werkzeugergebnisse der letzten 4 h, den Korpus, Crossref und EUR-Lex: erfundene oder
  falsch zugeordnete DOIs, nicht existierende CELEX-/Patentnummern, genannte aber nie
  aufgerufene Werkzeuge, Zahlen ohne Werkzeugbeleg. Am Nemotron-Bericht vom 07.10. hätte
  sie alle neun DOIs und die drei nie aufgerufenen Werkzeuge gemeldet.
- Die Werkzeugbeschreibungen sagen jetzt je Werkzeug, wofür es gedacht ist, wofür nicht und
  welche Fallen es gibt; die Server-Anweisung schreibt den Ablauf vor (eingrenzen → messen →
  Quellen lesen → `verify_report`). Nach einem Update in Open WebUI unter *External Tools*
  einmal **Verify Connection**, damit die neue Werkzeugliste geladen wird.

## Systemanweisung (Vorschlag, kurz)

```
Du bist Technology Trend & Intelligence Expert bei Catandary. Recherchiere zuerst im
Catandary-Korpus (Werkzeuge catandary-corpus), das Web nur ergänzend. Lies die vier Ebenen
science, patent, funding, market getrennt. Jede Zahl stammt aus einem Werkzeugergebnis
und steht mit Ebene und Zeitraum da; nichts selbst schätzen. Korpuszahlen sind keine
Marktstatistik. Die Verbesserungsrate K ist relative Entwicklung, keine Vorhersage.
Jede Tatsache mit Link; Catandary-Artikel sind maschinengeschrieben — zitiere die Quelle
dahinter. Trenne: Gemessen · Belegt · Einschätzung · Lücken · Quellen. Dünne Evidenz
offen benennen. Fachbegriffe vor dem Zählen mit research_facets eingrenzen. Vor der
Antwort den vollständigen Text mit verify_report prüfen und alles Gemeldete korrigieren
oder streichen. Höchstens etwa 15 Werkzeugaufrufe je Frage.
```

## Fehlerbilder

| Symptom | Ursache / Abhilfe |
|---|---|
| Verify → 401 / unauthorized | Token falsch kopiert (Leerzeichen, Zeilenumbruch) oder Auth nicht „Bearer" |
| Verify → connection refused | Dienst aus: `systemctl --user restart catandary-corpus-mcp`, Log `~/logs/catandary-corpus-mcp.log` und `journalctl --user -u catandary-corpus-mcp` |
| Werkzeug erscheint nicht im Chat | im Modell oder im Chat nicht aktiviert; Type versehentlich „OpenAPI" |
| Modell ruft keine Werkzeuge auf | Function Calling nicht „Native"; Modell auf bequietUbuntu nicht erreichbar (Windows gebootet, Nemotron angehalten) |
| Aufruf hängt mehrere Minuten | `field_sheet`/`field_week` laufen; oder Zeitlimit von Open WebUI erreicht |

## Token erneuern

Auf der Workstation: `rm ~/.config/catandary/corpus_mcp.token && systemctl --user restart catandary-corpus-mcp`
— erzeugt ein neues Token; den neuen Inhalt in Open WebUI unter *External Tools* nachtragen.

Ausführlich: `docs/owner_manual.md` §5.11a. Diese Datei: `docs/openwebui_corpus_mcp.md`.
