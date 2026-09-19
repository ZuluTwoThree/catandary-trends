"""Korpus-Evidenz für Scouting-Dossiers — der Korpus zuerst, das Web nur dort,
wo er dünn ist (Owner-Ziel 2026-09-19, Stufe 6 in
docs/plan_dossier_agent_2026-09-18.md).

Bis Runde 26 sah der Schreiber den eigenen Korpus nur als Suchmaschine: die
Korpus-Zählung (pipeline/dossier_corpus_stats.py) zählte Jahre, der Messblock
(pipeline/dossier_quant.py) maß die Patentklasse, und alles dazwischen — WER
sich in den letzten acht Quartalen auf WELCHER Ebene bewegt hat, welche
Quellen das tragen, welche Signale den Kern treffen — kam nur zufällig über die
Trefferlisten des Agenten in den Bericht. Und das Web lief für jede Lücke,
auch für solche, die der Korpus längst deckte.

Dieses Modul läuft deterministisch VOR dem Plan und vor jedem Agenten:

  * **Signale je Ebene und Quartal** (`signals_by_tier_quarter`): rohe Zahl
    UND Anteil je 10.000 Signale derselben Ebene im selben Quartal — dieselbe
    Normierung wie die Cluster-Schicht/`pipeline/emerging.py` („Anteil am
    Gehör", damit der eigene Ingest-Zuwachs die Reihe nicht aufbläst). Die
    Ebene kommt aus `pipeline/tiers.tier_of` (Quellname, Quelltyp, Signaltyp).
  * **Akteure** aus `trends.brands`/`companies` (Top 12 mit Zahl, erstem und
    letztem Auftreten) — Untergrenze, weil die Extraktion nur im Artikelpfad
    läuft (Forschung/Patente tragen keine Namen).
  * **Quellen** (Top-Outlets mit Zahl).
  * **Repräsentative Signale** (≤ 16): je Ebene die nützlichsten nach
    `0,5·Aktualität (12-Monats-Fenster) + 0,3·Trefferstärke (Phrase/Name)
    + 0,2·Kosinus zu den Pflichtpunkten` (Embedder, sonst Wortüberdeckung),
    market 6 / patent 3 / science 3 / funding 2 + 2 Regulierungszeilen, je
    Ebene mindestens eine akteurbenannte Zeile, wo es eine gibt; eine Zeile,
    deren Titel weder Themenwort noch Namen trägt, wird nie repräsentativ —
    jedes wird ein zitierbarer Katalogeintrag `T<id>` (wie `_row_to_source`).
  * **Dünne Bereiche** (`thin_areas`): eine Ebene mit < 5 Signalen in den
    letzten 12 Monaten; ein Pflichtpunkt mit < 2 Zeilen, die seine NAMEN
    tragen; Regulatorik und Kalender IMMER, es sei denn ≥ 3 Zeilen in 12
    Monaten nennen ein Instrument des Feldes (Kalender: mit Zukunftsdatum).
  * **Gating** (`web_gating`): nur dünne Bereiche bekommen Web-Schritte,
    Sweeps und Budget (`len(thin) × 4`, mindestens 6, höchstens `web_steps`).

Treffer-Regel des Korpus-Durchgangs (Runde 30, 2026-09-19 — vorher: jeder
Themenstamm irgendwo im Text, „virtual" traf alles): der KERN sind Zeilen, deren
Titel+Teaser+Tags die Themen-PHRASE tragen — alle Themenwörter innerhalb eines
Fensters von PHRASE_WINDOW Wörtern, stamm-unempfindlich („virtualized servers",
„server virtualisation", „virtualization of servers") — ODER deren Vektor zum
Themen-Embedding einen Kosinus >= CORPUS_MIN_COSINE (Env, Default 0,55) hat.
Die Vorauswahl läuft über den FTS-Index (OR der Begriffe und Namen), der
Kosinus wird in SQL nur auf diesen Kandidaten gerechnet: ein reiner ANN-Lauf
brachte am 19.09. 269 Zeilen über Serverless/Microservices ohne ein einziges
Themenwort. Der ERWEITERTE Satz (Runde 28) bleibt namensbasiert: ein Profil-/
Pflichtpunkt-Name plus ein Themenstamm — oder ein Name allein, wenn der Name
themenspezifisch ist (`name_specificity`: Anteil seiner Kandidatenzeilen im
Kern >= NAME_SPECIFICITY_MIN; VMware 0,74, Proxmox 0,83, Nutanix 0,59 gegen
Microsoft 0,14, EU Commission 0,12). SQLite (Tests) nimmt LIKE und hat keinen
Kosinus. Jede DB-Stufe degradiert einzeln — ohne Korpus-Evidenz gilt ALLES als
dünn und der Lauf verhält sich wie vor Stufe 6.

Deckung eines Pflichtpunkts (Runde 30): nur über seine NAMEN — Eigennamen,
Instrumente (SYS.1.5, Art. 28, Regulation (EU) 2023/2854, ISO/IEC 27001) und
Vendor-Namen des Profils —, nie über seine Allerweltswörter; ein Punkt, der
Regulierung/Fristen/Meilensteine/Anforderungen nennt, ist dünn, solange nicht
>= 2 Zeilen das Instrument nennen UND ein Datum der letzten 12 Monate oder der
Zukunft tragen. Regulatorik und Kalender sind IMMER dünn, es sei denn >= 3
Zeilen der letzten 12 Monate nennen ein Instrument DES FELDES (Profil), der
Kalender verlangt dazu Zukunftsdaten — nicht irgendein Regulierungssignal.
"""
from __future__ import annotations

import json
import logging
import re
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime

from pipeline.tiers import TIERS, tier_of

logger = logging.getLogger("dossier_corpus_evidence")

TREND_BASE_DEFAULT = "https://catandary.de/trends"
SINCE_MONTHS = 24
QUARTERS = 8
THIN_TIER_MIN = 5            # Signale einer Ebene in den letzten 12 Monaten
THIN_MUST_MIN = 2            # Korpustreffer je Pflichtpunkt
THIN_REG_MIN = 3             # Regulierungs-/Entscheidungssignale in 12 Monaten
REPRESENTATIVE_MAX = 16
REPRESENTATIVE_PER_TIER = {"market": 6, "patent": 3, "science": 3, "funding": 2}
REPRESENTATIVE_REGULATION = 2
RECENCY_WINDOW_DAYS = 365
PHRASE_WINDOW = 3            # alle Themenwoerter innerhalb von 3 Woertern
DEFAULT_MIN_COSINE = 0.55    # Kosinus-Boden fuer den Kern (Env CORPUS_MIN_COSINE)
NAME_SPECIFICITY_MIN = 0.4   # Anteil der Kandidatenzeilen eines Namens im Kern
NAME_SPECIFICITY_ROWS_MIN = 3
ANN_EF_SEARCH = 1000
ACTORS_TOP = 12
SOURCES_TOP = 8
FETCH_LIMIT = 60_000
PER10K_MIN_TOTAL = 500       # darunter trägt ein Ebene-Quartal keinen Anteil
STATEMENT_TIMEOUT = "90s"
STATUSES = ("signal", "published")
WEB_ACTIONS_PER_THIN = 4
WEB_BUDGET_MIN = 6

_REG_TYPES = frozenset({"regulation", "decision"})
_REG_WORDS = ("regulation", "regulator", "directive", "ruling", "court", "lawsuit",
              "compliance", "legislation", "verordnung", "gesetz", "gericht")
_BRITISH = (("isation", "ization"), ("ising", "izing"), ("ised", "ized"),
            ("centre", "center"), ("yse", "yze"), ("our", "or"))
_SEP = re.compile(r"[\s\-_/.,;:()\[\]'\"]+")
_WORD = re.compile(r"[A-Za-z][A-Za-z0-9+#.-]{2,}")
_STOP = frozenset("""and are the for with from into that this what which when where
how why does did will can could would should about over under between their there
they them then than more most other some such only also been being has have had was
were its you your our not but all any per via who whom whose does apply applies
must need needs does still after before each every much many""".split())


# --------------------------------------------------------------------------
# Textregel
# --------------------------------------------------------------------------

def normalize_text(s: str | None) -> str:
    """Klein, britisch → amerikanisch, alle Trenner raus: „Data-Centre
    Virtualisation" → „datacentervirtualization"."""
    t = (s or "").lower()
    for a, b in _BRITISH:
        t = t.replace(a, b)
    return _SEP.sub("", t)


_SUFFIXES = ("izations", "ization", "isation", "ational", "ations", "ation", "ities",
             "ity", "ers", "ing", "ies", "ed", "es", "er", "s")
_STEM_MIN = 4


def crude_stem(word: str) -> str:
    """Ein einziger Suffix-Schnitt in fester Reihenfolge — bewusst grob, wie
    das FTS-Lexem des Index (Snowball: „virtualization" → „virtual",
    „datacenters" → „datacent"). Der Stamm ist ein Teilstring-Muster über dem
    normalisierten Text, keine Wortgrenze: „virtual" trifft „virtualized" und
    „virtualization" gleichermaßen — dieselbe Reichweite, die die
    Korpus-Zählung (`dossier_corpus_stats`) über `to_tsquery` hat."""
    w = normalize_text(word)
    for suf in _SUFFIXES:
        if w.endswith(suf) and len(w) - len(suf) >= _STEM_MIN:
            return w[: -len(suf)]
    return w


def term_stems(terms) -> list[str]:
    """Je Begriff ein Stamm (Mehrwortbegriffe: Stamm je Wort, verkettet — der
    Text ist ebenfalls trennerfrei normalisiert)."""
    out: list[str] = []
    for t in terms or ():
        n = "".join(crude_stem(w) for w in _SEP.split(str(t).lower()) if w)
        if len(n) >= 3 and n not in out:
            out.append(n)
    return out


def row_text(row: dict) -> str:
    """Titel + Teaser + Tags — dieselben drei Felder wie der FTS-Vektor des
    Index (`dossier_quant.FTS_VECTOR`): ohne die Tags fand die Python-Regel
    am 19.09. 14 statt 50 Zeilen, weil die Klassifikation „data-center" /
    „virtualization" oft nur als Tag steht."""
    tags = row.get("tags")
    if isinstance(tags, list):
        tags = " ".join(str(t) for t in tags)
    return normalize_text(f"{row.get('title_en') or ''} {row.get('summary_en') or ''} {tags or ''}")


