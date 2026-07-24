#!/usr/bin/env python3
"""Erst-Abgleich: Catandary-TIR (fullz3+cited, MIT-Zeitfenster 1976-2015) vs.
Singh/Triulzi/Magee 1757-Domänen-Prognosen, aggregiert auf IPC4/CPC4-Subklassen.

Schritt 1 (SQL, ein Pass): je (CPC4-Subklasse, is_us) mittlere cited_pctl und n
über alle Patente mit Grant-Jahr 1976-2015 (Dedupe pub_number je Subklasse).
Schritt 2: MIT-CSV → IPC4-Aggregation (größen-gewichtet, log-Raum).
Schritt 3: Join + Spearman/Pearson(ln) für Welt- und US-only-Variante.
"""
import csv, json, math, os, re, sys
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from dotenv import load_dotenv
load_dotenv("/home/dirk/projects/catandary-trends/.env")
import psycopg2

SCRATCH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "mit_benchmark")
os.makedirs(SCRATCH, exist_ok=True)
MIT_CSV = "/mnt/data-hdd/shared_tir_research/Technology_improvement_rates_for_all_technologies_Singh_Triulzi_Magee_May6.csv"
OUT_RAW = os.path.join(SCRATCH, "abgleich_sub_x.csv")
OUT_JSON = os.path.join(SCRATCH, "abgleich_result.json")
OUT_MATCH = os.path.join(SCRATCH, "abgleich_matched.csv")

# Aktive Prod-Kalibrierung (fullz3 + cited, tir_trajectory.py:77-80)
COEF_A, COEF_B, SIGMA2 = -5.5622, 5.5036, 0.4930
def k_from_x(x): return 100.0 * math.exp(COEF_A + COEF_B * x) * math.exp(SIGMA2 / 2)

MIN_N = 500  # Subklassen-Floor für stabile Mittelwerte

def step1_sql():
    if os.path.exists(OUT_RAW) and os.path.getsize(OUT_RAW) > 1000:
        print("step1: cached", flush=True); return
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("SET statement_timeout = 0")
    cur.execute("SET work_mem = '1GB'")
    print("step1: running aggregate query ...", flush=True)
    cur.execute("""
        SELECT sub, is_us, AVG(cited_pctl) AS x, COUNT(*) AS n FROM (
          SELECT DISTINCT left(pc.cpc, 4) AS sub,
                 (sp.pub_number LIKE 'US-%') AS is_us,
                 pc.pub_number, cs.cited_pctl
          FROM patent_spnp_full_z3 sp
          JOIN patent_citedspnp_full_z3 cs ON cs.pub_number = sp.pub_number
          JOIN patent_cpc_full pc ON pc.pub_number = sp.pub_number
          WHERE sp.year BETWEEN 1976 AND 2015
        ) d GROUP BY sub, is_us ORDER BY sub, is_us
    """)
    with open(OUT_RAW, "w", newline="") as f:
        w = csv.writer(f); w.writerow(["sub", "is_us", "x", "n"])
        for r in cur.fetchall():
            w.writerow([r[0], r[1], float(r[2]) if r[2] is not None else "", r[3]])
    print("step1: done", flush=True)

def spearman(a, b):
    def rank(v):
        s = sorted(range(len(v)), key=lambda i: v[i]); r = [0.0] * len(v); i = 0
        while i < len(s):
            j = i
            while j + 1 < len(s) and v[s[j + 1]] == v[s[i]]: j += 1
            avg = (i + j) / 2 + 1
            for t in range(i, j + 1): r[s[t]] = avg
            i = j + 1
        return r
    ra, rb = rank(a), rank(b)
    ma, mb = sum(ra) / len(ra), sum(rb) / len(rb)
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    da = math.sqrt(sum((x - ma) ** 2 for x in ra)); db = math.sqrt(sum((y - mb) ** 2 for y in rb))
    return num / (da * db)

