# Newsletter Go-Live — Restliste bis zum ersten echten Newsletter (#16)

Stand 2026-09-02. Reihenfolge ist die Abhängigkeitsreihenfolge — von oben nach
unten abarbeiten, nichts überspringen. Alle Owner-Gates sind explizit markiert;
alles andere kann Claude Code vorbereiten, aber NICHT selbst ausführen (kein
Mail-Versand, kein Upload, keine DB-Schreibaktion, siehe Worktree-Regeln).

**Rahmen seit 02.09.2026 (Owner-Entscheid):** die öffentliche Website ist ein
statischer Export auf dem Hetzner-Webhosting. Es gibt keinen VPS, keinen
Reverse-Proxy und keine Next-Server-Routen im Netz. Alles, was schreibt
(Anmeldung, Bestätigung, **Abmeldung**), läuft über das PHP-Paket unter
`/newsletter/` auf demselben Webspace. Die frühere Next-Abmelderoute
`/trends/newsletter/unsubscribe` bleibt nur für die lokale Instanz bestehen und
wird in keiner Mail mehr verlinkt.

Hintergrund/Detailbegründung zu Schritt 1: `EINBAU.md`, Abschnitt „Nächster
Upload". Befunde: `docs/audits/2026-09-02_security_review.md` (X-3),
`docs/audits/2026-09-02_compliance_review.md` (HOCH 1).

---

## 1. PHP-Upload-Paket auf den Webspace (Owner-Gate: SFTP)

