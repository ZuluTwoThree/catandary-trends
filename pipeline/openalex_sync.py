"""OpenAlex-Sync v2 — Änderungen erkennen statt verwerfen (Owner 2026-10-05).

Anlass (`docs/openalex_sync_2026-10-05.md`): OpenAlex hat im Oktober-Release ~87 % des
Bestands neu ausgegeben. Der alte Ingest fügte mit `ON CONFLICT DO NOTHING` ein — für die
94 % vorhandenen Werke rechnete er trotzdem den Volltext-Vektor und verwarf dann alles:
neue Zitationszahlen, bereinigte Abstracts, Zurückziehungen. Owner-Vorgabe: Deduplizierung
früh, aber nicht um den Preis, dass wesentliche Information (etwa ein nachträglich
ergänzter Abstract) verborgen bleibt; robuster, sparsamer, mehr Nutzen.

Diese Datei ist die REINE Logik (testbar ohne DB/S3): Fingerabdruck, Textentscheidung,
Klassifikation eines Batches gegen den bekannten Zustand. Der Lauf selbst:
`scripts/ingest_openalex_snapshot.py`.

Textentscheidung (gemessen an 4.234 vorhandenen Werken, 05.10.):
  * Leerraum/Satzzeichen-Unterschiede (z. B. „transmission.The") → gleich (Fingerabdruck
    über Buchstaben/Ziffern, klein geschrieben).
  * Titel ohne Markup („MnO<sub>2</sub>" → „MnO2") → übernehmen.
  * Abstract ersetzt Seiten-Müll durch den echten Text oder vervollständigt einen
    abgeschnittenen → übernehmen.
  * Neuer Abstract ist nur ein ANFANGSSTÜCK unseres (z. B. „Aims" ohne „Methods") →
    unseren behalten, als `shortened` vermerken. Keine Information geht verloren.

Was die große Tabelle `research_corpus` (147 GB, 13-GB-GIN) anfasst: nur neue Werke,
echte Textänderungen und gekippte Zurückziehungen. Zitationen, FWCI, Perzentil, Typ und
Open-Access-Status stehen in der schmalen Tabelle `research_work_state`.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time as dtime, timedelta

KEEP_TYPES = ("article", "preprint", "review")
MIN_YEAR = 2010
CITE_FLOOR_BEFORE = 2023
TITLE_MAX = 2000
ABSTRACT_MAX = 16000
MIN_ABSTRACT = 50

_NONWORD = re.compile(r"[\W_]+", re.UNICODE)
_TAG = re.compile(r"<[^<>]{0,200}>")


def strip_markup(s: str | None) -> str:
    """HTML-Tags und Entities entfernen (`MnO<sub>2</sub>`, `&lt;i&gt;`) — für Vergleich und Anzeige."""
    import html
    s = s or ""
    for _ in range(2):                      # doppelt kodiert: &amp;lt;sub&amp;gt;
        s = html.unescape(s)
    return _TAG.sub("", s)


def norm(s: str | None) -> str:
    """Buchstaben + Ziffern, klein, ohne Markup — Leerraum, Satzzeichen, <i>/<sub> zählen nicht.
    Gemessen 05.10.: ohne das Markup-Entfernen hielt der Vergleich 15 % der vorhandenen
    Werke für geändert, fast alles entfernte Kursiv-/Index-Tags."""
    return _NONWORD.sub("", strip_markup(s).lower())


_LABEL = re.compile(r"^(abstract|summary|background|objectives?|introduction|purpose|aims?)", re.I)


def norm_abstract(s: str | None) -> str:
    """Wie norm(), dazu ohne vorangestellte Beschriftung („Abstract", „Background" …) —
    gemessen 05.10.: OpenAlex setzt/entfernt sie, ohne dass sich der Text ändert."""
    n = norm(s)
    for _ in range(2):                      # „Abstract Aims …" → zwei Beschriftungen
        n = _LABEL.sub("", n, count=1)
    return n


def text_fp(title: str | None, abstract: str | None) -> int:
    """64-bit-Fingerabdruck (signed, passt in BIGINT) über die normalisierten Texte."""
    h = hashlib.md5((norm(title) + "\x1f" + norm_abstract(abstract)).encode("utf-8")).digest()
    return int.from_bytes(h[:8], "big", signed=True)


@dataclass
class TextDecision:
    title: str
    abstract: str
    changed: bool          # Zeile in research_corpus neu schreiben
    shortened: bool        # OpenAlex liefert nur ein Anfangsstück — unseres behalten
    title_changed: bool = False
    abstract_changed: bool = False


def decide_text(db_title: str, db_abstract: str, new_title: str, new_abstract: str) -> TextDecision:
    """Was soll in research_corpus stehen? Siehe Modulkopf."""
    t_db, t_new = norm(db_title), norm(new_title)
    a_db, a_new = norm_abstract(db_abstract), norm_abstract(new_abstract)
    title = db_title
    # Titel: wie beim Abstract wird ein bloßes Anfangsstück (Untertitel weggefallen) nicht übernommen.
    title_changed = bool(t_new) and t_new != t_db and not (t_db.startswith(t_new) and len(t_new) < len(t_db))
    if title_changed:
        title = new_title
    abstract, abstract_changed, shortened = db_abstract, False, False
    if a_new != a_db:
        if a_new and a_db.startswith(a_new) and len(a_new) < len(a_db):
            shortened = True
        elif len((new_abstract or "").strip()) >= MIN_ABSTRACT:
            abstract, abstract_changed = new_abstract, True
    return TextDecision(title, abstract, title_changed or abstract_changed, shortened,
                        title_changed, abstract_changed)


def reconstruct(inv) -> str:
    """Abstract aus dem invertierten Index zusammensetzen."""
    if inv is None:
        return ""
    if isinstance(inv, str):
        try:
            inv = json.loads(inv)
        except ValueError:
            return ""
    if not isinstance(inv, dict):
        return ""
    pos: dict[int, str] = {}
    for word, places in inv.items():
        for p in places or []:
            pos[p] = word
    return " ".join(pos[k] for k in sorted(pos))


def recent_floor(today: date | None = None) -> int:
    """„Jüngste Zitationen" = laufendes und voriges Jahr (rollierend; vorher fest 2025)."""
    return (today or date.today()).year - 1


