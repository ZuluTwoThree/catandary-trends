# Statischer Export der öffentlichen Website — Machbarkeit & Architektur

Stand 2026-09-02, Worktree `/home/dirk/projects/ct-dev` (Branch `dev`), read-only erhoben.
Owner-Entscheidung 02.09.: catandary.de = statischer Export aufs Hetzner-Shared-Webhosting
(Apache/PHP, kein Node). Öffentlich: 30-Tage-Artikel + Analysen + Newsletter (PHP-DOI) + Rechtstexte.

## 0. Messwerte (Live-DB und Live-Instanzen, 02.09. ~09:30)

| Größe | Wert | Quelle |
|---|---|---|
| Published, `sort_date` ≤ 30 Tage | **14.713** Artikel | `trends WHERE status='published' AND sort_date >= now()-30d` |
| davon ohne `mega_trend` | 968 | dito |
| Body-Text gesamt | 11,8 MB (Ø 804 Zeichen) | `SUM(length(body_en))` |
| Titel / Summary gesamt | 1,0 MB (Ø 68) / 5,1 MB (Ø 346) | dito |
| Summary auf 160 Zeichen gekürzt | 2,26 MB | `SUM(length(left(summary_en,160)))` |
| `tags` | **leer in allen 14.713 Zeilen** (`[]`) | dito — Tags sind für den Index irrelevant |
| Slug Ø | 74 Zeichen, Muster `[a-z0-9-]+-<id>` | Stichprobe :3999 |
| Vertikale (30 T) | TECH 4.945 · BIZ 3.284 · ECO 2.485 · HEALTH 2.375 · FOOD 673 · LIFESTYLE 467 · FASHION 247 · DESIGN 237 | |
| Mega-Themes (30 T) | 26 distinct, Spitze `artificial_intelligence_and_automation` 2.924 | |
| Quellen (30 T) | 200 distinct `source_name` | |
| Tageszugang | 100–620/Tag (letzte 7 Tage), Ø ~490 | |
| Täglich aus dem Fenster fallend | ~587 (Tag 31) | |
| 60 / 90 Tage / alles published | 30.587 / 49.460 / 84.563 | Skalierung für Owner-Frage „mehr als 30 Tage" |
| `newsletter_editions` | 21 | |
| `dead_links` | Tabelle existiert auf der Live-DB | |
| Prod-Build, prerenderte Seiten (main-Worktree) | 23–28 KB HTML (`imprint`, `analysis`, `enquiry`, …) | `.next/server/app/*.html` |
| Artikelseite (dev :3999) | 50 KB gesamt, ~15 KB reines Markup, **9,7 KB gzip** | |
| `/trends` Listing (dev, 12 Karten) | 129 KB (dev-Overhead; prod-Schätzung ~45–60 KB bei 24 Karten) | |
| `_next/static` Prod-Build | **1,7 MB** (996 KB Chunks, 628 KB Fonts) | main-Worktree |
| Cycle-Ende | 05:55–06:12 (Mo–Fr; `full_cycle_cron.sh end … rc=0`) | `~/logs/catandary-full-cycle-*.log` |
| Maschine | 16 Kerne, 62 GB RAM, Postgres `max_connections=100` | |

Instanzen: `:3001` main, `:3004` dev (PUBLIC_MODE **nicht** gesetzt — liefert `/trends/pricing` 200),
`:3999` dev mit `PUBLIC_MODE=1` + `NEXT_DIST_DIR=.next-public` (liefert die Blockliste als 404 —
das ist die relevante Vorschau).

---

## 1. Inventar der öffentlich bleibenden Routen

Quelle: `frontend/src/lib/publicMode.ts` (Blockliste) ∩ #93 „Bleibt öffentlich / Neu".

