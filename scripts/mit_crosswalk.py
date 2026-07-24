#!/usr/bin/env python3
"""Patentweiser Normalisierungs-Crosswalk: unsere fullz3-Perzentile vs. MIT-Werte.

Join über ~3M US-Grants (unsere Seite: ours_us_grants.csv aus patent_spnp_full_z3
+ patent_citedspnp_full_z3) gegen All_patents_info.csv (MIT, 5,26M Patente).
Misst: (a) own@age3 vs. MIT own@t3 (like-for-like), (b) cited@age3-Endwert vs.
MIT cited@t-1 (Test der dokumentierten K5-Approximation), (c) vs. MIT own@2015,
(d) MIT-interne Referenzkorrelationen. Fittet die lineare Übersetzung und testet
damit auf Domänen-Ebene, ob die High-End-Kompression ein Skalen-Artefakt ist.
"""
import csv, json, math, os
import numpy as np

SCRATCH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "mit_benchmark")
os.makedirs(SCRATCH, exist_ok=True)
OURS = os.path.join(SCRATCH, "ours_us_grants.csv")
ALLP = "/mnt/data-hdd/All_patents_info.csv"
DOMS = os.path.join(SCRATCH, "com_abgleich_domains.csv")
MIT_CSV = "/mnt/data-hdd/shared_tir_research/Technology_improvement_rates_for_all_technologies_Singh_Triulzi_Magee_May6.csv"
OUT = os.path.join(SCRATCH, "crosswalk_result.json")

def log(m): print(m, flush=True)


def ensure_ours() -> None:
    """Extrahiert unsere US-Grant-Perzentile (1976-2015) aus der DB, falls fehlend."""
    if os.path.exists(OURS) and os.path.getsize(OURS) > 1000:
        return
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"))
    import psycopg2
    log("extrahiere ours_us_grants.csv aus der DB ...")
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur = conn.cursor()
    cur.execute("SET statement_timeout = 0")
    sql = """COPY (
      SELECT substring(sp.pub_number from '^US-([0-9]+)-')::bigint AS pnum,
             sp.year, sp.spnp_pctl, cs.cited_pctl
      FROM patent_spnp_full_z3 sp
      LEFT JOIN patent_citedspnp_full_z3 cs ON cs.pub_number = sp.pub_number
      WHERE sp.pub_number ~ '^US-[0-9]+-(A|B1|B2)$' AND sp.year BETWEEN 1976 AND 2015
    ) TO STDOUT WITH CSV HEADER"""
    with open(OURS, "w") as f:
        cur.copy_expert(sql, f)


ensure_ours()


def pearson(a, b):
    a = np.asarray(a, float); b = np.asarray(b, float)
    return float(np.corrcoef(a, b)[0, 1])

def spearman(a, b):
    def rk(v):
        o = np.argsort(v, kind="mergesort"); r = np.empty(len(v)); r[o] = np.arange(len(v))
        return r
    return pearson(rk(np.asarray(a)), rk(np.asarray(b)))

# --- 1. Unsere Seite laden ----------------------------------------------------
log("lade unsere Seite ...")
pn, sp, ci = [], [], []
for r in csv.reader(open(OURS)):
    if r[0] == "pnum": continue
    pn.append(int(r[0])); sp.append(float(r[2]) if r[2] else np.nan)
    ci.append(float(r[3]) if r[3] else np.nan)
pn = np.array(pn, dtype=np.int64); sp = np.array(sp); ci = np.array(ci)
order = np.argsort(pn); pn, sp, ci = pn[order], sp[order], ci[order]
log(f"unsere Seite: {len(pn):,} US-Grants")

# --- 2. MIT-Seite streamen + joinen ------------------------------------------
log("streame All_patents_info ...")
csv.field_size_limit(1 << 24)
f = open(ALLP, newline="", encoding="utf-8", errors="replace")
rd = csv.reader(f)
header = next(rd)
cols = {c.strip(): i for i, c in enumerate(header)}
i_pn = cols["patent_number"]
i_own_t3 = cols["SPNP_count_t3_randomized_zscore_RPbyYear"]
i_cited = cols["meanSPNPcited_1year_before_randomized_zscore_RPbyYear"]
i_own_15 = cols["SPNP_count_2015_randomized_zscore_RPbyYear"]
i_year = cols["filing_year"]
m_pn, m_own_t3, m_cited, m_own15, m_year = [], [], [], [], []
n_rows = 0
for row in rd:
    n_rows += 1
    p = row[i_pn].strip()
    if not p.isdigit(): continue
    try:
        m_pn.append(int(p))
        m_own_t3.append(float(row[i_own_t3]) if row[i_own_t3] else np.nan)
        m_cited.append(float(row[i_cited]) if row[i_cited] else np.nan)
        m_own15.append(float(row[i_own_15]) if row[i_own_15] else np.nan)
        m_year.append(int(float(row[i_year])) if row[i_year] else 0)
    except (ValueError, IndexError):
        for L in (m_pn, m_own_t3, m_cited, m_own15, m_year):
            if len(L) > len(m_pn) - 1: pass
        continue
