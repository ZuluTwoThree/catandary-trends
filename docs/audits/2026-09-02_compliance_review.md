# Compliance-Review Catandary Trends (Datenbeschaffung · Urheberrecht · Datenschutz)

Stand: 2026-09-02 · Repo `/home/dirk/projects/ct-dev` (Branch `dev`) · Prüfung strikt read-only (Code, Konfiguration, billige DB-SELECTs auf `catandary`). Keine Netzrequests. Lizenz-/ToS-Aussagen sind, wo nicht im Repo belegt, als **„zu verifizieren"** markiert.

Kontext-Annahme laut Auftrag: ab 01.10.2026 **statischer Export** (30-Tage-Artikelfeed + eigene Analysen) auf Hetzner-Webhosting; Newsletter-DOI als PHP auf demselben Webspace, Versand über Resend; volle App bleibt lokal. Achtung: `docs/launch/HOSTING_PUBLIC_VPS.md:54-57` verwirft den statischen Export noch ausdrücklich („verliert … jede API-Route … Newsletter-Signup-API") — die Doku hinkt der Owner-Entscheidung vom 02.09. hinterher. Mehrere HOCH-Befunde unten folgen direkt aus dieser Lücke.

---

## 0. Zusammenfassung

| Risiko | Anzahl | Kern |
|---|---|---|
| HOCH | 4 | Abmeldelink läuft im statischen Export ins Leere; `noindex` auf der Live-Landing; Volltext-Speicherung ohne Löschkonzept/TDM-Vorbehaltsprüfung bei 160 Quellen; BDDS-DOCDB-Zugriff über undokumentierte Web-App-OAuth mit lizenzrestriktiven Daten |
| MITTEL | 11 | Browser-UA-Spoofing im Poller/Linkchecker/Sitemap-Ingester; kein Overlap-Gate für „substanziell anders"; kein Takedown-Prozess; Next-Datenschutzseite stale; DOI-Cron nicht aktiv; TIP/PATSTAT-Exporte; pytrends; Wikidata-Gründer; CORDIS-Lizenzhinweis; Feed-Etikette ohne Conditional GET; Fulltext-Docstring stale |
| NIEDRIG | 9 | Zitate, Schlagzeilen, Bilder, Attribution (alle sauber), Tracking, Impressum, dead_links, SEC-Personendaten (nicht geladen), HN/CT.gov/FDA |

---

## 1. RSS-Feeds (`sources.yaml`, `pipeline/feed_poller.py`, `pipeline/article_fetcher.py`)

### 1.1 Bestand
- `sources.yaml`: 238 `name:`-Einträge, 8 `active: false`; DB `sources`: 323 aktiv / 339 gesamt (SELECT count), 1 Quelle mit `llm_pipeline=false` (SEC Form D).
- **160 von 238 Quellen tragen `fulltext: true`** (grep-Zählung). Der Docstring in `pipeline/article_fetcher.py:10-12` („Start set: the press wires + The Conversation") ist **stale** — die Breitfreischaltung kam mit Commit `eb0931c` („enable full-text for 135 probe-qualified sources (owner-approved)").
- Auswahlkriterium laut Commit-Message: `scripts/probe_fulltext.py` testete **robots.txt + extrahierbarer Text**, Owner-Ausschlüsse: HBR, MIT Technology Review, Project Syndicate, Nature (+14 Sub-Journals). 10 weitere Quellen sind mit Kommentar „bewusst aus — Fetch geblockt/Paywall (Einzel-URL-Test 2026-08-25)" (z. B. `sources.yaml:237`) ausgenommen. → Kriterium war **technisch** (klappt der Fetch?), nicht eine ToS-Prüfung je Verlag.

### 1.2 Poller-Etikette
| Aspekt | Befund | Beleg |
|---|---|---|
| User-Agent | **Browser-Spoof** `Mozilla/5.0 (Macintosh…) Chrome/125 … CatandaryTrends/1.0 (RSS Feed Reader)` — Token vorhanden, **keine Kontakt-URL/-Mail**; Kommentar nennt als Zweck das Umgehen von 403 für Bot-UAs | `pipeline/feed_poller.py:29-40`, Fallback `:44` |
| Conditional GET | **kein** ETag / If-Modified-Since | `:71-78` |
| robots.txt | nicht geprüft (bei RSS üblich, aber der WP-REST-Pfad `/wp-json/wp/v2/posts` wird ohne robots-Check täglich abgefragt; `wp-json` ist bei manchen Sites per robots gesperrt) | `:165-176` |
| Frequenz | 1 Request/Feed/Tag (Mo–Fr 04:00 via `full_cycle_cron.sh`), 90-Tage-Fenster — höflich | `deploy/crontab.txt:11`, `feed_poller.py:87` |
| Gespeicherter Umfang (Poll) | `title`, `url`, `excerpt` ≤ 2000 Zeichen — aus `summary`, sonst **aus `content[0]` (Volltext-Feeds)**; WP-API: `content` wenn `excerpt` leer | `:59-66`, `:184-186` |

### 1.3 Volltext-Fetch (`article_fetcher.py`)
- Ehrlicher UA mit Kontakt (`:37`), robots.txt je Host (`:62-80`), 1 req/s/Host (`:40`, `:83-89`), trafilatura-Extraktion, **bis 12.000 Zeichen** je Artikel in `raw_entries.raw_content` (`:39`).
- Läuft im Nachtlauf (`pipeline/run_full_cycle.py:283-298`) und im Draft-Richter (`pipeline/draft_judge.py:175-198`), sowie on-demand in `scripts/corpus_research.py:569`.
- **DB-Stichprobe** (letzte 1.000 published): 392 Artikel entstanden aus gespeichertem Volltext, Ø 4.766 Zeichen.
- **Kein Löschkonzept**: `grep "DELETE FROM raw_entries"` → nichts; Volltexte bleiben unbefristet in der 21,6-Mio-Zeilen-Tabelle.
- **Kein TDM-Vorbehalts-Check**: weder `tdm-reservation`-Header/TDMRep noch `noai`-Meta werden ausgewertet (nur robots.txt).

**Bewertung:** Für die interne Verarbeitung ist §44b UrhG (Text und Data Mining, auch kommerziell) die tragfähige Grundlage — **aber** nur solange (a) kein maschinenlesbarer Nutzungsvorbehalt des Rechteinhabers besteht (§44b Abs. 3; robots.txt allein deckt das nicht ab) und (b) die Vervielfältigungen gelöscht werden, „wenn sie für das Text und Data Mining nicht mehr erforderlich sind" (§44b Abs. 2 S. 2). Beides fehlt. Zusätzlich: Verlags-ToS (William Reed/FoodNavigator, Industry-Dive-Marken, Frontiers, Fraunhofer, t3n …) können automatisierte Volltextabrufe vertraglich untersagen — **zu verifizieren** (Nutzungsbedingungen der Top-20-Volltextquellen nach Artikelvolumen).

**Risiko: HOCH** (Umfang × Dauer × fehlender Vorbehalts-Check). **Fix:** (1) Retention: `raw_content` nach Abschluss von Content-Gen + Richterfenster (z. B. 90 Tage) auf NULL setzen, Embeddings bleiben; (2) TDM-Vorbehalt prüfen (HTTP-Header `tdm-reservation: 1`, `<meta name="tdm-reservation">`, `robots.txt`-Einträge für `*`, sowie `X-Robots-Tag: noai`) → Quelle automatisch `fulltext: false`; (3) Docstring in `article_fetcher.py` und CLAUDE.md auf den realen Umfang bringen; (4) ToS-Review der Top-Volltextquellen dokumentieren (`docs/sources_tos_review.md`).

### 1.4 Paywall-Inhalte
Kein Login-Bypass im Code; geblockte/Paywall-Quellen werden ausgenommen (Kommentare in `sources.yaml`). Owner-Ausschlussliste vorhanden. **NIEDRIG**.

### 1.5 Historische Archiv-Ingester (nicht im Cron, aber Teil des Korpus)
| Skript | UA | robots | Takt | Speicher | Risiko |
|---|---|---|---|---|---|
| `scripts/ingest_sitemap.py:29-31` | **reiner Chrome-Spoof, keine Kennung** | nein | 0,8 s (`:138`) | og:title/description | MITTEL |
| `scripts/ingest_wordpress.py:29` | `CatandaryBot/1.0; +https://catandary.de` | nein | 0,3 s (`:98`) | `content` ≤ 2000 Zeichen (`:200`) | MITTEL |
| `scripts/ingest_cms.py:41` | Hybrid-UA mit URL | Docstring behauptet „robots-konform" (`:6`), **kein Check im Code** | 0,5–1 s | og/JSON | MITTEL |
| `scripts/check_source_links.py:33-34` | **Chrome-Spoof ohne Kennung** (monatlich, ≤12 URLs/Quelle) | nein | 1 Worker/Host | nur Statuscode | NIEDRIG-MITTEL |

**Fix:** Einheitlicher UA `CatandaryTrends/1.0 (+https://catandary.de; trends@catandary.de)` in allen Fetchern; Browser-UA nur als dokumentierter Fallback nach 403 und niemals ohne Kennung; robots-Check aus `article_fetcher._robots_ok` in Sitemap/WP/CMS-Ingester wiederverwenden.

---

## 2. Nicht-RSS-Ingester

| Quelle | Skript | Lizenz/Basis | Attribution | Rate/Etikette | Personendaten | Status | Lücke |
|---|---|---|---|---|---|---|---|
| OpenAlex API | `scripts/ingest_openalex.py:37-51` | CC0 (Repo + Frontend `research/paper/[id]/page.tsx:286`) | „OpenAlex (CC0)" auf Paper-Seite + Export-Header | `mailto` im UA **und** als Param (Polite Pool), Backoff auf 429, `OPENALEX_API_KEY` optional | Autorennamen (öffentl. wissenschaftl. Daten) | OK | Frontend-Nennung nur im (nicht-öffentlichen) Foresight-Bereich |
| OpenAlex Snapshot (S3) | `scripts/ingest_openalex_snapshot.py:3-4, :49` | CC0, anonymer S3-Download | s. o. | Bulk, kein API-Limit | `authorships` im Parquet-Archiv (Autoren) | OK | Archiv enthält Personennamen — lokal, kein Zugriff Dritter |
| arXiv | `scripts/ingest_preprints.py:45, :158` | Metadaten (inkl. Abstracts) laut arXiv-API-ToU frei nutzbar — **zu verifizieren: arXiv „Terms of Use for arXiv APIs" (CC0-Metadaten, Attribution)** | Quellenlink je Eintrag | **3,1 s Sleep = 1 req/3 s eingehalten**, UA mit mailto | Autoren | OK | — |
| bioRxiv/medRxiv | `:166-214` | API frei; Preprint-Lizenzen variieren (CC-BY/ND/NC) — **zu verifizieren: bioRxiv API-Bedingungen für Abstract-Weiterverwendung** | Quellenlink | 1,0 s | Autoren | OK | — |
| NSF / NIH RePORTER | `scripts/ingest_funding.py:145-257` | US-Gov Public Domain | Funder-Präfix im Excerpt | Backoff, UA mit mailto | PI-Namen ggf. im Abstract | OK | — |
| OpenAIRE | `:259-336` | OpenAIRE Graph = **CC BY 4.0 — zu verifizieren** | Funder-Nennung, kein Lizenzhinweis | Paginierung ≤10k | — | Lücke | Attribution „OpenAIRE" + CC BY auf Methodik-Seite |
| UKRI GtR | `:338-` | **OGL v3 — zu verifizieren** („Contains public sector information licensed under OGL v3") | keine | Client-Filter | PI-Namen | Lücke | OGL-Hinweis auf Methodik-Seite |
| SEC EDGAR Form D | `scripts/ingest_secform_d.py:39-40, :243` | Public Domain; Fair-Access-Regel: **UA mit Name+Mail vorhanden**, 0,5 s Sleep (weit unter 10 req/s) | Quellenlink zur Filing-Seite | OK | **RELATEDPERSONS.TSV wird NICHT gelesen** (grep leer) — nur Issuer/Offering | OK | Bei künftiger Nutzung der Related-Persons: Art. 14 DSGVO-Info + Löschkonzept |
| Hacker News (Algolia) | `scripts/ingest_hn_launches.py:3-4, :37, :76` | HN-API MIT; Algolia-HN-Search **zu verifizieren (ToS, ~10k req/h)** | „Hacker News" in `VentureAttribution.tsx:19` | 0,4 s Sleep, UA mit Kontakt | **kein Autor/Username gespeichert** | OK | — |
| ClinicalTrials.gov v2 | `scripts/ingest_clinical_trials.py:33, :95` | US-Gov Open Data | Nennung in `VentureAttribution` | 1,3 s (~50 req/min) | Sponsor = Firma | OK | — |
| openFDA 510(k) | `scripts/ingest_fda_510k.py:3-5, :35` | Public Domain; openFDA-Disclaimer laut Docstring „gehört auf die Methodik-Seite" | Nennung in `VentureAttribution` | Bulk, 1 s | Applicant = Firma | Lücke (klein) | Disclaimer fehlt auf `/trends/methodology` (grep leer) |
| CORDIS | `scripts/ingest_cordis.py:4-5, :39` | **CC BY 4.0** (EU) | `VentureAttribution.tsx:12-15` (nur Ventures-Seite, PUBLIC_MODE-geblockt) | Bulk, UA mit Kontakt | Koordinator-Namen möglich | Lücke | Werden CORDIS-`raw_entries` zu **published Artikeln**, zeigt der Artikel nur `source_name`+Link, **keinen CC-BY-Hinweis** → Lizenzhinweis in Artikel-Footer wenn `source_name` ∈ {CORDIS, OpenAIRE, UKRI} |
| SBIR/STTR | `scripts/ingest_sbir.py:9-10` | Public Domain (US) | — | Bulk-CSV | Firmen | OK | — |
| GLEIF | `scripts/ingest_gleif.py:4` | CC0 | `VentureAttribution` | Bulk | — | OK | — |
| Companies House | `scripts/ingest_ch.py:3-4` | OGL v3, Attribution „Contains Companies House data © Crown copyright" | `VentureAttribution.tsx:18` ✔ | Bulk | **keine Officers** geladen (Free Company Data Product enthält keine) | OK | — |
| Wikidata | `scripts/enrich_wikidata.py:4-6, :45-47, :244-252` | CC0; WDQS-Etikette: UA mit Kontakt, 1,5 s Sleep | `VentureAttribution` | OK | **Gründernamen (P112) in `startup_companies.founders`** (577 Firmen), angezeigt auf `/trends/foresight/ventures/company/[id]` (`page.tsx:103-105`) — nur lokal (PUBLIC_MODE blockt `/trends/foresight`) | MITTEL (falls je öffentlich) | Art. 14 DSGVO-Info + Erwähnung in Datenschutzerklärung, bevor Ventures öffentlich wird |
| EPO OPS | `scripts/ingest_patents.py:11-16, :163-190` | Registrierter Free-Tier; `X-Throttling-Control` wird ausgewertet ✔ | „EPO, DOCDB" auf Methodik-Seite | OK | Anmelder; **keine Erfinder** gespeichert (grep leer) | OK | **zu verifizieren: OPS Terms & Conditions/Fair Use Charter (kommerzielle Nutzung, 4 GB/Woche)** |
| EPO BDDS DOCDB (Back-File + Weekly) | `scripts/ingest_patents.py:521-531` | DOCDB = **lizenzrestriktives Produkt**, Repo selbst: „proprietary, license-restricted; the underlying raw data cannot be redistributed" (`docs/tir_paper_draft.md:353`) | Methodik-Seite | **Zugriff über OAuth-Password-Grant der BDDS-Web-App mit hart kodierter Client-ID (`:529`) gegen `bdds-bff-service` (Backend-for-Frontend, undokumentiert)** | Anmelder | **HOCH (zu verifizieren)** | (1) **BDDS-Lizenz/Subscription-Bedingungen** prüfen: automatisierter Download, Anzeige von Titel/Abstract gegenüber Dritten, Weitergabe; (2) Patents-Explorer (Titel/Abstract-Volltext) ist unter `/trends/foresight` → PUBLIC_MODE-geblockt ✔ — muss so bleiben; (3) nur **abgeleitete Aggregate** (TIR, CPC-Serien) in „eigene Analysen" — Rohdatensätze nie exportieren |
| PATSTAT via TIP | `scripts/ingest_tip_csv.py:2-13`, Frontend `patents/page.tsx:521` („Source: PATSTAT Global (EPO)") | TIP-Exporte des Owners (SQL-Queries), lokal geladen | Quellenangabe vorhanden | — | PSN-Anmeldernamen | MITTEL (zu verifizieren) | **TIP Terms of Use: Export/Weiterverwendung aggregierter PATSTAT-Ergebnisse außerhalb der Plattform, Veröffentlichung** |
| Google Trends (pytrends) | `scripts/validate_demand.py:3-15` | inoffizielle API, Google-ToS-Grauzone | — | 10 s Sleep, nicht im Cron, nur Batch-Kreuzvalidierung | — | MITTEL | Nicht in den Produktpfad nehmen; ggf. offizielle Google-Trends-API (Alpha) anfragen |
| Reddit | — | nur in Doku/CLAUDE.md-Tabelle | — | — | — | nicht implementiert | CLAUDE.md-Tabelle „Ergänzende Datenquellen" bereinigen (Exploding Topics/Reddit/Google Trends sind nicht produktiv) |
| Brave/Firecrawl | `pipeline/config.py:129-133`, `pipeline/radar_discovery.py`, `sources.yaml:1255` (`radar:`-Suchbegriffe) | entfernt 2026-04-12 | — | — | — | Altlast | Tote Konfiguration/Keys entfernen |

---

## 3. Generierte Artikel (Urheberrecht)

### 3.1 Prompt & Gates
- Prompt verlangt „Substantially reworded from the source; never copy its phrasing" (`pipeline/llm_processor.py:268`) und Grounding (`:289-291`).
- Guards: Wortzahl/Cliché/Abbruch (`content_is_clean`, `:348-375`), Fabrikations-Gate (`pipeline/grounding.py`), Truncation + Grounding + pgvector-Dedup im Auto-Publish (`pipeline/auto_publisher.py:106-118`). **Kein Overlap-/Plagiats-Gate gegen den Quelltext.**
- Zitate: Extraktion liefert bis 5 `quotes` **ohne Längenlimit** (`pipeline/models.py:78-79`), davon 3 in den Prompt (`llm_processor.py:579`); `verbatim_only` filtert nur auf Wörtlichkeit (`:729`).

### 3.2 Messung (read-only, letzte 200 published, Body vs. Quelltitel+Volltext/Excerpt)
```
n=200, Median Body 111 Wörter
5-Gramm-Anteil: Median 0.000 · p90 0.091 · max 0.392
8-Gramm-Anteil: Median 0.000 · p90 0.024 · max 0.284
längster wörtlicher Wortlauf: Median 4 · p90 9 · max 22 Wörter
Bodies mit Lauf ≥12 Wörter: 10 (5 %) · ≥20: 1 (id 1678403: 28 % 8-Gramm-Überlappung)
```
Zusätzlich (letzte 1.000 published): Zitate ≥60 Zeichen in Anführungszeichen: **3**; ≥120: 1; **Titel identisch mit Quelltitel: 0**.

**Bewertung:** Im Median klar eigenständig; Ausreißer (≈5 %) mit 12–22 Wörtern wörtlicher Übernahme sind einzeln vertretbar (§51 UrhG Zitat/ freie Benutzung), aber ungesteuert. **MITTEL.** **Fix:** Overlap-Gate in `content_is_clean`/`auto_publish`: Re-Roll bzw. Halten bei 8-Gramm-Anteil > 0,15 oder längstem Lauf ≥ 15 Wörter; `quotes` auf ≤ 25 Wörter/Zitat und ≤ 2 Zitate im Prompt deckeln.

### 3.3 Attribution
- `trends` published: **84.563 Zeilen, 0 mit leerer `source_url`, 0 ohne `source_name`**, 13 mit host-only-URL (Regex `^https?://[^/]+/.+` verletzt) → NIEDRIG, per `normalize_entry_url` künftig verhindert (`feed_poller.py:118-150`).
- Rendering: Quellname + Link (`rel="noopener noreferrer"`) + Wayback-Fallback bei toten Links (`frontend/src/components/TrendArticle.tsx:221-240`, `lib/deadLinks.ts:14`). Impressum enthält Passus „Content and sources … linked publishers hold the rights" (`frontend/src/app/imprint/page.tsx`).
- Newsletter-Edition nutzt `summary_en` + `source_name` (`pipeline/newsletter_generator.py:216-242, :336-337`).

### 3.4 Bilder
Keine Übernahme: grep nach `og:image|enclosure|media_content|image_url` in Pipeline leer; Frontend nur eigene Analyse-Bilder (`analysis/[slug]/page.tsx:42`). **NIEDRIG/OK.**

### 3.5 Löschverlangen / Takedown
- **Kein dokumentiertes Verfahren** (grep `takedown|Löschverlangen|removal|opt-out` in docs/frontend/README leer). Vorhanden: `status='rejected'` via `scripts/review_cli.py:136,179`, Quellen-Deaktivierung in `sources.yaml` (stoppt Polling, syncht aber nicht `sources.active` in die DB — CLAUDE.md-Nebenfund), `sources.llm_pipeline=false`.
- Im statischen Export müsste ein Takedown zusätzlich einen **Re-Export** auslösen — nirgends beschrieben.
- **MITTEL.** **Fix:** `docs/takedown_runbook.md` + Absatz im Impressum („Rechteinhaber: trends@catandary.de, Bearbeitung binnen 2 Werktagen"): Trend → `rejected` + `reviewed_at`, Quelle ggf. `fulltext:false`/`llm_pipeline=false`, `raw_content` der Quelle nullen, Static-Export neu erzeugen, Wayback-Link nicht anbieten für zurückgezogene Inhalte.

### 3.6 dead_links
Tabelle existiert (124 Zeilen, 12 bestätigt), Frontend zeigt Badge + Archivlink. Der monatliche Check steht in `deploy/crontab.txt:30`, laut CLAUDE.md **noch nicht in der echten crontab** installiert. **NIEDRIG.**

---

## 4. Datenschutz (DSGVO)

### 4.1 Newsletter-DOI (`docs/launch/newsletter-doi-php/`)
| Anforderung | Befund | Beleg |
|---|---|---|
| Einwilligungstext | wortgleich in Formular (`preview.html:721-725`) und `nl_config.php` (`consent_text`), versioniert + archiviert (`nl_consent_text`, `_lib.php:nl_register_consent_text`) | ✔ |
| Serverseitige Consent-Pflicht | `subscribe.php:39-47` | ✔ |
| Protokoll Zeitpunkt/IP/UA | `signup_ip/ua`, `confirm_ip/ua`, `nl_consent_log` | ✔ |
| Echte Bestätigung (kein Prefetch) | GET zeigt Button, POST bestätigt (`confirm.php:6-17`) | ✔ |
| Keine Werbung in DOI-Mail | `_lib.php:nl_send_confirm_mail` | ✔ |
| Löschung unbestätigter Anmeldungen | `cron.php:44-46` (Ablauf 48 h + 7 Tage) — **aber `cron.php` laut `EINBAU.md` „Später (nicht dringend)" noch nicht in konsoleH eingetragen** → ohne Cron werden Pending-Datensätze **nie** gelöscht, obwohl Landing/Mail „spätestens nach 30 Tagen" versprechen | **MITTEL** |
| Aufbewahrung Nachweis | 1.095 Tage (`nl_config.php: retention_days`), im Modal erklärt | ✔ |
| Rate-Limits / Enumeration | HMAC-Buckets, neutrale Antworten | ✔ |
| Config-Schutz | `.htaccess.example` + PHP-Return | ✔ (Owner muss 403 prüfen) |
| **Abmeldelink** | Bestätigungsseite verspricht „unsubscribe via the link at the end of every email". Der Link zeigt auf **`{PUBLIC_BASE_URL}/trends/newsletter/unsubscribe?…`** (`pipeline/newsletter_sender.py:63-65`, auch `List-Unsubscribe`-Header `:142-143`). Diese Route ist eine **Next.js-Server-Seite mit DB-Write** (`frontend/src/app/trends/newsletter/unsubscribe/page.tsx:2,25,30`). Im **statischen Export existiert sie nicht**; das PHP-Paket enthält **kein `unsubscribe.php`**, obwohl `nl_config.php` Block 5 („Unsubscribe-Geheimnis") es antizipiert. Zusätzlich: `PUBLIC_BASE_URL=http://localhost:3004` und `AUTH_SECRET`-Mismatch (`NEWSLETTER_GOLIVE.md` Schritt 2/3). | **HOCH** |
| Resend-DPA | `NEWSLETTER_GOLIVE.md` Schritt 8 listet „Resend-DPA abschließen" als offen; `docs/legal/newsletter-doi-texte.draft.md` dokumentiert das DPA als mit ToS-Annahme wirksam und am 2026-07-26 geprüft → Widerspruch in der Doku, **zu klären**, kein technischer Blocker | NIEDRIG |

**Fix (Pflicht vor 01.10.):** `unsubscribe.php` auf dem Webspace (GET zeigt Bestätigungsbutton, POST setzt `status='unsubscribed'`, `unsubscribed_at`, `unsubscribe_ip`, Log-Event `unsubscribe`; Token = HMAC-SHA256(`unsub_secret`, email), identisch zu `newsletter_sender.unsubscribe_token`); `List-Unsubscribe-Post: One-Click` muss den POST **ohne** Button akzeptieren (RFC 8058); Sender-URL auf `https://catandary.de/newsletter/unsubscribe.php` umstellen; `export.php` liefert `unsubscribed` bereits zurück → `sync_subscribers.py` übernimmt es.

### 4.2 Datenschutzerklärung vs. Realität
- **Landing-Modal** (`docs/launch/preview.html:786 ff.`): vollständiger Newsletter-Abschnitt (Daten, DOI, Zweck, Rechtsgrundlagen inkl. §7 UWG, Resend/Plus Five Five, US-Transfer DPF+SCC, kein Tracking, Speicherdauer, Widerruf, Aufsichtsbehörde LfDI BW). **Gut.** Kontakt dort `contact@catandary.de`.
- **Next-App `/privacy`** (`frontend/src/app/privacy/page.tsx`): beschreibt Accounts/Stripe (öffentlich per `PUBLIC_MODE` abgeschaltet), Newsletter nur als Einzeiler **ohne** DOI/IP-Protokoll/US-Transfer/Speicherdauer/Resend-Firmierung; Kontakt `trends@catandary.de`. Wenn der statische Export die `/privacy`-Seite mitliefert, ist sie **unvollständig (Art. 13 DSGVO)** und widerspricht dem Modal. **MITTEL.** **Fix:** `/privacy` aus einer gemeinsamen Quelle mit dem Modal speisen (Newsletter-Abschnitt aus `docs/legal/newsletter-doi-texte.draft.md`), Accounts/Stripe-Abschnitte nur bei `AUTH_ENABLED`/`PAYWALL_ENABLED` rendern, eine Kontaktadresse.
- `docs/legal/README.md`: alle Rechtstexte sind **Entwürfe ohne Anwaltsprüfung** (Owner-Gate).

### 4.3 Engagement-Tracking
`POST /api/track` zählt `page_views`/`shares` je Trend, **keine IP, kein Cookie, keine ID** (`frontend/src/app/api/track/route.ts`); `unique_visitors`/`avg_time_on_page` ungenutzt. Rate-Limit-`clientIp` nur für Auth/Search (nicht persistiert). Session-Cookie nur bei `AUTH_ENABLED`. Im statischen Export fällt `/api/track` weg (Fetch in `TrendArticle.tsx:42` läuft harmlos ins 404). **NIEDRIG/OK.** Aussage „no third-party analytics" trifft zu.

### 4.4 Personenbezogene Daten in Inhalten
- `trends` hat **keine `people`-Spalte** (Schema-Query; CLAUDE.md-Datenmodell ist hier stale); `brands`/`companies` = Organisationen (Stichprobe).
- Personen tauchen in Quelltexten/Abstracts (Autoren, PIs, Gründer) und in `startup_companies.founders` auf — alles öffentliche berufliche Daten, lokal; Rechtsgrundlage Art. 6(1)(f). Sobald Ventures/Research öffentlich würden: Art. 14-Hinweis in der Datenschutzerklärung. **NIEDRIG (lokal).**

### 4.5 Impressum
Name/Anschrift/E-Mail in Next (`imprint/page.tsx`) und Landing-Modal ✔ (Owner-Gate am 2026-08-28 geschlossen). Fehlend/optional: USt-IdNr (nur falls vorhanden), „Verantwortlich i.S.d. §18 Abs. 2 MStV" steht in der Next-Version („Responsible for content") — im Landing-Modal nicht, was für die Landing ausreichend ist. **NIEDRIG.**

### 4.6 Drittlandtransfers im Backend
Optionale Anthropic-Nutzung (`CLASSIFY_BACKEND=anthropic`, Discovery-Labels `scripts/discover_trends.py:84-85`, Haiku-Review) überträgt **Quelltexte**, keine Nutzerdaten — DSGVO-neutral, urheberrechtlich als TDM-Vervielfältigung mitzudenken. **NIEDRIG.**

---

## 5. Robots / Indexierung

| Befund | Beleg | Risiko |
|---|---|---|
| **Live-Landing trägt `<meta name="robots" content="noindex">`** (seit Deploy 01.09. live) | `docs/launch/preview.html:7` | **HOCH** (für Lead-Gen: Seite ist für Google unsichtbar; jede Woche bis 01.10. kostet Index-Vorlauf) |
| `docs/launch/robots.txt` erlaubt alles — widerspricht dem `noindex` | `docs/launch/robots.txt` | s. o. |
| Next `robots.ts`: allow `/trends/`, disallow `/api/`, `/_next/`; Sitemap-Verweis auf `/sitemap.xml` | `frontend/src/app/robots.ts` | OK |
| `sitemap.ts` ist `force-dynamic` (DB-Query, 5.000 Trends, Foresight-URLs) — im **statischen Export nicht ausführbar** bzw. listet PUBLIC_MODE-geblockte Foresight-Routen | `frontend/src/app/sitemap.ts:5, :38-49` | MITTEL |
| `export.php` setzt `X-Robots-Tag: noindex` | `export.php:9` | OK |

**Fix vor 01.10.:** `noindex` entfernen (bewusst, mit Datum), `robots.txt` beibehalten; Sitemap zur Build-Zeit statisch erzeugen (nur `/`, `/trends`, 30-Tage-Artikel, `/analysis/*`, Rechtsseiten; Foresight-Einträge raus); `canonical` auf `https://catandary.de/…`.

---

## 6. Compliance-Matrix (Kurzform)

| Quelle | Lizenz/Basis | Attribution | Rate/Etikette | Personendaten | Status | Lücke |
|---|---|---|---|---|---|---|
| RSS-Feeds (323 aktiv) | Feed-Nutzung wie vorgesehen; Teaser ≤2000 Z. | Name+Backlink 100 % | 1×/Tag; **Browser-UA ohne Kontakt**, kein Conditional GET | Autorennamen in Teasern | MITTEL | UA ehrlich+Kontakt, ETag |
| Volltext-Fetch (160 Quellen) | §44b UrhG TDM | — | robots ✔, 1 req/s ✔, UA ✔ | — | **HOCH** | TDM-Vorbehalt, Retention, ToS-Review, stale Doku |
| Archiv-Ingester (WP/Sitemap/CMS) | WP-REST/Sitemaps öffentlich; ToS **zu verifizieren** | Backlink | **Chrome-Spoof (Sitemap)**, kein robots | — | MITTEL | robots + UA |
| OpenAlex (API+Snapshot) | CC0 | ✔ (lokal) | Polite Pool ✔ | Autoren | OK | — |
| arXiv / bioRxiv / medRxiv | API-ToU (zu verifizieren) | Backlink | 3 s ✔ / 1 s | Autoren | OK | — |
| NSF / NIH | Public Domain | Präfix | ✔ | PIs | OK | — |
| OpenAIRE / UKRI | CC BY 4.0 / OGL v3 (zu verifizieren) | fehlt | ✔ | PIs | Lücke | Lizenzhinweis |
| SEC Form D | Public Domain, Fair Access ✔ | Backlink | 0,5 s ✔ | **Related Persons nicht geladen** | OK | — |
| Hacker News | MIT / Algolia-ToS (zu verifizieren) | ✔ | 0,4 s | kein Autor | OK | — |
| ClinicalTrials.gov / openFDA | Public Domain | ✔ | ✔ | — | OK | FDA-Disclaimer auf Methodik |
| CORDIS / SBIR | CC BY 4.0 / PD | ✔ Ventures; **fehlt in Artikeln** | ✔ | — | Lücke | CC-BY-Zeile im Artikel |
| GLEIF / Companies House | CC0 / OGL v3 | ✔ | ✔ | keine Officers | OK | — |
| Wikidata | CC0 | ✔ | 1,5 s ✔ | **Gründer** | MITTEL (falls öffentlich) | Art. 14-Info |
| EPO OPS | Free Tier, Throttle ✔ | ✔ | ✔ | Anmelder | OK | ToU zu verifizieren |
| **EPO BDDS DOCDB** | lizenzrestriktiv (Repo-Eigenaussage) | ✔ | undokumentierte BFF-API, Web-OAuth | Anmelder | **HOCH (zu verifizieren)** | Lizenz, Anzeige, Zugriffsweg |
| PATSTAT/TIP | TIP-ToU (zu verifizieren) | ✔ | — | Anmelder | MITTEL | Export-Erlaubnis |
| Google Trends (pytrends) | inoffiziell | — | 10 s, nicht im Cron | — | MITTEL | aus Produktpfad halten |
| Reddit / Exploding Topics | nicht implementiert | — | — | — | — | CLAUDE.md-Tabelle bereinigen |
| Generierte Artikel | eigene Werke; Overlap p90 9 % | 0 NULL / 84.563 | — | — | MITTEL | Overlap-Gate, Zitatdeckel, Takedown-Prozess |
| Newsletter-DOI | Art. 6(1)(a), §7 UWG | — | Rate-Limits ✔ | E-Mail, IP, UA, 3 J. | **HOCH** | **unsubscribe.php fehlt**, cron.php inaktiv |
| Website-Tracking | aggregiert, cookielos | — | — | keine | OK | — |
| Rechtstexte | Entwürfe | — | — | — | MITTEL | `/privacy` angleichen, Anwaltsprüfung |
| Indexierung | — | — | — | — | **HOCH** | `noindex` entfernen, statische Sitemap |

---

## 7. Priorisierte Fixes

**Zwingend vor 01.10.2026**
1. **Abmeldung im statischen Setup funktionsfähig machen**: `unsubscribe.php` (HMAC mit `unsub_secret`, RFC-8058-One-Click-POST), Sender-URL + `List-Unsubscribe` umstellen, `PUBLIC_BASE_URL`/Secrets angleichen, E2E-Test nach `NEWSLETTER_GOLIVE.md` Schritt 6; `cron.php` in konsoleH aktivieren (sonst keine Löschung Unbestätigter).
2. **`noindex` von der Live-Landing entfernen** und eine statische Sitemap/Canonicals für den Export erzeugen (Foresight-Routen raus).
3. **Volltext-Speicherung absichern**: TDM-Vorbehalts-Check (TDMRep/`noai`) im `article_fetcher`, Retention für `raw_content` (z. B. 90 Tage nach Verarbeitung), Doku (`article_fetcher.py`-Docstring, CLAUDE.md) auf 160 Quellen korrigieren, ToS-Review der Top-Volltextquellen protokollieren.

**Zeitnah danach**
4. BDDS/DOCDB- und TIP-Lizenzbedingungen schriftlich verifizieren; Patents-/Research-Explorer weiterhin nur lokal; Rohdaten nie exportieren.
5. Einheitlicher, ehrlicher User-Agent mit Kontakt in Poller, Sitemap-/WP-/CMS-Ingestern und Linkchecker; robots-Check in die Archiv-Ingester.
6. Overlap-Gate + Zitatdeckel in Content-Gen/Auto-Publish; Takedown-Runbook + Impressums-Absatz; CC-BY-Hinweis für CORDIS/OpenAIRE/UKRI-basierte Artikel.
7. `/privacy` (Next) mit dem Landing-Modal zusammenführen, eine Kontaktadresse; Anwaltsprüfung der Entwürfe (`docs/legal/README.md`).
8. Aufräumen: Brave/Firecrawl-Konfig, `radar:`-Block in `sources.yaml`, CLAUDE.md-Tabelle „Ergänzende Datenquellen", Datenmodell (`people`-Spalte existiert nicht).
