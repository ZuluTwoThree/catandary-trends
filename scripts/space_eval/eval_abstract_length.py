#!/usr/bin/env python3
"""How much of a research abstract should be embedded — and does cleaning matter?

Issue #114 (Food pilot), owner 28.09.2026: before embedding ~140,000 Food
papers, compare three recipes on the SAME papers (Qwen3-Embedding-8B, the
pipeline's model; 1024-dim prefix, cosine — the space the cloud and the nests use):

  R0 raw500    today's recipe (scripts/signal_batch.py): title + first 500 chars, as stored
  R1 clean500  pipeline.text_clean.embed_text: boilerplate out, THEN 500 chars
  R2 cleanfull the same, whole abstract

Measured, per recipe:
  topic_purity@10     share of a paper's 10 nearest papers with the same OpenAlex topic
  subfield_purity@10  the same for the subfield (Food Science / Nutrition and Dietetics)
  retrieval P@20      each of the topics with >= 20 papers in the sample, its NAME as a
                      query (like the search box) -> share of the 20 nearest with that topic
  boilerplate lift    mean cosine of cross-topic pairs where BOTH raw abstracts are
                      structured (carry section labels) minus the same for pairs where
                      neither is — how much similarity the shared headings create
  agreement           mean cosine per paper between recipes, and neighbours@10 kept

Output data/space_eval/eval_abstract_length.json + a table. Needs an embedding
server (--host, default the CPU one on :8091; run_abstract_eval.sh starts one on the GPU).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

import httpx
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipeline import db  # noqa: E402
from pipeline.text_clean import embed_text  # noqa: E402

OUT = ROOT / "data" / "space_eval"
K = 10
DIM = 1024
LABELED = re.compile(r"\b(background|methods?|results?|conclusions?|objectives?)\s*:", re.I)


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def sample(n: int) -> list[dict]:
    with db.get_connection() as c:
        c.execute("SET statement_timeout = '900s'")
        return [dict(r) for r in c.execute(f"""
            WITH ft AS (SELECT DISTINCT ON (topic) topic, subfield FROM openalex_topics
                        WHERE subfield IN ('Food Science','Nutrition and Dietetics') ORDER BY topic)
            SELECT rc.id, rc.title, rc.abstract, rc.topic, ft.subfield
            FROM research_corpus rc JOIN ft ON ft.topic = rc.topic
            WHERE rc.published >= '2023-10-01' AND length(coalesce(rc.abstract, '')) > 200
              AND NOT (extract(month from rc.published) = 1 AND extract(day from rc.published) = 1)
            ORDER BY mod(hashtext(rc.id)::bigint * 2654435761, 4294967296) LIMIT {int(n)}""").fetchall()]


def embed(texts: list[str], host: str, batch: int) -> tuple[np.ndarray, float]:
    out = np.zeros((len(texts), DIM), np.float32)
    t0 = time.time()
    with httpx.Client(timeout=600) as cl:
        for s in range(0, len(texts), batch):
            r = cl.post(f"{host}/v1/embeddings", json={"input": texts[s:s + batch]})
            r.raise_for_status()
            for j, d in enumerate(r.json()["data"]):
                v = np.asarray(d["embedding"][:DIM], np.float32)
                out[s + j] = v / max(float(np.linalg.norm(v)), 1e-9)
            if (s // batch) % 20 == 0:
                log(f"  {min(s + batch, len(texts)):,}/{len(texts):,}")
    return out, time.time() - t0


def knn(V: np.ndarray, k: int) -> np.ndarray:
    S = V @ V.T
    np.fill_diagonal(S, -np.inf)
    return np.argsort(-S, axis=1)[:, :k]


def purity(nb: np.ndarray, lab: list) -> float:
    L = np.asarray(lab, dtype=object)
    return float(np.mean(L[nb] == L[:, None]))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--n", type=int, default=2000)
    ap.add_argument("--host", default="http://127.0.0.1:8091")
    ap.add_argument("--batch", type=int, default=32)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    rows = sample(args.n)
    log(f"sample: {len(rows):,} Food Science / Nutrition papers")
    topics = [r["topic"] for r in rows]
    subf = [r["subfield"] for r in rows]
    structured = np.array([bool(LABELED.search(r["abstract"] or "")) for r in rows])
    recipes = {
        "R0_raw500": [f"{r['title']}\n{(r['abstract'] or '')[:500]}" for r in rows],
        "R1_clean500": [embed_text(r["title"], r["abstract"], 500) for r in rows],
        "R2_cleanfull": [embed_text(r["title"], r["abstract"], None) for r in rows],
    }
    # queries: topic names with >= 20 papers in the sample
    tc: dict[str, int] = {}
    for t in topics:
        tc[t] = tc.get(t, 0) + 1
    qtopics = sorted(t for t, c in tc.items() if c >= 20)
    Q, _ = embed(qtopics, args.host, args.batch)
    log(f"{len(qtopics)} topic-name queries embedded")

    report: dict = {"n": len(rows), "structured_share": round(float(structured.mean()), 3),
                    "queries": len(qtopics), "host": args.host, "recipes": {}}
    vecs = {}
    for name, texts in recipes.items():
        chars = [len(t) for t in texts]
        log(f"{name}: embedding {len(texts):,} texts (median {int(np.median(chars))} chars)")
        V, secs = embed(texts, args.host, args.batch)
        vecs[name] = V
        nb = knn(V, K)
        S = V @ Q.T                                       # papers x queries
        p20 = []
        for j, t in enumerate(qtopics):
            top = np.argsort(-S[:, j])[:20]
            p20.append(float(np.mean([topics[i] == t for i in top])))
        # boilerplate lift: cross-topic pairs, both structured vs neither
        rng = np.random.default_rng(42)
        a, b = rng.integers(0, len(rows), 200000), rng.integers(0, len(rows), 200000)
        cross = np.array([topics[i] != topics[j] for i, j in zip(a, b)]) & (a != b)
        cos = np.sum(V[a] * V[b], axis=1)
        both = cross & structured[a] & structured[b]
        neither = cross & ~structured[a] & ~structured[b]
        report["recipes"][name] = {
            "median_chars": int(np.median(chars)), "embed_s": round(secs, 1),
            "texts_per_s": round(len(texts) / secs, 2),
            "topic_purity10": round(purity(nb, topics), 4),
            "subfield_purity10": round(purity(nb, subf), 4),
            "retrieval_p20": round(float(np.mean(p20)), 4),
            "cos_crosstopic_structured": round(float(cos[both].mean()), 4),
            "cos_crosstopic_plain": round(float(cos[neither].mean()), 4),
            "boilerplate_lift": round(float(cos[both].mean() - cos[neither].mean()), 4),
        }
        log(f"  {name}: {report['recipes'][name]}")
        (OUT / "eval_abstract_length.json").write_text(json.dumps(report, indent=2))
    base = vecs["R0_raw500"]
    nb0 = knn(base, K)
    for name in ("R1_clean500", "R2_cleanfull"):
        V = vecs[name]
        nbv = knn(V, K)
        report["recipes"][name]["cos_to_R0_mean"] = round(float(np.mean(np.sum(V * base, axis=1))), 4)
        report["recipes"][name]["neighbours_shared_with_R0"] = round(
            float(np.mean([len(set(x) & set(y)) / K for x, y in zip(nb0, nbv)])), 4)
    (OUT / "eval_abstract_length.json").write_text(json.dumps(report, indent=2))

    print("\nrecipe          chars  texts/s  topic@10  subfld@10  P@20   lift(struct)  cos→R0  nb∩R0")
    for name, r in report["recipes"].items():
        print(f"{name:14s} {r['median_chars']:6d} {r['texts_per_s']:8.2f} {r['topic_purity10']:9.3f} "
              f"{r['subfield_purity10']:10.3f} {r['retrieval_p20']:6.3f} {r['boilerplate_lift']:+12.4f} "
              f"{r.get('cos_to_R0_mean', 1.0):7.3f} {r.get('neighbours_shared_with_R0', 1.0):6.3f}")
    log(f"structured abstracts in the sample: {report['structured_share']:.1%} -> {OUT / 'eval_abstract_length.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