def raw_text(row: dict) -> str:
    """Titel + Teaser + Tags, unnormalisiert (für die Lückenregel)."""
    tags = row.get("tags")
    if isinstance(tags, list):
        tags = " ".join(str(t) for t in tags)
    return f"{row.get('title_en') or ''} {row.get('summary_en') or ''} {tags or ''}"


def row_matches(row: dict, stems: list[str]) -> bool:
    """Bis Runde 29 die Kernregel: jeder Themenstamm irgendwo im Text (Teil-
    string). Bleibt fuer die Stamm-Bedingung des erweiterten Satzes und fuer
    Aufrufer, die die alte Reichweite brauchen — der KERN nutzt seit Runde 30
    `phrase_match`."""
    if not stems:
        return False
    hay = row_text(row)
    return all(s in hay for s in stems)


# --------------------------------------------------------------------------
# Runde 30: Phrasenregel, Kosinus-Boden, Daten, Instrumente
# --------------------------------------------------------------------------

_TOKEN = re.compile(r"[a-z0-9]+")


def word_tokens(text: str | None) -> list[str]:
    """Woerter des Textes als grobe Staemme (klein, britisch -> amerikanisch,
    ein Suffix-Schnitt): "Virtualized Servers" -> ["virtual", "serv"]."""
    t = (text or "").lower()
    for a, b in _BRITISH:
        t = t.replace(a, b)
    return [crude_stem(w) for w in _TOKEN.findall(t)]


def term_word_stems(term: str) -> list[str]:
    return [crude_stem(w) for w in _TOKEN.findall(str(term or "").lower()) if w]


_STEM_PREFIX_MIN = 6


def tok_hits(tok: str, stem: str) -> bool:
    """Trifft ein Wort-Token einen Themenstamm? Gleichheit der groben Staemme
    ("servers" -> "serv" == "serv"), oder Praefix ab _STEM_PREFIX_MIN Zeichen
    ("virtualized" beginnt mit "virtual"). Kurze Staemme nur exakt: "serv"
    darf "services", "serving", "observe" NICHT treffen — das war der Grund,
    warum "Design of Virtual Reserve Services" am 19.09. als Phrase galt."""
    if not tok or not stem:
        return False
    if tok == stem:
        return True
    return len(stem) >= _STEM_PREFIX_MIN and tok.startswith(stem)


def _term_spans(toks: list[str], stems: list[str]) -> list[tuple[int, int]]:
    """Wo ein (Mehrwort-)Begriff im Tokenstrom steht: (Start, Ende). Ein
    Begriffswort trifft ein Token, das mit seinem Stamm beginnt; ein
    zusammengeschriebener Begriff ("datacenter") trifft auch zwei Tokens
    ("data", "center") in Folge."""
    out: list[tuple[int, int]] = []
    if not stems:
        return out
    n = len(toks)
    for i in range(n):
        pos = i
        ok = True
        for st in stems:
            if pos >= n:
                ok = False
                break
            if tok_hits(toks[pos], st):
                pos += 1
                continue
            if pos + 1 < n and len(st) >= _STEM_PREFIX_MIN and (toks[pos] + toks[pos + 1]).startswith(st):
                pos += 2
                continue
            ok = False
            break
        if ok:
            out.append((i, pos - 1))
    return out


def phrase_match(row: dict, terms: list[str], window: int = PHRASE_WINDOW) -> bool:
    """Kernregel seit Runde 30: ALLE Themenwoerter innerhalb eines Fensters
    von `window` Woertern (bei mehr Woertern als das Fenster: so viele Woerter
    wie der Begriff hat), stamm-unempfindlich und in beliebiger Reihenfolge —
    "server virtualization", "virtualized servers", "virtualization of
    servers" treffen; "the server farm runs a virtual assistant" nicht."""
    stems_per_term = [term_word_stems(t) for t in (terms or ()) if term_word_stems(t)]
    if not stems_per_term:
        return False
    toks = word_tokens(raw_text(row))
    spans = [_term_spans(toks, st) for st in stems_per_term]
    if any(not sp for sp in spans):
        return False
    if len(spans) == 1:
        return True
    total_words = sum(len(st) for st in stems_per_term)
    span_max = max(window, total_words)
    # kleinste Ausdehnung ueber je eine Fundstelle je Begriff
    for a in spans[0]:
        lo, hi = a
        # greedy: je weiterem Begriff die Fundstelle, die das Fenster am
        # wenigsten dehnt (die Listen sind kurz: Titel + Teaser)
        ok = True
        for sp in spans[1:]:
            best = min(sp, key=lambda b: max(hi, b[1]) - min(lo, b[0]))
            lo, hi = min(lo, best[0]), max(hi, best[1])
            if hi - lo + 1 > span_max:
                ok = False
                break
        if ok:
            return True
    return False


def min_cosine() -> float:
    """Kosinus-Boden fuer den Kern (`CORPUS_MIN_COSINE`, Default 0,55)."""
    import os
    try:
        v = float(os.getenv("CORPUS_MIN_COSINE", str(DEFAULT_MIN_COSINE)) or DEFAULT_MIN_COSINE)
    except ValueError:
        return DEFAULT_MIN_COSINE
    return v if 0.0 < v <= 1.0 else DEFAULT_MIN_COSINE


_MONTHS = ("january", "february", "march", "april", "may", "june", "july", "august",
           "september", "october", "november", "december")
_MONTH_RX = "(?:" + "|".join(m[:3] + r"[a-z]*\.?" for m in _MONTHS) + ")"
_DATE_ISO = re.compile(r"\b(20\d\d)-(\d\d)-(\d\d)\b")
_DATE_DE = re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(20\d\d)\b")
_DATE_DMY = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(" + _MONTH_RX + r")\s+(20\d\d)\b", re.I)
_DATE_MDY = re.compile(r"\b(" + _MONTH_RX + r")\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(20\d\d)\b", re.I)
_DATE_MY = re.compile(r"\b(" + _MONTH_RX + r")\s+(20\d\d)\b", re.I)
_DATE_Q = re.compile(r"\b(?:Q([1-4])|H([12]))\s*(20\d\d)\b", re.I)
_DATE_Y = re.compile(r"\b(20[2-4]\d)\b")


def _month_no(name: str) -> int | None:
    n = name.lower().rstrip(".")[:3]
    for i, m in enumerate(_MONTHS, start=1):
        if m.startswith(n):
            return i
    return None


def text_dates(text: str | None) -> list[tuple[date, str]]:
    """Datumsangaben eines Textes: (Datum, Genauigkeit day|month|quarter|year).
    Ein Quartal/Halbjahr/Jahr traegt seinen LETZTEN Tag (fuer "liegt in der
    Zukunft" zaehlt das Ende der Periode)."""
    t = str(text or "")
    out: list[tuple[date, str]] = []
    seen: set[tuple[int, int]] = set()

    def _add(y: int, m: int, d: int, prec: str) -> None:
        try:
            out.append((date(y, m, d), prec))
        except ValueError:
            return
    for m in _DATE_ISO.finditer(t):
        _add(int(m.group(1)), int(m.group(2)), int(m.group(3)), "day")
        seen.add((m.start(), m.end()))
    for m in _DATE_DE.finditer(t):
        _add(int(m.group(3)), int(m.group(2)), int(m.group(1)), "day")
        seen.add((m.start(), m.end()))
    for m in _DATE_DMY.finditer(t):
        mo = _month_no(m.group(2))
        if mo:
            _add(int(m.group(3)), mo, int(m.group(1)), "day")
            seen.add((m.start(), m.end()))
    for m in _DATE_MDY.finditer(t):
        mo = _month_no(m.group(1))
        if mo:
            _add(int(m.group(3)), mo, int(m.group(2)), "day")
            seen.add((m.start(), m.end()))
    for m in _DATE_MY.finditer(t):
        if any(a <= m.start() < b for a, b in seen):
            continue
        mo = _month_no(m.group(1))
        if mo:
            y = int(m.group(2))
            last = 31 if mo in (1, 3, 5, 7, 8, 10, 12) else (30 if mo != 2 else 28)
            _add(y, mo, last, "month")
            seen.add((m.start(), m.end()))
    for m in _DATE_Q.finditer(t):
        y = int(m.group(3))
        if m.group(1):
            q = int(m.group(1))
            _add(y, q * 3, (31, 30, 30, 31)[q - 1], "quarter")
        else:
            h = int(m.group(2))
            _add(y, 6 if h == 1 else 12, 30 if h == 1 else 31, "quarter")
        seen.add((m.start(), m.end()))
    for m in _DATE_Y.finditer(t):
        if any(a <= m.start() < b for a, b in seen):
            continue
        _add(int(m.group(1)), 12, 31, "year")
    return out


def dated_within(text: str | None, today: date, months: int = 12) -> bool:
    """Traegt der Text ein Datum der letzten `months` Monate oder der Zukunft?
    Ein nacktes Jahr zaehlt nur, wenn es das laufende oder ein spaeteres ist."""
    floor = months_ago(today, months)
    for d, prec in text_dates(text):
        if prec == "year":
            if d.year >= today.year:
                return True
        elif d >= floor:
            return True
    return False


def future_dated(text: str | None, today: date) -> bool:
    """Traegt der Text ein Datum, das nach `today` liegt? Periodenangaben
    (Monat/Quartal/Jahr) zaehlen mit ihrem Ende; ein nacktes Jahr ab dem
    laufenden Jahr."""
    for d, prec in text_dates(text):
        if prec == "year":
            if d.year >= today.year:
                return True
        elif d > today:
            return True
    return False


