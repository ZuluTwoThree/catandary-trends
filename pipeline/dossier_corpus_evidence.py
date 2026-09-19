"""Korpus-Evidenz für Scouting-Dossiers — der Korpus zuerst, das Web nur dort,
wo er dünn ist (Owner-Ziel 2026-09-19, Stufe 6 in
docs/plan_dossier_agent_2026-09-18.md).

Bis Runde 26 sah der Schreiber den eigenen Korpus nur als Suchmaschine: die
Korpus-Zählung (pipeline/dossier_corpus_stats.py) zählte Jahre, der Messblock
(pipeline/dossier_quant.py) maß die Patentklasse, und alles dazwischen — WER
sich in den letzten acht Quartalen auf WELCHER Ebene bewegt hat, welche
Quellen das tragen, welche Signale den Kern treffen — kam nur zufällig über die
Trefferlisten des Agenten in den Bericht. Und das Web lief für jede Lücke,
auch für solche, die der Korpus längst deckte.

Dieses Modul läuft deterministisch VOR dem Plan und vor jedem Agenten:

  * **Signale je Ebene und Quartal** (`signals_by_tier_quarter`): rohe Zahl
    UND Anteil je 10.000 Signale derselben Ebene im selben Quartal — dieselbe
    Normierung wie die Cluster-Schicht/`pipeline/emerging.py` („Anteil am
    Gehör", damit der eigene Ingest-Zuwachs die Reihe nicht aufbläst). Die
    Ebene kommt aus `pipeline/tiers.tier_of` (Quellname, Quelltyp, Signaltyp).
  * **Akteure** aus `trends.brands`/`companies` (Top 12 mit Zahl, erstem und
    letztem Auftreten) — Untergrenze, weil die Extraktion nur im Artikelpfad
    läuft (Forschung/Patente tragen keine Namen).
  * **Quellen** (Top-Outlets mit Zahl).
  * **Repräsentative Signale** (≤ 16): die neuesten je Ebene plus die
    zentrumsnächsten aus der Vektorsuche des Laufs — jedes wird ein zitierbarer
    Katalogeintrag `T<id>` (Art article/signal, wie `_row_to_source`).
  * **Dünne Bereiche** (`thin_areas`): eine Ebene mit < 5 Signalen in den
    letzten 12 Monaten; ein Pflichtpunkt mit < 2 Korpustreffern
    (Regex + Vektor); Regulatorik und Kalender IMMER, es sei denn ≥ 3
    Regulierungs-/Entscheidungssignale in 12 Monaten.
  * **Gating** (`web_gating`): nur dünne Bereiche bekommen Web-Schritte,
    Sweeps und Budget (`len(thin) × 4`, mindestens 6, höchstens `web_steps`).

Treffer-Regel des Korpus-Durchgangs: ein Signal zählt, wenn sein Titel+Teaser
JEDEN Themenbegriff trägt — nach Normalisierung (klein, Bindestriche und
Leerzeichen entfernt, britische Schreibweisen auf amerikanische:
„data centre virtualisation" trifft „datacenter virtualization"). Die Vorauswahl
läuft über den FTS-Index (OR der Präfixe), die Regel darüber in Python; SQLite
(Tests) nimmt LIKE. Jede DB-Stufe degradiert einzeln — ohne Korpus-Evidenz gilt
ALLES als dünn und der Lauf verhält sich wie vor Stufe 6.
"""
from __future__ import annotations

import json
import logging
import re
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime

from pipeline.tiers import TIERS, tier_of

logger = logging.getLogger("dossier_corpus_evidence")

TREND_BASE_DEFAULT = "https://catandary.de/trends"
SINCE_MONTHS = 24
QUARTERS = 8
THIN_TIER_MIN = 5            # Signale einer Ebene in den letzten 12 Monaten
THIN_MUST_MIN = 2            # Korpustreffer je Pflichtpunkt
THIN_REG_MIN = 3             # Regulierungs-/Entscheidungssignale in 12 Monaten
REPRESENTATIVE_MAX = 16
RECENT_PER_TIER = 2
NEAREST_MAX = 8
ACTORS_TOP = 12
SOURCES_TOP = 8
FETCH_LIMIT = 60_000
PER10K_MIN_TOTAL = 500       # darunter trägt ein Ebene-Quartal keinen Anteil
STATEMENT_TIMEOUT = "90s"
STATUSES = ("signal", "published")
WEB_ACTIONS_PER_THIN = 4
WEB_BUDGET_MIN = 6

_REG_TYPES = frozenset({"regulation", "decision"})
_REG_WORDS = ("regulation", "regulator", "directive", "ruling", "court", "lawsuit",
              "compliance", "legislation", "verordnung", "gesetz", "gericht")
_BRITISH = (("isation", "ization"), ("ising", "izing"), ("ised", "ized"),
            ("centre", "center"), ("yse", "yze"), ("our", "or"))
_SEP = re.compile(r"[\s\-_/.,;:()\[\]'\"]+")
_WORD = re.compile(r"[A-Za-z][A-Za-z0-9+#.-]{2,}")
_STOP = frozenset("""and are the for with from into that this what which when where
how why does did will can could would should about over under between their there
they them then than more most other some such only also been being has have had was
were its you your our not but all any per via who whom whose does apply applies
must need needs does still after before each every much many""".split())


# --------------------------------------------------------------------------
# Textregel
# --------------------------------------------------------------------------

def normalize_text(s: str | None) -> str:
    """Klein, britisch → amerikanisch, alle Trenner raus: „Data-Centre
    Virtualisation" → „datacentervirtualization"."""
    t = (s or "").lower()
    for a, b in _BRITISH:
        t = t.replace(a, b)
    return _SEP.sub("", t)


_SUFFIXES = ("izations", "ization", "isation", "ational", "ations", "ation", "ities",
             "ity", "ers", "ing", "ies", "ed", "es", "er", "s")
_STEM_MIN = 4


