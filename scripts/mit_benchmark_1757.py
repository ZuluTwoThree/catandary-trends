#!/usr/bin/env python3
"""Abgleich-Ausbaustufe: exakte COM-Domänen-Rekonstruktion + Abgleich je Domäne.

Rekonstruiert die 1757 Singh/Triulzi/Magee-Domänen aus All_patents_info.csv
(mainclass_id = USPC-Hauptklasse × IPC4 = IPC-Mainclass je Patent, Zuordnung
über den publizierten Domain-Code), validiert die Rekonstruktion gegen die
publizierten Domain Sizes, joint die Patent-Sets in unser fullz3-Substrat und
vergleicht unser K̂ (aktive Prod-Kalibrierung, cited) je Domäne mit dem
publizierten Predicted K — statt der bisherigen IPC4-Aggregation.
"""
import csv, json, math, os, re, sys
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from dotenv import load_dotenv
load_dotenv("/home/dirk/projects/catandary-trends/.env")
import psycopg2
from psycopg2.extras import execute_values

SCRATCH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "mit_benchmark")
os.makedirs(SCRATCH, exist_ok=True)
ALLP = "/mnt/data-hdd/All_patents_info.csv"
MIT_CSV = "/mnt/data-hdd/shared_tir_research/Technology_improvement_rates_for_all_technologies_Singh_Triulzi_Magee_May6.csv"
OUT_JSON = os.path.join(SCRATCH, "com_abgleich_result.json")
OUT_CSV = os.path.join(SCRATCH, "com_abgleich_domains.csv")

COEF_A, COEF_B, SIGMA2 = -5.5622, 5.5036, 0.4930  # aktiver Prod-Pfad fullz3+cited
def k_from_x(x): return 100.0 * math.exp(COEF_A + COEF_B * x) * math.exp(SIGMA2 / 2)

def log(m): print(m, flush=True)

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

# --- 1. Publizierte Domänen laden --------------------------------------------
domains = {}
for r in csv.DictReader(open(MIT_CSV)):
    code = r["Domain Code (UPC-IPC)"].strip()
    m = re.match(r"^([0-9]+|D[0-9]+)([A-Z][0-9]{2}[A-Z])$", code)
    if not m:
        log(f"unparsed: {code}"); continue
    upc = m.group(1).lstrip("0") or "0"
    domains[(upc, m.group(2))] = {
        "code": code, "K": float(r["Predicted K (% per annum)"]),
        "size": int(r["Domain Size"])}
log(f"publizierte Domänen: {len(domains)}")

# --- 2. All_patents_info streamen → Zuordnung --------------------------------
assign = defaultdict(list)   # (upc, ipc4) -> [patent_number]
csv.field_size_limit(1 << 24)
with open(ALLP, newline="", encoding="utf-8", errors="replace") as f:
    rd = csv.reader(f)
    header = next(rd)
    cols = {c.strip(): i for i, c in enumerate(header)}
    log(f"Spalten: {header[:12]} ... ({len(header)})")
    i_pn = cols.get("patent_number")
    i_mc = cols.get("mainclass_id")
    i_ipc = cols.get("IPC4") if "IPC4" in cols else cols.get("IPC")
    if i_pn is None or i_mc is None or i_ipc is None:
        log(f"FEHLER: Spalten nicht gefunden: {cols}"); sys.exit(1)
    n_rows = n_assigned = 0
    for row in rd:
        n_rows += 1
        try:
            pn = row[i_pn].strip()
            if not pn.isdigit(): continue
            mc = row[i_mc].strip().rstrip(".0") if "." in row[i_mc] else row[i_mc].strip()
            mc = mc.split(".")[0].lstrip("0") or "0"
            ipc = row[i_ipc].strip().upper()
        except IndexError:
            continue
        key = (mc, ipc)
        if key in domains:
            assign[key].append(int(pn)); n_assigned += 1
        if n_rows % 1_000_000 == 0:
            log(f"  {n_rows:,} Zeilen, {n_assigned:,} zugeordnet")
log(f"gesamt: {n_rows:,} Zeilen, {n_assigned:,} zugeordnet, "
    f"{len(assign)}/{len(domains)} Domänen getroffen")

# --- 3. Rekonstruktions-Validierung gegen publizierte Sizes ------------------
recon = []
for key, meta in domains.items():
    n = len(assign.get(key, []))
    recon.append((meta["code"], meta["size"], n))
