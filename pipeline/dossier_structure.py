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
    "## How this dossier was checked (auto-generated)",
    "## Wie dieses Dossier geprüft wurde (automatisch erzeugt)",
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
        ("next", "What happens next",
         r"what happens next|what comes next|catalyst calendar|dated catalysts"),
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
        ("next", "Was als Nächstes ansteht",
         r"was als n(ä|ae)chstes|terminkalender|anstehende termine"),
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


def split_claims(text: str) -> list[str]:
    """Saetze eines Berichtstexts — aber NIE innerhalb eines Zitat-Links.

    Ein kanonisierter Link traegt den Quellentitel im Klartext, und Titel
    enthalten Satzzeichen ("Transformative or overhyped? The impact of …").
    Ein naiver Split zerlegt genau dort und trennt die Behauptung von ihrem
    Beleg — im R5-Dossier fiel deshalb der teuerste Satz des Berichts aus der
    Beleg-Verifikation heraus (er stand danach zitatlos da)."""
    spans = [(m.start(), m.end()) for m in _LINK.finditer(text or "")]
    out, start = [], 0
    for m in _SENT_SPLIT.finditer(text or ""):
        if any(a < m.start() < b for a, b in spans):
            continue
        out.append(text[start:m.start()])
        start = m.end()
    out.append(text[start:])
    return [x for x in out if x.strip()]


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


# R9-4 (jury_13/jury_14 2026-09-07): „Effort: No figure in the evidence" —
# viermal wortgleich. Das Fuenf-Felder-Schema war formal 4/4 erfuellt und
# inhaltlich leer. Ein Pflichtfeld, das nur einen Platzhalter traegt, gilt ab
# jetzt als NICHT erfuellt.
_PLACEHOLDER_RE = re.compile(
    r"^(?:\W*)(?:"
    r"no(?:ne)?(?:\s+\w+){0,3}?\s*(?:figure|number|estimate|data|value)?"
    r"(?:\s+(?:in|from|available|given|provided|stated|disclosed))?"
    r"(?:\s+the)?(?:\s+(?:evidence|material|sources?|corpus|catalog))?"
    r"|not\s+(?:available|applicable|quantified|specified|stated|given|known)"
    r"|unknown|unclear|unspecified|undetermined|tbd|t\.b\.d\.?|n/?a"
    r"|keine?\s+(?:zahl|angabe|zahlen|daten|schaetzung|sch(?:ä|ae)tzung)"
    r"(?:\s+\w+){0,3}"
    r"|unbekannt|nicht\s+(?:bekannt|bezifferbar|quantifizierbar|angegeben"
    r"|verf(?:ü|ue)gbar|ermittelbar)"
    r"|k\.?\s?a\.?"
    r")\W*$", re.IGNORECASE)

# Wieviele Woerter ein Feldwert mindestens haben muss, damit er ueberhaupt als
# Inhalt zaehlt. "value", "—", "TBD" sind kein Aufwand.
MIN_FIELD_WORDS = 1


def _field_value(block: str, pat: str) -> str | None:
    """Der Text hinter dem Feldlabel bis zum Zeilenende — oder None."""
    m = re.search(rf"(?:^|\n|\*\*|[-*]\s*)\s*(?:\*\*)?\s*(?:{pat})\s*"
                  rf"(?:\*\*)?\s*[:：](?P<val>[^\n]*)", block, re.IGNORECASE)
    if m is None:
        return None
    return m.group("val").strip()


def is_placeholder(value: str) -> bool:
    """Traegt der Feldwert keinen Inhalt (Platzhalter, Leerformel, leer)?"""
    text = prose(value or "").strip(" \t*_-–—·:")
    if not text:
        return True
    if len(text.split()) < MIN_FIELD_WORDS:
        return True
    return bool(_PLACEHOLDER_RE.match(text))


def _explained_omission(block: str, pat: str) -> bool:
    """Das Feld fehlt, aber der Optionstext BEGRUENDET das belegt.

    Der Auftrag laesst genau zwei Wege: eine belegte Groessenordnung — oder
    das Feld entfaellt samt Begruendung im Text. Als Begruendung zaehlt nur
    ein belegter Satz ausserhalb der Feldzeilen, der das Feld beim Namen
    nennt; ein Nebensatz in der Trigger-Zeile reicht nicht."""
    field_pats = "|".join(p for _k, p in OPTION_FIELDS["en"]) + "|" + \
        "|".join(p for _k, p in OPTION_FIELDS["de"])
    label_re = re.compile(rf"^\W*(?:\*\*)?\s*(?:{field_pats})\s*(?:\*\*)?\s*[:：]",
                          re.IGNORECASE)
    for raw in split_claims(block):
        line = raw.strip()
        if not line or line.startswith("#") or label_re.match(line):
            continue
        if not _has_citation(line):
            continue
        if re.search(rf"\b(?:{pat})\b", prose(line), re.IGNORECASE):
            return True
    return False


def _missing_fields(block: str, lang: str) -> list[str]:
    L = _lang(lang)
    missing = []
    for (key, pat), label in zip(OPTION_FIELDS[L], OPTION_LABELS[L]):
        value = _field_value(block, pat)
        if value is None:
            if not _explained_omission(block, pat):
                missing.append(label)
        elif is_placeholder(value):
            missing.append(f"{label} (Platzhalter)")
    return missing


# --------------------------------------------------------------------------
# Messbezug der Optionen (R6-2, jury_7.md 2026-09-07)
# --------------------------------------------------------------------------
# Woertlich: „P verknuepft keine einzige seiner vier Handlungsoptionen damit."
# Der Messanhang ist unser einziger Alleinstellungsinhalt — beide Jurys sagen
# das ausdruecklich —, und er lag als unverbundener Datenblock hinter dem
# Bericht. Runde 6 erzwang deshalb: jede Option muss eine gemessene Groesse
# nennen. Runde 7 nimmt diesen Zwang WIEDER ZURUECK (jury_9.md 2026-09-07,
# woertlich: die Messwerte stehen „dekorativ" in den Optionen). An seine
# Stelle tritt die VERWENDBARKEITSREGEL — siehe `measure_inventory` weiter
# unten. Besser keine Zahl als eine, die nicht traegt.
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
    """Die Zahlen (und CPC-Codes), die als „gemessen" gelten UND verwendet
    werden duerfen.

    Quelle sind die Skalare der beiden Vorstufen, nicht der Anhangstext: was
    hier steht, ist per Konstruktion ein Query-Ergebnis. Seit R7 laeuft die
    Liste durch die Verwendbarkeitsregel (`measure_inventory`) — eine Groesse
    ohne n/Zeitraum oder unter Kalibrierungsvorbehalt steht nicht mehr darin
    und gilt im Bericht nicht als Beleg."""
    return _flatten_needles(
        measure_inventory(quant_summary, corpus_summary)["usable"])


def _needle_hit(text: str, needle: str) -> bool:
    # `(?![.,]\d)` ist nicht kosmetisch: ohne diesen Blick nach rechts traf die
    # Nadel „3" mitten in „3.3 % per year". Im B7-Lauf hat genau das fuenf
    # korrekte Saetze mit dem kanonischen Median geloescht — die Nadel kam von
    # einem GESPERRTEN Jahreswert 3.0, dessen Ganzzahlform „3" lautet.
    pat = re.compile(r"(?<![\w.,])" + re.escape(needle) + r"(?![\d]|[.,]\d)",
                     re.IGNORECASE)
    return bool(pat.search(text or ""))


def uses_measurement(text: str, needles: list[str]) -> bool:
    return any(_needle_hit(text, n) for n in needles or ())


def _brief_value(e: dict) -> str:
    v = e["value"]
    shown = f"{v:,}" if isinstance(v, int) and not str(e["key"]).startswith(
        ("takeoff", "centrality")) else str(v)
    if e["key"] == "selection":
        return f"measured patent class {shown}"
    tail = []
    if e.get("n") and e["n"] != v:      # bei einer Zaehlung IST der Wert das n
        tail.append(f"n={e['n']:,}" if isinstance(e["n"], int) else f"n={e['n']}")
    if e.get("window"):
        w = e["window"]
        tail.append("–".join(str(x) for x in w) if isinstance(w, (list, tuple))
                    else str(w))
    return f"{e['label']} {shown}" + (f" ({', '.join(tail)})" if tail else "")


def measured_brief(quant_summary: dict | None,
                   corpus_summary: dict | None = None) -> str:
    """Die VERWENDBAREN gemessenen Groessen als eine Zeile fuer den
    Berichtsprompt — was geprueft wird, muss das Modell auch benannt bekommen,
    und zwar mit n und Zeitraum, damit es sie belastbar einsetzen kann."""
    inv = measure_inventory(quant_summary, corpus_summary)
    return " · ".join(_brief_value(e) for e in inv["usable"])


def blocked_brief(quant_summary: dict | None,
                  corpus_summary: dict | None = None) -> str:
    """Die gesperrten Groessen samt Grund — das Modell muss wissen, welche
    Zahlen es NICHT verwenden darf, sonst holt es sie aus dem Anhang."""
    inv = measure_inventory(quant_summary, corpus_summary)
    return "\n".join(f"- {e['label']}: {e['value']} — do not use: {e['reason']}"
                      for e in inv["blocked"])


# --------------------------------------------------------------------------
# Verwendbarkeitsregel fuer gemessene Groessen (R7-1, jury_9.md 2026-09-07)
# --------------------------------------------------------------------------
# Der schwerste Vorwurf der neunten Jury lautet woertlich: die Messwerte stehen
# „dekorativ" im Text — sie erzeugen Belegoptik, ohne dass eine Option ohne sie
# anders lauten wuerde. Drei Belege dafuer, alle mechanisch pruefbar:
#
#   * Dieselbe Zykluszeit (12,0 Jahre) stuetzte zwei unvereinbare Schluesse
#     (Bauzeit einer Plattform UND Zeitpunkt der Generikawelle).
#   * Das Take-off-Jahr 1990 begruendete eine Option, obwohl der eigene Anhang
#     daneben „not reportable as a lead time" schreibt.
#   * Die Zahl der Kurzfassung (6,1 %/yr in 2026) sperrt der eigene
#     Kalibrierungsvorbehalt („calibrated only to ~2019"), und sie widersprach
#     unaufgeloest dem Median (3,3 %/yr) aus demselben Absatz.
#
# Die Regel, die den Nennungszwang aus Runde 6 ersetzt: eine gemessene Groesse
# darf im Fliesstext oder in einer Option nur erscheinen, wenn sie
#
#   (a) nicht als „not reportable" oder unter Kalibrierungsvorbehalt gefuehrt
#       wird,
#   (b) im Messanhang mit n, Zeitraum und Rechenweg steht (dieselben Felder,
#       die pipeline/dossier_quant.measurement_recipe ausgibt), und
#   (c) eindeutig ist: je Kennzahl genau ein kanonischer Wert im Dokument. Wer
#       Median und aktuellen Wert nennt, muss beide in EINEM Satz
#       gegenueberstellen — sonst Ablehnung.
#
# (a) schlaegt (c): ein gesperrter Wert wird auch durch eine Gegenueberstellung
# nicht verwendbar. Und eine Option ohne verwendbare Messgroesse ist zulaessig —
# sie muss ihre Begruendung dann aus Belegen ziehen (Zitat im Optionsblock).

# Die Stichworte, an denen eine Kennzahl im Satz erkennbar ist. Ein gesperrter
# Wert loest nur zusammen mit seinem Stichwort aus: „1990" allein kann das
# Datenfenster meinen, „market take-off ... 1990" meint die gesperrte Groesse.
MEASURE_CUES: dict[str, str] = {
    "rate": r"improvement rate|improvement-rate|k\s*\(\s*t\s*\)"
            r"|verbesserungsrate|%\s*/\s*(?:yr|year|jahr)|% per year",
    "cycle": r"cycle[- ]time|zykluszeit",
    "centrality": r"centrality|zentralit",
    "lead": r"lead[- ]time|lead of|vorlauf",
    "takeoff": r"take[- ]?off",
}

