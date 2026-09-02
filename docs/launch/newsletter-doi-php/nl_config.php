<?php
// Ziel:  /newsletter/nl_config.php  (neben _lib.php)
//
// ============================================================================
//  AUSFÜLLEN: Ersetze NUR die Zeilen zwischen  <<<'V'  und  V;
//  Jeder Wert steht ALLEIN auf seiner Zeile — exakt so einfügen, wie er ist.
//  NICHTS escapen, KEINE Anführungszeichen ergänzen. Sonderzeichen wie
//  ' " \ $ ! sind in dieser Schreibweise völlig unschädlich.
//  Die Zeilen  <<<'V'  und  V;  selbst NICHT verändern.
// ============================================================================
//
// Sicherheit: Datei liegt im Web-Bereich (Hetzner hat kein beschreibbares
// Verzeichnis oberhalb des Docroots) und ist doppelt geschützt: .htaccess
// sperrt den HTTP-Zugriff, und als .php-Datei liefert Apache nie Quelltext
// aus. Per FTP auf Rechte 600 setzen. NIE in Git einchecken.

// --- 1/7: MySQL-Verbindung --------------------------------------------------
// HOST_HIER  -> z. B. sql123.your-server.de   (NICHT localhost)
// DBNAME_HIER -> Name der Datenbank aus konsoleH
$DB_DSN = <<<'V'
mysql:host=HOST_HIER;port=3306;dbname=DBNAME_HIER;charset=utf8mb4
V;

// --- 2/7: MySQL-Benutzer ----------------------------------------------------
$DB_USER = <<<'V'
DBUSER_HIER
V;

// --- 3/7: MySQL-Passwort ----------------------------------------------------
$DB_PASS = <<<'V'
DBPASS_HIER
V;

// --- 4/7: App-Geheimnis (neu erzeugen:  openssl rand -hex 32) ----------------
$APP_SECRET = <<<'V'
CHANGE_ME_hex64
V;

// --- 5/7: Unsubscribe-Geheimnis ----------------------------------------------
// Signiert die Abmeldelinks (unsubscribe.php, HMAC-SHA256). Muss EXAKT dem Wert
// von NEWSLETTER_UNSUB_SECRET in der .env (Repo-Root) der Workstation
// entsprechen: pipeline/newsletter_sender.py erzeugt damit die Links in jeder
// Mail, unsubscribe.php prüft sie. Einmal erzeugen (openssl rand -hex 32) und
// auf BEIDEN Seiten eintragen. Weicht der Wert ab, ist jeder Abmeldelink in
// jeder verschickten Mail ungültig. Mindestens 16 Zeichen; mit "CHANGE_ME"
// beginnende Werte gelten als "nicht konfiguriert" -> unsubscribe.php lehnt
// dann ALLES ab (fail closed), erzeugt also nie eine stille Fehlabmeldung.
// (Bis 2026-09-02 stand hier "AUTH_SECRET aus frontend/.env.local" — das galt
// für die Next-Route /trends/newsletter/unsubscribe, die es öffentlich seit dem
// Umstieg auf den statischen Export nicht mehr gibt.)
$UNSUB_SECRET = <<<'V'
CHANGE_ME_same_as_NEWSLETTER_UNSUB_SECRET
V;

// --- 6/7: Export-Token (neu erzeugen:  openssl rand -hex 32) ------------------
$EXPORT_TOKEN = <<<'V'
CHANGE_ME_hex64
V;

// --- 7/7: Resend-API-Key (send-only, beginnt mit re_) -------------------------
$RESEND_KEY = <<<'V'
re_XXXXXXXX
V;

// --- Optionaler 8. Block: vertrauenswürdige Reverse-Proxies ------------------
// NUR relevant, wenn je ein eigener Reverse-Proxy VOR diesen Webspace
// geschaltet wird. Stand 2026-09-02 (Owner-Entscheid: statischer Export direkt
// auf dem Hetzner-Webhosting, kein VPS davor) gibt es keinen solchen Proxy —
// Block LEER LASSEN. Das ist der Standardzustand und entspricht dem laufenden
// Hetzner-only-Verhalten. Der Block bleibt als Vorsorge stehen.
//
// Steht hier eine IP UND kommt eine Anfrage mit genau dieser REMOTE_ADDR an,
// behandelt nl_client_ip() (_lib.php) deren X-Forwarded-For-Header als
// vertrauenswürdig und liest die echte Client-IP daraus (von rechts, erster
// nicht in dieser Liste stehender Eintrag). Leer = bisheriges Verhalten exakt
// unverändert (alte Varnish-Heuristik: XFF nur wenn REMOTE_ADDR selbst schon
// privat/loopback ist).
//
// PFLICHT vor dem DNS-Umzug auf den VPS, sonst tragen signup_ip / confirm_ip /
// unsubscribe_ip / nl_consent_log.ip überall dieselbe VPS-IP statt der echten
// Anmelder-IP ein — der Einwilligungsnachweis (Art. 7 Abs. 1 DSGVO) wäre
// wertlos, und das Rate-Limit liefe für alle Besucher in einem gemeinsamen
// Bucket.
define('NL_TRUSTED_PROXIES', [
    // 'VPS_IP_HIER',   // z. B. '203.0.113.7' — öffentliche IP des VPS-Proxys.
    // Mehrere Einträge möglich (IPv4 und/oder IPv6), falls mehr als ein
    // eigener Proxy in der Kette hängt.
]);

// ============================================================================
//  AB HIER NICHTS MEHR ÄNDERN
// ============================================================================
return [
    'db_dsn'   => trim($DB_DSN),
    'db_user'  => trim($DB_USER),
    'db_pass'  => trim($DB_PASS),

    'app_secret'     => trim($APP_SECRET),
    'unsub_secret'   => trim($UNSUB_SECRET),
    'export_token'   => trim($EXPORT_TOKEN),
    'resend_api_key' => trim($RESEND_KEY),

    'mail_from'      => 'Catandary Trends <trends@send.catandary.de>',
    'mail_reply_to'  => 'contact@catandary.de',

    'site_url'       => 'https://catandary.de',
    'site_host'      => 'catandary.de',          // kanonischer Host für Origin-Check

    'token_ttl_hours'  => 48,

    /* Einwilligung ----------------------------------------------------------
     * consent_text MUSS WORTGLEICH mit dem Checkbox-Text im Formular sein
     * (index.html, Label #nl-consent). Er wird als Nachweis archiviert; eine
     * Abweichung würde den Nachweis wertlos machen.
     * Bei JEDER Änderung am Text: consent_version hochzählen — der alte
     * Wortlaut bleibt dann in nl_consent_text stehen und bleibt beweisbar. */
    'consent_version'  => '2026-07-26.1',
    'consent_lang'     => 'en',
    'consent_text'     => 'Yes, send me the launch notice and the weekly Catandary newsletter '
                        . 'by email. I can withdraw this consent at any time via the unsubscribe '
                        . 'link in every email or by writing to contact@catandary.de.',

    // Limits
    'lim_ip_hour'      => 3,
    'lim_ip_day'       => 10,
    'lim_email_day'    => 2,     // max. Bestätigungsmails pro Adresse / 24 h
    'lim_email_total'  => 5,     // absolute Obergrenze pro Adresse
    'lim_global_hour'  => 100,   // Notbremse gegen verteiltes Mail-Bombing
    'retention_days'   => 1095,  // Log-Aufbewahrung nach Abmeldung (3 J. Verjährung)
];
