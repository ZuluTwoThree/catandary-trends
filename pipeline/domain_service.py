#!/usr/bin/env python3
"""Live pocket discovery for a free term — a resident service (Owner 01.10.2026).

The owner types a term nobody planned for ("batteries", "precision fermentation"); the
service selects the domain's signals, shows the selection, and on confirmation finds the
pockets inside it, dates them against the whole archive, groups and names them, and
stores the result as an ordinary emerging run with scope `domain:q_<term>` — so
/trends/foresight/emerging?domain=q_<term> shows it like every other run.

Same method as `python -m pipeline.domains adhoc` + `emerging_snapshot --scope domain:…`
(docs/domains_framework_2026-09-30.md). What the service changes is WHERE the vectors
come from: it keeps every embedded signal in memory (2.0 M × 1024 float16 ≈ 4 GB), so
nothing is streamed out of Postgres per request. The command-line path measured 95-100 s
for the selection and 174-505 s for the pockets (30.09.), almost all of it loading
vectors and scanning the archive; here both are matrix products.

Differences to the scheduled domain runs, all for free terms (the owner cannot tune a
term he did not foresee):
  * a 12-month slice instead of 90 days, and 150 signals minimum instead of 800 —
    "solid-state battery" had 398 members in 90 days and found nothing;
  * the density gate is relative to the domain (densest quarter of its own cells,
    emerging.DOMAIN_COHESION_QUANTILE), duplicates are merged on domain-centred cosine
    and the pockets are grouped (emerging.group_nests);
  * names come from the RESTING 8B on :8090, only while it is idle (no job holds the
    card); otherwise the tag labels stay — never a GPU handover from a web request.

Two stages per job, because a free term can drift or mean two things: `select` trains
the probe and returns a preview (size per tier, examples in and just outside, how many
members carry the term literally); `pockets` runs only after the owner confirms.

    .venv/bin/python -m pipeline.domain_service              # serve on 127.0.0.1:8093
    .venv/bin/python -m pipeline.domain_service --rebuild    # rebuild the vector copy
    .venv/bin/python -m pipeline.domain_service --once "batteries"   # one job, no server

The copy lives in DOMAIN_SERVICE_CACHE (default ~/.cache/catandary/domain_service, shared
by the dev and main worktrees); new rows are picked up incrementally before each job.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import queue
import threading
import time
import traceback
import uuid
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np

from pipeline import db as db_mod
from pipeline.db import get_connection
from pipeline.tiers import TIERS, tier_of

logger = logging.getLogger("domain_service")

DIM = 1024
PORT = int(os.getenv("DOMAIN_SERVICE_PORT", "8093"))
CACHE_DIR = Path(os.getenv("DOMAIN_SERVICE_CACHE",
                           str(Path.home() / ".cache" / "catandary" / "domain_service")))
TIER_NAMES = list(TIERS) + ["none"]
ST_SIGNAL, ST_PUBLISHED, ST_OTHER = 0, 1, 2
STATUSES = "signal,published,draft"
WINDOW_MONTHS = 12
MIN_SIGNALS = 150
MIN_NESTS_RETRY = 5
REFRESH_EVERY_S = 15 * 60
SAVE_AFTER_NEW_ROWS = 50_000
SCORE_CHUNK = 100_000
FETCH_CHUNK = 5_000
REST_MODEL = os.getenv("DOMAIN_NAME_MODEL", "Qwen3-8B-UD-Q4_K_XL.gguf")
LLAMA_URL = os.getenv("LLAMA_URL", "http://127.0.0.1:8090")
EXCLUDE_SOURCE_PREFIXES = ("OpenAlex corpus:",)   # = domains.TRAIN_EXCLUDE_SOURCES
MAX_JOBS_KEPT = 40


def month_num(published) -> int:
    s = published.isoformat() if isinstance(published, datetime) else (published or "")
    if len(s) < 7 or not s[:4].isdigit():
        return -1
    return int(s[:4]) * 12 + int(s[5:7]) - 1


def month_str(n: int) -> str:
    return f"{n // 12:04d}-{n % 12 + 1:02d}"


# ===================================================================== the copy

class Store:
    """Every embedded signal/published/draft row: id, unit vector (float16), month,
    tier, status, source. Rows are in ascending id order (keyset reads)."""

    def __init__(self) -> None:
        self.n = 0
        self.ids = np.zeros(0, np.int64)
        self.X = np.zeros((0, DIM), np.float16)
        self.month = np.zeros(0, np.int32)
        self.tier = np.zeros(0, np.int8)
        self.status = np.zeros(0, np.int8)
        self.source = np.zeros(0, np.int32)
        self.sources: list[str] = []
        self._source_code: dict[str, int] = {}
        self.built_at: str | None = None
        self.refreshed_at = 0.0
        self.unsaved = 0
        self.loading = ""

    # ---------------------------------------------------------------- growth
    def _reserve(self, extra: int) -> None:
        need = self.n + extra
        if need <= len(self.ids):
            return
        cap = max(need, int(len(self.ids) * 1.1) + 50_000)

        def grow(a, shape):
            b = np.zeros(shape, a.dtype)
            b[:self.n] = a[:self.n]
            return b
        self.ids = grow(self.ids, cap)
        self.X = grow(self.X, (cap, DIM))
        self.month = grow(self.month, cap)
        self.tier = grow(self.tier, cap)
        self.status = grow(self.status, cap)
        self.source = grow(self.source, cap)

    def _code(self, name: str | None) -> int:
        name = name or ""
        c = self._source_code.get(name)
        if c is None:
            c = len(self.sources)
            self.sources.append(name)
            self._source_code[name] = c
        return c

    def _append(self, batch: list[dict]) -> None:
        self._reserve(len(batch))
        m = len(batch)
        V = np.empty((m, DIM), np.float32)
        for i, r in enumerate(batch):
            V[i] = np.frombuffer(r["_emb"], np.float32)[:DIM]
        V /= np.clip(np.linalg.norm(V, axis=1, keepdims=True), 1e-9, None)
        s, e = self.n, self.n + m
        self.X[s:e] = V
        self.ids[s:e] = [r["id"] for r in batch]
        self.month[s:e] = [month_num(r.get("published_date")) for r in batch]
        self.tier[s:e] = [TIER_NAMES.index(tier_of(r.get("source_name"), r.get("source_type"),
                                                    r.get("trend_signal_type")) or "none")
                          for r in batch]
        self.status[s:e] = [ST_SIGNAL if r["status"] == "signal" else
                            ST_PUBLISHED if r["status"] == "published" else ST_OTHER for r in batch]
        self.source[s:e] = [self._code(r.get("source_name")) for r in batch]
        self.n = e

    def read_new(self) -> int:
        """Rows with an id above the copy's last one. Returns how many were added."""
        from pipeline.foresight import iter_signals
        start = int(self.ids[self.n - 1]) if self.n else 0
        added = 0
        for batch in iter_signals(status=STATUSES, dim1024=True, start_id=start, chunk_size=20_000):
            self._append(batch)
            added += len(batch)
            self.loading = f"{self.n:,} rows"
            if added % 200_000 < 20_000:
                logger.info("copy: %s rows", f"{self.n:,}")
        self.unsaved += added
        return added

    def recheck_status(self) -> int:
        """Drafts get published later; their status in the copy is refreshed."""
        idx = np.flatnonzero(self.status[:self.n] == ST_OTHER)
        if not len(idx):
            return 0
        changed = 0
        with get_connection() as c:
            for s in range(0, len(idx), 10_000):
                part = idx[s:s + 10_000]
                rows = c.execute("SELECT id, status FROM trends WHERE id = ANY(?)",
                                 ([int(i) for i in self.ids[part]],)).fetchall()
                st = {int(r["id"]): r["status"] for r in rows}
                for i in part:
                    v = st.get(int(self.ids[i]))
                    code = (ST_SIGNAL if v == "signal" else ST_PUBLISHED if v == "published"
                            else ST_OTHER)
                    if code != self.status[i]:
                        self.status[i] = code
                        changed += 1
        return changed

    def refresh(self, force: bool = False) -> None:
        if not force and time.time() - self.refreshed_at < REFRESH_EVERY_S:
            return
        t0 = time.time()
        added = self.read_new()
        changed = self.recheck_status()
        self.refreshed_at = time.time()
        logger.info("refresh: +%d rows, %d status changes (%.0fs), %s rows in memory",
                    added, changed, time.time() - t0, f"{self.n:,}")
        if self.unsaved >= SAVE_AFTER_NEW_ROWS:
            self.save()

    # ---------------------------------------------------------------- disk
    def save(self) -> None:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = CACHE_DIR / "vectors.tmp.npy"
        np.save(tmp, self.X[:self.n])
        tmp.replace(CACHE_DIR / "vectors.npy")
        np.savez(CACHE_DIR / "meta.tmp.npz", ids=self.ids[:self.n], month=self.month[:self.n],
                 tier=self.tier[:self.n], status=self.status[:self.n], source=self.source[:self.n])
        (CACHE_DIR / "meta.tmp.npz").replace(CACHE_DIR / "meta.npz")
        (CACHE_DIR / "sources.json").write_text(json.dumps(
            {"sources": self.sources, "built_at": self.built_at}), encoding="utf-8")
        self.unsaved = 0
        logger.info("copy saved: %s rows -> %s", f"{self.n:,}", CACHE_DIR)

    def load(self) -> bool:
        try:
            meta = np.load(CACHE_DIR / "meta.npz")
            X = np.load(CACHE_DIR / "vectors.npy")
            info = json.loads((CACHE_DIR / "sources.json").read_text(encoding="utf-8"))
        except (OSError, ValueError, KeyError):
            return False
        n = len(meta["ids"])
        if X.shape != (n, DIM):
            return False
        self.n = 0
        self.ids = np.zeros(0, np.int64)
        self.X = np.zeros((0, DIM), np.float16)
        self.month = np.zeros(0, np.int32)
        self.tier = np.zeros(0, np.int8)
        self.status = np.zeros(0, np.int8)
        self.source = np.zeros(0, np.int32)
        self._reserve(n + 50_000)
        self.X[:n] = X
        del X
        self.ids[:n], self.month[:n] = meta["ids"], meta["month"]
        self.tier[:n], self.status[:n], self.source[:n] = meta["tier"], meta["status"], meta["source"]
        self.n = n
        self.sources = list(info["sources"])
        self._source_code = {s: i for i, s in enumerate(self.sources)}
        self.built_at = info.get("built_at")
        return True

    def build(self) -> None:
        self.__init__()
        self.built_at = datetime.now().isoformat(timespec="seconds")
        with get_connection() as c:
            total = int(c.execute("SELECT count(*) AS n FROM trends WHERE embedding_1024 IS NOT NULL"
                                  " AND status IN ('signal','published','draft')").fetchone()["n"])
        self._reserve(total + 50_000)            # one allocation, not fifty
        self.read_new()
        self.refreshed_at = time.time()
        self.save()

    def open(self, rebuild: bool = False) -> None:
        t0 = time.time()
        if rebuild or not self.load():
            logger.info("building the vector copy from the database (~5 min) …")
            self.build()
        else:
            logger.info("copy loaded: %s rows (%.0fs), built %s", f"{self.n:,}",
                        time.time() - t0, self.built_at)
            self.refresh(force=True)
        self.loading = ""

    # ---------------------------------------------------------------- lookups
    def eligible(self) -> np.ndarray:
        return self.status[:self.n] <= ST_PUBLISHED

    def index_of(self, ids) -> np.ndarray:
        """Row index per id, -1 when the id is not in the copy."""
        q = np.asarray(list(ids), np.int64)
        if not len(q) or not self.n:
            return np.full(len(q), -1, np.int64)
        pos = np.searchsorted(self.ids[:self.n], q)
        pos = np.clip(pos, 0, self.n - 1)
        return np.where(self.ids[pos] == q, pos, -1)

    def known(self, ids) -> set[int]:
        ids = list(ids)
        idx = self.index_of(ids)
        el = self.eligible()
        return {int(i) for i, j in zip(ids, idx) if j >= 0 and el[j]}

    def vectors(self, ids: list[int]) -> tuple[np.ndarray, list[str]]:
        idx = self.index_of(ids)
        if (idx < 0).any():
            raise KeyError(f"{int((idx < 0).sum())} ids not in the copy")
        return self.X[idx].astype(np.float32), [TIER_NAMES[t] for t in self.tier[idx]]

    def nearest(self, text: str, k: int) -> set[int]:
        from pipeline.domains import embed_text
        q = embed_text(text)
        q = (q / max(float(np.linalg.norm(q)), 1e-9)).astype(np.float32)
        scores = np.full(self.n, -2.0, np.float32)
        for s in range(0, self.n, SCORE_CHUNK):
            e = min(self.n, s + SCORE_CHUNK)         # X has spare capacity beyond n
            scores[s:e] = self.X[s:e].astype(np.float32) @ q
        scores[~self.eligible()] = -2.0
        top = np.argpartition(-scores, min(k, self.n - 1))[:k]
        return {int(self.ids[i]) for i in top}

    def background(self, n: int, exclude: set[int]) -> list[int]:
        """Same rule as domains.background_ids (hash below a cut), from memory."""
        from pipeline.domains import HASH_MOD, HASH_MUL
        el = np.flatnonzero(self.eligible())
        h = (self.ids[el] * HASH_MUL) % HASH_MOD
        cut = int(HASH_MOD * min(1.0, 1.3 * n / max(len(el), 1)))
        pick = el[h < cut]
        hs = (self.ids[pick] * HASH_MUL) % HASH_MOD
        out = [int(i) for i in self.ids[pick[np.argsort(hs, kind="stable")]] if int(i) not in exclude]
        return out[:n]

    def excluded(self, ids) -> set[int]:
        bad = {c for c, s in enumerate(self.sources) if s.startswith(EXCLUDE_SOURCE_PREFIXES)}
        ids = list(ids)
        idx = self.index_of(ids)
        return {int(i) for i, j in zip(ids, idx) if j >= 0 and int(self.source[j]) in bad}

    def probability(self, probe) -> tuple[np.ndarray, np.ndarray]:
        """(p, threshold) for every row — DomainProbe.prob, vectorised over the copy."""
        clf = probe.clf
        w = clf.coef_[0].astype(np.float32)
        b = float(clf.intercept_[0])
        M = np.vstack([probe.means.get(t, probe._g) for t in TIER_NAMES]).astype(np.float32)
        thr = np.array([probe.tier_thresholds.get(t, probe.threshold) for t in TIER_NAMES], np.float32)
        p = np.empty(self.n, np.float32)
        for s in range(0, self.n, SCORE_CHUNK):
            e = min(self.n, s + SCORE_CHUNK)
            F = self.X[s:e].astype(np.float32) - M[self.tier[s:e]]
            F /= np.clip(np.linalg.norm(F, axis=1, keepdims=True), 1e-9, None)
            p[s:e] = 1.0 / (1.0 + np.exp(-(F @ w + b)))
        return p, thr[self.tier[:self.n]]


