"""Korpus-API — lesende Werkzeuge über den Catandary-Korpus (Owner 2026-10-04).

Eine Funktion je Werkzeug, jede mit JSON-fähigem Ergebnis. Zwei Aufrufer:

  * der MCP-Server (`tools/research/mcp_server.py`) für Claude Code / Desktop,
  * der Recherche-Worker (`tools/research/gptr_run.py`, gpt-researcher) über die
    Retriever-Endpunkte `gptr_retrieve` / `gptr_fetch`.

Beide sprechen nicht direkt mit dieser Datei, sondern mit `pipeline/corpus_service.py`
(HTTP auf 127.0.0.1, Einmal-Token). Plan: `docs/plan_field_research_2026-10-04.md`.

Regeln:
  * **Nur lesend.** Jede Abfrage läuft in einer READ-ONLY-Transaktion mit
    `statement_timeout`; Ergebnisgrößen sind gedeckelt.
  * **Jeder Seitenabruf** geht über `article_fetcher.fetch_fulltext_result`
    (CatandaryTrendsBot, robots.txt, TDM-Vorbehalt auch nach Weiterleitungen,
    Host-Drossel). Rechtstexte (`legal_text.LEGAL_HOSTS`) werden mit großer Kappe
    geholt und artikelweise um die Suchbegriffe geschnitten.
  * Ebenen nach derselben Regel wie Field Watch (`field_watch.TIER_SQL`).
"""
from __future__ import annotations

import ipaddress
import json
import logging
import re
import socket
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import pipeline.config  # noqa: E402,F401  — lädt .env (BRAVE_SEARCH_API_KEY, DATABASE_URL)

logger = logging.getLogger(__name__)

MAX_LIMIT = 50
DEFAULT_TEXT_CHARS = 4_000
MAX_TEXT_CHARS = 20_000
RRF_K = 60
SIGNAL_STATUSES = ("published", "signal")
TIERS = ("science", "patent", "funding", "market")
FETCH_WORKERS = 4


class ToolError(ValueError):
    """Fehler, der dem Aufrufer als Klartext zurückgegeben wird (kein Stacktrace)."""


# ---------------------------------------------------------------------------
# Hilfen
# ---------------------------------------------------------------------------
def _limit(n, default: int = 20) -> int:
    try:
        n = int(n if n is not None else default)
    except (TypeError, ValueError):
        raise ToolError(f"limit must be an integer, got {n!r}")
    return max(1, min(n, MAX_LIMIT))


def _chars(n, default: int = DEFAULT_TEXT_CHARS) -> int:
    try:
        n = int(n if n is not None else default)
    except (TypeError, ValueError):
        raise ToolError(f"max_chars must be an integer, got {n!r}")
    return max(200, min(n, MAX_TEXT_CHARS))


def _date(s, name: str) -> str | None:
    if s in (None, ""):
        return None
    s = str(s)
    if not re.fullmatch(r"\d{4}(-\d{2}(-\d{2})?)?", s):
        raise ToolError(f"{name} must look like YYYY, YYYY-MM or YYYY-MM-DD, got {s!r}")
    return (s + "-01-01")[:10] if len(s) == 4 else (s + "-01")[:10] if len(s) == 7 else s


def _terms(terms) -> list[str]:
    if isinstance(terms, str):
        terms = [t for t in (x.strip() for x in terms.split(",")) if t]
    terms = [str(t).strip() for t in (terms or []) if str(t).strip()]
    if not terms:
        raise ToolError("at least one search term is required")
    if len(terms) > 25:
        raise ToolError("at most 25 terms")
    return terms


def tsquery_sql(query: str) -> str:
    """Mehrwortige Anfrage ohne Operatoren = Phrase (wie Field Watch); mit Anführungszeichen,
    OR oder Minus = Websuche-Syntax. Ohne diese Regel fand "precision fermentation",
    nach Zitationen sortiert, zuerst VirSorter (beide Wörter irgendwo im Abstract)."""
    q = query.strip()
    if '"' in q or re.search(r"\bOR\b", q) or re.search(r"(^|\s)-\w", q) or " " not in q:
        return "websearch_to_tsquery('english', %s)"
    return "phraseto_tsquery('english', %s)"


def doi_url(doi: str | None) -> str | None:
    if not doi:
        return None
    return doi if doi.startswith("http") else f"https://doi.org/{doi}"


