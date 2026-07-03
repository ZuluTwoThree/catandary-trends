#!/usr/bin/env python3
"""Technology Improvement Rate (TIR) metrics on patent clusters.

Grounded in the patent-foresight methodology (Benson & Magee 2015; Triulzi et al.
2020 — see memory `tir-patent-metrics-methodology`): a technology domain's
improvement rate k is predicted by patent citation signals. We provide the
*domains* bottom-up (embedding clusters of patent signals) and compute, per
cluster, the validated patent metrics from the citation graph (`patent_links`):

  - Immediate Importance  = avg forward citations within 3 years of publication
                            (Benson-Magee's strongest single metric, r≈0.76)
  - Forward-citation rate  = avg total within-corpus forward citations / patent
  - Recency                = avg publication year (newer ⇒ faster-moving)
  - Cycle Time             = median(citing_year − cited_year) over backward cites
                            (shorter ⇒ faster TIR; best-effort, cited year parsed)
  - Hub patent             = the cluster's most forward-cited (foundational) patent

Domain scoping: --vertical (primary_vertical) or --cpc PREFIX (via patent_cpc,
e.g. A23C = dairy) — the latter defines the domain the way the TIR literature
does (a CPC technology area), with the embedding clusters as its semantic
sub-themes.

Ranking: by Immediate Importance (the r≈0.76 metric) when forward citations are
live; otherwise by Cycle Time (backward-only, computable on any graph) with the
forward metrics honestly marked data-gated. Forward metrics need OUR patents to
be cited by other in-corpus patents → near-empty until the broad DOCDB back-file
(#8/#14) makes the graph dense in both directions. SPNP network centrality
(Triulzi, ~64% variance) is a TODO once the graph is broad. Absolute k% needs the
calibrated regression + performance data.

    python scripts/tir_metrics.py --vertical TECH
    python scripts/tir_metrics.py --cpc A23C --k 3        # dairy sub-domains
    python scripts/tir_metrics.py --vertical HEALTH --examiner-only
"""
from __future__ import annotations

import argparse
import re
import sys
import statistics as stats
from collections import defaultdict
from pathlib import Path

import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

sys.path.insert(0, str(Path(__file__).parent.parent))
from pipeline import db as db_mod
from pipeline.db import get_connection
from pipeline.llm_processor import bytes_to_embedding

_YEAR_RE = re.compile(r"(19|20)\d{2}")


def year_of(pub_number: str, corpus_year: dict[str, int]) -> int | None:
    """Publication year — prefer the corpus date, else parse a year embedded in the
    publication number (US/WO application-style numbers carry it; many grants don't)."""
    if pub_number in corpus_year:
        return corpus_year[pub_number]
    # e.g. US-2026165336-A1 / WO2026125170-A1 → the number segment starts with a year
    m = _YEAR_RE.search(pub_number.replace("-", ""))
    if m:
        y = int(m.group(0))
        if 1900 <= y <= 2030:
            return y
    return None


def load_patents(vertical: str, limit: int, cpc: str = "") -> list[dict]:
    """Patent signals for a vertical: embedding + pub_number + year + tags/mega_trend.
    `cpc` scopes to a CPC prefix via patent_cpc (e.g. 'A23C' = dairy) — the
    domain is then CPC-defined and the clusters are its semantic sub-themes.
    Postgres-aware: embedding is a pgvector (cast + parse), published_date a
    timestamp (cast to text before substr), tags jsonb (already a list)."""
    emb_col = "t.embedding::text" if db_mod.USE_POSTGRES else "t.embedding"
    date_col = ("substr(re.published_date::text,1,4)" if db_mod.USE_POSTGRES
                else "substr(re.published_date,1,4)")
    sql = (f"SELECT t.id, re.pub_number AS pub_number, {emb_col} AS embedding, "
           f"       t.tags, t.mega_trend, {date_col} AS yr "
           "FROM trends t JOIN raw_entries re ON t.raw_entry_id = re.id "
           "WHERE t.status='signal' "
           "AND t.embedding IS NOT NULL AND re.pub_number IS NOT NULL")
    params: list = []
    if cpc:
        sql += (" AND EXISTS (SELECT 1 FROM patent_cpc pc "
                "WHERE pc.pub_number = re.pub_number AND pc.cpc LIKE ?)")
        params.append(cpc + "%")
    else:
        sql += " AND t.primary_vertical = ?"
        params.append(vertical)
    if limit:
        sql += " LIMIT ?"
        params.append(limit)
    out = []
    with get_connection() as c:
        for r in c.execute(sql, params).fetchall():
            raw = db_mod._vector_to_bytes(r["embedding"])
            vec = bytes_to_embedding(raw) if isinstance(raw, (bytes, bytearray)) else None
            if vec is None:
                continue
            tags = r["tags"]
            if isinstance(tags, list):  # PG jsonb arrives parsed
                tags = ",".join(str(t) for t in tags)
            out.append({"pub": r["pub_number"], "vec": vec, "tags": tags or "",
                        "mega": r["mega_trend"], "year": int(r["yr"]) if r["yr"] else None})
    return out


