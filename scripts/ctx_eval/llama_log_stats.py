#!/usr/bin/env python3
"""Kontext- und Parallelitäts-Statistik aus dem llama-server-Log (/tmp/llama-server.log).

Das Log kennt keine Wanduhr, nur die Laufzeit seit Serverstart (MM.SS.mmm.uuu).
Jede Zeile "load_model: loading model '<gguf>'" eröffnet ein Segment; die
Segmente werden über `journalctl --user -u llama-server.service` (Startzeiten
der Unit) datiert, wenn die Anzahl passt, sonst nur nummeriert.

Je Segment / Modell:
  - release-Zeilen: n_tokens (Prompt + Generierung im Slot) → n, Mittel, Median, p95, p99, Max, truncated
  - print_timing:   prompt eval "/ N tokens" und eval "/ N tokens" → Prompt- und Generierungslänge getrennt
  - Parallelität:   launch_slot_ → release je Slot-ID; maximale und mittlere Zahl gleichzeitig belegter Slots
  - truncated-Fälle: Prompt-/Generierungslänge, Segment, Laufzeitpunkt

Aufruf: python scripts/ctx_eval/llama_log_stats.py [/tmp/llama-server.log] [--json out.json]
"""
from __future__ import annotations

import json
import re
import statistics
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

TS_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)\.(\d+) ")
LOAD_RE = re.compile(r"load_model: loading model '([^']+)'")
INIT_RE = re.compile(r"initializing, n_slots = (\d+), n_ctx_slot = (\d+), kv_unified = '(\w+)'")
LAUNCH_RE = re.compile(r"launch_slot_: id +(\d+) \| task (\d+) \| processing task")
RELEASE_RE = re.compile(r"release: id +(\d+) \| task (\d+) \| stop processing: n_tokens = (\d+), truncated = (\d)")
PROMPT_RE = re.compile(r"print_timing: id +(\d+) \| task (\d+) \| prompt eval time = +([\d.]+) ms / +(\d+) tokens")
EVAL_RE = re.compile(r"print_timing: id +(\d+) \| task (\d+) \| +eval time = +([\d.]+) ms / +(\d+) tokens")


def ts_seconds(line: str) -> float | None:
    m = TS_RE.match(line)
    if not m:
        return None
    mi, s, ms, us = (int(x) for x in m.groups())
    return mi * 60 + s + ms / 1000 + us / 1e6


def pct(vals, p):
    if not vals:
        return None
    vals = sorted(vals)
    k = max(0, min(len(vals) - 1, round(p / 100 * (len(vals) - 1))))
    return vals[k]


def summarize(vals):
    if not vals:
        return {"n": 0}
    return {"n": len(vals), "mean": round(statistics.fmean(vals), 1),
            "median": statistics.median(vals), "p95": pct(vals, 95),
            "p99": pct(vals, 99), "max": max(vals)}


def unit_starts() -> list[str]:
    """Wanduhr-Startzeiten der Unit aus dem Journal (älteste zuerst)."""
    try:
        out = subprocess.run(
            ["journalctl", "--user", "-u", "llama-server.service", "--no-pager",
             "-o", "short-iso", "--grep", "Started llama"],
            capture_output=True, text=True, timeout=60).stdout
    except Exception:
        return []
    return [ln.split()[0] for ln in out.splitlines() if ln and ln[0].isdigit()]


