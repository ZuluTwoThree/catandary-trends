#!/usr/bin/env python3
"""Der Messtisch: Radar als Bewertungswerkzeug (docs/radar_overhaul_plan.md).

Zwei Achsen, zwei Besitzer — Blechschmidt, Quick Guide Trendmanagement, S. 100:

    „Die Trendreife bewertet den Trend auf seinen heutigen Zustand UNABHÄNGIG
     vom Unternehmen. Die Trendrelevanz ist ein Maß für die Bedeutung des Trends
     FÜR DAS JEWEILIGE UNTERNEHMEN."

Die **Reife** rechnet dieses Modul aus Verlauf und Evidenz. Die **Relevanz**
entsteht ausschließlich aus bewerteten Einzelsignalen — und zwar bewusst von
unten: ein Feld direkt zu bewerten („Wie relevant ist Ihnen Machine Learning?")
kann niemand ehrlich beantworten, ein einzelnes Signal schon. Daraus folgt, dass
die Feldrelevanz abgeleitet statt behauptet ist, auf ihre Belege zurückführbar
bleibt — und dass die Bewertungen ein Trainingsset bilden, aus dem später ein
Modell die übrigen Signale vorschlagen kann.

Jurisdiktionen kommen hier nicht mehr vor (Owner-Entscheidung 2026-08-05).
"""

from __future__ import annotations

import json
import logging
import math
import statistics
from datetime import date

from .db import get_connection

log = logging.getLogger("instrument")

# ---------------------------------------------------------------------------
# Blechschmidts Reifestufen (Abb. 8.2). Reihenfolge = Achsenreihenfolge.
# ---------------------------------------------------------------------------
STAGES = ["emerging", "volatile", "maturing", "established"]
# Beschriftungen sind ENGLISCH — die Produktsprache ist durchgehend Englisch
# (Owner 2026-08-07), und diese Texte gehen unverändert ins Frontend.
STAGE_LABEL = {"emerging": "Emerging", "volatile": "Volatile",
               "maturing": "Maturing", "established": "Established"}
STAGE_BAND = {"emerging": "Observe", "volatile": "Understand",
              "maturing": "Consider", "established": "Implement"}

# Owner-Vorgabe 2026-08-05: Wo die Reife nicht bestimmbar ist, steht ein Feld
# auf VOLATIL. Methodisch ist das die einzige richtige Wahl — es ist die einzige
# Stufe, deren Handlungsempfehlung „genauer hinsehen" lautet. „Entstehend" wäre
# eine Behauptung über Jugend, „etabliert" eine über Reife; beides wüssten wir
# nicht.
FALLBACK_STAGE = "volatile"

SAMPLE_SIZE = 48          # Owner: 40–60 je Feld
SAMPLE_BUCKETS = 8        # Zeitschichten der Stichprobe


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------
SCHEMA = """
CREATE TABLE IF NOT EXISTS workspace (
    id SERIAL PRIMARY KEY,
    slug TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS rater (
    id SERIAL PRIMARY KEY,
    workspace_id INTEGER REFERENCES workspace(id) ON DELETE CASCADE,
    handle TEXT NOT NULL,
    display_name TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (workspace_id, handle)
);
CREATE TABLE IF NOT EXISTS rater_expertise (
    rater_id INTEGER REFERENCES rater(id) ON DELETE CASCADE,
    vertical TEXT NOT NULL,
    self_declared INTEGER,
    PRIMARY KEY (rater_id, vertical)
);
CREATE TABLE IF NOT EXISTS workspace_field (
    workspace_id INTEGER REFERENCES workspace(id) ON DELETE CASCADE,
    field_key TEXT NOT NULL,
    label TEXT NOT NULL,
    vertical TEXT,
    sort_order INTEGER DEFAULT 0,
    PRIMARY KEY (workspace_id, field_key)
);
CREATE TABLE IF NOT EXISTS signal_relevance (
    id SERIAL PRIMARY KEY,
    workspace_id INTEGER REFERENCES workspace(id) ON DELETE CASCADE,
    rater_id INTEGER REFERENCES rater(id) ON DELETE CASCADE,
    field_key TEXT NOT NULL,
    trend_id INTEGER NOT NULL,
    points INTEGER,
    skipped BOOLEAN DEFAULT false,
    rated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (workspace_id, rater_id, trend_id)
);
CREATE INDEX IF NOT EXISTS idx_sigrel_field
    ON signal_relevance (workspace_id, field_key);
CREATE TABLE IF NOT EXISTS field_assessment (
    workspace_id INTEGER REFERENCES workspace(id) ON DELETE CASCADE,
    field_key TEXT NOT NULL,
    relevance REAL,
    relevance_spread REAL,
    n_rated INTEGER DEFAULT 0,
    n_raters INTEGER DEFAULT 0,
    maturity REAL,
    maturity_stage TEXT,
    maturity_basis TEXT,
    maturity_note TEXT,
    curve JSONB,
    computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (workspace_id, field_key)
);
"""


def migrate() -> None:
    with get_connection() as conn:
        conn.executescript(SCHEMA)
        conn.commit()
    log.info("Messtisch-Tabellen migriert")


# ---------------------------------------------------------------------------
# Kurvenposition — Hype Cycle / Rogers aus der Anteilsreihe
# ---------------------------------------------------------------------------
# Blechschmidt (S. 100): „Die Trendreife kann sich aus der Position des Trends im
# Gartner Hype Cycle oder dem Diffusionsmodell ergeben." Beides sind Kurven über
# die Zeit — und die haben wir: 440 Monatswerte je Cluster.
#
# WICHTIG und im Frontend zu sagen: der Anteil am Signalaufkommen misst
# AUFMERKSAMKEIT, nicht Marktreife. Ein Feld kann auf dem Plateau der
# Berichterstattung sitzen und nichts verkaufen. Deshalb ist die Kurve hier nur
# eine von zwei Quellen; die zweite ist die Marktevidenz aus radar_maturity.
NOISE_FLOOR_N = 8         # Monate mit weniger Signalen sind Rauschen
SMOOTH_MONTHS = 12


def _smooth(vals: list[float], win: int = SMOOTH_MONTHS) -> list[float]:
    out = []
    for i in range(len(vals)):
        lo = max(0, i - win + 1)
        out.append(statistics.median(vals[lo:i + 1]))
    return out


