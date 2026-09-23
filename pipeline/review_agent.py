"""Review-Agent (Test, 2026-09-22): prueft die vom Grounding-Gate gehaltenen
Drafts auf AEQUIVALENZ statt auf Wortgleichheit.

Owner-Befund 22.09.: die meisten Holds „Zahl/Jahr/Betrag nicht in der Quelle"
sind keine Erfindungen, sondern andere Ausdrucksformen derselben Angabe —
„1 000 kilometres" gegen „1,000", „23 heures" gegen „11:00 PM", „31. März 2027"
gegen „March 31, 2027", „1980er" gegen „1980s", „zweites Halbjahr 2027" gegen
„vor Anfang 2028", Zahlwort gegen Ziffer. Das Gate vergleicht Token, ein Mensch
vergleicht Bedeutung. Dieser Agent macht den Bedeutungsvergleich — mit einem
harten Beleg-Zwang, damit er nicht selbst erfindet:

  1. Fuer jede vom Gate beanstandete Zahl bekommt das lokale Modell den Satz
     des Artikels und den Quelltext und muss antworten, ob die Quelle dieselbe
     Angabe macht — und ein WOERTLICHES Zitat aus der Quelle liefern.
  2. Das Zitat wird gegen die Quelle geprueft (whitespace-/case-normalisiert).
     Fehlt es dort, zaehlt die Antwort als „nicht belegt", egal was das Modell
     behauptet. Das Modell kann also nur bestaetigen, was wirklich dasteht.
  3. Ein Draft gilt als „aequivalent", wenn JEDE beanstandete Zahl so belegt ist.

**Namens-Holds (Erweiterung 22.09., Owner-Befund):** dieselbe Mechanik, aber die
Entscheidung faellt deterministisch an den Namensteilen; das Modell liefert
Beleg, Quellform und ein Veto. Titelwoerter gehoeren nicht zur Identitaet
(„Chinese Vice Premier He Lifeng" gegen „Vize-Ministerpraesident He Lifeng"),
der Nachname muss als eigenes Wort in der Quelle stehen, Vorname/Titel duerfen
einen Tippfehler Abstand haben (Quelle „Urlula", Artikel „Ursula"). Klassen:

  named               alle Namensteile in der Quelle -> veroeffentlichbar
  translit_confirmed  andere Schrift; ein ZWEITER, BLINDER Durchgang romanisiert
                      nur die Quellform (ohne den Artikelnamen zu sehen) und
                      trifft den Nachnamen -> veroeffentlichbar
  surname_only        Quelle nennt nur den Nachnamen, Artikel ergaenzt den Vornamen
  role_only           Quelle nennt nur eine Rolle („the Foreign Secretary"), der
                      Name stammt aus dem Modellwissen — der gefaehrlichste Fall:
                      ein gewechselter Amtstraeger waere eine falsche Zuschreibung
  absent              Person kommt in der Quelle nicht vor
  misspelled          Nachname weicht von der Quelle ab (Defekt des Artikels)
  translit            Romanisierung passt nicht zum Artikelnamen

Gemessen am Bestand 22.09. (65 Namen in 83 gehaltenen Drafts): 16 waren nur eine
andere Schrift (ukrainische, japanische, chinesische Quellen), 17 ein ergaenzter
Vorname, 16 gar nicht in der Quelle, 6 falsch geschrieben, 4 aus der Rolle
erfunden. Der Fall „Quelle nennt den Nestle-Chef Філіп Навратіль, der Artikel
schrieb Mark Schneider" faellt dabei auf — genau das, was der blinde zweite
Durchgang leisten soll.

**Reparatur (Stufe 1, 22.09. abends):** einen Befund korrigiert der Agent selbst —
den ergaenzten Vornamen. Die Quellform ersetzt den Artikelnamen im ganzen Body,
danach laufen DIESELBEN Gates wie beim Auto-Publish (Namen, Zahlen, Garbage,
Laenge, Vollstaendigkeit); nur wenn alle gruen sind, gilt die Reparatur. Geglaubt
wird ihr nichts, sie wird nachgemessen. Schutzregeln: die Quellform muss
namensfoermig sein (kein Repo-Handle „arnegiacomo") und den Nachnamen behalten
(kein „Dario Amodei" -> „Dario"). Alles andere — abweichende Schreibweisen,
Saetze mit ungedeckter Zahl oder Person — steht als `proposals` im Bericht und
bleibt beim Menschen.

Default ist Dry-Run: Bericht nach data/review_agent_last.json und Tabelle.
`--apply` veroeffentlicht die aequivalenten Drafts mit
review_reason='agent:equivalent …' — durch dieselben uebrigen Gates wie
Auto-Publish (Garbage, Truncation, Dedup laufen dort ohnehin vorher).
Kein Reject: was nicht belegt ist, bleibt in der Warteschlange.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field

from pipeline.config import DATA_DIR

logger = logging.getLogger(__name__)

REPORT_PATH = Path(DATA_DIR) / "review_agent_last.json"
SOURCE_MAX_CHARS = 9000
CONFIDENCE_MIN = 0.85
MIN_BODY_WORDS = 60          # dieselbe Untergrenze wie der Garbage-Guard

SYSTEM = (
    "You verify whether a figure in a short article is supported by its source text. "
    "The source may be in another language and may express the same figure differently: "
    "digits vs. number words, '1 000' vs. '1,000', a date written in another convention, "
    "a time zone or clock format, a decade ('1980er' = '1980s'), a rounded value, a range "
    "('second half of 2027' = 'before early 2028'), a unit conversion the source itself states. "
    "Answer ONLY from the source. If the source does not state the figure or an equivalent, "
    "say so. Your evidence must be a verbatim quote copied from the source text — never "
    "paraphrase it, never translate it, never invent it."
)

PROMPT = """Article sentence:
{sentence}