def _clip(text: str | None, n: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= n else text[:n].rstrip() + " …"


def _iso(v):
    return v.isoformat()[:10] if hasattr(v, "isoformat") else (str(v)[:10] if v else None)


def _json_list(v) -> list:
    if isinstance(v, str):
        try:
            v = json.loads(v)
        except Exception:                                           # noqa: BLE001
            return []
    return list(v or [])


class _ReadOnly:
    """`with _ReadOnly("20s") as cur:` — eigene Verbindung, READ ONLY, Timeout."""

    def __init__(self, timeout: str = "30s"):
        if not re.fullmatch(r"\d+(ms|s|min)", timeout):
            raise ValueError(timeout)
        self.timeout = timeout

    def __enter__(self):
        import psycopg2
        import psycopg2.extras
        from pipeline.config import DATABASE_URL
        self.conn = psycopg2.connect(DATABASE_URL)
        self.conn.set_session(readonly=True)
        self.cur = self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        self.cur.execute(f"SET statement_timeout = '{self.timeout}'")
        return self.cur

    def __exit__(self, *exc):
        try:
            self.conn.rollback()
        finally:
            self.conn.close()
        return False


def _tier_sql() -> str:
    from pipeline.field_watch import TIER_SQL
    return TIER_SQL


FTS = ("to_tsvector('english', coalesce(t.title_en,'')||' '||coalesce(t.summary_en,'')"
       "||' '||coalesce(t.tags::text,''))")


# ---------------------------------------------------------------------------
# Query-Vektor (CPU-Embedder :8091, nie der GPU-Server)
# ---------------------------------------------------------------------------
def embed_query(text: str) -> list[float] | None:
    import os

    import httpx
    host = os.getenv("RESEARCH_EMBED_HOST") or "http://127.0.0.1:8091"
    try:
        r = httpx.post(f"{host}/v1/embeddings", json={"input": text}, timeout=30)
        r.raise_for_status()
        vec = r.json()["data"][0]["embedding"]
        return vec if len(vec) >= 1024 else None
    except Exception as exc:                                        # noqa: BLE001
        logger.warning("embedder %s unreachable: %r", host, exc)
        return None


def rrf_merge(*ranked: list[int], k: int = RRF_K) -> list[tuple[int, float]]:
    """Reciprocal Rank Fusion über mehrere ID-Ranglisten (beste zuerst)."""
    score: dict[int, float] = {}
    for lst in ranked:
        for rank, i in enumerate(lst):
            score[i] = score.get(i, 0.0) + 1.0 / (k + rank + 1)
    return sorted(score.items(), key=lambda kv: (-kv[1], -kv[0]))


# ---------------------------------------------------------------------------
# Signale
# ---------------------------------------------------------------------------
def _signal_filters(tier, vertical, since, until) -> tuple[str, list]:
    sql, params = [], []
    if tier:
        if tier not in TIERS:
            raise ToolError(f"tier must be one of {TIERS}")
        sql.append(f"({_tier_sql()}) = %s")
        params.append(tier)
    if vertical:
        sql.append("t.primary_vertical = %s")
        params.append(str(vertical).upper())
    if since:
        sql.append("t.sort_date >= %s")
        params.append(_date(since, "since"))
    if until:
        sql.append("t.sort_date < %s")
        params.append(_date(until, "until"))
    return (" AND " + " AND ".join(sql)) if sql else "", params


def _signal_rows(cur, ids: list[int]) -> dict[int, dict]:
    if not ids:
        return {}
    cur.execute(f"""SELECT t.id, t.title_en, t.summary_en, t.sort_date, t.status, t.primary_vertical,
                           t.trend_signal_type, t.mega_trend, t.source_url, t.source_name,
                           s.name AS src_name, r.url AS raw_url, ({_tier_sql()}) AS tier
                    FROM trends t LEFT JOIN raw_entries r ON r.id = t.raw_entry_id
                    LEFT JOIN sources s ON s.id = r.source_id WHERE t.id = ANY(%s)""", (ids,))
    return {r["id"]: r for r in cur.fetchall()}


def _signal_card(r: dict, summary_chars: int = 400) -> dict:
    return {"id": r["id"], "title": r["title_en"], "date": _iso(r["sort_date"]),
            "tier": r["tier"], "vertical": r["primary_vertical"], "signal_type": r["trend_signal_type"],
            "mega_trend": r["mega_trend"], "status": r["status"],
            "source": r["source_name"] or r["src_name"], "url": r["source_url"] or r["raw_url"],
            "summary": _clip(r["summary_en"], summary_chars)}


def search_signals(query: str, mode: str = "both", tier: str | None = None, vertical: str | None = None,
                   since: str | None = None, until: str | None = None, limit: int = 20) -> dict:
    """Signale (Presse, Forschung, Patente, Förderung) nach Text, Bedeutung oder beidem."""
    query = (query or "").strip()
    if not query:
        raise ToolError("query is required")
    if mode not in ("text", "meaning", "both"):
        raise ToolError("mode must be text, meaning or both")
    n = _limit(limit)
    where, params = _signal_filters(tier, vertical, since, until)
    text_ids: list[int] = []
    mean_ids: list[int] = []
    sims: dict[int, float] = {}
    notes: list[str] = []
    with _ReadOnly("25s") as cur:
        if mode in ("text", "both"):
            try:
                cur.execute(f"""SELECT t.id FROM trends t LEFT JOIN raw_entries r ON r.id = t.raw_entry_id
                                LEFT JOIN sources s ON s.id = r.source_id
                                WHERE {FTS} @@ websearch_to_tsquery('english', %s)
                                  AND t.status IN ('published','signal') {where}
                                ORDER BY ts_rank({FTS}, websearch_to_tsquery('english', %s)) DESC, t.id DESC
                                LIMIT %s""", [query] + params + [query, n * 3])
                text_ids = [r["id"] for r in cur.fetchall()]
            except Exception as exc:                                # noqa: BLE001
                cur.connection.rollback()
                cur.execute("SET statement_timeout = '25s'")
                notes.append(f"text search failed: {type(exc).__name__}")
        if mode in ("meaning", "both"):
            vec = embed_query(query)
            if vec is None:
                notes.append("meaning search unavailable (embedder :8091 not reachable)")
            else:
                lit = "[" + ",".join(f"{x:.6f}" for x in vec[:1024]) + "]"
                # Mit Filter (Ebene, Vertikale, Zeitraum) fallen die meisten Nachbarn weg —
                # pgvector 0.6 filtert NACH dem Index, also breit holen (ef_search <= 1000).
                k = 1000 if where else max(n * 3, 60)
                cur.execute(f"SET LOCAL hnsw.ef_search = {max(k, 200)}")
                cur.execute(f"""WITH nn AS (SELECT id, 1 - (embedding_1024 <=> %s::vector) AS sim FROM trends
                                    WHERE embedding_1024 IS NOT NULL AND status IN ('published','signal')
                                    ORDER BY embedding_1024 <=> %s::vector LIMIT %s)
                                SELECT nn.id, nn.sim FROM nn JOIN trends t ON t.id = nn.id
                                LEFT JOIN raw_entries r ON r.id = t.raw_entry_id
                                LEFT JOIN sources s ON s.id = r.source_id WHERE TRUE {where}
                                ORDER BY nn.sim DESC LIMIT %s""", [lit, lit, k] + params + [n * 3])
                for r in cur.fetchall():
                    mean_ids.append(r["id"])
                    sims[r["id"]] = round(float(r["sim"]), 4)
                if where and len(mean_ids) < n:
                    # Die Einbettung trennt nach Schreibstil: Patente/Förderung liegen fern von
                    # einer Alltagsfrage, unter den 1.000 Nachbarn ist oft keiner der Ebene.
                    # Rückfall: Kandidaten per Wortsuche (ODER) innerhalb des Filters, nach
                    # Vektornähe sortiert.
                    words = [w for w in re.findall(r"[A-Za-z][\w-]{2,}", query)][:12]
                    if words:
                        tq = " | ".join(words)
                        cur.execute(f"""WITH c AS (SELECT t.id, t.embedding_1024 FROM trends t
                                            LEFT JOIN raw_entries r ON r.id = t.raw_entry_id
                                            LEFT JOIN sources s ON s.id = r.source_id
                                            WHERE {FTS} @@ to_tsquery('english', %s)
                                              AND t.status IN ('published','signal')
                                              AND t.embedding_1024 IS NOT NULL {where} LIMIT 3000)
                                        SELECT id, 1 - (embedding_1024 <=> %s::vector) AS sim FROM c
                                        ORDER BY embedding_1024 <=> %s::vector LIMIT %s""",
                                    [tq] + params + [lit, lit, n * 3])
                        for r in cur.fetchall():
                            if r["id"] not in sims:
                                mean_ids.append(r["id"])
                                sims[r["id"]] = round(float(r["sim"]), 4)
                        notes.append("meaning within filter: nearest neighbours were outside the filter; "
                                     "ranked word-search candidates (any word, max 3000) by similarity")
        merged = rrf_merge(text_ids, mean_ids)[:n]
        rows = _signal_rows(cur, [i for i, _ in merged])
    tset, mset = set(text_ids), set(mean_ids)
    out = []
    for i, sc in merged:
        if i not in rows:
            continue
        card = _signal_card(rows[i])
        card["matched_by"] = "both" if (i in tset and i in mset) else ("text" if i in tset else "meaning")
        if i in sims:
            card["similarity"] = sims[i]
        out.append(card)
    return {"query": query, "mode": mode, "n": len(out), "results": out, "notes": notes}


def get_signal(signal_id: int, max_chars: int = DEFAULT_TEXT_CHARS) -> dict:
    """Ein Signal mit Text: Quelltext (falls konform geholt), sonst Teaser, plus unser Artikel."""
    try:
        sid = int(signal_id)
    except (TypeError, ValueError):
        raise ToolError("signal_id must be an integer")
    n = _chars(max_chars)
    with _ReadOnly("15s") as cur:
        cur.execute(f"""SELECT t.id, t.title_en, t.summary_en, t.body_en, t.sort_date, t.status,
                               t.primary_vertical, t.verticals, t.pestel, t.tags, t.trend_signal_type,
                               t.mega_trend, t.brands, t.companies, t.regions, t.source_url, t.source_name,
                               s.name AS src_name, r.url AS raw_url, r.title AS raw_title, r.excerpt,
                               r.raw_content, r.open_licence, ({_tier_sql()}) AS tier
                        FROM trends t LEFT JOIN raw_entries r ON r.id = t.raw_entry_id
                        LEFT JOIN sources s ON s.id = r.source_id WHERE t.id = %s""", (sid,))
        r = cur.fetchone()
    if not r:
        raise ToolError(f"no signal with id {sid}")
    src_text = r["raw_content"] if len(r["raw_content"] or "") > len(r["excerpt"] or "") else r["excerpt"]
    card = _signal_card(r, summary_chars=2000)
    card.update({
        "source_title": r["raw_title"],
        "source_text": _clip(src_text, n),
        "source_text_kind": "fulltext" if src_text and src_text == r["raw_content"] else "teaser",
        "open_licence": r["open_licence"],
        "article": _clip(r["body_en"], n) if r["status"] == "published" else None,
        "article_note": ("machine-written Catandary article (AI-generated)" if r["body_en"] else None),
        "verticals": _json_list(r["verticals"]), "pestel": _json_list(r["pestel"]),
        "tags": _json_list(r["tags"])[:20], "brands": _json_list(r["brands"])[:20],
        "companies": _json_list(r["companies"])[:20], "regions": _json_list(r["regions"]),
    })
    return card


# ---------------------------------------------------------------------------
# Forschung, Patente
# ---------------------------------------------------------------------------
def search_research(query: str, since_year: int | None = None, order: str = "cited",
                    limit: int = 20, abstract_chars: int = 600) -> dict:
    """Forschungswerke (OpenAlex-Korpus, ab 2010) per Volltextsuche über Titel+Abstract."""
    query = (query or "").strip()
    if not query:
        raise ToolError("query is required")
    if order not in ("cited", "recent"):
        raise ToolError("order must be cited or recent")
    n = _limit(limit)
    params: list = [query]
    sql = f"tsv @@ {tsquery_sql(query)} AND NOT coalesce(is_retracted, false)"
    if since_year:
        sql += " AND year >= %s"
        params.append(int(since_year))
    order_sql = "cited_by_count DESC NULLS LAST" if order == "cited" else "published DESC NULLS LAST"
    with _ReadOnly("40s") as cur:
        cur.execute(f"""SELECT id, doi, title, abstract, published, year, type, topic, cited_by_count, fwci
                        FROM research_corpus WHERE {sql} ORDER BY {order_sql} LIMIT %s""", params + [n])
        rows = cur.fetchall()
    out = [{"id": r["id"], "doi": r["doi"], "url": doi_url(r["doi"]),
            "title": r["title"], "year": r["year"], "published": _iso(r["published"]), "type": r["type"],
            "topic": r["topic"], "cited_by": r["cited_by_count"],
            "fwci": round(r["fwci"], 2) if r["fwci"] is not None else None,
            "abstract": _clip(r["abstract"], _chars(abstract_chars, 600))} for r in rows]
    return {"query": query, "order": order, "n": len(out), "results": out}


def search_patents(query: str, since: str | None = None, limit: int = 20) -> dict:
    """Patente (Volltextindex Titel+Abstract), neueste zuerst, mit Anmeldern."""
    query = (query or "").strip()
    if not query:
        raise ToolError("query is required")
    n = _limit(limit)
    params: list = [query]
    sql = f"p.tsv @@ {tsquery_sql(query)}"
    if since:
        sql += " AND p.published >= %s"
        params.append(_date(since, "since"))
    with _ReadOnly("40s") as cur:
        cur.execute(f"""SELECT p.pub_number, p.published FROM patent_search p WHERE {sql}
                        ORDER BY p.published DESC NULLS LAST LIMIT %s""", params + [n])
        hits = cur.fetchall()
        pubs = [h["pub_number"] for h in hits]
        cur.execute("""SELECT DISTINCT ON (pub_number) pub_number, title, url, excerpt FROM raw_entries
                       WHERE pub_number = ANY(%s) ORDER BY pub_number, id""", (pubs,))
        meta = {r["pub_number"]: r for r in cur.fetchall()}
        cur.execute("""SELECT pub_number, array_agg(name ORDER BY seq) AS names FROM patent_assignee_raw
                       WHERE pub_number = ANY(%s) GROUP BY 1""", (pubs,))
        assg = {r["pub_number"]: r["names"][:4] for r in cur.fetchall()}
    out = []
    for h in hits:
        m = meta.get(h["pub_number"]) or {}
        out.append({"pub_number": h["pub_number"], "published": _iso(h["published"]),
                    "title": m.get("title"), "url": m.get("url"),
                    "abstract": _clip(m.get("excerpt"), 600), "assignees": assg.get(h["pub_number"], [])})
    return {"query": query, "n": len(out), "results": out}


def term_counts(terms, since_year: int = 1990) -> dict:
    """Treffer je Begriff und Ebene (Feld-Einrichtung): wie stark trägt ein Begriff
    im Korpus? Phrasen-Suche wie in Field Watch (`phraseto_tsquery`)."""
    terms = _terms(terms)
    y0 = int(since_year or 1990)
    out = []
    with _ReadOnly("60s") as cur:
        for term in terms:
            row = {"term": term}
            try:
                cur.execute(f"""SELECT ({_tier_sql()}) AS tier, count(*) AS n FROM trends t
                                JOIN raw_entries r ON r.id = t.raw_entry_id JOIN sources s ON s.id = r.source_id
                                WHERE {FTS} @@ phraseto_tsquery('english', %s) AND t.sort_date >= %s
                                  AND r.pub_number IS NULL GROUP BY 1""", (term, date(y0, 1, 1)))
                tiers = {r["tier"]: r["n"] for r in cur.fetchall() if r["tier"]}
                row["market"] = tiers.get("market", 0)
                row["funding"] = tiers.get("funding", 0)
                cur.execute("SELECT count(*) n FROM research_corpus WHERE tsv @@ phraseto_tsquery('english', %s) AND year >= %s",
                            (term, max(y0, 2010)))
                row["science"] = cur.fetchone()["n"]
                cur.execute("SELECT count(*) n FROM patent_search WHERE tsv @@ phraseto_tsquery('english', %s) AND published >= %s",
                            (term, date(y0, 1, 1)))
                row["patent"] = cur.fetchone()["n"]
            except Exception as exc:                                # noqa: BLE001
                cur.connection.rollback()
                cur.execute("SET statement_timeout = '60s'")
                row["error"] = type(exc).__name__
            out.append(row)
    return {"since_year": y0, "science_from": 2010, "terms": out}


# ---------------------------------------------------------------------------
# Field Watch / Trajectory Sheet
# ---------------------------------------------------------------------------
def field_list(customer: str | None = None) -> dict:
    """Kundendateien (fields/*.yaml) und ihre Felder."""
    from pipeline.field_watch import FIELDS_DIR, load_customer
    paths = sorted(FIELDS_DIR.glob("*.yaml"))
    if customer:
        paths = [p for p in paths if p.stem == customer]
        if not paths:
            raise ToolError(f"no customer file fields/{customer}.yaml")
    out = []
    for p in paths:
        try:
            c = load_customer(str(p))
        except Exception as exc:                                    # noqa: BLE001
            out.append({"file": p.name, "error": str(exc)})
            continue
        out.append({"slug": c["slug"], "customer": c["customer"], "example": p.stem.startswith("example"),
                    "fields": [{"slug": f["slug"], "name": f["name"], "name_en": f.get("name_en"),
                                "terms": f["terms"], "cpc": f.get("cpc") or [],
                                "has_reading": bool(f.get("reading")),
                                "has_regulatory": bool(f.get("regulatory"))} for f in c["fields"]]})
    return {"customers": out}


def _customer_field(customer: str, field: str | None):
    from pipeline.field_watch import load_customer
    try:
        cust = load_customer(customer)
    except Exception as exc:                                        # noqa: BLE001
        raise ToolError(f"customer {customer!r}: {exc}")
    if field is None:
        return cust, None
    f = next((x for x in cust["fields"] if x["slug"] == field), None)
    if not f:
        raise ToolError(f"field {field!r} not in {cust['slug']}: {[x['slug'] for x in cust['fields']]}")
    return cust, f


def field_week(customer: str, week_date: str | None = None) -> dict:
    """Wochenmessung aller Felder eines Kunden (wie das Wochenblatt)."""
    from pipeline.field_watch import measure_week
    cust, _ = _customer_field(customer, None)
    today = date.fromisoformat(_date(week_date, "week_date")) if week_date else None
    return measure_week(cust["fields"], today)


def field_sheet(customer: str, field: str) -> dict:
    """Trajectory-Sheet-Messung eines Feldes (Jahresreihen, Take-off, Anmelder, Reifegrad)."""
    from pipeline.field_watch import measure_sheet
    _, f = _customer_field(customer, field)
    return measure_sheet(f)


def field_probe(phrase: str, terms=None, cpc=None) -> dict:
    """Feldprobe ohne GPU: Messung für eine Phrase. Ohne CPC-Anker fehlt der
    Reifegradblock (die Kandidatenklassen braucht die GPU — `scripts/field_watch.py --probe`)."""
    from pipeline.field_watch import measure_sheet, slugify
    phrase = (phrase or "").strip()
    if not phrase:
        raise ToolError("phrase is required")
    t = _terms(terms) if terms else [phrase]
    c = [x.strip() for x in (cpc.split(",") if isinstance(cpc, str) else (cpc or [])) if str(x).strip()]
    field = {"name": phrase, "name_en": phrase, "slug": slugify(phrase), "terms": t, "cpc": c, "reading": ""}
    d = measure_sheet(field)
    d["probe"] = {"phrase": phrase, "anchor_used": c,
                  "note": None if c else "no CPC anchor given: maturity block empty (GPU candidate lookup only via scripts/field_watch.py --probe)"}
    return d


def tir_block(cpc) -> dict:
    """Reifegradblock zu CPC-Ankern: Verbesserungsrate (relativ), Zykluszeit, Zentralität."""
    from pipeline.field_watch import cycle_time, quant_block
    codes = [x.strip() for x in (cpc.split(",") if isinstance(cpc, str) else (cpc or [])) if str(x).strip()]
    if not codes:
        raise ToolError("at least one CPC code is required")
    return {"cpc": codes, "quant": quant_block(codes), "cycle_time": cycle_time(codes)}


def emerging_nests(scope: str = "global", limit: int = 20) -> dict:
    """Nester (dichte, junge Signal-Taschen) des jüngsten Laufs eines Scopes."""
    n = _limit(limit)
    with _ReadOnly("15s") as cur:
        cur.execute("SELECT id, scope, created_at, window_days, signals, nests FROM emerging_runs WHERE scope = %s "
                    "ORDER BY created_at DESC LIMIT 1", (scope,))
        run = cur.fetchone()
        if not run:
            cur.execute("SELECT scope, max(created_at) AS last FROM emerging_runs GROUP BY 1 ORDER BY 2 DESC LIMIT 40")
            raise ToolError(f"no run for scope {scope!r}; known: {[r['scope'] for r in cur.fetchall()]}")
        cur.execute("""SELECT id, coalesce(llm_label, label) AS name, label, size, cohesion, n_sources, top_source,
                              top_source_share, first_month, age_months, novelty_lift, accel, rep_titles, tiers,
                              tier_order, science_to_market_months, group_label
                       FROM emerging_nests WHERE run_id = %s ORDER BY novelty_lift DESC NULLS LAST LIMIT %s""",
                    (run["id"], n))
        nests = []
        for r in cur.fetchall():
            titles = _json_list(r["rep_titles"])[:3]
            nests.append({"id": r["id"], "name": r["name"], "keywords": r["label"], "size": r["size"],
                          "cohesion": round(r["cohesion"] or 0, 3), "sources": r["n_sources"],
                          "top_source": r["top_source"], "top_source_share": r["top_source_share"],
                          "first_month": r["first_month"], "age_months": r["age_months"],
                          "novelty_lift": r["novelty_lift"], "accel": r["accel"], "group": r["group_label"],
                          "tier_order": r["tier_order"], "science_to_market_months": r["science_to_market_months"],
                          "examples": titles})
    return {"run": {"id": run["id"], "scope": run["scope"], "created_at": str(run["created_at"])[:16],
                    "window_days": run["window_days"], "signals": run["signals"], "nests": run["nests"]},
            "nests": nests}


# ---------------------------------------------------------------------------
# Web: Suche + konformer Abruf
# ---------------------------------------------------------------------------
def _host_ok(host: str) -> bool:
    """Nur öffentliche Ziele (kein SSRF auf localhost/LAN/Tailnet)."""
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%")[0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
                or ip.is_multicast or ip.is_unspecified or ip in ipaddress.ip_network("100.64.0.0/10")):
            return False
    return True


