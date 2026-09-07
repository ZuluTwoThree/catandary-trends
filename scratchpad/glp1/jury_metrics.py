"""Misst, was die Jury bewertet — nicht, was leicht zu zaehlen ist.

jury_17 senkte die Spezifitaet auf 5, waehrend unsere Faktenquote von 0,94 auf
4,15 stieg. Die Quote misst Dichte, nicht Einschlaegigkeit. Hier stehen die
drei Kriterien, die den Abstand tragen:

  ZEIT      einschlaegige Zukunftstermine + Zahl der tragenden Quellen
  SPEZ      benannte Akteure, davon mit Zahl im selben Satz; Zahlenspezifika
  AUFWAND   Optionen mit beziffertem Aufwandsfeld
  ABDECKUNG Ebenen der Innovationskette mit datierter, belegter Aussage
"""
import re, sys, json, pathlib
sys.path.insert(0, "/home/dirk/projects/ct-dev")
from scripts import corpus_research as cr
from pipeline import dossier_structure as ds

TOPIC = ("glp-1", "glp1", "incretin", "semaglutide", "tirzepatide", "obesity",
         "cagrisema", "retatrutide", "survodutide", "petrelintide",
         "orforglipron", "amycretin", "liraglutide", "amylin", "weight loss",
         "wegovy", "ozempic", "mounjaro", "zepbound")
LEVEL = {"science": ("stud", "trial", "paper", "journal", "nejm", "review",
                     "research", "phase 2", "phase 3", "randomi"),
         "patents": ("patent", "spc", "supplementary protection", "epo",
                     "filing", "ep ", "wo20", "us1"),
         "funding": ("grant", "horizon", "eic", "funding", "raised",
                     "series ", "award", "budget", "consortium"),
         "market": ("revenue", "market", "sales", "reimburse", "price",
                    "launch", "share", "guidance", "acquisition", "spend")}
_FIG = re.compile(r"[€$£]\s?\d|\b\d+(?:[.,]\d+)?\s?%|\b\d[\d.,]*\s?(?:m|bn|"
                  r"million|billion|thousand)\b|\bn\s?=\s?\d", re.IGNORECASE)
_CITE = re.compile(r"\[\[[A-Z]+\d+\]\]|\]\(https?://")
_ORG = re.compile(r"\b(?:[A-Z][a-z]+(?:\s+(?:[A-Z][a-z]+|&))*\s+"
                  r"(?:Nordisk|Lilly|Pharma\w*|Health|Foods?|Nestl\w+|AG|SA|"
                  r"Inc|Ltd|plc|Commission|Agency|EMA|FDA|EFSA|NHS))\b")
_ACRONYM = re.compile(r"\b(?:EMA|FDA|EFSA|NHS|EPO|CHMP|G-BA|HAS|NICE|WHO|USPTO)\b")


def body(md: str) -> str:
    """Fliesstext ohne Anhaenge und ohne Quellenliste."""
    out = []
    for part in re.split(r"\n(?=## )", md):
        h = part.split("\n", 1)[0].lower()
        if any(k in h for k in ("sources", "quellen", "appendix", "anhang",
                                "coverage", "measured", "how this")):
            continue
        out.append(part)
    return "\n".join(out)


def sentences(text):
    return [" ".join(s.split()) for s in ds._SENT_SPLIT.split(text)
            if len(s.split()) > 2]


def on_topic(s: str) -> bool:
    low = s.lower()
    return any(t in low for t in TOPIC)


def measure(path: pathlib.Path) -> dict:
    md = path.read_text()
    txt = body(md)
    sents = sentences(txt)
    words = len(txt.split())

    # ZEIT: einschlaegige Zukunftstermine
    fut, fut_src = [], set()
    for s in sents:
        cs = cr._clean_sentence(s)
        w = cr._when_label(cs, 2026)
        if not w or not on_topic(cs):
            continue
        if not any(mk in cs.lower() for mk in cr._FORWARD_MARKERS):
            continue
        fut.append((w, cs[:90]))
        for m in _CITE.finditer(s):
            fut_src.add(m.group(0))
        for m in re.finditer(r"\]\((https?://[^/)]+)", s):
            fut_src.add(m.group(1))

    # SPEZ: benannte Akteure
    actors, actors_fig = set(), set()
    for s in sents:
        found = set()
        for raw in s.split():
            w = raw.strip(".,;:!?()[]\"'*").lower()
            if cr._is_substance(w):
                found.add(w)
        found |= {m.group(0) for m in _ORG.finditer(s)}
        found |= {m.group(0) for m in _ACRONYM.finditer(s)}
        actors |= found
        if _FIG.search(s):
            actors_fig |= found
    figures = sum(1 for s in sents if _FIG.search(s))

    # AUFWAND
    opts = ds.option_blocks(txt)
    effort_ok = 0
    for b in opts:
        v = ds._field_value(b, r"effort|investment")
        if v and not ds.is_placeholder(v):
            effort_ok += 1

    # ABDECKUNG
    cov = {}
    for lvl, keys in LEVEL.items():
        cov[lvl] = sum(1 for s in sents
                       if any(k in s.lower() for k in keys)
                       and re.search(r"\b(?:19|20)\d\d\b", s)
                       and _CITE.search(s))
    return {"file": path.name, "words": words,
            "future_events": len(fut), "future_sources": len(fut_src),
            "actors": len(actors), "actors_with_figure": len(actors_fig),
            "figure_sentences": figures,
            "options": len(opts), "effort_sized": effort_ok,
            "coverage": cov, "examples": fut[:6]}


if __name__ == "__main__":
    rows = [measure(pathlib.Path(p)) for p in sys.argv[1:]]
    for r in rows:
        print(f"\n=== {r['file']} ({r['words']} Woerter) ===")
        print(f"  Zukunftstermine (einschlaegig): {r['future_events']} "
              f"auf {r['future_sources']} Quellen")
        print(f"  Akteure: {r['actors']}, davon mit Zahl im Satz: "
              f"{r['actors_with_figure']}; Saetze mit Zahl: {r['figure_sentences']}")
        print(f"  Optionen: {r['options']}, Aufwand beziffert: {r['effort_sized']}")
        print(f"  Abdeckung: {r['coverage']}")
        for w, s in r["examples"]:
            print(f"    · {w} — {s}")
    pathlib.Path("scratchpad/glp1/jury_metrics.json").write_text(
        json.dumps(rows, indent=2, ensure_ascii=False))