def crude_stem(word: str) -> str:
    """Ein einziger Suffix-Schnitt in fester Reihenfolge — bewusst grob, wie
    das FTS-Lexem des Index (Snowball: „virtualization" → „virtual",
    „datacenters" → „datacent"). Der Stamm ist ein Teilstring-Muster über dem
    normalisierten Text, keine Wortgrenze: „virtual" trifft „virtualized" und
    „virtualization" gleichermaßen — dieselbe Reichweite, die die
    Korpus-Zählung (`dossier_corpus_stats`) über `to_tsquery` hat."""
    w = normalize_text(word)
    for suf in _SUFFIXES:
        if w.endswith(suf) and len(w) - len(suf) >= _STEM_MIN:
            return w[: -len(suf)]
    return w


def term_stems(terms) -> list[str]:
    """Je Begriff ein Stamm (Mehrwortbegriffe: Stamm je Wort, verkettet — der
    Text ist ebenfalls trennerfrei normalisiert)."""
    out: list[str] = []
    for t in terms or ():
        n = "".join(crude_stem(w) for w in _SEP.split(str(t).lower()) if w)
        if len(n) >= 3 and n not in out:
            out.append(n)
    return out


def row_text(row: dict) -> str:
    """Titel + Teaser + Tags — dieselben drei Felder wie der FTS-Vektor des
    Index (`dossier_quant.FTS_VECTOR`): ohne die Tags fand die Python-Regel
    am 19.09. 14 statt 50 Zeilen, weil die Klassifikation „data-center" /
    „virtualization" oft nur als Tag steht."""
    tags = row.get("tags")
    if isinstance(tags, list):
        tags = " ".join(str(t) for t in tags)
    return normalize_text(f"{row.get('title_en') or ''} {row.get('summary_en') or ''} {tags or ''}")


def raw_text(row: dict) -> str:
    """Titel + Teaser + Tags, unnormalisiert (für die Lückenregel)."""
    tags = row.get("tags")
    if isinstance(tags, list):
        tags = " ".join(str(t) for t in tags)
    return f"{row.get('title_en') or ''} {row.get('summary_en') or ''} {tags or ''}"


def row_matches(row: dict, stems: list[str]) -> bool:
    if not stems:
        return False
    hay = row_text(row)
    return all(s in hay for s in stems)


# Runde 28 (2026-09-19): erweiterter Satz. Die UND-Regel ueber die Themen-
# begriffe fand fuer "datacenter virtualization" 42 Zeilen, mit den Produkt-
# und Akteursnamen des Profils (Proxmox, VMware, Nutanix, Broadcom …) sind es
# 92 — "VMware" + "virtualization" traegt das Thema, ohne "datacenter". Namen
# aus dem Profil (Stufe 2, `actor_seeds`) und die Eigennamen der Pflichtpunkte
# ersetzen EINEN der Themenbegriffe, nie beide (Messung 19.09.: reines ODER
# ueber die Profilnamen = 1.790 Zeilen, davon 1.213 "Microsoft").
_ENTITY_STOP = frozenset("""
the and for with from into that this what which when where how why who whom
does specific technical procedural regulatory current key top two three
german european eu us uk american chinese french british global regional
article articles act regulation directive section chapter annex
company companies firm firms provider providers service services market
security processing processor controller obligations requirements standard
""".split())
_LEAD_STOP = frozenset("""
which what how why who when where does the german european american chinese french
british swiss austrian dutch italian spanish global regional specific
""".split())
_PROPER = re.compile(r"\b(?:[A-Z][A-Za-z0-9]*(?:[-.][A-Za-z0-9]+)*|[A-Z]{2,}(?:[-.][A-Za-z0-9]+)*)"
                     r"(?:\s+(?:[A-Z][A-Za-z0-9]*(?:[-.][A-Za-z0-9]+)*|[A-Z]{2,}))*")


def clean_entity(name: str) -> str:
    """Profilname ohne Klammerzusatz: "BSI (Federal Office …)" -> "BSI"."""
    n = re.sub(r"\s*\([^)]*\)", "", str(name or "")).strip(" .,;:'\"")
    return n


def proper_nouns(text: str, cap: int = 8) -> list[str]:
    """Eigennamen eines Pflichtpunkts: grossgeschriebene Wortfolgen, nicht am
    Satzanfang, ohne Fuellwoerter und Gattungsbegriffe (`_ENTITY_STOP`),
    Akronyme ab 3 Zeichen; Klammerlisten werden aufgeloest."""
    out: list[str] = []
    text = str(text or "")
    for m in _PROPER.finditer(text):
        if m.start() == 0 or text[max(0, m.start() - 2):m.start()].strip() in (".", "?", "!"):
            continue
        for piece in re.split(r"\s*(?:,|/|;|\bor\b|\band\b)\s*", m.group(0)):
            words = piece.split()
            # fuehrende Demonyme/Fragewoerter ab ("German IT" -> "IT"), die
            # Phrase selbst bleibt ganz ("EU Data Act" ist ein Name)
            while words and words[0].lower().strip(".-") in _LEAD_STOP:
                words = words[1:]
            cand = " ".join(words).strip(" .,;:")
            if not cand:
                continue
            if len(cand) < 4 and not (cand.isupper() and len(cand) >= 3):
                continue
            if len(words) == 1 and cand.lower() in _ENTITY_STOP:
                continue
            if cand not in out:
                out.append(cand)
            if len(out) >= cap:
                return out
    return out


def _entity_regex(term: str) -> re.Pattern | None:
    t = clean_entity(term)
    if len(t) < 3:
        return None
    words = [re.escape(w) for w in re.split(r"[\s\-]+", t) if w]
    if not words:
        return None
    return re.compile(r"(?<![A-Za-z0-9])" + r"[\s\-]*".join(words) + r"(?![A-Za-z0-9])", re.IGNORECASE)


def row_matches_any(row: dict, terms: list[str]) -> list[str]:
    """Welche der Namen (Wort-/Phrasengrenze, gross/klein egal, Bindestrich
    oder Leerzeichen frei) die Zeile traegt."""
    hay = raw_text(row)
    hit: list[str] = []
    for t in terms or ():
        rx = _entity_regex(t)
        if rx is not None and rx.search(hay):
            hit.append(clean_entity(t))
    return hit


