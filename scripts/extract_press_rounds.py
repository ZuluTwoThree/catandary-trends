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
  investors  Investoren-Nachveredelung (#94 Teil 2, siehe unten) — schreibt
          NUR investors (+ round_label wenn leer), ruehrt company/amount_value
          nie an. Dry-Run ist hier der DEFAULT (kein LLM-Call ohne --apply).

VC-Fonds-Meldungen ("Acme Capital raises $200M fund") sind KEINE Startup-
Runden — sie werden mit round_label='vc_fund', confidence 0 abgelegt und
spaeter ausgefiltert.

    python scripts/extract_press_rounds.py --sample 200 --mode hybrid
    python scripts/extract_press_rounds.py --limit 5000 --mode regex
    python scripts/extract_press_rounds.py --report

Investoren-Nachveredelung (#94 Teil 2):
    python scripts/extract_press_rounds.py --mode investors --limit 50      # Dry-Run (Default)
    python scripts/extract_press_rounds.py --mode investors --eval 30       # LLM vs. vorhandenes Ergebnis
    python scripts/extract_press_rounds.py --mode investors --apply --limit 2000  # echter Lauf

Braucht vorher die additive Migration (NICHT auto-ausgefuehrt, siehe deren
Docstring): python -m scripts.migrate_press_investor_enrichment
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
from typing import Literal

sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
from pydantic import BaseModel, Field

from pipeline import db, llamacpp_client
from pipeline.config import STAGE_8B_MODEL

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("extract_press_rounds")

LLM_BASE = os.environ.get("PRESS_ROUNDS_LLM_BASE", "http://127.0.0.1:8090/v1")
# Expected model for --mode investors (Stage-10-style identity guard below).
# Overridable per-call via --model / PRESS_ROUNDS_LLM_MODEL for A/B testing
# against a different 8B build without touching config.py.
PRESS_ROUNDS_LLM_MODEL = os.environ.get("PRESS_ROUNDS_LLM_MODEL", STAGE_8B_MODEL)

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


# ---------------------------------------------------------------------------
# Investoren-Nachveredelung (#94 Teil 2)
#
# Anders als --mode llm/hybrid/upgrade oben (volle Re-Extraktion, ueberschreibt
# company/amount/round_label) ruehrt dieser Pfad NUR investors an (+ round_label
# per COALESCE nur wenn NULL). Eigenes, engeres Pydantic-Schema mit role-Feld
# (lead/participant) statt der rohen JSON-Objekt-Antwort von llm_extract().
# ---------------------------------------------------------------------------

class InvestorEntry(BaseModel):
    """One named investor with its role in the round."""
    name: str = Field(description="Investor or fund name exactly as written in the text")
    role: Literal["lead", "participant"] = Field(
        description="'lead' only if the text explicitly names a lead investor, else 'participant'")


class InvestorEnrichmentResult(BaseModel):
    """Investor-focused re-extraction — narrower than LLM_PROMPT/llm_extract()
    above: only investors + round_type + amount_usd are asked for, and only
    investors/round_label are ever written back (write_investor_enrichment).
    amount_usd is captured for the --eval comparison only; it never overwrites
    amount_value (company/amount stay whatever regex/an earlier LLM pass set)."""
    investors: list[InvestorEntry] = Field(
        default_factory=list, max_length=10,
        description="Named lead + participating investors; [] if none are named in the text")
    round_type: str | None = Field(
        default=None,
        description="Funding round label if explicitly stated (e.g. 'Seed', 'Series B'), else null")
    amount_usd: float | None = Field(
        default=None, description="Round amount in USD if explicitly stated, else null")


INVESTOR_ENRICH_SYSTEM = (
    "You extract named investors from a startup funding news item. Only use "
    "names explicitly stated in the text — never infer or guess an investor "
    "from context or reputation. If no investor is named, return an empty list."
)


def _investor_enrich_prompt(title: str, excerpt: str) -> str:
    return (f"Title: {(title or '')[:300]}\n"
            f"Text: {(excerpt or '')[:900]}\n\n"
            "Extract the named investors (lead + participants), the round "
            "type if explicitly stated, and the amount in USD if explicitly "
            "stated. Reply with the JSON object only.")


def llm_extract_investors(model: str, title: str, excerpt: str) -> InvestorEnrichmentResult | None:
    """chat_structured against llama-server (json_schema response_format,
    temperature 0, enable_thinking=False handled inside llamacpp_client) —
    same pattern as scripts/corpus_research.py's Plan/AgentAction/Audit calls.
    Retries + markdown-fence stripping + Pydantic validation are handled by
    chat_structured; returns None only once its retry budget is exhausted."""
    return llamacpp_client.chat_structured(
        model=model, schema=InvestorEnrichmentResult,
        system=INVESTOR_ENRICH_SYSTEM,
        prompt=_investor_enrich_prompt(title, excerpt),
        temperature=0.0, require_all_fields=True)


def _ground_investors(investors: list[InvestorEntry], title: str, excerpt: str) -> list[str]:
    """Verbatim-grounds each investor name against title+excerpt — same
    grounding philosophy as llm_extract()'s investor filter above: the 8B
    invents plausible VC names when the text names none (~8.5% measured
    2026-08-21 on the general extraction prompt). Lieber eine echte Nennung
    verlieren als eine erfundene anzeigen.

    Returns a flat list[str], LEAD investors first, dropping the `role` field.
    startup_press_rounds.investors (and startup_events.investors downstream,
    see pipeline/startup_resolution.py:load_press) is a flat list[str]
    contract consumed as such by the frontend (frontend/src/lib/ventures.ts:
    `investors: string[]`; .../ventures/company/[id]/page.tsx:
    `e.investors.join(", ")`) — nesting {name, role} objects into that column
    would silently break both (render as "[object Object]"). Lead-first
    ordering keeps the role signal without a schema-wide migration; the raw
    role is still visible in --eval output for quality review."""
    src = f"{title or ''} {excerpt or ''}".lower()
    leads: list[str] = []
    participants: list[str] = []
    seen: set[str] = set()
    for inv in investors:
        name = (inv.name or "").strip()
        key = name.lower()
        if not name or key in seen or key not in src:
            continue
        seen.add(key)
        (leads if inv.role == "lead" else participants).append(name[:120])
    return (leads + participants)[:10]


def _model_identity_ok(base: str, expected_model: str,
                       timeout: float = 5.0) -> tuple[bool, str]:
    """GET /v1/models and verify the expected 8B chat model is loaded.

    Mirrors the Stage-10 draft-judge guard (scripts/scheduled_cycle.sh) and
    scripts/update_startup_companies.py's embed_server_ready(): llama-server
    ignores the `model` field in the request body and just answers with
    whatever GGUF start-active.sh currently points at, so a stale/failed
    symlink swap would otherwise silently run this enrichment against the
    wrong model (e.g. the Stage-6 content model, or the judge's 27B) instead
    of loudly failing. Returns (ok, message) — message is either the served
    model id (ok) or a diagnostic (not ok)."""
    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.get(f"{base}/models")
            r.raise_for_status()
            data = r.json()
    except Exception as e:  # noqa: BLE001
        return False, f"LLM-Server nicht erreichbar ({base}): {type(e).__name__}: {e}"
    loaded = [str(m.get("id") or m.get("name") or "")
              for m in (data.get("data") or data.get("models") or [])]
    stub = Path(expected_model).name.lower()
    if not any(stub in m.lower() for m in loaded):
        return False, (f"Falsches Modell geladen (erwartet '{expected_model}', "
                       f"geladen {loaded or '(nichts)'}) — Symlink-Swap pruefen, Abbruch.")
    return True, (loaded[0] if loaded else expected_model)


def _investor_marker_exists() -> bool:
    """Whether startup_press_rounds.investors_enriched_at exists yet — the
    additive migration (scripts/migrate_press_investor_enrichment.py) is NOT
    auto-applied (repo convention, see that script's docstring)."""
    with db.get_connection() as conn:
        if db.USE_POSTGRES:
            row = conn.execute(
                "SELECT 1 FROM information_schema.columns WHERE table_name = "
                "'startup_press_rounds' AND column_name = 'investors_enriched_at'"
            ).fetchone()
            return row is not None
        rows = conn.execute("PRAGMA table_info(startup_press_rounds)").fetchall()
        names = [(r["name"] if hasattr(r, "keys") else r[1]) for r in rows]
        return "investors_enriched_at" in names


# Investor-cue gate: of the 15,543 rows otherwise eligible (measured against
# the live corpus 2026-08-29, #94), only 1,275 (8.2%) mention ANY
# investor-suggestive phrase in the excerpt at all — the rest would burn a
# full 8B call for a result the grounding filter discards anyway (nothing to
# ground a name against). %% (not %) because the Postgres wrapper
# (pipeline.db._PgConnectionWrapper.execute) always passes a params tuple to
# psycopg2, which then parses a lone '%' as its own placeholder syntax and
# raises "tuple index out of range" — same escaping already used in
# scripts/cpc_leadtime.py / scripts/build_cpc_tier_series.py. Harmless no-op
# doubling under SQLite (no param-style parsing there).
_INVESTOR_HINT_SQL = (
    " and (lower(r.excerpt) like '%%led by%%' or lower(r.excerpt) like '%%participation%%'"
    " or lower(r.excerpt) like '%%investor%%' or lower(r.excerpt) like '%%backed by%%'"
    " or lower(r.excerpt) like '%%joined by%%')"
)

_INVESTOR_CANDIDATE_WHERE = (
    "x.investors_enriched_at is null"
    " and (x.investors = '[]' or x.method = 'regex')"
    " and x.company is not null"
    " and coalesce(x.round_label, '') != 'vc_fund'"
)


def investor_candidates(limit: int, gate_on_hint: bool = True) -> list[dict]:
    """Rows in startup_press_rounds still missing investors AND not yet
    touched by a previous investor-enrichment pass (investors_enriched_at IS
    NULL — the idempotency marker). "leer" = investors == '[]'; "regex-roh" =
    method == 'regex' (regex_extract() never actually fills investors today,
    but the OR keeps this future-proof and matches the task wording — a
    regex-only row is always a candidate regardless of what investors holds).
    Rows a full LLM pass (method='llm', --mode llm/hybrid/upgrade) already
    populated with real investor names are excluded via investors != '[]'.

    Ordered oldest-first (raw_entry_id asc) for a stable, resumable backfill
    traversal — this is backlog cleanup, not a freshness-prioritised feed."""
    hint_sql = _INVESTOR_HINT_SQL if gate_on_hint else ""
    with db.get_connection() as conn:
        rows = conn.execute(f"""
            select x.raw_entry_id, r.title, r.excerpt, x.company, x.amount_value,
                   x.currency, x.round_label, x.investors, x.method
            from startup_press_rounds x
            join raw_entries r on r.id = x.raw_entry_id
            where {_INVESTOR_CANDIDATE_WHERE}
              {hint_sql}
            order by x.raw_entry_id asc
            limit {int(limit)}
        """).fetchall()
        return [dict(r) for r in rows]


def count_investor_candidates(gate_on_hint: bool = True) -> int:
    hint_sql = _INVESTOR_HINT_SQL if gate_on_hint else ""
    with db.get_connection() as conn:
        row = conn.execute(f"""
            select count(*) c from startup_press_rounds x
            join raw_entries r on r.id = x.raw_entry_id
            where {_INVESTOR_CANDIDATE_WHERE}
              {hint_sql}
        """).fetchone()
        return row["c"] if hasattr(row, "keys") else row[0]


def write_investor_enrichment(conn, raw_entry_id: int, investors: list[str],
                              round_type: str | None) -> None:
    """UPDATE that touches ONLY investors, round_label (via COALESCE — fills
    it in only when NULL, otherwise leaves the regex/LLM-extracted value
    alone) and the investors_enriched_at marker. company/amount_value/
    amount_text/currency/method/confidence/model are never referenced here —
    this pass enriches investors, it does not re-run extraction (#94 Teil 2
    scope; contrast with upgrade_llm() above, which does overwrite those)."""
    conn.execute(
        "UPDATE startup_press_rounds SET investors = ?, "
        "round_label = coalesce(round_label, ?), "
        "investors_enriched_at = CURRENT_TIMESTAMP "
        "WHERE raw_entry_id = ?",
        (json.dumps(investors), round_type, raw_entry_id))


def sync_events_from_enriched(conn) -> int:
    """Propagiert angereicherte Investoren in bereits materialisierte
    startup_events-Zeilen. Noetig, weil load_press() die Runden nur beim
    Materialisieren durchreicht — Events, die VOR der Anreicherung entstanden,
    stuenden sonst dauerhaft auf []. Befuellt NUR leere Event-Investorenlisten
    (nie bestehende ueberschreiben); idempotent. Befund 2026-08-29: alle 534
    angereicherten Runden hatten bereits Events mit investors=[]."""
    from pipeline.db import USE_POSTGRES
    cast = "::jsonb" if USE_POSTGRES else ""
    try:
        cur = conn.execute(
        f"UPDATE startup_events SET investors = pr.investors{cast} "
        "FROM startup_press_rounds pr "
        "WHERE startup_events.raw_entry_id = pr.raw_entry_id "
        "AND pr.investors_enriched_at IS NOT NULL "
        "AND pr.investors IS NOT NULL AND pr.investors != '[]' "
        "AND (startup_events.investors IS NULL "
        "     OR startup_events.investors::text IN ('[]', ''))"
        if USE_POSTGRES else
        "UPDATE startup_events SET investors = ("
        "  SELECT pr.investors FROM startup_press_rounds pr"
        "  WHERE pr.raw_entry_id = startup_events.raw_entry_id"
        "  AND pr.investors_enriched_at IS NOT NULL"
        "  AND pr.investors IS NOT NULL AND pr.investors != '[]') "
        "WHERE (investors IS NULL OR investors IN ('[]', '')) "
        "AND EXISTS (SELECT 1 FROM startup_press_rounds pr"
        "  WHERE pr.raw_entry_id = startup_events.raw_entry_id"
        "  AND pr.investors_enriched_at IS NOT NULL"
        "  AND pr.investors IS NOT NULL AND pr.investors != '[]')")
    except Exception as e:  # fehlende Tabelle (frische Test-DB) → kein Sync-Ziel
        if "startup_events" in str(e):
            logger.info("[press-rounds] Event-Sync uebersprungen: %s", e)
            return 0
        raise
    n = cur.rowcount if cur.rowcount is not None else 0
    logger.info("[press-rounds] Event-Sync: %d startup_events-Zeilen mit Investoren befuellt", n)
    return n


def enrich_investors(limit: int, apply: bool, gate_on_hint: bool = True,
                     model_override: str = "") -> int:
    """--mode investors main driver. Dry-run (apply=False) is the default and
    makes NO LLM call at all — it only reads candidates and previews which
    fields would change, so it runs even with the 8B server down or busy with
    something else (e.g. content-gen on :8090, see the hard rule this script
    was built under). --apply is required to actually call the LLM and write."""
    if not _investor_marker_exists():
        logger.error("startup_press_rounds.investors_enriched_at fehlt — erst "
                     "'python -m scripts.migrate_press_investor_enrichment' laufen lassen.")
        return 1

    cand = investor_candidates(limit, gate_on_hint=gate_on_hint)
    total = count_investor_candidates(gate_on_hint=gate_on_hint)
    logger.info("%d Kandidaten geladen (insgesamt %d verfuegbar, gate_on_hint=%s, limit=%d)",
                len(cand), total, gate_on_hint, limit)

    if not apply:
        logger.info("DRY-RUN (Default, kein LLM-Call) — --apply fuer den echten Lauf.")
        print(f"\n=== --mode investors DRY-RUN: {len(cand)}/{total} Kandidaten "
              f"(limit={limit}, gate_on_hint={gate_on_hint}) ===")
        for row in cand[:5]:
            round_note = "wird befuellt (aktuell leer)" if not row["round_label"] \
                else f"bleibt unveraendert ({row['round_label']!r})"
            print(f"\n[{row['raw_entry_id']}] {row['title']!r}")
            print(f"  Vorher : investors={row['investors']}  method={row['method']}")
            print(f"  Nachher: investors=<vom LLM befuellt, falls im Text genannt>; "
                  f"round_label {round_note}")
            print(f"  Text an LLM (Vorschau, KEIN Call): "
                  f"{(row['excerpt'] or '')[:200]!r}")
        return 0

    expected_model = model_override or PRESS_ROUNDS_LLM_MODEL
    ok, info = _model_identity_ok(LLM_BASE, expected_model)
    if not ok:
        logger.error(info)
        return 1
    logger.info("Modell-Identitaet OK (%s @ %s)", info, LLM_BASE)

    st = {"done": 0, "with_investors": 0, "empty": 0, "errors": 0}
    with db.get_connection() as conn:
        for row in cand:
            st["done"] += 1
            res = llm_extract_investors(expected_model, row["title"], row["excerpt"] or "")
            if res is None:
                st["errors"] += 1
                # KEIN Marker-Stempel bei Hard-Fail — retry im naechsten Lauf
                # (gleiches Prinzip wie pipeline.draft_judge.judged_at).
                continue
            grounded = _ground_investors(res.investors, row["title"], row["excerpt"] or "")
            if grounded:
                st["with_investors"] += 1
            else:
                st["empty"] += 1
            write_investor_enrichment(conn, row["raw_entry_id"], grounded, res.round_type)
            if st["done"] % 200 == 0:
                logger.info("  %d/%d", st["done"], len(cand))
    logger.info("[press-rounds] INVESTOR-ENRICH DONE: %(done)d verarbeitet | "
                "%(with_investors)d mit Investoren | %(empty)d leer (Grounding/keine Nennung) "
                "| %(errors)d Fehler (nicht markiert, naechster Lauf erneut)", st)
    with db.get_connection() as conn:
        sync_events_from_enriched(conn)
        conn.commit()
    return 0


def eval_investor_enrichment(n: int, model_override: str = "") -> int:
    """--eval N: compares the new investor-focused LLM extraction against
    whatever is already stored (mostly '[]' from the regex stage, some
    populated by the older general-purpose llm_extract()/--mode upgrade) on N
    random rows. Read-only — no writes, investors_enriched_at is never
    touched — so the orchestrator can re-run it freely while judging quality
    before committing to a mass --apply pass."""
    expected_model = model_override or PRESS_ROUNDS_LLM_MODEL
    ok, info = _model_identity_ok(LLM_BASE, expected_model)
    if not ok:
        logger.error(info)
        return 1
    logger.info("Modell-Identitaet OK (%s @ %s)", info, LLM_BASE)

    with db.get_connection() as conn:
        rows = [dict(r) for r in conn.execute(f"""
            select x.raw_entry_id, r.title, r.excerpt, x.company, x.round_label,
                   x.investors, x.method
            from startup_press_rounds x
            join raw_entries r on r.id = x.raw_entry_id
            where x.company is not null and coalesce(x.round_label, '') != 'vc_fund'
            order by random()
            limit {int(n)}
        """).fetchall()]

    existing_counts, new_counts, overlaps, examples = [], [], [], []
    for row in rows:
        try:
            existing = json.loads(row["investors"]) if row["investors"] else []
        except ValueError:
            existing = []
        existing = existing if isinstance(existing, list) else []
        res = llm_extract_investors(expected_model, row["title"], row["excerpt"] or "")
        new = _ground_investors(res.investors, row["title"], row["excerpt"] or "") if res else []
        existing_counts.append(len(existing))
        new_counts.append(len(new))
        ex_set = {str(x).strip().lower() for x in existing}
        new_set = {x.lower() for x in new}
        overlaps.append(len(ex_set & new_set))
        examples.append({
            "raw_entry_id": row["raw_entry_id"], "title": row["title"],
            "existing": existing, "existing_method": row["method"],
            "new": new,
            "new_roles": [(i.name, i.role) for i in (res.investors if res else [])],
        })

    n_done = len(rows)
    logger.info("[press-rounds] EVAL: n=%d  existing avg=%.2f (%d>0)  "
                "neu(LLM) avg=%.2f (%d>0)  Ueberlappung avg=%.2f", n_done,
                sum(existing_counts) / max(n_done, 1), sum(1 for c in existing_counts if c > 0),
                sum(new_counts) / max(n_done, 1), sum(1 for c in new_counts if c > 0),
                sum(overlaps) / max(n_done, 1))
    print(f"\n=== Eval: {n_done} Zeilen ===")
    print(f"vorhanden (Regex/aelterer LLM-Pfad): {sum(existing_counts)} Investoren gesamt, "
          f"{sum(1 for c in existing_counts if c > 0)}/{n_done} Zeilen mit >=1")
    print(f"neu (investor-fokussiertes LLM)    : {sum(new_counts)} Investoren gesamt, "
          f"{sum(1 for c in new_counts if c > 0)}/{n_done} Zeilen mit >=1")
    print(f"Ueberlappung (Name identisch, case-insensitiv): {sum(overlaps)}")
    print("\n--- Beispiele ---")
    for ex in examples[:10]:
        print(f"\n[{ex['raw_entry_id']}] {ex['title']!r}")
        print(f"  vorhanden ({ex['existing_method']}): {ex['existing']}")
        print(f"  neu (LLM)              : {ex['new']}  (roh mit Rolle: {ex['new_roles']})")
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
    ap = argparse.ArgumentParser(description="Presse-Funding-Extraktion (#87 Phase 0, #94 Teil 2)")
    ap.add_argument("--mode", choices=["regex", "llm", "hybrid", "upgrade", "investors"],
                    default="hybrid")
    ap.add_argument("--limit", type=int, default=1000)
    ap.add_argument("--sample", type=int, default=0,
                    help="N zufaellige Kandidaten statt der neuesten (modes regex/llm/hybrid)")
    ap.add_argument("--report", action="store_true", help="nur Bestandsbericht")
    ap.add_argument("--dry-run", action="store_true",
                    help="modes regex/llm/hybrid/upgrade: nichts schreiben (Default dort: schreiben)")
    ap.add_argument("--apply", action="store_true",
                    help="mode=investors: tatsaechlich LLM aufrufen + schreiben "
                         "(Default dort: Dry-Run OHNE LLM-Call)")
    ap.add_argument("--all-candidates", action="store_true",
                    help="mode=investors: Investoren-Hinweis-Gate im Excerpt abschalten "
                         "(exhaustiv statt der ~8%% mit Hinweistext — siehe investor_candidates())")
    ap.add_argument("--eval", type=int, default=0, metavar="N",
                    help="mode=investors: N zufaellige Zeilen LLM vs. vorhandenes Ergebnis "
                         "vergleichen (rein lesend, kein Marker-Stempel)")
    ap.add_argument("--sync-events", action="store_true",
                    help="mode=investors: nur die Event-Propagation nachziehen "
                         "(angereicherte Runden -> leere startup_events.investors; "
                         "laeuft nach --apply automatisch, dies ist der Standalone-Nachzug)")
    ap.add_argument("--model", type=str, default="",
                    help="mode=investors: Override fuer das erwartete 8B-Chat-Modell "
                         "(Default: STAGE_8B_MODEL aus pipeline/config.py)")
    args = ap.parse_args()

    ensure_table()
    if args.report:
        report()
        return 0

    limit = args.sample or args.limit
    if args.mode == "upgrade":
        return upgrade_llm(limit, args.dry_run)
    if args.mode == "investors":
        if args.eval:
            return eval_investor_enrichment(args.eval, model_override=args.model)
        if args.sync_events:
            with db.get_connection() as conn:
                sync_events_from_enriched(conn)
                conn.commit()
            return 0
        return enrich_investors(limit, apply=args.apply,
                                gate_on_hint=not args.all_candidates,
                                model_override=args.model)
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
