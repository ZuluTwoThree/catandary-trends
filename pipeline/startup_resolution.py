"""Startup-Explorer-Entity-Resolution — geteilter Kern für Rebuild + Update (#87/#94).

Ausgelagert aus `scripts/build_startup_companies.py` (2026-08-23) im Zuge von
#94 Teil 1: der inkrementelle Update-Pfad (`scripts/update_startup_companies.py`)
braucht exakt dieselbe Auflösungslogik wie der Voll-Rebuild — nicht eine
Kopie, die bei der nächsten Änderung auseinanderdriftet. `build_startup_companies.py`
importiert diese Namen unverändert zurück (Regression: bestehende Tests/Aufrufe
bleiben identisch, siehe tests/test_build_startup_companies.py).

Resolution konservativ nach Plan §4 (docs/startup_explorer_plan.md):
  Stufe A (hart):   Form D per CIK · SBIR per DUNS (aus data/sbir_award_data.csv)
                    · CORDIS per PIC. Innerhalb der Quelle fehlerfrei.
  Stufe B (Name+Gate): quellübergreifender Merge nur bei gleichem name_norm
                    UND kompatibler Geografie (US-State bzw. Land). Presse-
                    Runden tragen keine Geografie — sie mergen nur, wenn der
                    Namensschlüssel im Korpus EINDEUTIG ist und lang genug
                    (>=5 Zeichen; "Realize"-Befund 2026-08-21).
  Stufe C (Embedding-Fuzzy) lebt NICHT hier — sie braucht einen Live-
  Embedding-Server und ist Sache des Update-Skripts (optional/abschaltbar),
  siehe scripts/update_startup_companies.py.

Die vier `load_*`-Funktionen akzeptieren seit #94 zwei zusätzliche,
rückwärtskompatible Parameter (Default = altes Verhalten, exakt wie vor der
Auslagerung):
  - `unassigned_only=True` schließt raw_entries/press_rounds aus, für die
    bereits ein startup_events-Datensatz existiert (Grundlage des additiven
    Update-Pfads — der Rebuild braucht das nicht, er baut ohnehin komplett neu).
  - `since="YYYY-MM-DD"` filtert auf das Veröffentlichungsdatum (Kandidaten-
    Fenster für gestaffelte Updates).
"""
from __future__ import annotations

import csv
import json
import logging
import re
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

from pipeline.company_norm import cik_from_edgar_url, norm_company_name, pic_from_cordis_url
from pipeline.db import get_connection

logger = logging.getLogger("startup_resolution")

SBIR_CSV = Path(__file__).parent.parent / "data" / "sbir_award_data.csv"
MIN_PRESS_KEY_LEN = 5

_MONEY_RE = re.compile(r"(?:\$|EUR\s?)([0-9]+(?:\.[0-9]+)?)\s?([kMB])?", re.IGNORECASE)
_SCALE = {"k": 1e3, "m": 1e6, "b": 1e9}


def parse_money(text: str) -> tuple[float, str] | None:
    """'$3.1M' -> (3100000, USD) · 'EUR 149k' -> (149000, EUR)."""
    m = _MONEY_RE.search(text or "")
    if not m:
        return None
    val = float(m.group(1)) * _SCALE.get((m.group(2) or "").lower(), 1)
    cur = "EUR" if "eur" in m.group(0).lower() else "USD"
    return (val, cur)


_FORMD_TITLE = re.compile(r"^(.*?) raises .* private round \(([^)]+)\)\s*$")
_FORMD_GEO = re.compile(r"\(([^,()]+), ([^,()]+)\) filed")
_SBIR_TITLE = re.compile(r"^(.*?) wins (?:\$\S+|undisclosed) (SBIR|STTR) Phase (I{1,3}) award \(([^)]+)\)\s*$")
_PREFIX_GEO = re.compile(r"·\s*([^·\[\]]+?),\s*([A-Z]{2})\s*·")
_CORDIS_TITLE = re.compile(r"^(.*?) secures (EUR \S+|undisclosed) (Horizon Europe|Horizon 2020|FP7) grant \(([^)]+)\)\s*$")

US_STATE_NAMES = {  # Form D schreibt Bundesstaaten aus; SBIR nutzt Kürzel
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN",
    "mississippi": "MS", "missouri": "MO", "montana": "MT", "nebraska": "NE",
    "nevada": "NV", "new hampshire": "NH", "new jersey": "NJ",
    "new mexico": "NM", "new york": "NY", "north carolina": "NC",
    "north dakota": "ND", "ohio": "OH", "oklahoma": "OK", "oregon": "OR",
    "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA",
    "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
    "district of columbia": "DC", "puerto rico": "PR",
}


