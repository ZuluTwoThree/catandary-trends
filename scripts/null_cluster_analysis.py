"""Find clusters dominated by NULL mega-trend trends (potential new mega-trends)."""
import json
import sqlite3
import struct
from collections import Counter
from pathlib import Path

import numpy as np
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA

DB = Path("data/catandary.db")
K = 35

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
rows = conn.execute("""
    SELECT id, title_en, tags, primary_vertical, mega_trend, embedding
    FROM trends
    WHERE embedding IS NOT NULL AND status='published'
    ORDER BY id
""").fetchall()
conn.close()

trends = []
embs = []
for r in rows:
    n = len(r["embedding"]) // 4
    embs.append(np.array(struct.unpack(f"{n}f", r["embedding"]), dtype=np.float32))
    tags = json.loads(r["tags"]) if r["tags"] else []
    trends.append({"id": r["id"], "title": r["title_en"], "tags": tags,
                   "v": r["primary_vertical"], "mt": r["mega_trend"]})

X = np.vstack(embs)
X = X / (np.linalg.norm(X, axis=1, keepdims=True) + 1e-9)
Xp = PCA(n_components=50, random_state=42).fit_transform(X)
labels = KMeans(n_clusters=K, random_state=42, n_init=10).fit_predict(Xp)

total_null = sum(1 for t in trends if not t["mt"])
print(f"Total: {len(trends)} trends, {total_null} NULL mega_trend\n")

clusters = {}
for lab, t in zip(labels, trends):
    clusters.setdefault(int(lab), []).append(t)

rankings = []
for cid, members in clusters.items():
    nulls = [m for m in members if not m["mt"]]
    null_frac = len(nulls) / len(members)
    rankings.append((cid, len(members), len(nulls), null_frac, members, nulls))

# Rank by absolute null count AND fraction
rankings.sort(key=lambda x: (-x[2], -x[3]))

print("=" * 80)
print("TOP 10 CLUSTERS BY NULL-MEGA-TREND CONCENTRATION")
print("=" * 80)
for cid, size, n_null, frac, members, nulls in rankings[:10]:
    mts = Counter(m["mt"] for m in members if m["mt"])
    verts = Counter(m["v"] for m in members)
    tags = Counter(tag for m in members for tag in m["tags"])
    print(f"\n--- Cluster {cid}: {size} trends, {n_null} NULL ({frac:.0%}) ---")
    print(f"  Verticals: {dict(verts.most_common(3))}")
    print(f"  Top tags: {[t for t,_ in tags.most_common(8)]}")
    print(f"  Existing MTs: {dict(mts.most_common(3)) or 'none'}")
    print(f"  Sample NULL titles:")
    for m in nulls[:6]:
        print(f"    - [{m['v']}] {m['title'][:90]}")
