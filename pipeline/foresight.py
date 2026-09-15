"""Foresight core — shared signal-space clustering + trajectory analysis.

Extracted from scripts/cluster_trajectory_demo.py and scripts/propose_mega_trends.py
so the same engine drives three consumers (see issue #2):

  1. foresight_snapshot.py  — persists cluster/trajectory artifacts for the frontend
  2. the scoped discoverers — per-vertical / per-lead-time-tier proposal runs
  3. the distillation discovery loop — periodic LLM pass over cluster centers

The two original scripts remain unchanged for now (they are exercised by ongoing
production analysis); they migrate onto this core in a later step.

Design constraints (measured on the 455k-signal pool):
  - Embeddings are read as raw float32 BLOBs and decoded straight into a
    preallocated numpy matrix via np.frombuffer — never into Python float lists
    (the Stage-5 OOM pattern: ~46 GB at 400k signals).
  - Above ~100k points KMeans switches to MiniBatchKMeans (rows are
    L2-normalized, so Euclidean k-means ≈ spherical/cosine k-means).
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime

import numpy as np
from sklearn.cluster import KMeans, MiniBatchKMeans
from sklearn.metrics import silhouette_score

from pipeline import db as db_mod
from pipeline.db import get_connection

# Tags that make bad cluster labels (geographies, signal types, generic terms).
GENERIC_TAGS = {
    "germany", "usa", "china", "europe", "uk", "us", "eu", "france", "india",
    "regulation", "government regulation", "government policy", "economic_policy",
    "product_launch", "product launch", "consumer_behavior", "consumer behavior",
    "funding", "research", "market_shift", "partnership", "innovation",
    "sustainability", "policy", "data_privacy", "data privacy",
}

# SoV-delta thresholds (percentage points early→late) for the momentum tag.
MOMENTUM_RISING_PP = 1.0
MOMENTUM_DECLINING_PP = -1.0

# …plus a relative floor. Re-running FASHION with a different KMeans seed moved
# mid-sized clusters by 1–3 pp purely because the cluster boundaries landed
# elsewhere (stability check 2026-09-15: the extremes kept their direction under
# seed AND window changes, the middle did not). A large cluster must therefore
# move by a tenth of its own share, not just by a percentage point, before it
# gets a badge. On the 2026-09-15 runs this changes no classification — the pp
# gate binds first at today's cluster sizes — it bounds a known failure mode.
MOMENTUM_MIN_RELATIVE = 0.10

# Momentum is judged inside the most recent N months only. The corpus mixes
# acquisition eras (patent/research back-file dominates 2002-2020, RSS the
# recent years); an all-history SoV window measures that source-composition
# shift, not the trend (validation 2026-07-02 caught -60pp "declines" that
# were just the patent ingest window ending).
MOMENTUM_WINDOW_MONTHS = 36

# …but a recent window is NOT automatically composition-stable, and by
# 2026-09 it plainly was not: inside the last 36 months the mix moved from
# 49 % trade media / 28 % research (2023) to 19 % / 56 % (2026), and monthly
# volume went from ~10k to 129k as the source count grew 226 → 560. The
# early-vs-late share comparison was therefore measuring our own onboarding.
# Fix: only sources that delivered in BOTH the early and the late window get a
# voice in the share maths — a fixed panel, the way a price index holds its
# basket. Raw counts (size, n, n_sources, the monthly `n` series) stay
# unfiltered for display honesty; only `share`/`sov_delta_pp` use the panel.
# If the panel would cover less than MIN_COHORT_COVERAGE of the two windows'
# rows (tiny or freshly-built corpora), it is dropped and every source counts
# again — reported as cohort_applied=False rather than silently.
MIN_COHORT_COVERAGE = 0.25

# Representatives: a signal must be at least this central (percentile of the
# cluster's cosine-to-centroid) to qualify, and among those the NEWEST win,
# one per source. Centroid-nearest alone returns the blandest, often years-old
# member — five generic patent titles for an 83k cluster (audit 2026-09-15).
REP_CENTRALITY_PCT = 60
REP_MIN_MEMBERS = 20      # below this, centrality percentile is meaningless

MINIBATCH_ABOVE = 100_000  # switch to MiniBatchKMeans above this many points
LOAD_CHUNK = 20_000        # rows per keyset page in load_signals (memory, not speed)


# ---------------------------------------------------------------- data loading

# Canonical lead-time tier → source mapping (issue #2/#3). Preprint servers are
# source_type='api' but belong to the science tier; patents and funding share
# 'api' and are told apart by source name. LIKE patterns are bound params —
# literal % in the SQL breaks under the ?→%s psycopg2 wrapper.
TIER_FILTERS: dict[str, tuple[str, list[str]]] = {
    "science": ("(s.source_type = 'research' OR t.source_name LIKE ?)",
                ["%Preprints%"]),
    "patent": ("(t.source_name LIKE ? OR t.source_name LIKE ?)",
               ["Google Patents%", "EPO %"]),
    "funding": ("(" + " OR ".join(["t.source_name LIKE ?"] * 5) + ")",
                ["NIH RePORTER%", "NSF %", "OpenAIRE%", "UKRI%", "SEC Form D%"]),
    "market": ("s.source_type IN ('trade_media', 'press_wire', 'brand')", []),
}


def iter_signals(status: str = "signal,published", vertical: str | None = None,
                 source_like: str | None = None, limit: int = 0,
                 since: str | None = None, until: str | None = None,
                 dim1024: bool = False, tier: str | None = None,
                 chunk_size: int = LOAD_CHUNK):
    """Yield embedded trends in keyset-paginated chunks (list[dict] per chunk).

    Same filters as `load_signals`, which is just this drained into one list.
    Streaming matters for passes that walk the WHOLE archive without holding it:
    the emerging-nest history scan multiplies every chunk against the nest
    centroids and keeps only counts, so 1.75M rows cost one chunk of memory.

    status: comma list or 'all'. vertical: primary_vertical or None/'ALL' for no
    filter. source_like: comma-separated substrings OR-matched against
    source_name (e.g. 'NSF,NIH,OpenAIRE,UKRI' = the funding pool).
    tier: canonical lead-time tier scope (TIER_FILTERS key) — the maintained
    replacement for hand-rolled source_like tier pools.
    since/until: ISO date bounds on published_date (for time-window runs).
    dim1024: load the Matryoshka 1024-dim column instead of the full 4096 —
    4× less text to parse/hold, which is what makes the full 1.1M-signal space
    tractable in memory; KMeans centroids are ~identical on the truncation.
    Embeddings are kept as raw bytes in row['_emb'] for build_matrix().
    """
    where: list[str] = []
    params: list = []
    if tier:
        if tier not in TIER_FILTERS:
            raise ValueError(f"unknown tier {tier!r} (known: {sorted(TIER_FILTERS)})")
        cond, tier_params = TIER_FILTERS[tier]
        where.append(cond)
        params += tier_params
    if status and status.lower() != "all":
        sts = [s.strip() for s in status.split(",")]
        where.append(f"t.status IN ({','.join('?' * len(sts))})")
        params += sts
    if vertical and vertical.upper() != "ALL":
        where.append("t.primary_vertical = ?")
        params.append(vertical)
    emb_field = "embedding_1024" if dim1024 else "embedding"
    where.append(f"t.{emb_field} IS NOT NULL")
    if source_like:
        pats = [p.strip() for p in source_like.split(",") if p.strip()]
        if pats:
            where.append("(" + " OR ".join(["t.source_name LIKE ?"] * len(pats)) + ")")
            params += [f"%{p}%" for p in pats]
    if since:
        where.append("r.published_date >= ?")
        params.append(since)
    if until:
        where.append("r.published_date < ?")
        params.append(until)
    # Bogus future dates from malformed RSS/API records (observed up to 2029)
    # would stretch the month axis and hollow out the recent-window analysis.
    # Rows with NULL dates stay in (they cluster; they just carry no trajectory).
    # CURRENT_TIMESTAMP is portable (SQLite + Postgres); datetime('now') is not.
    where.append("(r.published_date IS NULL OR r.published_date <= CURRENT_TIMESTAMP)")
    # Under Postgres the embedding is a pgvector — cast to text and parse; under
    # SQLite it is the raw float32 blob.
    emb_col = f"t.{emb_field}::text" if db_mod.USE_POSTGRES else f"t.{emb_field}"
    # The join is unconditional since 2026-09-15: every row carries its
    # source_type so `pipeline.tiers.tier_of` can place it on a lead-time tier
    # while streaming. sources is a 600-row table, so this is a hash join.
    src_join = " LEFT JOIN sources s ON r.source_id = s.id"
    # Keyset pagination on t.id instead of one fetchall: under Postgres the
    # vector arrives as TEXT (~10 KB per 1024-dim row, ~40 KB at 4096), and a
    # single result set over 1.75M rows held every string at once — the
    # 2026-09-15 recompute from the desk reached 56 GB and the OOM killer
    # took the frontend service down with it. Each chunk is parsed to raw
    # float32 bytes immediately, so only 4 KB/row stays resident.
    base_where = " AND ".join(where)
    seen = 0
    last_id = 0
    with get_connection() as c:
        while True:
            chunk = min(chunk_size, limit - seen) if limit else chunk_size
            if chunk <= 0:
                break
            sql = ("SELECT t.id, t.title_en, t.mega_trend, t.tags, t.source_name, "
                   "       t.primary_vertical, t.status, t.source_url, "
                   "       t.brands, t.companies, s.source_type, "
                   f"       r.published_date, {emb_col} AS embedding "
                   f"FROM trends t JOIN raw_entries r ON t.raw_entry_id = r.id{src_join} "
                   f"WHERE {base_where} AND t.id > ? ORDER BY t.id LIMIT ?")
            rows = c.execute(sql, [*params, last_id, chunk]).fetchall()
            if not rows:
                break
            batch: list[dict] = []
            for raw in rows:
                r = dict(raw)
                last_id = r["id"]
                emb = db_mod._vector_to_bytes(r["embedding"])
                if not isinstance(emb, (bytes, bytearray)) or len(emb) < 4:
                    continue
                r["_emb"] = bytes(emb)
                r["embedding"] = None  # drop the text/blob reference, keep memory flat
                if isinstance(r["published_date"], datetime):
                    r["published_date"] = r["published_date"].isoformat()
                for field in ("tags", "brands", "companies"):
                    try:
                        val = r.get(field)
                        r[field] = val if isinstance(val, list) else (json.loads(val) if val else [])
                    except Exception:
                        r[field] = []
                batch.append(r)
            seen += len(rows)
            del rows
            if batch:
                yield batch


def load_signals(status: str = "signal,published", vertical: str | None = None,
                 source_like: str | None = None, limit: int = 0,
                 since: str | None = None, until: str | None = None,
                 dim1024: bool = False, tier: str | None = None) -> list[dict]:
    """All matching embedded trends in one list (see `iter_signals` for filters)."""
    out: list[dict] = []
    for batch in iter_signals(status=status, vertical=vertical, source_like=source_like,
                              limit=limit, since=since, until=until, dim1024=dim1024,
                              tier=tier):
        out.extend(batch)
    return out


def source_weights_from_pass_rate(target: float = 0.5, floor: float = 0.2,
                                  min_processed: int = 50) -> dict[str, float]:
    """Build {source_name: weight} from each source's signal pass-rate (#2 phase 2).

    weight = clamp(pass_rate / target, floor, 1.0): a source that converts
    `target` (default 50%) or more of its processed entries into signals gets
    full voice; noisier feeds are down-weighted, but never below `floor` (they
    still count, just less). Sources with < min_processed entries are left at
    1.0 (too little evidence to penalise). Read-only aggregate over raw_entries
    joined to the trends they became — the same measure source_signal_yield.py
    reports, folded into the foresight maths instead of only being printed.
    """
    sql = (
        "SELECT s.name AS source, "
        "  COUNT(*) FILTER (WHERE r.processed) AS processed, "
        "  COUNT(*) FILTER (WHERE EXISTS "
        "     (SELECT 1 FROM trends t WHERE t.raw_entry_id = r.id)) AS signals "
        "FROM raw_entries r JOIN sources s ON r.source_id = s.id "
        "WHERE s.name IS NOT NULL GROUP BY s.name"
    )
    weights: dict[str, float] = {}
    with get_connection() as c:
        for row in c.execute(sql).fetchall():
            proc = row["processed"] or 0
            if proc < min_processed:
                continue
            pr = (row["signals"] or 0) / proc
            weights[row["source"]] = float(min(1.0, max(floor, pr / target)))
    return weights


def build_matrix(rows: list[dict]) -> np.ndarray:
    """Raw float32 bytes → L2-row-normalized matrix; frees each row's bytes."""
    dim = len(rows[0]["_emb"]) // 4
    X = np.empty((len(rows), dim), dtype=np.float32)
    for i, r in enumerate(rows):
        X[i] = np.frombuffer(r["_emb"], dtype=np.float32)
        r["_emb"] = None
    X /= np.clip(np.linalg.norm(X, axis=1, keepdims=True), 1e-9, None)
    return X