def main(argv):
    path = Path(argv[1]) if len(argv) > 1 and not argv[1].startswith("--") else Path("/tmp/llama-server.log")
    json_out = None
    if "--json" in argv:
        json_out = Path(argv[argv.index("--json") + 1])

    segments: list[dict] = []
    seg = None
    # offene Tasks je Segment: (slot, task) -> launch_ts
    for line in open(path, errors="replace"):
        m = LOAD_RE.search(line)
        if m:
            seg = {"model": Path(m.group(1)).name, "n_slots": None, "n_ctx_slot": None,
                   "kv_unified": None, "releases": [], "prompt_tok": {}, "gen_tok": {},
                   "open": {}, "busy_samples": [], "max_busy": 0, "trunc": [], "prompt_full": [],
                   "prompt_ms": {}, "eval_ms": {}, "last_ts": 0.0}
            segments.append(seg)
            continue
        if seg is None:
            continue
        m = INIT_RE.search(line)
        if m:
            seg["n_slots"], seg["n_ctx_slot"], seg["kv_unified"] = int(m.group(1)), int(m.group(2)), m.group(3)
            continue
        m = LAUNCH_RE.search(line)
        if m:
            t = ts_seconds(line)
            seg["open"][(int(m.group(1)), int(m.group(2)))] = t
            busy = len(seg["open"])
            seg["max_busy"] = max(seg["max_busy"], busy)
            seg["busy_samples"].append(busy)
            continue
        m = PROMPT_RE.search(line)
        if m:
            key = (int(m.group(1)), int(m.group(2)))
            seg["prompt_tok"][key] = int(m.group(4))
            seg["prompt_ms"][key] = float(m.group(3))
            continue
        m = EVAL_RE.search(line)
        if m:
            key = (int(m.group(1)), int(m.group(2)))
            seg["gen_tok"][key] = int(m.group(4))
            seg["eval_ms"][key] = float(m.group(3))
            continue
        m = RELEASE_RE.search(line)
        if m:
            key = (int(m.group(1)), int(m.group(2)))
            n_tok, trunc = int(m.group(3)), int(m.group(4))
            t = ts_seconds(line) or 0.0
            seg["last_ts"] = max(seg["last_ts"], t)
            seg["releases"].append(n_tok)
            # Volle Prompt-Länge = Slot-Tokens minus Generierung (print_timing "prompt eval"
            # zählt nur NEU ausgewertete Tokens, Cache-Treffer fehlen dort).
            g = seg["gen_tok"].get(key)
            if g is not None:
                seg["prompt_full"].append(n_tok - g)
            launched = seg["open"].pop(key, None)
            if trunc:
                seg["trunc"].append({"slot": key[0], "task": key[1], "n_tokens": n_tok,
                                     "prompt_tokens": seg["prompt_tok"].get(key),
                                     "gen_tokens": seg["gen_tok"].get(key),
                                     "t_release_s": round(t), "t_launch_s": round(launched) if launched else None})

    starts = unit_starts()
    dated = len(starts) == len(segments)
    per_model: dict[str, dict] = defaultdict(lambda: {"releases": [], "prompt": [], "gen": [], "prompt_full": [], "trunc": 0,
                                                     "segments": 0, "max_busy": 0, "slot_cfgs": set()})
    seg_rows = []
    for i, s in enumerate(segments):
        pm = per_model[s["model"]]
        pm["releases"] += s["releases"]
        pm["prompt"] += list(s["prompt_tok"].values())
        pm["gen"] += list(s["gen_tok"].values())
        pm["prompt_full"] += s["prompt_full"]
        pm["trunc"] += len(s["trunc"])
        pm["segments"] += 1
        pm["max_busy"] = max(pm["max_busy"], s["max_busy"])
        pm["slot_cfgs"].add((s["n_slots"], s["n_ctx_slot"], s["kv_unified"]))
        busy_mean = round(statistics.fmean(s["busy_samples"]), 1) if s["busy_samples"] else 0
        seg_rows.append({"seg": i, "start": starts[i] if dated else None, "model": s["model"],
                         "n_slots": s["n_slots"], "n_ctx_slot": s["n_ctx_slot"], "kv_unified": s["kv_unified"],
                         "requests": len(s["releases"]), "max_busy": s["max_busy"], "busy_mean_at_launch": busy_mean,
                         "n_tokens_max": max(s["releases"]) if s["releases"] else None,
                         "prompt_max": max(s["prompt_tok"].values()) if s["prompt_tok"] else None,
                         "gen_max": max(s["gen_tok"].values()) if s["gen_tok"] else None,
                         "runtime_min": round(s["last_ts"] / 60), "truncated": s["trunc"]})

    print(f"Log: {path}  Segmente: {len(segments)}  Unit-Starts im Journal: {len(starts)}  datiert: {dated}\n")
    print("== je Modell ==")
    for model, pm in per_model.items():
        print(f"\n{model}  (Segmente {pm['segments']}, Slot-Konfigurationen {sorted(pm['slot_cfgs'])})")
        print("  n_tokens (Slot gesamt):", summarize(pm["releases"]))
        print("  prompt tokens (voll) :", summarize(pm["prompt_full"]))
        print("  prompt neu evaluiert :", summarize(pm["prompt"]))
        print("  gen tokens           :", summarize(pm["gen"]))
        print(f"  truncated: {pm['trunc']}   max gleichzeitig belegte Slots: {pm['max_busy']}")
    print("\n== je Segment ==")
    for r in seg_rows:
        print(f"  [{r['seg']:2}] {r['start'] or '?':25} {r['model'][:38]:38} slots={r['n_slots']}x{r['n_ctx_slot']} "
              f"uni={r['kv_unified']} req={r['requests']:6} busy_max={r['max_busy']:2} busy_mean={r['busy_mean_at_launch']:5} "
              f"ntok_max={r['n_tokens_max']} prompt_max={r['prompt_max']} gen_max={r['gen_max']} run={r['runtime_min']}min"
              + (f" TRUNC={len(r['truncated'])}" if r["truncated"] else ""))
    print("\n== truncated ==")
    for r in seg_rows:
        for t in r["truncated"]:
            print(f"  seg {r['seg']} {r['start'] or ''} {r['model'][:30]} slot {t['slot']} task {t['task']}: "
                  f"n_tokens={t['n_tokens']} prompt={t['prompt_tokens']} gen={t['gen_tokens']} "
                  f"launch={t['t_launch_s']}s release={t['t_release_s']}s")
    if json_out:
        out = {"segments": seg_rows, "per_model": {m: {"n_tokens": summarize(p["releases"]),
                                                       "prompt": summarize(p["prompt"]), "prompt_full": summarize(p["prompt_full"]), "gen": summarize(p["gen"]),
                                                       "truncated": p["trunc"], "max_busy": p["max_busy"],
                                                       "slot_cfgs": sorted(p["slot_cfgs"])} for m, p in per_model.items()}}
        json_out.write_text(json.dumps(out, indent=1, default=str))
        print(f"\nJSON → {json_out}")


if __name__ == "__main__":
    main(sys.argv)
