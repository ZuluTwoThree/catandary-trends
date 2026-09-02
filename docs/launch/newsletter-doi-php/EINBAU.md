# Newsletter-Anmeldung einbauen — Schritt für Schritt

Stand 2026-07-26 (Erstinstallation). Getestet gegen Hetzner Webhosting S (PHP 8.2.32,
cURL vorhanden, Resend erreichbar). **Update 2026-09-02 (#16):** Abschnitt
„Nächster Upload" unten beschreibt das Abmelde-Paket (`unsubscribe.php`, RFC 8058
One-Click) — Pflicht vor dem ersten Versand, weil die Website ein statischer
Export ist und die frühere Next-Abmelderoute öffentlich nicht existiert. Der
`NL_TRUSTED_PROXIES`-Patch vom 2026-08-28 ist damit gegenstandslos (kein Proxy
vor dem Webspace) und nur noch als Archivnotiz enthalten. Go-Live-Restliste:
`NEWSLETTER_GOLIVE.md`.

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
5. **unsub_secret**: einmal erzeugen mit `openssl rand -hex 32` und **denselben
   Wert** auf der Workstation in `.env` (Repo-Root) als `NEWSLETTER_UNSUB_SECRET`
   eintragen — die Pipeline signiert damit die Abmeldelinks, `unsubscribe.php`
   prüft sie. *(Bis 2026-09-02 stand hier „AUTH_SECRET aus frontend/.env.local";
   das galt für die Next-Route, die es öffentlich nicht mehr gibt.)*
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
| `unsubscribe.php` | Abmeldeseite (Link am Ende jeder Newsletter-Mail + One-Click-Button des Postfachs) |
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

## Nächster Upload — Abmelde-Paket `unsubscribe.php` (#16, Stand 2026-09-02)

**Warum:** Owner-Entscheid 02.09.2026 — die öffentliche Website wird ein
statischer Export auf diesem Webhosting. Damit gibt es die Next-Route
`/trends/newsletter/unsubscribe` (Abmeldung mit DB-Write) öffentlich nicht mehr.
Bis zu diesem Paket baute `pipeline/newsletter_sender.py` genau diese URL in
jede Mail — jeder Abmeldelink wäre tot gewesen (§ 7 UWG, Art. 7 Abs. 3 / Art. 21
DSGVO: Widerruf muss so einfach sein wie die Einwilligung; Befund X-3 in
`docs/audits/2026-09-02_security_review.md`, HOCH 1 im Compliance-Review).
Der Sender zeigt jetzt auf `https://catandary.de/newsletter/unsubscribe.php?t=…`
und setzt die RFC-8058-Header (`List-Unsubscribe` + `List-Unsubscribe-Post`),
mit denen Gmail/Yahoo/Apple Mail den „Abmelden"-Button im Postfach anbieten.
**Ohne dieses Paket auf dem Webspace darf kein Newsletter verschickt werden.**

**Wie der Link funktioniert:** `?t=<b64url(E-Mail)>.<b64url(HMAC-SHA256)>`,
signiert mit `unsub_secret` (Block 5) = `NEWSLETTER_UNSUB_SECRET` in der
Workstation-`.env`. Kein Ablauf — der Link einer drei Jahre alten Mail muss
noch gelten. **GET zeigt nur eine Seite mit Button** (Mail-Scanner und
Link-Vorschauen rufen jeden Link auf — sie dürfen niemanden abmelden),
**POST meldet ab**. Der One-Click-POST des Postfachs (Body
`List-Unsubscribe=One-Click`) meldet sofort ab und bekommt eine schlichte
200-Textantwort. Bereits abgemeldet / unbekannt → dieselbe Erfolgsantwort.
Jede Abmeldung landet als Ereignis `unsubscribe` (Detail `form` oder
`one-click`) in `nl_consent_log`, der Datensatz bekommt `status = unsubscribed`,
`unsubscribed_at`, `unsubscribe_ip`. Kein Schema-Update nötig — `schema.sql`
hatte Status und Spalten von Anfang an.

Reihenfolge für dieses Upload-Paket:

1. **`_lib.php` erneut hochladen** (überschreibt die laufende Version).
   Enthält jetzt `nl_unsub_token()`/`nl_unsub_verify()`; alles Bisherige ist
   unverändert, die laufende Anmeldung bricht durch den Upload nicht ab.
2. **`unsubscribe.php` neu hochladen** (fehlt bisher komplett).
3. **`nl_config.php` erneut hochladen** — Block 5 (`unsub_secret`) bekommt den
   neuen, mit `openssl rand -hex 32` erzeugten Wert; **derselbe Wert** kommt auf
   der Workstation als `NEWSLETTER_UNSUB_SECRET` in die `.env` (Repo-Root).
   Die übrigen Zugangsdaten (Blöcke 1–4, 6, 7) aus der aktuell auf dem
   Webspace liegenden Datei 1:1 übernehmen, nicht neu erzeugen — sonst reißen
   DB-Zugriff und Export-Token ab. Block 8 (`NL_TRUSTED_PROXIES`) bleibt leer.
   Nach dem Upload wieder per FTP auf Rechte 600 setzen.
