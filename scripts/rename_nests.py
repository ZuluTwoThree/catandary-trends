#!/usr/bin/env python3
"""Name emerging pockets whose naming step failed — without recomputing the run.

The naming step of pipeline/emerging_snapshot.py is the layer's only GPU step and is
never fatal: when the handover to the naming model fails, the pockets keep their tag
labels and `llm_label_note` says "handover failed: …" (29.09.: ECO, DESIGN and the patent
tier, 49 pockets, one Gemma start that took longer than 240 s). This script names exactly
those pockets afterwards, in ONE handover, with the same prompt and the same checks
(pipeline/nest_naming.name_nest) and the run's existing names counted for uniqueness.

    .venv/bin/python scripts/rename_nests.py --runs 60,61,66            # dry run: lists what it would name
    .venv/bin/python scripts/rename_nests.py --runs 60,61,66 --apply

Names come from the stored representative titles and top tags (the run itself names from
the same titles). Pockets that failed the name CHECK (one word, duplicate, a word not in
the documents) are left alone unless --all-unnamed: with fixed seeds they would fail again.
Afterwards the resting state is restored — the handover leaves llama-server stopped (#116).
"""
from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import db  # noqa: E402
from pipeline.nest_naming import NAME_MODEL, name_nest  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("rename_nests")


def _json(v):
    if isinstance(v, str):
        try:
            return json.loads(v)
        except ValueError:
            return []
    return v or []


def unit_active() -> bool:
    r = subprocess.run(["systemctl", "--user", "is-active", "llama-server.service"],
                       capture_output=True, text=True)
    return r.stdout.strip() == "active"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--runs", required=True, help="emerging_runs ids, comma list")
    ap.add_argument("--all-unnamed", action="store_true",
                    help="also retry pockets that failed the name check (not only failed handovers)")
    ap.add_argument("--redo", action="store_true",
                    help="name EVERY pocket of the given runs again (e.g. after a naming fix)")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    runs = [int(x) for x in args.runs.split(",") if x.strip()]
    with db.get_connection() as c:
        rows = [dict(r) for r in c.execute(
            "SELECT id, run_id, label, llm_label, llm_label_note, rep_titles, top_tags "
            "FROM emerging_nests WHERE run_id = ANY(?) ORDER BY run_id, id", (runs,)).fetchall()]
    used = {}
    todo = []
    for r in rows:
        used.setdefault(r["run_id"], set())
        if args.redo:
            todo.append(r)
        elif r["llm_label"]:
            used[r["run_id"]].add(r["llm_label"].lower())
        elif args.all_unnamed or (r["llm_label_note"] or "").startswith("handover failed"):
            todo.append(r)
    log.info("%d pockets to name in runs %s", len(todo), runs)
    if not args.apply or not todo:
        for r in todo[:10]:
            log.info("  #%d run %d  %s", r["id"], r["run_id"], r["label"])
        return 0
    was_active = unit_active()
    from pipeline.gpu_handover import content_gen_on_llamacpp
    results = []
    try:
        with content_gen_on_llamacpp(NAME_MODEL):
            for i, r in enumerate(todo, 1):
                name, note = name_nest(_json(r["rep_titles"]), _json(r["top_tags"]), model=NAME_MODEL)
                if name and name.lower() in used[r["run_id"]]:
                    name, note = None, "duplicate of another pocket"
                if name:
                    used[r["run_id"]].add(name.lower())
                results.append((r["id"], name, note))
                if i % 10 == 0:
                    log.info("  named %d/%d", i, len(todo))
    finally:
        if was_active and not unit_active():
            log.info("restoring the resting state (llama-server.service was active before)")
            subprocess.run(["systemctl", "--user", "reset-failed", "llama-server.service"], check=False)
            subprocess.run(["systemctl", "--user", "start", "llama-server.service"], check=False)
    with db.get_connection() as c:
        for nid, name, note in results:
            c.execute("UPDATE emerging_nests SET llm_label = ?, llm_label_note = ? WHERE id = ?",
                      (name, note, nid))
    named = sum(1 for _, n, _ in results if n)
    log.info("named %d of %d; %d kept their tag labels", named, len(results), len(results) - named)
    for nid, name, note in results:
        log.info("  #%d %s", nid, name or f"(kept tag label: {note})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
