#!/usr/bin/env python3
"""results.jsonl → Markdown-Tabelle (eine Zeile je Messstufe), optional gefiltert nach Label-Präfix."""
import json, sys
prefix = sys.argv[1] if len(sys.argv) > 1 else ""
path = sys.argv[2] if len(sys.argv) > 2 else "data/ctx_eval/results.jsonl"
rows = [json.loads(l) for l in open(path) if l.strip()]
rows = [r for r in rows if r["label"].startswith(prefix)]
print("| Label | Prompts | Modus | conc | ok/n | Anfragen/min | Prompt-Tok/s | Gen-Tok/s | p50 s | p95 s | Slot max | trunc | Fehler | VRAM-Spitze MiB |")
print("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
for r in rows:
    mode = (f"Dauer {r['duration']:.0f}s (Anlauf {r.get('ramp',0):.0f}s)" if r.get("duration") else
            ("Burst" if r.get("burst") else f"n={r['n']}"))
    print(f"| {r['label']} | {r['prompts'].replace('.jsonl','')} | {mode} | {r['concurrency']} | {r['ok']}/{r['n']} | "
          f"{r['req_per_min']} | {r['prompt_tok_s']} | {r['gen_tok_s']} | {r['lat_p50']} | {r['lat_p95']} | "
          f"{r['slot_tokens_max']} | {r['truncated']} | {r['errors']} | {r['vram_peak_mib']} |")
