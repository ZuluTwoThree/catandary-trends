"""Firmennamen-Normalisierung für die Startup-Explorer-Entity-Resolution (#87).

Eine Funktion, überall dieselbe: Ingester (GLEIF/Companies House), der
Resolution-Lauf und spätere Brücken (Patent-Assignees) müssen denselben
Schlüssel erzeugen, sonst matcht nichts. Deshalb lebt das hier in pipeline/
und nicht in einem Skript.

Designentscheidungen (Messungen 2026-08-21, docs/startup_explorer_plan.md §4):
- Rechtsform-Suffixe werden nur am NAMENSENDE entfernt (wiederholt): "Spa
  Beauty Ltd" -> "spa beauty", nicht "beauty". Ein Anywhere-Strip frisst
  echte Namensbestandteile.
- Der Schlüssel ist bewusst NICHT eindeutig — er ist Stufe-2-Material und
  braucht immer ein zweites Merkmal (Land/Stadt/Sektor), siehe den
  "Realize, Inc."-Befund (60 fremde Patente ohne Kontext-Gate).
- Nicht-lateinische Namen (CJK etc.) passieren unverändert außer
  Kleinschreibung/Whitespace — besser ein konservativer Schlüssel als ein
  zerstörter.
"""
from __future__ import annotations

import re
import unicodedata

# Rechtsformen, die am Namensende stehen (mehrsprachig; nur ganze End-Tokens).
# "co" und "spa" sind absichtlich NUR hier und nicht in einem Anywhere-Strip.
_LEGAL_SUFFIXES = {
    "inc", "incorporated", "corp", "corporation", "co", "company",
    "llc", "llp", "lp", "ltd", "limited", "plc", "pllc", "pc",
    "gmbh", "mbh", "ag", "kg", "ug", "ohg", "gbr", "ev",
    "sa", "sas", "sarl", "sl", "srl", "spa", "spzoo", "zoo",
    "bv", "nv", "ab", "oy", "oyj", "asa", "aps", "kft", "zrt", "sro",
    "doo", "dd", "pty", "pvt", "bhd", "sdn", "kk", "gk",
    "corpn", "intl", "international",
}

# Häufige End-Floskeln nach dem Rechtsform-Strip ("Acme Technologies" ==
# "Acme"): NICHT entfernt — zu aggressiv, "General Electric Company" würde
# mit "General Electric Technologies" kollidieren. Bewusst weggelassen.

_WS_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)


def _ascii_fold(s: str) -> str:
    """Diakritika entfernen (é->e), nicht-lateinische Zeichen erhalten."""
    out = []
    for ch in s:
        decomposed = unicodedata.normalize("NFKD", ch)
        stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
        # Nur übernehmen, wenn ein ASCII-Zeichen herauskommt (é->e). Sonst
        # Original behalten — NFKD würde z. B. japanische Dakuten abstreifen
        # (プ->フ) und damit den Namen verfälschen.
        out.append(stripped if stripped and stripped.isascii() else ch)
    return "".join(out)


def norm_company_name(name: str | None) -> str:
    """Kanonischer Vergleichsschlüssel eines Firmennamens.

    >>> norm_company_name("Müller & Söhne GmbH & Co. KG")
    'muller and sohne'
    >>> norm_company_name("Spa Beauty Ltd.")
    'spa beauty'
    """
    if not name:
        return ""
    s = _ascii_fold(name).lower()
    s = s.replace("&", " and ")
    s = _PUNCT_RE.sub(" ", s)
    tokens = _WS_RE.sub(" ", s).strip().split(" ")
    # Rechtsform-Suffixe am Ende wiederholt abwerfen ("... GmbH & Co KG").
    # "and" direkt vor einem Suffix gehört zur Floskel ("& Co") und fällt mit.
    while tokens and tokens[-1] in _LEGAL_SUFFIXES:
        tokens.pop()
        while tokens and tokens[-1] == "and":
            tokens.pop()
    return " ".join(tokens)


_CIK_RE = re.compile(r"/edgar/data/0*(\d+)/")


def cik_from_edgar_url(url: str | None) -> str | None:
    """CIK (ohne führende Nullen) aus einer EDGAR-Archiv-URL."""
    m = _CIK_RE.search(url or "")
    return m.group(1) if m else None


_CORDIS_RE = re.compile(r"cordis\.europa\.eu/project/id/(\d+)#org-(\d+)")


def pic_from_cordis_url(url: str | None) -> tuple[str, str] | None:
    """(projectID, organisationID/PIC) aus einer CORDIS-URL des Ingesters."""
    m = _CORDIS_RE.search(url or "")
    return (m.group(1), m.group(2)) if m else None


