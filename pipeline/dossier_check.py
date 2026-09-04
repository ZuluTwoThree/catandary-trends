"""Endkontrolle des Agenten über ein fertiges Scouting-Dossier.

Läuft NACH dem Bericht und VOR der finalen Owner-Durchsicht (Owner-Festlegung
2026-09-01: der Agent prüft zuerst, freigegeben wird immer von Hand). Alles
hier ist deterministisch — dieselbe Philosophie wie das Publish-Gate: kein
zweiter LLM-Hop, der selbst halluzinieren könnte, sondern mechanische Checks,
deren Befunde der Owner in der Review-Ansicht neben dem Bericht sieht.

Geprüft wird:

  * Zahlen-Grounding: jedes konkrete Token (Jahr, Zahl, %, Geldbetrag) im
    Berichtstext muss im gesammelten Beweismaterial vorkommen
    (pipeline/grounding.py — dieselbe Mechanik wie beim Artikel-Gate).
    Der code-generierte Coverage-Anhang wird vorher abgetrennt: seine
    Zählwerte entstehen im Code, nicht im Modell, und stünden sonst als
    falsch-positive "Erfindungen" in jedem Befund.
  * Zitat-Bilanz: gestrichene Zitate (kanonisiert gegen den geschlossenen
    Katalog) und der Anteil zitierter Quellen.
  * Offene Fragen: wie viele Audit-Lücken der Lauf nicht schließen konnte
    (aus dem Coverage-Ledger — belegt gesucht, nichts gefunden).
  * Umfang: Wortzahl des Berichts.

`ok=True` heißt nur "die mechanischen Checks sind sauber" — es ersetzt die
Owner-Durchsicht ausdrücklich nicht und schaltet nichts frei.
"""
from __future__ import annotations

import re

from pipeline.grounding import ungrounded_specifics

# Müssen textgleich zu den code-generierten Anhängen in
# scripts/corpus_research.py bleiben (dort erzeugt, hier abgetrennt) — eine
# Fassung je Berichtssprache (lang=en / lang=de, Firmen-Dossiers sind deutsch).
COVERAGE_HEADINGS = (
    "## Research coverage (auto-generated)",
    "## Recherche-Abdeckung (automatisch erzeugt)",
)
COVERAGE_HEADING = COVERAGE_HEADINGS[0]

# Ab so vielen ungebundenen Tokens ist der Bericht mit hoher Wahrscheinlichkeit
# strukturell losgelöst vom Material (nicht nur eine Umformulierungs-Grauzone).
SEVERE_UNGROUNDED = 8


_MD_LINK = re.compile(r"\[([^\]\n]+)\]\((https?://[^)\s]+)\)")


def _report_body(report_md: str) -> str:
    """Der modellgeschriebene Teil des Berichts — ohne Coverage-Anhang."""
    hits = [i for i in (report_md.find(h) for h in COVERAGE_HEADINGS) if i >= 0]
    return report_md[:min(hits)] if hits else report_md


def _claims_text(body: str) -> str:
    """Der Text, dessen Zahlen belegt sein müssen: Zitat-Links auf ihr Label
    reduziert. Eine URL ist keine Behauptung — die Artikel-Slugs des Korpus
    enden auf `-<id>` (…-24632113), DOIs und Patentnummern tragen Ziffern,
    und keine davon steht im Belegtext. Vor dieser Reduktion meldete die
    Endkontrolle sie als „Zahlen ohne Beleg" (Newsletter-Deep-Dive 2026-09-04:
    3 von 3 Befunden waren Slug-IDs)."""
    return _MD_LINK.sub(r"\1", body)


def _evidence_text(result: dict) -> str:
    """Alles, was der Lauf an Belegtext gesammelt hat: Evidenznotizen (Volltexte,
    Suchtreffer, Quant-Messblock) plus Katalog-Snippets/-Titel/-Daten."""
    parts: list[str] = list(result.get("evidence") or [])
    for s in result.get("sources") or []:
        parts.append(" ".join(str(s.get(k) or "")
                              for k in ("title", "snippet", "date", "outlet")))
    parts.append(str(result.get("question") or ""))
    return "\n".join(parts)


def check_result(result: dict) -> dict:
    """Endkontrolle über das run()-Ergebnis von scripts/corpus_research.py.

    Erwartet das unveränderte Result-Dict (insbesondere `report`, `sources`,
    `evidence`, `cited`, `stripped_citations`, `ledger`).
    """
    report = str(result.get("report") or "")
    body = _report_body(report)
    evidence = _evidence_text(result)

    ungrounded = ungrounded_specifics(_claims_text(body), evidence)
    stripped = int(result.get("stripped_citations") or 0)
    cited = len(result.get("cited") or [])
    n_sources = len(result.get("sources") or [])
    open_questions = len(result.get("ledger") or [])
    words = len(re.findall(r"\S+", body))

    findings: list[str] = []
    if not body.strip():
        findings.append("Bericht ist leer.")
    if ungrounded:
        sample = ", ".join(repr(t) for t in ungrounded[:8])
        more = f" (+{len(ungrounded) - 8} weitere)" if len(ungrounded) > 8 else ""
        level = ("STRUKTURELL" if len(ungrounded) >= SEVERE_UNGROUNDED
                 else "punktuell")
        findings.append(
            f"{len(ungrounded)} Zahl(en) ohne Beleg im gesammelten Material "
            f"({level}): {sample}{more}")
    if stripped:
        findings.append(
            f"{stripped} Zitat(e) gestrichen — das Modell hat URLs zitiert, "
            f"die nicht im Katalog liegen.")
    if cited == 0 and n_sources:
        findings.append("Kein einziges Zitat hat die Kanonisierung überlebt.")
    if open_questions:
        findings.append(
            f"{open_questions} Frage(n) blieben nach dem Audit offen "
            f"(Coverage-Anhang zeigt, wo gesucht wurde).")

    return {
        "ok": not ungrounded and not stripped and bool(body.strip())
              and (cited > 0 or n_sources == 0),
        "ungrounded": ungrounded,
        "stripped_citations": stripped,
        "cited": cited,
        "sources": n_sources,
        "open_questions": open_questions,
        "words": words,
        "findings": findings,
    }
