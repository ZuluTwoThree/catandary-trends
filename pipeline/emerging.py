"""Emerging-nest detection: find small, dense, RECENT pockets and date them.

Companion to `pipeline.foresight`, not a replacement (Owner 2026-09-15). The
cluster layer partitions the signal space: every document lands in one of ~28
cells, so a cell is a subject area with tens of thousands of members. A trend is
the opposite shape — a small, tight pocket that most of the corpus does not
belong to, and whose evidence is young. This module looks for that shape and
answers the only question that separates a trend from a topic:

    has this existed before, and if so, how much?

Two stages:

1. **Detect.** Cut a recent slice of the space finely (k-means with k in the
   hundreds), then keep only cells that are tight enough and big enough, and
   merge cells whose centres are near-duplicates. Everything else is noise —
   typically 85-90 % of the slice. Measured alternatives (2026-09-15, 314k docs
   over 90 days): HDBSCAN with leaf selection on a PCA-50 projection finds the
   same shape (58 nests, 93 % noise, median 44 docs) but needs 104 s for a
   60,000-row SAMPLE and scales superlinearly, so it never sees the whole slice;
   fine k-means covers all 314k in 40 s. HDBSCAN with the default (excess of
   mass) selection is useless here — it returns two blobs of 6,000 and 12,000.

2. **Date.** Stream the ENTIRE archive past the nest centroids and count, per
   month, how many documents of any age look like each nest. That history is
   what makes "new" measurable: a nest whose lookalikes start in 2009 is a
   subject area; one whose lookalikes start 11 months ago is a candidate.

Nothing here writes to the DB; `pipeline.emerging_snapshot` persists.
"""
from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime

import numpy as np
from sklearn.cluster import MiniBatchKMeans

from pipeline.foresight import (LOAD_CHUNK, build_matrix, distinctive_terms,
                                iter_signals, month_key, unique_label, _norm_tag)

logger = logging.getLogger("emerging")

# --- detection -------------------------------------------------------------

# One cell per ~400 documents, bounded. Fine enough that a tight cell is a
# specific thing, coarse enough that k-means stays a matter of seconds.
DOCS_PER_CELL = 400
MIN_CELLS = 200
MAX_CELLS = 1200

# A cell is a nest only if its members really sit together. 0.75 mean cosine is
# the measured knee: at k=800 over 90 days it keeps 111 of 800 cells holding
# 13 % of the documents (median 266 docs); 0.70 keeps 364 cells and 58 %, which
# is back to subject areas; 0.80 keeps 31 cells and 2 %.
MIN_COHESION = 0.75
MIN_NEST_SIZE = 30
# Two centres this similar describe the same pocket; the larger one absorbs it.
MERGE_SIM = 0.92

# --- history ---------------------------------------------------------------

# A document counts as a lookalike of a nest at this cosine. Per nest the
# threshold is its own 25th-percentile member similarity, never below this
# floor — a loose nest must not swallow half the archive.
HIST_SIM_FLOOR = 0.70
MIN_HIST_HITS = 3          # months below this are noise, not a first appearance
NOVELTY_WINDOW_MONTHS = 6  # "recent" for the novelty lift
ACCEL_RECENT_MONTHS = 3
ACCEL_BASE_MONTHS = 9      # the nine months before the recent three

# A nest can only be dated against sources that were already being read. The
# first FOOD run (2026-09-15) filled its top ten with agronomy pockets "first
# seen 3 to 5 months ago" — every one of them from journal sweeps that started
# delivering 3 to 5 months ago. Their age measured our subscriptions, not the
# world. A source counts as established once it has been in the corpus this
# long; the share of a nest carried by established sources is reported, and the
# card says so when it is low.
ESTABLISHED_AFTER_MONTHS = 24


# Words that never identify a pocket. Small on purpose: the fallback only runs
# when a nest carries NO usable tags at all, which happens for bulk-ingested
# research signals that never passed the classification stages.
TITLE_STOPWORDS = {
    "the", "and", "for", "with", "from", "that", "this", "are", "was", "were",
    "using", "used", "use", "via", "into", "based", "study", "studies", "new",
    "novel", "review", "analysis", "approach", "method", "methods", "results",
    "effect", "effects", "role", "case", "data", "model", "models", "system",
    "systems", "research", "paper", "report", "toward", "towards", "through",
    "between", "among", "their", "its", "can", "may", "our", "you", "your",
    "how", "what", "why", "who", "when", "where", "not", "все", "des", "der",
    "und", "für", "von", "mit", "les", "del", "las", "por", "una", "development",
}


