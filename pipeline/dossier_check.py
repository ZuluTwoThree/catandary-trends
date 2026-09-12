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
    (aus dem Coverage-Ledger — belegt gesucht, nichts gefunden). Die
    audit-unabhängig mitgesweepten Plan-Schritte zählen NICHT als offene Frage.
  * Messung (seit 2026-09-06): ist die deterministische Innovationsketten-
    Messung ausgefallen, steht das im Befund; lief sie, wird geprüft, ob
    mindestens eine gemessene Größe im modellgeschriebenen Text vorkommt
    (in 13 von 13 Läufen davor wurde die Messquelle nie zitiert).
  * Umfang: Wortzahl des Berichts.

`ok=True` heißt nur "die mechanischen Checks sind sauber" — es ersetzt die
Owner-Durchsicht ausdrücklich nicht und schaltet nichts frei.
"""
from __future__ import annotations

import re

from pipeline.dossier_corpus_stats import CORPUS_HEADINGS
from pipeline.dossier_quant import MEASURE_HEADINGS
from pipeline.dossier_structure import AUDIT_ANNEX_MARK, measured_needles
from pipeline.grounding import ungrounded_specifics

# Müssen textgleich zu den code-generierten Anhängen in
# scripts/corpus_research.py bleiben (dort erzeugt, hier abgetrennt) — eine
# Fassung je Berichtssprache (lang=en / lang=de, Firmen-Dossiers sind deutsch).
COVERAGE_HEADINGS = (
    AUDIT_ANNEX_MARK,
    "## How this dossier was checked (auto-generated)",
    "## Wie dieses Dossier geprüft wurde (automatisch erzeugt)",
    "## Research coverage (auto-generated)",
    "## Recherche-Abdeckung (automatisch erzeugt)",
)
COVERAGE_HEADING = COVERAGE_HEADINGS[3]

# Ebenfalls code-generiert: der Messanhang (pipeline/dossier_quant.py,
# measurement_appendix). Seine Jahresreihen sind Query-Ergebnisse, keine
# Modell-Prosa — ohne diese Schnittmarke zaehlte die Endkontrolle jede
# gemessene Zahl als "Erfindung" (derselbe Fall wie dc36438/ea0c069).
MEASUREMENT_HEADINGS = MEASURE_HEADINGS + CORPUS_HEADINGS

# Ebenfalls code-generiert (canonicalize_citations hängt die Quellenliste an):
# Ordinalzahlen und Datumsangaben dieser Liste entstehen im Code, nicht im
# Modell — "12." / "14." standen im zweiten #96-Dry-Run als "unbelegte Zahlen".
SOURCES_HEADINGS = ("\n## Sources\n", "\n## Quellen\n")

# Ab so vielen ungebundenen Tokens ist der Bericht mit hoher Wahrscheinlichkeit
# strukturell losgelöst vom Material (nicht nur eine Umformulierungs-Grauzone).
SEVERE_UNGROUNDED = 8


_MD_LINK = re.compile(r"\[([^\]\n]+)\]\((https?://[^)\s]+)\)")


def _report_body(report_md: str) -> str:
    """Der modellgeschriebene Teil des Berichts — ohne Coverage-Anhang und
    ohne die code-generierte Quellenliste."""
    hits = [i for i in (report_md.find(h) for h in COVERAGE_HEADINGS
                        + SOURCES_HEADINGS + MEASUREMENT_HEADINGS)
            if i >= 0]
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


def _measurement_used(body: str, quant: dict) -> bool:
    """Taucht mindestens eine GEMESSENE Groesse im modellgeschriebenen Teil auf?

    Geprueft werden die Skalare aus result["quant"] (CPC-Codes, Median-K,
    Vorlaufzeit, Zykluszeit, Zentralitaets-Peak, Take-off-Jahre, Patentzahl)
    plus das Wort "measured"/"gemessen". Ein Dossier ohne eine einzige eigene
    Zahl soll das in seinem Pruefbefund stehen haben."""
    hay = body.lower()
    return any(n.lower() in hay for n in measured_needles(quant))


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
    # Nur echte Audit-Luecken sind "offene Fragen"; die Plan-Schritte, die der
    # Sweep seit 2026-09-06 audit-unabhaengig mitnimmt, sind keine.
    open_questions = sum(1 for e in (result.get("ledger") or [])
                         if (e.get("kind") or "gap") not in ("plan", "legal", "market"))
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

    # Messung: ausgefallen ODER ungenutzt — beides muss im Befund stehen.
    # Bis 2026-09-06 verschwand eine gescheiterte Messung spurlos, und in
    # 13 von 13 Laeufen wurde die Messquelle Q1 nie zitiert.
    quant = result.get("quant") or {}
    measured = bool(quant) and not quant.get("off_topic")
    measurement_used = None
    if quant and quant.get("off_topic"):
        findings.append(
            "Messung der Innovationskette ausgefallen — das Dossier hat keine "
            "eigene Patent-/Zeitreihenmessung (Messanhang nennt jeden Versuch).")
    elif measured:
        measurement_used = _measurement_used(body, quant)
        if not measurement_used:
            findings.append(
                "Gemessen, aber im Berichtstext nicht verwendet: keine der "
                "gemessenen Groessen taucht ausserhalb des Messanhangs auf.")

    # Gliederung, Laengenbremse und Beleg-Verifikation (2026-09-07). Der
    # Rechercheur hat sie bereits geprueft und EINEN Neuwurf verbraucht; was
    # danach noch offen ist, gehoert in den Befund, den der Owner sieht.
    st = result.get("structure") or {}
    left = list(st.get("findings_after") or [])
    if left:
        findings.append("Gliederung/Umfang nach dem Neuwurf noch offen: "
                        + " | ".join(left[:4])
                        + (f" (+{len(left) - 4} weitere)" if len(left) > 4 else ""))
    # R6-2/R6-3: Messbezug der Optionen und Branchenabdeckung stehen als
    # Kennzahl im Befund, auch wenn der Neuwurf sie behoben hat.
    # R7-1: eine Option ohne Messgroesse ist KEIN Mangel mehr (die
    # Verwendbarkeitsregel zieht eine Zahl, die nicht traegt, aus dem Text) —
    # eine Option ohne Messgroesse UND ohne Beleg schon.
    if st.get("options") and st.get("options_unsupported"):
        findings.append(
            f"{int(st['options_unsupported'])} von {int(st['options'])} "
            f"Option(en) ohne verwendbare gemessene Groesse UND ohne Beleg — "
            f"die Empfehlung haengt dort an nichts.")
    if st.get("sectors_missing"):
        findings.append(
            "Optionen decken nicht alle in der Frage genannten Felder ab: "
            + ", ".join(st["sectors_missing"]) + ".")
    for a in (st.get("advisory") or []):
        findings.append(a)
    if st.get("dropped_sentences"):
        # Drei Streichgruende, drei Formulierungen — "die Zahl stand nicht auf
        # der Seite" war nach Runde 3 nicht mehr die ganze Wahrheit.
        why = []
        if st.get("off_topic_after"):
            why.append(f"{st['off_topic_after']}× zitierte die Seite ein anderes "
                       f"Thema als der Satz")
        if st.get("sourceless_after"):
            why.append(f"{st['sourceless_after']}× stand eine Praezisionszahl "
                       f"ohne Beleg im Satz")
        if st.get("distorted_after"):
            why.append(f"{st['distorted_after']}× gab der Satz die Seite "
                       f"verdreht wieder (Qualifizierer/Groessenordnung/"
                       f"Kategoriewort)")
        if st.get("misattributed_after"):
            why.append(f"{st['misattributed_after']}× stand die Zahl auf der "
                       f"Seite bei einer anderen Studie")
        if st.get("measure_after"):
            why.append(f"{st['measure_after']}× nannte der Satz eine eigene "
                       f"Messgroesse, die die Verwendbarkeitsregel sperrt")
        # R9-1/R8-2: Rangbefunde werden gekennzeichnet, nicht wegen einer
        # falschen Zahl gestrichen. Sie in denselben Topf zu werfen war eine
        # Falschaussage im eigenen Pruefnachweis (B9-Lauf v1: 19 von 27).
        rank_marked = (int(st.get("weaksource_after") or 0)
                       + int(st.get("weakclaim_after") or 0))
        if rank_marked:
            why.append(f"{rank_marked}× ruhte eine Kernaussage nur auf "
                       f"Rang-2-Material und wurde als \"secondary source "
                       f"only\" gekennzeichnet (in der Kurzfassung "
                       f"gestrichen)")
        # R10-1: eine datierte Aussage ganz ohne Beleg wird GESTRICHEN, nicht
        # gekennzeichnet — sie gehoert weder in den Rangtopf noch in den Rest,
        # sonst steht im Pruefnachweis wieder die falsche Begruendung.
        uncited = int(st.get("uncited_after") or 0)
        if uncited:
            why.append(f"{uncited}× stand eine datierte Aussage ohne jeden "
                       f"Beleg in einem Kernabschnitt und wurde gestrichen")
        rest = (int(st["dropped_sentences"]) - int(st.get("off_topic_after") or 0)
                - int(st.get("sourceless_after") or 0)
                - int(st.get("distorted_after") or 0)
                - int(st.get("misattributed_after") or 0)
                - int(st.get("measure_after") or 0)
                - rank_marked - uncited)
        if rest > 0 or not why:
            why.insert(0, f"{max(rest, 0)}× enthielt die zitierte Web-Seite "
                          f"die behauptete Zahl nicht")
        findings.append(
            f"{st['dropped_sentences']} Satz/Saetze gestrichen: "
            + ", ".join(why) + ".")
    if st.get("cite_findings") and not st.get("dropped_sentences"):
        findings.append(
            f"{len(st['cite_findings'])} Zitat-Zahl(en) waren im ersten Entwurf "
            f"nicht durch die zitierte Seite gedeckt (im Neuwurf behoben).")

    return {
        # `ok` beschreibt das AUSGELIEFERTE Dokument: nichts Unbelegtes, nichts
        # Gestrichenes, Gliederung vollstaendig. Was die Streichung nach dem
        # Neuwurf noch entfernt oder als "secondary source only" gekennzeichnet
        # hat, steht als eigene Befundzeile im Pruefnachweis, sperrt aber nicht
        # mehr (bis 2026-09-12 tat es das: LFP v4 fiel an 7 ehrlich markierten
        # Rang-2-Saetzen, obwohl kein Satz des Dokuments ungedeckt war).
        "ok": not ungrounded and not stripped and bool(body.strip())
              and (cited > 0 or n_sources == 0) and not left,
        "ungrounded": ungrounded,
        "stripped_citations": stripped,
        "cited": cited,
        "sources": n_sources,
        "open_questions": open_questions,
        "measured": measured,
        "measurement_used": measurement_used,
        "words": words,
        "body_words": st.get("words_after"),
        "rewritten": bool(st.get("rewritten")),
        "structure_findings": left,
        "dropped_sentences": int(st.get("dropped_sentences") or 0),
        "cites_checked": int(st.get("cites_checked") or 0),
        "options": int(st.get("options") or 0),
        "options_measured": int(st.get("options_measured") or 0),
        "options_unsupported": int(st.get("options_unsupported") or 0),
        "sectors_missing": list(st.get("sectors_missing") or []),
        "findings": findings,
    }
