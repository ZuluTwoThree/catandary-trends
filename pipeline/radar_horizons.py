"""Horizont-Radar: berechnet H1/H2/H3 pro (Technologiefeld × Dimension × Jurisdiktion).

Ersetzt die Logik des alten Lead-Time-Radars, dessen Ringe die *Quellenherkunft*
eines Clusters abbildeten statt der Reife einer Technologie (siehe
docs/radar_redesign_proposal.md §1.1). Hier ist die Position eine
Handlungsempfehlung:

    H1 = handeln      — im Markt / zugelassen / etabliert
    H2 = aufbauen     — im Übergang, Pfad offen, erste Produkte
    H3 = beobachten   — Forschung / kein Zulassungspfad / keine Produkte
    None = unbekannt  — zu wenig Evidenz; die Zelle schweigt statt zu raten

Hybrid nach Dimension (Owner-Entscheidung 2026-07-30), weil kein einzelner
Mechanismus alle Dimensionen ehrlich abdeckt:

  technology  → CPC-Takeoff-Anker aus cpc_leadtime_summary, aber nur bei
                `reliable=1`; sonst semantischer Signalmix, der HART auf H2
                gedeckelt ist (Skalen-/Kostenreife ist aus Signalen nicht lesbar)
  regulatory  → Meilenstein-Gates pro Jurisdiktion, Sub-Typ granted/filed/
                forming/gap; die Jurisdiktion einer Zulassung kommt aus der
                genannten BEHÖRDE, nicht aus `regions`
  market      → Produktstart-Zählung pro Jurisdiktion + Handels-/Skalierungsmarker,
                in regulierten Domänen an die Zulassung gekoppelt
  adoption    → Nachfrage-/Verhaltenssignale pro Jurisdiktion

WICHTIG — zwei Datenfallen, die die Auswertung sonst verfälschen:

1. `trend_signal_type` hat ZWEI Herkünfte. Der Distill-Pfad
   (scripts/signal_batch.py, _distill_signal_type) leitet den Typ deterministisch
   aus der QUELLE ab und schreibt dabei `tags=[]` und `regions=[]`. Für 80 % der
   market_shift- und 45 % der funding-Zeilen ist der Typ also keine semantische
   Aussage. Würde man darauf aggregieren, misst man wieder Quellenkomposition —
   genau der Fehler des alten Radars. Deshalb zählt der Signalmix nur Zeilen mit
   nicht-leeren tags (Spalte `semantic` in load_scope_signals = LLM-Pfad). Die
   vier Typen regulation / product_launch /
   partnership / consumer_behavior stammen ausschließlich aus dem LLM-Pfad und
   sind zu ~100 % regionsgetaggt — sie tragen die Gates.

2. `sort_date` ist für 52 % der Zeilen NULL. Zeitachse ist immer
   raw_entries.published_date.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from datetime import date, datetime, timedelta

from .db import get_connection

log = logging.getLogger(__name__)

HORIZONS = ("H1", "H2", "H3")
DIMENSIONS = ("technology", "regulatory", "market", "adoption")

# Dimensionen, die keine Jurisdiktion kennen, werden unter '*' abgelegt und vom
# Read-Layer für jede Region ausgeliefert (Patentreife ist nicht regional).
REGION_BLIND = {"technology"}
ANY_REGION = "*"

# ---------------------------------------------------------------------------
# Jurisdiktions-Normalisierung
# ---------------------------------------------------------------------------
# `trends.regions` ist freier LLM-Text und uneinheitlich: 'US' / 'us' / 'USA' /
# 'United States' / 'California' / 'US-CA' bzw. 'EU' / 'Europe' / 'europe' /
# 'Germany' stehen unverbunden nebeneinander (Inventur 2026-07-30: 'global'
# 276.927 vs 'Global' 21.471). Ohne dieses Mapping zersplittern die Zellen.
_EU_MEMBERS = {
    "eu", "european union", "europe", "eea", "brussels",
    "germany", "france", "netherlands", "belgium", "spain", "italy", "denmark",
    "sweden", "finland", "austria", "poland", "ireland", "portugal", "greece",
    "czech republic", "czechia", "hungary", "romania", "bulgaria", "croatia",
    "slovakia", "slovenia", "estonia", "latvia", "lithuania", "luxembourg",
    "cyprus", "malta",
}
_US_TERMS = {
    "us", "usa", "u.s.", "u.s.a.", "united states", "united states of america",
    "north america", "america",
    # Bundesstaaten und Städte, die als Region auftauchen
    "california", "texas", "new york", "wisconsin", "delaware", "massachusetts",
    "florida", "illinois", "washington", "colorado", "georgia", "michigan",
    "minnesota", "iowa", "ohio", "oregon", "pennsylvania", "north carolina",
    "new jersey", "virginia", "arizona", "missouri", "tennessee", "maryland",
    "silicon valley", "san francisco", "boston", "chicago",
}
_UK_TERMS = {"uk", "u.k.", "united kingdom", "great britain", "britain",
             "england", "scotland", "wales", "northern ireland", "london"}
_GLOBAL_TERMS = {"global", "worldwide", "international", "world"}
_APAC_TERMS = {
    "apac", "asia", "asia-pacific", "asia pacific", "southeast asia",
    "china", "japan", "south korea", "korea", "singapore", "india", "taiwan",
    "hong kong", "thailand", "vietnam", "indonesia", "malaysia", "philippines",
    "australia", "new zealand", "oceania",
}

JURISDICTIONS = ("US", "EU", "UK", "IL", "APAC", "GLOBAL")


def normalize_region(raw: str) -> str | None:
    """Rohen regions-Eintrag auf einen Jurisdiktions-Code abbilden.

    Rückgabe None für Werte, die keiner geführten Jurisdiktion zuzuordnen sind
    (z. B. 'Latin America', 'Africa') — die zählen dann nur in den Scope-Total,
    nicht in eine Zelle. Bewusst kein Ratespiel: eine falsch zugeordnete
    Zulassung ist teurer als eine fehlende.
    """
    if not raw:
        return None
    k = raw.strip().lower().replace("_", " ").replace("-", " ")
    k = re.sub(r"\s+", " ", k)
    if k in _GLOBAL_TERMS:
        return "GLOBAL"
    if k in _US_TERMS or k.startswith("us "):
        return "US"
    if k in _EU_MEMBERS:
        return "EU"
    if k in _UK_TERMS:
        return "UK"
    if k in {"israel", "il", "tel aviv"}:
        return "IL"
    if k in _APAC_TERMS:
        return "APAC"
    return None


def regions_of(row) -> set[str]:
    """Normalisierte Jurisdiktionen eines Trends (kann mehrere sein)."""
    raw = row.get("regions")
    vals = json.loads(raw) if isinstance(raw, str) else (raw or [])
    out = {normalize_region(v) for v in vals if isinstance(v, str)}
    return {v for v in out if v}


# ---------------------------------------------------------------------------
# Regulatorik-Sub-Typ
# ---------------------------------------------------------------------------
# `trend_signal_type='regulation'` unterscheidet nicht zwischen "Konsultation
# eröffnet" und "Zulassung erteilt" — genau die H2/H1-Grenze der wichtigsten
# Dimension. Hier eine regelbasierte, prüfbare Nachklassifikation über Titel +
# Tags. Bewusst konservativ: nur eindeutige Zulassungsformulierungen zählen als
# GRANTED, alles Antrags-/Verfahrensartige ist PATHWAY.
REG_GRANTED = re.compile(
    r"\b(gras (status|clearance|approval|self-affirmed)?|"
    r"self-affirmed gras|"
    # Titel schreiben „No Questions“ Letter mit typografischen Anführungs-
    # zeichen — starre Wortgrenzen greifen dort nicht.
    r"no[\s\"‘’“”\']*questions[\s\"‘’“”\']*letter|"
    r"(receives?|granted|obtains?|earns?|wins?|secures?|gets?) [^.]{0,40}"
    r"(approval|authorisation|authorization|clearance|licence|license|certification)|"
    r"(approved|authorised|authorized|cleared|certified|permitted|licensed) (for|in|by|to)|"
    r"(fda|efsa|usda|ema|fsa|fsanz|mhlw|health canada) (clears?|cleared|approves?|approved|authorises?|authorized)|"
    r"first .{0,30}approval|"
    r"regulatory approval|approval (granted|obtained|secured)|"
    r"enters? into force|comes? into force|now in force|takes? effect)\b",
    re.I,
)
REG_PATHWAY = re.compile(
    r"\b(consultation|draft|proposal|proposes?|roadmap|framework|reform|"
    r"pending|submitted|submission|applies for|application|under review|"
    r"reviewing|novel food|pathway|guidance|pilot scheme|"
    r"seeks? approval|awaiting|in the pipeline|prioriti[sz]e|"
    r"strategy|standard[- ]setting|harmoni[sz]ation)\b",
    re.I,
)
# NUR echte Blockaden. Kalibrierlauf 2026-08-02: „Regulatory Uncertainty Shapes
# Global Gene Therapy Strategy" zählte als Blockade und setzte die EU-Zelle auf
# H3 — für ein Feld mit 11+ EMA-Zulassungen. Unsicherheit, Verzögerung, Hürden
# und Komplexität sind REIBUNG; sie verlangsamen einen offenen Weg, sie
# verschließen ihn nicht. Wer H3 („beobachten, kein Weg") behauptet, braucht ein
# Verbot, eine Ablehnung oder einen Entzug.
REG_GAP = re.compile(
    r"\b(no approval|not approved|never approved|approval denied|"
    r"ban(ned|s)?|prohibit(ed|s|ion)?|outlaw(ed|s)?|"
    r"reject(ed|s|ion)?|refus(ed|al)|withdraw(n|s|al)?|suspend(ed|s|sion)?|"
    r"revok(ed|es)|moratorium|halt(ed|s)? (sales|approval|use))\b",
    re.I,
)

REG_GRANTED_TAGS = {
    "regulatory approval", "regulatory_approval", "fda approval", "fda_approval",
    "drug approval", "drug_approval", "gras", "gras_status", "market authorization",
    "market_authorization", "novel food approval",
}

# Absichts-Guard: Formulierungen, die eine Zulassung ERSTREBEN oder FORDERN, statt
# sie zu melden. Ohne diesen Filter zählt „Coalition To Advance Regulatory
# Approval" als Zulassung — also genau das Gegenteil dessen, was es belegt.
REG_INTENT = re.compile(
    r"\b(to advance|advance[sd]? (the )?regulatory|campaign|coalition|call(s|ed)? for|"
    r"push(es|ed)? for|lobb(y|ies|ying)|urge[sd]?|demand(s|ed)?|"
    r"seek(s|ing)? |applies for|appl(y|ied) for|submits?|submitted|awaiting|"
    r"pave the way|path(way)? to|road ?map|toward|prepar(e|es|ing)|"
    # „Nähert sich der Zulassung" ist der Beleg, dass es sie NICHT gibt.
    # Kalibrierlauf 2026-07-31: „Impossible Foods Approaches EU Approval
    # Following Second Positive EFSA Opinion" galt als erteilte EU-Zulassung und
    # hob ein regulatorisch blockiertes Feld auf H1.
    r"approach(es|ed|ing)?|near(s|ing|ed)? (approval|authorisation|authorization)|"
    r"clos(e|es|ing) in on|on track (for|to)|steps? closer|"
    r"positive opinion|draft opinion|recommend(s|ed)? (approval|authorisation)|"
    r"could|would|may |might |propose[sd]?|plan(s|ned)? to|aims? to)\b",
    re.I,
)

# Zulassende Behörde → Jurisdiktion. Für die Regulatorik-Dimension ist DAS die
# Attribution, nicht `regions`: `regions` markiert den Sitz des Unternehmens bzw.
# den Handlungsort der Geschichte. Beispiel aus dem Kalibrierlauf 2026-07-30:
# „Vivici Secures FDA 'No Questions' Letter" trägt regions=[EU] (niederländische
# Firma), belegt aber eine US-Zulassung. Ohne Behörden-Attribution wandert eine
# US-Zulassung in die EU-Zelle und macht ein blockiertes Feld handlungsfähig.
AUTHORITY_JURISDICTION: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(fda|usda|fsis|gras|us ?da|food and drug administration)\b", re.I), "US"),
    (re.compile(r"\b(efsa|european commission|eu commission|dg sante|"
                r"european food safety|eu novel foods?|novel foods? regulation)\b", re.I), "EU"),
    (re.compile(r"\b(fsa|food standards agency|defra)\b", re.I), "UK"),
    (re.compile(r"\b(israeli? ministry of health|israel moh)\b", re.I), "IL"),
    (re.compile(r"\b(sfa|singapore food agency|fsanz|food standards australia|"
                r"mhlw|mfds|cfsa)\b", re.I), "APAC"),
]


# Zweiter Attributionsweg: die Jurisdiktion steht ausdrücklich im Text, ohne dass
# eine Behörde genannt wird — „First Precision Fermentation Dairy Approval In
# Israel" nennt kein Ministerium, ist aber eindeutig. Wird nur für bereits als
# 'granted' erkannte Signale ausgewertet und ist deshalb unkritisch.
JURISDICTION_PHRASE: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(u\.?s\.?|united states|american)[- ](gras|approval|clearance|"
                r"authorisation|authorization|approved)\b", re.I), "US"),
    (re.compile(r"\b(eu|european|europe)[- ](approval|clearance|authorisation|"
                r"authorization|approved)\b|\bnovel foods? (approval|authorisation)\b",
                re.I), "EU"),
    (re.compile(r"\b(in|for|across) israel\b|\bisraeli\b", re.I), "IL"),
    (re.compile(r"\b(uk|british)[- ](approval|clearance|authorisation|approved)\b|"
                r"\b(in|for) the uk\b", re.I), "UK"),
    (re.compile(r"\b(in|for) (singapore|japan|australia|new zealand|south korea|china)\b|"
                r"\bsingaporean\b", re.I), "APAC"),
]


def reg_authority(text: str) -> str | None:
    """Jurisdiktion einer Zulassung: genannte Behörde, sonst explizite Nennung."""
    for pat, juris in AUTHORITY_JURISDICTION:
        if pat.search(text):
            return juris
    for pat, juris in JURISDICTION_PHRASE:
        if pat.search(text):
            return juris
    return None


def reg_subtype(row) -> str:
    """Sub-Typ eines Regulatorik-Signals.

    'granted' — Zulassung erteilt / in Kraft                          → H1
    'filed'   — Antrag läuft, in Prüfung                              → H2
    'forming' — Pfad wird erst gebaut (Konsultation, Strategie, Ruf
                nach Reform) — noch kein nutzbarer Weg                → H3
    'gap'     — Lücke ausdrücklich benannt                            → H3

    Die Trennung 'filed' vs. 'forming' ist die eigentliche Kalibrierung: eine
    laufende Konsultation ist kein offener Zulassungsweg, sondern der Versuch,
    einen zu schaffen.
    """
    text = f"{row.get('title_en') or ''} {row.get('summary_en') or ''}"
    intent = bool(REG_INTENT.search(text))

    tags_raw = row.get("tags")
    tags = json.loads(tags_raw) if isinstance(tags_raw, str) else (tags_raw or [])
    tagset = {str(t).strip().lower() for t in tags}
    tag_hit = bool(tagset & REG_GRANTED_TAGS)

    # Ein Tag allein genügt nicht: der Text muss die Zulassung bestätigen und darf
    # sie nicht bloß anstreben.
    if (tag_hit or REG_GRANTED.search(text)) and not intent:
        return "granted"
    if re.search(r"\b(applies for|applied for|submitted|submission|under review|"
                 r"pending|in review|dossier|awaiting (approval|decision))\b",
                 text, re.I):
        return "filed"
    if REG_GAP.search(text):
        return "gap"
    if REG_PATHWAY.search(text) or intent:
        return "forming"
    return "forming"


# Marktreife-Marker: unterscheidet "Produkt angekündigt" von "im Handel".
# Pilot- und Demonstrationsanlagen belegen Machbarkeit, nicht Marktverfügbarkeit.
# Kalibrierlauf 2026-08-02: Direct Air Capture stand in der EU auf H1 („on the
# market"), gestützt auf Ucaneos Berliner Anlage — 150 t CO2/Jahr, kommerzieller
# Ausbau ab 2027. Das ist der Beweis, dass es funktioniert, nicht dass man es
# kaufen kann.
MARKET_PILOT = re.compile(
    r"\b(pilot|demonstration|demo (plant|facility|unit)|prototype|test ?bed|"
    r"first[- ]of[- ]a[- ]kind|proof of concept|trial (plant|run)|"
    r"pre[- ]commercial|research (facility|plant)|experiment)\b",
    re.I,
)

MARKET_SCALE = re.compile(
    r"\b(retail|shelves|shelf|supermarket|grocery|whole foods|walmart|tesco|"
    r"nationwide|roll ?out|scal(e|ing|es) (up|to)|commercial (launch|production|scale)|"
    r"mass production|distribution deal|listed (in|at)|available (in|at|now))\b",
    re.I,
)

# ---------------------------------------------------------------------------
# Schwellen
# ---------------------------------------------------------------------------
MIN_N_REGULATORY = 2      # unter 2 Regulatorik-Signalen: keine Aussage
# Eine EINZELNE Zulassungsmeldung trägt keine Jurisdiktions-Aussage: im
# Kalibrierlauf 2026-08-02 hob ein einziges fehlklassifiziertes Silage-Signal
# Precision Fermentation in der EU auf H1 (Scope-Verunreinigung, vgl. §7.3).
# Echte Zulassungen werden mehrfach berichtet — die acht US-GRAS-Freigaben
# ebenso wie die zwei israelischen.
MIN_N_GRANTED = 2
MIN_N_MARKET = 3
MIN_N_ADOPTION = 3
MIN_N_TECH_FALLBACK = 20  # ohne CPC-Anker: mindestens so viele semantische Signale
PATHWAY_WINDOW_MONTHS = 36   # Konsultationen veralten
LAUNCH_WINDOW_MONTHS = 36    # Produktstarts: nur die jüngeren zählen
# Zulassungen sind dauerhaft und werden ohne Fenster gezählt.
MARKET_TAKEOFF_SETTLED_YEARS = 2  # Markt-Takeoff muss so lange her sein für H1

# Etablierungs-Gate: kumulative Markt-Historie des Scopes statt Klassen-Takeoffs.
# Kalibriert 2026-08-02 an 8 Fällen: diffundierte Technologien (Li-Ion, Solar,
# EV, Wärmepumpen) haben ihr erstes aktives Marktjahr 2010-2012 und >=8 aktive
# Jahre; junge Felder (Quantum, Precision Fermentation, Solid-State, Cultivated
# Meat) starten 2020-2021 mit <=7 aktiven Jahren. Acht Jahre Abstand zwischen
# den Gruppen — die Schwellen liegen in der Mitte, nicht an der Kante.
# Die CPC-Klassen-Takeoffs sind als Alternative geprüft und verworfen: H01M
# meldet Patent-Takeoff "2026" (Frontfile-Artefakt), A23C Markt-Takeoff "2021"
# (die Alt-Protein-Welle selbst, nicht Milchwirtschaft).
ESTABLISHED_MIN_FIRST_AGE = 10   # erstes aktives Marktjahr min. so viele Jahre her
ESTABLISHED_MIN_ACTIVE_YEARS = 8 # Jahre mit >=3 Marktsignalen
ESTABLISHED_MIN_LAUNCHES = 30    # kumulative Produktstarts über die Historie
ESTABLISHED_YEAR_MIN_N = 3       # so viele Marktsignale machen ein Jahr "aktiv"

SCHEMA = """
CREATE TABLE IF NOT EXISTS radar_configs (
    id SERIAL PRIMARY KEY,
    slug TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    dimension_set TEXT NOT NULL DEFAULT 'strategic',
    regions JSONB DEFAULT '[]',
    window_months INTEGER DEFAULT 48,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS radar_scopes (
    id SERIAL PRIMARY KEY,
    config_id INTEGER REFERENCES radar_configs(id) ON DELETE CASCADE,
    slug TEXT NOT NULL,
    label TEXT NOT NULL,
    include_terms JSONB DEFAULT '[]',
    exclude_terms JSONB DEFAULT '[]',
    sort_order INTEGER DEFAULT 0,
    UNIQUE (config_id, slug)
);
CREATE TABLE IF NOT EXISTS radar_runs (
    id SERIAL PRIMARY KEY,
    config_id INTEGER REFERENCES radar_configs(id) ON DELETE CASCADE,
    n_scopes INTEGER,
    n_cells INTEGER,
    n_signals INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS radar_cells (
    id SERIAL PRIMARY KEY,
    run_id INTEGER REFERENCES radar_runs(id) ON DELETE CASCADE,
    scope_slug TEXT NOT NULL,
    dimension TEXT NOT NULL,
    region TEXT NOT NULL,
    horizon TEXT,                 -- 'H1'|'H2'|'H3'|NULL = unbekannt
    score REAL,                   -- stetige Reife 0..1, wo verfügbar
    n_signals INTEGER DEFAULT 0,
    method TEXT,                  -- 'cpc_takeoff'|'gates'|'semantic_mix'
    rationale TEXT,               -- Klartext-Begründung für das Readout
    evidence JSONB DEFAULT '[]',  -- Trend-IDs, die das Gate ausgelöst haben
    override_horizon TEXT,        -- Analyst-Override (Option E)
    override_note TEXT
);
CREATE INDEX IF NOT EXISTS idx_radar_cells_run ON radar_cells (run_id, scope_slug);
CREATE TABLE IF NOT EXISTS radar_scope_trends (
    run_id INTEGER REFERENCES radar_runs(id) ON DELETE CASCADE,
    scope_slug TEXT NOT NULL,
    trend_id INTEGER NOT NULL,
    PRIMARY KEY (run_id, scope_slug, trend_id)
);
CREATE INDEX IF NOT EXISTS idx_radar_scope_trends_trend
    ON radar_scope_trends (trend_id);
"""


def migrate() -> None:
    with get_connection() as conn:
        conn.executescript(SCHEMA)
        # Additiv nachgezogen (2026-07-30): regulierte Domänen koppeln Markt an
        # Zulassung. Idempotent, damit bestehende Installationen mitziehen.
        conn.executescript(
            "ALTER TABLE radar_configs ADD COLUMN IF NOT EXISTS regulated "
            "BOOLEAN DEFAULT false;"
        )
        # Query-Radare (2026-07-30). Alle Defaults erhalten das bisherige
        # Verhalten, damit die geseedeten Radare kein Re-Seed brauchen.
        conn.executescript(
            "ALTER TABLE radar_configs ADD COLUMN IF NOT EXISTS kind "
            "TEXT NOT NULL DEFAULT 'curated';"
            "ALTER TABLE radar_configs ADD COLUMN IF NOT EXISTS query_text TEXT;"
            "ALTER TABLE radar_configs ADD COLUMN IF NOT EXISTS archived "
            "BOOLEAN DEFAULT false;"
            "ALTER TABLE radar_scopes ADD COLUMN IF NOT EXISTS selector "
            "TEXT NOT NULL DEFAULT 'terms';"
            "ALTER TABLE radar_scopes ADD COLUMN IF NOT EXISTS query_text TEXT;"
            "ALTER TABLE radar_scopes ADD COLUMN IF NOT EXISTS phrase TEXT;"
            "ALTER TABLE radar_scopes ADD COLUMN IF NOT EXISTS centroid BYTEA;"
        )
        conn.commit()
    log.info("radar_* Tabellen migriert")


# Reifegrad-Rang: kleiner = reifer. Für die Kopplung regulierter Domänen.
_RANK = {"H1": 1, "H2": 2, "H3": 3}
_UNRANK = {1: "H1", 2: "H2", 3: "H3"}


def couple_market_to_regulation(market: dict, regulatory: dict, region: str) -> dict:
    """In regulierten Domänen kann der Markt nicht reifer sein als die Zulassung.

    Das ist die kausale Aussage hinter dem Owner-Beispiel: in der EU ist Precision
    Fermentation nicht deshalb H3, weil keine Produkte gemeldet würden, sondern
    weil ohne Zulassung keine geben KANN. Produktmeldungen mit EU-Bezug betreffen
    dann Auslandsstarts europäischer Firmen — die Kopplung fängt genau diese
    Fehlzuordnung ab, die `regions` allein nicht auflösen kann.
    """
    mh, rh = market.get("horizon"), regulatory.get("horizon")
    if not mh or not rh:
        return market
    if _RANK[mh] >= _RANK[rh]:
        return market
    capped = _UNRANK[_RANK[rh]]
    return {
        **market,
        "horizon": capped,
        "score": min(market.get("score") or 1.0, regulatory.get("score") or 1.0),
        "method": market["method"] + "+reg_coupled",
        "rationale": (
            f"{market['rationale']} Capped at {capped} because {region} is "
            f"regulatorily {rh}: without an approval there is no lawful market — "
            "the product signals then describe launches outside this "
            "jurisdiction."
        ),
    }


# ---------------------------------------------------------------------------
# Scope-Auflösung
# ---------------------------------------------------------------------------
# Die 10 Spalten SIND der Vertrag zwischen Scope-Auswahl und Zellenlogik: jede
# Auswahlart muss exakt diese Form liefern, dann bleiben alle cell_*-Funktionen
# unverändert. Zeitachse ist raw_entries.published_date — `sort_date` ist für
# 52 % der Zeilen NULL.
SCOPE_COLUMNS = """t.id, t.title_en, t.summary_en, t.trend_signal_type, t.regions,
               t.tags, t.pestel, t.primary_vertical,
               COALESCE(r.published_date, t.created_at)::date AS event_date,
               (t.tags IS NOT NULL AND jsonb_array_length(t.tags) > 0) AS semantic"""

# MUSS wortgleich zum Index `idx_trends_fts` bleiben — und zu FTS_VECTOR in
# frontend/src/app/api/search/route.ts:39-41. Jede Abweichung degradiert still
# von einem 6-ms-Index-Scan auf einen Seq Scan über 1,13 Mio. Zeilen; das Ergebnis
# bleibt korrekt, nur eben 250-2400× langsamer. Der Test in
# tests/test_radar_query.py hält beide Fassungen zeichengleich.
FTS_VECTOR = (
    "to_tsvector('english', coalesce(t.title_en,'') || ' ' || "
    "coalesce(t.summary_en,'') || ' ' || coalesce(t.tags::text,''))"
)

# Ober- und Untergrenze einer Query-Treffermenge.
MAX_SCOPE_ROWS = 25_000   # darüber ist eine Query kein "Feld" mehr
MIN_SCOPE_ROWS = 60       # darunter verweigert das Radar die Aussage


def load_scope_signals(conn, include: list[str], exclude: list[str]) -> list[dict]:
    """Alle Trends eines Technologiefelds laden — kuratierter Term-Pfad.

    Term-basiert (ILIKE) mit expliziten Ausschlüssen — auditierbar und ohne
    GPU-Abhängigkeit. Der Ausschluss ist nicht Kosmetik: ein naives
    '%fermentation%' fängt traditionelle Fermentation, Silage- und
    Futtermittelzusätze mit ein (docs/radar_redesign_proposal.md §6.4).
    """
    sql = f"""
        SELECT {SCOPE_COLUMNS}
        FROM trends t
        LEFT JOIN raw_entries r ON r.id = t.raw_entry_id
        WHERE (t.title_en ILIKE ANY(%s) OR t.summary_en ILIKE ANY(%s))
    """
    params: list = [include, include]
    if exclude:
        sql += " AND NOT (t.title_en ILIKE ANY(%s))"
        params.append(exclude)
    return conn.execute(sql, tuple(params)).fetchall()


def build_query_sql(
    query: str,
    phrase: str | None = None,
    ids: list[int] | None = None,
    limit: int = MAX_SCOPE_ROWS,
) -> tuple[str, list]:
    """SQL + Parameter für einen FTS-ausgewählten Scope. PUR, ohne DB testbar.

    `query`  — die Basis-Query des Radars (bindet das gesamte Feld)
    `phrase` — zusätzliche Teilfeld-Phrase (UND-verknüpft)
    `ids`    — optionale Einschränkung auf eine vorab bestimmte Trend-Menge
               (Zentroid-Zuweisung); wirkt zusätzlich zur Query, nie statt ihrer,
               damit ein gespeichertes Teilfeld nie aus seinem Radar herauswächst.

    Parser ist `websearch_to_tsquery` — die nutzerseitige Variante (Phrasen in
    Anführungszeichen, OR, führendes Minus). NIE `to_tsquery`: das wirft bei
    beliebiger Nutzereingabe eine Exception.
    """
    sql = f"""
        SELECT {SCOPE_COLUMNS}
        FROM trends t
        LEFT JOIN raw_entries r ON r.id = t.raw_entry_id
        WHERE {FTS_VECTOR} @@ websearch_to_tsquery('english', %s)
    """
    params: list = [query]
    if phrase:
        sql += f" AND {FTS_VECTOR} @@ websearch_to_tsquery('english', %s)"
        params.append(phrase)
    if ids is not None:
        sql += " AND t.id = ANY(%s)"
        params.append(ids)
    sql += " LIMIT %s"
    params.append(int(limit))
    return sql, params


def count_query_signals(conn, query: str) -> int:
    """Trefferzahl der nackten Basis-Query (~6 ms) — der Vorab-Flug.

    Entscheidet vor jeder Arbeit, ob eine Query zu breit oder zu dünn ist, damit
    ein pathologischer Fall nicht erst das Concurrency-Gate blockiert.
    """
    row = conn.execute(
        f"SELECT count(*)::int AS n FROM trends t "
        f"WHERE {FTS_VECTOR} @@ websearch_to_tsquery('english', %s)",
        (query,),
    ).fetchone()
    return int(row["n"]) if row else 0


def load_query_signals(
    conn,
    query: str,
    *,
    phrase: str | None = None,
    ids: list[int] | None = None,
    limit: int = MAX_SCOPE_ROWS,
) -> list[dict]:
    """Wie load_scope_signals, aber über Postgres-FTS ausgewählt."""
    sql, params = build_query_sql(query, phrase, ids, limit)
    return conn.execute(sql, tuple(params)).fetchall()


def resolve_scope(conn, scope: dict) -> list[dict]:
    """DIE Naht. Bestimmt, welche Trends ein Feld ausmachen.

    Verzweigt auf `scope['selector']`, nicht auf NULL-Schnüffelei:
      'terms'  → kuratierter ILIKE-Pfad, unverändert
      'query'  → FTS über Basis-Query (+ optionale Teilfeld-Phrase)

    Alle drei Wege liefern dieselben 10 Spalten, weshalb sämtliche
    cell_*-Funktionen davon nichts mitbekommen.
    """
    selector = (scope.get("selector") or "terms").lower()
    if selector == "query":
        return load_query_signals(
            conn,
            scope.get("query_text") or "",
            phrase=scope.get("phrase"),
            ids=scope.get("ids"),
        )
    inc = scope.get("include_terms")
    inc = json.loads(inc) if isinstance(inc, str) else (inc or [])
    exc = scope.get("exclude_terms")
    exc = json.loads(exc) if isinstance(exc, str) else (exc or [])
    return load_scope_signals(conn, inc, exc)


def _market_history(rows: list[dict], today: date) -> dict:
    """Kumulative Markt-Historie eines Scopes — der Diffusions-Nachweis.

    News berichten über VERÄNDERUNG, nicht über Zustand: eine längst
    diffundierte Technologie (Li-Ionen) erzeugt im 36-Monats-Fenster
    Forschungs- und Inkrement-Meldungen, aber niemand schreibt 2026 "Verbraucher
    kaufen jetzt Lithium-Akkus". Ein Fenster-Blick liest reife Technik deshalb
    systematisch als unreif. Die Historie über den ganzen Korpus ist dagegen
    eindeutig: Marktsignale in vielen Jahren, beginnend weit vor dem Fenster.
    """
    years: dict[int, int] = {}
    launches = 0
    for r in rows:
        st = r["trend_signal_type"]
        is_market = st == "product_launch" or (st == "market_shift" and r["semantic"])
        if not is_market or not r["event_date"]:
            continue
        years[r["event_date"].year] = years.get(r["event_date"].year, 0) + 1
        if st == "product_launch":
            launches += 1
    active = sorted(y for y, n in years.items() if n >= ESTABLISHED_YEAR_MIN_N)
    first = active[0] if active else None
    established = bool(
        first is not None
        and first <= today.year - ESTABLISHED_MIN_FIRST_AGE
        and len(active) >= ESTABLISHED_MIN_ACTIVE_YEARS
        and launches >= ESTABLISHED_MIN_LAUNCHES
    )
    return {"first_year": first, "active_years": len(active),
            "launches": launches, "established": established}


def _recent(rows: list[dict], months: int, today: date) -> list[dict]:
    cutoff = today - timedelta(days=int(months * 30.44))
    return [r for r in rows if r["event_date"] and r["event_date"] >= cutoff]


# ---------------------------------------------------------------------------
# Dimensionen
# ---------------------------------------------------------------------------
def cell_regulatory(rows: list[dict], region: str, today: date,
                    regulated: bool = True) -> dict:
    """Meilenstein-Gates pro Jurisdiktion.

    Zulassung erteilt → H1 · Antrag läuft → H2 · Pfad erst im Aufbau / Lücke → H3.

    `regulated` steuert, was ABWESENHEIT bedeutet — der Li-Ionen-Fund vom
    2026-08-02: für Batterien existiert kein Zulassungsregime, und "keine
    Zulassung gefunden" wurde trotzdem als H3 "blockiert" gelesen. In einer
    unregulierten Domäne ist Abwesenheit von Zulassungen aber KEINE Aussage über
    den Marktzugang; H3 braucht dort positive Gegenwind-Evidenz (Verbote,
    Blockaden). Ohne die schweigt die Zelle.

    Zuordnung zur Jurisdiktion: für 'granted' zählt ausschließlich die im Text
    genannte **Behörde** (FDA → US, EFSA → EU …). Ein Zulassungssignal ohne
    erkennbare Behörde belegt für keine Region etwas und wird nicht als Zulassung
    gewertet. Für die schwächeren Sub-Typen genügt `regions`, weil eine
    Konsultation ohne Behördennennung die Aussage nicht überhöht.
    """
    regs = [r for r in rows if r["trend_signal_type"] == "regulation"]

    granted, filed, forming, gaps = [], [], [], []
    for r in regs:
        st = reg_subtype(r)
        text = f"{r.get('title_en') or ''} {r.get('summary_en') or ''}"
        if st == "granted":
            # Nur die genannte Behörde entscheidet, für welche Region die
            # Zulassung zählt — nicht der Firmensitz aus `regions`.
            if reg_authority(text) == region:
                granted.append(r)
            continue
        if region not in regions_of(r):
            continue
        if st == "filed":
            filed.append(r)
        elif st == "gap":
            gaps.append(r)
        else:
            forming.append(r)

    filed = _recent(filed, PATHWAY_WINDOW_MONTHS, today)
    forming = _recent(forming, PATHWAY_WINDOW_MONTHS, today)
    gaps = _recent(gaps, PATHWAY_WINDOW_MONTHS, today)
    in_region = [r for r in regs if region in regions_of(r)]
    n_region = len(in_region) + len(granted)

    # Mindest-Evidenz gilt nur für die ABWESENHEITS-Schlüsse (H2/H3): dort wird
    # aus fehlender Evidenz etwas gefolgert, und das braucht eine Basis. Eine von
    # der zuständigen Behörde erteilte Zulassung ist dagegen für sich
    # entscheidend — eine einzige FDA-Freigabe belegt H1, egal wie viel sonst
    # über die Jurisdiktion vorliegt.
    if not granted and len(in_region) < MIN_N_REGULATORY:
        return {"horizon": None, "n_signals": len(in_region), "method": "gates",
                "rationale": f"Too few regulatory signals for {region} "
                             f"({len(in_region)}) — no call.", "evidence": []}

    if len(granted) == 1 and len(regs) >= 8:
        # Genau ein Zulassungssignal in einem gut belegten Scope: zu dünn für H1,
        # aber ein Hinweis auf ein laufendes Verfahren.
        filed = filed + granted
        granted = []
    if len(granted) >= MIN_N_GRANTED or (granted and len(regs) < 8):
        ev = sorted(granted, key=lambda r: r["event_date"] or date.min, reverse=True)
        years = sorted({r["event_date"].year for r in ev if r["event_date"]})
        return {
            "horizon": "H1", "n_signals": n_region, "method": "gates",
            "score": 1.0,
            "rationale": f"{len(granted)} approval(s) granted by the responsible "
                         f"{region} authority"
                         + (f" since {years[0]}" if years else "")
                         + " — clear to act.",
            "evidence": [r["id"] for r in ev[:5]],
        }
    if filed:
        ev = sorted(filed, key=lambda r: r["event_date"] or date.min, reverse=True)
        return {
            "horizon": "H2", "n_signals": n_region, "method": "gates",
            "score": 0.55,
            "rationale": f"No granted approval in {region}, but {len(filed)} "
                         f"live proceeding(s) (filing, review) in the last "
                         f"{PATHWAY_WINDOW_MONTHS} months — the route is being walked.",
            "evidence": [r["id"] for r in ev[:5]],
        }
    ev = sorted(gaps + forming, key=lambda r: r["event_date"] or date.min,
                reverse=True)
    if not regulated:
        # Unregulierte Domäne: H3 nur bei ausdrücklichem Gegenwind.
        if len(gaps) >= MIN_N_REGULATORY:
            return {
                "horizon": "H3", "n_signals": n_region, "method": "gates",
                "score": 0.15,
                "rationale": f"{len(gaps)} signals in {region} name explicit "
                             "regulatory headwind (bans, blocks, barriers).",
                "evidence": [r["id"] for r in ev[:5]],
            }
        return {
            "horizon": None, "n_signals": n_region, "method": "gates",
            "rationale": f"No approval regime identified for this field in "
                         f"{region} — in an unregulated domain that is not a "
                         "barrier, so this dimension makes no call. Switch on "
                         "“Approval required” if approvals do gate this field.",
            "evidence": [],
        }
    parts = []
    if forming:
        parts.append(f"{len(forming)} signals on consultation, strategy or calls for reform")
    if gaps:
        parts.append(f"{len(gaps)} signals name the gap explicitly")
    return {
        "horizon": "H3", "n_signals": n_region, "method": "gates", "score": 0.15,
        "rationale": f"No granted approval and no live proceeding in {region}"
                     + (" — " + ", ".join(parts) if parts else "")
                     + ": the route to market is still being built.",
        "evidence": [r["id"] for r in ev[:5]],
    }


def cell_market(rows: list[dict], region: str, today: date) -> dict:
    """Produktstarts pro Jurisdiktion, Handels-/Skalierungsmarker hebt auf H1."""
    in_region = [r for r in rows if region in regions_of(r)]
    launches = _recent([r for r in in_region
                        if r["trend_signal_type"] == "product_launch"],
                       LAUNCH_WINDOW_MONTHS, today)
    if len(in_region) < MIN_N_MARKET:
        return {"horizon": None, "n_signals": len(in_region), "method": "gates",
                "rationale": f"Too few signals for {region} ({len(in_region)}).",
                "evidence": []}
    # Pilot- und Demonstrationsmeldungen zählen für den Übergang (H2), nicht für
    # Marktverfügbarkeit (H1): sie belegen, dass es funktioniert, nicht dass man
    # es kaufen kann.
    def _txt(r):
        return f"{r['title_en'] or ''} {r['summary_en'] or ''}"

    pilot_ids = {r["id"] for r in launches if MARKET_PILOT.search(_txt(r))}
    pilots = [r for r in launches if r["id"] in pilot_ids]
    commercial = [r for r in launches if r["id"] not in pilot_ids]
    scaled = [r for r in commercial if MARKET_SCALE.search(_txt(r))]
    ev = sorted(launches, key=lambda r: r["event_date"] or date.min, reverse=True)
    if len(commercial) >= 5 or (commercial and scaled):
        return {
            "horizon": "H1", "n_signals": len(in_region), "method": "gates",
            "score": 0.9,
            "rationale": f"{len(commercial)} commercial product launches in {region} "
                         f"(last {LAUNCH_WINDOW_MONTHS} months)"
                         + (f", {len(scaled)} of them with retail or scale evidence"
                            if scaled else "")
                         + (f"; {len(pilots)} further signals are pilots and do not count"
                            if pilots else "")
                         + " — on the market.",
            "evidence": [r["id"] for r in ev[:5]],
        }
    if launches:
        return {
            "horizon": "H2", "n_signals": len(in_region), "method": "gates",
            "score": 0.5,
            "rationale": (
                f"{len(pilots)} pilot or demonstration signal(s) in {region}"
                + (f" and {len(commercial)} other launch(es)" if commercial else "")
                + " — feasibility shown, not yet purchasable."
                if pilots else
                f"{len(commercial)} product launch(es) in {region}, but no "
                "retail or scale evidence — early market entry."
            ),
            "evidence": [r["id"] for r in ev[:5]],
        }
    return {
        "horizon": "H3", "n_signals": len(in_region), "method": "gates", "score": 0.1,
        "rationale": f"No product launches in {region} in the last "
                     f"{LAUNCH_WINDOW_MONTHS} months.",
        "evidence": [],
    }


def cell_adoption(rows: list[dict], region: str, today: date,
                  market_horizon: str | None = None) -> dict:
    """Nachfrage-/Verhaltensseite: consumer_behavior + semantische Marktbewegung.

    `market_horizon` entscheidet, was FEHLENDE Verbrauchersignale bedeuten:
    bei einem etablierten Markt (H1) spiegelt die Abwesenheit nur, worüber News
    berichten — niemand schreibt 2026 "Verbraucher nutzen jetzt Lithium-Akkus".
    Abwesenheit als H3 zu werten ist nur belastbar, wenn auch der Markt fehlt.
    """
    pool = [r for r in _recent(rows, LAUNCH_WINDOW_MONTHS, today)
            if region in regions_of(r)
            and (r["trend_signal_type"] == "consumer_behavior"
                 or (r["trend_signal_type"] == "market_shift" and r["semantic"]))]
    cb = [r for r in pool if r["trend_signal_type"] == "consumer_behavior"]
    if len(pool) < MIN_N_ADOPTION:
        return {"horizon": None, "n_signals": len(pool), "method": "gates",
                "rationale": f"Too few demand signals for {region} ({len(pool)}).",
                "evidence": []}
    ev = sorted(pool, key=lambda r: r["event_date"] or date.min, reverse=True)
    if len(cb) >= 3:
        h, sc, why = "H1", 0.85, f"{len(cb)} consumer signals in {region} — demand is evidenced."
    elif cb:
        h, sc, why = "H2", 0.5, f"{len(cb)} consumer signal(s) in {region} — demand is forming."
    elif market_horizon == "H1":
        return {"horizon": None, "n_signals": len(pool), "method": "gates",
                "rationale": f"No direct demand-side signals in {region} — with "
                             "an established market this reflects what news "
                             "covers, not absent demand. No call.",
                "evidence": []}
    else:
        h, sc, why = "H3", 0.2, (f"Market movement only, no consumer signals in "
                                 f"{region} — demand unevidenced.")
    return {"horizon": h, "n_signals": len(pool), "method": "gates", "score": sc,
            "rationale": why, "evidence": [r["id"] for r in ev[:5]]}


def cell_technology(conn, rows: list[dict], today: date) -> dict:
    """CPC-Takeoff-Anker; Fallback semantischer Signalmix.

    Der Patent-Layer ist das methodisch stärkste Asset (peer-reviewte
    SPNP-Methode, gegen den MIT-Datensatz validiert), deckt aber nur
    patentierbare Felder ab. Ohne belastbaren CPC-Anker fällt die Dimension auf
    den semantischen Signalmix zurück — und sagt das im Klartext.
    """
    # Diffusions-Nachweis zuerst: eine Technologie mit vieljähriger, weit vor
    # dem News-Fenster beginnender Markt-Historie IST skalenreif — genau der
    # Beleg, den die H2-Deckelung des Signalmixes zu Recht verlangt. Ohne diesen
    # Pfad las das Radar Lithium-Ionen als H2/H3, weil laufende Forschung den
    # Mix forschungsseitig färbt: News messen Veränderung, nicht Zustand.
    hist = _market_history(rows, today)
    if hist["established"]:
        return {
            "horizon": "H1", "score": 0.9, "method": "market_history",
            "n_signals": hist["launches"],
            "rationale": (
                f"Established at scale: market signals in {hist['active_years']} "
                f"distinct years since {hist['first_year']} and "
                f"{hist['launches']} product launches across the corpus. The "
                "research volume in this field reflects ongoing refinement, "
                "not immaturity."
            ),
            "evidence": [],
        }

    ids = [r["id"] for r in rows]
    anchor = None
    if ids:
        anchor = conn.execute(
            """
            SELECT sc.cpc, count(*) AS n,
                   ls.science_takeoff, ls.patent_takeoff, ls.market_takeoff,
                   ls.reliable, d.title
            FROM signal_cpc sc
            JOIN cpc_leadtime_summary ls ON ls.cpc = sc.cpc
            LEFT JOIN cpc_definitions d ON d.symbol = sc.cpc
            WHERE sc.trend_id = ANY(%s) AND sc.dist < 0.55
            GROUP BY sc.cpc, ls.science_takeoff, ls.patent_takeoff,
                     ls.market_takeoff, ls.reliable, d.title
            ORDER BY n DESC LIMIT 1
            """,
            (ids,),
        ).fetchone()

    # H1 nur mit belastbarem Anker: `reliable=1` gilt für 18 von 681 CPC-Klassen.
    # Der Kalibrierlauf 2026-07-30 zeigte, warum die Hürde nötig ist — Precision
    # Fermentation verankerte auf A23C („Dairy Products"), einer breiten
    # Lebensmittelklasse mit Markt-Takeoff 1990er/2021 aus *traditioneller*
    # Milchwirtschaft. Daraus „technologisch etabliert" zu folgern, ist ein
    # Kategorienfehler: der Anker beschreibt das Produktfeld, nicht das Verfahren.
    if anchor and anchor["n"] >= 5 and anchor["reliable"]:
        sci, pat, mkt = (anchor["science_takeoff"], anchor["patent_takeoff"],
                         anchor["market_takeoff"])
        cpc, title = anchor["cpc"], (anchor["title"] or "").strip()
        base = (f"Patent anchor {cpc}"
                + (f" ({title[:48]})" if title else "")
                + f", {anchor['n']} signals matched, lead-time flagged reliable")
        if mkt and mkt <= today.year - MARKET_TAKEOFF_SETTLED_YEARS:
            return {"horizon": "H1", "score": 0.9, "method": "cpc_takeoff",
                    "n_signals": anchor["n"],
                    "rationale": f"{base}: market takeoff {mkt} — technologically established.",
                    "evidence": []}
        if pat:
            return {"horizon": "H2", "score": 0.55, "method": "cpc_takeoff",
                    "n_signals": anchor["n"],
                    "rationale": f"{base}: patent takeoff {pat}"
                                 + (f", market takeoff only {mkt}" if mkt else
                                    ", no market takeoff yet")
                                 + " — in transition.",
                    "evidence": []}
        if sci:
            return {"horizon": "H3", "score": 0.2, "method": "cpc_takeoff",
                    "n_signals": anchor["n"],
                    "rationale": f"{base}: research takeoff {sci} only — "
                                 "pre-competitive.",
                    "evidence": []}

    # Fallback: semantischer Mix (nur LLM-Pfad, sonst misst man Quellenmix).
    #
    # HARTE DECKELUNG AUF H2: aus dem Signalmix ist Kosten- und Skalenreife nicht
    # ablesbar. Viele Produktmeldungen belegen, dass das Verfahren funktioniert —
    # nicht, dass es wettbewerbsfähig produziert. H1 darf deshalb nur der
    # Patentanker (oder ein begründeter Analyst-Override) setzen.
    sem = [r for r in _recent(rows, 36, today) if r["semantic"]]
    unreliable = ""
    if anchor and anchor["n"] >= 5:
        unreliable = (f" The nearest patent anchor would be {anchor['cpc']}, but its "
                      "lead-time is not flagged reliable, so it is left out.")
    if len(sem) < MIN_N_TECH_FALLBACK:
        return {"horizon": None, "score": None, "method": "semantic_mix",
                "n_signals": len(sem),
                "rationale": "No reliable patent anchor and too few semantic "
                             f"signals ({len(sem)}) — no call."
                             + unreliable,
                "evidence": []}
    n = len(sem)
    applied = sum(1 for r in sem if r["trend_signal_type"] in
                  ("product_launch", "partnership"))
    research = sum(1 for r in sem if r["trend_signal_type"] in ("research", "patent"))
    share = applied / n
    if share >= 0.10:
        h, sc = "H2", 0.5
        why = (f"{applied} of {n} semantic signals are applied "
               f"(product/partnership), {research} still research-side — the process "
               "works; scale and cost maturity are not readable from signals")
    else:
        h, sc = "H3", 0.2
        why = (f"only {applied} of {n} signals applied, {research} research-side "
               "— pre-competitive")
    return {"horizon": h, "score": sc, "method": "semantic_mix", "n_signals": n,
            "rationale": f"No reliable patent anchor, from the signal mix: {why}. "
                         f"H1 is unreachable on this path.{unreliable}",
            "evidence": []}


def pestel_of(row) -> set[str]:
    """PESTEL-Dimensionen eines Trends (LLM-Klassifikation, Stage 3)."""
    raw = row.get("pestel")
    vals = json.loads(raw) if isinstance(raw, str) else (raw or [])
    return {str(v) for v in vals if v}


# ---------------------------------------------------------------------------
# PESTEL-Dimensions-Set (dimension_set='pestel')
# ---------------------------------------------------------------------------
# Dieselben Gate-Primitiven, durch die PESTEL-Linse: T und L sind die
# Technologie- bzw. Zulassungs-Gates, S die Adoption, E zählt wirtschaftliche
# Aktivität, P politische Unterstützung vs. Widerstand. En misst ausdrücklich
# nur die SICHTBARKEIT des Umweltarguments im Signalraum — mehr gibt der Korpus
# ehrlich nicht her, und die Begründung sagt das auch so.
PESTEL_DIMENSIONS = ("P", "E", "S", "T", "En", "L")


def cell_economic(rows: list[dict], region: str, today: date) -> dict:
    """E: wirtschaftliche Aktivität — Finanzierung + Produktstarts je Region."""
    pool = [r for r in _recent(rows, LAUNCH_WINDOW_MONTHS, today)
            if region in regions_of(r)]
    funding = [r for r in pool if r["trend_signal_type"] == "funding"]
    launches = [r for r in pool if r["trend_signal_type"] == "product_launch"]
    n = len(funding) + len(launches)
    if n < MIN_N_MARKET:
        return {"horizon": None, "n_signals": n, "method": "gates",
                "rationale": f"Too few economic signals for {region} ({n}).",
                "evidence": []}
    ev = sorted(funding + launches, key=lambda r: r["event_date"] or date.min,
                reverse=True)
    if launches and funding:
        h, sc, why = "H1", 0.85, (f"{len(funding)} funding and {len(launches)} product "
                                  f"signals in {region} — commercial activity on both sides")
    elif funding:
        h, sc, why = "H2", 0.5, (f"{len(funding)} funding signals but only "
                                 f"{len(launches)} product launches in {region} — capital ahead of market")
    else:
        h, sc, why = "H2", 0.45, (f"{len(launches)} product launches with no visible "
                                  f"funding signals in {region}")
    return {"horizon": h, "n_signals": n, "method": "gates", "score": sc,
            "rationale": why + ".", "evidence": [r["id"] for r in ev[:5]]}


def cell_political(rows: list[dict], region: str, today: date) -> dict:
    """P: politische Unterstützung — Strategie/Förderprogramme vs. Blockade.

    Bewertet die POLITISCHE GROSSWETTERLAGE, nicht die erteilte Zulassung
    (das ist L): Strategien, Roadmaps und öffentliche Förderung = Unterstützung;
    Verbote und explizite Blockaden = Gegenwind.
    """
    regs = [r for r in _recent(rows, PATHWAY_WINDOW_MONTHS, today)
            if r["trend_signal_type"] == "regulation" and region in regions_of(r)
            and "P" in pestel_of(r)]
    support = [r for r in regs if reg_subtype(r) in ("forming", "filed")]
    gaps = [r for r in regs if reg_subtype(r) == "gap"]
    n = len(regs)
    if n < MIN_N_REGULATORY:
        return {"horizon": None, "n_signals": n, "method": "gates",
                "rationale": f"Too few political signals for {region} ({n}).",
                "evidence": []}
    ev = sorted(regs, key=lambda r: r["event_date"] or date.min, reverse=True)
    if len(support) >= 3 and len(support) > 2 * len(gaps):
        h, sc, why = "H1", 0.8, (f"{len(support)} supportive signals (strategy, roadmap, "
                                 f"funding programme) against {len(gaps)} headwind signals in {region}")
    elif support:
        h, sc, why = "H2", 0.5, (f"{len(support)} supportive against {len(gaps)} headwind "
                                 f"signals in {region} — politically in motion")
    else:
        h, sc, why = "H3", 0.2, (f"Headwind only, or no supportive signals in "
                                 f"{region} ({len(gaps)} blocking signals)")
    return {"horizon": h, "n_signals": n, "method": "gates", "score": sc,
            "rationale": why + ".", "evidence": [r["id"] for r in ev[:5]]}


def cell_environmental(rows: list[dict], region: str, today: date) -> dict:
    """En: Sichtbarkeit des Umweltarguments im Signalraum dieses Felds.

    Ausdrücklich KEINE Ökobilanz — gemessen wird, wie präsent die Umweltdimension
    in den Signalen ist und ob sie zunimmt. Die Formulierung der Begründung
    macht diese Grenze explizit.
    """
    sem = [r for r in rows if r["semantic"] and region in regions_of(r)]
    if region == "GLOBAL":
        sem = [r for r in rows if r["semantic"]]
    tagged = [r for r in sem if "En" in pestel_of(r)]
    n = len(sem)
    if n < 20:
        return {"horizon": None, "n_signals": len(tagged), "method": "semantic_mix",
                "rationale": f"Too few semantic signals for {region} ({n}).",
                "evidence": []}
    share = len(tagged) / n
    recent = [r for r in _recent(tagged, 12, today)]
    ev = sorted(tagged, key=lambda r: r["event_date"] or date.min, reverse=True)
    if share >= 0.35 and recent:
        h, sc = "H1", 0.8
        why = (f"The environmental case carries: {len(tagged)} of {n} signals "
               f"({share:.0%}) are environment-tagged, {len(recent)} of them from "
               "the last 12 months")
    elif share >= 0.15:
        h, sc = "H2", 0.5
        why = (f"Environmental framing present but not dominant: {share:.0%} of "
               f"{n} signals")
    else:
        h, sc = "H3", 0.2
        why = f"Environmental framing marginal: {share:.0%} of {n} signals"
    return {"horizon": h, "n_signals": len(tagged), "method": "semantic_mix",
            "score": sc,
            "rationale": why + ". This measures visibility in the signal space, "
                         "not a life-cycle assessment.",
            "evidence": [r["id"] for r in ev[:5]]}


# ---------------------------------------------------------------------------
# Lauf
# ---------------------------------------------------------------------------
def compute_cells(conn, rows: list[dict], *, regions: list[str],
                  dimension_set: str = "strategic", regulated: bool = False,
                  today: date | None = None) -> list[dict]:
    """Alle Zellen EINES Scopes. Ohne run_id, ohne scope_slug, ohne Schreiben.

    Herausgelöst aus compute(), damit derselbe Code den nächtlichen Batch-Lauf
    und den On-Demand-Pfad bedient — zwei Implementierungen derselben
    Einordnung wären zwei Wahrheiten. `conn` braucht nur cell_technology
    (der signal_cpc-Anker), alle übrigen Zellen sind rein.

    Rückgabe: [{dimension, region, horizon, score, n_signals, method,
                rationale, evidence}, …]
    """
    today = today or date.today()
    out: list[dict] = []

    tech = cell_technology(conn, rows, today)
    out.append({
        "dimension": "T" if dimension_set == "pestel" else "technology",
        "region": ANY_REGION, "horizon": tech["horizon"], "score": tech.get("score"),
        "n_signals": tech["n_signals"], "method": tech["method"],
        "rationale": tech["rationale"], "evidence": tech.get("evidence", []),
    })

    tech_idx = 0  # die Technologie-Zelle steht immer an Position 0

    for region in regions:
        if dimension_set == "pestel":
            # Dieselben Gate-Primitiven durch die PESTEL-Linse:
            # L = Zulassungs-Gates, S = Adoption, E = Wirtschaft,
            # P = politische Unterstützung, En = Umwelt-Sichtbarkeit.
            per_region = (("L", cell_regulatory(rows, region, today,
                                                regulated=regulated)),
                          ("E", cell_economic(rows, region, today)),
                          ("S", cell_adoption(rows, region, today)),
                          ("P", cell_political(rows, region, today)),
                          ("En", cell_environmental(rows, region, today)))
        else:
            reg = cell_regulatory(rows, region, today, regulated=regulated)
            mkt = cell_market(rows, region, today)
            if regulated:
                mkt = couple_market_to_regulation(mkt, reg, region)
            # Adoption sieht den GEKOPPELTEN Markt-Horizont: ist der Markt auf
            # H3 gedeckelt, bleibt Abwesenheit von Nachfrage eine H3-Aussage.
            per_region = (("regulatory", reg), ("market", mkt),
                          ("adoption", cell_adoption(rows, region, today,
                                                     market_horizon=mkt["horizon"])))
        for dim, c in per_region:
            out.append({
                "dimension": dim, "region": region, "horizon": c["horizon"],
                "score": c.get("score"), "n_signals": c["n_signals"],
                "method": c["method"], "rationale": c["rationale"],
                "evidence": c.get("evidence", []),
            })

    # Kohärenz-Boden: eine Technologie mit erteilten Zulassungen oder einem
    # laufenden Markt ist nicht "vorwettbewerblich". Kalibrierlauf 2026-08-02:
    # Gene Therapy stand auf Technologie H3, obwohl der Korpus 70 erteilte
    # US-Zulassungen enthält — der Signalmix sah nur 1,9 % angewandte Signale,
    # weil klinische Forschung das Volumen dominiert. Das ist die Signatur eines
    # reifen regulierten Therapiefelds, nicht die eines unreifen. Angehoben wird
    # auf H2, nicht auf H1: Skalen- und Kostenreife bleibt unbelegt.
    tech = out[tech_idx]
    if tech["horizon"] == "H3" and tech["method"] == "semantic_mix":
        proof = [c for c in out[1:]
                 if c["horizon"] == "H1" and c["dimension"] in
                 ("regulatory", "market", "L")]
        if proof:
            kinds = sorted({("approvals" if c["dimension"] in ("regulatory", "L")
                             else "a live market") for c in proof})
            tech.update({
                "horizon": "H2", "score": 0.5,
                "method": "semantic_mix+coherence",
                "rationale": (
                    f"{tech['rationale']} Raised to H2: the same field shows "
                    f"{' and '.join(kinds)} in at least one jurisdiction, so it "
                    "cannot be pre-competitive. The research volume reflects a "
                    "field under active clinical or industrial development."
                ),
            })
    return out


def compute_query_radar(conn, query: str, subfields: list[dict] | None = None, *,
                        regions: list[str] | None = None,
                        dimension_set: str = "strategic",
                        regulated: bool = False,
                        today: date | None = None,
                        name: str | None = None) -> dict:
    """Ein vollständiges Radar für eine Freitext-Query — OHNE Persistenz.

    Schreibt nichts nach radar_runs/radar_cells/radar_scope_trends. Liefert
    exakt die Form, die lib/radar.ts getRadar() erzeugt (RadarView), erweitert um
    `origin` und eine aufgelöste `evidence`-Map. Das ist die tragende
    Entscheidung dieses Pfads: er ist ein ZWEITER PRODUZENT DESSELBEN VERTRAGS,
    kein zweiter Renderpfad — deshalb bleiben HorizonArc und HorizonBoard
    unverändert.

    subfields: [{'slug','label','phrase','ids'}, …]
               Leer/None → die Query selbst ist das einzige Feld. Das ist der
               ehrliche Rückfall, wenn keine Zerlegung möglich oder gewollt ist.
    """
    today = today or date.today()
    regions = [r for r in (regions or ["US", "EU", "GLOBAL"]) if r in JURISDICTIONS]
    regions = regions or ["GLOBAL"]

    if not subfields:
        subfields = [{"slug": "query", "label": name or query, "phrase": None}]

    scopes_out: list[dict] = []
    cells_out: list[dict] = []
    n_signals = 0
    ev_ids: set[int] = set()

    for sf in subfields:
        rows = load_query_signals(
            conn, query, phrase=sf.get("phrase"), ids=sf.get("ids")
        )
        n_signals += len(rows)
        scopes_out.append({
            "slug": sf["slug"],
            "label": sf.get("label") or sf["slug"],
            "n_signals": len(rows),
        })
        for c in compute_cells(conn, rows, regions=regions,
                               dimension_set=dimension_set,
                               regulated=regulated, today=today):
            ev = c["evidence"] or []
            ev_ids.update(ev)
            cells_out.append({
                "scope_slug": sf["slug"],
                "dimension": c["dimension"],
                "region": c["region"],
                "horizon": c["horizon"],
                "effective": c["horizon"],   # Overrides gibt es nur für gespeicherte Radare
                "score": c["score"],
                "n_signals": c["n_signals"],
                "method": c["method"],
                "rationale": c["rationale"],
                "evidence": ev,
                "override_horizon": None,
                "override_note": None,
            })

    # Evidenz einmal auflösen — der Client soll nie nachladen müssen.
    evidence: dict[str, dict] = {}
    if ev_ids:
        for r in conn.execute(
            "SELECT id, title_en, source_url, source_name FROM trends "
            "WHERE id = ANY(%s)", (sorted(ev_ids),)
        ).fetchall():
            evidence[str(r["id"])] = {
                "id": r["id"], "title": r["title_en"],
                "source_url": r["source_url"], "source_name": r["source_name"],
            }

    order = (["T", "L", "E", "S", "P", "En"] if dimension_set == "pestel"
             else ["technology", "regulatory", "market", "adoption"])
    dims = [d for d in order if any(c["dimension"] == d for c in cells_out)]

    return {
        "config": {
            "slug": "__query__",
            "name": name or query,
            "description": None,
            "regions": regions,
            "regulated": regulated,
            "kind": "query",
        },
        "scopes": [{"slug": s["slug"], "label": s["label"]} for s in scopes_out],
        "dimensions": dims,
        "regions": regions,
        "cells": cells_out,
        "generated": None,          # nicht persistiert → kein Lauf-Datum
        "n_signals": n_signals,
        "origin": {"kind": "query", "query": query,
                   "field_signals": {s["slug"]: s["n_signals"] for s in scopes_out}},
        "evidence": evidence,
    }


def compute(config_slug: str, today: date | None = None) -> int:
    today = today or date.today()
    with get_connection() as conn:
        cfg = conn.execute(
            "SELECT id, slug, name, regions, window_months, regulated, dimension_set "
            "FROM radar_configs WHERE slug = %s",
            (config_slug,),
        ).fetchone()
        if not cfg:
            raise SystemExit(f"Radar-Konfiguration {config_slug!r} nicht gefunden")
        regions = cfg["regions"]
        regions = json.loads(regions) if isinstance(regions, str) else (regions or [])
        regions = [r for r in regions if r in JURISDICTIONS] or ["GLOBAL"]
        regulated = bool(cfg.get("regulated"))
        dimension_set = cfg.get("dimension_set") or "strategic"

        scopes = conn.execute(
            "SELECT slug, label, include_terms, exclude_terms, selector, "
            "query_text, phrase FROM radar_scopes "
            "WHERE config_id = %s ORDER BY sort_order, id",
            (cfg["id"],),
        ).fetchall()
        if not scopes:
            raise SystemExit(f"Radar {config_slug!r} hat keine Scopes")

        run = conn.execute(
            "INSERT INTO radar_runs (config_id, n_scopes) VALUES (%s, %s) RETURNING id",
            (cfg["id"], len(scopes)),
        ).fetchone()
        run_id = run["id"]

        n_cells = n_signals = 0
        for sc in scopes:
            rows = resolve_scope(conn, dict(sc))
            n_signals += len(rows)
            log.info("scope %-22s %6d Signale", sc["slug"], len(rows))

            if rows:
                conn.executemany(
                    "INSERT OR IGNORE INTO radar_scope_trends (run_id, scope_slug, trend_id) "
                    "VALUES (?, ?, ?)",
                    [(run_id, sc["slug"], r["id"]) for r in rows],
                )

            cells = [
                (run_id, sc["slug"], c["dimension"], c["region"], c["horizon"],
                 c["score"], c["n_signals"], c["method"], c["rationale"],
                 json.dumps(c["evidence"]))
                for c in compute_cells(conn, rows, regions=regions,
                                       dimension_set=dimension_set,
                                       regulated=regulated, today=today)
            ]
            conn.executemany(
                "INSERT INTO radar_cells (run_id, scope_slug, dimension, region, "
                "horizon, score, n_signals, method, rationale, evidence) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                cells,
            )
            n_cells += len(cells)

        conn.execute("UPDATE radar_runs SET n_cells = %s, n_signals = %s WHERE id = %s",
                     (n_cells, n_signals, run_id))
        # Alte Runs derselben Konfiguration aufräumen (nur den neuesten behalten +1).
        old = conn.execute(
            "SELECT id FROM radar_runs WHERE config_id = %s ORDER BY id DESC OFFSET 2",
            (cfg["id"],),
        ).fetchall()
        for o in old:
            conn.execute("DELETE FROM radar_runs WHERE id = %s", (o["id"],))
        conn.commit()
        log.info("Run %d: %d Scopes, %d Zellen, %d Signale",
                 run_id, len(scopes), n_cells, n_signals)
        return run_id


def main() -> None:
    ap = argparse.ArgumentParser(description="Horizont-Radar berechnen")
    ap.add_argument("--config", default="alt-protein", help="Radar-Slug")
    ap.add_argument("--migrate", action="store_true", help="nur Tabellen anlegen")
    ap.add_argument("--seed", action="store_true", help="Referenz-Radar anlegen")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    migrate()
    if args.migrate:
        return
    if args.seed:
        from .radar_seed import seed
        seed()
    compute(args.config)


if __name__ == "__main__":
    main()
