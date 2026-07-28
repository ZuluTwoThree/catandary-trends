<?php
declare(strict_types=1);
// /newsletter/_lib.php  – gemeinsame Helfer. Enthält selbst KEINE Secrets.

/**
 * Ort der Config.
 *
 * Auf Hetzner-Webhosting gibt es KEIN beschreibbares Verzeichnis oberhalb des
 * Docroots — gemessen am 2026-07-26: Docroot = /usr/www/users/<login>, das
 * darüberliegende /usr/www/users ist von allen Kunden geteilt und nicht
 * beschreibbar. Die Config liegt deshalb neben diesen Dateien und ist
 * doppelt geschützt:
 *   1. .htaccess verweigert den HTTP-Zugriff (siehe .htaccess.example)
 *   2. sie ist eine .php-Datei — Apache führt sie aus, statt den Quelltext
 *      auszuliefern; sie gibt per `return` nur ein Array zurück und
 *      produziert damit selbst bei direktem Aufruf keine Ausgabe.
 * Zusätzlich per FTP auf 600 setzen.
 */
function nl_cfg(): array
{
    static $cfg = null;
    if ($cfg === null) {
        $path = __DIR__ . '/nl_config.php';
        if (!is_readable($path)) {
            error_log('nl: config not readable at ' . $path);
            http_response_code(500);
            header('Content-Type: application/json');
            exit('{"error":"Configuration missing."}');
        }
        $cfg = require $path;
    }
    return $cfg;
}

function nl_db(): PDO
{
    static $pdo = null;
    if ($pdo === null) {
        $c = nl_cfg();
        $pdo = new PDO($c['db_dsn'], $c['db_user'], $c['db_pass'], [
            PDO::ATTR_ERRMODE            => PDO::ERRMODE_EXCEPTION,
            PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
            PDO::ATTR_EMULATE_PREPARES   => false,   // echte Server-Side Prepares
        ]);
    }
    return $pdo;
}

/**
 * Echte Client-IP. Auf Hetzner-Webhosting sitzt optional Varnish davor,
 * dann ist REMOTE_ADDR loopback/privat und die echte IP steht in X-Forwarded-For.
 * Wir nehmen NUR dann XFF, wenn REMOTE_ADDR nicht öffentlich ist – sonst wäre
 * der Header spoofbar und das Rate-Limit wertlos.
 */
function nl_client_ip(): string
{
    $remote = $_SERVER['REMOTE_ADDR'] ?? '0.0.0.0';
    $public = filter_var($remote, FILTER_VALIDATE_IP,
        FILTER_FLAG_NO_PRIV_RANGE | FILTER_FLAG_NO_RES_RANGE);
    if ($public !== false) {
        return $remote;
    }
    foreach (array_reverse(explode(',', $_SERVER['HTTP_X_FORWARDED_FOR'] ?? '')) as $cand) {
        $cand = trim($cand);
        if (filter_var($cand, FILTER_VALIDATE_IP,
            FILTER_FLAG_NO_PRIV_RANGE | FILTER_FLAG_NO_RES_RANGE) !== false) {
            return $cand;
        }
    }
    return $remote;
}

function nl_ua(): string
{
    return mb_substr((string)($_SERVER['HTTP_USER_AGENT'] ?? ''), 0, 255);
}

/**
 * Sorgt dafür, dass der aktuell gültige Einwilligungs-Wortlaut im Archiv steht.
 * Wird bei jeder Anmeldung aufgerufen — so kann nicht passieren, dass jemand
 * den Text in nl_config.php ändert, die Version hochzählt und der Wortlaut
 * nirgends festgehalten ist. INSERT IGNORE: existiert die Version schon,
 * passiert nichts (der Text einer Version wird NIE nachträglich geändert).
 */
function nl_register_consent_text(): void
{
    $c = nl_cfg();
    nl_db()->prepare(
        'INSERT IGNORE INTO nl_consent_text (version, text_hash, wording, language, valid_from)
         VALUES (?, ?, ?, ?, NOW())'
    )->execute([
        $c['consent_version'],
        hash('sha256', $c['consent_text']),
        $c['consent_text'],
        $c['consent_lang'] ?? 'de',
    ]);
}