def citation_counts(counts_by_year, today: date | None = None) -> tuple[int, int]:
    cby = counts_by_year or []
    floor = recent_floor(today)
    total = sum((x or {}).get("cited_by_count") or 0 for x in cby)
    recent = sum((x or {}).get("cited_by_count") or 0 for x in cby if ((x or {}).get("year") or 0) >= floor)
    return recent, total


def keep_row(r: dict) -> bool:
    """Derselbe Filter wie bisher (Typ, kein Paratext, Englisch, Jahr, Abstract, Zitations-Floor)."""
    if r.get("type") not in KEEP_TYPES or r.get("is_paratext") or r.get("language") != "en":
        return False
    y = r.get("publication_year") or 0
    if y < MIN_YEAR or r.get("abstract_inverted_index") is None:
        return False
    return y > CITE_FLOOR_BEFORE or (r.get("cited_by_count") or 0) >= 1


def _topic(r: dict) -> str | None:
    t = r.get("primary_topic")
    return t.get("display_name") if isinstance(t, dict) else None


def _cnp(r: dict) -> float | None:
    c = r.get("citation_normalized_percentile")
    v = c.get("value") if isinstance(c, dict) else None
    return float(v) if v is not None else None


@dataclass
class Work:
    """Eine Zeile aus dem Parquet, auf unsere Felder gebracht."""
    id: str
    doi: str | None
    title: str
    abstract: str
    published: str | None
    year: int | None
    type: str | None
    topic: str | None
    cited_by_count: int | None
    fwci: float | None
    cnp: float | None
    is_retracted: bool
    is_oa: bool
    oa_url: str | None
    journal: str | None
    funders: list[str]
    recent: int
    total: int
    updated: str | None
    fp: int = 0
    raw_index: int = -1        # Zeile im Parquet-Batch (für das Archiv)

    @classmethod
    def from_row(cls, r: dict, idx: int = -1, today: date | None = None) -> "Work | None":
        wid = (r.get("id") or "").rsplit("/", 1)[-1]
        title = (r.get("title") or "").strip()[:TITLE_MAX]
        abstract = reconstruct(r.get("abstract_inverted_index"))[:ABSTRACT_MAX]
        if not wid or not title or len(abstract) < MIN_ABSTRACT:
            return None
        oa = r.get("open_access") if isinstance(r.get("open_access"), dict) else {}
        url = (oa.get("oa_url") or "").strip() if oa else ""
        loc = r.get("primary_location") if isinstance(r.get("primary_location"), dict) else {}
        src = (loc or {}).get("source") if isinstance((loc or {}).get("source"), dict) else {}
        journal = ((src or {}).get("display_name") or "").strip()[:300] or None
        funders = []
        for fu in (r.get("funders") or [])[:10]:
            n = ((fu or {}).get("display_name") or "").strip()[:300]
            if n and n not in funders:
                funders.append(n)
        recent, total = citation_counts(r.get("counts_by_year"), today)
        w = cls(id=wid, doi=r.get("doi"), title=title, abstract=abstract,
                published=str(r["publication_date"])[:10] if r.get("publication_date") else None,
                year=r.get("publication_year"), type=r.get("type"), topic=_topic(r),
                cited_by_count=r.get("cited_by_count"),
                fwci=float(r["fwci"]) if r.get("fwci") is not None else None, cnp=_cnp(r),
                is_retracted=bool(r.get("is_retracted")), is_oa=bool(oa.get("is_oa")) and bool(url),
                oa_url=url[:600] or None, journal=journal, funders=funders, recent=recent, total=total,
                updated=str(r.get("updated_date"))[:10] if r.get("updated_date") else None, raw_index=idx)
        w.fp = text_fp(w.title, w.abstract)
        return w


