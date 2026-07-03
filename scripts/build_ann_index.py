#!/usr/bin/env python3
"""Add a 1024-dim truncated (Matryoshka-prefix) vector column + HNSW index.

pgvector 0.6 caps HNSW/ivfflat at 2000 dims, so the 4096-dim column cannot be
ANN-indexed. Qwen3-Embedding is MRL-trained → the 1024-prefix is the intended
truncation for cheap search; the full 4096 column stays for exact re-ranking.
Reads the float32 blobs from SQLite (cheaper than parsing pgvector text) and
updates PG by id.
"""
import sqlite3
import struct
import sys
import time

import psycopg2
from psycopg2.extras import execute_values

DIM = 1024
sq = sqlite3.connect("file:/home/dirk/projects/catandary-trends/data/catandary.db?mode=ro", uri=True)
pg = psycopg2.connect("postgresql:///catandary")
pg.autocommit = False
cur = pg.cursor()

cur.execute(f"ALTER TABLE trends ADD COLUMN IF NOT EXISTS embedding_1024 vector({DIM})")
pg.commit()

t0 = time.time()
buf, done = [], 0
for tid, blob in sq.execute("SELECT id, embedding FROM trends WHERE embedding IS NOT NULL"):
    if blob is None or len(blob) < DIM * 4:
        continue
    vec = struct.unpack(f"<{DIM}f", blob[: DIM * 4])
    buf.append((tid, "[" + ",".join(repr(float(x)) for x in vec) + "]"))
    if len(buf) >= 2000:
        execute_values(cur,
            "UPDATE trends t SET embedding_1024 = v.e::vector FROM (VALUES %s) AS v(id, e) WHERE t.id = v.id",
            buf)
        pg.commit()
        done += len(buf); buf.clear()
        if done % 50000 == 0:
            print(f"  {done} updated ({done/(time.time()-t0):.0f}/s)", flush=True)
if buf:
    execute_values(cur,
        "UPDATE trends t SET embedding_1024 = v.e::vector FROM (VALUES %s) AS v(id, e) WHERE t.id = v.id",
        buf)
    pg.commit()
    done += len(buf)
print(f"populated {done} in {time.time()-t0:.0f}s", flush=True)

print("building HNSW index (cosine) …", flush=True)
t1 = time.time()
cur.execute("SET maintenance_work_mem = '2GB'")
cur.execute("CREATE INDEX IF NOT EXISTS idx_trends_embedding_1024_hnsw ON trends "
            "USING hnsw (embedding_1024 vector_cosine_ops)")
pg.commit()
print(f"HNSW built in {time.time()-t1:.0f}s", flush=True)

# sanity: ANN query round-trip
cur.execute("SELECT id FROM trends WHERE embedding_1024 IS NOT NULL LIMIT 1")
ref = cur.fetchone()[0]
cur.execute("SELECT id, embedding_1024 <=> (SELECT embedding_1024 FROM trends WHERE id=%s) d "
            "FROM trends WHERE embedding_1024 IS NOT NULL ORDER BY d LIMIT 3", (ref,))
print("ANN sanity (ref", ref, "):", cur.fetchall(), flush=True)
pg.close(); sq.close()
sys.exit(0)
