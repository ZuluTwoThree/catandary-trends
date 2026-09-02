# Security-Review Catandary Trends — Worktree `/home/dirk/projects/ct-dev` (Branch `dev`), 2026-09-02

**Modus:** streng read-only. Verifiziert per Code-Lektüre, `ss`/`ip`/`tailscale status`, lokalen HTTP-Requests an :3001/:3004/:8090, read-only `psql`-SELECTs und `git log`-Historiensuche. Keine Requests an fremde Hosts, keine Schreibvorgänge.
**Nicht verifizierbar (kein sudo):** Host-Firewall (ufw/nft), `pg_hba.conf`, Sichtbarkeit (public/private) des GitHub-Repos.

Schweregrade: KRITISCH / HOCH / MITTEL / NIEDRIG. Pfade sind absolut; Zeilen beziehen sich auf den Stand im Worktree.

---

## 0. Kurzfazit

Der Code ist handwerklich überdurchschnittlich sauber: **kein SQL-Injection-Fund** (alle dynamischen Teile sind Platzhalter oder Whitelist-Konstanten), Stripe-Webhook mit korrekter Signatur- und Timestamp-Prüfung, Magic-Link mit gehashten Einmal-Tokens + Transaktion, PHP-DOI-Strecke mit `random_bytes`, `hash_equals`, Prepared Statements, Rate-Limits und GET/POST-Trennung. Kein `yaml.load` ohne SafeLoader, kein `pickle`, kein `shell=True`, kein `dangerouslySetInnerHTML` außer JSON-LD.

Die realen Probleme liegen **nicht im Code, sondern in der Exposition und im Betriebsmodell**:

1. Die Owner-Instanz :3001 lauscht auf **allen Interfaces** und ist im LAN und Tailnet erreichbar — inklusive der **Review-Queue mit Publish/Reject/Requeue ohne jede Auth** und der **GPU-auslösenden Foresight-APIs**.
2. Ein **echter Firecrawl-API-Key liegt in der Git-Historie** (`.env.example`, 2026-06-18 bis 06-20).
3. **Draft-/Rejected-/Signal-Artikel sind per Slug abrufbar** (kein Status-Filter) — heute lokal harmlos, für Export/Öffentlichkeit ein Blocker.
4. Der **Abmeldelink der Newsletter-Mails zeigt auf die Next-App**, die es beim statischen Hosting öffentlich nicht gibt.

---

## 1. Exposition der lokalen Owner-Instanz

### Ist-Zustand (verifiziert)

```
ss -ltnp:
  *:3001        next-server (main, systemd catandary-frontend)
  *:3004        next-server (dev-Worktree)
  0.0.0.0:8090  llama-server
  127.0.0.1:5432 postgres          <- korrekt nur lokal
Interfaces: 192.168.178.78/24 (LAN), 100.115.179.37 (tailscale0), 172.17.0.1 (docker0), 172.18.0.1 (br-…)
Tailnet: 5 Geräte (Workstation, Windows-PC, 2 iPhones, MacBook)
Docker: Container `understory-understory-1` läuft auf dem Host
```

HTTP-Test `GET /trends/review`:

| Ziel | Ergebnis |
|---|---|
| 127.0.0.1:3001 | **200** |
| 192.168.178.78:3001 (LAN) | **200** |
| 100.115.179.37:3001 (Tailnet) | **200** |
| :3004 (dev, `REVIEW_ENABLED` nicht gesetzt) | 404 |

Ursache: `/home/dirk/projects/catandary-trends/frontend/.env.local` setzt `REVIEW_ENABLED=1`, `AUTH_ENABLED=0`, `PAYWALL_ENABLED=0`; `PUBLIC_MODE` ist ungesetzt.

### Befunde

