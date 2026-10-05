"""Field Watch / Trajectory Sheet — die gemessene Lage je Kundenfeld.

Produktpfad des Pivots vom 2026-09-19/20 (`docs/business_model_2026-09-19.md`,
`docs/commercialization_plan_2026-09-20.md`): **alles hier ist deterministische
Abfrage, kein Sprachmodell.** Ein Feld ist eine Liste von Suchphrasen (Titel/
Teaser/Tags des Signalkorpus, Titel+Abstract des Patent-Volltextindex) plus
CPC-Anker fuer den Zitationsgraphen; das Mapping macht der Owner, der Kunde
gibt es frei, und es steht auf jedem Blatt (`fields/<kunde>.yaml`).

Drei Messungen:

  measure_week(fields, today)   Wochenblatt: je Feld und Ebene die Woche gegen
                                den Median der vier Vorwochen, 12 Quartale auf
                                festem Quellenpanel, Signale der Woche, Akteure,
                                Nester.
  measure_sheet(field)          Trajectory Sheet: Jahresreihe je Ebene ab 1990
                                (Wissenschaft aus dem Forschungskorpus ab 2010,
                                Patente aus patent_search), Take-off, Anmelder,
                                CPC-Subklassen, meistzitierte Werke/Patente,
                                Reifegradblock (K(t), Zykluszeit, Zentralitaet)
                                ueber die CPC-Anker.
  probe(phrase)                 Feldprobe: Seite 1 des Sheets fuer eine Phrase
                                ohne Anker — die Kandidatenklassen kommen aus
                                der Technologie-Suche (GPU-Handover fuer den
                                Query-Vektor), alles andere ist SQL.

Ebenenregel = Zwilling von `pipeline/tiers.py` (SQL-Form, damit die Zaehlung in
einem GROUP BY laeuft). Aendert sich dort eine Regel, aendert sie sich hier.
Die Quartalszaehlung laeuft auf einem festen Quellenpanel (Quelle in den ersten
UND letzten vier Quartalen des Fensters aktiv), weil 2026 der erste volle
Jahrgang mit 560 Quellen ist und eine rohe Anteilsreihe sonst die Sammelrampe
zeigt, nicht das Feld (gemessen 20.09.: Milchalternativen roh 65 -> 16 je 10k,
Panel 66 -> 59).
"""
from __future__ import annotations

import json
import logging
import re
import statistics
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

import yaml

from pipeline.config import DATA_DIR

logger = logging.getLogger(__name__)

TIERS = ("science", "patent", "funding", "market")
TIER_LABELS = {"science": "Wissenschaft", "patent": "Patente", "funding": "Förderung", "market": "Markt"}
FIELDS_DIR = Path(__file__).resolve().parents[1] / "fields"
OUT_DIR = Path(DATA_DIR) / "field_watch"
PATENT_SOURCE = "Patentamt (EPO/USPTO/WIPO via BDDS)"

# SQL-Zwilling von tiers.tier_of (Reihenfolge wie dort: Patentamt, Register,
# Forschung, Markt; Presse-Meldung zu einer Finanzierungsrunde = Foerderung).
TIER_SQL = """CASE
  WHEN lower(s.name) LIKE 'google patents%%' OR lower(s.name) LIKE 'epo %%' THEN 'patent'
  WHEN lower(s.name) ~ '^(nih reporter|nsf |openaire|ukri|sec form d|sbir)' OR lower(s.name) LIKE 'cordis%%' THEN 'funding'
  WHEN s.source_type='research' OR lower(s.name) LIKE '%%preprints%%' OR lower(s.name) LIKE 'openalex%%' THEN 'science'
  WHEN s.source_type IN ('trade_media','press_wire','brand') THEN CASE WHEN t.trend_signal_type='funding' THEN 'funding' ELSE 'market' END
  END"""
# Derselbe Ausdruck wie idx_trends_fts (GIN) — nur so nutzt die Suche den Index.
FTS = "to_tsvector('english', coalesce(t.title_en,'')||' '||coalesce(t.summary_en,'')||' '||coalesce(t.tags::text,''))"

CPC_SECTION_TITLES = {
    "Y02E": "Emissionsminderung bei Energieerzeugung/-speicherung (Tag)",
    "Y02W": "Abfallwirtschaft, Recycling (Tag)", "Y02P": "Klimaschutz in Produktion/Verarbeitung (Tag)",
    "Y02T": "Verkehr (Tag)", "Y02A": "Klimaanpassung (Tag)", "G06F": "Digitale Datenverarbeitung",
    "G01R": "Messung elektrischer Größen", "H02J": "Netze, Laden, Energieverteilung",
}


