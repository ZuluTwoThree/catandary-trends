"""Field Watch — Wochenmessung je Kundenfeld, rein SQL (kein Modell).
Usage: fieldwatch.py fields.json out.json [ISO-week-end YYYY-MM-DD]"""
import json, sys, statistics, re
from collections import Counter, defaultdict
from datetime import date, timedelta
import psycopg2, psycopg2.extras

TIER_SQL = """CASE
  WHEN lower(s.name) LIKE 'google patents%%' OR lower(s.name) LIKE 'epo %%' THEN 'patent'
  WHEN lower(s.name) ~ '^(nih reporter|nsf |openaire|ukri|sec form d|sbir)' OR lower(s.name) LIKE 'cordis%%' THEN 'funding'
  WHEN s.source_type='research' OR lower(s.name) LIKE '%%preprints%%' OR lower(s.name) LIKE 'openalex%%' THEN 'science'
  WHEN s.source_type IN ('trade_media','press_wire','brand') THEN CASE WHEN t.trend_signal_type='funding' THEN 'funding' ELSE 'market' END
  END"""
FTS = "to_tsvector('english', coalesce(t.title_en,'')||' '||coalesce(t.summary_en,'')||' '||coalesce(t.tags::text,''))"
TIERS = ("science", "patent", "funding", "market")

def tsq(terms):
    return "(" + " || ".join("phraseto_tsquery('english', %s)" for _ in terms) + ")", list(terms)

def iso_week(d):
    y, w, _ = d.isocalendar(); return f"{y}-W{w:02d}"

def quarter(d):
    return f"{d.year}-Q{(d.month-1)//3+1}"

