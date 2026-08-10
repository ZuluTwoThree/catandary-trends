-- ============================================================================
-- PATSTAT-Abfragen Runde 2 für die EPO Technology Intelligence Platform
-- ============================================================================
-- Owner-Auftrag 2026-08-10: alle acht vorgeschlagenen Auswertungen für den
-- Patent Explorer holen. Runde 1 (tip_queries.sql) lieferte harmonisierte
-- Anmelder, Sektor-Anteile, Legal-Event-Zählung und Publikationsvolumen.
--
-- Workflow unverändert: Zelle aus scripts/tip_round2_cell.py ins TIP-Notebook
-- kopieren → CSVs entstehen → per Taildrop an kiworkstation → Ingest via
-- scripts/ingest_tip_round2.py.
--
-- Engine: TIP läuft auf BigQuery. Standard-SQL zwingend
-- (`use_legacy_sql=False`), BigQuery-Spezifika hier: APPROX_QUANTILES(...)
-- [SAFE_OFFSET(50)] statt MEDIAN, SPLIT()/DATE_DIFF() statt SUBSTRING-Arithmetik.
--
-- Q5  Wissenschafts-Verknüpfung  → npl_share (NPL-Zitationsanteil + Paper→Patent-Lag)
-- Q6  Überlebenskurven           → survival (Alter beim Fallenlassen je Kohorte)
-- Q7  Länder-Rennen              → country_race
-- Q8  Internationalisierung      → internationalization
-- Q9  Uni-Firma-Kollaborationen  → collaborations
-- Q10 Sub-Trends (CPC-Gruppen)   → cpc_groups
-- Q11 NACE2-Branchenbrücke       → nace2_bridge
-- Q12 EP-Einsprüche              → ep_oppositions
--
-- Kuratierte CPC-Achsen (identisch zu Runde 1 / build_cpc_insights.CURATED
-- + B64G/H10K/H01L):
--   'A01H','A23C','A23J','A23L','A61B','A61K','A63F','B09B','B25J','B33Y',
--   'C12N','C25B','D01F','E04B','F03D','G06N','G06Q','G09B','G16H','G16Y',
--   'H01M','H02S','H04W','B64G','H10K','H01L'
--
-- Laufzeit-Hinweis: Q5 und Q6 fassen die großen Zitations-/Legal-Event-
-- Tabellen an (TLS212 ~1 Mrd., TLS231 ~500 Mio. Zeilen) und brauchen am
-- längsten; die Ergebnismengen bleiben trotzdem klein (Aggregate).
-- ============================================================================

-- ----------------------------------------------------------------------------
-- Q5 · Wissenschafts-Verknüpfung: Anteil Nicht-Patent-Literatur an allen
--      Zitationen je Achse & Publikationsjahr + Median-Lag Paper→Patent.
--      → npl_share.csv   Produkt: misst, wie forschungsgetrieben ein Feld ist,
--        und wie lange Wissenschaft bis ins Patent braucht (Lead-Time-Beleg für
--        die Innovation-Chain Research-Tier → Patent-Tier).
-- ----------------------------------------------------------------------------
WITH cpc AS (
  SELECT DISTINCT appln_id, SUBSTR(cpc_class_symbol, 1, 4) AS cpc_subclass
  FROM tls224_appln_cpc
  WHERE SUBSTR(cpc_class_symbol, 1, 4) IN (/* CPC-Liste */)
),
cit AS (
  SELECT p.appln_id,
         EXTRACT(YEAR FROM p.publn_date) AS publn_year,
         p.publn_date,
         c.cited_npl_publn_id,
         n.npl_publn_date
  FROM tls212_citation c
  JOIN tls211_pat_publn p ON p.pat_publn_id = c.pat_publn_id
  LEFT JOIN tls214_npl_publn n ON n.npl_publn_id = c.cited_npl_publn_id
  WHERE p.publn_date >= DATE '2010-01-01'
)
SELECT k.cpc_subclass,
       c.publn_year,
       COUNT(*) AS citations,
       SUM(CASE WHEN c.cited_npl_publn_id > 0 THEN 1 ELSE 0 END) AS npl_citations,
       APPROX_QUANTILES(
         CASE WHEN c.cited_npl_publn_id > 0
               AND c.npl_publn_date IS NOT NULL
               AND c.npl_publn_date > DATE '1950-01-01'
               AND c.npl_publn_date <= c.publn_date
              THEN DATE_DIFF(c.publn_date, c.npl_publn_date, DAY) END,
         100)[SAFE_OFFSET(50)] AS median_lag_days
