#!/usr/bin/env python3
"""Find real months for research works OpenAlex dates to 1 January (Owner 2026-10-03).

OpenAlex gives a work `YYYY-01-01` when it only knows the year. In the history sample
(pipeline/history_vectors.py) that put 55-89 % of every January's 2,000 research works
into January although they appeared any time of the year — a topic's first appearance in
the research tier could come out up to eleven months early.

For every such work in history_items with a DOI, Crossref is asked (batches of 50 DOIs,
`filter=doi:…`), and the first of these that names a month IN THE SAME YEAR wins:
published-online, published-print, issued, published, then the DOI registration date
(`created`, deposited within days of online publication for new articles; a later year
means a back-filed DOI and is ignored). Measured on 400 works (03.10.): 77 % dated.

    .venv/bin/python scripts/history_redate.py                # dry run: counts, agreement check
    .venv/bin/python scripts/history_redate.py --apply        # move dated works, mark the rest
    .venv/bin/python scripts/history_redate.py --refill-january --apply   # top January up again

--apply: history_items.month := the found month (the OpenAlex month stays in
month_openalex, month_source names the field); works without a month get layer
'random:yearonly' — readers take layer 'random' only, so they leave monthly counts.
research_corpus is not touched. Crossref answers are cached in
data/crossref_dates.json (re-runs ask nothing twice).

--refill-january: per year, January is topped up to the quota with works published
2-31 January (certainly January), smallest hash first; they are queued unembedded —
embed with `scripts/history_embed.py work --handover --host http://127.0.0.1:8090 --name 3090`.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.db import get_connection  # noqa: E402
from pipeline.history_vectors import HASH, migrate_history_tables  # noqa: E402

UA = "CatandaryTrendsBot/1.0 (+https://catandary.de/trends/methodology)"
CACHE = ROOT / "data" / "crossref_dates.json"
FIELDS = ("published-online", "published-print", "issued", "published")
SELECT = "DOI,issued,published-print,published-online,published,created"
BATCH = 50


def log(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def month_of(item: dict, year: int) -> tuple[int | None, str]:
    for k in FIELDS:
        dp = ((item.get(k) or {}).get("date-parts") or [[None]])[0]
        if dp and len(dp) >= 2 and dp[0] == year and dp[1]:
            return int(dp[1]), k
    dp = ((item.get("created") or {}).get("date-parts") or [[None]])[0]
    if dp and len(dp) >= 2 and dp[0] == year:
        return int(dp[1]), "created"
    return None, "year-only"


def bare(doi: str) -> str:
    return doi.lower().replace("https://doi.org/", "").replace("http://doi.org/", "").strip()


def resolve(row: dict, cache: dict) -> tuple[str, int | None, str]:
    """What --apply does with one work: ("move", month, field), ("year-only", None, why)
    or ("skip", None, "crossref unreachable"). A DOI that is NOT in the cache was never
    answered (the batch failed after four attempts) — that is unknown, not year-only;
    the row keeps month_source NULL and the next run asks again. Only a cached {} means
    Crossref does not know the DOI."""
    doi = row.get("doi")
    if not doi:
        return "year-only", None, "no DOI"
    key = bare(doi)
    if key not in cache:
        return "skip", None, "crossref unreachable"
    it = cache[key]
    if not it:
        return "year-only", None, "not at Crossref"
    m, src = month_of(it, row["y"])
    if m is None:
        return "year-only", None, src
    return "move", m, src


def fetch(dois: list[str], cache: dict) -> None:
    todo = [d for d in dois if d not in cache]
    log(f"crossref: {len(dois):,} DOIs, {len(todo):,} not cached")
    with httpx.Client(headers={"User-Agent": UA}, timeout=90) as cl:
        for s in range(0, len(todo), BATCH):
            part = todo[s:s + BATCH]
            for attempt in range(4):
                try:
                    r = cl.get("https://api.crossref.org/works",
                               params={"filter": ",".join("doi:" + d for d in part),
                                       "rows": BATCH, "select": SELECT})
                    if r.status_code != 200:
                        # 429/5xx: Crossref is busy. 4xx: the batch itself was refused
                        # (one odd DOI breaks the whole `filter=doi:…` list). Either way
                        # this is NOT "not at Crossref" — never cache {} for it.
                        time.sleep(5 * (attempt + 1))
                        continue
                    j = r.json()
                    break
                except Exception:                                  # noqa: BLE001
                    time.sleep(5 * (attempt + 1))
            else:
                log(f"  batch at {s} failed — left uncached, a re-run asks again")
                continue
            found = {}
            if isinstance(j, dict) and isinstance(j.get("message"), dict):
                found = {it["DOI"].lower(): it for it in j["message"]["items"]}
            for d in part:
                cache[d] = found.get(d) or {}      # {} = not at Crossref
            if (s // BATCH) % 40 == 0:
                log(f"  {min(s + BATCH, len(todo)):,}/{len(todo):,}")
                CACHE.write_text(json.dumps(cache), encoding="utf-8")
            time.sleep(0.2)
    CACHE.write_text(json.dumps(cache), encoding="utf-8")


def migrate() -> None:
    migrate_history_tables()
    with get_connection() as c:
        c.execute("ALTER TABLE history_items ADD COLUMN IF NOT EXISTS month_openalex INTEGER")
        c.execute("ALTER TABLE history_items ADD COLUMN IF NOT EXISTS month_source TEXT")


def redate(apply: bool) -> int:
    migrate()
    with get_connection() as c:
        c.execute("SET statement_timeout = 0")
        rows = [dict(r) for r in c.execute(
            "SELECT h.id, h.month, rc.doi, extract(year FROM rc.published)::int AS y "
            "FROM history_items h JOIN research_corpus rc ON rc.id = h.ref "
            "WHERE h.tier = 'science' AND h.layer = 'random' AND h.month_source IS NULL "
            "AND extract(month FROM rc.published) = 1 AND extract(day FROM rc.published) = 1").fetchall()]
    log(f"works dated 1 January in the sample: {len(rows):,} ({sum(1 for r in rows if r['doi']):,} with a DOI)")
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    fetch(sorted({bare(r["doi"]) for r in rows if r["doi"]}), cache)
    moves, stat, months, agree = [], Counter(), Counter(), Counter()
    for r in rows:
        kind, m, src = resolve(r, cache)
        stat[src] += 1
        if kind == "skip":
            continue                                # unanswered — asked again next run
        moves.append((r["id"], m, src))
        if m:
            months[m] += 1
        it = cache.get(bare(r["doi"])) if r["doi"] else None
        if not it:
            continue
        # how good is the DOI registration date? compare where both exist
        on, _ = month_of({"published-online": it.get("published-online")}, r["y"])
        cr = ((it.get("created") or {}).get("date-parts") or [[None]])[0]
        if on and cr and len(cr) >= 2 and cr[0] == r["y"]:
            agree["same month" if cr[1] == on else "±1 month" if abs(cr[1] - on) == 1 else "further"] += 1
    dated = sum(1 for _, m, _ in moves if m)
    log(f"outcome: {dict(stat)}")
    if stat["crossref unreachable"]:
        log(f"{stat['crossref unreachable']:,} works got no answer from Crossref — left untouched, "
            "a re-run asks again")
    log(f"dated {dated:,} of {len(rows):,} ({dated / max(len(rows), 1):.0%}); months {sorted(months.items())}")
    log(f"DOI registration vs online month where both exist: {dict(agree)}")
    if not apply:
        log("DRY RUN — nothing written")
        return 0
    with get_connection() as c:
        for s in range(0, len(moves), 1000):
            for item_id, m, src in moves[s:s + 1000]:
                if m:
                    c.execute("UPDATE history_items SET month_openalex = month, "
                              "month = (month / 12) * 12 + ? - 1, month_source = ? WHERE id = ?",
                              (m, "crossref:" + src, item_id))
                else:
                    c.execute("UPDATE history_items SET month_openalex = month, month_source = 'year-only', "
                              "layer = 'random:yearonly' WHERE id = ?", (item_id,))
            c.commit()
    log(f"APPLIED: {dated:,} moved, {len(moves) - dated:,} marked year-only")
    return 0


def refill_january(apply: bool, quota: int) -> int:
    migrate()
    with get_connection() as c:
        c.execute("SET statement_timeout = 0")
        have = {int(r["y"]): int(r["n"]) for r in c.execute(
            "SELECT month / 12 AS y, count(*) AS n FROM history_items WHERE tier = 'science' "
            "AND layer = 'random' AND mod(month, 12) = 0 GROUP BY 1").fetchall()}
        need = {y: quota - n for y, n in have.items() if n < quota}
        log("January after re-dating: " + ", ".join(f"{y} {have[y]:,}" for y in sorted(have)))
        log(f"to top up: {sum(need.values()):,} works over {len(need)} Januaries")
        if not apply or not need:
            log("DRY RUN — nothing queued" if not apply else "nothing to do")
            return 0
        n = 0
        for y, k in sorted(need.items()):
            # weight = frame / sample, like the planner: the frame is every eligible
            # work of 2-31 January, the sample the rows drawn from it — LEAST(frame, k),
            # so a January whose frame is smaller than k gets weight 1, not < 1
            # (Codex review on #121).
            n += c.execute(f"""
                WITH frame AS (
                    SELECT rc.id
                    FROM research_corpus rc
                    WHERE rc.published >= make_date(?, 1, 2) AND rc.published < make_date(?, 2, 1)
                      AND octet_length(rc.abstract) >= 80 AND NOT coalesce(rc.is_retracted, FALSE)
                      AND NOT EXISTS (SELECT 1 FROM history_items h WHERE h.tier = 'science' AND h.ref = rc.id)
                )
                INSERT INTO history_items (tier, ref, month, layer, month_source, weight)
                SELECT 'science', f.id, ? , 'random', 'openalex:jan-refill',
                       (SELECT count(*) FROM frame)::real / LEAST((SELECT count(*) FROM frame), ?)
                FROM frame f
                ORDER BY {HASH.format(k="hashtext(f.id)::bigint & 2147483647")}, f.id
                LIMIT ?
                ON CONFLICT (tier, ref) DO NOTHING""", (y, y, y * 12, k, k)).rowcount
            c.commit()
        log(f"queued {n:,} January works — embed with history_embed.py work")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--refill-january", action="store_true")
    ap.add_argument("--quota", type=int, default=2000)
    a = ap.parse_args()
    return refill_january(a.apply, a.quota) if a.refill_january else redate(a.apply)


if __name__ == "__main__":
    raise SystemExit(main())