**E-1 — HOCH — Review-Queue (Publish/Reject/Requeue) ohne Auth aus LAN + Tailnet**
- `frontend/src/lib/review-access.ts:22-24` — `canReview()` gibt `true` zurück, sobald `REVIEW_ENABLED=1` und `AUTH_ENABLED` aus ist.
- `frontend/src/app/trends/review/actions.ts:17-49` — Server Actions `publishAction`/`rejectAction`/`requeueAction` prüfen nur `canReview()`.
- `frontend/src/lib/review.ts:165-191, 218-249` — schreiben `trends.status` und setzen `raw_entries.processed=FALSE` (Requeue → erneute GPU-Generierung im Nachtlauf).
- `deploy/systemd/catandary-frontend.service:12` — `next start -p 3001` ohne `-H 127.0.0.1` → bindet `*`.
- Nexts eingebauter Origin-Check für Server Actions greift (Test: fremder `Origin` → 500, gleicher/kein Origin → durch). Er schützt nur gegen Cross-Site-CSRF aus einem Browser, **nicht** gegen direkte Requests eines Geräts im LAN/Tailnet.
- **Szenario:** Jedes Gerät im Heim-WLAN (Gast, kompromittiertes IoT) oder im Tailnet ruft `POST /trends/review` mit gültiger Action-ID (steht im HTML der Seite) und `id=<draft>` auf → ungeprüfte LLM-Drafts werden „human-reviewed" published bzw. gute Drafts rejected; per Requeue lassen sich beliebig viele GPU-Neugenerierungen für den Nachtlauf einplanen.
- **Fix:** Unit auf `ExecStart=… next start -p 3001 -H 127.0.0.1` (bzw. `Environment=HOSTNAME=127.0.0.1`) umstellen; Zugriff von anderen Geräten dann bewusst per SSH-Tunnel oder Tailscale-Serve. Zusätzlich `REVIEW_ENABLED` nur setzen, wenn Auth aktiv ist, oder `canReview()` an ein Tailscale-/Basic-Auth-Header-Gate binden.

**E-2 — HOCH — GPU-auslösende und rechenintensive APIs ohne Auth/ohne Rate-Limit, über LAN/Tailnet erreichbar**
- `frontend/src/app/api/foresight/query/route.ts:55`, `…/query/evidence/route.ts:59`, `…/tir/route.ts:50` — `execFile(.venv/bin/python, scripts/tech_query.py|tir_for_cpc.py …)`; Timeout 110 s, **kein** `rateLimit`, **kein** Concurrency-Gate (nur `analyze/route.ts:14-19, 88-102` hat beides).
- `frontend/src/lib/entitlement.ts:25-27` — `canAccess()` ist bei `PAYWALL_ENABLED=0` immer `true`.
- `frontend/src/proxy.ts:29-40` — der `PUBLIC_MODE`-Gate blockt diese Pfade, ist aber auf :3001 nicht aktiv.
- **Szenario:** Ein Gerät im LAN feuert parallel 20× `GET /api/foresight/query?q=…` → 20 Python-Prozesse mit Embedding-GPU-Handover; um 04:00 kollidiert das mit `scheduled_cycle.sh` (OOM/Timeout des Nachtlaufs, vgl. den bekannten 20-GB-OOM-Fall aus dem Memory).
- **Fix:** Gleiches Binding-Fix wie E-1 löst die Exposition. Zusätzlich in `query`, `evidence`, `tir` das vorhandene Muster aus `analyze` übernehmen (`rateLimit` + globale `ConcurrencyGate`, 2-3 Zeilen je Route).

**E-3 — MITTEL — Rate-Limiter vertraut `X-Forwarded-For`, obwohl kein Proxy davor steht**
- `frontend/src/lib/rateLimit.ts:114-123` — `clientIp()` nimmt bei `TRUSTED_PROXY_COUNT=1` (Default) den letzten XFF-Eintrag; ohne Caddy davor ist der Header vollständig angreiferkontrolliert.
- **Szenario:** Direktzugriff auf :3001 mit wechselndem `X-Forwarded-For` → alle Per-IP-Limits (`search`, `analyze`, `auth/request`) sind wirkungslos.
- **Fix:** `clientIp()` nur XFF auswerten, wenn die Socket-Peer-Adresse loopback ist (in Next: `request.headers.get("x-real-ip")` ist ohne Proxy ebenfalls fälschbar) — pragmatisch: `TRUSTED_PROXY_COUNT=0` unterstützen und in dieser Konfiguration auf die Verbindungs-IP zurückfallen, oder schlicht das Binding fixen (E-1).

**E-4 — MITTEL — llama-server ohne API-Key auf 0.0.0.0:8090**
- `/home/dirk/llama.cpp/start-gemma4-26b.sh:24` — `--host 0.0.0.0 --port 8090`, kein `--api-key`; `/props` und `/v1/models` antworten ohne Auth (lokal verifiziert). `~/.config/systemd/user/llama-server.service` startet dieses Skript.
- **Szenario:** Jedes LAN-/Tailnet-/Docker-Gerät kann Inferenz auf der 3090 fahren, die GPU während des Nachtlaufs belegen oder per `/slots`-Endpunkt Slots blockieren. (`--slot-save-path` ist nicht gesetzt — kein Dateischreiben möglich.)
- **Fix:** `--host 127.0.0.1` (der Pipeline-Client nutzt laut `pipeline/config.py:22` ohnehin 127.0.0.1); falls Docker-Container Zugriff brauchen: `--host 172.17.0.1` + `--api-key`.

