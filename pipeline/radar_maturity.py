#!/usr/bin/env python3
"""Trendreife und Trendrelevanz nach Blechschmidt (Quick Guide Trendmanagement,
Kap. 8, S. 95–112).

Der tragende Satz des Kapitels (S. 100):

    „Die Trendreife bewertet den Trend auf seinen heutigen Zustand UNABHÄNGIG
     vom Unternehmen. Die Trendrelevanz ist ein Maß für die Bedeutung des Trends
     FÜR DAS JEWEILIGE UNTERNEHMEN."

Daraus folgt die Arbeitsteilung dieses Moduls und des ganzen Umbaus: die
**Reife** lässt sich aus Evidenz ableiten und gehört der Maschine; die
**Relevanz** hängt davon ab, wer fragt, und gehört ausschließlich dem Nutzer.
Umsatzpotenzial für *dieses* Unternehmen steht in keinem RSS-Feed.

Blechschmidts Qualitätsforderung (S. 101) ist zugleich die Bauvorschrift:

    „Sie sollte unabhängig von der Person und dem Zeitpunkt der Bewertung sein.
     Zudem muss die Genauigkeit der Ergebnisse eine eindeutige und
     reproduzierbare Positionierung im Trendradar ermöglichen."

Deshalb ist jedes Teilkriterium hier an eine **überprüfbare Schwelle** gebunden
und trägt seine Begründung mit. Sein 0–4-Schema („im Alltag sichtbar", „an
verschiedensten Stellen sichtbar") ist bewusst weich, weil ein Mensch es
anwendet; maschinell angewandt würden wir sonst die Beliebigkeit erben, ohne den
Fachverstand zu erben. Die Kalibrierläufe (docs/radar_redesign_proposal.md
§8–§11) sind das Fundament, auf dem die Schwellen hier stehen.

Ein Teilkriterium, das schweigt, geht NICHT als 0 in die Summe ein — sonst
bestraft fehlende Quellenabdeckung ein Feld, statt sie zu melden. Derselbe
Grundsatz wie „Absenz ist kein Befund".
"""

from __future__ import annotations

import json
import logging
from datetime import date

from .db import get_connection
from .radar_horizons import WORLD, _market_history

log = logging.getLogger("radar_maturity")

# ---------------------------------------------------------------------------
# Blechschmidts Reifestufen (Abb. 8.2, S. 98/99) mit seinen Handlungsbändern
# ---------------------------------------------------------------------------
MATURITY_STAGES: list[dict] = [
    {
        "key": "emerging", "label": "Entstehend", "band": "Beobachten",
        "min_score": 0.0,
        "blurb": "Der Trend ist neu entstanden und sein weiterer Verlauf noch "
                 "weitgehend unklar. Er sollte weiter beobachtet werden.",
    },
    {
        "key": "volatile", "label": "Volatil", "band": "Verstehen",
        "min_score": 1.0,
        "blurb": "Der Trend hat sich verfestigt und wird stabiler. Es ist Zeit, "
                 "ihn genauer zu verstehen und erste Möglichkeiten zu "
                 "identifizieren.",
    },
    {
        "key": "maturing", "label": "Reifend", "band": "Berücksichtigen",
        "min_score": 2.0,
        "blurb": "Der Trend hat sich gefestigt. Seine Auswirkungen sollten "
                 "systematisch in Entscheidungen berücksichtigt werden.",
    },
    {
        "key": "established", "label": "Etabliert", "band": "Implementieren",
        "min_score": 3.0,
        "blurb": "Der Trend ist in der Breite wirksam. Das Unternehmen muss "
                 "konsequent seine Chancen nutzen und die Risiken minimieren.",
    },
]

