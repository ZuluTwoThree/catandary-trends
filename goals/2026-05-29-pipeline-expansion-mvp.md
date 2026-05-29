# Goal: Pipeline Expansion MVP — drei nicht-trade_media-Quellentypen produktiv

```yaml
goal: |
  Bis 2026-06-26 produziert die Catandary-Pipeline ≥30 published Trends mit
  confidence ≥0.85 aus drei neu eingeführten source_type-Werten
  (sozial/community, brand_newsroom, non_english_trade) — gemessen im
  14-Tage-Fenster 2026-06-12 bis 2026-06-26.
slug: pipeline-expansion-mvp
opened_at: 2026-05-29
deadline: 2026-06-26

north_star:
  metric: published trends from new source_types, 14d window
  baseline: |
    0 — am 2026-05-29 stammen alle 26.374 published trends aus den
    bestehenden 3 source_types {trade_media: 87 active sources, research: 48,
    press_wire: 2}. Verifiziert per
    `SELECT s.source_type, COUNT(*) FROM trends t JOIN raw_entries re ON
    re.id=t.raw_entry_id JOIN sources s ON s.id=re.source_id WHERE
    t.status='published' GROUP BY s.source_type`.
  target: ≥30 in 14d window (2026-06-12 → 2026-06-26)
  measurement: |
    sqlite3 data/catandary.db "SELECT s.source_type, COUNT(*) AS n
      FROM trends t
      JOIN raw_entries re ON re.id = t.raw_entry_id
      JOIN sources s ON s.id = re.source_id
      WHERE t.status = 'published'
        AND t.confidence >= 0.85
        AND t.created_at BETWEEN '2026-06-12' AND '2026-06-26 23:59:59'
        AND s.source_type IN ('social','brand_newsroom','non_english_trade')
      GROUP BY s.source_type;"

done_when:
  - sources.source_type enthält die drei Werte 'social', 'brand_newsroom',
    'non_english_trade' mit mindestens je einer aktiven Quelle.
  - Jede neue Quelle hat `lead_time_tier` ∈ {future, market, now} korrekt
    gesetzt und passiert `feed_poller.validate_lead_time_tier`.
  - Im 14d-Fenster: SUM aller drei source_types ≥30 published trends mit
    confidence ≥0.85.
  - Stage-2-Relevance-Filter hat für mindestens einen der drei neuen Typen
    ein source_type-spezifisches Verhalten (Prompt-Patch oder
    Threshold-Override), und das Verhalten ist via Env-Flag deaktivierbar.
  - 0 ToS-Verletzungen, 0 Login-Umgehungen, 0 Paywall-Bypässe — verifizierbar
    aus den hinzugefügten sources.yaml-Einträgen.

thresholds:
  good:    ≥30 published trends total, alle 3 source_types aktiv
  great:   ≥60 published trends, jeder source_type liefert ≥10
  stretch: ≥100 published trends + nachweisbar niedriger Lead-Time-Median für
           mindestens einen neuen Typ verglichen mit trade_media-Median
           desselben Vertikals

out_of_scope:
  - Reddit, X/Twitter, Crunchbase (alle paid >100 €/Monat, separater /goal
    falls überhaupt)
  - Patent- und Regulierungs-Pipelines (EPO/EUR-Lex/FDA — eigener /goal,
    größerer Scope)
  - DE-Übersetzung der neuen Quellen
  - Newsletter-Integration der neuen Source-Types (folgt automatisch sobald
    Trends published sind)
  - LinkedIn Jobs (rechtlich unklar ohne explizite Prüfung)

architecture_implications:
  - touches: data/catandary.db (sources.source_type)
    nature: Schema-Erweiterung (keine CHECK constraint vorhanden, nur neue
      Werte in der Domäne — keine Migration nötig, aber Werte sollten in
      pipeline/config.py oder feed_poller.py whitelisted werden)
    reversible_via: SQL-UPDATE auf alte Werte, Quellen-Deaktivierung in
      sources.yaml
  - touches: pipeline/feed_poller.py
    nature: neuer Code — Dispatch nach source_type für nicht-RSS-Quellen
      (z.B. Hacker News Algolia API)
    reversible_via: git revert <sha>, Quellen aktiv=false setzen
  - touches: pipeline/llm_processor.py (Stage 2)
    nature: source_type-aware Prompt-Patch
    reversible_via: Env-Flag STAGE2_SOURCE_TYPE_AWARE=0 (Default-on nach
      Validierung); git revert als Fallback
  - touches: sources.yaml
    nature: Konfig — neue Einträge mit source_type außerhalb der drei
      bisherigen Werte
    reversible_via: active: false oder Eintrag entfernen

first_action: |
  Run des Briefings in pipeline_expansion_prompt.md gegen Claude/Sparring,
  Ergebnis = priorisierte Quellen-Roadmap. Daraus exakt drei Starter-Quellen
  auswählen (eine pro neuem source_type). Resultat in
  goals/2026-05-29-pipeline-expansion-mvp.roadmap.md ablegen,
  diesen Goal Contract aktualisieren mit den gewählten Namen.

checkpoints:
  - 2026-06-05: Roadmap fertig, 1. Quelle (RSS-basierter brand_newsroom)
    integriert und liefert ≥1 raw_entry/Tag.
  - 2026-06-12: Alle 3 source_types aktiv und produzieren Einträge;
    Messfenster startet.
  - 2026-06-19: Mid-Window-Check — Hochrechnung auf 30-Trend-Schwelle.
  - 2026-06-26: Endabrechnung gegen Schwellen good/great/stretch.

abandon_if:
  - Bei Mid-Window-Check (2026-06-19) zeigt die Hochrechnung <15 Trends bis
    Deadline → das Ziel ist mit gewählten Quellen unerreichbar, neuer
    Quellen-Mix wäre nötig (= neuer /goal, dieser hier abgebrochen).
  - Eine der drei gewählten Quellen erweist sich als ToS/Legal-problematisch
    und keine Ersatzquelle desselben source_type ist in ≤3 Tagen aktivierbar
    → der ganze /goal wird abgebrochen, nicht nur der Typ gestrichen.
  - Stage-2-Filter-Anpassung führt zu Regression bei den bestehenden 137
    Quellen (Filter-Pass-Rate fällt um mehr als 5 Prozentpunkte) und ein
    Env-Flag-Rollback wäre nötig länger als 24 h → der Architektur-Eingriff
    ist nicht reversibel genug, /goal abbrechen.

dependencies: []

risk_log:
  - 2026-05-29: HN Algolia API hat keinen offiziellen SLA — Ausfälle möglich.
    Mitigation: Graceful Degradation in feed_poller, kein Pipeline-Crash bei
    Quelle-down.
  - 2026-05-29: Brand-Newsroom-RSS-Feeds sind oft marketing-lastig — Filter-
    Pass-Rate könnte niedrig ausfallen. Mitigation: Stage-2-Prompt-Patch für
    brand_newsroom mit erhöhter Skeptizismus-Schwelle.
  - 2026-05-29: Non-English-Quelle (z.B. Nikkei Asia EN-Edition) ist
    englischsprachig genug, dass Pipeline-Sprache nicht angefasst werden
    muss — aber Selektion kommt aus asiatischem Markt-Fokus. Risiko:
    Vertikale-Verteilung schief.
```

