#!/usr/bin/env python3
"""Agentischer Newsletter-Entwurf (PROTOTYP, Owner-Auftrag 2026-09-06).

Schreiber -> Kritiker -> Ueberarbeiter, alle drei auf DEMSELBEN lokalen Modell
(Gemma-4-26B), maximal MAX_ROUNDS Runden. Zweck dieses Skripts ist AUSSCHLIESS-
LICH der Vorher-Nachher-Vergleich an einer bereits erzeugten Edition. Es ist
bewusst NICHT integriert:

  * pipeline/newsletter_generator.py, scripts/weekly_newsletter_publish.sh und
    der Montags-Cron sind unveraendert; nichts hier wird von dort aufgerufen.
  * Das Skript schreibt NIE in die Datenbank. Es liest die Wochendaten und die
    bestehende Edition, und legt Protokoll + Bericht als Dateien ab.

Was eine spaetere Integration braeuchte (bewusst noch nicht gebaut):

  1. FLAG: ein Schalter (z. B. NEWSLETTER_AGENTIC=1 in
     scripts/weekly_newsletter_publish.sh), der den Loop anstelle der beiden
     Einzelaufrufe generate_editorial_en/generate_vertical_summaries_en setzt.
     Default aus, bis der Owner entschieden hat.
  2. LAUFZEITBUDGET: der Montagslauf ist heute ein Gemma-Handover mit zwei
     Generierungen (~1-2 min). Der Loop kostet pro Runde eine Kritik plus eine
     Ueberarbeitung, also grob das Drei- bis Fuenffache. Ein Budget in Minuten
     (SIGALRM wie scripts/newsletter_deep_dive.py) muss den Loop abbrechen
     koennen, ohne die Edition zu verlieren.
  3. RUECKFALLPFAD: jede Runde muss verwerfbar sein. Der zuletzt VOM KRITIKER
     BEURTEILTE Entwurf ist das Ergebnis; scheitert eine Ueberarbeitung am
     Parser oder das Modell am Handover, gilt der vorige Entwurf. Faellt der
     Loop komplett aus, muss der Produktionspfad (Runde 1 = heutiger Output)
     unveraendert weiterlaufen.
  4. HUMAN-IN-THE-LOOP: die Freigabe-Spalten (approved_at, #99) bleiben die
     Schranke. Der Loop ersetzt keine redaktionelle Freigabe, er liefert ihr
     nur einen besseren Ausgangstext.

Aufruf (GPU! vorher scripts/lib/gpu_guard.sh bzw. pgrep pruefen):

    .venv/bin/python -m scripts.newsletter_agentic_draft --year 2026 --week 35 \
        --report docs/newsletter_agentic_prototype_2026-09-06.md
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable, Literal

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from pydantic import BaseModel, Field  # noqa: E402

from pipeline import gpu_handover  # noqa: E402
from pipeline.config import DATA_DIR  # noqa: E402
from pipeline.db import get_connection  # noqa: E402
from pipeline.grounding import ungrounded_names, ungrounded_specifics  # noqa: E402
from pipeline.newsletter_generator import (  # noqa: E402
    BANNED_PHRASES,
    EDITORIAL_SYSTEM_PROMPT,
    VERTICAL_LABELS,
    VERTICAL_ORDER,
    VERTICAL_SYSTEM_PROMPT,
    build_editorial_prompt,
    build_vertical_prompt,
    decode_edition_row,
    get_weekly_newsletter_data,
    parse_vertical_summaries,
)

logger = logging.getLogger("newsletter_agentic_draft")

# --- Modell und Temperaturen ------------------------------------------------
# Ein Modell fuer alle drei Rollen (Owner-Vorgabe). Die Temperatur ist das
# Einzige, was sich je Rolle unterscheidet, und zwar begruendet:
MODEL = os.getenv("NEWSLETTER_AGENTIC_MODEL",
                  "gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf")

# Schreiber: exakt die Produktionswerte, damit Runde 1 der heutige Output ist
# und der Vergleich den Loop misst, nicht eine geaenderte Temperatur.
T_WRITER_EDITORIAL = 0.65
T_WRITER_VERTICAL = 0.6
# Kritiker: 0.0 — ein Urteil muss reproduzierbar sein. Eine Note, die beim
# zweiten Wuerfeln anders ausfaellt, ist als Abbruchbedingung wertlos.
T_CRITIC = 0.0
# Ueberarbeiter: 0.3 — Redigieren, nicht Erfinden. Hoch genug, um Saetze
# umzubauen, niedrig genug, dass das Modell an den uebergebenen Fakten bleibt
# statt neue Formulierungsideen zu erwuerfeln.
T_REVISER = 0.3

MAX_ROUNDS = int(os.getenv("NEWSLETTER_AGENTIC_ROUNDS", "5"))
# "Hervorragend" = 4,5 von 5. Darunter geht der Entwurf zurueck in die
# Ueberarbeitung.
ACCEPT_OVERALL = float(os.getenv("NEWSLETTER_AGENTIC_ACCEPT", "4.5"))

PROTOCOL_DIR = DATA_DIR / "newsletter_agentic"


# ---------------------------------------------------------------------------
# Kriterienkatalog — steht bewusst hier im Code, nicht im Prompt-String, damit
# Tests ihn pruefen koennen und eine Aenderung im Diff sichtbar ist.
# ---------------------------------------------------------------------------

CriterionKey = Literal["evidence", "specificity", "density", "tone", "structure"]

CRITERIA: dict[str, str] = {
    "evidence": (
        "Belegtreue. Jede Aussage muss aus dem <data>-Block stammen. Keine "
        "erfundenen Firmen, Zahlen, Orte, Gesetze, Zeitraeume oder Ereignisse; "
        "keine Kausalitaet, die die Daten nicht hergeben. Eine Zahl, die nicht "
        "in den Daten steht, ist immer ein Mangel — auch wenn sie plausibel ist."
    ),
    "specificity": (
        "Spezifitaet. Benannte Firmen, Produkte, Summen, Orte statt "
        "Abstraktionen. 'Marktverschiebungen praegen den Sektor' ohne Nennung "
        "eines Akteurs ist ein Mangel; die Nennung muss zum genannten Signal "
        "passen und darf nicht bloss angehaengt sein."
    ),
    "density": (
        "Verdichtung. Kein Fuellwort, keine leere Einleitungsfloskel, keine "
        "Doppelung. Ein Signal DARF im Editorial und in seiner Vertikale "
        "vorkommen — das Editorial waehlt aus, die Vertikale ordnet ein. Ein "
        "Mangel ist es erst, wenn die Vertikale dieselbe Aussage in nahezu "
        "denselben Worten wiederholt, ohne etwas hinzuzufuegen."
    ),
    "tone": (
        "Ton. Analystenregister: behauptend, knapp, ohne Assistenzsprache "
        "('Lassen Sie uns', 'Hier ist'), ohne rhetorische Fragen, ohne "
        "Superlative, ohne die verbotenen Floskeln."
    ),
    "structure": (
        "Struktur und Laenge. Editorial: genau drei Absaetze (dominantes Thema, "
        "Schluesselsignale, Querverbindung mit einer konkreten Folgerung), "
        "zusammen 150-200 Woerter, Flietext ohne Aufzaehlung. Jede Vertikale: "
        "2-3 Saetze als ein Absatz."
    ),
}


class Defect(BaseModel):
    """Ein konkreter, umsetzbarer Mangel mit Zitat der betroffenen Stelle."""

    criterion: CriterionKey
    quote: str = Field(description="Wortlaut der beanstandeten Stelle aus dem Entwurf")
    problem: str = Field(description="Was daran falsch ist, in einem Satz")
    fix: str = Field(description="Was der Ueberarbeiter konkret tun soll")


class Critique(BaseModel):
    """Strukturiertes Urteil des Kritikers. Es gibt bewusst KEIN Feld fuer
    einen umgeschriebenen Text: der Kritiker darf nicht selbst schreiben, und
    das Schema ist die Stelle, an der das erzwungen wird."""

    evidence: int = Field(ge=1, le=5)
    specificity: int = Field(ge=1, le=5)
    density: int = Field(ge=1, le=5)
    tone: int = Field(ge=1, le=5)
    structure: int = Field(ge=1, le=5)
    overall: float = Field(ge=1.0, le=5.0)
    defects: list[Defect] = Field(default_factory=list)


# Kalibrierung des Kritikers, korrigiert nach dem zweiten Lauf 2026-09-06: die
# erste Fassung sagte "You do not praise" und verlangte "at most 8 defects".
# Bei Temperatur 0 ergab das eine Konstante — der Kritiker lieferte in jeder
# Runde acht Maengel und Noten zwischen 2,2 und 2,5, egal wie der Entwurf
# aussah. Eine Note, die sich nie bewegt, kann keine Abbruchbedingung sein.
# Jetzt: Notenanker statt Haltungsanweisung, und eine leere Mangelliste ist
# eine zulaessige Antwort.
CRITIC_SYSTEM_PROMPT = (
    "You are the copy chief of Catandary Trends. You review a draft newsletter "
    "against a fixed catalogue of criteria. You never rewrite the text — you "
    "only judge it and name defects, each with the exact wording you object "
    "to, copied verbatim from the draft. Score honestly against these anchors: "
    "5 = a professional analyst would publish the passage unchanged; 4 = "
    "publishable after a small edit; 3 = usable but generic; 2 = weak, needs "
    "a rewrite; 1 = wrong, invented, or unusable. Do not deduct for a defect "
    "you cannot quote."
)

REVISER_SYSTEM_PROMPT = (
    "You are the editorial voice of Catandary Trends, rewriting your own draft "
    "after review. You fix every defect the review names, and you change "
    "nothing else that already works. You may only use facts from the supplied "
    "data block — you never add a company, number, date or event that is not in "
    "it. Your tone is analytical, confident, concise. Technical terms stay in "
    "English."
)


# ---------------------------------------------------------------------------
# Entwurf
# ---------------------------------------------------------------------------

@dataclass
class Draft:
    editorial: str
    verticals: dict[str, str] = field(default_factory=dict)

    def as_text(self) -> str:
        """Der ganze Entwurf am Stueck — Eingabe fuer Kritiker und Pruefungen."""
        parts = [f"## EDITORIAL\n{self.editorial}", "## VERTICALS"]
        for v in VERTICAL_ORDER:
            if v in self.verticals:
                parts.append(f"{v}\n{self.verticals[v]}")
        return "\n\n".join(parts)

    def words(self) -> tuple[int, int]:
        return (len(self.editorial.split()),
                sum(len(t.split()) for t in self.verticals.values()))


_MD_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_DATA_RE = re.compile(r"<data>(.*?)</data>", re.S)


def plain(text: str | None) -> str:
    """Markdown-Links entfernen — die gespeicherte Edition ist linkifiziert,
    der frische Entwurf nicht. Ohne das vergleicht man Klammern statt Prosa."""
    return _MD_LINK.sub(r"\1", text or "")


def data_block(prompt: str) -> str:
    """Nur der <data>-Teil eines Prompts. Das ist exakt das Material, das dem
    Modell uebergeben wurde — und damit die einzige zulaessige Faktenbasis."""
    m = _DATA_RE.search(prompt)
    return (m.group(1) if m else prompt).strip()


def full_data_block(data: dict) -> str:
    """Die <data>-Bloecke BEIDER Produktions-Prompts, ohne die Anweisungen.

    Kritiker, Ueberarbeiter und die maschinelle Pruefung muessen exakt
    dasselbe Material sehen. Im ersten Lauf am 2026-09-06 bekam der Kritiker
    nur den Editorial-Block und erklaerte daraufhin echte Vertikal-Signale
    (Maash, ProFound Therapeutics, Politecnico di Milano) fuer erfunden — die
    maschinelle Pruefung, die immer beide Bloecke sah, widersprach ihm mit 0
    unbelegten Zahlen. Ein Kritiker, der weniger sieht als der Schreiber,
    produziert Belegtreue-Maengel, die keine sind.

    Ohne die Anweisungen, weil die Zahlen enthalten ('150-200 Woerter',
    '2-3 Saetze') — sonst waere eine erfundene 200 im Text plotzlich belegt.
    """
    return data_block(build_editorial_prompt(data)) + "\n\n" + data_block(build_vertical_prompt(data))


def grounding_source(data: dict) -> str:
    """Faktenbasis der maschinellen Pruefung — identisch mit dem, was die
    Modellrollen sehen."""
    return full_data_block(data)


def banned_phrase_list() -> list[str]:
    """BANNED_PHRASES ist im Produktionscode ein Prompt-String; fuer die
    maschinelle Pruefung wird daraus eine Liste."""
    return [p.strip().strip('"') for p in BANNED_PHRASES.split(",") if p.strip()]


def banned_hits(text: str) -> list[str]:
    low = (text or "").lower()
    return sorted({p for p in banned_phrase_list() if p and p.lower() in low})


# ---------------------------------------------------------------------------
# Maschinelle Pruefung (ausserhalb des Modells)
# ---------------------------------------------------------------------------

def machine_check(draft: Draft, source: str) -> dict:
    """Grounding + Floskeln, deterministisch. Das Ergebnis geht dem Kritiker
    als FAKT in den Prompt — das Modell soll seine eigene Halluzination nicht
    selbst beurteilen muessen."""
    ed = plain(draft.editorial)
    spec_ed = ungrounded_specifics(ed, source)
    names_ed = ungrounded_names(ed, source)
    per_vertical: dict[str, dict] = {}
    spec_n = len(spec_ed)
    name_n = len(names_ed)
    for v, txt in draft.verticals.items():
        t = plain(txt)
        s = ungrounded_specifics(t, source)
        n = ungrounded_names(t, source)
        if s or n:
            per_vertical[v] = {"specifics": s, "names": n}
        spec_n += len(s)
        name_n += len(n)
    banned = banned_hits(draft.as_text())
    return {
        "editorial": {"specifics": spec_ed, "names": names_ed},
        "verticals": per_vertical,
        "ungrounded_specifics": spec_n,
        "ungrounded_names": name_n,
        "banned_phrases": banned,
    }


def format_machine_check(check: dict) -> str:
    """Die maschinellen Befunde so, wie der Kritiker sie liest."""
    lines = []
    ed = check["editorial"]
    if ed["specifics"]:
        lines.append("- EDITORIAL, figures not present in the data: "
                     + ", ".join(ed["specifics"]))
    if ed["names"]:
        lines.append("- EDITORIAL, person names not present in the data: "
                     + ", ".join(ed["names"]))
    for v, r in check["verticals"].items():
        if r["specifics"]:
            lines.append(f"- {v}, figures not present in the data: " + ", ".join(r["specifics"]))
        if r["names"]:
            lines.append(f"- {v}, person names not present in the data: " + ", ".join(r["names"]))
    if check["banned_phrases"]:
        lines.append("- Banned phrases used: " + ", ".join(check["banned_phrases"]))
    if not lines:
        return ("No fabricated figures, no unsupported person names, no banned "
                "phrases were found by the automatic check. Judge the remaining "
                "criteria on your own; do not invent evidence defects that the "
                "check did not find and that you cannot quote.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Abbruchbedingung
# ---------------------------------------------------------------------------

def open_evidence_defects(critique: Critique) -> list[Defect]:
    return [d for d in critique.defects if d.criterion == "evidence"]


def is_accepted(critique: Critique, check: dict,
                threshold: float = ACCEPT_OVERALL) -> tuple[bool, str]:
    """Abbruch nur, wenn ALLE drei Bedingungen erfuellt sind.

    Die dritte (maschinelles Grounding sauber) ist bewusst kein Modellurteil:
    eine erfundene Zahl darf nicht dadurch verschwinden, dass der Kritiker sie
    uebersieht. Unbelegte PERSONENNAMEN blockieren nicht — die Pruefung sieht
    laut pipeline/grounding.py keine Institutionen/Orte und ist dort als
    Warnung gedacht.
    """
    if check["ungrounded_specifics"] > 0:
        return False, (f"{check['ungrounded_specifics']} unbelegte Zahl(en) "
                       "in der maschinellen Pruefung")
    ev = open_evidence_defects(critique)
    if ev:
        return False, f"{len(ev)} offene(r) Mangel der Kategorie Belegtreue"
    if critique.overall < threshold:
        return False, f"Gesamtnote {critique.overall:.1f} < {threshold:.1f}"
    return True, f"Gesamtnote {critique.overall:.1f}, Belegtreue sauber"


# ---------------------------------------------------------------------------
# Prompts der drei Rollen
# ---------------------------------------------------------------------------

def build_critic_prompt(draft: Draft, data: dict, check: dict) -> str:
    catalogue = "\n".join(f"{i+1}. {k} — {v}" for i, (k, v) in enumerate(CRITERIA.items()))
    return f"""Review the draft below against the criteria catalogue. Score each
