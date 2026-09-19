"""VOI-Planer und Anfrage-Dedup des Dossier-Rechercheurs — Stufe 3 des Plans
docs/plan_dossier_agent_2026-09-18.md („Der nutzenbasierte Rechercheur").

Bis Runde 25 liefen der Korpus- und der Web-Agent feste Schrittzahlen ab
(6 Korpus-Schritte, 14 Web-Schritte) und das Modell entschied allein, welche
Lücke als nächste dran ist und wann Schluss ist. Jetzt trägt jede offene Lücke

  * ein **Gewicht** nach Herkunft: Pflichtpunkt des Auftrags 3,0 > Audit-Lücke
    2,0 > Planschritt 1,0 > festes Muster (Recht/Markt) 0,7;
  * eine **Deckung** in [0, 1]: aufgenommene + gelesene Quellen zur Lücke,
    sättigend bei 3 (`COVERAGE_SATURATION`);
  * eine **Erfolgswahrscheinlichkeit** aus `dossier_query_stats` (Beta-Mittel je
    Schablone, Thompson-Sampling bei ≥ 2 Schablonen derselben Lückenart) und
    `dossier_source_priors` (kleiner Bonus, wenn das Feld bewährte Hosts kennt);
    Rückfall 0,5;
  * **Kosten** je Aktion: Suche 1, Abruf 2, Öffnen 0,5.

`next_action()` gibt die Lücke mit dem höchsten
`weight · (1 − coverage) · p_success / cost` zurück; `should_stop()` ist wahr,
wenn der beste erwartete Zuwachs unter `DOSSIER_VOI_MIN_GAIN` (Default 0,15)
fällt oder das Aktionsbudget des Laufs aufgebraucht ist. Je Lücke und Phase
höchstens `PER_GAP_BUDGET` (3) Aktionen. Das Modell schlägt weiterhin die
konkrete Anfrage vor — WELCHE Lücke und WANN Schluss ist, entscheidet der
Planer; ein „finish" des Modells gilt nur, wenn der Planer zustimmt oder das
Budget aus ist. Jede Entscheidung steht im Trace (`result["voi"]`).

**Fast-Dubletten:** vor jeder Anfrage wird sie mit den bisherigen des Laufs
verglichen — Cosinus über den CPU-Embedder (`RESEARCH_EMBED_HOST`) ≥ 0,9 →
übersprungen; ist der Embedder nicht erreichbar, Token-Jaccard ≥ 0,8.
"""
from __future__ import annotations

import logging
import math
import os
import random
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

WEIGHTS = {"must": 3.0, "audit": 2.0, "plan": 1.0, "pattern": 0.7}
COSTS = {"search": 1.0, "fetch": 2.0, "open": 0.5}
COVERAGE_SATURATION = 3
PER_GAP_BUDGET = 3
DEFAULT_MIN_GAIN = 0.15
PRIOR_P = 0.5
PRIOR_HOST_BONUS = 0.1        # das Feld kennt bewährte Hosts → etwas wahrscheinlicher
FETCH_P = 0.7                 # ein aufgenommener Treffer ist meistens lesbar
COSINE_DUP = 0.9
JACCARD_DUP = 0.8
# Umrechnung Budget-Minuten → Aktionen: ein 30-Minuten-Lauf hat heute
# 6 Korpus- + 14 Web-Aktionen; das Budget aus dem Auftrag skaliert linear.
BASELINE_MINUTES = 30.0
BASELINE_ACTIONS = {"corpus": 6, "web": 14}
MIN_ACTIONS = 2
MAX_ACTIONS = 40


def min_gain() -> float:
    try:
        return float(os.getenv("DOSSIER_VOI_MIN_GAIN", str(DEFAULT_MIN_GAIN)) or DEFAULT_MIN_GAIN)
    except ValueError:
        return DEFAULT_MIN_GAIN


def action_budget(phase: str, default: int, budget_minutes=None) -> int:
    """Aktionsbudget einer Phase: aus `brief.budget_minutes`, sonst der
    bisherige Schrittwert (`max_steps` / `web_steps`)."""
    if budget_minutes is None:
        return int(default)
    try:
        minutes = float(budget_minutes)
    except (TypeError, ValueError):
        return int(default)
    if minutes <= 0:
        return int(default)
    base = BASELINE_ACTIONS.get(phase, default)
    return max(MIN_ACTIONS, min(MAX_ACTIONS, round(base * minutes / BASELINE_MINUTES)))