def curve_position(series: list[dict]) -> dict:
    """Wo steht das Feld auf seiner Aufmerksamkeitskurve?

    `series`: [{m: '2019-03', n: 42, share: 0.031}, …]

    Liefert Kennzahlen und eine Stufe — oder `stage=None`, wenn die Reihe zu
    dünn ist. Die frühen Jahre tragen Anteile wie 0,58 bei zweistelligen
    Signalzahlen; ungefiltert würde jede Kurve dort ihr Maximum haben.
    """
    pts = [p for p in series if (p.get("n") or 0) >= NOISE_FLOOR_N]
    if len(pts) < 24:
        return {"stage": None, "reason": "Series too short or too thin "
                                         f"({len(pts)} usable months).",
                "n_months": len(pts)}

    shares = _smooth([float(p["share"]) for p in pts])
    months = [p["m"] for p in pts]
    peak_i = max(range(len(shares)), key=lambda i: shares[i])
    peak = shares[peak_i]
    now = statistics.mean(shares[-6:]) if len(shares) >= 6 else shares[-1]
    if peak <= 0:
        return {"stage": None, "reason": "No measurable share.", "n_months": len(pts)}

    # Kennzahlen
    from_peak = now / peak                       # 1.0 = auf dem Gipfel
    age = len(pts)                               # verwertbare Monate
    tail = shares[-24:] if len(shares) >= 24 else shares
    slope = (tail[-1] - tail[0]) / max(tail[0], 1e-6)
    after_peak = shares[peak_i:]
    trough = min(after_peak) if len(after_peak) > 3 else now
    recovery = (now - trough) / max(peak, 1e-6)
    vola = statistics.pstdev(tail) / max(statistics.mean(tail), 1e-6)

    # Zuordnung. Reihenfolge zählt: die Prüfungen gehen von jung nach reif.
    if age < 48 and slope > 0.5:
        stage, why = "emerging", (
            f"Young series, climbing steeply: {age} usable months, "
            f"{slope:+.0%} over the last two years. A rise out of nothing — "
            "innovation trigger.")
    elif from_peak >= 0.75 and vola > 0.35:
        stage, why = "volatile", (
            f"Near its peak ({from_peak:.0%} of maximum) and swinging hard "
            f"(spread {vola:.0%}) — peak of inflated expectations.")
    elif from_peak < 0.45 and recovery < 0.1:
        stage, why = "volatile", (
            f"Well below its peak ({from_peak:.0%}) with no recovery — "
            "trough of disillusionment. Whether it climbs again is open.")
    elif recovery >= 0.1 and from_peak < 0.9:
        stage, why = "maturing", (
            f"Recovering after the slump ({recovery:+.0%} off the bottom, "
            f"{from_peak:.0%} of peak) — slope of enlightenment.")
    elif vola <= 0.25 and age >= 96:
        stage, why = "established", (
            f"Steady at {now:.1%} share for {age // 12} years "
            f"(spread {vola:.0%}) — plateau.")
    else:
        stage, why = None, (
            f"No clear pattern: {from_peak:.0%} of peak, "
            f"spread {vola:.0%}, trend {slope:+.0%}.")

    return {
        "stage": stage, "reason": why, "n_months": age,
        "peak_month": months[peak_i], "from_peak": round(from_peak, 3),
        "slope_24m": round(slope, 3), "volatility": round(vola, 3),
        "recovery": round(recovery, 3), "share_now": round(now, 4),
    }


def merge_maturity(curve: dict, evidence_score: float | None) -> dict:
    """Kurvenposition und Marktevidenz zusammenführen.

    Widersprechen sie sich, wird NICHT gemittelt — die Zelle sagt es. „Die
    Berichterstattung ist auf dem Plateau, ein Markt ist aber nicht belegt" ist
    selbst eine Aussage, und meist die interessanteste.
    """
    ev_stage = None
    if evidence_score is not None:
        ev_stage = ("established" if evidence_score >= 3.0 else
                    "maturing" if evidence_score >= 2.0 else
                    "volatile" if evidence_score >= 1.0 else "emerging")
    c_stage = curve.get("stage")

    if c_stage and ev_stage and c_stage == ev_stage:
        return {"stage": c_stage, "basis": "curve+evidence",
                "note": f"History and market evidence agree. {curve['reason']}"}
    if c_stage and ev_stage:
        # Der reifere der beiden gewinnt NICHT automatisch — wir nehmen den
        # niedrigeren und benennen den Widerspruch. Aufmerksamkeit ohne Markt
        # ist kein Reifebeleg.
        lower = min(c_stage, ev_stage, key=lambda s: STAGES.index(s))
        return {"stage": lower, "basis": "conflict",
                "note": (f"History and evidence disagree: the curve says "
                         f"{STAGE_LABEL[c_stage].lower()}, market evidence says "
                         f"{STAGE_LABEL[ev_stage].lower()}. The more cautious "
                         f"reading is shown. {curve['reason']}")}
    if ev_stage:
        return {"stage": ev_stage, "basis": "evidence",
                "note": ("From market evidence — the history yields no clear "
                         f"pattern. {curve.get('reason','')}")}
    if c_stage:
        return {"stage": c_stage, "basis": "curve",
                "note": f"From the shape of its history. {curve['reason']}"}
    return {"stage": FALLBACK_STAGE, "basis": "default",
            "note": ("Neither history nor market evidence is conclusive. The "
                     "topic therefore sits on volatile — the one band whose "
                     "recommendation is \u201clook closer\u201d. "
                     + curve.get("reason", ""))}


# ---------------------------------------------------------------------------
# Arbeitsbereich und Felder
# ---------------------------------------------------------------------------
def ensure_workspace(slug: str, name: str) -> int:
    with get_connection() as conn:
        row = conn.execute("SELECT id FROM workspace WHERE slug=%s",
                           (slug,)).fetchone()
        if row:
            return row["id"]
        wid = conn.execute(
            "INSERT INTO workspace (slug, name) VALUES (%s,%s) RETURNING id",
            (slug, name)).fetchone()["id"]
        conn.commit()
        return wid


def ensure_rater(workspace_id: int, handle: str, name: str | None = None) -> int:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM rater WHERE workspace_id=%s AND handle=%s",
            (workspace_id, handle)).fetchone()
        if row:
            return row["id"]
        rid = conn.execute(
            "INSERT INTO rater (workspace_id, handle, display_name) "
            "VALUES (%s,%s,%s) RETURNING id",
            (workspace_id, handle, name or handle)).fetchone()["id"]
        conn.commit()
        return rid


