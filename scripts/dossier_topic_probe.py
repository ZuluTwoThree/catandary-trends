"""Themenneutralitaets-Probe fuer den Dossier-Sweep — ohne 27B, ohne Lauf.

Zeigt fuer ein beliebiges Thema, welche Suchrichtungen das Themenprofil
(R14-3) erzeugt, und auf Wunsch, was Brave darauf liefert und welche
Kalender-Kandidaten aus den gelesenen Treffern entstehen. Das Profil wird
gegen den gerade laufenden llama-server gerechnet (im Ruhezustand das
8B-208k) — es geht um die Mechanik, nicht um die Berichtsqualitaet.

    .venv/bin/python scripts/dossier_topic_probe.py "solid-state batteries"
    .venv/bin/python scripts/dossier_topic_probe.py "vertical farming" --brave --read 6
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline import llamacpp_client  # noqa: E402
from scripts import corpus_research as cr  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("topic")
    ap.add_argument("--question", default=None)
    ap.add_argument("--brave", action="store_true", help="Anfragen an Brave senden")
    ap.add_argument("--read", type=int, default=0,
                    help="so viele Treffer der Termin-Anfragen lesen und "
                         "Kalender-Kandidaten zeigen")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.WARNING)

    question = args.question or (
        f"Where does {args.topic} stand today, and what should a mid-sized "
        f"European company do about it in the next 12 months?")
    try:
        served = [llamacpp_client.served_model_id() or ""]
    except Exception:                                  # noqa: BLE001
        served = []
    model = served[0] if served and served[0] else cr.MODEL
    cr.MODEL = model
    neighbours = cr.corpus_neighbours(args.topic)
    profile = cr.topic_profile(args.topic, question, neighbours)
    from pipeline.dossier_quant import normalize_topic
    phrase = (normalize_topic(args.topic) or args.topic).strip()
    terms = cr.anchor_terms(args.topic)
    pq = cr.profile_queries(profile, phrase, terms, question)

    out = {"topic": args.topic, "model": model, "neighbours": neighbours[:6],
           "profile": profile.model_dump() if profile else None,
           "queries": {k: [q.format(t=phrase, e="<actor>") for q in v]
                       for k, v in pq.items()}}
    if args.brave:
        hits = {}
        for q in pq["catalyst"][:4]:
            qq = q.format(t=phrase)
            hits[qq] = [h["title"][:80] for h in cr.brave_search(qq, count=4)]
        out["brave_catalyst_hits"] = hits
        if args.read:
            srcs, n = [], 0
            for qq, _ in hits.items():
                for h in cr.brave_search(qq, count=4):
                    if n >= args.read:
                        break
                    txt, st = cr.fetch_web_page_status(h["url"])
                    if st == "fetched":
                        srcs.append({"id": f"C{n}", "fetched": True, "text": txt,
                                     "url": h["url"]})
                        n += 1
            cands = cr.calendar_candidates(
                [], srcs, terms, [], dt.date.today().year,
                today=dt.date.today())
            out["calendar_candidates"] = [
                {"when": c["when"], "statement": c["statement"][:120], "id": c["id"]}
                for c in cands[:10]]
            out["read_pages"] = [s["url"] for s in srcs]
    if args.json:
        print(json.dumps(out, indent=2, ensure_ascii=False))
    else:
        print(f"Thema: {args.topic}  (Modell: {model})")
        print("Nachbarn:", "; ".join(out["neighbours"]))
        if profile:
            print(f"Feld: {profile.field}")
            print("Regulatoren:", profile.regulators)
            print("Ereignistypen:", profile.event_types)
            print("Saatgut:", profile.actor_seeds)
        for k, v in out["queries"].items():
            print(f"\n[{k}] {len(v)}")
            for q in v:
                print("  ", q)
        for k in ("brave_catalyst_hits", "calendar_candidates"):
            if k in out:
                print(f"\n== {k} ==")
                print(json.dumps(out[k], indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
