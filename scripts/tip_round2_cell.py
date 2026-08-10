# =============================================================================
#  PATSTAT-RUNDE 2  —  NEUN NOTEBOOK-ZELLEN FÜR tip.epo.org
#  (Owner-Auftrag 2026-08-10, Issue #75; SQL dokumentiert in
#   scripts/tip_queries_round2.sql)
# =============================================================================
#
#  SO BENUTZT DU DIESE DATEI
#  -------------------------
#  * Jeder Block zwischen "ANFANG ZELLE n" und "ENDE ZELLE n" kommt in EINE
#    eigene Zelle im Notebook. Die Kommentarzeilen (#) dürfen mitkopiert
#    werden, die stören nicht.
#  * ZELLE 1 muss ZUERST laufen — sie baut die Verbindung auf und definiert
#    CPC_CTE und die Hilfsfunktion run(), die alle anderen Zellen brauchen.
#  * Danach sind ZELLE 2 bis ZELLE 9 voneinander unabhängig: Reihenfolge egal,
#    einzeln wiederholbar, eine kaputte Zelle blockiert die anderen nicht.
#  * Jede Zelle schreibt genau eine CSV ins Notebook-Verzeichnis und zeigt
#    die ersten fünf Zeilen zur Kontrolle.
#  * Am Ende: alle acht CSVs im Datei-Browser links per Rechtsklick
#    herunterladen und per Taildrop schicken.
#
#  ZELLEN-ÜBERSICHT (Zeilennummern in dieser Datei)
#  -----------------------------------------------
#    ZELLE 1:  Zeile  44 bis 106   Setup (zuerst!)
#    ZELLE 2:  Zeile 109 bis 153   Q5  npl_share
#    ZELLE 3:  Zeile 156 bis 210   Q6  survival
#    ZELLE 4:  Zeile 213 bis 244   Q7  country_race
#    ZELLE 5:  Zeile 247 bis 281   Q8  internationalization
#    ZELLE 6:  Zeile 284 bis 322   Q9  collaborations
#    ZELLE 7:  Zeile 325 bis 361   Q10 cpc_groups
#    ZELLE 8:  Zeile 364 bis 394   Q11 nace2_bridge
#    ZELLE 9:  Zeile 397 bis 427   Q12 ep_oppositions
#
#  NANO-TIPPS
#  ----------
#    nano -l scripts/tip_round2_cell.py   Datei mit Zeilennummern öffnen
#    Strg+_                               zu einer Zeilennummer springen
#    Alt+A                                Markierung beginnen
#    Alt+6                                markierten Bereich kopieren
#    Strg+W                               suchen (z. B. nach "ANFANG ZELLE 5")
#
# =============================================================================


# #############################################################################
# ANFANG ZELLE 1 von 9  —  SETUP.  Muss zuerst laufen, danach nie wieder
#                          (außer der Kernel wurde neu gestartet).
# #############################################################################
from epo.tipdata.patstat import PatstatClient
import pandas as pd
import time

patstat = PatstatClient(env='PROD')

# Unsere 26 kuratierten Technologie-Achsen (= build_cpc_insights.CURATED
# plus B64G Raumfahrt, H10K organische Elektronik, H01L Halbleiter).
CPCS = ("'A01H','A23C','A23J','A23L','A61B','A61K','A63F','B09B','B25J','B33Y',"
        "'C12N','C25B','D01F','E04B','F03D','G06N','G06Q','G09B','G16H','G16Y',"
        "'H01M','H02S','H04W','B64G','H10K','H01L'")

# Gemeinsamer Kopf fast aller Abfragen: Anmeldungen -> CPC-Achse.
CPC_CTE = f"""
WITH cpc AS (
  SELECT DISTINCT appln_id, SUBSTR(cpc_class_symbol, 1, 4) AS cpc_subclass
  FROM tls224_appln_cpc
  WHERE SUBSTR(cpc_class_symbol, 1, 4) IN ({CPCS})
)"""


