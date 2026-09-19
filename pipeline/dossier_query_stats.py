"""Erfahrungsbasis je (Lückenart, Anfrage-Schablone) — Stufe 3 des Plans
docs/plan_dossier_agent_2026-09-18.md („Der nutzenbasierte Rechercheur").

Tabelle `dossier_query_stats`: je Lückenart (`must` Pflichtpunkt, `audit`
Audit-Lücke, `plan` Planschritt, `pattern:<sweep>` festes Muster) und
Schablone einer Web-/Korpus-Anfrage, wie oft sie lief (`n_used`), wie viele
Treffer sie brachte (`n_hits`), bei wie vielen Läufen davon mindestens eine
Quelle in den Katalog kam (`n_admitted` — ein ERFOLGSZÄHLER ≤ n_used, damit
das Beta-Mittel eine Wahrscheinlichkeit ist), wie viele ihrer Quellen gelesen
(`n_read`) und am Ende zitiert wurden (`n_cited`).

Die **Schablone** ist die Anfrage mit den themenspezifischen Wörtern ersetzt:
Themenbegriffe → `{topic}`, Akteure/Entitäten → `{entity}`, Regulatoren und
Instrumente des Profils → `{instrument}`, Jahreszahlen → `{year}`. So sagt
eine Zeile „`{instrument} {topic} obligations scope`" etwas über Recht-Anfragen
in jedem Feld, nicht nur über den Data Act.

Der Planer (`pipeline/dossier_planner.py`) liest daraus die
Erfolgswahrscheinlichkeit einer Lückenart: Beta-Mittel
`(n_admitted + 1) / (n_used + 2)` je Schablone, bei ≥ 2 Schablonen derselben
Lückenart Thompson-Sampling (eine Ziehung je Schablone aus
Beta(n_admitted + 1, n_used − n_admitted + 1), die beste gewinnt).

Schreibpfad NIE sperrend: `update_from_run` fängt alles und gibt 0 zurück.
Additive Migration `scripts/migrate_dossier_query_stats.py` (wie die anderen
Dossier-Tabellen nicht in `db.init_db`); `--backfill` rechnet die Tabelle aus
allen gespeicherten Läufen NEU (löscht vorher).

Inspektion: `python -m pipeline.dossier_query_stats --show [--kind K]`.
"""
from __future__ import annotations

import argparse
import json
import logging
import random
import re
import sys

from pipeline import db as db_mod
from pipeline.db import get_connection

logger = logging.getLogger(__name__)

TEMPLATE_MAX_CHARS = 160
GAP_KINDS = ("must", "audit", "plan", "pattern")
_WORD = re.compile(r"[A-Za-zÀ-ɏ][A-Za-zÀ-ɏ0-9+#.'’-]*|\d+")
_YEAR = re.compile(r"^(?:19|20)\d{2}$")
_NONWORD = re.compile(r"[^a-z0-9]+")


# --------------------------------------------------------------------------
# Schablone
# --------------------------------------------------------------------------

def _norm_word(w: str) -> str:
    return _NONWORD.sub("", w.lower().replace("’", "'"))


def _stem(w: str) -> str:
    """Nur der Plural-s fällt (obligations → obligation, changes → change);
    mehr Stammformen brächten falsche Gleichheiten (cores → cor)."""
    w = _norm_word(w)
    if len(w) > 4 and w.endswith("s") and not w.endswith(("ss", "us", "is")):
        return w[:-1]
    return w


def _phrase_words(items) -> list[list[str]]:
    out: list[list[str]] = []
    for it in items or ():
        words = [_stem(w) for w in _WORD.findall(str(it or "")) if _norm_word(w)]
        words = [w for w in words if len(w) >= 2]
        if words:
            out.append(words)
    out.sort(key=len, reverse=True)          # längste Phrase zuerst
    return out