# Relevanzstufen (S. 99/100) — vom NUTZER gesetzt, hier nur die Skala.
RELEVANCE_STAGES: list[dict] = [
    {
        "key": "low", "label": "Gering", "band": "Opportunistisch",
        "min_score": 0.0,
        "blurb": "Die Chancen des Trends werden als gering eingeschätzt. Es "
                 "empfiehlt sich ein opportunistisches Vorgehen.",
    },
    {
        "key": "medium", "label": "Mittel", "band": "Gleichwertig",
        "min_score": 1.34,
        "blurb": "Die Chancen des Trends sind attraktiv. Sie sollten mit "
                 "vergleichbaren Alternativen bewertet werden, etwa anderen "
                 "Projekten oder Investitionsmöglichkeiten.",
    },
    {
        "key": "high", "label": "Hoch", "band": "Proaktiv",
        "min_score": 2.67,
        "blurb": "Die Chancen des Trends sind sehr groß und können das "
                 "Unternehmen langfristig verändern. Es sollte proaktiv in den "
                 "Trend investiert und Kompetenzen aufgebaut werden.",
    },
]


def stage_for(score: float | None, stages: list[dict]) -> dict | None:
    if score is None:
        return None
    out = stages[0]
    for s in stages:
        if score >= s["min_score"]:
            out = s
    return out


# ---------------------------------------------------------------------------
# Teilkriterien der Trendreife
# ---------------------------------------------------------------------------
# Angelehnt an das DB-Systel-Referenzbeispiel (S. 104: Marktstrategie,
# Marktverfügbarkeit, Interoperabilität, Ökosystem, Status der Peer Group),
# aber nur mit dem, was unser Korpus TATSÄCHLICH hergibt. „Status der Peer
# Group" fehlt bewusst: er ist unternehmensspezifisch und gehört damit auf die
# Relevanz-Achse. „Interoperabilität"/„Standardisierung" fehlt, weil der Korpus
# dazu nichts trägt — erfinden wäre schlimmer als weglassen.
CRITERIA: list[dict] = [
    {"key": "market", "label": "Marktverfügbarkeit", "weight": 3,
     "question": "Kann man es heute kaufen?"},
    {"key": "regulatory", "label": "Regulatorischer Zugang", "weight": 2,
     "question": "Ist der Weg zum Markt rechtlich offen?"},
    {"key": "demand", "label": "Nachfrage", "weight": 2,
     "question": "Gibt es belegte Käufer?"},
    {"key": "ecosystem", "label": "Ökosystem", "weight": 2,
     "question": "Wie viele unterschiedliche Akteure tragen das Feld?"},
    {"key": "applied", "label": "Anwendungsreife", "weight": 1,
     "question": "Wie viel davon ist angewandt statt erforscht?"},
    {"key": "persistence", "label": "Verstetigung", "weight": 2,
     "question": "Wie lange trägt sich das Feld schon am Markt?"},
]

# Wortlaut der Punktwerte — im Frontend einsehbar, weil Blechschmidt genau das
# verlangt: „Präzise Vorgaben sorgen dafür, dass gleiche Informationen
# unabhängig vom Bewerter zur selben Bewertung führen." (S. 103)
ANCHORS: dict[str, dict[int, str]] = {
    "market": {
        0: "keine Marktevidenz",
        1: "nur Pilot- oder Demonstrationsvorhaben",
        2: "Produkteinführungen in einer Jurisdiktion",
        3: "Produkteinführungen in mehreren, oder Handel in einer",
        4: "laufender Handel in mehreren Jurisdiktionen",
    },
    "regulatory": {
        0: "ausdrückliche Blockade oder Ablehnung",
        1: "der Weg wird erst gebaut (Konsultationen, Strategien)",
        2: "Verfahren laufen oder Studien sind genehmigt",
        3: "Zulassung in einer Jurisdiktion erteilt",
        4: "Zulassungen in mehreren Jurisdiktionen erteilt",
    },
    "demand": {
        0: "keine Nachfrageevidenz",
        1: "Marktbewegung, aber kein belegter Käufer",
        2: "Nachfrage bildet sich",
        3: "Nachfrage in einem Teil der Jurisdiktionen belegt",
        4: "Nachfrage in allen bewerteten Jurisdiktionen belegt",
    },
    "ecosystem": {
        0: "eine einzige Quelle trägt über 60 % des Felds",
        1: "stark konzentriert — größte Quelle über 35 %",
        2: "mehrere Quellen, größte unter 35 %",
        3: "breite Quellenlage — größte Quelle unter 20 %",
        4: "sehr breite Quellenlage — größte Quelle unter 10 %",
    },
    "applied": {
        0: "unter 2 % angewandte Signale — reiner Erkenntnisstrom",
        1: "2–7 % angewandt",
        2: "7–15 % angewandt",
        3: "15–30 % angewandt",
        4: "über 30 % angewandt",
    },
    "persistence": {
        0: "keine Markthistorie",
        1: "Markthistorie unter 3 aktiven Jahren",
        2: "3–5 aktive Marktjahre",
        3: "6–8 aktive Marktjahre",
        4: "über 8 aktive Marktjahre, beginnend vor mehr als einem Jahrzehnt",
    },
}


