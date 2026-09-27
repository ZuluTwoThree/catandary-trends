"""Pilot C (2026-09-27): assign a CONTROLLED vocabulary to signals — measured.

Question from the owner: can signals get meaningful keywords cheaply? Route C:
take candidate labels from the embedding space we already have, let a small
reranker (Qwen3-Reranker-0.6B) read the TEXT and decide. Measured against
ground truth we already hold:

  * patents  -> CPC subclasses assigned by patent examiners (patent_cpc),
                independent of any model — the clean yardstick;
  * research -> the OpenAlex primary topic (research_corpus.topic via DOI),
                itself model-assigned by OpenAlex from title/abstract/citations,
                so agreement there is "agrees with OpenAlex", not "is right".

Reported per set: candidate recall@k (is a true label among the k embedding
candidates at all?), P@1 and P@3 of the embedding order, the same after
reranking, and a precision/recall table for "assign every candidate whose
reranker score clears t". Nothing is written to the database.

    python scripts/tag_eval/pilot_vocab_rerank.py --rerank-host http://127.0.0.1:8093 \
        --embed-host http://127.0.0.1:8095 [--n 1000] [--k 20]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pipeline import db  # noqa: E402

OUT = Path(__file__).resolve().parents[2] / "data" / "tag_eval"
QUERY_CHARS = 900


def rows(sql: str, params=()) -> list[dict]:
    with db.get_connection() as c:
        c.execute("SET statement_timeout = '300s'")
        return [dict(r) for r in c.execute(sql, params).fetchall()]


def vec(text) -> np.ndarray:
    v = np.frombuffer(db._vector_to_bytes(text), dtype=np.float32)
    return v / max(np.linalg.norm(v), 1e-9)


def unit(M: np.ndarray) -> np.ndarray:
    return M / np.clip(np.linalg.norm(M, axis=1, keepdims=True), 1e-9, None)


# ------------------------------------------------------------------- samples

def patent_sample(n: int) -> tuple[list[dict], dict]:
    items = rows("""
        SELECT t.id, t.title_en AS title, r.excerpt,
               -- the publication number from the Google Patents URL: raw_entries.pub_number
               -- is not filled on every row (444 of 1,000 in the first dry run)
               split_part(split_part(r.url, '/patent/', 2), '/', 1) AS pub_number,
               t.embedding_1024::text AS emb
        FROM trends t JOIN raw_entries r ON r.id = t.raw_entry_id JOIN sources s ON s.id = r.source_id
        WHERE t.status = 'signal' AND lower(s.name) LIKE 'google patents%%'
          AND r.url LIKE '%%/patent/%%' AND length(coalesce(r.excerpt, '')) > 200
          AND t.embedding_1024 IS NOT NULL AND mod(t.id, 31) = 0
        ORDER BY t.id LIMIT ?""", (n,))
    truth = {}
    for r in rows("""SELECT pub_number, array_agg(DISTINCT subclass) AS subs,
                            array_agg(DISTINCT subclass) FILTER (WHERE inventive = 1) AS inv
                     FROM patent_cpc WHERE pub_number = ANY(?) GROUP BY 1""",
                  ([i["pub_number"] for i in items],)):
        truth[r["pub_number"]] = {"any": set(r["subs"] or []), "inventive": set(r["inv"] or [])}
    items = [i for i in items if truth.get(i["pub_number"], {}).get("any")]
    for i in items:
        i["truth"] = truth[i["pub_number"]]["any"]
        i["truth_inv"] = truth[i["pub_number"]]["inventive"] or i["truth"]
    labels = rows("SELECT symbol, title, left(coalesce(definition, ''), 400) AS definition, "
                  "embedding_1024::text AS emb FROM cpc_definitions ORDER BY symbol")
    lab = {
        "ids": [l["symbol"] for l in labels],
        "text": [f"{l['symbol']}: {l['title'].capitalize()}. {l['definition']}".strip() for l in labels],
        "M": unit(np.vstack([vec(l["emb"]) for l in labels])),
    }
    return items, lab


def research_sample(n: int, embed_host: str) -> tuple[list[dict], dict]:
    cand = rows("""
        SELECT rs.trend_id AS id, rs.title, rs.abstract AS excerpt, lower(rs.url) AS doi,
               t.embedding_1024::text AS emb
        FROM research_signals rs JOIN trends t ON t.id = rs.trend_id
        WHERE rs.url LIKE 'https://doi.org/%%' AND length(coalesce(rs.abstract, '')) > 200
          AND t.embedding_1024 IS NOT NULL AND mod(rs.trend_id, 23) = 0
        ORDER BY rs.trend_id LIMIT ?""", (n * 4,))
    topic = {r["doi"]: r["topic"] for r in rows(
        "SELECT doi, topic FROM research_corpus WHERE doi = ANY(?) AND topic IS NOT NULL",
        ([c["doi"] for c in cand],))}
    tax = rows("SELECT DISTINCT ON (topic) topic, subfield, field FROM openalex_topics ORDER BY topic")
    sub_of = {t["topic"]: t["subfield"] for t in tax}
    items = [c for c in cand if topic.get(c["doi"]) in sub_of][:n]
    for i in items:
        i["truth"] = {topic[i["doi"]]}
        i["truth_sub"] = sub_of[topic[i["doi"]]]
    texts = [f"{t['topic']}. Subfield: {t['subfield']}. Field: {t['field']}." for t in tax]
    M = embed(texts, embed_host)
    lab = {"ids": [t["topic"] for t in tax], "text": texts, "M": unit(M), "sub_of": sub_of}
    return items, lab


def embed(texts: list[str], host: str, batch: int = 64) -> np.ndarray:
    out = []
    with httpx.Client(timeout=300) as c:
        for s in range(0, len(texts), batch):
            r = c.post(f"{host}/v1/embeddings", json={"input": texts[s:s + batch]})
            r.raise_for_status()
            data = sorted(r.json()["data"], key=lambda d: d["index"])
            out += [np.asarray(d["embedding"][:1024], dtype=np.float32) for d in data]
    return np.vstack(out)


# ------------------------------------------------------------------ rerank

def rerank(host: str, query: str, docs: list[str]) -> list[float]:
    """Relevance score of each document for the query, in document order.

    llama-server queues the documents of a request as separate tasks; under load
    one request starved past 300 s in the first run (27.09.) although the server
    kept working. Hence the long timeout and one retry.
    """
    for attempt in (1, 2):
        try:
            with httpx.Client(timeout=1200) as c:
                r = c.post(f"{host}/v1/rerank", json={"query": query, "documents": docs})
                r.raise_for_status()
            break
        except httpx.TimeoutException:
            if attempt == 2:
                raise
    scores = [0.0] * len(docs)
    for x in r.json()["results"]:
        scores[x["index"]] = float(x["relevance_score"])
    return scores


def query_text(item: dict, kind: str) -> str:
    body = (item.get("excerpt") or "")[:QUERY_CHARS]
    what = "patent" if kind == "patent" else "research paper"
    return f"Which classification label describes the subject of this {what}? {item['title']}. {body}"


def evaluate(items: list[dict], lab: dict, kind: str, host: str, k: int, workers: int) -> dict:
    S = np.vstack([vec(i["emb"]) for i in items]) @ lab["M"].T
    top = np.argsort(-S, axis=1)[:, :k]
    t0 = time.time()

    def one(j):
        idx = top[j]
        return rerank(host, query_text(items[j], kind), [lab["text"][x] for x in idx])

    with ThreadPoolExecutor(workers) as ex:
        scores = list(ex.map(one, range(len(items))))
    dt = time.time() - t0

    def p_at(order_ids, truth, n):
        return float(any(o in truth for o in order_ids[:n]))

    res = {"n": len(items), "k": k, "pairs": len(items) * k, "rerank_s": round(dt, 1),
           "pairs_per_s": round(len(items) * k / dt, 1)}
    emb_p1 = emb_p3 = rr_p1 = rr_p3 = rec = 0.0
    pairs = []   # (score, is_true)
    for j, it in enumerate(items):
        ids = [lab["ids"][x] for x in top[j]]
        truth = it["truth"]
        rec += float(any(i in truth for i in ids))
        emb_p1 += p_at(ids, truth, 1)
        emb_p3 += p_at(ids, truth, 3)
        order = [ids[x] for x in np.argsort(-np.asarray(scores[j]))]
        rr_p1 += p_at(order, truth, 1)
        rr_p3 += p_at(order, truth, 3)
        pairs += [(scores[j][x], ids[x] in truth) for x in range(len(ids))]
        it["_rr_top"] = order[:3]
        it["_emb_top"] = ids[:3]
    n = len(items)
    res.update({f"candidate_recall@{k}": round(rec / n, 3),
                "embedding_P@1": round(emb_p1 / n, 3), "embedding_P@3": round(emb_p3 / n, 3),
                "rerank_P@1": round(rr_p1 / n, 3), "rerank_P@3": round(rr_p3 / n, 3)})
    if kind == "patent":
        res["rerank_P@1_inventive"] = round(np.mean([float(it["_rr_top"][0] in it["truth_inv"]) for it in items]), 3)
        res["embedding_P@1_inventive"] = round(np.mean([float(it["_emb_top"][0] in it["truth_inv"]) for it in items]), 3)
    else:
        sub = lab["sub_of"]
        res["rerank_P@1_subfield"] = round(np.mean([float(sub.get(it["_rr_top"][0]) == it["truth_sub"]) for it in items]), 3)
        res["embedding_P@1_subfield"] = round(np.mean([float(sub.get(it["_emb_top"][0]) == it["truth_sub"]) for it in items]), 3)
    # "assign every candidate above t": precision/recall against the true labels
    sc = np.asarray([p[0] for p in pairs])
    ok = np.asarray([p[1] for p in pairs])
    total_true = sum(len(it["truth"]) for it in items)
    table = []
    for q in (0.5, 0.75, 0.9, 0.95, 0.98):
        t = float(np.quantile(sc, q))
        sel = sc >= t
        table.append({"threshold": round(t, 4), "assigned_per_item": round(sel.sum() / n, 2),
                      "precision": round(float(ok[sel].mean()) if sel.any() else 0.0, 3),
                      "recall": round(float(ok[sel].sum()) / total_true, 3)})
    res["threshold_table"] = table
    res["examples"] = [{"title": it["title"][:100], "truth": sorted(it["truth"])[:5],
                        "embedding_top3": it["_emb_top"], "rerank_top3": it["_rr_top"]}
                       for it in items[:8]]
    return res


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--rerank-host", required=True)
    ap.add_argument("--embed-host", required=True, help="GPU embedder, for the OpenAlex topic labels")
    ap.add_argument("--n", type=int, default=1000)
    ap.add_argument("--k", type=int, default=20)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--only", choices=["patent", "research"], default=None)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    report = {}
    if args.only in (None, "research"):
        items, lab = research_sample(args.n, args.embed_host)
        print(f"research: {len(items)} items, {len(lab['ids'])} topic labels", flush=True)
        report["research_openalex_topic"] = evaluate(items, lab, "research", args.rerank_host, args.k, args.workers)
        (OUT / "pilot_vocab_rerank_research.json").write_text(json.dumps(report["research_openalex_topic"], indent=2, ensure_ascii=False))
        print(json.dumps({k: v for k, v in report["research_openalex_topic"].items() if k not in ("examples", "threshold_table")}), flush=True)
    if args.only in (None, "patent"):
        items, lab = patent_sample(args.n)
        print(f"patents: {len(items)} items, {len(lab['ids'])} CPC subclasses", flush=True)
        report["patent_cpc_subclass"] = evaluate(items, lab, "patent", args.rerank_host, args.k, args.workers)
        (OUT / "pilot_vocab_rerank_patent.json").write_text(json.dumps(report["patent_cpc_subclass"], indent=2, ensure_ascii=False))
        print(json.dumps({k: v for k, v in report["patent_cpc_subclass"].items() if k not in ("examples", "threshold_table")}), flush=True)
    path = OUT / "pilot_vocab_rerank.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"written {path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
