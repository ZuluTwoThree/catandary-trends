#!/usr/bin/env python3
"""Erfuellen die Volltext-Vektoren ihren Zweck? (#102, Owner-Auftrag 2026-09-11)

Zwei Vektorraeume je Trend: `embedding_1024` (Titel + 500 Zeichen Anriss, fuer
den Dedup) und `embedding_full_1024` (Titel + voller Quelltext, fuer Analyse und
Retrieval). Der Anlass fuer den zweiten Raum war, dass der erste formelhafte
Meldungen nach ihrer SATZFORM gruppierte und auf Mega-Trend-Hoehe eine
Silhouette von ~0,02 hatte. Dieses Skript misst, ob der neue Raum das besser
macht — auf genau den Zeilen, die BEIDE Vektoren tragen, damit der Vergleich
fair ist.

Messungen (k = 10 naechste Nachbarn, Kosinus, je Raum):
  1. Nachbar-Ueberlappung zwischen den Raeumen (Jaccard@10) — sehen sie dasselbe?
  2. Anteil der Nachbarn aus derselben QUELLE (Satzform-Naehe) gegen Anteil mit
     demselben Mega-Trend / derselben Vertikale (Inhalts-Naehe).
  3. kNN-Mehrheitsvotum: wie gut sagen die Nachbarn Vertikale und Mega-Trend
     voraus? ACHTUNG Schieflage: Mega-Trend und Vertikale der Signale stammen
     von den Distill-Koepfen, die auf dem DEDUP-Vektor trainiert sind — dieser
     Test bevorzugt strukturell den alten Raum. Bei published Trends hat Stage 8
     (LLM) die Vertikale geprueft; die Zahl wird deshalb getrennt ausgewiesen.
  4. Silhouette auf Mega-Trend-Ebene (Stichprobe), der Wert aus dem Anlass.
  5. Dubletten-Probe: Paare mit Dedup-Kosinus > 0,92 — bleiben sie im
     Volltext-Raum nah? (Der neue Raum soll Inhalt trennen, nicht Dubletten
     auseinanderreissen.)
  6. Retrieval-Probe: sechs Anfragen ueber den CPU-Embedder (:8091, dasselbe
     Modell) — Top 5 je Raum zum Lesen.

    .venv/bin/python scripts/eval_full_text_embeddings.py [--queries 600] [--out docs/x.md]
"""
from __future__ import annotations

import argparse
import json
import logging
import random
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.db import get_connection  # noqa: E402

logger = logging.getLogger(__name__)
K = 10
QUERIES = [
    "gut microbiome and mental health",
    "solid-state battery manufacturing scale-up",
    "EU AI Act compliance obligations for companies",
    "plant-based meat alternatives sales decline",
    "quantum error correction milestones",
    "circular fashion textile recycling",
]


def load(limit: int | None) -> dict:
    sql = ("SELECT t.id, t.status, t.primary_vertical, t.mega_trend, t.source_name, t.title_en, "
           "t.full_embedded_chars, length(coalesce(re.excerpt, '')) AS excerpt_len, "
           "t.embedding_1024::text AS a, t.embedding_full_1024::text AS b "
           "FROM trends t LEFT JOIN raw_entries re ON re.id = t.raw_entry_id "
           "WHERE t.embedding_1024 IS NOT NULL AND t.embedding_full_1024 IS NOT NULL")
    if limit:
        sql += f" ORDER BY t.id DESC LIMIT {int(limit)}"
    with get_connection() as conn:
        rows = conn.execute(sql).fetchall()
    n = len(rows)
    A = np.empty((n, 1024), dtype=np.float32)
    B = np.empty((n, 1024), dtype=np.float32)
    meta = []
    for i, r in enumerate(rows):
        d = dict(r)
        A[i] = np.array(json.loads(d.pop("a")), dtype=np.float32)
        B[i] = np.array(json.loads(d.pop("b")), dtype=np.float32)
        meta.append(d)
    A /= np.linalg.norm(A, axis=1, keepdims=True) + 1e-9
    B /= np.linalg.norm(B, axis=1, keepdims=True) + 1e-9
    return {"A": A, "B": B, "meta": meta}