def _named(cells: list[dict], dim: str) -> list[dict]:
    return [c for c in cells if c["dimension"] == dim and c["region"] != WORLD]


def _score_market(cells: list[dict]) -> tuple[int | None, str]:
    named = _named(cells, "market")
    if not named or all(c["horizon"] is None and c.get("basis") in
                        ("blind", "silent", None) for c in named):
        return None, "Keine lesbare Marktevidenz — die Zelle schweigt."
    trading = [c for c in named if c.get("basis") == "trading"]
    commercial = [c for c in named if c.get("basis") == "commercial"]
    entry = [c for c in named if c.get("basis") == "entry"]
    # Der Spitzenwert verlangt laufenden HANDEL in mehr als einer Jurisdiktion.
    # Mit „Handel irgendwo = 4" landeten im ersten Lauf alle FOOD-Cluster auf
    # „etabliert"; die Skala muss oben eng sein, sonst unterscheidet sie nichts.
    if len(trading) >= 2:
        return 4, f"Laufender Handel in {len(trading)} Jurisdiktionen belegt."
    if trading or len(commercial) >= 2:
        return 3, ("Laufender Handel in einer Jurisdiktion belegt."
                   if trading else
                   f"Produkteinführungen in {len(commercial)} Jurisdiktionen.")
    if commercial:
        return 2, "Produkteinführungen in einer Jurisdiktion."
    if entry:
        return 1, "Nur Pilot- oder Demonstrationsvorhaben."
    return 0, "Signale vorhanden, aber keine Markteinführung darunter."


def _score_regulatory(cells: list[dict]) -> tuple[int | None, str]:
    named = _named(cells, "regulatory")
    bases = [c.get("basis") for c in named]
    if not named or all(b in ("unregulated", "silent", "uncovered",
                              "unreadable", None) for b in bases):
        return None, ("Kein Zulassungsregime sichtbar — für dieses Feld ist die "
                      "Frage entweder gegenstandslos oder unsere Quellen sehen "
                      "sie nicht. Fließt nicht in die Reife ein.")
    granted = [c for c in named if c.get("basis") == "granted"]
    blocked = [c for c in named if c.get("basis") in ("denied", "blockade")]
    live = [c for c in named if c.get("basis") in ("filed", "trial")]
    if blocked and not granted:
        return 0, f"Ausdrückliche Blockade in {len(blocked)} Jurisdiktion(en)."
    if len(granted) >= 2:
        return 4, f"Zulassungen in {len(granted)} Jurisdiktionen erteilt."
    if granted:
        return 3, "Zulassung in einer Jurisdiktion erteilt."
    if live:
        return 2, f"{len(live)} laufende(s) Verfahren oder genehmigte Studien."
    return 1, "Der Zulassungsweg wird erst gebaut."


def _score_demand(cells: list[dict]) -> tuple[int | None, str]:
    named = _named(cells, "adoption")
    placed = [c for c in named if c["horizon"]]
    if not placed:
        return None, "Keine lesbare Nachfrageevidenz — die Zelle schweigt."
    h1 = [c for c in placed if c["horizon"] == "H1"]
    h2 = [c for c in placed if c["horizon"] == "H2"]
    if len(h1) >= 2 and len(h1) == len(placed):
        return 4, f"Nachfrage in allen {len(h1)} bewerteten Jurisdiktionen belegt."
    if h1:
        return 3, f"Nachfrage in {len(h1)} von {len(placed)} Jurisdiktionen belegt."
    if h2:
        return 2, "Nachfrage bildet sich."
    return 1, "Marktbewegung, aber kein belegter Käufer."