m_pn = np.array(m_pn, dtype=np.int64)
m_own_t3 = np.array(m_own_t3); m_cited = np.array(m_cited)
m_own15 = np.array(m_own15); m_year = np.array(m_year)
log(f"MIT-Seite: {len(m_pn):,} Patente ({n_rows:,} Zeilen)")

idx = np.searchsorted(pn, m_pn)
idx[idx >= len(pn)] = 0
matched = pn[idx] == m_pn
log(f"gematcht: {matched.sum():,}")

o_sp = sp[idx][matched]; o_ci = ci[idx][matched]
t3 = m_own_t3[matched]; ct = m_cited[matched]; o15 = m_own15[matched]
yr = m_year[matched]

def corr_pair(a, b):
    ok = ~(np.isnan(a) | np.isnan(b))
    return {"n": int(ok.sum()), "pearson": round(pearson(a[ok], b[ok]), 4),
            "spearman": round(spearman(a[ok], b[ok]), 4)}

res = {
    "matched": int(matched.sum()),
    "ours_own_vs_mit_own_t3": corr_pair(o_sp, t3),
    "ours_cited_vs_mit_cited_t1": corr_pair(o_ci, ct),
    "ours_own_vs_mit_own_2015": corr_pair(o_sp, o15),
    "mit_intern_own_t3_vs_own_2015": corr_pair(t3, o15),
    "mit_intern_own_t3_vs_cited_t1": corr_pair(t3, ct),
    "ours_intern_own_vs_cited": corr_pair(o_sp, o_ci),
}

# lineare Übersetzung (Crosswalk-Fits)
fits = {}
for name, (a, b) in {"own_t3_from_ours_own": (o_sp, t3),
                     "cited_t1_from_ours_cited": (o_ci, ct)}.items():
    ok = ~(np.isnan(a) | np.isnan(b))
    co = np.polyfit(a[ok], b[ok], 1)
    resid = b[ok] - (co[0] * a[ok] + co[1])
    fits[name] = {"slope": round(float(co[0]), 4), "intercept": round(float(co[1]), 4),
                  "resid_sd": round(float(resid.std()), 4)}
res["fits"] = fits

# Stabilität über Filing-Jahre
by_year = {}
for y0 in (1980, 1990, 2000, 2010):
    m = (yr >= y0) & (yr < y0 + 5)
    a, b = o_ci[m], ct[m]
    ok = ~(np.isnan(a) | np.isnan(b))
    if ok.sum() > 1000:
        by_year[f"{y0}-{y0+4}"] = {"n": int(ok.sum()),
                                   "pearson_cited": round(pearson(a[ok], b[ok]), 4)}
res["cited_stability_by_filing_year"] = by_year

# --- 3. Domänen-Test: Kompression = Skalen-Artefakt? -------------------------
# Übersetze unser Domänen-X̄ (cited) in die MIT-cited-Skala und wende MIT Gl.13
# an (6.15987·X − 5.01885); Vergleich gegen publiziertes K (log-Raum, Spearman/
# Pearson + Top-Ende).
sl, ic = fits["cited_t1_from_ours_cited"]["slope"], fits["cited_t1_from_ours_cited"]["intercept"]
mit_k = {}
for r in csv.DictReader(open(MIT_CSV)):
    mit_k[r["Domain Code (UPC-IPC)"].strip()] = float(r["Predicted K (% per annum)"])
rows = list(csv.DictReader(open(DOMS)))
pairs = []
for r in rows:
    if int(r["n_matched"]) < 500: continue
    x_ours = float(r["ours_x"])
    x_mit = sl * x_ours + ic
    k_trans = 100 * math.exp(6.15987 * x_mit - 5.01885)   # Gl.13 ohne Smearing
    pairs.append((r["code"], mit_k[r["code"]], float(r["ours_K"]), k_trans))
lk_mit = [math.log(p[1]) for p in pairs]
lk_old = [math.log(p[2]) for p in pairs]
lk_new = [math.log(p[3]) for p in pairs]
med = lambda v: sorted(v)[len(v) // 2]
res["domain_translation_test"] = {
    "n_domains": len(pairs),
    "old_refit": {"spearman": round(spearman(lk_mit, lk_old), 4),
                  "pearson_ln": round(pearson(lk_mit, lk_old), 4),
                  "median_K": round(med([p[2] for p in pairs]), 2)},
    "translated_gl13": {"spearman": round(spearman(lk_mit, lk_new), 4),
                        "pearson_ln": round(pearson(lk_mit, lk_new), 4),
                        "median_K": round(med([p[3] for p in pairs]), 2)},
    "mit_median_K": round(med([p[1] for p in pairs]), 2),
    "top_examples": [
        {"code": c, "mit_K": k, "ours_refit": ko, "ours_translated": round(kt, 1)}
        for c, k, ko, kt in sorted(pairs, key=lambda p: -p[1])[:8]],
}
json.dump(res, open(OUT, "w"), indent=2)
log(json.dumps(res, indent=2))
