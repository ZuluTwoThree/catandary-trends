"""Research Pulse (#73) — reine Helfer ohne DB/GPU: Wochenlogik, Volumen-
Verhältnis, k-Regel, deterministisches Clustering + Labels, Prompt, Wortwächter,
SQLite-Schema/Insert (Vertrag der Tabelle)."""
from datetime import date

import numpy as np
import pytest

from pipeline import research_pulse as rp


# ---- Wochenlogik ----------------------------------------------------------

def test_iso_week_bounds_monday_to_sunday():
    mon, sun = rp.iso_week_bounds(2026, 35)
    assert mon == date(2026, 8, 24) and sun == date(2026, 8, 30)
    assert mon.isoweekday() == 1 and sun.isoweekday() == 7


def test_default_week_is_last_completed_week():
    # Samstag 2026-09-05 (Cron-Slot) → Vorwoche W35, nicht die laufende W36
    assert rp.default_week(date(2026, 9, 5)) == (2026, 35)
    # Montag 2026-08-31 → ebenfalls W35 (Newsletter-Regel: 7 Tage zurück)
    assert rp.default_week(date(2026, 8, 31)) == (2026, 35)
    # Jahreswechsel: 2026-01-04 (So, ISO W1) − 7 = 2025-12-28 → 2025-W52
    assert rp.default_week(date(2026, 1, 4)) == (2025, 52)


@pytest.mark.parametrize("text,expected", [
    ("2026-W35", (2026, 35)), ("2026-w05", (2026, 5)), ("2026-35", (2026, 35)),
])
def test_parse_week(text, expected):
    assert rp.parse_week(text) == expected


@pytest.mark.parametrize("bad", ["", "W35", "2026-W54", "2026-W0", "35-2026"])
def test_parse_week_rejects(bad):
    with pytest.raises(ValueError):
        rp.parse_week(bad)


def test_prior_weeks_cross_year():
    assert rp.prior_weeks(2026, 2, n=3) == [(2025, 51), (2025, 52), (2026, 1)]
    assert rp.prior_weeks(2026, 35) == [(2026, 31), (2026, 32), (2026, 33), (2026, 34)]


# ---- Kennzahlen -----------------------------------------------------------

def test_volume_ratio_uses_median_of_prior_weeks():
    assert rp.volume_ratio(120, [100, 90, 110, 400]) == pytest.approx(120 / 105, abs=5e-4)
    assert rp.volume_ratio(50, [0, 0, 0, 0]) is None
    assert rp.volume_ratio(50, []) is None
    assert rp.volume_ratio(0, [10, 10, 10, 10]) == 0.0


@pytest.mark.parametrize("n,k", [(0, 1), (3, 1), (7, 1), (8, 1), (16, 2), (39, 4), (40, 5), (6000, 5)])
def test_choose_k(n, k):
    assert rp.choose_k(n) == k


def test_source_groups_and_oa():
    assert rp.source_group("arXiv Preprints") == "preprints"
    assert rp.source_group("OpenAlex fresh: Agronomy") == "openalex"
    assert rp.source_group("OpenAlex: Quantum") == "openalex"
    assert rp.source_group("Nature (main)") == "journals"
    assert rp.is_open_access("medrxiv Preprints") is True
    assert rp.is_open_access("Nature (main)") is False


# ---- Clustering -----------------------------------------------------------

def _rows(seed=1, n=48, dim=16):
    rng = np.random.default_rng(seed)
    centers = rng.normal(size=(3, dim))
    rows = []
    words = [("perovskite solar cell stability", "Photovoltaic system"),
             ("gut microbiome fermentation probiotic", "Microbiome"),
             ("transformer language model reasoning", "Artificial intelligence")]
    for i in range(n):
        c = i % 3
        vec = centers[c] + rng.normal(scale=0.1, size=dim)
        rows.append({"trend_id": 1000 - i, "title": f"{words[c][0]} study {i}",
                     "abstract": f"We report {words[c][0]} results.", "url": f"https://x/{i}",
                     "source": "arXiv Preprints" if c == 2 else "OpenAlex fresh: X",
                     "concept": words[c][1], "published": "2026-08-25",
                     "vec": vec.astype(np.float32)})
    return rows


def test_build_clusters_is_deterministic_and_labelled():
    a, _ = rp.build_clusters(_rows())
    b, _ = rp.build_clusters(list(reversed(_rows())))   # Eingabereihenfolge egal
    assert [c["n"] for c in a] == [c["n"] for c in b]
    assert [c["label"] for c in a] == [c["label"] for c in b]
    assert [[p["trend_id"] for p in c["papers"]] for c in a] == \
           [[p["trend_id"] for p in c["papers"]] for c in b]
    assert len(a) == rp.choose_k(48) == 5
    assert sum(c["n"] for c in a) == 48
    for c in a:
        assert c["label"] and c["terms"], c
        assert 1 <= len(c["papers"]) <= rp.TOP_PAPERS_PER_CLUSTER
        assert all(p["oa"] == (p["source"] == "arXiv Preprints") for p in c["papers"])
    # die drei echten Gruppen tauchen in den Labels auf
    labels = " ".join(c["label"] for c in a)
    assert "perovskite" in labels and "microbiome" in labels and "transformer" in labels