# Wie ein rivalisierender Wert derselben Kennzahl im Satz aussieht (Regel (c)).
MEASURE_VALUE_RE: dict[str, re.Pattern] = {
    "rate": re.compile(r"(?<![\w.,])(\d{1,3}(?:[.,]\d{1,2})?)\s*%\s*"
                       r"(?:/|per\s+|pro\s+)\s*(?:yr|year|jahr|a)\b", re.IGNORECASE),
    "years": re.compile(r"(?<![\w.,])(\d{1,3}(?:[.,]\d{1,2})?)\s*"
                        r"(?:years|year|yrs|yr|jahre|jahren)\b", re.IGNORECASE),
    "year": re.compile(r"(?<![\w.,])((?:19|20)\d{2})(?![\d])"),
}

_TAKEOFF_TIERS = ("science", "patent", "funding", "market")

# Wie weit eine Zahl vom Stichwort ihrer Kennzahl entfernt stehen darf, um noch
# als diese Kennzahl zu gelten. Ohne diesen Abstand wuerde in einem Satz mit
# „centrality" jede Jahreszahl als rivalisierender Wert gelten — auch eine, die
# von etwas ganz anderem handelt.
CUE_PROXIMITY_CHARS = 90


def _near_cue(text: str, cue: str, start: int, end: int,
              window: int = CUE_PROXIMITY_CHARS) -> bool:
    """Steht ein Vorkommen des Stichworts nah genug an der Fundstelle?"""
    for m in re.finditer(cue, text, re.IGNORECASE):
        if m.start() - window <= end and start <= m.end() + window:
            return True
    return False


def _entry(key, label, value, *, cue=None, unit=None, n=None, window=None,
           year=False, reason=None) -> dict:
    # Nadeln unter MIN_NEEDLE_CHARS fliegen HIER raus, nicht erst beim
    # Einsammeln: `measure_use_findings` liest die Nadeln eines Eintrags
    # direkt, und eine einstellige Nadel trifft in jedem Text irgendetwas.
    return {"key": key, "label": label, "value": value,
            "needles": [n_ for n_ in _needle_forms(value, year=year)
                        if len(str(n_)) >= MIN_NEEDLE_CHARS],
            "cue": cue, "unit": unit, "n": n, "window": window,
            "reason": reason}


def measure_inventory(quant_summary: dict | None,
                      corpus_summary: dict | None = None) -> dict:
    """Welche gemessene Groesse verwendbar ist und welche gesperrt — und warum.

    Rueckgabe {"usable": [...], "blocked": [...]}. Beide Listen enthalten
    Eintraege mit `needles` (Schreibweisen der Zahl im Text), `cue`
    (Stichwort der Kennzahl) und bei gesperrten Groessen `reason` im Klartext.
    Quelle ist ausschliesslich der Skalar-Teil der Messung — kein Parsen des
    Anhangtexts."""
    q, c = quant_summary or {}, corpus_summary or {}
    usable: list[dict] = []
    blocked: list[dict] = []
    if not q.get("off_topic"):
        for code in (q.get("selection") or [])[:6]:
            usable.append(_entry("selection", "measured patent class", code))

        k, win, n_pat = q.get("K_median"), q.get("K_window"), q.get("n_patents")
        if k is not None:
            if q.get("K_calibrated", True) and win and n_pat:
                usable.append(_entry(
                    "K_median", MEASURED_LABELS["K_median"], k, cue="rate",
                    unit="rate", n=n_pat, window=win))
            else:
                blocked.append(_entry(
                    "K_median", MEASURED_LABELS["K_median"], k, cue="rate",
                    unit="rate", reason="the appendix reports no n and period "
                                        "for it, or its absolute value is "
                                        "outside the calibrated range"))
        # Jahreswerte der K(t)-Kurve: NIE verwendbar. Der eigene
        # Ehrlichkeitsvermerk kalibriert Absolutwerte nur bis ~2019, und die
        # juengsten Fenster sind ausdruecklich unvollstaendig. Genau diese Zahl
        # (6,1 %/yr in 2026) stand in der Entscheidungs-Kurzfassung.
        for p in (q.get("K_by_year") or []):
            v = p.get("K")
            if v is None or (k is not None and float(v) == float(k)):
                continue
            blocked.append(_entry(
                "K_year", f"improvement rate of the {p.get('year')} window", v,
                cue="rate", unit="rate",
                reason=(f"a single {p.get('year')} window of the K(t) curve — "
                        f"absolute rates are calibrated only to ~2019"
                        + ("; this window is still incomplete (citation lag)"
                           if not p.get("complete") else "")
                        + f". The canonical figure is the median "
                          f"{k if k is not None else 'n/a'} %/yr")))

        cyc, edges = q.get("cycle_time_years"), q.get("cycle_time_edges")
        if cyc is not None:
            if edges and q.get("cycle_time_since"):
                usable.append(_entry(
                    "cycle_time_years", MEASURED_LABELS["cycle_time_years"], cyc,
                    cue="cycle", unit="years", n=edges,
                    window=f"filings from {q.get('cycle_time_since')}"))
            else:
                blocked.append(_entry(
                    "cycle_time_years", MEASURED_LABELS["cycle_time_years"], cyc,
                    cue="cycle", unit="years",
                    reason="the appendix states no edge count and no period "
                           "for it"))

        peak, peak_n = q.get("centrality_peak_year"), q.get("centrality_peak_n")
        if peak is not None:
            if peak_n and q.get("centrality_window"):
                usable.append(_entry(
                    "centrality_peak_year",
                    MEASURED_LABELS["centrality_peak_year"], peak,
                    cue="centrality", unit="year", n=peak_n, year=True,
                    window=q.get("centrality_window")))
            else:
                blocked.append(_entry(
                    "centrality_peak_year",
                    MEASURED_LABELS["centrality_peak_year"], peak, year=True,
                    cue="centrality", unit="year",
                    reason="the appendix states no cohort size and no period "
                           "for it"))

        for key in ("lead_patent_market", "lead_science_market"):
            v = q.get(key)
            if v is None:
                continue
            usable.append(_entry(key, MEASURED_LABELS[key], v, cue="lead",
                                 unit="years",
                                 n=(q.get("tier_n") or {}).get("market"),
                                 window=q.get("K_window")))

        # Take-off-Jahre: nur verwendbar, wenn der Anhang aus ihnen eine
        # Vorlaufzeit bildet. Bildet er keine, schreibt er daneben „not
        # reportable as a lead time" — dann darf das Jahr auch keine Handlung
        # begruenden. Ein Take-off auf dem linken Rand des Datenfensters ist
        # ausserdem immer ein Artefakt der eigenen Sammlung.
        window_start = int(q.get("data_window_start") or 0)
        reportable = bool(q.get("takeoff_reportable"))
        for tier in _TAKEOFF_TIERS:
            y = (q.get("takeoffs") or {}).get(tier)
            if not y:
                continue
            label = f"{tier} take-off year"
            if reportable and int(y) > window_start:
                usable.append(_entry(f"takeoff_{tier}", label, y, cue="takeoff",
                                     unit="year", year=True,
                                     n=(q.get("tier_n") or {}).get(tier),
                                     window=q.get("K_window")))
            else:
                blocked.append(_entry(
                    f"takeoff_{tier}", label, y, cue="takeoff", unit="year",
                    year=True,
                    reason=("it sits on the left edge of the data window "
                            f"({window_start}) and measures our own collection"
                            if int(y) <= window_start else
                            "the appendix reports these take-offs as 'not "
                            "reportable as a lead time'")))

        if q.get("n_patents"):
            usable.append(_entry("n_patents", MEASURED_LABELS["n_patents"],
                                 q["n_patents"], n=q["n_patents"],
                                 window=q.get("K_window")))

    for key in CORPUS_KEYS:
        v = c.get(key)
        if v is None:
            continue
        win = c.get("market_window" if key.startswith("market")
                    else "science_window")
        usable.append(_entry(key, MEASURED_LABELS[key], v, n=v, window=win))
    return {"usable": usable, "blocked": blocked}


def _flatten_needles(entries: list[dict]) -> list[str]:
    out, seen = [], set()
    for e in entries:
        for n in e["needles"]:
            n = str(n).strip()
            if len(n) >= MIN_NEEDLE_CHARS and n.lower() not in seen:
                seen.add(n.lower())
                out.append(n)
    return out


def blocked_needles(quant_summary: dict | None,
                    corpus_summary: dict | None = None) -> list[str]:
    """Die Zahlen, die im Fliesstext NICHT stehen duerfen."""
    return _flatten_needles(
        measure_inventory(quant_summary, corpus_summary)["blocked"])


def _num(v) -> float | None:
    try:
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------
# Reichweite der Messung (R8-3, jury_11.md §4.5, 2026-09-07)
# --------------------------------------------------------------------------
# Woertlich: „Nicht-Sequitur aus der eigenen Messung: 'The measured median
# improvement rate of 3.3%/yr suggests that natural modulators may not offer a
# significant advantage over synthetic drugs'. Gemessen wurden A61P5/48 und
# C12N2501/335, also die Peptid-/Wirkstoffklassen — daraus folgt nichts ueber
# natuerliche Modulatoren."
#
# Die Regel ist damit nicht mehr nur „darf diese Zahl im Text stehen", sondern
# „reicht sie bis zu dem Gegenstand, ueber den der Satz etwas behauptet".
# Mechanisch: zieht ein Satz aus einer gemessenen Groesse einen Schluss, muss er
# den GEMESSENEN Gegenstand benennen — die Phrase, auf der die CPC-Aufloesung
# lief, oder eine ihrer Klassen. Tut er das nicht, ist die Reichweite unbelegt.

_SCOPE_STOP = frozenset("""
and or the of for in on with a an new next technology technologies industry
industries sector sectors market markets system systems field fields und oder
der die das fuer mit technologie technologien markt branche
""".split())

_INFERENCE_RE = re.compile(
    r"\b(?:suggest(?:s|ing|ed)?|impl(?:y|ies|ying|ied)|indicat(?:e|es|ing|ed)"
    r"|therefore|thus|hence|points?\s+to|shows?\s+that|demonstrat\w+\s+that"
    r"|means?\s+that|implication\s+is"
    r"|legt\s+nahe|deutet\s+darauf|folglich|zeigt,?\s+dass"
    r"|bedeutet,?\s+dass)\b", re.IGNORECASE)


def measurement_scope_terms(quant_summary: dict | None,
                            topic: str = "") -> list[str]:
    """Woran die Messung haengt: die aufgeloeste Phrase und ihre CPC-Klassen."""
    q = quant_summary or {}
    out: set[str] = set()
    for code in (q.get("selection") or []):
        code = str(code).strip().lower()
        if code:
            out.add(code)
            out.add(re.split(r"[/\s]", code)[0])
    phrase = f"{q.get('measured_phrase') or ''} {topic or ''}".lower()
    for w in re.findall(r"[a-z][a-z0-9-]{2,}", phrase):
        if w not in _SCOPE_STOP:
            out.add(w)
    return sorted(out)


def _names_scope(claim: str, scope_terms: list[str]) -> bool:
    return any(re.search(r"(?<![\w-])" + re.escape(t), claim, re.IGNORECASE)
               for t in scope_terms or ())