# Instrumente: Rechtsakte, Bausteine, Normen — was ein Pflichtpunkt oder ein
# Profil als Regelwerk nennt und was eine Korpuszeile woertlich tragen muss.
_INSTRUMENT_RX = (
    re.compile(r"\bSYS[.\s]?\d+(?:\.\d+)*", re.I),
    re.compile(r"\b(?:APP|OPS|CON|ORP|DER|IND|INF|NET)[.\s]?\d+(?:\.\d+)*", re.I),
    re.compile(r"\bArt(?:icles?|\.)?\s?\d+[a-z]?(?:\s?(?:and|,|/|&)\s?\d+[a-z]?)*", re.I),
    re.compile(r"\b(?:Regulation|Directive)\s?\((?:EU|EC)\)\s?(?:No\.?\s?)?\d{4}/\d+", re.I),
    re.compile(r"\b(?:EU|EC)\)?\s?\d{4}/\d{2,4}\b"),
    re.compile(r"\bISO(?:/IEC)?\s?\d{4,5}(?:-\d+)?", re.I),
    re.compile(r"\bNIS\s?2\b", re.I),
    re.compile(r"\b(?:BSI\s)?C5\b"),
    re.compile(r"\bIT-Grundschutz\b", re.I),
    re.compile(r"\bGDPR\b|\bDSGVO\b|\bData Act\b|\bAI Act\b|\bCyber Resilience Act\b|\bDORA\b", re.I),
)
_INSTRUMENT_ITEM = re.compile(
    r"regulat|deadline|support end|end[- ]of[- ]support|end[- ]of[- ]life|milestone|"
    r"requirement|directive|standard|compliance|\blegal\b|\blaw\b|obligation|frist|vorschrift",
    re.I)


def instrument_mentions(text: str | None) -> list[str]:
    """Instrument-Bezeichner eines Textes (SYS.1.5, Art. 28, Regulation (EU)
    2023/2854, ISO/IEC 27001, NIS2, GDPR, Data Act …), dedupliziert."""
    out: list[str] = []
    spans: list[tuple[int, int]] = []
    for rx in _INSTRUMENT_RX:
        for m in rx.finditer(str(text or "")):
            if any(a <= m.start() and m.end() <= b for a, b in spans):
                continue                                   # Teil eines laengeren Bezeichners
            v = " ".join(m.group(0).split()).strip(" .,;:")
            if v and v.lower() not in {x.lower() for x in out}:
                out.append(v)
                spans.append((m.start(), m.end()))
    return out


def is_instrument_item(text: str | None) -> bool:
    """Nennt der Pflichtpunkt Regulierung, Fristen, Meilensteine, Normen oder
    Anforderungen? Dann zaehlt nur eine Zeile, die das Instrument nennt UND
    ein Datum traegt."""
    return bool(_INSTRUMENT_ITEM.search(str(text or "")))


def item_names(item: str, entities: list[str] | None = None) -> list[str]:
    """Die NAMEN eines Pflichtpunkts: Eigennamen (`proper_nouns`), Instrument-
    Bezeichner (Regex) und die Vendor-/Akteursnamen des Profils, die der
    Punkt selbst nennt. Allerweltswoerter bleiben draussen."""
    out: list[str] = []
    for n in proper_nouns(item) + instrument_mentions(item):
        if n and n.lower() not in {x.lower() for x in out}:
            out.append(n)
    for e in entities or ():
        ce_ = clean_entity(e)
        rx = _entity_regex(ce_)
        if rx is not None and rx.search(str(item or "")) and ce_.lower() not in {x.lower() for x in out}:
            out.append(ce_)
    return out


def names_in_row(row: dict, names: list[str]) -> list[str]:
    """Welche Namen die Zeile traegt — Wortgrenze, gross/klein egal; fuer
    Instrument-Bezeichner zusaetzlich die Regex-Form (SYS.1.5 ↔ SYS 1.5)."""
    hit = row_matches_any(row, names)
    if hit:
        return hit
    hay = raw_text(row)
    def _key(x: str) -> str:
        return re.sub(r"[\s.]", "", str(x).lower())
    low_hits = {_key(x) for x in instrument_mentions(hay)}
    out: list[str] = []
    for n in names or ():
        k = _key(clean_entity(n))
        if k and k in low_hits:
            out.append(clean_entity(n))
    return out


# Runde 28 (2026-09-19): erweiterter Satz. Die UND-Regel ueber die Themen-
# begriffe fand fuer "datacenter virtualization" 42 Zeilen, mit den Produkt-
# und Akteursnamen des Profils (Proxmox, VMware, Nutanix, Broadcom …) sind es
# 92 — "VMware" + "virtualization" traegt das Thema, ohne "datacenter". Namen
# aus dem Profil (Stufe 2, `actor_seeds`) und die Eigennamen der Pflichtpunkte
# ersetzen EINEN der Themenbegriffe, nie beide (Messung 19.09.: reines ODER
# ueber die Profilnamen = 1.790 Zeilen, davon 1.213 "Microsoft").
_ENTITY_STOP = frozenset("""
the and for with from into that this what which when where how why who whom
does specific technical procedural regulatory current key top two three
german european eu us uk american chinese french british global regional
article articles act regulation directive section chapter annex
company companies firm firms provider providers service services market
security processing processor controller obligations requirements standard
""".split())
_LEAD_STOP = frozenset("""
which what how why who when where does the german european american chinese french
british swiss austrian dutch italian spanish global regional specific
""".split())
_PROPER = re.compile(r"\b(?:[A-Z][A-Za-z0-9]*(?:[-.][A-Za-z0-9]+)*|[A-Z]{2,}(?:[-.][A-Za-z0-9]+)*)"
                     r"(?:\s+(?:[A-Z][A-Za-z0-9]*(?:[-.][A-Za-z0-9]+)*|[A-Z]{2,}))*")


def clean_entity(name: str) -> str:
    """Profilname ohne Klammerzusatz: "BSI (Federal Office …)" -> "BSI"."""
    n = re.sub(r"\s*\([^)]*\)", "", str(name or "")).strip(" .,;:'\"")
    return n


def proper_nouns(text: str, cap: int = 8) -> list[str]:
    """Eigennamen eines Pflichtpunkts: grossgeschriebene Wortfolgen, nicht am
    Satzanfang, ohne Fuellwoerter und Gattungsbegriffe (`_ENTITY_STOP`),
    Akronyme ab 3 Zeichen; Klammerlisten werden aufgeloest."""
    out: list[str] = []
    text = str(text or "")
    for m in _PROPER.finditer(text):
        at_start = m.start() == 0 or text[max(0, m.start() - 2):m.start()].strip() in (".", "?", "!")
        for k, piece in enumerate(re.split(r"\s*(?:,|/|;|\bor\b|\band\b)\s*", m.group(0))):
            words = piece.split()
            if at_start and k == 0:
                # Satzanfang: das erste Wort ist gross, weil es den Satz beginnt
                # ("Which BSI IT-Grundschutz …" -> "BSI IT-Grundschutz"; Runde 30 —
                # vorher fiel die ganze Fundstelle weg)
                words = words[1:]
            # fuehrende Demonyme/Fragewoerter ab ("German IT" -> "IT"), die
            # Phrase selbst bleibt ganz ("EU Data Act" ist ein Name)
            while words and words[0].lower().strip(".-") in _LEAD_STOP:
                words = words[1:]
            cand = " ".join(words).strip(" .,;:")
            if not cand:
                continue
            if len(cand) < 4 and not (cand.isupper() and len(cand) >= 3):
                continue
            if len(words) == 1 and cand.lower() in _ENTITY_STOP:
                continue
            # "AI-driven", "GPU-based", "post-quantum": ein Attribut, kein Name
            # (Runde 30 — "AI-driven" zog 777 Zeilen in den erweiterten Satz)
            if len(words) == 1 and re.match(r"^[A-Za-z0-9]+-[a-z]", cand):
                continue
            if cand not in out:
                out.append(cand)
            if len(out) >= cap:
                return out
    return out


def _entity_regex(term: str) -> re.Pattern | None:
    t = clean_entity(term)
    if len(t) < 3:
        return None
    words = [re.escape(w) for w in re.split(r"[\s\-]+", t) if w]
    if not words:
        return None
    return re.compile(r"(?<![A-Za-z0-9])" + r"[\s\-]*".join(words) + r"(?![A-Za-z0-9])", re.IGNORECASE)


def row_matches_any(row: dict, terms: list[str]) -> list[str]:
    """Welche der Namen (Wort-/Phrasengrenze, gross/klein egal, Bindestrich
    oder Leerzeichen frei) die Zeile traegt."""
    hay = raw_text(row)
    hit: list[str] = []
    for t in terms or ():
        rx = _entity_regex(t)
        if rx is not None and rx.search(hay):
            hit.append(clean_entity(t))
    return hit


def gap_terms(text: str, cap: int = 6) -> list[str]:
    """Inhaltswörter einer Lücke/eines Pflichtpunkts (≥ 4 Zeichen, ohne
    Füllwörter) — für die Treffer-Regel je Pflichtpunkt."""
    out: list[str] = []
    for w in _WORD.findall((text or "").lower()):
        w = w.strip(".-#+")
        if len(w) < 4 or w in _STOP or w in out:
            continue
        out.append(w)
        if len(out) >= cap:
            break
    return out


def text_hits_gap(text: str, terms: list[str], min_terms: int = 2) -> bool:
    """Ein Text trifft eine Lücke, wenn er mindestens `min_terms` ihrer
    Begriffe trägt (bei einer Ein-Wort-Lücke: diesen)."""
    stems = term_stems(terms)
    if not stems:
        return False
    hay = normalize_text(text)
    need = min(min_terms, len(stems))
    return sum(1 for s in stems if s in hay) >= need


# --------------------------------------------------------------------------
# Zeit
# --------------------------------------------------------------------------

def quarter_of(d) -> str | None:
    s = str(d or "")[:10]
    if len(s) < 7 or not s[:4].isdigit():
        return None
    try:
        y, m = int(s[:4]), int(s[5:7])
    except ValueError:
        return None
    if not 1 <= m <= 12:
        return None
    return f"{y}-Q{(m - 1) // 3 + 1}"


def last_quarters(today: date, n: int = QUARTERS) -> list[str]:
    y, q = today.year, (today.month - 1) // 3 + 1
    out: list[str] = []
    for _ in range(n):
        out.append(f"{y}-Q{q}")
        q -= 1
        if q == 0:
            q, y = 4, y - 1
    return list(reversed(out))


def months_ago(today: date, months: int) -> date:
    y, m = today.year, today.month - months
    while m <= 0:
        m += 12
        y -= 1
    return date(y, m, 1)


def _date_of(row: dict) -> str:
    return str(row.get("sort_date") or row.get("published_at") or "")[:10]


# --------------------------------------------------------------------------
# DB
# --------------------------------------------------------------------------