def pearson(a, b):
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    da = math.sqrt(sum((x - ma) ** 2 for x in a)); db = math.sqrt(sum((y - mb) ** 2 for y in b))
    return num / (da * db)

def main():
    step1_sql()
    # MIT-Seite: IPC4-Aggregation, größen-gewichtet im Log-Raum
    mit = defaultdict(lambda: {"w": 0.0, "wlnk": 0.0, "wk": 0.0, "n_dom": 0, "size": 0})
    for r in csv.DictReader(open(MIT_CSV)):
        code = r["Domain Code (UPC-IPC)"].strip()
        m = re.match(r"^(\d+)([A-Z]\d{2}[A-Z])$", code)
        if not m:
            print("unparsed domain code:", code, flush=True); continue
        ipc4 = m.group(2)
        k = float(r["Predicted K (% per annum)"]); size = int(r["Domain Size"])
        d = mit[ipc4]
        d["w"] += size; d["wlnk"] += size * math.log(k); d["wk"] += size * k
        d["n_dom"] += 1; d["size"] += size
    mit_agg = {s: {"K_geo": math.exp(d["wlnk"] / d["w"]), "K_arith": d["wk"] / d["w"],
                   "n_dom": d["n_dom"], "size": d["size"]} for s, d in mit.items()}

    # Unsere Seite
    ours = defaultdict(dict)
    for r in csv.DictReader(open(OUT_RAW)):
        if not r["x"]: continue
        key = "us" if r["is_us"] in ("True", "t", "true") else "world"
        ours[r["sub"]][key] = (float(r["x"]), int(r["n"]))

    results = {}
    rows_out = []
    for variant in ("world", "us", "combined"):
        pairs = []
        for sub, magg in mit_agg.items():
            o = ours.get(sub, {})
            if variant == "combined":
                tot_n = sum(v[1] for v in o.values())
                if tot_n < MIN_N or not o: continue
                x = sum(v[0] * v[1] for v in o.values()) / tot_n
                n = tot_n
            else:
                if variant not in o or o[variant][1] < MIN_N: continue
                x, n = o[variant]
            k_ours = k_from_x(x)
            pairs.append((sub, magg["K_geo"], magg["K_arith"], k_ours, x, n, magg["n_dom"], magg["size"]))
        if len(pairs) < 10:
            results[variant] = {"n": len(pairs), "note": "zu wenige Matches"}; continue
        lk_mit = [math.log(p[1]) for p in pairs]
        lk_ours = [math.log(p[3]) for p in pairs]
        results[variant] = {
            "n_subclasses": len(pairs),
            "spearman": round(spearman(lk_mit, lk_ours), 4),
            "pearson_ln": round(pearson(lk_mit, lk_ours), 4),
            "mit_K_geo_median": round(sorted(p[1] for p in pairs)[len(pairs) // 2], 2),
            "ours_K_median": round(sorted(p[3] for p in pairs)[len(pairs) // 2], 2),
        }
        if variant == "combined":
            for p in pairs:
                rows_out.append(p)

    # Coverage-Statistik
    n_ipc4_mit = len(mit_agg)
    matched = {v: results[v].get("n_subclasses", 0) for v in results}
    summary = {"mit_domains": 1757, "mit_ipc4": n_ipc4_mit, "matched": matched,
               "min_n_floor": MIN_N, "results": results}
    json.dump(summary, open(OUT_JSON, "w"), indent=2)
    with open(OUT_MATCH, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ipc4", "mit_K_geo", "mit_K_arith", "ours_K", "ours_x", "ours_n", "mit_n_domains", "mit_size"])
        for p in sorted(rows_out, key=lambda p: -p[7]):
            w.writerow([p[0], round(p[1], 2), round(p[2], 2), round(p[3], 2), round(p[4], 4), p[5], p[6], p[7]])
    print(json.dumps(summary, indent=2), flush=True)

if __name__ == "__main__":
    main()
