"""Entscheidungsgeruest, Laengenbremse und Beleg-Verifikation ueber den Bericht.

Alles hier ist DETERMINISTISCH — kein zweiter Modell-Hop, kein Kritiker-Modell
(der Schreib-Kritik-Loop ist verworfen, docs/newsletter_agentic_prototype_2026-09-06.md).
Der Rechercheur ruft `structure_findings()` + `verify_cited_figures()` genau
einmal ueber den geschriebenen Bericht auf; findet eine der Pruefungen etwas,
gibt es GENAU EINEN gezielten Neuwurf mit `revision_prompt()`, danach greift die
mechanische Streichung. Keine Schleife.

Warum es das gibt (Blindgutachten 2026-09-07, scratchpad/glp1/jury_1.md +
jury_2.md — unser Dossier 51/70 bzw. 54/70 gegen 59/70 bzw. 62/70):

  S1  „Zu lang und nicht auf eine Entscheidung zugeschnitten" — 5.906 Woerter
      gegen 2.833 des Siegers; der Gutachter gab unseren Text „ans Entwicklungs-
      und Regulatory-Team, nicht ins Gremium".  ->  verbindliche Gliederung,
      harte Obergrenze fuer den Fliesstext.
  S2  „Keine Go/No-Go-Kriterien, kein Abbruchkriterium" in allen drei Texten.
      ->  jede Option traegt Bedingung/Zeit/Aufwand/Risiko/Gegenargument, und
      die Vollstaendigkeit dieser Felder wird hier geprueft, nicht erhofft.
  S3  Eine zitierte Zahl (»GKV +1,2 Mio. Patienten/Jahr«) stand in der
      zitierten Seite nachweislich NICHT. Die Kanonisierung belegt nur, dass
      die URL im Katalog liegt.  ->  `verify_cited_figures()` prueft die Zahlen
      eines Satzes gegen den Volltext genau der Web-Seite, die der Satz zitiert.

Wortzahl heisst hier immer FLIESSTEXT: der Zitatapparat (Marker `[[T123]]` wie
kanonisierte `[Titel](URL)`) wird vorher entfernt, damit dieselbe Zahl vor und
nach der Kanonisierung gilt. Die code-generierten Anhaenge (Coverage, Messung,
Korpus, Quellenliste) zaehlen nie mit — sie sind Anhang, kein Bericht.
"""
from __future__ import annotations

import re

from pipeline.grounding import (_concrete_tokens, _in_source, _source_words,
                                ungrounded_specifics)

# --- Laengenbudget --------------------------------------------------------
# 2.200-2.800 ist das Fenster des Siegertexts (2.833) plus unsere zwei
# Pflicht-Zusatzabschnitte (Recht/IP, Entscheidungsgeruest). Nur die OBERE
# Grenze loest einen Neuwurf aus; zu kurz ist ein Befund, kein Neuwurf.
BODY_WORDS_MIN = 2200
BODY_WORDS_MAX = 2800
SUMMARY_WORDS_MAX = 200
MIN_OPTIONS, MAX_OPTIONS = 2, 5

_MARKER = re.compile(r"\[\[\s*[A-Za-z][A-Za-z0-9_.-]{0,31}\s*\]\]")
_LINK = re.compile(r"\[([^\]\n]+)\]\((https?://[^)\s]+)\)")
_HEADING = re.compile(r"^\s{0,3}(#{1,6})\s*(.+?)\s*#*\s*$", re.MULTILINE)
# Aufzaehlungspraefixe einer Ueberschrift ("3.", "(c)", "c) ") — NICHT mehr als
# Zeichenklasse: [a-f] frass "dec" aus "Decision summary".
_HEAD_ENUM = re.compile(r"^[\s\d.)(]*(?:[a-z][.)]\s+)?")
# Zeilenweise UND satzweise (wie pipeline/grounding._SENT_SPLIT): Listen-
# punkte und Tabellenzeilen sind eigene Behauptungen, keine Absaetze.
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")

# Trennmarke zwischen dem AUSGELIEFERTEN Dokument und dem Pruefanhang
# (2026-09-07, jury_7.md/jury_8.md). Beide Gutachten rechneten dasselbe vor:
# 2.563 der 6.775 Woerter unseres Dossiers waren Suchprotokoll — "der Kaeufer
# liest die Werkstatt statt des Produkts". Das Protokoll verschwindet nicht
# (es ist der Ehrlichkeitsbeleg und steht im Desk), aber es steht ab hier
# UNTERHALB der Marke: alles davor ist das Dossier, alles danach Betriebsdaten.
AUDIT_ANNEX_MARK = "<!-- catandary:audit-annex -->"

# Schnittmarken der code-generierten Anhaenge. Textgleich zu
# pipeline/dossier_check.py zu halten (dort dieselbe Aufgabe nach dem Lauf).
_APPENDIX_HEADINGS = (
    AUDIT_ANNEX_MARK,
    "## Research coverage (auto-generated)",
    "## Recherche-Abdeckung (automatisch erzeugt)",
    "\n## Sources\n", "\n## Quellen\n",
)


def delivered(report_md: str) -> str:
    """Das ausgelieferte Dokument: Bericht + Quellen + Messanhang, ohne den
    Pruefanhang. Genau das, was der Kunde bekommt."""
    text = report_md or ""
    i = text.find(AUDIT_ANNEX_MARK)
    return (text[:i] if i >= 0 else text).rstrip()