def _json_list(v) -> list[str]:
    if v is None:
        return []
    if isinstance(v, str):
        try:
            v = json.loads(v)
        except ValueError:
            return []
    if not isinstance(v, list):
        return []
    return [str(x).strip() for x in v if str(x).strip()]


def _is_postgres() -> bool:
    from pipeline import db as db_mod
    return bool(db_mod.USE_POSTGRES)


def source_types() -> dict[str, str | None]:
    """Quellname → Quelltyp (616 Zeilen) — billiger als der Join über
    raw_entries auf jeder Signalzeile."""
    from pipeline.db import get_connection
    with get_connection() as conn:
        rows = conn.execute("SELECT name, source_type FROM sources").fetchall()
    return {str(r["name"]): r["source_type"] for r in (dict(x) for x in rows)}


_TSWORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9+#-]*")


def prequery_tsquery(terms) -> str:
    """OR über die Themenbegriffe für den FTS-Index — jeder Begriff wird von
    `to_tsquery` selbst gestemmt (kein Präfix: „virtualization:*" wird zu
    „virtualizati:*" und trifft das Lexem „virtual" NICHT — Befund am 19.09.,
    0 statt 50 Zeilen). Ein Mehrwortbegriff wird zur UND-Gruppe. Die AND-Regel
    über ALLE Begriffe läuft danach in Python (`row_matches`), weil „data
    center" und „datacenter" im Index verschiedene Lexeme sind."""
    groups: list[str] = []
    for t in terms or ():
        words = [w for w in _TSWORD.findall(str(t).lower()) if len(w) >= 2]
        if not words:
            continue
        g = " & ".join(words)
        groups.append(f"({g})" if len(words) > 1 else g)
    return " | ".join(dict.fromkeys(groups))


def _vec_literal(vec) -> str:
    return "[" + ",".join(f"{float(v):.6f}" for v in list(vec)[:1024]) + "]"


def fetch_topic_rows(stems: list[str], since: date, limit: int = FETCH_LIMIT,
                     terms: list[str] | None = None, entities: list[str] | None = None,
                     topic_nouns: list[str] | None = None, topic_vec=None,
                     must_vecs: list | None = None, floor: float | None = None,
                     stats: dict | None = None) -> list[dict]:
    """Vorauswahl über den Index (Postgres: OR der gestemmten Begriffe UND der
    Namen auf dem FTS-Vektor, neueste zuerst bis `limit`, mit Kosinus zum
    Themen- und zu den Pflichtpunkt-Vektoren als SQL-Spalten; SQLite: LIKE je
    Stamm/Name, ohne Kosinus), dann die Regeln in Python:

      * KERN (`match` = "phrase" | "cosine"): Themen-Phrase (`phrase_match`)
        oder Kosinus zum Themenvektor >= `floor` (Runde 30 — vorher jeder
        Stamm irgendwo, "virtual" traf Virtual Reality und Virtual Assets).
      * ERWEITERT (`extended` = getroffene Namen): ein Profil-/Pflichtpunkt-
        Name plus ein Themenstamm (Runde 28) — oder ein Name allein, wenn er
        themenspezifisch ist: mindestens NAME_SPECIFICITY_MIN seiner
        Kandidatenzeilen (>= NAME_SPECIFICITY_ROWS_MIN) liegen im Kern.

    Jede Zeile trägt `source_type` (per Namen), `tier`, `cos_topic`
    (None ohne Vektor), `cos_must` (Maximum über die Pflichtpunkte) und
    `names` (alle getroffenen Namen, auch im Kern). `stats` (optional, out)
    bekommt `n_candidates`, `name_specificity`, `specific_names`,
    `cosine_available`."""
    from pipeline.db import get_connection
    if not stems:
        return []
    entities = [e for e in (entities or []) if clean_entity(e)]
    topic_nouns = [e for e in (topic_nouns or []) if clean_entity(e)]
    names = [clean_entity(e) for e in entities + topic_nouns]
    floor = min_cosine() if floor is None else float(floor)
    must_vecs = [v for v in (must_vecs or []) if v]
    cols = ("id, slug, status, title_en, summary_en, source_url, source_name, "
            "primary_vertical, published_at, sort_date, trend_signal_type, brands, companies, tags")
    cosine_available = False
    with get_connection() as conn:
        if _is_postgres():
            conn.execute(f"SET statement_timeout = '{STATEMENT_TIMEOUT}'")
            from pipeline.dossier_quant import FTS_VECTOR
            tsq = prequery_tsquery(list(terms if terms is not None else stems) + names)
            if not tsq:
                return []
            extra_cols, params = "", []
            if topic_vec:
                cosine_available = True
                extra_cols += ", 1 - (embedding_1024 <=> ?::vector) AS cos_topic"
                params.append(_vec_literal(topic_vec))
                for i, mv in enumerate(must_vecs):
                    extra_cols += f", 1 - (embedding_1024 <=> ?::vector) AS cos_must_{i}"
                    params.append(_vec_literal(mv))
            sql = (f"SELECT {cols}{extra_cols} FROM trends WHERE {FTS_VECTOR} @@ to_tsquery('english', ?) "
                   f"AND sort_date >= ? AND status IN ({', '.join('?' for _ in STATUSES)}) "
                   f"ORDER BY sort_date DESC LIMIT ?")
            rows = conn.execute(sql, (*params, tsq, since.isoformat(), *STATUSES, limit)).fetchall()
        else:
            hay_sql = ("replace(replace(lower(coalesce(title_en,'') || ' ' || "
                       "coalesce(summary_en,'') || ' ' || coalesce(tags,'')), ' ', ''), '-', '')")
            extra = [normalize_text(n) for n in names]
            extra = [e for e in extra if e]
            like = "(" + " OR ".join(f"{hay_sql} LIKE ?" for _ in stems + extra) + ")"
            params = [f"%{s}%" for s in stems] + [f"%{e}%" for e in extra]
            sql = (f"SELECT {cols} FROM trends WHERE {like} AND sort_date >= ? "
                   f"AND status IN ({', '.join('?' for _ in STATUSES)}) "
                   f"ORDER BY sort_date DESC LIMIT ?")
            rows = conn.execute(sql, (*params, since.isoformat(), *STATUSES, limit)).fetchall()
    types = source_types()
    terms_list = list(terms if terms is not None else stems)
    cands: list[dict] = []
    for r in rows:
        r = dict(r)
        r["phrase"] = phrase_match(r, terms_list)
        ct = r.get("cos_topic")
        r["cos_topic"] = float(ct) if ct is not None else None
        cm = [r.pop(k) for k in list(r.keys()) if k.startswith("cos_must_")]
        cm = [float(x) for x in cm if x is not None]
        r["cos_must"] = max(cm) if cm else None
        toks = word_tokens(raw_text(r))
        r["stem_any"] = any(tok_hits(t, st) for t in toks for st in stems)
        r["names"] = row_matches_any(r, names) if names else []
        r["core"] = bool(r["phrase"] or (r["cos_topic"] is not None and r["cos_topic"] >= floor))
        cands.append(r)
    # Themenspezifitaet je Name: Anteil seiner Kandidatenzeilen im Kern.
    cand_n: Counter = Counter()
    core_n: Counter = Counter()
    for r in cands:
        for n in r["names"]:
            cand_n[n] += 1
            if r["core"]:
                core_n[n] += 1
    specificity = {n: (round(core_n[n] / cand_n[n], 3) if cand_n[n] else None) for n in names}
    specific = [n for n in names if cand_n[n] >= NAME_SPECIFICITY_ROWS_MIN
                and (core_n[n] / cand_n[n]) >= NAME_SPECIFICITY_MIN]
    if stats is not None:
        stats.update({"n_candidates": len(cands), "name_specificity": specificity,
                      "specific_names": specific, "cosine_available": cosine_available,
                      "name_candidates": {n: cand_n[n] for n in names}})
    out: list[dict] = []
    for r in cands:
        ext: list[str] = []
        if r["core"]:
            r["match"] = "phrase" if r["phrase"] else "cosine"
        else:
            if r["names"] and (r["stem_any"] or any(n in specific for n in r["names"])):
                ext = list(r["names"])
            if not ext:
                continue
            r["match"] = "extended"
        r["extended"] = ext
        r["brands"] = _json_list(r.get("brands"))
        r["companies"] = _json_list(r.get("companies"))
        r["tags"] = _json_list(r.get("tags"))
        r["source_type"] = types.get(str(r.get("source_name") or ""))
        r["tier"] = tier_of(r.get("source_name"), r["source_type"], r.get("trend_signal_type"))
        for k in ("phrase", "stem_any", "core"):
            r.pop(k, None)
        out.append(r)
    return out


def fetch_tier_totals(since: date, quarters: list[str]) -> dict[str, dict[str, int]]:
    """Signale je Ebene und Quartal über den GANZEN Korpus (Nenner der
    10k-Normierung). Gruppiert nach Quellname + Signaltyp, die Ebene wird in
    Python zugeordnet (0,4 s auf der Live-DB am 19.09.)."""
    from pipeline.db import get_connection
    with get_connection() as conn:
        if _is_postgres():
            conn.execute(f"SET statement_timeout = '{STATEMENT_TIMEOUT}'")
            rows = conn.execute(
                "SELECT to_char(date_trunc('quarter', sort_date), 'YYYY-MM') AS ym, "
                "source_name, trend_signal_type, count(*) AS n FROM trends "
                f"WHERE sort_date >= ? AND status IN ({', '.join('?' for _ in STATUSES)}) "
                "GROUP BY 1, 2, 3", (since.isoformat(), *STATUSES)).fetchall()
        else:
            rows = conn.execute(
                "SELECT substr(sort_date, 1, 7) AS ym, source_name, trend_signal_type, "
                "count(*) AS n FROM trends WHERE sort_date >= ? "
                f"AND status IN ({', '.join('?' for _ in STATUSES)}) GROUP BY 1, 2, 3",
                (since.isoformat(), *STATUSES)).fetchall()
    types = source_types()
    out: dict[str, dict[str, int]] = {t: {q: 0 for q in quarters} for t in TIERS}
    for r in rows:
        r = dict(r)
        q = quarter_of(str(r.get("ym") or "") + "-01")
        tier = tier_of(r.get("source_name"), types.get(str(r.get("source_name") or "")),
                       r.get("trend_signal_type"))
        if q in out.get(tier or "", {}):
            out[tier][q] += int(r.get("n") or 0)
    return out