FROM cit c
JOIN cpc k ON k.appln_id = c.appln_id
GROUP BY 1, 2
ORDER BY 1, 2;

-- ----------------------------------------------------------------------------
-- Q6 · Überlebenskurven: in welchem Alter erteilte Patente fallengelassen
--      werden (ST.27-Kategorie H = "IP right ceased"), je Achse & Anmeldekohorte.
--      → survival.csv   Produkt: die ehrliche patentseitige "Faded Hype"-
--        Messung — kurze Haltedauer = Feld überzeugt seine Anmelder nicht mehr.
--      cohort_size steht auf jeder Zeile (Nenner für die Kurve).
-- ----------------------------------------------------------------------------
WITH cpc AS (
  SELECT DISTINCT appln_id, SUBSTR(cpc_class_symbol, 1, 4) AS cpc_subclass
  FROM tls224_appln_cpc
  WHERE SUBSTR(cpc_class_symbol, 1, 4) IN (/* CPC-Liste */)
),
grants AS (
  SELECT k.cpc_subclass, a.appln_id, a.appln_filing_date,
         EXTRACT(YEAR FROM a.appln_filing_date) AS filing_year
  FROM tls201_appln a
  JOIN cpc k ON k.appln_id = a.appln_id
  WHERE a.granted = 'Y'
    AND a.appln_filing_date BETWEEN DATE '2000-01-01' AND DATE '2015-12-31'
),
cease AS (
  SELECT l.appln_id, MIN(l.event_publn_date) AS first_cease
  FROM tls231_inpadoc_legal_event l
  JOIN grants g ON g.appln_id = l.appln_id
  JOIN tls803_legal_event_code ec
    ON ec.event_auth = l.event_auth AND ec.event_code = l.event_code
  WHERE ec.event_category_code = 'H'
    AND l.event_publn_date > DATE '1990-01-01'
  GROUP BY 1
),
cohort AS (
  SELECT cpc_subclass, filing_year, COUNT(*) AS cohort_size
  FROM grants GROUP BY 1, 2
),
ages AS (
  SELECT g.cpc_subclass, g.filing_year,
         CAST(FLOOR(DATE_DIFF(c.first_cease, g.appln_filing_date, DAY) / 365.25) AS INT64) AS age_years,
         COUNT(*) AS cessations
  FROM grants g
  JOIN cease c ON c.appln_id = g.appln_id
  WHERE c.first_cease > g.appln_filing_date
  GROUP BY 1, 2, 3
)
SELECT co.cpc_subclass, co.filing_year, co.cohort_size, a.age_years, a.cessations
FROM cohort co
LEFT JOIN ages a ON a.cpc_subclass = co.cpc_subclass AND a.filing_year = co.filing_year
WHERE a.age_years IS NULL OR a.age_years BETWEEN 0 AND 25
ORDER BY 1, 2, 4;

-- ----------------------------------------------------------------------------
-- Q7 · Länder-Rennen je Technologie & Anmeldejahr (Anmelder-Sitzland).
--      → country_race.csv   Produkt: "wer gewinnt Anteile" — Kurven für das
--        Geopolitik-/Supply-Chain-Thema. HAVING >= 25 hält die Datei klein.
-- ----------------------------------------------------------------------------
WITH cpc AS (
  SELECT DISTINCT appln_id, SUBSTR(cpc_class_symbol, 1, 4) AS cpc_subclass
  FROM tls224_appln_cpc
  WHERE SUBSTR(cpc_class_symbol, 1, 4) IN (/* CPC-Liste */)
),
fam AS (
  SELECT DISTINCT k.cpc_subclass, a.docdb_family_id,
         EXTRACT(YEAR FROM a.appln_filing_date) AS filing_year,
         p.person_ctry_code
  FROM cpc k
  JOIN tls201_appln a ON a.appln_id = k.appln_id
                     AND a.appln_filing_date BETWEEN DATE '2010-01-01' AND DATE '2023-12-31'
  JOIN tls207_pers_appln pa ON pa.appln_id = a.appln_id AND pa.applt_seq_nr > 0
  JOIN tls206_person p ON p.person_id = pa.person_id
)
SELECT cpc_subclass, filing_year, person_ctry_code AS ctry, COUNT(*) AS families
FROM fam
WHERE person_ctry_code IS NOT NULL AND TRIM(person_ctry_code) <> ''
GROUP BY 1, 2, 3
HAVING COUNT(*) >= 25
ORDER BY 1, 2, 4 DESC;

