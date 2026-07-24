#!/usr/bin/env python3
"""Matching-Audit + Fehler-in-Variablen-Crosswalk (Paper-Pflichtanalysen #10/#12).

Ein Streaming-Pass über All_patents_info.csv (5,26M MIT-Patente):
(A) AUDIT — zerlegt den ~43%-Match-Verlust nach Ursache: (1) Patentnummer gar
    nicht im Graphen, (2) nur Nicht-Grant-Kind (z.B. A1-Application), (3) Grant-
    Kind vorhanden, aber Publikationsjahr-Proxy außerhalb 1976-2015. Plus
    Balance-Check gematcht vs. ungematcht (Anmeldejahr, Zitationen, Top-Klassen).
(B) EIV — Deming-/Orthogonal-Regression (λ=1) für den cited-Crosswalk auf
    Patent-Ebene (Attenuations-Test gegen die OLS-Steigung 0,672) und auf
    Domänen-Mittelwerten (651 Benchmark-Domänen), plus Quantil-Vergleich der
    Domänen-X̄-Verteilungen (Top-Tail-Analyse).

Output: data/mit_benchmark/audit_eiv_result.json
"""
import csv, json, math, os, re
from collections import defaultdict

import numpy as np

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "mit_benchmark")
ALLP = "/mnt/data-hdd/All_patents_info.csv"
MIT_CSV = "/mnt/data-hdd/shared_tir_research/Technology_improvement_rates_for_all_technologies_Singh_Triulzi_Magee_May6.csv"
US_ALL = os.path.join(BASE, "ours_us_all.csv")
US_GRANTS = os.path.join(BASE, "ours_us_grants.csv")
DOMS = os.path.join(BASE, "com_abgleich_domains.csv")
OUT = os.path.join(BASE, "audit_eiv_result.json")

def log(m): print(m, flush=True)

def load_sorted(path, cols, header_key):
    arrs = [[] for _ in cols]
    for r in csv.reader(open(path)):
        if r[0] == header_key: continue
        for i, (idx, conv) in enumerate(cols):
            v = r[idx]
            arrs[i].append(conv(v) if v not in ("", None) else np.nan)
    out = [np.array(a) for a in arrs]
    order = np.argsort(out[0])
    return [a[order] for a in out]

log("lade ours_us_all ...")
a_pn, a_grant, a_yg = load_sorted(US_ALL, [(0, np.int64), (1, lambda v: 1 if v == "t" else 0),
                                           (2, float)], "pnum")
log(f"  {len(a_pn):,} US-Patentnummern im Graphen")
log("lade ours_us_grants ...")
g_pn, g_cited = load_sorted(US_GRANTS, [(0, np.int64), (3, float)], "pnum")
log(f"  {len(g_pn):,} US-Grants 1976-2015")

domains = {}
for r in csv.DictReader(open(MIT_CSV)):
    code = r["Domain Code (UPC-IPC)"].strip()
    m = re.match(r"^([0-9]+|D[0-9]+)([A-Z][0-9]{2}[A-Z])$", code)
    if m:
        domains[(m.group(1).lstrip("0") or "0", m.group(2))] = code

def lookup(sorted_pn, pnums):
    idx = np.searchsorted(sorted_pn, pnums)
    idx[idx >= len(sorted_pn)] = 0
    return idx, sorted_pn[idx] == pnums

# --- Streaming-Pass -----------------------------------------------------------
CITBINS = [0, 1, 3, 10, 30, 100, 10**9]
cats = ("matched", "grant_kind_wrong_year", "only_nongrant_kind", "not_in_graph")
stat = {c: {"n": 0, "fy_sum": 0.0, "fy_n": 0, "cit_sum": 0.0, "cit_n": 0,
            "cit_hist": [0] * (len(CITBINS) - 1), "classes": defaultdict(int)} for c in cats}
# EIV-Akkus (Patent-Ebene, cited-Paar)
S = dict(n=0, sx=0.0, sy=0.0, sxx=0.0, syy=0.0, sxy=0.0)
dom_mit = defaultdict(lambda: [0.0, 0])   # code -> [sum MIT cited zRP, n]

csv.field_size_limit(1 << 24)
f = open(ALLP, newline="", encoding="utf-8", errors="replace")
rd = csv.reader(f)
header = next(rd)
cols = {c.strip(): i for i, c in enumerate(header)}
i_pn, i_fy = cols["patent_number"], cols["filing_year"]
i_cit, i_mc = cols["cit_received_dec2015"], cols["mainclass_id"]
i_ipc = cols["IPC4"]
i_mcit = cols["meanSPNPcited_1year_before_randomized_zscore_RPbyYear"]

CHUNK = 500_000
buf = []
def flush(buf):
    if not buf: return
    pns = np.array([b[0] for b in buf], dtype=np.int64)
    ai, am = lookup(a_pn, pns)
    gi, gm = lookup(g_pn, pns)
    for j, (pn, fy, cit, mc, mcit_v, code) in enumerate(buf):
        if gm[j]:
            cat = "matched"
            oc = g_cited[gi[j]]
            if not (np.isnan(oc) or np.isnan(mcit_v)):
                S["n"] += 1; S["sx"] += oc; S["sy"] += mcit_v
                S["sxx"] += oc * oc; S["syy"] += mcit_v * mcit_v; S["sxy"] += oc * mcit_v
        elif am[j]:
            if a_grant[ai[j]]:
                cat = "grant_kind_wrong_year"
            else:
                cat = "only_nongrant_kind"
        else:
            cat = "not_in_graph"
        s = stat[cat]; s["n"] += 1
        if fy == fy: s["fy_sum"] += fy; s["fy_n"] += 1
        if cit == cit:
            s["cit_sum"] += cit; s["cit_n"] += 1
            for b in range(len(CITBINS) - 1):
                if CITBINS[b] <= cit < CITBINS[b + 1]:
                    s["cit_hist"][b] += 1; break
        s["classes"][mc] += 1
        if code:
            d = dom_mit[code]
            if mcit_v == mcit_v: d[0] += mcit_v; d[1] += 1