function nl_log(string $email, string $event, ?string $detail = null): void
{
    $c = nl_cfg();
    nl_db()->prepare(
        'INSERT INTO nl_consent_log
           (email, event, occurred_at, ip, user_agent, consent_version, detail)
         VALUES (?, ?, NOW(), ?, ?, ?, ?)'
    )->execute([$email, $event, nl_client_ip(), nl_ua(), $c['consent_version'], $detail]);
}

/**
 * Ein Throttle-Treffer. Gibt die Trefferzahl im aktuellen Fenster zurück.
 * Bucket-Schlüssel sind HMACs -> im Rate-Limit-Table steht keine Klartext-PII.
 */
function nl_throttle(string $kind, string $value, int $windowSeconds): int
{
    $bucket = $kind . ':' . substr(
        hash_hmac('sha256', strtolower($value) . '|' . $windowSeconds, nl_cfg()['app_secret']), 0, 40
    );
    $db = nl_db();
    $db->prepare(
        'INSERT INTO nl_throttle (bucket, window_start, hits)
         VALUES (?, NOW(), 1)
         ON DUPLICATE KEY UPDATE
           hits         = IF(window_start < (NOW() - INTERVAL ? SECOND), 1, hits + 1),
           window_start = IF(window_start < (NOW() - INTERVAL ? SECOND), NOW(), window_start)'
    )->execute([$bucket, $windowSeconds, $windowSeconds]);

    $st = $db->prepare('SELECT hits FROM nl_throttle WHERE bucket = ?');
    $st->execute([$bucket]);
    return (int)$st->fetchColumn();
}

/** token = "<selector>.<verifier>" – nur sha256(verifier) wird gespeichert. */
function nl_make_token(): array
{
    $selector = bin2hex(random_bytes(8));                       // 16 hex, nicht geheim
    $verifier = rtrim(strtr(base64_encode(random_bytes(32)), '+/', '-_'), '='); // 256 bit
    return [$selector, $verifier, $selector . '.' . $verifier, hash('sha256', $verifier)];
}

function nl_valid_email(string $email): bool
{
    if (strlen($email) > 254 || strpbrk($email, "\r\n") !== false) {
        return false;
    }
    if (!filter_var($email, FILTER_VALIDATE_EMAIL)) {
        return false;
    }
    $domain = substr(strrchr($email, '@') ?: '', 1);
    return $domain !== '' && (checkdnsrr($domain, 'MX') || checkdnsrr($domain, 'A'));
}

