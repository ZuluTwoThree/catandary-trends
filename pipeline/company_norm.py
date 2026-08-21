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