def check_url(url: str) -> str:
    url = (url or "").strip()
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise ToolError("only http(s) URLs")
    if not _host_ok(p.hostname):
        raise ToolError("URL points to a non-public address")
    return url


_CELEX_RE = re.compile(r"CELEX(?::|%3A)([0-9A-Z()]+)", re.IGNORECASE)


def cellar_url(url: str) -> str | None:
    """EUR-Lex-Link mit CELEX-Nummer → Cellar-Adresse desselben Rechtsakts (oder None)."""
    if (urlparse(url).hostname or "").lower() != "eur-lex.europa.eu":
        return None
    m = _CELEX_RE.search(url)
    return f"https://publications.europa.eu/resource/celex/{m.group(1).upper()}" if m else None


def domain_matches(url: str, domains: list[str]) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == d or host.endswith("." + d) for d in domains)


def web_search(query: str, count: int = 8, domains=None) -> dict:
    """Websuche (Brave → SearXNG). `domains` begrenzt auf diese Hosts (auch nachträglich geprüft)."""
    from pipeline import web_search as ws
    query = (query or "").strip()
    if not query:
        raise ToolError("query is required")
    doms = [d.strip().lower().removeprefix("www.") for d in
            (domains.split(",") if isinstance(domains, str) else (domains or [])) if d and d.strip()]
    # Lange site:-Listen in EINER Anfrage verwässern die Suche — in Gruppen zu 5 fragen.
    groups = [doms[i:i + 5] for i in range(0, len(doms), 5)] or [[]]
    raw, backend, errors = [], None, []
    for g in groups:
        q = query + (" (" + " OR ".join(f"site:{d}" for d in g) + ")" if g else "")
        try:
            hits, backend = ws.search_raw(q, count=min(int(count or 8) * (2 if g else 1), 20))
            raw.extend(hits)
        except Exception as exc:                                    # noqa: BLE001
            errors.append(str(exc)[:120])
    if not raw and errors:
        raise ToolError(f"web search unavailable: {errors[0]}")
    out, seen = [], set()
    for x in raw:
        if str(x.get("url") or "") in seen:
            continue
        seen.add(str(x.get("url") or ""))
        url = str(x.get("url") or "")
        if not url.startswith("http") or (doms and not domain_matches(url, doms)):
            continue
        out.append({"url": url, "title": x.get("title"), "snippet": _clip(re.sub(r"<[^>]+>", "", x.get("description") or ""), 400),
                    "date": (x.get("page_age") or "")[:10] or None})
        if len(out) >= int(count or 8):
            break
    return {"query": query, "domains": doms, "backend": backend, "n": len(out), "results": out}


