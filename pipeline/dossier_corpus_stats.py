"""Zweite deterministische Vorstufe: was der eigene Korpus zum Thema ZÄHLT.

Der Rechercheur (scripts/corpus_research.py) behandelt den Korpus wie eine
Suchmaschine: jede Retrieval-Funktion gibt Zeilen zurück, es gibt in der ganzen
Datei keine einzige Aggregat-Query. Für GLP-1 heißt das: von 2.124 Markt-
signalen und 29.825 Arbeiten sieht der Schreiber rund 45 Titel — 0,1 % — und
über die restlichen 99,9 % darf er nichts sagen, weil sie nie gezählt wurden.

Dieses Modul zählt sie. Rein lesend, deterministisch, vor dem ersten
Modell-Hop — dieselbe Begründung wie bei pipeline/dossier_quant.py: Messung
ist kein Ermessen. Das Ergebnis wird als zitierbare Katalogquelle `Q0` plus
codegenerierter Anhang „Was der Korpus zählt" injiziert.

Was NICHT drin ist, und warum (die Grenze gehört ins Dossier, nicht in eine
stille Auslassung):

  * **Patente.** Der Textzähler auf `patent_search` braucht für ein Thema wie
    GLP-1 ~130 s (gemessen 2026-09-07) und misst dieselbe Ebene, die der
    Messanhang bereits CPC-nativ und viel schärfer erfasst. Doppelt gezählt
    wird nicht.
  * **Ventures/`startup_events`** (420.564 Zeilen, davon 24.813 `clinical` und
    11.549 `fda_clearance`). Die Tabelle trägt keinen Text; die Brücke zum
    Thema führt über `startup_patent_links` ⋈ Patent-Textmenge und kostet
    ~350 s — außerhalb des Laufbudgets eines Dossiers. Der Anhang sagt das,
    statt die Schicht kommentarlos wegzulassen.
  * **`raw_entries`** (21,9 Mio / 41 GB) hat keinen FTS-Index; eine
    Volltextsuche über die Rohschicht ist nicht möglich.

Jeder Block hat sein eigenes `statement_timeout` und degradiert einzeln: eine
zu teure Query wird als „nicht gemessen" berichtet, nie als Zahl geraten.
"""
from __future__ import annotations

import logging
import re
import time
from datetime import date

logger = logging.getLogger("dossier_corpus_stats")

CORPUS_TOOL_URL = "https://catandary.de/trends"
BLOCK_TIMEOUT = "90s"
TOP_N = 10
MIN_YEAR = 2005

# Überschriften des codegenerierten Korpus-Anhangs — textgleich zu den
# Schnittmarken in pipeline/dossier_check.py.
CORPUS_HEADINGS = (
    "## What the corpus counts (auto-generated)",
    "## Was der Korpus zählt (automatisch erzeugt)",
)

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9+#./-]*")


def topic_tsquery(topic: str, cap: int = 8) -> str:
    """OR-Query über die Inhaltswörter des Themas — dieselbe Wortmenge, die
    pipeline/dossier_quant.normalize_topic() übrig lässt."""
    from pipeline.dossier_quant import normalize_topic
    terms: list[str] = []
    for w in _WORD_RE.findall(normalize_topic(topic).lower()):
        w = w.strip(".-/")
        if len(w) >= 3 and w not in terms:
            terms.append(w)
        if len(terms) >= cap:
            break
    return " | ".join(terms)


def _rows(sql: str, params: tuple, timeout: str = BLOCK_TIMEOUT) -> list[dict]:
    from pipeline.db import get_connection
    with get_connection() as conn:
        conn.execute(f"SET statement_timeout = '{timeout}'")
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def _tally(rows: list[dict], key: str, top: int = TOP_N) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for r in rows:
        v = r.get(key)
        if v in (None, ""):
            continue
        counts[str(v)] = counts.get(str(v), 0) + 1
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:top]


def _years(rows: list[dict], key: str = "yr") -> dict[int, int]:
    out: dict[int, int] = {}
    for r in rows:
        try:
            y = int(str(r.get(key))[:4])
        except (TypeError, ValueError):
            continue
        if 1980 <= y <= 2100:
            out[y] = out.get(y, 0) + 1
    return dict(sorted(out.items()))


