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
  * Zahlenpruefung (Runde 28): jeder gespeicherte "figure"-Befund (Satz,
    Tokens, Seite) wird mit der heutigen Regel neu bewertet — welche Tokens
    bleiben unbelegt, und welche Regel die uebrigen rettet (Formatvariante,
    Bezeichner, eigener Messblock, Artikelschnitt im Rechtstext); dazu die
    Einordnung, ob ein noch offenes Token im vollen gecachten Seitentext
    jenseits der Speicherkappe steht

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


def _measured_text(res: dict) -> str:
    """Eigener Messblock des Laufs aus dem gespeicherten Ergebnis: Korpus-
    Evidenz (rendered_md) + die Nadeln der Messung (Skalare)."""
    parts = [str(((res.get("corpus_evidence") or {}).get("rendered_md")) or "")]
    try:
        inv = ds.measure_inventory(res.get("quant") or {}, res.get("corpus_stats") or {})
        parts.append(" ".join(ds._flatten_needles(inv["usable"]) + ds._flatten_needles(inv["blocked"])))
    except Exception:                                               # noqa: BLE001
        pass
    return "\n".join(p for p in parts if p)


def _cached_page(url: str) -> str:
    try:
        from pipeline import web_cache
        hit = web_cache.cache_get("page", web_cache.make_key("page", url))
        return str(hit.get("text") or "") if isinstance(hit, dict) else ""
    except Exception:                                               # noqa: BLE001
        return ""