def _score_ecosystem(rows: list[dict]) -> tuple[int | None, str]:
    """Breite des Trägerkreises — gemessen als KONZENTRATION, nicht als Anzahl.

    Erster Versuch zählte unterscheidbare Quellen. Das misst aber die
    Clustergröße: ein Feld mit 8.000 Signalen erreicht in einem Korpus mit 243
    Quellen fast zwangsläufig über 60, und alle Felder landeten auf 4. Der
    Anteil der GRÖSSTEN Quelle ist dagegen größenunabhängig und sagt das, was
    gemeint ist: trägt ein einzelnes Medium das Feld, oder viele?
    """
    named = [r.get("source_name") for r in rows if r.get("source_name")]
    if len(named) < 30:
        return None, f"Zu wenige Signale mit Quellenangabe ({len(named)})."
    counts: dict[str, int] = {}
    for s in named:
        counts[s] = counts.get(s, 0) + 1
    top = max(counts.values()) / len(named)
    n = len(counts)
    step = (4 if top < 0.10 else 3 if top < 0.20 else
            2 if top < 0.35 else 1 if top < 0.60 else 0)
    return step, (f"{n} Quellen tragen das Feld, die größte davon "
                  f"{top:.0%} der Signale. Markennennungen bleiben außen vor — "
                  "im Korpus zu dünn (12k von 1,13 Mio. Trends).")


def _score_applied(rows: list[dict]) -> tuple[int | None, str]:
    sem = [r for r in rows if r.get("semantic")]
    if len(sem) < 20:
        return None, f"Zu wenige klassifizierte Signale ({len(sem)}) für eine Quote."
    applied = sum(1 for r in sem if r["trend_signal_type"] in
                  ("product_launch", "partnership"))
    share = applied / len(sem)
    step = (4 if share >= 0.30 else 3 if share >= 0.15 else
            2 if share >= 0.07 else 1 if share >= 0.02 else 0)
    return step, (f"{applied} von {len(sem)} Signalen sind angewandt "
                  f"({share:.0%}), der Rest forschungs- oder diskursseitig.")


def _score_persistence(rows: list[dict], today: date) -> tuple[int | None, str]:
    hist = _market_history(rows, today)
    years, first = hist["active_years"], hist["first_year"]
    if not first:
        return 0, "Keine Markthistorie im Korpus."
    old = first <= today.year - 10
    step = (4 if years >= 8 and old else 3 if years >= 6 else
            2 if years >= 3 else 1)
    return step, (f"Marktsignale in {years} aktiven Jahren seit {first}"
                  + (" — mehr als ein Jahrzehnt Vorlauf." if old else "."))


def maturity(rows: list[dict], cells: list[dict], *,
             today: date | None = None) -> dict:
    """Trendreife eines Felds: Teilpunkte, gewichtete Summe, Stufe."""
    today = today or date.today()
    raw = {
        "market": _score_market(cells),
        "regulatory": _score_regulatory(cells),
        "demand": _score_demand(cells),
        "ecosystem": _score_ecosystem(rows),
        "applied": _score_applied(rows),
        "persistence": _score_persistence(rows, today),
    }
    parts, num, den = [], 0.0, 0.0
    for c in CRITERIA:
        pts, why = raw[c["key"]]
        parts.append({**{k: c[k] for k in ("key", "label", "weight", "question")},
                      "points": pts, "rationale": why,
                      "anchor": ANCHORS[c["key"]].get(pts) if pts is not None else None})
        if pts is not None:
            num += pts * c["weight"]
            den += c["weight"]
    score = round(num / den, 2) if den else None
    st = stage_for(score, MATURITY_STAGES)
    return {
        "score": score,
        "stage": st["key"] if st else None,
        "stage_label": st["label"] if st else None,
        "band": st["band"] if st else None,
        "blurb": st["blurb"] if st else None,
        "criteria": parts,
        "weight_used": den,
        "weight_total": sum(c["weight"] for c in CRITERIA),
    }


