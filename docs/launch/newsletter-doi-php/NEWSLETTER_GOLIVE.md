# Newsletter Go-Live — Restliste bis zum ersten echten Newsletter (#16)

Stand 2026-08-28. Reihenfolge ist die Abhängigkeitsreihenfolge — von oben nach
unten abarbeiten, nichts überspringen. Alle Owner-Gates sind explizit markiert;
alles andere kann Claude Code vorbereiten, aber NICHT selbst ausführen (kein
Mail-Versand, kein Upload, keine DB-Schreibaktion, siehe Worktree-Regeln).

Hintergrund/Detailbegründung zu Schritt 1: `EINBAU.md`, Abschnitt „Nächster
Upload". Hosting-Gesamtplan: `docs/launch/HOSTING_PUBLIC_VPS.md`.

---

## 1. PHP-Upload-Paket auf den Webspace (Owner-Gate: SFTP)

Dateien: `_lib.php`, `nl_config.php`, `export.php` (siehe EINBAU.md „Nächster
Upload" für die genaue Reihenfolge und Warum). Kurzfassung:

- `_lib.php` enthält jetzt `NL_TRUSTED_PROXIES`-fähiges `nl_client_ip()` —
  rückwärtskompatibel, solange der neue Block in `nl_config.php` leer bleibt.
- `nl_config.php`: **bestehende Zugangsdaten (Blöcke 1–7) aus der Live-Datei
  übernehmen**, nicht neu ausfüllen. Der neue optionale 8. Block
  (`NL_TRUSTED_PROXIES`) bleibt vorerst leer — er wird erst in Schritt 7 unten
  befüllt (VPS-Go-Live), nicht schon hier.
- `export.php` fehlt aktuell komplett auf dem Webspace (verifiziert 2026-08-28:
  `curl -I https://catandary.de/newsletter/export.php` → HTTP 404). Ohne sie
  läuft der Subscriber-Sync (Schritt 5) ins Leere.
- Danach Schutz erneut prüfen: `_lib.php` und `nl_config.php` müssen weiterhin
  403/Fehlerseite liefern, nie Quelltext (wie EINBAU.md Schritt 4).

## 2. `.env` auf der Workstation vervollständigen

Drei fehlende Werte (verifiziert 2026-08-28 — aktuell nicht in `.env` gesetzt):

- `NL_EXPORT_URL=https://catandary.de/newsletter/export.php`
- `NL_EXPORT_TOKEN=<export_token aus nl_config.php auf dem Webspace>` — **muss
  exakt derselbe Wert sein** wie Block 6/7 („Export-Token") in der auf dem
  Webspace liegenden `nl_config.php`. Das ist der „Secret-Angleich", auf den
  `deploy/crontab.txt` verweist.
- `NL_SYNC_STATE` optional (Default `data/nl_sync_state.json`, muss nicht
  gesetzt werden).

Zusätzlich prüfen: `PUBLIC_BASE_URL` in `.env` steht aktuell auf
`http://localhost:3004` (Dev-Wert). `pipeline/newsletter_sender.py` baut den
Abmeldelink als `{PUBLIC_BASE_URL}/trends/newsletter/unsubscribe?...` — mit
dem Dev-Wert wäre jeder Abmeldelink in einer echten Mail eine tote
localhost-URL. Vor dem ersten echten Versand (Schritt 8) auf die öffentlich
erreichbare Basis-URL setzen (`https://catandary.de`, sobald die App dort
über den VPS erreichbar ist — sonst zeigt `pipeline/newsletter_sender.py` den
`https://catandary.de`-Default, was ohnehin richtig ist, solange die Zeile in
`.env` entfernt oder korrigiert wird).

## 3. AUTH_SECRET-Angleich zwischen `.env` und `frontend/.env.local` (Pflicht)

**Warum:** `pipeline/newsletter_sender.py` signiert den Ein-Klick-Abmeldelink
mit `AUTH_SECRET` aus der pipeline-`.env` (`unsubscribe_token()`, HMAC-SHA256).
Die Next-App verifiziert denselben Token beim Aufruf von
`/trends/newsletter/unsubscribe` mit `AUTH_SECRET` aus `frontend/.env.local`.
Stehen dort zwei unterschiedliche Werte, ist **jeder** Abmeldelink in **jeder**
verschickten Mail ungültig — kein Bug im Code, sondern ein reiner
Konfigurationsabgleich.

**Status (verifiziert 2026-08-28, nur Hash-Vergleich — keine Klartextwerte
gelesen/dokumentiert):** die beiden `AUTH_SECRET`-Werte sind aktuell
**unterschiedlich**. Vor dem ersten echten Versand beheben:

1. Wert von `AUTH_SECRET` aus `.env` (Repo-Root) nehmen.
2. Denselben Wert in `frontend/.env.local` unter `AUTH_SECRET` eintragen
   (ersetzen, nicht ergänzen).
3. `systemctl --user restart catandary-frontend`, damit die Next-App den
   neuen Wert lädt (Next lädt `.env.local` beim Prozessstart, nicht live —
   siehe `frontend-env-gates-in-envlocal.md`).

**Keine Secret-Werte in diese oder eine andere Doku schreiben** — nur der
Abgleich-Schritt selbst ist dokumentiert.

## 4. `sync_subscribers.py` deployen

Liegt aktuell nur unter `docs/launch/newsletter-doi-php/sync_subscribers.py`
(Referenzkopie) — noch nicht unter `scripts/`. Vor der ersten Nutzung (manuell
oder per Cron) nach `scripts/sync_subscribers.py` kopieren. Das Skript ruft
sich selbst als `python -m scripts.sync_subscribers` auf (siehe eigener
Docstring) — das Modul-Präfix setzt voraus, dass die Datei unter `scripts/`
im Repo-Root liegt.

## 5. Cron aktivieren (nach Schritt 1–4)

`deploy/crontab.txt` enthält bereits zwei auskommentierte Einträge für dieses
Issue (Newsletter-Generierung+Versand Mo 09:00 über
`scripts/newsletter_tonight.sh`, Subscriber-Sync täglich 08:30 über
`scripts/sync_subscribers.py`). Erst einkommentieren, wenn Schritt 1–4 hier
erledigt sind — vorher liefe der Sync gegen ein fehlendes `export.php`
(Schritt 1) bzw. gegen fehlende `.env`-Werte (Schritt 2). Danach: Owner
installiert die neue `crontab.txt` (`crontab deploy/crontab.txt` oder Diff
manuell übernehmen — Claude Code installiert keine Crontabs).

## 6. Testdurchlauf (vor dem ersten ECHTEN Versand)

Mit der eigenen Adresse, Ende-zu-Ende, in dieser Reihenfolge:

1. **Signup**: `curl -X POST https://catandary.de/newsletter/subscribe.php -d "email=DEINE@ADRESSE.de" -d "consent=1"` (oder über das Formular). Erwartet: `{"ok":true,...}` (siehe EINBAU.md Schritt 5).
2. **DOI-Mail prüfen**: „Please confirm your subscription" muss ankommen (Resend, Absender `trends@send.catandary.de`).
3. **confirm**: Link in der Mail anklicken → Bestätigungsseite → Button klicken. In `phpMyAdmin` prüfen: `nl_subscriber.status = 'confirmed'`.
4. **export.php manuell prüfen**: `curl -H "Authorization: Bearer $NL_EXPORT_TOKEN" "https://catandary.de/newsletter/export.php?since=1970-01-01"` → JSON mit der eigenen Adresse, `status: "confirmed"`.
5. **sync_subscribers.py laufen lassen** (manuell, `.venv/bin/python -m scripts.sync_subscribers`) → Log meldet `synced 1 rows, watermark=...`. In Postgres prüfen: `SELECT * FROM newsletter_subscribers;` zeigt genau die eigene Adresse, `confirmed = TRUE`.
6. **Trockenlauf vor dem echten Versand**: `.venv/bin/python -m pipeline.newsletter_generator` (erzeugt/speichert die aktuelle Edition), danach `.venv/bin/python -m pipeline.newsletter_sender --latest --dry-run`. Das Log meldet die Empfängerzahl **und muss genau 1 sein** — `newsletter_sender.py` mailt IMMER an ALLE Zeilen mit `confirmed = TRUE AND unsubscribed_at IS NULL`, es gibt **kein** `--to`/Test-Adress-Flag. Zeigt der Dry-Run mehr als 1 Empfänger, NICHT weiterfahren, sondern erst klären, warum schon andere Zeilen bestätigt sind (z. B. weil das Formular vor diesem Testlauf schon öffentlich stand).
7. **Testversand an die eigene Adresse**: erst wenn Schritt 6 exakt 1 Empfänger zeigt: `.venv/bin/python -m pipeline.newsletter_sender --latest` (ohne `--dry-run`). Mail muss ankommen, mit funktionierendem `List-Unsubscribe`-Header und sichtbarem Abmeldelink im Footer.
8. **Abmeldelink-Klick**: Link in der Testmail anklicken → muss auf der Next-App tatsächlich abmelden (setzt Schritt 3 „AUTH_SECRET-Angleich" voraus — ohne den ist der Token ungültig und der Klick schlägt fehl). Danach in Postgres prüfen: `unsubscribed_at` gesetzt.
9. **Testdatensatz aufräumen**: Testadresse aus `nl_subscriber` (MySQL, Webspace) UND `newsletter_subscribers` (Postgres) wieder entfernen, damit die erste echte Kohorte sauber startet.

## 7. VPS-Go-Live: `NL_TRUSTED_PROXIES` setzen (separates, späteres Ereignis)

> **Stand 02.09.2026: entfällt.** Owner-Entscheid: statischer Export aufs Webhosting statt
> VPS — es gibt keinen Reverse-Proxy vor dem Webspace, also keinen DNS-Umzug und nichts, dem
> `nl_client_ip()` vertrauen müsste. `NL_TRUSTED_PROXIES` bleibt leer. Der Abschnitt bleibt
> als Archiv stehen, falls je wieder ein Proxy davorgeschaltet wird.

Erst wenn der VPS-Reverse-Proxy aus #82/#93 tatsächlich vor den Webspace
geschaltet wird (DNS-Umzug `catandary.de` → VPS-IP): in der auf dem Webspace
liegenden `nl_config.php` den `NL_TRUSTED_PROXIES`-Block auf die öffentliche
VPS-IP setzen, erneut hochladen. **Nicht** Voraussetzung für den ersten
Newsletter, wenn dieser noch auf dem heutigen Hetzner-only-Setup passiert —
aber zwingend **vor** dem DNS-Umzug selbst (siehe EINBAU.md „Nächster
Upload" und `HOSTING_PUBLIC_VPS.md` Schritt 4), sonst ist ab dem Umzug jeder
Einwilligungsnachweis wertlos.

## 8. Resend-DPA abschließen (Owner-Gate, extern)

Auftragsverarbeitungsvertrag (Art. 28 DSGVO) mit Resend im Resend-Dashboard
abschließen, bevor Adressen von EU-Personen dauerhaft über Resend versendet
werden. Rein rechtlicher/vertraglicher Schritt, nicht technisch — kann nur der
Owner erledigen (siehe auch `HOSTING_PUBLIC_VPS.md`, Owner-Gates-Tabelle).

## 9. Datenschutzerklärung (Owner-Gate, bereits in EINBAU.md vermerkt)

Newsletter-Abschnitt aus `docs/legal/newsletter-doi-texte.draft.md` in die
Datenschutzerklärung einbauen, bevor die Anmeldung öffentlich sichtbar
beworben wird. Unabhängig vom technischen Go-Live, aber Voraussetzung für den
ersten Versand an echte (nicht nur Owner-Test-)Adressen.

---

## Danach: erst dann ist „erster echter Newsletter" freigegeben

Wenn Schritt 1–6 durchlaufen und grün sind sowie Schritt 8–9 (Owner-Gates)
erledigt sind, kann der erste reguläre Signup-Traffic auf die Anmeldung
gelenkt werden. Schritt 7 (`NL_TRUSTED_PROXIES` mit echter VPS-IP) ist an den
DNS-Umzug gekoppelt, nicht an den ersten Newsletter selbst — beide Ereignisse
können, müssen aber nicht zusammenfallen.
