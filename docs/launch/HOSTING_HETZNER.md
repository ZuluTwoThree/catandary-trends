# Hosting the landing on Hetzner

`preview.html` is the **versioned copy of the live landing** on `https://catandary.de/`
(state 2026-09-01, uploaded 17:47 CEST). It is one self-contained HTML document — no build,
no database; CSS, JS, font stack, grain texture and inline SVGs are embedded. It references
three sibling files that live next to it in the webroot and in this folder:

| File | Purpose |
|---|---|
| `preview.html` | the page — upload **renamed to `index.html`** |
| `mark.svg` | icon (`<link rel="icon" type="image/svg+xml" href="/mark.svg">`) |
| `favicon.ico` | fallback icon, 16×16 + 32×32 (`<link rel="alternate icon">`) |
| `robots.txt` | allow-all; the page itself still carries `<meta name="robots" content="noindex">` |

The newsletter form posts to `/newsletter/subscribe.php` (double opt-in backend on the same
webspace) — see `newsletter-doi-php/EINBAU.md` for that package and the upload order
(`newsletter/` first, then the four files above).

> **Provenance:** the version that went live on 2026-07-27 (DOI form with consent, legal
> modal for Impressum/Datenschutz, OG meta tags, icon links) was never committed — the repo
> only held the 2026-07-22 base plus the 2026-08-25 edits (`6df0581`: countdown 01.10.,
> radar promise withdrawn). On 2026-09-01 the two were merged (live HTML + exactly those
> five edits) and uploaded; that merged file is this `preview.html`.
>
> `site_preview.html` is the **stale** 2026-08-25 fragment used only for an early Claude
> artifact preview — it has no DOI form, no legal modal, no `<head>`. Don't upload it and
> **don't regenerate `preview.html` from it** (the old regenerate snippet would silently drop
> the form and the modal). Edit `preview.html` directly.

## Option A — Hetzner Webhosting (shared webspace) — what is in use
1. Connect to the webspace with SFTP (host, user & password in the Hetzner *konsoleH* panel).
2. Upload `preview.html` as `index.html` into the document root, plus `mark.svg`,
   `favicon.ico`, `robots.txt` alongside.
3. Verify: `curl -sI https://catandary.de/ | grep -i last-modified` and
   `curl -s https://catandary.de/ | grep -o '2026-10-01T09:00:00+02:00'`.

```bash
# from docs/launch
sftp user@your-space.your-server.de
cd public_html
put preview.html index.html
put mark.svg
put favicon.ico
put robots.txt
```

## Option B — VPS with Caddy — **dropped (owner decision 2026-09-02)**
The VPS path (`HOSTING_PUBLIC_VPS.md`) was never ordered and is off the table. The public
site will be a **static export** of the Next.js app uploaded to the same webspace as this
landing (design: `docs/audits/2026-09-02_static_export_design.md`, plan:
`docs/launch/09_launch_plan_2026-09-02.md`). Until the export ships, this static file stays
the whole public site; once it ships, `/` may be replaced by the exported landing route.

## Statischer Export — Build (Schritte 1–4 + 7 des Designs, Stand 2026-09-03)

Der öffentliche Auftritt wird aus **demselben Quellbaum** wie die Workstation-Instanz
gebaut, nur in einem zweiten Modus. Ohne Flag ist `npm run build` / `next start` unverändert.

```bash
# vom Repo-Root; Ergebnis: frontend/.export/out (+ out.manifest.tsv, out.build_info.json)
scripts/build_public_static.sh                 # volles Fenster (PUBLIC_WINDOW_DAYS=30)
PUBLIC_WINDOW_DAYS=3 scripts/build_public_static.sh /pfad/zum/out   # Schnelltest
```

| Env | Default | Wirkung |
|---|---|---|
| `STATIC_EXPORT=1` | vom Skript gesetzt | `next.config.ts` → `output: "export"`, `images.unoptimized`, `trailingSlash: false`, konstante Build-ID `catandary`, `experimental.cpus: 6`, `turbopack.root` |
| `PUBLIC_MODE=1` | vom Skript gesetzt | Public-Mode-Rendering (kein Foresight/Pricing in Header/Footer/CTAs) |
| `PUBLIC_WINDOW_DAYS` | 30 | Artikelfenster (Slug-Liste, Sitemap, Related-Untergrenze). Tagesgrenze (UTC-Mitternacht − N Tage, `lib/archiveWindow.ts`), damit zwei Builds am selben Tag dieselbe Menge sehen |
| `PUBLIC_NOINDEX` | 1 | `robots.txt` = Disallow all + `<meta name="robots" content="noindex, nofollow">`. **Zum Launch am 01.10. auf 0 setzen** |
| `PUBLIC_SITE_URL` | `https://catandary.de` | `metadataBase` (Canonical/OG absolut), Sitemap-Basis |
| `KEEP_STAGING=1` | – | `.next` im Staging-Baum stehen lassen (Debug) |