ratios = sorted(n / s for _, s, n in recon if s and n)
covered = sum(1 for _, s, n in recon if n > 0)
size_pairs = [(s, n) for _, s, n in recon if n > 0]
size_corr = pearson([math.log(s) for s, n in size_pairs], [math.log(n) for s, n in size_pairs])
log(f"Rekonstruktion: {covered}/{len(domains)} Domänen besetzt; "
    f"Size-Ratio median={ratios[len(ratios)//2]:.3f}; ln-Size-Pearson={size_corr:.3f}")

# --- 4. In DB spiegeln + X je Domäne (US-Universum 1976-2015, cited) ---------
conn = psycopg2.connect(os.environ["DATABASE_URL"])
conn.autocommit = True
cur = conn.cursor()
cur.execute("SET statement_timeout = 0")
cur.execute("SET work_mem = '1GB'")
cur.execute("DROP TABLE IF EXISTS scratch_com")
cur.execute("CREATE UNLOGGED TABLE scratch_com (code text, pnum bigint)")
buf = []
for key, pns in assign.items():
    code = domains[key]["code"]
    buf.extend((code, pn) for pn in pns)
execute_values(cur, "INSERT INTO scratch_com VALUES %s", buf, page_size=20000)
cur.execute("CREATE INDEX ON scratch_com(pnum)")
log(f"scratch_com: {len(buf):,} Zeilen")

cur.execute("SELECT to_regclass('scratch_us7615')")
if cur.fetchone()[0] is None:
    log("baue scratch_us7615 ...")
    cur.execute("""
        CREATE UNLOGGED TABLE scratch_us7615 AS
        SELECT sp.pub_number,
               substring(sp.pub_number from '^US-([0-9]+)-')::bigint AS pnum
        FROM patent_spnp_full_z3 sp
        WHERE sp.pub_number LIKE 'US-%'
          AND sp.pub_number ~ '^US-[0-9]+-(A|B1|B2)$'
          AND sp.year BETWEEN 1976 AND 2015""")
    cur.execute("CREATE INDEX ON scratch_us7615(pnum)")

log("X je Domäne ...")
cur.execute("""
    SELECT c.code, AVG(cs.cited_pctl) AS x, COUNT(*) AS n
    FROM scratch_com c
    JOIN scratch_us7615 u ON u.pnum = c.pnum
    JOIN patent_citedspnp_full_z3 cs ON cs.pub_number = u.pub_number
    GROUP BY c.code""")
ours = {code: (float(x), int(n)) for code, x, n in cur.fetchall() if x is not None}
log(f"X berechnet für {len(ours)} Domänen")

# --- 5. Abgleich je Domäne ----------------------------------------------------
by_code = {meta["code"]: meta for meta in domains.values()}
rows_out, variants = [], {}
for floor in (100, 500):
    pairs = []
    for code, (x, n) in ours.items():
        if n < floor: continue
        meta = by_code[code]
        pairs.append((code, meta["K"], k_from_x(x), x, n, meta["size"]))
    lk_mit = [math.log(p[1]) for p in pairs]
    lk_our = [math.log(p[2]) for p in pairs]
    variants[f"floor_{floor}"] = {
        "n_domains": len(pairs),
        "spearman": round(spearman(lk_mit, lk_our), 4),
        "pearson_ln": round(pearson(lk_mit, lk_our), 4),
        "mit_K_median": round(sorted(p[1] for p in pairs)[len(pairs)//2], 2),
        "ours_K_median": round(sorted(p[2] for p in pairs)[len(pairs)//2], 2)}
    if floor == 100:
        rows_out = pairs

summary = {"published_domains": len(domains), "covered": covered,
           "assigned_rows": n_assigned,
           "size_ratio_median": round(ratios[len(ratios)//2], 3),
           "size_ln_pearson": round(size_corr, 3),
           "results": variants,
           "first_pass_reference": {"us_only_ipc4": {"spearman": 0.7044, "pearson_ln": 0.7735,
                                                     "n_subclasses": 526}}}
json.dump(summary, open(OUT_JSON, "w"), indent=2)
with open(OUT_CSV, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["code", "mit_K", "ours_K", "ours_x", "n_matched", "mit_size"])
    for p in sorted(rows_out, key=lambda p: -p[5]):
        w.writerow([p[0], p[1], round(p[2], 2), round(p[3], 4), p[4], p[5]])
log(json.dumps({k: v for k, v in summary.items()}, indent=2))
