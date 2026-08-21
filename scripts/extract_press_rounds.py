#!/usr/bin/env python3
"""Extrahiert strukturierte Funding-Runden aus Presse-Signalen (#87, Phase 0).

Der Roh-Korpus enthaelt ~106k Presse-Meldungen mit Funding-Titelmustern
("X raises $50M Series B …") aus Fachpresse/Presseverteilern — die einzige
freie Quelle fuer Investor-Namen und Runden-Labels. Dieses Skript zieht daraus
{company, amount, currency, round_label, investors} in die Staging-Tabelle
`startup_press_rounds` (ein Versuch pro raw_entry; Phase 1 loest die Firmen
gegen den Firmenstamm auf).

Zwei Stufen:
  regex   Titel-Parsing (Firma vor Funding-Verb, Betrag, Runde) — GPU-frei
  llm     OpenAI-kompatibler Endpoint (llama-server :8090) fuer Investoren
          und die Faelle, die das Regex nicht sauber trifft
  hybrid  regex zuerst; LLM nur wo Firma/Betrag fehlen oder Investoren im
          Text stehen (Default)

VC-Fonds-Meldungen ("Acme Capital raises $200M fund") sind KEINE Startup-
Runden — sie werden mit round_label='vc_fund', confidence 0 abgelegt und
spaeter ausgefiltert.

    python scripts/extract_press_rounds.py --sample 200 --mode hybrid
    python scripts/extract_press_rounds.py --limit 5000 --mode regex
    python scripts/extract_press_rounds.py --report
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
from pipeline import db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("extract_press_rounds")

LLM_BASE = os.environ.get("PRESS_ROUNDS_LLM_BASE", "http://127.0.0.1:8090/v1")

# Titelmuster der Kandidaten-Auswahl (Postgres ~*). Kein '?' verwenden —
# der DB-Wrapper ersetzt '?' durch Platzhalter.
TITLE_PATTERNS = (
    "(raises|raised|secures|lands|closes|nabs|banks) .{0,4}[0-9]",
    "series [a-e]\\y",
    "\\y(seed|pre-seed) (round|funding)",
)

CUR_MAP = {"$": "USD", "US$": "USD", "USD": "USD", "€": "EUR", "EUR": "EUR",
           "£": "GBP", "GBP": "GBP", "CHF": "CHF", "C$": "CAD", "A$": "AUD"}
SCALE = {"billion": 1e9, "bn": 1e9, "b": 1e9, "million": 1e6, "mn": 1e6,
         "m": 1e6, "k": 1e3, "thousand": 1e3}

AMOUNT_RE = re.compile(
    r"(US\$|C\$|A\$|[$€£]|USD|EUR|GBP|CHF)\s?([\d][\d.,]*)\s*"
    r"(billion|million|thousand|bn|mn|[bmk])?\b", re.I)
ROUND_RE = re.compile(
    r"\b(pre-?seed|seed|series\s+[a-k]\d?|angel|bridge|convertible|growth"
    r"|venture debt|debt|grant|crowdfunding|pre-?ipo)\b", re.I)
# Nur wenn der Akteur selbst einen FONDS raist ("closes $850M new fund"),
# nicht wenn er Geld VON einem Fonds bekommt ("raises $100M from Vision Fund").
FUND_NOISE_RE = re.compile(
    r"(raises|raised|closes|closed|launches|launched|debuts)\s+"
    r"(?:(?:its|a|an)\s+)?(?:(?:new|debut|latest|first|second|third|fourth"
    r"|fifth|inaugural)\s+)?[$€£]?[\d.,]*\s*(?:billion|million|bn|mn|[bmk])?\s*"
    r"(?:(?:new|debut|latest|inaugural|growth|seed|venture|vc|climate|crypto"
    r"|debt|opportunity|flagship|dollar|euro)\s+){0,2}fund\b"
    r"|\b(etf|reit|spac)\b", re.I)
VERB_RE = re.compile(
    r"\s+(raises|raised|secures|secured|lands|landed|closes|closed|nabs"
    r"|nabbed|banks|banked|gets|scores|snags|collects|announces)\s+", re.I)
PREFIX_RE = re.compile(
    r"^(exclusive|breaking|report|scoop|funding alert)\s*[:—-]\s*", re.I)


def _parse_amount(text: str) -> tuple[float | None, str | None, str | None]:
    m = AMOUNT_RE.search(text or "")
    if not m:
        return None, None, None
    cur = CUR_MAP.get(m.group(1).upper(), CUR_MAP.get(m.group(1), None))
    num = m.group(2).replace(",", "")
    try:
        val = float(num)
    except ValueError:
        return None, cur, m.group(0)
    unit = (m.group(3) or "").lower()
    val *= SCALE.get(unit, 1)
    # "$50" ohne Skala ist fast immer Rauschen ("$50 gift card")
    if val < 1e4:
        return None, cur, m.group(0)
    return val, cur, m.group(0).strip()


def _parse_round(text: str) -> str | None:
    m = ROUND_RE.search(text or "")
    if not m:
        return None
    label = re.sub(r"\s+", " ", m.group(1)).strip().title()
    return {"Pre-Seed": "Pre-Seed", "Preseed": "Pre-Seed"}.get(label, label)


def _parse_company(title: str) -> str | None:
    t = PREFIX_RE.sub("", (title or "").strip())
    m = VERB_RE.search(t)
    if not m:
        return None
    head = t[:m.start()].strip(" ,;–—-")
    # Ortsangaben wie "Berlin-based Solarize" auf den Firmennamen reduzieren
    head = re.sub(r"^.{0,40}?[-‑]based\s+", "", head)
    head = re.sub(r"^(startup|fintech|biotech|healthtech|climate tech|ai startup)\s+",
                  "", head, flags=re.I)
    # Beschreiber-Titel: "Australian wind farm monitoring startup Ping" -> "Ping",
    # "WebOps platform Pantheon" -> "Pantheon"
    m2 = re.search(r"\b(?:startup|company|firm|platform|maker|app|provider)\s+"
                   r"([A-Z][\w&.'-]*(?:\s+[A-Z][\w&.'-]*){0,2})$", head)
    if m2:
        head = m2.group(1)
    # Generische Subjekte sind keine Firmennamen — das entscheidet dann das LLM
    if re.match(r"(?i)^(this|that|these|the|a|an|it|its)\b", head):
        return None
    if not 2 <= len(head) <= 80:
        return None
    return head


def regex_extract(title: str, excerpt: str) -> dict:
    """Titel-first-Extraktion. confidence: 0.8 Firma+Betrag, 0.5 eines von
    beiden, 0.0 nichts (oder VC-Fonds-Rauschen)."""
    if FUND_NOISE_RE.search(title or ""):
        return {"company": None, "amount_value": None, "currency": None,
                "amount_text": None, "round_label": "vc_fund",
                "investors": [], "confidence": 0.0}
    company = _parse_company(title)
    val, cur, amt_text = _parse_amount(title)
    if val is None and excerpt:
        val, cur, amt_text = _parse_amount(excerpt[:400])
    rnd = _parse_round(title) or _parse_round((excerpt or "")[:400])
    conf = 0.8 if (company and val) else (0.5 if (company or val) else 0.0)
    return {"company": company, "amount_value": val, "currency": cur,
            "amount_text": amt_text, "round_label": rnd,
            "investors": [], "confidence": conf}


LLM_PROMPT = """Extract the startup funding round from this news item. Reply with ONLY a JSON object:
{"company": string|null, "amount": number|null, "currency": "USD"|"EUR"|"GBP"|string|null, "round": string|null, "investors": [string, ...]}
Rules: company = the startup receiving money (not the investor). amount = full number (e.g. 12000000 for "$12M"). round = e.g. "Seed", "Series B". investors = named lead + participating investors, [] if none named. If this is a VC fund raising its own fund (not a startup round), set company to null and round to "vc_fund".

