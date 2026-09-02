# Public Hosting der App — Runbook für den Launch 01.10. (#82, Stand 2026-08-28)

> **Überholt durch Owner-Entscheid 02.09.2026 — statischer Export statt VPS.** Die öffentliche
> Website wird als statischer `next build`-Export aufs bestehende Hetzner-Webhosting publiziert;
> ein VPS wird nicht bestellt, Caddy/Tunnel/Push-Pfad entfallen. Maßgeblich sind
> `docs/audits/2026-09-02_static_export_design.md` (Design) und
> `docs/launch/09_launch_plan_2026-09-02.md` (Plan, #82-Neuschnitt). Dieses Dokument bleibt als
> Archiv der verworfenen VPS-Variante stehen; nichts hieraus ist noch Arbeitsauftrag.

Durch #93 ist die Hosting-Frage klein geworden: öffentlich ausgeliefert werden nur noch
**~83 MB** (30-Tage-Feed, Analysen, Newsletter, Rechtsseiten) statt der 446-GB-Datenbank.
Die Workstation bleibt Produktionswerkzeug und wird **nicht** Teil des öffentlichen Pfads.

## Empfehlung: eigenständiger Mini-VPS (kein Tunnel zur Workstation)

**Hetzner Cloud CX22** (2 vCPU, 4 GB, ~4–5 €/Monat) mit Caddy + Node + Postgres.

Warum eigenständig statt des früher geplanten Tailscale-Tunnels (#82-Kommentar vom 15.08.):
- Die öffentliche Site hängt dann **nicht** an der Verfügbarkeit der Workstation
  (Stromausfall 17.08. wäre sonst ein öffentlicher Ausfall gewesen).
- 83 MB passen locker in ein VPS-Postgres; der Tunnel-Plan stammte aus der 391-GB-Zeit.
- `PUBLIC_MODE=1` (seit `9c7f02a`) blendet alles aus, was die großen Korpora bräuchte.

## Aufbau (Reihenfolge)

1. **Owner: VPS bestellen** (Hetzner Cloud, CX22, Standort egal, Ubuntu LTS). → IP notieren.
2. Grundinstallation: Caddy (`deploy/Caddyfile` als Basis, Ziel `localhost:3001`),
   Node 22 LTS, Postgres 16 + pgvector ist **nicht** nötig (kein Embedding-Query im
   Public-Umfang — verifizieren beim ersten Deploy: die 30-Tage-Feed-Queries laufen ohne
   `embedding`-Spalte; falls doch eine Route sie braucht, pgvector nachinstallieren).
3. **Publikations-Pfad bauen** (der eigentliche Arbeitsschritt in #82, ~1 Tag):
   - `scripts/export_public_slice.py` (zu bauen): zieht aus der Workstation-DB den
     öffentlichen Ausschnitt — `trends` (status='published', letzte 30 Tage, ohne
     `embedding`), zugehörige `raw_entries`-Metadaten, `sources`-Namen, `dead_links`,
     Newsletter-Editionen — als `pg_dump`-Teilmenge oder COPY-Satz.
   - Täglicher Push nach dem 04:00-Cycle (rsync/scp + Restore auf dem VPS), als
     Cron-Schritt im bestehenden `full_cycle_cron.sh`-Nachlauf.
   - App-Deploy: `git pull` auf dem VPS + `npm run build` + systemd-Unit
     (Kopie von `deploy/systemd/catandary-frontend.service`, plus `PUBLIC_MODE=1`
     und `REVIEW_ENABLED=0` in der Unit-Env).
4. **Vor dem DNS-Umzug (Pflicht, #16):** `nl_client_ip()`-Patch + `export.php` auf den
   Webspace hochladen und `NL_TRUSTED_PROXIES` auf die VPS-IP setzen — sonst ist der
   DOI-Einwilligungsnachweis ab Umzug wertlos. (Paket + Anleitung:
   `docs/launch/newsletter-doi-php/EINBAU.md`, Checkliste `NEWSLETTER_GOLIVE.md`.)
5. **DNS (Owner, konsoleH):** A-Record `catandary.de` → VPS-IP. ⚠️ Bekannte Falle:
   der konsoleH-Editor verwirft TXT-Werte mit `@` stillschweigend — SPF/DKIM/DMARC
   für send.catandary.de nach dem Umzug **verifizieren**, nicht annehmen.
   Die statische Landing zieht mit auf den VPS um (Caddy served `/` aus der App,
   die Landing-Route existiert dort).
6. `noindex` entfernen (Landing + App), OG-Bild prüfen, Countdown-Seite abschalten.

## Was bewusst NICHT passiert

- Kein Postgres-Port, kein SSH von außen zur Workstation; der Datenfluss ist
  Workstation → VPS (push), nie andersherum.
- Keine Foresight-/Auth-/Stripe-Routen öffentlich (`PUBLIC_MODE=1`).
- Der Tailscale-Tunnel bleibt für Admin-Zwecke nutzbar, ist aber kein Serving-Pfad.

## Alternative (verworfen, dokumentiert für die Entscheidung)

**Statischer Export** (`next output: export`) auf dem bestehenden Webspace: ginge für
Feed+Analysen, verliert aber Suche/`?q=`, ISR und jede API-Route (Anfrageformular später,
Newsletter-Signup-API) — und spart gegenüber dem CX22 nur ~4 €/Monat. Nur wählen, wenn
der VPS-Betrieb grundsätzlich nicht gewollt ist.

## Owner-Gates (nichts davon kann Claude ausführen)

| Gate | Wo |
|---|---|
| VPS bestellen | Hetzner Cloud Console |
| DNS-A-Record umziehen | konsoleH |
| Resend-DPA abschließen | resend.com Dashboard |
| PHP-Paket-Upload (Schritt 4) | SFTP Webspace |
| Anwaltliche Prüfung Rechtstexte | extern |
