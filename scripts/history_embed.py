#!/usr/bin/env python3
"""Embed the signal space's past into history_items / history_vectors (Owner 2026-10-03).

    .venv/bin/python scripts/history_embed.py select [--quota 2000]     # fill the queue once
    .venv/bin/python scripts/history_embed.py work --host URL --name 3090 [--threads 2]
    .venv/bin/python scripts/history_embed.py status
    .venv/bin/python scripts/history_embed.py check [--n 300]           # same space as trends?

Workers claim chunks with FOR UPDATE SKIP LOCKED, so any number of them on any number of
GPUs share the queue; a claim older than 20 minutes is free again (a killed worker loses
nothing). The two-GPU run (3090 + 5080 on bequietUbuntu) is scripts/run_history_embed.sh.
Plan: docs/history_backfill_plan_2026-10-03.md.
"""
from __future__ import annotations

import argparse
import sys
import threading
import time
from contextlib import nullcontext
from pathlib import Path

import httpx
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.db import get_connection  # noqa: E402
from pipeline import history_vectors as hv  # noqa: E402

try:
    from pipeline.ops_events import record
except ImportError:                                    # pragma: no cover
    def record(_job):
        return nullcontext()


def log(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def cmd_select(args) -> int:
    hv.migrate_history_tables()
    with get_connection() as c:
        c.execute("SET statement_timeout = 0")
        c.execute("SET work_mem = '1GB'")
        have = c.execute("SELECT count(*) AS n FROM history_items").fetchone()["n"]
        if have and not args.force:
            log(f"queue already holds {have:,} items — nothing selected (--force adds missing ones)")
            return 0
        t = time.time()
        n_p = hv.select_patents(c, args.patents_from, args.until, args.quota)
        c.commit()
        log(f"patents queued: {n_p:,} ({time.time() - t:.0f} s)")
        n_s = hv.select_science(c, args.science_from, args.until, args.quota)
        c.commit()
        log(f"science queued: {n_s:,} ({time.time() - t:.0f} s)")
        c.execute("ANALYZE history_items")
    return 0


def embed(client: httpx.Client, host: str, texts: list[str]) -> list[list[float]]:
    r = client.post(f"{host}/v1/embeddings", json={"input": texts})
    r.raise_for_status()
    return [d["embedding"] for d in sorted(r.json()["data"], key=lambda d: d.get("index", 0))]


class Counter:
    def __init__(self) -> None:
        self.n = 0
        self.lock = threading.Lock()

    def add(self, k: int) -> None:
        with self.lock:
            self.n += k


def worker_loop(args, tag: str, counter: Counter, stop: threading.Event) -> None:
    errors = 0
    with httpx.Client(timeout=600) as client:
        while not stop.is_set():
            with get_connection() as c:
                items = hv.claim(c, tag, args.chunk)
                c.commit()
                if not items:
                    return
                texts = hv.texts_for(c, items)
            ids = [it["id"] for it in items if it["id"] in texts]
            missing = [it["id"] for it in items if it["id"] not in texts]
            try:
                vecs = embed(client, args.host, [texts[i] for i in ids]) if ids else []
            except Exception as e:                               # noqa: BLE001
                errors += 1
                log(f"{tag}: embedding failed ({e!r}), {errors} in a row — claim expires and is retried")
                if errors >= args.max_errors:
                    stop.set()
                    return
                time.sleep(10)
                continue
            errors = 0
            with get_connection() as c:
                hv.store(c, [(i, hv.pack(v)) for i, v in zip(ids, vecs)], args.name)
                if missing:   # text gone (purged row) — mark done without a vector
                    c.execute("UPDATE history_items SET embedded_at = now(), layer = layer || ':notext' "
                              "WHERE id = ANY(?)", (missing,))
                c.commit()
            counter.add(len(ids))


def _unit_active() -> bool:
    from pipeline import gpu_handover
    try:
        r = gpu_handover._run(["systemctl", "--user", "is-active", gpu_handover.LLAMA_UNIT], timeout=15)
        return r.stdout.strip() == "active"
    except Exception:                                              # noqa: BLE001
        return False


def cmd_work(args) -> int:
    hv.migrate_history_tables()
    counter, stop = Counter(), threading.Event()
    gpu = nullcontext()
    was_active = False
    if args.handover:
        # the local 3090: swap llama-server to the embedding model like the signal path,
        # owner record + symlink restore come with the handover; the resting server is
        # started again afterwards (research_pulse rule)
        from pipeline import gpu_handover
        from pipeline.config import EMBED_MODEL
        was_active = _unit_active()
        gpu = gpu_handover.embed_on_llamacpp(EMBED_MODEL)
    try:
        with record(f"history_embed_{args.name}"), gpu:
            return _work(args, counter, stop)
    finally:
        if args.handover and was_active:
            from pipeline import gpu_handover
            log("restoring the resting llama-server")
            gpu_handover.unit_start()


def _work(args, counter: Counter, stop: threading.Event) -> int:
    t0 = time.time()
    threads = [threading.Thread(target=worker_loop, args=(args, f"{args.name}.{k}", counter, stop),
                                daemon=True) for k in range(args.threads)]
    for th in threads:
        th.start()
    last = 0
    while any(th.is_alive() for th in threads):
        time.sleep(args.report)
        n = counter.n
        el = time.time() - t0
        log(f"{args.name}: {n:,} embedded, {n / el:.1f}/s overall, {(n - last) / args.report:.1f}/s now")
        last = n
    log(f"{args.name}: done — {counter.n:,} in {time.time() - t0:.0f} s"
        + (" (stopped after repeated errors)" if stop.is_set() else ""))
    return 3 if stop.is_set() else 0


def cmd_status(_args) -> int:
    with get_connection() as c:
        rows = hv.status(c)
        size = c.execute("SELECT pg_size_pretty(pg_total_relation_size('history_vectors')) AS v, "
                         "pg_size_pretty(pg_total_relation_size('history_items')) AS i").fetchone()
    tot = sum(r["n"] for r in rows)
    done = sum(r["done"] for r in rows)
    for r in rows:
        print(f"{r['tier']:<8} {r['layer']:<14} {r['done']:>10,} / {r['n']:>10,}  claimed {r['claimed']:,}")
    print(f"total {done:,} / {tot:,} ({100 * done / max(tot, 1):.1f} %) · vectors {size['v']}, items {size['i']}")
    return 0


def cmd_check(args) -> int:
    """Same vector space as trends? Embeds the texts of n queued patents that also sit in
    trends with a vector, on --host, and compares with trends.embedding_1024. Writes nothing.
    Same model + same text recipe -> cosine ~0.99+ (other GPU/CPU: ~0.998)."""
    with get_connection() as c:
        rows = c.execute("""SELECT h.id, h.tier, h.ref, h.raw_entry_id, t.embedding_1024::text AS e
            FROM history_items h JOIN trends t ON t.raw_entry_id = h.raw_entry_id
            WHERE h.tier = 'patent' AND t.embedding_1024 IS NOT NULL ORDER BY h.id LIMIT ?""",
                         (args.n,)).fetchall()
        items = [dict(r) for r in rows]
        texts = hv.texts_for(c, items)
    if not items:
        print("no queued patent with a vector in trends")
        return 1
    ids = [it["id"] for it in items if it["id"] in texts]
    with httpx.Client(timeout=600) as client:
        vecs = embed(client, args.host, [texts[i] for i in ids])
    ref = {it["id"]: it["e"] for it in items}
    cs = []
    for i, v in zip(ids, vecs):
        a = hv.unpack(hv.pack(v))
        b = np.array([float(x) for x in ref[i].strip("[]").split(",")], np.float32)
        cs.append(float(a @ (b / np.linalg.norm(b))))
    cs.sort()
    print(f"{args.host}: n={len(cs)} cosine min {cs[0]:.4f} p5 {cs[len(cs) // 20]:.4f} "
          f"median {np.median(cs):.4f}")
    return 0 if cs[len(cs) // 20] > 0.98 else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("select")
    s.add_argument("--quota", type=int, default=2000)
    s.add_argument("--patents-from", default="1990-01-01")
    s.add_argument("--science-from", default="2010-01-01")
    s.add_argument("--until", default="2026-07-01",
                   help="exclusive; from here the Saturday run embeds every new patent (60-day window)")
    s.add_argument("--force", action="store_true")
    w = sub.add_parser("work")
    w.add_argument("--host", required=True)
    w.add_argument("--name", required=True, help="device label stored with each vector")
    w.add_argument("--threads", type=int, default=2)
    w.add_argument("--chunk", type=int, default=64)
    w.add_argument("--report", type=int, default=60)
    w.add_argument("--max-errors", type=int, default=20)
    w.add_argument("--handover", action="store_true",
                   help="local GPU: load the embedding model on :8090 for the run, restore after")
    sub.add_parser("status")
    k = sub.add_parser("check")
    k.add_argument("--n", type=int, default=200)
    k.add_argument("--host", default="http://127.0.0.1:8091", help="default: the CPU embedder")
    args = ap.parse_args()
    return {"select": cmd_select, "work": cmd_work, "status": cmd_status, "check": cmd_check}[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
