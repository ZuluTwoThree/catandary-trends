#!/usr/bin/env python3
"""Firmen-Embeddings + Distill-Vertical-Klassifikation (#87 Phase 1, Plan §5.9).

Ein Vektor pro FIRMA (nicht pro Filing): embedded wird der beste verfügbare
Text je Firma — SBIR/CORDIS-Abstract vor Presse-Volltext vor Form-D-Zeile
(Owner-Reihenfolge 2026-08-21). Der 4096er-Vektor klassifiziert über die
vorhandenen Distill-Heads das Vertical (GPU-frei); persistiert wird der
Matryoshka-Präfix `embedding_1024` (ANN-Konvention wie trends.embedding_1024).

Resumabel (WHERE embedding_1024 IS NULL); GPU-Handover wie embed_filtered.

    python scripts/embed_startup_companies.py --limit 50   # Smoke
    python scripts/embed_startup_companies.py              # Volllauf (~145k)
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
from pipeline import gpu_handover, llamacpp_client
from pipeline.config import EMBED_MODEL, LOG_LEVEL
from pipeline.db import get_connection
from pipeline.distill import DistillClassifier

logging.basicConfig(level=LOG_LEVEL,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("embed_startup_companies")

_PREFIX_RE = re.compile(r"^\[[^\]]*\]\s*")

# Bester Text je Firma: Förderungs-Abstract > Presse > Form-D-Template.
FETCH_SQL = """
    select distinct on (c.id) c.id, c.name, r.excerpt, e.event_type as src_type
    from startup_companies c
    left join startup_events e on e.company_id = c.id and e.raw_entry_id is not null
    left join raw_entries r on r.id = e.raw_entry_id and r.excerpt is not null
    where c.embedding_1024 is null
    order by c.id,
        case e.event_type
            when 'sbir_award' then 0 when 'grant' then 0
            when 'press_round' then 1 else 2 end,
        e.event_date desc
"""


def load_todo(limit: int) -> list[dict]:
    sql = FETCH_SQL + (" limit ?" if limit else "")
    with get_connection() as c:
        return [dict(r) for r in c.execute(sql, (limit,) if limit else ()).fetchall()]


def company_text(row: dict) -> str:
    body = _PREFIX_RE.sub("", row.get("excerpt") or "").strip()
    return f"{row['name']}\n{body[:600]}" if body else row["name"]


def main() -> int:
    ap = argparse.ArgumentParser(description="Firmen-Embeddings (#87 Phase 1)")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--commit-every", type=int, default=500)
    args = ap.parse_args()

    todo = load_todo(args.limit)
    logger.info("Firmen ohne Embedding: %d", len(todo))
    if not todo:
        return 0
    clf = DistillClassifier.load()

    t0 = time.time()
    done = errors = 0
    buf: list[tuple] = []  # (vec4096, company_id)

    def flush():
        nonlocal buf
        if not buf:
            return
        X = np.asarray([v for v, _, _ in buf], dtype=np.float32)
        preds = clf.classify_batch(X)
        emb_rows, vert_rows = [], []
        for (v, cid, real), p in zip(buf, preds):
            emb_rows.append(("[" + ",".join(f"{float(x):.7g}" for x in v[:1024]) + "]", cid))
            if real and p.get("primary_vertical"):
                vert_rows.append((json.dumps([p["primary_vertical"]]), cid))
        with get_connection() as c:
            c.executemany(
                "UPDATE startup_companies SET embedding_1024 = ? WHERE id = ?", emb_rows)
            if vert_rows:
                c.executemany(
                    "UPDATE startup_companies SET verticals = ? WHERE id = ?", vert_rows)
        buf = []

    # Distill-Vertical nur bei echtem Text — Form-D-Template wuerde alles
    # nach BIZ ziehen; dort bleibt das SEC-Industrie-Mapping aus dem Build.
    REAL_TEXT_TYPES = {"sbir_award", "grant", "press_round"}

    def work(row: dict):
        real = row.get("src_type") in REAL_TEXT_TYPES and bool(row.get("excerpt"))
        return row["id"], llamacpp_client.generate_embedding(
            company_text(row), model=EMBED_MODEL), real

    with gpu_handover.embed_on_llamacpp(EMBED_MODEL):
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            for cid, emb, real in ex.map(work, todo):
                done += 1
                if emb is None:
                    errors += 1
                else:
                    buf.append((emb, cid, real))
                if len(buf) >= args.commit_every:
                    flush()
                if done % 5000 == 0:
                    rate = done / (time.time() - t0)
                    eta = (len(todo) - done) / rate / 60 if rate else 0
                    logger.info("%d/%d (%.0f/s, %d errors, ETA %.0f min)",
                                done, len(todo), rate, errors, eta)
        flush()

    logger.info("Done in %.0fs: %d embedded+klassifiziert, %d errors (von %d)",
                time.time() - t0, done - errors, errors, len(todo))
    return 0 if errors < len(todo) * 0.05 else 1


if __name__ == "__main__":
    raise SystemExit(main())