@dataclass
class Gap:
    key: str                  # z. B. "must:0", "audit:2", "plan:1", "pattern:regulatory"
    text: str
    kind: str                 # must | audit | plan | pattern
    index: int | None = None  # Index in der Lückenliste des Laufs (Ledger)
    weight: float = 1.0
    admitted: int = 0         # aufgenommene Quellen
    read: int = 0             # gelesene Quellen (Abruf/Öffnen)
    unread: int = 0           # aufgenommen, aber noch ungelesen (→ fetch/open)
    actions: int = 0          # in dieser Phase verbrauchte Aktionen
    declined: int = 0         # „finish" des Modells auf dieser Lücke
    p_success: float = PRIOR_P
    template: str | None = None
    extra: dict = field(default_factory=dict)

    @property
    def coverage(self) -> float:
        return min(1.0, (self.admitted + self.read) / float(COVERAGE_SATURATION))


@dataclass
class Decision:
    gap: Gap
    action: str
    score: float
    cost: float

    def as_dict(self) -> dict:
        return {"gap": self.gap.key, "kind": self.gap.kind, "text": self.gap.text[:120],
                "action": self.action, "score": round(self.score, 3),
                "weight": self.gap.weight, "coverage": round(self.gap.coverage, 2),
                "p_success": round(self.gap.p_success, 2), "cost": self.cost,
                "template": self.gap.template}


def make_gaps(items: list[tuple[str, str]], offset: int = 0) -> list[Gap]:
    """[(kind, text)] → Lücken mit Gewicht; `index` = Position in der Liste."""
    out: list[Gap] = []
    for i, (kind, text) in enumerate(items):
        kind = kind if kind in WEIGHTS else "audit"
        out.append(Gap(key=f"{kind}:{offset + i}", text=str(text), kind=kind,
                       index=offset + i, weight=WEIGHTS[kind]))
    return out