def title_terms(titles: list[str], top: int = 3, min_share: float = 0.15) -> list[str]:
    """Frequent, distinctive words from a nest's titles.

    Only used when a nest has no usable tags. The first real run (2026-09-15)
    produced a 651-document nest called "Nest 14" because every member came
    from a bulk research sweep that never reached the tagging stage — the
    titles said "E8 Quantum Lattice" plainly enough."""
    counts: Counter = Counter()
    first_seen: dict[str, int] = {}
    for t in titles:
        seen: dict[str, None] = {}          # insertion-ordered, unlike a set
        for w in "".join(ch.lower() if ch.isalnum() else " " for ch in (t or "")).split():
            if len(w) < 3 or w in TITLE_STOPWORDS or w.isdigit():
                continue
            seen.setdefault(w, None)
            first_seen.setdefault(w, len(first_seen))
        counts.update(seen.keys())
    floor = max(2, int(len(titles) * min_share))
    # Ties are common when titles repeat a phrase; break them by where the word
    # first appeared, never by set iteration order — a label must be the same on
    # every run, and `set` ordering depends on the hash seed.
    ranked = sorted((w for w, n in counts.items() if n >= floor),
                    key=lambda w: (-counts[w], first_seen[w]))
    return ranked[:top]


def pick_cells(n_docs: int) -> int:
    """Cells for a slice of n_docs.

    DOCS_PER_CELL is a COMPUTE budget, not a principle: k-means assignment costs
    n*k*d, so the global slice can only afford a coarse partition and therefore
    only finds the larger pockets. Small scopes can afford ~40 documents per
    cell, and they need it — DESIGN with 3,518 documents had exactly one cell
    above the density gate at 58 cells and twenty-two at 120 (measured
    2026-09-15). The floor scales with the slice so a thin vertical is not
    blind, and stops at MIN_CELLS so a mid-sized one does not get absurd."""
    floor = max(8, min(MIN_CELLS, n_docs // 40))
    return int(max(floor, min(MAX_CELLS, n_docs // DOCS_PER_CELL)))


def detect_nests(X: np.ndarray, k: int | None = None, seed: int = 42,
                 min_cohesion: float = MIN_COHESION,
                 min_size: int = MIN_NEST_SIZE) -> list[dict]:
    """Fine partition → keep the tight cells → merge near-duplicates.

    Returns [{members: np.ndarray of row indices, centroid, cohesion, radius_p25}]
    sorted by size, largest first. X must be L2-normalized (build_matrix does).
    """
    n = X.shape[0]
    k = k or pick_cells(n)
    k = min(k, max(2, n // 2))
    km = MiniBatchKMeans(n_clusters=k, batch_size=4096, n_init=3,
                         random_state=seed).fit(X)
    labels = km.labels_
    centers = km.cluster_centers_
    centers = centers / np.clip(np.linalg.norm(centers, axis=1, keepdims=True), 1e-9, None)

    # Quality gate first, SIZE gate last. A real pocket that the fine partition
    # happened to slice into a dozen slivers would otherwise be thrown away
    # sliver by sliver before it ever got the chance to be put back together.
    cand: list[dict] = []
    for cid in range(k):
        members = np.flatnonzero(labels == cid)
        if members.size < 3:                 # degenerate cell, no density to judge
            continue
        sims = X[members] @ centers[cid]
        cohesion = float(sims.mean())
        if cohesion < min_cohesion:
            continue
        cand.append({
            "members": members,
            "centroid": centers[cid].astype(np.float32),
            "cohesion": round(cohesion, 4),
            "radius_p25": float(np.percentile(sims, 25)),
        })
    cand.sort(key=lambda c: -c["members"].size)

    # Merge near-duplicate centres: fine k-means happily splits one pocket in two.
    kept: list[dict] = []
    for c in cand:
        dup = next((k2 for k2 in kept if float(k2["centroid"] @ c["centroid"]) >= MERGE_SIM), None)
        if dup is None:
            kept.append(c)
            continue
        merged = np.union1d(dup["members"], c["members"])
        cen = X[merged].mean(axis=0)
        cen = cen / max(float(np.linalg.norm(cen)), 1e-9)
        sims = X[merged] @ cen
        dup["members"] = merged
        dup["centroid"] = cen.astype(np.float32)
        dup["cohesion"] = round(float(sims.mean()), 4)
        dup["radius_p25"] = float(np.percentile(sims, 25))
    kept = [c for c in kept if c["members"].size >= min_size]
    kept.sort(key=lambda c: -c["members"].size)
    return kept


def describe_nests(nests: list[dict], rows: list[dict]) -> None:
    """Attach label, tags, sources, verticals and representatives, in place."""
    counters = []
    for nest in nests:
        members = [rows[i] for i in nest["members"]]
        counters.append(Counter(t for m in members for t in (m["tags"] or [])))
    tag_df: Counter = Counter()
    for tc in counters:
        for norm in {_norm_tag(t) for t, _ in tc.most_common(20)}:
            if norm:
                tag_df[norm] += 1
    used: set[str] = set()
    for nest, tc in zip(nests, counters):
        members = [rows[i] for i in nest["members"]]
        size = len(members)
        terms = distinctive_terms(tc, size, tag_df, max(len(nests), 1))
        if not terms:
            terms = title_terms([m["title_en"] or "" for m in members])
        nest["label"] = unique_label(terms, used, fallback=f"Nest {len(used) + 1}")
        used.add(nest["label"])
        nest["size"] = size
        nest["top_tags"] = [t for t, _ in tc.most_common(12)]
        # How much of this nest ever passed the classification stages. A nest
        # at 0 consists purely of bulk-ingested signals that no stage of the
        # pipeline ever looked at — worth knowing before believing it.
        nest["tagged_share"] = round(
            sum(1 for m in members if m["tags"]) / size, 4) if size else 0.0
        src = Counter(m["source_name"] for m in members if m["source_name"])
        nest["source_counts"] = dict(src)   # consumed by score_nests, not stored
        nest["n_sources"] = len(src)
        nest["top_source"], top_n = src.most_common(1)[0] if src else (None, 0)
        nest["top_source_share"] = round(top_n / size, 4) if size else 0.0
        nest["verticals"] = [v for v, _ in Counter(
            m["primary_vertical"] for m in members if m["primary_vertical"]).most_common(3)]
        # Representatives: newest first, one per source (same rule as the
        # cluster cards — the centre-most member is the blandest one).
        order = sorted(range(size),
                       key=lambda j: (members[j]["published_date"] or ""), reverse=True)
        reps, seen = [], set()
        for j in order:
            s = members[j]["source_name"] or ""
            if s and s in seen:
                continue
            if s:
                seen.add(s)
            reps.append(members[j])
            if len(reps) >= 5:
                break
        nest["rep_trend_ids"] = [r["id"] for r in reps]
        nest["rep_titles"] = [(r["title_en"] or "")[:120] for r in reps]


# --- history ---------------------------------------------------------------

def scan_history(centroids: np.ndarray, thresholds: np.ndarray,
                 status: str = "signal,published", vertical: str | None = None,
                 dim1024: bool = True, since: str | None = None,
                 tag_windows: tuple[str, str] | None = None,
                 chunk_size: int = LOAD_CHUNK,
                 progress=None) -> dict:
    """Count, per month, how many archive documents look like each nest.

    centroids: (n_nests, dim) L2-normalized. thresholds: (n_nests,) cosine
    cut-offs. Streams the corpus, so memory is one chunk regardless of size.

    tag_windows: ('YYYY-MM', 'YYYY-MM') — an OLD month range whose tag counts
    are collected alongside, so a nest can be asked whether its vocabulary
    existed back then.

    Returns {months, totals (corpus docs per month), hits (n_nests × n_months),
    old_tags, recent_tags, source_first (first corpus month per source), scanned}.
    """
    hits_by_month: dict[str, np.ndarray] = {}
    totals: Counter = Counter()
    source_first: dict[str, str] = {}
    old_tags: Counter = Counter()
    recent_tags: Counter = Counter()
    n_nests = centroids.shape[0]
    scanned = 0
    C = np.ascontiguousarray(centroids.T)  # (dim, n_nests)

    for batch in iter_signals(status=status, vertical=vertical, dim1024=dim1024,
                              since=since, chunk_size=chunk_size):
        X = build_matrix(batch)
        S = X @ C                                   # (m, n_nests)
        above = S >= thresholds[None, :]
        for i, r in enumerate(batch):
            mk = month_key(r["published_date"])
            if not mk:
                continue
            totals[mk] += 1
            src = r["source_name"] or ""
            if src and (src not in source_first or mk < source_first[src]):
                source_first[src] = mk
            row = above[i]
            if row.any():
                arr = hits_by_month.get(mk)
                if arr is None:
                    arr = np.zeros(n_nests, dtype=np.int32)
                    hits_by_month[mk] = arr
                arr += row
            if tag_windows:
                bucket = (old_tags if tag_windows[0] <= mk <= tag_windows[1]
                          else recent_tags)
                for t in (r["tags"] or []):
                    norm = _norm_tag(t)
                    if norm:
                        bucket[norm] += 1
        scanned += len(batch)
        del X, S, above, batch
        if progress and scanned % (chunk_size * 25) == 0:
            progress(scanned)

    months = sorted(set(totals) | set(hits_by_month))
    hits = np.zeros((n_nests, len(months)), dtype=np.int32)
    for j, m in enumerate(months):
        arr = hits_by_month.get(m)
        if arr is not None:
            hits[:, j] = arr
    return {
        "months": months,
        "totals": [totals[m] for m in months],
        "hits": hits,
        "old_tags": old_tags,
        "recent_tags": recent_tags,
        "source_first": source_first,
        "scanned": scanned,
    }


def _months_back(months: list[str], n: int) -> set[int]:
    return set(range(max(0, len(months) - n), len(months)))


def score_nests(nests: list[dict], history: dict, now: datetime | None = None) -> None:
    """Attach the emergence metrics to each nest, in place.

    * first_month / age_months — the first month with at least MIN_HIST_HITS
      lookalikes. This is the measurement the cluster layer cannot make.
    * novelty_lift — the share of a nest's all-time lookalikes that falls in the
      recent window, divided by the share the CORPUS puts there. 1.0 means the
      nest is spread exactly like the archive; 3.0 means three times as
      concentrated in the present as the corpus at large. Corpus-normalized, so
      our own intake growth cannot inflate it.
    * accel — recent monthly rate over the rate of the preceding months, both
      as a share of the corpus in those months.
    * new_terms — nest tags that were rare in the old window and are common now.
    * established_share — how much of the nest comes from sources that were
      already being read two years ago. Near zero means its age is a fact about
      our subscriptions, not about the world.
    """
    months = history["months"]
    totals = np.asarray(history["totals"], dtype=np.float64)
    hits = history["hits"]
    if not months:
        for n in nests:
            n.update(history_months=[], history_hits=[], first_month=None,
                     age_months=None, novelty_lift=None, accel=None,
                     hits_total=0, hits_recent=0, new_terms=[],
                     established_share=0.0)
        return

    recent = sorted(_months_back(months, NOVELTY_WINDOW_MONTHS))
    acc_recent = sorted(_months_back(months, ACCEL_RECENT_MONTHS))
    acc_base = sorted(set(_months_back(months, ACCEL_RECENT_MONTHS + ACCEL_BASE_MONTHS))
                      - set(acc_recent))
    corpus_all = float(totals.sum()) or 1.0
    corpus_recent_share = float(totals[recent].sum()) / corpus_all
    corpus_acc_recent = float(totals[acc_recent].sum()) or 1.0
    corpus_acc_base = float(totals[acc_base].sum()) if acc_base else 0.0

    source_first: dict = history.get("source_first") or {}
    # the month a source must predate to count as established
    ref = months[-1]
    ry, rm = int(ref[:4]), int(ref[5:7])
    rm -= ESTABLISHED_AFTER_MONTHS
    while rm <= 0:
        rm += 12
        ry -= 1
    established_cut = f"{ry:04d}-{rm:02d}"

    old_tags: Counter = history["old_tags"]
    recent_tags: Counter = history["recent_tags"]
    old_total = max(sum(old_tags.values()), 1)
    recent_total = max(sum(recent_tags.values()), 1)

    for i, nest in enumerate(nests):
        series = hits[i]
        total = int(series.sum())
        first_idx = next((j for j in range(len(months)) if series[j] >= MIN_HIST_HITS), None)
        first_month = months[first_idx] if first_idx is not None else None
        age = (len(months) - first_idx) if first_idx is not None else None

        h_recent = int(series[recent].sum())
        nest_recent_share = h_recent / total if total else 0.0
        lift = (nest_recent_share / corpus_recent_share) if corpus_recent_share else None

        r_rate = float(series[acc_recent].sum()) / corpus_acc_recent
        b_rate = (float(series[acc_base].sum()) / corpus_acc_base) if corpus_acc_base else 0.0
        accel = (r_rate / b_rate) if b_rate > 0 else None

        counts = nest.get("source_counts") or {}
        total_members = sum(counts.values())
        established = sum(n for src, n in counts.items()
                          if source_first.get(src, "9999-99") <= established_cut)
        established_share = (established / total_members) if total_members else 0.0

        new_terms = []
        for t in nest["top_tags"][:8]:
            norm = _norm_tag(t)
            if not norm:
                continue
            old_rate = old_tags.get(norm, 0) / old_total
            new_rate = recent_tags.get(norm, 0) / recent_total
            if new_rate > 0 and (old_rate == 0 or new_rate / old_rate >= 3.0):
                new_terms.append(t)

        nest.update(
            history_months=months,
            history_hits=[int(x) for x in series],
            first_month=first_month,
            age_months=age,
            hits_total=total,
            hits_recent=h_recent,
            established_share=round(established_share, 4),
            novelty_lift=round(lift, 3) if lift is not None else None,
            accel=round(accel, 3) if accel is not None else None,
            new_terms=new_terms,
        )