def measure_use_findings(report_md: str, quant_summary: dict | None,
                         corpus_summary: dict | None = None,
                         topic: str = "") -> list[dict]:
    """Saetze, die gegen die Verwendbarkeitsregel verstossen.

    Rueckgabe wie `verify_cited_figures`: [{"sentence", "tokens", "kind",
    "detail", "url"}] — dieselbe Weiterverarbeitung (ein Neuwurf, danach
    mechanische Streichung)."""
    inv = measure_inventory(quant_summary, corpus_summary)
    scope_terms = measurement_scope_terms(quant_summary, topic)
    out: list[dict] = []
    seen: set[tuple] = set()

    def add(sentence: str, token: str, detail: str) -> None:
        key = (sentence, token)
        if key not in seen:
            seen.add(key)
            out.append({"sentence": sentence, "tokens": [token],
                        "kind": "measure", "detail": detail, "url": ""})

    for raw in split_claims(body_text(report_md)):
        sentence = raw.strip()
        if not sentence or sentence.startswith("#"):
            continue
        claim = prose(sentence)
        low = claim.lower()
        # (a) gesperrte Groesse — nur zusammen mit ihrem Stichwort, sonst
        # traefe "1990" jede Erwaehnung des Datenfensters.
        for e in inv["blocked"]:
            cue = MEASURE_CUES.get(e["cue"] or "", "")
            if cue and not re.search(cue, low, re.IGNORECASE):
                continue
            for n in e["needles"]:
                m = re.search(r"(?<![\w.,])" + re.escape(n) + r"(?![\d])",
                              claim, re.IGNORECASE)
                if m and (not cue or _near_cue(claim, cue, m.start(), m.end())):
                    add(sentence, n,
                        f"{e['label']} ({e['value']}) is not usable: "
                        f"{e['reason']}")
                    break
        # (c) rivalisierender Wert derselben Kennzahl ohne Gegenueberstellung
        for e in inv["usable"]:
            cue = MEASURE_CUES.get(e["cue"] or "", "")
            if not cue or not e.get("unit") or not re.search(cue, low, re.IGNORECASE):
                continue
            canon = _num(e["value"])
            pat = MEASURE_VALUE_RE.get(e["unit"])
            if canon is None or pat is None:
                continue
            if any(_needle_hit(claim, n) for n in e["needles"]):
                continue          # der kanonische Wert steht im selben Satz
            for m in pat.finditer(claim):
                v = _num(m.group(1))
                if v is None or v == canon:
                    continue
                if not _near_cue(claim, cue, m.start(), m.end()):
                    continue
                add(sentence, m.group(0).strip(),
                    f"{e['label']}: the document's canonical value is "
                    f"{e['value']}. A second value for the same quantity is "
                    f"only allowed if both stand in ONE sentence, contrasted")
        # (d) R8-3: Reichweite. Ein Schluss AUS der Messung muss den
        # gemessenen Gegenstand benennen — sonst behauptet er etwas ueber
        # etwas, das gar nicht gemessen wurde.
        if scope_terms and _INFERENCE_RE.search(claim) \
                and not _names_scope(claim, scope_terms):
            for e in inv["usable"]:
                cue = MEASURE_CUES.get(e["cue"] or "", "")
                if not cue or not re.search(cue, low, re.IGNORECASE):
                    continue
                hit = next((n for n in e["needles"] if _needle_hit(claim, n)),
                           None)
                if not hit:
                    continue
                add(sentence, hit,
                    f"the measurement's reach: {e['label']} was computed over "
                    f"{', '.join(scope_terms[:4])} — this sentence draws a "
                    f"conclusion without naming the measured subject, so the "
                    f"figure does not carry it")
                break
    return out


def _has_citation(text: str) -> bool:
    return bool(_MARKER.search(text or "") or _LINK.search(text or ""))


# --------------------------------------------------------------------------
# Branchenabdeckung der Optionen (R6-3, jury_8.md 2026-09-07)
# --------------------------------------------------------------------------
# „4 Optionen sind sauber strukturiert, aber fast ausschliesslich
# Food/Labeling-fokussiert; HealthTech kommt nicht vor." Die Frage nennt drei
# Felder, der Optionsteil bediente eines. Die Felder werden AUS DER FRAGE
# gelesen (kein GLP-1-Sonderfall): steht ein Feld in der Frage, muss der
# Optionsabschnitt es adressieren.

# Ein Stichwort mit "*" ist ein Wortanfang ("reformul*" trifft
# "reformulate"/"reformulation"); alles andere ist ein ganzes Wort mit
# einfacher Pluraltoleranz. Substring-Matching waere hier fatal: "app" steckt
# in "approval", "monitoring" in "regulatory monitoring" — der R5-Nachtest
# meldete damit alle drei Felder als abgedeckt, obwohl jury_8.md das Gegenteil
# feststellte ("HealthTech kommt nicht vor").
SECTOR_LEXICON: dict[str, tuple[str, ...]] = {
    "food": ("food", "beverage", "drink", "ingredient", "recipe", "snack",
             "grocery", "meal", "menu", "dairy", "bakery", "confectionery",
             "portion", "reformul*", "formulation", "shelf life", "retail",
             "lebensmittel*", "getränk*", "rezeptur*"),
    "nutrition": ("nutrition", "nutritional", "nutrient", "diet", "dietary",
                  "protein", "fibre", "fiber", "supplement", "satiety",
                  "calorie", "caloric", "vitamin", "micronutrient",
                  "ernährung*", "nährstoff*", "nahrungsergänzung*"),
    "health technology": ("health technology", "health tech", "healthtech",
                          "digital health", "medtech", "medical device",
                          "device", "wearable", "diagnostic", "sensor",
                          "telehealth", "telemedicine", "app", "mobile app",
                          "digital therapeutic", "remote monitoring",
                          "patient monitoring", "companion diagnostic",
                          "gesundheitstechnologie*", "medizintechnik*"),
    "packaging": ("packaging", "package", "label", "labelling", "labeling",
                  "verpackung*"),
    "logistics": ("logistics", "supply chain", "distribution", "warehouse",
                  "cold chain", "logistik*", "lieferkette*"),
    "energy": ("energy", "power grid", "electricity", "renewable",
               "energie*", "strom*"),
    "mobility": ("mobility", "vehicle", "automotive", "fleet",
                 "mobilität*", "fahrzeug*"),
}

# Wie das Feld in einer Frage heissen kann (Erkennung, nicht Abdeckung).
_SECTOR_ALIASES: dict[str, tuple[str, ...]] = {
    "health technology": ("health technology", "health tech", "healthtech",
                          "digital health", "medtech", "medical technology"),
}


def _term_re(term: str) -> re.Pattern:
    if term.endswith("*"):
        return re.compile(r"\b" + re.escape(term[:-1]), re.IGNORECASE)
    return re.compile(r"\b" + re.escape(term) + r"(?:e|en|es|s)?\b",
                      re.IGNORECASE)


def sectors_from_question(question: str) -> list[str]:
    """Die Felder, die die Frage ausdruecklich nennt — nur die werden geprueft."""
    low = (question or "").lower()
    out = []
    for name in SECTOR_LEXICON:
        for alias in _SECTOR_ALIASES.get(name, (name,)):
            if _term_re(alias).search(low):
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
        # R7-1: eine Option ohne Messgroesse ist kein Mangel mehr — eine ohne
        # Messgroesse UND ohne Beleg schon.
        "options_unsupported": sum(
            1 for b in blocks if not uses_measurement(b, measured or [])
            and not _has_citation(b)),
        "sectors": list(sectors or []),
        "sectors_missing": uncovered_sectors(sections.get("options", ""),
                                             sectors or []),
    }


# Aufzaehlung der geprueften Felder ("food, nutrition and health technology")
# — das ist die Anweisung, nachgesprochen, kein Inhalt. Der B6-Lauf bestand die
# Abdeckungspruefung genau so: "health technology" kam im Optionsteil nur in
# dem Satz vor, der die drei Felder aufzaehlt.
def _echo_spans(text: str, sectors: list[str]) -> str:
    if len(sectors or []) < 2:
        return text
    names = []
    for s in sectors:
        names += list(_SECTOR_ALIASES.get(s, (s,)))
    alt = "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True))
    enum = re.compile(rf"(?:{alt})(?:\s*(?:,|/|\band\b|\bor\b|\bund\b|\boder\b)\s*"
                      rf"(?:{alt})){{1,4}}", re.IGNORECASE)
    return enum.sub(" ", text or "")


def uncovered_sectors(text: str, sectors: list[str]) -> list[str]:
    """Felder, die der Text nicht bedient. Eine blosse Aufzaehlung der Felder
    zaehlt nicht als Abdeckung — sie ist die nachgesprochene Anweisung."""
    body = _echo_spans(text or "", list(sectors or []))
    return [s for s in sectors or ()
            if not any(_term_re(kw).search(body)
                       for kw in SECTOR_LEXICON.get(s, ()))]


# --------------------------------------------------------------------------
# Katalysator-Kalender und Abdeckung der Innovationskette (R8-1, jury_11/12)
# --------------------------------------------------------------------------
# Beide Jurys vom 2026-09-07 verloren wir an derselben Stelle: „Abdeckung 6:9"
# und „zeitliche Einordnung 6:9" — zusammen genau der Rueckstand. Der Gegner
# hatte einen datierten Katalysator-Kalender („CagriSema's US obesity decision
# (Q4 2026); Lilly's retatrutide BLA (Q1 2027)"), wir nur Zeithorizonte je
# Option. Und jury_11 zaehlte nach: unsere eigenen Messwerte „tauchen im
# Fliesstext kein einziges Mal auf", die Foerderebene stand nur in der Tabelle.
#
# Also drei mechanische Pflichten, alle im Neuwurf-Kanal:
#   (a) ein Pflichtabschnitt mit >= MIN_CALENDAR_ROWS datierten UND belegten
#       Zeilen,
#   (b) je Kette-Ebene (Wissenschaft/Patente/Foerderung/Markt) mindestens eine
#       datierte, belegte Aussage IM FLIESSTEXT,
#   (c) die Untergrenze des Laengenbands ist wieder ein Befund, kein Hinweis.

MIN_CALENDAR_ROWS = 5
# R9-4 (jury_14 2026-09-07): „6 Zeilen, 4 davon aus derselben Sekundaerquelle".
# Ein Terminkalender, der an einer Quelle haengt, ist eine Quelle mit Zeilen,
# kein Kalender.
MIN_CALENDAR_SOURCES = 3

_MONTHS = (r"jan(?:uary|uar)?|feb(?:ruary|ruar)?|mar(?:ch)?|m(?:ä|ae)rz|apr(?:il)?"
           r"|may|mai|jun[ei]?|jul[yi]?|aug(?:ust)?|sep(?:t(?:ember)?)?"
           r"|o[ck]t(?:ober)?|nov(?:ember)?|de[czk](?:ember)?")

# Ein Datum ist alles, woraus ein Leser einen Termin ablesen kann: Tag, Monat,
# Quartal, Halbjahr — immer MIT Jahr. Ein nacktes Jahr zaehlt auch: „SPC laeuft
# 2031 ab" ist eine terminierte Aussage.
_DATE_RE = re.compile(
    r"(?<![\w-])(?:"
    r"\d{4}-\d{2}-\d{2}"
    r"|\d{1,2}[./]\d{1,2}[./]((?:19|20)\d{2})"
    r"|[QH][1-4]\s*[-/ ]?\s*((?:19|20)\d{2})"
    r"|((?:19|20)\d{2})\s*[-/ ]?\s*[QH][1-4]"
    rf"|\d{{1,2}}\.?\s+(?:{_MONTHS})\.?,?\s+((?:19|20)\d{{2}})"
    rf"|(?:{_MONTHS})\.?\s+\d{{1,2}},?\s+((?:19|20)\d{{2}})"
    rf"|(?:{_MONTHS})\.?\s+((?:19|20)\d{{2}})"
    # "Mid-2026" mit Bindestrich zaehlt auch: der B8-Lauf schrieb genau das,
    # und die nackte Jahresform verwirft ein "-" davor (sonst traefe sie
    # jede URL mit einer Jahreszahl im Pfad).
    r"|(?:early|mid|late|first half|second half|anfang|mitte|ende)[\s-]+"
    r"((?:19|20)\d{2})"
    r"|((?:19|20)\d{2})"
    r")", re.IGNORECASE)


def _date_years(text: str) -> list[int]:
    """Die Jahre aller Datumsangaben eines Textstuecks."""
    out = []
    for m in _DATE_RE.finditer(text or ""):
        hit = m.group(0)
        year = next((g for g in m.groups() if g), None)
        if year is None:
            y = re.search(r"(?:19|20)\d{2}", hit)
            year = y.group(0) if y else None
        if year:
            out.append(int(year))
    return out


def has_date(text: str, year_floor: int | None = None) -> bool:
    years = _date_years(text)
    if year_floor is None:
        return bool(years)
    return any(y >= year_floor for y in years)


def table_rows(section_text: str) -> list[list[str]]:
    """Die Datenzeilen einer Markdown-Tabelle — ohne Kopf und Trennzeile."""
    rows: list[list[str]] = []
    for line in (section_text or "").splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 3:
            continue
        joined = " ".join(cells)
        if re.fullmatch(r"[\s|:_-]*", joined):        # Trennzeile
            continue
        rows.append(cells)
    return rows


