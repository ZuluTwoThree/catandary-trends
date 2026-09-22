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
  3. Ein Draft gilt als „aequivalent", wenn JEDE beanstandete Zahl so belegt
     ist. Personennamen-Holds werden nicht vom Modell entschieden (die Regel
     „refer to people exactly as the source does" ist eine Formregel, keine
     Bedeutungsfrage); ein Draft mit Namens-Hold bleibt beim Menschen.

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


def evidence_carries_number(evidence: str) -> bool:
    """Traegt der Beleg eine Ziffer? Zahlwoerter gibt es in jeder Quellsprache
    („tizennégy", „три тисячі", „Dreißigerjahren", „zehnjähriger") — eine
    Wortliste kann das nicht abdecken (gemessen 22.09.: alle zehn Belege ohne
    Ziffer waren echte Zahlwoerter). Deshalb entscheidet bei fehlender Ziffer
    die vom Modell benannte Form (NON_DIGIT_FORMS), nicht eine Liste."""
    return bool(re.search(r"\d", evidence))


def sentence_with(body: str, token: str) -> str:
    """Der Satz des Artikels, der das beanstandete Token traegt (sonst der Body-Anfang)."""
    t = token.strip(".,;:")
    for s in re.split(r"(?<=[.!?])\s+", body or ""):
        if t and t in s:
            return s.strip()
    return (body or "")[:300]


def verify_verdict(v: FigureVerdict | None, source: str) -> tuple[bool, str]:
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
    return True, v.form or "equivalent"


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
    out["names"] = ungrounded_names(body, source)
    figs = ungrounded_specifics(body, source)
    seen = set()
    for tok in figs:
        key = tok.strip(".,;:")
        if key in seen:
            continue
        seen.add(key)
        sent = sentence_with(body, tok)
        v = ask_model(sent, key, source, model)
        ok, why = verify_verdict(v, source)
        out["figures"].append({"token": key, "sentence": sent[:240], "ok": ok, "why": why,
                               "evidence": (v.evidence if v else "")[:200], "form": (v.form if v else ""),
                               "note": (v.note if v else "")[:160]})
    if out["garbled"]:
        out["decision"], out["why"] = "human", "garbled: " + "; ".join(out["garbled"][:2])
    elif out["truncated"]:
        out["decision"], out["why"] = "human", "truncated body"
    elif out["names"]:
        out["decision"], out["why"] = "human", "person name not in source: " + ", ".join(out["names"][:3])
    elif not out["figures"]:
        out["decision"], out["why"] = "human", "no gate objection found (re-check would publish)"
    elif all(f["ok"] for f in out["figures"]):
        out["decision"], out["why"] = "equivalent", "; ".join(f'{f["token"]} = "{f["evidence"]}" ({f["form"]})' for f in out["figures"])[:400]
    else:
        bad = [f for f in out["figures"] if not f["ok"]]
        out["decision"], out["why"] = "human", "not supported: " + "; ".join(f'{f["token"]} ({f["why"]})' for f in bad)[:300]
    return out


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
        model: str | None = None) -> dict:
    from pipeline import llamacpp_client
    served = llamacpp_client.served_model_id()
    if not served:
        raise SystemExit("kein llama-server auf :8090 — Ruhezustand herstellen oder Cycle abwarten (Exit 3)")
    model = model or served
    rows = held_drafts(limit, ids)
    report = {"date": datetime.now(timezone.utc).isoformat(timespec="seconds"), "model": served,
              "dry_run": not apply, "checked": 0, "equivalent": 0, "human": 0, "published": 0, "items": []}
    for t in rows:
        item = check_draft(t, model)
        report["checked"] += 1
        if item["decision"] == "equivalent":
            report["equivalent"] += 1
            if apply and publish_equivalent(item):
                report["published"] += 1
                item["published"] = True
        else:
            report["human"] += 1
        report["items"].append(item)
        logger.info("#%d %-10s %s", item["id"], item["decision"], item["why"][:120])
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    return report