def test_apply_prior_counts_growth_and_emerging():
    clusters, _ = rp.build_clusters(_rows(n=24))
    idx = [c["idx"] for c in clusters]
    rp.apply_prior_counts(clusters, {idx[0]: 4, idx[1]: 40}, prior_weeks_n=4)
    first = next(c for c in clusters if c["idx"] == idx[0])
    second = next(c for c in clusters if c["idx"] == idx[1])
    assert first["prior_weekly_mean"] == 1.0 and first["growth"] == first["n"] / 1.0
    assert first["emerging"] is (first["n"] >= 5)
    assert second["growth"] == pytest.approx(second["n"] / 10.0, abs=0.01)
    assert second["emerging"] is False
    # kein Vorwochen-Vorkommen → growth None, emerging nur ab 5 Papers
    missing = [c for c in clusters if c["idx"] not in (idx[0], idx[1])]
    for c in missing:
        assert c["growth"] is None and c["prior_n"] == 0


def test_small_theme_single_block_and_empty():
    clusters, cents = rp.build_clusters(_rows(n=5))
    assert len(clusters) == 1 and clusters[0]["n"] == 5 and len(cents) == 1
    assert rp.build_clusters([]) == ([], [])


# ---- Messblock, Prompt, Wortwächter ----------------------------------------

def test_week_stats_shape():
    rows = _rows(n=12)
    prior = [{"year": 2026, "week": w, "n": n} for w, n in zip((31, 32, 33, 34), (10, 12, 8, 30))]
    st = rp.week_stats(rows, 12, prior, (date(2026, 8, 24), date(2026, 8, 30)), 12)
    assert st["ratio"] == pytest.approx(12 / 11, abs=5e-4)
    assert st["sources"] == {"openalex": 8, "preprints": 4}
    assert st["oa_n"] == 4 and st["k"] == 1
    assert st["top_concepts"][0][0] in ("Photovoltaic system", "Microbiome", "Artificial intelligence")
    assert st["window"] == {"start": "2026-08-24", "end": "2026-08-30"}


def test_prompt_carries_numbers_and_no_forecast_ask():
    clusters, _ = rp.build_clusters(_rows(n=24))
    rp.apply_prior_counts(clusters, {c["idx"]: 8 for c in clusters})
    st = rp.week_stats(_rows(n=24), 24, [{"year": 2026, "week": w, "n": 20} for w in range(31, 35)],
                       (date(2026, 8, 24), date(2026, 8, 30)), 24)
    p = rp.build_prompt({"key": "x", "name_en": "X Theme", "description": "d"}, st, clusters)
    assert "Papers this week: 24" in p and "median 20" in p and "+20%" in p
    assert "100 to 150 words" in p and "do not say what it means for the future" in p
    for c in clusters:
        assert c["label"] in p


def test_ratio_phrase():
    assert rp.ratio_phrase(None) == "no comparable prior weeks"
    assert rp.ratio_phrase(1.02) == "about level with the prior four-week median"
    assert rp.ratio_phrase(1.31) == "+31% versus the prior four-week median"
    assert rp.ratio_phrase(0.7) == "-30% versus the prior four-week median"


def test_text_guard_and_cleaning():
    good = " ".join(["word"] * 120)
    assert rp.text_ok(good)
    assert not rp.text_ok(" ".join(["word"] * 40))
    assert not rp.text_ok(" ".join(["word"] * 260))
    assert not rp.text_ok("- " + good)
    assert rp.clean_text("**Research Pulse: X**\nFirst line.\nSecond line.") == "First line. Second line."


def test_generate_text_retries_once_then_accepts_last():
    calls = []

    def fake_chat(model, prompt, system, temperature, seed, max_tokens):
        calls.append(seed)
        return "too short"
    text, note = rp.generate_text({"key": "x", "name_en": "X"}, _stats(), [], chat=fake_chat)
    assert calls == [rp.PULSE_SEED, rp.PULSE_SEED + 1]
    assert text == "too short" and note and "word guard" in note

    ok = " ".join(["fine"] * 110)
    text, note = rp.generate_text({"key": "x", "name_en": "X"}, _stats(), [],
                                  chat=lambda **kw: ok)
    assert text == ok and note is None


def _stats():
    return rp.week_stats([], 0, [], (date(2026, 8, 24), date(2026, 8, 30)), 0)


# ---- Tabelle (SQLite-Vertrag) -----------------------------------------------

def test_schema_and_save_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "pulse.db"))
    from pipeline.db import get_connection
    with get_connection() as conn:
        rp.ensure_schema(conn)
        rp.ensure_schema(conn)  # idempotent
        res = {"theme": "x", "year": 2026, "week": 35, "week_start": date(2026, 8, 24),
               "stats": _stats(), "clusters": []}
        rid = rp.save_pulse(conn, res, "text", "gemma", 1.23, None)
        rid2 = rp.save_pulse(conn, res, None, None, 0.5, "no-llm run")
        assert rid2 > rid
        rows = conn.execute("SELECT theme, year, week, text, model, note FROM research_pulse "
                            "ORDER BY id").fetchall()
        assert [dict(r) for r in rows] == [
            {"theme": "x", "year": 2026, "week": 35, "text": "text", "model": "gemma", "note": None},
            {"theme": "x", "year": 2026, "week": 35, "text": None, "model": None, "note": "no-llm run"},
        ]