def gap_terms(text: str, cap: int = 6) -> list[str]:
    """Inhaltswörter einer Lücke/eines Pflichtpunkts (≥ 4 Zeichen, ohne
    Füllwörter) — für die Treffer-Regel je Pflichtpunkt."""
    out: list[str] = []
    for w in _WORD.findall((text or "").lower()):
        w = w.strip(".-#+")
        if len(w) < 4 or w in _STOP or w in out:
            continue
        out.append(w)
        if len(out) >= cap:
            break
    return out


def text_hits_gap(text: str, terms: list[str], min_terms: int = 2) -> bool:
    """Ein Text trifft eine Lücke, wenn er mindestens `min_terms` ihrer
    Begriffe trägt (bei einer Ein-Wort-Lücke: diesen)."""
    stems = term_stems(terms)
    if not stems:
        return False
    hay = normalize_text(text)
    need = min(min_terms, len(stems))
    return sum(1 for s in stems if s in hay) >= need


# --------------------------------------------------------------------------
# Zeit
# --------------------------------------------------------------------------

def quarter_of(d) -> str | None:
    s = str(d or "")[:10]
    if len(s) < 7 or not s[:4].isdigit():
        return None
    try:
        y, m = int(s[:4]), int(s[5:7])
    except ValueError:
        return None
    if not 1 <= m <= 12:
        return None
    return f"{y}-Q{(m - 1) // 3 + 1}"


def last_quarters(today: date, n: int = QUARTERS) -> list[str]:
    y, q = today.year, (today.month - 1) // 3 + 1
    out: list[str] = []
    for _ in range(n):
        out.append(f"{y}-Q{q}")
        q -= 1
        if q == 0:
            q, y = 4, y - 1
    return list(reversed(out))


def months_ago(today: date, months: int) -> date:
    y, m = today.year, today.month - months
    while m <= 0:
        m += 12
        y -= 1
    return date(y, m, 1)


def _date_of(row: dict) -> str:
    return str(row.get("sort_date") or row.get("published_at") or "")[:10]


# --------------------------------------------------------------------------
# DB
# --------------------------------------------------------------------------

def _json_list(v) -> list[str]:
    if v is None:
        return []
    if isinstance(v, str):
        try:
            v = json.loads(v)
        except ValueError:
            return []
    if not isinstance(v, list):
        return []
    return [str(x).strip() for x in v if str(x).strip()]


def _is_postgres() -> bool:
    from pipeline import db as db_mod
    return bool(db_mod.USE_POSTGRES)


def source_types() -> dict[str, str | None]:
    """Quellname → Quelltyp (616 Zeilen) — billiger als der Join über
    raw_entries auf jeder Signalzeile."""
    from pipeline.db import get_connection
    with get_connection() as conn:
        rows = conn.execute("SELECT name, source_type FROM sources").fetchall()
    return {str(r["name"]): r["source_type"] for r in (dict(x) for x in rows)}


_TSWORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9+#-]*")


def prequery_tsquery(terms) -> str:
    """OR über die Themenbegriffe für den FTS-Index — jeder Begriff wird von
    `to_tsquery` selbst gestemmt (kein Präfix: „virtualization:*" wird zu
    „virtualizati:*" und trifft das Lexem „virtual" NICHT — Befund am 19.09.,
    0 statt 50 Zeilen). Ein Mehrwortbegriff wird zur UND-Gruppe. Die AND-Regel
    über ALLE Begriffe läuft danach in Python (`row_matches`), weil „data
    center" und „datacenter" im Index verschiedene Lexeme sind."""
    groups: list[str] = []
    for t in terms or ():
        words = [w for w in _TSWORD.findall(str(t).lower()) if len(w) >= 2]
        if not words:
            continue
        g = " & ".join(words)
        groups.append(f"({g})" if len(words) > 1 else g)
    return " | ".join(dict.fromkeys(groups))


def fetch_topic_rows(stems: list[str], since: date, limit: int = FETCH_LIMIT,
                     terms: list[str] | None = None, entities: list[str] | None = None,
                     topic_nouns: list[str] | None = None) -> list[dict]:
    """Vorauswahl über den Index (Postgres: OR der gestemmten Begriffe auf dem
    FTS-Vektor, neueste zuerst bis `limit`; SQLite: LIKE je Stamm), dann die
    AND-Regel in Python. Gibt Zeilen mit `source_type` (per Namen) und `tier`
    zurück. Runde 28: `entities` (Profilnamen) und `topic_nouns` (Eigennamen
    der Pflichtpunkte) liefern den ERWEITERTEN Satz: ein Name als ODER-
    Alternative zur UND-Regel, aber immer zusammen mit mindestens EINEM
    Themenstamm — solche Zeilen tragen `extended` = die getroffenen Namen."""
    from pipeline.db import get_connection
    if not stems:
        return []
    entities = [e for e in (entities or []) if clean_entity(e)]
    topic_nouns = [e for e in (topic_nouns or []) if clean_entity(e)]
    cols = ("id, slug, status, title_en, summary_en, source_url, source_name, "
            "primary_vertical, published_at, sort_date, trend_signal_type, brands, companies, tags")
    with get_connection() as conn:
        if _is_postgres():
            conn.execute(f"SET statement_timeout = '{STATEMENT_TIMEOUT}'")
            from pipeline.dossier_quant import FTS_VECTOR
            tsq = prequery_tsquery(list(terms if terms is not None else stems)
                                   + [clean_entity(e) for e in entities + topic_nouns])
            if not tsq:
                return []
            sql = (f"SELECT {cols} FROM trends WHERE {FTS_VECTOR} @@ to_tsquery('english', ?) "
                   f"AND sort_date >= ? AND status IN ({', '.join('?' for _ in STATUSES)}) "
                   f"ORDER BY sort_date DESC LIMIT ?")
            rows = conn.execute(sql, (tsq, since.isoformat(), *STATUSES, limit)).fetchall()
        else:
            hay_sql = ("replace(replace(lower(coalesce(title_en,'') || ' ' || "
                       "coalesce(summary_en,'') || ' ' || coalesce(tags,'')), ' ', ''), '-', '')")
            like = "(" + " AND ".join(f"{hay_sql} LIKE ?" for _ in stems) + ")"
            params: list = [f"%{s}%" for s in stems]
            extra = [normalize_text(clean_entity(e)) for e in entities + topic_nouns]
            extra = [e for e in extra if e]
            if extra:
                like = "(" + like + " OR " + " OR ".join(f"{hay_sql} LIKE ?" for _ in extra) + ")"
                params += [f"%{e}%" for e in extra]
            sql = (f"SELECT {cols} FROM trends WHERE {like} AND sort_date >= ? "
                   f"AND status IN ({', '.join('?' for _ in STATUSES)}) "
                   f"ORDER BY sort_date DESC LIMIT ?")
            rows = conn.execute(sql, (*params, since.isoformat(), *STATUSES, limit)).fetchall()
    types = source_types()
    out: list[dict] = []
    for r in rows:
        r = dict(r)
        core = row_matches(r, stems)
        ext: list[str] = []
        if not core and (entities or topic_nouns):
            # Name UND mindestens ein Themenstamm: ein reines ODER ueber die
            # Profilnamen zog am 19.09. 1.790 Zeilen (Microsoft x1213, European
            # Commission x439, eine indonesische Bank "BSI") und machte jeden
            # Pflichtpunkt "gedeckt".
            if any(st in row_text(r) for st in stems):
                ext = row_matches_any(r, entities) or row_matches_any(r, topic_nouns)
            if not ext:
                continue
        r["extended"] = ext
        r["brands"] = _json_list(r.get("brands"))
        r["companies"] = _json_list(r.get("companies"))
        r["tags"] = _json_list(r.get("tags"))
        r["source_type"] = types.get(str(r.get("source_name") or ""))
        r["tier"] = tier_of(r.get("source_name"), r["source_type"], r.get("trend_signal_type"))
        out.append(r)
    return out