criterion 1-5, give an overall score 1.0-5.0, and list every defect you can
quote. Do NOT rewrite anything.

<data>
{full_data_block(data)}
</data>

<draft>
{draft.as_text()}
</draft>

<automatic_check>
{format_machine_check(check)}
</automatic_check>

Criteria:
{catalogue}

Banned phrases: {BANNED_PHRASES}

Rules for your answer:
- Every defect must carry a `quote` copied verbatim from the draft (a phrase or
  a sentence, not the whole draft). If you cannot quote it, it is not a defect.
- `fix` must be an instruction the writer can act on with the data above, not a
  wish ("name the company behind the $26 million Series A"), and must never ask
  for a fact the data does not contain.
- Every finding listed in <automatic_check> MUST appear as a defect with
  criterion "evidence" or "tone" — it is a measured fact, not an opinion.
- Before calling anything invented, search the WHOLE <data> block, including the
  per-vertical sections below the overall one. A company or figure that appears
  anywhere in <data> is evidence, not a fabrication. The summaries in <data> are
  cut off mid-sentence by design; a truncated source line is not a defect of the
  draft.
- List only defects you can actually quote, most serious first, at most 8. An
  empty list is a valid answer: if a criterion is met, do not manufacture a
  complaint for it. An invented defect costs another round for nothing.