**Was das Skript tut:** `rsync` von `frontend/` nach `frontend/.export/site/` mit
`frontend/static-export.exclude` (Blockliste aus `lib/publicMode.ts` + `proxy.ts`, `app/api`,
Unsubscribe-Seite, Vertical-Redirect — `src/lib/staticExport.test.ts` wacht über Drift),
Symlinks `node_modules` und `mega_trends.yaml`, Build mit `STATIC_EXPORT=1 PUBLIC_MODE=1`,
Verifikation (404/Index/Feed/Expired/Sitemap vorhanden, Artikelzahl > 0, **kein**
`"status":"draft"` im Payload), `.htaccess` aus `frontend/public-export/` hineinkopieren,
Manifest (`sha256  size  path`, Basis des inkrementellen Uploads in Schritt 8) und
`build_info.json` (Zeit, Commit, Fenster, Artikel-/Dateizahl, Bytes, Dauer).
`/analysis/[slug]` wird automatisch ausgelassen, solange keine Analyse mit `draft: false`
existiert (Next wertet eine leere `generateStaticParams`-Liste als Fehler).

**Determinismus:** zwei aufeinanderfolgende Builds sind byte-identisch (`diff -rq` leer) —
Voraussetzung dafür sind die konstante Build-ID, `source_date` aus den Daten statt `NOW()`,
`, t.id DESC` als Tiebreaker in allen Listen, Related = 3 Vorgänger derselben Vertikale und
die Tagesgrenze des Fensters. Erwartete Unterschiede von Tag zu Tag: neue/entfallene Artikel,
Feed-Seite 1, Sitemap, Mega-Seiten und die Artikel am unteren Fensterrand (ihre Related-Karten).

