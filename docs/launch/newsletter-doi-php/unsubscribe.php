<?php
declare(strict_types=1);
require __DIR__ . '/_lib.php';

/**
 * Abmeldung = Widerruf der Einwilligung (Art. 7 Abs. 3 DSGVO, § 7 Abs. 2 Nr. 2 UWG).
 * Muss so einfach sein wie die Anmeldung und dauerhaft funktionieren.
 *
 * Zwei Wege, EINE URL (die aus dem Mail-Footer / List-Unsubscribe-Header):
 *
 *   1. Mensch im Browser
 *        GET  ?t=<token>          -> Token prüfen, Seite mit Abmelde-Button zeigen.
 *                                    KEIN Write bei GET: Sicherheits-Scanner in
 *                                    Firmen-Mailservern, Link-Vorschauen und
 *                                    Prefetcher rufen jeden Link einer Mail auf —
 *                                    würde der GET abmelden, flögen Abonnenten
 *                                    ohne ihr Zutun aus der Liste (gleiches
 *                                    Muster wie confirm.php, nur umgekehrt).
 *        POST t=<token>           -> abmelden, Erfolgsseite.
 *
 *   2. Postfach-Button (RFC 8058 "One-Click", Gmail/Yahoo/Apple Mail)
 *        POST ?t=<token>  Body: List-Unsubscribe=One-Click
 *                                 -> sofort abmelden, HTTP 200, schlichter Text.
 *                                    Kein Formular, kein Redirect, keine Cookies,
 *                                    kein JS — der Aufruf kommt vom Mailanbieter,
 *                                    nicht vom Browser des Empfängers. Deshalb
 *                                    auch bewusst KEIN Origin-Check.
 *
 * Token: nl_unsub_verify() in _lib.php — HMAC über die Adresse mit unsub_secret,
 * ohne Ablauf (der Link muss in einer Mail von vor drei Jahren noch gelten).
 * Erzeugt wird er von pipeline/newsletter_sender.py mit demselben Secret.
 *
 * Idempotent: bereits abgemeldet -> dieselbe Erfolgsantwort, kein zweiter
 * Log-Eintrag. Unbekannte Adresse (nach Aufbewahrungsfrist gelöscht) -> ebenfalls
 * Erfolgsantwort; es gibt nichts mehr, was man abmelden könnte.
 */

$INVALID = '<p>This unsubscribe link is invalid.</p>'
         . '<p>To unsubscribe, use the link at the end of any Catandary Trends email '
         . 'or write to contact@catandary.de.</p>';

/* Ziel nach erfolgreicher Abmeldung im Browser (Form-POST): die statische
   Bestätigungsseite des Website-Exports (frontend/src/app/trends/newsletter/
   unsubscribed, noindex) — im Site-Design statt der PHP-Notseite. Der Export
   muss publiziert sein, bevor diese Datei hochgeladen wird; die Abmeldung
   selbst ist unabhängig davon längst geschrieben. One-Click (RFC 8058)
   antwortet weiterhin mit Klartext, nie mit einem Redirect. */
$UNSUBSCRIBED_URL = '/trends/newsletter/unsubscribed';

$method = $_SERVER['REQUEST_METHOD'] ?? 'GET';
if ($method === 'HEAD') {
    $method = 'GET';                                   // Prefetch/Scanner: wie GET, kein Write
}
if ($method !== 'GET' && $method !== 'POST') {
    http_response_code(405);
    header('Allow: GET, POST');
    exit;
}
$isPost = $method === 'POST';

/* RFC 8058: der One-Click-POST trägt das Token in der URL (Query) und den festen
   Body "List-Unsubscribe=One-Click". $_POST kennt den Schlüssel mit Bindestrich;
   zur Sicherheit zusätzlich der rohe Body, falls ein Anbieter einen anderen
   Content-Type schickt. */
$rawBody  = $isPost ? (string)file_get_contents('php://input') : '';
$oneClick = $isPost && (
    ($_POST['List-Unsubscribe'] ?? '') === 'One-Click'
    || str_contains($rawBody, 'List-Unsubscribe=One-Click')
);

$raw = (string)($isPost ? ($_POST['t'] ?? ($_GET['t'] ?? '')) : ($_GET['t'] ?? ''));