4. **`export.php` hochladen**, falls noch nicht geschehen (Stand 2026-08-28:
   HTTP 404, lag noch nicht auf dem Webspace). Die Datei ist durch dieses
   Paket unverändert — sie lieferte `status` (`confirmed`/`unsubscribed`) und
   `unsubscribed_at` schon vorher; `sync_subscribers.py` spiegelt beides nach
   Postgres, und der Sender mailt nur an `confirmed = TRUE AND unsubscribed_at
   IS NULL`. Eine Abmeldung auf dem Webspace ist damit nach dem nächsten
   Sync-Lauf lokal wirksam.
5. **Schutz erneut prüfen** wie in Schritt 4 oben: `_lib.php` und
   `nl_config.php` müssen weiterhin 403/Fehlerseite liefern, niemals Quelltext.
   Zusätzlich: `https://catandary.de/newsletter/unsubscribe.php` ohne `?t=`
   muss HTTP 400 mit „Link invalid" zeigen (kein Stacktrace, keine Interna).
6. **`cron.php` in konsoleH aktivieren** (Cronjob-Manager, Interpreter PHP 8.x,
   Pfad `/usr/www/users/<ftp-login>/newsletter/cron.php`, alle 15 Minuten).
   Ohne ihn werden unbestätigte Anmeldungen nie gelöscht (Art. 5 Abs. 1 lit. e
   DSGVO — die Bestätigungsmail verspricht die Löschung nach 30 Tagen) und
   Abgemeldete nie nach der Aufbewahrungsfrist entfernt. Bisher „später, nicht
   dringend" — seit dem Compliance-Review 2026-09-02 Pflicht vor dem Versand.

**Datei-Liste dieses Pakets:** `_lib.php`, `unsubscribe.php`, `nl_config.php`,
`export.php` (falls noch nicht live). (`subscribe.php`, `confirm.php`,
`cron.php`, `.htaccess` sind bereits live und durch diese Arbeit unverändert —
nicht erneut hochladen.)

**Token-Vektor zum Gegenprüfen** (Secret `unsub-test-secret-0123456789`,
Adresse ` Alice@Example.com `): beide Seiten müssen
`YWxpY2VAZXhhbXBsZS5jb20.PJOENDIrCGd1sSH0sF3nXjKLc6NBV3j04aeaklwoQ7I`
liefern. Python: `tests/test_newsletter_sender.py`. PHP (auf dem Webspace oder
mit lokalem `php`, ohne Config-Datei):

```bash
php -r 'echo rtrim(strtr(base64_encode("alice@example.com"),"+/","-_"),"="), ".",
  rtrim(strtr(base64_encode(hash_hmac("sha256","unsub:alice@example.com",
  "unsub-test-secret-0123456789",true)),"+/","-_"),"="), "\n";'
```

Secret-Angleich (`NEWSLETTER_UNSUB_SECRET`, `NL_EXPORT_URL`/`NL_EXPORT_TOKEN`),
Testdurchlauf inkl. Abmeldung und Owner-Gates: siehe `NEWSLETTER_GOLIVE.md`.

### Archiv: `NL_TRUSTED_PROXIES`-Patch (2026-08-28) — nur bei Reverse-Proxy davor

`_lib.php::nl_client_ip()` kann seit 2026-08-28 einen eigenen Reverse-Proxy
mit öffentlicher IP (damals geplant: VPS aus #82/#93) als vertrauenswürdigen
Hop behandeln, wenn dessen IP in `nl_config.php` Block 8 (`NL_TRUSTED_PROXIES`)
steht. **Stand 2026-09-02 entfällt das:** statischer Export direkt auf diesem
Webhosting, kein VPS, kein DNS-Umzug, kein Proxy. Der Block bleibt leer —
das ist der Default und das laufende Hetzner-only-Verhalten. Sollte je wieder
ein eigener Proxy davorgeschaltet werden, MUSS seine IP dort eingetragen
werden, bevor DNS umzieht — sonst tragen `signup_ip`/`confirm_ip`/
`unsubscribe_ip`/`nl_consent_log.ip` überall dieselbe Proxy-IP und der
Einwilligungsnachweis (Art. 7 Abs. 1 DSGVO) ist wertlos.

---

## Später (nicht dringend)

- ~~**`cron.php`** als Cronjob in konsoleH eintragen~~ — **seit 2026-09-02
  Pflicht vor dem Versand**, siehe „Nächster Upload" Punkt 6. Im S-Paket ist
  genau ein Cronjob enthalten — der reicht.
- **`export.php` + `sync_subscribers.py`**: holt die bestätigten UND die
  abgemeldeten Adressen auf die Workstation in die Postgres-Tabelle
  `newsletter_subscribers`, aus der `newsletter_sender.py` versendet.
  Upload-Details siehe „Nächster Upload" oben.
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
