#!/usr/bin/env python3
"""Parse the CPC scheme + definitions into a `cpc_definitions` table (issue #28).

The CPC (Cooperative Patent Classification) is the most mature, expert-curated
technology taxonomy in existence. Its definition XML carries a rich SEMANTIC
description per subclass ("This place covers: … Examples: …") plus cross-
references — exactly what lets us project the non-patent tiers (science, market,
funding, which carry no CPC) onto CPC via embedding similarity, giving all four
lead-time tiers a common technology backbone.

This builds the table (GPU-free); scripts/embed_cpc.py then embeds the text.

Input: pdf/cpc/**/CPC Definitionen XML/**/cpc-definition-*.xml (653 subclasses).

    python scripts/parse_cpc.py
"""
from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.db import USE_POSTGRES, get_connection

CPC_ROOT = Path(__file__).parent.parent / "pdf" / "cpc"
_WS = re.compile(r"\s+")


def _text_of(el) -> str:
    """All descendant text of an element, whitespace-collapsed."""
    return _WS.sub(" ", "".join(el.itertext())).strip()


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_definition(path: Path) -> dict | None:
    symbol = path.stem.replace("cpc-definition-", "")  # A23C
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError:
        return None
    title, body, refs = "", [], []
    for el in root.iter():
        lt = _local(el.tag)
        if lt == "definition-title" and not title:
            title = _text_of(el)
        elif lt == "paragraph-text":
            t = _text_of(el)
            if t:
                body.append(t)
        elif lt == "class-ref":
            sym = _text_of(el)
            if sym:
                refs.append(sym)
    # definition text = title + the covered/examples body (dedup cross-ref echoes)
    definition = title + ". " + " ".join(dict.fromkeys(body))
    return {"symbol": symbol, "title": title.split("(")[0].strip(),
            "definition": definition[:8000],
            "cross_refs": ",".join(sorted(set(refs))[:40])}


def migrate():
    with get_connection() as conn:
        vec = "vector(4096)" if USE_POSTGRES else "BLOB"
        vec1 = "vector(1024)" if USE_POSTGRES else "BLOB"
        conn.execute(
            f"CREATE TABLE IF NOT EXISTS cpc_definitions ("
            f" symbol TEXT PRIMARY KEY, title TEXT, definition TEXT, cross_refs TEXT,"
            f" vertical TEXT, embedding {vec}, embedding_1024 {vec1})")


def main() -> int:
    from scripts.ingest_patents import vertical_for_cpc
    files = sorted(CPC_ROOT.rglob("cpc-definition-*.xml"))
    print(f"CPC definition XMLs: {len(files)}")
    if not files:
        print("none found under pdf/cpc — check the path"); return 1
    migrate()
    rows = []
    for f in files:
        rec = parse_definition(f)
        if not rec or not rec["definition"].strip():
            continue
        # deterministic vertical from the subclass symbol (same map as the ingest)
        rec["vertical"] = vertical_for_cpc([{"code": rec["symbol"], "inventive": True}])
        rows.append((rec["symbol"], rec["title"], rec["definition"],
                     rec["cross_refs"], rec["vertical"]))
    with get_connection() as conn:
        if USE_POSTGRES:
            import psycopg2.extras
            cur = conn._conn.cursor()
            psycopg2.extras.execute_values(
                cur,
                "INSERT INTO cpc_definitions (symbol, title, definition, cross_refs, vertical) "
                "VALUES %s ON CONFLICT (symbol) DO UPDATE SET title=EXCLUDED.title, "
                "definition=EXCLUDED.definition, cross_refs=EXCLUDED.cross_refs, "
                "vertical=EXCLUDED.vertical",
                rows, page_size=1000)
        else:
            conn.executemany(
                "INSERT OR REPLACE INTO cpc_definitions (symbol, title, definition, cross_refs, vertical) "
                "VALUES (?, ?, ?, ?, ?)", rows)
    from collections import Counter
    vc = Counter(r[4] for r in rows)
    print(f"inserted {len(rows)} CPC subclasses. Vertical routing: {dict(vc.most_common())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
