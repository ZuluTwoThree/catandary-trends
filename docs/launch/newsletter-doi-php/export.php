<?php
declare(strict_types=1);
require __DIR__ . '/_lib.php';

/* Nur für den lokalen Cron der Workstation. Bearer-Token im Header,
   NICHT als Query-Parameter (landet sonst in Apache-/Proxy-Logs). */
header('Cache-Control: no-store');
header('X-Robots-Tag: noindex');

$cfg  = nl_cfg();
$auth = $_SERVER['HTTP_AUTHORIZATION'] ?? $_SERVER['HTTP_X_EXPORT_TOKEN'] ?? '';
$sent = str_starts_with($auth, 'Bearer ') ? substr($auth, 7) : $auth;

/* Fail closed like nl_unsub_secret(): an unconfigured token (placeholder or
   empty) must never let the subscriber list out — hash_equals('', '') is true. */
$tok = (string)($cfg['export_token'] ?? '');
if (strlen($tok) < 32 || str_starts_with($tok, 'CHANGE_ME') || $sent === '') {
    error_log('nl: export_token not configured (nl_config.php block 6) or empty token sent');
    http_response_code($sent === '' && strlen($tok) >= 32 ? 401 : 503);
    exit;
}
if (!hash_equals($tok, (string)$sent)) {
    // Bremse gegen Token-Raten
    nl_throttle('ex', nl_client_ip(), 3600);
    http_response_code(401);
    exit;
}
if (nl_throttle('ex', nl_client_ip(), 3600) > 60) {
    http_response_code(429);
    exit;
}

/* Vollständiger Zustandsspiegel (auch Abmeldungen!), optional inkrementell. */
$since = (string)($_GET['since'] ?? '1970-01-01 00:00:00');
if (!preg_match('/^\d{4}-\d{2}-\d{2}( \d{2}:\d{2}:\d{2})?$/', $since)) {
    http_response_code(400);
    exit;
}

$st = nl_db()->prepare(
    'SELECT email, status, verticals, confirmed_at, signup_at, unsubscribed_at, updated_at
       FROM nl_subscriber
      WHERE status IN ("confirmed","unsubscribed") AND updated_at > ?
      ORDER BY updated_at ASC
      LIMIT 5000'
);
$st->execute([$since]);
$rows = $st->fetchAll();

nl_db()->prepare(
    'INSERT INTO nl_consent_log (email, event, occurred_at, ip, detail)
     VALUES ("-", "export", NOW(), ?, ?)'
)->execute([nl_client_ip(), 'n=' . count($rows)]);

header('Content-Type: application/json; charset=utf-8');
echo json_encode([
    'server_time' => gmdate('Y-m-d H:i:s'),
    'count'       => count($rows),
    'subscribers' => $rows,
], JSON_UNESCAPED_UNICODE);
