#!/usr/bin/env python3
"""Review-Agent (Test): prueft gehaltene Drafts auf aequivalente Zahlen.

  scripts/review_agent.py                 Dry-Run ueber alle Holds (Confidence >= 0.85, ungerichtet)
  scripts/review_agent.py --limit 20      nur die 20 juengsten
  scripts/review_agent.py --ids 1794582,1794534
  scripts/review_agent.py --apply         aequivalente Drafts veroeffentlichen (review_reason 'agent:equivalent …')

Braucht den llama-server auf :8090 (nimmt das geladene Modell). Bericht:
data/review_agent_last.json. Exit 0; 3 ohne Server.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.review_agent import REPORT_PATH, run  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--ids", help="kommagetrennte Trend-IDs")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--model", help="Modellname fuer den Request (Default: das geladene)")
    ap.add_argument("-q", "--quiet", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.WARNING if args.quiet else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    for noisy in ("httpx", "httpcore", "pipeline.llamacpp_client"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    ids = [int(x) for x in args.ids.split(",")] if args.ids else None
    r = run(limit=args.limit, ids=ids, apply=args.apply, model=args.model)
    print(f'\n{"DRY-RUN" if r["dry_run"] else "APPLY"} · Modell {r["model"]} · geprüft {r["checked"]} · '
          f'äquivalent {r["equivalent"]} · bleibt beim Menschen {r["human"]} · veröffentlicht {r["published"]}')
    print(f'{"id":>8}  {"Entscheid":10} {"Quelle":24} Begründung')
    for it in r["items"]:
        print(f'{it["id"]:>8}  {it["decision"]:10} {(it["source_name"] or "")[:24]:24} {it["why"][:150]}')
    print(f"\nBericht: {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
