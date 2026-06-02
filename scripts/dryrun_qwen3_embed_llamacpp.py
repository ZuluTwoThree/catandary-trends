#!/usr/bin/env python3
"""Dry-run: compare Stage-5 embedding output Ollama qwen3-embedding vs
llama.cpp Qwen3-Embedding-8B-Q4_K_M.

For N random recent raw_entries, embed each text twice (once via Ollama,
once via llama-server in embed-mode on :8090) and measure the cosine
similarity between the two vectors. Drop-in is safe only if the median
Ollama↔llama.cpp similarity is high — anything <0.98 means the 26k stored
Ollama embeddings would drift relative to fresh llama.cpp ones, biasing
the Stage-5 dedup threshold (0.92) and the Foresight Hybrid Search.

Also: pick the 20 highest-cosine pairs among the N samples in each backend
and check that the same pairs land on the same side of the 0.92 threshold.

Validation thresholds (Goal Contract candidate):
  Median Ollama↔llama.cpp similarity   : ≥0.98
  P5 Ollama↔llama.cpp similarity       : ≥0.95
  Dimension                            : exactly 4096 (hard gate)
  Cross-backend dup-detection agreement: ≥90% on top-20 pairs at 0.92

Prerequisite: llama-server must serve the embedding model on port 8090.
Run: `ln -sfn start-qwen3-emb.sh ~/llama.cpp/start-active.sh`
     `systemctl --user restart llama-server.service`
then `python -m scripts.dryrun_qwen3_embed_llamacpp [N]`
"""

import argparse
import os
import statistics
import sys
import time
from math import sqrt
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
from pipeline.db import get_connection
from pipeline.ollama_client import generate_embedding as ollama_embed

OLLAMA_MODEL = "qwen3-embedding"
LLAMACPP_HOST = os.getenv("LLAMACPP_HOST", "http://127.0.0.1:8090")
LLAMACPP_EMBED_URL = f"{LLAMACPP_HOST}/v1/embeddings"


def llamacpp_embed(text: str) -> tuple[list[float] | None, float]:
    """Return (embedding, elapsed_seconds). embedding is None on failure."""
    t0 = time.time()
    try:
        r = httpx.post(LLAMACPP_EMBED_URL, json={"input": text}, timeout=120)
        r.raise_for_status()
        data = r.json()
        return data["data"][0]["embedding"], time.time() - t0
    except Exception as e:
        print(f"  !! llama.cpp embed error: {e}", file=sys.stderr)
        return None, time.time() - t0