# ------------------------------------------------------------------ clustering

def pick_k(X: np.ndarray, lo: int, hi: int) -> int:
    """Silhouette-picked k on a sample (deterministic seeds)."""
    n = X.shape[0]
    if n < 60:
        return max(2, min(lo, n // 8))
    sample = X if n <= 4000 else X[np.random.default_rng(42).choice(n, 4000, replace=False)]
    best_k, best_s = lo, -1.0
    for k in range(lo, min(hi, max(lo, n // 10)) + 1):
        labels = KMeans(n_clusters=k, n_init=4, random_state=42).fit_predict(sample)
        s = silhouette_score(sample, labels, sample_size=min(2000, len(sample)), random_state=42)
        if s > best_s:
            best_k, best_s = k, s
    return best_k


def cluster_signals(X: np.ndarray, k: int | None = None,
                    k_range: tuple[int, int] = (6, 14)) -> tuple[np.ndarray, np.ndarray, int]:
    """Spherical k-means (rows pre-normalized). Returns (labels, centroids, k)."""
    k = k or pick_k(X, *k_range)
    n = X.shape[0]
    if n > MINIBATCH_ABOVE:
        km = MiniBatchKMeans(n_clusters=k, batch_size=4096, n_init=3,
                             random_state=42).fit(X)
    else:
        km = KMeans(n_clusters=k, n_init=8 if n <= 50_000 else 3, random_state=42).fit(X)
    return km.labels_, km.cluster_centers_, k


# ------------------------------------------------------------------- analysis

def month_key(d) -> str | None:
    if not d:
        return None
    s = str(d)[:7]
    return s if len(s) == 7 and s[4] == "-" else None


# Acronyms that .title() would mangle ("AI" -> "Ai"). Display form per token.
ACRONYM_DISPLAY = {
    "ai": "AI", "ml": "ML", "ar": "AR", "vr": "VR", "xr": "XR", "llm": "LLM",
    "llms": "LLMs", "ev": "EV", "evs": "EVs", "iot": "IoT", "api": "API",
    "apis": "APIs", "ux": "UX", "ui": "UI", "5g": "5G", "6g": "6G",
    "mrna": "mRNA", "dna": "DNA", "rna": "RNA", "crispr": "CRISPR", "co2": "CO2",
    "esg": "ESG", "b2b": "B2B", "d2c": "D2C", "saas": "SaaS", "nlp": "NLP",
    "gpu": "GPU", "suv": "SUV", "hvac": "HVAC", "3d": "3D", "usa": "USA",
    # Added 2026-09-15 after the label audit produced "Nft · Blockchain",
    # "Sbir Funding · Education" and "Circular Economy · Eu Funding": the
    # geo/generic filter only drops these as STANDALONE tags, so they survive
    # inside compounds and must be cased per token here.
    "nft": "NFT", "nfts": "NFTs", "sbir": "SBIR", "eu": "EU", "uk": "UK",
    "us": "US", "sec": "SEC", "fda": "FDA", "ema": "EMA", "nasa": "NASA",
    "ipo": "IPO", "cpg": "CPG", "vc": "VC", "cbd": "CBD", "gmo": "GMO",
    "led": "LED", "uav": "UAV", "uavs": "UAVs", "sme": "SME", "smes": "SMEs",
    "ceo": "CEO", "cfo": "CFO", "gdpr": "GDPR", "ip": "IP", "pfas": "PFAS",
    "hiv": "HIV", "ncd": "NCD", "iso": "ISO", "csr": "CSR", "erp": "ERP",
    "cdmo": "CDMO", "gpus": "GPUs", "ott": "OTT", "vod": "VOD", "diy": "DIY",
}


def _norm_tag(t: str) -> str:
    """Normalize a tag for dedup/comparison: lowercase, and unify the underscore/
    hyphen/space variants ('plant_based' == 'plant-based' == 'plant based') so
    they don't produce separate labels for the same concept."""
    return (t or "").lower().replace("_", " ").replace("-", " ").strip()


def _pretty(tag_norm: str) -> str:
    """Title-case a normalized tag, keeping known acronyms uppercase."""
    return " ".join(ACRONYM_DISPLAY.get(w, w.capitalize()) for w in tag_norm.split())


def _distinct_thematic(tags: list[str]) -> list[str]:
    """Normalized, generic-filtered, variant-deduped thematic tags, in order."""
    seen: set[str] = set()
    out: list[str] = []
    for t in tags:
        if not t:
            continue
        norm = _norm_tag(t)
        if norm in GENERIC_TAGS or t.lower() in GENERIC_TAGS or norm in seen:
            continue
        seen.add(norm)
        out.append(norm)
    return out


def derive_label(tags: list[str], fallback: str = "Unlabelled cluster") -> str:
    """Human-readable label from the top thematic tags (geo/generic filtered,
    acronym-aware, variant-deduped). Frequency-ordered; see `distinctive_label`
    for the cross-cluster distinctiveness variant used by analyze()."""
    themal = _distinct_thematic(tags)
    picked = themal[:2] if themal else [tags[0].lower().replace("_", " ")] if tags else []
    if not picked:
        return fallback
    return " · ".join(_pretty(p) for p in picked)


def distinctive_terms(tag_counter: Counter, size: int, tag_df: dict[str, int],
                      n_clusters: int, top: int = 6) -> list[str]:
    """Ranked DISTINCTIVE tag stems for a cluster (tf-idf across clusters), not
    just the most frequent. Fixes the 'every FOOD cluster is Plant-Based'
    problem: a tag common to many clusters (df high) is downweighted, so each
    cluster surfaces what sets it apart (cultivated meat vs plant-based milk
    vs …). `tag_df` = number of clusters each normalized tag appears in.
    Returns normalized stems; `_pretty` turns them into display form."""
    # Sum counts of tag variants that normalize to the same concept
    # ('plant-based' + 'plant based' → one entry) before scoring.
    norm_counts: Counter = Counter()
    for tag, cnt in tag_counter.items():
        norm = _norm_tag(tag)
        if norm and norm not in GENERIC_TAGS:
            norm_counts[norm] += cnt
    scored: list[tuple[float, str]] = []
    for norm, cnt in norm_counts.items():
        tf = cnt / max(size, 1)
        idf = np.log(n_clusters / (1 + tag_df.get(norm, 0))) + 1.0  # +1 keeps it positive
        scored.append((tf * idf, norm))
    scored.sort(key=lambda x: (-x[0], x[1]))  # deterministic on ties
    return [norm for _, norm in scored[:top]]


def distinctive_label(tag_counter: Counter, size: int, tag_df: dict[str, int],
                      n_clusters: int, fallback: str = "Unlabelled cluster") -> str:
    """Two most distinctive tags as one label. Kept for callers that label a
    single cluster; `assign_labels` is the run-wide variant that also
    guarantees uniqueness."""
    picked = distinctive_terms(tag_counter, size, tag_df, n_clusters, top=2)
    if not picked:
        return derive_label([t for t, _ in tag_counter.most_common(6)], fallback)
    return " · ".join(_pretty(p) for p in picked)


def unique_label(terms: list[str], used: set[str], fallback: str) -> str:
    """A label from `terms` that no other cluster in the run carries yet.

    Two clusters of the same run used to end up with the identical label (the
    2026-09-15 FASHION run had 'Sustainable Fashion · Circular Economy' twice,
    with opposite momentum) — indistinguishable cards making contradictory
    claims. Candidates widen in a fixed order, so the same input always yields
    the same label: the top pair, then pairs reaching into the third term, then
    a triple, and only then a numbered suffix."""
    combos: list[tuple[str, ...]] = []
    if len(terms) >= 2:
        combos.append((terms[0], terms[1]))
    if len(terms) >= 3:
        combos += [(terms[0], terms[2]), (terms[1], terms[2]),
                   (terms[0], terms[1], terms[2])]
    if len(terms) >= 4:
        combos += [(terms[0], terms[3]), (terms[0], terms[1], terms[3])]
    if len(terms) == 1:
        combos.append((terms[0],))
    for combo in combos:
        label = " · ".join(_pretty(t) for t in combo)
        if label not in used:
            return label
    base = (" · ".join(_pretty(t) for t in terms[:2]) if terms else fallback)
    for n in range(2, 99):
        label = f"{base} ({n})"
        if label not in used:
            return label
    return base


def _pick_reps(members: list[dict], sims: np.ndarray, limit: int = 5) -> list[dict]:
    """Representative signals: central enough, then newest, one per source.

    Ranking purely by cosine-to-centroid returns the most AVERAGE member of the
    cluster, which in a six-figure cluster means an old, generic item — the
    2026-09-15 audit found five near-identical Google Patents titles standing
    for an 83k cluster. Centrality becomes a gate instead of the ranking: only
    members above the REP_CENTRALITY_PCT percentile qualify, and among those the
    most recent win, at most one per source so the list shows corroboration
    rather than one feed five times."""
    if len(members) == 0:
        return []
    order = np.argsort(-sims)
    if len(members) < REP_MIN_MEMBERS:
        return [members[j] for j in order[:limit]]
    cutoff = float(np.percentile(sims, REP_CENTRALITY_PCT))
    cands = [j for j in range(len(members)) if sims[j] >= cutoff]
    # newest first; cosine breaks ties between same-day items
    cands.sort(key=lambda j: ((members[j]["published_date"] or ""), float(sims[j])),
               reverse=True)
    reps: list[dict] = []
    seen: set[str] = set()
    spare: list[dict] = []
    for j in cands:
        src = members[j]["source_name"] or ""
        if src and src in seen:
            if len(spare) < limit:
                spare.append(members[j])
            continue
        if src:
            seen.add(src)
        reps.append(members[j])
        if len(reps) >= limit:
            break
    # A genuinely single-source cluster (a patent pool, one journal) would
    # otherwise show one line instead of five; top up from the same ranking.
    for m in spare:
        if len(reps) >= limit:
            break
        reps.append(m)
    return reps or [members[j] for j in order[:limit]]


def analyze(rows: list[dict], X: np.ndarray, labels: np.ndarray,
            centroids: np.ndarray, source_weights: dict[str, float] | None = None,
            now: datetime | None = None) -> dict:
    """Per-cluster analysis + global month axis.

    Returns {"months", "totals", "clusters", "cohort"} with each cluster
    carrying size, cohesion, dominant mega-trend + purity, verticals, top tags,
    source spread + concentration, representatives, its centroid, a monthly
    series (count + share of the scope's monthly volume) and SoV momentum
    (Δ share between the early and late thirds of the sufficiently-dense
    months).

    Two corrections from the 2026-09-15 audit:

    * the running (incomplete) month is dropped from the month axis — it
      otherwise ends every sparkline on a half-month dip and lets whichever
      ingest happened to run that week steer the late window;
    * share/momentum are computed on a FIXED SOURCE PANEL (sources that
      delivered in both the early and the late window, see MIN_COHORT_COVERAGE),
      so corpus growth cannot masquerade as a trend.

    source_weights (#2 phase 2): optional {source_name: weight in [0,1]} that
    down-weights noisy sources in the SHARE / momentum maths (a low-pass-rate
    feed contributes less voice) while raw counts — size, n, n_sources — stay
    unweighted for display honesty. None (default) = every source weight 1.0.
    """
    # One month lookup per row, reused by every pass below.
    rmonth = [month_key(r["published_date"]) for r in rows]

    months = sorted({m for m in rmonth if m})
    running = (now or datetime.now()).strftime("%Y-%m")
    dropped_month = running if months and months[-1] == running else None
    if dropped_month:
        months = months[:-1]
    midx = {m: i for i, m in enumerate(months)}

    totals = [0] * len(months)          # raw monthly volume (display / density gate)
    for i, r in enumerate(rows):
        mk = rmonth[i]
        if mk in midx:
            totals[midx[mk]] += 1

    # SoV windows: the most recent MOMENTUM_WINDOW_MONTHS with enough volume,
    # early/late thirds.
    window_start = max(0, len(months) - MOMENTUM_WINDOW_MONTHS)
    meaningful = [i for i in range(window_start, len(months)) if totals[i] >= 5]
    third = max(1, len(meaningful) // 3) if meaningful else 0
    early_idx = set(meaningful[:third])
    late_idx = set(meaningful[-third:]) if third else set()

    # Fixed source panel: present in both comparison windows.
    early_m = {months[i] for i in early_idx}
    late_m = {months[i] for i in late_idx}
    early_src: set[str] = set()
    late_src: set[str] = set()
    win_rows = 0
    for i, r in enumerate(rows):
        mk = rmonth[i]
        src = r["source_name"] or ""
        if mk in early_m:
            early_src.add(src)
            win_rows += 1
        elif mk in late_m:
            late_src.add(src)
            win_rows += 1
    cohort = (early_src & late_src) - {""}
    covered = sum(1 for i, r in enumerate(rows)
                  if (rmonth[i] in early_m or rmonth[i] in late_m)
                  and (r["source_name"] or "") in cohort)
    coverage = covered / win_rows if win_rows else 0.0
    cohort_applied = bool(cohort) and coverage >= MIN_COHORT_COVERAGE

    # Per-source monthly volume, and each source's typical output in an active
    # month. A source already inside the panel can still distort a window by
    # changing its OWN rate: the 2026-09-15 FASHION run had one outlet going
    # from ~50 items a month to 378/353/347 in April-June (a back-ingest, not a
    # publishing surge), which alone produced the run's single "rising"
    # cluster. Months above a source's median are damped back to it, so an
    # outlet contributes roughly one voice per month however many rows arrive.
    # Quiet months are NOT lifted — only spikes are suspect.
    src_month: Counter = Counter()
    for i, r in enumerate(rows):
        if rmonth[i] in midx:
            src_month[(r["source_name"] or "", rmonth[i])] += 1
    by_src: dict[str, list[int]] = {}
    for (src, _m), n in src_month.items():
        by_src.setdefault(src, []).append(n)
    src_median = {s: float(np.median(v)) for s, v in by_src.items()}

    def _w(i: int, r: dict) -> float:
        src = r["source_name"] or ""
        if cohort_applied and src not in cohort:
            return 0.0
        w = source_weights.get(src, 1.0) if source_weights else 1.0
        n = src_month.get((src, rmonth[i]), 0)
        med = src_median.get(src, 0.0)
        if n > med > 0:
            w *= med / n
        return w

    rw = [_w(i, r) for i, r in enumerate(rows)]   # final per-row voice
    wtotals = [0.0] * len(months)       # panel volume (share denominator)
    for i in range(len(rows)):
        mk = rmonth[i]
        if mk in midx:
            wtotals[midx[mk]] += rw[i]

    def share(series: list[float], idxs: set[int]) -> float:
        num = sum(series[i] for i in idxs)
        den = sum(wtotals[i] for i in idxs)
        return num / den if den else 0.0

    idx_by_cluster: dict[int, list[int]] = {}
    for i, lab in enumerate(labels):
        idx_by_cluster.setdefault(int(lab), []).append(i)

    clusters = []
    for cid, idxs in sorted(idx_by_cluster.items(), key=lambda kv: -len(kv[1])):
        members = [rows[i] for i in idxs]
        cen = centroids[cid]
        cen = cen / max(np.linalg.norm(cen), 1e-9)
        sims = X[idxs] @ cen
        cohesion = float(np.mean(sims))
        reps = _pick_reps(members, sims)
        megas = Counter(m["mega_trend"] for m in members if m["mega_trend"])
        dom, dom_n = (megas.most_common(1)[0] if megas else (None, 0))
        tags = Counter(t for m in members for t in (m["tags"] or []))
        verts = [v for v, _ in Counter(
            m["primary_vertical"] for m in members if m["primary_vertical"]).most_common(3)]
        src_counts = Counter(m["source_name"] for m in members if m["source_name"])
        top_source, top_n = src_counts.most_common(1)[0] if src_counts else (None, 0)

        series = [0] * len(months)          # raw counts (display)
        wseries = [0.0] * len(months)       # panel counts (share/momentum)
        for j in idxs:
            mk = rmonth[j]
            if mk in midx:
                series[midx[mk]] += 1
                wseries[midx[mk]] += rw[j]
        se, sl = share(wseries, early_idx), share(wseries, late_idx)
        delta_pp = (sl - se) * 100
        up = sl >= se * (1 + MOMENTUM_MIN_RELATIVE) if se else True
        down = sl <= se * (1 - MOMENTUM_MIN_RELATIVE) if se else False
        momentum = ("rising" if delta_pp > MOMENTUM_RISING_PP and up
                    else "declining" if delta_pp < MOMENTUM_DECLINING_PP and down
                    else "stable")
        # Share of voice is zero-sum: one cluster surging pushes every other
        # into negative pp even when they grew. Raw item counts answer the
        # question the badge cannot ("did we simply see more of this?"), and
        # both windows span the same number of months, so the ratio is fair.
        ve = sum(series[i] for i in early_idx)
        vl = sum(series[i] for i in late_idx)
        vol_delta_pct = round((vl / ve - 1) * 100, 1) if ve else None
        if len(meaningful) < 6:
            momentum, delta_pp, vol_delta_pct = "unknown", 0.0, None

        top_tags = [t for t, _ in tags.most_common(12)]
        clusters.append({
            "cluster_idx": cid,
            "_tag_counter": tags,           # kept for the distinctiveness pass below
            "label": derive_label(top_tags, fallback=f"Cluster {cid}"),  # provisional
            "size": len(members),
            "cohesion": round(cohesion, 4),
            "mega_trend": dom,
            "mega_purity": round(dom_n / len(members), 4) if members else 0.0,
            "verticals": verts,
            "top_tags": top_tags,
            "n_sources": len(src_counts),
            "top_source": top_source,
            "top_source_share": round(top_n / len(members), 4) if members else 0.0,
            "momentum": momentum,
            "sov_delta_pp": round(delta_pp, 2),
            # The two shares the delta is made of. A pp figure alone is not
            # readable: +0.5 pp is a big move for a 1 % cluster and noise for a
            # 20 % one, and the raw item count cannot substitute (in the
            # 2026-09 corpus EVERY cluster grew three- to fiftyfold because the
            # corpus did).
            "share_early": round(se, 4),
            "share_late": round(sl, 4),
            "vol_delta_pct": vol_delta_pct,
            "rep_trend_ids": [r["id"] for r in reps],
            "rep_titles": [(r["title_en"] or "")[:120] for r in reps],
            "monthly_series": [
                {"m": months[i], "n": series[i],
                 "share": round(wseries[i] / wtotals[i], 4) if wtotals[i] else 0.0}
                for i in range(len(months))
            ],
        })

    # Second pass: relabel each cluster by tag distinctiveness across clusters, so
    # near-identical clusters (e.g. the plant-based cluster of FOOD) surface what
    # sets them apart rather than repeating the vertical's dominant tag. tag_df =
    # in how many clusters each normalized tag ranks in the top 20. Labels are
    # assigned largest-cluster-first and must be unique within the run.
    tag_df: Counter = Counter()
    for c in clusters:
        top20 = [t for t, _ in c["_tag_counter"].most_common(20)]
        for norm in {_norm_tag(t) for t in top20}:
            if norm:
                tag_df[norm] += 1
    n_c = len(clusters)
    used: set[str] = set()
    for c in sorted(clusters, key=lambda c: -c["size"]):
        terms = distinctive_terms(c["_tag_counter"], c["size"], tag_df, n_c)
        c["label"] = unique_label(terms, used, fallback=c["label"])
        used.add(c["label"])
        del c["_tag_counter"]
    return {
        "months": months,
        "totals": totals,
        "clusters": clusters,
        "cohort": {
            "applied": cohort_applied,
            "sources": len(cohort),
            "coverage": round(coverage, 4),
            "dropped_month": dropped_month,
            "early_window": [min(early_m), max(early_m)] if early_m else None,
            "late_window": [min(late_m), max(late_m)] if late_m else None,
        },
    }


# -------------------------------------------------------------------- lineage
# Cross-window cluster evolution (issue #2 phase 1): cluster each rolling time
# window independently, then match clusters across consecutive windows by
# centroid cosine. The resulting graph carries emergence / continuation /
# split / merge / decline plus semantic drift — the "where is this trend
# going" substrate the single-window snapshots cannot express.

MATCH_SIM = 0.80          # centroid cosine >= this = same theme across windows
LINEAGE_MIN_SIGNALS = 300  # windows below this are recorded as gaps, not clustered


def _add_months(d: datetime, months: int) -> datetime:
    y, m = divmod(d.year * 12 + (d.month - 1) + months, 12)
    return d.replace(year=y, month=m + 1, day=1)


def window_bounds(since: str, until: str, step_months: int = 3,
                  span_months: int = 12) -> list[tuple[str, str]]:
    """Rolling (start, end) ISO-date windows covering [since, until).

    Windows overlap when span > step (default: quarterly step, 12-month span —
    9 months of shared data makes cross-window matches stable). The last
    window is the first one whose end reaches `until`.
    """
    start = datetime.fromisoformat(since).replace(day=1)
    stop = datetime.fromisoformat(until)
    out: list[tuple[str, str]] = []
    while True:
        end = _add_months(start, span_months)
        out.append((start.date().isoformat(), end.date().isoformat()))
        if end >= stop:
            break
        start = _add_months(start, step_months)
    return out


def _relation(out_deg: int, in_deg: int) -> str:
    if out_deg > 1 and in_deg > 1:
        return "split_merge"
    if out_deg > 1:
        return "split"
    if in_deg > 1:
        return "merge"
    return "continue"


def build_lineage(status: str = "signal,published", vertical: str | None = None,
                  since: str = "2016-01-01", until: str | None = None,
                  step_months: int = 3, span_months: int = 12,
                  k_range: tuple[int, int] = (6, 14), dim1024: bool = False,
                  min_signals: int = LINEAGE_MIN_SIGNALS,
                  match_sim: float = MATCH_SIM,
                  progress=None) -> dict:
    """Cluster every window, then match consecutive windows by centroid cosine.

    Returns {"windows": [...], "nodes": [...], "edges": [...]}.
    nodes: one per (window, cluster) with label/size/sov_share/cohesion/top_tags,
      a `status` of "emerged" / "declined" / "" (relative to the neighbouring
      computed windows) and the L2-normalized centroid as float32 bytes.
    edges: between consecutive computed windows with cosine `sim`, a
      relation (continue/split/merge/split_merge) and drift = 1 - sim.
    Windows with fewer than `min_signals` dated signals become gaps
    ({"computed": False}) and break lineage chains deliberately — matching
    across a data hole would fabricate continuity.
    """
    until = until or datetime.now().date().isoformat()
    bounds = window_bounds(since, until, step_months, span_months)
    windows: list[dict] = []
    per_win: list[dict | None] = []
    for ws, we in bounds:
        rows = load_signals(status=status, vertical=vertical, since=ws, until=we,
                            dim1024=dim1024)
        info = {"start": ws, "end": we, "n": len(rows), "computed": False}
        if len(rows) < min_signals:
            windows.append(info)
            per_win.append(None)
            continue
        X = build_matrix(rows)
        labels, centroids, k = cluster_signals(X, k_range=k_range)
        res = analyze(rows, X, labels, centroids)
        cn = centroids / np.clip(np.linalg.norm(centroids, axis=1, keepdims=True),
                                 1e-9, None)
        info.update(computed=True, k=k)
        windows.append(info)
        per_win.append({"clusters": res["clusters"], "centroids": cn.astype(np.float32),
                        "total": len(rows)})
        del X, rows
        if progress:
            progress(f"window {ws}..{we}: n={info['n']} k={k}")

    nodes: list[dict] = []
    node_at: dict[tuple[int, int], int] = {}  # (window_idx, cluster_idx) -> node idx
    for wi, pw in enumerate(per_win):
        if pw is None:
            continue
        for c in pw["clusters"]:
            node_at[(wi, c["cluster_idx"])] = len(nodes)
            nodes.append({
                "window_idx": wi,
                "window_start": windows[wi]["start"],
                "window_end": windows[wi]["end"],
                "cluster_idx": c["cluster_idx"],
                "label": c["label"], "size": c["size"],
                "sov_share": round(c["size"] / pw["total"], 4),
                "cohesion": c["cohesion"],
                "top_tags": c["top_tags"][:8],
                "rep_trend_ids": c["rep_trend_ids"],
                "centroid": pw["centroids"][c["cluster_idx"]].tobytes(),
                "status": "",
            })

    edges: list[dict] = []
    computed_idx = [i for i, pw in enumerate(per_win) if pw is not None]
    for a, b in zip(computed_idx, computed_idx[1:]):
        if b != a + 1:
            continue  # gap between them — no matching across data holes
        S = per_win[a]["centroids"] @ per_win[b]["centroids"].T
        pairs = [(i, j, float(S[i, j]))
                 for i in range(S.shape[0]) for j in range(S.shape[1])
                 if S[i, j] >= match_sim]
        out_deg = Counter(i for i, _, _ in pairs)
        in_deg = Counter(j for _, j, _ in pairs)
        for i, j, sim in pairs:
            edges.append({
                "from_node": node_at[(a, i)], "to_node": node_at[(b, j)],
                "sim": round(sim, 4), "drift": round(1.0 - sim, 4),
                "relation": _relation(out_deg[i], in_deg[j]),
            })

    # Emergence / decline: comparing against the *adjacent* window is useless
    # when windows overlap (span > step) — 9 of 12 shared months means almost
    # every cluster has a neighbour match, so nothing ever looks new. Judge
    # instead against the nearest NON-overlapping window (>= span months apart),
    # i.e. "did this theme exist as a distinct cluster a full span ago / will it
    # a full span from now". overlap_steps windows on each side share data.
    overlap_steps = max(1, span_months // max(step_months, 1))
    comp_set = set(computed_idx)

    def _ref_before(wi: int) -> int | None:
        for r in range(wi - overlap_steps, computed_idx[0] - 1, -1):
            if r in comp_set:
                return r
        return None

    def _ref_after(wi: int) -> int | None:
        for r in range(wi + overlap_steps, computed_idx[-1] + 1):
            if r in comp_set:
                return r
        return None

    def _matches(wi: int, ci: int, ref: int) -> bool:
        cen = per_win[wi]["centroids"][ci]
        return bool((per_win[ref]["centroids"] @ cen).max() >= match_sim)

    for n in nodes:
        wi, ci = n["window_idx"], n["cluster_idx"]
        before, after = _ref_before(wi), _ref_after(wi)
        if before is not None and not _matches(wi, ci, before):
            n["status"] = "emerged"      # absent a full span ago
        elif after is not None and not _matches(wi, ci, after):
            n["status"] = "declined"     # gone a full span from now
    return {"windows": windows, "nodes": nodes, "edges": edges}