# ===================================================================== DB rows

def fetch_rows(ids: list[int], fields: str = "full") -> list[dict]:
    """Row attributes (no vector) for `ids`, in the given order."""
    cols = ("t.id, t.title_en, t.tags, t.source_name, t.primary_vertical, t.status,"
            " t.brands, t.companies, t.trend_signal_type, s.source_type, r.published_date")
    join = ""
    if fields == "text":
        # the text a term can be found in: title, summary, the entry's excerpt (patent
        # abstracts live there) and the research abstract
        cols = ("t.id, t.title_en, t.summary_en, t.tags, t.source_name, s.source_type,"
                " t.trend_signal_type, r.excerpt, rs.abstract")
        join = " LEFT JOIN research_signals rs ON rs.trend_id = t.id"
    out: dict[int, dict] = {}
    with get_connection() as c:
        for s in range(0, len(ids), FETCH_CHUNK):
            part = [int(i) for i in ids[s:s + FETCH_CHUNK]]
            for raw in c.execute(
                    f"SELECT {cols} FROM trends t JOIN raw_entries r ON r.id = t.raw_entry_id"
                    f" LEFT JOIN sources s ON s.id = r.source_id{join} WHERE t.id = ANY(?)",
                    (part,)).fetchall():
                r = dict(raw)
                if isinstance(r.get("published_date"), datetime):
                    r["published_date"] = r["published_date"].isoformat()
                for f in ("tags", "brands", "companies"):
                    if f in r:
                        v = r[f]
                        try:
                            r[f] = v if isinstance(v, list) else (json.loads(v) if v else [])
                        except (TypeError, ValueError):
                            r[f] = []
                out[int(r["id"])] = r
    return [out.get(int(i)) or {"id": int(i), "title_en": "", "tags": [], "source_name": None,
                                "primary_vertical": None, "published_date": None, "brands": [],
                                "companies": []} for i in ids]


