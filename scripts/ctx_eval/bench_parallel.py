#!/usr/bin/env python3
"""Lastgenerator gegen einen llama-server (Testport 8190): Durchsatz vs. Parallelität.

Schickt Prompts aus einer JSONL-Datei (scripts/ctx_eval/build_prompts.py) so an den
Server, wie es die Pipeline tut (OpenAI-kompatibel, response_format json_schema,
enable_thinking=false, max_tokens/temperature aus der Zeile), mit C gleichzeitigen
Anfragen (ThreadPool wie pipeline.llm_processor._concurrent) und misst je Stufe:

  Anfragen/min · Prompt-Tokens/s · Generierungs-Tokens/s (aus `usage` der Antwort,
  Wanduhr des ganzen Blocks) · Latenz p50/p95 · Fehler · finish_reason=length ·
  max. Slot-Belegung (prompt+completion) · VRAM-Spitze (nvidia-smi, 0,5 s Raster).

  python scripts/ctx_eval/bench_parallel.py --prompts data/ctx_eval/prompts/gemma_stage6.jsonl \
      --concurrency 1,2,4,8 --n 48 --label gemma-c32k-p4 --out data/ctx_eval/results.jsonl

--mode embed für /v1/embeddings (Zeilen mit "input"). --burst schickt alle --n Anfragen
auf einmal (Grenzfall kleiner --kv-unified-Pool). Ergebnisse werden als JSON-Zeilen
angehängt; nichts davon berührt die DB oder den Produktivserver auf :8090.
"""
from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx


NO_SCHEMA = False  # --no-schema: Diagnose, ob die Grammatik (json_schema) den Durchsatz begrenzt


def pct(vals, p):
    if not vals:
        return None
    v = sorted(vals)
    return v[max(0, min(len(v) - 1, round(p / 100 * (len(v) - 1))))]


class VramSampler(threading.Thread):
    def __init__(self, interval=0.5):
        super().__init__(daemon=True)
        self.interval = interval
        self.peak = 0
        self.samples = []
        self._stop_evt = threading.Event()

    def _read(self):
        try:
            out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                                 capture_output=True, text=True, timeout=5).stdout.strip()
            return int(out.splitlines()[0])
        except Exception:  # noqa: BLE001
            return 0

    def run(self):
        while not self._stop_evt.is_set():
            v = self._read()
            self.samples.append(v)
            self.peak = max(self.peak, v)
            self._stop_evt.wait(self.interval)

    def stop(self):
        self._stop_evt.set()


def one_chat(client: httpx.Client, host: str, it: dict, timeout: float) -> dict:
    payload = {
        "model": "bench", "stream": False,
        "messages": ([{"role": "system", "content": it["system"]}] if it.get("system") else [])
        + [{"role": "user", "content": it["prompt"]}],
        "temperature": it.get("temperature", 0.0),
        "max_tokens": it.get("max_tokens", 1024),
        "chat_template_kwargs": {"enable_thinking": False},
    }
    if it.get("schema") and not NO_SCHEMA:
        payload["response_format"] = {"type": "json_schema", "json_schema": {
            "name": it.get("schema_name", "S"), "schema": it["schema"], "strict": True}}
    t0 = time.perf_counter()
    rec = {"id": it.get("id"), "stage": it.get("stage")}
    try:
        r = client.post(f"{host}/v1/chat/completions", json=payload, timeout=timeout)
        rec["status"] = r.status_code
        rec["latency"] = time.perf_counter() - t0
        if r.status_code != 200:
            rec["error"] = r.text[:200]
            return rec
        d = r.json()
        u = d.get("usage") or {}
        rec["prompt_tokens"] = u.get("prompt_tokens")
        rec["completion_tokens"] = u.get("completion_tokens")
        rec["finish_reason"] = d["choices"][0].get("finish_reason")
        tm = d.get("timings") or {}
        rec["prompt_ms"] = tm.get("prompt_ms")
        rec["predicted_ms"] = tm.get("predicted_ms")
        rec["cache_n"] = tm.get("cache_n")
        content = d["choices"][0]["message"].get("content") or ""
        rec["json_ok"] = _json_ok(content) if it.get("schema") else None
        rec["content"] = content[:6000]
        if it.get("label") is not None:
            rec["label_truth"] = it["label"]
    except Exception as e:  # noqa: BLE001
        rec["latency"] = time.perf_counter() - t0
        rec["error"] = repr(e)[:200]
    return rec


