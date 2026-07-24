#!/usr/bin/env python3
"""Surrogat-Qualität: CPC-Signaturen je MIT-Gold-Domäne (511k-Goldliste).

Je Domäne: CPC-Maingroup-Profil der Gold-Patente → greedy Signatur (F1-optimiert
auf Näherungsbasis) → EXAKTE Precision/Recall der finalen Signatur per SQL gegen
die Goldliste (Retrieval-Universum: US-Grants 1976-2015 im fullz3-Substrat).
Zusätzlich: X̄ (cited_pctl) über Gold-Set vs. über Signatur-Set — misst, wie stark
Signatur-Fehler den TIR-Prädiktor verzerren.
"""
import csv, json, math, os, sys
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from dotenv import load_dotenv
load_dotenv("/home/dirk/projects/catandary-trends/.env")
import psycopg2

SCRATCH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "mit_benchmark")
os.makedirs(SCRATCH, exist_ok=True)
GOLD = "/mnt/data-hdd/Domains_patent_info.csv"
OUT = os.path.join(SCRATCH, "com_signatures_result.json")

conn = psycopg2.connect(os.environ["DATABASE_URL"])
conn.autocommit = True
cur = conn.cursor()
cur.execute("SET statement_timeout = 0")
cur.execute("SET work_mem = '1GB'")

def log(m): print(m, flush=True)

# --- 1. US-Grant-Universum 1976-2015 (einmalig, unlogged) ---------------------
cur.execute("SELECT to_regclass('scratch_us7615')")
if cur.fetchone()[0] is None:
    log("baue scratch_us7615 (US-Grants 1976-2015) ...")
    cur.execute("""
        CREATE UNLOGGED TABLE scratch_us7615 AS
        SELECT sp.pub_number,
               substring(sp.pub_number from '^US-([0-9]+)-')::bigint AS pnum
        FROM patent_spnp_full_z3 sp
        WHERE sp.pub_number LIKE 'US-%'
          AND sp.pub_number ~ '^US-[0-9]+-(A|B1|B2)$'
          AND sp.year BETWEEN 1976 AND 2015""")
    cur.execute("CREATE INDEX ON scratch_us7615(pnum)")
    cur.execute("CREATE INDEX ON scratch_us7615(pub_number)")
cur.execute("SELECT COUNT(*) FROM scratch_us7615"); log(f"US-Universum: {cur.fetchone()[0]:,}")

# --- 2. Goldliste laden + in DB spiegeln --------------------------------------
cur.execute("SELECT to_regclass('scratch_gold')")
if cur.fetchone()[0] is None:
    log("lade Goldliste in scratch_gold ...")
    cur.execute("CREATE UNLOGGED TABLE scratch_gold (domain text, pnum bigint)")
    buf = []
    csv.field_size_limit(1 << 24)
    for r in csv.DictReader(open(GOLD)):
        pn = r["patent_number"].strip()
        if pn.isdigit():
            buf.append((r["Domain"], int(pn)))
    from psycopg2.extras import execute_values
    execute_values(cur, "INSERT INTO scratch_gold VALUES %s", buf, page_size=10000)
    cur.execute("CREATE INDEX ON scratch_gold(pnum)")
cur.execute("SELECT COUNT(*) FROM scratch_gold"); log(f"Gold-Zeilen: {cur.fetchone()[0]:,}")

# --- 3. Gold-CPC-Profile (Maingroup) ------------------------------------------
log("Gold-CPC-Profile ...")
cur.execute("""
    SELECT g.domain, split_part(pc.cpc, '/', 1) AS grp, COUNT(DISTINCT u.pub_number) AS n
    FROM scratch_gold g
    JOIN scratch_us7615 u ON u.pnum = g.pnum
    JOIN patent_cpc_full pc ON pc.pub_number = u.pub_number
    GROUP BY 1, 2""")
gold_grp = defaultdict(dict)
for dom, grp, n in cur.fetchall():
    gold_grp[dom][grp] = n

# Gold-Set-Größen (im Universum matchbar)
cur.execute("""
    SELECT g.domain, COUNT(DISTINCT u.pub_number)
    FROM scratch_gold g JOIN scratch_us7615 u ON u.pnum = g.pnum GROUP BY 1""")
gold_n = dict(cur.fetchall())
log(f"Domänen: {len(gold_n)}; Gold matchbar gesamt: {sum(gold_n.values()):,}")