## Begründung

**Warum jetzt:** Die Stage-6-Migration auf llama.cpp ist stabil (vier Produktivläufe in Folge, ratio "guard exhausted" < 0,25 %), die Quellen-Verifikations-Pipeline funktioniert (zuletzt 8/8 neue FOOD-Feeds in 2026-05-24 sauber integriert), und die DB-Größe (26k Trends, 137 Quellen, 21 Mega-Trends) ist groß genug, dass eine neue Quellen-Klasse einen klar messbaren Signal-Anteil ausmachen kann. Architektur-Risiken aus der Stage-6-Arbeit sind eingeholt — der nächste sinnvolle Hebel ist nicht mehr Modellqualität, sondern Quellen-Diversität. `pipeline_expansion_prompt.md` ist als Brief schon geschrieben (Commit `2f9db07`), die Roadmap ist das logische Folge-Artefakt.

**Warum dieses Ziel statt eines naheliegenden anderen:** Nicht „komplette Multi-Source-Pipeline" (zu breit für 4 Wochen, würde Patent/Regulierung/Funding gleich mit-skalieren wollen), nicht „eine konkrete Quelle integrieren" (zu schmal — würde die Architektur-Frage `source_type`-Dispatch nicht zwingen), sondern genau **drei neue source_types** als kleinstmöglicher MVP, der die Architektur ein Stück erweitert und die Lead-Time-Hypothese (Communities/Brand-Newsrooms/Non-English sind früher) gegen reale Trends testet. Ein Typ allein würde nicht zeigen, dass der Dispatch-Mechanismus generalisiert.

**Was hätte ich fast geschrieben, das ich verworfen habe:** Erste Version war „Reddit + HN + Brand-Newsroom" — verworfen, weil Reddit seit 2023 paid ist und das Ziel verwässert hätte. Zweite Version war „nur 1 Source, dafür gründlich" — verworfen, weil dann der `source_type`-Dispatch nicht erzwungen würde und der Architektur-Lerneffekt fehlt. Dritte Version hätte „Patent-Daten via EPO Open Patent Services" enthalten — verworfen, weil legal/format-komplex und für 4 Wochen MVP zu schwer; gehört in einen späteren `/goal`. Die `done_when`-Schwelle 30 ist nicht beliebig: bei drei Quellen und 14 Tagen Messfenster sind das ~0,7 Trends/Quelle/Tag — realistisch für aktive Feeds, eng genug um zu fordern.