from pipeline.domains import carries_term  # noqa: E402  (shared with the seed check)


def member_text(r: dict) -> str:
    """Everything a member says about itself, tags kept apart (see domains._seed_text)."""
    parts = [r.get("title_en") or "", r.get("summary_en") or "", r.get("excerpt") or "",
             r.get("abstract") or ""] + [str(t) for t in (r.get("tags") or [])]
    return " zzsep ".join(parts)


def _hpick(idx: np.ndarray, ids: np.ndarray, k: int) -> np.ndarray:
    """k rows of idx, deterministically (smallest id hash)."""
    from pipeline.domains import HASH_MOD, HASH_MUL
    if not len(idx):
        return idx
    h = (ids[idx] * HASH_MUL) % HASH_MOD
    return idx[np.argsort(h, kind="stable")[:k]]


# ===================================================================== naming

def resting_model_idle() -> tuple[bool, str]:
    """True when :8090 serves the resting 8B and no job has claimed the unit."""
    import httpx
    try:
        r = httpx.get(f"{LLAMA_URL}/v1/models", timeout=5)
        r.raise_for_status()
        served = r.json()["data"][0]["id"]
    except Exception as exc:                 # noqa: BLE001
        return False, f"llama-server not answering ({exc.__class__.__name__})"
    if Path(served).name != REST_MODEL:
        return False, f"GPU busy ({Path(served).name} loaded)"
    try:
        from pipeline.gpu_handover import _foreign_owner, _unit_main_pid
        pid = _unit_main_pid()
        owner = _foreign_owner(pid) if pid else None
    except Exception:                        # noqa: BLE001
        owner = None
    if owner:
        return False, f"GPU held by {owner}"
    return True, "resting 8B idle"


