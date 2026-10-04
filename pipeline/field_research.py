"""Recherche-Entwürfe für Trajectory Sheet und Field Watch — Aufträge, Prompts, Messkontext
(Owner 2026-10-04, Plan `docs/plan_field_research_2026-10-04.md`).

Rein: baut aus Kundenfeld und Messung den Auftrag (`spec`) für den gptr-Worker
(`tools/research/gptr_run.py`). Ausführen, GPU-Handover, Ablage: `scripts/field_research.py`.

Abschnitte:
  regulatory  Anhang A „Rechtsrahmen" des Sheets — Websuche auf Rechts-/Behördenseiten,
              dazu EUR-Lex-Treffer (Cellar) artikelweise als Messkontext.
  reading     Abschnitt 7 „Einordnung" — Zahlen NUR aus der Sheet-Messung, Erklärungen nur
              mit Quelle (Korpus + Web).
  movers      Wochenblatt: je Feld mit deutlicher Bewegung, was dahinter steckt.
  setup       Feld-Einrichtung: Kandidaten-Suchphrasen (danach deterministisch gezählt).
  prospect    Interessenten-Briefing vor dem Erstgespräch (nur Owner).

Alle Texte sind Entwürfe: der Analyst schreibt sie vor der Auslieferung um.
"""
from __future__ import annotations

import json
import re

REGULATORY_DOMAINS = [
    "eur-lex.europa.eu", "ec.europa.eu", "efsa.europa.eu", "echa.europa.eu", "ema.europa.eu",
    "eea.europa.eu", "op.europa.eu", "europarl.europa.eu", "consilium.europa.eu",
    "gesetze-im-internet.de", "bmel.de", "bvl.bund.de", "bfr.bund.de", "bmwk.de", "bmuv.de",
    "umweltbundesamt.de", "bundesnetzagentur.de", "bafa.de", "din.de", "cencenelec.eu",
]

LOCAL_CONTEXT_WORDS = 5_500     # Gemma-26B: -c 16384, ein Slot
CLOUD_CONTEXT_WORDS = 20_000
EXTRA_CONTEXT_WORDS = 1_800

COMMON_RULES = """Regeln (verbindlich):
- Verwende nur Aussagen, die im Kontext stehen. Jede Aussage trägt ihre Quelle als Markdown-Link [Kurzname](URL) mit genau der URL aus dem Kontext.
- Ergänze nichts aus eigenem Wissen: keine Zahlen, Daten, Namen, Rechtsakte oder Fristen, die nicht im Kontext stehen.
- Keine Prognose, keine Empfehlung, keine Rechtsberatung, kein „wir erkennen früh".
- Fehlt zu einem Punkt Evidenz: schreibe „Im Kontext nicht belegt." statt zu raten.
- Deutsch, sachlich, kurze Sätze. Markdown ohne HTML.
- Dies ist ein ENTWURF; ein Analyst schreibt ihn vor der Auslieferung um. Schreibe so, dass er jede Aussage am Link nachprüfen kann."""

REGULATORY_PROMPT = """Du schreibst den ENTWURF für den Anhang „Rechtsrahmen" eines Technology Trajectory Sheets.
Feld: {name} ({name_en}). Suchbegriffe des Feldes: {terms}.

{rules}

Gliederung (Überschriften mit ##, in dieser Reihenfolge):
## Geltende Rechtsakte
## Zulassung und Verfahren
## Kennzeichnung und Angaben
## Laufende Vorhaben und Fristen
## Offene Punkte für den Analysten

Nenne Rechtsakte mit Nummer, Datum und Artikel, wenn der Kontext sie nennt. Der Block „EUR-Lex" im Kontext
listet Rechtsakte aus der amtlichen Datenbank; nenne einen Rechtsakt nur, wenn er für das Feld einschlägig ist.
Höchstens {words} Wörter."""

READING_PROMPT = """Du schreibst den ENTWURF für Abschnitt 7 „Einordnung" eines Technology Trajectory Sheets.
Feld: {name} ({name_en}).

{rules}
- Zahlen kommen AUSSCHLIESSLICH aus dem Block „Catandary-Messung" im Kontext und werden wörtlich übernommen (mit Ebene und Jahr).
- Übernimm KEINE Zahl aus anderen Quellen: keine Marktgrößen, Umsätze, Investitionssummen, Wachstumsraten, Anteile, Prognosen — auch nicht mit Link. Webquellen dienen nur dazu, eine gemessene Bewegung in Worten zu erklären.
- Die Verbesserungsrate K ist eine relative Entwicklung, keine Vorhersage.
- Erkläre eine Bewegung nur, wenn eine Quelle im Kontext sie trägt (mit Link); sonst beschreibe nur, was gemessen ist.

Form: 150 bis 250 Wörter, ein bis drei Absätze, keine Überschriften, keine Aufzählung."""