Figure under review: {token}

Source text:
<<<
{source}
>>>

Question: Does the source state this figure or an equivalent of it (different format, wording, language, rounding, range or unit)?
Reply as JSON: {{"supported": true|false, "evidence": "<verbatim quote from the source, max 200 characters, empty if not supported>", "form": "<same|format|number-word|date|time|decade|range|rounding|unit|translation|not-found>", "note": "<one short sentence>"}}"""


NAME_SYSTEM = (
    "You check whether a person named in a short article is actually named in its source text. "
    "The source may be in another language or script and may render the name differently "
    "(transliteration, different order, a typo, a title attached). Decide ONLY from the source text. "
    "Never use your own knowledge of who holds an office: if the source mentions only a role "
    "('the Foreign Secretary', 'the CEO') and no name, the answer is role_only — even when you "
    "believe you know the person. Your evidence must be copied verbatim from the source text."
)

NAME_PROMPT = """Article sentence:
{sentence}

Person as the article names them: {name}

Source text:
<<<
{source}
>>>

How does the source refer to this person?
- "named": the source gives their name (any spelling, order, script or with a title)
- "surname_only": the source gives only the family name or title + family name, not the given name
- "role_only": the source mentions only a role, office or job title and no name at all
- "absent": the source does not refer to this person

Reply as JSON: {{"status": "named|surname_only|role_only|absent", "evidence": "<verbatim quote from the source, max 200 characters, empty if absent>", "source_form": "<exactly how the source writes the name or the role, copied verbatim, empty if absent>", "note": "<one short sentence>"}}"""


ROMAN_SYSTEM = (
    "You transliterate a personal name into the Latin alphabet. Output the transliteration only. "
    "Do not add titles, do not explain, do not substitute a different person."
)

ROMAN_PROMPT = """Name as written in the source text: {form}

Context from the source:
{context}

Write this person's name in the Latin alphabet.
Reply as JSON: {{"latin": "<the name in Latin letters>"}}"""


class Romanisation(BaseModel):
    latin: str = ""


class NameVerdict(BaseModel):
    status: str = Field(default="absent")
    evidence: str = ""
    source_form: str = ""
    note: str = ""


class FigureVerdict(BaseModel):
    supported: bool
    evidence: str = ""
    form: str = Field(default="not-found")
    note: str = ""


# ---------------------------------------------------------------------------
# Textregeln (rein, getestet)
# ---------------------------------------------------------------------------
def _norm(s: str) -> str:
    s = s.lower()
    s = s.replace(" ", " ").replace(" ", " ")
    s = re.sub(r"[‘’‚′]", "'", s)
    s = re.sub(r"[“”„″]", '"', s)
    s = re.sub(r"[‐-―]", "-", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def evidence_in_source(evidence: str, source: str, min_chars: int = 6) -> bool:
    """Woertliches Zitat? Normalisiert (Whitespace, Anfuehrungszeichen,
    Gedankenstriche, Gross/Klein) und ohne Rand-Interpunktion; zu kurze
    „Belege" (unter min_chars) zaehlen nicht — ein einzelnes „2025" ist kein
    Beleg fuer einen Satz."""
    e = _norm(evidence).strip(" .,;:!?\"'()[]")
    if len(e) < min_chars:
        return False
    return e in _norm(source)


NON_DIGIT_FORMS = {"number-word", "decade", "translation", "range", "rounding", "time"}


def _digits(s: str) -> str:
    """Nur die Ziffern — „1 000" und „1,000" werden dasselbe, „21.09.2026" traegt 21."""
    return re.sub(r"\D", "", s)