def fetch_tier_totals(since: date, quarters: list[str]) -> dict[str, dict[str, int]]:
    """Signale je Ebene und Quartal über den GANZEN Korpus (Nenner der
    10k-Normierung). Gruppiert nach Quellname + Signaltyp, die Ebene wird in
    Python zugeordnet (0,4 s auf der Live-DB am 19.09.)."""
    from pipeline.db import get_connection
    with get_connection() as conn:
        if _is_postgres():
            conn.execute(f"SET statement_timeout = '{STATEMENT_TIMEOUT}'")
            rows = conn.execute(
                "SELECT to_char(date_trunc('quarter', sort_date), 'YYYY-MM') AS ym, "
                "source_name, trend_signal_type, count(*) AS n FROM trends "
                f"WHERE sort_date >= ? AND status IN ({', '.join('?' for _ in STATUSES)}) "
                "GROUP BY 1, 2, 3", (since.isoformat(), *STATUSES)).fetchall()
        else:
            rows = conn.execute(
                "SELECT substr(sort_date, 1, 7) AS ym, source_name, trend_signal_type, "
                "count(*) AS n FROM trends WHERE sort_date >= ? "
                f"AND status IN ({', '.join('?' for _ in STATUSES)}) GROUP BY 1, 2, 3",
                (since.isoformat(), *STATUSES)).fetchall()
    types = source_types()
    out: dict[str, dict[str, int]] = {t: {q: 0 for q in quarters} for t in TIERS}
    for r in rows:
        r = dict(r)
        q = quarter_of(str(r.get("ym") or "") + "-01")
        tier = tier_of(r.get("source_name"), types.get(str(r.get("source_name") or "")),
                       r.get("trend_signal_type"))
        if q in out.get(tier or "", {}):
            out[tier][q] += int(r.get("n") or 0)
    return out


# --------------------------------------------------------------------------
# Katalogeintrag (Spiegel von scripts.corpus_research._row_to_source)
# --------------------------------------------------------------------------

def default_row_to_source(row: dict, kind: str) -> dict:
    import os
    base = os.getenv("RESEARCH_TREND_BASE", TREND_BASE_DEFAULT)
    snippet = row.get("summary_en") or row.get("excerpt") or ""
    return {
        "id": f"T{row['id']}", "trend_id": row["id"], "kind": kind,
        "title": (row.get("title_en") or "").strip(),
        "url": (f"{base}/{row['slug']}" if kind == "article" else (row.get("source_url") or "")),
        "origin": row.get("source_url") or "",
        "outlet": row.get("source_name") or "",
        "vertical": row.get("primary_vertical") or "",
        "date": _date_of(row),
        "snippet": " ".join(str(snippet).split())[:420],
    }


# --------------------------------------------------------------------------
# Ergebnis
# --------------------------------------------------------------------------