| Route | Datei | Datenabhängigkeit (db.ts) | Query-Parameter / Laufzeit | Statisch exportierbar? |
|---|---|---|---|---|
| `/` | `app/page.tsx` (597 Z.) | `getMethodologyStats()` (1h-Cache, Full-COUNTs) | `force-dynamic`; Client-Komponenten `LaunchCountdown`, `ProofCounter`, `HeroInstrument`, `TechReader` (kein Fetch) | **Ja** nach Entfernen von `force-dynamic`. Aber: Copy verlinkt noch `/trends/foresight*` (3×) und `/trends/pricing` (#93 Etappe 4 offen) |
| `/trends` | `app/trends/(feed)/page.tsx` | `getTrendsFiltered`, `getTrendsFilteredCount`, `getVerticalCountsScoped`, `getVerticalCounts`, `getTrendsCount`, `getMegaTrends`, `getTopSourcesByCount` | **`searchParams`**: `v` (Vertikale, multi), `pestel`, `signal`, `mega`, `exclude`, `min_score`, `range` (1d/7d/30d/all), `q` (Postgres-FTS `websearch_to_tsquery`), `sort` (date_desc/asc, score_desc, engagement_desc), `view` (grid/list), `page` (12/Seite); `redirect()` bei Seite > letzte | **Nein in heutiger Form** — `searchParams` macht die Seite zwingend dynamisch. Muss in statische Listing-Routen + clientseitige Filter zerlegt werden (Abschnitt 4) |
| `/trends/[slug]` | `app/trends/[slug]/page.tsx` | `getTrendBySlug`, `getTrends` (related: 4 neueste derselben Vertikale), `getTrendTechContext` (**pgvector-Query** `embedding_1024 <=>`, im PUBLIC_MODE nutzlos, da `TechContext` null rendert), `isSourceLinkDead` | `generateMetadata`; `TrendArticle` ist `"use client"` und feuert `POST /api/track` per `useEffect` | **Ja** mit `generateStaticParams` (14.713 Slugs) + `dynamicParams=false`. Achtung: „related" ist tagesabhängig → jede Artikel-HTML ändert sich täglich (siehe 5.) |
| `/trends/vertical/[v]` | 10 Zeilen, `redirect('/trends?v=…')` | — | Redirect auf `?v=` (den es statisch nicht mehr gibt) | Entfällt → Apache-`Redirect` in `.htaccess` |
| `/trends/mega` | `app/trends/mega/page.tsx` | `getMegaTrends('published')` (Full-GROUP-BY über 1,1 M Zeilen, 10-min-Cache) + `mega_trends.yaml` (Pfad `process.cwd()/../mega_trends.yaml`) | `MegaTrendsPage` ist Client (nur Props) | **Ja** |
| `/trends/mega/[m]` | `app/trends/mega/[megatrend]/page.tsx` | `getMegaTrends`, `getTrendsByMegaTrend` (Limit 50, gefenstert) | `generateMetadata` | **Ja** mit `generateStaticParams` (26–28 Keys) |
| `/trends/methodology` | 192 Z. | `getMethodologyStats()` | `force-dynamic` | **Ja** |
| `/trends/newsletter` | `app/trends/newsletter/page.tsx` (510 Z., **`"use client"`**) | — (Client) | Laufzeit-Fetches: `GET /api/newsletter?list=true`, `GET /api/newsletter[?year&week]`, `POST /api/newsletter` (Signup → Postgres) | **Nein** — Archiv/Edition müssen beim Build materialisiert werden; Signup → bestehendes `subscribe.php` |
| `/trends/newsletter/unsubscribe` | 63 Z. | `q()` UPDATE `newsletter_subscribers` + HMAC (`AUTH_SECRET`) | `searchParams` `email`, `token`; **schreibt in die DB** | **Nein** — braucht PHP-Endpoint (existiert im DOI-Paket noch nicht) |
| `/analysis`, `/analysis/[slug]` | `lib/analyses.ts` (fs, `content/analyses/*.md`) | keine DB | `generateStaticParams` **existiert bereits** | **Ja** (heute nur `_template.md`; `public/analyses/` für OG-Bilder existiert noch nicht — `frontend/public/` gibt es gar nicht) |
| `/enquiry` | 100 Z. | keine (mailto, `CONTACT_EMAIL`) | statisch | **Ja** |
| `/imprint`, `/privacy` | statisch | — | — | **Ja** |
| `/sitemap.xml` | `app/sitemap.ts` | `getTrends({limit:5000})`, `getMegaTrends`, Analysen | `force-dynamic`; listet heute **Foresight + Pricing** (öffentlich 404) und cappt bei 5.000 Artikeln | **Ja** nach Umbau (public-only URLs, alle 14.7k) |
| `/robots.txt` | `app/robots.ts` | — | statisch | **Ja** |
| `icon`, `opengraph-image` | `ImageResponse`, Font-Fetch von Google beim Build (Fallback vorhanden) | — | Build-Zeit | **Ja** |
| `not-found.tsx` | brandiertes 404 | — | — | Wird zu `out/404.html` → Apache `ErrorDocument 404` |

**API-Routen, die öffentlich blieben** (nicht in der Blockliste) und im Export **alle entfallen**:

| Route | Nutzung | Ersatz |
|---|---|---|
| `POST /api/track` | `TrendArticle` page_view/share → `trend_metrics` | entfällt (Server-Logs) oder `track.php` (Abschnitt 4) |
| `GET/POST /api/newsletter` | Newsletter-Seite (Archiv, Edition, Signup) | Build-Zeit-Materialisierung + `subscribe.php` |
| `GET /api/trends` | öffentliche JSON-API (50/Seite, Vertikale, Offset) | statisches `/data/index.json` oder ersatzlos (Owner) |
| `GET /api/search` | Foresight-Cockpit-Hybridsuche (Ollama-Embedding + RRF) | wird von den öffentlichen Seiten **nicht** genutzt; entfällt |

**Komponenten mit Laufzeit-Hooks** (funktionieren im Export nur als Client-Side-Rendering):
alle 11 `components/filters/*` + `Pagination`, `TrendsEmpty`, `VerticalFilter` nutzen
`useSearchParams`; `MobileNav`/`NavLink` nutzen `usePathname`. Das ist im Export erlaubt
(Suspense-Boundaries sind da), liefert aber nur clientseitig gefilterte Hrefs — die eigentliche
Datenfilterung passiert heute serverseitig und muss ersetzt werden.

**Kopplung an Auth/Cookies** ist unkritisch: `Header` ruft `getSession()` (→ `cookies()`) nur bei
`AUTH_ENABLED && !publicMode`; `archiveWindowDays()` kehrt bei PUBLIC_MODE vor `viewerTier()` zurück.
Kein öffentlicher Pfad berührt `cookies()`/`headers()` → kein „Dynamic Server Usage"-Fehler.

---

## 2. Pfad A: Next.js `output: 'export'`

### 2.1 Harte Inkompatibilitäten (im installierten Next 16.2.11 verifiziert, `node_modules/next/dist`)

| Bestand | Export-Verhalten | Befund |
|---|---|---|
| `src/proxy.ts` (Next-16-Name für Middleware) | Build-Fehler `Middleware cannot be used with "output: export"` | Datei darf im Export-Baum nicht existieren. Sie ist im Export ohnehin überflüssig (die Blockliste wird gar nicht erst gebaut) und auf der Workstation ohne PUBLIC_MODE ein No-op |
| 18 Route-Handler unter `app/api/**` (POST, `force-dynamic`) + `trends/foresight/research/{export,suggest}/route.ts` | `API Routes cannot be used with "output: export"` (nur statische GET-Handler erlaubt) | Müssen aus dem Export-Baum raus |
| `export const dynamic = "force-dynamic"` in **16 öffentlichen Dateien** (`page.tsx`, `(feed)`, `[slug]`, `mega`, `mega/[m]`, `methodology`, `sitemap.ts`, `unsubscribe`, …) | Export bricht ab („couldn't be rendered statically") | Segment-Config muss ein **Literal** sein — kein `process.env`-Ternary möglich. Ersatz: Laufzeit-Opt-in per `await connection()` (`next/server`, seit Next 15) hinter einem Env-Guard — ein Helfer `dynamicUnlessStatic()` ersetzt die Zeile 1:1 und hält die Workstation-Instanz frisch |
| 13 geblockte Seiten (`/account*`, 9× `/trends/foresight*`, `review`, `quality-preview`, `pricing`) — alle `force-dynamic`, `searchParams`, `cookies()` | Es gibt **keine** Route-Exclusion in Next; jede Seite im Baum muss exportierbar sein | Aus dem Export-Baum raus (Staging-Kopie, s. 2.3) |
| `/trends` mit `searchParams` + `redirect()` | dynamisch | Neue statische Listing-Routen (Abschnitt 4) |
| `[slug]`, `mega/[m]` ohne `generateStaticParams` | `is missing "generateStaticParams()" so it cannot be used with "output: export"` | ergänzen; `dynamicParams=false` |
| `vertical/[v]` → `redirect()` | Redirect-Seite statisch nur als Meta-Refresh | ersatzlos, `.htaccess`-Redirect |
| `next/image` | wird **nicht** benutzt | kein `images.unoptimized` nötig (schadet nicht) |
| `next/font/google` | lädt beim Build (Workstation hat Netz), self-hosted in `_next/static/media` (628 KB) | ok |
| `trailingSlash` | Default `false` → `out/trends/<slug>.html` + `<slug>.txt` (RSC-Payload für Client-Navigation) | Apache braucht Rewrite `/trends/<slug>` → `.html` (mod_rewrite via `.htaccess`; das DOI-Paket nutzt `.htaccess` bereits) — URLs bleiben identisch zur App. Alternative `trailingSlash: true` → `<slug>/index.html`, ohne Rewrite, aber URL-Form ändert sich |
| `basePath` | Site liegt auf der Domain-Wurzel | nicht nötig |
| Build-ID | app-router-HTML/RSC-Payload enthält die Build-ID → **jede** Datei ändert sich pro Build | `generateBuildId: () => "public"` für deterministische Ausgabe (Voraussetzung für inkrementellen Upload) |
| Export-Worker × pg-Pool | Next startet bis zu `cpus-1 = 15` Worker, `pg.ts` hat `max: 10` → bis 150 Verbindungen > `max_connections=100` | `experimental.cpus` auf ~6 setzen und/oder Pool-Max im Export auf 4 |

### 2.2 Betroffene Dateien (Umfang)

| Änderung | Dateien | Aufwand |
|---|---|---|
| `next.config.ts` env-bedingt (`STATIC_EXPORT=1` → `output:'export'`, `distDir`, `generateBuildId`, `trailingSlash`, `experimental.cpus`) | 1 | klein |
| `force-dynamic` → `await dynamicUnlessStatic()` | 16 (+ `lib/renderMode.ts` + Test) | klein, mechanisch |
| `[slug]`: `generateStaticParams`, `dynamicParams`, stabile Related, Tech-/Track-Skip, Canonical | 2 (`page.tsx`, `TrendArticle.tsx`) | mittel |
| `mega/[m]`: `generateStaticParams` | 1 | klein |
| Listing: `/trends` statisch + `trends/page/[n]` + `trends/v/[vertical]/page/[n]` + Filter-Panel client-seitig | 3–4 neue Routen, `FilterBar`/`Pagination`/`filter-params.ts` Anpassung | groß |
| JSON-Index als statischer GET-Route-Handler (`app/data/index.json/route.ts`) | 1 neu | klein |
| Newsletter-Seite: Client → Server-Komponente mit Build-Daten; Form → `subscribe.php` | 2 (+ `unsubscribe.php` im DOI-Paket + `newsletter_sender.py` Link) | mittel |
| `sitemap.ts` public-only, ungecappt; `robots.ts` | 2 | klein |
| `public/.htaccess`, `expired`-Seite | 2 neu | klein |
| Build-/Deploy-Skripte + Cron | 2 neu | mittel |
| Doku (CLAUDE.md, HOSTING_HETZNER.md, README) | 3 | klein |

Rund **30 Dateien**, davon 16 mechanisch. Der Export-Pfad bleibt eine **Zusatzkonfiguration** —
Workstation-Instanz (`:3001`) und PUBLIC_MODE-Vorschau (`:3999`) laufen unverändert weiter.

### 2.3 Zweite Next-Config über `NEXT_DIST_DIR`: sauber möglich?

**Teilweise.** Die Konfigurationsseite ist sauber lösbar (Env-Ternaries in `next.config.ts`,
`NEXT_DIST_DIR=.next-static` ist schon da). **Nicht** per Config lösbar sind die drei
Baumeigenschaften: `proxy.ts` darf nicht existieren, die 13 geblockten Seiten und 20 Route-Handler
dürfen nicht existieren, `searchParams`-Seiten dürfen nicht existieren. Der einzige saubere Weg,
der die Quelle **nicht** verdoppelt, ist ein **Staging-Baum per Verzeichnis-Exclusion**:

```
rsync -a --delete --exclude-from=frontend/static-export.exclude frontend/ .static-build/frontend/
#  static-export.exclude:
#   src/proxy.ts   src/app/api/   src/app/account/   src/app/trends/foresight/
#   src/app/trends/review/   src/app/trends/quality-preview/   src/app/trends/pricing/
#   src/app/trends/newsletter/unsubscribe/   src/app/trends/vertical/   node_modules/ .next*/
ln -s ../mega_trends.yaml .static-build/mega_trends.yaml   # db.ts liest process.cwd()/../mega_trends.yaml
ln -s ../../frontend/node_modules .static-build/frontend/node_modules
cd .static-build/frontend && STATIC_EXPORT=1 PUBLIC_MODE=1 NEXT_DIST_DIR=.next-static npm run build
```

Nur Verzeichnisse ausschließen, **keine** sed-Patches am Quelltext — die Exclude-Liste ist der
dokumentierte Spiegel von `BLOCKED_PREFIXES` in `publicMode.ts` (ein Vitest kann beide abgleichen).
Alles andere (Segment-Config, Listing, Index, Newsletter) wird im echten Quellbaum mit
`isStaticExport()`-Branches gelöst — ein Baum, zwei Modi, beide testbar.

### 2.4 Build-Zeit und Volumen (Schätzung, im Spike zu messen)

- Kompilieren ~1–2 min; Prerender 14,7k Artikel × (1 Slug-Query + 1 Related-Query + 1 dead_links)
  bei 6–8 Workern ≈ 3–6 min; ~1.6k Listing-Seiten ≈ 1–2 min → **~10 min Gesamtbuild**, täglich
  voll (Next-Export ist nicht inkrementell). RAM unkritisch (62 GB).
- `out/`: 14,7k × (~33 KB HTML + ~10 KB `.txt`) ≈ **630 MB** + Listing ~1,6k × ~75 KB ≈ 120 MB
  + `_next/static` 1,7 MB → **~750 MB, ~31k Dateien** (#93 schätzte ~550 MB; Größenordnung stimmt).
  Auf dem Draht ~10 KB/Artikel (gzip, sofern mod_deflate aktiv — zu prüfen).
- Skalierung Owner-Frage: 60 Tage ≈ 1,5 GB / 62k Dateien / ~20 min Build; 90 Tage ≈ 2,5 GB /
  100k Dateien / ~30 min. Jenseits ~50k Seiten wird der Next-Export zäh — dann Pfad B (unten).

---

## 3. Pfad B: eigener Generator

| Kriterium | Next `output:'export'` | Node `renderToStaticMarkup` mit Bestandskomponenten | Python/Jinja aus der DB |
|---|---|---|---|
| Designsystem-Wiederverwendung | 100 % (Layout, Header/Footer, Tailwind-v4-Tokens, Fonts, Metadata/OG, JSON-LD) | Nominell hoch, praktisch brüchig: `Header` ist eine **async Server-Komponente** (renderToStaticMarkup kann das nicht), `next/link`/`usePathname`/`useSearchParams` brauchen Router-Kontext, `next/font` fehlt, Tailwind v4 muss separat gescannt werden → man baut Next nach | 0 % — Templates + CSS-Duplikat; Tailwind-Klassen müssten per CLI gegen Jinja-Templates gebaut werden; zweite Design-Quelle driftet |
| Build-Zeit 15k Seiten | ~10 min, nicht inkrementell | ~1–2 min | <1 min, **inkrementell** (nur neue/geänderte Artikel) |
| Determinismus/Upload-Delta | nur mit konstanter Build-ID + stabilen Related | gut | sehr gut |
| Framework-Zwänge | viele (Abschnitt 2.1), aber einmalig | keine, dafür Eigenbau von Routing, Metadata, Sitemap, Hydration der Filter-UI | keine; Filter-UI muss als Vanilla-JS neu entstehen |
| Wartbarkeit | ein Quellbaum, zwei Modi | zwei Render-Pfade für dieselben Komponenten | zwei Produkte (Next intern, Jinja öffentlich) |
| Eignung für >50k Seiten / Vollarchiv | schlecht | mittel | sehr gut |

**Bewertung:** B1 (renderToStaticMarkup) ist die schlechteste Option — hoher Aufwand bei brüchigem
Ergebnis. B2 (Jinja) ist nur dann überlegen, wenn der Owner statt 30 Tagen das **Vollarchiv**
(84k Artikel, #93 offene Entscheidung 1) veröffentlichen will oder der Spike zeigt, dass der
Next-Export nicht deterministisch/zu langsam ist. Für 30–90 Tage gewinnt Pfad A durch
Wiederverwendung; B2 bleibt der dokumentierte Fallback für die Artikelseiten.

---

## 4. Ersatz der dynamischen Funktionen

### 4.1 Listing, Filter, Suche, Pagination

**Statisch vorgerendert (SEO, ohne JS lesbar):**
- `/trends` = Seite 1 (neueste 24), `/trends/page/2…N` (N ≈ 613 bei 24/Seite; 12/Seite hieße 1.226 Seiten — 24 halbiert Dateizahl und Churn)
- `/trends/v/{food|tech|…}/page/n` (8 Vertikale, TECH bis 206 Seiten)
- `/trends/mega/{key}` (existiert; ggf. `page/n`)
- `Pagination` bekommt statische Hrefs (`/trends/page/n`) statt `?page=`

**Clientseitig über vorgerenderten JSON-Index** (`/data/index-<YYYYMMDD>.json`, per Route-Handler
beim Build erzeugt): Suche `q`, PESTEL, Signaltyp, Score-Slider, Datumsbereich, Quellen-Exclude,
Sortierung, Mega-Kombinationen, Grid/List. Der Index wird **erst beim ersten Filter-/Suchklick**
geladen (nicht beim Seitenaufruf) und ist per Dateiname versioniert → `Cache-Control: immutable`.

Indexgröße (aus den DB-Summen, 14.713 Einträge):

| Felder | roh | gzip (Schätzung, engl. Text ~0,3) |
|---|---|---|
| slug + title + vertical + mega + date + source + score + pestel + signal (ohne Summary) | ~3,3 MB | ~1,0 MB |
| + Summary 160 Zeichen | ~5,6 MB | ~1,7 MB |
| + Summary voll (346 Ø) | ~8,5 MB | ~2,6 MB |
| pro Vertikale geshardet (größter Shard TECH, mit Summary160) | ~1,9 MB | ~0,6 MB |

Empfehlung: **eine Datei mit Summary160** (~1,7 MB gz, lazy) — Suche über Titel+Summary deckt ab,
was die heutige FTS (`title+summary+tags`, Tags sind leer) abdeckt. Matching clientseitig als
Token-`includes` mit einfachem Ranking (14,7k Strings < 30 ms), optional `minisearch` (8 KB), kein
Server. `sort=engagement_desc` („Most read") entfällt ohne Tracking.

### 4.2 Newsletter
- Signup: Formular postet **form-encoded** an `/newsletter/subscribe.php` (Origin-Check same-origin,
  Felder `email`, `consent=1`, Honeypots `website`/`company_url`, optional `verticals[]`) — exakt
  wie `preview.html` heute (`NL_ENDPOINT`). Die JSON-Antwort `{ok,message}` passt zur bestehenden
  Status-UI der Seite.
- Archiv/Edition: beim Build aus `newsletter_editions` als statische Seiten
  `/trends/newsletter` (aktuell) + `/trends/newsletter/2026-w35` (21 Editionen).
- Unsubscribe: **Lücke** — im DOI-Paket gibt es keinen Abmelde-Endpoint (nur `cron.php`-Cleanup
  für Status `unsubscribed`). Nötig: `newsletter/unsubscribe.php` (HMAC mit `unsub_secret` =
  `AUTH_SECRET`, wie `nl_config.php` Block 5 vorsieht) → schreibt in MySQL (System of Record),
  `sync_subscribers.py` spiegelt nach Postgres. `pipeline/newsletter_sender.py` baut den Link dann
  auf `/newsletter/unsubscribe.php?email&token`.

### 4.3 Engagement-Tracking
`/api/track` entfällt; `TrendArticle` darf im Static-Modus keinen Fetch absetzen. Optionen:
(a) nur Hetzner-Zugriffslogs/AWStats in konsoleH (0 h); (b) `track.php` in MySQL, per Sync zurück
in `trend_metrics` (~2 h, hält „Most read" am Leben); (c) Plausible (extern, cookieless, kostet).
Empfehlung Launch: (a), (b) als Folge-Issue.

### 4.4 Enquiry
Bleibt mailto (heute); ein Formular später als `enquiry.php` nach dem Muster des DOI-Pakets (Resend).

---

## 5. Betrieb

### 5.1 Ablauf täglich (Mo–Fr)
1. 04:00 Full Cycle, endet 05:55–06:12 (Log-Endzeile `rc=0`).
2. **06:30** `scripts/publish_static_site.sh` (eigener Cron-Eintrag; nicht in `full_cycle_cron.sh`
   einhängen, damit ein Export-Fehler den Cycle-Exit-Code und den Watchdog nicht verfälscht):
   Staging-Baum → `next build` (Export) → **Verifikation** (Dateizahl ≈ Slug-Zahl ±, `404.html`,
   Stichproben-`grep` auf Titel, kein `/trends/foresight`-Link im HTML) → Upload → Aufräumen.
3. `cycle_watchdog` um 07:45 zusätzlich das Export-Artefakt prüfen (Manifest-Datei mit Datum).

Wochenende: kein Cycle, kein Export; 30-Tage-Fenster wandert erst montags weiter (akzeptabel;
alternativ ein Export ohne Build-Änderung am Samstag).

### 5.2 Upload und Atomarität
- **Zu klären (Owner):** hat das Webhosting-Paket SSH (konsoleH → Zugänge)? `HOSTING_HETZNER.md`
  und `EINBAU.md` kennen nur SFTP; Docroot `/usr/www/users/<login>/`, „Webhosting S", 1 Cronjob.
- Mit SSH: `rsync -az --delete --delay-updates --exclude index.html --exclude newsletter/` —
  `--delay-updates` schreibt alle Dateien als Temp und benennt am Ende um (quasi-atomar), Delta ≈
  neue Artikel (~500 × 43 KB ≈ 21 MB) + alle Listing-Seiten (Pagination verschiebt sich, ~120 MB)
  + Löschungen (~590). Voraussetzung: **deterministische Artikel-HTML** — konstante Build-ID **und**
  stabile „Related"-Auswahl (heute „4 neueste der Vertikale" → jede Artikelseite ändert sich täglich
  → 700 MB/Tag). Vorschlag: Related = 3 Artikel derselben Vertikale **unmittelbar vor** dem Artikel
  (per `sort_date`), einmal berechnet, unveränderlich.
- Ohne SSH: `lftp mirror -R --only-newer --delete` über SFTP — inkrementell (mtime/size), nicht
  atomar. Tragbar, weil Artikelseiten unveränderlich sind und Listing-Seiten sekundenweise
  inkonsistent sein dürfen. Für einen Vollwechsel (Design-Release): Upload nach
  `_staging/`, dann Verzeichnis-Rename per SFTP (`trends` ↔ `_staging/trends`, ms-Fenster).
- `newsletter/` (PHP + Secrets) und `index.html` (solange `preview.html` die Landing ist) sind vom
  `--delete` **ausgenommen**.

### 5.3 30-Tage-Rolling, 410, Sitemap, Canonical
- Täglich ~590 Artikel-URLs verschwinden. Statt 15k-Zeilen-Redirect-Listen: **musterbasiertes 410**
  in `.htaccess` — alle Slugs enden auf `-<id>`:
  ```
  RewriteEngine On
  RewriteCond %{REQUEST_FILENAME} !-f
  RewriteCond %{REQUEST_FILENAME}.html -f
  RewriteRule ^(.*)$ $1.html [L]
  RewriteCond %{REQUEST_FILENAME}.html !-f
  RewriteRule ^trends/[a-z0-9-]+-[0-9]{3,}$ - [G,L]
  ErrorDocument 404 /404.html
  ErrorDocument 410 /expired.html
  Redirect 301 /trends/vertical/tech /trends/v/tech   # 8 Zeilen
  ```
  `expired.html` = brandierte Seite „Dieses Signal ist aus dem öffentlichen 30-Tage-Fenster
  gefallen — Archivzugang anfragen" (Lead-CTA statt Sackgasse).
- `sitemap.xml` täglich neu (14,7k URLs < 50k-Limit, `lastmod` aus `published_at`), nur öffentliche
  Routen; `robots.txt` aus `robots.ts`; `metadataBase` + `alternates.canonical` je Seite;
  bis zum Launch `Header set X-Robots-Tag "noindex"` in `.htaccess` (eine Zeile, am 01.10. weg —
  Owner-Entscheidung, ob vorab indexiert werden soll).

### 5.4 Countdown-Landing
`preview.html` ist heute `/` (noindex, DOI-Formular, Countdown 01.10. 09:00 CEST, aber noch
SaaS-Preise). Die Next-Landing (`app/page.tsx`) hat denselben Countdown (`LaunchCountdown`), aber
Links auf Foresight/Pricing. Empfehlung: bis die „Analysen statt Plattform"-Copy (Owner-Stimme,
#93 Etappe 4) steht, bleibt `preview.html` `/` und der Export lässt `index.html` aus; die
Next-Landing wird `/` zum Launch — dann ein Design für alles (Header/Footer-Nav konsistent).

---

## 6. Empfehlung

**Architektur:** Next `output:'export'` aus einem per Verzeichnis-Exclusion gebildeten Staging-Baum
(`STATIC_EXPORT=1 PUBLIC_MODE=1`), `force-dynamic` durch einen Laufzeit-Guard ersetzt, statische
Listing-Routen + lazy JSON-Index für Filter/Suche, Newsletter über das bestehende PHP-DOI-Paket
(+ `unsubscribe.php`), täglicher Build 06:30 nach dem Cycle mit inkrementellem Upload
(rsync `--delay-updates` bei SSH, sonst lftp), `.htaccess` für Rewrite/410/ErrorDocument/noindex.
Python/Jinja bleibt Fallback, falls der Spike Determinismus oder Build-Zeit widerlegt oder der
Owner das Vollarchiv will.

### Schrittliste (Agentenstunden)

| # | Schritt | Dateien | h |
|---|---|---|---|
| 0 | **Spike**: Staging-Baum, `output:'export'`, `[slug]` mit 300 Slugs, 2 Builds → `diff -r` (Determinismus), Build-Zeit/Größe hochrechnen, `.txt`-Payload-Verhalten hinter Apache-Rewrite lokal prüfen | temporär | 3 |
| 1 | `next.config.ts` env-bedingt; `frontend/static-export.exclude`; `scripts/build_public_static.sh`; Vitest „Exclude-Liste ≙ BLOCKED_PREFIXES" | 4 | 3 |
| 2 | `lib/renderMode.ts` (`isStaticExport`, `dynamicUnlessStatic` via `connection()`), 16× `force-dynamic` ersetzen, Test | 18 | 2 |
| 3 | `[slug]`: `generateStaticParams` (30-T-Slice), `dynamicParams`, stabile Related, Tech-Query/Track-Fetch im Static-Modus aus, Canonical/`metadataBase` | 3 | 3 |
| 4 | Listing: `/trends` statisch, `trends/page/[n]`, `trends/v/[v]/page/[n]`, Mega-Pagination, `Pagination` statisch, `generateStaticParams` für `mega/[m]` | 5 | 6 |
| 5 | JSON-Index-Route-Handler + Client-Filter/Suche-Panel über Index (FilterBar-Umbau im Static-Modus) | 4 | 6 |
| 6 | Newsletter: Server-Seite mit Build-Daten (Edition + Archiv-Routen), Signup → `subscribe.php`; `unsubscribe.php` ins DOI-Paket; `newsletter_sender.py` Link | 5 | 5 |
| 7 | `public/.htaccess`, `expired`-Seite, `sitemap.ts` public-only/ungecappt, `robots.ts`, `404.html`-Check | 4 | 2 |
| 8 | `scripts/publish_static_site.sh` (Build → Verify → rsync/lftp → Manifest → Mail bei Fehler), Cron 06:30, Watchdog-Erweiterung | 3 | 4 |
| 9 | Doku: CLAUDE.md (Routing/Hosting), `HOSTING_HETZNER.md` (Option A wird der Zielpfad), README, #93-Kommentar | 4 | 2 |
| | **Summe** | ~50 | **~36 h** |

Reihenfolge: 0 → 1 → 2 → 3 → 7 → 8 (damit ab hier täglich ein Export läuft, auch wenn Listing noch
`page 1 only` ist) → 4 → 5 → 6 → 9. Schritte 1–3 sind Voraussetzung für alles; 4/5/6 sind unabhängig.

### Risiken

1. **Determinismus/Volumen des Next-Exports.** Ohne konstante Build-ID und stabile Related ändern
   sich täglich alle 14,7k Seiten (~700 MB Upload). Mitigation: Spike-Diff als Gate, `generateBuildId`,
   Related-Regel; Fallback Jinja.
2. **Upload-Kanal unbekannt.** Nur-SFTP heißt kein atomarer Swap, 31k Dateien über lftp, Quota/Inodes
   unklar. Mitigation: Artikelseiten unveränderlich, Listing darf kurz inkonsistent sein, Vollwechsel
   per Verzeichnis-Rename; vorher Quota messen.
3. **Zwei Laufzeitmodi in einem Quellbaum.** Static-Branches (`isStaticExport`) und die Exclude-Liste
   können von der Workstation-Instanz wegdriften. Mitigation: Vitest-Abgleich Exclude ↔
   `BLOCKED_PREFIXES`, CI-Job „Export-Build mit 200 Slugs", Doku-Pflicht (konstitutionelle Regel).
4. **SEO-Churn** durch ~590 410er/Tag — mit 30-Tage-Fenster systemimmanent; längeres Fenster
   (Owner-Entscheidung #93/1) verdünnt es.

### Owner-Klärungen

1. Webspace: SSH/rsync verfügbar (konsoleH → Zugänge)? Speicher-/Inode-Quota des Pakets
   („Webhosting S")? mod_rewrite/mod_deflate aktiv (üblich, bisher nur `.htaccess`-Deny genutzt)?
2. Fenster: 30 Tage (~750 MB, 10 min Build) oder 60/90 Tage (1,5/2,5 GB, 20/30 min)? Vollarchiv
   → Pfad B.
3. Landing: `preview.html` bleibt `/` bis zur neuen Copy, Next-Landing zum 01.10.? Wer schreibt die
   Copy (Owner-Stimme laut #93)?
4. Indexierung vor dem 01.10. erlaubt (noindex-Zeile) oder erst zum Launch?
5. Tracking: gar nicht / Server-Logs / `track.php` / Plausible?
6. Unsubscribe als PHP-Endpoint mit `AUTH_SECRET`-Angleich (NEWSLETTER_GOLIVE Schritt 3) — Freigabe
   für Upload ins `newsletter/`-Verzeichnis (Owner-Gate SFTP).
7. Braucht jemand die öffentliche JSON-API `/api/trends`? Sonst ersatzlos.
8. Related-Regel („3 Vorgänger derselben Vertikale") statt „4 neueste" — Zustimmung.