def normalise_template(query: str, topic_terms=(), entities=(), instruments=()) -> str:
    """Anfrage → Schablone. Ersetzt zuerst mehrwortige Phrasen (längste
    zuerst), dann Einzelwörter; Jahreszahlen → `{year}`; Platzhalter, die
    aufeinander folgen, werden zu einem zusammengezogen.

    >>> normalise_template("EU Data Act cloud switching obligations 2027",
    ...                    topic_terms=["cloud"], instruments=["EU Data Act"])
    '{instrument} {topic} switching obligation {year}'
    """
    words = [w for w in _WORD.findall(str(query or ""))]
    toks = [(_stem(w), w) for w in words if _norm_word(w)]
    n = len(toks)
    label = [None] * n
    for ph_list, tag in ((_phrase_words(instruments), "{instrument}"),
                         (_phrase_words(entities), "{entity}"),
                         (_phrase_words(topic_terms), "{topic}")):
        for ph in ph_list:
            L = len(ph)
            i = 0
            while i + L <= n:
                if all(label[i + k] is None and toks[i + k][0] == ph[k] for k in range(L)):
                    for k in range(L):
                        label[i + k] = tag
                    i += L
                else:
                    i += 1
    out: list[str] = []
    for i, (st, raw) in enumerate(toks):
        piece = label[i]
        if piece is None:
            if _YEAR.match(raw):
                piece = "{year}"
            elif st.isdigit():
                piece = "{n}"
            else:
                piece = st
        if piece.startswith("{") and out and out[-1] == piece:
            continue
        out.append(piece)
    return " ".join(out)[:TEMPLATE_MAX_CHARS].strip()


def gap_kind_key(kind: str, pattern: str | None = None) -> str:
    kind = str(kind or "audit").lower()
    if kind.startswith("pattern"):
        return f"pattern:{pattern}" if pattern else kind
    return kind if kind in GAP_KINDS else "audit"


# --------------------------------------------------------------------------
# Schema
# --------------------------------------------------------------------------

def _ddl() -> str:
    return (
        "CREATE TABLE IF NOT EXISTS dossier_query_stats ("
        "  gap_kind TEXT NOT NULL,"
        "  template TEXT NOT NULL,"
        "  n_used INTEGER NOT NULL DEFAULT 0,"
        "  n_hits INTEGER NOT NULL DEFAULT 0,"
        "  n_admitted INTEGER NOT NULL DEFAULT 0,"
        "  n_read INTEGER NOT NULL DEFAULT 0,"
        "  n_cited INTEGER NOT NULL DEFAULT 0,"
        "  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,"
        "  PRIMARY KEY (gap_kind, template)"
        ")")


def ensure_schema() -> None:
    with get_connection() as conn:
        conn.execute(_ddl())
        conn.execute("CREATE INDEX IF NOT EXISTS idx_dossier_query_stats_kind "
                     "ON dossier_query_stats (gap_kind)")


def table_exists() -> bool:
    try:
        with get_connection() as conn:
            if db_mod.USE_POSTGRES:
                row = conn.execute("SELECT to_regclass('dossier_query_stats') AS r").fetchone()
                return bool(dict(row)["r"]) if row else False
            row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' "
                               "AND name='dossier_query_stats'").fetchone()
            return row is not None
    except Exception:                                               # noqa: BLE001
        return False


def upsert(rows: dict[tuple[str, str], dict]) -> int:
    """{(gap_kind, template): {n_used, n_hits, n_admitted, n_read, n_cited}} addieren."""
    if not rows:
        return 0
    sql = (
        "INSERT INTO dossier_query_stats (gap_kind, template, n_used, n_hits, n_admitted,"
        " n_read, n_cited, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)"
        " ON CONFLICT (gap_kind, template) DO UPDATE SET"
        "  n_used = dossier_query_stats.n_used + EXCLUDED.n_used,"
        "  n_hits = dossier_query_stats.n_hits + EXCLUDED.n_hits,"
        "  n_admitted = dossier_query_stats.n_admitted + EXCLUDED.n_admitted,"
        "  n_read = dossier_query_stats.n_read + EXCLUDED.n_read,"
        "  n_cited = dossier_query_stats.n_cited + EXCLUDED.n_cited,"
        "  updated_at = CURRENT_TIMESTAMP")
    n = 0
    with get_connection() as conn:
        for (kind, tmpl), b in sorted(rows.items()):
            if not tmpl:
                continue
            conn.execute(sql, (kind, tmpl, int(b.get("n_used") or 0), int(b.get("n_hits") or 0),
                               int(b.get("n_admitted") or 0), int(b.get("n_read") or 0),
                               int(b.get("n_cited") or 0)))
            n += 1
    return n