def _chat(**kw):
    from pipeline.llamacpp_client import chat
    return chat(enable_thinking=False, **kw)


def name_all(nests: list[dict], log) -> str:
    """Nest names and group names with the resting 8B — or a reason why not."""
    from pipeline.nest_naming import name_nest, name_nests
    ok, why = resting_model_idle()
    if not ok:
        for n in nests:
            n["llm_label"] = None
            n["llm_label_note"] = f"not named: {why}"
        log(f"names skipped — {why}; tag labels kept")
        return why
    log(f"naming {len(nests)} pockets with the resting 8B …")
    name_nests(nests, chat=_chat, model=REST_MODEL)
    groups: dict[int, list[dict]] = {}
    for n in nests:
        groups.setdefault(n.get("group_id") or 0, []).append(n)
    used: set[str] = set()
    for g, members in groups.items():
        if len(members) < 2:
            continue
        # the pockets' own names only: with member titles in the prompt the model named
        # the whole chemistry group after its biggest pocket ("Sodium Ion Battery …")
        titles = [m.get("llm_label") or m["label"] for m in members]
        tags = [t for m in members for t in (m.get("top_tags") or [])[:3]]
        name, _ = name_nest(titles, tags, chat=_chat, model=REST_MODEL)
        if name and name.lower() in used:
            name = None
        if name:
            used.add(name.lower())
        for m in members:
            m["group_label"] = name
    return why