def calendar_rows(report_md: str, lang: str = "en",
                  year_floor: int | None = None) -> dict:
    """Bilanz des Katalysator-Kalenders: wie viele Zeilen Datum UND Beleg
    tragen, und woran die uebrigen scheitern."""
    sections = split_sections(body_text(report_md), _lang(lang))
    rows = table_rows(sections.get("next", ""))
    ok = no_date = no_cite = 0
    for cells in rows:
        line = " ".join(cells)
        # Der Kopf ("Date | Event | Source | ...") traegt weder Datum noch Beleg
        # und wird nicht als Mangel gezaehlt.
        dated, cited = has_date(line, year_floor), _has_citation(line)
        if dated and cited:
            ok += 1
        elif not dated and not cited:
            continue
        elif not dated:
            no_date += 1
        else:
            no_cite += 1
    return {"rows": len(rows), "ok": ok, "no_date": no_date, "no_cite": no_cite,
            "sources": len(calendar_sources(report_md, lang, year_floor))}


def _citation_keys(text: str, by_id: dict | None = None) -> set[str]:
    """Womit ein Satz belegt ist — Katalog-ID oder Host des Links.

    Beide Formen, weil die Pruefung im Lauf VOR der Kanonisierung laeuft
    (Marker) und das ausgelieferte Dokument danach gelesen wird (Links)."""
    out: set[str] = set()
    for m in _MARKER.finditer(text or ""):
        key = m.group(0)[2:-2].strip()
        src = (by_id or {}).get(key) or (by_id or {}).get(key.upper())
        url = str((src or {}).get("url") or "")
        out.add(url.split("/")[2] if url.count("/") > 2 else key)
    for m in _LINK.finditer(text or ""):
        url = m.group(2)
        if url.count("/") > 2:
            out.add(url.split("/")[2])
    return out


def calendar_sources(report_md: str, lang: str = "en",
                     year_floor: int | None = None,
                     sources: list[dict] | None = None) -> set[str]:
    """Die VERSCHIEDENEN Quellen, auf denen die gueltigen Kalenderzeilen ruhen."""
    by_id = {s.get("id"): s for s in (sources or [])}
    sections = split_sections(body_text(report_md), _lang(lang))
    out: set[str] = set()
    for cells in table_rows(sections.get("next", "")):
        line = " ".join(cells)
        if has_date(line, year_floor) and _has_citation(line):
            out |= _citation_keys(line, by_id)
    return out


def calendar_findings(report_md: str, lang: str = "en",
                      year_floor: int | None = None) -> list[str]:
    """Zu wenige datierte, belegte Zeilen im Katalysator-Kalender = Neuwurf."""
    sections = split_sections(body_text(report_md), _lang(lang))
    if "next" not in sections:
        return []                       # fehlender Abschnitt: eigener Befund
    c = calendar_rows(report_md, lang, year_floor)
    if c["ok"] >= MIN_CALENDAR_ROWS:
        if c["sources"] >= MIN_CALENDAR_SOURCES:
            return []
        heading = dict((k, h) for k, h, _p in SECTIONS[_lang(lang)])["next"]
        return [f"'{heading}': {c['ok']} Zeilen, aber nur {c['sources']} "
                f"verschiedene Quelle(n) — mindestens "
                f"{MIN_CALENDAR_SOURCES}. Ein Kalender, dessen Zeilen "
                f"mehrheitlich aus einer Quelle stammen, belegt einen "
                f"Zeitplan nicht. Termine aus anderen Katalogeintraegen "
                f"aufnehmen (Behoerdenkalender, Firmen-IR, Gericht, "
                f"Studienregister) oder Zeilen streichen, die keine eigene "
                f"Quelle haben."]
        return []
    detail = []
    if c["no_date"]:
        detail.append(f"{c['no_date']} Zeile(n) ohne Datum")
    if c["no_cite"]:
        detail.append(f"{c['no_cite']} Zeile(n) ohne Beleg")
    heading = dict((k, h) for k, h, _p in SECTIONS[_lang(lang)])["next"]
    return [f"'{heading}': nur {c['ok']} von mindestens {MIN_CALENDAR_ROWS} "
            f"Tabellenzeilen tragen Datum UND Beleg"
            + (f" ({', '.join(detail)})" if detail else "")
            + f". Jede Zeile braucht ein Datum (Tag, Monat, Quartal oder "
              f"Halbjahr mit Jahr) und ein Zitat in der Spalte 'Source'. "
              f"Nur Ereignisse aufnehmen, deren Termin in den Belegen steht — "
              f"nichts schaetzen."]


# --------------------------------------------------------------------------
# Abdeckung je Ebene der Innovationskette
# --------------------------------------------------------------------------
# Die Kette ist Wissenschaft -> Patente -> Foerderung -> Markt. jury_11:
# „Foerderung nur ueber die eigene Tabelle — im Fliesstext nicht ausgewertet",
# „Wissenschaft am duennsten". Jede Ebene braucht mindestens einen Satz, der
# datiert UND belegt ist; sonst benennt der Neuwurf die fehlende Ebene.

CHAIN_LEVELS: dict[str, tuple[str, ...]] = {
    "science": ("study", "studies", "trial", "trials", "phase 1", "phase 2",
                "phase 3", "phase i", "phase ii", "phase iii", "read-out",
                "readout", "peer-review*", "journal", "preprint", "clinical",
                "endpoint", "cohort", "publication", "published in",
                "studie*", "klinisch*", "fachzeitschrift"),
    "patents": ("patent", "patents", "spc", "supplementary protection",
                "filing", "filings", "intellectual property", "citation graph",
                "cpc", "patentfamilie*", "schutzzertifikat", "schutzrecht*"),
    "funding": ("funding", "funded", "raised", "financing", "venture",
                "investor", "investors", "grant", "grants", "acquisition",
                "acquired", "acquire", "merger", "licensing", "licence deal",
                "license deal", "milestone payment", "ipo", "series a",
                "series b", "series c", "finanzierung*", "uebernahme*",
                "übernahme*", "foerder*", "förder*"),
    "market": ("revenue", "revenues", "sales", "market", "markets", "pricing",
               "price", "market share", "launch", "launched", "prescriptions",
               "reimbursement", "demand", "umsatz*", "markt*", "erstattung*"),
}

CHAIN_LABELS = {
    "en": {"science": "science", "patents": "patents", "funding": "funding",
           "market": "market"},
    "de": {"science": "Wissenschaft", "patents": "Patente",
           "funding": "Förderung", "market": "Markt"},
}


def chain_coverage(report_md: str, lang: str = "en") -> dict:
    """Je Kette-Ebene: gibt es im Fliesstext einen datierten, belegten Satz?"""
    out = {k: False for k in CHAIN_LEVELS}
    for raw in split_claims(body_text(report_md)):
        sentence = raw.strip()
        if not sentence or sentence.startswith("#"):
            continue
        if not _has_citation(sentence) or not has_date(prose(sentence)):
            continue
        claim = prose(sentence)
        for level, terms in CHAIN_LEVELS.items():
            if out[level]:
                continue
            if any(_term_re(t).search(claim) for t in terms):
                out[level] = True
    return out


def chain_findings(report_md: str, lang: str = "en") -> list[str]:
    L = _lang(lang)
    cov = chain_coverage(report_md, lang)
    missing = [k for k, v in cov.items() if not v]
    if not missing:
        return []
    names = ", ".join(CHAIN_LABELS[L].get(k, k) for k in missing)
    return [f"Innovationskette nicht abgedeckt — keine datierte UND belegte "
            f"Aussage im Fliesstext zu: {names}. Jede der vier Ebenen "
            f"(Wissenschaft, Patente, Foerderung, Markt) braucht mindestens "
            f"einen Satz mit Datum und Zitat im selben Satz; fehlt das "
            f"Material, gehoert die Luecke ausdruecklich in 'Open questions "
            f"and limits'."]


# --------------------------------------------------------------------------
# Faktenquote (R9-3, Endstand-Diagnose 2026-09-07)
# --------------------------------------------------------------------------
# „Wir gewinnen Struktur und verlieren Substanz." Die Wortzahl war bis R8 das
# primaere Mass — und sie misst genau das Falsche: ein Text kann die
# Untergrenze mit Prosa erreichen und dabei faktenaermer sein als vorher.
# Gezaehlt wird ab jetzt deterministisch, was die Jurys unter Spezifitaet,
# Abdeckung und zeitlicher Einordnung bewerten: DATIERTE, PRIMAERBELEGTE
# Angaben je 100 Woerter Fliesstext.
#
# Zaehlweise: ein Satz zaehlt, wenn er ein Datum traegt UND mindestens ein
# Zitat vom Rang 0/1. Gezaehlt werden dann seine Einzelangaben — jede
# eigenstaendige Datumsangabe plus jede Praezisionszahl. Die Wortzahl bleibt
# als OBERGRENZE bestehen; die Untergrenze ist kein Neuwurf-Grund mehr.
#
# Messlatte: derselbe Zaehler am Siegertext der vierzehnten Bewertung
# (scratchpad/glp1/C_sonnet.md) ergibt 1,83 je 100 Woerter (36 Angaben in
# 1.968 Woertern). B8 kam auf 1,00, B7 auf 0,06. Die Untergrenze steht knapp
# darueber: wer den Gegner schlagen will, muss dichter sein als er.

FACT_DENSITY_MIN = 2.0
OPPONENT_FACT_DENSITY = 1.83     # gemessen am 2026-09-07, C_sonnet.md


def _link_urls(text: str) -> list[str]:
    return [m.group(2) for m in _LINK.finditer(text or "")]


def fact_density(report_md: str, sources: list[dict] | None = None,
                 lang: str = "en", rank_of=None) -> dict:
    """Datierte, primaerbelegte Angaben je 100 Woerter Fliesstext.

    Funktioniert vor UND nach der Kanonisierung: Katalog-Marker werden ueber
    `sources` aufgeloest, freie Markdown-Links ueber `rank_of(url) -> int`
    (fehlt der Rueckruf, gilt ein Link ohne Katalogeintrag als Rang 2)."""
    by_id, by_url = _source_index(sources or [])
    body = body_text(report_md)
    words = count_words(body)
    dated = primary = specifics = 0
    for raw in split_claims(body):
        sentence = raw.strip()
        if not sentence or sentence.startswith("#"):
            continue
        text = prose(sentence)
        dates = {m.group(0).strip().lower() for m in _DATE_RE.finditer(text)}
        if not dates:
            continue
        cited = _cited_in(sentence, by_id, by_url)
        urls = _link_urls(sentence)
        if not cited and not urls:
            continue
        dated += 1
        ranks = [int(2 if c.get("rank") is None else c["rank"]) for c in cited]
        if rank_of is not None:
            known = {c.get("url") for c in cited} | {c.get("origin") for c in cited}
            ranks += [int(rank_of(u)) for u in urls if u not in known]
        if not ranks or min(ranks) > PRIMARY_RANK:
            continue
        primary += 1
        specifics += len(dates) + len(precision_figures(sentence))
    return {"words": words, "dated_claims": dated, "primary_claims": primary,
            "specifics": specifics,
            "per100": round(specifics * 100 / words, 2) if words else 0.0}


def fact_density_finding(density: dict | None, lang: str = "en") -> list[str]:
    """Unterschreitung der Faktenquote = Neuwurf-Grund (mit ERGAENZEN-Auftrag)."""
    if not density or not density.get("words"):
        return []
    if density["per100"] >= FACT_DENSITY_MIN:
        return []
    need = max(1, int(round(
        (FACT_DENSITY_MIN * density["words"] / 100) - density["specifics"])))
    return [f"Faktenquote {density['per100']} datierte, primaerbelegte Angaben "
            f"je 100 Woerter — Untergrenze {FACT_DENSITY_MIN} (Vergleichstext: "
            f"{OPPONENT_FACT_DENSITY}). Mindestens {need} weitere solche "
            f"Angaben ERGAENZEN: jede mit einem Datum (Tag, Monat, Quartal "
            f"oder Jahr) UND einem Katalog-Zitat vom Rang 0/1 (im Katalog mit "
            f"(primary) markiert) IM SELBEN Satz. Nicht verlaengern, sondern "
            f"unbelegte Prosa durch belegte Fakten ERSETZEN — Wiederholung, "
            f"Zusammenfassung und Allgemeinplaetze streichen, damit der Text "
            f"nicht ueber die Obergrenze waechst."]