-- ----------------------------------------------------------------------------
-- Q8 · Internationalisierung: Anteil Familien mit mehreren Ämtern bzw. PCT.
--      → internationalization.csv   Produkt: Auslandsanmeldungen kosten Geld —
--        ein ehrlicher Investitions-Confidence-Indikator je Feld und Jahr.
-- ----------------------------------------------------------------------------
WITH cpc AS (
  SELECT DISTINCT appln_id, SUBSTR(cpc_class_symbol, 1, 4) AS cpc_subclass
  FROM tls224_appln_cpc
  WHERE SUBSTR(cpc_class_symbol, 1, 4) IN (/* CPC-Liste */)
),
fam AS (
  SELECT k.cpc_subclass, a.docdb_family_id,
         MIN(EXTRACT(YEAR FROM a.earliest_filing_date)) AS filing_year,
         COUNT(DISTINCT a.appln_auth) AS n_auth,
         MAX(CASE WHEN a.appln_auth = 'WO' THEN 1 ELSE 0 END) AS has_pct
  FROM cpc k
  JOIN tls201_appln a ON a.appln_id = k.appln_id
  WHERE a.earliest_filing_date BETWEEN DATE '2010-01-01' AND DATE '2023-12-31'
  GROUP BY 1, 2
)
SELECT cpc_subclass, filing_year,
       COUNT(*) AS families,
       SUM(CASE WHEN n_auth >= 2 THEN 1 ELSE 0 END) AS multi_office_families,
       SUM(has_pct) AS pct_families,
       APPROX_QUANTILES(n_auth, 100)[SAFE_OFFSET(50)] AS median_offices
FROM fam
GROUP BY 1, 2
ORDER BY 1, 2;

-- ----------------------------------------------------------------------------
-- Q9 · Uni-Firma-Ko-Anmeldungen: Top-15-Paare je Achse (ab 2015).
--      → collaborations.csv   Produkt: Transfer 2.0 — nicht nur "wie viel Uni",
--        sondern wer konkret mit wem baut.
-- ----------------------------------------------------------------------------
WITH cpc AS (
  SELECT DISTINCT appln_id, SUBSTR(cpc_class_symbol, 1, 4) AS cpc_subclass
  FROM tls224_appln_cpc
  WHERE SUBSTR(cpc_class_symbol, 1, 4) IN (/* CPC-Liste */)
),
pers AS (
  SELECT DISTINCT k.cpc_subclass, a.docdb_family_id, p.psn_name, p.psn_sector
  FROM cpc k
  JOIN tls201_appln a ON a.appln_id = k.appln_id
                     AND a.appln_filing_date >= DATE '2015-01-01'
  JOIN tls207_pers_appln pa ON pa.appln_id = a.appln_id AND pa.applt_seq_nr > 0
  JOIN tls206_person p ON p.person_id = pa.person_id
  WHERE p.psn_name IS NOT NULL AND p.psn_name <> ''
),
pairs AS (
  SELECT u.cpc_subclass, u.psn_name AS university, c.psn_name AS company,
         COUNT(DISTINCT u.docdb_family_id) AS families
  FROM pers u
  JOIN pers c ON c.cpc_subclass = u.cpc_subclass
             AND c.docdb_family_id = u.docdb_family_id
  WHERE u.psn_sector LIKE '%UNIVERSITY%' AND c.psn_sector = 'COMPANY'
  GROUP BY 1, 2, 3
)
SELECT cpc_subclass, rn AS rank, university, company, families
FROM (SELECT p.*, ROW_NUMBER() OVER (PARTITION BY cpc_subclass
                                     ORDER BY families DESC) AS rn FROM pairs p)
WHERE rn <= 15
ORDER BY 1, 2;