/** Antwort für den Mailanbieter: kein HTML, keine Weiterleitung. */
function nl_oneclick_reply(int $code, string $text): never
{
    http_response_code($code);
    header('Content-Type: text/plain; charset=utf-8');
    header('Cache-Control: no-store');
    header('X-Robots-Tag: noindex');
    echo $text, "\n";
    exit;
}

try {
    /* Formprüfung + HMAC zuerst — reine CPU, kein DB-Zugriff. Ein Strom
       ungültiger Tokens erreicht so nie die Datenbank. */
    $email = nl_unsub_verify($raw);
    if ($email === null) {
        if ($oneClick) {
            nl_oneclick_reply(400, 'Invalid unsubscribe token');
        }
        http_response_code(400);
        nl_page('Link invalid', 'Link invalid', $INVALID);
    }

    /* Bremse pro IP für alles, was ab hier die DB berührt. Der Token ist 256 Bit
       HMAC — es geht um DB-Last, nicht um Raten. Großzügiger als confirm.php:
       One-Click-POSTs kommen gebündelt von wenigen Anbieter-IPs. */
    if (nl_throttle('un', nl_client_ip(), 3600) > 60) {
        if ($oneClick) {
            nl_oneclick_reply(429, 'Too many requests');
        }
        http_response_code(429);
        nl_page('Too many attempts', 'Too many attempts', '<p>Please try again later.</p>');
    }

    /* ---------- GET: nur anzeigen, nichts verändern ---------------------- */
    if (!$isPost) {
        $tokenEsc = htmlspecialchars($raw, ENT_QUOTES, 'UTF-8');
        $mailEsc  = htmlspecialchars($email, ENT_QUOTES, 'UTF-8');

        nl_page('Unsubscribe', 'Unsubscribe from Catandary Trends?',
              '<p>This will stop all newsletter emails to <strong>' . $mailEsc . '</strong>.</p>'
            . '<form method="post" action="unsubscribe.php">'
            . '<input type="hidden" name="t" value="' . $tokenEsc . '">'
            . '<button type="submit" style="display:inline-block;background:#d4ff3a;color:#0a0c0a;'
            . 'border:0;padding:.85rem 1.6rem;font-family:ui-monospace,monospace;font-size:.78rem;'
            . 'letter-spacing:.12em;text-transform:uppercase;cursor:pointer">'
            . 'Unsubscribe</button>'
            . '</form>'
            . '<p style="color:#8a8d82;font-size:.8rem;margin-top:1.4rem">'
            . 'Changed your mind? Just close this page - nothing happens until you click the button.</p>');
    }

    /* ---------- POST: jetzt wird abgemeldet ------------------------------ */
    $db  = nl_db();
    $upd = $db->prepare(
        'UPDATE nl_subscriber
            SET status = "unsubscribed", unsubscribed_at = NOW(), unsubscribe_ip = ?,
                token_selector = NULL, token_hash = NULL, token_expires_at = NULL
          WHERE email = ? AND status <> "unsubscribed"'
    );
    $upd->execute([nl_client_ip(), $email]);

    /* rowCount()==0: schon abgemeldet oder nicht (mehr) vorhanden -> trotzdem
       Erfolg, aber kein zweiter Nachweis-Eintrag. */
    if ($upd->rowCount() > 0) {
        nl_log($email, 'unsubscribe', $oneClick ? 'one-click' : 'form');
    }

    if ($oneClick) {
        nl_oneclick_reply(200, 'Unsubscribed');
    }
    /* 303 See Other: der Browser holt die Bestätigungsseite per GET — ein
       Reload dort wiederholt den POST nicht. Kein Token in der Ziel-URL. */
    header('Cache-Control: no-store');
    header('Location: ' . $UNSUBSCRIBED_URL, true, 303);
    exit;

} catch (Throwable $e) {
    error_log('unsubscribe.php: ' . $e->getMessage());   // Details nie an den Client
    if ($oneClick) {
        nl_oneclick_reply(500, 'Temporary error, please retry');
    }
    http_response_code(500);
    nl_page('Error', 'Something went wrong.',
        '<p>Please try again later, or write to contact@catandary.de and we will '
      . 'remove you manually.</p>');
}