def length_advisory(report_md: str, lang: str = "en") -> list[str]:
    """Die Laengenzahl fuer das Protokoll — der Befund selbst steht seit R8-1
    in `structure_findings`.

    Runde 7 behandelte „zu kurz" als blossen Hinweis, weil ein Neuwurf zum
    Auffuellen einlaedt. Der B7-Lauf kam damit auf 1.623 Woerter — 577 unter
    dem Band — und verlor bei beiden Jurys genau dort (Abdeckung 6:9). Die
    Untergrenze ist deshalb wieder ein Neuwurf-Grund; der Auftrag dazu lautet
    ausdruecklich „mit belegten Fakten fuellen, nicht mit Prosa"."""
    words = count_words(body_text(report_md))
    if words and words < BODY_WORDS_MIN:
        return [f"Fliesstext {words} Woerter — unter dem Zielband "
                f"{BODY_WORDS_MIN}-{BODY_WORDS_MAX}."]
    return []


def structure_findings(report_md: str, lang: str = "en",
                       measured: list[str] | None = None,
                       sectors: list[str] | None = None,
                       year_floor: int | None = None,
                       density: dict | None = None) -> list[str]:
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
    # R9-3: die Wortzahl-UNTERGRENZE ist kein Neuwurf-Grund mehr. Sie hat in
    # R8 genau das erzeugt, was die vierzehnte Jury dann ruegte — Struktur
    # erfuellt, Substanz duenn. An ihre Stelle tritt die Faktenquote
    # (`fact_density_finding`); die Wortzahl bleibt als Obergrenze.
    findings += fact_density_finding(density, L)
    if words > BODY_WORDS_MAX:
        # Die Zahl, die zu streichen ist, gehoert in den Befund: der B6-Neuwurf
        # kuerzte von 3.091 auf 2.901 und blieb damit 101 Woerter darueber —
        # „kuerzen" ohne Betrag ist keine Vorgabe.
        findings.append(
            f"Fliesstext {words} Woerter — Obergrenze {BODY_WORDS_MAX}: "
            f"mindestens {words - BODY_WORDS_MAX} Woerter streichen "
            f"(Zielband {BODY_WORDS_MIN}-{BODY_WORDS_MAX}), ohne einen "
            f"Pflichtabschnitt oder einen Beleg zu verlieren.")
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
                    f"Option {i}: Pflichtfeld(er) fehlen oder tragen nur einen "
                    f"Platzhalter — " + ", ".join(f"'{m}'" for m in miss)
                    + ". Ein Feld mit \"keine Zahl\", \"unbekannt\", "
                      f"\"n/a\" oder aehnlichem gilt als NICHT erfuellt. "
                      f"Entweder eine belegte Groessenordnung (eine Spanne "
                      f"genuegt, auch eine grobe — mit Zitat im selben Satz), "
                      f"oder das Feld faellt ganz weg und der Optionstext sagt "
                      f"belegt, warum es sich nicht beziffern laesst.")
            # R7-1: KEIN Nennungszwang mehr. Eine Option ohne verwendbare
            # Messgroesse ist zulaessig — aber dann muss ein Beleg im Block
            # stehen, sonst haengt die Empfehlung an gar nichts.
            if not uses_measurement(block, measured or []) \
                    and not _has_citation(block):
                findings.append(
                    f"Option {i}: weder eine verwendbare gemessene Groesse noch "
                    f"ein Beleg. Entweder eine Zahl aus dem Messanhang, die "
                    f"die Option wirklich traegt"
                    + (f" (verwendbar: {', '.join(measured[:4])})" if measured
                       else "")
                    + ", oder ein Zitat im Optionsblock.")
        missing_sectors = uncovered_sectors(sections["options"], sectors or [])
        for name in missing_sectors:
            findings.append(
                f"Optionsabschnitt deckt '{name}' nicht ab — die Frage nennt "
                f"dieses Feld ausdruecklich; mindestens eine Option muss es "
                f"adressieren.")
    findings += calendar_findings(report_md, L, year_floor)
    findings += chain_findings(report_md, L)
    return findings


# --------------------------------------------------------------------------
# Beleg-Verifikation: steht die zitierte Zahl auch in der zitierten Seite?
# --------------------------------------------------------------------------

# Alle vier gefetchten Web-Arten. "entity" fehlte hier bis R7 — und genau
# darueber lief der letzte Falschbeleg der Jury: der Satz mit der TRIUMPH-4/
# TRANSCEND-Verwechslung zitierte zwei Quellen der zweiten Welle (kind
# "entity"), und die Beleg-Verifikation ueberging ihn deshalb VOLLSTAENDIG.
# Die zweite Welle liefert dieselben gefetchten Seiten wie der Web-Sweep; es
# gibt keinen Grund, sie ungeprueft zu lassen.
_VERIFIABLE_KINDS = ("web", "legal", "market", "entity")

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
    distorted: list[dict] = []
    misattributed: list[dict] = []
    for raw in split_claims(body):
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
        # Verdrehungspruefung (R6-4): richtige Zahl, umgedrehter Qualifizierer;
        # gleiche Sache, andere Groessenordnung; falsches Kategoriewort.
        for e in distortion_conflicts(claim, haystack):
            distorted.append({**e, "sentence": sentence,
                              "url": cited[0].get("url", "")})
        # Zuordnungspruefung (R7-3): richtige Seite, richtige Zahl, falsche
        # Studie. Ueber alle zitierten Seiten — erst wenn keine von ihnen die
        # Zahl im Umfeld der genannten Studie fuehrt, ist der Satz falsch
        # zugeordnet.
        for e in context_conflicts_multi(
                claim, [str(c.get("text") or "") for c in cited]):
            misattributed.append({**e, "sentence": sentence,
                                  "url": cited[0].get("url", "")})
    return {"checked": checked, "figures": figures, "unverified": bad,
            "subjects": subjects, "off_topic": off_topic,
            "distorted": distorted, "misattributed": misattributed}


_FIELD_LINE = re.compile(
    r"^\s{0,3}(?:[-*]\s*)?(?:\*\*)?\s*(?:" + "|".join(
        p for L in OPTION_FIELDS.values() for _k, p in L) + r")\s*(?:\*\*)?\s*[:：]",
    re.IGNORECASE)
# Trennzeichen, an denen ein Nebensatz endet — die Klausel-Streichung schneidet
# zwischen ihnen, nicht mitten im Satz.
_CLAUSE_SPLIT = re.compile(r"\s*(?:[;,]|—|–| - |\() ?")


def _strip_clause(sentence: str, token: str) -> str | None:
    """Nur die Teilaussage mit `token` aus einer Optionszeile schneiden.

    Warum nicht die ganze Zeile: eine Zeile „- Trigger: ..." IST ein
    Pflichtfeld. Im B6-Lauf nahm die mechanische Streichung der Option 2 ihren
    Zeithorizont, und der Befund stand hinterher im Gutachten. Bleibt nach dem
    Schnitt zu wenig stehen, gibt es None zurueck — dann faellt die Zeile doch."""
    if not _FIELD_LINE.match(sentence or ""):
        return None
    label_end = sentence.index(":") + 1
    head, rest = sentence[:label_end], sentence[label_end:]
    parts, marks = [], []
    last = 0
    for m in _CLAUSE_SPLIT.finditer(rest):
        parts.append(rest[last:m.start()])
        marks.append(m.group(0))
        last = m.end()
    parts.append(rest[last:])
    keep = [p for p in parts if token.lower() not in p.lower()]
    if len(keep) == len(parts) or not keep:
        return None
    out = head + (marks[0] if marks and not parts[0] else " ") + ", ".join(
        p.strip() for p in keep if p.strip())
    out = re.sub(r"\s{2,}", " ", out).rstrip(" ,;-").rstrip()
    # Bindewort, das jetzt am Anfang haengt ("Trigger: and France ...").
    out = re.sub(r"(:\s*)(?:and|but|und|aber|sowie|oder|or|which|die|das)\b\s*",
                 r"\1", out, count=1, flags=re.IGNORECASE)
    out = re.sub(r"(:\s*)([a-z])", lambda m: m.group(1) + m.group(2).upper(),
                 out, count=1)
    if len(re.findall(r"\S+", out[label_end:])) < 4:
        return None
    return out if out.endswith((".", "!", "?")) else out + "."


# --------------------------------------------------------------------------
# Rangregel fuer Kernzahlen (R8-2, jury_11.md/jury_12.md 2026-09-07)
# --------------------------------------------------------------------------
# Beide Gutachten schlagen an derselben Stelle zu: "fuer zentrale Marktzahlen
# stuetzt sich R wiederholt auf duenne Blogs statt Primaerquellen" — der
# Lilly-Quartalsumsatz ueber einen Broker-Blog (TIKR) statt SEC/IR, die
# Retatrutid-Werte ueber einen Bluttest-Anbieter (Lola Health) statt Lilly/AJMC,
# die Marktgroesse ueber ein Content-Portal (PeptideJournal), die EU-SPC-Frist
# ausgerechnet ueber einen Compounding-Anbieter (formblends.com).
#
# Die Regel: JEDE Praezisionszahl in den drei Kernabschnitten (Kurzfassung,
# Optionen, Katalysator-Kalender) braucht mindestens eine zitierte Quelle vom
# Rang 0 oder 1 — Behoerde, Register, Gericht, Firmen-IR/SEC, Fachjournal. Ist
# nur schwaecheres Material da, muss die Aussage als "secondary source only"
# gekennzeichnet werden oder verschwinden. Gekennzeichnet wird mechanisch:
# eine belegte Zahl mit ehrlichem Rangvermerk ist mehr wert als eine geloeschte.
#
# Der Rang steht als `rank` an der Quelle (scripts/corpus_research.catalog_rank);
# fehlt er, gilt 2 (etablierte Presse und Rest) — die Pruefung ist dann streng,
# nie stillschweigend nachsichtig.

PRIMARY_RANK = 1
CORE_SECTIONS = ("decision", "options", "next")
# R9-1 (jury_13.md 2026-09-07): die Rangregel galt bis R8 nur fuer ZAHLEN.
# Der komplette Patentkalender inklusive der Kernaussage „SPCs ... 2031-2032"
# hing damit an `formblends.com`, einem Compounding-Vermarkter — „2031" ist
# keine Praezisionszahl, also sah `weak_source_figures` den Satz nie. Ab jetzt
# gilt die Regel fuer jede AUSSAGE in der Kurzfassung, unter „Recht und
# Schutzrechte", im Terminkalender und in den Optionen.
CLAIM_SECTIONS = ("decision", "regip", "next", "options")
SECONDARY_MARK = {"en": "secondary source only",
                  "de": "nur sekundär belegt"}
_SECONDARY_RE = re.compile(
    r"secondary source only|only a secondary source|secondary sourcing only"
    r"|nur sekund(?:ä|ae)r belegt|nur eine sekund(?:ä|ae)re quelle",
    re.IGNORECASE)


def is_marked_secondary(text: str) -> bool:
    return bool(_SECONDARY_RE.search(text or ""))


def _section_sentences(report_md: str, lang: str,
                       keys: tuple[str, ...]) -> list[tuple[str, str]]:
    """(Abschnitts-Schluessel, Satz) fuer die genannten Abschnitte."""
    sections = split_sections(body_text(report_md), _lang(lang))
    out: list[tuple[str, str]] = []
    for key in keys:
        text = sections.get(key, "")
        if not text:
            continue
        for line in text.splitlines():
            # Tabellenzeilen des Kalenders sind je Zeile eine Aussage — der
            # Satz-Splitter zerlegt sie sonst an den Pipe-Zeichen vorbei.
            if line.strip().startswith("|"):
                out.append((key, line.strip()))
            else:
                out += [(key, c.strip()) for c in split_claims(line) if c.strip()]
    return out


def _core_sentences(report_md: str, lang: str) -> list[str]:
    return [s for _k, s in _section_sentences(report_md, lang, CORE_SECTIONS)]


# Ein Satz, der keine eigene Aussage traegt: Tabellen-Trennzeile, reine
# Aufzaehlungsmarke, Ueberschrift. Die Rangregel darf daran nicht haengen.
_EMPTY_CLAIM = re.compile(r"^[\s|:*#_-]*$")
MIN_CLAIM_WORDS = 4


def _source_index(sources: list[dict]) -> tuple[dict, dict]:
    by_id, by_url = {}, {}
    for s in sources or ():
        by_id[s.get("id")] = s
        if s.get("origin"):
            by_url.setdefault(s["origin"], s)
    for s in sources or ():
        by_url[s.get("url")] = s
    return by_id, by_url