NUMBER_WORDS = (
    "one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
    "sixteen seventeen eighteen nineteen twenty thirty forty fifty sixty seventy eighty ninety "
    "hundred thousand million billion trillion half quarter dozen "
    "ein eine zwei drei vier fuenf fünf sechs sieben acht neun zehn elf zwoelf zwölf zwanzig "
    "dreissig dreißig vierzig fuenfzig fünfzig hundert tausend millionen milliarden halb "
    "un deux trois quatre cinq six sept huit neuf dix cent mille millions milliards demi "
    "uno dos tres cuatro cinco seis siete ocho nueve diez ciento mil "
    "en ett tva två tre fyra fem sex sju atta åtta nio tio hundra tusen "
    "egy ketto kettő harom három negy négy ot öt hat het hét nyolc kilenc tiz tíz szaz száz ezer"
).split()


def _numbers_in(text: str) -> list[float]:
    """Zahlen eines Textes — Tausendertrenner (Punkt, Komma, Leerzeichen) entfernt,
    Dezimalkomma wie Dezimalpunkt gelesen."""
    out: list[float] = []
    for raw in re.findall(r"\d[\d .,\u00a0\u202f]*", text):
        t = raw.strip(" .,\u00a0\u202f")
        if not t:
            continue
        t = t.replace("\u00a0", "").replace("\u202f", "").replace(" ", "")
        if "," in t and "." in t:
            t = t.replace("." if t.rindex(",") > t.rindex(".") else ",", "")
        t = t.replace(",", ".")
        if t.count(".") > 1:
            t = t.replace(".", "")
        try:
            out.append(float(t))
        except ValueError:
            continue
    return out


def evidence_supports_token(token: str, evidence: str, form: str) -> bool:
    """Traegt das Zitat wirklich DIESE Angabe?

    Die vom Modell genannte Form darf die Pruefung nicht allein steuern — sonst
    genuegt es, eine strengere Form in eine laxere umzudeklarieren. Gemessen
    23.09.: das 8B belegte das Jahr „2026" mit „59 % der Bevoelkerung ab 14
    Jahren nutzen zumindest gelegentlich KI-Tools"; als die Ziffernpruefung fuer
    „same" kam, nannte es dieselbe Fundstelle „number-word".

    Reihenfolge — jede Stufe ist pruefbar:
      1. Die Ziffern der Angabe stehen im Zitat  -> belegt (deckt gleiche Werte,
         Trennerformate, Datums- und Uhrzeitteile).
      2. Das Zitat ist nicht-lateinisch -> nicht nachrechenbar; hier entscheidet
         der blinde Zweitdurchgang bzw. der Mensch, wir lassen es zu.
      3. Das Zitat traegt ein Zahlwort -> Zahlwort-Fall.
      4. Eine Zahl des Zitats rundet auf die Angabe oder klammert sie ein
         (Spanne) -> belegt.
      5. Sonst: nicht belegt.
    """
    tok_digits = _digits(token)
    if not tok_digits or tok_digits in _digits(evidence):
        return True
    if has_non_latin(evidence):
        return True
    low = evidence.lower()
    if any(re.search(rf"\b{w}\b", low) for w in NUMBER_WORDS):
        return True
    nums = _numbers_in(evidence)
    if not nums:
        return False
    try:
        t = float(tok_digits)
    except ValueError:
        return False
    for n in nums:                       # Rundung: 207,5 -> 207, 5 % Toleranz
        if n and abs(n - t) / max(abs(t), 1.0) <= 0.05:
            return True
    if len(nums) >= 2 and min(nums) <= t <= max(nums):   # Spanne: 2 000 bis 20 000
        return True
    return False


def evidence_carries_number(evidence: str) -> bool:
    """Traegt der Beleg eine Ziffer? Zahlwoerter gibt es in jeder Quellsprache
    („tizennégy", „три тисячі", „Dreißigerjahren", „zehnjähriger") — eine
    Wortliste kann das nicht abdecken (gemessen 22.09.: alle zehn Belege ohne
    Ziffer waren echte Zahlwoerter). Deshalb entscheidet bei fehlender Ziffer
    die vom Modell benannte Form (NON_DIGIT_FORMS), nicht eine Liste."""
    return bool(re.search(r"\d", evidence))


def _edit_distance_le1(a: str, b: str) -> bool:
    """Levenshtein-Abstand <= 1 (Tippfehler wie „Urlula" gegen „Ursula")."""
    if a == b:
        return True
    la, lb = len(a), len(b)
    if abs(la - lb) > 1:
        return False
    i = j = 0
    diff = 0
    while i < la and j < lb:
        if a[i] == b[j]:
            i += 1
            j += 1
            continue
        diff += 1
        if diff > 1:
            return False
        if la == lb:
            i += 1
            j += 1
        elif la > lb:
            i += 1
        else:
            j += 1
    return diff + (la - i) + (lb - j) <= 1