def _us_state(s: str | None) -> str | None:
    s = (s or "").strip()
    if len(s) == 2 and s.isupper():
        return s
    return US_STATE_NAMES.get(s.lower())


class Group:
    """Eine (vorläufige) Firma: Events + Attribute einer Resolutionsstufe."""

    __slots__ = ("names", "country", "region", "city", "sector", "cik", "duns",
                 "pic", "website", "employees", "events", "sources")

    def __init__(self):
        self.names: list[str] = []
        self.country = self.region = self.city = self.sector = None
        self.cik = self.duns = self.pic = self.website = self.employees = None
        self.events: list[dict] = []
        self.sources: set[str] = set()

    def display_name(self) -> str:
        # häufigste Original-Schreibweise, bei Gleichstand die längste
        counts = defaultdict(int)
        for n in self.names:
            counts[n] += 1
        return sorted(counts.items(), key=lambda kv: (-kv[1], -len(kv[0])))[0][0]

    def absorb(self, other: "Group"):
        self.names += other.names
        self.events += other.events
        self.sources |= other.sources
        for attr in ("country", "region", "city", "sector", "cik", "duns",
                     "pic", "website", "employees"):
            if getattr(self, attr) is None:
                setattr(self, attr, getattr(other, attr))


def _event(etype: str, date, source: str, url: str, raw_id=None,
           amount=None, currency=None, round_label=None, investors=None,
           **meta) -> dict:
    return {"event_type": etype, "event_date": date, "source": source,
            "source_url": url, "raw_entry_id": raw_id, "amount": amount,
            "currency": currency, "round_label": round_label,
            "investors": investors or [], "meta": {k: v for k, v in meta.items() if v}}


# ---------------------------------------------------------------- Quellen

_UNASSIGNED_RAW = "and not exists (select 1 from startup_events e where e.raw_entry_id = r.id)"
_UNASSIGNED_PRESS = "and not exists (select 1 from startup_events e where e.raw_entry_id = x.raw_entry_id)"


def load_formd(unassigned_only: bool = False, since: str | None = None,
               limit: int = 0) -> dict[str, Group]:
    """Form D: Gruppierung per CIK (Stufe A)."""
    groups: dict[str, Group] = {}
    skipped = 0
    sql = ("select r.id, r.title, r.excerpt, r.url, r.published_date "
           "from raw_entries r join sources s on s.id = r.source_id "
           "where s.name like ? and r.title is not null and r.published_date is not null")
    params: list = ["SEC Form D%"]
    if unassigned_only:
        sql += f" {_UNASSIGNED_RAW}"
    if since:
        sql += " and r.published_date >= ?"
        params.append(since)
    sql += " order by r.id"
    with get_connection() as conn:
        rows = conn.execute(sql, tuple(params)).fetchall()
    if limit:
        # KEIN SQL-LIMIT hier (#94-Befund 2026-08-29): der Anti-Join gegen
        # startup_events, ohne Index auf raw_entries.source_id, lässt den
        # Postgres-Planner bei kleinem LIMIT + wenigen/keinen Treffern einen
        # Nested-Loop-Plan wählen, der de facto die ganze raw_entries-Tabelle
        # (22M+ Zeilen) durchsucht — gemessen: limit=20 lief in ~8s (Merge
        # Anti Join, Kostenschätzung ~9,3 Mio.), limit=5 lief >60s ohne
        # Ergebnis (Nested Loop, Kostenschätzung 543 Mio.). Bis
        # raw_entries(source_id) einen Index hat, wird darum immer die volle
        # Kandidatenmenge geholt und HIER in Python auf --limit gekappt.
        rows = rows[:limit]
    for x in rows:
        m = _FORMD_TITLE.match(x["title"])
        cik = cik_from_edgar_url(x["url"])
        if not m or not cik:
            skipped += 1
            continue
        name, industry = m.group(1).strip(), m.group(2).strip()
        g = groups.setdefault(f"cik:{cik}", Group())
        g.names.append(name)
        g.cik, g.country, g.sector = cik, "US", g.sector or industry
        gm = _FORMD_GEO.search(x["excerpt"] or "")
        if gm and not g.region:
            g.city = gm.group(1).strip().title()
            g.region = _us_state(gm.group(2))
        money = parse_money(x["title"])
        g.events.append(_event(
            "regd_offering", x["published_date"], "SEC Form D", x["url"], x["id"],
            amount=money[0] if money else None, currency=money[1] if money else None,
            industry=industry))
        g.sources.add("formd")
    logger.info("Form D: %d Firmen (CIK), %d Zeilen übersprungen", len(groups), skipped)
    return groups