@dataclass
class Plan:
    """Was ein Batch schreibt — reine Daten, ausgeführt in scripts/ingest_openalex_snapshot.py."""
    insert: list[Work] = field(default_factory=list)                       # neu in research_corpus
    update_text: list[tuple[Work, TextDecision]] = field(default_factory=list)
    retraction: list[tuple[str, bool]] = field(default_factory=list)      # nur das Flag
    state: list[tuple] = field(default_factory=list)                       # Upsert research_work_state
    side: list[Work] = field(default_factory=list)                         # Journal/Förderer (insert-if-missing)
    oa: list[Work] = field(default_factory=list)                           # research_work_oa
    cites: list[Work] = field(default_factory=list)                        # research_citation_recent upsert
    archive: list[int] = field(default_factory=list)                       # Zeilen fürs lokale Archiv
    unchanged: int = 0
    shortened: int = 0


def same_float(a, b) -> bool:
    """REAL in Postgres ist float4 und kommt als kurze Dezimalzahl zurück — gleich bis auf Rundung.
    Gemessen 05.10.: ein exakter Vergleich schrieb beim zweiten Lesen 95 % der Zustandszeilen neu."""
    if a is None or b is None:
        return a is None and b is None
    return abs(float(a) - float(b)) <= 1e-6 * max(1.0, abs(float(a)), abs(float(b)))


def state_row(w: Work, oa_fp: int, shortened: bool) -> tuple:
    return (w.id, oa_fp, w.cited_by_count, w.fwci, w.cnp, w.type, w.is_retracted, w.is_oa,
            shortened, w.updated)


def plan_batch(works: list[Work], state: dict[str, dict], db_text: dict[str, dict]) -> Plan:
    """Vergleicht einen Batch mit dem bekannten Zustand.

    `state[id]`  = Zeile aus research_work_state (oa_fp, cited_by_count, fwci, cnp, type,
                   is_retracted, is_oa, shortened) — fehlt beim ersten Kontakt.
    `db_text[id]`= {title, abstract, is_retracted} aus research_corpus — nur für Werke, deren
                   Text zu prüfen ist (kein Zustand oder geänderter OpenAlex-Fingerabdruck)
                   und zur Existenzprüfung (fehlt das Werk in beiden → neu).
    """
    p = Plan()
    for w in works:
        st = state.get(w.id)
        dbt = db_text.get(w.id)
        if st is None and dbt is None:                       # neu
            p.insert.append(w)
            p.state.append(state_row(w, w.fp, False))
            p.side.append(w)
            if w.is_oa:
                p.oa.append(w)
            if w.total > 0:
                p.cites.append(w)
            p.archive.append(w.raw_index)
            continue
        first_touch = st is None
        shortened = bool(st and st.get("shortened"))
        text_checked = text_updated = False
        if first_touch or st.get("oa_fp") != w.fp:
            if dbt is not None:
                d = decide_text(dbt["title"], dbt["abstract"], w.title, w.abstract)
                text_checked, shortened = True, d.shortened
                if d.changed:
                    text_updated = True
                    p.update_text.append((w, d))      # schreibt is_retracted gleich mit
                    p.archive.append(w.raw_index)
        known = dbt.get("is_retracted") if dbt is not None else st.get("is_retracted")
        if not text_updated and bool(known) != w.is_retracted:
            p.retraction.append((w.id, w.is_retracted))
        changed_state = first_touch or text_checked or any(
            st.get(k) != v for k, v in (("cited_by_count", w.cited_by_count), ("type", w.type),
                                         ("is_retracted", w.is_retracted), ("is_oa", w.is_oa))) or not (
            same_float(st.get("fwci"), w.fwci) and same_float(st.get("cnp"), w.cnp))
        if changed_state:
            p.state.append(state_row(w, w.fp, shortened))
            if shortened:
                p.shortened += 1
        else:
            p.unchanged += 1
        if first_touch:
            p.side.append(w)
        if w.is_oa and (first_touch or not st.get("is_oa")):
            p.oa.append(w)
        if w.total > 0 and (first_touch or st.get("cited_by_count") != w.cited_by_count):
            p.cites.append(w)
    return p


# ---------------------------------------------------------------------------
# Zeitfenster
# ---------------------------------------------------------------------------
def deadline(until: str | None, now: datetime | None = None) -> datetime | None:
    """„HH:MM" → nächster solcher Zeitpunkt nach `now` (über Mitternacht hinweg)."""
    if not until:
        return None
    if not re.fullmatch(r"\d{1,2}:\d{2}", until):
        raise ValueError(f"--until must be HH:MM, got {until!r}")
    now = now or datetime.now()
    h, m = (int(x) for x in until.split(":"))
    d = datetime.combine(now.date(), dtime(h, m))
    return d if d > now else d + timedelta(days=1)