def parse_field_key(field_key: str) -> tuple[str, str]:
    kind, _, rest = field_key.partition(":")
    return kind, rest


# Volltext über den kuratierten Signalraum. Wortgleich zum Index `idx_trends_fts`
# und zu FTS_VECTOR in radar_horizons — jede Abweichung degradiert still von
# einem 6-ms-Index-Scan auf einen Seq Scan über 1,13 Mio. Zeilen.
FTS_VECTOR = ("to_tsvector('english', coalesce(t.title_en,'') || ' ' || "
              "coalesce(t.summary_en,'') || ' ' || coalesce(t.tags::text,''))")


def field_trend_ids(conn, field_key: str, limit: int = 40_000) -> list[int]:
    """Alle Signal-IDs eines Felds.

    Vier Arten: eine Suche, ein Cluster, ein Mega-Trend, eine Vertikale.

    Die **Suche** ist seit 2026-08-07 der Hauptweg (Owner): der Nutzer tippt
    sein Thema — „robotics", „GLP-1", „dairy", „LLM" — statt aus einem Katalog
    von 253 Clustern zu wählen. Das ist die ehrlichere Reihenfolge: er weiß, was
    ihn interessiert, aber nicht, wie unsere Clusterung es genannt hat.
    """
    kind, rest = parse_field_key(field_key)
    if kind == "search":
        rows = conn.execute(
            f"""SELECT t.id FROM trends t
                 WHERE {FTS_VECTOR} @@ websearch_to_tsquery('english', %s)
                   AND t.title_en IS NOT NULL
                 LIMIT %s""", (rest, limit)).fetchall()
        return [r["id"] for r in rows]
    if kind == "cluster":
        run_id, _, idx = rest.partition(":")
        rows = conn.execute(
            "SELECT trend_id FROM foresight_cluster_members "
            "WHERE run_id=%s AND cluster_idx=%s LIMIT %s",
            (int(run_id), int(idx), limit)).fetchall()
        return [r["trend_id"] for r in rows]
    if kind == "mega":
        rows = conn.execute(
            "SELECT id FROM trends WHERE mega_trend=%s LIMIT %s",
            (rest, limit)).fetchall()
        return [r["id"] for r in rows]
    if kind == "vertical":
        rows = conn.execute(
            "SELECT id FROM trends WHERE primary_vertical=%s LIMIT %s",
            (rest, limit)).fetchall()
        return [r["id"] for r in rows]
    return []


def field_series(conn, field_key: str) -> list[dict]:
    """Monatliche Anteilsreihe eines Felds — die Grundlage der Kurvenposition.

    Cluster bringen sie mit (`foresight_clusters.monthly_series`); Suchfelder,
    Mega-Trends und Branchen nicht, also wird sie gerechnet: Treffer je Monat
    gegen alle Signale des Monats. Ohne den Nenner wäre die Reihe nur ein Abbild
    davon, wie der Korpus insgesamt gewachsen ist.

    Bis 2026-08-07 gab es sie nur für Suchfelder — mit der Folge, dass JEDE
    Branche und JEDER Mega-Trend mangels Kurve auf dem Rückfall „volatil"
    stehenblieb und die Reifeachse zur Hälfte tot war. Für diese beiden Arten
    rechnet sie jetzt `_series_by_column`.
    """
    kind, rest = parse_field_key(field_key)
    if kind == "mega":
        return _series_by_column(conn, "mega_trend", [rest]).get(rest, [])
    if kind == "vertical":
        return _series_by_column(conn, "primary_vertical", [rest]).get(rest, [])
    if kind != "search":
        return []
    rows = conn.execute(
        f"""WITH hits AS (
              SELECT to_char(COALESCE(r.published_date, t.created_at), 'YYYY-MM') AS m,
                     count(*) AS n
                FROM trends t LEFT JOIN raw_entries r ON r.id = t.raw_entry_id
               WHERE {FTS_VECTOR} @@ websearch_to_tsquery('english', %s)
               GROUP BY 1),
            total AS (
              SELECT to_char(COALESCE(r.published_date, t.created_at), 'YYYY-MM') AS m,
                     count(*) AS n
                FROM trends t LEFT JOIN raw_entries r ON r.id = t.raw_entry_id
               GROUP BY 1)
            SELECT h.m, h.n, (h.n::float / NULLIF(tt.n, 0)) AS share
              FROM hits h JOIN total tt ON tt.m = h.m
             WHERE h.m IS NOT NULL ORDER BY h.m""", (rest,)).fetchall()
    return [{"m": r["m"], "n": int(r["n"]), "share": float(r["share"] or 0)}
            for r in rows]


def reset_preview(workspace_id: int) -> dict:
    """Was ein Neustart wirklich löschen würde — VOR dem Löschen.

    Existiert, weil die Bestätigung sonst untertreibt: die Tafel zählt nur
    Bewertungen zu Feldern, die noch auf dem Tisch liegen. Nimmt man ein Feld
    herunter, bleiben seine Bewertungen stehen und speisen weiter das globale
    Interessensmodell — real gemessen 175 Zeilen, während die Oberfläche 18
    zeigte. Eine Bestätigung, die zu niedrige Zahlen nennt, ist schlimmer als
    gar keine.
    """
    with get_connection() as conn:
        row = conn.execute(
            """SELECT
                 (SELECT count(*) FROM signal_relevance
                   WHERE workspace_id=%s AND points IS NOT NULL) AS ratings,
                 (SELECT count(*) FROM signal_relevance sr
                   WHERE sr.workspace_id=%s AND sr.points IS NOT NULL
                     AND NOT EXISTS (SELECT 1 FROM workspace_field wf
                                      WHERE wf.workspace_id = sr.workspace_id
                                        AND wf.field_key = sr.field_key)) AS orphaned,
                 (SELECT count(*) FROM signal_relevance
                   WHERE workspace_id=%s AND points IS NULL) AS skipped,
                 (SELECT count(*) FROM workspace_field
                   WHERE workspace_id=%s) AS fields,
                 (SELECT count(DISTINCT rater_id) FROM signal_relevance
                   WHERE workspace_id=%s) AS raters""",
            (workspace_id,) * 5).fetchone()
        labels = [r["label"] for r in conn.execute(
            "SELECT label FROM workspace_field WHERE workspace_id=%s "
            "ORDER BY sort_order, label", (workspace_id,)).fetchall()]
    d = {k: int(row[k]) for k in ("ratings", "orphaned", "skipped", "fields", "raters")}
    d["field_labels"] = labels
    # Das Modell schaltet ab MIN_RATINGS_FOR_HINT frei — das ist der Verlust,
    # den ein Nutzer am ehesten unterschätzt.
    d["model_was_ready"] = d["ratings"] >= MIN_RATINGS_FOR_HINT
    return d