# ===================================================================== jobs

class Job:
    def __init__(self, term: str, also: list[str], window_months: int) -> None:
        from pipeline.domains import adhoc_key
        self.id = uuid.uuid4().hex[:12]
        self.term = " ".join(term.split())
        self.also = [a for a in also if a.strip()]
        self.window_months = window_months
        self.key = adhoc_key(self.term)
        self.state = "queued"          # queued select preview pockets done failed discarded
        self.stage = ""
        self.log: list[dict] = []
        self.preview: dict | None = None
        self.result: dict | None = None
        self.error: str | None = None
        self.created = time.time()
        self.t_select = None
        self.t_pockets = None
        self._p = None
        self._thr = None
        self._previous_probe = None

    def say(self, msg: str) -> None:
        self.stage = msg
        self.log.append({"t": round(time.time() - self.created, 1), "msg": msg})
        logger.info("[%s] %s", self.key, msg)

    def public(self) -> dict:
        return {"id": self.id, "term": self.term, "also": self.also, "key": self.key,
                "window_months": self.window_months, "state": self.state, "stage": self.stage,
                "log": self.log[-40:], "preview": self.preview, "result": self.result,
                "error": self.error, "seconds_select": self.t_select,
                "seconds_pockets": self.t_pockets}


def _backup_probe(key: str):
    with get_connection() as c:
        r = c.execute("SELECT key, name, definition, threshold, metrics, n_pos, n_neg, measured, model,"
                      " trained_at FROM domain_probes WHERE key = ?", (key,)).fetchone()
    return dict(r) if r else None


def _restore_probe(key: str, row) -> None:
    with get_connection() as c:
        c.execute("DELETE FROM domain_probes WHERE key = ?", (key,))
        if row:
            c.execute("INSERT INTO domain_probes (key, name, definition, threshold, metrics, n_pos,"
                      " n_neg, measured, model, trained_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                      (row["key"], row["name"], row["definition"], row["threshold"], row["metrics"],
                       row["n_pos"], row["n_neg"], row["measured"], row["model"], row["trained_at"]))