MOVERS_PROMPT = """Du schreibst den ENTWURF für eine Notiz im Field-Watch-Wochenblatt.
Feld: {name} ({name_en}), Woche {week}. Die Bewegung der Woche steht im Block „Catandary-Messung".

{rules}
- Nenne die Meldungen, die hinter der Bewegung stehen, mit Link. Trägt der Kontext keine Erklärung, schreibe das in einem Satz.

Form: höchstens 120 Wörter, ein Absatz."""

SETUP_PROMPT = """You help define a technology field for corpus monitoring. Field phrase: "{phrase}".
From the context only, collect English search phrases that a title or abstract about this field would contain:
synonyms, technical terms, product categories, established abbreviations (only if unambiguous), and the
names of relevant patent classes (CPC) if the context mentions them.
Return ONLY a JSON object, no prose:
{{"terms": ["2-4 word phrases, 8 to 20 items"], "cpc_hints": ["CPC symbols mentioned in the context"], "notes": "one sentence on ambiguities"}}"""

PROSPECT_PROMPT = """Du schreibst ein internes Briefing (ENTWURF) vor einem Erstgespräch mit „{company}".

{rules}
- Keine Angaben zu Privatpersonen; Organe/Ansprechpartner nur mit Funktion, wenn eine Quelle sie nennt.

Gliederung (## Überschriften): Geschäft und Märkte · Technologiefelder (mit Belegen) · Jüngste Meldungen ·
Patente und Förderung (nur wenn im Kontext) · Mögliche Felder für ein Trajectory Sheet (als Fragen formuliert).
Höchstens {words} Wörter."""


def _words(text: str, n: int) -> str:
    w = str(text).split()
    return " ".join(w[:n]) + (" …" if len(w) > n else "")


def _llm_budget(llm: dict) -> int:
    return CLOUD_CONTEXT_WORDS if (llm or {}).get("backend") == "anthropic" else LOCAL_CONTEXT_WORDS


def base_spec(query: str, llm: dict, *, scope: str = "both", domains=None, language: str = "german",
              total_words: int = 900, max_iterations: int = 3, max_results: int = 6) -> dict:
    return {"query": query, "llm": llm, "scope": scope, "domains": list(domains or []), "language": language,
            "total_words": total_words, "max_iterations": max_iterations, "max_results": max_results,
            "context_word_budget": _llm_budget(llm)}


# ---------------------------------------------------------------------------
# Messkontext (deterministisch, vor dem GPU-Handover berechnet)
# ---------------------------------------------------------------------------
def sheet_measurement_text(d: dict) -> str:
    """Kompakter, zitierfähiger Block aus measure_sheet()."""
    from pipeline.field_watch import TIER_LABELS, TIERS
    f = d["field"]
    lines = [f"Catandary-Messung (Stand {d['measured_on']}; Korpus-Zählungen, keine Marktstatistik) — Feld {f['name']}",
             f"Suchbegriffe: {', '.join(f['terms'])}; CPC-Anker: {', '.join(f.get('cpc') or []) or 'keiner'}"]
    for t in TIERS:
        ser = [x for x in d["series"][t] if x["n"]]
        last5 = [x for x in d["series"][t] if x["y"] >= int(d["measured_on"][:4]) - 5]
        lines.append(f"{TIER_LABELS[t]}: gesamt {d['totals'][t]}, erstes Jahr {d['first'][t]}, Take-off {d['takeoff'][t]}; "
                     "letzte Jahre " + ", ".join(f"{x['y']}: {x['n']}" + (f" ({x['per10k']} je 10.000)" if x['per10k'] is not None else "")
                                                for x in last5) + ("" if ser else " (keine Treffer)"))
    q = d.get("quant") or {}
    if q.get("K_median") is not None:
        lines.append(f"Verbesserungsrate K (relativ, Patentgraph über die CPC-Anker): Median {q.get('K_median')}, jüngster Wert {q.get('K_latest')}")
    if d.get("assignees"):
        lines.append("Patentanmelder, 5 Jahre: " + ", ".join(f"{a['name']} ({a['n']})" for a in d["assignees"][:6]))
    if d.get("subclasses"):
        lines.append("CPC-Subklassen: " + ", ".join(f"{s['sub']} {s.get('title') or ''} ({s['n']})".strip() for s in d["subclasses"][:4]))
    return "\n".join(lines)