def _is_primary(cited: list[dict]) -> bool:
    # Rang 0 ist falsy — `or 2` waere hier ein Fehler, der ausgerechnet
    # Behoerden und Register (Rang 0) als schwach gewertet haette.
    return any(int(2 if c.get("rank") is None else c["rank"]) <= PRIMARY_RANK
               for c in cited)


def weak_source_claims(report_md: str, sources: list[dict], lang: str = "en",
                       measured: str = "") -> list[dict]:
    """AUSSAGEN in den Kernabschnitten, die nur an Rang-2-Material haengen.

    R9-1: bis R8 pruefte die Regel nur Kernzahlen (`weak_source_figures`),
    und genau daran ging der Patentkalender der dreizehnten Jury durch — die
    SPC-Aussage „2031-2032" enthaelt keine Praezisionszahl. Geprueft wird jetzt
    jeder belegte Satz der Kurzfassung, des Rechtsabschnitts, des Kalenders und
    der Optionen.

    Rueckgabe wie `verify_cited_figures`: [{"sentence", "tokens", "kind",
    "detail", "url", "section"}] — derselbe Kanal (ein Neuwurf, danach
    mechanische Kennzeichnung bzw. Streichung in der Kurzfassung)."""
    by_id, by_url = _source_index(sources)
    out: list[dict] = []
    seen: set[str] = set()
    for key, sentence in _section_sentences(report_md, lang, CLAIM_SECTIONS):
        if sentence.startswith("#") or is_marked_secondary(sentence):
            continue
        if _EMPTY_CLAIM.match(sentence):
            continue
        cited = _cited_in(sentence, by_id, by_url)
        if not cited:
            continue                # ohne Beleg: das ist `sourceless_figures`
        if _is_primary(cited):
            continue
        if len(prose(sentence).split()) < MIN_CLAIM_WORDS:
            continue
        if sentence in seen:
            continue
        seen.add(sentence)
        figs = [f for f in precision_figures(sentence)
                if not _figure_in_measured(f, measured)]
        hosts = sorted({(c.get("host")
                         or (str(c.get("url") or "").split("/")[2]
                             if str(c.get("url") or "").count("/") > 2 else ""))
                        for c in cited} - {""})
        out.append({"sentence": sentence,
                    "tokens": figs or [prose(sentence).strip()[:60]],
                    "kind": "weaksource" if figs else "weakclaim",
                    "detail": ", ".join(hosts[:3]),
                    "url": cited[0].get("url", ""),
                    "section": key})
    return out


def weak_source_figures(report_md: str, sources: list[dict], lang: str = "en",
                        measured: str = "") -> list[dict]:
    """Nur der Zahlen-Teil von `weak_source_claims` (R8-2, unveraendert)."""
    return [e for e in weak_source_claims(report_md, sources, lang, measured)
            if e["kind"] == "weaksource"]


def mark_secondary(sentence: str, lang: str = "en") -> str:
    """Den Rangvermerk in den Satz setzen — vor dem Schlusszeichen."""
    mark = f" ({SECONDARY_MARK[_lang(lang)]})"
    if is_marked_secondary(sentence):
        return sentence
    body = sentence.rstrip()
    tail = sentence[len(body):]
    if body.endswith((".", "!", "?", "|")):
        return body[:-1].rstrip() + mark + body[-1] + tail
    return body + mark + tail


def drop_unverified(report_md: str, unverified: list[dict],
                    lang: str = "en") -> tuple[str, int]:
    """Saetze, deren Zahl in der zitierten Seite nicht steht, aus dem Bericht
    entfernen. Letzte Instanz nach dem einen Neuwurf — eine Zahl, die die
    zitierte Quelle nicht hergibt, darf nicht im Dokument stehen bleiben.

    Zwei Ausnahmen: eine gesperrte MESSGROESSE in einer Optionszeile kostet
    nicht die ganze Zeile (das waere ein fehlendes Pflichtfeld), sondern nur
    ihre Teilaussage. Und eine Kernaussage, die nur an einer Quelle vom Rang 2
    haengt (R8-2/R9-1), wird GEKENNZEICHNET statt geloescht: der Auftrag laesst
    beides zu, und eine belegte Aussage mit ehrlichem Rangvermerk ist fuer den
    Leser mehr wert als eine Luecke.

    AUSSER in der Kurzfassung: dort darf eine nur sekundaer belegte Aussage
    laut Auftrag (R9-1) nicht stehenbleiben — die drei Saetze, die eine
    Entscheidung tragen, sind entweder primaer belegt oder nicht da."""
    out, dropped = report_md, 0
    for e in unverified:
        s = e["sentence"]
        if not s or s not in out:
            continue
        if e.get("kind") in ("weaksource", "weakclaim"):
            if e.get("section") != "decision":
                marked = mark_secondary(s, lang)
                if marked != s:
                    out = out.replace(s, marked, 1)
                    dropped += 1
                continue
            # Kurzfassung: streichen (faellt in den allgemeinen Pfad unten).
        # Eine Optionszeile traegt ein Pflichtfeld: sie zu loeschen erzeugt
        # den naechsten Befund. Erst die Teilaussage kuerzen, nur wenn das
        # nicht geht, die Zeile ganz nehmen. Bis R8 galt das nur fuer
        # gesperrte Messgroessen — im B8-Lauf v1 kostete eine themenfremd
        # belegte Zeile Option 1 ihr "Against it" und Option 4 ihr "Risk".
        if e.get("kind") == "measure" or _FIELD_LINE.match(s):
            trimmed = _strip_clause(s, (e.get("tokens") or [""])[0])
            if trimmed:
                out = out.replace(s, trimmed, 1)
                dropped += 1
                continue
        if s in out:
            out = out.replace(s + " ", "", 1) if (s + " ") in out \
                else out.replace(s, "", 1)
            dropped += 1
    # Doppelte Leerzeichen/Leerzeilen, die durch die Streichung entstehen.
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out, dropped


# So viele Einzelbefunde nimmt der eine Neuwurf mit. Reihum ueber die
# Befundarten, nicht der Reihe nach: eine Liste, die mit zehn Zahlenbefunden
# beginnt, haette die Messgroessen-Befunde sonst nie erreicht.
MAX_REVISION_ITEMS = 14


def _spread_by_kind(entries: list[dict], cap: int) -> list[dict]:
    buckets: dict[str, list[dict]] = {}
    for e in entries or []:
        buckets.setdefault(e.get("kind", "figure"), []).append(e)
    out: list[dict] = []
    while len(out) < cap and any(buckets.values()):
        for kind in list(buckets):
            if buckets[kind] and len(out) < cap:
                out.append(buckets[kind].pop(0))
    return out


def needs_expansion(findings: list[str]) -> bool:
    """Verlangt einer der Befunde, den Text zu VERLAENGERN?

    Der Neuwurf sagte bis R8 pauschal „keine neuen Fakten, keine neuen Zahlen,
    keine neuen Zitate" — und bekam gleichzeitig den Auftrag, 689 Woerter
    belegte Fakten zu ergaenzen. Im B8-Lauf v1 hat das Modell daraufhin
    gekuerzt statt ergaenzt (1.511 -> 1.335). Ein Widerspruch im Auftrag ist
    kein Modellfehler."""
    return any("ERGAENZEN" in f for f in findings or ())


