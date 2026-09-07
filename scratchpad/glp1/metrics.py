"""Dieselben Zaehler ueber alle GLP-1-Laeufe — DR-Modus gegen die Runden davor.

Alles deterministisch aus dem gespeicherten Lauf: Faktenquote wie in
pipeline.dossier_structure, Rangmischung der tatsaechlich zitierten Quellen,
Lese- und Katalogzahlen. Kein Modell, keine Schaetzung.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipeline import dossier_structure as ds
from pipeline.db import get_connection
from scripts.corpus_research import source_rank


def rows():
    with get_connection() as conn:
        cur = conn.execute(
            "select id, slug, version, report_md, result, created_at "
            "from dossiers where slug ~ '^glp1-' order by id")
        for r in cur.fetchall():
            yield dict(r)


def metrics(row):
    res = row["result"]
    if isinstance(res, str):
        res = json.loads(res)
    sources = res.get("sources") or []
    by_id = {s["id"]: s for s in sources}
    for s in sources:
        if s.get("rank") is None:
            url = s.get("origin") or s.get("url") or ""
            s["rank"] = source_rank(url) if url else 2
    cited_ids = res.get("cited") or []
    cited = [by_id[c] for c in cited_ids if c in by_id]
    dens = ds.fact_density(row["report_md"], sources, "en", rank_of=source_rank)
    body = ds.body_text(row["report_md"])
    prim = [c for c in cited if int(c.get("rank", 2)) <= 1]
    read = sum(1 for s in sources if s.get("fetched"))
    return {
        "id": row["id"], "slug": row["slug"], "v": row["version"],
        "dr": bool(res.get("dr")),
        "sec": int(res.get("seconds") or 0),
        "words": dens["words"],
        "dated": dens["dated_claims"],
        "primary": dens["primary_claims"],
        "per100": dens["per100"],
        "cited": len(cited),
        "cited_primary": len(prim),
        "primary_hosts": len({(c.get("host") or c.get("outlet") or "")
                              for c in prim}),
        "sources": len(sources),
        "catalog_primary": sum(1 for s in sources if int(s.get("rank", 2)) <= 1),
        "read": read,
        "ledger": len(res.get("fact_ledger") or []),
        "rewritten": bool((res.get("structure") or {}).get("rewritten")),
        "calendar_rows": body.count("\n|") if "| Date " in body else 0,
    }


def main():
    out = [metrics(r) for r in rows()]
    cols = ["id", "slug", "v", "dr", "sec", "words", "dated", "primary",
            "per100", "cited", "cited_primary", "primary_hosts",
            "catalog_primary", "sources", "read", "ledger", "rewritten"]
    print(" | ".join(c.ljust(9) for c in cols))
    for m in out:
        print(" | ".join(str(m[c]).ljust(9) for c in cols))
    Path(__file__).with_name("metrics.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
