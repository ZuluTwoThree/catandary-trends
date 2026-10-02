# 10 — Landing-Copy für den Launch 01.10.2026 (ohne SaaS, #93)

> **Überholt in Abschnitt „For clients" seit 2026-09-20:** die Dossier-/Super-Pro+-Karten
> sind in `preview.html` durch die drei Produkte des Pivots ersetzt (Trajectory Sheet 1.490 €,
> Field Watch 390 €/Monat, Analyst Day 1.200 €, Feldprobe frei) — Owner-Freigabe 20.09.,
> Belege `docs/commercialization_plan_2026-09-20.md` §1 und §6. Der Rest dieses Blatts gilt weiter.

**Status:** Entwurf für den Owner, 2026-09-03. Die Copy ist in `preview.html` bereits
eingebaut; dieses Blatt ist die Vorlage mit Belegen, damit der Owner jede Zeile in seiner
Stimme umschreiben oder streichen kann. **Seine Stimme entscheidet.**

**Rahmen (Owner-Entscheidungen):** kein SaaS — keine Tarife, keine Selbstbedienung, keine
Zahlungen (#93, 26.08.). Die Website ist ein Lead-Gen-Schaufenster; verkauft werden sales-led
**Super Pro+** (betreuter Zugang zur vollen Foresight-Engine) und **Individualanalysen**.
Öffentlich ab 01.10.: der 30-Tage-Feed unter `/trends` als statischer Export
(`HOSTING_HETZNER.md`). Sprache der Seite: Englisch, Ton „Editorial Intelligence".

**Ehrlichkeitsregeln (bindend, `02_product_truth_matrix.md` §C + Owner):** kein Methoden-USP
(H3), keine Kunden/Referenzen/Zertifikate (H1, H4), keine „erkennt Trends früh"-Claims
(Positionierung: relative Entwicklung, nicht Früherkennung — Owner 25.07.), keine
Radar-Versprechen (Radar 25.08. aus dem Produkt genommen), keine Prognose-Versprechen (H7),
Zahlen nur belegt und mit Stand, keine Gegenwarts-TIR (H6).

**Belegkonvention:** jede Aussage trägt eine Fußnote `[Vn]` (Truth-Matrix-Zeile), `[C:…]`
(CLAUDE.md-Stelle), `[D:…]` (andere Repo-Datei) oder **[OWNER]** = Owner-Entscheid nötig.
Fußnoten aufgelöst in Abschnitt 12.

---

## 1. Statusleiste + Countdown

| Element | Copy | Beleg |
|---|---|---|
| Brand | `CATANDARY // Trend & Foresight Intelligence` | unverändert |
| Nav | `Free` (#free) · `Analyses` (#services) · `Method` (#how) · `Feed` (→ `/trends`, **erst ab Launch sichtbar**) · `Briefing →` (#subscribe) | Abschnitt 9 |
| Countdown | `Public launch · 01 Oct 2026 · 09:00 CEST` — unverändert; das Datum steht weiterhin genau **zweimal** in der Datei (`.cd-date`-Text, `new Date(...)`) | `preview.html` |

## 2. Hero

- **Eyebrow:** `Read from primary sources · built on local models` [V2][V4]
- **Headline:** **Trend intelligence, *traced* to its sources.** [V5]
  - Alternativen (gleich belegbar): *„Foresight you can cite."* (`03_positioning_brief.md` §4) ·
    *„Evidence, read closely."* (bereits auf `/analysis`) · *„Every trend, traced to its
    source."* — **[OWNER]** wählen.
  - Bewusst **nicht** mehr: *„See it in the research before you see it in the market."* —
    Früherkennungs-Claim (Owner-Regel 25.07.; Truth Matrix H6/H7).
- **Subline:** *Catandary reads science, patents, funding and market news on local models and
  publishes a free trend feed of the last 30 days. For clients we build individual analyses
  from the full corpus — by hand, dated, sourced and signed.* [V3][V4][D:#93][D:_template.md]
- **CTA 1 (primär):** vor Launch `Feed opens at launch · get notified` → `#subscribe`; ab
  Launch automatisch `Browse the trend feed` → `/trends` (Abschnitt 9).
- **CTA 2:** `Request an analysis →` → `mailto:trends@catandary.de?subject=Catandary — analysis
  request` [D:EnquiryContent.tsx `CONTACT_EMAIL`, ImprintContent.tsx] — **[OWNER]** siehe
  Adressfrage in Abschnitt 11.
- **Proof-Zeile (Zähler):** `21.6M Signals collected` [C:912] · `19.6M Patents` [C:516] ·
  `45M Scholarly works` [C:502] · `100% Local analysis` [V4]
  - Stand-Zeile darunter: *Corpus on our own hardware, as of August 2026 · the public feed
    shows the last 30 days* — Stand-Pflicht der Truth Matrix.
  - **[OWNER]** Patentzahl: CLAUDE.md nennt 19,6 M (BDDS-Backlog mit Abstract), Truth Matrix V16
    nennt ~42,6 M Patente (Live-DB-`reltuples` 21.07., andere Zählbasis). Eingebaut ist die
    konservative 19,6 M. **[OWNER]** „145k Firmen" ist nur in
    `docs/startup_explorer_plan.md:140` (145.038, 23.08.) und `docs/issue_status.md:33` belegt,
    nicht in Truth Matrix/CLAUDE.md → **weggelassen**; Empfehlung: V-Zeile in der Truth
    Matrix ergänzen, dann aufnehmen.
- **Instrument-Panel (Canvas):** bleibt als Design-Identität; Caption jetzt `Signal chain ·
  science → patents → funding → market` [V3] statt „Lead-time reader". Die Animation zeigt
  Signale, die in einen Cluster mit Momentum-Linie laufen [V9][V10] — Mechanik, kein Versprechen.

## 3. „What you get for free" (`#free`)

- **Eyebrow/H2:** `Free · from launch day` — **The last 30 days of signals, open to everyone.**
- **Lede:** *No account, no paywall, no tracking. The feed is the public face of the corpus we
  work from.* [D:#93][D:static_export_design — `/api/track` im Export entfernt]
- **01 · The feed — Every article, 30 days:** *Around 15,000 short trend articles, one per source
  signal, refreshed daily. Each links to the primary source it was written from and carries its
  vertical, PESTEL dimensions and theme.* Tag `8 verticals`. [D:HOSTING_HETZNER Messwerte
  14.846 Artikel 03.09.; #93: 15.081][V5][V7]
- **02 · Search & filters — Find it fast:** *Text search across the whole window, plus filters
  by vertical, PESTEL dimension and theme. It runs in your browser — what you type never leaves
  the page.* Tag `runs in the browser`. [D:StaticSearch.tsx (Chips Vertical/PESTEL/Theme,
  lazy `trends/index.json`)]
- **03 · Themes — 28 Mega Signal Themes:** *Signals grouped into 28 curated themes, from AI &
  automation to the orbital economy. A theme earns its "megatrend" badge from measured breadth
  and persistence, not from opinion.* Tag `measured, not asserted`. [C:„Mega Signal Themes"
  Routing-Block: 28 Themes, Megatrend = gemessenes Badge, `measure_mega_axes.py`]
- **04 · Briefing — One email a week:** *What moved across the eight verticals and which themes
  gained share, with an archive of past editions on the site. Double opt-in, no open or click
  tracking.* Tag `archive included`. [D6][D:HOSTING_HETZNER „Newsletter im Export" (letzte 12
  Editionen)][D:preview.html Datenschutz §7]
- **CTAs:** `Get the launch notice` (→ `#subscribe`; ab Launch `Open the feed` → `/trends`) ·
  `Mega Signal Themes →` (`/trends/mega`, erst ab Launch sichtbar) · `Newsletter archive →`
  (`/trends/newsletter`, erst ab Launch sichtbar).

## 4. „What we do for clients" (`#services`)

- **Eyebrow/H2:** `For clients · sales-led` — **Individual analyses, built from the full corpus.**
- **Lede:** *The feed shows 30 days. Behind it sits the whole corpus on our own hardware, and the
  tools to read it. Bring one question — we scope it, build the analysis by hand and sign it.*
  [D:#93 „Der Mensch im Pfad ist jetzt das Verkaufsargument"][D:_template.md]
- **Technology dossier:** *Where a technology stands across research, patents, funding and market
  signals, with an improvement-rate reading where the patent record supports one. Delivered as
  a dated, sourced write-up you can put in front of a board.* [D:corpus_research.py
  `--foresight`][V3][V11][V13 — „where the patent record supports one" = Honesty-Gate]
- **Company dossier:** *An established company or start-up read against the field it operates
  in: its own publications and filings, the technologies it depends on, and the signals moving
  around them. Built for SMEs facing a strategy, partner or investment decision — in German or
  English.* [D:corpus_research.py `--company` (web-first, Berichtssprache de/en), #95]
- **Trend assessment:** *One trend, placed: mega, macro or micro level, its momentum in the corpus
  measured as share of attention, and the primary sources behind it. Including what the
  evidence does not show.* [V7][V9][V10][V5]
- **Super Pro+ (Band):** `Super Pro+ · ongoing` — **Supervised access to the engine** — *Standing
  access to the full corpus and the tools behind it — clusters, technology trajectories, research
  and patent explorers — as a supported service: recurring analyses on your watch list and a
  direct line to the person who built them. Scoped and quoted per engagement. For hands-on
  analyst days in your team, ask about Hypercare, billed by the day.* [D:#93][D:EnquiryContent
  .tsx][V9][V12][V15][V19 Hypercare = Tagessatz, sales-led]
  - **[OWNER]** Hypercare-Betrag: V19/`07_launch_kit.md` belegen 1.499 €/Tag (ab 2. Auftrag
    999 €/Tag, Memory 19.07.). **Nicht** eingebaut — die Seite nennt keinen einzigen Betrag
    (sales-led, und der Betrag stammt aus der SaaS-Preisreihe). Bei Bedarf nachtragen.
- **Schlussnote:** *No tiers, no checkout, no self-service. Every engagement is scoped and quoted
  individually — write to trends@catandary.de with the question you need answered.* [D:#93]
- **[OWNER]** Eigene Analysen-Serie (`/analysis`): bewusst **nicht verlinkt/erwähnt** — es
  existiert noch keine Analyse (`content/analyses/_template.md` ist ein Draft) und die
  Root-Seite `/analysis` wird vom Publisher nicht hochgeladen (`HOSTING_HETZNER.md` „Offen").
  Sobald die erste Analyse steht und ihre Adresse feststeht, einen Satz + Link ergänzen.

## 5. „How it works" + Ehrlichkeit (`#how`)

- **H2:** **Four steps from a source to a sourced article.**
- **01 · Collect — Primary sources only:** *RSS feeds of trade media, newsrooms and press wires,
  plus open datasets for research, patents and public funding. Curated by hand; no aggregator
  scraping.* Tag `323 sources`. [C:912 „323 aktive Quellen (DB-Ist 2026-09-02)"][V2]
- **02 · Classify — On local models:** *Models on our own hardware tag each signal with 8
  industry verticals, 6 PESTEL dimensions and a mega/macro/micro horizon. No cloud API in the
  content pipeline.* Tag `8 × 6 × 3 taxonomy`. [V4][V7]
- **03 · Write & check — Short, and gated:** *A short article per signal, generated locally. A
  grounding gate holds back any piece that introduces a figure or date not present in its
  source; held pieces are reviewed, not published.* Tag `grounding gate`. [V6 — Formulierung
  „held", nicht „impossible"][C:Stage 5/10]
- **04 · Attribute — The source, always:** *Every article links to the primary source it was
  built from — a trend without a source cannot exist in our database. Links are re-checked
  monthly and marked when they die.* Tag `source enforced`. [V5 `source_url NOT NULL`][D:#48
  `check_source_links.py --mark`, Cron 2. des Monats, `dead_links`, `deadLinks.ts`]
- **What runs where:** *Filtering, classification, embeddings and article generation run on
  local models on our own hardware. Outside processors touch only what the site itself needs:
  the host that serves these pages and the email service that delivers the newsletter.*
  [V4 — Scope Content-Pipeline][D:preview.html Datenschutz §2 Hetzner, §7 Resend]
- **What we don't claim:** *The improvement-rate method we use is published research (SPNP;
  Singh, Triulzi & Magee, 2021) and others use it too. Absolute rates are reliable only to
  about 2019, and we say so. No forecasts, no customer logos, no certifications.*
  [V11][V13][H1][H3][H4][H7]
- **Where the limits are:** *Feed articles are model-written, about a hundred words, from one
  source each — gated by rules and a second model, not by an editor. The feed is a 30-day
  window. Analyses are the human part: built, checked and signed by a person.*
  [C:Stage 5 „~100 Wörter; Owner-Festlegung 2026-08-19"][C:Stage 9/10 Auto-Publish +
  Draft-Richter][D:#93][D:_template.md `author`]

## 6. FAQ

| Frage | Antwort (Kurzfassung — Volltext in `preview.html`) | Beleg |
|---|---|---|
| Where does the data come from? | 323 Primärquellen, RSS + offene Datensätze; kein Aggregator-Scraping; jeder Artikel behält den Link | [C:912][V2][V5] |
| Do you predict trends? | Nein — Richtung, Breite, Momentum als Share of Attention, TIR-Lesung bis zum belastbaren Jahr; keine Vorhersage | [V10][V12][V13][H7] |
| Is the method proprietary? | Nein — peer-reviewte MIT-Forschung, andere nutzen sie auch; unser Beitrag: Korpus, Kalibrierung, Transparenz, ein Mensch, der mitliest | [V11][H3][`07_launch_kit.md` Objection] |
| How are the feed articles written? | Lokale Modelle, ~100 Wörter, eine Quelle; Grounding-Gate; zweites Modell für Grenzfälle; gated, nicht redigiert | [V6][C:Stage 5/9/10] |
| What does an analysis cost? | Alles einzeln scoped und angeboten; keine Tiers/Abo; Tagessatz für Hands-on-Tage; Anfrage per Mail | [D:#93][V19 Hypercare Tagessatz] |
| Is my data private? | Kein Account; Feed-Suche im Browser; keine Analytics/Tracking-Cookies; Newsletter-Adresse beim Versanddienstleister laut Datenschutz | [D:static_export (kein `/api/track`)][D:Datenschutz §7] |
| Who is it for? | Innovations-/Strategie-/R&D-Teams in KMU und Konzernen; Berater; Investoren | [`03_positioning_brief.md` §3, ohne Preis-Persona] |

## 7. Newsletter-Block (`#subscribe`)

- **Eyebrow/H2:** `Weekly briefing` — **One email a week. Every item, sourced.**
- **Lede:** *What moved across the eight verticals, which themes gained share, and a note when a
  new analysis is out — each item linked to its source. Weekly from launch; until then, the
  launch notice.* [D6][D:#93 offene Entscheidung 2: „wöchentliche Zusammenfassung plus ‚neue
  Analyse erschienen'"] — **[OWNER]** „note when a new analysis is out" ist ein Versprechen an
  die Abonnenten; streichen, wenn der Newsletter das nicht leisten soll.
- **Formular, Consent-Text, Rechtshinweis, `NL_ENDPOINT`:** unverändert (DOI-Strecke
  `/newsletter/subscribe.php`). Der Consent-Text nennt weiterhin `contact@catandary.de`.

## 8. Footer

- **Brand:** *Trend intelligence read from primary sources on local models. A free 30-day feed,
  and individual analyses built from the full corpus.*
- **Product:** Trend feed (`/trends`) · Mega Signal Themes (`/trends/mega`) · Newsletter archive
  (`/trends/newsletter`) · Methodology (`/trends/methodology`) — alle vier **erst ab Launch
  sichtbar** — · What's free (#free) · How it works (#how) · Weekly briefing (#subscribe)
  [D:HOSTING_HETZNER URL-Schema des Exports]
- **Company:** Request an analysis (mailto) · Contact (`trends@catandary.de`) · Impressum ·
  Datenschutz (Modal, unverändert)
- **Legal-Zeile:** `© 2026 Catandary · catandary.de` · `Built in Germany · runs on our own
  hardware · cites its sources` [V4][V5]

---

## 9. Technik: Feed-Links und Launch-Schaltung

Der Export unter `/trends/…` existiert erst nach dem ersten Publisher-Lauf; bis dahin wäre
jeder Feed-Link ein 404. Deshalb hängen alle Links in die App **an derselben Logik wie das
„We are live"** des Countdowns:

- Jedes Element mit `data-live-href="…"` ist vor dem Launch entweder `hidden` (Nav „Feed",
  Footer-Produktlinks, Themen-/Archiv-Buttons) oder zeigt auf `#subscribe` (Hero-CTA, Free-CTA)
  mit einem Vor-Launch-Label (`data-live-label` trägt das Launch-Label).
- Erreicht der Countdown `diff <= 0`, ruft `tick()` zusätzlich `goLive()`: setzt `href` auf
  `data-live-href`, entfernt `hidden`, tauscht das Label. Beim Seitenaufruf nach dem 01.10.
  09:00 CEST passiert das sofort beim ersten `tick()`. Neue CSS-Regel
  `[hidden]{display:none!important}` (nötig, weil `.hide-sm{display:inline}` das
  UA-`hidden` sonst überstimmt).
- **Früher freischalten** (Export ist vor dem 01.10. oben): das Zieldatum in `new Date(...)`
  vorziehen — eine Stelle; `.cd-date`-Text dann mitziehen. **Ohne JS** bleibt die Seite im
  Vor-Launch-Zustand (kein toter Link). Nach dem Launch kann der Owner die `hidden`-Attribute
  und die `#subscribe`-Hrefs von Hand hart setzen, damit der Zustand nicht von JS abhängt
  (optional, ca. 2 Minuten).
- **Entfernt (JS):** TIR-Chart-Block, Momentum-Board-Block (Engine ist nicht mehr öffentlich).
  **Entfernt (CSS):** Demo-, Lanes-, Board-, Compare-, Pricing-Regeln. **Geändert:** Zähler
  formatiert Millionen (`data-fmt="m"` → `21.6M`).

### Validierung (2026-09-03)

| Prüfung | Ergebnis |
|---|---|
| Wohlgeformtheit (`html.parser`, Tag-Balance, Void-Elemente) | 0 Fehler, 0 offene Tags (`tidy` nicht installiert) |
| JS-Syntax (`node --check` auf dem extrahierten `<script>`) | OK |
| `grep -c` `/trends/pricing` · `/trends/foresight` · `€` · `per month` · `/mo` · `Starter` · `early access` · `coming soon` · `Explore the live engine` · `unique` · `radar` | je **0** |
| `\bPro\b` | nur in „Super Pro+" (4 Treffer: 1 CSS-Kommentar, 1 HTML-Kommentar, Band, FAQ) |
| `before you see it in the market` | **1** — ausschließlich `og:description` (unverändert, Auftrag; siehe Abschnitt 11) |
| Byte-identisch zu HEAD (`git show HEAD:…`): `<head>` inkl. OG + `noindex`, Countdown-Sektion, `<form>` + Consent + Rechtshinweis, Legal-Modal, Newsletter-JS, Modal-JS | alle `identical=True` |
| Datum `01 Oct 2026 · 09:00 CEST` / `2026-10-01T09:00:00+02:00` | genau 2 Vorkommen wie zuvor |
| Dateigröße | 77.052 → 60.870 Bytes (−16.182; 1.259 → 994 Zeilen) |

## 10. Bewusst weggelassene Claims

| Weggelassen | Warum |
|---|---|
| „See it in the research before you see it in the market" / „The gap: … research years earlier" / „Research led the market by several years" | Früherkennungs-Claims (Owner-Regel 25.07., H6/H7) |
| Preistabelle Free/Starter/Pro/Super Pro+ mit €-Beträgen, „Individual Analysis · €1,499/day", „Request early access", „coming soon", „self-service price" | kein SaaS (#93); Seite nennt keinen Betrag |
| „Explore the live engine", TIR-Demo mit Chips, Momentum-Board „See the full cluster board", Vergleichstabelle „Keyword tools / Catandary / Enterprise suites" mit €-Bändern | Engine nicht öffentlich (PUBLIC_MODE), €-Vergleich = Positionierung ohne Benchmark (H10) |
| „221 live clusters", „~42.6M patents", „~150 million data points", „hand-checked, all six matched", „1,059,838 signals / 60,482 articles" | Stand 21.07. bzw. widersprüchliche Zählbasis; ersetzt durch CLAUDE.md-Zahlen mit Stand August 2026 — 23/24-Recovery und 6/6-Momentum (V14) bewusst nicht auf der Landing, weil sie Engine-Features bewerben |
| „145k companies" | nur in `docs/startup_explorer_plan.md` belegt, nicht in Truth Matrix/CLAUDE.md |
| „Lead-time" als Produktbegriff, „radar", „export/CSV/dossier export", „saved searches & alerts", „API" | Radar entfernt, Export-Features waren Tarif-Merkmale, API war D1 „coming soon" |
| Kunden, Logos, Zertifikate, „GDPR compliant", „unique/proprietary" | H1–H4 |
| Aussagen zur Anzahl der Abonnenten | D6 (1 Abonnent) |

## 11. Offene Owner-Entscheide

1. **`og:description`** trägt noch *„See it in the research before you see it in the market."* —
   im Auftrag als unverändert vorgegeben, widerspricht aber der Früherkennungs-Regel. Vorschlag
   beim Upload: *„A free 30-day trend feed read from primary sources on local models, and
   individual analyses built from the full corpus."* (`og:title`/`<title>` „Evidence-Based
   Trend & Foresight Intelligence" können bleiben.)
2. **Anfrage-Adresse:** die Seite nutzt `trends@catandary.de` (App-Impressum, `/enquiry`,
   bisheriger Footer); Impressum-Modal und Consent-Text in derselben Datei nennen
   `contact@catandary.de`. Eine Adresse festlegen oder beide bewusst behalten.
3. **Headline** wählen (Abschnitt 2) — eingebaut ist *„Trend intelligence, traced to its sources."*
4. **Patentzahl** 19,6 M (eingebaut) vs. 42,6 M (V16); **145k Firmen** aufnehmen? (→ Truth
   Matrix ergänzen).
5. **Hypercare-Tagessatz** nennen (1.499 €/Tag, V19) oder weiter „billed by the day, quoted"?
6. **`/analysis`** verlinken, sobald erste Analyse + Adresse feststehen (Root-Seite wird nicht
   mit exportiert; `HOSTING_HETZNER.md` „Offen").
7. **Newsletter-Versprechen** „note when a new analysis is out" behalten?
8. **Fenster — seit 02.10.2026 14 Tage (Owner):** Landing auf „last 14 days" umgestellt (Meta-/OG-Beschreibung, Hero-Subline, H2, Karte 01, Lede, FAQ, Footer); „around 15,000" passt (16.201 am 02.10.). Früher: 30 Tage blieb die Aussage der Seite („last 30 days", „around 15,000") — bei
   Wechsel auf 60/90 Tage (#93 Entscheidung 1) drei Stellen anpassen (Hero-Subline, Free-Lede,
   Free-Karte 01, Footer-Brand, FAQ „Where the limits are").
9. **`noindex`** bleibt bis zum Launch (`preview.html:7`); zum 01.10. entfernen (Launch-Plan
   Owner-Aktion 4).
10. **Die App-Landing** (`frontend/src/app/page.tsx`) trägt noch die alte Copy mit sechs toten
    Links (`/trends/foresight*`, `/trends/pricing`) — nicht in diesem Scope; sobald der Export
    `/` ersetzen soll, diese Copy dorthin übernehmen.

## 12. Upload (Owner-Aktion)

Unverändert die drei SFTP-Schritte aus `HOSTING_HETZNER.md` → „Option A — Hetzner Webhosting":

1. Per SFTP auf den Webspace (Host/User/Passwort aus konsoleH → Zugänge).
2. `preview.html` als **`index.html`** in den Document Root, daneben `mark.svg`, `favicon.ico`,
   `robots.txt` (Reihenfolge laut `newsletter-doi-php/EINBAU.md`: erst `newsletter/`, dann die
   vier Dateien).
3. Prüfen: `curl -sI https://catandary.de/ | grep -i last-modified` und
   `curl -s https://catandary.de/ | grep -o '2026-10-01T09:00:00+02:00'`; zusätzlich
   `curl -s https://catandary.de/ | grep -c 'data-live-href'` → `12`.

Die Feed-Links werden erst mit dem Countdown aktiv (Abschnitt 9); der Export unter `/trends`
muss bis dahin per `publish_static_site.py --apply` oben sein (HOSTING_HETZNER „Erster
SFTP-Dry-Run"), sonst laufen die Links ab 09:00 CEST ins 404.

## 13. Belege

- **[Vn]/[Hn]/[Dn]** = Zeilen der `02_product_truth_matrix.md` (V1–V22, D1–D8, H1–H10).
- **[C:912]** CLAUDE.md „Ist-Zustand": 323 aktive Quellen (DB-Ist 2026-09-02), 21,6 Mio. Raw
  Entries (Snapshot 2026-08-07), 28 kanonische Mega-Trends. **[C:516]** Cron-Block
  `weekly_ingesters.sh`: „19,6M-BDDS-Backlog". **[C:502]** Cron-Block OpenAlex-Sync:
  „research_corpus (45M-Suchschicht)". **[C:Stage 5]** Pipeline-Ablauf Schritt 5 (~100 Wörter,
  Owner 2026-08-19). **[C:Stage 9/10]** Auto-Publish + Draft-Richter. **[C:Mega]**
  Routing-Block `/trends/mega` (28 Themes, gemessenes Badge).
- **[D:#93]** `gh api …/issues/93` (Volltext), Zusammenfassung `docs/audits/2026-09-02_issue_audit.md`.
- **[D:HOSTING_HETZNER]** `docs/launch/HOSTING_HETZNER.md` — URL-Schema des Exports, Messwerte
  03.09. (14.846 Artikel, 28 Mega-Seiten, 8 Vertikale), Newsletter-Archiv (12 Editionen), Upload.
- **[D:static_export_design]** `docs/audits/2026-09-02_static_export_design.md` (`/api/track`
  entfällt, 14.713 Artikel am 02.09.).
- **[D:StaticSearch.tsx]** `frontend/src/components/StaticSearch.tsx` (Suche + Chips
  Vertical/PESTEL/Theme, lazy Index).
- **[D:EnquiryContent.tsx]** `frontend/src/components/EnquiryContent.tsx` (`CONTACT_EMAIL`
  Default `trends@catandary.de`, Super-Pro+/Individual-Texte). **[D:ImprintContent.tsx]**
  `frontend/src/components/legal/ImprintContent.tsx` (`trends@catandary.de`).
- **[D:corpus_research.py]** `scripts/corpus_research.py` (`--foresight`, `--company`,
  `--focus`, `--lang` de/en).
- **[D:_template.md]** `frontend/content/analyses/_template.md` (Datum, `corpus_asof`, Autor).
- **[D:#48]** `docs/audits/2026-09-02_issue_audit.md` §#48 (Cron installiert, `dead_links`,
  `deadLinks.ts`).
- Owner-Regeln aus dem Auftrag: keine Früherkennung (25.07.), Radar entfernt (25.08.), kein SaaS
  (26.08.), Tagessätze (19.07.).
