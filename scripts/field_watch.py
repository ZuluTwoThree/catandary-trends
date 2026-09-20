#!/usr/bin/env python3
"""Field Watch / Trajectory Sheet / Feldprobe — Kommandozeile.

  scripts/field_watch.py <kunde>                       Wochenblatt (Vorwoche, alle Felder)
  scripts/field_watch.py <kunde> --week 2026-09-14     Wochenblatt der Woche, in der das Datum liegt
  scripts/field_watch.py <kunde> --sheet <feld-slug>   Trajectory Sheet (Quartals-Scorecard) eines Feldes
  scripts/field_watch.py <kunde> --export              Kundenseite (index.html + PDFs) nach data/field_watch/<kunde>/site/
  scripts/field_watch.py --probe "precision fermentation" [--terms a,b] [--cpc C12P21/00]
                                                       Feldprobe: Seite 1 des Sheets + Anker-Vorschlag
  --all                                                 alle fields/*.yaml (Cron), example.yaml ausgenommen
  --no-pdf                                              nur HTML/JSON

<kunde> = fields/<kunde>.yaml (oder ein Pfad). Ausgabe: data/field_watch/<kunde>/
{<woche>.{json,html,pdf} | sheet-<feld>-<datum>.{json,html,pdf}}; jede Erzeugung
eine Zeile in field_watch_runs. Rein SQL — die Feldprobe ohne --cpc ist der
einzige Aufruf mit GPU-Handover (Query-Vektor der Technologie-Suche).
Exit 0 ok, 1 Fehler, 2 keine Felddateien.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.field_watch import (FIELDS_DIR, OUT_DIR, load_customer, measure_sheet,  # noqa: E402
                                  measure_week, probe, save_run, slugify)
from pipeline.field_watch_render import (dump_json, render_client_index, render_probe,  # noqa: E402
                                         render_sheet, render_week, to_pdf)

try:
    from pipeline.ops_events import record as ops_record
except Exception:  # noqa: BLE001
    from contextlib import nullcontext as ops_record  # type: ignore

logger = logging.getLogger("field_watch")


def _write(out_dir: Path, stem: str, payload: dict, html: str, pdf: bool) -> str | None:
    out_dir.mkdir(parents=True, exist_ok=True)
    dump_json(payload, out_dir / f"{stem}.json")
    (out_dir / f"{stem}.html").write_text(html, encoding="utf-8")
    if not pdf:
        return None
    p = out_dir / f"{stem}.pdf"
    if to_pdf(out_dir / f"{stem}.html", p):
        return str(p)
    logger.warning("kein Chromium gefunden — nur HTML (FIELD_WATCH_CHROME setzen)")
    return None


def run_week(cust: dict, today: date, pdf: bool, sample: bool) -> dict:
    d = measure_week(cust["fields"], today)
    out_dir = OUT_DIR / cust["slug"]
    html = render_week(d, cust["customer"], sample=sample)
    pdf_path = _write(out_dir, d["week"], d, html, pdf)
    rid = save_run(cust["slug"], "week", d["week"], None, d, pdf_path)
    for f in d["fields"]:
        print(f'  {f["name"]}: ' + ", ".join(f'{t} {f["week"][t]["n"]}' for t in ("science", "patent", "funding", "market"))
              + f' · neue Akteure {f["actors_new_week"]} · Nester {len(f["nests"])}')
    print(f'wochenblatt {d["week"]} → {out_dir}/{d["week"]}.{"pdf" if pdf_path else "html"} (run {rid})')
    return d


def run_sheet(cust: dict, slug: str, today: date, pdf: bool, sample: bool) -> dict:
    field = next((f for f in cust["fields"] if f["slug"] == slug), None)
    if not field:
        raise SystemExit(f"Feld {slug!r} nicht in {cust['slug']} — vorhanden: {[f['slug'] for f in cust['fields']]}")
    week = measure_week([field], today)
    d = measure_sheet(field, today)
    out_dir = OUT_DIR / cust["slug"]
    stem = f"sheet-{slug}-{d['measured_on']}"
    html = render_sheet(d, week, cust["customer"], sample=sample)
    pdf_path = _write(out_dir, stem, {"sheet": d, "week": week}, html, pdf)
    rid = save_run(cust["slug"], "sheet", week["week"], slug, {"sheet": d, "week": week}, pdf_path)
    q = d.get("quant") or {}
    print(f'sheet {field["name"]}: Patente {d["totals"]["patent"]}, Forschung {d["totals"]["science"]}, '
          f'K-Median {q.get("K_median")}, Take-off {d["takeoff"]} → {out_dir}/{stem}.{"pdf" if pdf_path else "html"} (run {rid})')
    return d


def run_probe(phrase: str, terms: list[str] | None, cpc: list[str] | None, today: date, pdf: bool, requester: str) -> dict:
    d = probe(phrase, terms, cpc, today)
    out_dir = OUT_DIR / "probes"
    stem = f"probe-{slugify(phrase)}-{d['measured_on']}"
    html = render_probe(d, requester)
    pdf_path = _write(out_dir, stem, d, html, pdf)
    save_run("probe", "probe", None, slugify(phrase), d, pdf_path)
    p = d["probe"]
    print(f'feldprobe "{phrase}": Patente {d["totals"]["patent"]}, Forschung {d["totals"]["science"]}, Markt {d["totals"]["market"]}, '
          f'Gate {p.get("gate")}, Anker {p.get("anchor_used")} → {out_dir}/{stem}.{"pdf" if pdf_path else "html"}')
    for c in p.get("candidates") or []:
        print(f'  {"*" if c.get("default") else " "} {c["symbol"]:<14} {c.get("n") or 0:>8}  {(c.get("title") or "")[:70]}')
    return d


def run_export(cust: dict) -> Path:
    out_dir = OUT_DIR / cust["slug"]
    site = out_dir / "site"
    site.mkdir(parents=True, exist_ok=True)
    entries = []
    for p in sorted(out_dir.glob("*.pdf"), key=lambda p: p.stat().st_mtime, reverse=True):
        (site / p.name).write_bytes(p.read_bytes())
        label = f"Wochenblatt {p.stem}" if p.stem[:4].isdigit() else f"Trajectory Sheet {p.stem[6:]}"
        entries.append({"file": p.name, "label": label, "date": datetime.fromtimestamp(p.stat().st_mtime).strftime("%d.%m.%Y")})
    (site / "index.html").write_text(render_client_index(cust["customer"], entries), encoding="utf-8")
    print(f"kundenseite: {site} ({len(entries)} Blätter) — per SFTP nach trends/clients/{cust['slug']}/ (htpasswd, s. deploy/webspace/)")
    return site


def customers_all() -> list[Path]:
    return sorted(p for p in FIELDS_DIR.glob("*.yaml") if not p.stem.startswith("example"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("customer", nargs="?", help="fields/<kunde>.yaml oder Pfad")
    ap.add_argument("--all", action="store_true", help="alle Kunden in fields/ (Cron)")
    ap.add_argument("--week", help="ein Datum der zu berichtenden Woche (Default: Vorwoche)")
    ap.add_argument("--sheet", metavar="FELD", help="Trajectory Sheet dieses Feld-Slugs")
    ap.add_argument("--export", action="store_true", help="Kundenseite bauen (index.html + PDFs)")
    ap.add_argument("--probe", metavar="PHRASE", help="Feldprobe für eine Phrase")
    ap.add_argument("--terms", help="Suchbegriffe der Probe, kommagetrennt (Default: die Phrase)")
    ap.add_argument("--cpc", help="CPC-Anker der Probe, kommagetrennt (sonst Vorschlag der Technologie-Suche, GPU)")
    ap.add_argument("--requester", default="", help="Name auf der Feldprobe")
    ap.add_argument("--no-pdf", action="store_true")
    ap.add_argument("--sample", action="store_true", help="Blatt als 'Beispiel zur Demonstration' kennzeichnen")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    pdf = not args.no_pdf
    if args.week:
        today = date.fromisoformat(args.week)
    else:
        today = date.today()
        if not args.probe and not args.sheet:
            # Vorwoche: der Samstagslauf berichtet Mo–So der laufenden Woche erst,
            # wenn sie vorbei ist — also die Woche vor dem letzten Sonntag.
            from datetime import timedelta
            today = today - timedelta(days=today.weekday() + 1) if today.weekday() < 6 else today
    with ops_record("field_watch"):
        if args.probe:
            terms = [t.strip() for t in (args.terms or "").split(",") if t.strip()] or None
            cpc = [c.strip() for c in (args.cpc or "").split(",") if c.strip()] or None
            run_probe(args.probe, terms, cpc, today, pdf, args.requester)
            return 0
        paths: list[str] = []
        if args.all:
            paths = [str(p) for p in customers_all()]
            if not paths:
                print(f"keine Felddateien in {FIELDS_DIR}")
                return 2
        elif args.customer:
            paths = [args.customer]
        else:
            ap.error("Kunde, --all oder --probe angeben")
        rc = 0
        for p in paths:
            try:
                cust = load_customer(p)
                if args.sheet:
                    run_sheet(cust, args.sheet, today, pdf, args.sample)
                elif not args.export:
                    run_week(cust, today, pdf, args.sample)
                if args.export:
                    run_export(cust)
            except Exception as exc:  # noqa: BLE001
                logger.exception("%s: %s", p, exc)
                rc = 1
        return rc


if __name__ == "__main__":
    sys.exit(main())