@lru_cache(maxsize=1)
def _sbir_attr_map() -> dict[tuple[str, str], dict]:
    """(name_norm, state) -> {duns, website, employees, city} aus dem CSV-Cache.

    Gecacht (#94): die CSV ist ~368 MB / 208k Zeilen. Der Rebuild ruft dies
    einmal pro Prozess auf (unkritisch), der additive Update-Pfad potenziell
    oft (gestaffelte Läufe, Cron) — ohne Cache würde jeder Lauf erneut
    Sekunden für denselben, prozesslaufzeit-stabilen Datei-Read verlieren."""
    attrs: dict[tuple[str, str], dict] = {}
    if not SBIR_CSV.exists():
        logger.warning("SBIR-CSV-Cache fehlt (%s) — Stufe A für SBIR entfällt", SBIR_CSV)
        return attrs
    with open(SBIR_CSV, encoding="utf-8", errors="replace", newline="") as f:
        for row in csv.DictReader(f):
            key = (norm_company_name(row.get("Company")), (row.get("State") or "").strip())
            if not key[0]:
                continue
            a = attrs.setdefault(key, {})
            for src, dst in (("Duns", "duns"), ("Company Website", "website"),
                             ("City", "city")):
                v = (row.get(src) or "").strip()
                if v and not a.get(dst):
                    a[dst] = v
            emp = (row.get("Number Employees") or "").strip()
            if emp.isdigit() and int(emp) > 0 and not a.get("employees"):
                a["employees"] = int(emp)
    return attrs


def load_sbir(unassigned_only: bool = False, since: str | None = None,
              limit: int = 0) -> dict[str, Group]:
    """SBIR: Gruppierung per (name_norm, State); DUNS aus dem CSV-Cache."""
    attrs = _sbir_attr_map()
    groups: dict[str, Group] = {}
    skipped = 0
    sql = ("select r.id, r.title, r.excerpt, r.url, r.published_date "
           "from raw_entries r join sources s on s.id = r.source_id "
           "where s.name like ? and r.title is not null and r.published_date is not null")
    params: list = ["SBIR%"]
    if unassigned_only:
        sql += f" {_UNASSIGNED_RAW}"
    if since:
        sql += " and r.published_date >= ?"
        params.append(since)
    sql += " order by r.id"
    with get_connection() as conn:
        rows = conn.execute(sql, tuple(params)).fetchall()
    if limit:
        # KEIN SQL-LIMIT hier (#94-Befund 2026-08-29): der Anti-Join gegen
        # startup_events, ohne Index auf raw_entries.source_id, lässt den
        # Postgres-Planner bei kleinem LIMIT + wenigen/keinen Treffern einen
        # Nested-Loop-Plan wählen, der de facto die ganze raw_entries-Tabelle
        # (22M+ Zeilen) durchsucht — gemessen: limit=20 lief in ~8s (Merge
        # Anti Join, Kostenschätzung ~9,3 Mio.), limit=5 lief >60s ohne
        # Ergebnis (Nested Loop, Kostenschätzung 543 Mio.). Bis
        # raw_entries(source_id) einen Index hat, wird darum immer die volle
        # Kandidatenmenge geholt und HIER in Python auf --limit gekappt.
        rows = rows[:limit]
    for x in rows:
        m = _SBIR_TITLE.match(x["title"])
        if not m:
            skipped += 1
            continue
        name, program, phase, agency = (m.group(1).strip(), m.group(2),
                                        m.group(3), m.group(4).strip())
        nn = norm_company_name(name)
        gm = _PREFIX_GEO.search(x["excerpt"] or "")
        state = _us_state(gm.group(2)) if gm else None
        g = groups.setdefault(f"sbir:{nn}|{state or ''}", Group())
        g.names.append(name)
        g.country = "US"
        g.region = g.region or state
        if gm and not g.city:
            g.city = gm.group(1).strip().title()
        a = attrs.get((nn, state or ""), {})
        g.duns = g.duns or a.get("duns")
        g.website = g.website or a.get("website")
        g.employees = g.employees or a.get("employees")
        money = parse_money(x["title"])
        g.events.append(_event(
            "sbir_award", x["published_date"], "SBIR.gov", x["url"], x["id"],
            amount=money[0] if money else None,
            currency="USD" if money else None,
            program=program, phase=phase, agency=agency))
        g.sources.add("sbir")
    logger.info("SBIR: %d Firmen (Name+State), %d Zeilen übersprungen", len(groups), skipped)
    return groups