def audit_annex(report_md: str) -> str:
    """Der Pruefanhang eines gespeicherten Dokuments (leer, wenn keiner da)."""
    text = report_md or ""
    i = text.find(AUDIT_ANNEX_MARK)
    return text[i + len(AUDIT_ANNEX_MARK):].strip() if i >= 0 else ""


def join_document(report_md: str, annex: str) -> str:
    """Ausgeliefertes Dokument + Pruefanhang zu einem speicherbaren Ganzen."""
    if not annex:
        return report_md
    if AUDIT_ANNEX_MARK in (report_md or ""):
        return report_md
    return f"{(report_md or '').rstrip()}\n\n{AUDIT_ANNEX_MARK}\n{annex.strip()}\n"


_SOURCES_HEADING = re.compile(
    r"^(?:#{1,6}\s*)?(?:\*\*)?(?:sources?|references?|bibliography|works\s+cited"
    r"|quellen(?:verzeichnis)?|literatur(?:verzeichnis)?)(?:\*\*)?:?\s*$",
    re.IGNORECASE | re.MULTILINE)


# --------------------------------------------------------------------------
# Die verbindliche Gliederung
# --------------------------------------------------------------------------
# (key, Ueberschrift wie sie im Bericht stehen soll, Erkennungsmuster)
SECTIONS: dict[str, list[tuple[str, str, str]]] = {
    "en": [
        ("decision", "Decision summary", r"decision summary|decision brief"),
        ("moving", "What is moving", r"what is moving|what is actually moving"),
        ("regip", "Regulatory and IP status",
         r"(regulator\w*|legal)[^\n]{0,20}(and|/|&)[^\n]{0,20}ip|ip[^\n]{0,20}(and|/|&)[^\n]{0,20}regulator"),
        ("unsupported", "What the evidence does not support",
         r"evidence does not support|does not support"),
        ("options", "Options for a mid-sized European company",
         r"^options\b|options for a"),
        ("open", "Open questions and limits", r"open questions"),
    ],
    "de": [
        ("decision", "Entscheidungs-Kurzfassung", r"entscheidungs"),
        ("moving", "Was sich bewegt", r"was sich bewegt"),
        ("regip", "Recht und Schutzrechte", r"recht und schutzrechte|rechts?[- ]"),
        ("unsupported", "Was die Belege nicht hergeben",
         r"nicht hergeben|nicht belegt|nicht tragen"),
        ("options", "Optionen für ein mittelständisches europäisches Unternehmen",
         r"^optionen\b|optionen für"),
        ("open", "Offene Fragen und Grenzen", r"offene fragen"),
    ],
}

# Pflichtfelder je Option — das Entscheidungsgeruest. „Was dagegen spricht" ist
# der Kern: eine Optionsliste ohne Gegenargument ist eine Wunschliste.
OPTION_FIELDS: dict[str, list[tuple[str, str]]] = {
    "en": [("trigger", r"trigger|condition"), ("horizon", r"time horizon|horizon"),
           ("effort", r"effort|investment"), ("risk", r"risk"),
           ("against", r"against it|argument against|what speaks against")],
    "de": [("trigger", r"auslöser|bedingung"), ("horizon", r"zeithorizont|horizont"),
           ("effort", r"aufwand|investition"), ("risk", r"risiko"),
           ("against", r"dagegen spricht|gegenargument")],
}

OPTION_LABELS = {
    "en": ["Trigger", "Time horizon", "Effort", "Risk", "Against it"],
    "de": ["Auslöser", "Zeithorizont", "Aufwand", "Risiko", "Dagegen spricht"],
}

_OPTION_START = re.compile(r"^\s{0,3}(?:#{2,6}\s*|\*\*|[-*]\s*\*\*|\d+[.)]\s*)?"
                           r"(?:option|szenario|scenario|variante)\b",
                           re.IGNORECASE | re.MULTILINE)


def _lang(lang: str) -> str:
    return "de" if lang == "de" else "en"


def outline_block(lang: str = "en") -> str:
    """Die Gliederung als Prompt-Baustein — wortgleich zu dem, was geprueft wird."""
    L = _lang(lang)
    if L == "de":
        return "\n".join(f"{i}. ## {h}" for i, (_, h, _) in
                         enumerate(SECTIONS["de"], 1))
    return "\n".join(f"{i}. ## {h}" for i, (_, h, _) in
                     enumerate(SECTIONS["en"], 1))


def body_text(report_md: str) -> str:
    """Der modellgeschriebene Teil: ohne code-generierte Anhaenge und ohne eine
    vom Modell selbst geschriebene Quellenliste."""
    text = report_md or ""
    hits = [i for i in (text.find(h) for h in _APPENDIX_HEADINGS) if i >= 0]
    if hits:
        text = text[:min(hits)]
    m = _SOURCES_HEADING.search(text)
    if m:
        text = text[:m.start()]
    return text.rstrip()


def prose(text: str) -> str:
    """Fliesstext ohne Zitatapparat — dieselbe Zahl vor und nach der
    Kanonisierung. Marker verschwinden ganz, kanonisierte Links samt Titel."""
    return _LINK.sub("", _MARKER.sub("", text or ""))


def count_words(text: str) -> int:
    return len(re.findall(r"\S+", prose(text)))


