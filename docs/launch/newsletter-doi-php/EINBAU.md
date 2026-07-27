# Newsletter-Anmeldung einbauen — Schritt für Schritt

Stand 2026-07-26. Getestet gegen Hetzner Webhosting S (PHP 8.2.32, cURL vorhanden,
Resend erreichbar).

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

## Später (nicht dringend)

- **`cron.php`** als Cronjob in konsoleH eintragen (täglich): löscht
  unbestätigte Anmeldungen nach 30 Tagen (Art. 5 Abs. 1 lit. e DSGVO) und alte
  Throttle-Einträge. Im S-Paket ist genau ein Cronjob enthalten — der reicht.
- **`export.php` + `sync_subscribers.py`**: holt die bestätigten Adressen auf die
  Workstation in die Postgres-Tabelle `newsletter_subscribers`, aus der
  `newsletter_sender.py` versendet.
- **SPF und DMARC** für `send.catandary.de` ergänzen — aktuell existiert dort nur
  DKIM. Verbessert die Zustellbarkeit der Bestätigungsmails deutlich.
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