def fetch_url(url: str, max_chars: int = DEFAULT_TEXT_CHARS, terms=None) -> dict:
    """Seite konform holen (CatandaryTrendsBot, robots, TDM). Rechtstexte werden um
    `terms` artikelweise geschnitten. Kein Text bei Vorbehalt/Sperre — der Grund steht dabei."""
    from pipeline import article_fetcher, legal_text, web_cache
    url = check_url(url)
    n = _chars(max_chars)
    legal = legal_text.is_legal_host(url)
    via = cellar_url(url)
    key = web_cache.make_key("page-legal" if legal else "page-corpus-api", via or url)
    hit = web_cache.cache_get("page", key)
    if isinstance(hit, dict) and hit.get("text"):
        text, reason, cached = hit.get("text"), hit.get("reason"), True
    else:
        client = None
        if via:
            # EUR-Lex beantwortet Bot-Abrufe mit einer Challenge (HTTP 202). Derselbe Rechtsakt
            # kommt vom Cellar des Amts für Veröffentlichungen per Content Negotiation — über
            # denselben Fetcher (robots, TDM, Drossel), nur mit Accept-Kopf für XHTML.
            import httpx
            client = httpx.Client(timeout=60, follow_redirects=True,
                                  headers={"User-Agent": article_fetcher.UA,
                                           "Accept": "application/xhtml+xml",
                                           "Accept-Language": "eng"})
        try:
            res = article_fetcher.fetch_fulltext_result(
                via or url, client=client,
                max_chars=legal_text.LEGAL_FETCH_CHARS if legal else article_fetcher.MAX_TEXT_CHARS)
        finally:
            if client is not None:
                client.close()
        text, reason, cached = res.text, res.reason, False
        if text:  # nur Treffer cachen — eine Sperre/Challenge kann morgen anders aussehen
            web_cache.cache_put("page", key, {"text": text, "reason": None})
    sliced: list[str] = []
    if text and legal and terms:
        text, sliced = legal_text.slice_articles(text, _terms(terms), limit=max(n, legal_text.LEGAL_KEEP_CHARS))
    return {"url": url, "fetched_via": via, "ok": bool(text), "reason": None if text else (reason or "no text"),
            "legal": legal, "articles": sliced, "cached": cached, "chars": len(text or ""),
            "text": _clip(text, n) if text else None}