class Planner:
    """Eine Phase (Korpus- oder Web-Agent) über eine Lückenliste."""

    def __init__(self, gaps: list[Gap], *, phase: str, budget: int,
                 gain_floor: float | None = None, per_gap: int = PER_GAP_BUDGET,
                 stats=None, prior_hosts=(), rng: random.Random | None = None):
        self.gaps = list(gaps)
        self.phase = phase
        self.budget = int(budget)
        self.used = 0
        self.gain_floor = min_gain() if gain_floor is None else float(gain_floor)
        self.per_gap = int(per_gap)
        self.trace: list[dict] = []
        self.skipped: list[dict] = []
        self.rng = rng or random.Random(73)
        self.prior_bonus = PRIOR_HOST_BONUS if prior_hosts else 0.0
        self._stats_rows: dict[str, list[dict]] = {}
        if stats is not None:
            for g in self.gaps:
                if g.kind not in self._stats_rows:
                    try:
                        self._stats_rows[g.kind] = list(stats(g.kind) or [])
                    except Exception as exc:                        # noqa: BLE001
                        logger.warning("query stats unavailable for %s: %r", g.kind, exc)
                        self._stats_rows[g.kind] = []
        self._refresh_p()

    # -- Erfolgswahrscheinlichkeit ----------------------------------------
    def _refresh_p(self) -> None:
        from pipeline import dossier_query_stats as qs
        for g in self.gaps:
            p, tmpl = qs.p_success(self._stats_rows.get(g.kind) or [], rng=self.rng, prior=PRIOR_P)
            g.p_success = min(1.0, p + self.prior_bonus)
            g.template = tmpl

    # -- Bewertung --------------------------------------------------------
    @staticmethod
    def suggested_action(gap: Gap, phase: str) -> str:
        if gap.unread > 0:
            return "fetch" if phase == "web" else "open"
        return "search"

    def score(self, gap: Gap, action: str | None = None) -> tuple[float, str, float]:
        action = action or self.suggested_action(gap, self.phase)
        cost = COSTS.get(action, 1.0)
        p = FETCH_P if action in ("fetch", "open") else gap.p_success
        return gap.weight * (1.0 - gap.coverage) * p / cost, action, cost

    def open_gaps(self) -> list[Gap]:
        return [g for g in self.gaps if g.actions < self.per_gap and g.coverage < 1.0]

    def best(self) -> Decision | None:
        best: Decision | None = None
        for g in self.open_gaps():
            s, action, cost = self.score(g)
            if best is None or s > best.score + 1e-9:
                best = Decision(g, action, s, cost)
        return best

    def budget_left(self) -> int:
        return max(0, self.budget - self.used)

    def should_stop(self) -> bool:
        if self.budget_left() <= 0:
            return True
        b = self.best()
        return b is None or b.score < self.gain_floor

    def next_action(self) -> Decision | None:
        """Argmax über die offenen Lücken; None, wenn Schluss ist. Jede
        Entscheidung landet im Trace."""
        if self.should_stop():
            b = self.best()
            self.trace.append({"phase": self.phase, "decision": "stop",
                               "reason": ("budget" if self.budget_left() <= 0 else
                                          "no gap left" if b is None else "gain below floor"),
                               "best": b.as_dict() if b else None,
                               "gain_floor": self.gain_floor, "used": self.used})
            return None
        d = self.best()
        assert d is not None
        self.trace.append({"phase": self.phase, "decision": "act", **d.as_dict(),
                           "used": self.used, "budget": self.budget})
        return d

    # -- Rückmeldung ------------------------------------------------------
    def find(self, key_or_index) -> Gap | None:
        for g in self.gaps:
            if g.key == key_or_index or (isinstance(key_or_index, int) and g.index == key_or_index):
                return g
        return None

    def record(self, gap: Gap | None, action: str, *, admitted: int = 0, read: int = 0,
               unread_delta: int = 0, note: str | None = None) -> None:
        """Eine ausgeführte (oder abgelehnte/übersprungene) Aktion verbuchen.
        Jeder Modellaufruf kostet eine Budgeteinheit — auch ein abgelehnter,
        sonst könnte das Modell den Lauf mit „finish" endlos verzögern."""
        self.used += 1
        if gap is not None:
            gap.actions += 1
            gap.admitted += int(admitted)
            gap.read += int(read)
            gap.unread = max(0, gap.unread + int(unread_delta))
            if action == "finish":
                gap.declined += 1
        self.trace.append({"phase": self.phase, "decision": "result",
                           "gap": gap.key if gap else None, "action": action,
                           "admitted": admitted, "read": read, "note": note,
                           "coverage": round(gap.coverage, 2) if gap else None})

    def accept_finish(self) -> bool:
        """Das Modell will aufhören: nur, wenn der Planer zustimmt."""
        return self.should_stop()

    def summary(self) -> dict:
        return {"phase": self.phase, "budget": self.budget, "used": self.used,
                "gain_floor": self.gain_floor,
                "gaps": [{"key": g.key, "kind": g.kind, "weight": g.weight,
                          "coverage": round(g.coverage, 2), "actions": g.actions,
                          "admitted": g.admitted, "read": g.read,
                          "p_success": round(g.p_success, 2), "template": g.template}
                         for g in self.gaps],
                "trace": self.trace, "skipped": self.skipped}

    def prompt_line(self, d: Decision) -> str:
        tmpl = f" A query shape that worked before for this kind of gap: \"{d.gap.template}\"." if d.gap.template else ""
        idx = f" (open question {d.gap.index})" if d.gap.index is not None else ""
        return (f"PLANNER — work on THIS gap now{idx}: {d.gap.text[:200]}\n"
                f"  kind={d.gap.kind}, weight={d.gap.weight}, coverage={d.gap.coverage:.2f}, "
                f"expected gain={d.score:.2f}; suggested action: {d.action}.{tmpl}\n"
                f"  Finish is accepted only when the planner sees no gap worth another action.\n")


# --------------------------------------------------------------------------
# Fast-Dubletten
# --------------------------------------------------------------------------

_TOK = re.compile(r"[a-z0-9][a-z0-9+#.'-]*")


