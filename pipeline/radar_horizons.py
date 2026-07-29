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
REG_GAP = re.compile(
    r"\b(no approval|not approved|lack of|absence of|ban(ned|s)?|prohibit(ed|s)?|"
    r"block(ed|s)?|reject(ed|s)?|delay(ed|s)?|lag|barrier|hurdle|"
    r"black box|bottleneck|stalled|uncertainty)\b",
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
MIN_N_MARKET = 3
MIN_N_ADOPTION = 3
MIN_N_TECH_FALLBACK = 20  # ohne CPC-Anker: mindestens so viele semantische Signale
PATHWAY_WINDOW_MONTHS = 36   # Konsultationen veralten
LAUNCH_WINDOW_MONTHS = 36    # Produktstarts: nur die jüngeren zählen
# Zulassungen sind dauerhaft und werden ohne Fenster gezählt.
MARKET_TAKEOFF_SETTLED_YEARS = 2  # Markt-Takeoff muss so lange her sein für H1

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
            f"{market['rationale']} Auf {capped} begrenzt, weil {region} "
            f"regulatorisch {rh} ist: ohne Zulassung kein zulässiger Markt — "
            "die Produktsignale betreffen dann Starts außerhalb dieser "
            "Jurisdiktion."
        ),
    }


# ---------------------------------------------------------------------------
# Scope-Auflösung
# ---------------------------------------------------------------------------
def load_scope_signals(conn, include: list[str], exclude: list[str]) -> list[dict]:
    """Alle Trends eines Technologiefelds laden.

    Term-basiert (ILIKE) mit expliziten Ausschlüssen — auditierbar und ohne
    GPU-Abhängigkeit. Der Ausschluss ist nicht Kosmetik: ein naives
    '%fermentation%' fängt traditionelle Fermentation, Silage- und
    Futtermittelzusätze mit ein (docs/radar_redesign_proposal.md §6.4).
    Zeitachse ist raw_entries.published_date, nicht sort_date.
    """
    sql = """
        SELECT t.id, t.title_en, t.summary_en, t.trend_signal_type, t.regions,
               t.tags, t.primary_vertical,
               COALESCE(r.published_date, t.created_at)::date AS event_date,
               (t.tags IS NOT NULL AND jsonb_array_length(t.tags) > 0) AS semantic
        FROM trends t
        LEFT JOIN raw_entries r ON r.id = t.raw_entry_id
        WHERE (t.title_en ILIKE ANY(%s) OR t.summary_en ILIKE ANY(%s))
    """
    params: list = [include, include]
    if exclude:
        sql += " AND NOT (t.title_en ILIKE ANY(%s))"
        params.append(exclude)
    return conn.execute(sql, tuple(params)).fetchall()


def _recent(rows: list[dict], months: int, today: date) -> list[dict]:
    cutoff = today - timedelta(days=int(months * 30.44))
    return [r for r in rows if r["event_date"] and r["event_date"] >= cutoff]


