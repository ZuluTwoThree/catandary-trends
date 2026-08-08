-- ============================================================================
-- PATSTAT-Abfragen für die EPO Technology Intelligence Platform (tip.epo.org)
-- ============================================================================
-- Zweck: die PATSTAT-Deltas, die unser BDDS-Eigenbestand NICHT hat, als kleine
-- gezielte Ergebnismengen ziehen — statt des 2.700-€-Bulk-Kaufs (Issue #7,
-- 2026-08-09). Workflow: Query in TIP ausführen → CSV exportieren → per
-- Taildrop an kiworkstation → Ingest übernimmt Claude.
--
-- Was unser Eigenbestand schon kann (Re-Parse, Paket C): family-id,
-- Anmelder-ROHnamen. Was NUR PATSTAT hat und diese Queries holen:
--   Q1  harmonisierte Anmelder (PSN) + Sektor je Technologie → "führende Firmen"
--   Q2  Uni-vs-Firma-Anteil je Technologie & Jahr → Transfer-Signal
--   Q3  Rechtsstands-Ereignisse (Lapse/Withdrawal) je Technologie & Jahr
--       → Desinvestitions-Kurve ("Faded Hype" auf der Patentseite)
--   Q4  Sanity: Publikations-Volumen je Amt & Jahr (Abgleich mit unserem Bestand)
--
-- Die CPC-Liste = unsere kuratierten Technologie-Achsen (build_cpc_insights.py).
-- SQL-Dialekt: Standard-SQL; je nach TIP-Engine ggf. SUBSTR/LEFT bzw.
-- EXTRACT(YEAR …) anpassen. Ergebnisgrößen sind bewusst klein (Tausende Zeilen).
-- ============================================================================

-- Gemeinsame CPC-Achsen (in jede Query einsetzen):
--   'A01H','A23C','A23J','A23L','A61B','A61K','A63F','B09B','B25J','B33Y',
--   'C12N','C25B','D01F','E04B','F03D','G06N','G06Q','G09B','G16H','G16Y',
--   'H01M','H02S','H04W'
--   + neue Themes: 'G06N' (Quantum via G06N10 s. u.), 'B64G' (Raumfahrt),
--     'H10K'/'H01L' (Halbleiter)

-- ----------------------------------------------------------------------------
-- Q1 · Führende Anmelder je Technologie (harmonisiert, mit Sektor), ab 2015
--      → CSV: leading_applicants.csv   (~ 23 Achsen × 50 Zeilen)
-- ----------------------------------------------------------------------------
WITH cpc AS (
  SELECT appln_id, SUBSTR(cpc_class_symbol, 1, 4) AS cpc_subclass
  FROM tls224_appln_cpc
  WHERE SUBSTR(cpc_class_symbol, 1, 4) IN
    ('A01H','A23C','A23J','A23L','A61B','A61K','A63F','B09B','B25J','B33Y',
     'C12N','C25B','D01F','E04B','F03D','G06N','G06Q','G09B','G16H','G16Y',
     'H01M','H02S','H04W','B64G','H10K','H01L')
  GROUP BY appln_id, SUBSTR(cpc_class_symbol, 1, 4)
),
ranked AS (
  SELECT c.cpc_subclass, p.psn_name, p.psn_sector, p.person_ctry_code,
         COUNT(DISTINCT a.docdb_family_id) AS families,
         ROW_NUMBER() OVER (PARTITION BY c.cpc_subclass
                            ORDER BY COUNT(DISTINCT a.docdb_family_id) DESC) AS rn
  FROM cpc c
  JOIN tls201_appln a      ON a.appln_id = c.appln_id
                          AND a.appln_filing_date >= DATE '2015-01-01'
  JOIN tls207_pers_appln pa ON pa.appln_id = a.appln_id AND pa.applt_seq_nr > 0
  JOIN tls206_person p      ON p.person_id = pa.person_id
  GROUP BY c.cpc_subclass, p.psn_name, p.psn_sector, p.person_ctry_code
)
SELECT cpc_subclass, rn AS rank, psn_name, psn_sector, person_ctry_code, families
FROM ranked WHERE rn <= 50
ORDER BY cpc_subclass, rn;

-- ----------------------------------------------------------------------------
-- Q2 · Sektor-Anteile je Technologie & Anmeldejahr (Uni→Industrie-Transfer)
--      → CSV: sector_shares.csv   (~ 26 Achsen × ~15 Jahre × Sektoren)
-- ----------------------------------------------------------------------------
SELECT SUBSTR(cp.cpc_class_symbol, 1, 4)      AS cpc_subclass,
       EXTRACT(YEAR FROM a.appln_filing_date) AS filing_year,
       p.psn_sector,
       COUNT(DISTINCT a.docdb_family_id)      AS families
FROM tls224_appln_cpc cp
JOIN tls201_appln a       ON a.appln_id = cp.appln_id
                         AND a.appln_filing_date >= DATE '2010-01-01'
JOIN tls207_pers_appln pa ON pa.appln_id = a.appln_id AND pa.applt_seq_nr > 0
JOIN tls206_person p      ON p.person_id = pa.person_id
WHERE SUBSTR(cp.cpc_class_symbol, 1, 4) IN
    ('A01H','A23C','A23J','A23L','A61B','A61K','A63F','B09B','B25J','B33Y',
     'C12N','C25B','D01F','E04B','F03D','G06N','G06Q','G09B','G16H','G16Y',
     'H01M','H02S','H04W','B64G','H10K','H01L')
GROUP BY 1, 2, 3
ORDER BY 1, 2, 3;

-- ----------------------------------------------------------------------------
-- Q3 · Rechtsstands-Ereignisse je Technologie & Jahr (Lapse/Withdrawal/Grant)
--      → CSV: legal_event_curve.csv
--      Ereignisklassen über TLS803 (event_code → Kategorie); wir zählen je
--      (Achse, Jahr, Kategorie) — die Lapse-Kurve ist das Desinvestitions-Signal.
-- ----------------------------------------------------------------------------
SELECT SUBSTR(cp.cpc_class_symbol, 1, 4)        AS cpc_subclass,
       EXTRACT(YEAR FROM l.event_publn_date)    AS event_year,
       ec.event_category_code                   AS event_category,
       COUNT(*)                                 AS events
FROM tls231_inpadoc_legal_event l
JOIN tls803_legal_event_code ec ON ec.event_auth = l.event_auth
                               AND ec.event_code = l.event_code
JOIN tls224_appln_cpc cp        ON cp.appln_id = l.appln_id
WHERE SUBSTR(cp.cpc_class_symbol, 1, 4) IN
    ('G06N','B64G','H10K','H01L','G16H','G09B','H01M','H02S','F03D','C12N','A61K')
  AND l.event_publn_date >= DATE '2012-01-01'
GROUP BY 1, 2, 3
ORDER BY 1, 2, 3;

-- ----------------------------------------------------------------------------
-- Q4 · Sanity/Abgleich: Publikationsvolumen je Amt & Jahr
--      → CSV: publn_volume.csv — Abgleich gegen unsere raw_entries-Dichte
--      (Dichte-Wächter-Kalibrierung; erwartbarer Peak-Versatz durch DOCDB-Lag)
-- ----------------------------------------------------------------------------
SELECT publn_auth, EXTRACT(YEAR FROM publn_date) AS publn_year, COUNT(*) AS publications
FROM tls211_pat_publn
WHERE publn_date >= DATE '2018-01-01' AND publn_auth IN ('US','EP','CN','WO','KR','JP','DE')
GROUP BY 1, 2
ORDER BY 1, 2;