def split_sections(body: str, lang: str = "en") -> dict[str, str]:
    """Ordnet jede Ueberschrift des Berichts einem Gliederungspunkt zu.

    Erkannt wird ueber die Muster in SECTIONS, nicht ueber exakte Gleichheit —
    das Modell nummeriert oder ergaenzt Ueberschriften gern."""
    spec = SECTIONS[_lang(lang)]
    heads = [(m.start(), m.end(), len(m.group(1)), m.group(2))
             for m in _HEADING.finditer(body)]
    out: dict[str, str] = {}
    for i, (_s, e, level, title) in enumerate(heads):
        low = _HEAD_ENUM.sub("", title.strip().lower())
        # Bis zur naechsten GLEICH- oder hoeherrangigen Ueberschrift: die
        # Optionen stehen als "### Option N" INNERHALB des Optionsabschnitts.
        end = next((h[0] for h in heads[i + 1:] if h[2] <= level), len(body))
        for key, _h, pat in spec:
            if key in out:
                continue
            if re.search(pat, low, re.IGNORECASE):
                out[key] = body[e:end].strip()
                break
    return out


def option_blocks(section_text: str) -> list[str]:
    """Die einzelnen Optionen innerhalb des Optionsabschnitts."""
    if not section_text:
        return []
    starts = [m.start() for m in _OPTION_START.finditer(section_text)]
    if not starts:
        return []
    bounds = starts + [len(section_text)]
    return [section_text[bounds[i]:bounds[i + 1]].strip()
            for i in range(len(starts))]


def _missing_fields(block: str, lang: str) -> list[str]:
    L = _lang(lang)
    missing = []
    for (key, pat), label in zip(OPTION_FIELDS[L], OPTION_LABELS[L]):
        if not re.search(rf"(?:^|\n|\*\*|[-*]\s*)\s*(?:\*\*)?\s*(?:{pat})\s*"
                         rf"(?:\*\*)?\s*[:：]", block, re.IGNORECASE):
            missing.append(label)
    return missing


# --------------------------------------------------------------------------
# Messbezug der Optionen (R6-2, jury_7.md 2026-09-07)
# --------------------------------------------------------------------------
# Woertlich: „P verknuepft keine einzige seiner vier Handlungsoptionen damit."
# Der Messanhang ist unser einziger Alleinstellungsinhalt — beide Jurys sagen
# das ausdruecklich —, und er lag als unverbundener Datenblock hinter dem
# Bericht. Also: jede Option muss mindestens eine GEMESSENE Groesse als
# Ausloeser oder Begruendung tragen, und das wird hier gezaehlt, nicht erhofft.
#
# Geprueft werden nur Zahlen, die im Messanhang stehen — nicht das Wort
# „gemessen". Zu kurze Zahlen fliegen raus: eine Zykluszeit von 12 Jahren waere
# sonst durch jedes „within 12 months" scheinbar erfuellt.

MEASURED_KEYS = ("K_median", "lead_patent_market", "lead_science_market",
                 "cycle_time_years", "centrality_peak_year", "n_patents")
CORPUS_KEYS = ("market_n", "market_published", "science_n", "science_citations")
MEASURED_LABELS = {
    "K_median": "improvement rate median (%/yr)",
    "lead_patent_market": "patent→market lead time (years)",
    "lead_science_market": "science→market lead time (years)",
    "cycle_time_years": "cycle time (years)",
    "centrality_peak_year": "centrality peak (year)",
    "n_patents": "patents in the measured citation graph",
    "market_n": "market signals in the corpus",
    "market_published": "written-up articles in the corpus",
    "science_n": "works in the research corpus",
    "science_citations": "citations between them",
}
MIN_NEEDLE_CHARS = 3


def _needle_forms(value, year: bool = False) -> list[str]:
    """Alle Schreibweisen, in denen eine gemessene Groesse im Anhang steht.
    Jahreszahlen bekommen KEINE Tausenderform ("2,017" schreibt niemand)."""
    if value is None or isinstance(value, bool):
        return []
    if isinstance(value, int):
        return [str(value)] if year else [f"{value:,}", str(value)]
    if isinstance(value, float):
        out = [f"{value:,}" if value != int(value) else str(value)]
        out.append(str(value))
        if value == int(value):
            out.append(f"{int(value):,}")
        return out
    return [str(value)]


def measured_needles(quant_summary: dict | None,
                     corpus_summary: dict | None = None) -> list[str]:
    """Die Zahlen (und CPC-Codes), die als „gemessen" gelten.

    Quelle sind die Skalare der beiden Vorstufen, nicht der Anhangstext: was
    hier steht, ist per Konstruktion ein Query-Ergebnis."""
    q = quant_summary or {}
    out: list[str] = []
    seen: set[str] = set()

    def add(x: str) -> None:
        x = str(x).strip()
        if len(x) >= MIN_NEEDLE_CHARS and x.lower() not in seen:
            seen.add(x.lower())
            out.append(x)

    if not q.get("off_topic"):
        for code in (q.get("selection") or [])[:6]:
            add(code)
        for key in MEASURED_KEYS:
            for form in _needle_forms(q.get(key), year=key.endswith("_year")):
                add(form)
        for v in (q.get("takeoffs") or {}).values():
            for form in _needle_forms(v, year=True):
                add(form)
    for key in CORPUS_KEYS:
        for form in _needle_forms((corpus_summary or {}).get(key)):
            add(form)
    return out


def _needle_hit(text: str, needle: str) -> bool:
    pat = re.compile(r"(?<![\w.,])" + re.escape(needle) + r"(?![\d])",
                     re.IGNORECASE)
    return bool(pat.search(text or ""))


def uses_measurement(text: str, needles: list[str]) -> bool:
    return any(_needle_hit(text, n) for n in needles or ())