# ---------------------------------------------------------------------------
# Dimensionen
# ---------------------------------------------------------------------------
def cell_regulatory(rows: list[dict], region: str, today: date) -> dict:
    """Meilenstein-Gates pro Jurisdiktion.

    Zulassung erteilt → H1 · Antrag läuft → H2 · Pfad erst im Aufbau / Lücke → H3.

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
                "rationale": f"Zu wenige Regulatorik-Signale für {region} "
                             f"({len(in_region)}) — keine Aussage.", "evidence": []}

    if granted:
        ev = sorted(granted, key=lambda r: r["event_date"] or date.min, reverse=True)
        years = sorted({r["event_date"].year for r in ev if r["event_date"]})
        return {
            "horizon": "H1", "n_signals": n_region, "method": "gates",
            "score": 1.0,
            "rationale": f"{len(granted)} von der zuständigen {region}-Behörde "
                         f"erteilte Zulassung(en)"
                         + (f" seit {years[0]}" if years else "")
                         + " — regulatorisch handlungsfähig.",
            "evidence": [r["id"] for r in ev[:5]],
        }
    if filed:
        ev = sorted(filed, key=lambda r: r["event_date"] or date.min, reverse=True)
        return {
            "horizon": "H2", "n_signals": n_region, "method": "gates",
            "score": 0.55,
            "rationale": f"Keine erteilte Zulassung in {region}, aber {len(filed)} "
                         f"laufende(s) Verfahren (Antrag, Prüfung) in den letzten "
                         f"{PATHWAY_WINDOW_MONTHS} Monaten — Weg ist beschritten.",
            "evidence": [r["id"] for r in ev[:5]],
        }
    ev = sorted(gaps + forming, key=lambda r: r["event_date"] or date.min,
                reverse=True)
    parts = []
    if forming:
        parts.append(f"{len(forming)} Signale zu Konsultation/Strategie/Reformruf")
    if gaps:
        parts.append(f"{len(gaps)} Signale benennen die Lücke ausdrücklich")
    return {
        "horizon": "H3", "n_signals": n_region, "method": "gates", "score": 0.15,
        "rationale": f"Keine erteilte Zulassung und kein laufendes Verfahren in "
                     f"{region}"
                     + (" — " + ", ".join(parts) if parts else "")
                     + ": der Zulassungsweg wird erst gebaut.",
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
                "rationale": f"Zu wenige Signale für {region} ({len(in_region)}).",
                "evidence": []}
    scaled = [r for r in launches
              if MARKET_SCALE.search(f"{r['title_en'] or ''} {r['summary_en'] or ''}")]
    ev = sorted(launches, key=lambda r: r["event_date"] or date.min, reverse=True)
    if len(launches) >= 5 or (launches and scaled):
        return {
            "horizon": "H1", "n_signals": len(in_region), "method": "gates",
            "score": 0.9,
            "rationale": f"{len(launches)} Produktstarts in {region} "
                         f"({LAUNCH_WINDOW_MONTHS} Monate)"
                         + (f", davon {len(scaled)} mit Handels-/Skalierungsbezug"
                            if scaled else "")
                         + " — im Markt.",
            "evidence": [r["id"] for r in ev[:5]],
        }
    if launches:
        return {
            "horizon": "H2", "n_signals": len(in_region), "method": "gates",
            "score": 0.5,
            "rationale": f"{len(launches)} Produktstart(e) in {region}, aber kein "
                         "Handels-/Skalierungsnachweis — früher Markteintritt.",
            "evidence": [r["id"] for r in ev[:5]],
        }
    return {
        "horizon": "H3", "n_signals": len(in_region), "method": "gates", "score": 0.1,
        "rationale": f"Keine Produktstarts in {region} in den letzten "
                     f"{LAUNCH_WINDOW_MONTHS} Monaten.",
        "evidence": [],
    }


def cell_adoption(rows: list[dict], region: str, today: date) -> dict:
    """Nachfrage-/Verhaltensseite: consumer_behavior + semantische Marktbewegung."""
    pool = [r for r in _recent(rows, LAUNCH_WINDOW_MONTHS, today)
            if region in regions_of(r)
            and (r["trend_signal_type"] == "consumer_behavior"
                 or (r["trend_signal_type"] == "market_shift" and r["semantic"]))]
    cb = [r for r in pool if r["trend_signal_type"] == "consumer_behavior"]
    if len(pool) < MIN_N_ADOPTION:
        return {"horizon": None, "n_signals": len(pool), "method": "gates",
                "rationale": f"Zu wenige Nachfragesignale für {region} ({len(pool)}).",
                "evidence": []}
    ev = sorted(pool, key=lambda r: r["event_date"] or date.min, reverse=True)
    if len(cb) >= 3:
        h, sc, why = "H1", 0.85, f"{len(cb)} Verbrauchersignale in {region} — Nachfrage belegt."
    elif cb:
        h, sc, why = "H2", 0.5, f"{len(cb)} Verbrauchersignal(e) in {region} — Nachfrage entsteht."
    else:
        h, sc, why = "H3", 0.2, (f"Nur Marktbewegung ohne Verbrauchersignale in "
                                 f"{region} — Nachfrage unbelegt.")
    return {"horizon": h, "n_signals": len(pool), "method": "gates", "score": sc,
            "rationale": why, "evidence": [r["id"] for r in ev[:5]]}


def cell_technology(conn, rows: list[dict], today: date) -> dict:
    """CPC-Takeoff-Anker; Fallback semantischer Signalmix.

    Der Patent-Layer ist das methodisch stärkste Asset (peer-reviewte
    SPNP-Methode, gegen den MIT-Datensatz validiert), deckt aber nur
    patentierbare Felder ab. Ohne belastbaren CPC-Anker fällt die Dimension auf
    den semantischen Signalmix zurück — und sagt das im Klartext.
    """
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
        base = (f"Patentanker {cpc}"
                + (f" ({title[:48]})" if title else "")
                + f", {anchor['n']} Signale zugeordnet, Lead-Time als belastbar markiert")
        if mkt and mkt <= today.year - MARKET_TAKEOFF_SETTLED_YEARS:
            return {"horizon": "H1", "score": 0.9, "method": "cpc_takeoff",
                    "n_signals": anchor["n"],
                    "rationale": f"{base}: Markt-Takeoff {mkt} — technologisch etabliert.",
                    "evidence": []}
        if pat:
            return {"horizon": "H2", "score": 0.55, "method": "cpc_takeoff",
                    "n_signals": anchor["n"],
                    "rationale": f"{base}: Patent-Takeoff {pat}"
                                 + (f", Markt-Takeoff erst {mkt}" if mkt else
                                    ", noch kein Markt-Takeoff")
                                 + " — in der Übergangsphase.",
                    "evidence": []}
        if sci:
            return {"horizon": "H3", "score": 0.2, "method": "cpc_takeoff",
                    "n_signals": anchor["n"],
                    "rationale": f"{base}: nur Forschungs-Takeoff {sci} — "
                                 "vorwettbewerblich.",
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
        unreliable = (f" Nächster Patentanker wäre {anchor['cpc']}, dessen Lead-Time "
                      "ist aber nicht als belastbar markiert und bleibt daher außen vor.")
    if len(sem) < MIN_N_TECH_FALLBACK:
        return {"horizon": None, "score": None, "method": "semantic_mix",
                "n_signals": len(sem),
                "rationale": "Kein belastbarer Patentanker und zu wenige "
                             f"semantische Signale ({len(sem)}) — keine Aussage."
                             + unreliable,
                "evidence": []}
    n = len(sem)
    applied = sum(1 for r in sem if r["trend_signal_type"] in
                  ("product_launch", "partnership"))
    research = sum(1 for r in sem if r["trend_signal_type"] in ("research", "patent"))
    share = applied / n
    if share >= 0.10:
        h, sc = "H2", 0.5
        why = (f"{applied} von {n} semantischen Signalen sind angewandt "
               f"(Produkt/Partnerschaft), {research} forschungsseitig — das Verfahren "
               "funktioniert, Skalen- und Kostenreife ist aus Signalen nicht belegbar")
    else:
        h, sc = "H3", 0.2
        why = (f"nur {applied} von {n} Signalen angewandt, {research} forschungsseitig "
               "— vorwettbewerblich")
    return {"horizon": h, "score": sc, "method": "semantic_mix", "n_signals": n,
            "rationale": f"Ohne belastbaren Patentanker, aus dem Signalmix: {why}. "
                         f"H1 ist auf diesem Weg ausgeschlossen.{unreliable}",
            "evidence": []}


# ---------------------------------------------------------------------------
# Lauf
# ---------------------------------------------------------------------------
def compute(config_slug: str, today: date | None = None) -> int:
    today = today or date.today()
    with get_connection() as conn:
        cfg = conn.execute(
            "SELECT id, slug, name, regions, window_months, regulated "
            "FROM radar_configs WHERE slug = %s",
            (config_slug,),
        ).fetchone()
        if not cfg:
            raise SystemExit(f"Radar-Konfiguration {config_slug!r} nicht gefunden")
        regions = cfg["regions"]
        regions = json.loads(regions) if isinstance(regions, str) else (regions or [])
        regions = [r for r in regions if r in JURISDICTIONS] or ["GLOBAL"]
        regulated = bool(cfg.get("regulated"))

        scopes = conn.execute(
            "SELECT slug, label, include_terms, exclude_terms FROM radar_scopes "
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
            inc = sc["include_terms"]
            inc = json.loads(inc) if isinstance(inc, str) else (inc or [])
            exc = sc["exclude_terms"]
            exc = json.loads(exc) if isinstance(exc, str) else (exc or [])
            rows = load_scope_signals(conn, inc, exc)
            n_signals += len(rows)
            log.info("scope %-22s %6d Signale", sc["slug"], len(rows))

            if rows:
                conn.executemany(
                    "INSERT OR IGNORE INTO radar_scope_trends (run_id, scope_slug, trend_id) "
                    "VALUES (?, ?, ?)",
                    [(run_id, sc["slug"], r["id"]) for r in rows],
                )

            cells: list[tuple] = []
            tech = cell_technology(conn, rows, today)
            cells.append((run_id, sc["slug"], "technology", ANY_REGION,
                          tech["horizon"], tech.get("score"), tech["n_signals"],
                          tech["method"], tech["rationale"],
                          json.dumps(tech.get("evidence", []))))
            for region in regions:
                reg = cell_regulatory(rows, region, today)
                mkt = cell_market(rows, region, today)
                if regulated:
                    mkt = couple_market_to_regulation(mkt, reg, region)
                ado = cell_adoption(rows, region, today)
                for dim, c in (("regulatory", reg), ("market", mkt),
                               ("adoption", ado)):
                    cells.append((run_id, sc["slug"], dim, region, c["horizon"],
                                  c.get("score"), c["n_signals"], c["method"],
                                  c["rationale"], json.dumps(c.get("evidence", []))))
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