@dataclass
class CorpusEvidence:
    ok: bool = False
    reason: str | None = None
    terms: list[str] = field(default_factory=list)
    stems: list[str] = field(default_factory=list)
    since: str = ""
    measured_on: str = ""
    seconds: float = 0.0
    n_signals: int = 0
    n_signals_12m: int = 0
    quarters: list[str] = field(default_factory=list)
    signals_by_tier_quarter: dict = field(default_factory=dict)
    tier_totals_12m: dict = field(default_factory=dict)
    actors: list[dict] = field(default_factory=list)
    sources: list[dict] = field(default_factory=list)
    representative: list[dict] = field(default_factory=list)
    must_hits: list[dict] = field(default_factory=list)
    regulatory_12m: int = 0
    thin_areas: list[dict] = field(default_factory=list)
    rendered_md: str = ""
    rows: list[dict] = field(default_factory=list, repr=False)
    # Runde 28: erweiterter Satz (Profil-/Pflichtpunkt-Namen als ODER)
    extra_terms: list[str] = field(default_factory=list)
    rows_extended: list[dict] = field(default_factory=list, repr=False)
    n_signals_extended: int = 0
    n_signals_extended_12m: int = 0
    tier_totals_extended_12m: dict = field(default_factory=dict)
    extended_hits: list[dict] = field(default_factory=list)

    # -- Abfragen -------------------------------------------------------
    def thin_names(self) -> list[str]:
        return [t["area"] for t in self.thin_areas]

    def is_thin(self, area: str) -> bool:
        return any(t["area"] == area for t in self.thin_areas)

    def gap_is_thin(self, text: str) -> bool:
        """Eine freie Lücke (Audit/Plan/Perspektive) ist dünn, wenn < 2
        Korpuszeilen ihre Begriffe tragen. Ohne Korpus-Evidenz: immer dünn."""
        if not self.ok:
            return True
        terms = gap_terms(text)
        if not terms:
            return True
        hits = sum(1 for r in self.rows if text_hits_gap(raw_text(r), terms))
        # Erweiterte Zeilen zaehlen nur ueber den Namen, der sie hereinholte —
        # sonst deckt "Microsoft" + "virtual" jede Luecke mit zwei Fuellwoertern.
        hits += sum(1 for r in self.rows_extended if _names_in(text, r.get("extended") or []))
        return hits < THIN_MUST_MIN

    def catalog_ids(self) -> set[str]:
        return {s["id"] for s in self.representative}

    def as_dict(self) -> dict:
        """Kompakt für `result["corpus_evidence"]` — ohne die Rohzeilen."""
        return {
            "ok": self.ok, "reason": self.reason, "terms": self.terms, "stems": self.stems,
            "since": self.since, "measured_on": self.measured_on, "seconds": self.seconds,
            "n_signals": self.n_signals, "n_signals_12m": self.n_signals_12m,
            "quarters": self.quarters,
            "signals_by_tier_quarter": self.signals_by_tier_quarter,
            "tier_totals_12m": self.tier_totals_12m,
            "actors": self.actors, "sources": self.sources,
            "representative": [{"id": s["id"], "kind": s["kind"], "tier": s.get("tier"),
                                "title": s.get("title"), "date": s.get("date"),
                                "outlet": s.get("outlet"), "why": s.get("why")}
                               for s in self.representative],
            "must_hits": self.must_hits, "regulatory_12m": self.regulatory_12m,
            "thin_areas": self.thin_areas, "rendered_md": self.rendered_md,
            "extra_terms": self.extra_terms, "n_signals_extended": self.n_signals_extended,
            "n_signals_extended_12m": self.n_signals_extended_12m,
            "tier_totals_extended_12m": self.tier_totals_extended_12m,
            "extended_hits": self.extended_hits,
        }


# --------------------------------------------------------------------------
# Zählung
# --------------------------------------------------------------------------

def tally_tier_quarter(rows: list[dict], quarters: list[str],
                       totals: dict[str, dict[str, int]] | None) -> dict:
    counts: dict[str, Counter] = {t: Counter() for t in TIERS}
    for r in rows:
        t, q = r.get("tier"), quarter_of(_date_of(r))
        if t in counts and q in quarters:
            counts[t][q] += 1
    out: dict = {}
    for t in TIERS:
        out[t] = {}
        for q in quarters:
            n = int(counts[t][q])
            tot = int((totals or {}).get(t, {}).get(q, 0) or 0)
            per = round(n * 10_000 / tot, 2) if tot >= PER10K_MIN_TOTAL else None
            out[t][q] = {"n": n, "per_10k": per, "total": tot}
    return out


def tally_actors(rows: list[dict], top: int = ACTORS_TOP) -> list[dict]:
    counts: Counter = Counter()
    first: dict[str, str] = {}
    last: dict[str, str] = {}
    canon: dict[str, str] = {}
    for r in rows:
        d = _date_of(r)
        for name in r.get("brands", []) + r.get("companies", []):
            key = name.lower()
            canon.setdefault(key, name)
            counts[key] += 1
            if d:
                first[key] = min(first.get(key, d), d)
                last[key] = max(last.get(key, d), d)
    return [{"name": canon[k], "n": n, "first": first.get(k), "last": last.get(k)}
            for k, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:top]]


def tally_sources(rows: list[dict], top: int = SOURCES_TOP) -> list[dict]:
    counts: Counter = Counter(str(r.get("source_name") or "") for r in rows)
    counts.pop("", None)
    return [{"name": k, "n": n} for k, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:top]]


def regulatory_count(rows: list[dict], since: date) -> int:
    n = 0
    for r in rows:
        if _date_of(r) < since.isoformat():
            continue
        if str(r.get("trend_signal_type") or "").lower() in _REG_TYPES:
            n += 1
            continue
        hay = f"{r.get('title_en') or ''} {r.get('summary_en') or ''}".lower()
        if any(w in hay for w in _REG_WORDS):
            n += 1
    return n


def pick_representative(rows: list[dict], search, topic: str, stems: list[str],
                        row_to_source=None, cap: int = REPRESENTATIVE_MAX) -> list[dict]:
    """Die neuesten je Ebene (RECENT_PER_TIER) + die zentrumsnächsten aus der
    Vektor-/Volltextsuche des Laufs, themengefiltert, ≤ cap. Jeder Eintrag
    trägt `tier` und `why` (recent | nearest)."""
    to_src = row_to_source or default_row_to_source
    out: list[dict] = []
    seen: set[str] = set()
    for t in TIERS:
        tier_rows = sorted((r for r in rows if r.get("tier") == t), key=_date_of, reverse=True)
        for r in tier_rows[:RECENT_PER_TIER]:
            kind = "article" if r.get("status") == "published" else "signal"
            src = to_src(r, kind)
            if src["id"] in seen:
                continue
            src["tier"] = t
            src["why"] = "recent"
            src["fetched"] = True
            seen.add(src["id"])
            out.append(src)
    if search is not None and len(out) < cap:
        try:
            hits = search(topic, NEAREST_MAX * 2) or []
        except Exception as exc:                                    # noqa: BLE001
            logger.warning("corpus evidence: nearest search failed (%s)", exc)
            hits = []
        by_id = {f"T{r['id']}": r for r in rows}
        taken = 0
        for h in hits:
            if taken >= NEAREST_MAX or len(out) >= cap:
                break
            hid = str(h.get("id") or "")
            if hid in seen or not hid:
                continue
            hay = normalize_text(f"{h.get('title') or ''} {h.get('snippet') or ''}")
            if stems and not any(s in hay for s in stems):
                continue
            src = dict(h)
            r = by_id.get(hid)
            src["tier"] = r.get("tier") if r else None
            src["why"] = "nearest"
            src["fetched"] = True
            seen.add(hid)
            out.append(src)
            taken += 1
    return out[:cap]


