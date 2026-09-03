#!/usr/bin/env python3
"""Measure the #67 query-gate signals on a fixed test set and cache them.

Embeds every phrase of the test set (needs an embedding llama-server — the
production one via the usual handover, or any server reachable through
LLAMACPP_HOST), collects the gate signals against the live DB
(pipeline.query_gate.collect_signals) and writes

    tests/fixtures/tech_query_gate.json   vectors + raw signals per phrase

so the pytest regression (tests/test_query_gate.py) and any threshold
recalibration run WITHOUT GPU or DB. Prints the markdown table that
docs/tech_query_gate_2026-09-04.md carries.

    LLAMACPP_HOST=http://127.0.0.1:8091 python scripts/measure_query_gate.py
    python scripts/measure_query_gate.py --signals-only   # reuse cached vectors
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline import llamacpp_client
from pipeline.config import EMBED_MODEL
from pipeline.query_gate import collect_signals, summarize, verdict

FIXTURE = Path(__file__).parent.parent / "tests" / "fixtures" / "tech_query_gate.json"

# Real technologies: the tool's example chips + well-known domains across sections.
TECH = [
    "processed cheese", "solid-state battery electrolyte", "mRNA vaccine manufacturing",
    "perovskite tandem solar cells",                              # the 4 example chips
    "perovskite tandem photovoltaics", "CRISPR base editing", "quantum error correction",
    "lithium-ion battery cathode", "heat pump", "vertical farming",
    "hydrogen electrolysis", "carbon capture and storage", "metal powder 3D printing",
    "lidar sensors for autonomous vehicles", "organic light-emitting diode display",
    "wind turbine blade", "semiconductor lithography", "precision fermentation",
    "gene therapy viral vectors", "wireless charging", "robotic surgery",
    "microfluidic lab-on-a-chip", "plant-based meat extrusion", "sodium-ion battery",
    "silicon photonics", "insulin pump",
]
# Nonsense / everyday phrases — must NEVER get a number.
NONSENSE = [
    "unicorn breeding", "my cat is sad on tuesdays", "best pizza in berlin",
    "how to be happy", "what time is it", "birthday party ideas", "why is the sky blue",
    "cheap flights to rome", "funny dog videos", "meaning of life",
    "harry potter fan fiction", "football world cup winner", "asdf qwerty",
    "lorem ipsum dolor", "my neighbour is loud", "recipe for pancakes",
    "who won the election", "tax return deadline", "monday morning blues",
    "the weather tomorrow", "love poems for her", "dragon taming school",
    "invisible pink elephant", "hello world", "stock market crash prediction",
]
# Grey: abstract trends / names — informative, not part of the acceptance count.
GREY = [
    "future of work", "artificial intelligence", "blockchain", "sustainable fashion",
    "Tesla", "climate change", "digital transformation", "nanotechnology",
]


def embed(text: str) -> list[float]:
    emb = llamacpp_client.generate_embedding(text, model=EMBED_MODEL)
    if not emb:
        raise SystemExit(f"embedding failed for {text!r} — is an embedding server up "
                         f"at LLAMACPP_HOST?")
    return [round(float(x), 6) for x in list(emb)[:1024]]   # same truncation as embed_query


def main() -> int:
    ap = argparse.ArgumentParser(description="Measure #67 query-gate signals")
    ap.add_argument("--signals-only", action="store_true",
                    help="reuse the cached vectors, recompute only the DB signals")
    args = ap.parse_args()
    cached: dict[str, list[float]] = {}
    if args.signals_only and FIXTURE.exists():
        cached = {it["query"]: it["vec"] for it in json.loads(FIXTURE.read_text())["items"]}
    items = []
    t_all = time.time()
    for group, phrases in (("tech", TECH), ("nonsense", NONSENSE), ("grey", GREY)):
        for q in phrases:
            t0 = time.time()
            vec = cached.get(q) or embed(q)
            t1 = time.time()
            sig = collect_signals(vec, q)
            t2 = time.time()
            v = verdict(sig)
            items.append({"query": q, "group": group, "vec": vec, "signals": sig})
            f = v["features"]
            print(f"{group:8s} {q:42s} d1={f['d1']:.3f} m20={f['margin20']:.3f} "
                  f"sub={f['subclasses12']} share={f['top_subclass_share12']:.2f} "
                  f"ft={f['and_hits']:>4} ({sig['fulltext']['ms']} ms) → {v['verdict']:9s} "
                  f"[embed {t1 - t0:.2f}s, signals {t2 - t1:.2f}s]", file=sys.stderr)
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE.write_text(json.dumps({
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "embed_model": EMBED_MODEL, "dims": 1024,
        "items": items,
    }, separators=(",", ":")))
    print(f"\nfixture → {FIXTURE} ({len(items)} items, {time.time() - t_all:.1f}s)",
          file=sys.stderr)
    print(summarize(items))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