def _json_ok(content: str) -> bool:
    try:
        json.loads(content)
        return True
    except Exception:  # noqa: BLE001
        return False


def one_embed(client: httpx.Client, host: str, it: dict, timeout: float) -> dict:
    t0 = time.perf_counter()
    rec = {"id": it.get("id"), "stage": "emb"}
    try:
        r = client.post(f"{host}/v1/embeddings", json={"input": it["input"]}, timeout=timeout)
        rec["status"] = r.status_code
        rec["latency"] = time.perf_counter() - t0
        if r.status_code != 200:
            rec["error"] = r.text[:200]
            return rec
        d = r.json()
        rec["prompt_tokens"] = (d.get("usage") or {}).get("prompt_tokens")
        rec["completion_tokens"] = 0
        rec["dim"] = len(d["data"][0]["embedding"])
    except Exception as e:  # noqa: BLE001
        rec["latency"] = time.perf_counter() - t0
        rec["error"] = repr(e)[:200]
    return rec


def run_level(host, items, conc, mode, timeout, duration=0.0, ramp=0.0):
    """duration>0: Dauerlast — C Anfragen dauerhaft in Flug aus dem (zyklischen) Pool, bis die
    Zeit um ist; gewertet werden nur Anfragen, die VOR der Frist fertig wurden (steady state,
    kein Schweif einzelner Langläufer wie bei einem festen n)."""
    fn = one_embed if mode == "embed" else one_chat
    sampler = VramSampler(); sampler.start()
    t0 = time.perf_counter()
    with httpx.Client(limits=httpx.Limits(max_connections=conc + 4, max_keepalive_connections=conc + 4)) as client:
        if duration > 0:
            import itertools, threading as _th
            pool = itertools.cycle(items); lock = _th.Lock(); deadline = t0 + duration
            recs = []
            def worker():
                while time.perf_counter() < deadline:
                    with lock:
                        it = next(pool)
                    r = fn(client, host, it, timeout)
                    r["t_done"] = time.perf_counter()
                    with lock:
                        recs.append(r)
            threads = [_th.Thread(target=worker) for _ in range(conc)]
            for t in threads: t.start()
            for t in threads: t.join()
            # Anlaufphase (ramp) nicht werten: erst ab t0+ramp sind C Anfragen im Fluss UND
            # die ersten fertig — sonst zählt ein 75-s-Fenster bei 40 s Latenz fast nichts.
            recs = [r for r in recs if t0 + ramp < r["t_done"] <= deadline]
            wall = duration - ramp
        else:
            with ThreadPoolExecutor(max_workers=conc) as ex:
                recs = list(ex.map(lambda it: fn(client, host, it, timeout), items))
            wall = time.perf_counter() - t0
    sampler.stop(); sampler.join(timeout=2)
    ok = [r for r in recs if r.get("status") == 200 and not r.get("error")]
    lat = [r["latency"] for r in ok]
    ptok = sum(r.get("prompt_tokens") or 0 for r in ok)
    ctok = sum(r.get("completion_tokens") or 0 for r in ok)
    slot = [(r.get("prompt_tokens") or 0) + (r.get("completion_tokens") or 0) for r in ok]
    res = {
        "concurrency": conc, "n": len(recs) if duration else len(items), "ok": len(ok), "duration": duration, "ramp": ramp, "errors": len(recs) - len(ok),
        "wall_s": round(wall, 1), "req_per_min": round(len(ok) / wall * 60, 1) if wall else None,
        "prompt_tok_s": round(ptok / wall, 1), "gen_tok_s": round(ctok / wall, 1),
        "prompt_tokens_total": ptok, "gen_tokens_total": ctok,
        "lat_p50": round(pct(lat, 50), 2) if lat else None, "lat_p95": round(pct(lat, 95), 2) if lat else None,
        "lat_max": round(max(lat), 2) if lat else None,
        "slot_tokens_max": max(slot) if slot else None,
        "prompt_tokens_max": max((r.get("prompt_tokens") or 0) for r in ok) if ok else None,
        "gen_tokens_max": max((r.get("completion_tokens") or 0) for r in ok) if ok else None,
        "truncated": sum(1 for r in ok if r.get("finish_reason") == "length"),
        "json_bad": sum(1 for r in ok if r.get("json_ok") is False),
        "vram_peak_mib": sampler.peak, "vram_min_mib": min(sampler.samples) if sampler.samples else None,
        "error_samples": [r.get("error") for r in recs if r.get("error")][:3],
    }
    return res, recs


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="http://127.0.0.1:8190")
    ap.add_argument("--prompts", required=True)
    ap.add_argument("--concurrency", default="1,2,4,8")
    ap.add_argument("--n", type=int, default=48, help="Anfragen je Parallelitätsstufe")
    ap.add_argument("--offset", type=int, default=0, help="Startindex in der Prompt-Datei")
    ap.add_argument("--mode", choices=["chat", "embed"], default=None)
    ap.add_argument("--label", default="")
    ap.add_argument("--server_args", default="", help="nur zur Dokumentation in der Ergebniszeile")
    ap.add_argument("--out", default="data/ctx_eval/results.jsonl")
    ap.add_argument("--timeout", type=float, default=900)
    ap.add_argument("--burst", action="store_true", help="alle --n Anfragen gleichzeitig (Grenzfall)")
    ap.add_argument("--duration", type=float, default=0, help="Sekunden Dauerlast je Stufe statt fester Anzahl (steady state)")
    ap.add_argument("--ramp", type=float, default=0, help="Sekunden Anlauf, die bei --duration nicht gewertet werden")
    ap.add_argument("--no-schema", action="store_true", help="Diagnose: ohne response_format/Grammatik senden")
    ap.add_argument("--warmup", type=int, default=2, help="Anfragen vorab (Modell/Cache warm), nicht gewertet")
    ap.add_argument("--dump", default="", help="Einzelantworten als JSONL hierhin")
    a = ap.parse_args()
    global NO_SCHEMA
    NO_SCHEMA = a.no_schema

    items = [json.loads(l) for l in open(a.prompts) if l.strip()]
    mode = a.mode or ("embed" if items and "input" in items[0] else "chat")
    levels = [a.n] if a.burst else [int(x) for x in a.concurrency.split(",")]
    fn = one_embed if mode == "embed" else one_chat
    pos = a.offset
    if a.warmup:
        with httpx.Client() as c:
            for it in items[pos:pos + a.warmup]:
                fn(c, a.host, it, a.timeout)
        pos += a.warmup
    print(f"{a.label}  {Path(a.prompts).name}  mode={mode}  n/Stufe={a.n}")
    print(f"{'conc':>5} {'ok/n':>7} {'wall s':>7} {'req/min':>8} {'prompt t/s':>11} {'gen t/s':>8} "
          f"{'p50 s':>7} {'p95 s':>7} {'slot max':>8} {'trunc':>5} {'VRAM peak':>9}")
    out = Path(a.out); out.parent.mkdir(parents=True, exist_ok=True)
    for conc in levels:
        batch = items[pos:pos + a.n]
        if len(batch) < a.n:  # zyklisch auffüllen
            batch += items[:a.n - len(batch)]
        pos += a.n
        res, recs = run_level(a.host, batch if not a.duration else items, conc, mode, a.timeout, a.duration, a.ramp)
        res.update({"label": a.label, "prompts": Path(a.prompts).name, "mode": mode,
                    "server_args": a.server_args, "burst": a.burst,
                    "ts": time.strftime("%Y-%m-%dT%H:%M:%S")})
        print(f"{conc:>5} {res['ok']:>3}/{res['n']:<3} {res['wall_s']:>7} {res['req_per_min']:>8} "
              f"{res['prompt_tok_s']:>11} {res['gen_tok_s']:>8} {res['lat_p50']:>7} {res['lat_p95']:>7} "
              f"{res['slot_tokens_max']:>8} {res['truncated']:>5} {res['vram_peak_mib']:>9}"
              + (f"  ERR {res['errors']}: {res['error_samples'][:1]}" if res["errors"] else ""))
        with out.open("a") as f:
            f.write(json.dumps(res, ensure_ascii=False) + "\n")
        if a.dump:
            with open(a.dump, "a") as f:
                for r in recs:
                    r.update({"label": a.label, "concurrency": conc})
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