def ollama_embed_timed(text: str) -> tuple[list[float] | None, float]:
    t0 = time.time()
    v = ollama_embed(OLLAMA_MODEL, text)
    return v, time.time() - t0


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sqrt(sum(x * x for x in a))
    nb = sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _p(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = int(round(q * (len(s) - 1)))
    return s[idx]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("n", nargs="?", type=int, default=100)
    args = ap.parse_args()

    with get_connection() as conn:
        conn.row_factory = __import__("sqlite3").Row
        rows = conn.execute(
            "SELECT id, title, excerpt FROM raw_entries "
            "WHERE excerpt IS NOT NULL AND length(excerpt) > 200 "
            "ORDER BY RANDOM() LIMIT ?",
            (args.n,),
        ).fetchall()

    print(f"Sample size       : {len(rows)} raw_entries (random)")
    print(f"Ollama model      : {OLLAMA_MODEL}")
    print(f"llama.cpp endpoint: {LLAMACPP_EMBED_URL}")
    print("=" * 80)

    ollama_vecs: dict[int, list[float]] = {}
    llama_vecs: dict[int, list[float]] = {}
    ollama_dts: list[float] = []
    llama_dts: list[float] = []
    cross_sims: list[float] = []
    dims_seen: set[int] = set()
    failed = 0

    for i, row in enumerate(rows, 1):
        text = f"{row['title'] or ''}\n{(row['excerpt'] or '')[:500]}"

        ov, odt = ollama_embed_timed(text)
        lv, ldt = llamacpp_embed(text)
        ollama_dts.append(odt)
        llama_dts.append(ldt)

        if ov is None or lv is None:
            failed += 1
            continue

        dims_seen.add(len(ov))
        dims_seen.add(len(lv))

        sim = cosine(ov, lv)
        cross_sims.append(sim)
        ollama_vecs[row["id"]] = ov
        llama_vecs[row["id"]] = lv

        if i % 20 == 0 or i == 1:
            print(f"[{i}/{len(rows)}] #{row['id']} sim={sim:.4f}")

    # ---- summary ---------------------------------------------------------
    print()
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"\nDimension(s) seen      : {sorted(dims_seen)}  "
          f"(target: {{4096}}) {'✓' if dims_seen == {4096} else '✗'}")
    print(f"Failed pairs           : {failed}/{len(rows)}")

    if cross_sims:
        med = statistics.median(cross_sims)
        p5 = _p(cross_sims, 0.05)
        p95 = _p(cross_sims, 0.95)
        mn = min(cross_sims)
        print(f"\nOllama ↔ llama.cpp cosine similarity per entry:")
        print(f"  median  : {med:.4f}  [target ≥0.98] {'✓' if med >= 0.98 else '✗'}")
        print(f"  P5      : {p5:.4f}  [target ≥0.95] {'✓' if p5 >= 0.95 else '✗'}")
        print(f"  P95     : {p95:.4f}")
        print(f"  min     : {mn:.4f}")

    if ollama_dts:
        omed = statistics.median(ollama_dts)
        lmed = statistics.median(llama_dts)
        print(f"\nLatency per call:")
        print(f"  Ollama   p50/p95 : {omed:.3f}s / {_p(ollama_dts, 0.95):.3f}s")
        print(f"  llama.cpp p50/p95: {lmed:.3f}s / {_p(llama_dts, 0.95):.3f}s")
        ratio = lmed / omed if omed > 0 else 0
        marker = "✓" if ratio <= 1.5 else "✗"
        print(f"  median ratio llama/Ollama: {ratio:.2f}x  [target ≤1.5x] {marker}")

    # ---- cross-backend duplicate detection consistency -------------------
    # Find top-20 high-similarity pairs in Ollama space, then check whether
    # those same pairs cross the 0.92 threshold in llama.cpp space.
    ids = list(ollama_vecs.keys())
    pair_sims_ollama: list[tuple[float, int, int]] = []
    pair_sims_llama: list[tuple[float, int, int]] = []
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            a, b = ids[i], ids[j]
            so = cosine(ollama_vecs[a], ollama_vecs[b])
            sl = cosine(llama_vecs[a], llama_vecs[b])
            pair_sims_ollama.append((so, a, b))
            pair_sims_llama.append((sl, a, b))

    if pair_sims_ollama:
        # Top-20 by Ollama
        top20_o = sorted(pair_sims_ollama, key=lambda t: -t[0])[:20]
        agree = 0
        for so, a, b in top20_o:
            sl = cosine(llama_vecs[a], llama_vecs[b])
            # both above OR both below 0.92 = agreement
            if (so > 0.92) == (sl > 0.92):
                agree += 1
        print(f"\nDup-detection consistency (top-20 pairs by Ollama-sim):")
        print(f"  same side of 0.92 threshold: {agree}/20  [target ≥18] "
              f"{'✓' if agree >= 18 else '✗'}")

        # Show top-5 pairs with biggest disagreement
        diffs = sorted(
            [(abs(so - cosine(llama_vecs[a], llama_vecs[b])), so,
              cosine(llama_vecs[a], llama_vecs[b]), a, b)
             for so, a, b in top20_o],
            key=lambda t: -t[0],
        )[:5]
        if diffs:
            print(f"\nTop-5 largest backend disagreements (in top-20 pairs):")
            for d, so, sl, a, b in diffs:
                print(f"  |Δ|={d:.3f}  ollama={so:.3f} llama={sl:.3f}  "
                      f"entries #{a} ↔ #{b}")


if __name__ == "__main__":
    main()