def topk(M: np.ndarray, q_idx: np.ndarray, k: int) -> tuple[np.ndarray, np.ndarray]:
    """Indizes + Kosinus der k naechsten Nachbarn (ohne sich selbst)."""
    sims = M[q_idx] @ M.T
    sims[np.arange(len(q_idx)), q_idx] = -1.0
    idx = np.argpartition(-sims, k, axis=1)[:, :k]
    s = np.take_along_axis(sims, idx, axis=1)
    order = np.argsort(-s, axis=1)
    return np.take_along_axis(idx, order, axis=1), np.take_along_axis(s, order, axis=1)


def neighbour_stats(meta: list[dict], q_idx: np.ndarray, nn: np.ndarray, field: str) -> float | None:
    """Anteil der Nachbarn, die im Feld mit der Anfrage uebereinstimmen (nur
    Anfragen mit gesetztem Feld)."""
    hits = tot = 0
    for qi, row in zip(q_idx, nn):
        v = meta[qi].get(field)
        if not v:
            continue
        for j in row:
            tot += 1
            hits += meta[j].get(field) == v
    return hits / tot if tot else None


def knn_accuracy(meta: list[dict], q_idx: np.ndarray, nn: np.ndarray, field: str,
                 only_status: str | None = None) -> tuple[float | None, int]:
    ok = tot = 0
    for qi, row in zip(q_idx, nn):
        v = meta[qi].get(field)
        if not v or (only_status and meta[qi]["status"] != only_status):
            continue
        votes = Counter(meta[j].get(field) for j in row if meta[j].get(field))
        if not votes:
            continue
        tot += 1
        ok += votes.most_common(1)[0][0] == v
    return (ok / tot if tot else None), tot


def silhouette(M: np.ndarray, labels: list[str], sample: int, seed: int) -> tuple[float, int]:
    rng = random.Random(seed)
    idx = [i for i, l in enumerate(labels) if l]
    counts = Counter(labels[i] for i in idx)
    idx = [i for i in idx if counts[labels[i]] >= 20]
    rng.shuffle(idx)
    idx = np.array(idx[:sample])
    X = M[idx]
    lab = np.array([labels[i] for i in idx])
    D = 1.0 - X @ X.T
    n = len(idx)
    s = np.zeros(n)
    for i in range(n):
        same = lab == lab[i]
        same[i] = False
        if same.sum() == 0:
            continue
        a = D[i, same].mean()
        b = min(D[i, lab == other].mean() for other in set(lab) if other != lab[i])
        s[i] = (b - a) / max(a, b) if max(a, b) > 0 else 0.0
    return float(s.mean()), n