# --------------------------------------------------------------------------
# Katalogeintrag (Spiegel von scripts.corpus_research._row_to_source)
# --------------------------------------------------------------------------

def default_row_to_source(row: dict, kind: str) -> dict:
    import os
    base = os.getenv("RESEARCH_TREND_BASE", TREND_BASE_DEFAULT)
    snippet = row.get("summary_en") or row.get("excerpt") or ""
    return {
        "id": f"T{row['id']}", "trend_id": row["id"], "kind": kind,
        "title": (row.get("title_en") or "").strip(),
        "url": (f"{base}/{row['slug']}" if kind == "article" else (row.get("source_url") or "")),
        "origin": row.get("source_url") or "",
        "outlet": row.get("source_name") or "",
        "vertical": row.get("primary_vertical") or "",
        "date": _date_of(row),
        "snippet": " ".join(str(snippet).split())[:420],
    }


# --------------------------------------------------------------------------
# Ergebnis
# --------------------------------------------------------------------------

@dataclass
class CorpusEvidence:
    ok: bool = False
    reason: str | None = None
    terms: list[str] = field(default_factory=list)
    stems: list[str] = field(default_factory=list)
    since: str = ""
    measured_on: str = ""
    seconds: float = 0.0
    n_signals: int = 0
    n_signals_12m: int = 0
    quarters: list[str] = field(default_factory=list)
    signals_by_tier_quarter: dict = field(default_factory=dict)
    tier_totals_12m: dict = field(default_factory=dict)
    actors: list[dict] = field(default_factory=list)
    sources: list[dict] = field(default_factory=list)
    representative: list[dict] = field(default_factory=list)
    must_hits: list[dict] = field(default_factory=list)
    regulatory_12m: int = 0
    thin_areas: list[dict] = field(default_factory=list)
    rendered_md: str = ""
    rows: list[dict] = field(default_factory=list, repr=False)
    # Runde 28: erweiterter Satz (Profil-/Pflichtpunkt-Namen als ODER)
    extra_terms: list[str] = field(default_factory=list)
    rows_extended: list[dict] = field(default_factory=list, repr=False)
    n_signals_extended: int = 0
    n_signals_extended_12m: int = 0
    tier_totals_extended_12m: dict = field(default_factory=dict)
    extended_hits: list[dict] = field(default_factory=list)
    # Runde 30: Phrase/Kosinus-Kern, Namensspezifitaet, Instrumente des Feldes
    min_cosine: float = DEFAULT_MIN_COSINE
    anchor: str = ""
    cosine_available: bool = False
    n_candidates: int = 0
    n_signals_phrase: int = 0
    n_signals_cosine: int = 0
    name_specificity: dict = field(default_factory=dict)
    specific_names: list[str] = field(default_factory=list)
    instruments: list[str] = field(default_factory=list)
    regulatory_named_12m: int = 0
    calendar_named_12m: int = 0

    # -- Abfragen -------------------------------------------------------
    def thin_names(self) -> list[str]:
        return [t["area"] for t in self.thin_areas]

    def is_thin(self, area: str) -> bool:
        return any(t["area"] == area for t in self.thin_areas)

    def gap_is_thin(self, text: str) -> bool:
        """Eine freie Lücke (Audit/Plan/Perspektive) ist dünn, wenn < 2
        Korpuszeilen ihre Begriffe tragen. Ohne Korpus-Evidenz: immer dünn."""
        if not self.ok:
            return True
        terms = gap_terms(text)
        if not terms:
            return True
        hits = sum(1 for r in self.rows if text_hits_gap(raw_text(r), terms))
        # Erweiterte Zeilen zaehlen nur ueber den Namen, der sie hereinholte —
        # sonst deckt "Microsoft" + "virtual" jede Luecke mit zwei Fuellwoertern.
        hits += sum(1 for r in self.rows_extended if _names_in(text, r.get("extended") or []))
        return hits < THIN_MUST_MIN

    def catalog_ids(self) -> set[str]:
        return {s["id"] for s in self.representative}

    def as_dict(self) -> dict:
        """Kompakt für `result["corpus_evidence"]` — ohne die Rohzeilen."""
        return {
            "ok": self.ok, "reason": self.reason, "terms": self.terms, "stems": self.stems,
            "since": self.since, "measured_on": self.measured_on, "seconds": self.seconds,
            "n_signals": self.n_signals, "n_signals_12m": self.n_signals_12m,
            "quarters": self.quarters,
            "signals_by_tier_quarter": self.signals_by_tier_quarter,
            "tier_totals_12m": self.tier_totals_12m,
            "actors": self.actors, "sources": self.sources,
            "representative": [{"id": s["id"], "kind": s["kind"], "tier": s.get("tier"),
                                "title": s.get("title"), "date": s.get("date"),
                                "outlet": s.get("outlet"), "why": s.get("why"),
                                "score": s.get("score")}
                               for s in self.representative],
            "must_hits": self.must_hits, "regulatory_12m": self.regulatory_12m,
            "thin_areas": self.thin_areas, "rendered_md": self.rendered_md,
            "extra_terms": self.extra_terms, "n_signals_extended": self.n_signals_extended,
            "n_signals_extended_12m": self.n_signals_extended_12m,
            "tier_totals_extended_12m": self.tier_totals_extended_12m,
            "extended_hits": self.extended_hits,
            "min_cosine": self.min_cosine, "anchor": self.anchor,
            "cosine_available": self.cosine_available,
            "n_candidates": self.n_candidates, "n_signals_phrase": self.n_signals_phrase,
            "n_signals_cosine": self.n_signals_cosine, "name_specificity": self.name_specificity,
            "specific_names": self.specific_names, "instruments": self.instruments,
            "regulatory_named_12m": self.regulatory_named_12m,
            "calendar_named_12m": self.calendar_named_12m,
        }


# --------------------------------------------------------------------------
# Zählung
# --------------------------------------------------------------------------

def tally_tier_quarter(rows: list[dict], quarters: list[str],
                       totals: dict[str, dict[str, int]] | None) -> dict:
    counts: dict[str, Counter] = {t: Counter() for t in TIERS}
    for r in rows:
        t, q = r.get("tier"), quarter_of(_date_of(r))
        if t in counts and q in quarters:
            counts[t][q] += 1
    out: dict = {}
    for t in TIERS:
        out[t] = {}
        for q in quarters:
            n = int(counts[t][q])
            tot = int((totals or {}).get(t, {}).get(q, 0) or 0)
            per = round(n * 10_000 / tot, 2) if tot >= PER10K_MIN_TOTAL else None
            out[t][q] = {"n": n, "per_10k": per, "total": tot}
    return out


def tally_actors(rows: list[dict], top: int = ACTORS_TOP) -> list[dict]:
    counts: Counter = Counter()
    first: dict[str, str] = {}
    last: dict[str, str] = {}
    canon: dict[str, str] = {}
    for r in rows:
        d = _date_of(r)
        for name in r.get("brands", []) + r.get("companies", []):
            key = name.lower()
            canon.setdefault(key, name)
            counts[key] += 1
            if d:
                first[key] = min(first.get(key, d), d)
                last[key] = max(last.get(key, d), d)
    return [{"name": canon[k], "n": n, "first": first.get(k), "last": last.get(k)}
            for k, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:top]]


def tally_sources(rows: list[dict], top: int = SOURCES_TOP) -> list[dict]:
    counts: Counter = Counter(str(r.get("source_name") or "") for r in rows)
    counts.pop("", None)
    return [{"name": k, "n": n} for k, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:top]]


def regulatory_count(rows: list[dict], since: date) -> int:
    """Regulierungs-/Entscheidungssignale nach Typ oder Wortliste — seit
    Runde 30 nur noch Anzeige, nicht mehr Gate (v9: 16 solcher Signale, keines
    ueber das Feld — "EU Commission draft on online game providers")."""
    n = 0
    for r in rows:
        if _date_of(r) < since.isoformat():
            continue
        if str(r.get("trend_signal_type") or "").lower() in _REG_TYPES:
            n += 1
            continue
        hay = f"{r.get('title_en') or ''} {r.get('summary_en') or ''}".lower()
        if any(w in hay for w in _REG_WORDS):
            n += 1
    return n


def instrument_rows(rows: list[dict], instruments: list[str], since: date,
                    today: date | None = None, future: bool = False) -> list[dict]:
    """Zeilen seit `since`, die ein Instrument DES FELDES nennen — die Profil-
    Instrumente (`regulators`, ohne Klammerzusatz) oder einen Instrument-
    Bezeichner aus dem Profil-Text (SYS.1.5, Art. 28, ISO/IEC 27001 …). Mit
    `future` nur Zeilen, die zusaetzlich ein Zukunftsdatum tragen (Kalender)."""
    names: list[str] = []
    for i in instruments or ():
        c = clean_entity(i)
        if c and c.lower() not in {x.lower() for x in names}:
            names.append(c)
        for m in instrument_mentions(str(i or "")):
            if m.lower() not in {x.lower() for x in names}:
                names.append(m)
    if not names:
        return []
    out: list[dict] = []
    for r in rows:
        if _date_of(r) < since.isoformat():
            continue
        hit = names_in_row(r, names)
        if not hit:
            continue
        if future and (today is None or not future_dated(raw_text(r), today)):
            continue
        out.append(r)
    return out


def _days_ago(row: dict, today: date) -> float | None:
    d = _date_of(row)
    if len(d) < 10:
        return None
    try:
        return float((today - date.fromisoformat(d)).days)
    except ValueError:
        return None


def _title_stem(row: dict, stems: list[str]) -> bool:
    toks = word_tokens(row.get("title_en") or "")
    return any(tok_hits(t, st) or (i + 1 < len(toks) and len(st) >= _STEM_PREFIX_MIN
                                    and (t + toks[i + 1]).startswith(st))
               for i, t in enumerate(toks) for st in stems)