# ---------------------------------------------------------------------------
# EUR-Lex (Cellar SPARQL, offen, ohne Registrierung)
# ---------------------------------------------------------------------------
EURLEX_SPARQL = "https://publications.europa.eu/webapi/rdf/sparql"


def eurlex_search(keywords, in_force_only: bool = True, limit: int = 15) -> dict:
    """EU-Rechtsakte (Verordnung, Richtlinie, Beschluss) mit allen Stichwörtern im
    englischen Titel; CELEX, Datum, Link. Grundrechtsakte (Verordnung, Richtlinie) zuerst,
    dann Durchführungs-/delegierte Rechtsakte und Beschlüsse, je neueste zuerst — sonst
    verdrängen Dutzende Einzelzulassungen den Rahmen (gemessen „novel food": 2015/2283
    fehlte unter den ersten 6). Danach mit `fetch_url` artikelweise lesen."""
    import httpx

    from pipeline.article_fetcher import UA
    kws = _terms(keywords)
    for k in kws:
        if not re.fullmatch(r"[\w\- ]{2,60}", k):
            raise ToolError(f"keyword {k!r}: letters, digits, space and hyphen only")
    n = _limit(limit, 15)
    filters = "\n".join(f'FILTER(CONTAINS(LCASE(STR(?title)), "{k.lower()}"))' for k in kws)
    force = "?work cdm:resource_legal_in-force \"true\"^^xsd:boolean ." if in_force_only else ""
    q = f"""PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
SELECT DISTINCT ?celex ?date ?title ?type WHERE {{
  ?work cdm:resource_legal_id_celex ?celex ;
        cdm:work_has_resource-type ?type ;
        cdm:work_date_document ?date .
  {force}
  FILTER(?type IN (<http://publications.europa.eu/resource/authority/resource-type/REG>,
                   <http://publications.europa.eu/resource/authority/resource-type/DIR>,
                   <http://publications.europa.eu/resource/authority/resource-type/DEC>,
                   <http://publications.europa.eu/resource/authority/resource-type/REG_IMPL>,
                   <http://publications.europa.eu/resource/authority/resource-type/REG_DEL>))
  ?expr cdm:expression_belongs_to_work ?work ;
        cdm:expression_uses_language <http://publications.europa.eu/resource/authority/language/ENG> ;
        cdm:expression_title ?title .
  {filters}
  BIND(IF(?type IN (<http://publications.europa.eu/resource/authority/resource-type/REG>,
                    <http://publications.europa.eu/resource/authority/resource-type/DIR>), 0, 1) AS ?prio)
}} ORDER BY ?prio DESC(?date) LIMIT {n}"""
    try:
        r = httpx.get(EURLEX_SPARQL, params={"query": q, "format": "application/sparql-results+json"},
                      headers={"User-Agent": UA, "Accept": "application/sparql-results+json"}, timeout=60)
        r.raise_for_status()
        rows = r.json()["results"]["bindings"]
    except Exception as exc:                                        # noqa: BLE001
        raise ToolError(f"EUR-Lex SPARQL unavailable: {type(exc).__name__}: {str(exc)[:120]}")
    out = []
    for b in rows:
        celex = b["celex"]["value"]
        out.append({"celex": celex, "date": b["date"]["value"][:10], "type": b["type"]["value"].rsplit("/", 1)[-1],
                    "title": _clip(b["title"]["value"], 400),
                    "url": f"https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:{celex}"})
    return {"keywords": kws, "in_force_only": bool(in_force_only), "n": len(out), "results": out}