def ursache(e, tiefe=6):
    """Die echte BigQuery-Meldung aus der Exception-Kette holen.

    Der TIP-Client faengt BadRequest ab und wirft darueber eine generische
    QueryException ("BigQuery Standard SQL dialect is currently selected"),
    die nichts ueber den Fehler sagt — der Klartext steckt nur in
    __context__. Ohne diese Funktion ist jeder SQL-Fehler blind.
    """
    teile, cur = [], e
    while cur is not None and tiefe:
        teile.append(f"{type(cur).__name__}: {cur}")
        cur, tiefe = (cur.__context__ or cur.__cause__), tiefe - 1
    return "\n--- verursacht durch ---\n".join(teile)


def run(name, sql):
    """Abfrage ausfuehren, als <name>.csv speichern, Ergebnis melden.

    Faengt Fehler ab und gibt sie lesbar aus, damit ein Problem in einer
    Zelle nicht den Kernel-Zustand oder die anderen Abfragen stoert.
    """
    t0 = time.time()
    try:
        df = pd.DataFrame(patstat.sql_query(sql, use_legacy_sql=False))
        df.to_csv(f"{name}.csv", index=False)
        print(f"OK — {name}: {len(df):,} Zeilen in {time.time()-t0:.0f}s "
              f"-> {name}.csv\n")
        print(df.head(5).to_string(max_colwidth=40))
        return df
    except Exception as e:
        print(f"FEHLER bei {name} nach {time.time()-t0:.0f}s:\n{ursache(e)}")
        return None


print("Setup fertig. Verbindung steht, run() ist definiert.")
# #############################################################################
# ENDE ZELLE 1
# #############################################################################


# #############################################################################
# ANFANG ZELLE 2 von 9  —  Q5  WISSENSCHAFTS-VERKNÜPFUNG   -> npl_share.csv
#
#   Misst je Technologie und Jahr, welcher Anteil der zitierten Literatur
#   wissenschaftliche Papers sind (statt anderer Patente) und wie viele Tage
#   im Median zwischen Paper und zitierendem Patent liegen.
#   Produktnutzen: belegt die Kette Research-Tier -> Patent-Tier mit Zahlen.
#
#   ACHTUNG: langsamste Abfrage (Zitationstabelle ~1 Mrd. Zeilen).
#   Mehrere Minuten sind normal — nicht abbrechen.
# #############################################################################
sql_npl = f"""
{CPC_CTE},
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
ORDER BY 1, 2
"""

run("npl_share", sql_npl)
# #############################################################################
# ENDE ZELLE 2
# #############################################################################


# #############################################################################
# ANFANG ZELLE 3 von 9  —  Q6  ÜBERLEBENSKURVEN            -> survival.csv
#
#   Für erteilte Patente der Anmeldejahrgänge 2000-2015: in welchem Alter
#   werden sie fallengelassen (ST.27-Kategorie H, "IP right ceased")?
#   cohort_size steht auf jeder Zeile und ist der Nenner für die Kurve.
#   Produktnutzen: die ehrliche patentseitige "Faded Hype"-Messung —
#   kurze Haltedauer heißt, das Feld überzeugt seine eigenen Anmelder nicht.
#
#   ACHTUNG: zweitlangsamste Abfrage (Rechtsstandstabelle ~500 Mio. Zeilen).
# #############################################################################
sql_survival = f"""
{CPC_CTE},
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
ORDER BY 1, 2, 4
"""

run("survival", sql_survival)
# #############################################################################
# ENDE ZELLE 3
# #############################################################################


# #############################################################################
# ANFANG ZELLE 4 von 9  —  Q7  LÄNDER-RENNEN             -> country_race.csv
#
#   Patentfamilien je Technologie, Anmeldejahr und Sitzland des Anmelders
#   (2010-2023). Länder mit weniger als 25 Familien fallen raus, damit die
#   Datei klein bleibt.
#   Produktnutzen: "wer gewinnt Anteile" — Kurven fürs Geopolitik-Thema.
# #############################################################################
sql_country = f"""
{CPC_CTE},
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
ORDER BY 1, 2, 4 DESC
"""

run("country_race", sql_country)
# #############################################################################
# ENDE ZELLE 4
# #############################################################################