-- ----------------------------------------------------------------------------
-- Q10 · Sub-Trends: CPC-Hauptgruppen-Serien innerhalb unserer Achsen.
--       → cpc_groups.csv   Produkt: unsere Subclass-Achsen sind teils zu grob
--         (G06N enthält Quantencomputing G06N10 UND neuronale Netze G06N3) —
--         das hier macht Teilfelder als eigene Kurven sichtbar.
-- ----------------------------------------------------------------------------
WITH grp AS (
  SELECT a.docdb_family_id,
         SUBSTR(c.cpc_class_symbol, 1, 4) AS cpc_subclass,
         REPLACE(SPLIT(c.cpc_class_symbol, '/')[OFFSET(0)], ' ', '') AS cpc_group,
         EXTRACT(YEAR FROM a.appln_filing_date) AS filing_year
  FROM tls224_appln_cpc c
  JOIN tls201_appln a ON a.appln_id = c.appln_id
  WHERE SUBSTR(c.cpc_class_symbol, 1, 4) IN (/* CPC-Liste */)
    AND a.appln_filing_date BETWEEN DATE '2012-01-01' AND DATE '2023-12-31'
),
agg AS (
  SELECT cpc_subclass, cpc_group, filing_year,
         COUNT(DISTINCT docdb_family_id) AS families
  FROM grp GROUP BY 1, 2, 3
),
big AS (
  SELECT cpc_group FROM agg GROUP BY 1 HAVING SUM(families) >= 500
)
SELECT a.cpc_subclass, a.cpc_group, a.filing_year, a.families
FROM agg a JOIN big b ON b.cpc_group = a.cpc_group
ORDER BY 1, 2, 3;

-- ----------------------------------------------------------------------------
-- Q11 · NACE2-Branchenbrücke: welche Wirtschaftszweige hinter einer
--       Technologie-Achse stehen (gewichtetes Mapping der EPO).
--       → nace2_bridge.csv   Produkt: die Brücke von CPC-Achsen zu unseren
--         acht Verticals — datenbasiert statt handverdrahtet.
-- ----------------------------------------------------------------------------
WITH cpc AS (
  SELECT DISTINCT appln_id, SUBSTR(cpc_class_symbol, 1, 4) AS cpc_subclass
  FROM tls224_appln_cpc
  WHERE SUBSTR(cpc_class_symbol, 1, 4) IN (/* CPC-Liste */)
),
n AS (
  SELECT k.cpc_subclass, na.nace2_code,
         COUNT(*) AS applications,
         SUM(na.weight) AS weighted_applications
  FROM cpc k
  JOIN tls229_appln_nace2 na ON na.appln_id = k.appln_id
  JOIN tls201_appln a ON a.appln_id = k.appln_id
                     AND a.appln_filing_date >= DATE '2010-01-01'
  GROUP BY 1, 2
),
lbl AS (SELECT DISTINCT nace2_code, nace2_descr FROM tls902_ipc_nace2)
SELECT n.cpc_subclass, n.nace2_code, l.nace2_descr,
       n.applications, n.weighted_applications
FROM n LEFT JOIN lbl l ON l.nace2_code = n.nace2_code
ORDER BY 1, n.weighted_applications DESC;

-- ----------------------------------------------------------------------------
-- Q12 · EP-Einsprüche je Achse & Jahr, mit amtlicher Code-Beschreibung.
--       → ep_oppositions.csv   Produkt: wo Wettbewerber Geld für Einsprüche
--         ausgeben, steht kommerzieller Wert — Konflikt-Intensität als Signal.
--       Codes 26* (Einspruch gefiltert/keiner) und 27* (Verfahrensausgang);
--       die Bedeutung kommt aus TLS803 statt aus Annahmen.
-- ----------------------------------------------------------------------------
WITH cpc AS (
  SELECT DISTINCT appln_id, SUBSTR(cpc_class_symbol, 1, 4) AS cpc_subclass
  FROM tls224_appln_cpc
  WHERE SUBSTR(cpc_class_symbol, 1, 4) IN (/* CPC-Liste */)
)
SELECT k.cpc_subclass,
       EXTRACT(YEAR FROM l.event_publn_date) AS event_year,
       l.event_code,
       ec.event_descr,
       COUNT(DISTINCT l.appln_id) AS applications
FROM tls231_inpadoc_legal_event l
JOIN cpc k ON k.appln_id = l.appln_id
LEFT JOIN tls803_legal_event_code ec
       ON ec.event_auth = l.event_auth AND ec.event_code = l.event_code
WHERE l.event_auth = 'EP'
  AND (l.event_code LIKE '26%' OR l.event_code LIKE '27%')
  AND l.event_publn_date >= DATE '2005-01-01'
GROUP BY 1, 2, 3, 4
ORDER BY 1, 2, 3;