def load_corpus_years() -> dict[str, int]:
    """pub_number -> publication year for EVERY patent raw entry (all verticals,
    incl. unprocessed back-file rows). Cited patents are mostly outside the
    analyzed vertical's signal set — resolving their year from the whole corpus
    (instead of parsing it out of the number, which fails for CN/EP formats)
    is what makes Cycle Time / Immediacy actually computable."""
    years: dict[str, int] = {}
    date_col = ("substr(published_date::text,1,4)" if db_mod.USE_POSTGRES
                else "substr(published_date,1,4)")
    with get_connection() as c:
        for r in c.execute(
                f"SELECT pub_number, {date_col} AS yr FROM raw_entries "
                "WHERE pub_number IS NOT NULL AND published_date IS NOT NULL").fetchall():
            pub = r["pub_number"] if isinstance(r, dict) else r[0]
            yr = r["yr"] if isinstance(r, dict) else r[1]
            try:
                y = int(yr)
            except (TypeError, ValueError):
                continue
            if 1900 <= y <= 2030:
                years[pub] = y
    return years


def load_forward_index(examiner_only: bool) -> dict[str, list[str]]:
    """dst_pub -> list of citing src_pub (forward citations, inverted graph).
    examiner_only drops applicant (APP) citations — a self-citation proxy."""
    fwd: dict[str, list[str]] = defaultdict(list)
    q = "SELECT src_pub, dst_pub FROM patent_links WHERE link_type='cites'"
    if examiner_only:
        q += " AND category='EXA'"
    with get_connection() as c:
        for r in c.execute(q).fetchall():
            # access by name: the PG wrapper yields dict rows — tuple-unpacking
            # them silently binds the COLUMN NAMES, collapsing the whole graph
            src, dst = (r["src_pub"], r["dst_pub"]) if isinstance(r, dict) else (r[0], r[1])
            fwd[dst].append(src)
    return fwd


def backward_index() -> dict[str, list[str]]:
    """src_pub -> list of cited dst_pub (backward citations, for Cycle Time)."""
    bwd: dict[str, list[str]] = defaultdict(list)
    with get_connection() as c:
        for r in c.execute("SELECT src_pub, dst_pub FROM patent_links WHERE link_type='cites'").fetchall():
            src, dst = (r["src_pub"], r["dst_pub"]) if isinstance(r, dict) else (r[0], r[1])
            bwd[src].append(dst)
    return bwd


