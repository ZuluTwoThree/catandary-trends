#!/usr/bin/env python3
"""Parse the CPC SCHEME XML into a fine-grained `cpc_fine` table (issue #42).

parse_cpc.py only ingests the 653 SUBCLASS definitions (4-char, e.g. A23C). This
walks the full CPC scheme (nested <classification-item>) and extracts EVERY fine
group/subgroup with its title and its hierarchy PATH — so a technology can be
resolved to the specific codes that describe it (A23C20/025 = plant-based cheese)
rather than a coarse subclass.

Additive: leaves cpc_definitions untouched; builds cpc_fine alongside it. The
title_path (parent titles joined) is what gets embedded (scripts/embed_cpc_fine.py)
so a free-text query lands on the right fine code with full context.

Input: pdf/cpc/**/CPC Schema XML/**/cpc-scheme-*.xml (692 subclass files).

    python scripts/parse_cpc_scheme.py            # build cpc_fine
    python scripts/parse_cpc_scheme.py --stats     # coverage vs patent_cpc
"""
from __future__ import annotations

import argparse
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.db import USE_POSTGRES, get_connection

CPC_ROOT = Path(__file__).parent.parent / "pdf" / "cpc"
_WS = re.compile(r"\s+")


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _title_text(item) -> str:
    """The classification-item's own title: join its <class-title>/<title-part>/
    <text> leaves, dropping nested reference/note cruft, whitespace-collapsed."""
    parts: list[str] = []
    for ct in item:
        if _local(ct.tag) != "class-title":
            continue
        for tp in ct:
            if _local(tp.tag) != "title-part":
                continue
            # take all text under the title-part EXCEPT <reference> cross-refs
            # ("preservation thereof …", "… takes precedence"). Handles both a
            # direct <text> and the <CPC-specific-text><text> wrapper.
            frags: list[str] = []
            for el in tp:
                if _local(el.tag) == "reference":
                    continue
                frags.append("".join(el.itertext()))
            t = _WS.sub(" ", " ".join(frags)).strip()
            if t:
                parts.append(t)
    return "; ".join(parts)


def _children_items(item):
    return [c for c in item if _local(c.tag) == "classification-item"]


def _symbol(item) -> str | None:
    for c in item:
        if _local(c.tag) == "classification-symbol":
            return (c.text or "").strip()
    return None


def walk(item, ancestor_titles: list[str], out: list[dict], parent: str | None):
    sym = _symbol(item)
    title = _title_text(item)
    if not sym:
        for ch in _children_items(item):
            walk(ch, ancestor_titles, out, parent)
        return
    path = ancestor_titles + ([title] if title else [])
    allocatable = item.get("not-allocatable", "false") != "true"
    out.append({
        "symbol": sym,
        "title": title,
        "title_path": " > ".join([p for p in path if p])[:1200],
        "level": int(item.get("level", 0) or 0),
        "parent": parent,
        "allocatable": 1 if allocatable else 0,
    })
    for ch in _children_items(item):
        walk(ch, path, out, sym)


def parse_file(path: Path) -> list[dict]:
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError:
        return []
    out: list[dict] = []
    # top-level may be the class-scheme with classification-item children
    items = ([root] if _local(root.tag) == "classification-item"
             else [c for c in root if _local(c.tag) == "classification-item"])
    for it in items:
        walk(it, [], out, None)
    return out


def migrate():
    with get_connection() as conn:
        vec1 = "vector(1024)" if USE_POSTGRES else "BLOB"
        conn.execute(
            "CREATE TABLE IF NOT EXISTS cpc_fine ("
            " symbol TEXT PRIMARY KEY, title TEXT, title_path TEXT, level INTEGER,"
            " parent TEXT, allocatable INTEGER DEFAULT 1, vertical TEXT,"
            f" n_patents INTEGER, embedding_1024 {vec1})")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cpc_fine_parent ON cpc_fine (parent)")


def build() -> int:
    from scripts.ingest_patents import vertical_for_cpc
    files = sorted(CPC_ROOT.rglob("cpc-scheme-*.xml"))
    print(f"CPC scheme XMLs: {len(files)}")
    if not files:
        print("none found under pdf/cpc — check the path")
        return 1
    migrate()
    seen: dict[str, dict] = {}
    for f in files:
        for rec in parse_file(f):
            # keep the first (deepest-context) occurrence; dedup by symbol
            if rec["symbol"] not in seen and rec["title"]:
                rec["vertical"] = vertical_for_cpc([{"code": rec["symbol"], "inventive": True}])
                seen[rec["symbol"]] = rec
    rows = list(seen.values())
    print(f"parsed {len(rows):,} fine CPC codes with titles")
    with get_connection() as conn:
        if USE_POSTGRES:
            import psycopg2.extras
            cur = conn._conn.cursor()
            psycopg2.extras.execute_values(
                cur,
                "INSERT INTO cpc_fine (symbol, title, title_path, level, parent,"
                " allocatable, vertical) VALUES %s ON CONFLICT (symbol) DO UPDATE SET"
                " title=EXCLUDED.title, title_path=EXCLUDED.title_path,"
                " level=EXCLUDED.level, parent=EXCLUDED.parent,"
                " allocatable=EXCLUDED.allocatable, vertical=EXCLUDED.vertical",
                [(r["symbol"], r["title"], r["title_path"], r["level"], r["parent"],
                  r["allocatable"], r["vertical"]) for r in rows], page_size=2000)
        else:
            conn.executemany(
                "INSERT OR REPLACE INTO cpc_fine (symbol, title, title_path, level,"
                " parent, allocatable, vertical) VALUES (?,?,?,?,?,?,?)",
                [(r["symbol"], r["title"], r["title_path"], r["level"], r["parent"],
                  r["allocatable"], r["vertical"]) for r in rows])
    # tag patent counts (which codes actually matter) — best-effort, PG only
    if USE_POSTGRES:
        with get_connection() as conn:
            print("counting patents per fine code (this scans patent_cpc) …", flush=True)
            conn.execute(
                "UPDATE cpc_fine f SET n_patents = c.n FROM ("
                "  SELECT cpc, COUNT(*) n FROM patent_cpc GROUP BY cpc) c "
                "WHERE c.cpc = f.symbol")
    print(f"cpc_fine built: {len(rows):,} codes")
    return 0


def stats():
    with get_connection() as conn:
        r = conn.execute(
            "SELECT COUNT(*) total, COUNT(*) FILTER (WHERE n_patents > 0) with_patents,"
            " COUNT(*) FILTER (WHERE n_patents >= 200) ge200,"
            " COUNT(*) FILTER (WHERE symbol LIKE '%/%') fine FROM cpc_fine").fetchone()
    d = dict(r)
    print(f"cpc_fine: {d['total']:,} codes | {d['fine']:,} fine (with '/') |"
          f" {d['with_patents']:,} with patents | {d['ge200']:,} with ≥200 patents")


def main() -> int:
    ap = argparse.ArgumentParser(description="Parse CPC scheme → cpc_fine (#42)")
    ap.add_argument("--stats", action="store_true")
    args = ap.parse_args()
    if args.stats:
        stats()
        return 0
    return build()


if __name__ == "__main__":
    raise SystemExit(main())