def embed_queries(queries: list[str]) -> list[np.ndarray] | None:
    try:
        from pipeline.config import RESEARCH_EMBED_HOST
        from pipeline import llamacpp_client
        if not RESEARCH_EMBED_HOST:
            return None
        out = []
        for q in queries:
            v = llamacpp_client.generate_embedding(q, host=RESEARCH_EMBED_HOST)
            v = np.array(v[:1024], dtype=np.float32)
            out.append(v / (np.linalg.norm(v) + 1e-9))
        return out
    except Exception as e:                                          # noqa: BLE001
        logger.warning("Retrieval-Probe uebersprungen: %s", e)
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--queries", type=int, default=600, help="Anfrage-Stichprobe je Schicht (published / uebrige)")
    ap.add_argument("--sil", type=int, default=3000, help="Stichprobe fuer die Silhouette")
    ap.add_argument("--limit", type=int, default=0, help="nur die N juengsten Zeilen laden (0 = alle mit beiden Vektoren)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    data = load(args.limit or None)
    A, B, meta = data["A"], data["B"], data["meta"]
    n = len(meta)
    logger.info("%d Zeilen mit beiden Vektoren", n)
    rng = np.random.default_rng(args.seed)
    pub = np.array([i for i, m in enumerate(meta) if m["status"] == "published"])
    rest = np.array([i for i, m in enumerate(meta) if m["status"] != "published"])
    q_idx = np.concatenate([rng.choice(pub, size=min(args.queries, len(pub)), replace=False) if len(pub) else np.array([], dtype=int),
                            rng.choice(rest, size=min(args.queries, len(rest)), replace=False)]).astype(int)
    gain = np.array([(m["full_embedded_chars"] or 0) / max(m["excerpt_len"] or 0, 1) for m in meta])

    nnA, sA = topk(A, q_idx, K)
    nnB, sB = topk(B, q_idx, K)
    lines: list[str] = []
    P = lines.append
    P(f"# Volltext-Vektoren gegen Dedup-Vektoren — Messung {datetime.now():%Y-%m-%d %H:%M}")
    P("")
    P(f"Grundgesamtheit: **{n:,}** Trends mit beiden Vektoren "
      f"({Counter(m['status'] for m in meta).most_common()}); "
      f"Anfragen: {len(q_idx)} (je {args.queries} published / uebrige), k = {K}, Kosinus. "
      f"Textgewinn Volltext/Anriss: Median {np.median(gain):.1f}×, Anteil ≥ 3×: {np.mean(gain >= 3) * 100:.0f} %.")
    P("")
    # 1 Ueberlappung
    jac = [len(set(a) & set(b)) / len(set(a) | set(b)) for a, b in zip(nnA, nnB)]
    P("## 1. Sehen die Raeume dasselbe? (Jaccard@10 zwischen den Nachbarlisten)")
    P(f"- mittlere Ueberlappung **{np.mean(jac):.2f}** (Median {np.median(jac):.2f}); "
      f"{np.mean(np.array(jac) == 0) * 100:.0f} % der Anfragen haben KEINEN gemeinsamen Nachbarn")
    P(f"- mittlerer Kosinus zum naechsten Nachbarn: Dedup {sA[:, 0].mean():.3f}, Volltext {sB[:, 0].mean():.3f}")
    P("")
    # 2 Quelle vs Inhalt
    P("## 2. Satzform oder Inhalt? Anteil der Nachbarn mit …")
    P("| | Dedup-Raum | Volltext-Raum |")
    P("|---|---|---|")
    for label, field in (("derselben Quelle (Form)", "source_name"),
                         ("demselben Mega-Trend (Inhalt)", "mega_trend"),
                         ("derselben Vertikale (Inhalt)", "primary_vertical")):
        a = neighbour_stats(meta, q_idx, nnA, field)
        b = neighbour_stats(meta, q_idx, nnB, field)
        P(f"| {label} | {a * 100:.1f} % | {b * 100:.1f} % |" if a is not None and b is not None else f"| {label} | — | — |")
    # nach Status
    for st in ("signal", "published"):
        sel = np.array([i for i, qi in enumerate(q_idx) if meta[qi]["status"] == st])
        if len(sel) < 30:
            continue
        a = neighbour_stats(meta, q_idx[sel], nnA[sel], "source_name")
        b = neighbour_stats(meta, q_idx[sel], nnB[sel], "source_name")
        am = neighbour_stats(meta, q_idx[sel], nnA[sel], "mega_trend")
        bm = neighbour_stats(meta, q_idx[sel], nnB[sel], "mega_trend")
        P(f"| nur `{st}` (n={len(sel)}): dieselbe Quelle / derselbe Mega-Trend | "
          f"{(a or 0) * 100:.1f} % / {(am or 0) * 100:.1f} % | {(b or 0) * 100:.1f} % / {(bm or 0) * 100:.1f} % |")
    for label, sel in (("Textgewinn < 2× (Volltext ≈ Anriss, z. B. Abstracts)", np.array([i for i, qi in enumerate(q_idx) if gain[qi] < 2])),
                       ("Textgewinn ≥ 3× (echter Volltext)", np.array([i for i, qi in enumerate(q_idx) if gain[qi] >= 3]))):
        if len(sel) < 30:
            continue
        a = neighbour_stats(meta, q_idx[sel], nnA[sel], "source_name")
        b = neighbour_stats(meta, q_idx[sel], nnB[sel], "source_name")
        am = neighbour_stats(meta, q_idx[sel], nnA[sel], "mega_trend")
        bm = neighbour_stats(meta, q_idx[sel], nnB[sel], "mega_trend")
        P(f"| {label} (n={len(sel)}): dieselbe Quelle / derselbe Mega-Trend | "
          f"{(a or 0) * 100:.1f} % / {(am or 0) * 100:.1f} % | {(b or 0) * 100:.1f} % / {(bm or 0) * 100:.1f} % |")
    P("")
    P("Lesart: sinkt der Quellen-Anteil und steigt der Inhalts-Anteil, gruppiert der "
      "Raum nach Thema statt nach Satzform. Bei Abstracts (Textgewinn < 2×) sehen "
      "beide Raeume fast denselben Text — Unterschiede sind dort nicht zu erwarten.")
    P("")
    # 3 kNN accuracy
    P("## 3. kNN-Mehrheitsvotum (k = 10)")
    P("| Ziel | Dedup-Raum | Volltext-Raum | n |")
    P("|---|---|---|---|")
    big = np.array([i for i, qi in enumerate(q_idx) if gain[qi] >= 3])
    for label, field, st, sel in (("Vertikale, alle", "primary_vertical", None, None),
                                  ("Vertikale, nur published (Stage-8-geprueft)", "primary_vertical", "published", None),
                                  ("Vertikale, published mit Textgewinn ≥ 3×", "primary_vertical", "published", big),
                                  ("Mega-Trend, alle (Kopf-Label, dedup-nah)", "mega_trend", None, None),
                                  ("Mega-Trend, nur published", "mega_trend", "published", None),
                                  ("Mega-Trend, published mit Textgewinn ≥ 3×", "mega_trend", "published", big)):
        qq, ma, mb = (q_idx, nnA, nnB) if sel is None else (q_idx[sel], nnA[sel], nnB[sel])
        a, na = knn_accuracy(meta, qq, ma, field, st)
        b, nb = knn_accuracy(meta, qq, mb, field, st)
        P(f"| {label} | {a * 100:.1f} % | {b * 100:.1f} % | {na} |" if a is not None and b is not None and na >= 20
          else f"| {label} | — | — | {na} |")
    P("")
    P("Schieflage beachten: Mega-Trend und Vertikale der Signale kommen von den "
      "Distill-Koepfen, die auf dem Dedup-Vektor trainiert sind — der alte Raum "
      "ist hier im Vorteil. Zieht der neue gleich oder vorbei, wiegt das doppelt.")
    P("")
    # 4 silhouette
    labels = [m.get("mega_trend") or "" for m in meta]
    silA, ns = silhouette(A, labels, args.sil, args.seed)
    silB, _ = silhouette(B, labels, args.sil, args.seed)
    P(f"## 4. Silhouette auf Mega-Trend-Ebene (Stichprobe {ns}, Klassen mit ≥ 20)")
    P(f"- Dedup-Raum **{silA:.3f}**, Volltext-Raum **{silB:.3f}** (Anlass #102: ~0,02)")
    P("")
    # 5 duplicates
    pairs = [(qi, j, sa, sb) for qi, rowA, rowSA in zip(q_idx, nnA, sA) for j, sa in zip(rowA, rowSA) if sa > 0.92
             for sb in [float(B[qi] @ B[j])]]
    P("## 5. Dubletten-Probe (Paare mit Dedup-Kosinus > 0,92)")
    if pairs:
        sbv = np.array([p[3] for p in pairs])
        P(f"- {len(pairs)} Paare; Volltext-Kosinus Median **{np.median(sbv):.3f}**, "
          f"Quartile {np.percentile(sbv, 25):.3f}/{np.percentile(sbv, 75):.3f}, "
          f"unter 0,7: {np.mean(sbv < 0.7) * 100:.0f} %")
        low = sorted(pairs, key=lambda p: p[3])[:3]
        for qi, j, sa, sb in low:
            P(f"  - auseinander: {sa:.3f} → {sb:.3f} · „{meta[qi]['title_en'][:70]}“ ↔ „{meta[j]['title_en'][:70]}“")
    else:
        P("- keine Paare in der Stichprobe")
    P("")
    # 6 retrieval
    qv = embed_queries(QUERIES)
    P("## 6. Retrieval-Probe (Top 5 je Raum, Anfrage ueber :8091)")
    if qv is None:
        P("- uebersprungen (kein RESEARCH_EMBED_HOST / Embedder nicht erreichbar)")
    else:
        for q, v in zip(QUERIES, qv):
            P(f"### „{q}“")
            for name, M in (("Dedup", A), ("Volltext", B)):
                sims = M @ v
                top = np.argsort(-sims)[:5]
                P(f"- **{name}:**")
                for j in top:
                    m = meta[j]
                    P(f"  - {sims[j]:.3f} · {m['title_en'][:90]} *({m.get('source_name') or '?'}, {m.get('primary_vertical') or '?'})*")
            P("")
    text = "\n".join(lines)
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
        logger.info("→ %s", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