Dateien, in dieser Reihenfolge (Details + Warum in EINBAU.md „Nächster Upload"):

| Datei | Status auf dem Webspace | Was sich ändert |
|---|---|---|
| `_lib.php` | live (alte Version) | **überschreiben** — neu: `nl_unsub_token()`/`nl_unsub_verify()`; sonst unverändert, Anmeldung läuft weiter |
| `unsubscribe.php` | **fehlt** | **neu** — Abmeldeseite (GET = Button, POST = Abmeldung) + RFC-8058-One-Click |
| `nl_config.php` | live | **überschreiben** — Block 5 `unsub_secret` NEU befüllen (s. Schritt 3); Blöcke 1–4, 6, 7 aus der Live-Datei 1:1 übernehmen; Block 8 leer lassen; danach Rechte 600 |
| `export.php` | **fehlt** (verifiziert 2026-08-28: HTTP 404) | hochladen — Datei selbst unverändert, liefert `status` + `unsubscribed_at` bereits |

Nicht erneut hochladen (unverändert, live): `subscribe.php`, `confirm.php`,
`cron.php`, `.htaccess`. Kein SQL-Update nötig — `schema.sql` hatte
`status = 'unsubscribed'`, `unsubscribed_at`, `unsubscribe_ip` und das
Log-Ereignis `unsubscribe` von Anfang an.

Danach Schutz prüfen (EINBAU.md Schritt 4): `_lib.php`/`nl_config.php` → 403,
nie Quelltext. Plus: `https://catandary.de/newsletter/unsubscribe.php` ohne
`?t=` → HTTP 400 „Link invalid", ohne Interna.

## 2. `.env` auf der Workstation vervollständigen

Werte in `.env` (Repo-Root; Vorlage und Kommentare in `.env.example`):

- `NEWSLETTER_UNSUB_SECRET=<neu: openssl rand -hex 32>` — **Pflicht**, s. Schritt 3.
- `NEWSLETTER_PUBLIC_BASE=https://catandary.de` — Basis für
  `/newsletter/unsubscribe.php` (Default im Code ist bereits catandary.de;
  setzen schadet nicht). **Unabhängig von `PUBLIC_BASE_URL`**, das weiter
  `http://localhost:3004` sein darf — der Abmeldelink folgt ihm seit
  2026-09-02 nicht mehr.
- `NEWSLETTER_UNSUB_MAILTO=contact@catandary.de` — mailto-Hälfte des
  `List-Unsubscribe`-Headers (Default; die Adresse aus dem Einwilligungstext).
- `NL_EXPORT_URL=https://catandary.de/newsletter/export.php`
- `NL_EXPORT_TOKEN=<export_token aus nl_config.php Block 6>` — exakt derselbe
  Wert wie auf dem Webspace.
- `RESEND_API_KEY` / `NEWSLETTER_FROM` (vorhanden).
- `NL_SYNC_STATE` optional (Default `data/nl_sync_state.json`).

## 3. Secret-Angleich `unsub_secret` ⇄ `NEWSLETTER_UNSUB_SECRET` (Pflicht)

**Warum:** `pipeline/newsletter_sender.py` signiert den Abmeldelink jeder Mail
(HMAC-SHA256 über die Adresse) mit `NEWSLETTER_UNSUB_SECRET` aus der
pipeline-`.env`; `unsubscribe.php` prüft denselben Token mit `unsub_secret`
(Block 5) aus `nl_config.php` auf dem Webspace. Stehen dort zwei
unterschiedliche Werte, ist **jeder** Abmeldelink in **jeder** verschickten Mail
ungültig — kein Bug im Code, sondern ein reiner Konfigurationsabgleich.

1. Einmal erzeugen: `openssl rand -hex 32`.
2. In `nl_config.php` Block 5 eintragen (mittlere Zeile ersetzen) → Upload in
   Schritt 1.
3. Denselben Wert in `.env` (Repo-Root) als `NEWSLETTER_UNSUB_SECRET` eintragen.
4. Gegenprobe ohne Versand: `.venv/bin/python -m pipeline.newsletter_sender
   --latest --dry-run` zeigt einen `sample unsubscribe link` — den im Browser
   öffnen: erscheint die Abmeldeseite mit der Adresse und dem Button, passen
   beide Secrets (nur ansehen, **nicht** klicken, sonst ist die Testadresse
   abgemeldet). „Link invalid" = Secrets weichen ab.

Fail closed auf beiden Seiten: fehlt/kurz/`CHANGE_ME` → der Sender verweigert
selbst den Dry-Run, `unsubscribe.php` lehnt jeden Token ab.

**Keine Secret-Werte in diese oder eine andere Doku schreiben** — nur der
Abgleich-Schritt selbst ist dokumentiert. *(Der frühere `AUTH_SECRET`-Angleich
mit `frontend/.env.local` ist damit für den Newsletter gegenstandslos —
`AUTH_SECRET` signiert nur noch die Session-Cookies der lokalen Instanz.)*

## 4. `sync_subscribers.py` deployen

Liegt aktuell nur unter `docs/launch/newsletter-doi-php/sync_subscribers.py`
(Referenzkopie) — noch nicht unter `scripts/`. Vor der ersten Nutzung (manuell
oder per Cron) nach `scripts/sync_subscribers.py` kopieren. Das Skript ruft
sich selbst als `python -m scripts.sync_subscribers` auf (siehe eigener
Docstring) — das Modul-Präfix setzt voraus, dass die Datei unter `scripts/`
im Repo-Root liegt. Es spiegelt bestätigte **und abgemeldete** Zeilen
(`confirmed = FALSE`, `unsubscribed_at` gesetzt) — der Sender mailt nur an
`confirmed = TRUE AND unsubscribed_at IS NULL`.

## 5. Crons aktivieren (nach Schritt 1–4)

**Webspace (konsoleH, Owner-Gate):** `cron.php` als Cronjob eintragen —
Cronjob-Manager, Interpreter PHP 8.x, Pfad
`/usr/www/users/<ftp-login>/newsletter/cron.php`, alle 15 Minuten. Löscht
unbestätigte Anmeldungen nach Ablauf (die Bestätigungsmail verspricht das —
Art. 5 Abs. 1 lit. e DSGVO), wiederholt fehlgeschlagene Bestätigungsmails,
räumt Throttle/Log/Abgemeldete nach Frist auf. Bisher inaktiv (Compliance-
Review 2026-09-02, HOCH 1) — **vor dem ersten Versand**.

**Workstation:** `deploy/crontab.txt` enthält zwei auskommentierte Einträge
(Newsletter-Generierung+Versand Mo 09:00 über `scripts/newsletter_tonight.sh`,
Subscriber-Sync täglich 08:30 über `scripts/sync_subscribers.py`). Erst
einkommentieren, wenn Schritt 1–4 erledigt sind. Danach: Owner installiert die
neue `crontab.txt` (Claude Code installiert keine Crontabs). Der Sync sollte
**vor** jedem Versand laufen, damit Abmeldungen vom Webspace lokal
angekommen sind.

## 6. Testdurchlauf (vor dem ersten ECHTEN Versand)

Mit der eigenen Adresse, Ende-zu-Ende, in dieser Reihenfolge:

1. **Signup**: `curl -X POST https://catandary.de/newsletter/subscribe.php -d "email=DEINE@ADRESSE.de" -d "consent=1"` (oder über das Formular). Erwartet: `{"ok":true,...}` (siehe EINBAU.md Schritt 5).
2. **DOI-Mail prüfen**: „Please confirm your subscription" muss ankommen (Resend, Absender `trends@send.catandary.de`).
3. **confirm**: Link in der Mail anklicken → Bestätigungsseite → Button klicken. In `phpMyAdmin` prüfen: `nl_subscriber.status = 'confirmed'`.
4. **export.php manuell prüfen**: `curl -H "Authorization: Bearer $NL_EXPORT_TOKEN" "https://catandary.de/newsletter/export.php?since=1970-01-01"` → JSON mit der eigenen Adresse, `status: "confirmed"`, `unsubscribed_at: null`.
5. **sync_subscribers.py laufen lassen** (manuell, `.venv/bin/python -m scripts.sync_subscribers`) → Log meldet `synced 1 rows (0 unsubscribed), watermark=...`. In Postgres prüfen: `SELECT * FROM newsletter_subscribers;` zeigt genau die eigene Adresse, `confirmed = TRUE`, `unsubscribed_at IS NULL`.
6. **Trockenlauf vor dem echten Versand**: `.venv/bin/python -m pipeline.newsletter_generator` (erzeugt/speichert die aktuelle Edition), danach `.venv/bin/python -m pipeline.newsletter_sender --latest --dry-run`. Das Log meldet die Empfängerzahl **und muss genau 1 sein** — `newsletter_sender.py` mailt IMMER an ALLE Zeilen mit `confirmed = TRUE AND unsubscribed_at IS NULL`, es gibt **kein** `--to`/Test-Adress-Flag. Zeigt der Dry-Run mehr als 1 Empfänger, NICHT weiterfahren, sondern erst klären, warum schon andere Zeilen bestätigt sind. Der `sample unsubscribe link` muss auf `https://catandary.de/newsletter/unsubscribe.php?t=…` zeigen; im Browser geöffnet erscheint die Abmeldeseite mit Button (nicht klicken).
7. **Testversand an die eigene Adresse**: erst wenn Schritt 6 exakt 1 Empfänger zeigt: `.venv/bin/python -m pipeline.newsletter_sender --latest` (ohne `--dry-run`). Mail muss ankommen; im Quelltext der Mail: `List-Unsubscribe: <mailto:contact@catandary.de?subject=unsubscribe>, <https://catandary.de/newsletter/unsubscribe.php?t=…>` und `List-Unsubscribe-Post: List-Unsubscribe=One-Click`; im Footer der sichtbare „Unsubscribe"-Link auf dieselbe URL. Gmail zeigt bei korrekten Headern „Abbestellen" neben dem Absender (kann bei neuen Absendern einige Mails dauern).
8. **One-Click (Postfach-Weg) prüfen — ohne Klick, nur simuliert**: `curl -i -X POST -d "List-Unsubscribe=One-Click" "<die unsubscribe.php-URL aus der Mail>"` → `HTTP/1.1 200`, Body `Unsubscribed`. In phpMyAdmin: `status = 'unsubscribed'`, `unsubscribed_at`, `unsubscribe_ip` gesetzt; in `nl_consent_log` ein Ereignis `unsubscribe` mit `detail = 'one-click'`. *(Wer stattdessen den Browser-Weg testen will: Link öffnen → Seite mit Adresse → Button „Unsubscribe" → 303 auf die statische Seite `/trends/newsletter/unsubscribed` („You're unsubscribed", Teil des Website-Exports — muss vor dem PHP-Upload publiziert sein); Log-Detail dann `form`. Ein zweiter Aufruf liefert dieselbe Erfolgsseite ohne zweiten Log-Eintrag — idempotent.)*
9. **Abmeldung kommt lokal an**: `curl … export.php?since=1970-01-01` zeigt jetzt `status: "unsubscribed"` mit `unsubscribed_at`; `.venv/bin/python -m scripts.sync_subscribers` → `synced 1 rows (1 unsubscribed)`; Postgres: `confirmed = FALSE`, `unsubscribed_at` gesetzt; `pipeline.newsletter_sender --latest --dry-run` meldet **0** Empfänger. Erst damit ist bewiesen, dass Abgemeldete nie wieder Empfänger werden.
10. **Testdatensatz aufräumen**: Testadresse aus `nl_subscriber` (MySQL, Webspace) UND `newsletter_subscribers` (Postgres) wieder entfernen, `data/nl_sync_state.json` löschen, damit die erste echte Kohorte sauber startet.

