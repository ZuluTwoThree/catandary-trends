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
STAGE_LABEL = {"emerging": "Entstehend", "volatile": "Volatil",
               "maturing": "Reifend", "established": "Etabliert"}
STAGE_BAND = {"emerging": "Beobachten", "volatile": "Verstehen",
              "maturing": "Berücksichtigen", "established": "Implementieren"}

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
        return {"stage": None, "reason": "Zu kurze oder zu dünne Reihe "
                                         f"({len(pts)} verwertbare Monate).",
                "n_months": len(pts)}

    shares = _smooth([float(p["share"]) for p in pts])
    months = [p["m"] for p in pts]
    peak_i = max(range(len(shares)), key=lambda i: shares[i])
    peak = shares[peak_i]
    now = statistics.mean(shares[-6:]) if len(shares) >= 6 else shares[-1]
    if peak <= 0:
        return {"stage": None, "reason": "Kein Anteil messbar.", "n_months": len(pts)}

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
            f"Junge, steil steigende Reihe: {age} verwertbare Monate, "
            f"letzte zwei Jahre {slope:+.0%}. Anstieg aus dem Nichts — "
            "Innovation Trigger.")
    elif from_peak >= 0.75 and vola > 0.35:
        stage, why = "volatile", (
            f"Nahe am Gipfel ({from_peak:.0%} des Maximums) und stark "
            f"schwankend (Streuung {vola:.0%}) — Peak of Inflated Expectations.")
    elif from_peak < 0.45 and recovery < 0.1:
        stage, why = "volatile", (
            f"Deutlich unter dem Gipfel ({from_peak:.0%}) ohne Erholung — "
            "Tal der Enttäuschungen. Ob es wieder steigt, ist offen.")
    elif recovery >= 0.1 and from_peak < 0.9:
        stage, why = "maturing", (
            f"Erholung nach dem Einbruch ({recovery:+.0%} seit dem Tief, "
            f"{from_peak:.0%} des Gipfels) — Slope of Enlightenment.")
    elif vola <= 0.25 and age >= 96:
        stage, why = "established", (
            f"Seit {age // 12} Jahren stabil bei {now:.1%} Anteil "
            f"(Streuung {vola:.0%}) — Plateau.")
    else:
        stage, why = None, (
            f"Kein eindeutiges Muster: {from_peak:.0%} des Gipfels, "
            f"Streuung {vola:.0%}, Trend {slope:+.0%}.")

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
                "note": f"Verlauf und Marktevidenz stimmen überein. {curve['reason']}"}
    if c_stage and ev_stage:
        # Der reifere der beiden gewinnt NICHT automatisch — wir nehmen den
        # niedrigeren und benennen den Widerspruch. Aufmerksamkeit ohne Markt
        # ist kein Reifebeleg.
        lower = min(c_stage, ev_stage, key=lambda s: STAGES.index(s))
        return {"stage": lower, "basis": "conflict",
                "note": (f"Verlauf und Evidenz widersprechen sich: die Kurve sagt "
                         f"{STAGE_LABEL[c_stage].lower()}, die Marktevidenz "
                         f"{STAGE_LABEL[ev_stage].lower()}. Gezeigt wird die "
                         f"vorsichtigere Lesart. {curve['reason']}")}
    if ev_stage:
        return {"stage": ev_stage, "basis": "evidence",
                "note": ("Aus der Marktevidenz — der Verlauf gibt kein "
                         f"eindeutiges Muster her. {curve.get('reason','')}")}
    if c_stage:
        return {"stage": c_stage, "basis": "curve",
                "note": f"Aus dem Verlaufsmuster. {curve['reason']}"}
    return {"stage": FALLBACK_STAGE, "basis": "default",
            "note": ("Weder Verlauf noch Marktevidenz sind eindeutig. Das Feld "
                     "steht deshalb auf volatil — dem einzigen Band, dessen "
                     "Empfehlung „genauer hinsehen“ lautet. "
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


def field_trend_ids(conn, field_key: str, limit: int = 40_000) -> list[int]:
    """Alle Signal-IDs eines Felds. Ein Feld ist ein Cluster, ein Mega-Trend
    oder eine Vertikale — die drei Flughöhen aus dem Auftrag."""
    kind, rest = parse_field_key(field_key)
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


def relevance_stage(score: float | None) -> str | None:
    """Blechschmidts drei Relevanzstufen aus dem 0–4-Mittel."""
    if score is None:
        return None
    return "high" if score >= 2.67 else "medium" if score >= 1.34 else "low"