def pick_k(X: np.ndarray, lo=6, hi=12) -> int:
    n = len(X)
    if n < lo * 8:
        return max(2, min(lo, n // 8 or 2))
    best_k, best_s = lo, -1.0
    sample = X if n <= 4000 else X[np.random.RandomState(42).choice(n, 4000, replace=False)]
    for k in range(lo, min(hi, n // 4) + 1):
        labels = KMeans(n_clusters=k, n_init=4, random_state=42).fit_predict(sample)
        s = silhouette_score(sample, labels, sample_size=min(1500, len(sample)), random_state=42)
        if s > best_s:
            best_k, best_s = k, s
    return best_k


def top_tags(items: list[dict], n=5) -> list[str]:
    cnt: dict[str, int] = defaultdict(int)
    for it in items:
        for tag in (it["tags"] or "").replace('"', "").strip("[]").split(","):
            tag = tag.strip()
            if tag:
                cnt[tag] += 1
    return [t for t, _ in sorted(cnt.items(), key=lambda x: -x[1])[:n]]


def main() -> int:
    ap = argparse.ArgumentParser(description="TIR metrics on patent clusters")
    ap.add_argument("--vertical", default="TECH")
    ap.add_argument("--cpc", default="", help="scope by CPC prefix via patent_cpc (e.g. A23C) instead of vertical")
    ap.add_argument("--k", type=int, help="cluster count (default: silhouette)")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--examiner-only", action="store_true",
                    help="count only examiner (EXA) citations — drops applicant self-cites")
    args = ap.parse_args()

    items = load_patents(args.vertical, args.limit, cpc=args.cpc)
    scope = args.cpc or args.vertical
    print(f"{scope} patent signals with embedding+pub_number: {len(items)}")
    if len(items) < 50:
        print("too few patents for clustering (need >=50)"); return 1
    corpus_year = load_corpus_years()  # ALL patent entries, not just this vertical
    print(f"corpus year map: {len(corpus_year)} patents with known publication year")
    fwd = load_forward_index(args.examiner_only)
    bwd = backward_index()
    print(f"citation graph: {sum(len(v) for v in fwd.values())} forward edges"
          f"{' (examiner-only)' if args.examiner_only else ''}\n")

    X = np.asarray([it["vec"] for it in items], dtype=np.float32)
    X /= (np.linalg.norm(X, axis=1, keepdims=True) + 1e-9)
    k = args.k or pick_k(X)
    print(f"clustering into k={k} (spherical KMeans) ...\n")
    labels = KMeans(n_clusters=k, n_init=8, random_state=42).fit_predict(X)

    clusters = defaultdict(list)
    for it, lab in zip(items, labels):
        clusters[lab].append(it)

    rows = []
    for lab, members in clusters.items():
        years = [m["year"] for m in members if m["year"]]
        recency = stats.mean(years) if years else None
        imm_list, fwd_list, cyc_list = [], [], []
        hub = (None, -1)
        for m in members:
            my = m["year"]
            citers = fwd.get(m["pub"], [])
            fwd_list.append(len(citers))
            if len(citers) > hub[1]:
                hub = (m["pub"], len(citers))
            if my:
                imm = sum(1 for s in citers
                          if (sy := year_of(s, corpus_year)) and 0 <= sy - my <= 3)
                imm_list.append(imm)
            # Cycle Time: ages of this patent's backward citations (where cited year known)
            if my:
                for dst in bwd.get(m["pub"], []):
                    dy = year_of(dst, corpus_year)
                    if dy and 0 <= my - dy <= 60:
                        cyc_list.append(my - dy)
        rows.append({
            "lab": lab, "n": len(members),
            "imm": stats.mean(imm_list) if imm_list else 0.0,
            "fwd": stats.mean(fwd_list) if fwd_list else 0.0,
            "recency": recency,
            "cycle": stats.median(cyc_list) if cyc_list else None,
            "cyc_cov": len(cyc_list),
            "hub": hub[0], "hub_cites": hub[1],
            "mega": stats.mode([m["mega"] for m in members if m["mega"]] or ["—"]),
            "tags": top_tags(members),
        })

    # Forward metrics (Immediate Importance / Forward-Rate) need OUR patents to be
    # CITED by other in-corpus patents — near-empty until the broad DOCDB back-file
    # lands (#8). When forward coverage is negligible, ranking by Immediate
    # Importance is meaningless; fall back to the backward-only signal that IS
    # computable now — Cycle Time (shorter ⇒ faster TIR) among clusters with enough
    # coverage. This keeps the ranking honest and correct on the current graph.
    total_fwd = sum(r["fwd"] * r["n"] for r in rows)
    forward_live = total_fwd >= 1.0
    if forward_live:
        rows.sort(key=lambda r: -r["imm"])
        basis = "Immediate Importance (ø Forward-Zitate in 3 J, r≈0.76)"
    else:
        # shorter cycle time first; clusters without coverage sink to the bottom
        rows.sort(key=lambda r: (r["cycle"] if r["cyc_cov"] >= 20 else 1e9))
        basis = "Cycle Time (Forward-Metriken noch daten-gegated → siehe Hinweis)"

    print(f"Cluster-Ranking nach predicted-TIR — Basis: {basis}\n")
    for i, r in enumerate(rows, 1):
        cyc = f"{r['cycle']:.0f}J" if r["cycle"] is not None else "n/a"
        rec = f"{r['recency']:.0f}" if r["recency"] else "?"
        ii = f"{r['imm']:.2f}" if forward_live else "n/a*"
        fr = f"{r['fwd']:.2f}" if forward_live else "n/a*"
        print(f"━━ #{i}  Cluster {r['lab']}  ·  {r['n']} Patente  ·  mega={r['mega']}")
        print(f"   Cycle Time: {cyc} (cov {r['cyc_cov']})   | Recency: {rec}"
              f"   | Immediate Importance: {ii}   | Forward-Rate: {fr}")
        if forward_live:
            print(f"   Hub-Patent: {r['hub']} ({r['hub_cites']} Forward-Zitate)")
        print(f"   Tags: {', '.join(r['tags'])}\n")

    print("Lesart: kürzere Cycle Time + neuere Recency (+ höhere Immediate Importance,")
    print("        sobald verfügbar) ⇒ höhere Technology Improvement Rate.")
    if not forward_live:
        print("\n* Forward-Metriken (Immediate Importance / Forward-Rate) benötigen einen")
        print("  beidseitig dichten Zitationsgraphen — erst mit dem DOCDB-Back-File (#8/#14)")
        print("  aussagekräftig. Cycle Time ist backward-only und schon jetzt korrekt.")
    print("TODO: SPNP-Netzwerk-Zentralität (Triulzi, ~64% Varianz) — braucht breiteren Graphen (DOCDB).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