def _names_in(text: str, names: list[str]) -> bool:
    low = normalize_text(text)
    return any(normalize_text(n) and normalize_text(n) in low for n in names)


def must_answer_hits(must: list[str], rows: list[dict], search, stems: list[str]) -> list[dict]:
    out: list[dict] = []
    for item in must:
        terms = gap_terms(item)
        ids: set[str] = set()
        for r in rows:
            if r.get("extended"):
                # Runde 28: eine erweiterte Zeile trifft den Pflichtpunkt nur
                # ueber den Namen, der sie hereinholte ("SYS.1.5", "Proxmox").
                if _names_in(item, r.get("extended") or []):
                    ids.add(f"T{r['id']}")
                continue
            if text_hits_gap(raw_text(r), terms):
                ids.add(f"T{r['id']}")
        if search is not None and terms:
            try:
                for h in (search(item, 6) or []):
                    hay = f"{h.get('title') or ''} {h.get('snippet') or ''}"
                    nh = normalize_text(hay)
                    if text_hits_gap(hay, terms) and (not stems or any(s in nh for s in stems)):
                        ids.add(str(h.get("id")))
            except Exception as exc:                                # noqa: BLE001
                logger.warning("corpus evidence: must-answer search failed (%s)", exc)
        out.append({"item": item, "terms": terms, "hits": len(ids),
                    "thin": len(ids) < THIN_MUST_MIN})
    return out


def find_thin_areas(tier_12m: dict[str, int], must_hits: list[dict], reg_12m: int) -> list[dict]:
    out: list[dict] = []
    for t in TIERS:
        n = int(tier_12m.get(t, 0))
        if n < THIN_TIER_MIN:
            out.append({"area": t, "kind": "tier",
                        "reason": f"{n} signal(s) on the {t} tier in the last 12 months (< {THIN_TIER_MIN})"})
    for m in must_hits:
        if m.get("thin"):
            out.append({"area": m["item"], "kind": "must",
                        "reason": f"{m['hits']} corpus hit(s) for this must-answer point (< {THIN_MUST_MIN})"})
    if reg_12m < THIN_REG_MIN:
        why = f"{reg_12m} regulation/decision signal(s) in 12 months (< {THIN_REG_MIN})"
        out.append({"area": "regulatory", "kind": "fixed", "reason": why})
        out.append({"area": "calendar", "kind": "fixed", "reason": why})
    return out


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------

def render_block(ev: CorpusEvidence) -> str:
    """Kompakter Prompt-Block: Tabelle Ebene × letzte 8 Quartale (n, Anteil je
    10k), Akteure, Quellen, repräsentative Signale mit ids."""
    if not ev.ok:
        return f"(no corpus evidence: {ev.reason})"
    L: list[str] = []
    L.append(f"Corpus signals matching ALL of {', '.join(ev.terms)} since {ev.since} "
             f"(measured {ev.measured_on}): {ev.n_signals:,} — {ev.n_signals_12m:,} in the last "
             f"12 months. Per tier and quarter: count, and share per 10,000 signals of that "
             f"tier in that quarter (\"—\" = tier too small that quarter to carry a share).")
    L.append("")
    L.append("| Tier | " + " | ".join(ev.quarters) + " |")
    L.append("|---|" + "---|" * len(ev.quarters))
    for t in TIERS:
        cells = []
        for q in ev.quarters:
            c = ev.signals_by_tier_quarter.get(t, {}).get(q, {"n": 0, "per_10k": None})
            per = c.get("per_10k")
            cells.append(f"{c['n']}" + (f" ({per:g}/10k)" if per is not None else " (—)"))
        L.append(f"| {t} | " + " | ".join(cells) + " |")
    L.append("")
    if ev.actors:
        L.append("Actors named in these signals (extracted names; a floor, not a census): "
                 + "; ".join(f"{a['name']} ×{a['n']} ({a['first']}–{a['last']})" if a.get("first")
                             else f"{a['name']} ×{a['n']}" for a in ev.actors))
    else:
        L.append("Actors: none extracted on these signals (extraction runs only on the article path).")
    if ev.sources:
        L.append("Outlets: " + "; ".join(f"{s['name']} ×{s['n']}" for s in ev.sources))
    L.append(f"Regulation/decision signals in 12 months: {ev.regulatory_12m}.")
    if ev.extra_terms:
        tt = ev.tier_totals_extended_12m or {}
        L.append(f"EXTENDED set (flagged, not in the table above — signals carrying ONE topic term "
                 f"plus a product/actor name from the brief or the field profile: "
                 f"{', '.join(ev.extra_terms[:10])}): {ev.n_signals_extended:,} further signal(s) "
                 f"since {ev.since}, {ev.n_signals_extended_12m:,} in 12 months ("
                 + ", ".join(f"{t} {int(tt.get(t, 0))}" for t in TIERS) + ")"
                 + ("; names hit: " + "; ".join(f"{h['name']} ×{h['n']}" for h in ev.extended_hits[:8])
                    if ev.extended_hits else "") + ".")
    L.append("")
    if ev.representative:
        L.append("Representative signals (cite by id; 'extended' = matched by a product/actor name):")
        for s in ev.representative:
            L.append(f"- [[{s['id']}]] [{s['kind']}] {s.get('date') or '—'} · {s.get('tier') or '?'} · "
                     f"{s.get('title')}" + (f" — {s['outlet']}" if s.get("outlet") else "")
                     + f" ({s.get('why')})")
    else:
        L.append("Representative signals: none — the corpus holds no signal matching all topic terms.")
    L.append("")
    if ev.thin_areas:
        L.append("THIN in the corpus (the web is used ONLY here): "
                 + "; ".join(f"{t['area']} — {t['reason']}" for t in ev.thin_areas))
    else:
        L.append("Nothing thin in the corpus — no web research was needed.")
    return "\n".join(L)


def render_note(ev: CorpusEvidence) -> str:
    return ("Deterministic corpus evidence — our own count over the corpus, run before any "
            "model hop. Figures here carry NO citation; the representative signals below "
            "are catalog entries and are cited by id:\n" + render_block(ev))


