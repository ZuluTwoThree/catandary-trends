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

## Statischer Export — Build (Schritte 1–3 + 7 des Designs, Stand 2026-09-02)

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
Export ist es ein No-op). Die vier Metadata-Routen (`sitemap.ts`, `robots.ts`, `icon.tsx`,
`opengraph-image.tsx`) sind jetzt `force-static` (Export-Pflicht) — die Workstation-Sitemap
wird dadurch beim Build gerendert, nicht mehr pro Request. Der Export-Modus unterdrückt
`/api/track` (Artikel) und die `/api/newsletter`-Fetches (Signup postet stattdessen
form-encoded an `/newsletter/subscribe.php` mit Consent-Checkbox; Editions-Archiv folgt in
Schritt 6). `/trends` rendert im Export vorerst nur die Default-Ansicht (Seite 1, keine
Filter) — statische Listing-Routen sind Schritt 4/5.

**Ausgabe-Layout** (`trailingSlash: false`): `/trends/<slug>.html` + `<slug>.txt` (RSC) +
`<slug>/__next.*.txt` (Segment-Prefetch, 7 Dateien, kein Schalter in Next 16.2) — daher die
`.htaccess`-Regeln unten.

**Messwerte (voller 30-Tage-Export, 2026-09-02 22:45, 16 Kerne, Postgres über Socket):**
15.229 Artikel + 28 Mega-Seiten + 10 statische Seiten → **137.512 Dateien, 1.545 MB**
(`du`: 1,9 GB); `next build` **35 s** (Prerender 6 Worker), Skript gesamt **41 s** inkl.
Verifikation, Manifest und Kopie; RSS-Spitze 1,46 GB. Die Spike-Hochrechnung „~10 min" galt
für die damalige Related-Implementierung (drei sequentielle Slug-Nachladungen pro Seite) — mit
`getRelatedPredecessors` (eine Query) rendert der Export ~440 Seiten/s. Zwei direkt
aufeinanderfolgende Läufe: `diff -rq` leer. Sitemap 15.266 URLs (< 50k-Limit). Bekannte
Restfunde im HTML: `/trends/foresight` und `/trends/pricing` nur in der Landing (`index.html`,
Copy #93 Etappe 4); `/api/` nur als Teil externer Quell-URLs (z. B.
`developers.openai.com/api/docs/pricing`); in den JS-Chunks stehen `/api/track` und
`/api/newsletter` als tote Nicht-Export-Zweige, die zur Laufzeit nicht aufgerufen werden.

Aufräumen zwischen den Läufen ist nicht nötig (das Skript baut die Staging-Kopie mit
`rsync --delete` neu und löscht `.next`/`out` darin vor jedem Build); ein Ausgabeverzeichnis
mit 137k Dateien lässt sich mit `rm -rf` in ~10 s entfernen.

### `.htaccess` (frontend/public-export/.htaccess)

Wird ins Export-Root kopiert. Enthält: `Options -Indexes`, `DirectorySlash Off` (sonst
301 auf `/trends/<slug>/`, weil das Segment-Verzeichnis gleichen Namens existiert), Rewrite
`/pfad` → `/pfad.html` wenn die Datei existiert, `/pfad/` → 301 `/pfad`, musterbasiertes
**410** für `^/trends/[a-z0-9-]+-[0-9]+$` ohne Datei (abgelaufene Artikel; alle 15.266
Slugs im Fenster tragen die numerische Id — geprüft 02.09.) mit
`ErrorDocument 410 /trends/expired.html`, `ErrorDocument 404 /404.html`, 301 für
`/trends/vertical/<v>` → `/trends`, `ForceType image/png` für `opengraph-image`/`icon`,
Security-Header (Spiegel von `next.config.ts`), Cache-Control (`_next/static` immutable 1 Jahr,
HTML/TXT/XML `no-cache`), mod_deflate. `.txt`-RSC-Payloads bleiben `text/plain` — Nexts
Router akzeptiert das im Export-Modus.