def run_select(store: Store, job: Job) -> None:
    from pipeline.domains import (DomainProbe, adhoc_definition, migrate_domain_tables, seed_ids,
                                  train)
    t0 = time.time()
    job.state = "select"
    store.refresh()
    defn = adhoc_definition(job.term, job.also)
    migrate_domain_tables()
    job._previous_probe = _backup_probe(job.key)
    job.say("finding seed signals (full text + nearest vectors) …")
    seeds = seed_ids(defn, nearest=store.nearest)
    seeds = {k: store.known(v) for k, v in seeds.items()}
    job.say("seeds: " + ", ".join(f"{k} {len(v):,}" for k, v in seeds.items() if v)
            + " — training the probe …")
    out: list[DomainProbe] = []
    metrics = train(job.key, {job.key: defn}, seeds=seeds, vectors=store.vectors,
                    background=store.background, excluded=store.excluded,
                    corpus_size=int(store.eligible().sum()), probe_out=out)
    probe = out[0]
    job.say("scoring every signal in memory …")
    p, thr = store.probability(probe)
    member = (p >= thr) & store.eligible()
    job._p, job._thr = p, thr
    now = datetime.now()
    since_m = month_num(now) - job.window_months + 1
    win = member & (store.month[:store.n] >= since_m)
    by_tier = {TIER_NAMES[t]: int(c) for t, c in zip(*np.unique(store.tier[:store.n][win],
                                                                   return_counts=True))}
    m_idx = np.flatnonzero(win)
    edge = np.flatnonzero((p >= 0.8 * thr) & ~member & store.eligible()
                          & (store.month[:store.n] >= since_m))
    ex_ids = [int(i) for i in store.ids[_hpick(m_idx, store.ids, 14)]]
    edge_ids = [int(i) for i in store.ids[_hpick(edge, store.ids, 8)]]
    lit_idx = _hpick(m_idx, store.ids, 400)
    lit_rows = fetch_rows([int(i) for i in store.ids[lit_idx]], fields="text")
    literal = sum(1 for r in lit_rows if carries_term(member_text(r), [job.term] + job.also))
    ex_rows = {int(r["id"]): r for r in fetch_rows(ex_ids + edge_ids, fields="text")}
    pos = store.index_of(ex_ids + edge_ids)

    def card(i, j):
        r = ex_rows.get(i) or {}
        return {"id": i, "title": (r.get("title_en") or "")[:160],
                "source": r.get("source_name"), "tier": TIER_NAMES[int(store.tier[j])],
                "month": month_str(int(store.month[j])) if store.month[j] >= 0 else None,
                "p": round(float(p[j]), 3)}
    first_months = store.month[:store.n][member]
    job.preview = {
        "window_from": month_str(since_m), "window_months": job.window_months,
        "members_window": int(win.sum()), "members_archive": int(member.sum()),
        "first_month": month_str(int(first_months[first_months >= 0].min()))
                       if (first_months >= 0).any() else None,
        "by_tier": dict(sorted(by_tier.items(), key=lambda kv: -kv[1])),
        "literal_share": round(literal / max(len(lit_rows), 1), 3),
        "literal_sample": len(lit_rows),
        "seeds": {k: len(v) for k, v in seeds.items()},
        "auc": metrics.get("auc"),
        "per_tier": metrics.get("per_tier"),
        "examples": [card(i, int(j)) for i, j in zip(ex_ids, pos[:len(ex_ids)])],
        "just_outside": [card(i, int(j)) for i, j in zip(edge_ids, pos[len(ex_ids):])],
        "enough": int(win.sum()) >= MIN_SIGNALS,
        "min_signals": MIN_SIGNALS,
    }
    job.t_select = round(time.time() - t0, 1)
    job.state = "preview"
    job.say(f"selection ready: {int(win.sum()):,} signals in {job.window_months} months "
            f"({job.t_select:.0f}s)")