# ---------------------------------------------------------------------------
# Relevanz: das Schema gehört dem Nutzer, der Vorschlag der Maschine
# ---------------------------------------------------------------------------
# Vorbelegt nach dem DB-Systel-Referenzbeispiel (S. 104), das Blechschmidt als
# „DB Business Value" beschreibt: „Wie wichtig ist es für die Deutsche Bahn,
# sich mit dem Trend auseinanderzusetzen?" — Chancen und Risiken auf zehn Jahre.
DEFAULT_RELEVANCE_CRITERIA: list[dict] = [
    {"key": "revenue", "label": "Umsatzpotenzial", "weight": 3,
     "question": "Wie viel Umsatz kann dieser Trend für uns eröffnen?",
     "anchor_0": "kein erkennbarer Umsatzbezug",
     "anchor_4": "eröffnet ein wesentliches neues Umsatzfeld"},
    {"key": "efficiency", "label": "Effizienzpotenzial", "weight": 2,
     "question": "Wie stark kann er unsere Kosten oder Prozesse verändern?",
     "anchor_0": "keine Wirkung auf unsere Prozesse",
     "anchor_4": "verändert unsere Kostenstruktur grundlegend"},
    {"key": "disruption", "label": "Disruptionspotenzial", "weight": 3,
     "question": "Wie stark bedroht er unser bestehendes Geschäft?",
     "anchor_0": "bedroht nichts, was wir tun",
     "anchor_4": "stellt unser Geschäftsmodell infrage"},
    {"key": "regulatory", "label": "Regulatorisches", "weight": 2,
     "question": "Zwingt uns Regulierung, uns damit zu befassen?",
     "anchor_0": "keine regulatorische Betroffenheit",
     "anchor_4": "wir sind rechtlich zum Handeln verpflichtet"},
]


def suggest_relevance(scope_meta: dict | None, mat: dict) -> dict:
    """Maschineller VORSCHLAG je Relevanzkriterium — kein gesetzter Wert.

    Owner-Entscheidung 2026-08-04: das Raster bleibt leer, der Vorschlag steht
    sichtbar daneben. Damit ist ein Abweichen des Nutzers erkennbar, statt in
    einer Vorbelegung zu verschwinden — und die Relevanz bleibt seine Aussage,
    nicht unsere.

    Belegt wird nur, was wir wirklich messen: das Disruptionspotenzial
    korreliert mit dem Anteilstrend eines Felds (steigender Anteil am
    Signalaufkommen), das Regulatorische mit der Regulatorik-Zelle. Umsatz- und
    Effizienzpotenzial sind unternehmensspezifisch — dafür gibt es KEINEN
    Vorschlag, und das Feld sagt das auch.
    """
    out: dict[str, dict] = {}
    meta = scope_meta or {}
    delta = meta.get("sov_delta_pp")
    if isinstance(delta, (int, float)):
        pts = (4 if delta >= 8 else 3 if delta >= 3 else 2 if delta >= -1
               else 1 if delta >= -6 else 0)
        out["disruption"] = {
            "points": pts,
            "why": (f"Anteil am Signalaufkommen {delta:+.1f} Prozentpunkte. Das "
                    "misst die Bewegung im Korpus, nicht die Bedrohung für Sie "
                    "— es ist ein Anhaltspunkt, keine Bewertung."),
        }
    reg = next((c for c in mat["criteria"] if c["key"] == "regulatory"), None)
    if reg and reg["points"] is not None:
        out["regulatory"] = {
            "points": min(4, max(0, 4 - reg["points"])) if reg["points"] <= 2 else 2,
            "why": (f"Regulatorischer Zugang: {reg['rationale']} Je enger der "
                    "Zugang, desto eher zwingt er zum Handeln."),
        }
    for key in ("revenue", "efficiency"):
        out[key] = {
            "points": None,
            "why": ("Unternehmensspezifisch — dazu kann unser Korpus nichts "
                    "sagen. Diese Bewertung gehört Ihnen."),
        }
    return out