def list_stats(kind: str | None = None) -> list[dict]:
    with get_connection() as conn:
        if kind:
            rows = conn.execute("SELECT * FROM dossier_query_stats WHERE gap_kind = ? "
                                "ORDER BY n_admitted DESC, n_used DESC, template", (kind,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM dossier_query_stats "
                                "ORDER BY gap_kind, n_admitted DESC, n_used DESC, template").fetchall()
    return [dict(r) for r in rows]


# --------------------------------------------------------------------------
# Erfolgswahrscheinlichkeit für den Planer
# --------------------------------------------------------------------------

def beta_mean(n_used: int, n_admitted: int) -> float:
    return (int(n_admitted) + 1) / (int(n_used) + 2)


def templates_for(kind: str) -> list[dict]:
    """Zeilen einer Lückenart (leer ohne Tabelle / Fehler — nie sperrend)."""
    try:
        if not table_exists():
            return []
        return list_stats(kind)
    except Exception as exc:                                        # noqa: BLE001
        logger.warning("query stats not read (%s: %s)", type(exc).__name__, exc)
        return []


def p_success(rows: list[dict], rng: random.Random | None = None,
              prior: float = 0.5) -> tuple[float, str | None]:
    """(p, beste Schablone). Eine Zeile: Beta-Mittel. ≥ 2 Zeilen: Thompson-
    Sampling — je Schablone eine Ziehung aus Beta(n_admitted + 1,
    n_used − n_admitted + 1), die beste gewinnt (mit `rng` deterministisch).
    Ohne Zeilen der Prior."""
    rows = [r for r in rows or [] if int(r.get("n_used") or 0) > 0]
    if not rows:
        return prior, None
    if len(rows) == 1:
        r = rows[0]
        return beta_mean(r["n_used"], r["n_admitted"]), str(r["template"])
    rng = rng or random.Random()
    best, best_t = -1.0, None
    for r in rows:
        a = int(r.get("n_admitted") or 0) + 1
        b = max(0, int(r.get("n_used") or 0) - int(r.get("n_admitted") or 0)) + 1
        draw = rng.betavariate(a, b)
        if draw > best:
            best, best_t = draw, str(r["template"])
    return best, best_t


# --------------------------------------------------------------------------
# Rechnung über einen Lauf (rein) — Live-Pfad und Backfill teilen sie
# --------------------------------------------------------------------------

def run_query_stats(result: dict, topic_terms=(), entities=(), instruments=()) -> dict:
    """{(gap_kind, template): Zähler} aus einem Laufprotokoll.

    Quellen: `web.steps` (Suchschritte mit hits/new und gap-Index),
    `ledger` (Lückenart je Index, `web_queries`), `trace` (Korpus-Suchen),
    `sources` (welche Anfrage einen Treffer aufnahm — `query`, seit Stufe 3;
    ältere Läufe kennen nur den gap-Index, dann zählt der Treffer für jede
    Anfrage dieser Lücke) und `cited`.
    """
    ledger = result.get("ledger") or []
    steps = (result.get("web") or {}).get("steps") or []
    sources = result.get("sources") or []
    cited = {str(c) for c in (result.get("cited") or [])}
    kind_of_gap: dict[int, str] = {}
    for i, e in enumerate(ledger):
        k = str(e.get("kind") or "gap")
        kind_of_gap[i] = {"gap": "audit", "followup": "audit"}.get(k, k)
    rows: dict[tuple[str, str], dict] = {}

    def _row(kind: str, tmpl: str) -> dict:
        return rows.setdefault((kind, tmpl), {"n_used": 0, "n_hits": 0, "n_admitted": 0,
                                              "n_read": 0, "n_cited": 0})

    # Web-Suchschritte
    query_kind: dict[str, str] = {}
    gap_queries: dict[int, list[str]] = {}
    for st in steps:
        if st.get("action") != "search" or not st.get("argument"):
            continue
        q = str(st["argument"])
        gi = st.get("gap")
        kind = kind_of_gap.get(gi, "audit") if isinstance(gi, int) else "audit"
        if st.get("kind"):
            kind = str(st["kind"])
        tmpl = normalise_template(q, topic_terms, entities, instruments)
        if not tmpl:
            continue
        r = _row(kind, tmpl)
        r["n_used"] += 1
        r["n_hits"] += int(st.get("hits") or 0)
        r["n_admitted"] += 1 if int(st.get("new") or 0) > 0 else 0
        query_kind[q] = kind
        if isinstance(gi, int) and q not in gap_queries.setdefault(gi, []):
            gap_queries[gi].append(q)
    # Korpus-Suchen des Agenten (trace) — Lückenart aus dem Schritt, sonst plan
    for st in result.get("trace") or []:
        if st.get("action") != "search" or not st.get("argument"):
            continue
        q = str(st["argument"])
        kind = str(st.get("kind") or "plan")
        tmpl = normalise_template(q, topic_terms, entities, instruments)
        if not tmpl:
            continue
        r = _row(kind, tmpl)
        r["n_used"] += 1
        r["n_hits"] += int(st.get("hits") or 0)
        r["n_admitted"] += 1 if int(st.get("new") or 0) > 0 else 0
        query_kind[q] = kind
    # gelesen / zitiert je Anfrage
    for s in sources:
        if str(s.get("kind") or "") not in ("web", "legal", "market", "entity", "funding"):
            continue
        read = bool(s.get("fetched"))
        cit = str(s.get("id")) in cited
        if not (read or cit):
            continue
        qs: list[str] = []
        if s.get("query"):
            qs = [str(s["query"])]
        elif isinstance(s.get("gap"), int):
            qs = gap_queries.get(s["gap"], [])
        for q in qs:
            kind = query_kind.get(q)
            if kind is None:
                continue
            tmpl = normalise_template(q, topic_terms, entities, instruments)
            if not tmpl:
                continue
            r = _row(kind, tmpl)
            r["n_read"] += int(read)
            r["n_cited"] += int(cit)
    return rows


def update_from_run(result: dict, topic_terms=(), entities=(), instruments=()) -> int:
    """Laufende Fortschreibung am Ende eines Laufs — nie sperrend."""
    try:
        if not table_exists():
            logger.info("dossier_query_stats fehlt — Migration "
                        "scripts/migrate_dossier_query_stats.py nicht ausgeführt; "
                        "keine Fortschreibung")
            return 0
        rows = run_query_stats(result, topic_terms, entities, instruments)
        n = upsert(rows)
        logger.info("query stats: %d template row(s) updated", n)
        return n
    except Exception as exc:                                        # noqa: BLE001
        logger.warning("query stats not updated (%s: %s)", type(exc).__name__, exc)
        return 0


# --------------------------------------------------------------------------
# Backfill aus den gespeicherten Läufen
# --------------------------------------------------------------------------

def _as_dict(v) -> dict:
    if isinstance(v, dict):
        return v
    if isinstance(v, (str, bytes)):
        try:
            d = json.loads(v)
            return d if isinstance(d, dict) else {}
        except ValueError:
            return {}
    return {}


def load_runs() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute("SELECT id, slug, version, topic, result FROM dossiers "
                            "ORDER BY id").fetchall()
    out = []
    for r in rows:
        r = dict(r)
        r["result"] = _as_dict(r.get("result"))
        out.append(r)
    return out


def run_terms(run: dict, entity_fn=None) -> tuple[list[str], list[str], list[str]]:
    """Themenbegriffe, Entitäten und Instrumente eines gespeicherten Laufs:
    Thema, Profil (`regulators`, `actor_seeds`) und — weil alte Läufe kein
    Profil tragen — die Akteure, die `entity_fn(sources, topic)` aus dem
    Katalog des Laufs erntet (`corpus_research.harvest_entities`)."""
    res = run.get("result") or {}
    topic = str(run.get("topic") or res.get("question") or "")
    topic_terms = [w for w in _WORD.findall(topic) if len(_norm_word(w)) >= 3]
    prof = res.get("profile") or {}
    instruments = list(prof.get("regulators") or []) if isinstance(prof, dict) else []
    entities = list(prof.get("actor_seeds") or []) if isinstance(prof, dict) else []
    if entity_fn is not None:
        try:
            entities += [e for e in (entity_fn(res.get("sources") or [], topic) or [])
                         if e not in entities]
        except Exception as exc:                                    # noqa: BLE001
            logger.warning("entity harvest failed for run %s: %r", run.get("id"), exc)
    return topic_terms, entities, instruments


def backfill(runs: list[dict] | None = None, wipe: bool = True, entity_fn=None) -> dict:
    ensure_schema()
    runs = load_runs() if runs is None else runs
    if wipe:
        with get_connection() as conn:
            conn.execute("DELETE FROM dossier_query_stats")
    n_runs, n_queries = 0, 0
    total: dict[tuple[str, str], dict] = {}
    for r in runs:
        res = r.get("result") or {}
        tt, ents, inst = run_terms(r, entity_fn)
        rows = run_query_stats(res, tt, ents, inst)
        if not rows:
            continue
        n_runs += 1
        for k, b in rows.items():
            n_queries += b["n_used"]
            t = total.setdefault(k, {"n_used": 0, "n_hits": 0, "n_admitted": 0, "n_read": 0, "n_cited": 0})
            for f in t:
                t[f] += b[f]
    upsert(total)
    kinds: dict[str, int] = {}
    for (k, _t) in total:
        kinds[k] = kinds.get(k, 0) + 1
    return {"runs": n_runs, "queries": n_queries, "templates": len(total), "kinds": kinds}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="dossier_query_stats ansehen / neu rechnen")
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--kind", help="nur diese Lückenart (must|audit|plan|pattern:…)")
    ap.add_argument("--backfill", action="store_true",
                    help="Tabelle aus allen gespeicherten Läufen NEU rechnen (löscht vorher)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if a.backfill:
        from scripts import corpus_research as cr
        out = backfill(entity_fn=lambda srcs, topic: cr.harvest_entities(srcs, topic)[0])
        print(json.dumps(out, ensure_ascii=False, indent=1) if a.json else
              f"{out['runs']} Lauf/Läufe, {out['queries']} Anfragen → {out['templates']} Schablonen "
              f"({', '.join(f'{k}={v}' for k, v in sorted(out['kinds'].items()))})")
        return 0
    rows = list_stats(a.kind)
    if a.json:
        print(json.dumps(rows, ensure_ascii=False, indent=1, default=str))
        return 0
    if not rows:
        print("(keine Zeilen)")
        return 0
    cur = None
    for r in rows:
        if r["gap_kind"] != cur:
            cur = r["gap_kind"]
            print(f"\n== {cur}")
        print(f"  p={beta_mean(r['n_used'], r['n_admitted']):.2f}  used {r['n_used']:>3}  hits {r['n_hits']:>3}  "
              f"ok {r['n_admitted']:>3}  read {r['n_read']:>3}  cited {r['n_cited']:>3}  {r['template']}")
    print("\np = Beta-Mittel (n_admitted + 1) / (n_used + 2); ok = Läufe mit ≥ 1 aufgenommener Quelle")
    return 0


if __name__ == "__main__":
    sys.exit(main())
