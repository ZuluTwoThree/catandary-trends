"""Story grouping (#109): one event, several published articles.

The embedding dedup (Stage 5, cosine >= 0.92) measures TEXT similarity, not
EVENT identity. Three outlets covering the same launch from three angles sit
at 0.78-0.87 and all get published. Lowering the global threshold would drop
~9 % of all articles and still not catch the measured case (issue #109), so
the grouping is a POST-PASS with its own rule and nothing in Stage 5 changes:

    same extracted brand  ·  published within STORY_WINDOW_HOURS of each other
    ·  cosine >= STORY_MIN_SIMILARITY, groups closed transitively (union-find)

Measured on all 21,411 published September-2026 articles with brand + vector
(issue #109): at 0.80 the rule forms 896 groups covering 2,434 articles, i.e.
1,538 articles (7.2 %) are follow-up reports; the Apple-keynote day (73
articles with brand "Apple") stays apart because its pairs sit at 0.25-0.69 —
the cosine carries the decision, the brand is only the pre-filter.

Stage 1 (this module): measure and show. The oldest article LEADS the group
(the report that was there first; ties by id); the others are listed on its
page and on each other's as "also reported by". Whether followers should stop
being published at all (Stage 5 + mark_filtered) is a later decision, after a
week of seeing the groups (#109, step 2).

Persisted in `trend_stories` (one row per grouped article, story_id = the
lead's trend id, so a re-run over the same window is idempotent and the
static export stays byte-identical). Ungrouped articles have no row.
"""
from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import numpy as np

logger = logging.getLogger(__name__)

STORY_WINDOW_HOURS = 48
STORY_MIN_SIMILARITY = 0.80
# Extraction sometimes returns a headline as the "brand" (idw press releases:
# "Neue Studie grenzt Zeitfenster ... ein"). Keys longer than this are not a
# brand and would only bucket unrelated articles together.
BRAND_KEY_MAX_WORDS = 4
_BRAND_STRIP = re.compile(r"[\s\.,;:!?'\"“”‘’()\[\]]+$|^[\s\.,;:!?'\"“”‘’()\[\]]+")
_WS = re.compile(r"\s+")


def brand_keys(brands) -> list[str]:
    """Normalised brand keys of one article: lower-cased, whitespace-collapsed,
    edge punctuation stripped, de-duplicated; headline-like values dropped."""
    if isinstance(brands, str):
        try:
            brands = json.loads(brands)
        except ValueError:
            brands = [brands]
    out: list[str] = []
    for b in brands or []:
        if not isinstance(b, str):
            continue
        k = _WS.sub(" ", _BRAND_STRIP.sub("", b)).strip().lower()
        if len(k) < 2 or len(k.split(" ")) > BRAND_KEY_MAX_WORDS:
            continue
        if k not in out:
            out.append(k)
    return out


@dataclass
class Article:
    id: int
    date: datetime
    keys: list[str]
    vec: np.ndarray                      # L2-normalised
    source_name: str | None = None
    title: str | None = None


@dataclass
class Story:
    lead_id: int
    member_ids: list[int]                # lead first, then by date, id
    brand_key: str
    sims: dict[int, float] = field(default_factory=dict)   # member -> cosine to lead


class _UnionFind:
    def __init__(self):
        self.parent: dict[int, int] = {}

    def find(self, x: int) -> int:
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)


def group_stories(articles: list[Article], *, window_hours: float = STORY_WINDOW_HOURS,
                  min_similarity: float = STORY_MIN_SIMILARITY) -> list[Story]:
    """Apply the rule to a set of articles and return the groups of size >= 2.

    Pure function: no DB. Pairs are only compared inside a brand-key bucket
    (any shared key), so the cost is sum(bucket^2) — the biggest measured
    bucket is a keynote day with 73 articles.
    """
    by_id = {a.id: a for a in articles}
    buckets: dict[str, list[Article]] = defaultdict(list)
    for a in articles:
        for k in a.keys:
            buckets[k].append(a)
    uf = _UnionFind()
    pair_key: dict[tuple[int, int], str] = {}
    window = timedelta(hours=window_hours)
    for key, group in buckets.items():
        if len(group) < 2:
            continue
        group = sorted(group, key=lambda a: (a.date, a.id))
        M = np.vstack([a.vec for a in group])
        S = M @ M.T
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                if group[j].date - group[i].date > window:
                    break                              # sorted by date
                if S[i, j] >= min_similarity:
                    uf.union(group[i].id, group[j].id)
                    pair_key.setdefault((group[i].id, group[j].id), key)
    members: dict[int, list[int]] = defaultdict(list)
    for a in articles:
        if a.id in uf.parent:
            members[uf.find(a.id)].append(a.id)
    stories: list[Story] = []
    for ids in members.values():
        if len(ids) < 2:
            continue
        ordered = sorted(ids, key=lambda i: (by_id[i].date, i))
        lead = by_id[ordered[0]]
        # the brand key that joined the lead to its first follower names the story
        bk = next((pair_key.get((min(lead.id, o), max(lead.id, o)))
                   for o in ordered[1:] if (min(lead.id, o), max(lead.id, o)) in pair_key),
                  None) or (lead.keys[0] if lead.keys else "")
        sims = {o: float(lead.vec @ by_id[o].vec) for o in ordered[1:]}
        stories.append(Story(lead_id=lead.id, member_ids=ordered, brand_key=bk, sims=sims))
    stories.sort(key=lambda s: s.lead_id)
    return stories


