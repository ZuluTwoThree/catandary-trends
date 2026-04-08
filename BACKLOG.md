# Catandary Trends — Backlog

## Pipeline-Optimierung

- [ ] **Kombinierter EN+DE-Call testen.** Aktuell laufen Stage 6 (Content EN, Qwen3 14B) und Stage 7 (Translate DE, Qwen3 14B) als zwei separate strukturierte Calls pro Entry — zusammen ~38 s/entry und damit 90% der Gesamt-Pipeline-Laufzeit. Hypothese: Ein einziger Call mit Schema `{title_en, summary_en, body_en, title_de, summary_de, body_de}` könnte Overhead (Prompt-Reprocessing, JSON-Parsing, Retry-Loop) halbieren. Risiko: 14B könnte bei doppeltem Output-Volumen Schema-Validierung häufiger reißen oder DE-Qualität durch Aufmerksamkeitsverteilung leiden. Test: 50-Entry-Vergleichslauf, Wall-Clock + manueller Quality-Check (5 Stichproben pro Vertical) gegen aktuelle 2-Call-Variante.