def measured_brief(quant_summary: dict | None,
                   corpus_summary: dict | None = None) -> str:
    """Die gemessenen Groessen als eine Zeile fuer den Berichtsprompt — was
    geprueft wird, muss das Modell auch benannt bekommen."""
    q, c = quant_summary or {}, corpus_summary or {}
    bits: list[str] = []
    if not q.get("off_topic"):
        sel = [str(x) for x in (q.get("selection") or [])[:4]]
        if sel:
            bits.append("measured patent classes " + ", ".join(sel))
        for key in MEASURED_KEYS:
            v = q.get(key)
            if v is not None:
                bits.append(f"{MEASURED_LABELS[key]} {v}")
        for tier, v in (q.get("takeoffs") or {}).items():
            if v:
                bits.append(f"{tier} take-off {v}")
    for key in CORPUS_KEYS:
        v = c.get(key)
        if v is not None:
            bits.append(f"{MEASURED_LABELS[key]} {v:,}"
                        if isinstance(v, int) else f"{MEASURED_LABELS[key]} {v}")
    return " · ".join(bits)


# --------------------------------------------------------------------------
# Branchenabdeckung der Optionen (R6-3, jury_8.md 2026-09-07)
# --------------------------------------------------------------------------
# „4 Optionen sind sauber strukturiert, aber fast ausschliesslich
# Food/Labeling-fokussiert; HealthTech kommt nicht vor." Die Frage nennt drei
# Felder, der Optionsteil bediente eines. Die Felder werden AUS DER FRAGE
# gelesen (kein GLP-1-Sonderfall): steht ein Feld in der Frage, muss der
# Optionsabschnitt es adressieren.

SECTOR_LEXICON: dict[str, tuple[str, ...]] = {
    "food": ("food", "beverage", "drink", "ingredient", "recipe", "snack",
             "grocery", "meal", "menu", "dairy", "bakery", "confectionery",
             "portion", "reformulat", "formulation", "packaging", "retail",
             "lebensmittel", "getränk", "rezeptur"),
    "nutrition": ("nutrition", "nutrient", "nutritional", "diet", "dietary",
                  "protein", "fibre", "fiber", "supplement", "satiety",
                  "calorie", "caloric", "vitamin", "micronutrient",
                  "ernährung", "nährstoff", "nahrungsergänzung"),
    "health technology": ("health technology", "healthtech", "digital health",
                          "device", "app", "wearable", "diagnostic", "sensor",
                          "telehealth", "telemedicine", "software", "platform",
                          "monitoring", "medtech", "companion", "algorithm",
                          "gesundheitstechnologie", "medizintechnik"),
    "packaging": ("packaging", "pack ", "label", "verpackung"),
    "logistics": ("logistic", "supply chain", "distribution", "warehouse",
                  "cold chain", "logistik", "lieferkette"),
    "energy": ("energy", "power", "grid", "electricity", "energie", "strom"),
    "mobility": ("mobility", "vehicle", "automotive", "transport", "fleet",
                 "mobilität", "fahrzeug"),
}

# Wie das Feld in einer Frage heissen kann (Erkennung, nicht Abdeckung).
_SECTOR_ALIASES: dict[str, tuple[str, ...]] = {
    "health technology": ("health technology", "health tech", "healthtech",
                          "digital health", "medtech", "medical technology"),
}


def sectors_from_question(question: str) -> list[str]:
    """Die Felder, die die Frage ausdruecklich nennt — nur die werden geprueft."""
    low = (question or "").lower()
    out = []
    for name in SECTOR_LEXICON:
        for alias in _SECTOR_ALIASES.get(name, (name,)):
            if alias in low:
                out.append(name)
                break
    return out


def option_measure_stats(report_md: str, lang: str, measured: list[str] | None,
                         sectors: list[str] | None = None) -> dict:
    """Kennzahlen fuer den Pruefbefund: wie viele Optionen eine gemessene
    Groesse tragen und welche Felder der Optionsabschnitt nicht bedient."""
    sections = split_sections(body_text(report_md), _lang(lang))
    blocks = option_blocks(sections.get("options", ""))
    return {
        "options": len(blocks),
        "options_measured": sum(1 for b in blocks
                                if uses_measurement(b, measured or [])),
        "sectors": list(sectors or []),
        "sectors_missing": uncovered_sectors(sections.get("options", ""),
                                             sectors or []),
    }


def uncovered_sectors(text: str, sectors: list[str]) -> list[str]:
    low = (text or "").lower()
    return [s for s in sectors or ()
            if not any(kw in low for kw in SECTOR_LEXICON.get(s, ()))]


def length_advisory(report_md: str, lang: str = "en") -> list[str]:
    """Untergrenze — HINWEIS, kein Neuwurf-Grund.

    Ein zu langer Bericht ist ein Formfehler, den ein zweiter Wurf behebt; ein
    zu kurzer ist meist duennes Material, und ein Neuwurf wuerde das Modell nur
    zum Auffuellen einladen. Der Owner sieht die Zahl im Pruefbefund."""
    words = count_words(body_text(report_md))
    if words and words < BODY_WORDS_MIN:
        return [f"Fliesstext {words} Woerter — unter dem Zielband "
                f"{BODY_WORDS_MIN}-{BODY_WORDS_MAX} (kein Neuwurf: zu kurz "
                f"heisst in der Regel duennes Material, nicht schlechte Form)."]
    return []


