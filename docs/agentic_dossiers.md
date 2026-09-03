# Agentic Scouting-Dossiers (Owner-only) — Branch `Agentic-Dossiers`

Stand 2026-09-01. Baut den agentischen Rechercheur (`scripts/corpus_research.py`,
Skizze in `docs/corpus_research_sketch.md`) zum Owner-Werkzeug aus: Der Owner
bestellt Scouting-Dossiers zu Technologiefeldern, der Agent analysiert die
gesamte Innovationskette (Text **und** Messung) und liefert einen zitierten
Bericht samt eigener Endkontrolle — die finale Durchsicht bleibt beim Owner.

## Owner-Festlegungen (2026-09-01, Konstruktionsprinzip)

1. **Nur der Owner erteilt Aufträge.** Dossiers sind kein Kundenfeature; die
   Seite `/trends/dossiers` ist owner-only (s.u.), es gibt keinen Kundenpfad.
2. **Streng lokal.** Recherche, Bericht und Endkontrolle laufen vollständig
   auf dem lokalen Modell (Qwen3.8-27B via llama-server :8090). Kein
   Cloud-Hop — Dossiers sind proprietäre Dokumente mit vertraulichem Inhalt.
3. **Kein Automatikbetrieb.** Kein Cron. Aufträge werden nur abgearbeitet,
   wenn der Owner den Worker von Hand startet. (Deckt sich mit der älteren
   Radar-Regel in `save_dossier`: „a dossier is a dated document, never a
   cron job".)
4. **Endkontrolle: erst der Agent, dann der Owner.** Jeder Lauf endet im
   Status `review` mit dem maschinellen Prüfbefund; `done` gibt es nur per
   Owner-Abnahme („Sign off").

## Ablauf

```
Owner: Auftragszettel                    Owner: Worker-Start (von Hand)
/trends/dossiers  ──▶  dossier_orders  ──▶  scripts/dossier_worker.py
                        (queued)              │
                                              ▼  Phase 1 (Embedding-Handover)
                                    pipeline/dossier_quant.py
                                    tech_analyze: CPC → TIR-Trajektorie →
                                    Lead-Time → Leitpatente  ➜  zitierbarer
                                    Messblock (Quelle "Q1" + Hub-Patente)
                                              │
                                              ▼  Phase 2 (27B-Handover, Guards)
                                    scripts/corpus_research.py run()
                                    Plan → Korpus (Artikel+Signale) → Audit →
                                    Paper/Patent-Sweep → Web → Bericht →
                                    Zitat-Kanonisierung → dossiers(slug, v+1)
                                              │
                                              ▼
                                    pipeline/dossier_check.py (deterministisch)
                                    Zahlen-Grounding · Zitat-Bilanz · offene
                                    Fragen  ➜  check_json, Status 'review'
                                              │
Owner: /trends/dossiers/[slug]  ◀─────────────┘
Bericht + Endkontrolle + Versionshistorie · „Sign off" → 'done'
```

## Bausteine

| Teil | Datei | Rolle |
|---|---|---|
| Auftragszettel | `pipeline/dossier_orders.py` | Tabelle `dossier_orders`, Statusfluss `queued→running→review→done` (nie automatisch über `review` hinaus), `cancelled`/`failed`/requeue |
| Quant-Vorstufe | `pipeline/dossier_quant.py` | ruft `scripts/tech_analyze.analyze_query` (deterministisch, vor dem ersten Modell-Hop) und formatiert Messblock + Katalogquellen; jede Zahl trägt ihre Ehrlichkeitsgrenze (TIR kalibriert bis ~2019, Patent ≠ Produkt, Datenfenster ab 1990). Degradiert ohne GPU/Postgres zum protokollierten Fehlgrund |
| Rechercheur | `scripts/corpus_research.py` | unverändert im Kern; neu: `run(..., quant=...)` injiziert Messquellen+Notiz, Result enthält `evidence` (für die Endkontrolle) und `quant`; CLI-Flag `--quant`; `--slug` ohne `--out` crasht nicht mehr |
| Endkontrolle | `pipeline/dossier_check.py` | deterministisch: `ungrounded_specifics` (pipeline/grounding.py) über den modellgeschriebenen Berichtsteil (Coverage-Anhang abgetrennt) gegen das gesamte gesammelte Material; plus gestrichene Zitate, Zitatquote, offene Fragen |
| Worker | `scripts/dossier_worker.py` | Owner-getriggert, zweiphasig (ein Embedding- + ein 27B-Handover für alle Aufträge); `--list`, `--order N`, `--order-new "topic" [--run]`, `--assume-model-up`, `--skip-quant` |
| GPU-Guards | `pipeline/gpu_handover.py` `model_on_llamacpp` | generischer Handover mit striktem VRAM-Vorab-Check (27B braucht <1100 MiB Fremdbelegung — 2026-08-26-Vorfall) + Identitäts-Check via `/v1/models`; 27B-Startskript in `MODEL_START_SCRIPTS` registriert |
| Frontend | `frontend/src/app/trends/dossiers/*`, `lib/dossiers.ts`, `lib/dossier-access.ts` | Owner-Desk (Formular, Auftragsliste, Serienliste) + Leseansicht mit Versionswechsler, Endkontroll-Panel und Sign-off |

## Zugriff & Deployment

- **Flag:** `DOSSIERS_ENABLED=1` (`.env` des Frontends). Default aus → 404,
  gleiche Mechanik wie `REVIEW_ENABLED` (lib/dossier-access.ts); mit
  `AUTH_ENABLED=1` zusätzlich Session-Pflicht.
- **PUBLIC_MODE:** `/trends/dossiers` steht in der Blockliste
  (`lib/publicMode.ts`) — die öffentliche Instanz kennt die Route nie.
- **Migration (einmalig, von Hand, auf dem Host mit DATABASE_URL):**

  ```bash
  .venv/bin/python scripts/migrate_dossier_orders.py
  ```

  Bekannte Repo-Falle (siehe `migrate_dead_links.py`): additive Migrationen
  laufen nie automatisch. Bis zum Lauf zeigt die Seite einen Hinweis statt zu
  crashen (to_regclass-Guard), und der Worker legt sich sein Schema selbst an.

## Bedienung (Owner-Runbook)

```bash
# Auftrag über die Seite ODER per CLI:
.venv/bin/python -m scripts.dossier_worker --order-new "solid-state batteries" --run

# Alle offenen Aufträge abarbeiten (nicht parallel zum 04:00-Full-Cycle!):
.venv/bin/python -m scripts.dossier_worker

# Auftragslage:
.venv/bin/python -m scripts.dossier_worker --list

# 27B läuft schon (z. B. nach Draft-Richter-Session):
.venv/bin/python -m scripts.dossier_worker --assume-model-up
```

Gleiches Thema erneut bestellen ⇒ nächste Version derselben Serie
(`dossiers(slug, version)`); die Leseansicht verlinkt alle Versionen —
„was hat sich seit dem letzten Lauf verschoben" ist selbst das Signal.

## Tests

- `tests/test_dossier_orders.py` — Statusfluss-Invarianten (nie automatisch
  `done`, mark_running gewinnt genau einmal, requeue).
- `tests/test_dossier_check.py` — Grounding inkl. Coverage-Anhang-Abtrennung,
  Zitat-Bilanz.
- `tests/test_dossier_quant.py` — Messblock-Formatierung (Ehrlichkeitsgrenzen,
  Established-Fall, off-topic), Degradierungspfade.
- `tests/test_dossier_worker.py` — Worker-Kontrakt ohne GPU (review+Version,
  failed, Identitäts-Guard, Quant-Durchreichung).
- Frontend: `dossier-access.test.ts` (Guard + Slug-Parität zu Python),
  `publicMode.test.ts` erweitert.

## Bewusste Grenzen / offene Punkte

- Kein Versions-**Diff** in der Ansicht (nur Versionswechsler) — Kandidat für
  den nächsten Schritt, die Versionierung existiert genau dafür.
- Die Quant-Vorstufe misst das **Thema** (Freitextphrase). Eine eigene Frage
  (`question`) ändert die Recherche, nicht die Messung.
- `--retrieval vector` bleibt wie in der Skizze ungetestet; Worker-Default
  ist FTS.
- Die offenen Kanten der Skizze gelten weiter (Web-Treffer ungeranked,
  Patent-Sweep titelbasiert).