def relevance_score(scores: dict[str, int | None],
                    criteria: list[dict]) -> dict:
    """Gewichtete Relevanz aus den vom Nutzer gesetzten Punkten."""
    num = den = 0.0
    n_set = 0
    for c in criteria:
        v = scores.get(c["key"])
        if v is None:
            continue
        num += v * c["weight"]
        den += c["weight"]
        n_set += 1
    score = round(num / den, 2) if den else None
    st = stage_for(score, RELEVANCE_STAGES)
    return {
        "score": score, "n_set": n_set, "n_criteria": len(criteria),
        "stage": st["key"] if st else None,
        "stage_label": st["label"] if st else None,
        "band": st["band"] if st else None,
        "blurb": st["blurb"] if st else None,
        "complete": n_set == len(criteria),
    }


# ---------------------------------------------------------------------------
# Persistenz
# ---------------------------------------------------------------------------
SCHEMA = """
CREATE TABLE IF NOT EXISTS radar_relevance_criteria (
    id SERIAL PRIMARY KEY,
    config_id INTEGER REFERENCES radar_configs(id) ON DELETE CASCADE,
    key TEXT NOT NULL,
    label TEXT NOT NULL,
    question TEXT,
    anchor_0 TEXT,
    anchor_4 TEXT,
    weight INTEGER DEFAULT 1,
    sort_order INTEGER DEFAULT 0,
    UNIQUE (config_id, key)
);
CREATE TABLE IF NOT EXISTS radar_relevance_scores (
    id SERIAL PRIMARY KEY,
    config_id INTEGER REFERENCES radar_configs(id) ON DELETE CASCADE,
    scope_slug TEXT NOT NULL,
    criterion_key TEXT NOT NULL,
    points INTEGER,
    note TEXT,
    rated_by TEXT,
    rated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (config_id, scope_slug, criterion_key, rated_by)
);
CREATE INDEX IF NOT EXISTS idx_relscores_cfg
    ON radar_relevance_scores (config_id, scope_slug);
CREATE TABLE IF NOT EXISTS radar_maturity (
    id SERIAL PRIMARY KEY,
    run_id INTEGER REFERENCES radar_runs(id) ON DELETE CASCADE,
    scope_slug TEXT NOT NULL,
    score REAL,
    stage TEXT,
    criteria JSONB,
    relevance_hint JSONB,
    UNIQUE (run_id, scope_slug)
);
"""


def migrate() -> None:
    with get_connection() as conn:
        conn.executescript(SCHEMA)
        conn.commit()
    log.info("Reife-/Relevanz-Tabellen migriert")


def seed_relevance_criteria(config_id: int,
                            criteria: list[dict] | None = None) -> None:
    """Kriterienschema eines Radars anlegen — leer bewertet, nur die Fragen."""
    criteria = criteria or DEFAULT_RELEVANCE_CRITERIA
    with get_connection() as conn:
        for i, c in enumerate(criteria):
            exists = conn.execute(
                "SELECT id FROM radar_relevance_criteria WHERE config_id=%s "
                "AND key=%s", (config_id, c["key"])).fetchone()
            if exists:
                continue
            conn.execute(
                "INSERT INTO radar_relevance_criteria (config_id, key, label, "
                "question, anchor_0, anchor_4, weight, sort_order) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (config_id, c["key"], c["label"], c.get("question"),
                 c.get("anchor_0"), c.get("anchor_4"), c.get("weight", 1), i))
        conn.commit()


def store_maturity(conn, run_id: int, scope_slug: str, mat: dict,
                   hint: dict | None = None) -> None:
    conn.execute(
        "INSERT INTO radar_maturity (run_id, scope_slug, score, stage, criteria,"
        " relevance_hint) VALUES (%s,%s,%s,%s,%s,%s) "
        "ON CONFLICT (run_id, scope_slug) DO UPDATE "
        "SET score=EXCLUDED.score, stage=EXCLUDED.stage, "
        "criteria=EXCLUDED.criteria, relevance_hint=EXCLUDED.relevance_hint",
        (run_id, scope_slug, mat["score"], mat["stage"],
         json.dumps(mat["criteria"]), json.dumps(hint or {})))