Title: {title}
Text: {excerpt}
/no_think"""


def llm_extract(client: httpx.Client, model: str, title: str, excerpt: str) -> dict | None:
    prompt = LLM_PROMPT.replace("{title}", (title or "")[:300]) \
                       .replace("{excerpt}", (excerpt or "")[:900])
    try:
        r = client.post(f"{LLM_BASE}/chat/completions", json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0, "max_tokens": 300,
            "response_format": {"type": "json_object"},
        }, timeout=90)
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"]
    except Exception as e:  # noqa: BLE001
        logger.warning("LLM error: %s", type(e).__name__)
        return None
    content = re.sub(r"^```(json)?\s*|\s*```$", "", content.strip())
    try:
        obj = json.loads(content)
    except ValueError:
        return None
    if not isinstance(obj, dict):
        return None
    # Grounding-Gate (gleiche Philosophie wie pipeline/grounding.py): das 8B
    # erfindet plausible VC-Namen, wenn der Text keine Investoren nennt
    # (gemessen 2026-08-21: ~8,5 % der Nennungen nicht belegt, darunter
    # "Bessemer"/"Y Combinator" zu Texten ohne jede Investor-Angabe). Nur
    # Namen behalten, die woertlich in Titel+Excerpt stehen — lieber eine
    # echte Nennung verlieren als eine erfundene anzeigen.
    _src = f"{title or ''} {excerpt or ''}".lower()
    inv = [str(x)[:120] for x in (obj.get("investors") or [])
           if x and str(x).lower() in _src][:10]
    amt = obj.get("amount")
    amt = float(amt) if isinstance(amt, (int, float)) and amt > 0 else None
    return {"company": (obj.get("company") or None),
            "amount_value": amt,
            "currency": (obj.get("currency") or None),
            "amount_text": None,
            "round_label": (obj.get("round") or None),
            "investors": inv,
            "confidence": 0.9 if obj.get("company") else 0.0}


def ensure_table() -> None:
    with db.get_connection() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS startup_press_rounds ("
            " raw_entry_id INTEGER PRIMARY KEY,"
            " company TEXT,"
            " amount_value REAL,"
            " currency TEXT,"
            " amount_text TEXT,"
            " round_label TEXT,"
            " investors TEXT DEFAULT '[]',"
            " method TEXT,"
            " confidence REAL,"
            " model TEXT,"
            " extracted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_spr_company ON startup_press_rounds (company)")


def candidates(limit: int, sample: bool) -> list[dict]:
    where = " or ".join(f"r.title ~* '{p}'" for p in TITLE_PATTERNS)
    order = "random()" if sample else "r.published_date desc nulls last"
    with db.get_connection() as conn:
        rows = conn.execute(f"""
            select r.id, r.title, r.excerpt
            from raw_entries r
            join sources s on s.id = r.source_id
            left join startup_press_rounds x on x.raw_entry_id = r.id
            where x.raw_entry_id is null
              and s.source_type in ('trade_media', 'press_wire', 'brand')
              and ({where})
            order by {order}
            limit {int(limit)}
        """).fetchall()
        return [dict(r) for r in rows]


def _served_model() -> str:
    try:
        r = httpx.get(f"{LLM_BASE}/models", timeout=5)
        data = r.json()
        return (data.get("data") or data.get("models"))[0].get("id") or \
               (data.get("models"))[0].get("name")
    except Exception:  # noqa: BLE001
        return "unknown"


def upgrade_llm(limit: int, dry_run: bool) -> int:
    """LLM-Nachveredelung: Zeilen, die die Regex-Stufe nur unvollstaendig
    fuellte (keine Firma/kein Betrag) oder deren Text Investoren nennt,
    erneut mit dem LLM extrahieren und per UPDATE anreichern."""
    model = _served_model()
    logger.info("Upgrade via %s @ %s", model, LLM_BASE)
    with db.get_connection() as conn:
        rows = [dict(r) for r in conn.execute(f"""
            select x.raw_entry_id, r.title, r.excerpt
            from startup_press_rounds x join raw_entries r on r.id = x.raw_entry_id
            where x.method = 'regex' and coalesce(x.round_label, '') != 'vc_fund'
              and (x.company is null or x.amount_value is null
                   or (x.investors = '[]' and
                       r.excerpt ~* '(led by|participation|investors)'))
            order by x.raw_entry_id
            limit {int(limit)}
        """).fetchall()]
    logger.info("%d Zeilen fuer LLM-Upgrade", len(rows))
    st = {"done": 0, "upgraded": 0}
    with httpx.Client() as client, db.get_connection() as conn:
        for row in rows:
            st["done"] += 1
            res = llm_extract(client, model, row["title"], row["excerpt"] or "")
            if not res or not res["company"]:
                continue
            st["upgraded"] += 1
            if not dry_run:
                conn.execute(
                    "UPDATE startup_press_rounds SET company = ?, "
                    "amount_value = coalesce(?, amount_value), "
                    "currency = coalesce(?, currency), "
                    "round_label = coalesce(?, round_label), "
                    "investors = ?, method = 'llm', confidence = ?, model = ? "
                    "WHERE raw_entry_id = ?",
                    (res["company"], res["amount_value"], res["currency"],
                     res["round_label"], json.dumps(res["investors"]),
                     res["confidence"], model, row["raw_entry_id"]))
            if st["done"] % 200 == 0:
                logger.info("  %d/%d", st["done"], len(rows))
    logger.info("[press-rounds] UPGRADE DONE: %(done)d geprueft | %(upgraded)d angereichert", st)
    return 0


def report() -> None:
    with db.get_connection() as conn:
        tot = conn.execute("select count(*) c from startup_press_rounds").fetchone()
        ok = conn.execute(
            "select count(*) c from startup_press_rounds "
            "where company is not null and amount_value is not null").fetchone()
        inv = conn.execute(
            "select count(*) c from startup_press_rounds where investors != '[]'").fetchone()
        fund = conn.execute(
            "select count(*) c from startup_press_rounds where round_label = 'vc_fund'").fetchone()
        print(f"rows={tot['c']}  company+amount={ok['c']}  mit Investoren={inv['c']}  "
              f"vc_fund-Rauschen={fund['c']}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Presse-Funding-Extraktion (#87 Phase 0)")
    ap.add_argument("--mode", choices=["regex", "llm", "hybrid", "upgrade"],
                    default="hybrid")
    ap.add_argument("--limit", type=int, default=1000)
    ap.add_argument("--sample", type=int, default=0,
                    help="N zufaellige Kandidaten statt der neuesten")
    ap.add_argument("--report", action="store_true", help="nur Bestandsbericht")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    ensure_table()
    if args.report:
        report()
        return 0

    limit = args.sample or args.limit
    if args.mode == "upgrade":
        return upgrade_llm(limit, args.dry_run)
    cand = candidates(limit, sample=bool(args.sample))
    logger.info("%d Kandidaten (mode=%s)", len(cand), args.mode)
    model = _served_model() if args.mode in ("llm", "hybrid") else ""
    if args.mode in ("llm", "hybrid"):
        logger.info("LLM: %s @ %s", model, LLM_BASE)

    st = {"done": 0, "regex": 0, "llm": 0, "empty": 0}
    t0 = time.time()
    with httpx.Client() as client, db.get_connection() as conn:
        for row in cand:
            res = regex_extract(row["title"], row["excerpt"] or "")
            method = "regex"
            needs_llm = args.mode == "llm" or (
                args.mode == "hybrid" and res["round_label"] != "vc_fund" and (
                    not res["company"] or not res["amount_value"]
                    or re.search(r"\bled by\b|\bparticipation\b|investors",
                                 (row["excerpt"] or ""), re.I)))
            if needs_llm:
                llm = llm_extract(client, model, row["title"], row["excerpt"] or "")
                if llm:
                    # Regex-Betrag behalten, wenn das LLM keinen fand
                    if llm["amount_value"] is None and res["amount_value"] is not None:
                        llm["amount_value"] = res["amount_value"]
                        llm["currency"] = llm["currency"] or res["currency"]
                        llm["amount_text"] = res["amount_text"]
                    res, method = llm, "llm"
            if res["confidence"] == 0 and res["round_label"] != "vc_fund":
                st["empty"] += 1
            st[method] += 1
            st["done"] += 1
            if not args.dry_run:
                conn.execute(
                    "INSERT INTO startup_press_rounds "
                    "(raw_entry_id, company, amount_value, currency, amount_text, "
                    " round_label, investors, method, confidence, model) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT (raw_entry_id) DO NOTHING",
                    (row["id"], res["company"], res["amount_value"], res["currency"],
                     res["amount_text"], res["round_label"],
                     json.dumps(res["investors"]), method, res["confidence"],
                     model if method == "llm" else ""))
            if st["done"] % 200 == 0:
                logger.info("  %d/%d (%.1f/s)", st["done"], len(cand),
                            st["done"] / max(time.time() - t0, 1))
    logger.info("[press-rounds] DONE: %(done)d verarbeitet | %(regex)d regex "
                "| %(llm)d llm | %(empty)d leer", st)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