**E-5 — MITTEL — Schreibende API-Routen ohne Token/Origin-Check/Rate-Limit**
- `frontend/src/app/api/newsletter/route.ts:69-101` — `POST` legt jede syntaktisch gültige Adresse in `newsletter_subscribers` an; kein Rate-Limit, kein DOI, kein Origin-Check, keine Längenbegrenzung.
- `frontend/src/app/api/track/route.ts:6-37` — `POST {trend_id, event}` inkrementiert `trend_metrics` ohne Limit; `trend_id` wird nicht typgeprüft (String → pg-Fehler → 500).
- **Szenario:** Listenvermüllung / Engagement-Manipulation („engagement_desc"-Sortierung, `db.ts:1441`) von jedem Gerät im LAN. Der `newsletter_sender.py:72` mailt nur `confirmed = TRUE`, daher kein Spam-Versand — aber die Tabelle wird zur Müllhalde, und `sync_subscribers.py` überschreibt Zeilen per `ON CONFLICT`.
- **Fix:** Beide Routen fallen beim statischen Export weg. Bis dahin: `rateLimitInfo()` (bereits im Repo) einbauen; `trend_id` mit `Number.isInteger` prüfen. Die Next-Newsletter-Route sollte ohnehin abgeschaltet werden, sobald die PHP-DOI-Strecke „System of Record" ist (Doppelpfad ohne Einwilligung).

**E-6 — HOCH (launch-relevant; heute lokal MITTEL) — Draft-/Rejected-/Signal-Artikel per Slug abrufbar**
- `frontend/src/lib/db.ts:110` — `getTrendBySlug`: `WHERE t.slug = $1` **ohne** `status`-Filter.
- `frontend/src/app/trends/[slug]/page.tsx:43-45, 62` — nur `notFound()` bei fehlender Zeile; im `PUBLIC_MODE` nur das 30-Tage-Fenster.
- **Verifiziert:** jüngster `draft`-Slug und ein `rejected`-Slug liefern auf :3001 und :3004 jeweils **200**. DB (read-only): 5.520 drafts, 213 rejected, 1,59 Mio. `signal`-Zeilen, 84.563 published.
- **Szenario:** Slugs sind aus Titeln ableitbar und stehen in Logs/Newsletter-Refs. Auf jeder öffentlichen Instanz (VPS-Plan in `docs/launch/HOSTING_PUBLIC_VPS.md:20` proxyt `localhost:3001`) wären ungeprüfte, vom Grounding-Gate zurückgehaltene oder explizit abgelehnte LLM-Texte abrufbar — inkl. JSON-LD/OG-Metadaten, die Suchmaschinen indexieren.
- **Fix:** `getTrendBySlug` um `AND t.status = 'published'` ergänzen (Review-Seite nutzt eigene Queries, `review.ts:98-104`). Für den Export: Slug-Liste ausschließlich aus `status='published' AND sort_date >= now()-30d` erzeugen.

**E-7 — MITTEL — Abmeldung wird bei GET ausgeführt; HMAC-Secret fail-open**
- `frontend/src/app/trends/newsletter/unsubscribe/page.tsx:22-35` — Seitenaufruf mit `?email&token` führt sofort `UPDATE … unsubscribed_at = NOW()` aus.
- `frontend/src/lib/unsubscribe.ts:9` — `process.env.AUTH_SECRET || ""` → bei fehlender Variable HMAC mit Leerstring, d. h. Tokens sind für jeden berechenbar.
- **Szenario:** Link-Scanner in Firmen-Mailgateways/Outlook-Vorschau rufen jeden Link auf → Abonnenten werden ohne ihr Zutun abgemeldet (genau das Problem, das `confirm.php:8-17` für die Bestätigung korrekt vermeidet). Bei einer Instanz ohne `AUTH_SECRET` (dev-`.env.local` hat 64 Zeichen — aktuell ok) könnte jeder beliebige Adressen abmelden.
- **Fix:** GET zeigt Bestätigungs-Button, POST (Server Action) meldet ab; `unsubscribeToken` bei leerem Secret werfen statt rechnen. Siehe außerdem X-3 (Link zeigt auf die falsche Domain).

**E-8 — NIEDRIG — Keine Security-Header, `X-Powered-By: Next.js`**
- `curl -I :3001/trends`: kein CSP, kein `X-Frame-Options`/`frame-ancestors`, kein HSTS, `X-Powered-By` gesetzt. `frontend/next.config.ts` hat keine `headers()`, `deploy/Caddyfile` setzt keine Header.
- **Fix:** Beim statischen Hosting per `.htaccess` (`Header set X-Frame-Options DENY`, `X-Content-Type-Options nosniff`, `Referrer-Policy strict-origin-when-cross-origin`, CSP ohne `unsafe-inline` soweit Next-Runtime es zulässt); in Next `poweredByHeader: false`.

**E-9 — NIEDRIG — `quality-preview` und Dev-Rest**
- `frontend/src/app/trends/quality-preview/page.tsx:99` — nur `NODE_ENV==="production"` → 404; auf :3004 (dev) offen, liest `public/quality_preview.json`. Unkritisch (Owner-Daten), aber `PUBLIC_MODE` blockt den Pfad bereits.

---

## 2. Frontend-Code

**F-1 — SQL-Injection: kein Fund.**
Alle Query-Bausteine in `frontend/src/lib/db.ts`, `review.ts`, `ventures.ts`, `auth.ts`, `api/track/route.ts` sind entweder `$n`-Platzhalter, `params.length`-Indizes, Modul-Konstanten (`TREND_COLS`, `RC_COLS`, `PATENT_RANK_WEIGHTS`, `CAPPED_DATE`) oder Whitelist-Mappings (`suggestLocal` `db.ts:915-925`, `buildOrderBy` `db.ts:1434-1448`, `track` `column` `route.ts:30`). `auth.ts:165` interpoliert nur die Konstante `TOKEN_TTL_MIN`. `pg.ts` setzt `statement_timeout: 20s` — guter DoS-Schutz.

**F-2 — MITTEL — JSON-LD ohne `<`-Escaping (Stored XSS aus RSS/LLM-Daten, wandert in den Export)**
- `frontend/src/components/JsonLd.tsx:33` — `dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}` mit `title_en`, `summary_en`, `tags` aus der DB. `JSON.stringify` escaped `</script>` nicht.
- **Szenario:** Ein Feed-Titel (oder ein LLM-Output, der den Titel echoed) enthält `</script><script>…` → bricht aus dem `<script type="application/ld+json">` aus. Bei statischem Export ist das dauerhaft im HTML eingebacken.
- **Fix:** `JSON.stringify(jsonLd).replace(/</g, "\\u003c")` (eine Zeile, zwei Stellen: Z. 33 und 56).

**F-3 — NIEDRIG — Unvalidierte URL-Schemata in `href`**
- RSS-Links sind in `pipeline/feed_poller.py:149-150` auf `http/https` gefiltert (gut). Nicht gefiltert: `website`/`homepage` aus GLEIF/Companies-House/Wikidata (`ventures/company/[id]/page.tsx:59,114`, `research/page.tsx:722`), Newsletter-`RichText`-Links (`trends/newsletter/page.tsx:60-73`, `<Link href={match[2]}>` aus generiertem Editionstext) und `lib/markdown.ts:110` (Analysen, owner-authored). React blockt `javascript:`-URLs nach meinem Stand nur mit Warnung (für React 19.2 nicht verifiziert).
- **Fix:** Ein `safeHref()`-Helper (nur `^https?://` oder relative Pfade) an den 5 Stellen; die Ventures-Seiten fallen im Export ohnehin weg.

**F-4 — NIEDRIG — Magic-Link-Basis aus Host-Header**
- `frontend/src/lib/auth.ts:236` + `api/auth/request/route.ts:67` — Fallback `new URL(request.url).origin` (Host-Header-kontrolliert), wenn `PUBLIC_BASE_URL` fehlt. Aktuell gesetzt und `AUTH_ENABLED=0`; Auth ist Rückbau-Kandidat (#93).
- `isSafeInternalPath` (`auth.ts:70-72`) verhindert Open Redirects korrekt (`/`, nicht `//`).

**F-5 — OK — Stripe-Webhook** (`frontend/src/lib/stripe.ts:96-134`): `t`-Toleranz 300 s, alle `v1`-Signaturen, mehrere Secrets, `timingSafeEqual`, rohe Body-Bytes. `.env.local` enthält einen `sk_test_`-Key. Kein Befund.

**F-6 — OK — Session/Token-Handling** (`auth.ts`): HMAC-SHA256-Cookie `httpOnly`/`sameSite=lax`, Fail-closed bei Secret < 16 Zeichen in Production, Tokens `randomBytes(32)`, nur SHA-256-Hash gespeichert, atomarer `UPDATE … RETURNING` in Transaktion. Kein Befund.

**F-7 — OK — Env/Secrets:** keine `NEXT_PUBLIC_*`-Variablen im Code; Secrets nur serverseitig. `.env.local` (664) und `.env` (644) sind durch `/home/dirk` (750) vor anderen lokalen Nutzern geschützt.

**F-8 — NIEDRIG — `GET /api/newsletter` liefert `SELECT *`** (`route.ts:35-40`) aus `newsletter_editions` — gibt alle Spalten ungefiltert aus; heute keine sensiblen Spalten bekannt, aber Spalten-Whitelist wäre robuster.

---

## 3. Secrets im Repo / in der Historie

**S-1 — HOCH — Echter Firecrawl-API-Key in der Git-Historie**
- `git show 4c0b116 -- .env.example` (2026-06-18, „feat: backfill_sources.py …") fügte `FIRECRAWL_API_KEY=fc-e81…` (35 Zeichen, reales Format) hinzu; `3b47ffa` (2026-06-20) ersetzte den Wert durch leer. Der Key bleibt in allen Klonen und auf `origin` (`git@github.com:ZuluTwoThree/catandary-trends.git`) abrufbar.
- Repo-Sichtbarkeit nicht geprüft (kein Netz). Bei öffentlichem Repo: KRITISCH.
- **Fix:** Key im Firecrawl-Dashboard **rotieren/widerrufen** (einzige wirksame Maßnahme; History-Rewrite ist optional und ändert an bereits gezogenen Klonen nichts). Danach `git log -p -S'fc-' --all` als Nachweis.

**S-2 — OK — Sonst keine Secrets**
- HEAD: `git grep` auf `sk_live|sk_test|re_…|whsec_|AKIA|ghp_|BEGIN PRIVATE` ohne Treffer.
- Historie: `-S sk_live_`, `-G whsec_…`, `-G re_[A-Za-z0-9]{30,}` ohne Treffer; alle `KEY=`-Zeilen in `.env.example` außer S-1 sind leer/Platzhalter. `DATABASE_URL` nur als `user:pass@`-Platzhalter (`f79dff6`, auskommentiert).
- Nie committed: `.env`, `.env.local` (nur `.env.example` je hinzugefügt); `docs/launch/newsletter-doi-php/nl_config.php` enthielt in der Historie nur `CHANGE_ME_…`/`DBPASS_HIER`.
- `.gitignore` deckt `.env*` (mit `!.env.example`), `frontend/.env*`, `models/`, `data/`, `*.log`, `public/quality_preview.json` ab.

---

## 4. Pipeline / Skripte / Betrieb

**P-1 — OK — Gefährliche Primitive:** kein `yaml.load` ohne SafeLoader, kein `pickle`/`marshal`/`eval`/`exec`, kein `shell=True`/`os.system`; `gpu_handover.py:95` nutzt `subprocess.run(cmd_list)`; f-String-SQL in `db.py:482-626,1199`, `foresight_snapshot.py:140-163`, `reclassify.py:176`, `newsletter_sender.py:54` interpoliert nur interne Spaltennamen/Platzhalterketten.

**P-2 — NIEDRIG — Kein Private-IP-Guard beim Volltext-Holen (SSRF-Restrisiko)**
- `pipeline/article_fetcher.py:100-111, 135` und `feed_poller.py:34` — `httpx.Client(follow_redirects=True)` ohne IP-Filter; Ziel-URLs kommen aus RSS-Feeds (Opt-in-Quellen) bzw. Redirects.
- **Szenario:** Ein Feed-Link/Redirect auf `http://127.0.0.1:8090/props` oder `http://172.17.0.1:3800/…` wird abgeholt und landet (≤12.000 Zeichen) in `raw_content`. Begrenzt durch kuratierte Quellen und `robots.txt`-Check; kein Credential-Zugriff möglich (Postgres nicht HTTP).
- **Fix:** In `fetch_fulltext` vor dem Request `ipaddress.ip_address(resolved).is_private/is_loopback/is_link_local` prüfen (auch nach Redirects: `httpx`-Event-Hook), oder Schema+Host-Allowlist auf die Quellen-Domain.

**P-3 — NIEDRIG — Temp-/Log-Dateien:** `scripts/backup_db.py:49` nutzt `tempfile.NamedTemporaryFile` (sicher). `llama-server.service` hängt Logs an `/tmp/llama-server.log` (unrotiert, wächst — bekanntes Memory-Item; Symlink-Race durch `fs.protected_symlinks` + Sticky-`/tmp` praktisch entschärft, Datei besser nach `~/logs/` legen).

**P-4 — OK — Cron/Units/Rechte:** Crontab läuft ausschließlich aus `/home/dirk/projects/catandary-trends` (main-Worktree); Skripte `rwxrwxr-x dirk:dirk`, keine world-writable Dateien im Repo; `XDG_RUNTIME_DIR` gesetzt. `deploy/deploy.sh` referenziert noch `pm2` (stale, kein Sicherheitsproblem).

**P-5 — INFO — Docker:** Container `understory-understory-1` (0.0.0.0:3800) läuft auf dem Host und erreicht :3001/:8090 über `docker0`. Solange E-1/E-4 offen sind, ist die Docker-Bridge ein weiterer Zugangsweg.

---

## 5. PHP-Double-Opt-in (`docs/launch/newsletter-doi-php/`, live auf catandary.de)

Gesamturteil: **solide**. Konkret geprüft:

| Aspekt | Befund |
|---|---|
| Token | `_lib.php:169-174`: Selector 8 Byte + Verifier 32 Byte aus `random_bytes`, nur `sha256(verifier)` gespeichert; `confirm.php:28-33` Formatprüfung vor DB-Zugriff; `hash_equals` immer ausgeführt (Z. 51-53). |
| DOI-Semantik | GET zeigt Button, POST bestätigt (`confirm.php:71-99`) — korrekt gegen Link-Scanner. |
| SQL | Durchgehend PDO-Prepared-Statements, `EMULATE_PREPARES=false`. |
| Rate-Limit | global 100/h, IP 3/h + 10/d, Adresse 2/d + 5 total, Confirm 30/h/IP; Buckets als HMAC (`_lib.php:149-166`). |
| Header-Injection | `nl_valid_email` (`_lib.php:176-186`) verwirft `\r\n`; Versand als JSON an Resend-API (kein `mail()`), `to` ist ein Array. |
| CSRF | cookieless; Origin/Referer-Check gegen `site_host` (`subscribe.php:17-23`); Honeypot; serverseitige Consent-Pflicht. |
| XSS | Alle Ausgaben `htmlspecialchars(..., ENT_QUOTES)`; CSP `default-src 'none'`, `Referrer-Policy: no-referrer`, `noindex` (`_lib.php:271-275`). |
| Secrets/Datenort | `nl_config.php` gibt nur ein Array zurück; `.htaccess.example:17-38` sperrt `nl_config|_*|cron`, `.sql/.py/.md` und Editor-Backups. `cron.php:9` nur CLI. Speicher ist MySQL, nicht Dateien im Webroot. |
| Fehlerausgaben | `error_log` serverseitig, Client bekommt neutrale Meldungen (`subscribe.php:145-149`, `confirm.php:110-115`). |

Restbefunde:

**N-1 — NIEDRIG — Brute-Force-Bremse in `export.php` wirkungslos** (`export.php:14-23`): der Throttle-Treffer nach Fehlversuch (Z. 16) wird nie ausgewertet — die 429-Prüfung (Z. 20) erreicht nur Anfragen mit gültigem Token. Bei 64-Hex-Token praktisch irrelevant; Fix: Zähler vor dem `hash_equals` prüfen und bei >60 sofort 429.

**N-2 — NIEDRIG — Ungedrosselte DNS-Lookups** (`subscribe.php:51` ruft `nl_valid_email` → `checkdnsrr` **vor** den Throttles in Z. 69-72): pro Request zwei DNS-Anfragen auf eine angreiferkontrollierte Domain (Slow-DNS-Amplifikation). Fix: Reihenfolge tauschen (Throttle zuerst).

**N-3 — NIEDRIG — Globale Notbremse als Verfügbarkeits-Hebel** (`nl_config.php:118`, `lim_global_hour=100`): ein Bot mit 100 Requests/h schaltet alle echten Anmeldungen still ab (neutrale Antwort, keine Mail). Bewusster Trade-off gegen Mail-Bombing; ggf. auf 300 anheben und per Log-Alarm überwachen.

**N-4 — OK — `.htaccess` muss aktiv sein:** Schutz hängt an der Umbenennung von `.htaccess.example` (EINBAU.md:71). Nicht verifizierbar von hier — ein `curl https://catandary.de/newsletter/schema.sql` (Owner) sollte 403 liefern.

---

## 6. Was der statische Export ändert

### Fällt weg (Risiken verschwinden, weil kein Node-Prozess mehr öffentlich läuft)
- Alle `/api/*`-Routen und Server Actions: E-2, E-3, E-5, F-4, F-5, F-6, Rate-Limit- und Concurrency-Themen, Session-Cookies, Magic-Link, Stripe.
- SQL-Layer (`pg.ts`/`db.ts`) und `statement_timeout`-Themen — kein DB-Zugriff aus dem Web.
- Review-Queue (E-1) und Foresight-Seiten — sofern sie nicht mit exportiert werden (siehe Prozess).

### Bleibt / wird neu
- **PHP-DOI** (Abschnitt 5) bleibt die einzige serverseitige Fläche → N-1…N-3 + `.htaccess`-Nachweis.
- **X-1 — In HTML eingebackene Injektionen:** F-2 (JSON-LD) und F-3 (href-Schemata) sind nach dem Export **permanent** und werden nicht mehr durch React-Runtime-Verhalten abgefangen. F-2 vor dem ersten Export fixen.
- **X-2 — Clientseitige Suche über JSON (falls gebaut):** Die JSON-Datei ist öffentlich und vollständig herunterladbar. Sie darf ausschließlich `status='published'` + 30-Tage-Fenster enthalten und keine der Felder, die `api/trends/route.ts:10-24` heute schon strippt (`auto_published`, `raw_entry_id`, `status`, `confidence`, Embeddings, `raw_content`). Größe/Bandbreite (83 MB laut #93) auf dem Shared-Hosting einplanen.
- **X-3 — HOCH (launch-blockierend) — Abmeldelink zeigt auf die Next-App:** `pipeline/newsletter_sender.py:63-65` baut `{PUBLIC_BASE_URL}/trends/newsletter/unsubscribe?email&token`; `PUBLIC_BASE_URL` ist in der Pipeline-`.env` `http://localhost:3004`, Default `https://catandary.de`. Beim statischen Hosting existiert `/trends/newsletter/unsubscribe` öffentlich nicht → jede versendete Mail hätte einen toten Abmeldelink (UWG §7/DSGVO Art. 21 — Widerruf muss so einfach sein wie die Erteilung). `NEWSLETTER_GOLIVE.md:44-57` beschreibt noch den Next-Pfad. **Fix:** `unsubscribe.php` neben `confirm.php` (HMAC mit `unsub_secret`, GET = Button, POST = `status="unsubscribed"`, Log-Eintrag), `unsubscribe_url()` darauf zeigen lassen, `List-Unsubscribe`-Header mitziehen; GOLIVE-Doku anpassen.
- **X-4 — Tracking:** `/api/track` gibt es nicht mehr; entweder auf Server-Logs/Matomo o. ä. umstellen oder den `fetch("/api/track")`-Client-Code beim Export entfernen (sonst 404-Rauschen).
- **X-5 — Header:** CSP/`X-Frame-Options`/HSTS/`Referrer-Policy` müssen per `.htaccess` gesetzt werden (E-8); `Cache-Control` für `_next/static` ebenfalls.
- **X-6 — Landing (`docs/launch/preview.html`):** keine externen Skripte/iframes, Formular postet relativ auf `/newsletter/subscribe.php` (Z. 710, 1126, 1174) — sauber. `robots.txt` erlaubt alles → sicherstellen, dass beim Export keine `/trends/review`-, `/trends/foresight`-, `/account`-Seiten mitkommen (sonst indexiert).

### Was der Export-Prozess selbst beachten muss (Checkliste)
1. **Slug-Enumeration nur aus `status='published' AND sort_date >= now()-30d`** (E-6); `getTrendBySlug` zusätzlich mit Status-Filter härten, damit ein versehentlicher Full-Crawl nichts anderes rendern kann.
2. `PUBLIC_MODE=1` und `NEXT_DIST_DIR` beim Build setzen (`next.config.ts:9`), damit Foresight/Account/Review/Pricing nicht im Output landen; Ergebnis mit `find out/ -path '*foresight*' -o -path '*review*' -o -path '*account*'` gegenprüfen.
3. Keine `.env*`, `quality_preview.json`, `content/analyses/*` mit `draft: true` (`lib/analyses.ts` filtert, `generateStaticParams` in `analysis/[slug]/page.tsx:17` gegenprüfen), keine Source-Maps im Output.
4. `sitemap.ts`/`robots.ts` neu generieren: `sitemap.ts:35-85` listet heute Foresight-URLs — im Export entfernen.
5. F-2-Fix vor dem ersten Export; F-3-Helper an den verbleibenden Stellen (`TrendArticle.tsx:227/238`, Newsletter-`RichText`).
6. `PUBLIC_BASE_URL=https://catandary.de` für Pipeline **und** Frontend-Build (Newsletter-Links, OG-URLs, `JsonLd.tsx:24`).
7. Nach dem Upload: `curl -I` auf `/newsletter/schema.sql` (403), `/newsletter/nl_config.php` (403/leer), eine `/trends/<draft-slug>` (404), Header-Check.

---

## 7. Übersicht

| # | Schwere | Fundstelle | Kurz |
|---|---|---|---|
| E-1 | HOCH | `deploy/systemd/catandary-frontend.service:12`, `frontend/src/lib/review-access.ts:22-24`, `frontend/src/app/trends/review/actions.ts:17-49` | :3001 auf `*`, Review-Writes ohne Auth aus LAN/Tailnet (verifiziert 200) |
| E-2 | HOCH | `frontend/src/app/api/foresight/query/route.ts:55`, `query/evidence/route.ts:59`, `tir/route.ts:50`, `lib/entitlement.ts:25-27` | GPU-Jobs ohne Auth/Rate-Limit über LAN/Tailnet |
| S-1 | HOCH | Git-Historie `4c0b116` (`.env.example`) | Echter Firecrawl-Key committed, nur „geleert", nicht rotiert |
| E-6 | HOCH (launch) / MITTEL (lokal) | `frontend/src/lib/db.ts:110`, `frontend/src/app/trends/[slug]/page.tsx:43-45` | Draft/Rejected/Signal per Slug abrufbar (verifiziert 200) |
| X-3 | HOCH (launch) | `pipeline/newsletter_sender.py:63-65`, `docs/launch/newsletter-doi-php/NEWSLETTER_GOLIVE.md:44-57` | Abmeldelink zeigt auf Next-App, die es öffentlich nicht gibt |
| E-3 | MITTEL | `frontend/src/lib/rateLimit.ts:114-123` | XFF-Vertrauen ohne Proxy → Per-IP-Limits umgehbar |
| E-4 | MITTEL | `/home/dirk/llama.cpp/start-gemma4-26b.sh:24`, `llama-server.service` | llama-server 0.0.0.0:8090 ohne API-Key |
| E-5 | MITTEL | `frontend/src/app/api/newsletter/route.ts:69-101`, `api/track/route.ts:6-37` | Schreibende Routen ohne Limit/Origin-Check |
| E-7 | MITTEL | `frontend/src/app/trends/newsletter/unsubscribe/page.tsx:22-35`, `lib/unsubscribe.ts:9` | Abmeldung bei GET; HMAC fail-open bei leerem Secret |
| F-2 | MITTEL | `frontend/src/components/JsonLd.tsx:33,56` | JSON-LD ohne `<`-Escaping (Stored XSS, im Export permanent) |
| E-8 | NIEDRIG | `frontend/next.config.ts`, `deploy/Caddyfile` | Keine Security-Header, `X-Powered-By` |
| E-9 | NIEDRIG | `frontend/src/app/trends/quality-preview/page.tsx:99` | Nur NODE_ENV-Gate (dev-Instanz) |
| F-3 | NIEDRIG | `TrendArticle.tsx:227/238`, `ventures/company/[id]/page.tsx:59,114`, `newsletter/page.tsx:67`, `lib/markdown.ts:110` | href-Schemata aus Fremddaten ungeprüft |
| F-4 | NIEDRIG | `frontend/src/lib/auth.ts:236`, `api/auth/request/route.ts:67` | Magic-Link-Basis aus Host-Header (Fallback) |
| F-8 | NIEDRIG | `frontend/src/app/api/newsletter/route.ts:35-40` | `SELECT *` ohne Spalten-Whitelist |
| P-2 | NIEDRIG | `pipeline/article_fetcher.py:100-111`, `feed_poller.py:34` | Kein Private-IP-Guard (SSRF-Rest) |
| P-3 | NIEDRIG | `~/.config/systemd/user/llama-server.service` | Log in `/tmp`, unrotiert |
| N-1 | NIEDRIG | `docs/launch/newsletter-doi-php/export.php:14-23` | Fehlversuch-Throttle wirkungslos |
| N-2 | NIEDRIG | `docs/launch/newsletter-doi-php/subscribe.php:51,69` | DNS-Lookups vor Throttle |
| N-3 | NIEDRIG | `docs/launch/newsletter-doi-php/nl_config.php:118` | Globale 100/h-Bremse als DoS-Hebel |

**Zählung:** 0 KRITISCH · 5 HOCH (davon 2 launch-bezogen) · 5 MITTEL · 10 NIEDRIG.

## 8. Die drei Fixes mit bestem Aufwand/Nutzen

1. **Binding auf Loopback** — `deploy/systemd/catandary-frontend.service` und `~/.config/systemd/user/…`: `next start -p 3001 -H 127.0.0.1`; `start-gemma4-26b.sh`/`start-qwen3-8b-208k.sh`: `--host 127.0.0.1`. Eine Zeile je Datei, `systemctl --user daemon-reload && restart`. Erledigt E-1, E-2, E-3, E-4, E-5 auf einen Schlag. Fernzugriff danach per `ssh -L`/`tailscale serve`.
2. **Firecrawl-Key rotieren** (S-1) — 5 Minuten im Anbieter-Dashboard, neuen Wert nur in `.env`.
3. **Status-Filter + JSON-LD-Escape + PHP-Unsubscribe** vor dem Export — `db.ts:110` `AND t.status='published'`; `JsonLd.tsx` `.replace(/</g,"\\u003c")`; `unsubscribe.php` nach dem Muster von `confirm.php` und `newsletter_sender.py:63-65` umhängen. Zusammen ~2 Stunden, entschärft E-6, F-2, X-3 und damit die beiden Launch-Blocker.
