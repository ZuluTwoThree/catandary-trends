"""Technology Trajectory Sheet — Messdaten je Feld (SQL, kein Modell).
Usage: sheet.py field.json quant.json out.json"""
import json, sys
from collections import Counter, defaultdict
from datetime import date
import psycopg2, psycopg2.extras
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from measure_field import TIER_SQL, FTS, TIERS

def ramp_takeoff(years: Counter, frac=0.15):
    if not years: return None
    peak = max(years.values())
    for y in sorted(years):
        if years[y] >= max(3, frac * peak): return y
    return None

def main(field_path, quant_path, out_path):
    f = json.load(open(field_path)); quant = json.load(open(quant_path))
    terms = f["terms"]
    conn = psycopg2.connect("dbname=catandary")
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SET statement_timeout = '900s'")
    q = "(" + " || ".join("phraseto_tsquery('english', %s)" for _ in terms) + ")"
    # Jahresreihe je Ebene (Wissenschaft/Förderung/Markt) aus trends, Nenner je Ebene und Jahr
    cur.execute(f"""SELECT {TIER_SQL} AS tier, extract(year FROM t.sort_date)::int AS y, count(*) AS n
        FROM trends t JOIN raw_entries r ON r.id=t.raw_entry_id JOIN sources s ON s.id=r.source_id
        WHERE t.sort_date >= '1990-01-01' AND r.pub_number IS NULL GROUP BY 1,2""")
    denom = defaultdict(dict)
    for r in cur.fetchall():
        if r["tier"]: denom[r["tier"]][r["y"]] = r["n"]
    cur.execute(f"""SELECT {TIER_SQL} AS tier, extract(year FROM t.sort_date)::int AS y, count(*) AS n
        FROM trends t JOIN raw_entries r ON r.id=t.raw_entry_id JOIN sources s ON s.id=r.source_id
        WHERE {FTS} @@ {q} AND t.sort_date >= '1990-01-01' AND r.pub_number IS NULL GROUP BY 1,2""", terms)
    yearly = {t: Counter() for t in TIERS}
    for r in cur.fetchall():
        if r["tier"] and r["tier"] != "patent": yearly[r["tier"]][r["y"]] = r["n"]
    # Patente je Jahr aus patent_search, Nenner aus patent_search
    cur.execute("SELECT extract(year FROM published)::int y, count(*) n FROM patent_search WHERE published >= '1990-01-01' GROUP BY 1")
    for r in cur.fetchall(): denom["patent"][r["y"]] = r["n"]
    cur.execute(f"SELECT extract(year FROM published)::int y, count(*) n FROM patent_search WHERE tsv @@ {q} AND published >= '1990-01-01' GROUP BY 1", terms)
    for r in cur.fetchall(): yearly["patent"][r["y"]] = r["n"]
    # Wissenschaft aus dem Forschungskorpus (OpenAlex-Auszug, 45,5 M Werke, 2010+), Nenner je Jahr
    cur.execute("SELECT year, sum(n)::int n FROM research_topic_years GROUP BY 1")
    denom["science"] = {r["year"]: r["n"] for r in cur.fetchall()}
    cur.execute(f"SELECT year, count(*) n FROM research_corpus WHERE tsv @@ {q} AND year >= 1990 GROUP BY 1", terms)
    yearly["science"] = Counter({r["year"]: r["n"] for r in cur.fetchall()})
    cur.execute(f"""SELECT id, doi, title, year, type, cited_by_count, fwci FROM research_corpus WHERE tsv @@ {q} AND year >= 2018
                    ORDER BY cited_by_count DESC NULLS LAST LIMIT 6""", terms)
    top_works = [dict(r) for r in cur.fetchall()]
    cur.execute(f"""SELECT type, count(*) n FROM research_corpus WHERE tsv @@ {q} AND year >= 2021 GROUP BY 1 ORDER BY 2 DESC""", terms)
    work_types = [dict(r) for r in cur.fetchall()]
    years = list(range(1990, date.today().year + 1))
    series = {t: [{"y": y, "n": yearly[t].get(y, 0),
                   "per10k": round(10000 * yearly[t].get(y, 0) / denom[t][y], 1) if denom.get(t, {}).get(y, 0) >= 30 else None}
                  for y in years] for t in TIERS}
    takeoff = {t: ramp_takeoff(yearly[t]) for t in TIERS}
    first = {t: (min(yearly[t]) if yearly[t] else None) for t in TIERS}
    totals = {t: sum(yearly[t].values()) for t in TIERS}
    # Patente: Treffer der letzten 5 Jahre → Anmelder, CPC-Subklassen, meistzitierte
    cur.execute(f"""SELECT pub_number, published FROM patent_search WHERE tsv @@ {q} AND published >= '2021-01-01'""", terms)
    pubs = {r["pub_number"]: r["published"] for r in cur.fetchall()}
    pl = list(pubs)
    cur.execute("SELECT upper(regexp_replace(a.name, '[,.]', '', 'g')) AS name, count(DISTINCT a.pub_number) n FROM patent_assignee_raw a WHERE a.pub_number = ANY(%s) GROUP BY 1 ORDER BY 2 DESC LIMIT 15", (pl,))
    assignees = [dict(r) for r in cur.fetchall()]
    cur.execute("SELECT count(DISTINCT pub_number) n FROM patent_assignee_raw WHERE pub_number = ANY(%s)", (pl,))
    with_assignee = cur.fetchone()["n"]
    cur.execute("""SELECT left(cpc, 4) AS sub, count(DISTINCT pub_number) n FROM patent_cpc_full WHERE pub_number = ANY(%s) GROUP BY 1 ORDER BY 2 DESC LIMIT 8""", (pl,))
    subclasses = [dict(r) for r in cur.fetchall()]
    cur.execute("SELECT symbol, title FROM cpc_definitions WHERE symbol = ANY(%s)", ([s["sub"] for s in subclasses],))
    titles = {r["symbol"]: r["title"] for r in cur.fetchall()}
    for s in subclasses: s["title"] = titles.get(s["sub"], "")
    # Meistzitierte Patente des Feldes (alle Jahre): Zitationen INNERHALB des Korpus
    cur.execute(f"""WITH m AS (SELECT pub_number, published FROM patent_search WHERE tsv @@ {q})
        SELECT m.pub_number, m.published, count(l.src_pub) AS cited_by, r.title, r.url
        FROM m LEFT JOIN patent_links l ON l.dst_pub = m.pub_number LEFT JOIN raw_entries r ON r.pub_number = m.pub_number
        GROUP BY 1,2,4,5 HAVING r.title ILIKE ANY(%s) ORDER BY 3 DESC LIMIT 8""", terms + [[f"%{t}%" for t in terms]])
    landmarks = [dict(r) for r in cur.fetchall()]
    # Länder der Anmeldungen (aus dem Präfix der Publikationsnummer), letzte 5 Jahre
    offices = Counter(p.split("-")[0] for p in pl)
    out = {"field": f, "measured_on": date.today().isoformat(), "series": series, "takeoff": takeoff, "first": first,
           "totals": totals, "patents_5y": len(pl), "patents_with_assignee_5y": with_assignee, "assignees": assignees,
           "subclasses": subclasses, "landmarks": landmarks, "offices": offices.most_common(6),
           "quant": quant["quant"]["summary"], "top_works": top_works, "work_types": work_types, "quant_note": quant["quant"]["note"]}
    json.dump(out, open(out_path, "w"), default=str, indent=1, ensure_ascii=False)
    print("totals", totals, "takeoff", takeoff, "first", first, "patents5y", len(pl), "assignee-cov", with_assignee)
    print("assignees", [(a["name"], a["n"]) for a in assignees[:8]])
    print("subclasses", [(s["sub"], s["n"]) for s in subclasses])
    print("landmarks", [(l["pub_number"], l["cited_by"], (l["title"] or "")[:50]) for l in landmarks[:5]])
    print("offices", offices.most_common(6))

if __name__ == "__main__":
    main(*sys.argv[1:])
