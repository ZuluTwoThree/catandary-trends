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

## Zwei Belegarten: Artikel und Signale

Der publizierte Bestand ist nur die Spitze. `trends` enthält (Stand 2026-08-26):

| status | Zeilen | body_en | title_en | embedding_1024 |
|---|---|---|---|---|
| `signal` | 1.498.066 | 0 | alle | alle |
| `published` | 81.397 | alle | alle | alle |
| `draft` | 4.358 | alle | alle | alle |

Die 1,5 Mio. Signale sind klassifiziert und eingebettet, aber nie durch die
Content-Generierung gelaufen. Sie haben Titel, Quelle, Datum, Vertikale,
Mega-Trend und Tags — kein `summary_en`. Öffnen lässt sich ein Signal über
`raw_entries.excerpt` (rund 60 % haben einen brauchbaren), `raw_content` ist bei
ihnen leer.

Warum das zählt, am Beispiel „solid-state battery":

```
publizierte Artikel:   45   2026-03 … 2026-08   22 Quellen
Signale:              320   2011    … 2026      34 Quellen
                            2026:111 2025:47 2024:44 2023:26 2022:22 2021:31 2020:19
```

Die Historie fehlt dem Korpus also nicht — sie liegt nur nicht in den Artikeln.
In den Signalen stecken zusätzlich OpenAlex-Paper und EPO-Patentsätze.

`--scope both` (Default) teilt das Katalogbudget und verschränkt beide Pools;
sonst begraben 18-mal so viele Signale die eigene Analyse. Jeder Katalogeintrag
ist als `[article]` oder `[signal]` markiert, die Prompts erklären den
Unterschied, und ein Signal wird an seiner **Ursprungs-URL** zitiert — es hat
keine Artikelseite, ein `catandary.de`-Link liefe ins Leere. In der Quellenliste
steht bei ihnen `*(signal — not written up)*`.

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

## Vergleichslauf mit Signalen (gleiche Frage, `--scope both`)

```
                   nur Artikel   Artikel+Signale
Sekunden                 168,9             187,8
Katalog                     11    15 (6 Art./9 Sig.)
zitiert                     11                11
gestrichene Zitate           0                 0
Belegzeitraum      2024-05 … 2026-08   2020-04 … 2026-08
```

Inhaltlich ist der Unterschied größer als die Zahlen andeuten:

* **QuantumScape** war im Artikel-Lauf eine ausdrückliche Lücke („cannot be
  established from this evidence"). Mit Signalen entsteht eine Bahn: B-Samples
  für OEM-Tests (10/2024) → Corning-Partnerschaft (09/2025) → Eagle-Line-Pilot
  (02/2026).
* **Eine gemessene Prognose-Korrektur:** Solid Power stellte 2022 Feststoff-EVs
  „ab 2028" in Aussicht, CATL verschob 2026 auf „nicht vor 2030". Vier Jahre
  Differenz zwischen zwei Akteuren, im Bericht ausdrücklich als Widerspruch
  benannt. Im Artikel-Lauf war das strukturell unmöglich — 2022 liegt außerhalb
  des publizierten Bestands.
* Die Audit-Lücken wurden **schärfer** statt weniger: aus „wir wissen nichts über
  QuantumScapes Pilotlinien" wurde „uns fehlt die Kapazitätsangabe der
  Eagle Line".

Nebenbeobachtung: der Audit-Hop lief einmal in `finish_reason=length` bei
`max_tokens=1024` und wurde von `llamacpp_client` automatisch mit 2048
wiederholt — die vorhandene Retry-Logik trägt.

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