# ---------------------------------------------------------------------------
# Feld-Definition
# ---------------------------------------------------------------------------
def slugify(s: str) -> str:
    s = s.lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        s = s.replace(a, b)
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", s)).strip("-")


def validate_customer(doc: dict) -> dict:
    """Pflichtfelder pruefen, Slugs ableiten. Wirft ValueError mit klarer Zeile."""
    if not isinstance(doc, dict) or not doc.get("customer"):
        raise ValueError("fields yaml: 'customer' fehlt")
    doc = dict(doc)
    doc["slug"] = slugify(doc.get("slug") or doc["customer"])
    fields = doc.get("fields") or []
    if not fields:
        raise ValueError("fields yaml: 'fields' ist leer")
    out = []
    for f in fields:
        if not f.get("name"):
            raise ValueError("fields yaml: Feld ohne 'name'")
        terms = [str(t).strip() for t in (f.get("terms") or []) if str(t).strip()]
        if not terms:
            raise ValueError(f"fields yaml: Feld {f['name']!r} ohne 'terms'")
        cpc = [str(c).strip() for c in (f.get("cpc") or []) if str(c).strip()]
        out.append({"name": f["name"], "name_en": f.get("name_en") or f["name"],
                    "slug": slugify(f.get("slug") or f["name"]), "terms": terms, "cpc": cpc,
                    "reading": (f.get("reading") or "").strip(),
                    # Anhang A (Rechtsrahmen) — Text des Analysten (Markdown); Suche/Domains
                    # für den Entwurf (scripts/field_research.py regulatory). Owner 2026-10-04.
                    "regulatory": (f.get("regulatory") or "").strip(),
                    "regulatory_keywords": [str(k).strip() for k in (f.get("regulatory_keywords") or []) if str(k).strip()],
                    "regulatory_domains": [str(k).strip() for k in (f.get("regulatory_domains") or []) if str(k).strip()]})
    if len({f["slug"] for f in out}) != len(out):
        raise ValueError("fields yaml: doppelter Feld-Slug")
    doc["fields"] = out
    return doc


def load_customer(name_or_path: str) -> dict:
    p = Path(name_or_path)
    if not p.exists():
        p = FIELDS_DIR / f"{name_or_path}.yaml"
    if not p.exists():
        raise FileNotFoundError(f"keine Felddatei {name_or_path!r} (gesucht: {p})")
    return validate_customer(yaml.safe_load(p.read_text(encoding="utf-8")) or {})


# ---------------------------------------------------------------------------
# Kalender- und Rechenhelfer (rein, getestet)
# ---------------------------------------------------------------------------
def iso_week(d: date) -> str:
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def week_bounds(today: date) -> tuple[date, date]:
    """Mo–So der ISO-Woche, in der `today` liegt."""
    end = today + timedelta(days=6 - today.weekday())
    return end - timedelta(days=6), end


def quarter(d: date) -> str:
    return f"{d.year}-Q{(d.month - 1) // 3 + 1}"