def week_measurement_text(f: dict, week: str) -> str:
    """Block für ein Feld aus measure_week()['fields'][i] (Woche gegen Median, Signale der Woche)."""
    from pipeline.field_watch import TIER_LABELS, TIERS
    lines = [f"Catandary-Messung — Feld {f['name']}, Woche {week} (Signale dieser Woche gegen Median der 4 Vorwochen)"]
    for t in TIERS:
        w = f["week"][t]
        lines.append(f"{TIER_LABELS[t]}: {w['n']} (Median {w['median4']})")
    lines.append("Signale der Woche:")
    for t in TIERS:
        for x in (f.get("top") or {}).get(t, [])[:5]:
            lines.append(f"- [{TIER_LABELS[t]}] {x['title']} ({x['date']}, {x['source']}) {x['url']}")
    return "\n".join(lines)


def movers(fields: list[dict], min_delta_pct: int = 50, min_n: int = 5) -> list[dict]:
    """Felder mit deutlicher Bewegung: in einer Ebene >= min_n Signale und >= +min_delta_pct %
    gegen den Median (Median 0 zählt ab min_n)."""
    from pipeline.field_watch import TIERS
    out = []
    for f in fields:
        hits = []
        for t in TIERS:
            n, med = f["week"][t]["n"], f["week"][t]["median4"] or 0
            if n >= min_n and (med == 0 or 100 * (n - med) / med >= min_delta_pct):
                hits.append(t)
        if hits:
            out.append({"field": f, "tiers": hits})
    return out


def eurlex_context(field: dict, max_acts: int = 8, read_acts: int = 3) -> tuple[str, list[dict]]:
    """EUR-Lex-Treffer zu den Stichwörtern des Feldes, die ersten Rechtsakte artikelweise gelesen.
    Liefert (Kontextblock, Quellen)."""
    from pipeline import corpus_api
    kws = field.get("regulatory_keywords") or []
    queries = [[k] for k in kws] or [[t] for t in ([field.get("name_en")] + field["terms"])[:5] if t]
    seen, acts = set(), []
    for q in queries:
        q = [re.sub(r"[^\w\- ]", " ", x).strip() for x in q if x]
        if not q or not all(q):
            continue
        try:
            res = corpus_api.eurlex_search(q, in_force_only=True, limit=3)["results"]
        except corpus_api.ToolError:
            continue
        for a in res:
            if a["celex"] not in seen:
                seen.add(a["celex"])
                acts.append(a)
        if len(acts) >= max_acts:
            break
    acts = acts[:max_acts]
    if not acts:
        return "", []
    blocks = ["EUR-Lex (amtliche Datenbank, in Kraft) — Rechtsakte, deren Titel die Stichwörter enthält:"]
    blocks += [f"- {a['title']} (CELEX {a['celex']}, {a['date']}) {a['url']}" for a in acts]
    terms = (kws or []) + field["terms"][:6]
    base = [a for a in acts if a["type"] in ("REG", "DIR")] or acts
    for a in base[:read_acts]:
        try:
            f = corpus_api.fetch_url(a["url"], max_chars=6000, terms=terms)
        except corpus_api.ToolError:
            continue
        if f["ok"]:
            blocks.append(f"\nSource: {a['url']}\nTitle: {a['title']}\nArtikel: {', '.join(f['articles'][:10])}\n"
                          f"Content: {_words(f['text'], 700)}")
    return "\n".join(blocks), [{"url": a["url"], "title": a["title"], "kind": "eurlex"} for a in acts]


# ---------------------------------------------------------------------------
# Aufträge
# ---------------------------------------------------------------------------
def regulatory_spec(field: dict, llm: dict, words: int = 700, eurlex_block: str = "") -> dict:
    s = base_spec(f"EU and German regulatory framework, authorisation, labelling and pending legislation for {field['name_en']}",
                  llm, scope="web", domains=field.get("regulatory_domains") or REGULATORY_DOMAINS, total_words=words)
    s["custom_prompt"] = REGULATORY_PROMPT.format(name=field["name"], name_en=field["name_en"],
                                                  terms=", ".join(field["terms"]), rules=COMMON_RULES, words=words)
    s["extra_context"] = _words(eurlex_block, EXTRA_CONTEXT_WORDS) if eurlex_block else ""
    return s