def measure_market(tsq: str) -> dict:
    """Markt-/Signalschicht: `trends` über idx_trends_fts. Eine Index-Abfrage,
    danach wird in Python aggregiert (billiger als vier GROUP BYs)."""
    from pipeline.dossier_quant import FTS_VECTOR
    t0 = time.time()
    sql = ("SELECT status, primary_vertical AS vertical, trend_signal_type AS sigtype, "
           "       source_name AS outlet, "
           "       substr(coalesce(sort_date, created_at)::text, 1, 4) AS yr "
           f"  FROM trends WHERE {FTS_VECTOR} @@ to_tsquery('english', ?)")
    try:
        rows = _rows(sql, (tsq,))
    except Exception as exc:                                        # noqa: BLE001
        logger.warning("market tally not measured: %r", exc)
        return {"ok": False, "reason": f"not measured ({type(exc).__name__})"}
    years = _years(rows)
    return {
        "ok": True, "n": len(rows), "seconds": round(time.time() - t0, 1),
        "published": sum(1 for r in rows if r.get("status") == "published"),
        "signals": sum(1 for r in rows if r.get("status") == "signal"),
        "first": min(years) if years else None,
        "last": max(years) if years else None,
        "years": years,
        "verticals": _tally(rows, "vertical"),
        "signal_types": _tally(rows, "sigtype"),
        "outlets": _tally(rows, "outlet", 12),
    }


def measure_science(tsq: str) -> dict:
    """Wissenschaftsschicht: `research_corpus` (45,5 Mio, GIN idx_rc_tsv) plus
    die Förderer-Nebentabelle. Institutionen/Journale bleiben außen vor — die
    Joins verdoppeln die Laufzeit, ohne eine neue Aussage zu tragen."""
    t0 = time.time()
    try:
        rows = _rows("SELECT year AS yr, type AS kind, cited_by_count AS cites "
                     "  FROM research_corpus WHERE tsv @@ to_tsquery('english', ?)",
                     (tsq,))
    except Exception as exc:                                        # noqa: BLE001
        logger.warning("science tally not measured: %r", exc)
        return {"ok": False, "reason": f"not measured ({type(exc).__name__})"}
    out = {
        "ok": True, "n": len(rows), "seconds": round(time.time() - t0, 1),
        "reviews": sum(1 for r in rows if r.get("kind") == "review"),
        "citations": sum(int(r.get("cites") or 0) for r in rows),
        "years": _years(rows),
        "funders": [],
    }
    try:
        f = _rows("WITH hit AS (SELECT id FROM research_corpus "
                  "             WHERE tsv @@ to_tsquery('english', ?)) "
                  "SELECT f.funder AS name, count(*) AS n "
                  "  FROM hit JOIN research_work_funder f ON f.work_id = hit.id "
                  " GROUP BY 1 ORDER BY n DESC LIMIT ?", (tsq, TOP_N), "60s")
        out["funders"] = [(r["name"], int(r["n"])) for r in f]
    except Exception as exc:                                        # noqa: BLE001
        logger.warning("funder tally not measured: %r", exc)
    return out


def measure_corpus(topic: str) -> dict:
    """Beide Blöcke; jeder degradiert einzeln."""
    tsq = topic_tsquery(topic)
    if not tsq:
        return {"ok": False, "reason": "no usable topic terms", "tsquery": ""}
    t0 = time.time()
    market = measure_market(tsq)
    science = measure_science(tsq)
    ok = bool(market.get("ok") or science.get("ok"))
    return {"ok": ok, "reason": None if ok else "no corpus block completed",
            "tsquery": tsq, "market": market, "science": science,
            "seconds": round(time.time() - t0, 1),
            "measured_on": date.today().isoformat()}


# ---------------------------------------------------------------------------
# Formatierung
# ---------------------------------------------------------------------------

def _year_table(years: dict, de: bool, label: str) -> list[str]:
    ys = {y: n for y, n in (years or {}).items() if y >= MIN_YEAR}
    if len(ys) < 3:
        return []
    return ["| " + ("Jahr" if de else "year") + f" | {label} |", "|---|---|"] + \
           [f"| {y} | {n:,} |" for y, n in sorted(ys.items())]


def _pairs(pairs: list, sep: str = " · ") -> str:
    return sep.join(f"{k} {v:,}" for k, v in pairs)