def token_in_source(tok: str, source: str) -> bool:
    """Wort im Quelltext — als Teilstring (Komposita wie „Vizepremier") oder
    mit einem Tippfehler Abstand (Quelle schreibt „Urlula", Artikel „Ursula")."""
    t = _norm(tok).strip(".,;:")
    if len(t) < 2:
        return True
    src = _norm(source)
    if t in src:
        return True
    return any(_edit_distance_le1(t, w) for w in re.findall(r"[^\W\d_]+", src, flags=re.UNICODE))


# Titelwoerter, die `grounding._TITLES` nicht kennt. Ein Titel gehoert nicht zur
# Identitaet: „Chinese Vice Premier He Lifeng" gegen „Vize-Ministerpraesident He
# Lifeng" ist derselbe Mensch. Fehlt ein Titel in der Quelle, wird er im Bericht
# vermerkt (title_not_in_source), haelt den Draft aber nicht zurueck — der
# gefaehrliche Fall ist der umgekehrte: Rolle in der Quelle, Name aus dem Modell.
TITLE_EXTRA = frozenset("""
premier premierminister ministerpräsident vizepremier prime deputy chief head officer
executive lead leiter leiterin vorsitzender vorsitzende partner manager managerin
generalsekretär generalsekretärin staatschef staatschefin bundeskanzler bundesministerin
bundesminister eu-kommissarin kommissarin kommissar vp svp evp cdo cpo cro
""".split())


def _title_words() -> frozenset:
    from pipeline.grounding import _TITLES
    return _TITLES | TITLE_EXTRA


def name_tokens_in_source(name: str, source: str) -> tuple[bool, list[str]]:
    """(nennt die Quelle diesen Namen?, die fehlenden NAMENSteile).

    Titelwoerter werden uebersprungen (dieselbe Liste, mit der das Gate Namen
    erkennt): „Chinese Vice Premier He Lifeng" gegen eine Quelle, die
    „Vize-Ministerpraesident He Lifeng" schreibt, ist derselbe Mensch mit einem
    uebersetzten Titel — kein erfundener Name. Der Nachname muss als eigenes
    Wort in der Quelle stehen (ein Tippfehler DORT ist ein Defekt des Artikels:
    „Papfuss" gegen „Papenfuss" bleibt beim Menschen), Vornamen duerfen einen
    Tippfehler Abstand haben (Quelle „Urlula", Artikel „Ursula")."""
    titles = _title_words()
    parts = [p for p in re.split(r"\s+", name.strip()) if p]
    words = [p for p in parts if p.lower().rstrip(".") not in titles]
    if not words:
        return False, parts
    missing = []
    surname = _norm(words[-1]).strip(".,;:")
    if surname and not re.search(rf"(?<![^\W\d_]){re.escape(surname)}(?![^\W\d_])", _norm(source), flags=re.UNICODE):
        missing.append(words[-1])
    for p in words[:-1]:
        if not token_in_source(p, source):
            missing.append(p)
    return (not missing), missing


def titles_not_in_source(name: str, source: str) -> list[str]:
    """Titelwoerter des Artikels, die die Quelle nicht fuehrt — Vermerk, kein Hold."""
    titles = _title_words()
    return [p for p in re.split(r"\s+", name.strip())
            if p.lower().rstrip(".") in titles and not token_in_source(p, source)]


def has_non_latin(s: str) -> bool:
    return bool(re.search(r"[^\x00-\x7F\u00C0-\u024F]", s))


NAME_HOLD_LABEL = {
    "role_only": "Rolle ohne Name in der Quelle — Name stammt aus dem Modellwissen",
    "surname_only": "Quelle nennt nur den Nachnamen — Vorname ergaenzt",
    "absent": "Person kommt in der Quelle nicht vor",
    "misspelled": "Schreibweise weicht von der Quelle ab",
    "translit": "andere Schrift — Romanisierung passt nicht zum Artikelnamen",
    "unverified": "Beleg nicht woertlich in der Quelle",
}


def verify_name_verdict(v: NameVerdict | None, name: str, source: str) -> tuple[bool, str]:
    """(gilt als belegt?, Klasse).

    Entschieden wird deterministisch an den Namensteilen; das Modell liefert den
    Beleg, die Quellform und ein Veto:

      alle Teile in der Quelle  -> veroeffentlichbar (das Gate stolperte ueber
                                   einen Tippfehler der Quelle oder ein Kompositum),
                                   ausser das Modell sagt, die Quelle nenne die
                                   Person gar nicht (role_only/absent).
      nur Vorname/Titel fehlt   -> surname_only (Vorname ergaenzt — bleibt beim Menschen)
      Nachname fehlt            -> role_only / absent (Modell), sonst translit
                                   (andere Schrift) oder misspelled.
    """
    st = ((v.status if v else "") or "absent").strip().lower()
    ok, missing = name_tokens_in_source(name, source)
    if ok:
        if st in ("role_only", "absent"):
            return False, st
        return True, "named"
    if missing and missing[0] not in (name.split()[-1:] or [""]) and name.split()[-1] not in missing:
        return False, "surname_only"
    if st in ("role_only", "absent"):
        return False, st
    if v and has_non_latin(v.evidence) and evidence_in_source(v.evidence, source):
        return False, "translit"
    return False, "misspelled"