def _title_has_topic(row: dict, stems: list[str], names: list[str],
                     specific: list[str] | None = None) -> bool:
    """Darf die Zeile repraesentativ werden? Kern-Zeilen: der Titel traegt ein
    Themenwort oder einen Namen. Erweiterte Zeilen: der Titel traegt einen
    THEMENSPEZIFISCHEN Namen oder die Phrase — ein generischer Name
    ("Microsoft", "EU Commission") macht keine Zeile repraesentativ (v9:
    "EU Commission draft on online game providers", "Microsoft update risks
    credential rejection" standen ueber Microsoft/EU Commission im Bericht)."""
    title_row = {"title_en": row.get("title_en") or "", "summary_en": "", "tags": []}
    if row.get("extended"):
        return bool(row_matches_any(title_row, list(specific or [])))
    if _title_stem(row, stems):
        return True
    return bool(row_matches_any(title_row, names))


def _actor_named(row: dict, names: list[str]) -> bool:
    if row.get("brands") or row.get("companies"):
        return True
    title_row = {"title_en": row.get("title_en") or "", "summary_en": "", "tags": []}
    return bool(row_matches_any(title_row, names))


def _token_overlap(row: dict, must_terms: list[list[str]]) -> float:
    """Rueckfall ohne Embedder: groesste Wortueberdeckung mit einem
    Pflichtpunkt (Staemme der Inhaltswoerter)."""
    if not must_terms:
        return 0.0
    toks = set(word_tokens(raw_text(row)))
    best = 0.0
    for terms in must_terms:
        stems = [crude_stem(t) for t in terms]
        if not stems:
            continue
        hit = sum(1 for st in stems if any(tok.startswith(st) for tok in toks))
        best = max(best, hit / len(stems))
    return best


def score_row(row: dict, today: date, stems: list[str], names: list[str],
              must_terms: list[list[str]]) -> dict:
    """Nutzen einer Zeile als repraesentatives Signal (Runde 30):
    0,5·Aktualitaet (linear ueber RECENCY_WINDOW_DAYS) + 0,3·Trefferstaerke
    (Phrase 1,0; Kosinus-Kern 0,6; Name im Titel 0,8 (+0,1 je weiterem, max
    1,0); Name nur im Teaser 0,5) + 0,2·Kosinus zu den Pflichtpunkten
    (Embedder; sonst Wortueberdeckung)."""
    days = _days_ago(row, today)
    recency = 0.0 if days is None else max(0.0, min(1.0, 1.0 - days / RECENCY_WINDOW_DAYS))
    title_row = {"title_en": row.get("title_en") or "", "summary_en": "", "tags": []}
    title_names = row_matches_any(title_row, names) if names else []
    if row.get("match") == "phrase":
        strength = 1.0
    elif row.get("match") == "cosine":
        strength = 0.6 if not title_names else 0.8
    elif title_names:
        strength = min(1.0, 0.8 + 0.1 * (len(title_names) - 1))
    else:
        strength = 0.5
    cm = row.get("cos_must")
    must = float(cm) if cm is not None else _token_overlap(row, must_terms)
    must = max(0.0, min(1.0, must))
    score = 0.5 * recency + 0.3 * strength + 0.2 * must
    return {"score": round(score, 3), "recency": round(recency, 2), "match": round(strength, 2),
            "must": round(must, 2)}


def pick_representative(rows: list[dict], search=None, topic: str = "", stems: list[str] | None = None,
                        row_to_source=None, cap: int = REPRESENTATIVE_MAX, *,
                        today: date | None = None, names: list[str] | None = None,
                        must_terms: list[list[str]] | None = None,
                        instruments: list[str] | None = None,
                        per_tier: dict | None = None,
                        specific_names: list[str] | None = None) -> list[dict]:
    """Je Ebene die nuetzlichsten Zeilen (`score_row`), market 6 / patent 3 /
    science 3 / funding 2, plus REPRESENTATIVE_REGULATION Zeilen, die ein
    Instrument des Feldes nennen oder vom Typ regulation/decision sind. Je
    Ebene mindestens eine akteurbenannte Zeile, wo es eine gibt. Zeilen, deren
    Titel weder Themenwort noch Namen traegt, werden nie repraesentativ (v9:
    vier akteurlose Patente und "AliveCor … Medicare" standen in der Tabelle).
    `search` wird seit Runde 30 nicht mehr benutzt (die zentrumsnaechsten
    Treffer der Vektorsuche waren undatiert und ohne Ebene)."""
    to_src = row_to_source or default_row_to_source
    today = today or datetime.now().date()
    stems = list(stems or [])
    names = list(names or [])
    must_terms = list(must_terms or [])
    per_tier = dict(per_tier or REPRESENTATIVE_PER_TIER)
    scored: list[tuple[dict, dict]] = []
    specific = list(specific_names or [])
    for r in rows:
        if not _title_has_topic(r, stems, names, specific):
            continue
        scored.append((r, score_row(r, today, stems, names, must_terms)))
    scored.sort(key=lambda rs: (-rs[1]["score"], _date_of(rs[0]) == "", str(rs[0].get("id"))))
    out: list[dict] = []
    seen: set[str] = set()

    def _emit(r: dict, sc: dict, tier_label: str | None, why: str) -> None:
        kind = "article" if r.get("status") == "published" else "signal"
        src = to_src(r, kind)
        if src["id"] in seen:
            return
        src["tier"] = tier_label or r.get("tier")
        src["why"] = why
        src["score"] = sc
        src["fetched"] = True
        seen.add(src["id"])
        out.append(src)
        logger.info("representative %s [%s] %.3f (recency %.2f, match %.2f, must %.2f) %s: %s",
                    src["id"], src["tier"] or "?", sc["score"], sc["recency"], sc["match"],
                    sc["must"], why, (r.get("title_en") or "")[:80])

    for t in TIERS:
        k = int(per_tier.get(t, 0))
        if k <= 0:
            continue
        tier_rows = [(r, sc) for r, sc in scored if r.get("tier") == t]
        take = tier_rows[:k]
        if take and not any(_actor_named(r, specific or names) for r, _ in take):
            named = next(((r, sc) for r, sc in tier_rows[k:] if _actor_named(r, specific or names)), None)
            if named is not None:
                take = take[:-1] + [named]
        for r, sc in take:
            why = "extended: " + ", ".join(r.get("extended") or [])[:60] if r.get("extended") else str(r.get("match") or "phrase")
            _emit(r, sc, t, why)
    # Regulierungszeilen: Instrument des Feldes oder Signaltyp regulation/decision
    reg_ids = {f"T{r['id']}" for r in instrument_rows(rows, instruments or [], date(1900, 1, 1))}
    reg_rows = [(r, sc) for r, sc in scored
                if f"T{r['id']}" in reg_ids or str(r.get("trend_signal_type") or "").lower() in _REG_TYPES]
    taken = 0
    for r, sc in reg_rows:
        if taken >= REPRESENTATIVE_REGULATION:
            break
        if f"T{r['id']}" in seen:
            continue
        _emit(r, sc, r.get("tier"), "regulation")
        taken += 1
    return out[:cap + REPRESENTATIVE_REGULATION]


def must_answer_hits(must: list[str], rows: list[dict], search=None, stems: list[str] | None = None,
                     *, entities: list[str] | None = None, instruments: list[str] | None = None,
                     today: date | None = None, specific_names: list[str] | None = None) -> list[dict]:
    """Deckung je Pflichtpunkt (Runde 30): gezaehlt werden nur Zeilen (Kern +
    erweitert), die einen NAMEN des Punkts tragen (`item_names`: Eigennamen,
    Instrument-Bezeichner, Vendor-Namen des Profils, die der Punkt nennt).
    Ein Punkt ueber Regulierung/Fristen/Meilensteine/Anforderungen zaehlt eine
    Zeile nur, wenn sie das Instrument nennt UND ein Datum der letzten 12
    Monate oder der Zukunft traegt; nennt er selbst kein Instrument, gelten
    die Instrumente des Profils und die THEMENSPEZIFISCHEN Vendor-Namen
    (`specific_names`; "Microsoft ends support for Windows 11" deckt keine
    Frist der Server-Virtualisierung) als seine Namen. Ein
    Punkt ganz ohne Namen (z. B. "Wo steht die Technologie im Zyklus?") wird
    ueber seine Inhaltswoerter gegen den KERN gezaehlt — der ist seit Runde 30
    praezise genug dafuer. `search` wird nicht mehr benutzt."""
    today = today or datetime.now().date()
    out: list[dict] = []
    ents = [clean_entity(e) for e in (entities or []) if clean_entity(e)]
    instr = [clean_entity(i) for i in (instruments or []) if clean_entity(i)]
    for item in must:
        names = item_names(item, ents)
        instrument_item = is_instrument_item(item)
        via = "names"
        if instrument_item and not names:
            names = list(dict.fromkeys(instr + [clean_entity(n) for n in (specific_names or [])]))
            via = "profile instruments + topic-specific vendors"
        ids: set[str] = set()
        if names:
            for r in rows:
                if not names_in_row(r, names):
                    continue
                if instrument_item and not dated_within(raw_text(r), today):
                    continue
                ids.add(f"T{r['id']}")
        else:
            via = "common words (no names in the item)"
            terms = gap_terms(item)
            for r in rows:
                if r.get("extended"):
                    continue
                if terms and text_hits_gap(raw_text(r), terms):
                    ids.add(f"T{r['id']}")
        out.append({"item": item, "terms": gap_terms(item), "names": names[:12],
                    "instrument": instrument_item, "via": via, "hits": len(ids),
                    "thin": len(ids) < THIN_MUST_MIN})
    return out