def format_corpus_stats(stats: dict, topic: str, lang: str = "en") -> dict:
    """{sources, note, appendix} — Q0 als zitierbare Messquelle plus der
    codegenerierte Anhang."""
    de = lang == "de"
    m = stats.get("market") or {}
    s = stats.get("science") or {}
    tsq = stats.get("tsquery") or ""
    today = stats.get("measured_on") or date.today().isoformat()

    note_lines = [
        f"Corpus tally for {topic!r} (Catandary corpus, deterministic count, "
        f"measured {today}; search terms: {tsq}):"]
    if m.get("ok"):
        note_lines.append(
            f"* Market/signal layer (trends): {m['n']:,} entries "
            f"({m['published']:,} written up, {m['signals']:,} captured signals), "
            f"{m.get('first')}–{m.get('last')}.")
        if m.get("years"):
            note_lines.append("  - entries by year: " + ", ".join(
                f"{y}:{n}" for y, n in sorted(m["years"].items()) if y >= MIN_YEAR))
        if m.get("verticals"):
            note_lines.append("  - by vertical: " + _pairs(m["verticals"]))
        if m.get("signal_types"):
            note_lines.append("  - by signal type: " + _pairs(m["signal_types"]))
        if m.get("outlets"):
            note_lines.append("  - most frequent outlets: " + _pairs(m["outlets"]))
    if s.get("ok"):
        note_lines.append(
            f"* Research layer (research_corpus, 45M works): {s['n']:,} works, "
            f"{s['reviews']:,} of them reviews, {s['citations']:,} citations "
            f"accumulated.")
        if s.get("years"):
            note_lines.append("  - works by year: " + ", ".join(
                f"{y}:{n}" for y, n in sorted(s["years"].items()) if y >= MIN_YEAR))
        if s.get("funders"):
            note_lines.append("  - most frequent funders of those works: "
                              + _pairs(s["funders"]))
    note_lines.append(
        "* Counting limits: the research series only becomes reliable from 2010 "
        "(corpus edge) and the market series only from the start of our own RSS "
        "collection — a rise at the left edge of either series measures coverage, "
        "not the world. Patent counts are not repeated here (the measurement "
        "appendix covers them CPC-natively). The venture layer (420,564 startup "
        "events) carries no text and its bridge to a topic costs ~350 s, which is "
        "outside a dossier run's query budget.")
    note = "\n".join(note_lines)

    snip = []
    if m.get("ok"):
        snip.append(f"{m['n']:,} market signals ({m['published']:,} written up), "
                    f"{m.get('first')}–{m.get('last')}")
    if s.get("ok"):
        snip.append(f"{s['n']:,} research works, {s['citations']:,} citations")
    if s.get("funders"):
        snip.append("top funder " + " ".join(str(x) for x in s["funders"][0]))
    sources = [{
        "id": "Q0", "trend_id": None, "kind": "measurement",
        "title": f"Corpus tally: {topic}",
        "url": CORPUS_TOOL_URL, "origin": CORPUS_TOOL_URL,
        "outlet": "Catandary corpus count", "vertical": "", "date": today,
        "snippet": (" · ".join(snip)
                    or "Deterministic count over the Catandary corpus.")[:420],
        "fetched": True,
    }]

    L = ["", "---", "", CORPUS_HEADINGS[1] if de else CORPUS_HEADINGS[0], ""]
    L.append(
        f"Deterministische Zählung über den eigenen Korpus am {today} "
        f"(Suchbegriffe: `{tsq}`). Kein Modelltext — jede Zahl ist ein "
        f"Query-Ergebnis."
        if de else
        f"Deterministic count over our own corpus on {today} "
        f"(search terms: `{tsq}`). No model text — every figure is a query result.")
    L.append("")
    if m.get("ok"):
        L.append("### " + ("Markt- und Signalschicht" if de
                           else "Market and signal layer"))
        L.append("")
        L.append((f"**{m['n']:,} Einträge** ({m['published']:,} ausgearbeitete "
                  f"Artikel, {m['signals']:,} erfasste Signale), "
                  f"{m.get('first')}–{m.get('last')}."
                  if de else
                  f"**{m['n']:,} entries** ({m['published']:,} written-up articles, "
                  f"{m['signals']:,} captured signals), {m.get('first')}–{m.get('last')}."))
        L.append("")
        tbl = _year_table(m.get("years") or {}, de,
                          "Einträge" if de else "entries")
        if tbl:
            L += tbl + [""]
        if m.get("verticals"):
            L.append(("**Nach Vertikale:** " if de else "**By vertical:** ")
                     + _pairs(m["verticals"]))
        if m.get("signal_types"):
            L.append(("**Nach Signaltyp:** " if de else "**By signal type:** ")
                     + _pairs(m["signal_types"]))
        if m.get("outlets"):
            L.append(("**Häufigste Quellen:** " if de else "**Most frequent outlets:** ")
                     + _pairs(m["outlets"]))
        L.append("")
    elif m.get("reason"):
        L.append(("Markt-/Signalschicht: " if de else "Market/signal layer: ")
                 + str(m["reason"]) + ".")
        L.append("")
    if s.get("ok"):
        L.append("### " + ("Wissenschaftsschicht" if de else "Research layer"))
        L.append("")
        L.append((f"**{s['n']:,} Arbeiten** im 45-Mio-Forschungskorpus, davon "
                  f"{s['reviews']:,} Reviews, zusammen {s['citations']:,} Zitationen."
                  if de else
                  f"**{s['n']:,} works** in the 45M research corpus, "
                  f"{s['reviews']:,} of them reviews, {s['citations']:,} citations "
                  f"between them."))
        L.append("")
        tbl = _year_table(s.get("years") or {}, de,
                          "Arbeiten" if de else "works")
        if tbl:
            L += tbl + [""]
        if s.get("funders"):
            L.append(("**Häufigste Geldgeber dieser Arbeiten:** " if de
                      else "**Most frequent funders of those works:** ")
                     + _pairs(s["funders"]))
            L.append("")
    elif s.get("reason"):
        L.append(("Wissenschaftsschicht: " if de else "Research layer: ")
                 + str(s["reason"]) + ".")
        L.append("")
    L.append(
        "*Zählgrenzen: die Forschungsreihe wird erst ab 2010 belastbar "
        "(Korpuskante), die Marktreihe erst ab dem Beginn der eigenen "
        "RSS-Erhebung — ein Anstieg am linken Rand misst die Abdeckung, nicht "
        "die Welt. Patente sind hier nicht noch einmal gezählt (der Messanhang "
        "erfasst sie CPC-nativ). Die Venture-Schicht (420.564 Startup-Events) "
        "trägt keinen Text; ihre Brücke zum Thema kostet ~350 s und liegt "
        "außerhalb des Abfragebudgets eines Dossier-Laufs.*"
        if de else
        "*Counting limits: the research series only becomes reliable from 2010 "
        "(corpus edge) and the market series only from the start of our own RSS "
        "collection — a rise at the left edge measures coverage, not the world. "
        "Patents are not counted again here (the measurement appendix covers them "
        "CPC-natively). The venture layer (420,564 startup events) carries no text; "
        "its bridge to a topic costs ~350 s, outside a dossier run's query budget.*")
    return {"sources": sources, "note": note, "appendix": "\n".join(L) + "\n",
            "summary": {"market_n": m.get("n"), "market_published": m.get("published"),
                        "science_n": s.get("n"),
                        "science_citations": s.get("citations"),
                        "top_funder": (s.get("funders") or [(None, None)])[0][0],
                        # Zeitfenster je Zaehlung — die Verwendbarkeitsregel
                        # (pipeline/dossier_structure.py) laesst eine Zahl nur
                        # in den Fliesstext, wenn n UND Zeitraum bekannt sind.
                        "market_window": ([m["first"], m["last"]]
                                          if m.get("first") and m.get("last") else None),
                        "science_window": (
                            [min(s["years"]), max(s["years"])]
                            if s.get("years") else None),
                        "measured_on": stats.get("measured_on"),
                        "tsquery": tsq}}


def build_corpus_evidence(topic: str, lang: str = "en") -> dict:
    """Zählung + Formatierung. Gibt IMMER ein Dict zurück; jeder Fehler wird
    zum Fehlgrund, nie zum Absturz."""
    try:
        stats = measure_corpus(topic)
    except Exception as exc:                                        # noqa: BLE001
        logger.warning("corpus tally failed for %r: %r", topic, exc)
        return {"ok": False, "reason": f"corpus tally failed: {exc}",
                "sources": [], "note": None, "appendix": None, "summary": None}
    if not stats.get("ok"):
        return {"ok": False, "reason": stats.get("reason") or "no corpus tally",
                "sources": [], "note": None, "appendix": None, "summary": None}
    out = format_corpus_stats(stats, topic, lang)
    logger.info("corpus tally: market n=%s, research n=%s (%.0fs)",
                (stats.get("market") or {}).get("n"),
                (stats.get("science") or {}).get("n"), stats.get("seconds") or 0)
    return {"ok": True, "reason": None, **out}