def name_shaped(form: str) -> bool:
    """Sieht die Quellform wie ein Personenname aus? Schutz gegen Fundstellen,
    die woertlich in der Quelle stehen, aber kein Name sind — gemessen 22.09.:
    „Arne Giacomo" haette sonst das GitHub-Handle „arnegiacomo" bekommen, Gate
    gruen, Text Unsinn. Regel: 1-4 Woerter, jedes beginnt gross (oder ist ein
    Namenspartikel wie „von"/„de"), keine Ziffern, kein Sonderzeichen-Klumpen."""
    f = (form or "").strip().strip(".,;:")
    if not f or any(ch.isdigit() for ch in f) or any(ch in f for ch in "@/\\_|<>()[]{}"):
        return False
    words = f.split()
    if not 1 <= len(words) <= 4:
        return False
    particles = {"von", "van", "de", "der", "den", "del", "della", "di", "du", "da", "dos", "bin", "al", "le", "la"}
    for i, w in enumerate(words):
        w = w.strip(".,;:")
        if not w:
            return False
        if w.lower() in particles and i < len(words) - 1:
            continue    # „von der Leyen" ist eine gueltige Quellform, „Leyen von" nicht
        if not w[0].isupper():
            return False
    return True


def repair_name(body: str, article_name: str, source_form: str) -> str | None:
    """Den Artikelnamen durch die Form der Quelle ersetzen — an JEDER Stelle des
    Bodys, denn der ergaenzte Vorname taucht oft mehrfach auf. Gibt None zurueck,
    wenn nichts zu ersetzen ist oder die Ersetzung nichts aendert."""
    art = (article_name or "").strip()
    form = (source_form or "").strip().strip(".,;:")
    if not art or not form or art == form or art not in body:
        return None
    out = body.replace(art, form)
    return out if out != body else None


def repairs_for(item: dict) -> list[dict]:
    """Die verlaesslich reparierbaren Befunde: NUR der ergaenzte Vorname
    (`surname_only`) — die Quellform ersetzt den Artikelnamen, es kommt keine
    Information hinzu, die nicht in der Quelle steht.

    `misspelled` ist bewusst NICHT dabei (Messung 22.09., 4 echte Faelle):
    zweimal haette der Tausch den Namen richtig gestellt (Papfuss->Papenfuss,
    Kokotjalo->Kokotajlo), zweimal haette er einen Fehler der QUELLE uebernommen
    (Xi Jinping->„Xi Jiping") oder den Nachnamen ganz verloren (Amodei->„Dario").
    Welche Seite richtig schreibt, ist ohne Weltwissen nicht zu entscheiden —
    und Weltwissen ist genau das, was hier nicht entscheiden soll. Diese Faelle
    stehen als Vorschlag im Bericht (`proposals`) und bleiben beim Menschen."""
    out = []
    for n in item.get("names", []):
        if n.get("ok") or n.get("kind") != "surname_only":
            continue
        form = (n.get("source_form") or "").strip()
        if not form or not name_shaped(form) or form.lower() == n["name"].strip().lower():
            continue
        # Der Nachname des Artikels muss in der Quellform erhalten bleiben —
        # sonst wuerde aus „Dario Amodei" ein blosses „Dario".
        surname = n["name"].split()[-1].strip(".,;:").lower()
        if surname and surname not in form.lower():
            continue
        out.append({"name": n["name"], "source_form": form, "kind": n["kind"]})
    return out


def proposals_for(item: dict) -> list[dict]:
    """Was ein Mensch mit einem Klick uebernehmen koennte, der Agent aber nicht
    selbst entscheidet: abweichende Schreibweisen (welche Seite stimmt?) und
    Saetze, deren Zahl/Person die Quelle nicht deckt (das Gate waere danach
    gruen, aber ob der Artikel noch etwas sagt, misst kein Gate)."""
    out = []
    for n in item.get("names", []):
        if not n.get("ok") and n.get("kind") == "misspelled" and n.get("source_form"):
            out.append({"kind": "spelling", "what": n["name"], "to": n["source_form"],
                        "note": "Quelle schreibt es anders — welche Seite stimmt, entscheidet ein Mensch"})
    drop = [f["token"] for f in item.get("figures", []) if not f["ok"]]
    drop += [n["name"] for n in item.get("names", []) if not n.get("ok") and n.get("kind") in ("role_only", "absent")]
    for d in drop:
        out.append({"kind": "drop_sentence", "what": d,
                    "note": "Satz mit dieser Angabe streichen"})
    return out


