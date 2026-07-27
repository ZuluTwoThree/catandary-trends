<?php
declare(strict_types=1);
require __DIR__ . '/_lib.php';

header('Cache-Control: no-store');
header('Referrer-Policy: no-referrer');

/* --- 1. Nur POST ------------------------------------------------------- */
if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') {
    http_response_code(405);
    header('Allow: POST');
    exit;
}

$cfg = nl_cfg();

/* --- 2. Origin-Check (cookieless CSRF-/Drive-by-Schutz) ---------------- */
$origin = $_SERVER['HTTP_ORIGIN'] ?? $_SERVER['HTTP_REFERER'] ?? '';
$host   = $origin !== '' ? (parse_url($origin, PHP_URL_HOST) ?? '') : '';
if ($host !== '' && $host !== $cfg['site_host'] && $host !== 'www.' . $cfg['site_host']) {
    http_response_code(403);
    exit;
}

/* --- 3. Honeypot: unsichtbare Felder müssen leer bleiben --------------- */
if (($_POST['website'] ?? '') !== '' || ($_POST['company_url'] ?? '') !== '') {
    nl_json_neutral();                       // Bot bekommt dieselbe Erfolgsmeldung
}

/* --- 3b. Einwilligung MUSS serverseitig vorliegen ----------------------
 * Die Checkbox im Formular ist nur eine Bequemlichkeit — `required` im HTML
 * lässt sich mit zwei Klicks in den Entwicklerwerkzeugen aushebeln, und ein
 * direkter POST kennt das Formular gar nicht. Ohne diese Prüfung würden wir
 * Adressen ohne Einwilligung aufnehmen und hätten im Streitfall nichts in der
 * Hand (Art. 7 Abs. 1 DSGVO: Nachweispflicht liegt bei uns).
 * Hier bewusst KEINE neutrale Antwort: das ist ein Formularfehler, keine
 * Information über die Existenz einer Adresse.
 */
$consent = (string)($_POST['consent'] ?? '');
if ($consent !== '1' && strtolower($consent) !== 'on' && strtolower($consent) !== 'true') {
    http_response_code(400);
    header('Content-Type: application/json; charset=utf-8');
    echo json_encode(['ok' => false,
        'message' => 'Bitte bestätige die Einwilligung, damit wir dir schreiben dürfen.'],
        JSON_UNESCAPED_UNICODE);
    exit;
}

/* --- 4. Eingaben ------------------------------------------------------- */
$email = strtolower(trim((string)($_POST['email'] ?? '')));
if ($email === '' || !nl_valid_email($email)) {
    http_response_code(400);
    header('Content-Type: application/json; charset=utf-8');
    echo json_encode(['ok' => false, 'message' => 'Bitte eine gültige E-Mail-Adresse angeben.'],
        JSON_UNESCAPED_UNICODE);
    exit;
}

$allowed   = ['FOOD','TECH','HEALTH','ECO','DESIGN','FASHION','BIZ','LIFESTYLE'];
$verticals = array_values(array_intersect($allowed,
    array_map('strtoupper', (array)($_POST['verticals'] ?? []))));
$verticalsJson = json_encode($verticals);

$ip  = nl_client_ip();
$now = date('Y-m-d H:i:s');

try {
    /* --- 5. Rate-Limits: global -> IP -> Adresse ----------------------- */
    if (nl_throttle('global', 'all', 3600)          > $cfg['lim_global_hour']) nl_json_neutral();
    if (nl_throttle('ip', $ip, 3600)                > $cfg['lim_ip_hour'])     nl_json_neutral();
    if (nl_throttle('ipd', $ip, 86400)              > $cfg['lim_ip_day'])      nl_json_neutral();
    if (nl_throttle('em', $email, 86400)            > $cfg['lim_email_day'])   nl_json_neutral();

    $db = nl_db();
    // Wortlaut der aktuellen Einwilligung archivieren (idempotent) — muss VOR
    // dem Anlegen des Datensatzes passieren, damit der Nachweis lückenlos ist.
    nl_register_consent_text();

    $st = $db->prepare('SELECT id, status, mail_send_count, last_mail_at
                          FROM nl_subscriber WHERE email = ?');
    $st->execute([$email]);
    $row = $st->fetch();

    /* --- 6. Bereits bestätigt: NIE erneut mailen ----------------------- */
    // Sonst wäre das Formular ein Werkzeug, um Abonnenten zuzumüllen.
    if ($row && $row['status'] === 'confirmed') {
        nl_log($email, 'signup', 'already_confirmed_noop');
        nl_json_neutral();
    }

    /* --- 7. Harte Obergrenze pro Adresse ------------------------------- */
    if ($row && (int)$row['mail_send_count'] >= (int)$cfg['lim_email_total']) {
        nl_log($email, 'signup', 'capped');
        nl_json_neutral();
    }
    // Pending + gerade erst gemailt -> nicht erneut senden (Doppelklick/Retry)
    if ($row && $row['status'] === 'pending' && $row['last_mail_at'] !== null
        && strtotime((string)$row['last_mail_at']) > time() - 600) {
        nl_json_neutral();
    }

    /* --- 8. Token erzeugen, nur Hash speichern ------------------------- */
    [$selector, $verifier, $token, $tokenHash] = nl_make_token();
    $expires = date('Y-m-d H:i:s', time() + (int)$cfg['token_ttl_hours'] * 3600);

    if ($row) {
        $db->prepare(
            'UPDATE nl_subscriber
                SET status = "pending", verticals = ?, token_selector = ?, token_hash = ?,
                    token_expires_at = ?, consent_version = ?, consent_text_hash = ?,
                    signup_at = ?, signup_ip = ?, signup_ua = ?, unsubscribed_at = NULL
              WHERE id = ?'
        )->execute([$verticalsJson, $selector, $tokenHash, $expires,
                    $cfg['consent_version'], hash('sha256', $cfg['consent_text']),
                    $now, $ip, nl_ua(), $row['id']]);
    } else {
        try {
            $db->prepare(
                'INSERT INTO nl_subscriber
                   (email, status, verticals, token_selector, token_hash, token_expires_at,
                    consent_version, consent_text_hash, signup_at, signup_ip, signup_ua)
                 VALUES (?, "pending", ?, ?, ?, ?, ?, ?, ?, ?, ?)'
            )->execute([$email, $verticalsJson, $selector, $tokenHash, $expires,
                        $cfg['consent_version'], hash('sha256', $cfg['consent_text']),
                        $now, $ip, nl_ua()]);
        } catch (PDOException $e) {
            if (($e->errorInfo[1] ?? 0) === 1062) nl_json_neutral();   // Race: parallel angelegt
            throw $e;
        }
    }
    nl_log($email, 'signup', 'v=' . $cfg['consent_version']);

    /* --- 9. Versand; Fehler bleibt für den Cron-Retry stehen ----------- */
    if (nl_send_confirm_mail($email, $token)) {
        $db->prepare('UPDATE nl_subscriber
                         SET mail_send_count = mail_send_count + 1, last_mail_at = NOW(),
                             mail_last_error = NULL
                       WHERE email = ?')->execute([$email]);
        nl_log($email, 'mail_sent');
    } else {
        $db->prepare('UPDATE nl_subscriber SET mail_last_error = "send_failed" WHERE email = ?')
           ->execute([$email]);
        nl_log($email, 'mail_failed');
    }
} catch (Throwable $e) {
    error_log('subscribe.php: ' . $e->getMessage());   // Details nie an den Client
}

nl_json_neutral();
