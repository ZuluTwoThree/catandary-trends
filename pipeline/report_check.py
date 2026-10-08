"""Belegprüfung modellgeschriebener Berichte (Owner 2026-10-08, MCP Punkt 1).

Anlass: Der Elektrolyse-Bericht vom 07.10. (Nemotron über Open WebUI) zitierte neun
Fachartikel mit DOI — alle erfunden (sechs gibt es nicht, drei führen zu fremden Arbeiten);
er behauptete, Rechtsakte mit `fetch_url` gelesen zu haben, obwohl das Werkzeug nie lief,
und beschrieb ein Nest aus `emerging_nests`, das nie abgefragt wurde. Die Zahlen aus den
Werkzeugen stimmten dagegen.

Diese Prüfung ist deterministisch (kein Modell): sie zieht Kennungen und Zahlen aus dem
Bericht und vergleicht sie mit (a) den Werkzeugergebnissen DIESER Sitzung (Ergebnisspeicher
in `corpus_api`), (b) dem Korpus (DOI, Patentnummer) und (c) auf Wunsch Crossref bzw.
EUR-Lex/Cellar. Ergebnis je Fund: `in_results` | `exists_not_from_tools` | `not_found` |
`title_mismatch` | `unchecked`. Zahlen: belegt, wenn sie (auch gerundet) in einem
Werkzeugergebnis vorkommen — ein Hinweis, kein Urteil.

Reine Funktionen hier; Datenbank- und Netzabfragen kommen als Callables herein (testbar).
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Callable, Iterable

DOI_RE = re.compile(r"\b10\.\d{4,9}/[^\s\"'<>\]\)|,;]+", re.I)
CELEX_RE = re.compile(r"\b3\d{4}[A-Z]{1,2}\d{4}\b")
# EP-3535216-B1 · EP3535216B1 · US 12722991 B2 · WO2024/123456 A1 · CN116622681A
PATENT_RE = re.compile(r"\b(EP|US|WO|CN|JP|KR|DE|GB|FR)[\s\-‑]?((?:19|20)\d{2}[/\-]?\d{5,6}|\d{6,9})"
                       r"(?:[\s\-‑]?([ABCUYTE]\d?))?\b")
CPC_RE = re.compile(r"\b[A-HY]\d{2}[A-Z]\d{1,4}/\d{1,6}\b")
URL_RE = re.compile(r"https?://\S+")
# 3 429 · 3,429 · 3.429 · 1 510 · 6,4 · 6.4 · 87 % · ≈ 420
NUM_RE = re.compile(r"(?<![\w./-])(\d{1,3}(?:[   .,]\d{3})+|\d+(?:[.,]\d+)?)(?![\w/])")
STOP = {"the", "and", "for", "of", "in", "on", "a", "an", "to", "with", "by", "from", "as", "at", "is",
        "der", "die", "das", "und", "mit", "von", "für", "im", "in", "auf", "zu", "ein", "eine"}


def norm_doi(d: str) -> str:
    d = d.strip().rstrip(".").lower()
    d = re.sub(r"^https?://(dx\.)?doi\.org/", "", d)
    return d


def find_dois(text: str) -> list[str]:
    return list(dict.fromkeys(norm_doi(m.group(0)) for m in DOI_RE.finditer(text)))


def find_celex(text: str) -> list[str]:
    return list(dict.fromkeys(CELEX_RE.findall(text)))


def norm_patent(cc: str, num: str, kind: str | None) -> str:
    num = re.sub(r"[/\-]", "", num)
    return f"{cc}-{num}-{kind}" if kind else f"{cc}-{num}"


def find_patents(text: str) -> list[str]:
    out = []
    for m in PATENT_RE.finditer(text):
        out.append(norm_patent(m.group(1), m.group(2), m.group(3)))
    return list(dict.fromkeys(out))


def line_of(text: str, needle: str) -> str:
    i = text.lower().find(needle.lower())
    if i < 0:
        return ""
    a, b = text.rfind("\n", 0, i) + 1, text.find("\n", i)
    return text[a:b if b >= 0 else len(text)]


def words(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-zäöüß0-9]+", (s or "").lower()) if len(w) > 2 and w not in STOP}


def title_matches(report_line: str, real_title: str) -> bool:
    """Steht der echte Titel ungefähr in der Berichtszeile? (≥ 40 % seiner Inhaltswörter)"""
    real = words(real_title)
    if not real:
        return True
    return len(real & words(report_line)) / len(real) >= 0.4


def parse_number(tok: str) -> float | None:
    t = tok.replace(" ", " ").replace(" ", " ")
    if re.fullmatch(r"\d{1,3}(?:[ .,]\d{3})+", t):          # Tausendergruppen
        return float(re.sub(r"[ .,]", "", t))
    t = t.replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def numbers_in(text: str) -> set[float]:
    """Alle Zahlen eines (JSON-)Textes, plus gerundete Varianten (0 und 1 Nachkommastelle)."""
    out: set[float] = set()
    for m in re.finditer(r"-?\d+(?:\.\d+)?", text):
        try:
            v = abs(float(m.group(0)))
        except ValueError:
            continue
        out.update({v, round(v), round(v, 1), round(v, 2)})
        if v <= 1:                                               # Anteil → Prozent
            out.update({round(v * 100), round(v * 100, 1)})
    return out


def masked(text: str) -> str:
    """Kennungen, Links und CPC-Codes ausblenden, damit ihre Ziffern nicht als Zahlen gelten."""
    for rx in (URL_RE, DOI_RE, CELEX_RE, PATENT_RE, CPC_RE):
        text = rx.sub(" ", text)
    text = re.sub(r"(?m)^\s*#+\s*[\d.]+", " ", text)            # Abschnittsnummern
    text = re.sub(r"(?m)^\s*\d+[.)]\s", " ", text)               # Aufzählungen „1. "
    text = re.sub(r"\b\d{4}-\d{2}(-\d{2})?\b", " ", text)        # Datumsangaben
    return text


def report_numbers(text: str) -> list[tuple[str, float, str]]:
    """(Token, Wert, Kontext) für Zahlen im Bericht, ohne Jahreszahlen und Kleinstzahlen."""
    t = masked(text)
    out = []
    for m in NUM_RE.finditer(t):
        tok = m.group(1)
        v = parse_number(tok)
        if v is None:
            continue
        if float(v).is_integer() and (1900 <= v <= 2100 or v < 10):
            continue
        ctx = t[max(0, m.start() - 40):m.end() + 25].replace("\n", " ").strip()
        out.append((tok, v, ctx))
    return out


def number_supported(v: float, pool: set[float]) -> bool:
    return v in pool or round(v) in pool or round(v, 1) in pool


def check_report(text: str, results: list[dict], tool_names: Iterable[str],
                 doi_lookup: Callable[[list[str]], dict[str, str]],
                 patent_lookup: Callable[[list[str]], set[str]],
                 doi_external: Callable[[str], str | None] | None = None,
                 celex_lookup: Callable[[str], str | None] | None = None,
                 max_numbers: int = 60) -> dict:
    """`results` = [{"tool", "text"}] dieser Sitzung; Lookups liefern Korpus/Extern-Treffer."""
    blob = "\n".join(r["text"] for r in results).lower()
    called = Counter(r["tool"] for r in results)

    # Werkzeuge, die der Bericht nennt, die aber nicht liefen
    mentioned = sorted({t for t in tool_names if re.search(rf"\b{re.escape(t)}\b", text)})
    tools = {"called": dict(called), "mentioned_not_called": [t for t in mentioned if t not in called]}

    # DOIs
    dois = find_dois(text)
    corpus = doi_lookup(dois) if dois else {}
    doi_out = []
    for d in dois:
        row = {"doi": d, "line": line_of(text, d)[:200]}
        real = corpus.get(d)
        if real is None and doi_external:
            real = doi_external(d)
            row["source"] = "crossref" if real else None
        elif real is not None:
            row["source"] = "corpus"
        if d in blob:
            row["status"] = "in_results"
        elif real is None:
            row["status"] = "not_found" if doi_external else "not_in_corpus"
        elif not title_matches(row["line"], real):
            row["status"] = "title_mismatch"
        else:
            row["status"] = "exists_not_from_tools"
        if real:
            row["real_title"] = real[:200]
        doi_out.append(row)

    # CELEX
    celex_out = []
    for c in find_celex(text):
        row = {"celex": c}
        if c.lower() in blob:
            row["status"] = "in_results"
        elif celex_lookup:
            title = celex_lookup(c)
            row["status"] = "exists_not_from_tools" if title else "not_found"
            if title:
                row["real_title"] = title[:200]
        else:
            row["status"] = "unchecked"
        celex_out.append(row)

    # Patente
    pats = find_patents(text)
    known = patent_lookup(pats) if pats else set()
    pat_out = []
    for p in pats:
        base = p.rsplit("-", 1)[0] if p.count("-") == 2 else p
        status = ("in_results" if p.lower() in blob or base.lower() in blob
                  else "exists_not_from_tools" if p in known or base in known else "not_in_corpus")
        pat_out.append({"patent": p, "status": status})

    # Zahlen
    pool = numbers_in(blob)
    nums = report_numbers(text)
    unsupported = [{"number": tok, "context": ctx} for tok, v, ctx in nums if not number_supported(v, pool)]

    bad = (sum(r["status"] in ("not_found", "not_in_corpus", "title_mismatch") for r in doi_out)
           + sum(r["status"] == "not_found" for r in celex_out)
           + sum(r["status"] == "not_in_corpus" for r in pat_out))
    summary = {
        "tool_results_checked": len(results),
        "dois": len(doi_out), "dois_problem": sum(r["status"] in ("not_found", "not_in_corpus", "title_mismatch") for r in doi_out),
        "dois_not_from_tools": sum(r["status"] == "exists_not_from_tools" for r in doi_out),
        "celex": len(celex_out), "patents": len(pat_out),
        "numbers": len(nums), "numbers_unsupported": len(unsupported),
        "tools_mentioned_not_called": len(tools["mentioned_not_called"]),
        "verdict": "problems" if bad or tools["mentioned_not_called"] else
                   ("check_numbers" if unsupported else "ok"),
    }
    return {"summary": summary, "tools": tools, "dois": doi_out, "celex": celex_out, "patents": pat_out,
            "numbers_unsupported": unsupported[:max_numbers],
            "how_to_fix": ("Remove or replace every DOI/CELEX/patent with status not_found, not_in_corpus or "
                           "title_mismatch; cite only identifiers that appear in tool results (status "
                           "in_results) or that you have fetched with a tool. Do not claim tool calls that "
                           "were not made. Numbers listed as unsupported must come from a tool result or go.")}