# --------------------------------------------------------------------------
# Einstieg
# --------------------------------------------------------------------------

EXTENDED_REPRESENTATIVE = 4


def build(topic: str, brief: dict | None = None, *, terms: list[str] | None = None,
          search=None, since_months: int = SINCE_MONTHS, today: date | None = None,
          row_to_source=None, entities: list[str] | None = None) -> CorpusEvidence:
    """Der Korpus-Durchgang. Gibt IMMER ein CorpusEvidence zurück; jeder DB-
    oder Suchfehler wird zum Fehlgrund (`ok=False`), nie zum Absturz.

    Runde 28: `entities` (Akteur-/Produktnamen des Profils, Stufe 2) und die
    Eigennamen der Pflichtpunkte des Auftrags bilden den ERWEITERTEN Satz
    (Name + mindestens ein Themenstamm); die Tabelle, die Akteure und die
    Duenne-Regel je Ebene bleiben auf dem Kernsatz (UND ueber die Themen-
    begriffe), Pflichtpunkt-Treffer und `gap_is_thin` zaehlen beide."""
    t0 = time.time()
    today = today or datetime.now().date()
    ev = CorpusEvidence(measured_on=today.isoformat())
    ev.terms = [str(t) for t in (terms or []) if str(t).strip()]
    if not ev.terms:
        ev.terms = gap_terms(topic, cap=4)
    ev.stems = term_stems(ev.terms)
    since = months_ago(today, since_months)
    ev.since = since.isoformat()
    ev.quarters = last_quarters(today, QUARTERS)
    must = [str(m) for m in ((brief or {}).get("must_answer") or []) if str(m).strip()]
    ents = [clean_entity(e) for e in (entities or []) if clean_entity(e)]
    ents = [e for e in dict.fromkeys(ents) if e.lower() not in {t.lower() for t in ev.terms}]
    nouns: list[str] = []
    for item in must:
        for n in proper_nouns(item):
            if n.lower() not in {e.lower() for e in ents} and n.lower() not in {t.lower() for t in ev.terms}:
                if n not in nouns:
                    nouns.append(n)
    ev.extra_terms = ents + nouns
    if not ev.stems:
        ev.reason = "no usable topic terms"
        ev.rendered_md = render_block(ev)
        return ev
    try:
        rows_all = fetch_topic_rows(ev.stems, since, terms=ev.terms, entities=ents, topic_nouns=nouns)
        rows = [r for r in rows_all if not r.get("extended")]
        rows_ext = [r for r in rows_all if r.get("extended")]
    except Exception as exc:                                        # noqa: BLE001
        logger.warning("corpus evidence: topic rows not measured (%r)", exc)
        ev.reason = f"corpus rows not measured ({type(exc).__name__})"
        ev.rendered_md = render_block(ev)
        return ev
    totals: dict | None = None
    try:
        totals = fetch_tier_totals(since, ev.quarters)
    except Exception as exc:                                        # noqa: BLE001
        logger.warning("corpus evidence: tier totals not measured (%r) — raw counts only", exc)
    ev.ok = True
    ev.rows = rows
    ev.rows_extended = rows_ext
    ev.n_signals = len(rows)
    cut12 = months_ago(today, 12).isoformat()
    rows12 = [r for r in rows if _date_of(r) >= cut12]
    ev.n_signals_12m = len(rows12)
    ev.n_signals_extended = len(rows_ext)
    ext12 = [r for r in rows_ext if _date_of(r) >= cut12]
    ev.n_signals_extended_12m = len(ext12)
    ev.tier_totals_extended_12m = {t: sum(1 for r in ext12 if r.get("tier") == t) for t in TIERS}
    hits: Counter = Counter(n for r in rows_ext for n in (r.get("extended") or []))
    ev.extended_hits = [{"name": k, "n": n} for k, n in sorted(hits.items(), key=lambda kv: (-kv[1], kv[0]))]
    ev.signals_by_tier_quarter = tally_tier_quarter(rows, ev.quarters, totals)
    ev.tier_totals_12m = {t: sum(1 for r in rows12 if r.get("tier") == t) for t in TIERS}
    ev.actors = tally_actors(rows)
    ev.sources = tally_sources(rows)
    ev.regulatory_12m = regulatory_count(rows, months_ago(today, 12))
    ev.representative = pick_representative(rows, search, topic, ev.stems, row_to_source)
    if rows_ext and len(ev.representative) < REPRESENTATIVE_MAX + EXTENDED_REPRESENTATIVE:
        to_src = row_to_source or default_row_to_source
        seen_ids = {s_["id"] for s_ in ev.representative}
        for r in sorted(rows_ext, key=_date_of, reverse=True)[:EXTENDED_REPRESENTATIVE]:
            src = to_src(r, "article" if r.get("status") == "published" else "signal")
            if src["id"] in seen_ids:
                continue
            src["tier"] = r.get("tier")
            src["why"] = "extended: " + ", ".join(r.get("extended") or [])[:60]
            src["fetched"] = True
            seen_ids.add(src["id"])
            ev.representative.append(src)
    ev.must_hits = must_answer_hits(must, rows + rows_ext, search, ev.stems)
    ev.thin_areas = find_thin_areas(ev.tier_totals_12m, ev.must_hits, ev.regulatory_12m)
    ev.seconds = round(time.time() - t0, 1)
    ev.rendered_md = render_block(ev)
    logger.info("corpus evidence: %d signal(s) since %s (%d in 12 months), tiers 12m %s, "
                "%d actor(s), %d representative, extended +%d (%s), thin: %s (%.1fs)",
                ev.n_signals, ev.since, ev.n_signals_12m, ev.tier_totals_12m, len(ev.actors),
                len(ev.representative), ev.n_signals_extended,
                ", ".join(ev.extra_terms[:6]) or "no names",
                ", ".join(ev.thin_names()) or "nothing", ev.seconds)
    return ev


# --------------------------------------------------------------------------
# Gating: Web nur, wo der Korpus dünn ist
# --------------------------------------------------------------------------