- A vertical summary MAY cover a signal the editorial also names — that is the
  design, not a defect. Flag it only if the vertical says it in near-identical
  words and adds nothing the editorial did not already say.
- `overall` is your judgement of the draft as a whole, not the mean of the five
  scores. 4.5 or higher means: an analyst would send this out as it stands."""


def build_reviser_prompt(draft: Draft, data: dict, critique: Critique, check: dict) -> str:
    defects = "\n".join(
        f'- [{d.criterion}] "{d.quote}" — {d.problem} FIX: {d.fix}'
        for d in critique.defects) or "- (no quoted defects; tighten the weakest sentences)"
    verticals = [v for v in VERTICAL_ORDER if v in draft.verticals]
    return f"""Rewrite the draft below so that every defect from the review is
fixed. Keep what already works.

<data>
{full_data_block(data)}
</data>

<draft>
{draft.as_text()}
</draft>

<review score="{critique.overall:.1f}">
{defects}
</review>

<automatic_check>
{format_machine_check(check)}
</automatic_check>

Rules:
- Use ONLY facts from <data>. Never add a company, figure, date or event that
  is not there. A figure flagged by the automatic check must be removed or
  replaced by a figure that IS in the data.
- Editorial: exactly 3 paragraphs (dominant theme / key signals / cross-current
  ending in one concrete implication), 150-200 words total, flowing prose, no
  bullet points, no headers inside the paragraphs. Do not open with "This week".