def sentence_with(body: str, token: str) -> str:
    """Der Satz des Artikels, der das beanstandete Token traegt (sonst der Body-Anfang)."""
    t = token.strip(".,;:")
    for s in re.split(r"(?<=[.!?])\s+", body or ""):
        if t and t in s:
            return s.strip()
    return (body or "")[:300]


def verify_verdict(v: FigureVerdict | None, source: str, token: str = "") -> tuple[bool, str]:
    """(gilt als belegt?, Grund). Belegt nur, wenn das Modell 'supported' sagt
    UND das Zitat woertlich in der Quelle steht UND eine Zahl traegt."""
    if v is None:
        return False, "no answer"
    if not v.supported:
        return False, "model: not supported"
    if not v.evidence.strip():
        return False, "supported without evidence"
    if not evidence_in_source(v.evidence, source):
        return False, "evidence not verbatim in source"
    if not evidence_carries_number(v.evidence) and (v.form or "") not in NON_DIGIT_FORMS:
        return False, f"evidence carries no figure (form {v.form or '?'})"
    if not evidence_supports_token(token, v.evidence, v.form or ""):
        return False, f"evidence does not carry {token} (form {v.form or '?'})"
    return True, v.form or "equivalent"


# ---------------------------------------------------------------------------
# GPU-Handover (Stage 11 des Nachtlaufs)
# ---------------------------------------------------------------------------
def llama_unit_active() -> bool:
    """Laeuft die llama-server-Unit gerade? Der Handover stoppt sie am Ende;
    lief sie vorher, muss sie danach wieder laufen (Ruhezustand)."""
    from pipeline import gpu_handover
    try:
        r = gpu_handover._run(["systemctl", "--user", "is-active", gpu_handover.LLAMA_UNIT], timeout=15)
        return r.stdout.strip() == "active"
    except Exception:                                               # noqa: BLE001
        return False


def restore_resting_server(was_active: bool) -> None:
    """Ruhezustand wiederherstellen — dieselbe Regel wie in scripts/research_pulse.py."""
    if not was_active:
        return
    from pipeline import gpu_handover
    try:
        gpu_handover._run(["systemctl", "--user", "start", gpu_handover.LLAMA_UNIT], timeout=60)
    except Exception as exc:                                        # noqa: BLE001
        logger.error("llama-server konnte nicht neu gestartet werden: %s", exc)


# ---------------------------------------------------------------------------
# Modell
# ---------------------------------------------------------------------------
def ask_model(sentence: str, token: str, source: str, model: str) -> FigureVerdict | None:
    from pipeline import llamacpp_client
    prompt = PROMPT.format(sentence=sentence, token=token, source=source[:SOURCE_MAX_CHARS])
    try:
        return llamacpp_client.chat_structured(model, prompt, FigureVerdict, system=SYSTEM,
                                               temperature=0.0, max_tokens=400)
    except Exception as exc:  # noqa: BLE001
        logger.warning("review_agent: model call failed for %r: %r", token, exc)
        return None


def ask_romanisation(form: str, context: str, model: str) -> str:
    """Blinder zweiter Durchgang: das Modell romanisiert NUR die Quellform und
    sieht den Artikelnamen nicht. So bestaetigt es eine Transliteration, statt
    den Namen aus dem Artikel zu wiederholen — und der Fall „Quelle nennt
    Філіп Навратіль, Artikel schreibt Mark Schneider" faellt auf."""
    from pipeline import llamacpp_client
    prompt = ROMAN_PROMPT.format(form=form[:120], context=context[:600])
    try:
        r = llamacpp_client.chat_structured(model, prompt, Romanisation, system=ROMAN_SYSTEM,
                                            temperature=0.0, max_tokens=120)
        return (r.latin if r else "") or ""
    except Exception as exc:  # noqa: BLE001
        logger.warning("review_agent: romanisation failed for %r: %r", form, exc)
        return ""


def romanisation_matches(name: str, latin: str) -> bool:
    """Trifft die romanisierte Quellform den Nachnamen des Artikels? Exakt,
    als Teilwort oder mit bis zu einem Tippfehler (Transliterationen weichen
    leicht ab: „Макінтайр" -> „Makintair"/„McIntyre")."""
    titles = _title_words()
    words = [w for w in re.split(r"\s+", name.strip()) if w.lower().rstrip(".") not in titles]
    if not words or not latin.strip():
        return False
    surname = _norm(words[-1]).strip(".,;:")
    cand = [_norm(w).strip(".,;:") for w in re.split(r"[^\w']+", latin) if len(w) > 1]
    return any(c == surname or surname in c or c in surname or _edit_distance_le1(c, surname) for c in cand)