def revision_prompt(findings: list[str], cite_findings: list[dict],
                    lang: str = "en") -> str:
    """Der EINE gezielte Neuwurf. Kein Kritiker-Modell: der Text hier ist
    vollstaendig aus deterministischen Befunden erzeugt."""
    L = _lang(lang)
    expand = needs_expansion(findings)
    lines = list(findings)
    for e in _spread_by_kind(cite_findings, MAX_REVISION_ITEMS):
        toks = ", ".join(repr(t) for t in e["tokens"][:4])
        kind = e.get("kind", "figure")
        if kind == "subject":
            lines.append(
                f"Die zitierte Seite ({e['url'][:80]}) handelt NICHT von "
                f"{toks} — der Beleg traegt diese Aussage nicht. Satz mit einem "
                f"passenden Beleg neu schreiben oder streichen: "
                f"\"{e['sentence'][:180]}\"")
        elif kind == "reach":
            lines.append(
                f"Der Satz beruft sich auf ein {toks}, das die zitierte Seite "
                f"({e['url'][:80]}) nicht fuehrt — {e.get('detail', '')}. "
                f"Entweder eine Quelle zitieren, die dieses Verzeichnis "
                f"wirklich enthaelt, oder die Aussage auf das zuruecknehmen, "
                f"was die Seite sagt: \"{e['sentence'][:180]}\"")
        elif kind in ("qualifier", "magnitude", "category"):
            what = {"qualifier": "Der Qualifizierer ist umgedreht",
                    "magnitude": "Die Groessenordnung stimmt nicht",
                    "category": "Das Kategoriewort ist falsch"}[kind]
            lines.append(
                f"{what}: {toks} — {e.get('detail', '')} "
                f"({e['url'][:80]}). Satz woertlich nach der Quelle neu "
                f"schreiben oder streichen: \"{e['sentence'][:180]}\"")
        elif kind == "measure":
            lines.append(
                f"Gemessene Groesse nicht verwendbar: {toks} — "
                f"{e.get('detail', '')}. Diese Zahl darf im Bericht NICHT "
                f"stehen (besser keine Zahl als eine, die nicht traegt). Satz "
                f"ohne sie neu schreiben — die Begruendung dann aus einem "
                f"Beleg ziehen: \"{e['sentence'][:180]}\"")
        elif kind == "context":
            lines.append(
                f"Falsche Zuordnung innerhalb der Quelle: {toks} steht auf "
                f"{e['url'][:80]} NICHT im Umfeld von "
                f"{e.get('detail', '')}. Satz der Quelle entsprechend neu "
                f"zuordnen oder streichen: \"{e['sentence'][:180]}\"")
        elif kind == "weaksource":
            lines.append(
                f"Kernzahl nur schwach belegt: {toks} steht in der "
                f"Kurzfassung, einer Option oder im Kalender, haengt aber nur "
                f"an Rang-2-Material ({e.get('detail', '')}). Eine Zahl an "
                f"dieser Stelle braucht eine Quelle vom Rang 0/1 — Behoerde, "
                f"Register, Gericht, Firmen-IR/SEC oder Fachjournal, im "
                f"Katalog mit (primary) markiert. Entweder eine solche Quelle "
                f"aus dem Katalog zitieren, oder den Satz mit dem Zusatz "
                f"\"{SECONDARY_MARK[L]}\" kennzeichnen, oder die Zahl "
                f"streichen: \"{e['sentence'][:180]}\"")
        elif kind == "weakclaim":
            where = ("in der Kurzfassung" if e.get("section") == "decision"
                     else "in einem Kernabschnitt")
            way_out = ("Die Kurzfassung traegt NUR primaer belegte Aussagen — "
                       "eine Kennzeichnung reicht dort nicht, der Satz muss "
                       "primaer belegt oder weg sein."
                       if e.get("section") == "decision" else
                       f"Entweder eine solche Quelle aus dem Katalog zitieren, "
                       f"oder den Satz mit dem Zusatz \"{SECONDARY_MARK[L]}\" "
                       f"kennzeichnen, oder die Aussage streichen.")
            lines.append(
                f"Aussage {where} nur schwach belegt: sie haengt allein an "
                f"Rang-2-Material ({e.get('detail', '')}). Eine Aussage an "
                f"dieser Stelle braucht eine Quelle vom Rang 0/1 — Behoerde, "
                f"Register, Gericht, Firmen-IR/SEC, Fachjournal oder eine "
                f"Fachpublikation einer Patentkanzlei, im Katalog mit "
                f"(primary) markiert. {way_out} "
                f"Betroffen: \"{e['sentence'][:180]}\"")
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
        rule = ("Alles andere bleibt inhaltlich, wie es ist: keine neuen "
                "Fakten, keine neuen Zahlen, keine neuen Zitate — nur die "
                "vorhandenen Katalog-IDs.")
        if expand:
            rule = ("Ein Befund verlangt ausdrücklich, den Bericht zu "
                    "VERLÄNGERN. Dafür — und nur dafür — darfst du weitere "
                    "belegte Fakten aus dem unten mitgelieferten Material "
                    "aufnehmen: jede Ergänzung mit Datum, benanntem Akteur "
                    "oder Zahl UND Katalog-Zitat im selben Satz. Der neue "
                    "Bericht muss LÄNGER sein als der vorige; kürze nichts, "
                    "was bereits belegt dasteht. Sonst gilt: keine neuen "
                    "Zahlen ohne Beleg, nur vorhandene Katalog-IDs.")
        return (
            "ÜBERARBEITUNG — das ist der einzige Korrekturdurchgang.\n\n"
            "Eine mechanische Prüfung des eben geschriebenen Berichts hat "
            "folgende Punkte gefunden:\n\n" + numbered + "\n\n"
            "Schreibe den VOLLSTÄNDIGEN Bericht neu und behebe genau diese "
            "Punkte. " + rule + " Gliederung und Zitierweise unverändert.")
    rule = ("Everything else stays as it is in substance: no new facts, no new "
            "figures, no new citations — only catalog ids that already appear.")
    if expand:
        rule = ("One finding explicitly asks you to LENGTHEN the report. For "
                "that purpose — and only that — you may take further "
                "evidenced facts from the material supplied below: every "
                "addition carries a date, a named actor or a figure AND a "
                "catalog citation in the same sentence. The new report must be "
                "LONGER than the previous one; do not cut anything that "
                "already stands supported. Otherwise: no figure without a "
                "citation, and only catalog ids.")
    return (
        "REVISION — this is the only correction pass.\n\n"
        "A mechanical check of the report you just wrote found the following:\n\n"
        + numbered + "\n\n"
        "Rewrite the COMPLETE report and fix exactly these points. " + rule
        + " Keep the mandated outline and the citation form unchanged.")


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
time other permitted against regarding
what who which where how why our their its it is are was were has have had
key core main major minor overall further given based note noted see
marketing authorisation authorization revenue revenues quarterly pipeline
rollout reimbursement coverage sales launch launches funding investment
consumer consumers patient patients product products treatment therapy
""".split())

# Verbformen, die am Satz- oder Zellenanfang wie ein Eigenname aussehen:
# "Confirms", "Expands Mounjaro's label", "Adds ...", "Regarding", "Permitted",
# "Missing". Neun solcher Fehlalarme in drei Laeufen (B6: 3 Streichungen,
# B7: 2, B8-v1: 3) — sie kosteten zuletzt zwei Pflichtfelder einer Option und
# zwei Zeilen des Katalysator-Kalenders. Geprueft wird NUR das erste Wort einer
# Fundstelle, die am Anfang eines Satzes oder einer Tabellenzelle steht: dort
# ist die Grossschreibung erzwungen und traegt keine Information.
_VERBISH = re.compile(r"^[A-Z][a-z]{2,}(?:s|es|ed|ing)$")

_CAP_TOKEN = re.compile(r"[A-Z][A-Za-z0-9&./'’-]*")
_LOWER_TOKEN = re.compile(r"\b[a-z][a-z-]{6,}\b")
# Verbindungswoerter INNERHALB eines Eigennamens ("Bank of England",
# "Novo Nordisk A/S") — nur wenn links UND rechts ein Grossbuchstabenwort steht.
_NAME_GLUE = frozenset("of and & de la van der von den du el al".split())
MAX_SUBJECTS = 8


def _inn_like(word: str) -> bool:
    return len(word) >= 8 and word.endswith(_INN_SUFFIX)


def _at_start(text: str, pos: int) -> bool:
    """Steht die Fundstelle am Anfang eines Satzes, einer Zeile, eines
    Listenpunkts oder einer Tabellenzelle?"""
    left = (text or "")[:pos]
    return not left.strip("| \t-*•") or bool(
        re.search(r"(?:^|[.!?:;|\n])\s*[-*•]?\s*(?:\*\*)?\s*$", left))


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
        # Am Anfang eines Satzes oder einer Tabellenzelle ist die
        # Grossschreibung erzwungen — ein fuehrendes Verb faellt weg, der Rest
        # der Fundstelle bleibt ("Expands Mounjaro's" -> "Mounjaro's").
        if clean and _VERBISH.match(clean[0]) and _at_start(text, toks[i].start()):
            clean = clean[1:]
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


# --------------------------------------------------------------------------
# Verdrehte Wiedergabe (R6-4, jury_7.md/jury_8.md 2026-09-07)
# --------------------------------------------------------------------------
# Drei Faktenfehler fanden die Stichproben, und KEINEN davon konnte die
# bestehende Beleg-Verifikation sehen, weil alle drei Zahlen bzw. Woerter
# benutzen, die auf der zitierten Seite vorkommen:
#
#   Q  Quelle: "we estimate that AT LEAST 2% of adults are currently using
#      them"  ->  Bericht: "ONLY APPROXIMATELY 2% of European and UK adults".
#      Aus einer Untergrenze wird eine beruhigende Obergrenze; die Zahl selbst
#      stimmt, also schwieg die Zahlenpruefung.
#   M  Quelle: "More than 2 million prescriptions"  ->  Bericht: "over 5
#      million cumulative US prescriptions". Die "5" steht irgendwo auf jeder
#      langen Seite, also galt sie als belegt.
#   K  EMA: Liraglutide STADA ist ein HYBRIDARZNEIMITTEL ("in Victoza the
#      active substance is made using living cells, whereas in Liraglutide
#      STADA it is made using chemical processes")  ->  Bericht: "a GENERIC
#      version of liraglutide". Ein Kategoriewort, keine Zahl.
#
# Alle drei laufen durch denselben Kanal wie die Zahlenpruefung: ein Neuwurf,
# danach mechanische Streichung.

# Zahl MIT Groessenangabe — Jahreszahlen und blanke Stueckzahlen bleiben
# aussen vor, dort waere die Falsch-Ablehnung wahrscheinlicher als der Fund.
_QTY_RE = re.compile(
    r"(?<![\w.,])(?P<sym>[$€£]\s?)?(?P<num>\d[\d.,\u00b7]*)\s*"
    r"(?P<scale>%|percent|bn|billion|million|trillion|thousand|k|Mrd\.?|Mio\.?)"
    r"(?![a-z])", re.IGNORECASE)

_SCALE_FACTORS = {"bn": 1e9, "billion": 1e9, "mrd": 1e9, "mrd.": 1e9,
                  "million": 1e6, "mio": 1e6, "mio.": 1e6,
                  "trillion": 1e12, "thousand": 1e3, "k": 1e3}

# Der Blick vor die Zahl: so weit reicht die Qualifizierer-Suche.
QUALIFIER_WINDOW = 45

# Drei Klassen, nicht zwei: "around 2%" ist eine Naeherung, "only 2%" eine
# Verkleinerung. Die ING-Seite traegt BEIDES ("Around 2% of European adults"
# und "we estimate that at least 2%") — nur die Verkleinerung im Bericht ist
# die Verdrehung, die jury_7.md gefunden hat.
_QUALIFIER_MIN = ("at least", "no less than", "no fewer than", "more than",
                  "in excess of", "upwards of", "over", "above",
                  "mindestens", "mehr als", "ueber", "über")
_QUALIFIER_CAP = ("only", "just", "merely", "no more than", "fewer than",
                  "less than", "up to", "at most", "nur", "lediglich",
                  "höchstens", "weniger als", "bis zu")
_QUALIFIER_APPROX = ("approximately", "about", "roughly", "around", "nearly",
                     "almost", "some", "etwa", "rund", "knapp", "ungefähr",
                     "circa", "ca.")

# Sich gegenseitig ausschliessende Kategoriewoerter. Eine Seite, die ein
# ANDERES Wort derselben Menge benutzt und das des Satzes NICHT kennt,
# widerspricht dem Satz. Bewusst klein gehalten und erweiterbar.
CATEGORY_SETS: tuple[tuple[str, ...], ...] = (
    ("generic", "hybrid", "biosimilar", "originator"),
)

_QTY_STOP = frozenset("""
of in on at to by for from with and or the a an that this these those is are
was were has have had been being will would could should may might do does
did its their his her our your it he she they we you i as than then so such
""".split())


def _qty_value(m: re.Match) -> float | None:
    raw = (m.group("num") or "").replace(",", "").replace("\u00b7", ".")
    # "1.234" (deutsche Tausender) vs "1.2" (Dezimal): drei Nachkommastellen
    # sind ein Tausenderpunkt, alles andere ein Dezimaltrenner.
    if raw.count(".") == 1 and len(raw.split(".")[1]) == 3:
        raw = raw.replace(".", "")
    try:
        v = float(raw)
    except ValueError:
        return None
    scale = (m.group("scale") or "").lower().rstrip(".")
    if scale in ("%", "percent"):
        return v
    return v * _SCALE_FACTORS.get(scale, _SCALE_FACTORS.get(scale + ".", 1.0))


def _qty_unit(m: re.Match) -> str:
    return "%" if (m.group("scale") or "").lower() in ("%", "percent") else "n"


def _qty_nouns(text: str, end: int, cap: int = 4) -> set[str]:
    """Die Inhaltswoerter direkt hinter der Zahl — WORUEBER sie etwas sagt."""
    out: set[str] = set()
    for w in re.findall(r"[A-Za-z][A-Za-z-]{2,}", text[end:end + 90]):
        low = w.lower()
        if low in _QTY_STOP or low in _SUBJECT_STOP:
            continue
        out.add(low)
        if len(out) >= cap:
            break
    return out


def _qualifier_class(prefix: str) -> str | None:
    """'min' = Untergrenze, 'cap' = Verkleinerung/Obergrenze, 'approx' =
    Naeherung. Die Verkleinerung schlaegt die Naeherung ("only approximately"
    ist eine Verkleinerung), die Naeherung schlaegt nichts."""
    low = prefix.lower()[-QUALIFIER_WINDOW:]

    def ends_with(words) -> re.Match | None:
        for p in words:
            m = re.search(rf"(?:^|\W)({re.escape(p)})\W*$", low)
            if m:
                return m
        return None

    # Naeherungswoerter direkt vor der Zahl abschaelen: "only approximately 2%"
    # ist eine Verkleinerung, keine Naeherung — das Wort davor entscheidet.
    approx = False
    while (m := ends_with(_QUALIFIER_APPROX)) is not None:
        approx = True
        low = low[:m.start(1)]
    if ends_with(_QUALIFIER_CAP):
        return "cap"
    if ends_with(_QUALIFIER_MIN):
        return "min"
    return "approx" if approx else None


# Was der Bericht sagen darf, wenn die Seite eine bestimmte Klasse fuehrt:
# {Klasse im Bericht: Klassen auf der Seite, die den Satz widerlegen}
_QUALIFIER_CONFLICT = {"cap": {"min"}, "min": {"cap", "approx"},
                       "approx": {"min"}}


def qualifier_conflicts(sentence: str, page: str) -> list[dict]:
    """Dieselbe Zahl, umgedrehter Qualifizierer.

    Steht sie auf der Seite als Untergrenze ("at least 2%") und im Satz als
    Ober-/Naeherungsgrenze ("only approximately 2%") — oder umgekehrt —, gibt
    die Seite den Satz nicht her, obwohl die Zahl stimmt."""
    claim = prose(sentence or "")
    out: list[dict] = []
    page_q = list(_QTY_RE.finditer(page or ""))
    for m in _QTY_RE.finditer(claim):
        cls = _qualifier_class(claim[:m.start()])
        if cls is None:
            continue
        val, unit = _qty_value(m), _qty_unit(m)
        if val is None:
            continue
        classes = set()
        for pm in page_q:
            if _qty_unit(pm) != unit or _qty_value(pm) != val:
                continue
            pc = _qualifier_class(page[:pm.start()])
            if pc:
                classes.add(pc)
        # Widerlegt ist der Satz nur, wenn die Seite die GEGENKLASSE fuehrt
        # und seine eigene Klasse nirgends. Eine Seite, die beides schreibt,
        # traegt beides.
        bad = _QUALIFIER_CONFLICT[cls] & classes
        if bad and cls not in classes:
            names = {"min": "eine Untergrenze", "cap": "eine Verkleinerung",
                     "approx": "eine Näherung"}
            out.append({"tokens": [m.group(0).strip()], "kind": "qualifier",
                        "detail": f"die Seite schreibt "
                                  f"{names[sorted(bad)[0]]}, der Satz "
                                  f"{names[cls]}"})
    return out


def magnitude_conflicts(sentence: str, page: str,
                        tolerance: float = 0.25) -> list[dict]:
    """Dieselbe Groesse, andere Groessenordnung.

    Verglichen wird nur, wenn die Seite dieselbe Sache beziffert (gemeinsames
    Inhaltswort hinter der Zahl). Weicht der Satz von JEDEM solchen Quellwert
    um mehr als `tolerance` ab, traegt die Seite ihn nicht."""
    claim = prose(sentence or "")
    page_q = [(pm, _qty_value(pm), _qty_unit(pm), _qty_nouns(page, pm.end()))
              for pm in _QTY_RE.finditer(page or "")]
    out: list[dict] = []
    for m in _QTY_RE.finditer(claim):
        val, unit = _qty_value(m), _qty_unit(m)
        nouns = _qty_nouns(claim, m.end())
        if val is None or not nouns:
            continue
        # Steht GENAU dieser Wert mit derselben Einheit irgendwo auf der Seite,
        # ist die Groessenordnung nicht das Problem — dann greift, wenn
        # ueberhaupt, die Qualifizierer-Pruefung. Ohne diese Bremse meldete die
        # Regel im R5-Nachtest "12 % Adoption in den USA" als falsch, weil auf
        # derselben Seite auch "weniger als 1 % global" steht.
        if any(pv == val and pu == unit for _pm, pv, pu, _pn in page_q):
            continue
        cands = [(pv, pn) for _pm, pv, pu, pn in page_q
                 if pv is not None and pu == unit and (pn & nouns)]
        if not cands:
            continue
        if any(abs(val - pv) <= tolerance * max(abs(pv), 1e-9)
               for pv, _pn in cands):
            continue
        near = min(cands, key=lambda c: abs(val - c[0]))[0]
        out.append({"tokens": [m.group(0).strip()], "kind": "magnitude",
                    "detail": f"die Seite beziffert dieselbe Sache mit "
                              f"{near:g}, der Satz mit {val:g}"})
    return out


def category_conflicts(sentence: str, page: str) -> list[dict]:
    """Falsches Kategoriewort: der Satz nennt eine Kategorie, die Seite eine
    andere derselben Menge — und die des Satzes gar nicht."""
    claim = prose(sentence or "").lower()
    low = (page or "").lower()
    out: list[dict] = []
    for group in CATEGORY_SETS:
        in_claim = [w for w in group
                    if re.search(rf"\b{re.escape(w)}s?\b", claim)]
        in_page = [w for w in group if re.search(rf"\b{re.escape(w)}s?\b", low)]
        for w in in_claim:
            others = [x for x in in_page if x != w]
            if others and w not in in_page:
                out.append({"tokens": [w], "kind": "category",
                            "detail": f"die Seite spricht von "
                                      f"{', '.join(others)}, nicht von {w!r}"})
    return out


# --------------------------------------------------------------------------
# Zuordnung INNERHALB einer Quelle (R7-3, jury_9.md 2026-09-07)
# --------------------------------------------------------------------------
# Der letzte verbliebene Falschbeleg der neunten Jury: „28.7% weight loss plus
# 75% pain reduction at 12 mg/68 weeks in the TRANSCEND-T2D-2 trial" — die
# zitierte Seite fuehrt diese Werte unter TRIUMPH-4 (Kniearthrose), waehrend
# TRANSCEND-T2D-2 dort ohne Wirksamkeitsdaten steht. Richtige Seite, richtige
# Zahl, falsche Studie.
#
# Alle bisherigen Pruefungen mussten das durchlassen: `unverified_tokens` fragt
# nur, OB die Zahl auf der Seite steht, `unverified_subjects` nur, OB der Name
# auf der Seite steht. Beides war der Fall. Was fehlte, ist die Naehe:
#
#   Nennt ein Satz den Eigennamen einer Studie/eines Programms/einer Zulassung,
#   muessen die Zahlen des Satzes im Umfeld dieser Nennung stehen
#   (+/- NAME_CONTEXT_CHARS Zeichen), nicht irgendwo auf der Seite.
#
# Ausgeloest wird nur auf Seiten, die MEHRERE solche Namen fuehren — auf einer
# Seite ueber genau eine Studie waere ein entfernter Tabellenwert kein Fund,
# sondern ein Fehlalarm. Erkannt werden Namen in der ueblichen Versalform mit
# optionalem Ziffernsuffix: TRIUMPH-4, TRANSCEND-T2D-2, SURMOUNT-1, ATTAIN.

NAME_CONTEXT_CHARS = 400
MIN_SCOPES_ON_PAGE = 2

_SCOPE_NAME = re.compile(r"\b[A-Z][A-Z0-9]{3,}(?:-[A-Za-z0-9]{1,6}){0,3}\b")

# Versalwoerter, die keine Studie/kein Programm benennen: Behoerden, Register,
# Kennzahlen, Rechtsbegriffe. Ohne sie waere "NICE recommends 12%" ein Fund.
SCOPE_STOP = frozenset("""
NICE NHS MHRA EMA FDA WHO EFSA ECHA EPO USPTO WIPO DPMA CNIPA PMDA NMPA TGA
OECD IQVIA SEC CMS NIH NSF CDC HTA GBA IGES AIFA HAS ANSM BFARM
CAGR EBIT EBITDA GAAP IFRS ROI CAPEX OPEX YOY QOQ USD EUR GBP CHF JPY CNY
SPC EPO2000 IPRP CIPO PCT TRIPS GDPR FTO NDA BLA IND ANDA MAA CHMP PRAC
DTC B2B B2C SKU CPG FMCG SME KPI HTML JSON PDF API CEO CFO COO CTO
GLP1 GLP2 GIP DPP4 SGLT2 BMI HDL LDL RCT ITT
MONDAY TUESDAY WEDNESDAY THURSDAY FRIDAY SATURDAY SUNDAY
JANUARY FEBRUARY MARCH APRIL JUNE JULY AUGUST SEPTEMBER OCTOBER NOVEMBER
DECEMBER
""".split())


def scope_names(text: str) -> list[str]:
    """Eigennamen von Studien/Programmen/Zulassungen in der Versalform."""
    out, seen = [], set()
    for m in _SCOPE_NAME.finditer(text or ""):
        name = m.group(0)
        if name.upper().replace("-", "") in SCOPE_STOP or name.upper() in SCOPE_STOP:
            continue
        head = name.split("-")[0].upper()
        if head in SCOPE_STOP:
            continue
        if name.lower() not in seen:
            seen.add(name.lower())
            out.append(name)
    return out


def _windows(page: str, names: list[str], width: int) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    for n in names:
        for m in re.finditer(re.escape(n), page or "", re.IGNORECASE):
            spans.append((max(0, m.start() - width), m.end() + width))
    return spans


def _judge_context(sentence: str, page: str, width: int) -> tuple[set, set, list]:
    """(Zahlen, die diese Seite beurteilen kann; davon die falsch zugeordneten;
    die im Satz genannten Studien, die die Seite kennt).

    Beurteilen kann eine Seite eine Zahl nur, wenn sie eine der im Satz
    genannten Studien fuehrt, mehrere Studien kennt (sonst kein
    Verwechslungsrisiko) und die Zahl ueberhaupt traegt."""
    page = page or ""
    claim = prose(sentence or "")
    named = [n for n in scope_names(claim)
             if re.search(re.escape(n), page, re.IGNORECASE)]
    if not named:
        return set(), set(), []
    if len({n.split("-")[0].upper() for n in scope_names(page)}) < MIN_SCOPES_ON_PAGE:
        return set(), set(), []      # Seite handelt von genau einem Gegenstand
    spans = _windows(page, named, width)
    judged, bad = set(), set()
    for fig in precision_figures(claim):
        hits = list(re.finditer(re.escape(fig), page, re.IGNORECASE))
        if not hits:
            continue                 # gar nicht auf der Seite -> Zahlenpruefung
        judged.add(fig)
        if not any(a <= h.start() <= b for h in hits for a, b in spans):
            bad.add(fig)
    return judged, bad, named


def context_conflicts(sentence: str, page: str,
                      width: int = NAME_CONTEXT_CHARS) -> list[dict]:
    """Zahlen, die auf der Seite stehen — aber nicht bei der Studie, die der
    Satz nennt.

    Leere Liste heisst: keine benannte Studie im Satz, nur eine auf der Seite,
    oder jede Zahl steht im Umfeld ihrer Nennung."""
    _judged, bad, named = _judge_context(sentence, page, width)
    return [{"tokens": [fig], "kind": "context", "detail": ", ".join(named[:3])}
            for fig in precision_figures(prose(sentence or "")) if fig in bad]


def context_conflicts_multi(sentence: str, pages: list[str],
                            width: int = NAME_CONTEXT_CHARS) -> list[dict]:
    """Dasselbe ueber mehrere zitierte Seiten.

    Ein Satz mit zwei Belegen ist erst dann falsch zugeordnet, wenn JEDE Seite,
    die die Zahl beurteilen kann, sie ausserhalb des Studien-Kontexts fuehrt —
    sonst traegt der andere Beleg den Satz. Genau so stand der Jury-Fall im
    Dossier: zwei Wiki-Seiten, dieselbe falsche Studie."""
    judged_any: dict[str, int] = {}
    bad_all: dict[str, int] = {}
    names: list[str] = []
    for page in pages or []:
        judged, bad, named = _judge_context(sentence, page, width)
        for fig in judged:
            judged_any[fig] = judged_any.get(fig, 0) + 1
        for fig in bad:
            bad_all[fig] = bad_all.get(fig, 0) + 1
        for n in named:
            if n not in names:
                names.append(n)
    out = []
    for fig in precision_figures(prose(sentence or "")):
        if judged_any.get(fig) and bad_all.get(fig) == judged_any[fig]:
            out.append({"tokens": [fig], "kind": "context",
                        "detail": ", ".join(names[:3])})
    return out


# --------------------------------------------------------------------------
# Reichweite der Quelle (R8-3, jury_11.md §4.3, 2026-09-07)
# --------------------------------------------------------------------------
# „Nicht getragene Registeraussage: 'The EFSA register of authorized health
# claims does not include any claims specifically referencing GLP-1 use' — die
# verlinkte Seite enthaelt kein Register." Derselbe Fehler wie bei der Messung,
# nur auf der Belegseite: der Satz beruft sich auf ein formales Nachweisstueck,
# das die zitierte Seite gar nicht fuehrt.
#
# Geprueft wird eng: nur Woerter, die ausdruecklich ein amtliches Verzeichnis
# oder eine Entscheidungssammlung benennen. Die Seitenseite ist bewusst
# grosszuegiger als die Satzseite (Wortstamm statt Vollform) — wir wollen den
# Fehlalarm vermeiden, nicht den Fund erzwingen.
EVIDENCE_ARTEFACTS: dict[str, tuple[str, str]] = {
    # Name: (Muster im SATZ, Muster auf der SEITE)
    "register": (r"\bregist(?:er|ers|ry|ries)\b", r"regist"),
    "database": (r"\b(?:database|datenbank)\b", r"database|datenbank"),
    "docket": (r"\bdocket\b", r"docket"),
    "gazette": (r"\b(?:gazette|amtsblatt)\b", r"gazette|amtsblatt"),
    "official journal": (r"\bofficial journal\b", r"official journal"),
    "case law": (r"\b(?:case law|rechtsprechung)\b", r"case law|rechtsprechung"),
}


def artefact_conflicts(sentence: str, page: str) -> list[dict]:
    """Formale Nachweisstuecke, auf die sich der Satz beruft, die die zitierte
    Seite aber nicht fuehrt."""
    out = []
    for name, (claim_pat, page_pat) in EVIDENCE_ARTEFACTS.items():
        if not re.search(claim_pat, sentence or "", re.IGNORECASE):
            continue
        if re.search(page_pat, page or "", re.IGNORECASE):
            continue
        out.append({"tokens": [name], "kind": "reach",
                    "detail": f"the cited page carries no {name}"})
    return out


def distortion_conflicts(sentence: str, page: str) -> list[dict]:
    """Alle Verdrehungs- und Reichweitenpruefungen ueber einen Satz."""
    return (qualifier_conflicts(sentence, page)
            + magnitude_conflicts(sentence, page)
            + category_conflicts(sentence, page)
            + artefact_conflicts(sentence, page))


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
    for raw in split_claims(body_text(report_md)):
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