def structure_findings(report_md: str, lang: str = "en",
                       measured: list[str] | None = None,
                       sectors: list[str] | None = None) -> list[str]:
    """Was am fertigen Bericht mechanisch nicht stimmt. Leere Liste = sauber.

    `measured` = die gemessenen Groessen (measured_needles): jede Option muss
    mindestens eine davon nennen. `sectors` = die Felder, die die Frage nennt
    (sectors_from_question): der Optionsabschnitt muss alle bedienen. Beide
    Listen leer = beide Pruefungen aus (alter Pfad, Firmen-Dossiers)."""
    L = _lang(lang)
    body = body_text(report_md)
    if not body.strip():
        return ["Bericht ist leer."]
    findings: list[str] = []
    words = count_words(body)
    if words > BODY_WORDS_MAX:
        findings.append(
            f"Fliesstext {words} Woerter — Obergrenze {BODY_WORDS_MAX}. "
            f"Auf {BODY_WORDS_MIN}-{BODY_WORDS_MAX} kuerzen, ohne einen "
            f"Pflichtabschnitt oder einen Beleg zu streichen.")
    sections = split_sections(body, L)
    for key, heading, _pat in SECTIONS[L]:
        if key not in sections:
            findings.append(f"Pflichtabschnitt fehlt: '## {heading}'.")
    summary = sections.get("decision", "")
    if summary and count_words(summary) > SUMMARY_WORDS_MAX:
        findings.append(
            f"'{SECTIONS[L][0][1]}' hat {count_words(summary)} Woerter — "
            f"hoechstens {SUMMARY_WORDS_MAX}.")
    if "options" in sections:
        blocks = option_blocks(sections["options"])
        if len(blocks) < MIN_OPTIONS:
            findings.append(
                f"Nur {len(blocks)} Option(en) erkennbar — mindestens "
                f"{MIN_OPTIONS}, jede mit eigener Ueberschrift 'Option N — ...'.")
        elif len(blocks) > MAX_OPTIONS:
            findings.append(f"{len(blocks)} Optionen — hoechstens {MAX_OPTIONS}.")
        for i, block in enumerate(blocks[:MAX_OPTIONS], 1):
            miss = _missing_fields(block, L)
            if miss:
                findings.append(
                    f"Option {i}: Pflichtfeld(er) fehlen — "
                    + ", ".join(f"'{m}:'" for m in miss))
            if measured and not uses_measurement(block, measured):
                findings.append(
                    f"Option {i}: keine gemessene Groesse genannt. Ausloeser "
                    f"oder Begruendung muss eine Zahl aus dem Messanhang "
                    f"tragen (z. B. {', '.join(measured[:4])}).")
        missing_sectors = uncovered_sectors(sections["options"], sectors or [])
        for name in missing_sectors:
            findings.append(
                f"Optionsabschnitt deckt '{name}' nicht ab — die Frage nennt "
                f"dieses Feld ausdruecklich; mindestens eine Option muss es "
                f"adressieren.")
    return findings


# --------------------------------------------------------------------------
# Beleg-Verifikation: steht die zitierte Zahl auch in der zitierten Seite?
# --------------------------------------------------------------------------

_VERIFIABLE_KINDS = ("web", "legal", "market")

# Ein Dezimalwert mit 1-2 Nachkommastellen. `pipeline.grounding._norm_token`
# entfernt Punkt UND Komma (deutsch/englisch tauschen die Trennzeichen), also
# ist dort "1.2" == "12" — und genau daran ging der teuerste Befund des
# Blindgutachtens durch: die Seite nannte "12 %", das Dossier machte daraus
# "1,2 Mio. Patienten". Fuer Dezimalwerte pruefen wir deshalb ZUSAETZLICH
# trennzeichen-erhaltend: 1.2 darf 1,2 oder 1·2 auf der Seite treffen, aber
# niemals 12. Ganze Zahlen bleiben beim toleranten Pfad von grounding.py.
_DECIMAL_RE = re.compile(r"^[$€£]?\s?(\d{1,3})[.,\u00b7](\d{1,2})%?$")


def _decimal_on_page(token: str, page: str) -> bool:
    m = _DECIMAL_RE.match(token)
    if not m:
        return True
    pat = re.compile(rf"(?<!\d){re.escape(m.group(1))}[.,\u00b7]{re.escape(m.group(2))}"
                     rf"(?!\d)")
    return bool(pat.search(page or ""))


def unverified_tokens(claim: str, page: str) -> list[str]:
    """Konkrete Tokens des Satzes, die die zitierte Seite nicht hergibt.

    Basis ist `ungrounded_specifics` (dieselbe Mechanik wie das Publish-Gate),
    verschaerft um die Dezimalpruefung oben."""
    bad = list(ungrounded_specifics(claim, page))
    for t in sorted(_concrete_tokens(claim)):
        if t in bad or _DECIMAL_RE.match(t) is None:
            continue
        if not _decimal_on_page(t, page):
            bad.append(t)
    return bad


def _cited_in(sentence: str, by_id: dict, by_url: dict) -> list[dict]:
    out, seen = [], set()
    for m in re.finditer(r"\[\[\s*([A-Za-z][A-Za-z0-9_.-]{0,31})\s*\]\]", sentence):
        s = by_id.get(m.group(1)) or by_id.get(m.group(1).upper())
        if s is not None and id(s) not in seen:
            seen.add(id(s))
            out.append(s)
    for m in _LINK.finditer(sentence):
        url = m.group(2)
        s = by_url.get(url) or by_url.get(url.rstrip("/."))
        if s is not None and id(s) not in seen:
            seen.add(id(s))
            out.append(s)
    return out


