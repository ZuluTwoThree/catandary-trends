#!/usr/bin/env python
"""Replay der deterministischen Pruefregeln ueber alle gespeicherten Dossiers.

Stufe 4/5 des Plans `docs/plan_dossier_agent_2026-09-18.md`: jede Regel-
aenderung wird gegen die vorhandenen Laeufe gemessen, bevor sie live geht.
Laeuft OHNE Modell — nur die reinen Textpruefungen aus
`pipeline.dossier_structure` ueber `dossiers.report_md` + `result.sources`:

  * Strukturbefunde (structure_findings, mit Quoten aus dem gespeicherten
    Protokoll, soweit vorhanden) und Faktenquote (fact_density)
  * Widerspruchs-Gate (contradiction_findings) — mechanisch, plus die
    Leser-Befunde aus dem Protokoll (coherence/"contradict")
  * Kalender mit `today` = Datum des Laufs: wie viele Zeilen trugen einen
    schon vergangenen Termin
  * Subjektabgleich per Stamm: welche der gespeicherten "subject"-Befunde
    (cite_findings_after) wuerden heute akzeptiert
  * Streichungen: wie viele gestrichene Saetze standen in einer Kernsektion
    oder nannten einen Themenbegriff (bekaemen jetzt zwei Reparaturen) und
    wie viele waren Fuellsaetze

Die alten Regeln lassen sich nicht mehr ausfuehren; gedruckt werden die
heutigen Zaehlungen und daneben die im Protokoll gespeicherten (findings_after
usw.). Aufruf: `.venv/bin/python scripts/dossier_replay.py [--slug S] [--json]`.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import dossier_structure as ds          # noqa: E402
from pipeline.db import get_connection                 # noqa: E402

ENT_SECTIONS = tuple(dict.fromkeys(ds.CORE_SECTIONS + ("regip",)))


def _load_rows(slug: str | None) -> list[dict]:
    with get_connection() as conn:
        if slug:
            rows = conn.execute("SELECT id, slug, version, created_at, report_md, result FROM dossiers "
                                "WHERE slug = ? ORDER BY id", (slug,)).fetchall()
        else:
            rows = conn.execute("SELECT id, slug, version, created_at, report_md, result FROM dossiers "
                                "ORDER BY id").fetchall()
    out = []
    for r in rows:
        res = r["result"]
        if isinstance(res, str):
            try:
                res = json.loads(res)
            except ValueError:
                res = {}
        out.append({"id": r["id"], "slug": r["slug"], "version": r["version"],
                    "created_at": r["created_at"], "report_md": r["report_md"] or "",
                    "result": res or {}})
    return out


def _topic_terms(row: dict) -> list[str]:
    from scripts.corpus_research import anchor_terms
    res = row["result"]
    terms = anchor_terms(row["slug"].replace("-", " "), cap=6)
    for t in anchor_terms(str(res.get("question") or ""), cap=6):
        if t not in terms:
            terms.append(t)
    for r in res.get("landscape") or []:
        for t in anchor_terms(str(r.get("name") or ""), cap=3):
            if t not in terms:
                terms.append(t)
    return terms


def _rank_of(sources: list[dict]):
    by_id = {str(s.get("id")): s for s in sources}

    def rank(x):
        s = by_id.get(str(x)) if not isinstance(x, dict) else x
        if s is None:
            return 2
        r = s.get("rank")
        return 2 if r is None else int(r)
    return rank


def replay_one(row: dict) -> dict:
    res = row["result"]
    report = str(res.get("report") or row["report_md"] or "")
    sources = list(res.get("sources") or [])
    lang = str(res.get("lang") or "en")
    st = res.get("structure") or {}
    terms = _topic_terms(row)
    run_day = row["created_at"].date() if hasattr(row["created_at"], "date") else None
    year_floor = run_day.year if run_day else None

    density = ds.fact_density(report, sources, lang, rank_of=_rank_of(sources))
    findings = ds.structure_findings(
        report, lang, year_floor=year_floor, density=density, topic_terms=terms,
        calendar_min=st.get("calendar_min"), actor_min=st.get("actor_min"),
        watch_min=st.get("watch_min"), today=run_day)
    contra_mech = ds.contradiction_findings(report, lang, terms)
    contra_reader = ds.contradiction_from_reader(st.get("reader_after") or st.get("reader"), lang)
    cal_run = ds.calendar_rows(report, lang, year_floor, terms, today=run_day)
    cal_plain = ds.calendar_rows(report, lang, year_floor, terms)

    # Subjektabgleich: gespeicherte "subject"-Befunde gegen die Seite von heute
    by_url = {str(s.get("url")): s for s in sources if s.get("url")}
    subj_stored = subj_now_ok = 0
    for e in st.get("cite_findings_after") or []:
        if e.get("kind") != "subject":
            continue
        subj_stored += 1
        page = by_url.get(str(e.get("url") or ""), {})
        hay = " ".join(str(page.get(k) or "") for k in ("text", "title", "snippet", "date"))
        if hay.strip() and not ds.unverified_subjects(ds.prose(str(e.get("sentence") or "")), hay):
            subj_now_ok += 1

    # Streichungen: Kernsektion / Themenbezug gegen Fuellsatz
    core_sents = {s for _k, s in ds._section_sentences(report, lang, ENT_SECTIONS)}
    dropped_core = dropped_filler = 0
    for e in st.get("cite_findings_after") or []:
        if e.get("kind") in ("weaksource", "weakclaim"):
            continue
        sent = str(e.get("sentence") or "")
        if not sent:
            continue
        is_core = (e.get("section") in ENT_SECTIONS or sent in core_sents
                   or ds._row_on_topic(sent, terms))
        if is_core:
            dropped_core += 1
        else:
            dropped_filler += 1

    return {
        "id": row["id"], "slug": row["slug"], "version": row["version"],
        "run_day": str(run_day) if run_day else None,
        "words": ds.count_words(ds.body_text(report)),
        "density": round(float(density.get("per100") or 0.0), 2),
        "findings_now": len(findings),
        "findings_stored": len(st.get("findings_after") or []),
        "contradictions_mechanical": len(contra_mech),
        "contradictions_reader": len(contra_reader),
        "contradiction_texts": [c["text"][:200] for c in contra_mech],
        "calendar_ok_run_day": cal_run["ok"], "calendar_passed_run_day": cal_run.get("passed", 0),
        "calendar_ok_plain": cal_plain["ok"],
        "subject_findings_stored": subj_stored, "subject_now_accepted": subj_now_ok,
        "dropped_stored": int(st.get("dropped_sentences") or 0),
        "dropped_core": dropped_core, "dropped_filler": dropped_filler,
        "reader_answers": (st.get("reader_after") or {}).get("answers_question"),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--slug", help="nur diese Serie")
    ap.add_argument("--json", action="store_true", help="JSON statt Tabelle")
    args = ap.parse_args(argv)
    rows = _load_rows(args.slug)
    out = [replay_one(r) for r in rows]
    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return 0
    print(f"{'id':>3} {'slug':<34} {'v':>2} {'run':<10} {'w':>5} {'dens':>5} {'find':>4}/{'st':<3} "
          f"{'con':>3} {'rd':>2} {'cal':>3} {'pass':>4} {'subj':>4} {'drop':>4} {'core':>4} {'fill':>4}")
    for r in out:
        print(f"{r['id']:>3} {r['slug'][:34]:<34} {r['version']:>2} {r['run_day'] or '':<10} {r['words']:>5} "
              f"{r['density']:>5} {r['findings_now']:>4}/{r['findings_stored']:<3} "
              f"{r['contradictions_mechanical']:>3} {r['contradictions_reader']:>2} "
              f"{r['calendar_ok_run_day']:>3} {r['calendar_passed_run_day']:>4} "
              f"{r['subject_now_accepted']:>2}/{r['subject_findings_stored']:<2} "
              f"{r['dropped_stored']:>4} {r['dropped_core']:>4} {r['dropped_filler']:>4}")
    n = len(out)
    print()
    print(f"runs: {n}")
    print(f"runs with a mechanical contradiction finding: "
          f"{sum(1 for r in out if r['contradictions_mechanical'])}"
          f" ({sum(r['contradictions_mechanical'] for r in out)} finding(s))")
    print(f"runs with a reader contradiction finding: "
          f"{sum(1 for r in out if r['contradictions_reader'])}")
    print(f"calendar rows with a date already passed on the run day: "
          f"{sum(r['calendar_passed_run_day'] for r in out)} in "
          f"{sum(1 for r in out if r['calendar_passed_run_day'])} run(s)")
    print(f"stored subject findings: {sum(r['subject_findings_stored'] for r in out)}, "
          f"accepted by the stem rule now: {sum(r['subject_now_accepted'] for r in out)}")
    dc, df = sum(r['dropped_core'] for r in out), sum(r['dropped_filler'] for r in out)
    print(f"dropped sentences (stored cite_findings_after, without rank marks): "
          f"{dc + df} — core/on-topic {dc}, filler {df}")
    for r in out:
        for t in r["contradiction_texts"]:
            print(f"  [{r['id']} {r['slug']} v{r['version']}] {t}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
