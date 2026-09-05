<?php
declare(strict_types=1);
/* DER EINE Cronjob (Webhosting S erlaubt genau 1).
   konsoleH -> Cronjob-Manager: Interpreter PHP 8.x,
   Pfad /usr/www/users/<ftp-login>/public_html/newsletter/cron.php
   Intervall alle 15 Minuten.
   Erledigt alle Hintergrundaufgaben sequenziell. */

if (PHP_SAPI !== 'cli') { http_response_code(404); exit; }   // nie per HTTP aufrufbar
require __DIR__ . '/_lib.php';

$cfg = nl_cfg();
$db  = nl_db();

/* 1. Nicht zugestellte Bestätigungsmails erneut versuchen (max. 3 Versuche) */
$st = $db->prepare(
    'SELECT id, email, token_selector FROM nl_subscriber
      WHERE status = "pending" AND mail_last_error IS NOT NULL
        AND mail_send_count < 3 AND token_expires_at > NOW()
        AND (last_mail_at IS NULL OR last_mail_at < NOW() - INTERVAL 15 MINUTE)
      LIMIT 20'
);
$st->execute();
foreach ($st->fetchAll() as $r) {
    /* Der Verifier ist bewusst nicht mehr rekonstruierbar -> neues Token ausstellen. */
    [$selector, $verifier, $token, $hash] = nl_make_token();
    $db->prepare('UPDATE nl_subscriber
                     SET token_selector = ?, token_hash = ?,
                         token_expires_at = NOW() + INTERVAL ? HOUR
                   WHERE id = ?')
       ->execute([$selector, $hash, (int)$cfg['token_ttl_hours'], $r['id']]);

    $ok = nl_send_confirm_mail($r['email'], $token);
    $db->prepare('UPDATE nl_subscriber
                     SET mail_send_count = mail_send_count + 1, last_mail_at = NOW(),
                         mail_last_error = ?
                   WHERE id = ?')->execute([$ok ? null : 'send_failed', $r['id']]);
    nl_log($r['email'], $ok ? 'mail_sent' : 'mail_failed', 'retry');
}

/* 2. Datenminimierung: unbestätigte Anmeldungen nach Ablauf + 7 Tagen löschen.
      Ohne Bestätigung existiert keine Einwilligung -> keine Speichergrundlage. */
$db->exec('DELETE FROM nl_subscriber
            WHERE status = "pending" AND token_expires_at < NOW() - INTERVAL 7 DAY');

/* 3. Rate-Limit-Fenster aufräumen */
$db->exec('DELETE FROM nl_throttle WHERE window_start < NOW() - INTERVAL 2 DAY');

/* 4. Nachweis-Log nach Aufbewahrungsfrist löschen (Verjährung) */
$db->prepare('DELETE FROM nl_consent_log WHERE occurred_at < NOW() - INTERVAL ? DAY')
   ->execute([(int)$cfg['retention_days']]);

/* 5. Abgemeldete: PII nach Frist entfernen, Beleg-Hash behalten (Suppression-Liste) */
$db->prepare('DELETE FROM nl_subscriber
               WHERE status = "unsubscribed" AND unsubscribed_at < NOW() - INTERVAL ? DAY')
   ->execute([(int)$cfg['retention_days']]);

echo "ok\n";