def verify_cited_figures(report_md: str, sources: list[dict]) -> dict:
    """Jeden Satz, der AUSSCHLIESSLICH gefetchte Web-/Rechtsquellen zitiert,
    gegen deren Volltext pruefen.

    Geprueft werden die konkreten Tokens des Satzes (Jahr, Zahl, %, Betrag) mit
    derselben Mechanik wie das Publish-Gate (`ungrounded_specifics`). Zitiert
    ein Satz zusaetzlich Korpus-Material (Artikel/Signal/Paper/Patent/Messung),
    bleibt er dem bestehenden Pfad ueberlassen — dessen Beleg ist der
    Evidenzblock, nicht eine Seite.

    Rueckgabe: {"checked": n Saetze, "figures": n gepruefte Tokens,
                "unverified": [{"sentence":…, "tokens":[…], "url":…}]}
    """
    by_id, by_url = {}, {}
    for s in sources:
        by_id[s.get("id")] = s
        if s.get("origin"):
            by_url.setdefault(s["origin"], s)
    for s in sources:
        by_url[s.get("url")] = s
    body = body_text(report_md)
    checked = figures = subjects = 0
    bad: list[dict] = []
    off_topic: list[dict] = []
    for raw in _SENT_SPLIT.split(body):
        sentence = raw.strip()
        if not sentence or sentence.startswith("#"):
            continue
        cited = _cited_in(sentence, by_id, by_url)
        if not cited:
            continue
        if not all(c.get("kind") in _VERIFIABLE_KINDS and c.get("text")
                   for c in cited):
            continue
        haystack = "\n".join(
            " ".join(str(c.get(k) or "") for k in ("text", "title", "snippet", "date"))
            for c in cited)
        claim = prose(sentence)
        tokens = unverified_tokens(claim, haystack)
        checked += 1
        figures += len(_concrete_tokens(claim))
        if tokens:
            bad.append({"sentence": sentence, "tokens": tokens, "kind": "figure",
                        "url": cited[0].get("url", "")})
        # Themenpruefung: handelt die zitierte Seite ueberhaupt von dem, was der
        # Satz behauptet? (Befund 2 der Jurys — richtige Zahl, falsche Seite.)
        names = unverified_subjects(claim, haystack)
        subjects += len(subject_names(claim))
        if names:
            off_topic.append({"sentence": sentence, "tokens": names,
                              "kind": "subject", "url": cited[0].get("url", "")})
    return {"checked": checked, "figures": figures, "unverified": bad,
            "subjects": subjects, "off_topic": off_topic}


def drop_unverified(report_md: str, unverified: list[dict]) -> tuple[str, int]:
    """Saetze, deren Zahl in der zitierten Seite nicht steht, aus dem Bericht
    entfernen. Letzte Instanz nach dem einen Neuwurf — eine Zahl, die die
    zitierte Quelle nicht hergibt, darf nicht im Dokument stehen bleiben."""
    out, dropped = report_md, 0
    for e in unverified:
        s = e["sentence"]
        if s and s in out:
            out = out.replace(s + " ", "", 1) if (s + " ") in out \
                else out.replace(s, "", 1)
            dropped += 1
    # Doppelte Leerzeichen/Leerzeilen, die durch die Streichung entstehen.
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out, dropped


def revision_prompt(findings: list[str], cite_findings: list[dict],
                    lang: str = "en") -> str:
    """Der EINE gezielte Neuwurf. Kein Kritiker-Modell: der Text hier ist
    vollstaendig aus deterministischen Befunden erzeugt."""
    L = _lang(lang)
    lines = list(findings)
    for e in cite_findings[:10]:
        toks = ", ".join(repr(t) for t in e["tokens"][:4])
        kind = e.get("kind", "figure")
        if kind == "subject":
            lines.append(
                f"Die zitierte Seite ({e['url'][:80]}) handelt NICHT von "
                f"{toks} — der Beleg traegt diese Aussage nicht. Satz mit einem "
                f"passenden Beleg neu schreiben oder streichen: "
                f"\"{e['sentence'][:180]}\"")
        elif kind == "sourceless":
            lines.append(
                f"Die Zahl(en) {toks} stehen ohne jeden Beleg im Fliesstext. "
                f"Entweder ein Zitat aus dem Katalog IN DENSELBEN Satz setzen "
                f"oder die Zahl streichen: \"{e['sentence'][:180]}\"")
        else:
            lines.append(
                f"Die Zahl(en) {toks} stehen NICHT in der zitierten Seite "
                f"({e['url'][:80]}). Satz ohne diese Zahl neu schreiben oder "
                f"streichen: \"{e['sentence'][:180]}\"")
    numbered = "\n".join(f"{i}. {x}" for i, x in enumerate(lines, 1))
    if L == "de":
        return (
            "ÜBERARBEITUNG — das ist der einzige Korrekturdurchgang.\n\n"
            "Eine mechanische Prüfung des eben geschriebenen Berichts hat "
            "folgende Punkte gefunden:\n\n" + numbered + "\n\n"
            "Schreibe den VOLLSTÄNDIGEN Bericht neu und behebe genau diese "
            "Punkte. Alles andere bleibt inhaltlich, wie es ist: keine neuen "
            "Fakten, keine neuen Zahlen, keine neuen Zitate — nur die "
            "vorhandenen Katalog-IDs. Gliederung und Zitierweise unverändert.")
    return (
        "REVISION — this is the only correction pass.\n\n"
        "A mechanical check of the report you just wrote found the following:\n\n"
        + numbered + "\n\n"
        "Rewrite the COMPLETE report and fix exactly these points. Everything "
        "else stays as it is in substance: no new facts, no new figures, no new "
        "citations — only catalog ids that already appear. Keep the mandated "
        "outline and the citation form unchanged.")


