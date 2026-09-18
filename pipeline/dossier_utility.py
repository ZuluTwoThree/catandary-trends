"""Nutzen U eines Dossier-Laufs — Stufe 0 des Plans „nutzen- und lernbasierter
Dossier-Agent" (docs/plan_dossier_agent_2026-09-18.md, Stufe 0 „Messlatte zuerst").

Alles hier ist Replay über gespeicherte Daten: `dossiers.result` (Struktur-,
Leser-, Zitat- und Quellenprotokoll des Laufs) und `dossier_orders.check_json`
(Endkontrolle). Kein Modell, kein Netz, keine GPU — deshalb ist U für jeden
alten Lauf nachrechenbar (`scripts/dossier_eval.py --backfill`) und
deterministisch.

Komponenten (je in [0, 1], sofern nicht anders vermerkt; None = nicht messbar,
weil der Lauf das Signal nicht erzeugt hat — z. B. Läufe vor dem Leser):

  density_norm      Faktenquote nach dem Neuwurf (per100), normiert auf 2,0
                    (Untergrenze der Strukturprüfung); Rückfall auf die Quote
                    vor dem Neuwurf, sonst 0.
  primary_share     Anteil der zitierten Katalog-IDs, deren Quelle Rang ≤ 1
                    trägt (Register/Journale/Primärseiten); fehlender Rang
                    zählt als 2. None, wenn nichts zitiert wurde.
  no_contradiction  0, wenn der Leser einen `coherence`-Befund hat oder in
                    Gesamturteil/Befundtext „contradict" steht; sonst 1
                    (auch ohne Leser — ein fehlender Prüfer ist kein Befund).
  tables_on_topic   1 − (Strukturbefunde nach dem Neuwurf, die „off topic" /
                    „nicht zum Thema" nennen, gedeckelt bei 2) / 2. None ohne
                    Strukturprüfung (Läufe vor dem 07.09.).
  reader_answers    Leser-Urteil „beantwortet die Frage" (reader_after, sonst
                    reader) als 1/0; None ohne Leser.
  answered_must     Anteil belegt beantworteter Pflichtpunkte des Auftrags
                    (`result["brief_eval"]["answered_share"]`, Stufe 1 seit
                    2026-09-19: `pipeline/dossier_brief.must_answer_scores`,
                    ein Modellurteil je Punkt, mechanisch am Zitat geprüft).
                    None bei Läufen ohne Auftrag (vor Stufe 1, CLI) und damit
                    aus der Gewichtung herausnormiert.
  cost_minutes      Laufzeit in Minuten (roh, nicht in [0, 1]).
  web_calls         Brave- + SearXNG-API-Aufrufe des Laufs (roh).
  signed_off        Owner-Abnahme (reviewed_at gesetzt) — Label, keine
                    Komponente von U.

Nutzen:

  U = Σ_i w_i · c_i / Σ_i w_i   über die MESSBAREN Qualitätskomponenten
      (c_i ≠ None; fehlende werden herausnormiert, nie als 0 gewertet)
    − 0,02 je angefangene 10 Minuten über 30 Minuten Laufzeit
    − 0,01 je angefangene 10 Web-Aufrufe über 40

Gewichte je Fragetyp (`WEIGHT_PRESETS`; Default `technology`; seit Stufe 1
wählt der Worker den Typ aus dem Auftrag, `brief.question_type`). Die fünf Qualitätsgewichte summieren je Preset auf
1,0; `answered_must` trägt zusätzlich 0,25 und greift erst, wenn die
Komponente messbar ist:

  technology  density 0,25 · primary 0,20 · no_contradiction 0,20 · tables 0,10 · reader 0,25
  landscape   density 0,20 · primary 0,15 · no_contradiction 0,20 · tables 0,20 · reader 0,25
  regulatory  density 0,20 · primary 0,35 · no_contradiction 0,20 · tables 0,05 · reader 0,20
  market      density 0,30 · primary 0,15 · no_contradiction 0,20 · tables 0,10 · reader 0,25
  evidence    density 0,30 · primary 0,30 · no_contradiction 0,15 · tables 0,05 · reader 0,20

„Abgabereif" (dritte Ampel im Desk, Runde 21 Punkt 9): Leser beantwortet ∧
kein Widerspruch ∧ Dichte ≥ 2,0 ∧ Tabellen themenbezogen. Ein Lauf ohne Leser
ist nie abgabereif — das Urteil fehlt, es ist nicht „gut".

Ergebnis je Lauf steht in `dossier_run_outcomes` (eine Zeile je dossiers.id;
additive Migration `scripts/migrate_dossier_run_outcomes.py`, wie die
Dossier-Tabellen NICHT in db.init_db verdrahtet).
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from pipeline import db as db_mod
from pipeline.db import get_connection

logger = logging.getLogger(__name__)

DENSITY_FLOOR = 2.0          # Untergrenze der Strukturprüfung (Faktenquote je 100 Wörter)
COST_FREE_MINUTES = 30.0     # bis hierhin keine Kostenstrafe
COST_PER_10_MIN = 0.02
WEB_FREE_CALLS = 40
WEB_PER_10_CALLS = 0.01
MUST_ANSWER_WEIGHT = 0.25    # greift erst ab Stufe 1 (answered_must messbar)

QUALITY_KEYS = ("density_norm", "primary_share", "no_contradiction",
                "tables_on_topic", "reader_answers", "answered_must")

WEIGHT_PRESETS: dict[str, dict[str, float]] = {
    "technology": {"density_norm": 0.25, "primary_share": 0.20, "no_contradiction": 0.20,
                   "tables_on_topic": 0.10, "reader_answers": 0.25},
    "landscape":  {"density_norm": 0.20, "primary_share": 0.15, "no_contradiction": 0.20,
                   "tables_on_topic": 0.20, "reader_answers": 0.25},
    "regulatory": {"density_norm": 0.20, "primary_share": 0.35, "no_contradiction": 0.20,
                   "tables_on_topic": 0.05, "reader_answers": 0.20},
    "market":     {"density_norm": 0.30, "primary_share": 0.15, "no_contradiction": 0.20,
                   "tables_on_topic": 0.10, "reader_answers": 0.25},
    "evidence":   {"density_norm": 0.30, "primary_share": 0.30, "no_contradiction": 0.15,
                   "tables_on_topic": 0.05, "reader_answers": 0.20},
}
for _p in WEIGHT_PRESETS.values():
    _p.setdefault("answered_must", MUST_ANSWER_WEIGHT)
DEFAULT_PRESET = "technology"

_OFF_TOPIC_RE = re.compile(r"off[ -]topic|nicht zum thema", re.I)
_CONTRADICT_RE = re.compile(r"contradict|widerspr", re.I)


# --------------------------------------------------------------------------
# Komponenten
# --------------------------------------------------------------------------

def _as_dict(v: Any) -> dict:
    if isinstance(v, str):
        try:
            v = json.loads(v)
        except ValueError:
            return {}
    return v if isinstance(v, dict) else {}


def _reader(structure: dict) -> dict | None:
    """Das letzte Leser-Urteil: nach der Endfassung, sonst nach dem Entwurf."""
    for key in ("reader_after", "reader"):
        r = structure.get(key)
        if isinstance(r, dict):
            return r
    return None


def _density(structure: dict) -> float:
    for key in ("density_after", "density_before"):
        d = structure.get(key)
        if isinstance(d, dict) and d.get("per100") is not None:
            try:
                return min(1.0, max(0.0, float(d["per100"]) / DENSITY_FLOOR))
            except (TypeError, ValueError):
                continue
    return 0.0


def _primary_share(result: dict) -> float | None:
    cited = result.get("cited") or []
    if not isinstance(cited, list) or not cited:
        return None
    ranks: dict[str, int] = {}
    for s in result.get("sources") or []:
        if not isinstance(s, dict) or s.get("id") is None:
            continue
        r = s.get("rank")
        try:
            ranks[str(s["id"])] = 2 if r is None else int(r)
        except (TypeError, ValueError):
            ranks[str(s["id"])] = 2
    ids = [str(c) for c in cited]
    primary = sum(1 for c in ids if ranks.get(c, 2) <= 1)
    return round(primary / len(ids), 4)


def _no_contradiction(reader: dict | None) -> int:
    if not reader:
        return 1
    if _CONTRADICT_RE.search(str(reader.get("overall") or "")):
        return 0
    for f in reader.get("findings") or []:
        if not isinstance(f, dict):
            continue
        if str(f.get("kind") or "").lower() == "coherence":
            return 0
        if _CONTRADICT_RE.search(str(f.get("issue") or "")):
            return 0
    return 1


def _tables_on_topic(structure: dict) -> float | None:
    if not structure:
        return None
    findings = structure.get("findings_after")
    if findings is None:
        findings = structure.get("findings")
    if not isinstance(findings, list):
        return None
    n = sum(1 for f in findings if _OFF_TOPIC_RE.search(str(f)))
    return round(1.0 - min(n, 2) / 2.0, 4)


def _reader_answers(reader: dict | None) -> bool | None:
    if not reader or "answers_question" not in reader:
        return None
    v = reader.get("answers_question")
    return None if v is None else bool(v)


def _web_calls(result: dict) -> int:
    cache = _as_dict(_as_dict(result.get("web")).get("cache"))
    total = 0
    for k in ("brave_api", "searxng_api"):
        try:
            total += int(cache.get(k) or 0)
        except (TypeError, ValueError):
            pass
    return total


def _answered_must(res: dict) -> float | None:
    """Stufe 1: Anteil der Pflichtpunkte mit belegter Antwort. Vorrang hat
    `answered_share`; sonst aus den Items gezählt. None ohne Auftrag."""
    ev = _as_dict(res.get("brief_eval"))
    if not ev:
        return None
    share = ev.get("answered_share")
    if share is not None:
        try:
            return round(min(1.0, max(0.0, float(share))), 4)
        except (TypeError, ValueError):
            pass
    items = [i for i in (ev.get("items") or []) if isinstance(i, dict)]
    if not items:
        return None
    return round(sum(1 for i in items if i.get("answered")) / len(items), 4)


def components(result: dict | str | None, check: dict | str | None,
               reviewed_at: Any) -> dict:
    """Alle Komponenten eines Laufs aus dem, was er gespeichert hat.
    `check` (Endkontrolle) trägt heute keine eigene Komponente: sein
    `reader_ok` heißt „kein schwerer Einwand", nicht „beantwortet die Frage",
    und wird deshalb bewusst NICHT als Antwort gewertet. Der Parameter bleibt,
    damit Stufe 4 (Aussagenprüfung) dort ansetzen kann, ohne die Signatur zu
    ändern."""
    res = _as_dict(result)
    _ = _as_dict(check)
    structure = _as_dict(res.get("structure"))
    reader = _reader(structure)
    reader_answers = _reader_answers(reader)
    seconds = res.get("seconds")
    try:
        cost_minutes = round(float(seconds) / 60.0, 2) if seconds is not None else None
    except (TypeError, ValueError):
        cost_minutes = None
    return {
        "density_norm": round(_density(structure), 4),
        "primary_share": _primary_share(res),
        "no_contradiction": _no_contradiction(reader),
        "tables_on_topic": _tables_on_topic(structure),
        "reader_answers": (None if reader_answers is None else (1 if reader_answers else 0)),
        "answered_must": _answered_must(res),
        "cost_minutes": cost_minutes,
        "web_calls": _web_calls(res),
        "signed_off": reviewed_at is not None,
        "has_structure": bool(structure),
        "has_reader": reader is not None,
    }


# --------------------------------------------------------------------------
# Nutzen und Ampel
# --------------------------------------------------------------------------

def utility(comps: dict, weights: dict[str, float] | str | None = None) -> float:
    """Gewichtete Summe der messbaren Qualitätskomponenten (herausnormiert),
    minus Kostenstrafe. `weights` = Preset-Name oder Gewichtsdict."""
    if weights is None:
        w = WEIGHT_PRESETS[DEFAULT_PRESET]
    elif isinstance(weights, str):
        w = WEIGHT_PRESETS[weights]
    else:
        w = weights
    num = den = 0.0
    for key in QUALITY_KEYS:
        wk = float(w.get(key, 0.0) or 0.0)
        val = comps.get(key)
        if wk <= 0 or val is None:
            continue
        num += wk * float(val)
        den += wk
    quality = num / den if den > 0 else 0.0
    penalty = 0.0
    minutes = comps.get("cost_minutes")
    if minutes is not None and minutes > COST_FREE_MINUTES:
        over = minutes - COST_FREE_MINUTES
        penalty += COST_PER_10_MIN * (int((over - 1e-9) // 10) + 1)
    calls = comps.get("web_calls")
    if calls is not None and calls > WEB_FREE_CALLS:
        over = calls - WEB_FREE_CALLS
        penalty += WEB_PER_10_CALLS * ((over - 1) // 10 + 1)
    return round(quality - penalty, 4)


def delivery_ready(comps: dict) -> bool:
    """Dritte Ampel: Leser beantwortet ∧ kein Widerspruch ∧ Dichte ≥ Floor ∧
    Tabellen themenbezogen. Ohne Leser nie."""
    return bool(
        comps.get("reader_answers") == 1
        and comps.get("no_contradiction") == 1
        and (comps.get("density_norm") or 0.0) >= 1.0
        and comps.get("tables_on_topic") == 1
    )


def evaluate(result: dict | str | None, check: dict | str | None, reviewed_at: Any,
             preset: str = DEFAULT_PRESET) -> dict:
    """Komponenten + U + Ampel in einem Objekt (Worker, Backfill, Tests)."""
    comps = components(result, check, reviewed_at)
    weights = dict(WEIGHT_PRESETS[preset])
    return {
        "preset": preset,
        "weights": weights,
        "components": comps,
        "utility": utility(comps, weights),
        "delivery_ready": delivery_ready(comps),
        "reader_answers": (None if comps["reader_answers"] is None
                           else bool(comps["reader_answers"])),
        "signed_off": bool(comps["signed_off"]),
    }


# --------------------------------------------------------------------------
# Tabelle dossier_run_outcomes
# --------------------------------------------------------------------------

def _ddl() -> str:
    if db_mod.USE_POSTGRES:
        id_col, js, ts = "id SERIAL PRIMARY KEY", "JSONB", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
        fk = " REFERENCES dossiers(id)"
    else:
        id_col, js, ts = "id INTEGER PRIMARY KEY AUTOINCREMENT", "TEXT", "TEXT DEFAULT (datetime('now'))"
        fk = ""
    return (
        "CREATE TABLE IF NOT EXISTS dossier_run_outcomes ("
        f" {id_col},"
        f" dossier_id INTEGER NOT NULL UNIQUE{fk},"
        "  order_id INTEGER,"
        "  slug TEXT NOT NULL,"
        "  version INTEGER NOT NULL,"
        f" computed_at {ts},"
        "  utility REAL,"
        f" weights {js},"
        f" components {js},"
        "  delivery_ready BOOLEAN NOT NULL DEFAULT FALSE,"
        "  reader_answers BOOLEAN,"
        "  signed_off BOOLEAN NOT NULL DEFAULT FALSE,"
        "  owner_edit_diff TEXT,"      # Stufe 5: Diff geliefert → freigegeben
        "  notes TEXT"
        ")")


def ensure_schema() -> None:
    """Idempotent; auf der Live-DB übernimmt das scripts/migrate_dossier_run_outcomes.py."""
    with get_connection() as conn:
        conn.execute(_ddl())
        conn.execute("CREATE INDEX IF NOT EXISTS idx_dossier_run_outcomes_slug "
                     "ON dossier_run_outcomes (slug, version)")


def record_outcome(dossier_id: int, order_id: int | None, slug: str, version: int,
                   evaluation: dict, owner_edit_diff: str | None = None,
                   notes: str | None = None) -> None:
    """Eine Zeile je Lauf — Upsert auf dossier_id (Backfill darf neu rechnen)."""
    weights = json.dumps(evaluation["weights"], ensure_ascii=False)
    comps = json.dumps(evaluation["components"], ensure_ascii=False)
    sql = (
        "INSERT INTO dossier_run_outcomes (dossier_id, order_id, slug, version, computed_at,"
        " utility, weights, components, delivery_ready, reader_answers, signed_off,"
        " owner_edit_diff, notes) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?, ?, ?, ?, ?, ?, ?)"
        " ON CONFLICT (dossier_id) DO UPDATE SET"
        "  order_id = EXCLUDED.order_id, slug = EXCLUDED.slug, version = EXCLUDED.version,"
        "  computed_at = CURRENT_TIMESTAMP, utility = EXCLUDED.utility,"
        "  weights = EXCLUDED.weights, components = EXCLUDED.components,"
        "  delivery_ready = EXCLUDED.delivery_ready, reader_answers = EXCLUDED.reader_answers,"
        "  signed_off = EXCLUDED.signed_off,"
        "  owner_edit_diff = COALESCE(EXCLUDED.owner_edit_diff, dossier_run_outcomes.owner_edit_diff),"
        "  notes = COALESCE(EXCLUDED.notes, dossier_run_outcomes.notes)")
    with get_connection() as conn:
        conn.execute(sql, (int(dossier_id), order_id, slug, int(version),
                           float(evaluation["utility"]), weights, comps,
                           bool(evaluation["delivery_ready"]),
                           evaluation.get("reader_answers"),
                           bool(evaluation.get("signed_off")),
                           owner_edit_diff, notes))


def record_run(slug: str, version: int, order_id: int | None, result: dict | str | None,
               check: dict | str | None, reviewed_at: Any = None,
               preset: str = DEFAULT_PRESET) -> dict | None:
    """Worker-Einstieg: dossiers(slug, version) nachschlagen, U rechnen, speichern.
    Gibt die Auswertung zurück; None, wenn der Lauf keine dossiers-Zeile hat."""
    with get_connection() as conn:
        row = conn.execute("SELECT id FROM dossiers WHERE slug = ? AND version = ?",
                           (slug, int(version))).fetchone()
    if not row:
        return None
    ensure_schema()
    ev = evaluate(result, check, reviewed_at, preset)
    record_outcome(int(dict(row)["id"]), order_id, slug, int(version), ev)
    return ev


def list_outcomes() -> list[dict]:
    """Alle Outcome-Zeilen (Scoreboard, Tests), Komponenten als dict."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT o.*, d.created_at AS dossier_created_at, d.model AS dossier_model,"
            " d.result AS result FROM dossier_run_outcomes o"
            " JOIN dossiers d ON d.id = o.dossier_id"
            " ORDER BY o.slug, o.version").fetchall()
    out = []
    for r in rows:
        r = dict(r)
        res = _as_dict(r.pop("result", None))
        r["components"] = _as_dict(r.get("components"))
        r["weights"] = _as_dict(r.get("weights"))
        r["writer_model"] = res.get("writer_model") or r.get("dossier_model")
        r["mode"] = res.get("mode")
        r["dr"] = res.get("dr")
        out.append(r)
    return out