def quarter_start(today: date, years_back: int = 3) -> date:
    return date(today.year - years_back, ((today.month - 1) // 3) * 3 + 1, 1)


def ramp_takeoff(years: dict[int, int], frac: float = 0.15) -> int | None:
    """Erstes Jahr mit >= max(3, frac * Spitzenjahr) — Ramp-Regel von tech_query."""
    if not years:
        return None
    peak = max(years.values())
    for y in sorted(years):
        if years[y] >= max(3, frac * peak):
            return y
    return None


def delta_pct(this: float, median: float) -> int | None:
    return round(100 * (this - median) / median) if median else None


def panel_sources(per_src: dict[int, dict[str, int]], early: list[str], late: list[str]) -> set[int]:
    """Quellen, die in den fruehen UND den spaeten Quartalen geliefert haben."""
    return {sid for sid, qc in per_src.items()
            if any(qc.get(q) for q in early) and any(qc.get(q) for q in late)}


def clean_actor(n: str) -> str | None:
    n = str(n).strip()
    if not (2 < len(n) < 60):
        return None
    if any(ch in n for ch in "\"'’"):
        return None
    if n.isupper() and len(n.split()) >= 2:      # Bylines in Grossbuchstaben
        return None
    return n


def _tsq(terms: list[str]) -> tuple[str, list[str]]:
    return "(" + " || ".join("phraseto_tsquery('english', %s)" for _ in terms) + ")", list(terms)


def _json_list(v) -> list:
    if isinstance(v, str):
        try:
            v = json.loads(v)
        except Exception:
            return []
    return list(v or [])


# ---------------------------------------------------------------------------
# DB
# ---------------------------------------------------------------------------
def _cursor(timeout: str = "600s"):
    import psycopg2
    import psycopg2.extras
    from pipeline.config import DATABASE_URL
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(f"SET statement_timeout = '{timeout}'")
    return conn, cur


# ---------------------------------------------------------------------------
# Wochenblatt
# ---------------------------------------------------------------------------
def measure_week(fields: list[dict], today: date | None = None) -> dict:
    today = today or date.today()
    wk_start, wk_end = week_bounds(today)
    weeks = [iso_week(wk_start - timedelta(weeks=i)) for i in range(7, -1, -1)]
    since_weeks = wk_start - timedelta(weeks=7)
    q_since = quarter_start(today)
    conn, cur = _cursor()
    try:
        # Nenner je Ebene und Quartal, Quellenpanel
        cur.execute(f"""SELECT s.id AS sid, {TIER_SQL} AS tier, to_char(t.sort_date,'YYYY-"Q"Q') AS q, count(*) AS n
            FROM trends t JOIN raw_entries r ON r.id=t.raw_entry_id JOIN sources s ON s.id=r.source_id
            WHERE t.sort_date >= %s AND t.sort_date <= %s GROUP BY 1,2,3""", (q_since, wk_end))
        per_src: dict[str, dict[int, dict[str, int]]] = defaultdict(lambda: defaultdict(dict))
        denom: dict[str, dict[str, int]] = defaultdict(dict)
        for r in cur.fetchall():
            if not r["tier"]:
                continue
            per_src[r["tier"]][r["sid"]][r["q"]] = r["n"]
            denom[r["tier"]][r["q"]] = denom[r["tier"]].get(r["q"], 0) + r["n"]
        qs = sorted({q for t in denom for q in denom[t]} | {quarter(q_since), quarter(wk_end)})
        qs = [q for q in qs if q >= quarter(q_since)][-12:]
        early, late = qs[:4], qs[-4:]
        panel = {t: panel_sources(per_src[t], early, late) for t in per_src}
        pdenom: dict[str, dict[str, int]] = defaultdict(dict)
        for t, sids in panel.items():
            for sid in sids:
                for q, n in per_src[t][sid].items():
                    pdenom[t][q] = pdenom[t].get(q, 0) + n
        cur.execute("""SELECT to_char(published,'YYYY-"Q"Q') q, count(*) n FROM patent_search WHERE published >= %s GROUP BY 1""", (q_since,))
        for r in cur.fetchall():
            denom["patent"][r["q"]] = r["n"]
            pdenom["patent"][r["q"]] = r["n"]
        out = {"week": iso_week(wk_start), "week_start": wk_start.isoformat(), "week_end": wk_end.isoformat(),
               "measured_on": today.isoformat(), "weeks": weeks, "quarters": qs,
               "panel_size": {t: len(panel.get(t, ())) for t in TIERS if t != "patent"}, "fields": []}
        for f in fields:
            out["fields"].append(_measure_field_week(cur, f, wk_start, wk_end, since_weeks, q_since, weeks, qs, panel, pdenom))
    finally:
        conn.close()
    return out


def _measure_field_week(cur, f, wk_start, wk_end, since_weeks, q_since, weeks, qs, panel, pdenom) -> dict:
    q, params = _tsq(f["terms"])
    cur.execute(f"""SELECT t.id, t.sort_date::date AS d, t.title_en, t.source_url, s.name AS source_name, s.id AS sid,
               t.status, t.brands, t.companies, {TIER_SQL} AS tier
        FROM trends t JOIN raw_entries r ON r.id=t.raw_entry_id JOIN sources s ON s.id=r.source_id
        WHERE {FTS} @@ {q} AND t.sort_date >= %s AND t.sort_date <= %s ORDER BY t.sort_date DESC""",
                params + [q_since, wk_end])
    rows = [dict(r) for r in cur.fetchall() if r["tier"] and r["tier"] != "patent"]
    pq, pparams = _tsq(f["terms"])
    cur.execute(f"""SELECT ps.pub_number, ps.published AS d, coalesce(r.title, ps.pub_number) AS title, r.url
        FROM patent_search ps LEFT JOIN raw_entries r ON r.pub_number = ps.pub_number
        WHERE ps.tsv @@ {pq} AND ps.published >= %s AND ps.published <= %s ORDER BY ps.published DESC""",
                pparams + [q_since, wk_end])
    prows = cur.fetchall()
    for r in prows:
        rows.append({"id": r["pub_number"], "d": r["d"], "title_en": r["title"], "sid": -1, "status": "signal",
                     "source_url": r["url"] or "https://patents.google.com/patent/" + r["pub_number"].replace("-", ""),
                     "source_name": PATENT_SOURCE, "brands": [], "companies": [], "tier": "patent"})
    wk = {t: Counter() for t in TIERS}
    qc = {t: Counter() for t in TIERS}
    pqc = {t: Counter() for t in TIERS}
    for r in rows:
        if r["d"] >= since_weeks:
            wk[r["tier"]][iso_week(r["d"])] += 1
        qc[r["tier"]][quarter(r["d"])] += 1
        if r["tier"] == "patent" or r["sid"] in panel.get(r["tier"], set()):
            pqc[r["tier"]][quarter(r["d"])] += 1
    weekly = {t: [wk[t].get(w, 0) for w in weeks] for t in TIERS}
    week = {}
    for t in TIERS:
        this, prior = weekly[t][-1], weekly[t][-5:-1]
        med = statistics.median(prior)
        week[t] = {"n": this, "median4": med, "delta_pct": delta_pct(this, med)}
    quarterly = {t: [{"q": qq, "n": qc[t].get(qq, 0), "panel_n": pqc[t].get(qq, 0),
                      "per10k": (round(10000 * pqc[t].get(qq, 0) / pdenom[t][qq], 1)
                                 if pdenom.get(t, {}).get(qq, 0) >= 30 else None)}
                     for qq in qs] for t in TIERS}
    week_rows = [r for r in rows if wk_start <= r["d"] <= wk_end]
    top = {t: [{"title": r["title_en"], "source": r["source_name"], "url": r["source_url"],
                "date": r["d"].isoformat(), "status": r["status"]}
               for r in week_rows if r["tier"] == t][:5] for t in TIERS}
    d90 = wk_end - timedelta(days=90)
    before, this_week = Counter(), Counter()
    for r in rows:
        if r["tier"] not in ("market", "funding") or r["d"] < d90:
            continue
        names = {clean_actor(n) for col in ("brands", "companies") for n in _json_list(r[col])}
        for n in names - {None}:
            (this_week if r["d"] >= wk_start else before)[n] += 1
    actors = [{"name": n, "n90": before[n] + this_week[n], "week": this_week[n], "new": n not in before}
              for n in (before + this_week)]
    actors.sort(key=lambda a: (-a["week"], -a["n90"], a["name"]))
    src = Counter(r["source_name"] for r in rows if r["d"] >= d90 and r["tier"] != "patent")
    n90 = sum(src.values())
    pat = "|".join(re.escape(t) for t in f["terms"])
    cur.execute("""SELECT n.id, r.scope, coalesce(n.llm_label, n.label) AS label, n.size, n.cohesion, n.n_sources,
               n.top_source, n.top_source_share, n.first_month, n.age_months, n.novelty_lift, n.accel,
               n.tier_order, n.science_to_market_months, n.rep_titles, r.created_at::date AS run_date
        FROM emerging_nests n JOIN emerging_runs r ON r.id=n.run_id
        WHERE r.id IN (SELECT max(id) FROM emerging_runs GROUP BY scope)
          AND (coalesce(n.llm_label,'')||' '||coalesce(n.label,'')||' '||coalesce(n.rep_titles,'')) ~* %s
        ORDER BY n.novelty_lift DESC NULLS LAST LIMIT 6""", (pat,))
    nests = []
    for r in cur.fetchall():
        n = dict(r)
        n["rep_titles"] = [str(x) for x in _json_list(n.get("rep_titles"))][:3]
        n["tier_order"] = [str(x) for x in _json_list(n.get("tier_order"))]
        n["run_date"] = str(n["run_date"])
        nests.append(n)
    return {"name": f["name"], "slug": f["slug"], "terms": f["terms"], "cpc": f.get("cpc") or [],
            "week": week, "weekly": weekly, "quarterly": quarterly, "top": top,
            "actors": actors[:12], "actors_total": len(actors),
            "actors_new_week": sum(1 for a in actors if a["new"] and a["week"]),
            "sources_90d": len(src), "signals_90d": n90, "patents_window": len(prows),
            "top_source": ([src.most_common(1)[0][0], round(100 * src.most_common(1)[0][1] / n90)] if n90 else None),
            "nests": nests}


# ---------------------------------------------------------------------------
# Trajectory Sheet
# ---------------------------------------------------------------------------
def quant_block(codes: list[str]) -> dict | None:
    """Reifegrad aus dem Patentgraph fuer die CPC-Anker: K(t) (scripts.tir_trajectory,
    SPNP-Methode), Zykluszeit, Zentralitaets-Peak. Kein Embedding, keine GPU."""
    if not codes:
        return None
    from scripts.tir_trajectory import TRUNC_YEARS, YEAR_HI, trajectory
    traj = trajectory([c + "%" for c in codes])
    pts = traj.get("points") or []
    settled = [(int(y), float(v[0]), int(v[1])) for y, v in (traj.get("x_by_year") or {}).items()
               if int(v[1]) >= 100 and int(y) <= YEAR_HI - TRUNC_YEARS]
    peak = None
    if settled:
        y, x, n = max(settled, key=lambda p: p[1])
        later = [p[1] for p in settled if p[0] > y]
        peak = {"year": y, "percentile": round(x, 3), "n": n, "from": min(p[0] for p in settled),
                "to": max(p[0] for p in settled), "falling": bool(later and max(later) < x)}
    return {"codes": codes, "n_patents": traj.get("n_total"), "K_median": traj.get("K_median"),
            "K_latest": traj.get("K_latest"), "calibrated": bool(traj.get("calibrated")),
            "direction": traj.get("direction"), "K_by_year": pts,
            "earliest_year": traj.get("earliest_year"), "cycle_time": cycle_time(codes),
            "centrality_peak": peak}


def cycle_time(codes: list[str], since: str = "2015-01-01") -> dict:
    """Median-Alter der rueckwaerts zitierten Patente (Singh/Triulzi/Magee).
    Zu wenige Kanten (< 200) -> nicht berichtet, nie geraten."""
    like = " OR ".join("pc.cpc LIKE %s" for _ in codes)
    sql = ("WITH dom AS (SELECT DISTINCT pc.pub_number FROM patent_cpc pc WHERE (" + like + ")), "
           "src AS (SELECT d.pub_number, r.published_date FROM dom d JOIN raw_entries r ON r.pub_number = d.pub_number "
           "        WHERE r.published_date >= %s), "
           "ages AS (SELECT EXTRACT(year FROM s.published_date) - EXTRACT(year FROM r2.published_date) AS age "
           "         FROM src s JOIN patent_links l ON l.src_pub = s.pub_number AND l.link_type = 'cites' "
           "         JOIN raw_entries r2 ON r2.pub_number = l.dst_pub WHERE r2.published_date IS NOT NULL) "
           "SELECT count(*) AS n, percentile_cont(0.5) WITHIN GROUP (ORDER BY age) AS med FROM ages WHERE age BETWEEN 0 AND 60")
    conn, cur = _cursor("120s")
    try:
        cur.execute(sql, tuple(c + "%" for c in codes) + (since,))
        r = cur.fetchone()
        n, med = int(r["n"] or 0), r["med"]
    except Exception as exc:  # noqa: BLE001
        logger.warning("cycle time not measured for %r: %r", codes, exc)
        return {"years": None, "edges": 0, "reason": f"not measured ({type(exc).__name__})"}
    finally:
        conn.close()
    if n < 200:
        return {"years": None, "edges": n, "reason": f"nur {n} datierte Zitationskanten"}
    return {"years": round(float(med), 1), "edges": n, "reason": None, "since": since[:4]}


def measure_sheet(field: dict, today: date | None = None) -> dict:
    today = today or date.today()
    terms = field["terms"]
    q, params = _tsq(terms)
    conn, cur = _cursor("900s")
    try:
        cur.execute(f"""SELECT {TIER_SQL} AS tier, extract(year FROM t.sort_date)::int AS y, count(*) AS n
            FROM trends t JOIN raw_entries r ON r.id=t.raw_entry_id JOIN sources s ON s.id=r.source_id
            WHERE t.sort_date >= '1990-01-01' AND r.pub_number IS NULL GROUP BY 1,2""")
        denom: dict[str, dict[int, int]] = defaultdict(dict)
        for r in cur.fetchall():
            if r["tier"]:
                denom[r["tier"]][r["y"]] = r["n"]
        cur.execute(f"""SELECT {TIER_SQL} AS tier, extract(year FROM t.sort_date)::int AS y, count(*) AS n
            FROM trends t JOIN raw_entries r ON r.id=t.raw_entry_id JOIN sources s ON s.id=r.source_id
            WHERE {FTS} @@ {q} AND t.sort_date >= '1990-01-01' AND r.pub_number IS NULL GROUP BY 1,2""", params)
        yearly: dict[str, dict[int, int]] = {t: {} for t in TIERS}
        for r in cur.fetchall():
            if r["tier"] in ("funding", "market"):
                yearly[r["tier"]][r["y"]] = r["n"]
        cur.execute("SELECT extract(year FROM published)::int y, count(*) n FROM patent_search WHERE published >= '1990-01-01' GROUP BY 1")
        for r in cur.fetchall():
            denom["patent"][r["y"]] = r["n"]
        cur.execute(f"SELECT extract(year FROM published)::int y, count(*) n FROM patent_search WHERE tsv @@ {q} AND published >= '1990-01-01' GROUP BY 1", params)
        for r in cur.fetchall():
            yearly["patent"][r["y"]] = r["n"]
        cur.execute("SELECT year, sum(n)::int n FROM research_topic_years GROUP BY 1")
        denom["science"] = {r["year"]: r["n"] for r in cur.fetchall()}
        cur.execute(f"SELECT year, count(*) n FROM research_corpus WHERE tsv @@ {q} AND year >= 1990 GROUP BY 1", params)
        for r in cur.fetchall():
            yearly["science"][r["year"]] = r["n"]
        # Zitationen/FWCI aus research_work_state (jüngster OpenAlex-Stand, Sync v2 seit 05.10.2026),
        # sonst der Stand beim Einlesen; zurückgezogene Werke nie als „meistzitiert".
        cur.execute(f"""SELECT rc.id, rc.doi, rc.title, rc.year, rc.type,
                               COALESCE(ws.cited_by_count, rc.cited_by_count) AS cited_by_count,
                               COALESCE(ws.fwci, rc.fwci) AS fwci
                        FROM research_corpus rc LEFT JOIN research_work_state ws ON ws.id = rc.id
                        WHERE rc.tsv @@ {q} AND rc.year >= %s AND NOT COALESCE(rc.is_retracted, FALSE)
                        ORDER BY 6 DESC NULLS LAST LIMIT 6""", params + [today.year - 8])
        from pipeline.openalex_sync import strip_markup
        top_works = [dict(r, title=strip_markup(r["title"])) for r in cur.fetchall()]
        years = list(range(1990, today.year + 1))
        series = {t: [{"y": y, "n": yearly[t].get(y, 0),
                       "per10k": (round(10000 * yearly[t].get(y, 0) / denom[t][y], 1)
                                  if denom.get(t, {}).get(y, 0) >= 30 and not (t == "science" and y == today.year) else None)}
                      for y in years] for t in TIERS}
        cur.execute(f"SELECT pub_number FROM patent_search WHERE tsv @@ {q} AND published >= %s", params + [date(today.year - 5, 1, 1)])
        pubs = [r["pub_number"] for r in cur.fetchall()]
        cur.execute("""SELECT upper(regexp_replace(a.name, '[,.]', '', 'g')) AS name, count(DISTINCT a.pub_number) n
                       FROM patent_assignee_raw a WHERE a.pub_number = ANY(%s) GROUP BY 1 ORDER BY 2 DESC LIMIT 15""", (pubs,))
        assignees = [dict(r) for r in cur.fetchall()]
        cur.execute("SELECT count(DISTINCT pub_number) n FROM patent_assignee_raw WHERE pub_number = ANY(%s)", (pubs,))
        with_assignee = cur.fetchone()["n"]
        cur.execute("SELECT left(cpc, 4) AS sub, count(DISTINCT pub_number) n FROM patent_cpc_full WHERE pub_number = ANY(%s) GROUP BY 1 ORDER BY 2 DESC LIMIT 8", (pubs,))
        subclasses = [dict(r) for r in cur.fetchall()]
        cur.execute("SELECT symbol, title FROM cpc_definitions WHERE symbol = ANY(%s)", ([s["sub"] for s in subclasses],))
        titles = {r["symbol"]: r["title"] for r in cur.fetchall()}
        for s_ in subclasses:
            s_["title"] = titles.get(s_["sub"]) or CPC_SECTION_TITLES.get(s_["sub"], "")
        cur.execute(f"""WITH m AS (SELECT pub_number, published FROM patent_search WHERE tsv @@ {q})
            SELECT m.pub_number, m.published, count(l.src_pub) AS cited_by, r.title, r.url
            FROM m LEFT JOIN patent_links l ON l.dst_pub = m.pub_number LEFT JOIN raw_entries r ON r.pub_number = m.pub_number
            GROUP BY 1,2,4,5 HAVING r.title ILIKE ANY(%s) ORDER BY 3 DESC LIMIT 8""", params + [[f"%{t}%" for t in terms]])
        landmarks = [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()
    offices = Counter(p.split("-")[0] for p in pubs)
    return {"field": field, "measured_on": today.isoformat(), "series": series,
            "takeoff": {t: ramp_takeoff(yearly[t]) for t in TIERS},
            "first": {t: (min(yearly[t]) if yearly[t] else None) for t in TIERS},
            "totals": {t: sum(yearly[t].values()) for t in TIERS},
            "science_from": 2010, "market_from": 2020,
            "patents_5y": len(pubs), "patents_with_assignee_5y": with_assignee, "assignees": assignees,
            "subclasses": subclasses, "landmarks": landmarks, "offices": offices.most_common(6),
            "top_works": top_works, "quant": quant_block(field.get("cpc") or [])}


# ---------------------------------------------------------------------------
# Feldprobe
# ---------------------------------------------------------------------------
def probe(phrase: str, terms: list[str] | None = None, cpc: list[str] | None = None,
          today: date | None = None) -> dict:
    """Seite 1 des Sheets fuer eine Phrase. Ohne `cpc` fragt die Technologie-
    Suche nach Kandidatenklassen (GPU-Handover fuer den Query-Vektor); die
    Vorschlaege stehen im Ergebnis, damit der Owner den Anker waehlt."""
    terms = terms or [phrase]
    candidates: list[dict] = []
    gate = None
    if not cpc:
        from scripts.tech_analyze import analyze_query
        res = analyze_query(phrase)
        gate = (res.get("gate") or {}).get("verdict")
        candidates = [{"symbol": c["symbol"], "title": c.get("title"), "n": c.get("n"), "default": c.get("default")}
                      for c in (res.get("candidates") or [])]
        cpc = [c["symbol"] for c in candidates if c.get("default")] if gate == "ok" else []
    field = {"name": phrase, "name_en": phrase, "slug": slugify(phrase), "terms": terms, "cpc": cpc, "reading": ""}
    sheet = measure_sheet(field, today)
    sheet["probe"] = {"phrase": phrase, "gate": gate, "candidates": candidates, "anchor_used": cpc}
    return sheet


# ---------------------------------------------------------------------------
# Laufprotokoll
# ---------------------------------------------------------------------------
def save_run(customer_slug: str, kind: str, week: str | None, field_slug: str | None,
             payload: dict, pdf_path: str | None) -> int | None:
    """Eine Zeile je erzeugtem Blatt in field_watch_runs (additiv, pipeline/db.py)."""
    try:
        conn, cur = _cursor("30s")
    except Exception as exc:  # noqa: BLE001
        logger.warning("field_watch_runs: keine DB (%r)", exc)
        return None
    try:
        cur.execute("""INSERT INTO field_watch_runs (customer, kind, week, field_slug, payload, pdf_path)
                       VALUES (%s, %s, %s, %s, %s::jsonb, %s) RETURNING id""",
                    (customer_slug, kind, week, field_slug, json.dumps(payload, default=str), pdf_path))
        rid = cur.fetchone()["id"]
        conn.commit()
        return int(rid)
    except Exception as exc:  # noqa: BLE001
        logger.warning("field_watch_runs: nicht geschrieben (%r)", exc)
        return None
    finally:
        conn.close()