def main(fields_path, out_path, week_end=None):
    fields = json.load(open(fields_path))
    today = date.fromisoformat(week_end) if week_end else date.today()
    # letzte abgeschlossene ISO-Woche = die Woche, in der week_end liegt
    wk_end = today + timedelta(days=6 - today.weekday())
    wk_start = wk_end - timedelta(days=6)
    weeks = [iso_week(wk_start - timedelta(weeks=i)) for i in range(7, -1, -1)]
    since_weeks = wk_start - timedelta(weeks=7)
    q_since = date(today.year - 3, ((today.month-1)//3)*3 + 1, 1)
    conn = psycopg2.connect("dbname=catandary")
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SET statement_timeout = '600s'")
    # Nenner je Ebene und Quartal (Anteilsnormierung)
    cur.execute(f"""SELECT {TIER_SQL} AS tier, to_char(t.sort_date,'YYYY-"Q"Q') AS q, count(*) AS n
        FROM trends t JOIN raw_entries r ON r.id=t.raw_entry_id JOIN sources s ON s.id=r.source_id
        WHERE t.sort_date >= %s GROUP BY 1,2""", (q_since,))
    denom = defaultdict(dict)
    for r in cur.fetchall():
        if r["tier"]: denom[r["tier"]][r["q"]] = r["n"]
    # Festes Quellenpanel: Quellen, die in den ersten UND letzten vier Quartalen des Fensters geliefert haben
    q_all = sorted({q for t in denom for q in denom[t]})
    q_all = [q for q in q_all if q >= quarter(q_since)][-12:]
    early, late = q_all[:4], q_all[-4:]
    cur.execute(f"""WITH x AS (SELECT s.id AS sid, {TIER_SQL} AS tier, to_char(t.sort_date,'YYYY-"Q"Q') AS q, count(*) AS n
        FROM trends t JOIN raw_entries r ON r.id=t.raw_entry_id JOIN sources s ON s.id=r.source_id
        WHERE t.sort_date >= %s GROUP BY 1,2,3)
        SELECT sid, tier, q, n FROM x WHERE tier IS NOT NULL""", (q_since,))
    per_src = defaultdict(lambda: defaultdict(Counter))
    for r in cur.fetchall(): per_src[r["tier"]][r["sid"]][r["q"]] += r["n"]
    panel = {}
    pdenom = defaultdict(dict)
    for t in per_src:
        panel[t] = {sid for sid, qc in per_src[t].items() if any(qc.get(q) for q in early) and any(qc.get(q) for q in late)}
        for sid in panel[t]:
            for q, n in per_src[t][sid].items(): pdenom[t][q] = pdenom[t].get(q, 0) + n
    # Patente aus patent_search (Volltext-Index), Nenner je Quartal
    cur.execute("""SELECT to_char(published,'YYYY-"Q"Q') q, count(*) n FROM patent_search WHERE published >= %s GROUP BY 1""", (q_since,))
    for r in cur.fetchall(): denom["patent"][r["q"]] = r["n"]; pdenom["patent"][r["q"]] = r["n"]
    cur.execute(f"""SELECT {TIER_SQL} AS tier, count(*) AS n
        FROM trends t JOIN raw_entries r ON r.id=t.raw_entry_id JOIN sources s ON s.id=r.source_id
        WHERE t.sort_date >= %s AND t.sort_date <= %s GROUP BY 1""", (since_weeks, wk_end))
    denom_weeks = {r["tier"]: r["n"] for r in cur.fetchall() if r["tier"]}
    out = {"week": iso_week(wk_start), "week_start": wk_start.isoformat(), "week_end": wk_end.isoformat(),
           "measured_on": today.isoformat(), "weeks": weeks, "fields": []}
    for f in fields:
        q, params = tsq(f["terms"])
        cur.execute(f"""SELECT t.id, t.sort_date::date AS d, t.title_en, t.summary_en, t.source_url, s.name AS source_name, s.id AS sid,
                   t.status, t.brands, t.companies, t.primary_vertical, t.mega_trend, t.regions, {TIER_SQL} AS tier
            FROM trends t JOIN raw_entries r ON r.id=t.raw_entry_id JOIN sources s ON s.id=r.source_id
            WHERE {FTS} @@ {q} AND t.sort_date >= %s AND t.sort_date <= %s ORDER BY t.sort_date DESC""",
            params + [q_since, wk_end])
        rows = [r for r in cur.fetchall() if r["tier"] and r["tier"] != "patent"]
        # Patente: eigener Index (patent_search.tsv), Titel+Abstract
        pq = " || ".join("phraseto_tsquery('english', %s)" for _ in f["terms"])
        cur.execute(f"""SELECT ps.pub_number, ps.published AS d, coalesce(r.title, ps.pub_number) AS title, r.url FROM patent_search ps LEFT JOIN raw_entries r ON r.pub_number = ps.pub_number WHERE ps.tsv @@ ({pq}) AND ps.published >= %s AND ps.published <= %s ORDER BY ps.published DESC""",
                    list(f["terms"]) + [q_since, wk_end])
        prows = cur.fetchall()
        for r in prows:
            rows.append({"id": r["pub_number"], "d": r["d"], "title_en": r["title"], "summary_en": "", "source_url": r["url"] or ("https://patents.google.com/patent/" + r["pub_number"].replace("-", "")),
                         "source_name": "Patentamt (EPO/USPTO/WIPO via BDDS)", "sid": -1, "status": "signal", "brands": [], "companies": [], "tier": "patent"})
        # Wochen
        wk = {t: Counter() for t in TIERS}
        for r in rows:
            if r["d"] >= since_weeks: wk[r["tier"]][iso_week(r["d"])] += 1
        weekly = {t: [wk[t].get(w, 0) for w in weeks] for t in TIERS}
        this = {t: weekly[t][-1] for t in TIERS}
        prior = {t: weekly[t][-5:-1] for t in TIERS}
        med = {t: statistics.median(prior[t]) for t in TIERS}
        # Quartale (roh + je 10.000 der Ebene)
        qs = sorted({quarter(r["d"]) for r in rows} | {q for t in denom for q in denom[t]})
        qs = [q for q in qs if q >= quarter(q_since)][-12:]
        qc = {t: Counter() for t in TIERS}
        for r in rows: qc[r["tier"]][quarter(r["d"])] += 1
        pqc = {t: Counter() for t in TIERS}
        for r in rows:
            if r["tier"] == "patent" or r["sid"] in panel.get(r["tier"], set()): pqc[r["tier"]][quarter(r["d"])] += 1
        quarterly = {t: [{"q": q, "n": qc[t].get(q, 0),
                          "panel_n": pqc[t].get(q, 0),
                          "per10k": round(10000*pqc[t].get(q, 0)/pdenom[t][q], 1) if pdenom.get(t, {}).get(q, 0) >= 30 else None}
                         for q in qs] for t in TIERS}
        panel_size = {t: len(panel.get(t, ())) for t in TIERS if t != "patent"}
        # Signale der Woche je Ebene
        week_rows = [r for r in rows if wk_start <= r["d"] <= wk_end]
        top = {t: [{"title": r["title_en"], "source": r["source_name"], "url": r["source_url"], "date": r["d"].isoformat(),
                    "status": r["status"]} for r in week_rows if r["tier"] == t][:5] for t in TIERS}
        # Akteure (Untergrenze: extrahierte Marken/Firmen der Markt- und Förderebene, 90 Tage)
        d90 = wk_end - timedelta(days=90)
        seen_before, seen_week = Counter(), Counter()
        for r in rows:
            if r["tier"] not in ("market", "funding") or r["d"] < d90: continue
            names = set()
            for col in ("brands", "companies"):
                v = r[col]
                if isinstance(v, str):
                    try: v = json.loads(v)
                    except Exception: v = []
                for n in (v or []):
                    n = str(n).strip()
                    if 2 < len(n) < 60 and '"' not in n and "'" not in n and "’" not in n and not (n.isupper() and len(n.split()) >= 2): names.add(n)
            for n in names:
                (seen_week if r["d"] >= wk_start else seen_before)[n] += 1
        actors = [{"name": n, "n90": seen_before[n] + seen_week[n], "week": seen_week[n],
                   "new": n not in seen_before} for n in (seen_before + seen_week)]
        actors.sort(key=lambda a: (-a["week"], -a["n90"], a["name"]))
        # Quellenbreite
        src = Counter(r["source_name"] for r in rows if r["d"] >= d90 and r["tier"] != "patent")
        n90 = sum(src.values())
        # Nester (jüngster Lauf je Scope), Treffer über Label/Titel
        pat = "|".join(re.escape(t) for t in f["terms"])
        cur.execute("""SELECT n.id, n.run_id, r.scope, coalesce(n.llm_label, n.label) AS label, n.size, n.cohesion, n.n_sources,
                   n.top_source, n.top_source_share, n.first_month, n.age_months, n.novelty_lift, n.accel, n.new_terms, n.tier_order,
                   n.science_to_market_months, n.rep_titles
            FROM emerging_nests n JOIN emerging_runs r ON r.id=n.run_id
            WHERE r.id IN (SELECT max(id) FROM emerging_runs GROUP BY scope)
              AND (coalesce(n.llm_label,'')||' '||coalesce(n.label,'')||' '||coalesce(n.rep_titles,'')) ~* %s
            ORDER BY n.novelty_lift DESC NULLS LAST LIMIT 6""", (pat,))
        nests = [dict(r) for r in cur.fetchall()]
        for n in nests:
            for k in ("rep_titles", "tier_order"):
                v = n.get(k)
                if isinstance(v, str):
                    try: v = json.loads(v)
                    except Exception: v = [v]
                n[k] = list(v or [])
        out["fields"].append({
            "name": f["name"], "terms": f["terms"], "cpc": f.get("cpc"),
            "week": {t: {"n": this[t], "median4": med[t],
                         "delta_pct": (round(100*(this[t]-med[t])/med[t]) if med[t] else None)} for t in TIERS},
            "weekly": weekly, "quarterly": quarterly, "top": top,
            "actors": actors[:12], "actors_total": len(actors), "actors_new_week": sum(1 for a in actors if a["new"] and a["week"]),
            "sources_90d": len(src), "signals_90d": n90, "panel_size": panel_size,
            "patents_total_window": len(prows),
            "top_source": (src.most_common(1)[0][0], round(100*src.most_common(1)[0][1]/n90)) if n90 else None,
            "nests": nests,
        })
    json.dump(out, open(out_path, "w"), default=str, indent=1, ensure_ascii=False)
    for f in out["fields"]:
        print(f["name"], {t: f["week"][t]["n"] for t in TIERS}, "akteure", f["actors_total"], "nester", len(f["nests"]), "quellen90", f["sources_90d"])

if __name__ == "__main__":
    main(*sys.argv[1:])