# --------------------------------------------------------------------------
# Themenpruefung der Zitate (Befund 2, jury_3.md/jury_4.md 2026-09-07)
# --------------------------------------------------------------------------
# Der schwerwiegendste Einzelfund beider Jurys: ein CNBC-Artikel ueber die
# Wegovy-Pille von NOVO NORDISK wurde zweimal als Beleg fuer die Zulassung von
# LILLYS Orforglipron gefuehrt. `verify_cited_figures` prueft Zahlen — und die
# Zahl stimmte sogar ungefaehr. Was niemand prueft, ist der GEGENSTAND: worueber
# die Seite ueberhaupt handelt. Also dieselbe Mechanik wie `ungrounded_names`
# (Namensliste aus dem Satz, Wort-fuer-Wort-Abgleich gegen die Quelle), nur auf
# die Namen zugeschnitten, um die es in einem Technologie-Dossier geht:
# Wirkstoffe (INN-Endungen) und Firmen/Produkte (Eigennamen).
#
# Bewusst NICHT geprueft werden reine Abkuerzungen (FDA, EMA, NHS) und einzelne
# Grossbuchstaben-Woerter aus der Stoppliste: dort waere die Falsch-Ablehnung
# wahrscheinlicher als der Fund, weil Seiten dieselbe Sache anders abkuerzen.

# INN-Stammendungen (WHO-Nomenklatur) — reicht fuer Wirkstoffnamen im Satz:
# semaglutide, tirzepatide, orforglipron, retatrutide, bimagrumab, dapagliflozin.
_INN_SUFFIX = ("tide", "glipron", "glutide", "trutide", "mab", "nib", "cept",
               "gliflozin", "sartan", "prazole", "statin", "parin", "vastatin",
               "kinra", "lukast", "afil", "setron", "tinib", "ciclib")

# Grossgeschriebene Woerter, die keinen Gegenstand benennen: Satzanfaenge,
# Zeitangaben, Geografie/Politik-Sammelbegriffe, Rollenwoerter.
_SUBJECT_STOP = frozenset("""
the this that these those there their they them then than when where which
while with without within after before during since until under over about
across against among between into onto upon from for and but not now new
however therefore because although though despite both each every some many
most more less least first second third fourth fifth next last only also
january february march april may june july august september october november
december monday tuesday wednesday thursday friday saturday sunday
europe european eu union america american americas asia asian africa african
germany german france french italy italian spain spanish netherlands dutch
britain british england english uk usa us china chinese japan japanese india
indian brazil global international national federal state states government
company companies market markets industry sector technology technologies
research development regulation regulatory approval approvals patent patents
science scientific clinical trial trials study studies data evidence report
reports analysis source sources phase price prices supply demand growth
option options risk risks trigger effort horizon summary decision decisions
what who which where how why our their its it is are was were has have had
key core main major minor overall further given based note noted see
marketing authorisation authorization revenue revenues quarterly pipeline
rollout reimbursement coverage sales launch launches funding investment
consumer consumers patient patients product products treatment therapy
""".split())

_CAP_TOKEN = re.compile(r"[A-Z][A-Za-z0-9&./'’-]*")
_LOWER_TOKEN = re.compile(r"\b[a-z][a-z-]{6,}\b")
# Verbindungswoerter INNERHALB eines Eigennamens ("Bank of England",
# "Novo Nordisk A/S") — nur wenn links UND rechts ein Grossbuchstabenwort steht.
_NAME_GLUE = frozenset("of and & de la van der von den du el al".split())
MAX_SUBJECTS = 8


def _inn_like(word: str) -> bool:
    return len(word) >= 8 and word.endswith(_INN_SUFFIX)


def subject_names(sentence: str) -> list[str]:
    """Die Gegenstaende, die ein Satz behauptet: Firmen-/Produkt-Eigennamen und
    Wirkstoffnamen. Reihenfolge = Satzreihenfolge, jeder Name einmal."""
    text = prose(sentence or "")
    out: list[str] = []
    seen: set[str] = set()

    def add(name: str) -> None:
        key = name.lower()
        if key not in seen and len(out) < MAX_SUBJECTS:
            seen.add(key)
            out.append(name)

    toks = list(_CAP_TOKEN.finditer(text))
    i = 0
    while i < len(toks):
        parts = [toks[i].group(0)]
        j = i + 1
        while j < len(toks):
            gap = text[toks[j - 1].end():toks[j].start()]
            glue = gap.strip().lower()
            if gap.strip() == "":
                parts.append(toks[j].group(0))
            elif (glue in _NAME_GLUE and j + 1 < len(toks)
                  and text[toks[j].end():toks[j + 1].start()].strip() == ""):
                parts.append(gap.strip())
                parts.append(toks[j].group(0))
            elif glue == "":
                parts.append(toks[j].group(0))
            else:
                break
            j += 1
        words = [p for p in parts if p[:1].isupper()]
        clean = [w.rstrip(".,;:").strip("'’") for w in words]
        # Zahlenhaltige Bestandteile fliegen raus ("Eli Lilly's Q1", "Wegovy 2.4
        # mg"): `grounding._source_words` tokenisiert die Seite nur ueber
        # Buchstaben, "Q1" waere dort NIE zu finden — ein sicherer Fehlalarm.
        # Die Zahl selbst deckt ohnehin die Zahlenpruefung ab.
        clean = [w for w in clean if not any(c.isdigit() for c in w)]
        clean = [w for w in clean if w and w.lower() not in _SUBJECT_STOP]
        if len(clean) >= 2:
            add(" ".join(clean))
        elif len(clean) == 1:
            w = clean[0]
            # Ein Artikel davor macht aus dem Wort meist einen Ort oder eine
            # Institution ("the Hague", "the Netherlands", "the Commission") —
            # dort ist die Falsch-Ablehnung wahrscheinlicher als der Fund.
            prev = text[:toks[i].start()].rstrip().split(" ")[-1].lower()
            lead = parts[0].rstrip(".,;:").lower() if parts else ""
            if prev in ("the", "a", "an", "der", "die", "das") \
                    or lead in ("the", "a", "an"):
                i = max(j, i + 1)
                continue
            # Ein einzelnes Wort nur, wenn es wie ein Eigenname aussieht
            # (Grossbuchstabe + Kleinbuchstaben, >=4 Zeichen): "Wegovy",
            # "Mounjaro", "Metsera" — nicht "FDA", nicht "The".
            if len(w) >= 4 and w[0].isupper() and any(c.islower() for c in w[1:]) \
                    and not w.isupper():
                add(w)
        i = max(j, i + 1)
    for m in _LOWER_TOKEN.finditer(text):
        if _inn_like(m.group(0)):
            add(m.group(0))
    return out