# --- 4. Globale Gruppen-Größen (nur benötigte Gruppen) ------------------------
need = sorted({g for d in gold_grp.values() for g in d})
log(f"globale Counts für {len(need)} Kandidaten-Gruppen ...")
cur.execute("""
    SELECT grp, COUNT(*) FROM (
      SELECT DISTINCT split_part(pc.cpc,'/',1) AS grp, u.pub_number
      FROM scratch_us7615 u
      JOIN patent_cpc_full pc ON pc.pub_number = u.pub_number
      WHERE split_part(pc.cpc,'/',1) = ANY(%s)
    ) d GROUP BY grp""", (need,))
glob = dict(cur.fetchall())

# --- 5. Greedy-Signatur je Domäne + exakte Bewertung --------------------------
results = {}
for dom in sorted(gold_n):
    G = gold_n[dom]
    prof = gold_grp[dom]
    cands = [(grp, n, glob.get(grp, n)) for grp, n in prof.items()
             if n >= max(5, 0.005 * G)]
    # Greedy nach approximiertem F1 (Union als Summe genähert)
    chosen, ret_apx, hit_apx = [], 0, 0
    cands.sort(key=lambda t: -(t[1] / t[2]))  # Start: präziseste zuerst
    improved = True
    while improved:
        improved = False
        best = None
        f1_now = (2 * hit_apx / (ret_apx + G)) if (ret_apx + G) else 0
        for grp, gn, tot in cands:
            if grp in chosen: continue
            f1_new = 2 * (hit_apx + gn) / ((ret_apx + tot) + G)
            if f1_new > f1_now and (best is None or f1_new > best[0]):
                best = (f1_new, grp, gn, tot)
        if best:
            chosen.append(best[1]); hit_apx += best[2]; ret_apx += best[3]
            improved = True
    if not chosen:
        chosen = [max(prof, key=prof.get)] if prof else []
    # exakte Bewertung der Signatur
    if chosen:
        cur.execute("""
            WITH sig AS (
              SELECT DISTINCT u.pub_number
              FROM scratch_us7615 u
              JOIN patent_cpc_full pc ON pc.pub_number = u.pub_number
              WHERE split_part(pc.cpc,'/',1) = ANY(%s))
            SELECT (SELECT COUNT(*) FROM sig),
                   (SELECT COUNT(*) FROM sig s JOIN scratch_us7615 u ON u.pub_number = s.pub_number
                      JOIN scratch_gold g ON g.pnum = u.pnum AND g.domain = %s),
                   (SELECT AVG(cs.cited_pctl) FROM sig s
                      JOIN patent_citedspnp_full_z3 cs ON cs.pub_number = s.pub_number)
        """, (chosen, dom))
        ret, hit, x_sig = cur.fetchone()
    else:
        ret, hit, x_sig = 0, 0, None
    cur.execute("""
        SELECT AVG(cs.cited_pctl) FROM scratch_gold g
        JOIN scratch_us7615 u ON u.pnum = g.pnum
        JOIN patent_citedspnp_full_z3 cs ON cs.pub_number = u.pub_number
        WHERE g.domain = %s""", (dom,))
    x_gold = cur.fetchone()[0]
    P = hit / ret if ret else 0.0
    R = hit / G if G else 0.0
    F1 = 2 * P * R / (P + R) if (P + R) else 0.0
    results[dom] = {"gold_n": G, "sig_groups": len(chosen), "signature": chosen[:12],
                    "retrieved": ret, "precision": round(P, 3), "recall": round(R, 3),
                    "f1": round(F1, 3),
                    "x_gold": round(float(x_gold), 4) if x_gold is not None else None,
                    "x_sig": round(float(x_sig), 4) if x_sig is not None else None}
    log(f"{dom:22s} G={G:>7,} sig={len(chosen):>3} P={P:.2f} R={R:.2f} F1={F1:.2f} "
        f"Xgold={results[dom]['x_gold']} Xsig={results[dom]['x_sig']}")

f1s = sorted(r["f1"] for r in results.values())
xs = [(r["x_gold"], r["x_sig"]) for r in results.values() if r["x_gold"] and r["x_sig"]]
mx = sum(a for a, b in xs) / len(xs); my = sum(b for a, b in xs) / len(xs)
num = sum((a - mx) * (b - my) for a, b in xs)
den = math.sqrt(sum((a - mx) ** 2 for a, b in xs)) * math.sqrt(sum((b - my) ** 2 for a, b in xs))
summary = {"n_domains": len(results), "f1_median": f1s[len(f1s) // 2],
           "f1_min": f1s[0], "f1_max": f1s[-1],
           "x_gold_vs_x_sig_pearson": round(num / den, 4) if den else None,
           "domains": results}
json.dump(summary, open(OUT, "w"), indent=2)
log(json.dumps({k: v for k, v in summary.items() if k != "domains"}, indent=2))
