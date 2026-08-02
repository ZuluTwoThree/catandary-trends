"""Tests für den Query-Pfad des Horizont-Radars (Schnitt 1).

Reine Funktionen, keine DB — conftest.py erzwingt SQLite, und der Query-Pfad ist
Postgres-only. Was hier geprüft wird, ist die SQL-*Form* und die Sprachwahl,
nicht das Ergebnis einer Abfrage.
"""

import re
from pathlib import Path

import pytest

from pipeline.radar_horizons import (
    FTS_VECTOR,
    MAX_SCOPE_ROWS,
    MIN_SCOPE_ROWS,
    build_query_sql,
    resolve_scope,
)

REPO = Path(__file__).resolve().parent.parent


def _norm(s: str) -> str:
    """Whitespace glätten und Tabellen-Alias entfernen — der Alias ist der
    einzige zulässige Unterschied zwischen der Python- und der TS-Fassung."""
    return re.sub(r"\s+", " ", s.replace("t.", "")).strip()


# --------------------------------------------------------------------------
# Drift-Wächter: der teuerste stille Fehler dieses Features
# --------------------------------------------------------------------------
def test_fts_vector_matches_the_search_route():
    """Python- und TypeScript-Fassung des FTS-Ausdrucks müssen deckungsgleich sein.

    Weicht einer der beiden ab, bleibt das Ergebnis korrekt — die Abfrage fällt
    nur vom 6-ms-Index-Scan auf einen Seq Scan über 1,13 Mio. Zeilen zurück.
    Genau die Sorte Fehler, die niemand bemerkt, bis jemand drei Wochen später
    fragt, warum es langsam ist.
    """
    ts = (REPO / "frontend/src/app/api/search/route.ts").read_text()
    m = re.search(r"const FTS_VECTOR\s*=\s*(.+?);", ts, re.S)
    assert m, "FTS_VECTOR nicht in search/route.ts gefunden"
    # Die TS-Konstante ist ein zusammengesetztes String-Literal.
    ts_expr = "".join(re.findall(r'"([^"]*)"', m.group(1)))
    assert _norm(ts_expr) == _norm(FTS_VECTOR), (
        f"FTS-Ausdruck driftet:\n  py: {_norm(FTS_VECTOR)}\n  ts: {_norm(ts_expr)}"
    )


def test_fts_vector_covers_title_summary_and_tags():
    n = _norm(FTS_VECTOR)
    assert "to_tsvector('english'" in n
    for col in ("title_en", "summary_en", "tags::text"):
        assert col in n, f"{col} fehlt im FTS-Ausdruck"


# --------------------------------------------------------------------------
# build_query_sql
# --------------------------------------------------------------------------
def test_build_query_sql_uses_websearch_parser():
    """`to_tsquery` wirft bei beliebiger Nutzereingabe eine Exception —
    `websearch_to_tsquery` ist die einzige Variante, die man einem Textfeld
    aussetzen darf."""
    sql, _ = build_query_sql("carbon capture")
    assert "websearch_to_tsquery('english', %s)" in sql
    assert re.search(r"\bto_tsquery\(", sql.replace("websearch_to_tsquery(", "")) is None


def test_build_query_sql_binds_everything_as_parameters():
    sql, params = build_query_sql("robert'); drop table trends;--")
    assert "drop table" not in sql.lower()
    assert params[0] == "robert'); drop table trends;--"


def test_build_query_sql_applies_limit_last():
    sql, params = build_query_sql("x", limit=123)
    assert sql.rstrip().endswith("LIMIT %s")
    assert params[-1] == 123


def test_build_query_sql_phrase_is_conjunctive():
    """Die Teilfeld-Phrase verengt das Feld, sie ersetzt die Basis-Query nicht —
    sonst könnte ein Teilfeld aus seinem eigenen Radar herauswachsen."""
    sql, params = build_query_sql("alternative proteins", phrase="mycoprotein")
    assert sql.count("websearch_to_tsquery") == 2
    assert " AND " in sql
    assert params[:2] == ["alternative proteins", "mycoprotein"]


def test_build_query_sql_ids_narrow_but_never_widen():
    sql, params = build_query_sql("q", ids=[1, 2, 3])
    assert "t.id = ANY(%s)" in sql
    assert sql.index("websearch_to_tsquery") < sql.index("t.id = ANY")
    assert [1, 2, 3] in params