def run_pockets(store: Store, job: Job) -> None:
    from pipeline.emerging import (DOMAIN_COHESION_QUANTILE, HIST_SIM_FLOOR, describe_nests,
                                   detect_nests, group_nests, pick_cells, scan_history,
                                   score_nests)
    from pipeline.emerging_snapshot import (ACTOR_WINDOW, OLD_TAG_WINDOW, _month_back,
                                            persist_run, prune_old_emerging_runs)
    t0 = time.time()
    job.state = "pockets"
    p, thr = job._p, job._thr
    member = (p >= thr) & store.eligible()
    now = datetime.now()
    since_m = month_num(now) - job.window_months + 1
    idx = np.flatnonzero(member & (store.month[:store.n] >= since_m))
    if len(idx) < MIN_SIGNALS:
        raise ValueError(f"only {len(idx)} signals in {job.window_months} months — "
                         f"below {MIN_SIGNALS}, no pockets to speak of")
    job.say(f"loading titles and tags of {len(idx):,} signals …")
    rows = fetch_rows([int(i) for i in store.ids[idx]])
    X = store.X[idx].astype(np.float32)
    X /= np.clip(np.linalg.norm(X, axis=1, keepdims=True), 1e-9, None)
    center = X.mean(axis=0)
    min_size = 30 if len(idx) >= 1500 else 15
    k = pick_cells(len(idx))
    job.say(f"cutting the selection into {k} cells …")
    tiers = store.tier[idx]
    nests = detect_nests(X, k=k, relative_quantile=DOMAIN_COHESION_QUANTILE, center=center,
                         min_size=min_size, row_tiers=tiers)
    if len(nests) < MIN_NESTS_RETRY:
        finer = min(len(idx) // 15, k * 3)
        if finer > k:
            job.say(f"only {len(nests)} pockets — trying {finer} finer cells …")
            n2 = detect_nests(X, k=finer, relative_quantile=DOMAIN_COHESION_QUANTILE,
                              center=center, min_size=min_size, row_tiers=tiers)
            if len(n2) > len(nests):
                k, nests = finer, n2
    if not nests:
        raise ValueError("no pocket passed the density gate")
    share = sum(n["members"].size for n in nests) / len(idx)
    job.say(f"{len(nests)} pockets holding {share:.0%} of the selection — dating them …")
    describe_nests(nests, rows, X=X)
    group_nests(nests, center)
    del X, rows

    centroids = np.vstack([n["centroid"] for n in nests])
    thresholds = np.array([max(HIST_SIM_FLOOR, n["radius_p25"]) for n in nests], np.float32)
    arch = np.flatnonzero(member)

    def batches():
        for s in range(0, len(arch), 20_000):
            part = arch[s:s + 20_000]
            Xa = store.X[part].astype(np.float32)
            Xa /= np.clip(np.linalg.norm(Xa, axis=1, keepdims=True), 1e-9, None)
            yield Xa, fetch_rows([int(i) for i in store.ids[part]])
    hist = scan_history(centroids, thresholds, batches=batches(),
                        tag_windows=(_month_back(OLD_TAG_WINDOW[1], now),
                                     _month_back(OLD_TAG_WINDOW[0], now)),
                        actor_windows=(_month_back(ACTOR_WINDOW[1], now),
                                       _month_back(ACTOR_WINDOW[0], now)))
    score_nests(nests, hist, now=now)
    job.say(f"dated against {hist['scanned']:,} archive signals of the domain")
    name_note = name_all(nests, job.say)
    since = month_str(since_m) + "-01"
    params = {"mode": "live", "term": job.term, "also": job.also,
              "window_months": job.window_months, "min_size": min_size,
              "cohesion_quantile": DOMAIN_COHESION_QUANTILE, "cells": k,
              "members_window": int(len(idx)), "members_archive": int(len(arch)),
              "in_pockets": round(share, 3), "naming": name_note,
              "seconds": {"select": job.t_select, "pockets": round(time.time() - t0, 1)}}
    run_id = persist_run(f"domain:{job.key}", "signal,published", since,
                         job.window_months * 30, k, nests, hist, params=params)
    prune_old_emerging_runs(keep_per_scope=1)
    groups = {}
    for n in nests:
        groups.setdefault(n.get("group_id") or 0, []).append(n)
    job.t_pockets = round(time.time() - t0, 1)
    job.result = {
        "run_id": run_id, "scope": f"domain:{job.key}", "nests": len(nests),
        "groups": len(groups), "in_pockets": round(share, 3),
        "named": sum(1 for n in nests if n.get("llm_label")), "naming": name_note,
        "outline": [{"group": g, "label": (ns[0].get("group_label") or None),
                     "nests": [{"name": n.get("llm_label") or n["label"], "size": n["size"],
                                "first_month": n.get("first_month")} for n in ns]}
                    for g, ns in sorted(groups.items())],
    }
    job.state = "done"
    job.say(f"done: run {run_id}, {len(nests)} pockets in {len(groups)} groups "
            f"({job.t_pockets:.0f}s)")


def discard(job: Job) -> None:
    if job.state in ("preview", "failed", "queued"):
        _restore_probe(job.key, job._previous_probe)
    job.state = "discarded"
    job._p = job._thr = None
    job.say("discarded")


def delete_domain(key: str) -> dict:
    """Remove a free-term domain: its probe and its runs (q_* keys only)."""
    if not key.startswith("q_"):
        raise ValueError("only free-term domains (q_…) can be deleted here")
    scope = f"domain:{key}"
    with get_connection() as c:
        runs = [int(r["id"]) for r in c.execute("SELECT id FROM emerging_runs WHERE scope = ?",
                                                 (scope,)).fetchall()]
        if runs:
            c.execute("DELETE FROM emerging_nests WHERE run_id = ANY(?)" if db_mod.USE_POSTGRES
                      else f"DELETE FROM emerging_nests WHERE run_id IN ({','.join('?' * len(runs))})",
                      (runs,) if db_mod.USE_POSTGRES else tuple(runs))
            c.execute("DELETE FROM emerging_runs WHERE scope = ?", (scope,))
        c.execute("DELETE FROM domain_probes WHERE key = ?", (key,))
    return {"key": key, "runs_deleted": len(runs)}


class Service:
    def __init__(self, store: Store) -> None:
        self.store = store
        self.jobs: dict[str, Job] = {}
        self.q: queue.Queue = queue.Queue()
        self.ready = False
        self.current: str | None = None

    def submit(self, term: str, also: list[str], window_months: int) -> Job:
        if not term or not term.strip():
            raise ValueError("empty term")
        if len(term) > 80:
            raise ValueError("term too long (80 characters at most)")
        job = Job(term, also[:6], max(3, min(int(window_months or WINDOW_MONTHS), 36)))
        self.jobs[job.id] = job
        while len(self.jobs) > MAX_JOBS_KEPT:
            self.jobs.pop(next(iter(self.jobs)))
        self.q.put((job.id, "select"))
        return job

    def confirm(self, job_id: str) -> Job:
        job = self.jobs[job_id]
        if job.state != "preview":
            raise ValueError(f"job is {job.state}, not waiting for confirmation")
        job.state = "queued"
        job.say("queued for pocket discovery")
        self.q.put((job_id, "pockets"))
        return job

    def worker(self) -> None:
        try:
            self.store.open()
        except Exception:                        # noqa: BLE001
            logger.error("could not open the vector copy:\n%s", traceback.format_exc())
            self.store.loading = "failed — see the service log"
            return
        self.ready = True
        while True:
            job_id, stage = self.q.get()
            job = self.jobs.get(job_id)
            if job is None or job.state == "discarded":
                continue
            self.current = job_id
            try:
                (run_select if stage == "select" else run_pockets)(self.store, job)
            except Exception as exc:             # noqa: BLE001
                job.state = "failed"
                job.error = f"{exc.__class__.__name__}: {exc}"
                job.say(f"failed — {job.error}")
                logger.error("[%s] %s", job.key, traceback.format_exc())
            finally:
                self.current = None
                if job.state in ("done", "failed"):
                    job._p = job._thr = None

    def health(self) -> dict:
        s = self.store
        return {"ready": self.ready, "loading": s.loading, "rows": s.n,
                "built_at": s.built_at,
                "refreshed_at": (datetime.fromtimestamp(s.refreshed_at).isoformat(timespec="seconds")
                                 if s.refreshed_at else None),
                "queue": self.q.qsize(), "running": self.current,
                "memory_gb": round(s.X.nbytes / 2 ** 30, 2)}


def make_handler(svc: Service):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):      # quiet; the job log is the record
            return

        def _send(self, code: int, obj) -> None:
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _body(self) -> dict:
            n = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(n) or b"{}") if n else {}

        def do_GET(self):                        # noqa: N802
            parts = [p for p in self.path.split("?")[0].split("/") if p]
            if parts == ["health"]:
                return self._send(200, svc.health())
            if parts == ["jobs"]:
                return self._send(200, [j.public() for j in reversed(list(svc.jobs.values()))])
            if len(parts) == 2 and parts[0] == "jobs" and parts[1] in svc.jobs:
                return self._send(200, svc.jobs[parts[1]].public())
            return self._send(404, {"error": "not found"})

        def do_POST(self):                       # noqa: N802
            parts = [p for p in self.path.split("?")[0].split("/") if p]
            try:
                if parts == ["jobs"]:
                    b = self._body()
                    job = svc.submit(str(b.get("term") or ""), [str(a) for a in b.get("also") or []],
                                     int(b.get("window_months") or WINDOW_MONTHS))
                    return self._send(202, job.public())
                if len(parts) == 3 and parts[0] == "jobs" and parts[1] in svc.jobs:
                    if parts[2] == "confirm":
                        return self._send(202, svc.confirm(parts[1]).public())
                    if parts[2] == "discard":
                        job = svc.jobs[parts[1]]
                        discard(job)
                        return self._send(200, job.public())
                if len(parts) == 3 and parts[0] == "domains" and parts[2] == "delete":
                    return self._send(200, delete_domain(parts[1]))
            except (ValueError, KeyError) as exc:
                return self._send(400, {"error": str(exc)})
            return self._send(404, {"error": "not found"})
    return Handler