def tokens(query: str) -> set[str]:
    return {t.strip(".'-") for t in _TOK.findall(str(query or "").lower()) if t.strip(".'-")}


def jaccard(a: str, b: str) -> float:
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / float(len(ta | tb))


def cosine(u: list[float], v: list[float]) -> float:
    if not u or not v or len(u) != len(v):
        return 0.0
    dot = sum(x * y for x, y in zip(u, v))
    nu = math.sqrt(sum(x * x for x in u))
    nv = math.sqrt(sum(y * y for y in v))
    return dot / (nu * nv) if nu and nv else 0.0


def would_skip_jaccard(queries: list[str], threshold: float = JACCARD_DUP) -> list[int]:
    """Offline-Messung: Indizes der Anfragen, die gegen eine FRÜHERE des Laufs
    per Jaccard ≥ threshold als Dublette gälten."""
    out: list[int] = []
    kept: list[str] = []
    for i, q in enumerate(queries):
        if any(jaccard(q, k) >= threshold for k in kept):
            out.append(i)
        else:
            kept.append(q)
    return out


class QueryDedup:
    """Merkt sich die Anfragen eines Laufs und erkennt Fast-Dubletten.

    `embed`: callable(query) → Vektor; None oder ein Fehler beim ersten Aufruf
    schaltet für den Rest des Laufs auf Jaccard um (einmal geloggt)."""

    def __init__(self, embed=None, cos_threshold: float = COSINE_DUP,
                 jac_threshold: float = JACCARD_DUP):
        self.embed = embed
        self.cos_threshold = float(cos_threshold)
        self.jac_threshold = float(jac_threshold)
        self.queries: list[str] = []
        self.vectors: list[list[float] | None] = []
        self.skips: list[dict] = []
        self.method = "embedding" if embed is not None else "jaccard"

    def _vector(self, q: str) -> list[float] | None:
        if self.embed is None:
            return None
        try:
            v = self.embed(q)
            return list(v) if v else None
        except Exception as exc:                                    # noqa: BLE001
            logger.warning("query dedup: embedder unavailable (%s) — token Jaccard from here", exc)
            self.embed = None
            self.method = "jaccard"
            return None

    def check(self, q: str) -> tuple[bool, str, float, str | None]:
        """(Dublette?, Verfahren, Ähnlichkeit, nächste frühere Anfrage)."""
        q = " ".join(str(q or "").split())
        if not q:
            return False, self.method, 0.0, None
        if q in self.queries:
            return True, "exact", 1.0, q
        v = self._vector(q)
        best, best_q = 0.0, None
        if v is not None:
            for pq, pv in zip(self.queries, self.vectors):
                if pv is None:
                    continue
                c = cosine(v, pv)
                if c > best:
                    best, best_q = c, pq
            if best >= self.cos_threshold:
                return True, "embedding", best, best_q
            if any(pv is not None for pv in self.vectors) or not self.queries:
                return False, "embedding", best, best_q
            # Embedder da, aber keine frühere Anfrage trägt einen Vektor: Jaccard
        bj, bq = 0.0, None
        for pq in self.queries:
            j = jaccard(q, pq)
            if j > bj:
                bj, bq = j, pq
        if bj >= self.jac_threshold:
            return True, "jaccard", bj, bq
        return False, ("embedding" if v is not None else "jaccard"), max(best, bj), best_q or bq

    def add(self, q: str, vector: list[float] | None = None) -> None:
        q = " ".join(str(q or "").split())
        if not q:
            return
        self.queries.append(q)
        self.vectors.append(vector if vector is not None else self._vector(q))

    def check_and_add(self, q: str, where: str = "") -> bool:
        """True = übersprungen (Dublette, protokolliert); sonst aufgenommen."""
        dup, method, sim, near = self.check(q)
        if dup:
            self.skips.append({"query": q[:160], "near": (near or "")[:160],
                               "method": method, "similarity": round(sim, 3), "where": where})
            logger.info("  near-duplicate query skipped (%s %.2f): %r ~ %r", method, sim, q[:60], (near or "")[:60])
            return True
        self.add(q)
        return False

    def summary(self) -> dict:
        return {"method": self.method, "queries": len(self.queries),
                "skipped": len(self.skips), "skips": self.skips}