/** Bestätigungsmail über Resend. true = angenommen. */
function nl_send_confirm_mail(string $email, string $token): bool
{
    $c   = nl_cfg();
    $url = $c['site_url'] . '/newsletter/confirm.php?t=' . rawurlencode($token);
    $esc = htmlspecialchars($url, ENT_QUOTES);

    /* Sprache folgt der Seite, auf der eingewilligt wurde (Landing = englisch).
     * Bewusst KEINE Werbung, kein Logo, keine Inhaltsvorschau, kein Zählpixel:
     * Die Bestätigungsmail darf selbst keine Werbung sein, solange die
     * Einwilligung noch aussteht (OLG Celle 13 U 15/14; OLG Düsseldorf
     * I-15 U 64/15). Deshalb rein funktional. */
    $consentEsc = htmlspecialchars((string)$c['consent_text'], ENT_QUOTES, 'UTF-8');
    $hours      = (int)$c['token_ttl_hours'];

    $html = '<div style="font-family:system-ui,sans-serif;font-size:15px;line-height:1.6">'
          . '<p>Almost there - please confirm your subscription to the Catandary Trends '
          . 'newsletter:</p>'
          . '<p><a href="' . $esc . '">Confirm subscription</a></p>'
          . '<p style="color:#666;font-size:13px">You agreed to the following: "'
          . $consentEsc . '"</p>'
          . '<p style="color:#666;font-size:13px">The link is valid for ' . $hours
          . ' hours and can be used once. If you did not sign up, simply ignore this email - '
          . 'without your confirmation we will not send you anything and the signup data is '
          . 'deleted after 30 days.</p>'
          . '<p style="color:#666;font-size:13px">contact@catandary.de</p></div>';

    $payload = json_encode([
        'from'     => $c['mail_from'],
        'to'       => [$email],
        'reply_to' => $c['mail_reply_to'],
        'subject'  => 'Please confirm your subscription',
        'html'     => $html,
        'text'     => "Almost there - please confirm your subscription:\n$url\n\n"
                    . "You agreed to the following:\n\"{$c['consent_text']}\"\n\n"
                    . "The link is valid for {$hours} hours and can be used once.\n"
                    . "Did not sign up? Just ignore this email - without confirmation we send "
                    . "you nothing and delete the signup data after 30 days.\n\n"
                    . "contact@catandary.de",
    ], JSON_UNESCAPED_UNICODE);

    $ch = curl_init('https://api.resend.com/emails');
    curl_setopt_array($ch, [
        CURLOPT_POST           => true,
        CURLOPT_POSTFIELDS     => $payload,
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_TIMEOUT        => 10,
        CURLOPT_SSL_VERIFYPEER => true,
        CURLOPT_SSL_VERIFYHOST => 2,
        CURLOPT_HTTPHEADER     => [
            'Authorization: Bearer ' . $c['resend_api_key'],
            'Content-Type: application/json',
        ],
    ]);
    $res  = curl_exec($ch);
    $code = (int)curl_getinfo($ch, CURLINFO_HTTP_CODE);
    $err  = curl_error($ch);
    curl_close($ch);

    if ($code >= 200 && $code < 300) {
        return true;
    }
    error_log("resend failed http=$code err=$err body=" . substr((string)$res, 0, 200));
    return false;
}

/** Antwort ohne User-Enumeration: für jeden gültigen Input identisch. */
function nl_json_neutral(): never
{
    http_response_code(202);
    header('Content-Type: application/json; charset=utf-8');
    header('Cache-Control: no-store');
    echo json_encode([
        'ok'      => true,
        'message' => 'Wenn die Adresse gültig ist, haben wir eine Bestätigungs-E-Mail geschickt. '
                   . 'Bitte klicke den Link darin – erst dann bist du angemeldet.',
    ], JSON_UNESCAPED_UNICODE);
    exit;
}

/** Minimale Seite im Look der Landing (dark, inline, cookieless). */
function nl_page(string $title, string $headline, string $body): never
{
    header('Content-Type: text/html; charset=utf-8');
    header('Cache-Control: no-store');
    header("Content-Security-Policy: default-src 'none'; style-src 'unsafe-inline'; img-src 'self'");
    header('Referrer-Policy: no-referrer');   // Token darf nicht via Referer leaken
    header('X-Robots-Tag: noindex');
    $t = htmlspecialchars($title, ENT_QUOTES);
    $h = htmlspecialchars($headline, ENT_QUOTES);
    echo <<<HTML
<!doctype html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex"><title>$t</title>
<style>
:root{color-scheme:dark}
body{margin:0;min-height:100vh;display:grid;place-items:center;background:#0b0d10;color:#e8eaed;
     font:16px/1.6 ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;padding:24px}
main{max-width:34rem;text-align:center}
h1{font-size:1.6rem;font-weight:600;margin:0 0 .75rem;letter-spacing:-.01em}
p{color:#a8adb6;margin:.5rem 0}
a{color:#e8eaed}
.back{display:inline-block;margin-top:1.5rem;padding:.6rem 1.1rem;border:1px solid #2a2f36;
      border-radius:8px;text-decoration:none}
</style></head><body><main><h1>$h</h1>$body
<a class="back" href="/">Zurück zur Startseite</a></main></body></html>
HTML;
    exit;
}