**Lokal gibt es keinen Apache** — der Testplan steht als Kommentarblock am Ende der
`.htaccess` (curl-Checks für 200/301/410/404/Content-Type/Cache-Header + ein Browser-Test der
Client-Navigation). Beim ersten Upload abarbeiten; schlägt eine Regel mit 500 fehl, ist
`AllowOverride` auf dem Webspace zu eng (`Options -Indexes` zuerst entfernen, dann
`DirectorySlash`).

## Statischer Export — Publish (Schritt 8, Stand 2026-09-02)

Der Upload ist ein **Manifest-Delta**, kein Spiegel: `scripts/publish_static_site.py`
vergleicht das lokale `frontend/.export/out.manifest.tsv` (sha256, Größe, Pfad) mit dem
Remote-Manifest `trends/.publish-manifest.tsv`, das nach jedem erfolgreichen Lauf hochgeladen
wird. Ein normaler Tag sind ~500 neue Artikelseiten, die Listing-/Sitemap-Dateien und ~500
Löschungen — kein Hashing auf dem Webspace, kein Listing. Bis der Webspace-Zugang vorliegt,
ist alles gegen `MODE=local` (Ordner) und einen privaten `sshd` auf 127.0.0.1 getestet
(`tests/test_publish_static_site.py`, 65 Tests inkl. SFTP-E2E).

**Was verwaltet wird — und was nie:** nur `REMOTE_ROOT/trends/**` und `REMOTE_ROOT/_next/**`
(plus `trends/.htaccess`, `_next/.htaccess`, `trends/sitemap.xml`, `trends/index.json`, sofern
der Build sie dort ablegt). Der Webroot ist Owner-verwaltet — `index.html` (Landing),
`robots.txt`, `mark.svg`, `favicon.ico`, `newsletter/**` (PHP-DOI mit DB-Zugang) werden weder
geschrieben noch gelöscht; jeder Pfad wird normalisiert und gegen die Teilbäume geprüft
(`..`, absolute Pfade, Backslashes → Abbruch, Exit 2). Root-Dateien des Exports
(`404.html`, `trends.html`, `sitemap.xml`, `imprint.html` …) werden als „outside scope"
gezählt und **nicht** hochgeladen — sie müssen entweder vom Build unter `trends/` landen
(`/trends` → `trends/index.html`) oder einmalig von Hand mit den Landing-Dateien mitgehen.

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

Danach die `.htaccess`-Checks aus `frontend/public-export/.htaccess` (Kommentarblock am Ende)
abarbeiten. `--full` ist der Reparaturmodus: Remote-**Listing** (Pfad + Größe) statt Manifest
ist die Wahrheit — Fremddateien in den Teilbäumen werden entfernt, größengleiche Dateien ohne
bekannten Hash gelten als unverändert.

### Betrieb

| Was | Wo |
|---|---|
| Cron-Wrapper | `scripts/publish_static_site.sh`: Lock, Kollisionswächter (wartet bis 90 min auf einen laufenden Full Cycle), `build_public_static.sh`, dann `--apply`. Ohne `webspace.env`: stiller Skip (Exit 0). Reicht `PUBLIC_NOINDEX`/`PUBLIC_WINDOW_DAYS`/`PUBLIC_SITE_URL` aus der Config an den Build durch |
| Cron-Zeile | `30 6 * * *` in `deploy/crontab.txt` — täglich, auch Sa/So (das 30-Tage-Fenster rollt ohne Cycle weiter). **Noch nicht in der echten crontab** (Zugang fehlt) |
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
außerhalb des Scopes (`index.html`, `404.html`, `trends.html`, `sitemap.xml`, `robots.txt`,
`imprint`/`privacy`/`enquiry`/`analysis` … — s. o.); Planung < 1 s. (Vor dem Build-Schritt 2b
waren es 137.457 Dateien / 1.616 MB.)

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
