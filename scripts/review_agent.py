#!/usr/bin/env python3
"""Review-Agent (Test): prueft gehaltene Drafts auf aequivalente Zahlen.

  scripts/review_agent.py                 Dry-Run ueber alle Holds (Confidence >= 0.85, ungerichtet)
  scripts/review_agent.py --limit 20      nur die 20 juengsten
  scripts/review_agent.py --ids 1794582,1794534
  scripts/review_agent.py --apply         aequivalente UND reparierte Drafts veroeffentlichen
  scripts/review_agent.py --no-repair     nur pruefen, keine Namen umschreiben
  scripts/review_agent.py --handover      llama-server selbst auf das Content-Gen-Modell
                                          umhaengen und danach den Ruhezustand wiederherstellen
                                          (so laeuft der Agent im Nachtlauf, Stage 11)

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
    ap.add_argument("--no-repair", action="store_true", help="nur pruefen, nichts umschreiben")
    ap.add_argument("--handover", action="store_true",
                    help="GPU-Handover auf das Content-Gen-Modell selbst machen (Nachtlauf)")
    ap.add_argument("-q", "--quiet", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.WARNING if args.quiet else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    for noisy in ("httpx", "httpcore", "pipeline.llamacpp_client"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    ids = [int(x) for x in args.ids.split(",")] if args.ids else None
    if args.handover:
        # Stage 11 des Nachtlaufs: der Ruhezustand traegt das 8B, geprueft wird
        # aber auf dem Content-Gen-Modell (es hat die Aequivalenz-Faelle in der
        # Messung vom 22.09. entschieden). Der Handover haengt start-active.sh um,
        # startet den Server und stellt den vorigen Zustand beim Verlassen wieder her.
        from pipeline import gpu_handover
        from pipeline.config import STAGE5_MODEL
        was_active = _llama_unit_active()
        with gpu_handover.content_gen_on_llamacpp(STAGE5_MODEL):
            r = run(limit=args.limit, ids=ids, apply=args.apply, model=args.model,
                    no_repair=args.no_repair)
        _restore_resting_server(was_active)
    else:
        r = run(limit=args.limit, ids=ids, apply=args.apply, model=args.model, no_repair=args.no_repair)
    print(f'\n{"DRY-RUN" if r["dry_run"] else "APPLY"} · Modell {r["model"]} · geprüft {r["checked"]} · '
          f'äquivalent {r["equivalent"]} · repariert {r.get("repaired", 0)} · '
          f'bleibt beim Menschen {r["human"]} · veröffentlicht {r["published"]}')
    print(f'{"id":>8}  {"Entscheid":10} {"Quelle":24} Begründung')
    for it in r["items"]:
        print(f'{it["id"]:>8}  {it["decision"]:10} {(it["source_name"] or "")[:24]:24} {it["why"][:150]}')
    props = [(it["id"], p) for it in r["items"] for p in it.get("proposals", [])]
    if props:
        print(f'\nVorschläge für dich ({len(props)}) — der Agent entscheidet sie nicht:')
        for tid, p in props[:20]:
            line = f'  {tid:>8}  {p["kind"]:14} {p["what"][:40]:40}'
            line += f' → {p["to"][:40]}' if p.get("to") else ""
            print(line + f'   {p["note"][:60]}')
        if len(props) > 20:
            print(f"  … {len(props) - 20} weitere im Bericht")
    print(f"\nBericht: {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
