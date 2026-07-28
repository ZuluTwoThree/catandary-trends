<?php
declare(strict_types=1);
require __DIR__ . '/_lib.php';

/**
 * Bestätigungsseite des Double-Opt-in.
 *
 * WICHTIG — warum hier zwei Schritte nötig sind:
 * Ein Klick auf den Link (GET) darf die Einwilligung NICHT bereits erteilen.
 * Sicherheits-Scanner in Firmen-Mailservern, Link-Vorschauen (Slack, Outlook,
 * WhatsApp) und Prefetch-Mechanismen rufen jeden Link in einer Mail automatisch
 * auf. Würde der GET bestätigen, entstünden Einwilligungen ohne menschliches
 * Zutun — und genau der Nachweis, für den das ganze Verfahren existiert, wäre
 * wertlos (Art. 7 Abs. 1 DSGVO: "eindeutige bestätigende Handlung").
 *
 * Deshalb:  GET  = Token prüfen und Bestätigungs-Button zeigen
 *           POST = Einwilligung erteilen (nur durch echten Klick auslösbar)
 */

$INVALID = '<p>This confirmation link is invalid or has expired.</p>'
         . '<p>Just sign up again and we will send you a fresh link.</p>';

$isPost = ($_SERVER['REQUEST_METHOD'] ?? 'GET') === 'POST';
$raw    = (string)($isPost ? ($_POST['t'] ?? '') : ($_GET['t'] ?? ''));
$parts  = explode('.', $raw, 2);

/* Formprüfung, bevor irgendetwas die DB berührt */
if (count($parts) !== 2
    || preg_match('/^[a-f0-9]{16}$/', $parts[0]) !== 1
    || preg_match('/^[A-Za-z0-9_-]{40,64}$/', $parts[1]) !== 1) {
    nl_page('Link invalid', 'Link invalid', $INVALID);
}
[$selector, $verifier] = $parts;

try {
    $cfg = nl_cfg();

    /* Brute-Force-Bremse auf den Selector-Namensraum */
    if (nl_throttle('cf', nl_client_ip(), 3600) > 30) {
        http_response_code(429);
        nl_page('Too many attempts', 'Too many attempts', '<p>Please try again later.</p>');
    }

    $db = nl_db();
    $st = $db->prepare('SELECT id, email, status, token_hash, token_expires_at
                          FROM nl_subscriber WHERE token_selector = ?');
    $st->execute([$selector]);
    $row = $st->fetch();

    /* Timing-sicher: hash_equals immer ausführen, auch wenn kein Datensatz da ist. */
    $stored    = is_array($row) ? (string)$row['token_hash'] : str_repeat('0', 64);
    $presented = hash('sha256', $verifier);
    $match     = hash_equals($stored, $presented);

    if (!is_array($row) || !$match) {
        nl_log(is_array($row) ? (string)$row['email'] : '-', 'confirm_failed', 'bad_token');
        nl_page('Link invalid', 'Link invalid', $INVALID);
    }

    /* Schon bestätigt -> idempotent, gleiche Erfolgsseite (auch bei GET) */
    if ($row['status'] === 'confirmed') {
        nl_page('Subscription confirmed', 'All set - you are subscribed.',
            '<p>We already had this confirmation on file.</p>');
    }

    if ($row['token_expires_at'] === null || strtotime((string)$row['token_expires_at']) < time()) {
        nl_log($row['email'], 'confirm_failed', 'expired');
        nl_page('Link expired', 'Link expired', $INVALID);
    }

    /* ---------- GET: nur anzeigen, nichts verändern ---------------------- */
    if (!$isPost) {
        $tokenEsc = htmlspecialchars($raw, ENT_QUOTES, 'UTF-8');
        $mailEsc  = htmlspecialchars((string)$row['email'], ENT_QUOTES, 'UTF-8');
        $textEsc  = htmlspecialchars((string)$cfg['consent_text'], ENT_QUOTES, 'UTF-8');

        nl_page('Confirm subscription', 'One last click.',
              '<p>Please confirm the subscription for <strong>' . $mailEsc . '</strong>.</p>'
            . '<blockquote style="margin:1.4rem 0;padding:.9rem 1.1rem;border-left:2px solid #d4ff3a;'
            . 'color:#8a8d82;font-size:.9rem">' . $textEsc . '</blockquote>'
            . '<form method="post" action="confirm.php">'
            . '<input type="hidden" name="t" value="' . $tokenEsc . '">'
            . '<button type="submit" style="display:inline-block;background:#d4ff3a;color:#0a0c0a;'
            . 'border:0;padding:.85rem 1.6rem;font-family:ui-monospace,monospace;font-size:.78rem;'
            . 'letter-spacing:.12em;text-transform:uppercase;cursor:pointer">'
            . 'Confirm subscription</button>'
            . '</form>'
            . '<p style="color:#8a8d82;font-size:.8rem;margin-top:1.4rem">'
            . 'Did not sign up? Just close this page - without a confirmation we send you nothing.</p>');
    }

    /* ---------- POST: jetzt erst wird die Einwilligung erteilt ----------- */
    $upd = $db->prepare(
        'UPDATE nl_subscriber
            SET status = "confirmed", confirmed_at = NOW(), confirm_ip = ?, confirm_ua = ?,
                token_selector = NULL, token_hash = NULL, token_expires_at = NULL
          WHERE id = ? AND status = "pending"'
    );
    $upd->execute([nl_client_ip(), nl_ua(), $row['id']]);

    /* rowCount()==0 heißt: parallel schon bestätigt -> trotzdem Erfolgsseite */
    if ($upd->rowCount() > 0) {
        nl_log($row['email'], 'confirm', 'v=' . $cfg['consent_version']);
    }

    nl_page('Subscription confirmed', 'Subscription confirmed.',
        '<p>You will now receive the Catandary Trends newsletter.</p>'
      . '<p>You can unsubscribe at any time via the link at the end of every email.</p>');

} catch (Throwable $e) {
    error_log('confirm.php: ' . $e->getMessage());
    http_response_code(500);
    nl_page('Error', 'Something went wrong.',
        '<p>Please try again later.</p>');
}
