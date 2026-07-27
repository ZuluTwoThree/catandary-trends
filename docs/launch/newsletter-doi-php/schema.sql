-- Catandary Newsletter DOI – MySQL/MariaDB (Hetzner Webhosting S, 1 DB)
-- Alle Tabellen mit Prefix nl_, damit die eine erlaubte DB teilbar bleibt.

CREATE TABLE IF NOT EXISTS nl_subscriber (
  id                 INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  email              VARCHAR(254)     NOT NULL,          -- normalisiert (lowercase, getrimmt)
  status             ENUM('pending','confirmed','unsubscribed') NOT NULL DEFAULT 'pending',
  verticals          VARCHAR(255)     NOT NULL DEFAULT '[]',  -- JSON-Array, spiegelt Postgres

  -- DOI-Token: Split-Token (selector.verifier); nur der Verifier-Hash liegt in der DB
  token_selector     CHAR(16)         DEFAULT NULL,
  token_hash         CHAR(64)         DEFAULT NULL,      -- sha256(verifier), hex
  token_expires_at   DATETIME         DEFAULT NULL,

  -- Einwilligungs-Nachweis (Art. 7 Abs. 1 DSGVO / BGH I ZR 164/09)
  consent_version    VARCHAR(32)      NOT NULL,
  consent_text_hash  CHAR(64)         NOT NULL,          -- sha256 des exakten Einwilligungstexts
  signup_at          DATETIME         NOT NULL,
  signup_ip          VARCHAR(45)      DEFAULT NULL,
  signup_ua          VARCHAR(255)     DEFAULT NULL,
  confirmed_at       DATETIME         DEFAULT NULL,
  confirm_ip         VARCHAR(45)      DEFAULT NULL,
  confirm_ua         VARCHAR(255)     DEFAULT NULL,
  unsubscribed_at    DATETIME         DEFAULT NULL,
  unsubscribe_ip     VARCHAR(45)      DEFAULT NULL,

  -- Mail-Bombing-/Retry-Steuerung
  mail_send_count    SMALLINT UNSIGNED NOT NULL DEFAULT 0,
  last_mail_at       DATETIME         DEFAULT NULL,
  mail_last_error    VARCHAR(255)     DEFAULT NULL,

  updated_at         TIMESTAMP        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

  UNIQUE KEY uq_email (email),
  UNIQUE KEY uq_selector (token_selector),
  KEY idx_status (status, updated_at),
  KEY idx_pending_retry (status, mail_send_count, last_mail_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Append-only-Protokoll: der eigentliche Rechenschafts-Nachweis.
-- Wird NIE geupdatet, nur eingefügt (und nach Aufbewahrungsfrist gelöscht).
CREATE TABLE IF NOT EXISTS nl_consent_log (
  id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  email           VARCHAR(254) NOT NULL,
  event           ENUM('signup','mail_sent','mail_failed','confirm','confirm_failed',
                       'unsubscribe','export','purge') NOT NULL,
  occurred_at     DATETIME     NOT NULL,
  ip              VARCHAR(45)  DEFAULT NULL,
  user_agent      VARCHAR(255) DEFAULT NULL,
  consent_version VARCHAR(32)  DEFAULT NULL,
  detail          VARCHAR(255) DEFAULT NULL,
  KEY idx_email (email, occurred_at),
  KEY idx_time (occurred_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Wortlaut-Archiv der Einwilligungstexte.
--
-- WARUM DAS NÖTIG IST: nl_subscriber speichert nur consent_version + einen
-- sha256-Hash. Der Hash beweist zwar, dass der Text unverändert ist, lässt ihn
-- aber nicht rekonstruieren. Die DSK-Orientierungshilfe Direktwerbung (Ziff.
-- 3.3) verlangt jedoch, die Erklärung "vollständig und im Wortlaut" jederzeit
-- ausdruckbar vorzuhalten — ein Hash genügt ausdrücklich nicht, ebenso wenig
-- die IP-Adresse allein. Ohne diese Tabelle hinge der Nachweis daran, dass die
-- alte nl_config.php aufbewahrt wird; das ist kein belastbares Archiv.
--
-- Bei JEDER Textänderung: neue Zeile mit neuer Version anlegen und
-- consent_version in nl_config.php hochzählen. Alte Zeilen NIE ändern.
CREATE TABLE IF NOT EXISTS nl_consent_text (
  version     VARCHAR(32)  NOT NULL PRIMARY KEY,
  text_hash   CHAR(64)     NOT NULL,          -- sha256(wording), = consent_text_hash
  wording     TEXT         NOT NULL,          -- der exakte Text am Formular
  language    CHAR(2)      NOT NULL DEFAULT 'de',
  valid_from  DATETIME     NOT NULL,
  valid_until DATETIME     DEFAULT NULL       -- gesetzt, sobald eine neue Version gilt
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Rate-Limiting ohne Redis. Enthält KEINE Klartext-PII (nur HMAC-Buckets).
CREATE TABLE IF NOT EXISTS nl_throttle (
  bucket       VARCHAR(96) NOT NULL PRIMARY KEY,   -- 'ip:<hmac>' | 'em:<hmac>' | 'global'
  window_start DATETIME    NOT NULL,
  hits         INT UNSIGNED NOT NULL DEFAULT 0,
  KEY idx_window (window_start)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