# ---------------------------------------------------------------------
# Neu-Anlage-Ausschluss (#94 Teil 1): Fondsvehikel / Presse-Artefakte.
#
# `startup_companies.excluded` (2.648 'fund_vehicle' + 494
# 'press_name_artifact', Stand 2026-08-28) trägt Werte, die beim initialen
# Rebuild (#87) NICHT über eine Code-Regel gesetzt wurden — build_startup_
# companies.py kennt die Spalte gar nicht, sie wurde nachträglich per Hand
# geprüft (Merge-Audit-Stichprobe, Plan §7). Die zwei Funktionen hier sind
# KEINE Reproduktion dieser manuellen Prüfung, sondern aus dem beobachteten
# Bestand rückgeleitete, konservative Heuristiken für NEU anzulegende
# Firmen im additiven Update-Pfad:
#   - press_name_artifact: `name like '%:%' or length(name) > 60` trifft
#     (Stichprobe 2026-08-28) alle 494 bestehenden press_name_artifact-Zeilen
#     exakt — Regex-Extraktion griff dort die ganze Schlagzeile statt des
#     Firmennamens ("Another Super Angel Levels Up: ...", "UPDATE: ...").
#     Nur auf Presse-Kandidaten angewandt (die Anomalie ist presse-spezifisch).
#   - fund_vehicle: alle 2.648 bestehenden Zeilen enthalten "fund" als
#     eigenständiges Token in name_norm (0 Gegenbeispiele) — Investment-
#     Vehikel, die trotz des INDUSTRY_VERTICAL-Filters in ingest_secform_d.py
#     durchrutschen (z. B. unter "Commercial"/"Other Technology" statt
#     "Pooled Investment Fund" gemeldet). ACHTUNG: diese Regel ist nicht
#     erschöpfend gegen den BESTEHENDEN Korpus geprüft — eine Stichprobe
#     zeigte ~700 unmarkierte fund-artige Namen im Bestand (die manuelle
#     Prüfung war selbst nicht vollständig). Das ist ein bekannter, hier
#     bewusst nicht rückwirkend behobener Punkt (Rebuild-Backlog, kein
#     Update-Pfad-Bug) — siehe docs/startup_explorer_plan.md §7.
_FUND_TOKEN_RE = re.compile(r"(?:^|\s)fund(?:$|\s)")

# Presse-Extraktion klebt Geo-Possessive an Firmennamen ("Stockholm's Pixelgen
# Technologies", "Canada's Mid-Day Squares") — der Praefix verhindert den
# Stufe-B-Match auf die bestehende Firma und erzeugt Dubletten (#94-Dry-Run
# 2026-08-29: 'Stockholm's Pixelgen Technologies' vs. Bestand #124520).
# Heuristik bewusst eng: EIN fuehrendes, grossgeschriebenes Token >= 5 Zeichen
# mit 's-Possessiv (gerade/typografische Apostrophe), danach mindestens ein
# weiteres Token mit >= 4 Zeichen Rest. "McDonald's" (nichts danach) und
# "Ninety One's ..." (Zwei-Token-Praefix) bleiben unberuehrt; der 5-Zeichen-
# Boden schuetzt Kurz-Marken wie "Levi's".
_POSSESSIVE_PREFIX_RE = re.compile(r"^([A-Z][A-Za-z]{4,})[\u2019\u2018'`]s\s+(\S.{3,})$")


def strip_possessive_prefix(name: str | None) -> str:
    """"Stockholm's Pixelgen Technologies" -> "Pixelgen Technologies"."""
    if not name:
        return name or ""
    m = _POSSESSIVE_PREFIX_RE.match(name.strip())
    return m.group(2) if m else name


def classify_new_company_exclusion(name: str, sources: set[str] | frozenset[str] = frozenset()) -> str | None:
    """None, 'fund_vehicle' oder 'press_name_artifact' für eine NEU
    anzulegende Firma (siehe Modul-Docstring oben für Herleitung/Grenzen).

    >>> classify_new_company_exclusion("Sovereign Fund IV, LLC")
    'fund_vehicle'
    >>> classify_new_company_exclusion("UPDATE: Acme Raises $5M In Really Long Headline Text Here", {"press"})
    'press_name_artifact'
    >>> classify_new_company_exclusion("Acme Robotics Inc")
    """
    name = (name or "").strip()
    if "press" in sources and (":" in name or len(name) > 60):
        return "press_name_artifact"
    if _FUND_TOKEN_RE.search(norm_company_name(name)):
        return "fund_vehicle"
    return None


def _char_trigrams(s: str) -> set[str]:
    """Zeichen-Trigramme mit Padding, angelehnt an pg_trgm (best-effort
    Python-Näherung — nicht bit-identisch zu Postgres' `similarity()`, aber
    nah genug für eine Selbst-Kontrolle im Dry-Run, siehe #94)."""
    s = f"  {(s or '').strip().lower()}  "
    if len(s) < 3:
        return set()
    return {s[i:i + 3] for i in range(len(s) - 2)}


def trigram_similarity(a: str, b: str) -> float:
    """Jaccard-Ähnlichkeit über Zeichen-Trigramme, Bereich [0, 1].

    >>> round(trigram_similarity("Acme Robotics Inc", "Acme Robotics Inc"), 2)
    1.0
    >>> trigram_similarity("Acme Robotics", "Totally Different Co")
    0.0
    """
    ta, tb = _char_trigrams(a), _char_trigrams(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)
