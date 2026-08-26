# Deep Research über den eigenen Korpus (Skizze, 2026-08-26)

`scripts/corpus_research.py` — ein agentischer Rechercheur, der über die
publizierten Trends läuft statt über das Web: Plan → Schleife → Audit → zitierter
Bericht. Gedacht als Vorstufe für das Foresight-Dossier, das heute ein einziger
Retrieval-Durchgang in einen einzigen Prompt ist.

## Ablauf

| Phase | Modell-Hop | Rückgabe |
|---|---|---|
| `plan` | Planer | `{title, steps:[{title, query}]}` |
| Schleife | Agent, bis zu `--steps` mal | `search` \| `open` \| `finish` + `researchState` |
| `audit` | Beleg-zu-Behauptung | `supported[]` (jede mit Trend-ids), `inferences[]`, `contradictions[]`, `missing[]` |
| `report` | Bericht | Markdown mit `[Titel](URL)` |

Danach werden alle Zitate gegen den Katalog kanonisiert: was nicht auf einen
gesammelten Artikel zeigt, wird gestrichen, eine selbstgeschriebene Quellenliste
abgeschnitten, unsere generiert.

## Drei Entscheidungen

**Das Modell ruft kein Werkzeug auf.** Jeder Hop liefert striktes JSON mit der
nächsten Aktion, ausgeführt wird sie vom Runner. `chat_structured` erzwingt das
über `response_format: json_schema`, aus dem llama.cpp eine Grammatik baut —
`action` ist ein `Literal`, eine ungültige Aktion ist also nicht darstellbar.

**Der Zitat-Katalog ist geschlossen.** Anders als bei Web-Recherche ist eine
erfundene URL hier beweisbar falsch, nicht nur verdächtig.

**Retrieval per Volltext (`idx_trends_fts`), nicht per Vektor — als Default.**
Auf einer 24-GB-Karte passen das 27B und `qwen3-embedding` nicht gleichzeitig
hinein. `--retrieval vector` existiert für den Fall eines zweiten
Embedding-Endpunkts (oder Ollama auf CPU; ~10 Queries pro Lauf).

Dabei ein Fallstrick: `websearch_to_tsquery` UND-verknüpft alle Terme, eine
Agent-Query aus acht Wörtern traf damit 1 von 80.712 Artikeln. `search_fts()`
läuft deshalb zweistufig — strenge UND-Lesart, dann OR über die inhaltstragenden
Wörter, nach `ts_rank` sortiert.

## Erster Lauf (2026-08-26, Qwen3.8-27B auf `-c 65536`)

Frage: Stand der Solid-State-Kommerzialisierung — laufende Pilotlinien, belegte
Energiedichte-Angaben, Nähe zur Serienfertigung.

```
169 s gesamt | 3 Suchen, 2 Volltexte, dann finish (nicht ins Limit gelaufen)
11 Artikel im Katalog, 11 zitiert, 0 Zitate gestrichen
Audit: 7 belegte Behauptungen, 3 Inferenzen, 1 Widerspruch, 4 Lücken
Bericht: 16.383 Zeichen
```

Der Bericht benennt seine Lücken selbst („The provided corpus does not contain
specific details on the operational status of pilot lines for Toyota, Samsung,
QuantumScape"). Stichprobe: „84 % Kapazität nach 350 Zyklen" deckt sich wörtlich
mit dem zitierten Artikel.

## Offen

* Ranking: das OR-Retrieval holt breit; bei größeren Katalogen prüfen, ob
  Randtreffer die Belegdichte verwässern.
* `--retrieval vector` ist implementiert, aber ungetestet (Embedding-Endpunkt).
* Kein Streaming, keine Persistenz — ein Lauf, eine Datei. Für ein Produkt
  bräuchte es Lauf-Zustand in der DB.

## Herkunft

Die Ablaufform (planen, iterieren, vor dem Schreiben auditieren, Zitate
nachträglich kanonisieren) ist Unsloth Studios Web-Deep-Research abgeschaut.
**Kein Code und kein Prompt daraus übernommen** — jener Code ist AGPL-3.0-only
und würde diese Lizenz auf das Produkt ziehen. Prompts und Implementierung hier
sind eigenständig.