# ----------------------------------------------------------------- DB side
def _parse_vec(v) -> np.ndarray | None:
    if v is None:
        return None
    if isinstance(v, (bytes, bytearray)):
        arr = np.frombuffer(v, dtype=np.float32)
    elif isinstance(v, str):
        arr = np.array(v.strip("[]").split(","), dtype=np.float32)
    else:
        arr = np.asarray(v, dtype=np.float32)
    n = float(np.linalg.norm(arr))
    return arr / n if n > 0 else None


def load_window(conn, since: datetime, until: datetime | None = None) -> list[Article]:
    """Published articles with brand + 1024-dim vector whose sort_date lies in
    [since, until]. Called with a window that OVERLAPS the previous run by the
    story window, so groups spanning the boundary are seen whole."""
    params: list = [since]
    sql = ("SELECT id, sort_date, brands, embedding_1024::text AS v, source_name, title_en "
           "FROM trends WHERE status = 'published' AND sort_date >= ? "
           "AND embedding_1024 IS NOT NULL AND brands IS NOT NULL")
    if until is not None:
        sql += " AND sort_date <= ?"
        params.append(until)
    rows = conn.execute(sql, params).fetchall()
    out: list[Article] = []
    for r in rows:
        rid, d, brands, v, sn, title = (r["id"], r["sort_date"], r["brands"], r["v"],
                                        r["source_name"], r["title_en"]) if isinstance(r, dict) \
            else (r[0], r[1], r[2], r[3], r[4], r[5])
        keys = brand_keys(brands)
        vec = _parse_vec(v)
        if not keys or vec is None:
            continue
        if isinstance(d, str):
            d = datetime.fromisoformat(d.replace("Z", "+00:00"))
        out.append(Article(id=rid, date=d, keys=keys, vec=vec, source_name=sn, title=title))
    return out


def write_stories(conn, stories: list[Story], article_ids: list[int], computed_at: datetime) -> int:
    """Replace the rows of every article in the window with the fresh grouping.
    Articles that left a group lose their row; story_id = lead id keeps the
    result stable across runs. Returns the number of member rows written."""
    if article_ids:
        conn.execute("DELETE FROM trend_stories WHERE trend_id = ANY(?)", (article_ids,)) \
            if _is_pg(conn) else _delete_sqlite(conn, article_ids)
    rows = []
    for s in stories:
        for m in s.member_ids:
            rows.append((m, s.lead_id, s.lead_id, s.brand_key,
                         1.0 if m == s.lead_id else s.sims.get(m), computed_at))
    if rows:
        conn.executemany(
            "INSERT INTO trend_stories (trend_id, story_id, lead_trend_id, brand_key, similarity, computed_at) "
            "VALUES (?, ?, ?, ?, ?, ?)", rows)
    conn.commit()
    return len(rows)


def _is_pg(conn) -> bool:
    return hasattr(conn, "_conn")


def _delete_sqlite(conn, ids: list[int]) -> None:
    for i in range(0, len(ids), 500):
        chunk = ids[i:i + 500]
        conn.execute(f"DELETE FROM trend_stories WHERE trend_id IN ({','.join('?' * len(chunk))})", chunk)


def summarize(stories: list[Story], n_articles: int) -> dict:
    sizes = [len(s.member_ids) for s in stories]
    covered = sum(sizes)
    return {
        "articles_considered": n_articles,
        "groups": len(stories),
        "articles_in_groups": covered,
        "followers": covered - len(stories),
        "follower_share": round((covered - len(stories)) / n_articles, 4) if n_articles else 0.0,
        "size_hist": {str(k): sizes.count(k) for k in sorted(set(sizes))[:8]},
        "largest": sorted(({"lead_id": s.lead_id, "size": len(s.member_ids), "brand": s.brand_key}
                           for s in stories), key=lambda d: -d["size"])[:10],
    }