def figure_replay(st: dict, sources: list[dict], measured: str) -> dict:
    """Gespeicherte figure-Befunde (vor und nach dem Neuwurf, je Satz+Seite
    einmal) mit der heutigen `unverified_tokens`-Regel neu bewertet."""
    from pipeline import legal_text
    by_url: dict = {}
    for s_ in sources:
        if s_.get("origin"):
            by_url.setdefault(s_["origin"], s_)
    for s_ in sources:
        by_url[s_.get("url")] = s_
    catalog = ds.catalog_text(sources)
    out = {"findings": 0, "tokens": 0, "still": 0, "still_findings": 0,
           "rescued": {"format": 0, "designator": 0, "measured": 0, "legal": 0},
           "beyond_cap": 0, "absent": 0, "items": []}
    seen: set = set()
    for stage in ("cite_findings", "cite_findings_after"):
        for e in st.get(stage) or []:
            if e.get("kind") != "figure":
                continue
            key = (e.get("sentence"), e.get("url"))
            if key in seen:
                continue
            seen.add(key)
            src = by_url.get(e.get("url")) or {}
            hay = " ".join(str(src.get(k) or "") for k in ("text", "title", "snippet", "date"))
            claim = ds.prose(str(e.get("sentence") or ""))
            stored = [str(t) for t in (e.get("tokens") or [])]
            out["findings"] += 1
            out["tokens"] += len(stored)
            # Regeln einzeln, in Reihenfolge
            fmt = set(ds.unverified_tokens(claim, hay))
            desig = set(ds.unverified_tokens(claim, hay, catalog=catalog))
            meas = set(ds.unverified_tokens(claim, hay, measured, catalog))
            remaining = set(meas)
            legal_hit = False
            url = str(e.get("url") or "")
            if remaining and legal_text.is_legal_host(url):
                full = legal_text.cached_full_text(url)
                if full and len(full) > len(str(src.get("text") or "")):
                    kept, _labels = legal_text.reslice_for(url, ds._reslice_terms(claim), full_text=full)
                    if kept:
                        again = set(ds.unverified_tokens(claim, hay + "\n" + kept, measured, catalog))
                        if again < remaining:
                            legal_hit = True
                            remaining = again
            page_full = _cached_page(url) if remaining else ""
            desig_tokens = {ds._norm_token(x) for x in ds._designator_tokens(claim, catalog)}
            for t in stored:
                if t not in fmt and ds._norm_token(t) in desig_tokens:
                    out["rescued"]["designator"] += 1
                    why = "designator"
                elif t not in fmt:
                    out["rescued"]["format"] += 1
                    why = "format"
                elif t not in desig:
                    out["rescued"]["designator"] += 1
                    why = "designator"
                elif t not in meas:
                    out["rescued"]["measured"] += 1
                    why = "measured"
                elif t not in remaining and legal_hit:
                    out["rescued"]["legal"] += 1
                    why = "legal"
                else:
                    out["still"] += 1
                    n = ds._norm_token(t)
                    beyond = bool(page_full) and len(page_full) > len(str(src.get("text") or "")) \
                        and not ds.unverified_tokens(claim, page_full, measured, catalog).count(t)
                    if beyond:
                        out["beyond_cap"] += 1
                        why = "beyond_cap"
                    else:
                        out["absent"] += 1
                        why = "absent"
                out["items"].append({"stage": stage, "token": t, "why": why, "url": url[:80],
                                     "sentence": claim[:140]})
            if remaining:
                out["still_findings"] += 1
    return out


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
    contra_ex: list[dict] = []
    contra_mech = ds.contradiction_findings(report, lang, terms, excluded=contra_ex)
    contra_reader = ds.contradiction_from_reader(st.get("reader_after") or st.get("reader"), lang,
                                                 report, excluded=contra_ex)
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

    figs = figure_replay(st, sources, _measured_text(res))

    return {
        "id": row["id"], "slug": row["slug"], "version": row["version"],
        "run_day": str(run_day) if run_day else None,
        "figures": figs,
        "words": ds.count_words(ds.body_text(report)),
        "density": round(float(density.get("per100") or 0.0), 2),
        "findings_now": len(findings),
        "findings_stored": len(st.get("findings_after") or []),
        "contradictions_mechanical": len(contra_mech),
        "contradictions_reader": len(contra_reader),
        "contradictions_stored": len(st.get("contradictions_after") or []),
        "contradictions_excluded": len(contra_ex),
        "contradiction_excluded_why": [e["why"] for e in contra_ex],
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
    print(f"contradiction candidates excluded as scope/drift (Runde 28): "
          f"{sum(r['contradictions_excluded'] for r in out)} in "
          f"{sum(1 for r in out if r['contradictions_excluded'])} run(s) — "
          f"stored blocking contradictions: {sum(r['contradictions_stored'] for r in out)} in "
          f"{sum(1 for r in out if r['contradictions_stored'])} run(s)")
    print(f"calendar rows with a date already passed on the run day: "
          f"{sum(r['calendar_passed_run_day'] for r in out)} in "
          f"{sum(1 for r in out if r['calendar_passed_run_day'])} run(s)")
    print(f"stored subject findings: {sum(r['subject_findings_stored'] for r in out)}, "
          f"accepted by the stem rule now: {sum(r['subject_now_accepted'] for r in out)}")
    dc, df = sum(r['dropped_core'] for r in out), sum(r['dropped_filler'] for r in out)
    print(f"dropped sentences (stored cite_findings_after, without rank marks): "
          f"{dc + df} — core/on-topic {dc}, filler {df}")
    F = [r["figures"] for r in out]
    resc = {k: sum(f["rescued"][k] for f in F) for k in ("format", "designator", "measured", "legal")}
    print(f"figure findings stored (sentence+page, before+after): {sum(f['findings'] for f in F)} with "
          f"{sum(f['tokens'] for f in F)} token(s) — under today's rule still unverified: "
          f"{sum(f['still'] for f in F)} token(s) in {sum(f['still_findings'] for f in F)} finding(s); "
          f"rescued: format {resc['format']}, designator {resc['designator']}, measured {resc['measured']}, "
          f"legal re-slice {resc['legal']}; of the remaining: {sum(f['beyond_cap'] for f in F)} present only "
          f"beyond the stored cap (cached full page), {sum(f['absent'] for f in F)} absent from the page")
    for r in out:
        for t in r["contradiction_texts"]:
            print(f"  [{r['id']} {r['slug']} v{r['version']}] {t}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