def reading_spec(field: dict, measurement: str, llm: dict) -> dict:
    s = base_spec(f"What explains recent developments in {field['name_en']} across research, patents, funding and market",
                  llm, scope="both", total_words=250)
    s["custom_prompt"] = READING_PROMPT.format(name=field["name"], name_en=field["name_en"], rules=COMMON_RULES)
    s["extra_context"] = _words(measurement, EXTRA_CONTEXT_WORDS)
    return s


def movers_spec(field: dict, week: str, measurement: str, since: str, llm: dict) -> dict:
    name_en = field.get("name_en") or field["name"]
    s = base_spec(f"{name_en}: news and announcements in week {week}", llm, scope="both",
                  total_words=120, max_iterations=2)
    s["since"] = since
    s["custom_prompt"] = MOVERS_PROMPT.format(name=field["name"], name_en=name_en, week=week, rules=COMMON_RULES)
    s["extra_context"] = _words(measurement, EXTRA_CONTEXT_WORDS)
    return s


def setup_spec(phrase: str, llm: dict) -> dict:
    s = base_spec(f"terminology, synonyms and technical terms for {phrase}", llm, scope="both",
                  language="english", total_words=300, max_iterations=2)
    s["custom_prompt"] = SETUP_PROMPT.format(phrase=phrase)
    return s


def prospect_spec(company: str, llm: dict, words: int = 600) -> dict:
    s = base_spec(f"{company}: business, technologies, recent announcements, patents and funding", llm,
                  scope="both", total_words=words)
    s["custom_prompt"] = PROSPECT_PROMPT.format(company=company, rules=COMMON_RULES, words=words)
    return s


def parse_setup(report: str) -> dict:
    """JSON aus der Setup-Antwort ziehen (auch wenn das Modell Text drumherum schreibt)."""
    m = re.search(r"\{.*\}", report or "", re.S)
    if not m:
        return {"terms": [], "cpc_hints": [], "notes": "no JSON in model output"}
    try:
        d = json.loads(m.group(0))
    except json.JSONDecodeError:
        return {"terms": [], "cpc_hints": [], "notes": "unparseable JSON in model output"}
    terms = []
    for t in d.get("terms") or []:
        t = re.sub(r"\s+", " ", str(t)).strip().lower()
        if 2 <= len(t) <= 60 and t not in terms:
            terms.append(t)
    return {"terms": terms[:25], "cpc_hints": [str(c).strip() for c in (d.get("cpc_hints") or [])][:10],
            "notes": str(d.get("notes") or "")[:400]}


def setup_yaml(phrase: str, counts: list[dict], cpc_hints: list[str]) -> str:
    """YAML-Entwurf für fields/<kunde>.yaml — Begriffe mit Treffern, schwache auskommentiert."""
    from pipeline.field_watch import slugify
    keep = [c for c in counts if (c.get("market", 0) + c.get("science", 0) + c.get("patent", 0)) >= 5]
    weak = [c for c in counts if c not in keep]
    # Zu breit: ein Begriff, der in einer Ebene > 5x so oft trifft wie die Feldphrase selbst
    # (und > 200), zieht vermutlich fremde Felder mit (Fund 04.10.: „coconut oil" 5.753 Werke
    # bei „plant-based cheese" 113).
    ref = counts[0] if counts else {}
    def broad(c):
        return c is not ref and any(c.get(t, 0) > 200 and c.get(t, 0) > 5 * max(ref.get(t, 0), 1)
                                    for t in ("market", "science", "patent"))
    lines = [f"  - name: {phrase}", f"    name_en: {phrase}", f"    slug: {slugify(phrase)}", "    terms:"]
    for c in keep:
        flag = "ZU BREIT? Gegenprobe mit search_signals/search_patents · " if broad(c) else ""
        lines.append(f"      {'# ' if flag else ''}- {json.dumps(c['term'], ensure_ascii=False)}   # {flag}Markt {c.get('market', 0)} · Wiss. {c.get('science', 0)} · Pat. {c.get('patent', 0)} · Förd. {c.get('funding', 0)}")
    for c in weak:
        lines.append(f"      # - {json.dumps(c['term'], ensure_ascii=False)}   # zu schwach: Markt {c.get('market', 0)} · Wiss. {c.get('science', 0)} · Pat. {c.get('patent', 0)}")
    lines.append(f"    cpc: []   # Kandidaten aus dem Kontext: {', '.join(cpc_hints) or 'keine'} — Anker per scripts/field_watch.py --probe prüfen")
    return "\n".join(lines) + "\n"