def load_cordis(unassigned_only: bool = False, since: str | None = None,
                limit: int = 0) -> dict[str, Group]:
    """CORDIS: Gruppierung per PIC (Stufe A)."""
    groups: dict[str, Group] = {}
    skipped = 0
    sql = ("select r.id, r.title, r.excerpt, r.url, r.published_date "
           "from raw_entries r join sources s on s.id = r.source_id "
           "where s.name like ? and r.title is not null and r.published_date is not null")
    params: list = ["%CORDIS%"]
    if unassigned_only:
        sql += f" {_UNASSIGNED_RAW}"
    if since:
        sql += " and r.published_date >= ?"
        params.append(since)
    sql += " order by r.id"
    with get_connection() as conn:
        rows = conn.execute(sql, tuple(params)).fetchall()
    if limit:
        # KEIN SQL-LIMIT hier (#94-Befund 2026-08-29): der Anti-Join gegen
        # startup_events, ohne Index auf raw_entries.source_id, lässt den
        # Postgres-Planner bei kleinem LIMIT + wenigen/keinen Treffern einen
        # Nested-Loop-Plan wählen, der de facto die ganze raw_entries-Tabelle
        # (22M+ Zeilen) durchsucht — gemessen: limit=20 lief in ~8s (Merge
        # Anti Join, Kostenschätzung ~9,3 Mio.), limit=5 lief >60s ohne
        # Ergebnis (Nested Loop, Kostenschätzung 543 Mio.). Bis
        # raw_entries(source_id) einen Index hat, wird darum immer die volle
        # Kandidatenmenge geholt und HIER in Python auf --limit gekappt.
        rows = rows[:limit]
    for x in rows:
        m = _CORDIS_TITLE.match(x["title"])
        ids = pic_from_cordis_url(x["url"])
        if not m or not ids:
            skipped += 1
            continue
        name, amount_s, programme, acronym = (m.group(1).strip(), m.group(2),
                                              m.group(3), m.group(4).strip())
        project_id, pic = ids
        g = groups.setdefault(f"pic:{pic}", Group())
        g.names.append(name)
        g.pic = pic
        gm = _PREFIX_GEO.search(x["excerpt"] or "")
        if gm:
            # CORDIS nutzt EU-Codes: UK/EL statt ISO GB/GR
            iso = {"UK": "GB", "EL": "GR"}.get(gm.group(2), gm.group(2))
            g.country = g.country or iso
            g.city = g.city or gm.group(1).strip().title()
        money = parse_money(amount_s)
        g.events.append(_event(
            "grant", x["published_date"], "CORDIS", x["url"], x["id"],
            amount=money[0] if money else None,
            currency="EUR" if money else None,
            programme=programme, project_id=project_id, acronym=acronym))
        g.sources.add("cordis")
    logger.info("CORDIS: %d Firmen (PIC), %d Zeilen übersprungen", len(groups), skipped)
    return groups