def find_thin_areas(tier_12m: dict[str, int], must_hits: list[dict], reg_12m: int,
                    reg_named_12m: int | None = None, cal_named_12m: int | None = None) -> list[dict]:
    """Ebenen < THIN_TIER_MIN, duenne Pflichtpunkte, und Regulatorik/Kalender:
    seit Runde 30 IMMER duenn, es sei denn >= THIN_REG_MIN Zeilen der letzten
    12 Monate nennen ein Instrument des Feldes (`reg_named_12m`); der Kalender
    verlangt dazu Zukunftsdaten (`cal_named_12m`). Ohne die beiden Zaehler
    (alte Aufrufer) gilt die alte Regel ueber `reg_12m`."""
    out: list[dict] = []
    for t in TIERS:
        n = int(tier_12m.get(t, 0))
        if n < THIN_TIER_MIN:
            out.append({"area": t, "kind": "tier",
                        "reason": f"{n} signal(s) on the {t} tier in the last 12 months (< {THIN_TIER_MIN})"})
    for m in must_hits:
        if m.get("thin"):
            how = ("naming " + ", ".join(m.get("names") or [])[:80]) if m.get("names") else "on its terms"
            if m.get("instrument"):
                how += " with a date in the last 12 months or ahead"
            out.append({"area": m["item"], "kind": "must",
                        "reason": f"{m['hits']} corpus row(s) {how} (< {THIN_MUST_MIN})"})
    if reg_named_12m is None:
        if reg_12m < THIN_REG_MIN:
            why = f"{reg_12m} regulation/decision signal(s) in 12 months (< {THIN_REG_MIN})"
            out.append({"area": "regulatory", "kind": "fixed", "reason": why})
            out.append({"area": "calendar", "kind": "fixed", "reason": why})
        return out
    if reg_named_12m < THIN_REG_MIN:
        out.append({"area": "regulatory", "kind": "fixed",
                    "reason": f"{reg_named_12m} corpus row(s) in 12 months naming an instrument of this "
                              f"field (< {THIN_REG_MIN}; {reg_12m} generic regulation signal(s) do not count)"})
    cal = int(cal_named_12m or 0)
    if cal < THIN_REG_MIN:
        out.append({"area": "calendar", "kind": "fixed",
                    "reason": f"{cal} corpus row(s) in 12 months naming an instrument of this field "
                              f"AND carrying a future date (< {THIN_REG_MIN})"})
    return out


def _names_in(text: str, names: list[str]) -> bool:
    low = normalize_text(text)
    return any(normalize_text(n) and normalize_text(n) in low for n in names)


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------

def render_block(ev: CorpusEvidence) -> str:
    """Kompakter Prompt-Block: Tabelle Ebene × letzte 8 Quartale (n, Anteil je
    10k), Akteure, Quellen, repräsentative Signale mit ids."""
    if not ev.ok:
        return f"(no corpus evidence: {ev.reason})"
    L: list[str] = []
    L.append(f"Corpus signals carrying the topic phrase '{' '.join(ev.terms)}' (all words within "
             f"{PHRASE_WINDOW} words) or a vector cosine >= {ev.min_cosine:g} to the topic anchor "
             f"(topic plus the names from brief and profile)"
             + ("" if ev.cosine_available else " (no embedder this run — phrase rule only)")
             + f", since {ev.since} (measured {ev.measured_on}): {ev.n_signals:,} "
             f"(phrase {ev.n_signals_phrase:,}, cosine-only {ev.n_signals_cosine:,}) — "
             f"{ev.n_signals_12m:,} in the last 12 months. Per tier and quarter: count, and share "
             f"per 10,000 signals of that tier in that quarter (\"—\" = tier too small that "
             f"quarter to carry a share).")
    L.append("")
    L.append("| Tier | " + " | ".join(ev.quarters) + " |")
    L.append("|---|" + "---|" * len(ev.quarters))
    for t in TIERS:
        cells = []
        for q in ev.quarters:
            c = ev.signals_by_tier_quarter.get(t, {}).get(q, {"n": 0, "per_10k": None})
            per = c.get("per_10k")
            cells.append(f"{c['n']}" + (f" ({per:g}/10k)" if per is not None else " (—)"))
        L.append(f"| {t} | " + " | ".join(cells) + " |")
    L.append("")
    if ev.actors:
        L.append("Actors named in these signals (extracted names; a floor, not a census): "
                 + "; ".join(f"{a['name']} ×{a['n']} ({a['first']}–{a['last']})" if a.get("first")
                             else f"{a['name']} ×{a['n']}" for a in ev.actors))
    else:
        L.append("Actors: none extracted on these signals (extraction runs only on the article path).")
    if ev.sources:
        L.append("Outlets: " + "; ".join(f"{s['name']} ×{s['n']}" for s in ev.sources))
    L.append(f"Rows in 12 months naming an instrument of this field "
             f"({', '.join(ev.instruments[:6]) or 'no instruments in the profile'}): "
             f"{ev.regulatory_named_12m}, of which future-dated {ev.calendar_named_12m} "
             f"(generic regulation/decision signals: {ev.regulatory_12m} — they do not count).")
    if ev.extra_terms:
        tt = ev.tier_totals_extended_12m or {}
        L.append(f"EXTENDED set (flagged, not in the table above — signals carrying ONE topic term "
                 f"plus a product/actor name from the brief or the field profile: "
                 f"{', '.join(ev.extra_terms[:10])}): {ev.n_signals_extended:,} further signal(s) "
                 f"since {ev.since}, {ev.n_signals_extended_12m:,} in 12 months ("
                 + ", ".join(f"{t} {int(tt.get(t, 0))}" for t in TIERS) + ")"
                 + ("; names hit: " + "; ".join(f"{h['name']} ×{h['n']}" for h in ev.extended_hits[:8])
                    if ev.extended_hits else "")
                 + ("; topic-specific names (a name alone carries the topic): "
                    + ", ".join(ev.specific_names) if ev.specific_names else "") + ".")
    L.append("")
    if ev.representative:
        L.append("Representative signals (cite by id; the most useful per tier — recency, match "
                 "strength, fit to the must-answer points; 'extended' = matched by a product/actor name):")
        for s in ev.representative:
            sc = s.get("score") or {}
            L.append(f"- [[{s['id']}]] [{s['kind']}] {s.get('date') or '—'} · {s.get('tier') or '?'} · "
                     f"{s.get('title')}" + (f" — {s['outlet']}" if s.get("outlet") else "")
                     + f" ({s.get('why')}" + (f", score {sc.get('score'):.2f}" if sc.get("score") is not None else "") + ")")
    else:
        L.append("Representative signals: none — no corpus row carries the topic phrase or a topic-specific name in its title.")
    L.append("")
    if ev.thin_areas:
        L.append("THIN in the corpus (the web is used ONLY here): "
                 + "; ".join(f"{t['area']} — {t['reason']}" for t in ev.thin_areas))
    else:
        L.append("Nothing thin in the corpus — no web research was needed.")
    return "\n".join(L)


def render_note(ev: CorpusEvidence) -> str:
    return ("Deterministic corpus evidence — our own count over the corpus, run before any "
            "model hop. Figures here carry NO citation; the representative signals below "
            "are catalog entries and are cited by id:\n" + render_block(ev))


# --------------------------------------------------------------------------
# Einstieg
# --------------------------------------------------------------------------

def build(topic: str, brief: dict | None = None, *, terms: list[str] | None = None,
          search=None, since_months: int = SINCE_MONTHS, today: date | None = None,
          row_to_source=None, entities: list[str] | None = None,
          instruments: list[str] | None = None, embed=None) -> CorpusEvidence:
    """Der Korpus-Durchgang. Gibt IMMER ein CorpusEvidence zurück; jeder DB-
    oder Suchfehler wird zum Fehlgrund (`ok=False`), nie zum Absturz.

    Runde 28: `entities` (Akteur-/Produktnamen des Profils, Stufe 2) und die
    Eigennamen der Pflichtpunkte des Auftrags bilden den ERWEITERTEN Satz.
    Runde 30: `instruments` (Profil-`regulators`) tragen die Regulatorik-/
    Kalender-Regel und die Deckung der Instrument-Pflichtpunkte; `embed`
    (Text → Vektor, der CPU-Embedder) liefert den Themenvektor fuer den
    Kosinus-Boden des Kerns und die Pflichtpunkt-Vektoren fuer die Auswahl der
    repraesentativen Zeilen — faellt der Embedder aus, gilt die Phrasenregel
    allein und die Wortueberdeckung ersetzt den Kosinus (im Log vermerkt)."""
    t0 = time.time()
    today = today or datetime.now().date()
    ev = CorpusEvidence(measured_on=today.isoformat())
    ev.terms = [str(t) for t in (terms or []) if str(t).strip()]
    if not ev.terms:
        ev.terms = gap_terms(topic, cap=4)
    ev.stems = term_stems(ev.terms)
    ev.min_cosine = min_cosine()
    since = months_ago(today, since_months)
    ev.since = since.isoformat()
    ev.quarters = last_quarters(today, QUARTERS)
    must = [str(m) for m in ((brief or {}).get("must_answer") or []) if str(m).strip()]
    ents = [clean_entity(e) for e in (entities or []) if clean_entity(e)]
    ents = [e for e in dict.fromkeys(ents) if e.lower() not in {t.lower() for t in ev.terms}]
    nouns: list[str] = []
    for item in must:
        for n in proper_nouns(item):
            if n.lower() not in {e.lower() for e in ents} and n.lower() not in {t.lower() for t in ev.terms}:
                if n not in nouns:
                    nouns.append(n)
    ev.extra_terms = ents + nouns
    ev.instruments = [clean_entity(i) for i in (instruments or []) if clean_entity(i)]
    if not ev.stems:
        ev.reason = "no usable topic terms"
        ev.rendered_md = render_block(ev)
        return ev
    topic_vec = None
    must_vecs: list = []
    # Ankertext fuer den Kosinus: Thema PLUS die Namen aus Profil und Auftrag.
    # Gemessen 19.09. (Kandidatensatz 6.644 Zeilen, Boden 0,55): "server
    # virtualization" allein -> 208 Zeilen, darunter 24 Virtual-Reality-/
    # Virtual-Asset-Treffer (der Vektor haengt am Wort "virtual"); Thema +
    # Namen -> 47 Zeilen, 14 mit Vendor im Titel, 0 VR-Treffer.
    ev.anchor = (" ".join(ev.terms) if ev.terms else topic) + (
        ": " + ", ".join(ev.extra_terms[:16]) if ev.extra_terms else "")
    if embed is not None:
        try:
            topic_vec = embed(ev.anchor)
            must_vecs = [embed(m) for m in must]
        except Exception as exc:                                    # noqa: BLE001
            logger.warning("corpus evidence: embedder unavailable (%r) — phrase rule only, "
                           "token overlap for the must-answer score", exc)
            topic_vec, must_vecs = None, []
    stats: dict = {}
    try:
        rows_all = fetch_topic_rows(ev.stems, since, terms=ev.terms, entities=ents, topic_nouns=nouns,
                                    topic_vec=topic_vec, must_vecs=must_vecs, floor=ev.min_cosine,
                                    stats=stats)
        rows = [r for r in rows_all if not r.get("extended")]
        rows_ext = [r for r in rows_all if r.get("extended")]
    except Exception as exc:                                        # noqa: BLE001
        logger.warning("corpus evidence: topic rows not measured (%r)", exc)
        ev.reason = f"corpus rows not measured ({type(exc).__name__})"
        ev.rendered_md = render_block(ev)
        return ev
    totals: dict | None = None
    try:
        totals = fetch_tier_totals(since, ev.quarters)
    except Exception as exc:                                        # noqa: BLE001
        logger.warning("corpus evidence: tier totals not measured (%r) — raw counts only", exc)
    ev.ok = True
    ev.cosine_available = bool(stats.get("cosine_available"))
    ev.n_candidates = int(stats.get("n_candidates") or 0)
    ev.name_specificity = dict(stats.get("name_specificity") or {})
    ev.specific_names = list(stats.get("specific_names") or [])
    ev.rows = rows
    ev.rows_extended = rows_ext
    ev.n_signals = len(rows)
    ev.n_signals_phrase = sum(1 for r in rows if r.get("match") == "phrase")
    ev.n_signals_cosine = sum(1 for r in rows if r.get("match") == "cosine")
    cut12 = months_ago(today, 12).isoformat()
    rows12 = [r for r in rows if _date_of(r) >= cut12]
    ev.n_signals_12m = len(rows12)
    ev.n_signals_extended = len(rows_ext)
    ext12 = [r for r in rows_ext if _date_of(r) >= cut12]
    ev.n_signals_extended_12m = len(ext12)
    ev.tier_totals_extended_12m = {t: sum(1 for r in ext12 if r.get("tier") == t) for t in TIERS}
    hits: Counter = Counter(n for r in rows_ext for n in (r.get("extended") or []))
    ev.extended_hits = [{"name": k, "n": n} for k, n in sorted(hits.items(), key=lambda kv: (-kv[1], kv[0]))]
    ev.signals_by_tier_quarter = tally_tier_quarter(rows, ev.quarters, totals)
    ev.tier_totals_12m = {t: sum(1 for r in rows12 if r.get("tier") == t) for t in TIERS}
    ev.actors = tally_actors(rows)
    ev.sources = tally_sources(rows)
    since12 = months_ago(today, 12)
    ev.regulatory_12m = regulatory_count(rows, since12)
    ev.regulatory_named_12m = len(instrument_rows(rows + rows_ext, ev.instruments, since12))
    ev.calendar_named_12m = len(instrument_rows(rows + rows_ext, ev.instruments, since12,
                                                today=today, future=True))
    must_terms = [gap_terms(m) for m in must]
    ev.representative = pick_representative(rows + rows_ext, None, topic, ev.stems, row_to_source,
                                            today=today, names=ev.extra_terms, must_terms=must_terms,
                                            instruments=ev.instruments, specific_names=ev.specific_names)
    ev.must_hits = must_answer_hits(must, rows + rows_ext, None, ev.stems, entities=ents,
                                    instruments=ev.instruments, today=today,
                                    specific_names=ev.specific_names)
    ev.thin_areas = find_thin_areas(ev.tier_totals_12m, ev.must_hits, ev.regulatory_12m,
                                    ev.regulatory_named_12m, ev.calendar_named_12m)
    ev.seconds = round(time.time() - t0, 1)
    ev.rendered_md = render_block(ev)
    logger.info("corpus evidence: %d core signal(s) since %s (phrase %d, cosine %d%s; %d in 12 months), "
                "tiers 12m %s, %d actor(s), %d representative, extended +%d (%s; specific: %s), "
                "instrument rows 12m %d (future-dated %d), thin: %s (%.1fs)",
                ev.n_signals, ev.since, ev.n_signals_phrase, ev.n_signals_cosine,
                "" if ev.cosine_available else ", no embedder", ev.n_signals_12m, ev.tier_totals_12m,
                len(ev.actors), len(ev.representative), ev.n_signals_extended,
                ", ".join(ev.extra_terms[:6]) or "no names", ", ".join(ev.specific_names) or "none",
                ev.regulatory_named_12m, ev.calendar_named_12m,
                ", ".join(ev.thin_names()) or "nothing", ev.seconds)
    return ev