def test_build_query_sql_selects_the_scope_contract():
    """Die 10 Spalten SIND der Vertrag zu den Zellenfunktionen."""
    sql, _ = build_query_sql("q")
    for col in ("t.id", "t.trend_signal_type", "t.regions", "t.tags", "t.pestel",
                "event_date", "semantic"):
        assert col in sql, f"{col} fehlt in der Scope-Auswahl"


# --------------------------------------------------------------------------
# resolve_scope — die Naht
# --------------------------------------------------------------------------
class _FakeConn:
    """Merkt sich nur, welcher Pfad genommen wurde."""

    def __init__(self):
        self.sql = None

    def execute(self, sql, params=None):
        self.sql = sql
        self.params = params
        return self

    def fetchall(self):
        return []


def test_resolve_scope_defaults_to_the_curated_term_path():
    conn = _FakeConn()
    resolve_scope(conn, {"include_terms": ["%x%"], "exclude_terms": []})
    assert "ILIKE ANY" in conn.sql
    assert "websearch_to_tsquery" not in conn.sql


def test_resolve_scope_takes_the_fts_path_when_selector_says_so():
    conn = _FakeConn()
    resolve_scope(conn, {"selector": "query", "query_text": "carbon capture"})
    assert "websearch_to_tsquery" in conn.sql
    assert "ILIKE ANY" not in conn.sql


def test_resolve_scope_parses_json_terms():
    """radar_scopes.include_terms kommt je nach Treiber als str oder als Liste."""
    conn = _FakeConn()
    resolve_scope(conn, {"selector": "terms",
                         "include_terms": '["%a%","%b%"]',
                         "exclude_terms": '["%c%"]'})
    assert conn.params[0] == ["%a%", "%b%"]


# --------------------------------------------------------------------------
# Grenzen — und ihr Gleichlauf mit dem Hilfetext im Frontend
# --------------------------------------------------------------------------
def test_thresholds_match_the_frontend_help_text():
    """Die Hilfe im Radar nennt diese Zahlen wörtlich.

    Ein Tooltip, der veraltete Schwellen behauptet, ist schlimmer als keiner: er
    bringt dem Nutzer eine Regel bei, nach der die Engine nicht mehr arbeitet.
    Deshalb sind die Werte in lib/radar-params.ts gespiegelt und werden hier
    gegen die Python-Konstanten gehalten.
    """
    from pipeline.radar_horizons import (
        MIN_N_ADOPTION, MIN_N_MARKET, MIN_N_REGULATORY, MIN_N_TECH_FALLBACK,
        LAUNCH_WINDOW_MONTHS, PATHWAY_WINDOW_MONTHS,
    )
    ts = (REPO / "frontend/src/lib/radar-params.ts").read_text()
    block = re.search(r"RADAR_THRESHOLDS = \{(.+?)\} as const", ts, re.S)
    assert block, "RADAR_THRESHOLDS nicht in radar-params.ts gefunden"
    got = dict(re.findall(r"(\w+):\s*([0-9_]+)", block.group(1)))
    as_int = {k: int(v.replace("_", "")) for k, v in got.items()}

    assert as_int["minScopeRows"] == MIN_SCOPE_ROWS
    assert as_int["maxScopeRows"] == MAX_SCOPE_ROWS
    assert as_int["minRegulatory"] == MIN_N_REGULATORY
    assert as_int["minMarket"] == MIN_N_MARKET
    assert as_int["minAdoption"] == MIN_N_ADOPTION
    assert as_int["minTechFallback"] == MIN_N_TECH_FALLBACK
    # Beide Fenster sind gleich lang; der Hilfetext nennt nur eine Zahl.
    assert LAUNCH_WINDOW_MONTHS == PATHWAY_WINDOW_MONTHS == as_int["windowMonths"]



def test_scope_bounds_are_sane():
    assert MIN_SCOPE_ROWS < MAX_SCOPE_ROWS
    # Untergrenze muss über den Mindest-Evidenz-Schwellen der Zellen liegen,
    # sonst liefert ein Radar systematisch nur leere Zellen.
    assert MIN_SCOPE_ROWS >= 20


@pytest.mark.parametrize("bad", ["", "  ", "ab"])
def test_short_queries_are_rejected_before_sql(bad):
    """Die Längenprüfung sitzt in der Route und im Skript — hier nur die
    Gewissheit, dass build_query_sql selbst nichts Magisches tut."""
    sql, params = build_query_sql(bad)
    assert params[0] == bad