**Rendering-Modi im Code:** `lib/renderMode.ts` — `isStaticExport()` und
`await dynamicUnlessStatic()` (ersetzt das frühere `export const dynamic = "force-dynamic"`
in den öffentlichen Seiten; `connection()` hält die Workstation-Instanz request-frisch, im
Export ist es ein No-op). Die DB-gestützten dynamischen Segmente (`[slug]`, `mega/[megatrend]`,
`page/[n]`, `v/[vertical]`, `v/[vertical]/page/[n]`) exportieren `generateStaticParams` **nur im
Export** (`exportStaticParams(...)`, außerhalb `undefined`): die frühere leere Liste machte die
Routen für Next zu SSG, unbekannte Params wurden unter `next start` on-demand *statisch*
gerendert, und das `connection()` darin war ein `DYNAMIC_SERVER_USAGE`-**500 auf jeder
Artikel-, Mega- und Listing-Seite der Workstation-Instanz** (Fund 03.09. beim Owner-Modus-Build;
`next dev` hatte es verdeckt — Prod-Verhalten immer mit `next start` prüfen). Die vier Metadata-Routen (`sitemap.ts`, `robots.ts`, `icon.tsx`,
`opengraph-image.tsx`) sind jetzt `force-static` (Export-Pflicht) — die Workstation-Sitemap
wird dadurch beim Build gerendert, nicht mehr pro Request. Der Export-Modus unterdrückt
`/api/track` (Artikel) und die `/api/newsletter`-Fetches (Signup postet stattdessen
form-encoded an `/newsletter/subscribe.php` mit Consent-Checkbox). Das Listing ist seit 03.09.
statisch (URL-Schema unten), Suche/Filter laufen clientseitig über `trends/index.json`
(Abschnitt „Suche im Export"), das Newsletter-Archiv ist seit 03.09. gebaut (Abschnitt
„Newsletter im Export").

### URL-Schema des Exports (Stand 2026-09-03; `trailingSlash: false`, Apache mappt die Endung)

| URL | Datei im Export | Bemerkung |
|---|---|---|
| `/trends` | `trends/index.html` (Build-Kopie von `trends.html`) + Root `trends.html`, `trends.txt` | Seite 1, neueste 24 (`sort_date DESC, id DESC`); `/trends/` → 301 `/trends` |
| `/trends/page/<n>` | `trends/page/<n>.html` | n ≥ 2; `/trends/page/1` = 404 (eine URL je Seite) |
| `/trends/v/<vertical>` | `trends/v/<vertical>.html` | Kleinbuchstaben (`tech`); `/trends/v/TECH`, `/trends/vertical/tech` → 301 |
| `/trends/v/<vertical>/page/<n>` | `trends/v/<vertical>/page/<n>.html` | n ≥ 2, je Vertikale |
| `/trends/<slug>-<id>` | `trends/<slug>-<id>.html` + `.txt` | Artikel + RSC-Payload; ohne Datei → 410 |
| `/trends/mega`, `/trends/mega/<key>` | `trends/mega.html`, `trends/mega/<key>.html` | 28 Themes |
| `/trends/imprint`, `/trends/privacy`, `/trends/enquiry` | `trends/{imprint,privacy,enquiry}.html` | Export-Adressen der Root-Seiten (`lib/sitePaths.ts`: alle Links gehen darüber; lokal bleiben `/imprint`, `/privacy`, `/enquiry`, die `/trends/…`-Kopien sind dort 404) |
| `/trends/newsletter` | `trends/newsletter.html` | Signup + neueste Edition + Archivliste (s. „Newsletter im Export") |
| `/trends/newsletter/<jahr>-w<kw>` | `trends/newsletter/<jahr>-w<kw>.html` | eine Edition, z. B. `2026-w35` (KW zweistellig); letzte 12; ältere/unbekannte → 404 |
| `/trends/newsletter/unsubscribed` | `trends/newsletter/unsubscribed.html` | statische Abmelde-Bestätigung (303-Ziel von `unsubscribe.php`), noindex |
| `/trends/methodology`, `/trends/expired`, `/trends/sitemap.xml` | `trends/<name>.html`, `trends/sitemap.xml` | |
| `/trends/index.json` | `trends/index.json` | Suchindex des Fensters (ein Artikel je Zeile; `app/trends/index.json/route.ts`), lädt die Client-Suche lazy — s. „Suche im Export" |

Listing-Routen: `app/trends/(feed)/page.tsx` (Seite 1), `app/trends/page/[n]`,
`app/trends/v/[vertical]`, `app/trends/v/[vertical]/page/[n]` → alle rendern
`components/StaticFeed.tsx` (Vertikale + Seite, kein searchParam), `generateStaticParams`
aus den gefensterten Counts (`lib/staticListing.ts`: `STATIC_PAGE_SIZE = 24`,
`listingPath`, `parsePageParam`). Die Filter-Bar des Exports (`StaticFilterBar`) trägt die
Vertical-Links (Seiten, ohne JS nutzbar) und darüber die Client-Suche (`StaticSearch`, nur im
Export gerendert — Abschnitt „Suche im Export"). Vertical-Badges auf Artikel-/Mega-Seiten verlinken im Export `/trends/v/<v>`
(`verticalFeedHref`), lokal `/trends?v=<V>`. Jede Listing-Seite trägt Canonical +
`rel=prev/next`; die Sitemap listet die acht Vertical-Startseiten.

**Root-Dateien:** Next schreibt `/trends` als `trends.html` + `trends.txt` in die Wurzel
des Exports. Der Build kopiert `trends.html` nach `trends/index.html` (das bedient Apache
für `/trends`, mit den `trends/`-Headern), und der Publisher verwaltet zusätzlich genau
diese zwei Root-Dateien (`ROOT_ALLOWLIST`, s. Publish) — `/trends.txt` holt der Router bei
einer Client-Navigation nach `/trends`. Alle anderen Root-Dateien des Exports
(`404.html`, `imprint.html`, `privacy.html`, `enquiry.html`, `analysis.html`, `analysis.txt`,
`_landing_preview.html`, `robots.txt`, `icon`, `opengraph-image`) bleiben „outside scope" und
werden nicht hochgeladen. **Offen:** `/analysis` (Footer-Link „Analyses") ist damit auf der
Live-Site ein 404, solange keine Analyse veröffentlicht ist und der Owner die Root-Seite
nicht von Hand mit der Landing hochlädt — Entscheidung Owner (Verschieben nach
`/trends/analysis` wäre dieselbe Mechanik wie bei den Rechtstexten).

**Messwerte (voller 30-Tage-Export, 2026-09-03 05:15, während des laufenden Full Cycle):**
14.846 Artikel + 28 Mega-Seiten + 618 Feed-Seiten + 8 Vertikale mit 613 Unterseiten +
10 statische Seiten → **32.335 Dateien, 1.200 MiB** (Manifest 1.258.388.304 Bytes);
`next build` **56 s** (Prerender 6 Worker), Skript gesamt **61 s**. Sitemap 14.891 URLs.
Publish-Dry-Run (MODE=local, leeres Ziel): 32.320 verwaltete Dateien / 1.258 MB — Assets 74
(1,4 MB), Artikel 29.692 (930 MB), Listing 2.554 (327 MB, davon die 1.231 Feed-/Vertical-
Seiten je ~130 KB, die sich täglich alle ändern), 15 Root-Dateien außerhalb des Scopes.
Bekannte Restfunde im HTML: `/api/` nur in der externen Quell-URL
`developers.openai.com/api/docs/pricing`; `/trends/foresight` nur in `_landing_preview.html`
(nicht hochgeladen); in den JS-Chunks stehen `/api/track` und `/api/newsletter` als tote
Nicht-Export-Zweige, die zur Laufzeit nicht aufgerufen werden.

**Determinismus-Gate:** zwei direkt aufeinanderfolgende Läufe müssen byte-identisch sein
(`diff -rq` leer). Läuft der 04:00-Cycle parallel (er publiziert bis ~06:00), unterscheiden sich
zwei Läufe nur durch die inzwischen publizierten Artikel — am 03.09. 05:07/05:08: 640 neue
Dateien, 48 geänderte Artikelseiten (Reclassify/Related), sonst nichts; kein Hinweis auf
Nichtdeterminismus. Ein Nebenfund: unter DB-Last (laufender Cycle) lief `getMethodologyStats`
einmal in das 20-s-`statement_timeout` von `lib/pg.ts` und brach den Export ab — der
03:15-Cron liegt vor dem Cycle (Owner 05.09.: veröffentlicht wird der tagsüber freigegebene Stand); ein manueller Build während des Cycles kann scheitern.

Aufräumen zwischen den Läufen ist nicht nötig (das Skript baut die Staging-Kopie mit
`rsync --delete` neu und löscht `.next`/`out` darin vor jedem Build).

### `.htaccess` (frontend/public-export/trends/.htaccess + _next/.htaccess)

Verzeichnisweise — **nie im Webroot** (der bleibt Owner-Sache; der Kommentarblock „ROOT
SNIPPET" am Ende von `trends/.htaccess` listet die wenigen Zeilen, die die Owner-Datei
braucht: Rewrite für Root-Seiten, `ErrorDocument 404`, `ForceType image/png` für
`icon`/`opengraph-image`, Security-Header, `Sitemap:`-Zeile in `robots.txt`).
`trends/.htaccess`: `Options -Indexes`, `DirectorySlash Off` + `RewriteOptions AllowNoSlash`
(Seiten haben gleichnamige Verzeichnisse neben sich), `/trends` → `trends/index.html`,
`/trends/` → 301 `/trends`, `/pfad` → `/pfad.html`, `/pfad/` → 301 `/pfad`, Any-Case- und
Legacy-Vertical-301s (8 Zeilen), 204 für nicht mehr gelieferte Segment-Payloads,
musterbasiertes **410** für `^[a-z0-9-]+-[0-9]+$` ohne Datei
(`ErrorDocument 410 /trends/expired.html`), `ErrorDocument 404 /404.html`, Security-Header
(Spiegel von `next.config.ts`), `Cache-Control: no-cache` für html/txt/xml/json, mod_deflate.
`_next/.htaccess`: immutable 1 Jahr, die drei Manifeste `no-cache`. `.txt`-RSC-Payloads bleiben
`text/plain` — Nexts Router akzeptiert das im Export-Modus.

**Lokaler Apache-Test:** `scripts/htaccess_test_server.sh` startet `httpd:2.4` im Docker
(Stock-Config + rewrite/headers/deflate/expires, `AllowOverride All`, `frontend/.export/out`
read-only als htdocs, Port 8098) und curlt die Kernfälle; nach jedem Build neu starten (der
Build ersetzt das `out/`-Verzeichnis, der Bind-Mount würde stale). Der vollständige Testplan
steht als Kommentarblock am Ende von `trends/.htaccess` — Stand 03.09. alle grün. Schlägt eine
Regel auf dem Webspace mit 500 fehl, ist `AllowOverride` dort zu eng (`Options -Indexes` zuerst
entfernen, dann `DirectorySlash`/`RewriteOptions`).

### Suche im Export (Schritt 5 / D, Stand 2026-09-03)

Der Webspace hat keinen Server, also keine `?q=`-Suche (Postgres-FTS der Workstation). Der
Export trägt stattdessen **einen JSON-Index des Fensters**, `trends/index.json`
(`app/trends/index.json/route.ts`, `force-static` wie die Sitemap — der einzige Route-Handler,
den der Drift-Test `staticExport.test.ts` im Export-Baum duldet), und der Browser filtert ihn
(`components/StaticSearch.tsx`; reine Logik mit Vitest-Abdeckung in `lib/staticSearch.ts`).

**Index:** ein JSON-Array, ein Artikel je Zeile (`wc -l` = Artikelzahl, Build-Check), Reihenfolge
`sort_date DESC, id DESC` wie das Listing, keine Zeitstempel (byte-stabil). Felder je Artikel:
`slug`, `title`, `summary` (≤ 160 Zeichen, an der Wortgrenze gekürzt, „…"), `verticals`
(primäre Vertikale zuerst), `pestel`, `mega_trend`, `sort_date` (ISO-Tag), `trend_score`,
`source_name`, `source_type` (`research` fasst den Research-Signaltyp zusammen — das
Karten-Label „Research/Press/Brand"). Maß 03.09. (14.846 Artikel): **7.840.260 B roh,
2.099.331 B gzip** (Apache liefert per mod_deflate 2.097.082 B) — ~5 % über dem 2-MB-Ziel;
Stellschrauben, falls das drücken soll: Summary auf 120 Zeichen (−8 %) oder ein positionales
Zeilenformat statt Objekten (−6 %). Das Build-Skript prüft valides JSON und Zeilen = Einträge
(fatal) sowie Einträge = Artikelseiten (nur Warnung: beide Abfragen laufen zu verschiedenen
Zeitpunkten des Builds; publiziert der 04:00-Cycle dazwischen, weichen sie ab) und schreibt
`index_entries`, `index_bytes`, `index_gzip_bytes` nach `build_info.json`. Im Webspace gilt
`Cache-Control: no-cache` (trends/.htaccess, `.json`) — nach dem Tagesexport kommt der neue
Index, sonst ein 304. Der Publisher nimmt die Datei als Teil von `trends/**` automatisch mit.

**Ladeverhalten:** Suchbox und Vertical-/PESTEL-Chips stehen im HTML; der Index wird erst beim
ersten Fokus/Klick geholt (ein `fetch`, Ladezustand in der Statuszeile, Fehler mit „Retry"),
dann im Speicher gehalten (Kleinschreibung einmal vorberechnet) und über Client-Navigationen
zwischen Listing-Seiten hinweg behalten. Theme-Chips entstehen aus dem Index (Top 28 nach
Häufigkeit, eingeklappt 8; im 30-Tage-Fenster am 03.09. sind es 26). Suche = Substring über
Titel + Summary, mehrere Terme = AND, Chips = AND zwischen den Dimensionen, OR innerhalb; die
Vertical-Chips matchen die primäre Vertikale (wie `/trends/v/<v>` — dort ist sie der
Default-Chip). Ranking: Titel-Treffer vor Summary-Treffer, dann Indexreihenfolge (Datum).
Max. 50 Karten (`TrendCard`, Link auf `/trends/<slug>`), der Zähler zeigt alle Treffer. Zustand
im URL-Hash (`#q=…&v=TECH,ECO&pestel=T&mega=<key>`, `replaceState`, teilbar, kein
History-Eintrag); ein Deep-Link lädt den Index sofort. Sobald etwas gesetzt ist, ersetzt das
Treffer-Grid den Listing-Body; „Reset filters" / „Back to the feed" stellt ihn wieder her.
Tastatur: Chips sind Buttons mit `aria-pressed`, Escape leert das Feld, Statuszeile `aria-live`.

**Grenzen:** kein Stemming, keine Phrasen (reine Substrings — nicht die
`websearch_to_tsquery`-Semantik der Workstation), nur Titel + gekürzte Summary (keine Bodies,
Tags, Firmen), nur das Fenster, Treffer nicht crawlbar (Client-only; die statischen
Listing-Seiten bleiben der SEO-Pfad), erster Aufruf lädt ~2 MB. Ohne JavaScript bleibt das
Listing samt Vertical-Links voll nutzbar. Lokal (ohne Export-Flag) erscheint die Komponente
nicht — der Handler liefert dort `[]`, die Feed-Suche bleibt `?q=`.

**Test:** Playwright aus dem Python-`.venv` (Chromium) gegen den Apache-Container
(`scripts/htaccess_test_server.sh`): Laden beim Fokus, AND-Suche, Chips, Hash-Deep-Link auf
`/trends/v/tech`, Reset, Escape, Klick auf einen Treffer (Soft-Navigation über das
`.txt`-Payload) — 03.09. ohne Konsolenfehler oder fehlgeschlagene Requests.

### Newsletter im Export (Schritt E, Stand 2026-09-03)

Die Website-Edition des Briefings (Mo 09:00 `scripts/weekly_newsletter_publish.sh` →
`newsletter_editions`) ist im Export ein **statisches Archiv**; lokal bleibt
`/trends/newsletter` die Client-Seite mit `/api/newsletter` und `?year=&week=`
(`components/newsletter/NewsletterClient.tsx`, unverändert). Beide rendern denselben
`components/newsletter/EditionBody.tsx`; der Export-Zweig ist `StaticBriefing.tsx`,
Daten aus `lib/newsletterExport.ts`, Regeln (rein, Vitest) in `lib/newsletterEditions.ts`.

**Seiten:** `/trends/newsletter` = Signup (oben und unten) + neueste Edition + Archivliste;
`/trends/newsletter/<jahr>-w<kw>` (`2026-w35`, KW zweistellig — genau eine Schreibweise, `2026-w5`
ist 404) = eine Edition mit `rel=prev/next`-Leiste, Canonical und OG-Description aus dem
ersten Editorial-Absatz (`editionExcerpt`, ≤ 160 Zeichen); `/trends/newsletter/unsubscribed` =
statische Bestätigung nach der Abmeldung, `noindex, nofollow`. `generateStaticParams` nur im
Export (`exportStaticParams`), auf der Workstation sind die Editions-URLs 404 (dort gilt die
Client-Seite). Die Sitemap listet die Editionen (`lastmod` = `created_at`).

**Archivumfang:** die letzten `PUBLIC_NEWSLETTER_EDITIONS` Editionen (Default **12**,
`lib/archiveWindow.ts` neben dem Artikelfenster; `ORDER BY year DESC, week DESC`, kein
`created_at`-Bezug — die Editionen KW22–29 wurden am 19.07. nachgeneriert und sortieren trotzdem
nach Kalenderwoche). Der Montags-Cron schreibt die neue Edition, der 06:30-Export vom Dienstag
nimmt sie mit; die älteste fällt heraus und antwortet 404 (kein 410 — das Slug-Muster
`^[a-z0-9-]+-[0-9]+$` greift nur auf Artikel ohne Verzeichnis). Datumsangaben in der
Archivliste sind die ISO-Woche (`24–30 Aug 2026`, reine UTC-Arithmetik aus Jahr/KW — kein
`new Date()`, kein Zeitzonenrisiko).

**Link-Regel** (beim Build entschieden, deterministisch über die Tagesgrenze des Fensters):
Editionstexte tragen Markdown-Links `[Titel](/trends/<slug>)` (Editorial + Vertical-Summaries)
und `trend_refs` (3 je Vertikale). Ein Artikel-Link (Slug endet auf `-<id>`) bleibt **intern**,
wenn der Artikel im Fenster liegt — Prädikat identisch mit `getPublicWindowSlugs`
(`status='published' AND sort_date >= Fensterstart`, `getTrendLinkTargets`), also nie ein Link
auf ein 410. Sonst wird er auf die **Primärquelle** umgebogen (`trend_refs[].source_url` der
Edition, vorhanden seit KW32; davor `trends.source_url`) und als externer Link mit
`rel="noopener noreferrer"` und „· Quelle ↗" gerendert; ohne brauchbare Quelle (`safeHref`)
steht der Titel als **Text ohne Link**. `/trends/mega` und absolute URLs bleiben unverändert.
Stand 03.09. (Fenster ab 04.08.): KW24–31 alle 24 Referenzen je Edition extern, KW32 18 intern /
6 extern, KW33–35 24 intern; 0 Text-only.

**Signup:** `components/newsletter/SignupForm.tsx` postet im Export form-encoded an
`/newsletter/subscribe.php` (Owner-Webroot, `docs/launch/newsletter-doi-php/`): Felder `email`,
`consent` (spiegelt die Checkbox; das Backend verlangt `1`), Honeypot `website` leer; kein
`/api/*`-Aufruf. Erfolg → „—— Subscribed" + Backend-Meldung, Fehler → `role="alert"` mit der
Backend-Meldung, Netz-/JSON-Fehler → „Connection error." (so antwortet auch der Apache-Testcontainer,
der kein PHP hat). Der Origin-Check des PHP akzeptiert nur `catandary.de`.

**Redirect-Ziel:** `unsubscribe.php` antwortet nach dem bestätigten Form-POST mit **303** auf
`$UNSUBSCRIBED_URL = '/trends/newsletter/unsubscribed'` (eine Stelle im PHP; One-Click bleibt
Klartext 200). Reihenfolge beim Ausrollen: erst der Export publiziert, dann das PHP hochladen —
sonst landet die (trotzdem vollzogene) Abmeldung auf einem 404.

**Build-Checks** (`build_public_static.sh`): `trends/newsletter.html`,
`trends/newsletter/unsubscribed.html`, ≥ 1 Editions-Seite, `newsletter_editions` in
`build_info.json`. Grenze: eine **leere** `newsletter_editions`-Tabelle bricht den Build (Next
verweigert eine leere `generateStaticParams`-Liste, wie bei `/analysis/[slug]`) — es gibt keinen
automatischen Fallback; Tabelle prüfen, notfalls `weekly_newsletter_publish.sh` von Hand.

**Test 03.09.** (`:8098`, Container neu gestartet): `/trends/newsletter` 200, `/trends/newsletter/`
301, `/trends/newsletter/2026-w35` und `2026-w24` 200, `2026-w23` und `2026-w5` 404,
`/trends/newsletter/unsubscribed` 200 (+ `/` → 301). Zwei Builds `diff -rq`-leer.

## Statischer Export — Publish (Schritt 8, Stand 2026-09-02)

Der Upload ist ein **Manifest-Delta**, kein Spiegel: `scripts/publish_static_site.py`
vergleicht das lokale `frontend/.export/out.manifest.tsv` (sha256, Größe, Pfad) mit dem
Remote-Manifest `trends/.publish-manifest.tsv`, das nach jedem erfolgreichen Lauf hochgeladen
wird. Ein normaler Tag sind ~500 neue Artikelseiten, die Listing-/Sitemap-Dateien und ~500
Löschungen — kein Hashing auf dem Webspace, kein Listing. Bis der Webspace-Zugang vorliegt,
ist alles gegen `MODE=local` (Ordner) und einen privaten `sshd` auf 127.0.0.1 getestet
(`tests/test_publish_static_site.py`, 75 Tests inkl. SFTP-E2E).

**Was verwaltet wird — und was nie:** `REMOTE_ROOT/trends/**` und `REMOTE_ROOT/_next/**`
(plus `trends/.htaccess`, `_next/.htaccess`, `trends/sitemap.xml`, `trends/index.json`, sofern
der Build sie dort ablegt) **und genau vier Root-Dateien (`trends.html`, `trends.txt`, `robots.txt`, `.well-known/tdmrep.json` — `ROOT_ALLOWLIST`)**, `trends.html` + `trends.txt`
(`ROOT_ALLOWLIST` — Nexts Name für Feed-Seite 1; `/trends.txt` ist der RSC-Payload einer
Client-Navigation nach `/trends`). Sie werden hochgeladen, im Manifest geführt und nur gelöscht,
wenn der Build sie nicht mehr erzeugt; der Webroot wird dafür nie gelistet (`--full` stat()et
die beiden einzeln, rsync überträgt sie als Einzeldatei ohne `--delete`). Der Webroot ist
Owner-verwaltet — `index.html` (Landing), `robots.txt`, `mark.svg`, `favicon.ico`,
`newsletter/**` (PHP-DOI mit DB-Zugang) werden weder geschrieben noch gelöscht; jeder Pfad wird
normalisiert und gegen Teilbäume + Allowlist geprüft (`..`, absolute Pfade, Backslashes →
Abbruch, Exit 2). Alle anderen Root-Dateien des Exports (`404.html`, `imprint.html`,
`analysis.html` …) werden als „outside scope" gezählt und **nicht** hochgeladen — was davon
öffentlich sein muss, hat seine Export-Adresse unter `/trends/…` (Rechtstexte, Anfrage) oder
geht einmalig von Hand mit den Landing-Dateien mit.

**Reihenfolge (kein atomarer Swap auf Shared Hosting, also Reihenfolge = Konsistenz):**
(a) neue/geänderte `_next/**`-Assets → (b) Artikelseiten + RSC-Payloads (`trends/<slug>-<id>.*`)
→ (c) Listing/Index/Sitemap, `.htaccess` zuletzt → (d) Löschen abgelaufener Dateien, dann leere
Verzeichnisse. Jede Datei wird als `<name>.publish-tmp` geschrieben und umbenannt. Alle 2000
Operationen wird das Remote-Manifest als Checkpoint geschrieben; eine Phase läuft nur, wenn die
vorige fehlerfrei war. **Abbruch mittendrin → nächster Lauf macht beim Checkpoint weiter**, kein
Vollupload (getestet: `test_aborted_run_resumes_from_the_checkpoint`).

**Sicherheitsnetze (Exit 2, Schwellen per Flag):** Config-Datei muss existieren und `0600`
sein; `build_info.json` älter als 12 h (`--max-build-age-hours`) → Abbruch; weniger als 1000
Artikel in `build_info` **oder** im Manifest (`--min-articles`) → Abbruch (Leer-Export nach
DB-Fehler); mehr als 60 % der Remote-Dateien würden gelöscht (`--max-delete-pct`) → nur mit
`--force`; 0 verwaltete Dateien im Manifest → Abbruch (Export-Layout verschoben). SFTP läuft mit
1–4 Sessions (`CONNECTIONS`, Default 3 — Hetzner-Shared-Hosting verträgt keine 16).

### Config: `~/.config/catandary/webspace.env` (chmod 600)

```bash
mkdir -p ~/.config/catandary && umask 077 && cat > ~/.config/catandary/webspace.env <<'CFG'
MODE=sftp                  # sftp | rsync | local
HOST=wpXXX.webspace-host.de  # aus konsoleH → Zugänge (SFTP)
PORT=22
USER=login
PASSWORD='geheim#123'      # oder KEY_FILE=~/.ssh/id_ed25519 (falls das Paket SSH-Keys erlaubt)
REMOTE_ROOT=/public_html   # Docroot laut EINBAU.md: /usr/www/users/<login>/ — prüfen!
CONNECTIONS=3
HOST_KEY_POLICY=strict     # beim allerersten Lauf accept-new, danach strict
KNOWN_HOSTS=~/.ssh/known_hosts
# optional, vom Cron-Wrapper an den Build durchgereicht:
PUBLIC_NOINDEX=1           # zum Launch 01.10. auf 0
# PUBLIC_WINDOW_DAYS=30
CFG
chmod 600 ~/.config/catandary/webspace.env
```

`MODE=rsync` (nur wenn das Paket SSH hat — Owner-Klärung): `rsync -rlt --delete
--delay-updates` je Teilbaum (`_next/` zuerst, dann `trends/`), Owner-Dateien sind durch die
Teilbaum-Ziele ausgeschlossen, das Manifest wird danach mitgeschrieben (Wechsel zu SFTP ohne
Vollupload möglich). `MODE=local` + `LOCAL_DEST=/pfad` = Vorschau/Test in einen Ordner.

### Erster SFTP-Dry-Run (Owner)

```bash
cd /home/dirk/projects/catandary-trends
scripts/build_public_static.sh                                 # frischer Export (< 12 h)
.venv/bin/python scripts/publish_static_site.py                # Dry-Run ist Default
#   → verbindet sich, liest trends/.publish-manifest.tsv (fehlt beim ersten Mal → alles „new"),
#     druckt je Phase Dateizahl + MB, schreibt NICHTS. Bei HOST_KEY_POLICY=accept-new wird der
#     Host-Key in KNOWN_HOSTS gespeichert; danach auf strict stellen.
.venv/bin/python scripts/publish_static_site.py --apply        # Erstupload (Stunden bei ~30k Dateien über SFTP)
.venv/bin/python scripts/publish_static_site.py --apply --full # nur falls trends/ oder _next/ dort schon Dateien hatten
```

Danach die `.htaccess`-Checks aus `frontend/public-export/trends/.htaccess` (Kommentarblock am
Ende) abarbeiten. `--full` ist der Reparaturmodus: Remote-**Listing** (Pfad + Größe) statt Manifest
ist die Wahrheit — Fremddateien in den Teilbäumen werden entfernt, größengleiche Dateien ohne
bekannten Hash gelten als unverändert.

### Betrieb

| Was | Wo |
|---|---|
| Cron-Wrapper | `scripts/publish_static_site.sh`: Lock, Kollisionswächter (wartet bis 90 min auf einen laufenden Full Cycle), `build_public_static.sh`, dann `--apply`. Ohne `webspace.env`: stiller Skip (Exit 0). Reicht `PUBLIC_NOINDEX`/`PUBLIC_WINDOW_DAYS`/`PUBLIC_SITE_URL` aus der Config an den Build durch |
| Cron-Zeile | `15 3 * * *` in `deploy/crontab.txt` — täglich, auch Sa/So (das 30-Tage-Fenster rollt ohne Cycle weiter). **Noch nicht in der echten crontab** (Zugang fehlt) |
| Log | `~/logs/catandary-publish-<YYYYMMDD>.log` (Wrapper + Python im selben File) |
| Summary | `data/publish_last.json` (Zeit, Commit, Modus, hoch/gelöscht/unverändert/übersprungen, Dauer, Fehler + Beispiele) — nur bei `--apply` geschrieben |
| Wächter | `scripts/cycle_watchdog.py` (07:45): Summary muss vom Tag sein und `errors == 0`, sonst Mail (fehlt / veraltet / fehlgeschlagen / läuft noch). Schläft, solange `webspace.env` nicht existiert |
| Exit-Codes | 0 ok · 1 Übertragungsfehler (Manifest-Checkpoint steht, erneut starten) · 2 verweigert (Config/Gate/Pfad) |
| Lock | `frontend/.export/.lock` — dieselbe Datei wie der Build: ein Rebuild während des Uploads würde einen gemischten Baum hochladen |

Ein `--apply` bei unverändertem Export ist ein No-op mit Summary (0 hoch, 0 gelöscht) — das
ist der Wochenendfall, wenn kein Artikel das Fenster verlässt.

**Dry-Run gegen den realen Export (02.09. 23:12, Build 23:08 nach Wegfall der
Segment-Payloads, MODE=local, leeres Ziel):** 30.595 verwaltete Dateien / 964 MB — Assets 73
(1,4 MB), Artikel 30.458 (954 MB), Listing 64 (8,8 MB), 0 Löschungen, 20 Root-Dateien
außerhalb des Scopes; Planung < 1 s. (Vor dem Build-Schritt 2b waren es 137.457 Dateien /
1.616 MB.) **Mit statischem Listing + Root-Allowlist (03.09. 05:15):** 32.320 verwaltete
Dateien / 1.258 MB — Listing jetzt 2.554 Dateien / 327 MB (die 1.231 Feed-/Vertical-Seiten
wandern täglich komplett mit), 15 Root-Dateien außerhalb des Scopes.

## Notes
- **Countdown:** targets `2026-10-01T09:00:00+02:00` (09:00 CEST), computed against the
  visitor's clock as an absolute instant. At zero it flips to "We are live" — which is why
  the file must be re-uploaded *before* the date if the launch moves again (on 2026-09-01 the
  old 01.09. target expired on the live site while the repo already said 01.10.). To change
  the date, edit **both** the `<span class="cd-date">` text and the
  `new Date("2026-10-01T09:00:00+02:00")` line in `preview.html`.
- **Still in the page and still open (#93):** the €99/499/799 tier table and the
  "Explore the live engine" CTA reflect the withdrawn SaaS model — the "analyses instead of
  platform" rewrite is the owner's voice and not done yet.
- **Before the real public launch:** remove the `noindex` meta and upload the static export
  next to it (no DNS change — same webspace; `HOSTING_PUBLIC_VPS.md` is archived).


### Methodik-Statistik als Snapshot (seit 2026-09-05)

Der erste Produktions-Export starb auf `/trends/methodology`: die Live-Aggregate der Seite
(COUNT über `trends`, Join `trends×raw_entries×sources`, MIN/MAX über 21 M `raw_entries`) liefen
unter sechs Build-Workern in den 20-s-`statement_timeout`. Der Build rechnet die Zahlen jetzt
einmal vorab (`scripts/methodology_stats.py` → `frontend/.export/methodology_stats.json`, ~1–2 min,
ohne Timeout) und reicht die Datei per `METHODOLOGY_STATS_FILE` an `next build`;
`getMethodologyStats()` liest sie, wenn die Variable gesetzt ist. Die lokale Owner-Instanz nutzt
weiter die Live-Abfragen mit 1-h-Cache. Nebeneffekt: der Export ist auch hier deterministisch.

## TDM-Vorbehalt + KI-Crawler-Sperre (Owner-Entscheid 2026-09-03)

catandary.de erklärt einen **maschinenlesbaren Nutzungsvorbehalt für Text-und-Data-Mining**
(§44b Abs. 3 UrhG / Art. 4 Abs. 3 DSM-RL) und sperrt bekannte KI-Crawler. Suchmaschinen und
Link-Vorschauen bleiben erlaubt — die Seite ist ein Lead-Gen-Schaufenster.

| Signal | Wo | Quelle |
|---|---|---|
| `TDM-Reservation: 1` (HTTP-Header) | `/trends/**`, `/_next/**` | `frontend/public-export/{trends,_next}/.htaccess` |
| `<meta name="tdm-reservation" content="1">`, `tdm-policy`, `robots: noai, noimageai` | jede exportierte Seite | `frontend/src/app/layout.tsx` (`metadata.other`) |
| `/.well-known/tdmrep.json` (TDMRep) | Webroot | `scripts/build_public_static.sh`, hochgeladen über `ROOT_ALLOWLIST` |
| Klartext-Policy | `/trends/tdm-policy` | `frontend/src/app/trends/tdm-policy/page.tsx` |
| `robots.txt`: KI-Crawler `Disallow: /` | Webroot (**ersetzt die handgeschriebene Datei**) | `frontend/src/app/robots.ts` ← `frontend/src/lib/aiCrawlers.ts` |
| 403 per User-Agent | `/trends/**`, `/_next/**` | `.htaccess`-RewriteCond, Liste = `aiCrawlers.ts` (Vitest hält beides synchron) |

**Owner-Aktion (einmalig):** Die Root-`.htaccess` des Webspace ist owner-verwaltet. Damit Landing,
`/newsletter/` und die Root-Dateien dieselben Regeln tragen, den Inhalt von
`docs/launch/root-htaccess.snippet` dort einfügen. Prüfen nach dem Upload:

```bash
curl -sI https://catandary.de/trends/ | grep -i tdm-reservation      # → 1
curl -s  https://catandary.de/.well-known/tdmrep.json               # → JSON
curl -sI -A "GPTBot/1.0" https://catandary.de/trends/               # → 403
curl -sI -A "Googlebot/2.1" https://catandary.de/trends/            # → 200
curl -s  https://catandary.de/robots.txt | head -20                  # → User-agent: GPTBot … Disallow: /
```

`MODE=rsync` braucht auf dem Webspace rsync ≥ 3.2.3 (`--mkpath` für `.well-known/`); SFTP/local legen das Verzeichnis selbst an.

Liste pflegen: nur in `frontend/src/lib/aiCrawlers.ts` ergänzen, dann die Regex in beiden
`.htaccess`-Dateien und in `root-htaccess.snippet` nachziehen (`npx vitest run aiCrawlers` schlägt
sonst fehl). `robots.txt` und `tdmrep.json` entstehen beim Build.