n_rows = 0
for row in rd:
    n_rows += 1
    p = row[i_pn].strip()
    if not p.isdigit(): continue
    try:
        fy = float(row[i_fy]) if row[i_fy] else float("nan")
        cit = float(row[i_cit]) if row[i_cit] else float("nan")
        mc = row[i_mc].split(".")[0].strip().lstrip("0") or "0"
        ipc = row[i_ipc].strip().upper()
        mcit_v = float(row[i_mcit]) if row[i_mcit] else float("nan")
    except (ValueError, IndexError):
        continue
    buf.append((int(p), fy, cit, mc, mcit_v, domains.get((mc, ipc))))
    if len(buf) >= CHUNK:
        flush(buf); buf = []
        if n_rows % 2_000_000 < CHUNK: log(f"  {n_rows:,} Zeilen")
flush(buf)
log(f"Stream fertig: {n_rows:,} Zeilen")

# --- (A) Audit-Auswertung -----------------------------------------------------
total = sum(stat[c]["n"] for c in cats)
audit = {"total_mit_patents": total}
for c in cats:
    s = stat[c]
    top = sorted(s["classes"].items(), key=lambda kv: -kv[1])[:8]
    audit[c] = {"n": s["n"], "share": round(s["n"] / total, 4),
                "mean_filing_year": round(s["fy_sum"] / s["fy_n"], 1) if s["fy_n"] else None,
                "mean_citations": round(s["cit_sum"] / s["cit_n"], 2) if s["cit_n"] else None,
                "cit_hist_bins": CITBINS[:-1], "cit_hist": s["cit_hist"],
                "top_mainclasses": [{"class": k, "n": v} for k, v in top]}
log(json.dumps({c: {"n": audit[c]["n"], "share": audit[c]["share"],
                    "fy": audit[c]["mean_filing_year"], "cit": audit[c]["mean_citations"]}
                for c in cats}, indent=2))

# --- (B) EIV: Deming patent- und domänenweise --------------------------------
def deming(n, sx, sy, sxx, syy, sxy):
    mx, my = sx / n, sy / n
    Sxx = sxx / n - mx * mx; Syy = syy / n - my * my; Sxy = sxy / n - mx * my
    slope = (Syy - Sxx + math.sqrt((Syy - Sxx) ** 2 + 4 * Sxy * Sxy)) / (2 * Sxy)
    return slope, my - slope * mx

ols_slope = (S["sxy"] / S["n"] - S["sx"] / S["n"] * S["sy"] / S["n"]) / \
            (S["sxx"] / S["n"] - (S["sx"] / S["n"]) ** 2)
dem_slope, dem_ic = deming(S["n"], S["sx"], S["sy"], S["sxx"], S["syy"], S["sxy"])
eiv = {"patent_level": {"n": S["n"], "ols_slope": round(ols_slope, 4),
                        "deming_slope_lambda1": round(dem_slope, 4),
                        "deming_intercept": round(dem_ic, 4)}}

ours_dom = {r["code"]: (float(r["ours_x"]), int(r["n_matched"]))
            for r in csv.DictReader(open(DOMS))}
pairs = [(ours_dom[c][0], s / n_) for c, (s, n_) in dom_mit.items()
         if n_ >= 500 and c in ours_dom and ours_dom[c][1] >= 500]
xs = np.array([p[0] for p in pairs]); ys = np.array([p[1] for p in pairs])
n = len(pairs)
b_ols, a_ols = np.polyfit(xs, ys, 1)
sd = dict(n=n, sx=float(xs.sum()), sy=float(ys.sum()), sxx=float((xs**2).sum()),
          syy=float((ys**2).sum()), sxy=float((xs*ys).sum()))
b_dem, a_dem = deming(**sd)
r = float(np.corrcoef(xs, ys)[0, 1])
eiv["domain_level"] = {"n_domains": n, "pearson": round(r, 4),
                       "ols_slope": round(float(b_ols), 4),
                       "deming_slope_lambda1": round(b_dem, 4)}

qs = [50, 75, 90, 95, 99]
eiv["qq_domain_means"] = {
    "quantiles": qs,
    "ours_x": [round(float(np.percentile(xs, q)), 4) for q in qs],
    "mit_cited_zrp": [round(float(np.percentile(ys, q)), 4) for q in qs],
    "tail_span_ours_q99_minus_q50": round(float(np.percentile(xs, 99) - np.percentile(xs, 50)), 4),
    "tail_span_mit_q99_minus_q50": round(float(np.percentile(ys, 99) - np.percentile(ys, 50)), 4),
}
log(json.dumps(eiv, indent=2))
json.dump({"audit": audit, "eiv": eiv}, open(OUT, "w"), indent=2)
log(f"→ {OUT}")