# ---------------------------------------------------------------------------
# Retriever für gpt-researcher (Format: [{url, raw_content, title}], nur MIT Text)
# ---------------------------------------------------------------------------
GPTR_TEXT_CHARS = 6_000


def _corpus_documents(query: str, max_results: int, since: str | None) -> list[dict]:
    docs: list[dict] = []
    per = max(2, max_results)
    try:
        sig = search_signals(query, mode="both", since=since, limit=per)["results"]
    except ToolError:
        sig = []
    if sig:
        with _ReadOnly("15s") as cur:
            cur.execute("""SELECT t.id, r.raw_content, r.excerpt FROM trends t LEFT JOIN raw_entries r
                           ON r.id = t.raw_entry_id WHERE t.id = ANY(%s)""", ([s["id"] for s in sig],))
            texts = {r["id"]: (r["raw_content"] if len(r["raw_content"] or "") > len(r["excerpt"] or "") else r["excerpt"])
                     for r in cur.fetchall()}
        for s in sig:
            body = texts.get(s["id"]) or s.get("summary")
            if not s.get("url") or not body or len(body) < 80:
                continue
            head = f"[Catandary corpus · {s.get('tier') or 'signal'} · {s.get('date')} · {s.get('source')}]"
            docs.append({"url": s["url"], "title": s["title"],
                         "raw_content": _clip(f"{head}\n{s['title']}\n\n{body}", GPTR_TEXT_CHARS)})
    try:
        for w in search_research(query, since_year=int(since[:4]) if since else None, order="cited",
                                 limit=max(2, max_results // 2), abstract_chars=3000)["results"]:
            if w["url"] and w["abstract"] and len(w["abstract"]) >= 80:
                head = f"[Catandary corpus · science · {w['published']} · cited by {w['cited_by']}]"
                docs.append({"url": w["url"], "title": w["title"],
                             "raw_content": f"{head}\n{w['title']}\n\n{w['abstract']}"})
    except ToolError:
        pass
    return docs


def _web_documents(query: str, max_results: int, domains: list[str]) -> list[dict]:
    try:
        hits = web_search(query, count=max_results, domains=domains or None)["results"]
    except ToolError as exc:
        logger.warning("gptr web search: %s", exc)
        return []
    terms = [w for w in re.findall(r"[\w-]{4,}", query)][:12]

    def one(h):
        try:
            f = fetch_url(h["url"], max_chars=GPTR_TEXT_CHARS, terms=terms or None)
        except ToolError:
            return None
        if not f["ok"] or f["chars"] < 200:
            return None
        return {"url": h["url"], "title": h.get("title") or h["url"], "raw_content": f["text"]}

    with ThreadPoolExecutor(FETCH_WORKERS) as ex:
        return [d for d in ex.map(one, hits) if d]


def gptr_retrieve(query: str, scope: str = "both", domains=None, max_results: int = 6,
                  since: str | None = None) -> list[dict]:
    """Treffer für den `custom`-Retriever von gpt-researcher. Gibt NIE einen Treffer ohne
    Text zurück — sonst würde gpt-researcher die Seite selbst holen (researcher.py)."""
    if scope not in ("corpus", "web", "both"):
        raise ToolError("scope must be corpus, web or both")
    n = max(1, min(int(max_results or 6), 12))
    doms = [d.strip().lower() for d in (domains.split(",") if isinstance(domains, str) else (domains or [])) if d.strip()]
    docs: list[dict] = []
    if scope in ("corpus", "both"):
        docs += _corpus_documents(query, n, since)
    if scope in ("web", "both"):
        docs += _web_documents(query, n, doms)
    seen, out = set(), []
    for d in docs:
        if d["url"] in seen or not (d.get("raw_content") or "").strip():
            continue
        seen.add(d["url"])
        out.append(d)
    return out


def gptr_fetch(urls) -> list[dict]:
    """Ersatz für den Scraper von gpt-researcher: holt jede URL konform; ohne Text kein Eintrag."""
    urls = [u for u in (urls or []) if isinstance(u, str)][:20]

    def one(u):
        try:
            f = fetch_url(u, max_chars=GPTR_TEXT_CHARS)
        except ToolError:
            return None
        if not f["ok"]:
            return None
        return {"url": u, "raw_content": f["text"], "image_urls": [], "title": ""}

    with ThreadPoolExecutor(FETCH_WORKERS) as ex:
        return [d for d in ex.map(one, urls) if d]


# ---------------------------------------------------------------------------
# Werkzeug-Register (Name → Funktion); der Dienst ruft nur, was hier steht
# ---------------------------------------------------------------------------
TOOLS = {
    "search_signals": search_signals,
    "get_signal": get_signal,
    "search_research": search_research,
    "search_patents": search_patents,
    "term_counts": term_counts,
    "field_list": field_list,
    "field_week": field_week,
    "field_sheet": field_sheet,
    "field_probe": field_probe,
    "tir_block": tir_block,
    "emerging_nests": emerging_nests,
    "web_search": web_search,
    "fetch_url": fetch_url,
    "eurlex_search": eurlex_search,
    "gptr_retrieve": gptr_retrieve,
    "gptr_fetch": gptr_fetch,
}


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]
