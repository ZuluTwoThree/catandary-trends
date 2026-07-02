# Catandary Trends — Backlog

> **⚠️ Umzug 2026-07-02:** Das Backlog lebt jetzt in den **[GitHub Issues](https://github.com/ZuluTwoThree/catandary-trends/issues)**.
> Alle offenen Items wurden in 15 konsolidierte Issues überführt; die vollständigen
> Detail-Texte der alten Backlog-Items stehen in der Git-Historie dieser Datei
> (letzter Vollstand: Commit `1fd18e5`). Neue Ideen → als Issue anlegen (Labels:
> `foresight`, `acquisition`, `pipeline`, `frontend`, `content-quality`, `ops`,
> `prio-high`), nicht mehr hier.

## Issue-Übersicht (Stand 2026-07-02)

| Issue | Thema | Labels |
|---|---|---|
| [#2](https://github.com/ZuluTwoThree/catandary-trends/issues/2) | ⭐ Foresight-Engine v1: Cluster-/Trajektorien-Analyse produktisieren (inkl. gescopte Discoverer, lebende Taxonomie, Mega-Trend-Full-Review) | foresight, prio-high |
| [#3](https://github.com/ZuluTwoThree/catandary-trends/issues/3) | ⭐ Frontend: Foresight-Visualisierungen auf den 455k-Signal-Space heben (Plan: `docs/frontend_foresight_visualization_plan.md`) | frontend, foresight, prio-high |
| [#4](https://github.com/ZuluTwoThree/catandary-trends/issues/4) | ⭐ Quellen-Acquisition nach Lead-Time-Tier (arXiv/bioRxiv/RePORTER/CORDIS, CMS-Probe, OpenAlex-Expansion, Sitemap, Router-Cleanup) | acquisition, prio-high |
| [#5](https://github.com/ZuluTwoThree/catandary-trends/issues/5) | Regulatory Disclosures Multi-Jurisdiktion (EDGAR/DART/EDINET/RNS, ESAP-ready) | acquisition |
| [#6](https://github.com/ZuluTwoThree/catandary-trends/issues/6) | Brand-Newsrooms als market-Tier-Quellen | acquisition |
| [#7](https://github.com/ZuluTwoThree/catandary-trends/issues/7) | Patent-Layer ausbauen (OPS-Credentials, INPADOC Legal Events, Family-Dedup, Full-Text, CPC-Backfill) | acquisition, foresight |
| [#8](https://github.com/ZuluTwoThree/catandary-trends/issues/8) | ⭐ DOCDB-Back-File + Lazy-Embedding (`ensure_embeddings`) + Postgres/pgvector-Migration | pipeline, foresight, prio-high |
| [#9](https://github.com/ZuluTwoThree/catandary-trends/issues/9) | ⭐ OpenAlex Graph-Layer als Science-Signal | acquisition, foresight, prio-high |
| [#10](https://github.com/ZuluTwoThree/catandary-trends/issues/10) | ⭐⭐ Deep-Backfill: Embedding-Distillation-Klassifikation + Discovery-Loop | pipeline, foresight, prio-high |
| [#11](https://github.com/ZuluTwoThree/catandary-trends/issues/11) | Content-Qualität: Volltext, Prompt-Optimierung, Qualitäts-Gate, Eval-Harness | content-quality |
| [#12](https://github.com/ZuluTwoThree/catandary-trends/issues/12) | Content-Gen-Durchsatz (Stage 6) parallelisieren | pipeline |
| [#13](https://github.com/ZuluTwoThree/catandary-trends/issues/13) | Quellen-Qualität: Noisy-Feed-Watch + Vertical-Balance-Check | ops |
| [#14](https://github.com/ZuluTwoThree/catandary-trends/issues/14) | Structural-vs-Hype-Score (Wiedervorlage ~2026-12, lead_time_tier-gewichtet) | foresight |
| [#15](https://github.com/ZuluTwoThree/catandary-trends/issues/15) | Google-Trends-Integration via pytrends (3 Ebenen) | acquisition |
| [#16](https://github.com/ZuluTwoThree/catandary-trends/issues/16) | Newsletter-Automatisierung (Cron + Versand) + `deploy/crontab.txt` aufräumen | ops |

**Beim Konsolidieren erledigt/obsolet markiert** (Details in der Git-Historie):
Stage-1-Dedup difflib→rapidfuzz (erledigt 2026-06-20, 167×), Funding-Tier-Ingester
(erledigt 2026-06-30, 35.227 Signale), Hybrid-Suche/Foresight-Cockpit (erledigt
2026-04-11), Auto-Publish-Integration (2026-04-12), `discover_mega_trends.py`-v1.1
(abgelöst durch `propose_mega_trends.py` → #2), vLLM-Klassifizierungs-Plan
(abgelöst durch produktiven llama.cpp-24-Slot-Pfad → Referenz in #12),
Firecrawl-/Brave-Backfill (obsolet durch WP-API/OpenAlex → Hinweis in #4),
kombinierter EN+DE-Call (getestet & verworfen 2026-04-09), Brave Search Radar
(entfernt 2026-04-12).

## Kurz-Historie (Meilensteine, Details in Git-Historie dieser Datei)

- **2026-05-25** Stage 6 (Content-Gen) produktiv auf llama.cpp 35B; ab 2026-06-26 30B (`be444d0`).
- **2026-06-12** Quellennetz vereinigt: 192 Feeds (189 aktiv) inkl. `product/trend-radar`-Port; Poller robuster (UA-Fallbacks, 5xx-Retry).
- **2026-06-20** FOOD-Backfill (Brave + Firecrawl-Deep, Datums-Recovery); WP-REST-Survey: 44 Quellen mit WP-API (~3 Mio. Posts) → Datenbeschaffung gelöst, Engpass = Selektivität + Durchsatz.
- **2026-06-22** Strategie-Entscheidung: **Cluster-/Trajektorien-Foresight auf den Signal-Embeddings ist das Verkaufsfeature**; Artikel sind der Free-Lead-Magnet.
- **2026-06-25** Patent-Graph-Layer (BDDS-DOCDB, `patent_links`, `tir_graph.py`) — GPU-freie TIR-Metriken belegt; Back-File-Entscheidung offen (→ #8).
- **2026-06-28** Deep-Backfill-Architektur (Embedding-Distillation + Lazy-Content) dokumentiert (`docs/deep_backfill_architecture.md`, → #10).
- **2026-06-30** Funding-Tier live (NSF/NIH/OpenAIRE/UKRI, 35.227 Signale); Regulatory-Disclosure-Landschaft geprobt (→ #5).
- **2026-07-02** Mega-Trend-Proposer (`propose_mega_trends.py`) gebaut; Backlog → GitHub Issues migriert; DB-Stand: 768k raw_entries, 455.600 embedded Trends (404.567 Signale, 47.030 published).

## Betriebs-Referenz

- **Pipeline-Lauf:** `scripts/scheduled_cycle.sh` (transienter systemd-Timer, Watermark-Scoping, llama.cpp-Backends mit Ollama-Fallback, Symlink-Reset auf den 208K-Classifier am Ende).
- **DB-Backup:** täglich 00:05 via `scripts/backup_db.py`.
- **Newsletter:** Editions in `newsletter_editions`, Frontend liest live; Automatisierung offen (→ #16).
- **Hardware:** RTX 3090 24 GB; llama-server hält ~22 GB im Ruhezustand — vor lokalen LLM-Läufen `nvidia-smi` prüfen (siehe CLAUDE.md).
