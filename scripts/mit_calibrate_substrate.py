#!/usr/bin/env python3
"""WS1 rigoroser Test: own- vs cited-Prädiktor auf UNSEREM Substrat, aber mit den
EXAKTEN MIT-Domänen (patent_number-Sets) und den EXAKTEN K_true — entfernt den
BENCH-Proxy- und CPC-Mapping-Rauschanteil.

Matching: MIT patent_number (int) ↔ unsere US-Grant pub_number 'US-<num>-(A|B1|B2)'.

    python scripts/mit_calibrate_substrate.py
"""
from __future__ import annotations
import csv, io, math, sys
from collections import defaultdict
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from pipeline.db import get_connection

PERF = "/mnt/data-hdd/performance_time_series.csv"
INFO = "/mnt/data-hdd/Domains_patent_info.csv"
csv.field_size_limit(1 << 24)


def k_true() -> dict[str, float]:
    s = defaultdict(list)
    for r in csv.DictReader(open(PERF)):
        try:
            y = float(r["Year"]); v = float(r["Data"])
        except (ValueError, TypeError):
            continue
        if v > 0:
            s[r["Domain"]].append((y, math.log(v)))
    K = {}
    for d, pts in s.items():
        if len(pts) < 3:
            continue
        xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
        mx = sum(xs)/len(xs); my = sum(ys)/len(ys)
        den = sum((x-mx)**2 for x in xs)
        if den > 0:
            K[d] = sum((x-mx)*(y-my) for x, y in zip(xs, ys))/den
    return K


def fit(xs, ys):
    n = len(xs); mx = sum(xs)/n; my = sum(ys)/n
    den = sum((x-mx)**2 for x in xs) or 1e-12
    b = sum((x-mx)*(y-my) for x, y in zip(xs, ys))/den
    a = my - b*mx
    pred = [a+b*x for x in xs]
    ssr = sum((y-p)**2 for y, p in zip(ys, pred)); sst = sum((y-my)**2 for y in ys) or 1e-12
    return a, b, 1-ssr/sst


def spearman(xs, ys):
    def rk(v):
        o = sorted(range(len(v)), key=lambda i: v[i]); r = [0]*len(v)
        for k, i in enumerate(o): r[i] = k
        return r
    rx, ry = rk(xs), rk(ys); n = len(xs); mx = sum(rx)/n; my = sum(ry)/n
    num = sum((a-mx)*(b-my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a-mx)**2 for a in rx)*sum((b-my)**2 for b in ry)) or 1e-12
    return num/den


def loo(xs, ys):
    n = len(xs); e = []
    for i in range(n):
        a, b, _ = fit(xs[:i]+xs[i+1:], ys[:i]+ys[i+1:])
        e.append((ys[i]-(a+b*xs[i]))**2)
    my = sum(ys)/n; sst = sum((y-my)**2 for y in ys) or 1e-12
    return 1-sum(e)/sst


def main() -> int:
    K = k_true()
    print(f"K_true: {len(K)} Domänen")
    with get_connection() as conn:
        c = conn._conn.cursor()
        c.execute("SET statement_timeout='0'"); c.execute("SET work_mem='1GB'")
        print("lade MIT-Domänen-Patente (Domain, patent_number) → temp …")
        c.execute("DROP TABLE IF EXISTS mit_dp")
        c.execute("CREATE UNLOGGED TABLE mit_dp (domain text, patnum bigint)")
        buf = io.StringIO(); nrows = 0
        for r in csv.DictReader(open(INFO)):
            pn = r["patent_number"]
            if pn and pn.isdigit():
                buf.write(f"{r['Domain']}\t{pn}\n"); nrows += 1
                if buf.tell() > 40_000_000:
                    buf.seek(0); c.copy_expert("COPY mit_dp FROM STDIN", buf); buf = io.StringIO()
        buf.seek(0); c.copy_expert("COPY mit_dp FROM STDIN", buf)
        c.execute("CREATE INDEX ON mit_dp(patnum)")
        conn._conn.commit()
        print(f"  {nrows:,} (Domäne, Patent)-Zeilen")
        print("baue US-Grant-Nummern-Map aus patent_spnp_full_z3 …")
        c.execute("DROP TABLE IF EXISTS us_grant_map")
        c.execute("CREATE UNLOGGED TABLE us_grant_map AS "
                  "SELECT substring(pub_number from '^US-([0-9]+)-')::bigint AS patnum, pub_number "
                  "FROM patent_spnp_full_z3 WHERE pub_number ~ '^US-[0-9]+-(A|B1|B2)$'")
        c.execute("CREATE INDEX ON us_grant_map(patnum)")
        conn._conn.commit()
        print("aggregiere own- und cited-X je Domäne (exakte MIT-Sets) …")
        c.execute("""
          SELECT dp.domain, AVG(sp.spnp_pctl) own_x, AVG(cs.cited_pctl) cited_x,
                 COUNT(sp.spnp_pctl) n_own, COUNT(cs.cited_pctl) n_cited
          FROM mit_dp dp
          JOIN us_grant_map g ON g.patnum = dp.patnum
          JOIN patent_spnp_full_z3 sp ON sp.pub_number = g.pub_number
          LEFT JOIN patent_citedspnp_full_z3 cs ON cs.pub_number = g.pub_number
          GROUP BY dp.domain""")
        rows = {r[0]: (r[1], r[2], r[3], r[4]) for r in c.fetchall()}
        c.execute("DROP TABLE IF EXISTS mit_dp"); c.execute("DROP TABLE IF EXISTS us_grant_map")
        conn._conn.commit()

    doms = [d for d in K if d in rows and rows[d][0] is not None and rows[d][1] is not None and K[d] > 0]
    print(f"\n{len(doms)} Domänen mit Match + K_true>0")
    print(f"{'domain':22s} {'K%':>6} {'own_X':>6} {'cited_X':>7} {'n_own':>7} {'n_cited':>7}")
    for d in sorted(doms, key=lambda d: -K[d]):
        o, ci, no, nc = rows[d]
        print(f"{d:22s} {100*K[d]:6.1f} {o:6.3f} {ci:7.3f} {no:7} {nc:7}")
    ys = [math.log(K[d]) for d in doms]
    for label, idx in [("own (eigene Zentralität)", 0), ("cited (zitierte Zentralität)", 1)]:
        xs = [rows[d][idx] for d in doms]
        a, b, r2 = fit(xs, ys)
        pred = [a + b * x for x in xs]
        sig = sum((y - p) ** 2 for y, p in zip(ys, pred)) / (len(xs) - 2)
        print(f"\n{label}: a={a:.4f} b={b:.4f} SIGMA2={sig:.4f} "
              f"R²={r2:.3f} Spearman={spearman(xs,ys):.3f} LOO-R²={loo(xs,ys):.3f}")
        print(f"    → _CALIB-Tupel: ({a - math.log(100):.4f}, {b:.4f}, {sig:.4f})  "
              f"(ln-fraction-Intercept für _k_from_x ×100)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