def main() -> int:
    ap = argparse.ArgumentParser(description="Live pocket discovery for a free term")
    ap.add_argument("--port", type=int, default=PORT)
    ap.add_argument("--rebuild", action="store_true", help="rebuild the vector copy and exit")
    ap.add_argument("--once", metavar="TERM", help="run one job (select + pockets) and exit")
    ap.add_argument("--also", default="", help="with --once: comma-separated synonyms")
    ap.add_argument("--window-months", type=int, default=WINDOW_MONTHS)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
    store = Store()
    if args.rebuild:
        store.open(rebuild=True)
        return 0
    if args.once:
        store.open()
        job = Job(args.once, [a for a in args.also.split(",") if a.strip()], args.window_months)
        run_select(store, job)
        print(json.dumps({k: v for k, v in job.preview.items() if k not in ("examples", "just_outside")},
                         indent=2))
        for e in job.preview["examples"]:
            print(f"  in      {e['p']:.2f} {e['tier']:8s} {e['title'][:100]}")
        for e in job.preview["just_outside"]:
            print(f"  outside {e['p']:.2f} {e['tier']:8s} {e['title'][:100]}")
        if job.preview["enough"]:
            run_pockets(store, job)
            print(json.dumps(job.result, indent=2))
        return 0
    svc = Service(store)
    threading.Thread(target=svc.worker, name="domain-worker", daemon=True).start()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(svc))
    logger.info("domain service on 127.0.0.1:%d", args.port)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