## 7. `NL_TRUSTED_PROXIES` — entfällt (nur bei Reverse-Proxy)

Owner-Entscheid 02.09.2026: statischer Export direkt auf dem Webhosting, kein
VPS, kein Proxy, kein DNS-Umzug — es gibt nichts, dem `nl_client_ip()`
vertrauen müsste. Block 8 in `nl_config.php` bleibt leer. Nur falls je wieder
ein eigener Proxy vor den Webspace kommt: dessen IP dort eintragen, **bevor**
DNS umzieht (Archivnotiz in EINBAU.md), sonst ist ab dem Umzug jeder
Einwilligungsnachweis wertlos.

## 8. Resend-DPA abschließen (Owner-Gate, extern)

Auftragsverarbeitungsvertrag (Art. 28 DSGVO) mit Resend im Resend-Dashboard
abschließen, bevor Adressen von EU-Personen dauerhaft über Resend versendet
werden. Rein rechtlicher/vertraglicher Schritt, nicht technisch — kann nur der
Owner erledigen (siehe auch `HOSTING_PUBLIC_VPS.md`, Owner-Gates-Tabelle).
*(Der Compliance-Review 2026-09-02 merkt an, dass
`docs/legal/newsletter-doi-texte.draft.md` das DPA als mit ToS-Annahme wirksam
beschreibt — Widerspruch zur Doku, zu klären; kein technischer Blocker.)*

## 9. Datenschutzerklärung (Owner-Gate, bereits in EINBAU.md vermerkt)

Newsletter-Abschnitt aus `docs/legal/newsletter-doi-texte.draft.md` in die
Datenschutzerklärung einbauen, bevor die Anmeldung öffentlich sichtbar
beworben wird. Unabhängig vom technischen Go-Live, aber Voraussetzung für den
ersten Versand an echte (nicht nur Owner-Test-)Adressen.

---

## Danach: erst dann ist „erster echter Newsletter" freigegeben

Wenn Schritt 1–6 durchlaufen und grün sind sowie Schritt 8–9 (Owner-Gates)
erledigt sind, kann der erste reguläre Signup-Traffic auf die Anmeldung
gelenkt werden. Schritt 7 ist mit dem Owner-Entscheid vom 02.09. entfallen.