# --------------------------------------------------------------------------
# Gating: Web nur, wo der Korpus dünn ist
# --------------------------------------------------------------------------

def web_gating(ev: CorpusEvidence | None, gaps: list[str], gap_kinds: list[str],
               web_steps: int) -> dict:
    """Welche Lücken ans Web gehen, welche Sweeps laufen, wie viel Budget.

    * Pflichtpunkte: nur die mit < 2 Korpustreffern (`must_hits`).
    * Audit-/Plan-/Perspektiv-Lücken: nur wenn `gap_is_thin` (< 2 Zeilen des
      Korpus-Durchgangs tragen ihre Begriffe).
    * Sweeps: Regulatorik ↔ „regulatory" dünn; Markt ↔ Markt-Ebene dünn;
      Förderung ↔ Förder-Ebene dünn; Katalysator/Kalender ↔ „calendar" dünn.
    * Budget: `len(thin) × 4`, mindestens 6, höchstens `web_steps`.
    Ohne Korpus-Evidenz (ok=False) ist alles dünn = Verhalten vor Stufe 6."""
    ok = bool(ev and ev.ok)
    thin_must = {m["item"].lower() for m in ((ev.must_hits if ev else []) or []) if m.get("thin")}
    decisions: list[dict] = []
    web_idx: list[int] = []
    for i, (g, k) in enumerate(zip(gaps, gap_kinds)):
        if not ok:
            keep, why = True, "no corpus evidence — everything counts as thin"
        elif k == "must":
            keep = g.lower() in thin_must
            why = "must-answer point thin in the corpus" if keep else "must-answer point covered by the corpus"
        else:
            keep = ev.gap_is_thin(g)
            why = "gap terms thin in the corpus" if keep else "gap terms covered by the corpus"
        decisions.append({"index": i, "kind": k, "gap": g[:120], "web": keep, "why": why})
        if keep:
            web_idx.append(i)
    if not ok:
        sweeps = {"regulatory": True, "market": True, "funding": True, "catalyst": True}
        budget = int(web_steps)
        thin = []
    else:
        sweeps = {"regulatory": ev.is_thin("regulatory"), "market": ev.is_thin("market"),
                  "funding": ev.is_thin("funding"), "catalyst": ev.is_thin("calendar")}
        thin = ev.thin_names()
        budget = min(int(web_steps), max(WEB_BUDGET_MIN, WEB_ACTIONS_PER_THIN * len(thin)))
        if web_steps <= 0:
            budget = 0
    return {"corpus_evidence_ok": ok, "thin_areas": thin, "web_gaps": web_idx,
            "corpus_only_gaps": [i for i in range(len(gaps)) if i not in web_idx],
            "sweeps": sweeps, "web_budget": budget, "web_steps": int(web_steps),
            "decisions": decisions}


# --------------------------------------------------------------------------
# Was das Web zu den dünnen Bereichen ergab (Sektion „Where the evidence is thin")
# --------------------------------------------------------------------------

CORPUS_KINDS = frozenset({"article", "signal", "paper", "patent", "measurement"})


def is_corpus_source(src: dict) -> bool:
    """Katalogeintrag aus dem eigenen Korpus oder der eigenen Messung — im
    Gegensatz zu allem, was aus dem Web kam (web/legal/market/entity/funding)."""
    return str((src or {}).get("kind") or "") in CORPUS_KINDS


def thin_yield(ev: CorpusEvidence | None, gating: dict | None, gaps: list[str],
               ledger: list[dict], sweeps_added: dict[str, int] | None = None) -> list[dict]:
    """Je dünnem Bereich: was der Korpus hatte und was die Web-Stufe dazu
    brachte (Anfragen, aufgenommene, gelesene Seiten). Tier-Bereiche und die
    festen Bereiche (regulatory/calendar) hängen an den Sweeps, Pflichtpunkte
    an ihrer Ledger-Zeile."""
    if not ev or not ev.ok:
        return []
    sweeps_added = sweeps_added or {}
    web_idx = set((gating or {}).get("web_gaps") or [])
    low_gaps = [g.lower() for g in gaps]
    out: list[dict] = []
    for t in ev.thin_areas:
        row = {"area": t["area"], "kind": t["kind"], "reason": t["reason"],
               "web_queries": 0, "web_sources": 0, "web_fetched": 0, "gated": False}
        if t["kind"] == "must":
            gi = next((i for i, g in enumerate(low_gaps) if g == t["area"].lower()), None)
            if gi is not None and gi < len(ledger):
                e = ledger[gi]
                row["web_queries"] = len(e.get("web_queries") or [])
                row["web_sources"] = int(e.get("web_sources") or 0)
                row["web_fetched"] = int(e.get("web_fetched") or 0)
                row["gated"] = gi in web_idx
        elif t["kind"] == "tier":
            key = {"market": "market", "funding": "funding"}.get(t["area"])
            if key:
                row["web_sources"] = int(sweeps_added.get(key, 0))
                row["gated"] = bool(((gating or {}).get("sweeps") or {}).get(key))
        else:                                   # regulatory / calendar
            key = "regulatory" if t["area"] == "regulatory" else "catalyst"
            row["web_sources"] = int(sweeps_added.get(key, 0))
            row["gated"] = bool(((gating or {}).get("sweeps") or {}).get(key))
        out.append(row)
    return out


def render_thin_block(rows: list[dict]) -> str:
    """Prompt-Block für die Sektion „Where the evidence is thin"."""
    if not rows:
        return ""
    L = ["THIN AREAS — what the corpus lacked, and what the web stage brought for exactly "
         "these (the web ran ONLY here). Write 'Where the evidence is thin' from these lines: "
         "one bullet per area, naming the area, the corpus count and what the web yielded "
         "(cite the web pages you use by id); an area where the web brought nothing is "
         "stated as such, never filled."]
    for r in rows:
        got = (f"web: {r['web_queries']} quer{'y' if r['web_queries'] == 1 else 'ies'}, "
               f"{r['web_sources']} source(s) admitted, {r['web_fetched']} read"
               if r["kind"] == "must" else f"web sweep: {r['web_sources']} source(s) admitted")
        if not r.get("gated") and r["kind"] == "must":
            got = "web: not searched (budget)"
        L.append(f"- {r['area']} [{r['kind']}] — corpus: {r['reason']}; {got}")
    return "\n".join(L)

