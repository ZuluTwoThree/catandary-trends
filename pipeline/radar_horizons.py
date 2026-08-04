"""Horizont-Radar: berechnet H1/H2/H3 pro (Technologiefeld × Dimension × Jurisdiktion).

Ersetzt die Logik des alten Lead-Time-Radars, dessen Ringe die *Quellenherkunft*
eines Clusters abbildeten statt der Reife einer Technologie (siehe
docs/radar_redesign_proposal.md §1.1). Hier ist die Position eine
Handlungsempfehlung:

    H1 = handeln      — im Markt / zugelassen / etabliert
    H2 = aufbauen     — im Übergang, Pfad offen, erste Produkte
    H3 = beobachten   — Forschung / kein Zulassungspfad / keine Produkte
    None = unbekannt  — zu wenig Evidenz; die Zelle schweigt statt zu raten

Hybrid nach Dimension (Owner-Entscheidung 2026-07-30), weil kein einzelner
Mechanismus alle Dimensionen ehrlich abdeckt:

  technology  → CPC-Takeoff-Anker aus cpc_leadtime_summary, aber nur bei
                `reliable=1`; sonst semantischer Signalmix, der HART auf H2
                gedeckelt ist (Skalen-/Kostenreife ist aus Signalen nicht lesbar)
  regulatory  → Meilenstein-Gates pro Jurisdiktion, Sub-Typ granted/filed/
                forming/gap; die Jurisdiktion einer Zulassung kommt aus der
                genannten BEHÖRDE, nicht aus `regions`
  market      → Produktstart-Zählung pro Jurisdiktion + Handels-/Skalierungsmarker,
                in regulierten Domänen an die Zulassung gekoppelt
  adoption    → Nachfrage-/Verhaltenssignale pro Jurisdiktion

WICHTIG — zwei Datenfallen, die die Auswertung sonst verfälschen:

1. `trend_signal_type` hat ZWEI Herkünfte. Der Distill-Pfad
   (scripts/signal_batch.py, _distill_signal_type) leitet den Typ deterministisch
   aus der QUELLE ab und schreibt dabei `tags=[]` und `regions=[]`. Für 80 % der
   market_shift- und 45 % der funding-Zeilen ist der Typ also keine semantische
   Aussage. Würde man darauf aggregieren, misst man wieder Quellenkomposition —
   genau der Fehler des alten Radars. Deshalb zählt der Signalmix nur Zeilen mit
   nicht-leeren tags (Spalte `semantic` in load_scope_signals = LLM-Pfad). Die
   vier Typen regulation / product_launch /
   partnership / consumer_behavior stammen ausschließlich aus dem LLM-Pfad und
   sind zu ~100 % regionsgetaggt — sie tragen die Gates.

2. `sort_date` ist für 52 % der Zeilen NULL. Zeitachse ist immer
   raw_entries.published_date.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from datetime import date, datetime, timedelta

from .db import get_connection

log = logging.getLogger(__name__)

HORIZONS = ("H1", "H2", "H3")
DIMENSIONS = ("technology", "regulatory", "market", "adoption")

# Dimensionen, die keine Jurisdiktion kennen, werden unter '*' abgelegt und vom
# Read-Layer für jede Region ausgeliefert (Patentreife ist nicht regional).
REGION_BLIND = {"technology"}
ANY_REGION = "*"

# ---------------------------------------------------------------------------
# Jurisdiktions-Normalisierung
# ---------------------------------------------------------------------------
# `trends.regions` ist freier LLM-Text und uneinheitlich: 'US' / 'us' / 'USA' /
# 'United States' / 'California' / 'US-CA' bzw. 'EU' / 'Europe' / 'europe' /
# 'Germany' stehen unverbunden nebeneinander (Inventur 2026-07-30: 'global'
# 276.927 vs 'Global' 21.471). Ohne dieses Mapping zersplittern die Zellen.
_EU_MEMBERS = {
    "eu", "european union", "europe", "eea", "brussels",
    "germany", "france", "netherlands", "belgium", "spain", "italy", "denmark",
    "sweden", "finland", "austria", "poland", "ireland", "portugal", "greece",
    "czech republic", "czechia", "hungary", "romania", "bulgaria", "croatia",
    "slovakia", "slovenia", "estonia", "latvia", "lithuania", "luxembourg",
    "cyprus", "malta",
}
_US_TERMS = {
    "us", "usa", "u.s.", "u.s.a.", "united states", "united states of america",
    "north america", "america",
    # Bundesstaaten und Städte, die als Region auftauchen
    "california", "texas", "new york", "wisconsin", "delaware", "massachusetts",
    "florida", "illinois", "washington", "colorado", "georgia", "michigan",
    "minnesota", "iowa", "ohio", "oregon", "pennsylvania", "north carolina",
    "new jersey", "virginia", "arizona", "missouri", "tennessee", "maryland",
    "silicon valley", "san francisco", "boston", "chicago",
}
_UK_TERMS = {"uk", "u.k.", "united kingdom", "great britain", "britain",
             "england", "scotland", "wales", "northern ireland", "london"}
_GLOBAL_TERMS = {"global", "worldwide", "international", "world"}
_APAC_TERMS = {
    "apac", "asia", "asia-pacific", "asia pacific", "southeast asia",
    "china", "japan", "south korea", "korea", "singapore", "india", "taiwan",
    "hong kong", "thailand", "vietnam", "indonesia", "malaysia", "philippines",
    "australia", "new zealand", "oceania",
}

JURISDICTIONS = ("US", "EU", "UK", "IL", "APAC", "GLOBAL")


def normalize_region(raw: str) -> str | None:
    """Rohen regions-Eintrag auf einen Jurisdiktions-Code abbilden.

    Rückgabe None für Werte, die keiner geführten Jurisdiktion zuzuordnen sind
    (z. B. 'Latin America', 'Africa') — die zählen dann nur in den Scope-Total,
    nicht in eine Zelle. Bewusst kein Ratespiel: eine falsch zugeordnete
    Zulassung ist teurer als eine fehlende.
    """
    if not raw:
        return None
    k = raw.strip().lower().replace("_", " ").replace("-", " ")
    k = re.sub(r"\s+", " ", k)
    if k in _GLOBAL_TERMS:
        return "GLOBAL"
    if k in _US_TERMS or k.startswith("us "):
        return "US"
    if k in _EU_MEMBERS:
        return "EU"
    if k in _UK_TERMS:
        return "UK"
    if k in {"israel", "il", "tel aviv"}:
        return "IL"
    if k in _APAC_TERMS:
        return "APAC"
    return None


def regions_of(row) -> set[str]:
    """Normalisierte Jurisdiktionen eines Trends (kann mehrere sein)."""
    raw = row.get("regions")
    vals = json.loads(raw) if isinstance(raw, str) else (raw or [])
    out = {normalize_region(v) for v in vals if isinstance(v, str)}
    return {v for v in out if v}


# „GLOBAL" ist keine Jurisdiktion, sondern das Etikett, das die Klassifikation
# vergibt, wenn ein Artikel keine Geografie nennt — gemessen 49-56 % aller
# Signale (Kalibrierlauf 2026-08-02). Als eigene Spalte gelesen beantwortete sie
# damit die Frage „was steht in den Signalen, die wir nicht verorten konnten?" —
# strategisch wertlos, und wegen der schieren Masse fast immer H1.
#
# Sie bedeutet ab jetzt WELTWEIT: die Vereinigung aller Signale des Felds,
# unabhängig von ihrer Region. Das ist die Frage, die ein Stratege wirklich hat —
# „gibt es das irgendwo?" — und sie steht sinnvoll neben „gibt es das hier?".
# `cell_environmental` verfuhr bereits so; jetzt tun es alle Zellen.
WORLD = "GLOBAL"


def in_jurisdiction(row, region: str) -> bool:
    return True if region == WORLD else region in regions_of(row)


# ---------------------------------------------------------------------------
# Regulatorik-Sub-Typ
# ---------------------------------------------------------------------------
# `trend_signal_type='regulation'` unterscheidet nicht zwischen "Konsultation
# eröffnet" und "Zulassung erteilt" — genau die H2/H1-Grenze der wichtigsten
# Dimension. Hier eine regelbasierte, prüfbare Nachklassifikation über Titel +
# Tags. Bewusst konservativ: nur eindeutige Zulassungsformulierungen zählen als
# GRANTED, alles Antrags-/Verfahrensartige ist PATHWAY.
REG_GRANTED = re.compile(
    r"\b(gras (status|clearance|approval|self-affirmed)?|"
    r"self-affirmed gras|"
    # Titel schreiben „No Questions“ Letter mit typografischen Anführungs-
    # zeichen — starre Wortgrenzen greifen dort nicht.
    r"no[\s\"‘’“”\']*questions[\s\"‘’“”\']*letter|"
    r"(receives?|granted|obtains?|earns?|wins?|secures?|gets?) [^.]{0,40}"
    r"(approval|authorisation|authorization|clearance|licence|license|certification)|"
    r"(approved|authorised|authorized|cleared|certified|permitted|licensed) (for|in|by|to)|"
    r"(fda|efsa|usda|ema|fsa|fsanz|mhlw|health canada) (clears?|cleared|approves?|approved|authorises?|authorized)|"
    r"first .{0,30}approval|"
    r"regulatory approval|approval (granted|obtained|secured)|"
    r"enters? into force|comes? into force|now in force|takes? effect)\b",
    re.I,
)
REG_PATHWAY = re.compile(
    r"\b(consultation|draft|proposal|proposes?|roadmap|framework|reform|"
    r"pending|submitted|submission|applies for|application|under review|"
    r"reviewing|novel food|pathway|guidance|pilot scheme|"
    r"seeks? approval|awaiting|in the pipeline|prioriti[sz]e|"
    r"strategy|standard[- ]setting|harmoni[sz]ation)\b",
    re.I,
)
# NUR echte Blockaden. Kalibrierlauf 2026-08-02: „Regulatory Uncertainty Shapes
# Global Gene Therapy Strategy" zählte als Blockade und setzte die EU-Zelle auf
# H3 — für ein Feld mit 11+ EMA-Zulassungen. Unsicherheit, Verzögerung, Hürden
# und Komplexität sind REIBUNG; sie verlangsamen einen offenen Weg, sie
# verschließen ihn nicht. Wer H3 („beobachten, kein Weg") behauptet, braucht ein
# Verbot, eine Ablehnung oder einen Entzug.
# TIER 1 — selbsterklärend: diese Formulierungen NENNEN die Zulassung, die
# fehlt. Sie brauchen keinen Objektbezug, weil sie ihn schon enthalten.
REG_GAP_EXPLICIT = re.compile(
    r"\b(no approval|not approved|never approved|unapproved|"
    r"approval (denied|rejected|refused)|denied approval|"
    r"refus(ed|al) of (approval|authorisation|authorization)|"
    r"(marketing )?authoris?z?ation (withdrawn|revoked|denied)|"
    r"moratorium)\b",
    re.I,
)

# TIER 2 — mehrdeutig: „bans", „suspends", „rejected" sagen für sich NICHT,
# WAS blockiert wird. Kalibrierlauf 2026-08-02, Feld „electric vehicle": „EU
# formally bans sale of gas and diesel cars from 2035" zählte als regulatorischer
# Gegenwind GEGEN Elektroautos — das Verbot trifft die Konkurrenztechnologie und
# ist der stärkste denkbare Rückenwind. Ebenfalls gezählt: „eBay announces ban on
# private sales of electric bicycles" und „Norway Suspends Arctic Seabed Mining".
# Diese Muster zählen deshalb nur, wenn ein Begriff des FELDES in Reichweite der
# Blockade steht — dann ist das Feld das Objekt, nicht bloß der Kontext.
REG_GAP_OBJECT = re.compile(
    r"\b(ban(ned|s)?|prohibit(ed|s|ion)?|outlaw(ed|s)?|"
    r"reject(ed|s|ion)?|refus(ed|al)|withdraw(n|s|al)?|suspend(ed|s|sion)?|"
    r"revok(ed|es)|halt(ed|s)? (sales|approval|use))\b",
    re.I,
)
BLOCKADE_WINDOW = 80   # Zeichen links und rechts der Blockade

# Ein Verbot, das gerade FÄLLT, ist keine Blockade. Kalibrierlauf 2026-08-02:
# „California's ban on self-driving trucks could soon be over" und „Waymo's
# Freeway Suspension Signals Growing Safety Scrutiny" trugen gemeinsam die
# Aussage „die US-Route für autonomes Fahren ist geschlossen" — während Waymo
# rund 500.000 bezahlte Fahrten pro Woche durchführte.
# Ein VORGESCHLAGENES Verbot ist keins, und ein von der Kommission als
# „unjustified" zurückgewiesenes erst recht nicht. Die EU-Zelle von Cultivated
# Meat stand auf „Route geschlossen", getragen von einer österreichischen
# Petition und zwei Meldungen darüber, dass Brüssel das ungarische Verbot für
# unzulässig hält.
BLOCKADE_PROPOSED = re.compile(
    r"\b(propos(e|es|ed|al)|petition|draft|bill\b|plans? to|seeks? to|"
    r"aims? to|calls? for|would (ban|prohibit)|considering|debate[sd]?|"
    r"unjustified|unlawful|illegal|challenge[sd]?|contest(ed|s)?|"
    r"criticis|criticiz|opposes?|pushback)\b",
    re.I,
)

BLOCKADE_LIFTED = re.compile(
    r"\b(lift(s|ed|ing)?|overturn(s|ed)?|repeal(s|ed)?|reversed?|"
    r"struck down|end(s|ed|ing)?|expir(e|es|ed)|"
    r"(could|will|to|may) (soon )?be over|no longer|"
    r"allow(s|ed)? again|resum(e|es|ed))\b",
    re.I,
)

# Rückwärtskompatibler Gesamtausdruck (Tests, Werkzeuge). Für die Einordnung
# wird er NICHT mehr benutzt — dort entscheidet `blockade_match`.
REG_GAP = re.compile(
    f"({REG_GAP_EXPLICIT.pattern}|{REG_GAP_OBJECT.pattern})", re.I
)


# Eine Blockade ist ein HOHEITLICHER Akt. „Waymo's Freeway Suspension Signals
# Growing Safety Scrutiny" ist eine Betriebspause des Unternehmens und trug
# dennoch die Aussage „die US-Route für autonomes Fahren ist geschlossen" —
# während Waymo rund 500.000 bezahlte Fahrten pro Woche fuhr.
GOVERNMENTAL = re.compile(
    r"\b(government|federal|state|states|parliament|congress|senate|commission|"
    r"ministry|minister|agency|regulator|regulatory|authority|authorities|court|"
    r"judge|law|legal|act\b|bill\b|directive|regulation|statute|ordinance|"
    r"member state|county|municipal|city|town|province|eu\b|brussels)\b",
    re.I,
)

# Ein benannter Staat IST der hoheitliche Akteur — „Italy bans cultivated meat"
# nennt keine Behörde und ist trotzdem eindeutig. Die Namen stammen aus derselben
# Jurisdiktions-Liste, die auch `normalize_region` benutzt: eine Quelle, keine
# zweite Pflegeliste.
_JURISDICTION_NAMES = sorted(
    {re.escape(n) for n in (_EU_MEMBERS | _US_TERMS | _UK_TERMS | _APAC_TERMS)
     if len(n) > 3},
    key=len, reverse=True,
)
GOVERNMENTAL_NAMES = re.compile(r"\b(" + "|".join(_JURISDICTION_NAMES) + r")\b", re.I)

# Eine Kennzeichnungsregel ist kein Marktverbot. Der EU-Trilog vom 5. März 2026
# beschränkt 31 Fleisch-Bezeichnungen, lässt „Burger" und „Wurst" aber
# ausdrücklich zu — Plant-Based Meat wird EU-weit frei verkauft. Das Radar las
# daraus „Route geschlossen", direkt neben seiner eigenen Marktzelle H1.
BLOCKADE_LABELLING = re.compile(
    r"\b(label(l?ing|s)?|naming|names?|denomination|designation|wording|"
    r"advertis(ing|ement)|marketing claim|terminology|\bterms?\b|"
    r"may not be called|cannot be called)\b",
    re.I,
)


def blockade_match(text: str, field_terms: list[str] | None = None):
    """Blockiert dieser Text DAS FELD — oder bloß irgendetwas?

    Ohne Feldbegriffe zählt nur Tier 1. Das ist die konservative Wahl: eine
    übersehene Blockade kostet eine H3-Aussage, eine erfundene behauptet einem
    Kunden gegenüber ein Verbot, das es nicht gibt.
    """
    # Eine Regel über NAMEN verschließt keinen Markt — vor allen anderen Prüfungen.
    if BLOCKADE_LABELLING.search(text):
        return None
    m = REG_GAP_EXPLICIT.search(text)
    if m:
        return m
    if not field_terms:
        return None
    if not (GOVERNMENTAL.search(text) or GOVERNMENTAL_NAMES.search(text)):
        return None      # mehrdeutige Blockade ohne hoheitlichen Akteur
    low = text.lower()
    for m in REG_GAP_OBJECT.finditer(text):
        window = low[max(0, m.start() - BLOCKADE_WINDOW):m.end() + BLOCKADE_WINDOW]
        if not any(t in window for t in field_terms):
            continue
        if BLOCKADE_LIFTED.search(window) or BLOCKADE_PROPOSED.search(window):
            continue          # das Verbot fällt gerade oder gibt es noch nicht
        return m
    return None


# Mehrere Felder in einer Query: Semikolon, Komma oder " vs " trennen. Die
# Trennzeichen sind bewusst schlicht — ein Nutzer, der vergleichen will, tippt
# genau so.
QUERY_SPLIT = re.compile(r"\s*(?:;|\bvs\.?\b|\bversus\b|,)\s*", re.I)
MAX_QUERY_TERMS = 4      # darüber wird der Bogen unlesbar und der Lauf teuer


def split_query_terms(query: str) -> list[str]:
    parts = [p.strip() for p in QUERY_SPLIT.split(query or "") if p.strip()]
    seen, out = set(), []
    for p in parts:
        k = p.lower()
        if k not in seen and len(p) >= Q_MIN_TERM:
            seen.add(k)
            out.append(p)
    return out[:MAX_QUERY_TERMS]


Q_MIN_TERM = 3


def slugify_term(term: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (term or "").lower()).strip("-")
    return (s or "field")[:40]


def field_terms_of(*sources: str) -> list[str]:
    """Feldbegriffe aus Query oder kuratierten ILIKE-Termen — klein, ohne %,
    ohne Füllwörter. Nur damit ist der Objektbezug einer Blockade prüfbar."""
    stop = {"and", "the", "for", "with", "based", "new", "technology", "tech"}
    out: set[str] = set()
    for s in sources:
        for tok in re.split(r"[^a-z0-9]+", (s or "").lower()):
            if len(tok) >= 4 and tok not in stop:
                out.add(tok)
    return sorted(out)

REG_GRANTED_TAGS = {
    "regulatory approval", "regulatory_approval", "fda approval", "fda_approval",
    "drug approval", "drug_approval", "gras", "gras_status", "market authorization",
    "market_authorization", "novel food approval",
}

# Absichts-Guard: Formulierungen, die eine Zulassung ERSTREBEN oder FORDERN, statt
# sie zu melden. Ohne diesen Filter zählt „Coalition To Advance Regulatory
# Approval" als Zulassung — also genau das Gegenteil dessen, was es belegt.
REG_INTENT = re.compile(
    r"\b(to advance|advance[sd]? (the )?regulatory|campaign|coalition|call(s|ed)? for|"
    r"push(es|ed)? for|lobb(y|ies|ying)|urge[sd]?|demand(s|ed)?|"
    r"seek(s|ing)? |applies for|appl(y|ied) for|submits?|submitted|awaiting|"
    r"pave the way|path(way)? to|road ?map|toward|prepar(e|es|ing)|"
    # „Nähert sich der Zulassung" ist der Beleg, dass es sie NICHT gibt.
    # Kalibrierlauf 2026-07-31: „Impossible Foods Approaches EU Approval
    # Following Second Positive EFSA Opinion" galt als erteilte EU-Zulassung und
    # hob ein regulatorisch blockiertes Feld auf H1.
    r"predict(s|ed)?|expect(s|ed)?|anticipat(e|es|ed)|forecast(s|ed)?|"
    r"opportunity for|write off|criticism of|"
    r"approach(es|ed|ing)?|near(s|ing|ed)? (approval|authorisation|authorization)|"
    r"clos(e|es|ing) in on|on track (for|to)|steps? closer|"
    r"positive opinion|draft opinion|recommend(s|ed)? (approval|authorisation)|"
    r"could|would|may |might |propose[sd]?|plan(s|ned)? to|aims? to)\b",
    re.I,
)

# Zulassende Behörde → Jurisdiktion. Für die Regulatorik-Dimension ist DAS die
# Attribution, nicht `regions`: `regions` markiert den Sitz des Unternehmens bzw.
# den Handlungsort der Geschichte. Beispiel aus dem Kalibrierlauf 2026-07-30:
# „Vivici Secures FDA 'No Questions' Letter" trägt regions=[EU] (niederländische
# Firma), belegt aber eine US-Zulassung. Ohne Behörden-Attribution wandert eine
# US-Zulassung in die EU-Zelle und macht ein blockiertes Feld handlungsfähig.
# Der Katalog war lebensmittel- und arzneimittelzentriert und damit die Ursache
# einer strukturellen Schieflage: korpusweit ließen sich 93,4 % der erteilten
# Zulassungen den USA zuordnen, 4,1 % der EU (Kalibrierlauf 2026-08-02). Das ist
# keine Eigenschaft der Welt, sondern des Katalogs — EASA, EMA, FCC, FAA, KBA und
# die nationalen EU-Behörden fehlten schlicht. Ein Feld wie „electric aircraft"
# konnte deshalb keine EU-Zulassung haben, obwohl seit 2020 eine EASA-
# Musterzulassung existiert.
AUTHORITY_JURISDICTION: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(fda|usda|fsis|gras|us ?da|food and drug administration|"
                r"fcc|faa|nhtsa|epa|nrc|cpsc|ftc|"
                r"federal (communications|aviation) (commission|administration)|"
                r"nuclear regulatory commission|"
                r"environmental protection agency)\b", re.I), "US"),
    (re.compile(r"\b(efsa|ema|chmp|easa|echa|european commission|eu commission|"
                r"dg sante|european medicines agency|european union aviation|"
                r"european food safety|eu novel foods?|novel foods? regulation|"
                r"kba|kraftfahrt-bundesamt|bfarm|paul[- ]ehrlich|anses|"
                r"bundesnetzagentur|arcep|agcom|ce mark(ing|ed)?|"
                r"eu (type[- ]approval|mdr|ivdr|ai act))\b", re.I), "EU"),
    (re.compile(r"\b(mhra|fsa|food standards agency|defra|ofcom|"
                r"uk civil aviation authority|caa)\b", re.I), "UK"),
    (re.compile(r"\b(israeli? ministry of health|israel moh)\b", re.I), "IL"),
    (re.compile(r"\b(sfa|singapore food agency|fsanz|food standards australia|"
                r"mhlw|mfds|cfsa|nmpa|pmda|caac|"
                r"china national medical products)\b", re.I), "APAC"),
]


# Zweiter Attributionsweg: die Jurisdiktion steht ausdrücklich im Text, ohne dass
# eine Behörde genannt wird — „First Precision Fermentation Dairy Approval In
# Israel" nennt kein Ministerium, ist aber eindeutig. Wird nur für bereits als
# 'granted' erkannte Signale ausgewertet und ist deshalb unkritisch.
JURISDICTION_PHRASE: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(u\.?s\.?|united states|american)[- ](gras|approval|clearance|"
                r"authorisation|authorization|approved)\b", re.I), "US"),
    (re.compile(r"\b(eu|european|europe)[- ](approval|clearance|authorisation|"
                r"authorization|approved)\b|\bnovel foods? (approval|authorisation)\b",
                re.I), "EU"),
    (re.compile(r"\b(in|for|across) israel\b|\bisraeli\b", re.I), "IL"),
    (re.compile(r"\b(uk|british)[- ](approval|clearance|authorisation|approved)\b|"
                r"\b(in|for) the uk\b", re.I), "UK"),
    (re.compile(r"\b(in|for) (singapore|japan|australia|new zealand|south korea|china)\b|"
                r"\bsingaporean\b", re.I), "APAC"),
]


# Ablehnung ist nicht Abwesenheit. Kalibrierlauf 2026-08-02, Feld „psychedelic
# therapy": das Radar meldete „5 approvals since 2023 — clear to act", und drei
# der vier sichtbaren Belege waren Meldungen über ABLEHNUNGEN („FDA rejects MDMA
# for PTSD"). Ursache ist der Tag-Pfad: die Stage-3-Klassifikation vergibt bei
# einer Ablehnungsmeldung plausibel den Tag „fda approval", und der Tag allein
# genügte. Ein negativer Bescheid muss den Zulassungspfad deshalb hart schlagen.
# Regulierungspfade, die neben dem gefragten herlaufen: Tierfutter, Heimtier-
# nahrung, Veterinärmedizin, Silage. Eine Freigabe dort belegt nichts für den
# Lebensmittel- oder Humanpfad.
OTHER_ROUTE = re.compile(
    r"\b(pet food|petfood|animal feed|feed material|feed additive|fodder|silage|"
    r"veterinary|animal nutrition|dog food|cat food|aquafeed)\b", re.I,
)
OTHER_ROUTE_TERMS = {"feed", "petfood", "fodder", "silage", "veterinary",
                     "aquafeed"}

REG_DENIED = re.compile(
    r"\b(reject(s|ed)|refus(es|ed)|declin(es|ed) to approve|turns? down|"
    r"denie[sd]|complete response letter|\bcrl\b|non[- ]approvable|"
    r"votes? against|fails? to (win|secure|gain) approval|"
    r"(approval|authoris?z?ation) (denied|rejected|refused|not granted))\b",
    re.I,
)

# Erlaubnis zu FORSCHEN ist nicht Erlaubnis zu VERKAUFEN. „FDA approves first
# xenotransplantation clinical trial" hob ein Feld ohne einzige Marktzulassung
# auf H1 „clear to act"; dieselbe Verwechslung machte aus IDE-Freigaben für
# Neuroimplantate einen freien Marktzugang. Das Stadienwort steht fast immer in
# der Überschrift.
REG_TRIAL_STAGE = re.compile(
    r"(\b(clinical trial|first[- ]in[- ]human|investigational|ind|ide|cta|"
    r"expanded access|compassionate use|pivotal study|"
    r"breakthrough (device )?designation|fast track designation|"
    r"orphan (drug )?designation)\b"
    r"|\bphase (1|2|3|i|ii|iii)\b"
    # „FDA approves Paradromics' brain-computer interface TRIAL" — zwischen Verb
    # und Stadienwort steht der Produktname, oft 40+ Zeichen. Ein enges Fenster
    # verfehlt genau die Fälle, um die es geht.
    r"|\b(approv|clear|authoris|authoriz|greenlight)\w*[^.]{0,70}?\b(trial|study|studies)\b"
    r"|\b(approval|clearance|permission) to (implant|test|study|conduct|begin|start)\b"
    r")",
    re.I,
)


def reg_authority(text: str) -> str | None:
    """Jurisdiktion einer Zulassung: genannte Behörde, sonst explizite Nennung."""
    for pat, juris in AUTHORITY_JURISDICTION:
        if pat.search(text):
            return juris
    for pat, juris in JURISDICTION_PHRASE:
        if pat.search(text):
            return juris
    return None


def reg_subtype(row, field_terms: list[str] | None = None) -> str:
    """Sub-Typ eines Regulatorik-Signals.

    'granted' — Zulassung erteilt / in Kraft                          → H1
    'filed'   — Antrag läuft, in Prüfung                              → H2
    'forming' — Pfad wird erst gebaut (Konsultation, Strategie, Ruf
                nach Reform) — noch kein nutzbarer Weg                → H3
    'gap'     — Blockade für DIESES Feld ausdrücklich benannt         → H3
    'other'   — regulatorisches Umfeld, aber KEINE Aussage über den
                Zulassungsweg                                → zählt für nichts

    Die Trennung 'filed' vs. 'forming' ist die eigentliche Kalibrierung: eine
    laufende Konsultation ist kein offener Zulassungsweg, sondern der Versuch,
    einen zu schaffen.

    'other' ist neu (Kalibrierlauf 2026-08-02) und behebt den folgenschwersten
    Fehler des Radars: 'forming' war der DEFAULT-Rückgabewert, also die Antwort
    auf „kein Muster hat gegriffen". Korpusweit fielen damit 70.603 von 76.262
    Regulatorik-Signalen (92,6 %) in einen Eimer, dessen Bedeutung „der
    Zulassungsweg wird gerade erst gebaut" ist. Im Feld Gentherapie stützten so
    11 von 13 EU-Signalen ein H3 „kein nutzbarer Weg", die über den Zulassungsweg
    NICHTS sagen — ein klinischer Hold, ein Rückzug aus Erstattungsgründen, ein
    Nachrichten-Roundup. Fehlende Mustererkennung ist keine Evidenz für
    Abwesenheit; sie ist Schweigen, und Schweigen gehört in eine eigene Kategorie.
    """
    text = f"{row.get('title_en') or ''} {row.get('summary_en') or ''}"
    intent = bool(REG_INTENT.search(text))

    tags_raw = row.get("tags")
    tags = json.loads(tags_raw) if isinstance(tags_raw, str) else (tags_raw or [])
    tagset = {str(t).strip().lower() for t in tags}
    tag_hit = bool(tagset & REG_GRANTED_TAGS)

    # Ein Tag allein genügt nicht — und seit dem Psychedelika-Fund genügt er auch
    # nicht mit Rückendeckung: „FDA criticism of MDMA-assisted therapy is an
    # opportunity" und „MAPS predicts FDA approval in 2024" trugen den Tag
    # `fda_approval` und hoben ein Feld mit NULL Zulassungen auf „clear to act".
    # Der Tag darf nur noch stützen, was der Text selbst als Entscheidung meldet.
    tag_ok = tag_hit and re.search(
        r"\b(approval|approved|authoris?z?ation|authoris?z?ed|cleared|clearance|"
        r"granted|no questions letter)\b", text, re.I)
    # Eine Zulassung auf einem ANDEREN Regulierungspfad räumt diesen nicht frei.
    # Die EU-Zelle von Cultivated Meat stand auf „clear to act", getragen von
    # Bene Meats Eintrag im Futtermittel-Katalog — eine Registrierung für
    # Tierfutter, nicht einmal eine Zulassung, und in keinem Fall eine für
    # Lebensmittel. Fragt jemand ausdrücklich nach dem Futtermittelpfad, bleibt
    # das Signal gültig.
    if OTHER_ROUTE.search(text) and not (
            field_terms and any(t in OTHER_ROUTE_TERMS for t in field_terms)):
        return "other"
    if (tag_ok or REG_GRANTED.search(text)) and not intent:
        # Vorzeichen und Stadium schlagen die Zulassungsformulierung — in dieser
        # Reihenfolge, weil ein abgelehnter Antrag zugleich ein Antrag ist.
        if REG_DENIED.search(text):
            return "denied"
        if REG_TRIAL_STAGE.search(text):
            return "trial"
        return "granted"
    if REG_DENIED.search(text):
        return "denied"
    if REG_TRIAL_STAGE.search(text):
        return "trial"
    if re.search(r"\b(applies for|applied for|submitted|submission|under review|"
                 r"pending|in review|dossier|awaiting (approval|decision))\b",
                 text, re.I):
        return "filed"
    if blockade_match(text, field_terms):
        return "gap"
    if REG_PATHWAY.search(text) or intent:
        return "forming"
    return "other"


# Marktreife-Marker: unterscheidet "Produkt angekündigt" von "im Handel".
# Pilot- und Demonstrationsanlagen belegen Machbarkeit, nicht Marktverfügbarkeit.
# Kalibrierlauf 2026-08-02: Direct Air Capture stand in der EU auf H1 („on the
# market"), gestützt auf Ucaneos Berliner Anlage — 150 t CO2/Jahr, kommerzieller
# Ausbau ab 2027. Das ist der Beweis, dass es funktioniert, nicht dass man es
# kaufen kann.
MARKET_PILOT = re.compile(
    r"\b(pilot|demonstration|demo (plant|facility|unit)|prototype|test ?bed|"
    r"first[- ]of[- ]a[- ]kind|proof of concept|trial (plant|run)|"
    r"pre[- ]commercial|research (facility|plant)|experiment)\b",
    re.I,
)

MARKET_SCALE = re.compile(
    r"\b(retail|shelves|shelf|supermarket|grocery|whole foods|walmart|tesco|"
    r"nationwide|roll ?out|scal(e|ing|es) (up|to)|commercial (launch|production|scale)|"
    r"mass production|distribution deal|listed (in|at)|available (in|at|now)|"
    # Belege für einen laufenden Markt, die keine Produktmeldung sind: Umsatz,
    # installierte Basis, Erstattung, Abnahmeverträge. Die Scout-Prüfung
    # 2026-08-02 fand reihenweise Felder, die genau daran scheiterten — Guardant
    # (>1 Mrd. $ Testumsatz) und Dexcom (13,4 Mrd. $ Markt) galten als „nicht am
    # Markt", weil ihre Produkteinführungen vor dem 36-Monats-Fenster lagen.
    r"subscribers?|installed base|units? (shipped|sold|delivered)|"
    r"reimbursed?|reimbursement|offtake|purchase agreement|"
    r"revenue|shipments?|in production|serial production)\b",
    re.I,
)

# Größenordnung — der Test, den alle vier Scouts der zweiten Runde unabhängig
# verlangten: „market calls need a magnitude test (installed base, mandated
# volume, catalogue availability), not a count of launch stories". Ein reifer
# Markt hört auf, Produktmeldungen zu erzeugen, nennt aber ständig seine Größe:
# 100 GWh europäischer Speicher, 3,6 Mio. verkaufte Wärmepumpen, 12 Mio.
# Starlink-Kunden, 6 GWth Geothermie-Fernwärme. Zahl PLUS Einheit — „100" allein
# sagt nichts, „100 GWh" schon.
MARKET_MAGNITUDE = re.compile(
    r"\b\d[\d.,]*\s?(%|percent|"
    r"[kmgt]w(h|th)?|kilowatt|megawatt|gigawatt|terawatt|"
    r"tonnes?|tons?|kt\b|mt\b|barrels?|litres?|liters?|"
    r"million|billion|bn\b|thousand|"
    r"units?|systems?|vehicles?|patients?|customers?|users?|subscribers?|"
    r"sites?|plants?|facilities|stores?|outlets?|centres?|centers?)\b",
    re.I,
)

# Meinungsstücke sehen wie Produktmeldungen aus, wenn man nur den Signaltyp
# ansieht. Die Scouts fanden „The Sodium Shift", „The Solid-State Illusion",
# „Beyond Lithium" und „The X Imperative" in den Zählern, die über H1 entscheiden
# — Sodium-Ion stand auf „9 commercial product launches" in den USA, deren vier
# sichtbare Belege null Produkteinführungen enthielten. Ein Essay über ein Feld
# ist kein Ereignis in ihm.
ESSAY_TITLE = re.compile(
    r"\b(imperative|inflection point|illusion|paradox|dilemma|reckoning|"
    r"playbook|blueprint|deep dive|explainer|state of (the|play)|"
    r"lessons (from|learned)|takeaways|what .{0,20}means|"
    r"^why\b|\bwhy .{0,40}(is|are|will|matters?|should|could|must)|"
    r"the (rise|fall|future|case|end|shift|pivot|promise|myth|decoupling|"
    r"hidden cost|next (wave|frontier|chapter)) of|"
    r"the \w+ (shift|illusion|imperative|paradox|era|age|reckoning|pivot|"
    r"playbook|reign|myth|promise|inflection)\b|"
    r"beyond \w+|rethinking|reimagining|the hidden|outlook for|"
    r"signals? (a|an|the)|accelerat(es|ing) [a-z ]{0,24}(transition|shift)|"
    r"what .{0,30}(gets|got) (right|wrong)|the .{0,20}(era|age|dawn) of)\b",
    re.I,
)

# Ein Produktstart, der ein Markt-H1 tragen soll, muss nach einer Transaktion
# klingen, nicht nach einer Ankündigung. „unveils"/„showcases"/„previews" sind
# bewusst NICHT hier: sie belegen einen Prototyp und tragen H2.
LAUNCH_COMMERCIAL = re.compile(
    r"\b(launch(es|ed)?|debuts?|introduc(es|ed)|begins? (selling|shipping|deliveries)|"
    r"now (available|on sale|shipping)|starts? (sales|production|deliveries)|"
    r"ships?|shipping|deliver(s|ed|ies)|on sale|goes on sale|opens? (orders|sales)|"
    r"available (in|at|now|from)|price[ds]? (at|from)|enters? the market)\b",
    re.I,
)

# Nachfrage-Primitive jenseits der Verbraucherstimme. Der Energie-Scout traf den
# Kern: Nachfrage nach Netzspeichern, Offshore-Wind oder Batterierecycling kommt
# als Auktion, PPA, Abnahmevertrag oder Erstattungsentscheid — nie als
# „Verbrauchersignal". Vier Felder mit veröffentlichten Zuschlagspreisen standen
# deshalb auf „demand unevidenced".
DEMAND_MARKERS = re.compile(
    r"\b(auction|tender|procure(s|d|ment)|offtake|power purchase agreement|\bppa\b|"
    r"order book|orders? (for|of|worth)|contract(ed|s)? (to supply|for)|"
    r"subscribers?|installed base|reimburs(ed|ement)|coverage decision|"
    r"adoption rate|uptake|penetration|market share|prescriptions?|"
    r"shipments?|deployments?|customers?|users?)\b",
    re.I,
)

# ---------------------------------------------------------------------------
# Schwellen
# ---------------------------------------------------------------------------
def _title(row) -> str:
    return row.get("title_en") or ""


def _text(row) -> str:
    return f"{row.get('title_en') or ''} {row.get('summary_en') or ''}"


def mentions_field(row, field_terms: list[str] | None) -> bool:
    """Spricht dieses Signal vom Feld — oder wurde es über ein Tag eingesammelt?

    Der Scope kommt aus Volltextsuche über Titel + Zusammenfassung + Tags. Über
    den Tag-Weg geraten Signale hinein, die das Feld nie erwähnen: „CIRANDA
    Announces Two New Baking Chips" trug die Marktzelle von „organ on a chip",
    „Ponnath Secures Organic Pork Supply via Vertical Integration" die von
    „vertical farming". Für schwellenrelevante Zählungen muss der Feldbegriff im
    Text stehen; fürs bloße Mitzählen im Scope-Total genügt der Treffer.
    """
    if not field_terms:
        return True
    low = _text(row).lower()
    # EIN Begriff genügt — bewusst, nach Messung. Zwei zu verlangen entfernt zwar
    # „CIRANDA Announces Two New Baking Chips" aus „organ on a chip", kostet aber
    # weit mehr: Zulassungsmeldungen nennen das Feld oft nur mit einem Wort („FDA
    # approves Moderna's COVID vaccine" für „mrna vaccine"; Geothermie-Meldungen
    # ohne „energy"). Im Lauf 2026-08-02 kippte die strengere Regel mRNA, CRISPR
    # und Digital Therapeutics von belegtem H1 in eine FALSCHE H3-Aussage — und
    # eine falsche Verneinung ist teurer als eine verrauschte Belegliste. Die
    # verbleibende Homonym-Verunreinigung gehört in die Scope-Verfeinerung
    # (Teilfeld-Zerlegung), nicht in diese Schwelle.
    return any(t in low for t in field_terms)


def scope_verticals(rows: list[dict], floor: float = 0.05) -> set[str]:
    """Die Vertikalen, aus denen ein Feld wirklich besteht.

    Zweite Verteidigungslinie gegen Homonyme, dort wo Wortabgleich versagt:
    „EFSA Clears Genetically Modified Corynebacterium for L-Leucine Production"
    enthält das Wort „additive" (Lebensmittel-Zusatzstoff) und lieferte damit die
    Regulatorik-Zelle von „additive manufacturing"; „CIRANDA Announces Two New
    Baking Chips" enthält „chip" und trug die Marktzelle von „organ on a chip".
    Beide Signale sind FOOD, beide Felder sind es nicht.

    Der Anteilsboden statt „nur die größte": Felder wie grüner Wasserstoff sind
    echt mehrvertikal (ECO/TECH/BIZ). Abgeschnitten wird nur der lange Schwanz.
    """
    counts: dict[str, int] = {}
    for r in rows:
        v = r.get("primary_vertical")
        if v:
            counts[v] = counts.get(v, 0) + 1
    total = sum(counts.values())
    if total < 40:          # zu wenig, um einen Schwanz zu erkennen
        return set(counts)
    return {v for v, n in counts.items() if n / total >= floor}


def _sig_tokens(title: str) -> frozenset:
    stop = {"the", "for", "and", "with", "from", "new", "its", "has", "have",
            "will", "that", "this", "into", "over", "after", "says"}
    return frozenset(t for t in re.split(r"[^a-z0-9]+", title.lower())
                     if len(t) > 3 and t not in stop)


def dedupe_events(rows: list[dict], window_days: int = 30) -> list[dict]:
    """Ein Ereignis, drei Meldungen — für einen Schwellenwert ist das EINS.

    „3 approvals since 2024" für Mycoprotein/US war ein einziger GRAS-Bescheid,
    berichtet von Green Queen, AgFunderNews und vegconomist; vier der
    Cultivated-Meat-Belege waren dasselbe Believer-Meats-Ereignis. Zwei Signale
    gelten als dasselbe Ereignis, wenn sich ihre bedeutungstragenden Titelwörter
    zu >= 60 % decken und sie hoechstens `window_days` auseinanderliegen.

    Über 400 Zeilen wird nicht dedupliziert: dort ist der quadratische Vergleich
    teuer und die Zählung so weit über jeder Schwelle, dass Duplikate nichts
    entscheiden.
    """
    if len(rows) > 400:
        return rows
    kept: list[tuple[frozenset, date | None, dict]] = []
    for r in sorted(rows, key=lambda r: r["event_date"] or date.min):
        toks = _sig_tokens(_title(r))
        d = r["event_date"]
        dup = False
        for ktoks, kd, _ in kept:
            if not toks or not ktoks:
                continue
            if d and kd and abs((d - kd).days) > window_days:
                continue
            overlap = len(toks & ktoks) / min(len(toks), len(ktoks))
            if overlap >= 0.6:
                dup = True
                break
        if not dup:
            kept.append((toks, d, r))
    return [r for _, _, r in kept]


MIN_N_REGULATORY = 2      # unter 2 Regulatorik-Signalen: keine Aussage
# Asymmetrische Beweislast — der wichtigste Grundsatz dieser Datei.
# Alle sieben Scouts der Prüfung 2026-08-02 fanden unabhängig dasselbe Muster:
# das Radar VERWEIGERTE die Aussage bei n=2 und BEHAUPTETE „kein Weg zum Markt"
# bei n=3. Das ist die Beweislast verkehrt herum. Eine positive Aussage („es gibt
# eine Zulassung") stützt sich auf einen gefundenen Beleg; eine negative („es
# gibt keine") stützt sich darauf, dass ein Beleg gefunden WORDEN WÄRE — und
# braucht deshalb den Nachweis, dass in dieser Jurisdiktion überhaupt
# hingeschaut wurde. Negative Schlüsse liegen ab hier durchgängig höher.
MIN_N_NEGATIVE = 6        # Untergrenze für JEDE Absenz-Aussage (H3 ohne Blockade)

# Gemessene Beobachtbarkeit je Jurisdiktion: Anteil der korpusweit ZUORDENBAREN
# erteilten Zulassungen. Messung 2026-08-02 über 76.262 Regulatorik-Signale;
# `scripts/measure_reg_coverage.py --check` rechnet sie nach und meldet nur, wenn
# eine Jurisdiktion die Schwelle überquert — nur dann ändert sich Verhalten.
#
#     US 91,6 %  ·  EU 4,6 %  ·  APAC 3,1 %  ·  IL 0,5 %  ·  UK 0,2 %
#
# (Die Grundmenge fiel von 1.331 auf 586 zuordenbare Zulassungen, seit ein
# Zulassungs-TAG allein nicht mehr zählt — rund 2.400 Signale trugen ihn, ohne
# eine Entscheidung zu melden. Die Anteile blieben stabil.)
#
# Diese Zahl entscheidet, ob „hier ist keine Zulassung zu sehen" eine Aussage
# über die WELT oder über UNSERE QUELLEN ist. Bei 4 % EU-Abdeckung ist sie eine
# über die Quellen — und genau daraus entstanden die schwersten Fehlaussagen der
# Fachprüfung: „kein Zulassungsweg in der EU" für mRNA-Impfstoffe, CAR-T,
# Gentherapie, Insektenprotein und Mycoprotein, allesamt in der EU zugelassen.
#
# Die Schwelle sperrt Absenz-Schlüsse dort, wo wir nicht hinsehen können.
# POSITIVE Befunde (eine gefundene Zulassung, ein benanntes Verbot) bleiben in
# jeder Jurisdiktion zulässig — sie hängen nicht von Abdeckung ab.
REG_COVERAGE_SHARE = {"US": 0.916, "EU": 0.046, "APAC": 0.031, "IL": 0.005,
                      "UK": 0.002}
MIN_COVERAGE_FOR_ABSENCE = 0.10
# Eine EINZELNE Zulassungsmeldung trägt keine Jurisdiktions-Aussage: im
# Kalibrierlauf 2026-08-02 hob ein einziges fehlklassifiziertes Silage-Signal
# Precision Fermentation in der EU auf H1 (Scope-Verunreinigung, vgl. §7.3).
# Echte Zulassungen werden mehrfach berichtet — die acht US-GRAS-Freigaben
# ebenso wie die zwei israelischen.
MIN_N_GRANTED = 2
MIN_N_MARKET = 3
MIN_N_ADOPTION = 3
MIN_N_TECH_FALLBACK = 20  # ohne CPC-Anker: mindestens so viele semantische Signale
# Ein Patentanker darf die Reife eines Felds nur setzen, wenn die Klasse das Feld
# auch beschreibt. Gemessen 2026-08-02 (Containment = Anteil der Klasse, der im
# Feld liegt): B33Y/Additive Manufacturing 0,205 · H01M/Li-Ionen 0,111 ·
# H10K/Perowskit 0,101 gegen G06N/Neuromorphic 0,035 · G06N/LLM 0,033 ·
# G06N/BCI 0,014. Die Schwelle liegt zwischen den Gruppen.
ANCHOR_MIN_CONTAINMENT = 0.09
PATHWAY_WINDOW_MONTHS = 36   # Konsultationen veralten
LAUNCH_WINDOW_MONTHS = 36    # Produktstarts: nur die jüngeren zählen
# Zulassungen sind dauerhaft und werden ohne Fenster gezählt.
MARKET_TAKEOFF_SETTLED_YEARS = 2  # Markt-Takeoff muss so lange her sein für H1

# Etablierungs-Gate: kumulative Markt-Historie des Scopes statt Klassen-Takeoffs.
# Kalibriert 2026-08-02 an 8 Fällen: diffundierte Technologien (Li-Ion, Solar,
# EV, Wärmepumpen) haben ihr erstes aktives Marktjahr 2010-2012 und >=8 aktive
# Jahre; junge Felder (Quantum, Precision Fermentation, Solid-State, Cultivated
# Meat) starten 2020-2021 mit <=7 aktiven Jahren. Acht Jahre Abstand zwischen
# den Gruppen — die Schwellen liegen in der Mitte, nicht an der Kante.
# Die CPC-Klassen-Takeoffs sind als Alternative geprüft und verworfen: H01M
# meldet Patent-Takeoff "2026" (Frontfile-Artefakt), A23C Markt-Takeoff "2021"
# (die Alt-Protein-Welle selbst, nicht Milchwirtschaft).
ESTABLISHED_MIN_FIRST_AGE = 10   # erstes aktives Marktjahr min. so viele Jahre her
ESTABLISHED_MIN_ACTIVE_YEARS = 8 # Jahre mit >=3 Marktsignalen
ESTABLISHED_MIN_LAUNCHES = 30    # kumulative Produktstarts über die Historie
ESTABLISHED_YEAR_MIN_N = 3       # so viele Marktsignale machen ein Jahr "aktiv"

SCHEMA = """
CREATE TABLE IF NOT EXISTS radar_configs (
    id SERIAL PRIMARY KEY,
    slug TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    dimension_set TEXT NOT NULL DEFAULT 'strategic',
    regions JSONB DEFAULT '[]',
    window_months INTEGER DEFAULT 48,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS radar_scopes (
    id SERIAL PRIMARY KEY,
    config_id INTEGER REFERENCES radar_configs(id) ON DELETE CASCADE,
    slug TEXT NOT NULL,
    label TEXT NOT NULL,
    include_terms JSONB DEFAULT '[]',
    exclude_terms JSONB DEFAULT '[]',
    sort_order INTEGER DEFAULT 0,
    UNIQUE (config_id, slug)
);
CREATE TABLE IF NOT EXISTS radar_runs (
    id SERIAL PRIMARY KEY,
    config_id INTEGER REFERENCES radar_configs(id) ON DELETE CASCADE,
    n_scopes INTEGER,
    n_cells INTEGER,
    n_signals INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS radar_cells (
    id SERIAL PRIMARY KEY,
    run_id INTEGER REFERENCES radar_runs(id) ON DELETE CASCADE,
    scope_slug TEXT NOT NULL,
    dimension TEXT NOT NULL,
    region TEXT NOT NULL,
    horizon TEXT,                 -- 'H1'|'H2'|'H3'|NULL = unbekannt
    score REAL,                   -- stetige Reife 0..1, wo verfügbar
    n_signals INTEGER DEFAULT 0,
    method TEXT,                  -- 'cpc_takeoff'|'gates'|'semantic_mix'
    rationale TEXT,               -- Klartext-Begründung für das Readout
    evidence JSONB DEFAULT '[]',  -- Trend-IDs, die das Gate ausgelöst haben
    override_horizon TEXT,        -- Analyst-Override (Option E)
    override_note TEXT
);
CREATE INDEX IF NOT EXISTS idx_radar_cells_run ON radar_cells (run_id, scope_slug);
CREATE TABLE IF NOT EXISTS radar_scope_trends (
    run_id INTEGER REFERENCES radar_runs(id) ON DELETE CASCADE,
    scope_slug TEXT NOT NULL,
    trend_id INTEGER NOT NULL,
    PRIMARY KEY (run_id, scope_slug, trend_id)
);
CREATE INDEX IF NOT EXISTS idx_radar_scope_trends_trend
    ON radar_scope_trends (trend_id);
"""


def migrate() -> None:
    with get_connection() as conn:
        conn.executescript(SCHEMA)
        # Additiv nachgezogen (2026-07-30): regulierte Domänen koppeln Markt an
        # Zulassung. Idempotent, damit bestehende Installationen mitziehen.
        conn.executescript(
            "ALTER TABLE radar_configs ADD COLUMN IF NOT EXISTS regulated "
            "BOOLEAN DEFAULT false;"
        )
        # Query-Radare (2026-07-30). Alle Defaults erhalten das bisherige
        # Verhalten, damit die geseedeten Radare kein Re-Seed brauchen.
        conn.executescript(
            "ALTER TABLE radar_configs ADD COLUMN IF NOT EXISTS kind "
            "TEXT NOT NULL DEFAULT 'curated';"
            "ALTER TABLE radar_configs ADD COLUMN IF NOT EXISTS query_text TEXT;"
            "ALTER TABLE radar_configs ADD COLUMN IF NOT EXISTS archived "
            "BOOLEAN DEFAULT false;"
            "ALTER TABLE radar_scopes ADD COLUMN IF NOT EXISTS selector "
            "TEXT NOT NULL DEFAULT 'terms';"
            "ALTER TABLE radar_scopes ADD COLUMN IF NOT EXISTS query_text TEXT;"
            "ALTER TABLE radar_scopes ADD COLUMN IF NOT EXISTS phrase TEXT;"
            "ALTER TABLE radar_scopes ADD COLUMN IF NOT EXISTS centroid BYTEA;"
            # Cluster-Radare (2026-08-02): ein Feld ist kein getippter Begriff
            # mehr, sondern ein aus den Embeddings entstandenes Cluster. Die
            # Herkunft steht explizit da, damit `resolve_scope` sie auflösen kann
            # und ein Leser sieht, woher das Feld stammt.
            "ALTER TABLE radar_scopes ADD COLUMN IF NOT EXISTS cluster_run_id INTEGER;"
            "ALTER TABLE radar_scopes ADD COLUMN IF NOT EXISTS cluster_idx INTEGER;"
            "ALTER TABLE radar_scopes ADD COLUMN IF NOT EXISTS meta JSONB;"
        )
        # Die Grundlage einer Zelle (2026-08-02): granted/denied/blockade/filed/
        # trial vs. silent/uncovered/unreadable/unregulated/blind/unconfirmed.
        # Ohne sie sind alle sechs Schweige-Gründe im Frontend derselbe Strich —
        # die gesamte Kalibrierarbeit bleibt für den Nutzer unsichtbar.
        conn.executescript(
            "ALTER TABLE radar_cells ADD COLUMN IF NOT EXISTS basis TEXT;"
            "ALTER TABLE radar_cells ADD COLUMN IF NOT EXISTS lead_time JSONB;"
            "ALTER TABLE radar_runs ADD COLUMN IF NOT EXISTS readouts JSONB;"
        )
        conn.commit()
    log.info("radar_* Tabellen migriert")


# Reifegrad-Rang: kleiner = reifer. Für die Kopplung regulierter Domänen.
_RANK = {"H1": 1, "H2": 2, "H3": 3}
_UNRANK = {1: "H1", 2: "H2", 3: "H3"}


def couple_market_to_regulation(market: dict, regulatory: dict, region: str) -> dict:
    """In regulierten Domänen kann der Markt nicht reifer sein als die Zulassung.

    Das ist die kausale Aussage hinter dem Owner-Beispiel: in der EU ist Precision
    Fermentation nicht deshalb H3, weil keine Produkte gemeldet würden, sondern
    weil ohne Zulassung keine geben KANN. Produktmeldungen mit EU-Bezug betreffen
    dann Auslandsstarts europäischer Firmen — die Kopplung fängt genau diese
    Fehlzuordnung ab, die `regions` allein nicht auflösen kann.
    """
    mh, rh = market.get("horizon"), regulatory.get("horizon")
    if not mh or not rh:
        return market
    if _RANK[mh] >= _RANK[rh]:
        return market

    # Die Kopplung darf nur auf einem POSITIVEN regulatorischen Befund beruhen.
    # Fachprüfung 2026-08-02: bei SAF/US schrieb das Radar wörtlich „7 commercial
    # product launches — on the market. Capped at H3 …" — es hatte die richtige
    # Antwort, erkannte den Widerspruch und löste ihn zugunsten des SCHWÄCHEREN
    # Schlusses auf, indem es eine Begründung erfand, warum der starke Beleg
    # nicht zählt. Dasselbe zerstörte GLP-1/US, Gentherapie/EU und die
    # DiGA-Marktzelle. Eine aus Schweigen abgeleitete Regulatorik-Aussage darf
    # beobachteten Handel nicht überschreiben.
    if regulatory.get("basis") not in ("granted", "denied", "blockade",
                                      "filed", "trial"):
        return market
    # Handels-Evidenz schlägt die Kopplung ebenfalls: wer nachweislich Umsatz
    # macht, tut das nicht ohne Marktzugang — dann ist die Regulatorik-Zelle
    # falsch, nicht der Markt.
    if market.get("basis") == "trading":
        return market
    capped = _UNRANK[_RANK[rh]]
    return {
        **market,
        "horizon": capped,
        "score": min(market.get("score") or 1.0, regulatory.get("score") or 1.0),
        "method": market["method"] + "+reg_coupled",
        "rationale": (
            f"{market['rationale']} Capped at {capped} because {region} is "
            f"regulatorily {rh}: without an approval there is no lawful market — "
            "the product signals then describe launches outside this "
            "jurisdiction."
        ),
    }


# ---------------------------------------------------------------------------
# Scope-Auflösung
# ---------------------------------------------------------------------------
# Die Spalten SIND der Vertrag zwischen Scope-Auswahl und Zellenlogik: jede
# Auswahlart muss exakt diese Form liefern, dann bleiben alle cell_*-Funktionen
# unverändert. Zeitachse ist raw_entries.published_date — `sort_date` ist für
# 52 % der Zeilen NULL.
SCOPE_COLUMNS = """t.id, t.title_en, t.summary_en, t.trend_signal_type, t.regions,
               t.tags, t.pestel, t.primary_vertical, t.source_name,
               COALESCE(r.published_date, t.created_at)::date AS event_date,
               (t.tags IS NOT NULL AND jsonb_array_length(t.tags) > 0) AS semantic"""

# MUSS wortgleich zum Index `idx_trends_fts` bleiben — und zu FTS_VECTOR in
# frontend/src/app/api/search/route.ts:39-41. Jede Abweichung degradiert still
# von einem 6-ms-Index-Scan auf einen Seq Scan über 1,13 Mio. Zeilen; das Ergebnis
# bleibt korrekt, nur eben 250-2400× langsamer. Der Test in
# tests/test_radar_query.py hält beide Fassungen zeichengleich.
FTS_VECTOR = (
    "to_tsvector('english', coalesce(t.title_en,'') || ' ' || "
    "coalesce(t.summary_en,'') || ' ' || coalesce(t.tags::text,''))"
)

# Ober- und Untergrenze einer Query-Treffermenge.
MAX_SCOPE_ROWS = 25_000   # darüber ist eine Query kein "Feld" mehr
# Cluster werden im Batch gerechnet, nicht im Request — dort darf mehr geladen
# werden. Die Grenze schützt nur den Speicher, nicht eine Antwortzeit.
MAX_CLUSTER_ROWS = 40_000
MIN_SCOPE_ROWS = 60       # darunter verweigert das Radar die Aussage


def load_scope_signals(conn, include: list[str], exclude: list[str]) -> list[dict]:
    """Alle Trends eines Technologiefelds laden — kuratierter Term-Pfad.

    Term-basiert (ILIKE) mit expliziten Ausschlüssen — auditierbar und ohne
    GPU-Abhängigkeit. Der Ausschluss ist nicht Kosmetik: ein naives
    '%fermentation%' fängt traditionelle Fermentation, Silage- und
    Futtermittelzusätze mit ein (docs/radar_redesign_proposal.md §6.4).
    """
    sql = f"""
        SELECT {SCOPE_COLUMNS}
        FROM trends t
        LEFT JOIN raw_entries r ON r.id = t.raw_entry_id
        WHERE (t.title_en ILIKE ANY(%s) OR t.summary_en ILIKE ANY(%s))
    """
    params: list = [include, include]
    if exclude:
        sql += " AND NOT (t.title_en ILIKE ANY(%s))"
        params.append(exclude)
    return conn.execute(sql, tuple(params)).fetchall()


def build_query_sql(
    query: str,
    phrase: str | None = None,
    ids: list[int] | None = None,
    limit: int = MAX_SCOPE_ROWS,
) -> tuple[str, list]:
    """SQL + Parameter für einen FTS-ausgewählten Scope. PUR, ohne DB testbar.

    `query`  — die Basis-Query des Radars (bindet das gesamte Feld)
    `phrase` — zusätzliche Teilfeld-Phrase (UND-verknüpft)
    `ids`    — optionale Einschränkung auf eine vorab bestimmte Trend-Menge
               (Zentroid-Zuweisung); wirkt zusätzlich zur Query, nie statt ihrer,
               damit ein gespeichertes Teilfeld nie aus seinem Radar herauswächst.

    Parser ist `websearch_to_tsquery` — die nutzerseitige Variante (Phrasen in
    Anführungszeichen, OR, führendes Minus). NIE `to_tsquery`: das wirft bei
    beliebiger Nutzereingabe eine Exception.
    """
    sql = f"""
        SELECT {SCOPE_COLUMNS}
        FROM trends t
        LEFT JOIN raw_entries r ON r.id = t.raw_entry_id
        WHERE {FTS_VECTOR} @@ websearch_to_tsquery('english', %s)
    """
    params: list = [query]
    if phrase:
        sql += f" AND {FTS_VECTOR} @@ websearch_to_tsquery('english', %s)"
        params.append(phrase)
    if ids is not None:
        sql += " AND t.id = ANY(%s)"
        params.append(ids)
    sql += " LIMIT %s"
    params.append(int(limit))
    return sql, params


def count_query_terms(conn, query: str) -> list[tuple[str, int]]:
    """Trefferzahl je Begriff — für Vergleichs-Queries der einzig sinnvolle
    Vorab-Flug: `a; b; c` als ein tsquery zu zählen misst nichts."""
    return [(term, count_query_signals(conn, term))
            for term in (split_query_terms(query) or [query])]


def count_query_signals(conn, query: str) -> int:
    """Trefferzahl der nackten Basis-Query (~6 ms) — der Vorab-Flug.

    Entscheidet vor jeder Arbeit, ob eine Query zu breit oder zu dünn ist, damit
    ein pathologischer Fall nicht erst das Concurrency-Gate blockiert.
    """
    row = conn.execute(
        f"SELECT count(*)::int AS n FROM trends t "
        f"WHERE {FTS_VECTOR} @@ websearch_to_tsquery('english', %s)",
        (query,),
    ).fetchone()
    return int(row["n"]) if row else 0


def load_query_signals(
    conn,
    query: str,
    *,
    phrase: str | None = None,
    ids: list[int] | None = None,
    limit: int = MAX_SCOPE_ROWS,
) -> list[dict]:
    """Wie load_scope_signals, aber über Postgres-FTS ausgewählt."""
    sql, params = build_query_sql(query, phrase, ids, limit)
    return conn.execute(sql, tuple(params)).fetchall()


def load_cluster_signals(conn, run_id: int, cluster_idx: int,
                         limit: int = MAX_CLUSTER_ROWS) -> list[dict]:
    """Alle Trends eines Foresight-Clusters.

    Der Cluster-Pfad ist der einzige, der sein Feld nicht über Wörter definiert,
    sondern über die Lage im Embedding-Raum. Genau das war der Grund für die
    Umstellung: eine getippte Query trennt Felder schlecht (die Punkte
    unterschieden sich zu wenig) und ihre Zusammensetzung ist für den Leser
    nicht nachvollziehbar. Ein Cluster bringt seine eigenen Belege mit — die
    fünf zentralsten Signale sind seine Definition.

    Sortiert nach Datum absteigend und gedeckelt: die größten TECH-Cluster haben
    über 40.000 Mitglieder, und die Zellenlogik braucht keine vollständige
    Aufzählung, sondern Repräsentativität über die Zeit.
    """
    sql = f"""
        SELECT {SCOPE_COLUMNS}
        FROM foresight_cluster_members m
        JOIN trends t ON t.id = m.trend_id
        LEFT JOIN raw_entries r ON r.id = t.raw_entry_id
        WHERE m.run_id = %s AND m.cluster_idx = %s
        ORDER BY COALESCE(r.published_date, t.created_at) DESC
        LIMIT %s
    """
    return conn.execute(sql, (run_id, cluster_idx, limit)).fetchall()


def resolve_scope(conn, scope: dict) -> list[dict]:
    """DIE Naht. Bestimmt, welche Trends ein Feld ausmachen.

    Verzweigt auf `scope['selector']`, nicht auf NULL-Schnüffelei:
      'terms'  → kuratierter ILIKE-Pfad, unverändert
      'query'  → FTS über Basis-Query (+ optionale Teilfeld-Phrase)

    Alle drei Wege liefern dieselben 10 Spalten, weshalb sämtliche
    cell_*-Funktionen davon nichts mitbekommen.
    """
    selector = (scope.get("selector") or "terms").lower()
    if selector == "cluster":
        return load_cluster_signals(conn, scope["cluster_run_id"],
                                    scope["cluster_idx"])
    if selector == "query":
        return load_query_signals(
            conn,
            scope.get("query_text") or "",
            phrase=scope.get("phrase"),
            ids=scope.get("ids"),
        )
    inc = scope.get("include_terms")
    inc = json.loads(inc) if isinstance(inc, str) else (inc or [])
    exc = scope.get("exclude_terms")
    exc = json.loads(exc) if isinstance(exc, str) else (exc or [])
    return load_scope_signals(conn, inc, exc)


def scope_field_terms(scope: dict) -> list[str]:
    """Feldbegriffe eines Scopes — egal ob kuratiert oder als Query definiert.

    Sie entscheiden, ob ein Signal das Feld überhaupt NENNT und ob eine Blockade
    dieses Feld trifft. Beim kuratierten Pfad stammen sie aus den ILIKE-Termen
    (ohne %), beim Query-Pfad aus der Query selbst.
    """
    if (scope.get("selector") or "terms").lower() == "query":
        return field_terms_of(scope.get("query_text") or "",
                              scope.get("phrase") or "")
    inc = scope.get("include_terms")
    inc = json.loads(inc) if isinstance(inc, str) else (inc or [])
    return field_terms_of(*[str(t).replace("%", " ") for t in inc])


def _market_history(rows: list[dict], today: date) -> dict:
    """Kumulative Markt-Historie eines Scopes — der Diffusions-Nachweis.

    News berichten über VERÄNDERUNG, nicht über Zustand: eine längst
    diffundierte Technologie (Li-Ionen) erzeugt im 36-Monats-Fenster
    Forschungs- und Inkrement-Meldungen, aber niemand schreibt 2026 "Verbraucher
    kaufen jetzt Lithium-Akkus". Ein Fenster-Blick liest reife Technik deshalb
    systematisch als unreif. Die Historie über den ganzen Korpus ist dagegen
    eindeutig: Marktsignale in vielen Jahren, beginnend weit vor dem Fenster.
    """
    years: dict[int, int] = {}
    launches = 0
    for r in rows:
        st = r["trend_signal_type"]
        is_market = st == "product_launch" or (st == "market_shift" and r["semantic"])
        if not is_market or not r["event_date"]:
            continue
        years[r["event_date"].year] = years.get(r["event_date"].year, 0) + 1
        if st == "product_launch":
            launches += 1
    active = sorted(y for y, n in years.items() if n >= ESTABLISHED_YEAR_MIN_N)
    first = active[0] if active else None
    established = bool(
        first is not None
        and first <= today.year - ESTABLISHED_MIN_FIRST_AGE
        and len(active) >= ESTABLISHED_MIN_ACTIVE_YEARS
        and launches >= ESTABLISHED_MIN_LAUNCHES
    )
    return {"first_year": first, "active_years": len(active),
            "launches": launches, "established": established}


def _recent(rows: list[dict], months: int, today: date) -> list[dict]:
    cutoff = today - timedelta(days=int(months * 30.44))
    return [r for r in rows if r["event_date"] and r["event_date"] >= cutoff]


# ---------------------------------------------------------------------------
# Dimensionen
# ---------------------------------------------------------------------------
def cell_regulatory(rows: list[dict], region: str, today: date,
                    regulated: bool = True,
                    field_terms: list[str] | None = None) -> dict:
    """Meilenstein-Gates pro Jurisdiktion.

    Zulassung erteilt → H1 · Antrag läuft → H2 · Pfad erst im Aufbau / Lücke → H3.

    `regulated` steuert, was ABWESENHEIT bedeutet — der Li-Ionen-Fund vom
    2026-08-02: für Batterien existiert kein Zulassungsregime, und "keine
    Zulassung gefunden" wurde trotzdem als H3 "blockiert" gelesen. In einer
    unregulierten Domäne ist Abwesenheit von Zulassungen aber KEINE Aussage über
    den Marktzugang; H3 braucht dort positive Gegenwind-Evidenz (Verbote,
    Blockaden). Ohne die schweigt die Zelle.

    Zuordnung zur Jurisdiktion: für 'granted' zählt ausschließlich die im Text
    genannte **Behörde** (FDA → US, EFSA → EU …). Ein Zulassungssignal ohne
    erkennbare Behörde belegt für keine Region etwas und wird nicht als Zulassung
    gewertet. Für die schwächeren Sub-Typen genügt `regions`, weil eine
    Konsultation ohne Behördennennung die Aussage nicht überhöht.
    """
    regs = [r for r in rows if r["trend_signal_type"] == "regulation"
            and mentions_field(r, field_terms)]

    # Eine Zulassung bleibt eine Zulassung, egal wie Stage 3 das Signal getypt
    # hat. Fund 2026-08-02: die beiden FDA-Zulassungen für orales Wegovy und
    # Orforglipron liegen im Korpus als `product_launch` — die Regulatorik-Zelle
    # sah sie nie und meldete für den größten Medikamentenstart der Geschichte
    # „kein Zulassungsweg in den USA". Nur der GRANTED-Pfad öffnet sich für alle
    # Signaltypen; die schwächeren Sub-Typen blieben sonst reines Rauschen.
    candidates = list(regs) + [
        r for r in rows
        if r["trend_signal_type"] != "regulation" and mentions_field(r, field_terms)
        and reg_subtype(r, field_terms) == "granted"
    ]

    buckets: dict[str, list] = {k: [] for k in
                                ("granted", "denied", "filed", "trial",
                                 "forming", "gap", "other")}
    for r in candidates:
        st = reg_subtype(r, field_terms)
        if st == "granted":
            # Nur die genannte Behörde entscheidet, für welche Region die
            # Zulassung zählt — nicht der Firmensitz aus `regions`. Für die
            # Weltspalte zählt sie unabhängig von der Behörde: „irgendwo
            # zugelassen" ist genau die Frage, die dort beantwortet wird.
            if region == WORLD or reg_authority(_text(r)) == region:
                buckets["granted"].append(r)
            continue
        if not in_jurisdiction(r, region):
            continue
        buckets[st].append(r)

    for k in ("filed", "trial", "forming", "gap", "denied"):
        buckets[k] = _recent(buckets[k], PATHWAY_WINDOW_MONTHS, today)
    granted = dedupe_events(buckets["granted"])
    denied = dedupe_events(buckets["denied"])
    filed, trial = buckets["filed"], buckets["trial"]
    forming, gaps = buckets["forming"], buckets["gap"]

    # Der Zulassungsweg-Bestand: alles, was ÜBER DEN WEG etwas sagt. 'other'
    # gehört ausdrücklich nicht dazu — ein Artikel über einen klinischen Hold
    # oder einen Erstattungsstreit ist regulatorisches Umfeld, keine Aussage
    # über den Marktzugang.
    pathway = granted + denied + filed + trial + forming + gaps
    n_path = len(pathway)

    def _ev(*groups):
        merged = [r for g in groups for r in g]
        merged.sort(key=lambda r: r["event_date"] or date.min, reverse=True)
        return [r["id"] for r in merged[:5]]

    # Nenner ist der PFAD-Bestand, nicht jedes regulatorisch getönte Signal.
    # Mit `regs` (inkl. 'other') fiel „SpaceX gets FCC approval to launch 7.500
    # more Starlink satellites" auf H2 zurück, weil acht Kommentarstücke im
    # Scope lagen.
    if len(granted) == 1 and len(pathway) >= 8:
        # Genau ein Zulassungssignal in einem gut belegten Scope: zu dünn für H1,
        # aber ein Hinweis auf ein laufendes Verfahren.
        filed = filed + granted
        granted = []

    # In einer als UNREGULIERT geführten Domäne hat diese Dimension nichts zu
    # melden außer einem echten Hindernis. Kalibrierlauf 2026-08-02: Plant-Based
    # Meat — ausdrücklich nicht reguliert — bekam ein US-„H1, clear to act" aus
    # drei Produktmeldungen (zwei davon aus Japan und Spanien) und ein EU-„H3,
    # Route geschlossen" aus einer Kennzeichnungsregel für Produktnamen. Beide
    # Aussagen erfindet der Erkenner aus einem Regime, das es nicht gibt.
    if not regulated:
        # Eine GEFUNDENE Zulassung bleibt positive Evidenz, egal wie das Feld
        # konfiguriert ist — nur muss sie aus einem Regulatorik-Signal stammen,
        # nicht aus dem quertypigen Zulassungs-Scan. Genau dort entstand das
        # falsche „H1, clear to act" für Plant-Based Meat: drei Produktmeldungen,
        # zwei davon aus Japan und Spanien, in einem Feld ohne Zulassungsregime.
        strict = [r for r in granted if r["trend_signal_type"] == "regulation"]
        if len(strict) >= MIN_N_GRANTED:
            years = sorted({r["event_date"].year for r in strict if r["event_date"]})
            return {
                "horizon": "H1", "n_signals": n_path, "method": "gates",
                "score": 1.0, "basis": "granted",
                "rationale": f"{len(strict)} approval event(s) recorded for this "
                             f"field in {region}"
                             + (f" since {years[0]}" if years else "")
                             + " — clear to act.",
                "evidence": _ev(strict),
            }
        if len(gaps) + len(denied) >= MIN_N_REGULATORY + 1:
            return {
                "horizon": "H3", "n_signals": n_path, "method": "gates",
                "score": 0.15, "basis": "blockade",
                "rationale": f"{len(gaps) + len(denied)} signals name an explicit "
                             f"blockade for this field in {region} — notable "
                             "because no approval regime otherwise gates it.",
                "evidence": _ev(gaps, denied),
            }
        return {
            "horizon": None, "n_signals": n_path, "method": "gates",
            "basis": "unregulated",
            "rationale": (
                f"No approval regime gates this field in {region}, so this "
                "dimension makes no call — the absence of approvals says nothing "
                "about market access. Switch on “Approval required” if one applies."
            ),
            "evidence": [],
        }

    # --- POSITIVE Befunde: ein gefundener Beleg trägt sie ---
    if (len(granted) >= MIN_N_GRANTED or (granted and len(pathway) < 8)) \
            and len(denied) <= len(granted):
        years = sorted({r["event_date"].year for r in granted if r["event_date"]})
        return {
            "horizon": "H1", "n_signals": n_path, "method": "gates",
            "score": 1.0, "basis": "granted",
            "rationale": f"{len(granted)} distinct approval event(s) granted by the "
                         f"responsible {'authority anywhere' if region == WORLD else region + ' authority'}"
                         + (f" since {years[0]}" if years else "")
                         + " — clear to act.",
            "evidence": _ev(granted),
        }
    # Ablehnung und Verbot sind derselbe Befundtyp: ein positiv festgestelltes
    # Hindernis, im Unterschied zu „nichts gefunden". Sie zählen deshalb
    # gemeinsam gegen die Mindestschwelle — sonst scheitert ein Feld mit je einer
    # Ablehnung UND einem Verbot an beiden Einzelschwellen und das Radar
    # schweigt, obwohl der Fall so klar ist wie er nur sein kann.
    blocked = denied + gaps
    if blocked and len(blocked) >= MIN_N_REGULATORY and len(denied) >= len(granted):
        parts = []
        if denied:
            parts.append(f"{len(denied)} refusal(s) or negative decision(s)")
        if gaps:
            parts.append(f"{len(gaps)} explicit blockade(s) (ban, prohibition, "
                         "moratorium)")
        return {
            "horizon": "H3", "n_signals": n_path, "method": "gates",
            "score": 0.15, "basis": "denied" if denied else "blockade",
            "rationale": f"{' and '.join(parts)} for this field in {region}, with no "
                         "standing approval — the route is closed for now, not "
                         "merely unbuilt.",
            "evidence": _ev(denied, gaps),
        }
    if filed:
        return {
            "horizon": "H2", "n_signals": n_path, "method": "gates",
            "score": 0.55, "basis": "filed",
            "rationale": f"No granted approval in {region}, but {len(filed)} "
                         f"live proceeding(s) (filing, review) in the last "
                         f"{PATHWAY_WINDOW_MONTHS} months — the route is being walked.",
            "evidence": _ev(filed),
        }
    if len(trial) >= MIN_N_REGULATORY:
        return {
            "horizon": "H2", "n_signals": n_path, "method": "gates",
            "score": 0.45, "basis": "trial",
            "rationale": f"{len(trial)} authorisation(s) in {region} concern studies "
                         "or trials, not marketing — permission to investigate is "
                         "not permission to sell.",
            "evidence": _ev(trial),
        }
    # --- NEGATIVE Befunde: sie brauchen den Nachweis, dass hingeschaut wurde ---
    #
    # Hier sitzt der teuerste Fehler des alten Radars. „Kein Zulassungsweg in der
    # EU" ist die folgenreichste Aussage des ganzen Rasters, und sie stand auf
    # zwei schwachen Signalen. Die Fachprüfung 2026-08-02 fand sie für mRNA-
    # Impfstoffe, CAR-T, Gentherapie, Insektenprotein, Mycoprotein, SAF, CCS und
    # SMR — durchweg Felder mit erteilten Zulassungen oder bindenden Regimen.
    #
    # Der Grund ist strukturell und nicht durch mehr Quellen behebbar: ein
    # Gesetz, das ruhig in Kraft ist, erzeugt keine Nachrichten. Nachrichten
    # messen Veränderung, ein Regime ist ein Zustand. Ein Nachrichtenkorpus kann
    # die EXISTENZ eines Zulassungswegs deshalb prinzipiell nicht widerlegen.
    # Das Radar darf hier nur noch schweigen — und sagt auch, warum.
    observable = region == WORLD or \
        REG_COVERAGE_SHARE.get(region, 0.0) >= MIN_COVERAGE_FOR_ABSENCE
    # Zweite Bedingung: das Feld muss IRGENDWO eine Zulassung zeigen. Dann ist
    # „hier keine" eine Jurisdiktions-Aussage, die der Korpus tragen kann — genau
    # der Fall Cultivated Meat (USA/Singapur zugelassen, EU nicht). Findet sich
    # NIRGENDS eine Zulassung, ist die naheliegendste Erklärung, dass unser
    # Erkenner das Regime dieses Felds nicht sieht: SAF wird von einer bindenden
    # EU-Beimischungsquote und elf ASTM-Pfaden getragen, von denen kein einziger
    # als „Zulassung" formuliert ist. Dann schweigt die Zelle.
    granted_anywhere = any(reg_subtype(r, field_terms) == "granted"
                           for r in candidates)
    # Die Absenz-H3 ist ERSATZLOS gestrichen (2026-08-02, nach der zweiten
    # Prüfrunde). Sie war der letzte Ort, an dem aus Schweigen ein Befund wurde,
    # und sie lag in jedem geprüften Fall falsch: „kein Zulassungsweg in den USA"
    # für autonomes Fahren, während Waymo mit staatlichen Genehmigungen rund
    # 500.000 bezahlte Fahrten pro Woche fuhr; dasselbe für SAF (bindende
    # EU-Quote), mRNA-Impfstoffe und CCS. Der Grund ist strukturell: Zulassungen
    # sind oft nachrangig (Bundesstaat, Notified Body, Norm) oder schlicht älter
    # als das Nachrichtenfenster. H3 setzt ab jetzt ausschließlich ein POSITIV
    # festgestelltes Hindernis — eine Ablehnung oder ein in Kraft gesetztes
    # Verbot. Alles andere schweigt.
    if regulated and n_path >= MIN_N_NEGATIVE and not observable:
        share = REG_COVERAGE_SHARE.get(region, 0.0)
        return {
            "horizon": None, "n_signals": n_path, "method": "gates",
            "basis": "uncovered",
            "rationale": (
                f"{n_path} signals discuss the regulatory route in {region} but none "
                f"reports a decision. No call is made: only {share:.0%} of the "
                "approvals our sources can attribute belong to this jurisdiction, so "
                "absence here measures the sources rather than the law."
            ),
            "evidence": _ev(forming, filed),
        }
    if regulated and n_path >= MIN_N_NEGATIVE and not granted_anywhere:
        return {
            "horizon": None, "n_signals": n_path, "method": "gates",
            "basis": "unreadable",
            "rationale": (
                f"{n_path} signals discuss the regulatory route in {region}, but this "
                "field shows no granted approval in any jurisdiction — including "
                "those where our sources see approvals well. The likelier reading is "
                "that its regime is not expressed as approvals at all (a mandate, a "
                "standard, a permit) and our detector cannot see it. No call."
            ),
            "evidence": _ev(forming, filed),
        }
    return {
        "horizon": None, "n_signals": n_path, "method": "gates", "basis": "silent",
        "rationale": (
            f"No approval, refusal or filing for this field is visible in {region} "
            f"({n_path} signals speak to the regulatory route at all). That is a "
            "statement about the sources, not about the law: a regime quietly in "
            "force generates no news. No call."
        ),
        "evidence": [],
    }


def cell_market(rows: list[dict], region: str, today: date,
                field_terms: list[str] | None = None) -> dict:
    """Marktzugang pro Jurisdiktion — Transaktionsbelege, nicht Ankündigungen.

    Drei Verschärfungen aus der Fachprüfung 2026-08-02:

    1. Ein Signal zählt nur, wenn es das Feld auch NENNT. „CIRANDA Announces Two
       New Baking Chips" trug die Marktzelle von „organ on a chip".
    2. Meinungsstücke sind keine Produktstarts. Sodium-Ion stand in den USA auf
       H1 wegen „9 commercial product launches", deren Belege drei Essays und
       ein Regionalartikel waren.
    3. „Keine Produktstarts im Fenster" ist KEIN Beleg für „nicht am Markt".
       Guardants Bluttest (>1 Mrd. $ Umsatz), NatureWorks' PLA-Werk (seit 2002)
       und Starlink (12 Mio. Kunden) fielen darunter: ihre Markteinführung lag
       vor dem Fenster, und wer im Markt ist, startet nicht ständig neu. H3
       verlangt jetzt eine breite, aber leere Beobachtung — sonst schweigt die
       Zelle.
    """
    in_region = [r for r in rows if in_jurisdiction(r, region)
                 and mentions_field(r, field_terms)]
    launches = _recent([r for r in in_region
                        if r["trend_signal_type"] == "product_launch"],
                       LAUNCH_WINDOW_MONTHS, today)
    if len(in_region) < MIN_N_MARKET:
        return {"horizon": None, "n_signals": len(in_region), "method": "gates",
                "rationale": f"Too few signals mentioning this field in {region} "
                             f"({len(in_region)}) — no call.",
                "evidence": []}

    launches = dedupe_events(launches)
    # Meinungsstücke sind keine Ereignisse und fliegen ganz raus; Pilotanlagen
    # sind Ereignisse, belegen aber Machbarkeit statt Käuflichkeit (H2).
    # Der Transaktionsverb ist bewusst nur ein VERSTÄRKER, keine Pflicht: als
    # Pflicht ausprobiert fielen Lithium-Ionen, Wärmepumpen und Offshore-Wind
    # auf H2 — echte Produktmeldungen tragen das Verb oft nicht im Titel.
    essays = [r for r in launches if ESSAY_TITLE.search(_title(r))]
    real = [r for r in launches if r not in essays]
    pilots = [r for r in real if MARKET_PILOT.search(_text(r))]
    commercial = [r for r in real if r not in pilots]
    scaled = [r for r in commercial
              if MARKET_SCALE.search(_text(r)) or LAUNCH_COMMERCIAL.search(_text(r))]

    # Zweiter Weg zu H1, unabhängig vom Ereignisfenster: laufender Handel. Ein
    # Feld mit Umsatz-, Erstattungs- oder Stückzahlbelegen IST am Markt, auch
    # wenn seine Produkteinführungen Jahre zurückliegen.
    trading = [r for r in in_region
               if r["trend_signal_type"] in ("product_launch", "market_shift",
                                             "consumer_behavior")
               and not MARKET_PILOT.search(_text(r))
               and (MARKET_SCALE.search(_text(r))
                    or MARKET_MAGNITUDE.search(_text(r)))]
    trading = dedupe_events(_recent(trading, LAUNCH_WINDOW_MONTHS, today))

    def _ev(*groups):
        merged = [r for g in groups for r in g]
        merged.sort(key=lambda r: r["event_date"] or date.min, reverse=True)
        return [r["id"] for r in merged[:5]]

    # Der Abkürzungspfad über Skalen-Evidenz braucht mindestens MIN_N_MARKET
    # Meldungen. Mit „ein Signal plus ein Skalenwort" reichte sonst eine einzelne
    # Meldung für „am Markt" — 6G stand so weltweit auf H1, obwohl der Standard
    # vor 2028 nicht existiert.
    if len(commercial) >= 5 or (len(commercial) >= MIN_N_MARKET and scaled):
        return {
            "horizon": "H1", "n_signals": len(in_region), "method": "gates",
            "score": 0.9, "basis": "commercial",
            "rationale": f"{len(commercial)} distinct commercial launches in {region} "
                         f"(last {LAUNCH_WINDOW_MONTHS} months)"
                         + (f", {len(scaled)} with retail, revenue or volume evidence"
                            if scaled else "")
                         + (f"; {len(pilots)} pilots and {len(essays)} commentary "
                            "pieces excluded" if (pilots or essays) else "")
                         + " — on the market.",
            "evidence": _ev(commercial),
        }
    if len(trading) >= MIN_N_MARKET:
        return {
            "horizon": "H1", "n_signals": len(in_region), "method": "trade_evidence",
            "score": 0.85, "basis": "trading",
            "rationale": f"{len(trading)} signals in {region} evidence a running "
                         "trade — revenue, shipments, installed base or "
                         "reimbursement — even though the launch events predate "
                         "the window. An established market stops announcing itself.",
            "evidence": _ev(trading),
        }
    if pilots or commercial:
        return {
            "horizon": "H2", "n_signals": len(in_region), "method": "gates",
            "score": 0.5, "basis": "entry",
            "rationale": (
                f"{len(pilots)} pilot or demonstration signal(s)"
                + (f", {len(commercial)} product launch(es)" if commercial else "")
                + (f", {len(essays)} commentary piece(s) excluded" if essays else "")
                + f" in {region} — feasibility and first entry shown, not yet a "
                  "running market."
            ),
            "evidence": _ev(commercial, pilots),
        }
    # Blindheits-Prüfung: hat das Feld IRGENDWO und IRGENDWANN eine Produktmeldung?
    # Für mRNA-Impfstoffe, CAR-T, Silicon Photonics und neuromorphes Rechnen
    # enthält der Korpus null `product_launch`-Signale — in keinem Jahr, in keiner
    # Region. Dann misst die Marktdimension für dieses Feld gar nichts, und „nicht
    # am Markt" wäre eine Aussage über einen Sensor, der nicht ausschlägt. Der
    # Unterschied zu 6G oder Xenotransplantation ist entscheidend: dort GIBT es
    # Produktmeldungen im Feld, sie sind nur dünn und jung — da trägt H3.
    any_launch = any(r["trend_signal_type"] == "product_launch"
                     and mentions_field(r, field_terms) for r in rows)
    if len(in_region) >= MIN_N_NEGATIVE and any_launch:
        return {
            "horizon": "H3", "n_signals": len(in_region), "method": "gates",
            "score": 0.1, "basis": "absence",
            "rationale": f"{len(in_region)} signals mention this field in {region}, "
                         f"none of them a launch, a pilot or trade evidence in the "
                         f"last {LAUNCH_WINDOW_MONTHS} months — no market visible.",
            "evidence": [],
        }
    if len(in_region) >= MIN_N_NEGATIVE and not any_launch:
        return {
            "horizon": None, "n_signals": len(in_region), "method": "gates",
            "basis": "blind",
            "rationale": (
                f"{len(in_region)} signals mention this field in {region}, but the "
                "corpus holds no product-launch signal for it in any region or year. "
                "The market dimension has nothing to read here, so it makes no call "
                "— that is a gap in the sources, not an empty market."
            ),
            "evidence": [],
        }
    return {
        "horizon": None, "n_signals": len(in_region), "method": "gates",
        "basis": "silent",
        "rationale": f"Too little market evidence either way for {region} "
                     f"({len(in_region)} signals) — no call.",
        "evidence": [],
    }


def cell_adoption(rows: list[dict], region: str, today: date,
                  market_horizon: str | None = None,
                  field_terms: list[str] | None = None) -> dict:
    """Nachfrage-/Verhaltensseite: consumer_behavior + semantische Marktbewegung.

    `market_horizon` entscheidet, was FEHLENDE Verbrauchersignale bedeuten:
    bei einem etablierten Markt (H1) spiegelt die Abwesenheit nur, worüber News
    berichten — niemand schreibt 2026 "Verbraucher nutzen jetzt Lithium-Akkus".
    Abwesenheit als H3 zu werten ist nur belastbar, wenn auch der Markt fehlt.
    """
    pool = [r for r in _recent(rows, LAUNCH_WINDOW_MONTHS, today)
            if in_jurisdiction(r, region) and mentions_field(r, field_terms)
            and (r["trend_signal_type"] in ("consumer_behavior", "partnership")
                 or (r["trend_signal_type"] in ("market_shift", "product_launch")
                     and r["semantic"]))]
    cb = [r for r in pool if r["trend_signal_type"] == "consumer_behavior"]
    # Nachfrage kommt in den meisten Feldern NICHT als Verbraucherstimme. Bei
    # Netzspeichern, Offshore-Wind, SMR oder Batterierecycling erscheint sie als
    # Auktion, Abnahmevertrag oder Erstattungsentscheid — die Fachprüfung fand
    # vier Felder mit veröffentlichten Zuschlagspreisen, die auf „demand
    # unevidenced" standen, und >10 GW Hyperscaler-Verträge für SMR ebenso.
    procured = [r for r in pool if DEMAND_MARKERS.search(_text(r))]
    evidenced = dedupe_events(cb + [r for r in procured if r not in cb])
    if len(pool) < MIN_N_ADOPTION:
        return {"horizon": None, "n_signals": len(pool), "method": "gates",
                "rationale": f"Too few demand signals for {region} ({len(pool)}) "
                             "— no call.",
                "evidence": []}
    ev = sorted(evidenced or pool, key=lambda r: r["event_date"] or date.min,
                reverse=True)
    if len(evidenced) >= 3:
        kind = ("consumer signals" if len(cb) >= len(procured)
                else "procurement, offtake or uptake signals")
        return {"horizon": "H1", "n_signals": len(pool), "method": "gates",
                "score": 0.85,
                "rationale": f"{len(evidenced)} distinct {kind} in {region} — "
                             "demand is evidenced.",
                "evidence": [r["id"] for r in ev[:5]]}
    if evidenced:
        return {"horizon": "H2", "n_signals": len(pool), "method": "gates",
                "score": 0.5,
                "rationale": f"{len(evidenced)} demand signal(s) in {region} — "
                             "demand is forming.",
                "evidence": [r["id"] for r in ev[:5]]}
    # H3 „Nachfrage unbelegt" ist eine Absenz-Aussage und braucht deshalb
    # sowohl eine breite Beobachtung als auch einen Markt, der selbst nicht
    # läuft. Wo ein Markt existiert, misst fehlende Verbraucher-Berichterstattung
    # den Nachrichtenkorpus, nicht die Nachfrage.
    if market_horizon in (None, "H3") and len(pool) >= MIN_N_NEGATIVE:
        return {"horizon": "H3", "n_signals": len(pool), "method": "gates",
                "score": 0.2,
                "rationale": f"{len(pool)} signals in {region} show market movement "
                             "but none evidences a buyer — no purchase, contract or "
                             "uptake reported.",
                "evidence": []}
    return {"horizon": None, "n_signals": len(pool), "method": "gates",
            "rationale": f"No direct demand-side signal in {region}. With a market "
                         "that exists, that reflects what news covers rather than "
                         "absent demand — no call.",
            "evidence": []}


def cell_technology(conn, rows: list[dict], today: date) -> dict:
    """CPC-Takeoff-Anker; Fallback semantischer Signalmix.

    Der Patent-Layer ist das methodisch stärkste Asset (peer-reviewte
    SPNP-Methode, gegen den MIT-Datensatz validiert), deckt aber nur
    patentierbare Felder ab. Ohne belastbaren CPC-Anker fällt die Dimension auf
    den semantischen Signalmix zurück — und sagt das im Klartext.
    """
    # Diffusions-Nachweis zuerst: eine Technologie mit vieljähriger, weit vor
    # dem News-Fenster beginnender Markt-Historie IST skalenreif — genau der
    # Beleg, den die H2-Deckelung des Signalmixes zu Recht verlangt. Ohne diesen
    # Pfad las das Radar Lithium-Ionen als H2/H3, weil laufende Forschung den
    # Mix forschungsseitig färbt: News messen Veränderung, nicht Zustand.
    hist = _market_history(rows, today)

    ids = [r["id"] for r in rows]
    anchor = None
    if ids:
        anchor = conn.execute(
            """
            SELECT sc.cpc, count(*) AS n,
                   ls.science_takeoff, ls.patent_takeoff, ls.market_takeoff,
                   ls.reliable, d.title,
                   (SELECT count(DISTINCT trend_id) FROM signal_cpc g
                     WHERE g.cpc = sc.cpc AND g.dist < 0.55) AS corpus_n
            FROM signal_cpc sc
            JOIN cpc_leadtime_summary ls ON ls.cpc = sc.cpc
            LEFT JOIN cpc_definitions d ON d.symbol = sc.cpc
            WHERE sc.trend_id = ANY(%s) AND sc.dist < 0.55
            GROUP BY sc.cpc, ls.science_takeoff, ls.patent_takeoff,
                     ls.market_takeoff, ls.reliable, d.title
            ORDER BY n DESC LIMIT 1
            """,
            (ids,),
        ).fetchone()

    # SPEZIFITÄT statt bloßer Belastbarkeit. `reliable=1` sagt, dass die
    # Lead-Time der KLASSE belastbar ist — nicht, dass die Klasse das Feld
    # beschreibt. Kalibrierlauf 2026-08-02: G06N („computing arrangements based
    # on specific computational models", also maschinelles Lernen insgesamt)
    # verankerte gleichzeitig Large Language Models, neuromorphes Rechnen UND
    # Brain-Computer-Interfaces und vererbte allen dreien seinen Markt-Takeoff
    # 2023 — der KI-Welle. B25J (Manipulatoren) gab humanoiden Robotern den
    # Takeoff 2009 von Industrie-Roboterarmen. Beides derselbe Kategorienfehler,
    # den der A23C-Fall 2026-07-30 schon zeigte; `reliable` hat ihn nicht
    # gefangen, weil breite Klassen wegen ihrer Masse besonders zuverlässig
    # aussehen.
    #
    # Gemessen trennt Containment (Anteil der Klasse, der in diesem Feld liegt)
    # sauber: B33Y/Additive Manufacturing 0,205 gegen G06N/Neuromorphic 0,035 und
    # G06N/BCI 0,014. Der Schwellenwert liegt zwischen den Gruppen, nicht an der
    # Kante. Ein unspezifischer Anker fällt auf den Signalmix zurück, der bei H2
    # gedeckelt ist und das auch sagt.
    containment = 0.0
    if anchor and anchor["corpus_n"]:
        containment = anchor["n"] / anchor["corpus_n"]
    specific = containment >= ANCHOR_MIN_CONTAINMENT

    # Der Lead-Time-Kontext wird IMMER mitgegeben, auch wenn der Anker den
    # Horizont nicht setzen darf. Das Radar zeigte bisher das Band und verschwieg
    # die Jahre, die es erzeugt haben — für eine Investitionsentscheidung ist
    # genau das die fehlende Achse.
    #
    # Ausdrücklich KEINE Prognose. Wir geben wieder, wie lange vergleichbare
    # Technologien DIESER Patentklasse historisch von der Forschung zum Markt
    # gebraucht haben, und sagen dazu, wie gut die Klasse zum Feld passt. Die
    # Owner-Regel (TIR = relative Entwicklung, nicht Früherkennung, #68) verlangt
    # diese Trennung: „Klassen wie diese brauchten X Jahre" ist eine Aussage über
    # die Vergangenheit, „wird 2029 verfügbar" wäre eine über die Zukunft.
    lead = None
    if anchor and anchor["n"] >= 5:
        sci, pat, mkt = (anchor["science_takeoff"], anchor["patent_takeoff"],
                         anchor["market_takeoff"])
        lead = {
            "cpc": anchor["cpc"],
            "title": (anchor["title"] or "").strip() or None,
            "science_takeoff": sci, "patent_takeoff": pat, "market_takeoff": mkt,
            "reliable": bool(anchor["reliable"]),
            "containment": round(containment, 3),
            "matched": anchor["n"],
            # Der historische Vorlauf der KLASSE, nicht des Felds.
            "science_to_market": (mkt - sci) if (sci and mkt and mkt > sci) else None,
            "patent_to_market": (mkt - pat) if (pat and mkt and mkt > pat) else None,
            "fits_field": bool(anchor["reliable"] and specific),
        }

    if hist["established"]:
        return {
            "horizon": "H1", "score": 0.9, "method": "market_history",
            "n_signals": hist["launches"], "lead_time": lead,
            "rationale": (
                f"Established at scale: market signals in {hist['active_years']} "
                f"distinct years since {hist['first_year']} and "
                f"{hist['launches']} product launches across the corpus. The "
                "research volume in this field reflects ongoing refinement, "
                "not immaturity."
            ),
            "evidence": [],
        }

    if anchor and anchor["n"] >= 5 and anchor["reliable"] and specific:
        sci, pat, mkt = (anchor["science_takeoff"], anchor["patent_takeoff"],
                         anchor["market_takeoff"])
        cpc, title = anchor["cpc"], (anchor["title"] or "").strip()
        base = (f"Patent anchor {cpc}"
                + (f" ({title[:48]})" if title else "")
                + f", {anchor['n']} signals matched, lead-time flagged reliable")
        if mkt and mkt <= today.year - MARKET_TAKEOFF_SETTLED_YEARS:
            return {"horizon": "H1", "score": 0.9, "method": "cpc_takeoff",
                    "n_signals": anchor["n"], "lead_time": lead,
                    "rationale": f"{base}: market takeoff {mkt} — technologically established.",
                    "evidence": []}
        if pat:
            return {"horizon": "H2", "score": 0.55, "method": "cpc_takeoff",
                    "n_signals": anchor["n"], "lead_time": lead,
                    "rationale": f"{base}: patent takeoff {pat}"
                                 + (f", market takeoff only {mkt}" if mkt else
                                    ", no market takeoff yet")
                                 + " — in transition.",
                    "evidence": []}
        if sci:
            return {"horizon": "H3", "score": 0.2, "method": "cpc_takeoff",
                    "n_signals": anchor["n"], "lead_time": lead,
                    "rationale": f"{base}: research takeoff {sci} only — "
                                 "pre-competitive.",
                    "evidence": []}

    # Fallback: semantischer Mix (nur LLM-Pfad, sonst misst man Quellenmix).
    #
    # HARTE DECKELUNG AUF H2: aus dem Signalmix ist Kosten- und Skalenreife nicht
    # ablesbar. Viele Produktmeldungen belegen, dass das Verfahren funktioniert —
    # nicht, dass es wettbewerbsfähig produziert. H1 darf deshalb nur der
    # Patentanker (oder ein begründeter Analyst-Override) setzen.
    sem = [r for r in _recent(rows, 36, today) if r["semantic"]]
    unreliable = ""
    if anchor and anchor["n"] >= 5:
        why = ("its lead-time is not flagged reliable"
               if not anchor["reliable"] else
               f"it is far broader than this field ({containment:.1%} of the class "
               "falls inside it), so its take-off dates describe the class")
        unreliable = (f" The nearest patent anchor would be {anchor['cpc']}, but "
                      f"{why}, so it is left out.")
    if len(sem) < MIN_N_TECH_FALLBACK:
        return {"horizon": None, "score": None, "method": "semantic_mix",
                "n_signals": len(sem), "lead_time": lead,
                "rationale": "No reliable patent anchor and too few semantic "
                             f"signals ({len(sem)}) — no call."
                             + unreliable,
                "evidence": []}
    n = len(sem)
    applied = sum(1 for r in sem if r["trend_signal_type"] in
                  ("product_launch", "partnership"))
    research = sum(1 for r in sem if r["trend_signal_type"] in ("research", "patent"))
    share = applied / n
    if share >= 0.10:
        h, sc = "H2", 0.5
        why = (f"{applied} of {n} semantic signals are applied "
               f"(product/partnership), {research} still research-side — the process "
               "works; scale and cost maturity are not readable from signals")
    else:
        h, sc = "H3", 0.2
        why = (f"only {applied} of {n} signals applied, {research} research-side "
               "— pre-competitive")
    return {"horizon": h, "score": sc, "method": "semantic_mix", "n_signals": n,
            "lead_time": lead,
            "rationale": f"No reliable patent anchor, from the signal mix: {why}. "
                         f"H1 is unreachable on this path.{unreliable}",
            "evidence": []}


def pestel_of(row) -> set[str]:
    """PESTEL-Dimensionen eines Trends (LLM-Klassifikation, Stage 3)."""
    raw = row.get("pestel")
    vals = json.loads(raw) if isinstance(raw, str) else (raw or [])
    return {str(v) for v in vals if v}


# ---------------------------------------------------------------------------
# PESTEL-Dimensions-Set (dimension_set='pestel')
# ---------------------------------------------------------------------------
# Dieselben Gate-Primitiven, durch die PESTEL-Linse: T und L sind die
# Technologie- bzw. Zulassungs-Gates, S die Adoption, E zählt wirtschaftliche
# Aktivität, P politische Unterstützung vs. Widerstand. En misst ausdrücklich
# nur die SICHTBARKEIT des Umweltarguments im Signalraum — mehr gibt der Korpus
# ehrlich nicht her, und die Begründung sagt das auch so.
PESTEL_DIMENSIONS = ("P", "E", "S", "T", "En", "L")


def cell_economic(rows: list[dict], region: str, today: date) -> dict:
    """E: wirtschaftliche Aktivität — Finanzierung + Produktstarts je Region."""
    pool = [r for r in _recent(rows, LAUNCH_WINDOW_MONTHS, today)
            if region in regions_of(r)]
    funding = [r for r in pool if r["trend_signal_type"] == "funding"]
    launches = [r for r in pool if r["trend_signal_type"] == "product_launch"]
    n = len(funding) + len(launches)
    if n < MIN_N_MARKET:
        return {"horizon": None, "n_signals": n, "method": "gates",
                "rationale": f"Too few economic signals for {region} ({n}).",
                "evidence": []}
    ev = sorted(funding + launches, key=lambda r: r["event_date"] or date.min,
                reverse=True)
    if launches and funding:
        h, sc, why = "H1", 0.85, (f"{len(funding)} funding and {len(launches)} product "
                                  f"signals in {region} — commercial activity on both sides")
    elif funding:
        h, sc, why = "H2", 0.5, (f"{len(funding)} funding signals but only "
                                 f"{len(launches)} product launches in {region} — capital ahead of market")
    else:
        h, sc, why = "H2", 0.45, (f"{len(launches)} product launches with no visible "
                                  f"funding signals in {region}")
    return {"horizon": h, "n_signals": n, "method": "gates", "score": sc,
            "rationale": why + ".", "evidence": [r["id"] for r in ev[:5]]}


def cell_political(rows: list[dict], region: str, today: date) -> dict:
    """P: politische Unterstützung — Strategie/Förderprogramme vs. Blockade.

    Bewertet die POLITISCHE GROSSWETTERLAGE, nicht die erteilte Zulassung
    (das ist L): Strategien, Roadmaps und öffentliche Förderung = Unterstützung;
    Verbote und explizite Blockaden = Gegenwind.
    """
    regs = [r for r in _recent(rows, PATHWAY_WINDOW_MONTHS, today)
            if r["trend_signal_type"] == "regulation" and region in regions_of(r)
            and "P" in pestel_of(r)]
    support = [r for r in regs if reg_subtype(r) in ("forming", "filed", "trial")]
    gaps = [r for r in regs if reg_subtype(r) in ("gap", "denied")]
    n = len(regs)
    if n < MIN_N_REGULATORY:
        return {"horizon": None, "n_signals": n, "method": "gates",
                "rationale": f"Too few political signals for {region} ({n}).",
                "evidence": []}
    ev = sorted(regs, key=lambda r: r["event_date"] or date.min, reverse=True)
    if len(support) >= 3 and len(support) > 2 * len(gaps):
        h, sc, why = "H1", 0.8, (f"{len(support)} supportive signals (strategy, roadmap, "
                                 f"funding programme) against {len(gaps)} headwind signals in {region}")
    elif support:
        h, sc, why = "H2", 0.5, (f"{len(support)} supportive against {len(gaps)} headwind "
                                 f"signals in {region} — politically in motion")
    else:
        h, sc, why = "H3", 0.2, (f"Headwind only, or no supportive signals in "
                                 f"{region} ({len(gaps)} blocking signals)")
    return {"horizon": h, "n_signals": n, "method": "gates", "score": sc,
            "rationale": why + ".", "evidence": [r["id"] for r in ev[:5]]}


def cell_environmental(rows: list[dict], region: str, today: date) -> dict:
    """En: Sichtbarkeit des Umweltarguments im Signalraum dieses Felds.

    Ausdrücklich KEINE Ökobilanz — gemessen wird, wie präsent die Umweltdimension
    in den Signalen ist und ob sie zunimmt. Die Formulierung der Begründung
    macht diese Grenze explizit.
    """
    sem = [r for r in rows if r["semantic"] and region in regions_of(r)]
    if region == "GLOBAL":
        sem = [r for r in rows if r["semantic"]]
    tagged = [r for r in sem if "En" in pestel_of(r)]
    n = len(sem)
    if n < 20:
        return {"horizon": None, "n_signals": len(tagged), "method": "semantic_mix",
                "rationale": f"Too few semantic signals for {region} ({n}).",
                "evidence": []}
    share = len(tagged) / n
    recent = [r for r in _recent(tagged, 12, today)]
    ev = sorted(tagged, key=lambda r: r["event_date"] or date.min, reverse=True)
    if share >= 0.35 and recent:
        h, sc = "H1", 0.8
        why = (f"The environmental case carries: {len(tagged)} of {n} signals "
               f"({share:.0%}) are environment-tagged, {len(recent)} of them from "
               "the last 12 months")
    elif share >= 0.15:
        h, sc = "H2", 0.5
        why = (f"Environmental framing present but not dominant: {share:.0%} of "
               f"{n} signals")
    else:
        h, sc = "H3", 0.2
        why = f"Environmental framing marginal: {share:.0%} of {n} signals"
    return {"horizon": h, "n_signals": len(tagged), "method": "semantic_mix",
            "score": sc,
            "rationale": why + ". This measures visibility in the signal space, "
                         "not a life-cycle assessment.",
            "evidence": [r["id"] for r in ev[:5]]}


# ---------------------------------------------------------------------------
# Lauf
# ---------------------------------------------------------------------------
def compute_cells(conn, rows: list[dict], *, regions: list[str],
                  dimension_set: str = "strategic", regulated: bool = False,
                  today: date | None = None,
                  field_terms: list[str] | None = None) -> list[dict]:
    """Alle Zellen EINES Scopes. Ohne run_id, ohne scope_slug, ohne Schreiben.

    Herausgelöst aus compute(), damit derselbe Code den nächtlichen Batch-Lauf
    und den On-Demand-Pfad bedient — zwei Implementierungen derselben
    Einordnung wären zwei Wahrheiten. `conn` braucht nur cell_technology
    (der signal_cpc-Anker), alle übrigen Zellen sind rein.

    Rückgabe: [{dimension, region, horizon, score, n_signals, method,
                rationale, evidence}, …]
    """
    today = today or date.today()
    out: list[dict] = []

    # Long-Tail-Vertikale einmal abschneiden — danach sieht jede Zelle denselben,
    # bereinigten Scope. Signale ohne Vertikale bleiben drin: eine fehlende
    # Klassifikation ist kein Ausschlussgrund.
    keep = scope_verticals(rows)
    if keep:
        rows = [r for r in rows
                if not r.get("primary_vertical") or r["primary_vertical"] in keep]

    tech = cell_technology(conn, rows, today)
    out.append({
        "dimension": "T" if dimension_set == "pestel" else "technology",
        "region": ANY_REGION, "horizon": tech["horizon"], "score": tech.get("score"),
        "n_signals": tech["n_signals"], "method": tech["method"],
        "rationale": tech["rationale"], "evidence": tech.get("evidence", []),
    })

    tech_idx = 0  # die Technologie-Zelle steht immer an Position 0

    for region in regions:
        if dimension_set == "pestel":
            # Dieselben Gate-Primitiven durch die PESTEL-Linse:
            # L = Zulassungs-Gates, S = Adoption, E = Wirtschaft,
            # P = politische Unterstützung, En = Umwelt-Sichtbarkeit.
            per_region = (("L", cell_regulatory(rows, region, today,
                                                regulated=regulated,
                                                field_terms=field_terms)),
                          ("E", cell_economic(rows, region, today)),
                          ("S", cell_adoption(rows, region, today,
                                              field_terms=field_terms)),
                          ("P", cell_political(rows, region, today)),
                          ("En", cell_environmental(rows, region, today)))
        else:
            reg = cell_regulatory(rows, region, today, regulated=regulated,
                                  field_terms=field_terms)
            mkt = cell_market(rows, region, today, field_terms=field_terms)
            if regulated:
                mkt = couple_market_to_regulation(mkt, reg, region)
            # Adoption sieht den GEKOPPELTEN Markt-Horizont: ist der Markt auf
            # H3 gedeckelt, bleibt Abwesenheit von Nachfrage eine H3-Aussage.
            per_region = (("regulatory", reg), ("market", mkt),
                          ("adoption", cell_adoption(rows, region, today,
                                                     market_horizon=mkt["horizon"],
                                                     field_terms=field_terms)))
        for dim, c in per_region:
            out.append({
                "dimension": dim, "region": region, "horizon": c["horizon"],
                "score": c.get("score"), "n_signals": c["n_signals"],
                "method": c["method"], "rationale": c["rationale"],
                "basis": c.get("basis"),
                "evidence": c.get("evidence", []),
            })

    # Kohärenz-Boden: eine Technologie mit erteilten Zulassungen oder einem
    # laufenden Markt ist nicht "vorwettbewerblich". Kalibrierlauf 2026-08-02:
    # Gene Therapy stand auf Technologie H3, obwohl der Korpus 70 erteilte
    # US-Zulassungen enthält — der Signalmix sah nur 1,9 % angewandte Signale,
    # weil klinische Forschung das Volumen dominiert. Das ist die Signatur eines
    # reifen regulierten Therapiefelds, nicht die eines unreifen. Angehoben wird
    # auf H2, nicht auf H1: Skalen- und Kostenreife bleibt unbelegt.
    # ---- Bestätigungspflicht für Markt-Absenz -----------------------------
    # „Nicht am Markt" aus fehlenden Produktmeldungen ist nur dann eine Aussage
    # über die Welt, wenn es nirgends einen Markt gibt ODER hier etwas den
    # Zugang versperrt. Trägt das Feld anderswo einen Markt und liegt hier kein
    # Hindernis vor, misst die Leere den Korpus: mRNA-Impfstoffe und CAR-T
    # standen so auf „kein Markt in der EU", weil ihre Markteinführungen vor dem
    # 36-Monats-Fenster lagen. Cultivated Meat/EU bleibt dagegen H3 — dort
    # BELEGT die Regulatorik-Zelle das Hindernis.
    reg_by_region = {c["region"]: c for c in out[1:] if c["dimension"] in
                     ("regulatory", "L")}
    # Jede POSITIVE Marktevidenz irgendwo genügt — nicht erst ein volles H1.
    # Silicon Photonics wird ausschließlich als unsichtbares Bauteil verkauft und
    # erzeugt fast keine Produktmeldungen; mit „nur H1 zählt" blieb es in beiden
    # Jurisdiktionen auf „nicht am Markt", obwohl weltweit Evidenz vorlag.
    sells_somewhere = any(c["dimension"] == "market" and c["horizon"] in ("H1", "H2")
                          for c in out[1:])
    for c in out[1:]:
        if c["dimension"] != "market" or c.get("basis") != "absence":
            continue
        blocked_here = (reg_by_region.get(c["region"], {}).get("basis")
                        in ("denied", "blockade", "absence"))
        if sells_somewhere and not blocked_here:
            c.update({
                "horizon": None, "score": None, "basis": "unconfirmed",
                "rationale": (
                    f"{c['n_signals']} signals mention this field in {c['region']} "
                    "but none is a launch or trade record. No call: the field does "
                    "trade in another jurisdiction and nothing here blocks it, so "
                    "the gap is most likely one of coverage — an established "
                    "product stops generating launch coverage."
                ),
            })

    tech = out[tech_idx]
    if tech["horizon"] == "H3" and tech["method"] == "semantic_mix":
        proof = [c for c in out[1:]
                 if c["horizon"] == "H1" and c["dimension"] in
                 ("regulatory", "market", "L")]
        if proof:
            kinds = sorted({("approvals" if c["dimension"] in ("regulatory", "L")
                             else "a live market") for c in proof})
            tech.update({
                "horizon": "H2", "score": 0.5,
                "method": "semantic_mix+coherence",
                "rationale": (
                    f"{tech['rationale']} Raised to H2: the same field shows "
                    f"{' and '.join(kinds)} in at least one jurisdiction, so it "
                    "cannot be pre-competitive. The research volume reflects a "
                    "field under active clinical or industrial development."
                ),
            })

    # Die Gegenrichtung — und der Grund, warum es sie geben muss: ohne sie ist
    # die Technologie-Dimension auf dem Signalmix-Pfad eine KONSTANTE. Sie sagte
    # dort ausschließlich H2 und schrieb selbst dazu „H1 is unreachable on this
    # path". Vier von sieben Scouts fanden dasselbe: ein 92-GW-Offshore-Markt,
    # ein 13,4-Mrd.-$-CGM-Markt und eine seit 1960 kommerzielle Geothermie
    # standen auf „Skalenreife unbelegt" — nicht als Messergebnis, sondern weil
    # der Pfad nichts anderes ausgeben KANN. Eine Dimension, die ihren Höchstwert
    # nicht erreichen kann, misst nicht.
    #
    # Die Deckelung war trotzdem richtig gedacht: viele Produktmeldungen belegen,
    # dass ein Verfahren funktioniert, nicht dass es wettbewerbsfähig produziert.
    # Genau diesen Unterschied macht aber die HANDELS-Evidenz — Umsatz,
    # installierte Basis, Stückzahlen, Erstattung. Wer laufend verkauft,
    # produziert zu Marktpreisen. Deshalb hebt nur sie auf H1, und nur wenn sie
    # in mehr als einer Jurisdiktion trägt.
    if tech["horizon"] == "H2" and tech["method"].startswith("semantic_mix"):
        h1_markets = [c for c in out[1:]
                      if c["dimension"] == "market" and c["horizon"] == "H1"]
        trading = [c for c in h1_markets if c.get("basis") == "trading"]
        if trading and len(h1_markets) >= 2:
            where = ", ".join(sorted({c["region"] for c in h1_markets})[:4])
            tech.update({
                "horizon": "H1", "score": 0.85,
                "method": tech["method"] + "+trade",
                "rationale": (
                    f"{tech['rationale']} Raised to H1: the field trades in "
                    f"{where} with revenue, shipment or reimbursement evidence, "
                    "not merely product announcements. Sustained commerce is the "
                    "cost and scale proof the signal mix alone cannot give."
                ),
            })
    return out


# Ist die Query überhaupt ein FELD?
#
# Der Zufallszug vom 2026-08-02 (50 Felder gleichverteilt aus 7.037 Pipeline-Tags)
# traf überwiegend Querschnittsthemen und Signalgattungen statt Technologien —
# und das Radar platzierte sie bereitwillig: „cost reduction" stand in JEDER
# Zelle auf H1, „disruption" und „user interaction" fast durchgehend. Ein Nutzer,
# der „digital transformation" eintippt, bekommt ein durchgehend grünes Radar,
# das nichts bedeutet. Das ist die schädlichste Ausgabe überhaupt, weil sie nach
# einer Aussage aussieht.
#
# Zwei UNABHÄNGIGE Eigenschaften eines echten Felds, beide gemessen:
#   * Branchenfokus — ein Feld lebt in einer Vertikalen, ein Thema in allen
#   * Patentabbildung — für Technologien gibt es Patentklassen, für „Diversität"
#     nicht
#
# Einzeln trennt keine sauber (Offshore-Wind ist hoch fokussiert, aber schlecht
# patentabgebildet: 0,89/0,12), zusammen schon. Gemessen an 15 echten Feldern
# und 12 abstrakten Themen: alle 15 echten bestehen, 10 von 12 abstrakten fallen
# durch. Die zwei Durchrutscher — „fashion design", „user interaction" — sind
# echte Gestaltungsdisziplinen und damit Grenzfälle, keine Fehlurteile.
# Der Branchenfokus zählt die ZWEI größten Vertikalen, nicht die größte. Echte
# Felder sind oft zweivertikal — Elektroautos leben in ECO und TECH (0,65 / 0,87),
# grüner Wasserstoff in ECO und BIZ (0,49 / 0,97) —, Querschnittsthemen dagegen
# streuen auch über zwei hinaus (cost reduction 0,38 / 0,61).
FIELD_FOCUS2_MIN = 0.85   # zwei Branchen tragen das Feld allein
FIELD_PATENT_STRONG = 0.70  # oder die Patentabbildung trägt es allein
FIELD_FOCUS1_MIN = 0.50   # sonst müssen Fokus und Patente zusammen tragen
FIELD_PATENT_MIN = 0.30


def field_coherence(conn, rows: list[dict]) -> dict:
    """Misst, ob eine Treffermenge ein Technologiefeld beschreibt oder ein Thema."""
    vc: dict[str, int] = {}
    for r in rows:
        v = r.get("primary_vertical")
        if v:
            vc[v] = vc.get(v, 0) + 1
    tot = sum(vc.values())
    ranked = sorted(vc.values(), reverse=True)
    focus = ranked[0] / tot if tot else 0.0
    focus2 = sum(ranked[:2]) / tot if tot else 0.0

    patent = 0.0
    ids = [r["id"] for r in rows]
    if ids and conn is not None:
        row = conn.execute(
            "SELECT count(DISTINCT trend_id) AS c FROM signal_cpc "
            "WHERE trend_id = ANY(%s) AND dist < 0.55", (ids,)
        ).fetchone()
        patent = (row["c"] / len(ids)) if row else 0.0

    is_field = (focus2 >= FIELD_FOCUS2_MIN
                or patent >= FIELD_PATENT_STRONG
                or (focus >= FIELD_FOCUS1_MIN and patent >= FIELD_PATENT_MIN))
    note = None
    if not is_field:
        note = (
            "This reads as a cross-cutting theme rather than a technology field: "
            f"its signals spread across industries (the two largest account for "
            f"{focus2:.0%}) and only {patent:.0%} map to a patent class. The "
            "horizons below then describe how the phrase is used in the press, not "
            "the maturity of a technology — expect them to look uniformly positive "
            "and to mean little. Name a concrete technology, material or process "
            "for a reading you can act on."
        )
    return {"vertical_focus": round(focus, 3), "vertical_focus2": round(focus2, 3),
            "patent_share": round(patent, 3), "is_field": is_field, "note": note}


# ---------------------------------------------------------------------------
# Klartext-Readout mit Technology Readiness Level
# ---------------------------------------------------------------------------
# Ein Nutzer, der eine Investitionsentscheidung trifft, braucht einen Satz, den
# er ins Memo kopieren kann — nicht vier Buchstabenpaare. TRL ist dafür die
# richtige Sprache, weil sie in Industrie, EU-Förderung und Beschaffung längst
# etabliert ist: „TRL 6" ist in einem Lenkungskreis sofort anschlussfähig,
# „H2 / MKT" nicht.
#
# WICHTIG: wir schätzen ein TRL-BAND, keinen Punktwert. Ein exaktes TRL setzt
# Einblick in ein konkretes Entwicklungsprogramm voraus; wir sehen ein
# Signalfeld. Das Band wird deshalb aus den Zellen ABGELEITET und die Ableitung
# offengelegt — dieselbe Disziplin wie bei den Horizonten.
TRL_BANDS: list[tuple[tuple[int, int], str, str]] = [
    ((1, 3), "Research",
     "principles observed and formulated, proof of concept at best"),
    ((4, 5), "Validation",
     "validated in the laboratory and in a relevant environment"),
    ((6, 7), "Demonstration",
     "demonstrated at pilot or pre-commercial scale in an operational setting"),
    ((8, 8), "Qualification",
     "the system is complete and qualified; first commercial units exist"),
    ((9, 9), "Operations",
     "proven in operation, sold and run at commercial scale"),
]


def _trl_band(tech: dict | None, markets: list[dict]) -> tuple[int, int]:
    """TRL-Band aus Technologie- und Marktzellen.

    Gewertet werden die BENANNTEN Jurisdiktionen, nicht die Weltspalte. Die ist
    die Vereinigung aller Signale und damit für fast jedes Feld „kommerziell" —
    mit ihr landeten alle acht Alt-Protein-Felder auf demselben Band 7–8, von
    der reifen Extrusionsindustrie bis zum vorkommerziellen Molecular Farming.
    Ein Band, das nicht unterscheidet, ist keine Messung. Die Weltspalte trägt
    nur, wenn keine benannte Jurisdiktion etwas hergibt — dann aber gedeckelt.
    """
    th = (tech or {}).get("horizon")
    named = [c for c in markets if c["region"] != WORLD]
    world = [c for c in markets if c["region"] == WORLD]

    def _has(cells, basis):
        return any(c.get("basis") == basis for c in cells)

    trading = _has(named, "trading")
    commercial = _has(named, "commercial")
    entry = _has(named, "entry")
    n_h1 = sum(1 for c in named if c["horizon"] == "H1")

    if not named or all(c["horizon"] is None for c in named):
        # Nur die Weltspalte spricht: die Technologie existiert irgendwo, aber
        # kein Markt ist lokalisierbar. Höchstens Demonstration.
        if _has(world, "trading") or _has(world, "commercial"):
            return (6, 7)
        if _has(world, "entry"):
            return (5, 6)

    if th == "H1" and trading:
        return (9, 9)
    if th == "H1" and (commercial or n_h1 >= 2):
        return (8, 9)
    if trading:
        return (8, 8) if th != "H3" else (7, 8)
    if commercial and n_h1 >= 2:
        return (7, 8)
    if commercial:
        return (7, 7)
    if entry:
        return (6, 7) if th != "H3" else (5, 6)
    if th == "H1":
        return (8, 9)
    if th == "H2":
        return (4, 6)
    if th == "H3":
        return (1, 3)
    if any(c["horizon"] == "H3" for c in markets):
        return (1, 4)
    return (0, 0)      # nichts Belastbares


def readout(cells: list[dict], scope_label: str,
            lead_time: dict | None = None) -> dict:
    """Ein Absatz Klartext über einem Feld — die Zusammenfassung fürs Memo."""
    tech = next((c for c in cells if c["dimension"] in ("technology", "T")), None)
    markets = [c for c in cells if c["dimension"] == "market"]
    regs = [c for c in cells if c["dimension"] in ("regulatory", "L")]
    ados = [c for c in cells if c["dimension"] == "adoption"]

    lo, hi = _trl_band(tech, markets)
    label = why = None
    for (a, b), name, blurb in TRL_BANDS:
        if lo and a <= lo <= b:
            label, why = name, blurb
            break

    parts: list[str] = []
    if tech and tech.get("horizon"):
        parts.append(tech["rationale"].split(".")[0].strip() + ".")

    sells = [c["region"] for c in markets if c["horizon"] == "H1"]
    enters = [c["region"] for c in markets if c["horizon"] == "H2"]
    absent = [c["region"] for c in markets if c["horizon"] == "H3"]
    if sells:
        parts.append(f"It is on the market in {_join(sells)}.")
    if enters:
        parts.append(f"First entry — pilots or early launches — in {_join(enters)}.")
    if absent:
        parts.append(f"No market visible in {_join(absent)}.")
    if not (sells or enters or absent):
        parts.append("No jurisdiction shows readable market evidence.")

    cleared = [c["region"] for c in regs if c["horizon"] == "H1"]
    blocked = [c["region"] for c in regs if c["horizon"] == "H3"]
    running = [c["region"] for c in regs if c["horizon"] == "H2"]
    if cleared:
        parts.append(f"Approvals are granted in {_join(cleared)}.")
    if running:
        parts.append(f"Proceedings are live in {_join(running)}.")
    if blocked:
        parts.append(f"A blockade is on record in {_join(blocked)}.")
    if not regs or all(c["horizon"] is None for c in regs):
        parts.append("No approval regime is visible for this field — treat "
                     "regulation as an open question, not as a cleared one.")

    demand = [c["region"] for c in ados if c["horizon"] == "H1"]
    if demand:
        parts.append(f"Demand is evidenced in {_join(demand)}.")

    # Der Lead-Time-Kontext ist ausdrücklich Vergangenheit, keine Prognose.
    if lead_time and lead_time.get("science_to_market"):
        fit = ("its patent class matches the field closely"
               if lead_time.get("fits_field") else
               "its patent class is broader than the field, so read this as a "
               "loose reference")
        parts.append(
            f"For historical context: technologies in patent class "
            f"{lead_time['cpc']} took {lead_time['science_to_market']} years from "
            f"research take-off ({lead_time['science_takeoff']}) to market "
            f"take-off ({lead_time['market_takeoff']}) — {fit}. That is what "
            "comparable classes did, not a forecast for this one."
        )

    stance = {
        (9, 9): "Decide now: this is an operating market, and the question is "
                "position, not feasibility.",
        (8, 9): "Commit selectively: the technology is qualified, the market is "
                "forming around it.",
        (8, 8): "Commit selectively: first commercial units exist.",
        (8, 8): "Commit selectively: first commercial units exist, sustained "
                "trade is evidenced.",
        (7, 8): "Build capability: demonstrated and entering commerce, but the "
                "trade is not yet running.",
        (7, 7): "Build capability: one jurisdiction shows commerce, the rest do "
                "not — treat it as a beachhead, not a market.",
        (6, 7): "Build optionality: demonstrated, not yet a running market.",
        (5, 6): "Build optionality: validated, commercial proof still missing.",
        (4, 6): "Keep an option open: the process works, scale and cost are "
                "unproven.",
        (1, 4): "Watch: too early to plan around.",
        (1, 3): "Watch: research stage, no route to market yet.",
    }.get((lo, hi), "Not enough evidence to take a position.")

    # Das TRL-Band ist am 2026-08-03 aus der ANZEIGE entfernt worden
    # (Owner-Entscheidung): auf Erkenntnis-Cluster wie „Gene Expression" passt
    # ein Reifegrad nicht, und ein Band, das für ein Drittel der Felder keine
    # Bedeutung hat, entwertet es für die übrigen. Berechnet wird es weiter —
    # es trägt den Haltungssatz, der die eigentliche Aussage war.
    return {
        "trl_low": lo or None, "trl_high": hi or None,
        "trl_label": label, "trl_blurb": why,
        "text": " ".join(parts),
        "stance": stance,
        "scope": scope_label,
    }


def _join(xs: list[str]) -> str:
    named = [("worldwide" if x == WORLD else x) for x in dict.fromkeys(xs)]
    if len(named) == 1:
        return named[0]
    return ", ".join(named[:-1]) + " and " + named[-1]


def compute_query_radar(conn, query: str, subfields: list[dict] | None = None, *,
                        regions: list[str] | None = None,
                        dimension_set: str = "strategic",
                        regulated: bool = False,
                        today: date | None = None,
                        name: str | None = None) -> dict:
    """Ein vollständiges Radar für eine Freitext-Query — OHNE Persistenz.

    Schreibt nichts nach radar_runs/radar_cells/radar_scope_trends. Liefert
    exakt die Form, die lib/radar.ts getRadar() erzeugt (RadarView), erweitert um
    `origin` und eine aufgelöste `evidence`-Map. Das ist die tragende
    Entscheidung dieses Pfads: er ist ein ZWEITER PRODUZENT DESSELBEN VERTRAGS,
    kein zweiter Renderpfad — deshalb bleiben HorizonArc und HorizonBoard
    unverändert.

    subfields: [{'slug','label','phrase','ids'}, …]
               Leer/None → die Query selbst ist das einzige Feld. Das ist der
               ehrliche Rückfall, wenn keine Zerlegung möglich oder gewollt ist.
    """
    today = today or date.today()
    regions = [r for r in (regions or ["US", "EU", "GLOBAL"]) if r in JURISDICTIONS]
    regions = regions or ["GLOBAL"]

    if not subfields:
        terms = split_query_terms(query)
        if len(terms) > 1:
            # Vergleichsmodus: jeder Begriff wird ein eigenes Feld mit eigener
            # Query. Eine Entscheidung lautet nie "X ja/nein", sondern "X statt
            # Y" — und die Darstellung trägt das längst (das kuratierte Radar
            # zeigt acht Felder).
            subfields = [{"slug": slugify_term(x), "label": x, "query": x}
                         for x in terms]
        else:
            subfields = [{"slug": "query", "label": name or query, "phrase": None}]

    scopes_out: list[dict] = []
    cells_out: list[dict] = []
    n_signals = 0
    ev_ids: set[int] = set()

    readouts: list[dict] = []
    for sf in subfields:
        sf_query = sf.get("query") or query
        rows = load_query_signals(
            conn, sf_query, phrase=sf.get("phrase"), ids=sf.get("ids")
        )
        n_signals += len(rows)
        scopes_out.append({
            "slug": sf["slug"],
            "label": sf.get("label") or sf["slug"],
            "n_signals": len(rows),
        })
        terms = field_terms_of(sf_query, sf.get("phrase") or "")
        sf_cells = compute_cells(conn, rows, regions=regions,
                                 dimension_set=dimension_set,
                                 regulated=regulated, today=today,
                                 field_terms=terms)
        tech_cell = next((c for c in sf_cells
                          if c["dimension"] in ("technology", "T")), None)
        readouts.append({
            "scope_slug": sf["slug"],
            **readout(sf_cells, sf.get("label") or sf["slug"],
                      (tech_cell or {}).get("lead_time")),
        })
        for c in sf_cells:
            ev = c["evidence"] or []
            ev_ids.update(ev)
            cells_out.append({
                "scope_slug": sf["slug"],
                "dimension": c["dimension"],
                "region": c["region"],
                "horizon": c["horizon"],
                "effective": c["horizon"],   # Overrides gibt es nur für gespeicherte Radare
                "score": c["score"],
                "n_signals": c["n_signals"],
                "method": c["method"],
                "rationale": c["rationale"],
                "basis": c.get("basis"),
                "lead_time": c.get("lead_time"),
                "evidence": ev,
                "override_horizon": None,
                "override_note": None,
            })

    # Evidenz einmal auflösen — der Client soll nie nachladen müssen.
    evidence: dict[str, dict] = {}
    if ev_ids:
        for r in conn.execute(
            "SELECT id, title_en, source_url, source_name FROM trends "
            "WHERE id = ANY(%s)", (sorted(ev_ids),)
        ).fetchall():
            evidence[str(r["id"])] = {
                "id": r["id"], "title": r["title_en"],
                "source_url": r["source_url"], "source_name": r["source_name"],
            }

    order = (["T", "L", "E", "S", "P", "En"] if dimension_set == "pestel"
             else ["technology", "regulatory", "market", "adoption"])
    dims = [d for d in order if any(c["dimension"] == d for c in cells_out)]

    # Feld-Prüfung über die Vereinigung aller Teilfeld-Treffer.
    seen_ids: set[int] = set()
    all_rows: list[dict] = []
    for term in (split_query_terms(query) or [query]):
        for r in load_query_signals(conn, term):
            if r["id"] not in seen_ids:
                seen_ids.add(r["id"])
                all_rows.append(r)
    field_check = field_coherence(conn, all_rows)

    return {
        "field_check": field_check,
        "readouts": readouts,
        "config": {
            "slug": "__query__",
            "name": name or query,
            "description": None,
            "regions": regions,
            "regulated": regulated,
            "kind": "query",
        },
        "scopes": [{"slug": s["slug"], "label": s["label"]} for s in scopes_out],
        "dimensions": dims,
        "regions": regions,
        "cells": cells_out,
        "generated": None,          # nicht persistiert → kein Lauf-Datum
        "n_signals": n_signals,
        "origin": {"kind": "query", "query": query,
                   "field_signals": {s["slug"]: s["n_signals"] for s in scopes_out}},
        "evidence": evidence,
    }


def compute(config_slug: str, today: date | None = None) -> int:
    today = today or date.today()
    with get_connection() as conn:
        cfg = conn.execute(
            "SELECT id, slug, name, regions, window_months, regulated, dimension_set "
            "FROM radar_configs WHERE slug = %s",
            (config_slug,),
        ).fetchone()
        if not cfg:
            raise SystemExit(f"Radar-Konfiguration {config_slug!r} nicht gefunden")
        regions = cfg["regions"]
        regions = json.loads(regions) if isinstance(regions, str) else (regions or [])
        regions = [r for r in regions if r in JURISDICTIONS] or ["GLOBAL"]
        regulated = bool(cfg.get("regulated"))
        dimension_set = cfg.get("dimension_set") or "strategic"

        scopes = conn.execute(
            "SELECT slug, label, include_terms, exclude_terms, selector, "
            "query_text, phrase, cluster_run_id, cluster_idx, meta "
            "FROM radar_scopes "
            "WHERE config_id = %s ORDER BY sort_order, id",
            (cfg["id"],),
        ).fetchall()
        if not scopes:
            raise SystemExit(f"Radar {config_slug!r} hat keine Scopes")

        run = conn.execute(
            "INSERT INTO radar_runs (config_id, n_scopes) VALUES (%s, %s) RETURNING id",
            (cfg["id"], len(scopes)),
        ).fetchone()
        run_id = run["id"]

        n_cells = n_signals = 0
        all_readouts: list[dict] = []
        for sc in scopes:
            rows = resolve_scope(conn, dict(sc))
            n_signals += len(rows)
            log.info("scope %-22s %6d Signale", sc["slug"], len(rows))

            if rows:
                conn.executemany(
                    "INSERT OR IGNORE INTO radar_scope_trends (run_id, scope_slug, trend_id) "
                    "VALUES (?, ?, ?)",
                    [(run_id, sc["slug"], r["id"]) for r in rows],
                )

            scope_cells = compute_cells(conn, rows, regions=regions,
                                        dimension_set=dimension_set,
                                        regulated=regulated, today=today,
                                        field_terms=scope_field_terms(dict(sc)))
            # Trendreife nach Blechschmidt: derselbe Zellenbestand, in seine
            # Form gebracht. Der Import steht hier statt oben, weil
            # radar_maturity aus radar_horizons importiert — ein Modul-Zyklus
            # sonst.
            from .radar_maturity import (maturity, seed_relevance_criteria,
                                         store_maturity, suggest_relevance)
            mat = maturity(rows, scope_cells, today=today)
            meta = sc["meta"] if isinstance(sc["meta"], dict) else \
                json.loads(sc["meta"] or "{}") if sc["meta"] else {}
            store_maturity(conn, run_id, sc["slug"], mat,
                           suggest_relevance(meta, mat))

            tech_cell = next((c for c in scope_cells
                              if c["dimension"] in ("technology", "T")), None)
            all_readouts.append({
                "scope_slug": sc["slug"],
                **readout(scope_cells, sc["label"],
                          (tech_cell or {}).get("lead_time")),
            })
            cells = [
                (run_id, sc["slug"], c["dimension"], c["region"], c["horizon"],
                 c["score"], c["n_signals"], c["method"], c["rationale"],
                 json.dumps(c["evidence"]), c.get("basis"),
                 json.dumps(c.get("lead_time")) if c.get("lead_time") else None)
                for c in scope_cells
            ]
            conn.executemany(
                "INSERT INTO radar_cells (run_id, scope_slug, dimension, region, "
                "horizon, score, n_signals, method, rationale, evidence, basis, "
                "lead_time) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                cells,
            )
            n_cells += len(cells)

        # Relevanz-Kriterien anlegen, falls das Radar noch keine hat. Sie
        # bleiben UNBEWERTET — die Relevanz gehört dem Nutzer (Owner-
        # Entscheidung 2026-08-04: leer, mit sichtbarem Vorschlag daneben).
        from .radar_maturity import seed_relevance_criteria
        seed_relevance_criteria(cfg["id"])

        conn.execute("UPDATE radar_runs SET n_cells = %s, n_signals = %s, "
                     "readouts = %s WHERE id = %s",
                     (n_cells, n_signals, json.dumps(all_readouts), run_id))
        # Alte Runs derselben Konfiguration aufräumen (nur den neuesten behalten +1).
        old = conn.execute(
            "SELECT id FROM radar_runs WHERE config_id = %s ORDER BY id DESC OFFSET 2",
            (cfg["id"],),
        ).fetchall()
        for o in old:
            conn.execute("DELETE FROM radar_runs WHERE id = %s", (o["id"],))
        conn.commit()
        log.info("Run %d: %d Scopes, %d Zellen, %d Signale",
                 run_id, len(scopes), n_cells, n_signals)
        return run_id


def main() -> None:
    ap = argparse.ArgumentParser(description="Horizont-Radar berechnen")
    ap.add_argument("--config", default="alt-protein", help="Radar-Slug")
    ap.add_argument("--migrate", action="store_true", help="nur Tabellen anlegen")
    ap.add_argument("--seed", action="store_true", help="Referenz-Radar anlegen")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    migrate()
    if args.migrate:
        return
    if args.seed:
        from .radar_seed import seed
        seed()
    compute(args.config)


if __name__ == "__main__":
    main()


# ---------------------------------------------------------------------------
# Signalwolke: jedes Signal einzeln platzieren
# ---------------------------------------------------------------------------
# Die Zellenlogik klassifiziert JEDES Signal, bevor sie aggregiert — welchen
# Sub-Typ ein Regulatorik-Signal hat, ob eine Produktmeldung Pilot oder Handel
# ist, ob ein Signal Forschung oder Anwendung ist. Diese Information wird beim
# Zusammenfassen auf 32 Zellen weggeworfen.
#
# Die Wolke wirft sie nicht weg. Sie zeigt die VERTEILUNG statt ihres Mittels:
# wo die Masse eines Felds liegt, wie breit sie streut, wo einzelne Ausreißer
# sitzen. Und jeder Punkt ist ein echtes Signal mit Titel und Quelle — die
# Nachvollziehbarkeit, die einer aggregierten Zelle fehlt.
#
# Dieselben Klassifikatoren wie in den Zellen, damit Wolke und Zelle nie
# auseinanderlaufen: eine Zelle IST das Mittel ihrer Punkte.

CLOUD_DIMENSIONS = ("technology", "regulatory", "market", "adoption")


def place_signal(row, today: date, field_terms: list[str] | None = None) -> dict | None:
    """Ein Signal auf (Dimension, Stufe) abbilden.

    Stufe 1 = H1 (belegt Marktzugang / Zulassung / Nachfrage),
    Stufe 2 = H2 (Übergang: Antrag, Pilot, erste Einführung),
    Stufe 3 = H3 (vorwettbewerblich: Forschung, Patent, versperrter Weg).

    Gibt None zurück, wenn ein Signal für keine Dimension etwas belegt — das ist
    der Regelfall für Meinungsstücke und Nachrichten-Roundups, und sie gehören
    nicht in die Wolke.
    """
    st = row.get("trend_signal_type")
    text = _text(row)

    if st == "regulation":
        sub = reg_subtype(row, field_terms)
        stage = {"granted": 1, "filed": 2, "trial": 2,
                 "forming": 3, "gap": 3, "denied": 3}.get(sub)
        if not stage:
            return None
        return {"dim": "regulatory", "stage": stage, "kind": sub}

    if st == "product_launch":
        if ESSAY_TITLE.search(_title(row)):
            return None            # Kommentar ist kein Ereignis
        if MARKET_PILOT.search(text):
            return {"dim": "market", "stage": 2, "kind": "pilot"}
        if MARKET_SCALE.search(text) or MARKET_MAGNITUDE.search(text):
            return {"dim": "market", "stage": 1, "kind": "trade"}
        return {"dim": "market", "stage": 2, "kind": "launch"}

    if st in ("research", "patent"):
        return {"dim": "technology", "stage": 3, "kind": st}

    if st == "partnership":
        return {"dim": "technology", "stage": 2, "kind": "partnership"}

    if st == "consumer_behavior":
        return {"dim": "adoption", "stage": 1, "kind": "consumer"}

    if st == "market_shift":
        if DEMAND_MARKERS.search(text):
            return {"dim": "adoption", "stage": 2, "kind": "demand"}
        if MARKET_SCALE.search(text) or MARKET_MAGNITUDE.search(text):
            return {"dim": "market", "stage": 1, "kind": "trade"}
        return None

    if st == "funding":
        return {"dim": "technology", "stage": 2, "kind": "funding"}

    return None


def signal_cloud(rows: list[dict], *, today: date | None = None,
                 field_terms: list[str] | None = None,
                 cap: int = 4000) -> dict:
    """Alle platzierbaren Signale eines Felds als Punktwolke.

    Gedeckelt nach Aktualität: ein Cluster hat bis zu 40.000 Mitglieder, und
    jenseits einiger tausend Punkte sieht ein Auge ohnehin nur noch Fläche. Was
    weggelassen wurde, steht in der Antwort — ein stiller Schnitt wäre eine
    Behauptung über Vollständigkeit, die nicht stimmt.
    """
    today = today or date.today()
    dated = sorted((r for r in rows if r["event_date"]),
                   key=lambda r: r["event_date"])
    placed = []
    dropped = 0
    for r in dated:
        p = place_signal(r, today, field_terms)
        if p:
            placed.append((r, p))
        else:
            dropped += 1

    # Systematische Stichprobe über die ZEIT, nicht die jüngsten N. Nach
    # Aktualität zu deckeln sah zuerst vernünftig aus, tötete aber genau die
    # Achse, für die die Wolke gebaut ist: bei einem großen Cluster stammten
    # alle 4.000 gezeigten Punkte aus demselben Jahr, die Historie verschwand.
    # Ein gleichmäßiger Schnitt durch die chronologisch sortierte Liste erhält
    # die Verteilung über die Jahre — sichtbar wird dann, wie ein Feld nach
    # innen wandert.
    step = max(1, len(placed) // cap) if cap else 1
    sample = placed[::step][:cap]
    points = []
    for r, p in sample:
        points.append({
            "id": r["id"],
            "d": CLOUD_DIMENSIONS.index(p["dim"]),
            "s": p["stage"],
            "k": p["kind"],
            "y": r["event_date"].year,
            "t": (r.get("title_en") or "")[:120],
            "r": sorted(regions_of(r))[:2],
        })
    per_dim = {d: sum(1 for p in points if CLOUD_DIMENSIONS[p["d"]] == d)
               for d in CLOUD_DIMENSIONS}
    return {
        "points": points,
        "n_total": len(rows),
        "n_placed": len(placed),
        "n_shown": len(points),
        "n_unplaceable": dropped,
        "sample_step": step,
        "capped": step > 1,
        "per_dimension": per_dim,
        "dimensions": list(CLOUD_DIMENSIONS),
    }
