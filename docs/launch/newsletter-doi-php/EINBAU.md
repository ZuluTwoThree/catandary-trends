# Newsletter-Anmeldung einbauen — Schritt für Schritt

Stand 2026-07-26 (Erstinstallation). Getestet gegen Hetzner Webhosting S (PHP 8.2.32,
cURL vorhanden, Resend erreichbar). **Update 2026-08-28 (#16):** Abschnitt
„Nächster Upload" unten dokumentiert den `NL_TRUSTED_PROXIES`-Patch, der vor dem
VPS-DNS-Umzug (#82/#93) live sein muss, plus den aktuellen Live-Status von
`export.php`. Go-Live-Restliste: `NEWSLETTER_GOLIVE.md`.

**Reihenfolge ist wichtig:** erst der `newsletter/`-Ordner, dann testen, dann die
neue Startseite. Sonst zeigt die Landing einen Verbindungsfehler, weil der
Endpunkt noch fehlt.

---

## Schritt 1 — Datenbank-Tabellen anlegen

konsoleH → **Datenbanken** → bei deiner Datenbank auf **phpMyAdmin**.

Dort oben den Reiter **SQL** wählen, den kompletten Inhalt von `schema.sql`
hineinkopieren, **OK**.

Danach müssen links vier Tabellen stehen:
`nl_subscriber`, `nl_consent_log`, `nl_consent_text`, `nl_throttle`.

---

## Schritt 2 — Zugangsdaten eintragen

`nl_config.php` in einem Texteditor öffnen. Die Datei hat **sieben Ausfüll-Blöcke**,
die alle gleich aussehen:

```php
$DB_PASS = <<<'V'
DBPASS_HIER          ← NUR diese mittlere Zeile ersetzen
V;
```

**Regeln (wichtig, dafür narrensicher):**
- Nur die **mittlere Zeile** jedes Blocks ersetzen — den Wert exakt einfügen,
  wie er ist. **Keine Anführungszeichen ergänzen, nichts escapen.** Sonderzeichen
  wie `'` `"` `\` `$` `!` sind in dieser Schreibweise unschädlich.
- Die Zeilen `<<<'V'` und `V;` **nicht anfassen**.
- Jeder Wert bleibt **allein auf seiner Zeile**.

Die sieben Werte:
1. **DSN**: nur `HOST_HIER` (z. B. `sql123.your-server.de`) und `DBNAME_HIER` ersetzen
2. **DB-Benutzer** (aus konsoleH)
3. **DB-Passwort** (aus konsoleH)
4. **app_secret**: neu erzeugen mit `openssl rand -hex 32`
5. **unsub_secret**: **kein neuer Wert** — exakt das `AUTH_SECRET` aus
   `frontend/.env.local` der Workstation
6. **export_token**: neu erzeugen mit `openssl rand -hex 32`
7. **Resend-Key**: aus dem Resend-Dashboard, beginnt mit `re_`

> Diese Datei enthält Zugangsdaten. Nicht in Git einchecken, nach dem Upload per
> FTP auf Rechte **600** setzen.

---

## Schritt 3 — Dateien hochladen

Per SFTP im Webroot (dort, wo `index.html` liegt) einen Ordner **`newsletter`**
anlegen und hineinladen:

| Datei | Zweck |
|---|---|
| `subscribe.php` | nimmt die Anmeldung an, verschickt die Bestätigungsmail |
| `confirm.php` | Bestätigungsseite (Link aus der Mail) |
| `_lib.php` | gemeinsame Funktionen |
| `nl_config.php` | deine Zugangsdaten |
| `.htaccess` | Schutz — **`.htaccess.example` in `.htaccess` umbenennen!** |

`schema.sql`, `cron.php`, `export.php` und `sync_subscribers.py` brauchst du
jetzt noch nicht — die gehören zu Aufräum-Job und Synchronisation.

---

## Schritt 4 — Schutz prüfen (wichtig!)

Diese zwei Adressen im Browser aufrufen:

```
https://catandary.de/newsletter/nl_config.php
https://catandary.de/newsletter/_lib.php
```

Beide **müssen** „Forbidden" oder eine Fehlerseite zeigen — **niemals** Quelltext
oder eine leere weiße Seite mit Inhalt. Wenn du Quelltext siehst, sofort abbrechen
und mir Bescheid geben: dann greift die `.htaccess` nicht.

---

## Schritt 5 — Anmeldung testen

Mit deiner eigenen Adresse:

```bash
curl -X POST https://catandary.de/newsletter/subscribe.php \
     -d "email=DEINE@ADRESSE.de" -d "consent=1"
```

Erwartete Antwort:
```json
{"ok":true,"message":"Wenn die Adresse gültig ist, haben wir eine Bestätigungs-E-Mail geschickt..."}
```

Dann ins Postfach schauen. Die Mail „Please confirm your subscription" muss
ankommen. Link anklicken → es erscheint eine Seite mit dem Einwilligungstext und
einem Button. **Erst der Klick auf den Button** bestätigt (das ist Absicht, siehe
Kommentar oben in `confirm.php`).

In phpMyAdmin prüfen: In `nl_subscriber` muss deine Adresse jetzt auf
`status = confirmed` stehen, mit ausgefüllten Feldern `confirmed_at` und
`confirm_ip`.

**Testdatensatz danach löschen**, damit die Liste sauber startet.

---

## Schritt 6 — Neue Startseite hochladen

Jetzt erst `index.html`, `mark.svg`, `favicon.ico`, `robots.txt` ins Webroot.
Das Formular auf der Seite zeigt dann nach dem Absenden:

> Almost there — you're about to join the list.
> Please confirm via the link we just emailed you.

---

## Nächster Upload — `NL_TRUSTED_PROXIES`-Patch + `export.php` (#16, Stand 2026-08-28)

**Warum:** Sobald der VPS-Reverse-Proxy aus #82/#93 vor den Webspace geschaltet
wird (DNS-Umzug `catandary.de` → VPS-IP; der VPS reicht `/newsletter/*` an
dieses Hetzner-Webhosting durch), sitzt dort erstmals ein Proxy mit
**öffentlicher** IP davor. `REMOTE_ADDR` wechselt dann von der bisherigen
Varnish-Loopback-IP auf die öffentliche VPS-IP — die alte Heuristik in
`nl_client_ip()` ("XFF nur nehmen, wenn REMOTE_ADDR nicht öffentlich ist")
würde diesen Fall nicht erkennen und für **jede** Anmeldung dieselbe VPS-IP
speichern. Damit wäre `signup_ip`/`confirm_ip`/`unsubscribe_ip`/
`nl_consent_log.ip` als Einwilligungsnachweis (Art. 7 Abs. 1 DSGVO) wertlos,
und das IP-Rate-Limit liefe für alle Besucher in einem einzigen Bucket.
**Dieser Patch muss vor dem DNS-Umzug live sein — nicht erst danach nachziehen.**

**Status `export.php` heute** (`curl -I https://catandary.de/newsletter/export.php`,
geprüft 2026-08-28): **HTTP 404 — liegt noch nicht auf dem Webspace.** Zum
Vergleich: `subscribe.php` antwortet korrekt mit HTTP 405 auf GET (live),
`_lib.php`/`nl_config.php` korrekt mit HTTP 403 (gesperrt). `export.php` muss
vor dem ersten `sync_subscribers.py`-Lauf hochgeladen sein, sonst läuft der
Sync ins Leere.

Reihenfolge für dieses Upload-Paket:

1. **`_lib.php` erneut hochladen** (überschreibt die aktuell laufende Version).
   Enthält jetzt den `NL_TRUSTED_PROXIES`-fähigen `nl_client_ip()`.
   Rückwärtskompatibel: solange `NL_TRUSTED_PROXIES` in `nl_config.php` leer
   bleibt (Default), ist das Verhalten bitidentisch zur bisherigen Version —
   nur die alte Varnish-Heuristik greift, die laufende Hetzner-only-Anmeldung
   bricht durch diesen Upload nicht ab.
2. **`nl_config.php` erneut hochladen** — enthält jetzt den neuen, optionalen
   8. Block `NL_TRUSTED_PROXIES` (leer, s. u.). **Die bestehenden Zugangsdaten
   (Blöcke 1–7) aus der aktuell auf dem Webspace liegenden Datei 1:1
   übernehmen**, nicht neu erzeugen — sonst reißt DB-Zugriff und Unsubscribe-
   Signatur ab. Nach dem Upload wieder per FTP auf Rechte 600 setzen.
3. **`export.php` neu hochladen** (fehlt bisher komplett, s. o.). Zweck: Bridge
   für `sync_subscribers.py` — liefert bestätigte/abgemeldete Adressen an die
   Workstation.
4. **Schutz erneut prüfen** wie in Schritt 4 oben: `_lib.php` und
   `nl_config.php` müssen weiterhin 403/Fehlerseite liefern, niemals Quelltext.
5. **Erst beim eigentlichen VPS-Go-Live** (nicht schon bei diesem Upload): in
   `nl_config.php` den `NL_TRUSTED_PROXIES`-Block auf die öffentliche VPS-IP
   setzen und erneut hochladen. Bis dahin schadet der leere Block nicht — er
   ist der Default und entspricht dem heutigen (Hetzner-only) Verhalten.

**Datei-Liste dieses Pakets:** `_lib.php`, `nl_config.php`, `export.php`.
(`subscribe.php`, `confirm.php`, `cron.php`, `.htaccess` sind bereits live und
durch diese Arbeit unverändert — nicht erneut hochladen, außer bei einem
künftigen Code-Update dieser Dateien.)

Cron-Aktivierung, Secret-Angleich (`NL_EXPORT_URL`/`NL_EXPORT_TOKEN`), erster
Testdurchlauf und Owner-Gates: siehe `NEWSLETTER_GOLIVE.md`.

---

## Später (nicht dringend)

- **`cron.php`** als Cronjob in konsoleH eintragen (täglich): löscht
  unbestätigte Anmeldungen nach 30 Tagen (Art. 5 Abs. 1 lit. e DSGVO) und alte
  Throttle-Einträge. Im S-Paket ist genau ein Cronjob enthalten — der reicht.
- **`export.php` + `sync_subscribers.py`**: holt die bestätigten Adressen auf die
  Workstation in die Postgres-Tabelle `newsletter_subscribers`, aus der
  `newsletter_sender.py` versendet. Upload-Details siehe „Nächster Upload" oben.
- ~~SPF und DMARC für `send.catandary.de` ergänzen~~ — **erledigt.** Verifiziert
  2026-08-28 per `dig`: SPF unter `send.send.catandary.de` (`v=spf1
  include:amazonses.com ~all`), DMARC unter `_dmarc.catandary.de`
  (`p=none; pct=50`), dazu SPF am Root (`catandary.de`: `v=spf1 a mx ~all`).
- **Datenschutzerklärung**: den Newsletter-Abschnitt aus
  `docs/legal/newsletter-doi-texte.draft.md` einbauen, bevor die Anmeldung
  öffentlich live geht.

---

## Wenn etwas klemmt

Fehler landen im PHP-Error-Log (konsoleH → Logs). Die Endpunkte geben aus
Sicherheitsgründen nie Details preis — die stehen nur im Log.

Häufigste Ursachen:
- *„Configuration missing"* → `nl_config.php` liegt nicht neben `_lib.php`
- Keine Mail → Resend-Key falsch, oder Absenderdomain nicht verifiziert
- *„Bitte bestätige die Einwilligung"* → `consent=1` fehlt im Request