def load_press(unassigned_only: bool = False, since: str | None = None,
               limit: int = 0) -> dict[str, Group]:
    """Presse-Runden: Gruppierung per name_norm (keine Geografie verfügbar)."""
    groups: dict[str, Group] = {}
    sql = ("select x.raw_entry_id, x.company, x.amount_value, x.currency, "
           "x.round_label, x.investors, "
           "r.url, coalesce(r.published_date, r.fetched_at) as d, "
           "s.name as source_name "
           "from startup_press_rounds x "
           "join raw_entries r on r.id = x.raw_entry_id "
           "join sources s on s.id = r.source_id "
           "where x.company is not null and coalesce(x.round_label, '') != 'vc_fund'")
    params: list = []
    if unassigned_only:
        sql += f" {_UNASSIGNED_PRESS}"
    if since:
        sql += " and coalesce(r.published_date, r.fetched_at) >= ?"
        params.append(since)
    sql += " order by x.raw_entry_id"
    with get_connection() as conn:
        rows = conn.execute(sql, tuple(params)).fetchall()
    if limit:
        # KEIN SQL-LIMIT hier (#94-Befund 2026-08-29): der Anti-Join gegen
        # startup_events, ohne Index auf raw_entries.source_id, lässt den
        # Postgres-Planner bei kleinem LIMIT + wenigen/keinen Treffern einen
        # Nested-Loop-Plan wählen, der de facto die ganze raw_entries-Tabelle
        # (22M+ Zeilen) durchsucht — gemessen: limit=20 lief in ~8s (Merge
        # Anti Join, Kostenschätzung ~9,3 Mio.), limit=5 lief >60s ohne
        # Ergebnis (Nested Loop, Kostenschätzung 543 Mio.). Bis
        # raw_entries(source_id) einen Index hat, wird darum immer die volle
        # Kandidatenmenge geholt und HIER in Python auf --limit gekappt.
        rows = rows[:limit]
    for x in rows:
        nn = norm_company_name(x["company"])
        if not nn:
            continue
        g = groups.setdefault(f"press:{nn}", Group())
        g.names.append(x["company"].strip())
        try:
            investors = (json.loads(x["investors"])
                         if isinstance(x["investors"], str) else (x["investors"] or []))
        except ValueError:
            investors = []
        g.events.append(_event(
            "press_round", x["d"], x["source_name"], x["url"], x["raw_entry_id"],
            amount=x["amount_value"], currency=x["currency"] or None,
            round_label=x["round_label"], investors=investors))
        g.sources.add("press")
    logger.info("Presse: %d Firmen (name_norm)", len(groups))
    return groups


# ---------------------------------------------------------------- Merge (Stufe B)

def _geo_compatible(a, b) -> bool:
    if a.country and b.country and a.country != b.country:
        return False
    if a.region and b.region and a.region != b.region:
        return False
    return True


def merge(all_groups: list[Group]) -> list[Group]:
    """Quellübergreifender Merge: gleicher name_norm + Geo-Gate; Presse nur
    bei eindeutigem, hinreichend langem Schlüssel."""
    by_norm: dict[str, list[Group]] = defaultdict(list)
    for g in all_groups:
        by_norm[norm_company_name(g.display_name())].append(g)

    merged: list[Group] = []
    stats = {"buckets": 0, "b_merges": 0, "press_merges": 0, "press_kept_alone": 0}
    for nn, bucket in by_norm.items():
        if len(bucket) == 1:
            merged.append(bucket[0])
            continue
        stats["buckets"] += 1
        press = [g for g in bucket if g.sources == {"press"}]
        rest = [g for g in bucket if g.sources != {"press"}]
        # Geo-basierte Merges unter den Quellen MIT Geografie
        out: list[Group] = []
        for g in rest:
            target = next((o for o in out if _geo_compatible(o, g)), None)
            if target:
                target.absorb(g)
                stats["b_merges"] += 1
            else:
                out.append(g)
        # Presse (ohne Geo): nur mergen, wenn genau EIN Kandidat existiert
        for p in press:
            if len(out) == 1 and len(nn) >= MIN_PRESS_KEY_LEN:
                out[0].absorb(p)
                stats["press_merges"] += 1
            else:
                out.append(p)
                stats["press_kept_alone"] += 1
        merged.extend(out)
    logger.info("Merge: %(buckets)d Mehrfach-Buckets · %(b_merges)d Geo-Merges · "
                "%(press_merges)d Presse-Merges · %(press_kept_alone)d Presse separat", stats)
    return merged


def _corroborates_regd(e: dict, events: list[dict]) -> bool:
    """True, wenn ein press_round-Betrag dasselbe Geld beschreibt wie ein
    Reg-D-Filing derselben Firma (±15 % Betrag, ±120 Tage): Presse meldet die
    Runde, das Filing meldet sie der SEC — einmal zaehlen, nicht doppelt.
    (Sound-Agriculture-Befund 2026-08-21: 45M/45M und 75M/75M je doppelt.)
    Restunschaerfe bleibt: teilverkaufte Offerings vs. Runden-Gesamtbetrag
    sind nicht unterscheidbar — total_funding_usd ist eine belegte
    Naeherung, kein Buchhaltungswert."""
    if e["event_type"] != "press_round" or not e["amount"]:
        return False
    for r in events:
        if r["event_type"] != "regd_offering" or not r["amount"]:
            continue
        a, b = float(e["amount"]), float(r["amount"])
        if abs(a - b) / max(a, b) <= 0.15 and abs((e["event_date"] - r["event_date"]).days) <= 120:
            return True
    return False