def unverified_subjects(sentence: str, page: str) -> list[str]:
    """Gegenstaende des Satzes, die im Volltext der zitierten Seite fehlen.

    Nicht leer = die Seite handelt nachweislich von etwas anderem; das Zitat
    wird abgelehnt. Abgleich wortweise ueber `grounding._in_source`, also
    diakritika- und possessiv-tolerant ("Lilly's" trifft "Lilly")."""
    src = _source_words(page or "")
    if not src:
        return []
    bad: list[str] = []
    for name in subject_names(sentence):
        if not _in_source_phrase(name, src):
            bad.append(name)
    return bad


def _in_source_phrase(name: str, src: set[str]) -> bool:
    """Ein mehrteiliger Name gilt als belegt, wenn ALLE seine Namensteile in der
    Seite stehen (Verbindungswoerter zaehlen nicht mit). "Eli Lilly" verlangt
    "Eli" UND "Lilly"; ein Artikel ueber Novo Nordisk hat beides nicht."""
    words = [w for w in re.split(r"\s+", name)
             if w and w.lower() not in _NAME_GLUE]
    return all(_in_source(w, src) for w in words) if words else True


# --------------------------------------------------------------------------
# Quellenlose Praezisionszahlen (Befund 3, jury_3.md/jury_4.md)
# --------------------------------------------------------------------------
# „North America held 77.72% of worldwide sales in 2024, while Asia-Pacific is
# projected to grow at a CAGR of 14.6% through 2035 ." — der Satz endet auf
# einen freistehenden Punkt, wo das Zitat stehen sollte. Beide Jurys werteten
# das als inakzeptabel fuer ein bezahltes Gutachten. Regel ohne Modellurteil:
# eine Praezisionszahl im Fliesstext braucht ein Zitat IM SELBEN SATZ — oder sie
# muss aus dem eigenen Messanhang stammen (der steht codegeneriert im Dokument).
# Jahreszahlen und kleine ganze Zahlen sind keine Praezisionszahlen: sie zu
# streichen wuerde jeden zweiten Satz kosten, ohne einen Beleg zu erzwingen.

_PRECISION_RE = re.compile(
    r"(?<![\w.,])(?:"
    r"[$€£]\s?\d[\d.,·]*\s?(?:bn|billion|m|million|k|trillion)?"   # Betraege
    r"|\d[\d.,·]*\s?%"                                            # Prozent
    r"|\d{1,3}[.,·]\d{1,2}(?![\d.,])"                             # Dezimal
    r"|\d[\d.,·]*\s?(?:billion|million|trillion|bn|Mrd\.?|Mio\.?)"  # Groessen
    r")", re.IGNORECASE)


def precision_figures(sentence: str) -> list[str]:
    """Zahlen, die ohne Beleg nicht im Fliesstext stehen duerfen."""
    out, seen = [], set()
    for m in _PRECISION_RE.finditer(prose(sentence or "")):
        t = m.group(0).strip()
        if t and t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
    return out


def _figure_in_measured(token: str, measured: str) -> bool:
    if not measured:
        return False
    return not ungrounded_specifics(token, measured) and _decimal_on_page(token, measured)


def sourceless_figures(report_md: str, sources: list[dict],
                       measured: str = "") -> list[dict]:
    """Saetze des Fliesstexts, die eine Praezisionszahl OHNE Zitat tragen und
    deren Zahl auch nicht aus dem eigenen Messanhang stammt.

    Rueckgabe wie `verify_cited_figures`: [{"sentence", "tokens", "url"}] —
    dieselbe Weiterverarbeitung (ein Neuwurf, danach mechanische Streichung)."""
    by_id, by_url = {}, {}
    for s in sources:
        by_id[s.get("id")] = s
        if s.get("origin"):
            by_url.setdefault(s["origin"], s)
    for s in sources:
        by_url[s.get("url")] = s
    out: list[dict] = []
    for raw in _SENT_SPLIT.split(body_text(report_md)):
        sentence = raw.strip()
        if not sentence or sentence.startswith("#") or sentence.startswith("|"):
            continue
        if _cited_in(sentence, by_id, by_url):
            continue                     # belegt — der Zahlen-Check greift dort
        figs = [f for f in precision_figures(sentence)
                if not _figure_in_measured(f, measured)]
        if figs:
            out.append({"sentence": sentence, "tokens": figs, "url": ""})
    return out
