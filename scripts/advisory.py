#!/usr/bin/env python3
"""Der Advisor: Beratungsnotiz fuer EINEN Kunden aus EINEM Dossier (Owner 2026-09-14).

    python -m scripts.advisory --list [--dossier <slug>]
    python -m scripts.advisory --new --dossier <slug>[@<version>] \\
        --profile-file profile.json --scope "Die Entscheidung, die ansteht …" [--run]
    python -m scripts.advisory --note <id>            # eine Notiz rechnen
    python -m scripts.advisory                        # alle queued Notizen
    python -m scripts.advisory --approve <id> [--by owner] [--approval-note "…"]
    python -m scripts.advisory --withdraw <id>

Ablauf je Notiz: Dossier + Katalog laden → Prompt (pipeline/advisory.py) →
27B mit eingeschaltetem Denken (Startskript start-qwen3.8-27b-thinking.sh,
Symlink-Wechsel wie beim Rechercheur, Ruhezustand danach) → Marker gegen den
Dossier-Katalog kanonisieren → deterministische Pruefung (Platzhalter, Zahlen
gegen Dossier + Profil, gestrichene Marker) → der Leser → `review`. Freigabe
nur durch einen Menschen (`--approve` oder Desk); nichts geht ohne
`approved_at` raus.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import advisory as adv                      # noqa: E402
from pipeline import advisory_store as store             # noqa: E402
from pipeline import gpu_handover, llamacpp_client       # noqa: E402
try:
    from pipeline.ops_events import record               # noqa: E402
except ImportError:                                      # Protokoll ist optional
    from contextlib import nullcontext as record
import scripts.corpus_research as cr                     # noqa: E402

logger = logging.getLogger("advisory")

THINKING_START = os.getenv("ADVISOR_START_SCRIPT", "start-qwen3.8-27b-thinking.sh")
ADVISOR_TIMEOUT = float(os.getenv("ADVISOR_TIMEOUT", "2400"))
ADVISOR_MAX_TOKENS = int(os.getenv("ADVISOR_MAX_TOKENS", "6000"))


@contextmanager
def thinking_server(assume_model_up: bool = False):
    """Den 27B mit Denken auf :8090 — Symlink auf das Thinking-Startskript, Start
    ueber den Handover (Besitzvermerk, Pre-Flight), Ruhezustand danach."""
    if assume_model_up:
        yield
        return
    saved = gpu_handover._safe_saved_target()
    target = gpu_handover.LLAMA_CPP_ROOT / THINKING_START
    if not target.is_file():
        raise RuntimeError(f"thinking start script missing: {target}")
    prev = gpu_handover._current_symlink_target()
    if prev != target.name:
        logger.info("Swapping start-active.sh: %s → %s", prev, target.name)
        if gpu_handover.START_ACTIVE.is_symlink() or gpu_handover.START_ACTIVE.exists():
            gpu_handover.START_ACTIVE.unlink()
        gpu_handover.START_ACTIVE.symlink_to(target.name)
    gpu_handover.llama_server_start(cr.MODEL, timeout=300, swap_symlink=False)
    try:
        yield
    finally:
        gpu_handover._teardown(saved)


def catalog_for(dossier: dict) -> tuple[list[dict], str]:
    """Die zitierfaehigen Quellen des Dossiers (alle im Katalog des Laufs mit
    Adresse) und ihr Block fuer den Prompt — der Advisor zitiert nur daraus."""
    result = dossier.get("result") or {}
    sources = [s for s in (result.get("sources") or []) if s.get("id") and cr.citable_url(s)]
    cited = set(result.get("cited") or [])
    # Zitierte zuerst, dann der Rest des Katalogs
    sources.sort(key=lambda s: (0 if s["id"] in cited else 1, s["id"]))
    lines = []
    for s in sources:
        mark = " (cited in the dossier)" if s["id"] in cited else ""
        rank = " (primary)" if int(s.get("rank", 2)) <= 1 else ""
        lines.append(f"[[{s['id']}]]{rank} {s.get('title', '')[:120]}"
                     + (f" — {s.get('outlet')}" if s.get("outlet") else "")
                     + (f", {s.get('date')}" if s.get("date") else "") + mark)
    return sources, "\n".join(lines)


def run_note(note_id: int, assume_model_up: bool = False) -> bool:
    note = store.get_note(note_id)
    if not note:
        logger.error("note #%d not found", note_id)
        return False
    if not store.mark_running(note_id):
        logger.error("note #%d is %s — not queued/failed", note_id, note.get("status"))
        return False
    t0 = time.time()
    try:
        dossier = store.get_dossier(note["dossier_slug"], note["dossier_version"])
        if not dossier:
            raise RuntimeError(f"dossier {note['dossier_slug']} v{note['dossier_version']} not found")
        result = dossier.get("result") or {}
        sources, catalog = catalog_for(dossier)
        report_md = dossier["report_md"]
        profile = note.get("profile") or {}
        prompt = adv.build_prompt(
            report_md + "\n\nCITATION CATALOG (cite by the id in double brackets, exactly as written):\n" + catalog,
            profile, note["scope"], dossier.get("question") or "", dossier.get("topic") or "")
        want = ADVISOR_TIMEOUT
        if llamacpp_client.TIMEOUT < want:
            llamacpp_client.TIMEOUT = want
        with thinking_server(assume_model_up):
            raw = llamacpp_client.chat(model=cr.MODEL, system=adv.ADVISOR_SYSTEM, prompt=prompt,
                                       enable_thinking=True, temperature=0.4,
                                       max_tokens=ADVISOR_MAX_TOKENS)
            text = re.sub(r"<think>.*?</think>", "", raw or "", flags=re.DOTALL).strip()
            lang = str(result.get("lang") or "en")
            # [[client]] markiert Profil-Fakten — kein Katalog-Eintrag, darf die
            # Kanonisierung nicht als Phantom-Zitat streichen.
            text = re.sub(r"\[\[\s*client\s*\]\]", "\u27e6client\u27e7", text, flags=re.IGNORECASE)
            note_md, cited_srcs, stripped = cr.canonicalize_citations(text, sources, lang, markers=True)
            note_md = note_md.replace("\u27e6client\u27e7", "(client profile)")
            profile_text = adv.profile_block(profile) + "\n" + note["scope"]
            unfilled = adv.unfilled_fields(note_md)
            foreign = adv.figures_not_in_sources(note_md, report_md + "\n" + catalog, profile_text)
            reader = cr.reader_review(
                note_md, f"Advisory note for this client — {note['scope']}",
                dossier.get("topic") or "", None, lang) if cr.reader_enabled() else None
        findings: list[str] = []
        if stripped:
            findings.append(f"{stripped} Zitat(e) gestrichen — ids, die nicht im Dossier-Katalog liegen.")
        if unfilled:
            findings.append("Platzhalter statt Inhalt in: " + ", ".join(unfilled) + ".")
        if foreign:
            findings.append("Zahlen, die weder im Dossier noch im Profil/Auftrag stehen: "
                            + ", ".join(foreign[:8]) + ".")
        majors = [f for f in ((reader or {}).get("findings") or []) if f.get("severity") == "major"]
        if reader and reader.get("answers_question") is False:
            findings.append("Leser (nicht sperrend): beantwortet den Auftrag nicht — " + (reader.get("overall") or ""))
        for f in majors[:4]:
            findings.append(f"Leser (nicht sperrend) [{f.get('section', '?')}]: {f.get('issue', '')} "
                            f"— Vorschlag: {f.get('suggestion', '')}")
        check = {
            "ok": not stripped and not unfilled and not foreign,
            "reader_ok": (bool(reader.get("answers_question")) and not majors) if reader else None,
            "stripped_citations": int(stripped), "unfilled": unfilled, "foreign_figures": foreign,
            "cited": len(cited_srcs), "words": len(re.findall(r"\S+", note_md)),
            "reader": reader, "findings": findings, "seconds": round(time.time() - t0, 1),
        }
        store.mark_review(note_id, note_md, check, f"{cr.MODEL} (thinking)", time.time() - t0)
        logger.info("note #%d → review: %s, %d finding(s), %.0fs", note_id,
                    "ok" if check["ok"] else "findings", len(findings), time.time() - t0)
        return True
    except Exception as exc:                                        # noqa: BLE001
        logger.exception("note #%d failed: %s", note_id, exc)
        store.mark_failed(note_id, f"{type(exc).__name__}: {exc}")
        return False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--dossier", help="Dossier-Slug[@Version] (--new, --list)")
    ap.add_argument("--new", action="store_true", help="Notiz anlegen (braucht --dossier, --profile-file, --scope)")
    ap.add_argument("--profile-file", help="JSON mit industry/size/position/capabilities/geography/horizon/risk_appetite/notes")
    ap.add_argument("--scope", help="Auftragsumfang: die anstehende Entscheidung, Grenzen, Budget/Zeit")
    ap.add_argument("--run", action="store_true", help="mit --new: sofort rechnen")
    ap.add_argument("--note", type=int, help="diese Notiz rechnen")
    ap.add_argument("--approve", type=int)
    ap.add_argument("--by", default="owner")
    ap.add_argument("--approval-note", default=None)
    ap.add_argument("--withdraw", type=int)
    ap.add_argument("--assume-model-up", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s: %(message)s")
    store.ensure_schema()

    if args.list:
        slug = (args.dossier or "").split("@")[0] or None
        for n in store.list_notes(slug):
            c = n.get("check") or {}
            print(f"#{n['id']:>4} [{n['status']:>9}] {n['dossier_slug']} v{n['dossier_version']} — "
                  f"{n['scope'][:60]}"
                  + (f"  {'✓' if c.get('ok') else '⚠'} {len(c.get('findings') or [])} Befund(e)"
                     + ("" if c.get("reader_ok") is None else (" · Leser ✓" if c.get("reader_ok") else " · Leser ✗"))
                     if c else ""))
        return 0
    if args.approve:
        ok = store.approve(args.approve, args.by, args.approval_note)
        print("freigegeben" if ok else "nicht freigegeben (Status?)")
        return 0 if ok else 1
    if args.withdraw:
        ok = store.withdraw(args.withdraw)
        print("zurueckgezogen" if ok else "nichts zurueckgezogen")
        return 0 if ok else 1

    new_id = None
    if args.new:
        if not (args.dossier and args.profile_file and args.scope):
            ap.error("--new braucht --dossier, --profile-file und --scope")
        slug, _, ver = args.dossier.partition("@")
        d = store.get_dossier(slug, int(ver) if ver else None)
        if not d:
            ap.error(f"Dossier {args.dossier} nicht gefunden")
        profile = json.loads(Path(args.profile_file).read_text(encoding="utf-8"))
        new_id = store.create_note(slug, int(d["version"]), profile, args.scope)
        print(f"Notiz #{new_id} angelegt (Dossier {slug} v{d['version']})")
        if not args.run:
            return 0

    todo = [store.get_note(args.note)] if args.note else ([store.get_note(new_id)] if new_id else store.queued_notes())
    todo = [n for n in todo if n]
    if not todo:
        print("keine Notizen")
        return 0
    with record("advisory"):
        rc = 0
        for n in todo:
            if not run_note(n["id"], assume_model_up=args.assume_model_up):
                rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