def reset_workspace(workspace_id: int, *, keep_fields: bool = False) -> dict:
    """Alles zurücksetzen — für Nutzertests.

    Löscht Bewertungen, Bewertungen-Aggregate und (optional) die Felder. Der
    Arbeitsbereich und die Bewerter bleiben stehen, damit die Sitzung nicht
    abreißt.
    """
    before = reset_preview(workspace_id)
    with get_connection() as conn:
        n = conn.execute(
            "SELECT count(*) AS n FROM signal_relevance WHERE workspace_id=%s",
            (workspace_id,)).fetchone()["n"]
        conn.execute("DELETE FROM signal_relevance WHERE workspace_id=%s",
                     (workspace_id,))
        conn.execute("DELETE FROM field_assessment WHERE workspace_id=%s",
                     (workspace_id,))
        if not keep_fields:
            conn.execute("DELETE FROM workspace_field WHERE workspace_id=%s",
                         (workspace_id,))
        conn.commit()
    return {"deleted_ratings": int(n), "fields_kept": keep_fields, "before": before}


def sample_for_rating(conn, workspace_id: int, rater_id: int, field_key: str,
                      n: int = SAMPLE_SIZE) -> list[dict]:
    """Die Stichprobe, die dem Bewerter vorgelegt wird.

    Geschichtet über ZEIT und SIGNALTYP — nicht die jüngsten n. Eine Stichprobe
    aus dem letzten Jahr würde ein Feld systematisch als jung erscheinen lassen,
    und eine nach Häufigkeit gezogene bestünde zu 40 % aus Marktbewegung. Beides
    verzerrt die Relevanzaussage, die daraus entsteht.

    Bereits bewertete Signale fallen raus, damit ein Bewerter weiterkommt.
    """
    ids = field_trend_ids(conn, field_key)
    if not ids:
        return []
    done = {r["trend_id"] for r in conn.execute(
        "SELECT trend_id FROM signal_relevance "
        "WHERE workspace_id=%s AND rater_id=%s", (workspace_id, rater_id)
    ).fetchall()}

    rows = conn.execute(
        f"""SELECT t.id, t.title_en, t.summary_en, t.source_name, t.source_url,
                   t.trend_signal_type, t.primary_vertical,
                   COALESCE(r.published_date, t.created_at)::date AS event_date
              FROM trends t LEFT JOIN raw_entries r ON r.id = t.raw_entry_id
             WHERE t.id = ANY(%s) AND t.title_en IS NOT NULL
             ORDER BY event_date""",
        (ids,)).fetchall()
    rows = [dict(r) for r in rows if r["id"] not in done and r["event_date"]]
    if not rows:
        return []

    # Zeitschichten
    per_bucket = max(1, n // SAMPLE_BUCKETS)
    size = max(1, len(rows) // SAMPLE_BUCKETS)
    picked: list[dict] = []
    seen_types: dict[str, int] = {}
    for b in range(SAMPLE_BUCKETS):
        chunk = rows[b * size:(b + 1) * size] if b < SAMPLE_BUCKETS - 1 \
            else rows[b * size:]
        if not chunk:
            continue
        # Innerhalb der Schicht nach Signaltyp durchmischen: reihum je Typ eines
        # nehmen, damit kein Typ die Schicht dominiert.
        by_type: dict[str, list[dict]] = {}
        for r in chunk:
            by_type.setdefault(r["trend_signal_type"] or "?", []).append(r)
        order = sorted(by_type, key=lambda k: seen_types.get(k, 0))
        i = 0
        while len(picked) < (b + 1) * per_bucket and any(by_type.values()):
            k = order[i % len(order)]
            if by_type[k]:
                r = by_type[k].pop(len(by_type[k]) // 2)   # aus der Mitte
                picked.append(r)
                seen_types[k] = seen_types.get(k, 0) + 1
            i += 1
            if i > 400:
                break
    return picked[:n]


# ---------------------------------------------------------------------------
# Fachnähe
# ---------------------------------------------------------------------------
# Blechschmidt (S. 102): „Personen mit wenigen Kontaktpunkten zu den jeweiligen
# Themen werden zudem sehr subjektive Meinungen abgeben und so das Gewicht gut
# begründeter Bewertungen der (wenigen) Spezialisten verwässern."
#
# Selbstauskunft allein reicht nicht — sie ist notorisch großzügig. Drei
# Anteile, multiplikativ, gedeckelt. NIE null: eine Stimme ganz zu streichen
# wäre eine Vertrauensfrage, keine Methodik.
WEIGHT_MIN = 0.25
WEIGHT_MAX = 4.0


def expertise_weight(conn, rater_id: int, workspace_id: int,
                     vertical: str | None) -> dict:
    self_declared = 1
    if vertical:
        row = conn.execute(
            "SELECT self_declared FROM rater_expertise "
            "WHERE rater_id=%s AND vertical=%s", (rater_id, vertical)).fetchone()
        if row and row["self_declared"] is not None:
            self_declared = int(row["self_declared"])
    base = {0: 0.5, 1: 1.0, 2: 1.6, 3: 2.4}.get(self_declared, 1.0)

    n = conn.execute(
        "SELECT count(*) AS n FROM signal_relevance "
        "WHERE workspace_id=%s AND rater_id=%s AND points IS NOT NULL",
        (workspace_id, rater_id)).fetchone()["n"]
    # Erfahrung sättigt: die ersten 50 Bewertungen zählen viel, die 500ste kaum.
    exp = 0.6 + 0.4 * min(1.0, math.log10(max(n, 1) + 1) / math.log10(201))

    w = max(WEIGHT_MIN, min(WEIGHT_MAX, base * exp))
    return {"weight": round(w, 2), "self_declared": self_declared,
            "n_rated": n, "experience_factor": round(exp, 2)}


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------
def assess_field(workspace_id: int, field_key: str,
                 evidence_score: float | None = None,
                 series: list[dict] | None = None,
                 vertical: str | None = None) -> dict:
    """Relevanz aus den Bewertungen, Reife aus Verlauf und Evidenz."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT rater_id, points FROM signal_relevance "
            "WHERE workspace_id=%s AND field_key=%s AND points IS NOT NULL",
            (workspace_id, field_key)).fetchall()

        by_rater: dict[int, list[int]] = {}
        for r in rows:
            by_rater.setdefault(r["rater_id"], []).append(int(r["points"]))

        num = den = 0.0
        means: list[float] = []
        for rid, pts in by_rater.items():
            w = expertise_weight(conn, rid, workspace_id, vertical)["weight"]
            m = statistics.mean(pts)
            means.append(m)
            num += m * w
            den += w
        relevance = round(num / den, 2) if den else None
        # Streuung ÜBER DIE BEWERTER, nicht über die Signale — Blechschmidts
        # Sorge gilt dem Auseinanderfallen der Urteile, nicht der Varianz
        # innerhalb eines Felds.
        spread = round(statistics.pstdev(means), 2) if len(means) > 1 else 0.0

        curve = curve_position(series or [])
        mat = merge_maturity(curve, evidence_score)
        mat_num = STAGES.index(mat["stage"])

        conn.execute(
            """INSERT INTO field_assessment (workspace_id, field_key, relevance,
                   relevance_spread, n_rated, n_raters, maturity, maturity_stage,
                   maturity_basis, maturity_note, curve, computed_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,CURRENT_TIMESTAMP)
               ON CONFLICT (workspace_id, field_key) DO UPDATE SET
                   relevance=EXCLUDED.relevance,
                   relevance_spread=EXCLUDED.relevance_spread,
                   n_rated=EXCLUDED.n_rated, n_raters=EXCLUDED.n_raters,
                   maturity=EXCLUDED.maturity, maturity_stage=EXCLUDED.maturity_stage,
                   maturity_basis=EXCLUDED.maturity_basis,
                   maturity_note=EXCLUDED.maturity_note, curve=EXCLUDED.curve,
                   computed_at=CURRENT_TIMESTAMP""",
            (workspace_id, field_key, relevance, spread, len(rows),
             len(by_rater), float(mat_num), mat["stage"], mat["basis"],
             mat["note"], json.dumps(curve)))
        conn.commit()

    return {"field_key": field_key, "relevance": relevance,
            "relevance_spread": spread, "n_rated": len(rows),
            "n_raters": len(by_rater), **mat, "curve": curve}


# ---------------------------------------------------------------------------
# Vorschlag aus den bisherigen Bewertungen
# ---------------------------------------------------------------------------
# Gemessen am ersten echten Bestand (98 Bewertungen, 12 davon hoch):
#
#   Positiv-Schwerpunkt allein   AUC 0,626   Präzision@20 20 %
#   Rocchio (positiv − negativ)  AUC 0,700   Präzision@20 30 %  (Grundrate 12 %)
#
# Rocchio gewinnt deutlich, weil die Negativen mitzählen: der Nutzer bewertet
# nicht „ähnlich zu etwas", sondern „ähnlich zu dem, was ihn interessiert, und
# unähnlich zu dem, was ihn nicht interessiert".
#
# ENTSCHEIDEND: das Modell ist GLOBAL, nicht je Feld. Feldweise trainiert
# scheiterte es genau dort, wo es darauf ankam — im Cluster „Venture Capital ·
# AI" lag die AUC bei 0,40 (unter Zufall), weil die hoch bewerteten Signale
# darin von GMO, Cultured Meat und Bodensensorik handelten. Das Interesse des
# Nutzers ist THEMATISCH und quer zu den Feldern; ein feldweises Modell lernt
# stattdessen die Semantik des Felds.
MIN_RATINGS_FOR_HINT = 25
MIN_POSITIVES_FOR_HINT = 5
HINT_THRESHOLD = 3


def relevance_direction(conn, workspace_id: int) -> tuple[list[float] | None, dict]:
    """Rocchio-Richtung aus allen Bewertungen des Arbeitsbereichs."""
    import numpy as np
    rows = conn.execute(
        "SELECT sr.points, t.embedding_1024::text AS emb "
        "FROM signal_relevance sr JOIN trends t ON t.id = sr.trend_id "
        "WHERE sr.workspace_id=%s AND sr.points IS NOT NULL "
        "  AND t.embedding_1024 IS NOT NULL", (workspace_id,)).fetchall()
    n = len(rows)
    pos_n = sum(1 for r in rows if r["points"] >= HINT_THRESHOLD)
    meta = {"n": n, "positives": pos_n,
            "ready": n >= MIN_RATINGS_FOR_HINT and pos_n >= MIN_POSITIVES_FOR_HINT}
    if not meta["ready"]:
        return None, meta
    X = np.stack([np.fromstring(r["emb"].strip("[]"), sep=",", dtype=np.float32)
                  for r in rows])
    X /= np.clip(np.linalg.norm(X, axis=1, keepdims=True), 1e-9, None)
    y = np.array([r["points"] for r in rows])
    pos = y >= HINT_THRESHOLD
    v = X[pos].mean(0) - X[~pos].mean(0)
    nrm = float(np.linalg.norm(v))
    if nrm < 1e-6:
        return None, meta
    return (v / nrm).tolist(), meta


def score_against(conn, direction: list[float], trend_ids: list[int]) -> dict[int, float]:
    """Kosinus der Signale zur Interessensrichtung."""
    import numpy as np
    if not direction or not trend_ids:
        return {}
    v = np.array(direction, dtype=np.float32)
    rows = conn.execute(
        "SELECT id, embedding_1024::text AS emb FROM trends "
        "WHERE id = ANY(%s) AND embedding_1024 IS NOT NULL", (trend_ids,)).fetchall()
    out = {}
    for r in rows:
        e = np.fromstring(r["emb"].strip("[]"), sep=",", dtype=np.float32)
        nrm = float(np.linalg.norm(e))
        if nrm > 0:
            out[r["id"]] = float(e @ v / nrm)
    return out


def hint_points(score: float) -> int:
    """Kosinus in einen Punktvorschlag übersetzen.

    Die Schwellen sind an der gemessenen Verteilung geeicht: die Spitze der
    30.000 ungesehenen Signale lag bei +0,40, der Boden bei −0,24. Bewusst
    zurückhaltend — ein Vorschlag, der zu oft 4 sagt, wird weggeklickt statt
    gelesen.
    """
    return (4 if score >= 0.28 else 3 if score >= 0.18 else
            2 if score >= 0.08 else 1 if score >= 0.0 else 0)


# ---------------------------------------------------------------------------
# Entdeckung: wo sonst noch passiert, was den Nutzer interessiert
# ---------------------------------------------------------------------------
# Der Grund, warum das überhaupt geht: das Interessensmodell ist GLOBAL (siehe
# relevance_direction). Es kennt keine Feldgrenzen — und findet deshalb genau
# die Signale, die im Thema des Nutzers liegen, aber in einem Cluster, einem
# Mega-Trend oder einer Branche wohnen, die er gar nicht gewählt hat.
#
# Über pgvector kostet die Suche über 1,13 Mio. Signale 0,02 s (HNSW-Index).
# Der teure Teil ist nicht das Finden, sondern das ENTDROSSELN: die reine
# Spitzenliste bestand aus acht Varianten derselben Solein-Meldung. Ohne
# Streuung ist eine Entdeckung keine.
DISCOVER_POOL = 600       # so viele Nachbarn holen
DISCOVER_PER_GROUP = 3    # so viele je Gruppe zeigen
DISCOVER_MIN_SIM = 0.20   # darunter ist es nicht mehr „das Thema"


def _dedupe_titles(rows: list[dict], overlap: float = 0.6) -> list[dict]:
    """Nahezu gleiche Meldungen zusammenfassen — dieselbe Nachricht in drei
    Fachmedien ist eine Entdeckung, nicht drei."""
    import re
    stop = {"the", "for", "and", "with", "from", "new", "its", "has", "will",
            "that", "this", "into", "over", "after", "says"}
    kept: list[tuple[frozenset, dict]] = []
    for r in rows:
        toks = frozenset(w for w in re.split(r"[^a-z0-9]+", (r["title"] or "").lower())
                         if len(w) > 3 and w not in stop)
        if any(toks and k and len(toks & k) / min(len(toks), len(k)) >= overlap
               for k, _ in kept):
            continue
        kept.append((toks, r))
    return [r for _, r in kept]


def discover(conn, workspace_id: int, pool: int = DISCOVER_POOL) -> dict:
    """Wo im Korpus liegt sonst noch, was den Nutzer interessiert?"""
    direction, meta = relevance_direction(conn, workspace_id)
    if not direction:
        return {"ready": False, "model": meta, "groups": []}
    lit = "[" + ",".join(f"{x:.6f}" for x in direction) + "]"
    # hnsw.ef_search steht standardmäßig auf 40 und DECKELT die Ergebnisliste:
    # ein LIMIT 600 lieferte trotzdem nur 40 Zeilen, und die Entdeckung blieb
    # auf acht Varianten derselben Meldung sitzen. Der Wert muss über dem LIMIT
    # liegen — er bestimmt, wie viele Kandidaten der Index überhaupt betrachtet.
    conn.execute("SET LOCAL hnsw.ef_search = %s", (min(1000, max(64, pool * 2)),))

    chosen = {r["field_key"] for r in conn.execute(
        "SELECT field_key FROM workspace_field WHERE workspace_id=%s",
        (workspace_id,)).fetchall()}

    rows = conn.execute(
        """SELECT t.id, t.title_en AS title, t.source_name, t.source_url,
                  t.primary_vertical, t.mega_trend, t.trend_signal_type,
                  1 - (t.embedding_1024 <=> %s::vector) AS sim,
                  COALESCE(r.published_date, t.created_at)::date AS d
             FROM trends t LEFT JOIN raw_entries r ON r.id = t.raw_entry_id
            WHERE t.embedding_1024 IS NOT NULL AND t.title_en IS NOT NULL
              AND t.id NOT IN (SELECT trend_id FROM signal_relevance
                                WHERE workspace_id = %s)
            ORDER BY t.embedding_1024 <=> %s::vector
            LIMIT %s""", (lit, workspace_id, lit, pool)).fetchall()
    rows = [dict(r) for r in rows if float(r["sim"]) >= DISCOVER_MIN_SIM]
    rows = _dedupe_titles(rows)

    # Cluster-Zugehörigkeit der Treffer nachschlagen (jüngster Lauf je Scope).
    ids = [r["id"] for r in rows]
    cl: dict[int, tuple[str, str]] = {}
    if ids:
        for m in conn.execute(
            """SELECT m.trend_id, m.run_id, m.cluster_idx, fc.label
                 FROM foresight_cluster_members m
                 JOIN foresight_clusters fc
                   ON fc.run_id = m.run_id AND fc.cluster_idx = m.cluster_idx
                WHERE m.trend_id = ANY(%s)
                  AND m.run_id IN (SELECT max(id) FROM foresight_runs
                                    WHERE scope LIKE %s GROUP BY scope)""",
            (ids, "vertical:%")).fetchall():
            cl.setdefault(m["trend_id"],
                          (f"cluster:{m['run_id']}:{m['cluster_idx']}", m["label"]))

    groups: dict[str, dict] = {}
    for r in rows:
        for kind, key, label in (
            ("cluster", *(cl.get(r["id"]) or (None, None))),
            ("mega", f"mega:{r['mega_trend']}" if r["mega_trend"] else None,
             (r["mega_trend"] or "").replace("_", " ").title() or None),
            ("vertical", f"vertical:{r['primary_vertical']}"
             if r["primary_vertical"] else None, r["primary_vertical"]),
        ):
            if not key:
                continue
            g = groups.setdefault(key, {
                "kind": kind, "field_key": key, "label": label,
                "on_table": key in chosen, "n": 0, "top_sim": 0.0, "hits": [],
            })
            g["n"] += 1
            g["top_sim"] = max(g["top_sim"], float(r["sim"]))
            if len(g["hits"]) < DISCOVER_PER_GROUP:
                g["hits"].append({
                    "id": r["id"], "title": r["title"], "sim": round(float(r["sim"]), 3),
                    "source": r["source_name"], "url": r["source_url"],
                    "type": r["trend_signal_type"], "date": str(r["d"]),
                })

    out = sorted(groups.values(), key=lambda g: (-g["n"], -g["top_sim"]))
    return {
        "ready": True, "model": meta, "n_hits": len(rows),
        "groups": out,
        "new_groups": sum(1 for g in out if not g["on_table"]),
    }


def relevance_stage(score: float | None) -> str | None:
    """Blechschmidts drei Relevanzstufen aus dem 0–4-Mittel."""
    if score is None:
        return None
    return "high" if score >= 2.67 else "medium" if score >= 1.34 else "low"


# ---------------------------------------------------------------------------
# Projektion: den GANZEN Signalraum ins Radar legen
# ---------------------------------------------------------------------------
# Der letzte Schritt der Kette, die mit einem getippten Wort beginnt:
#
#   Suchen → bewerten → Interessensrichtung lernen → **alles danach ordnen**
#
# `discover` beantwortet „wo sonst noch?" mit einer Liste. Die Projektion legt
# dieselbe Erkenntnis ins Radar: jedes Feld, in dem relevante Signale liegen,
# bekommt eine Position — Reife aus dem Verlauf, Relevanz aus dem gelernten
# Modell. Das ist ausdrücklich ein VORSCHLAG (zinnoberrot), keine Setzung; er
# zählt erst, wenn der Nutzer die Signale des Felds tatsächlich bewertet.
#
# Warum Felder und nicht einzelne Signale als Punkte: die Reifeachse ist als
# Verlaufsposition definiert, und ein einzelnes Signal HAT keinen Verlauf — es
# ist ein Punkt darin. Ein Radar aus 1.000 Einzelmeldungen wäre eine Wolke ohne
# Aussage. Jedes Signal geht deshalb in genau ein Heimatfeld (Cluster vor
# Mega-Trend vor Branche), sodass die Blips eine Partition der Treffer sind und
# nichts doppelt zählt.
PROJECT_POOL = 1000       # hnsw.ef_search deckelt bei 1000 — mehr geht nicht
PROJECT_MIN_SIM = 0.16    # weiter draußen als DISCOVER: hier zählt Breite
PROJECT_MIN_HITS = 6      # darunter ist eine Position nicht behauptbar
PROJECT_MAX_BLIPS = 18
PROJECT_EST_SAMPLE = 120  # Stichprobe je Feld für die Relevanzschätzung


def relevance_calibration(conn, workspace_id: int,
                          direction: list[float]) -> tuple[float, float]:
    """Kosinus → Punkte, geeicht an den eigenen Bewertungen des Nutzers.

    `hint_points` ist eine Leiter mit festen Schwellen; sie ist für die
    WARTESCHLANGE gebaut, wo es aufs Ordnen ankommt, und sagt an der Spitze
    bewusst oft 4. Für eine Feldschätzung ist genau das falsch — gemessen an
    157 echten Bewertungen (leave-one-out):

        Leiter        MAE 1,06   Verzerrung **+0,82**   r 0,472
        lineare Eich  MAE 0,72   Verzerrung  +0,02      r 0,509

    Die Leiter trifft die Reihenfolge, aber nicht die Höhe: sie sagte im Mittel
    1,78, wo der Nutzer 0,96 vergab. Ein Feldvorschlag mit dieser Verzerrung
    landet reihenweise in „hoch" und macht die Relevanzachse blind. Die
    Kleinste-Quadrate-Gerade auf den eigenen Bewertungen behebt das, und sie
    passt sich an, wie streng dieser Nutzer bewertet.
    """
    import numpy as np
    rows = conn.execute(
        "SELECT sr.points, t.embedding_1024::text AS emb "
        "FROM signal_relevance sr JOIN trends t ON t.id = sr.trend_id "
        "WHERE sr.workspace_id=%s AND sr.points IS NOT NULL "
        "  AND t.embedding_1024 IS NOT NULL", (workspace_id,)).fetchall()
    if len(rows) < MIN_RATINGS_FOR_HINT:
        return (0.0, 0.0)
    v = np.array(direction, dtype=np.float32)
    X = np.stack([np.fromstring(r["emb"].strip("[]"), sep=",", dtype=np.float32)
                  for r in rows])
    X /= np.clip(np.linalg.norm(X, axis=1, keepdims=True), 1e-9, None)
    b, a = np.polyfit(X @ v, np.array([float(r["points"]) for r in rows]), 1)
    return (float(a), float(b))


def estimate_relevance(conn, direction: list[float], field_key: str,
                       n: int = PROJECT_EST_SAMPLE,
                       calib: tuple[float, float] | None = None) -> dict | None:
    """Was würde der Nutzer diesem Feld im Mittel geben?

    Der erste Anlauf mittelte über die GEFUNDENEN Treffer — und setzte jedes
    Feld auf 4,0, weil die Treffer per Konstruktion die nächsten Nachbarn der
    Interessensrichtung sind. Das ist ein Zirkelschluss: er misst die Auswahl,
    nicht das Feld.

    Deshalb hier derselbe Schätzer, den der Mensch bedient — Mittel über eine
    ZUFÄLLIGE Stichprobe des Felds, inklusive der uninteressanten Signale. Nur
    so ist die vorgeschlagene Zahl mit den selbst bewerteten Feldern auf einer
    Skala, und nur so kann ein breites Feld mit wenigen Treffern auch niedrig
    landen. Die Punkte kommen aus `relevance_calibration`, nicht aus der
    Warteschlangen-Leiter — siehe dort.
    """
    import random
    ids = field_trend_ids(conn, field_key)
    if not ids:
        return None
    pick = ids if len(ids) <= n else random.Random(len(ids)).sample(ids, n)
    scores = score_against(conn, direction, pick)
    if not scores:
        return None
    if calib and calib[1]:
        a0, b0 = calib
        pts = [min(4.0, max(0.0, a0 + b0 * s)) for s in scores.values()]
    else:
        pts = [float(hint_points(s)) for s in scores.values()]
    return {"relevance": round(statistics.mean(pts), 2), "field_n": len(ids),
            "sampled": len(pts)}


def _series_by_column(conn, column: str, values: list[str]) -> dict[str, list[dict]]:
    """Monatliche Anteilsreihen für mehrere Spaltenwerte in einem Rutsch.

    Der Nenner ist das gesamte Monatsaufkommen — ohne ihn misst die Reihe nur,
    wie der Korpus insgesamt gewachsen ist, und jedes Feld sähe „steigend" aus.
    """
    if not values:
        return {}
    assert column in ("mega_trend", "primary_vertical")  # kein Nutzer-Input
    rows = conn.execute(
        f"""WITH hits AS (
              SELECT t.{column} AS v,
                     to_char(COALESCE(r.published_date, t.created_at), 'YYYY-MM') AS m,
                     count(*) AS n
                FROM trends t LEFT JOIN raw_entries r ON r.id = t.raw_entry_id
               WHERE t.{column} = ANY(%s) GROUP BY 1, 2),
            total AS (
              SELECT to_char(COALESCE(r.published_date, t.created_at), 'YYYY-MM') AS m,
                     count(*) AS n
                FROM trends t LEFT JOIN raw_entries r ON r.id = t.raw_entry_id
               GROUP BY 1)
            SELECT h.v, h.m, h.n, (h.n::float / NULLIF(tt.n, 0)) AS share
              FROM hits h JOIN total tt ON tt.m = h.m
             WHERE h.m IS NOT NULL ORDER BY h.v, h.m""", (values,)).fetchall()
    out: dict[str, list[dict]] = {}
    for r in rows:
        out.setdefault(r["v"], []).append(
            {"m": r["m"], "n": int(r["n"]), "share": float(r["share"] or 0)})
    return out


def project(conn, workspace_id: int, pool: int = PROJECT_POOL) -> dict:
    """Den gesamten Signalraum gegen das gelernte Interesse ordnen."""
    direction, meta = relevance_direction(conn, workspace_id)
    if not direction:
        return {"ready": False, "model": meta, "blips": []}

    lit = "[" + ",".join(f"{x:.6f}" for x in direction) + "]"
    conn.execute("SET LOCAL hnsw.ef_search = %s", (min(1000, max(64, pool)),))
    rows = [dict(r) for r in conn.execute(
        """SELECT t.id, t.title_en AS title, t.source_name, t.source_url,
                  t.primary_vertical, t.mega_trend, t.trend_signal_type,
                  1 - (t.embedding_1024 <=> %s::vector) AS sim,
                  COALESCE(r.published_date, t.created_at)::date AS d
             FROM trends t LEFT JOIN raw_entries r ON r.id = t.raw_entry_id
            WHERE t.embedding_1024 IS NOT NULL AND t.title_en IS NOT NULL
            ORDER BY t.embedding_1024 <=> %s::vector
            LIMIT %s""", (lit, lit, pool)).fetchall()]
    rows = [r for r in rows if float(r["sim"]) >= PROJECT_MIN_SIM]
    if not rows:
        return {"ready": True, "model": meta, "n_hits": 0, "blips": []}

    ids = [r["id"] for r in rows]
    chosen = {r["field_key"] for r in conn.execute(
        "SELECT field_key FROM workspace_field WHERE workspace_id=%s",
        (workspace_id,)).fetchall()}
    rated = {r["trend_id"] for r in conn.execute(
        "SELECT trend_id FROM signal_relevance WHERE workspace_id=%s AND trend_id = ANY(%s)",
        (workspace_id, ids)).fetchall()}

    # Heimatfeld: Cluster vor Mega-Trend vor Branche. Genau eines je Signal.
    home: dict[int, tuple[str, str, str]] = {}
    series_src: dict[str, list[dict]] = {}
    for m in conn.execute(
        """SELECT m.trend_id, m.run_id, m.cluster_idx, fc.label, fc.monthly_series
             FROM foresight_cluster_members m
             JOIN foresight_clusters fc
               ON fc.run_id = m.run_id AND fc.cluster_idx = m.cluster_idx
            WHERE m.trend_id = ANY(%s)
              AND m.run_id IN (SELECT max(id) FROM foresight_runs
                                WHERE scope LIKE %s GROUP BY scope)""",
        (ids, "vertical:%")).fetchall():
        key = f"cluster:{m['run_id']}:{m['cluster_idx']}"
        if m["trend_id"] not in home:
            home[m["trend_id"]] = ("cluster", key, m["label"])
            if key not in series_src:
                ms = m["monthly_series"]
                series_src[key] = ms if isinstance(ms, list) else json.loads(ms or "[]")

    for r in rows:
        if r["id"] in home:
            continue
        if r["mega_trend"]:
            home[r["id"]] = ("mega", f"mega:{r['mega_trend']}",
                             r["mega_trend"].replace("_", " ").title())
        elif r["primary_vertical"]:
            home[r["id"]] = ("vertical", f"vertical:{r['primary_vertical']}",
                             r["primary_vertical"])

    groups: dict[str, dict] = {}
    for r in rows:
        h = home.get(r["id"])
        if not h:
            continue
        kind, key, label = h
        g = groups.setdefault(key, {
            "kind": kind, "field_key": key, "label": label,
            "on_table": key in chosen, "n": 0, "n_rated": 0,
            "top_sim": 0.0, "_pts": [], "hits": [],
        })
        g["n"] += 1
        g["n_rated"] += 1 if r["id"] in rated else 0
        g["top_sim"] = max(g["top_sim"], float(r["sim"]))
        g["_pts"].append(hint_points(float(r["sim"])))
        if len(g["hits"]) < 3 and r["id"] not in rated:
            g["hits"].append({
                "id": r["id"], "title": r["title"], "source": r["source_name"],
                "url": r["source_url"], "date": str(r["d"]),
                "sim": round(float(r["sim"]), 3),
            })

    keep = sorted((g for g in groups.values() if g["n"] >= PROJECT_MIN_HITS),
                  key=lambda g: (-g["n"], -g["top_sim"]))[:PROJECT_MAX_BLIPS]

    # Reihen für Mega/Branche in je einem Durchgang — nicht je Blip einzeln.
    for col, kind in (("mega_trend", "mega"), ("primary_vertical", "vertical")):
        vals = [g["field_key"].split(":", 1)[1] for g in keep if g["kind"] == kind]
        for v, s in _series_by_column(conn, col, vals).items():
            series_src[f"{kind}:{v}"] = s

    calib = relevance_calibration(conn, workspace_id, direction)
    blips = []
    for g in keep:
        est = estimate_relevance(conn, direction, g["field_key"], calib=calib)
        if not est:
            continue
        rel = est["relevance"]
        mat = merge_maturity(curve_position(series_src.get(g["field_key"], [])), None)
        blips.append({
            "kind": g["kind"], "field_key": g["field_key"], "label": g["label"],
            "on_table": g["on_table"], "n": g["n"], "n_rated": g["n_rated"],
            "field_n": est["field_n"], "sampled": est["sampled"],
            "top_sim": round(g["top_sim"], 3),
            "peak": round(statistics.mean(g["_pts"]), 2),
            "relevance": rel, "rel_stage": relevance_stage(rel),
            "stage": mat["stage"], "basis": mat["basis"], "note": mat["note"],
            "hits": g["hits"],
        })
    blips.sort(key=lambda b: (-(b["relevance"] or 0), -b["n"]))
    return {"ready": True, "model": meta, "n_hits": len(rows),
            "n_placed": sum(b["n"] for b in blips), "blips": blips}