def ask_model_name(sentence: str, name: str, source: str, model: str) -> NameVerdict | None:
    from pipeline import llamacpp_client
    prompt = NAME_PROMPT.format(sentence=sentence, name=name, source=source[:SOURCE_MAX_CHARS])
    try:
        return llamacpp_client.chat_structured(model, prompt, NameVerdict, system=NAME_SYSTEM,
                                               temperature=0.0, max_tokens=400)
    except Exception as exc:  # noqa: BLE001
        logger.warning("review_agent: model call failed for name %r: %r", name, exc)
        return None


# ---------------------------------------------------------------------------
# Durchlauf
# ---------------------------------------------------------------------------
def held_drafts(limit: int | None = None, ids: list[int] | None = None) -> list[dict]:
    from pipeline.db import get_connection
    sql = ("SELECT id, raw_entry_id, title_en, body_en, source_name, source_url, primary_vertical, confidence, "
           "created_at::text AS created_at FROM trends WHERE status = 'draft' AND confidence >= ? AND judged_at IS NULL "
           "AND reviewed_at IS NULL")
    params: list = [CONFIDENCE_MIN]
    if ids:
        sql += " AND id = ANY(?)"
        params.append(ids)
    sql += " ORDER BY created_at DESC"
    if limit:
        sql += f" LIMIT {int(limit)}"
    with get_connection() as conn:
        return [dict(r) for r in conn.execute(sql, tuple(params)).fetchall()]


def check_draft(t: dict, model: str) -> dict:
    """Ein Draft: Gate-Befunde, je Zahl der Modell-Beleg, Entscheidung."""
    from pipeline.auto_publisher import _body_complete, _source_text
    from pipeline.content_guard import garbage_reasons
    from pipeline.grounding import ungrounded_names, ungrounded_specifics
    body = t.get("body_en") or ""
    source = _source_text(t.get("raw_entry_id")) or ""
    out = {"id": t["id"], "title": (t.get("title_en") or "")[:90], "source_name": t.get("source_name"),
           "vertical": t.get("primary_vertical"), "created_at": (t.get("created_at") or "")[:10],
           "figures": [], "names": [], "garbled": [], "truncated": False, "decision": "human", "why": ""}
    if not source:
        out["why"] = "no source text"
        return out
    out["garbled"] = garbage_reasons(body, source)
    out["truncated"] = not _body_complete(body)
    out["names"] = []
    seen_names = set()
    for nm in ungrounded_names(body, source):
        if nm in seen_names:
            continue
        seen_names.add(nm)
        sent = sentence_with(body, nm.split()[-1])
        v = ask_model_name(sent, nm, source, model)
        ok, kind = verify_name_verdict(v, nm, source)
        latin = ""
        if kind == "translit" and v:
            latin = ask_romanisation(v.source_form or v.evidence, v.evidence, model)
            if romanisation_matches(nm, latin):
                ok, kind = True, "translit_confirmed"
        out["names"].append({"name": nm, "sentence": sent[:240], "ok": ok, "kind": kind,
                             "title_not_in_source": titles_not_in_source(nm, source), "latin": latin,
                             "evidence": (v.evidence if v else "")[:200],
                             "source_form": (v.source_form if v else "")[:120],
                             "note": (v.note if v else "")[:160]})
    seen = set()
    for tok in ungrounded_specifics(body, source):
        key = tok.strip(".,;:")
        if key in seen:
            continue
        seen.add(key)
        sent = sentence_with(body, tok)
        v = ask_model(sent, key, source, model)
        ok, why = verify_verdict(v, source, key)
        out["figures"].append({"token": key, "sentence": sent[:240], "ok": ok, "why": why,
                               "evidence": (v.evidence if v else "")[:200], "form": (v.form if v else ""),
                               "note": (v.note if v else "")[:160]})
    bad_names = [n for n in out["names"] if not n["ok"]]
    bad_figs = [f for f in out["figures"] if not f["ok"]]
    if out["garbled"]:
        out["decision"], out["why"] = "human", "garbled: " + "; ".join(out["garbled"][:2])
    elif out["truncated"]:
        out["decision"], out["why"] = "human", "truncated body"
    elif bad_names:
        out["decision"] = "human"
        out["why"] = "; ".join(f'{n["name"]}: {NAME_HOLD_LABEL.get(n["kind"], n["kind"])}'
                               + (f' (Quelle: "{n["source_form"]}")' if n["source_form"] and n["kind"] in ("surname_only", "role_only", "misspelled") else "")
                               for n in bad_names)[:400]
    elif bad_figs:
        out["decision"] = "human"
        out["why"] = "not supported: " + "; ".join(f'{f["token"]} ({f["why"]})' for f in bad_figs)[:300]
    elif not out["figures"] and not out["names"]:
        out["decision"], out["why"] = "human", "no gate objection found (re-check would publish)"
    else:
        out["decision"] = "equivalent"
        parts = [f'{n["name"]} = "{n["evidence"][:60]}"'
                 + (f' [Titel nicht in der Quelle: {", ".join(n["title_not_in_source"])}]' if n["title_not_in_source"] else "")
                 for n in out["names"]]
        parts += [f'{f["token"]} = "{f["evidence"][:60]}" ({f["form"]})' for f in out["figures"]]
        out["why"] = "; ".join(parts)[:400]
    return out