# #############################################################################
# ANFANG ZELLE 5 von 9  —  Q8  INTERNATIONALISIERUNG
#                                              -> internationalization.csv
#
#   Je Technologie und Jahr: wie viele Patentfamilien bei mehr als einem Amt
#   angemeldet wurden und wie viele den PCT-Weg (WO) genommen haben.
#   Produktnutzen: Auslandsanmeldungen kosten richtig Geld — ein ehrlicher
#   Indikator dafür, wie sehr Anmelder an ein Feld glauben.
# #############################################################################
sql_intl = f"""
{CPC_CTE},
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
ORDER BY 1, 2
"""

run("internationalization", sql_intl)
# #############################################################################
# ENDE ZELLE 5
# #############################################################################


# #############################################################################
# ANFANG ZELLE 6 von 9  —  Q9  UNI-FIRMA-KOLLABORATIONEN -> collaborations.csv
#
#   Top-15-Paare je Technologie: welche Universität meldet gemeinsam mit
#   welcher Firma an (Anmeldungen ab 2015, harmonisierte PSN-Namen).
#   Produktnutzen: Transfer 2.0 — nicht nur "wie viel Uni steckt drin",
#   sondern wer konkret mit wem baut.
# #############################################################################
sql_collab = f"""
{CPC_CTE},
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
ORDER BY 1, 2
"""

run("collaborations", sql_collab)
# #############################################################################
# ENDE ZELLE 6
# #############################################################################


# #############################################################################
# ANFANG ZELLE 7 von 9  —  Q10 SUB-TRENDS (CPC-GRUPPEN)    -> cpc_groups.csv
#
#   Zeitreihen eine Ebene feiner als unsere Achsen: Hauptgruppen wie G06N10
#   (Quantencomputing) getrennt von G06N3 (neuronale Netze). Nur Gruppen mit
#   mindestens 500 Familien insgesamt.
#   Produktnutzen: aufkommende Teilfelder werden sichtbar, die in der groben
#   Subclass-Summe untergehen.
# #############################################################################
sql_groups = f"""
WITH grp AS (
  SELECT a.docdb_family_id,
         SUBSTR(c.cpc_class_symbol, 1, 4) AS cpc_subclass,
         REPLACE(SPLIT(c.cpc_class_symbol, '/')[OFFSET(0)], ' ', '') AS cpc_group,
         EXTRACT(YEAR FROM a.appln_filing_date) AS filing_year
  FROM tls224_appln_cpc c
  JOIN tls201_appln a ON a.appln_id = c.appln_id
  WHERE SUBSTR(c.cpc_class_symbol, 1, 4) IN ({CPCS})
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
ORDER BY 1, 2, 3
"""

run("cpc_groups", sql_groups)
# #############################################################################
# ENDE ZELLE 7
# #############################################################################


# #############################################################################
# ANFANG ZELLE 8 von 9  —  Q11 NACE2-BRANCHENBRÜCKE       -> nace2_bridge.csv
#
#   Das gewichtete amtliche Mapping von Technologie auf Wirtschaftszweig,
#   inklusive Klartext-Bezeichnung der NACE2-Codes.
#   Produktnutzen: datenbasierte Brücke von den CPC-Achsen zu unseren acht
#   Verticals, statt die Zuordnung von Hand zu verdrahten.
# #############################################################################
sql_nace = f"""
{CPC_CTE},
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
ORDER BY 1, n.weighted_applications DESC
"""

run("nace2_bridge", sql_nace)
# #############################################################################
# ENDE ZELLE 8
# #############################################################################


# #############################################################################
# ANFANG ZELLE 9 von 9  —  Q12 EP-EINSPRÜCHE            -> ep_oppositions.csv
#
#   Einspruchsbezogene Rechtsstandsereignisse am Europäischen Patentamt
#   (Codes 26* und 27*) je Technologie und Jahr — die Bedeutung jedes Codes
#   kommt als Klartext aus der amtlichen Tabelle TLS803, nicht aus Annahmen.
#   Produktnutzen: wo Wettbewerber Geld für Einsprüche ausgeben, steht
#   kommerzieller Wert — Konflikt-Intensität als Signal.
# #############################################################################
sql_opp = f"""
{CPC_CTE}
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
ORDER BY 1, 2, 3
"""

run("ep_oppositions", sql_opp)
# #############################################################################
# ENDE ZELLE 9  —  danach alle acht CSVs herunterladen und per Taildrop
#                  schicken. Fertig.
# #############################################################################