- One paragraph of 2-3 sentences per vertical, for exactly these verticals in
  this order: {", ".join(verticals)}.
- Banned phrases: {BANNED_PHRASES}
- The signal summaries in <data> are cut off mid-sentence by design. Never copy
  one verbatim and never end a sentence mid-word — write your own sentence from
  what the fragment does say.
- Do not use bracketed IDs. Do not add introductions, transitions or comments.

Answer in exactly this format and nothing else:

## EDITORIAL
<the three paragraphs>

## VERTICALS
{verticals[0] if verticals else "TECH"}
<2-3 sentences>

<next vertical label>
<2-3 sentences>"""


# ---------------------------------------------------------------------------
# Parser fuer die Ueberarbeitung
# ---------------------------------------------------------------------------

_ED_HEAD = re.compile(r"^\s*#{0,3}\s*\**\s*EDITORIAL\s*\**\s*$", re.M | re.I)
_VE_HEAD = re.compile(r"^\s*#{0,3}\s*\**\s*VERTICALS?\s*\**\s*$", re.M | re.I)


def parse_revision(raw: str, previous: Draft) -> tuple[Draft, list[str]]:
    """Antwort des Ueberarbeiters in einen Entwurf zerlegen.

    Faellt ein Teil aus (Modell laesst den Marker weg, eine Vertikale fehlt),
    wird der entsprechende Teil des VORIGEN Entwurfs behalten statt den ganzen
    Durchgang zu verwerfen — dieselbe Haltung wie im Produktionspfad, der
    fehlende Vertikale einzeln nachgeneriert. Zweiter Rueckgabewert = was
    nicht geparst werden konnte."""
    problems: list[str] = []
    text = (raw or "").strip()
    m_v = _VE_HEAD.search(text)
    if m_v:
        head, tail = text[:m_v.start()], text[m_v.end():]
    else:
        head, tail = text, ""
        problems.append("VERTICALS-Marker fehlt")
    m_e = _ED_HEAD.search(head)
    editorial = head[m_e.end():] if m_e else head
    editorial = editorial.strip()
    if not m_e:
        problems.append("EDITORIAL-Marker fehlt")
    if len(editorial.split()) < 60:
        problems.append(f"Editorial zu kurz ({len(editorial.split())} Woerter) — voriges behalten")
        editorial = previous.editorial
    verticals = parse_vertical_summaries(tail) if tail else {}
    missing = [v for v in previous.verticals if v not in verticals]
    for v in missing:
        verticals[v] = previous.verticals[v]
    if missing:
        problems.append("Vertikale aus dem vorigen Entwurf uebernommen: " + ", ".join(missing))
    # Nichts erfinden: nur die Vertikalen, die es vorher schon gab.
    verticals = {v: verticals[v] for v in previous.verticals}
    return Draft(editorial=editorial, verticals=verticals), problems


# ---------------------------------------------------------------------------
# Modellzugriff
# ---------------------------------------------------------------------------

def _default_chat():
    from pipeline.llamacpp_client import assert_served_model, chat

    def _chat(prompt: str, system: str, temperature: float) -> str:
        assert_served_model(MODEL, stage="newsletter-agentic")
        return chat(model=MODEL, prompt=prompt, system=system, temperature=temperature)

    return _chat


def _default_structured():
    from pipeline.llamacpp_client import chat_structured

    def _structured(prompt: str, system: str, temperature: float) -> Critique | None:
        return chat_structured(model=MODEL, prompt=prompt, schema=Critique,
                               system=system, temperature=temperature,
                               require_all_fields=True, max_tokens=2048,
                               verify_model=True)

    return _structured


def est_tokens(text: str) -> int:
    """Grobe Schaetzung (4 Zeichen je Token). llama-server liefert usage nicht
    ueber pipeline.llamacpp_client zurueck, und der Owner will die Groessen-
    ordnung, nicht die Abrechnung."""
    return max(1, len(text or "") // 4)


# ---------------------------------------------------------------------------
# Loop
# ---------------------------------------------------------------------------

def write_first_draft(data: dict, chat_fn: Callable) -> Draft:
    """Runde 1 = der heutige Produktionsoutput: dieselben Prompt-Builder,
    dieselben System-Prompts, dieselben Temperaturen."""
    editorial = chat_fn(build_editorial_prompt(data), EDITORIAL_SYSTEM_PROMPT,
                        T_WRITER_EDITORIAL).strip()
    raw = chat_fn(build_vertical_prompt(data), VERTICAL_SYSTEM_PROMPT,
                  T_WRITER_VERTICAL).strip()
    return Draft(editorial=editorial, verticals=parse_vertical_summaries(raw))


def run_loop(data: dict, *, chat_fn: Callable | None = None,
             structured_fn: Callable | None = None,
             max_rounds: int = MAX_ROUNDS,
             threshold: float = ACCEPT_OVERALL) -> dict:
    """Schreiben -> (Pruefen -> Kritisieren -> Ueberarbeiten) x N.

    Eine RUNDE ist ein Entwurf mit seiner Beurteilung. Runde 1 ist der
    Schreiber-Entwurf, Runde i>1 die Ueberarbeitung aus Runde i-1. Ergebnis ist
    immer ein Entwurf, der beurteilt WURDE — nach der letzten Kritik wird nicht
    mehr blind ueberarbeitet."""
    chat_fn = chat_fn or _default_chat()
    structured_fn = structured_fn or _default_structured()
    source = grounding_source(data)
    t0 = time.time()
    tokens_in = tokens_out = 0

    p_ed, p_ve = build_editorial_prompt(data), build_vertical_prompt(data)
    tokens_in += est_tokens(p_ed) + est_tokens(p_ve) + 2 * est_tokens(EDITORIAL_SYSTEM_PROMPT)
    draft = write_first_draft(data, chat_fn)
    tokens_out += est_tokens(draft.as_text())
    first = Draft(editorial=draft.editorial, verticals=dict(draft.verticals))

    rounds: list[dict] = []
    stop_reason = f"Rundenbudget ({max_rounds}) erschoepft"
    accepted = False
    for i in range(1, max_rounds + 1):
        t_round = time.time()
        check = machine_check(draft, source)
        cp = build_critic_prompt(draft, data, check)
        tokens_in += est_tokens(cp) + est_tokens(CRITIC_SYSTEM_PROMPT)
        critique = structured_fn(cp, CRITIC_SYSTEM_PROMPT, T_CRITIC)
        if critique is None:
            # Kein Urteil = kein Fortschritt. Der Entwurf dieser Runde bleibt
            # stehen (Rueckfallpfad), der Loop endet.
            rounds.append({"round": i, "error": "Kritiker lieferte kein gueltiges JSON",
                           "machine": check, "seconds": round(time.time() - t_round, 1)})
            stop_reason = "Kritiker lieferte kein gueltiges JSON"
            break
        tokens_out += est_tokens(critique.model_dump_json())
        ok, why = is_accepted(critique, check, threshold)
        ed_w, ve_w = draft.words()
        entry = {
            "round": i,
            "scores": {k: getattr(critique, k) for k in CRITERIA},
            "overall": critique.overall,
            "defects": [d.model_dump() for d in critique.defects],
            "machine": check,
            "accepted": ok,
            "reason": why,
            "words": {"editorial": ed_w, "verticals": ve_w},
            "draft": {"editorial": draft.editorial, "verticals": dict(draft.verticals)},
        }
        if ok:
            entry["seconds"] = round(time.time() - t_round, 1)
            rounds.append(entry)
            accepted = True
            stop_reason = f"angenommen in Runde {i}: {why}"
            break
        if i == max_rounds:
            entry["seconds"] = round(time.time() - t_round, 1)
            rounds.append(entry)
            break
        rp = build_reviser_prompt(draft, data, critique, check)
        tokens_in += est_tokens(rp) + est_tokens(REVISER_SYSTEM_PROMPT)
        raw = chat_fn(rp, REVISER_SYSTEM_PROMPT, T_REVISER)
        tokens_out += est_tokens(raw)
        revised, problems = parse_revision(raw, draft)
        entry["revision_problems"] = problems
        entry["seconds"] = round(time.time() - t_round, 1)
        rounds.append(entry)
        draft = revised

    return {
        "model": MODEL,
        "temperatures": {"writer_editorial": T_WRITER_EDITORIAL,
                         "writer_vertical": T_WRITER_VERTICAL,
                         "critic": T_CRITIC, "reviser": T_REVISER},
        "threshold": threshold,
        "max_rounds": max_rounds,
        "rounds_used": len(rounds),
        "accepted": accepted,
        "stop_reason": stop_reason,
        "first_draft": {"editorial": first.editorial, "verticals": first.verticals},
        "final_draft": {"editorial": draft.editorial, "verticals": draft.verticals},
        "final_machine": machine_check(draft, source),
        "first_machine": machine_check(first, source),
        "rounds": rounds,
        "seconds": round(time.time() - t0, 1),
        "tokens_in_est": tokens_in,
        "tokens_out_est": tokens_out,
    }


# ---------------------------------------------------------------------------
# Daten der Woche + bestehende Edition
# ---------------------------------------------------------------------------

def week_data(year: int, week: int) -> dict:
    monday = date.fromisocalendar(year, week, 1)
    sunday = date.fromisocalendar(year, week, 7)
    data = get_weekly_newsletter_data(week_start=f"{monday.isoformat()}T00:00:00",
                                      week_end=f"{sunday.isoformat()}T23:59:59")
    data["period"] = f"{year}-W{week:02d}"
    data["period_label"] = f"Week {week}/{year}"
    return data


def stored_edition(year: int, week: int) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM newsletter_editions WHERE year = ? AND week = ?",
            (year, week)).fetchone()
    return decode_edition_row(row) if row else None


# ---------------------------------------------------------------------------
# Bericht
# ---------------------------------------------------------------------------

def _defect_lines(entry: dict, limit: int = 3) -> str:
    out = []
    for d in entry.get("defects", [])[:limit]:
        out.append(f'  - [{d["criterion"]}] "{d["quote"][:110]}" — {d["problem"]}')
    return "\n".join(out) or "  - (keine zitierten Maengel)"


def build_report(result: dict, before: dict, data: dict, year: int, week: int,
                 verticals_shown: list[str]) -> str:
    b_ed = plain(before.get("editorial"))
    b_ve = {k: plain(v) for k, v in (before.get("vertical_summaries") or {}).items()}
    source = grounding_source(data)
    before_draft = Draft(editorial=b_ed, verticals=b_ve)
    before_check = machine_check(before_draft, source)
    first, final = result["first_draft"], result["final_draft"]
    fm, lm = result["first_machine"], result["final_machine"]

    lines: list[str] = []
    a = lines.append
    a(f"# Agentischer Newsletter-Entwurf — Prototyp am Beispiel {year}-W{week:02d}")
    a("")
    a(f"Erzeugt: {datetime.now(timezone.utc).isoformat(timespec='seconds')} — "
      f"`scripts/newsletter_agentic_draft.py` (Prototyp, NICHT integriert).")
    a("")
    a("## Aufbau")
    a("")
    a(f"- Modell fuer alle drei Rollen: `{result['model']}`")
    a(f"- Temperaturen: Schreiber {result['temperatures']['writer_editorial']} (Editorial) / "
      f"{result['temperatures']['writer_vertical']} (Vertikale), Kritiker "
      f"{result['temperatures']['critic']}, Ueberarbeiter {result['temperatures']['reviser']}")
    a(f"- Abbruch bei Gesamtnote >= {result['threshold']} UND keinem offenen Mangel "
      "der Kategorie Belegtreue UND null unbelegten Zahlen in der maschinellen Pruefung")
    a(f"- Rundenbudget: {result['max_rounds']}; genutzt: {result['rounds_used']}")
    a(f"- Ergebnis: **{result['stop_reason']}**")
    a(f"- Laufzeit: {result['seconds']:.0f} s; Tokenaufwand grob: "
      f"~{result['tokens_in_est']:,} in / ~{result['tokens_out_est']:,} out".replace(",", "."))
    a(f"- Datengrundlage: {data['total_count']} veroeffentlichte Signale der Woche, "
      f"{len(data['verticals'])} Vertikale (Ist-Edition nannte {before.get('total_signals')})")
    a("")
    a("## Rundenprotokoll")
    a("")
    a("| Runde | Gesamt | Belegtreue | Spezifitaet | Verdichtung | Ton | Struktur | "
      "Maengel | unbelegte Zahlen | Floskeln | Woerter (Ed/Vert) | s |")
    a("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for e in result["rounds"]:
        if "scores" in e:
            s = e["scores"]
            m = e["machine"]
            a(f"| {e['round']} | **{e['overall']:.1f}** | {s['evidence']} | {s['specificity']} | "
              f"{s['density']} | {s['tone']} | {s['structure']} | {len(e['defects'])} | "
              f"{m['ungrounded_specifics']} | {len(m['banned_phrases'])} | "
              f"{e['words']['editorial']}/{e['words']['verticals']} | {e.get('seconds', 0)} |")
        else:
            a(f"| {e['round']} | — | | | | | | | | | | {e.get('seconds', 0)} | ")
    a("")
    a("### Hauptkritik je Runde")
    a("")
    for e in result["rounds"]:
        if "scores" not in e:
            a(f"**Runde {e['round']}:** {e.get('error')}")
            continue
        a(f"**Runde {e['round']} — {e['overall']:.1f}/5 ({e['reason']})**")
        a("")
        a(_defect_lines(e))
        if e.get("revision_problems"):
            a("")
            a("  - Parser-Hinweise der Ueberarbeitung: " + "; ".join(e["revision_problems"]))
        a("")
    a("## Vorher / Nachher — Editorial")
    a("")
    a(f"### A) Ist-Text der Edition {year}-W{week:02d} (Datenbank, unveraendert)")
    a("")
    a(b_ed.strip())
    a("")
    a("### B) Runde 1 — Schreiber allein (heutiger Produktionspfad, frisch erzeugt)")
    a("")
    a(first["editorial"].strip())
    a("")
    a(f"### C) Nach dem Loop (Runde {result['rounds_used']})")
    a("")
    a(final["editorial"].strip())
    a("")
    a("## Vorher / Nachher — Vertical-Summaries")
    a("")
    for v in verticals_shown:
        label = VERTICAL_LABELS.get(v, (v, ""))[0]
        a(f"### {v} — {label}")
        a("")
        a(f"**A) Ist-Text:** {b_ve.get(v, '(nicht in der Edition)').strip()}")
        a("")
        a(f"**B) Runde 1:** {first['verticals'].get(v, '(fehlt)').strip()}")
        a("")
        a(f"**C) Nach dem Loop:** {final['verticals'].get(v, '(fehlt)').strip()}")
        a("")
    a("## Grounding und Floskeln, maschinell gemessen")
    a("")
    a("Gepruft mit `pipeline/grounding.py` gegen die `<data>`-Bloecke beider "
      "Produktions-Prompts (Titel, Summaries, Quellen, Mega-Trend-Zaehlungen). "
      "`ungrounded_specifics` = Zahl/Jahr/Betrag im Text, der in den Daten nicht "
      "vorkommt; `ungrounded_names` = Personenname ohne Beleg (laut Modul nur "
      "Warnung, blockiert den Abbruch nicht).")
    a("")
    a("| Text | unbelegte Zahlen | unbelegte Namen | verbotene Floskeln | Woerter (Ed/Vert) |")
    a("|---|---|---|---|---|")
    for name, chk, drf in (
        (f"A) Ist-Edition {year}-W{week:02d}", before_check, before_draft),
        ("B) Runde 1 (Schreiber allein)", fm,
         Draft(first["editorial"], first["verticals"])),
        (f"C) Nach dem Loop (Runde {result['rounds_used']})", lm,
         Draft(final["editorial"], final["verticals"])),
    ):
        ed_w, ve_w = drf.words()
        a(f"| {name} | {chk['ungrounded_specifics']} | {chk['ungrounded_names']} | "
          f"{len(chk['banned_phrases'])}"
          + (f" ({', '.join(chk['banned_phrases'])})" if chk["banned_phrases"] else "")
          + f" | {ed_w}/{ve_w} |")
    a("")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _llama_unit_active() -> bool:
    try:
        r = gpu_handover._run(["systemctl", "--user", "is-active",
                               gpu_handover.LLAMA_UNIT], timeout=15)
        return r.stdout.strip() == "active"
    except Exception:                                               # noqa: BLE001
        return False


def _restore_resting_server(was_active: bool) -> None:
    """Ruhezustand wiederherstellen: der Handover haengt start-active.sh
    zurueck; lief der llama-server vorher, wird er wieder gestartet."""
    target = gpu_handover._current_symlink_target()
    if target != gpu_handover.CANONICAL_RESTING_SCRIPT:
        logger.warning("start-active.sh zeigt auf %s statt %s", target,
                       gpu_handover.CANONICAL_RESTING_SCRIPT)
    if not was_active or _llama_unit_active():
        return
    logger.info("Ruhezustand: llama-server wieder starten (start-active.sh -> %s)", target)
    try:
        gpu_handover._run(["systemctl", "--user", "start", gpu_handover.LLAMA_UNIT],
                          timeout=60)
    except Exception as exc:                                        # noqa: BLE001
        logger.error("llama-server konnte nicht neu gestartet werden: %s", exc)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--year", type=int, required=True)
    p.add_argument("--week", type=int, required=True)
    p.add_argument("--rounds", type=int, default=MAX_ROUNDS)
    p.add_argument("--threshold", type=float, default=ACCEPT_OVERALL)
    p.add_argument("--report", type=Path, help="Markdown-Vergleich hierhin schreiben")
    p.add_argument("--verticals", default="TECH,ECO,HEALTH",
                   help="Vertikale im Vergleichsteil des Berichts")
    p.add_argument("--no-handover", action="store_true",
                   help="llama-server nicht umschalten (Server laeuft schon mit Gemma)")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    data = week_data(args.year, args.week)
    if not data["total_count"]:
        logger.error("keine Signale fuer %d-W%02d", args.year, args.week)
        return 1
    before = stored_edition(args.year, args.week)
    if before is None:
        logger.error("keine gespeicherte Edition %d-W%02d — nichts zu vergleichen",
                     args.year, args.week)
        return 1

    was_active = _llama_unit_active()
    logger.info("Ruhezustand vor dem Lauf: llama-server aktiv=%s, start-active.sh -> %s",
                was_active, gpu_handover._current_symlink_target())
    try:
        if args.no_handover:
            result = run_loop(data, max_rounds=args.rounds, threshold=args.threshold)
        else:
            with gpu_handover.content_gen_on_llamacpp(MODEL):
                result = run_loop(data, max_rounds=args.rounds, threshold=args.threshold)
    finally:
        if not args.no_handover:
            _restore_resting_server(was_active)

    result["year"], result["week"] = args.year, args.week
    PROTOCOL_DIR.mkdir(parents=True, exist_ok=True)
    protocol = PROTOCOL_DIR / f"{args.year}-W{args.week:02d}.json"
    protocol.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str),
                        encoding="utf-8")
    logger.info("Protokoll: %s", protocol)

    if args.report:
        shown = [v.strip().upper() for v in args.verticals.split(",") if v.strip()]
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(build_report(result, before, data, args.year, args.week, shown),
                               encoding="utf-8")
        logger.info("Bericht: %s", args.report)

    logger.info("Loop %d-W%02d: %d Runde(n), %s, %.0f s",
                args.year, args.week, result["rounds_used"], result["stop_reason"],
                result["seconds"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