def try_repair(t: dict, item: dict, source: str) -> dict | None:
    """Reparatur versuchen und das Ergebnis GEGEN DIESELBEN GATES pruefen, die
    das Auto-Publish anlegt. Nur wenn danach alles gruen ist, gilt sie —
    geglaubt wird der Reparatur nichts, sie wird nachgemessen.

    Gibt {"body", "changes", "words"} zurueck oder None."""
    from pipeline.auto_publisher import _body_complete
    from pipeline.content_guard import garbage_reasons
    from pipeline.grounding import ungrounded_names, ungrounded_specifics
    reps = repairs_for(item)
    if not reps or item.get("garbled") or item.get("truncated"):
        return None
    if any(not f["ok"] for f in item.get("figures", [])):
        return None          # eine unbelegte Zahl repariert kein Namenstausch
    if any(not n["ok"] and n["kind"] != "surname_only" for n in item.get("names", [])):
        return None          # role_only/absent/translit gehoeren dem Menschen
    body = t.get("body_en") or ""
    changes = []
    for r in reps:
        new = repair_name(body, r["name"], r["source_form"])
        if new is None:
            return None
        body = new
        changes.append(f'{r["name"]} → {r["source_form"]} ({r["kind"]})')
    words = len(body.split())
    if words < MIN_BODY_WORDS:
        return None
    if garbage_reasons(body, source) or not _body_complete(body):
        return None
    if ungrounded_names(body, source) or ungrounded_specifics(body, source):
        return None
    return {"body": body, "changes": changes, "words": words}


def publish_repaired(item: dict, body: str) -> bool:
    from pipeline.db import get_connection
    reason = ("agent:repair:" + "; ".join(item["repair"]["changes"]))[:500]
    with get_connection() as conn:
        conn.execute("UPDATE trends SET body_en = ?, status = 'published', published_at = NOW(), "
                     "auto_published = TRUE, review_reason = ? WHERE id = ? AND status = 'draft'",
                     (body, reason, item["id"]))
        if hasattr(conn, "commit"):
            conn.commit()
    return True


def publish_equivalent(item: dict) -> bool:
    from pipeline.db import get_connection
    reason = ("agent:equivalent:" + item["why"])[:500]
    with get_connection() as conn:
        conn.execute("UPDATE trends SET status = 'published', published_at = NOW(), auto_published = TRUE, "
                     "review_reason = ? WHERE id = ? AND status = 'draft'", (reason, item["id"]))
        if hasattr(conn, "commit"):
            conn.commit()
    return True


def run(limit: int | None = None, ids: list[int] | None = None, apply: bool = False,
        model: str | None = None, no_repair: bool = False) -> dict:
    from pipeline import llamacpp_client
    served = llamacpp_client.served_model_id()
    if not served:
        raise SystemExit("kein llama-server auf :8090 — Ruhezustand herstellen oder Cycle abwarten (Exit 3)")
    model = model or served
    rows = held_drafts(limit, ids)
    report = {"date": datetime.now(timezone.utc).isoformat(timespec="seconds"), "model": served,
              "dry_run": not apply, "checked": 0, "equivalent": 0, "repaired": 0, "human": 0,
              "published": 0, "items": []}
    for t in rows:
        item = check_draft(t, model)
        report["checked"] += 1
        item["proposals"] = proposals_for(item) if item["decision"] == "human" else []
        if item["decision"] == "human" and not no_repair:
            from pipeline.auto_publisher import _source_text
            rep = try_repair(t, item, _source_text(t.get("raw_entry_id")) or "")
            if rep:
                item["repair"] = {"changes": rep["changes"], "words": rep["words"]}
                item["decision"] = "repaired"
                item["why"] = "; ".join(rep["changes"])
        if item["decision"] == "equivalent":
            report["equivalent"] += 1
            if apply and publish_equivalent(item):
                report["published"] += 1
                item["published"] = True
        elif item["decision"] == "repaired":
            report["repaired"] += 1
            if apply and publish_repaired(item, rep["body"]):
                report["published"] += 1
                item["published"] = True
        else:
            report["human"] += 1
        report["items"].append(item)
        logger.info("#%d %-10s %s", item["id"], item["decision"], item["why"][:120])
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    return report