def web_gating(ev: CorpusEvidence | None, gaps: list[str], gap_kinds: list[str],
               web_steps: int) -> dict:
    """Welche Lücken ans Web gehen, welche Sweeps laufen, wie viel Budget.

    * Pflichtpunkte: nur die mit < 2 Korpustreffern (`must_hits`).
    * Audit-/Plan-/Perspektiv-Lücken: nur wenn `gap_is_thin` (< 2 Zeilen des
      Korpus-Durchgangs tragen ihre Begriffe).
    * Sweeps: Regulatorik ↔ „regulatory" dünn; Markt ↔ Markt-Ebene dünn;
      Förderung ↔ Förder-Ebene dünn; Katalysator/Kalender ↔ „calendar" dünn.
    * Budget: `len(thin) × 4`, mindestens 6, höchstens `web_steps`.
    Ohne Korpus-Evidenz (ok=False) ist alles dünn = Verhalten vor Stufe 6."""
    ok = bool(ev and ev.ok)
    thin_must = {m["item"].lower() for m in ((ev.must_hits if ev else []) or []) if m.get("thin")}
    decisions: list[dict] = []
    web_idx: list[int] = []
    for i, (g, k) in enumerate(zip(gaps, gap_kinds)):
        if not ok:
            keep, why = True, "no corpus evidence — everything counts as thin"
        elif k == "must":
            keep = g.lower() in thin_must
            why = "must-answer point thin in the corpus" if keep else "must-answer point covered by the corpus"
        else:
            keep = ev.gap_is_thin(g)
            why = "gap terms thin in the corpus" if keep else "gap terms covered by the corpus"
        decisions.append({"index": i, "kind": k, "gap": g[:120], "web": keep, "why": why})
        if keep:
            web_idx.append(i)
    if not ok:
        sweeps = {"regulatory": True, "market": True, "funding": True, "catalyst": True}
        budget = int(web_steps)
        thin = []
    else:
        sweeps = {"regulatory": ev.is_thin("regulatory"), "market": ev.is_thin("market"),
                  "funding": ev.is_thin("funding"), "catalyst": ev.is_thin("calendar")}
        thin = ev.thin_names()
        budget = min(int(web_steps), max(WEB_BUDGET_MIN, WEB_ACTIONS_PER_THIN * len(thin)))
        if web_steps <= 0:
            budget = 0
    return {"corpus_evidence_ok": ok, "thin_areas": thin, "web_gaps": web_idx,
            "corpus_only_gaps": [i for i in range(len(gaps)) if i not in web_idx],
            "sweeps": sweeps, "web_budget": budget, "web_steps": int(web_steps),
            "decisions": decisions}


# --------------------------------------------------------------------------
# Was das Web zu den dünnen Bereichen ergab (Sektion „Where the evidence is thin")
# --------------------------------------------------------------------------

CORPUS_KINDS = frozenset({"article", "signal", "paper", "patent", "measurement"})


def is_corpus_source(src: dict) -> bool:
    """Katalogeintrag aus dem eigenen Korpus oder der eigenen Messung — im
    Gegensatz zu allem, was aus dem Web kam (web/legal/market/entity/funding)."""
    return str((src or {}).get("kind") or "") in CORPUS_KINDS


def thin_yield(ev: CorpusEvidence | None, gating: dict | None, gaps: list[str],
               ledger: list[dict], sweeps_added: dict[str, int] | None = None) -> list[dict]:
    """Je dünnem Bereich: was der Korpus hatte und was die Web-Stufe dazu
    brachte (Anfragen, aufgenommene, gelesene Seiten). Tier-Bereiche und die
    festen Bereiche (regulatory/calendar) hängen an den Sweeps, Pflichtpunkte
    an ihrer Ledger-Zeile."""
    if not ev or not ev.ok:
        return []
    sweeps_added = sweeps_added or {}
    web_idx = set((gating or {}).get("web_gaps") or [])
    low_gaps = [g.lower() for g in gaps]
    out: list[dict] = []
    for t in ev.thin_areas:
        row = {"area": t["area"], "kind": t["kind"], "reason": t["reason"],
               "web_queries": 0, "web_sources": 0, "web_fetched": 0, "gated": False}
        if t["kind"] == "must":
            gi = next((i for i, g in enumerate(low_gaps) if g == t["area"].lower()), None)
            if gi is not None and gi < len(ledger):
                e = ledger[gi]
                row["web_queries"] = len(e.get("web_queries") or [])
                row["web_sources"] = int(e.get("web_sources") or 0)
                row["web_fetched"] = int(e.get("web_fetched") or 0)
                row["gated"] = gi in web_idx
        elif t["kind"] == "tier":
            key = {"market": "market", "funding": "funding"}.get(t["area"])
            if key:
                row["web_sources"] = int(sweeps_added.get(key, 0))
                row["gated"] = bool(((gating or {}).get("sweeps") or {}).get(key))
        else:                                   # regulatory / calendar
            key = "regulatory" if t["area"] == "regulatory" else "catalyst"
            row["web_sources"] = int(sweeps_added.get(key, 0))
            row["gated"] = bool(((gating or {}).get("sweeps") or {}).get(key))
        out.append(row)
    return out


def render_thin_block(rows: list[dict]) -> str:
    """Prompt-Block für die Sektion „Where the evidence is thin"."""
    if not rows:
        return ""
    L = ["THIN AREAS — what the corpus lacked, and what the web stage brought for exactly "
         "these (the web ran ONLY here). Write 'Where the evidence is thin' from these lines: "
         "one bullet per area, naming the area, the corpus count and what the web yielded "
         "(cite the web pages you use by id); an area where the web brought nothing is "
         "stated as such, never filled."]
    for r in rows:
        got = (f"web: {r['web_queries']} quer{'y' if r['web_queries'] == 1 else 'ies'}, "
               f"{r['web_sources']} source(s) admitted, {r['web_fetched']} read"
               if r["kind"] == "must" else f"web sweep: {r['web_sources']} source(s) admitted")
        if not r.get("gated") and r["kind"] == "must":
            got = "web: not searched (budget)"
        L.append(f"- {r['area']} [{r['kind']}] — corpus: {r['reason']}; {got}")
    return "\n".join(L)

