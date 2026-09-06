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

from pipeline.grounding import _concrete_tokens, ungrounded_specifics

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

# Schnittmarken der code-generierten Anhaenge. Textgleich zu
# pipeline/dossier_check.py zu halten (dort dieselbe Aufgabe nach dem Lauf).
_APPENDIX_HEADINGS = (
    "## Research coverage (auto-generated)",
    "## Recherche-Abdeckung (automatisch erzeugt)",
    "\n## Sources\n", "\n## Quellen\n",
)
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


def structure_findings(report_md: str, lang: str = "en") -> list[str]:
    """Was am fertigen Bericht mechanisch nicht stimmt. Leere Liste = sauber."""
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
    return findings


# --------------------------------------------------------------------------
# Beleg-Verifikation: steht die zitierte Zahl auch in der zitierten Seite?
# --------------------------------------------------------------------------

_VERIFIABLE_KINDS = ("web", "legal")

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
    checked = figures = 0
    bad: list[dict] = []
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
            bad.append({"sentence": sentence, "tokens": tokens,
                        "url": cited[0].get("url", "")})
    return {"checked": checked, "figures": figures, "unverified": bad}


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
    for e in cite_findings[:8]:
        toks = ", ".join(repr(t) for t in e["tokens"][:4])
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
