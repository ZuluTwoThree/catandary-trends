"""Unit tests for the TIR-trajectory classifier (#36) — pure functions, no DB."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.tir_trajectory import (
    classify, build_points, DOMAIN_MIN_TOTAL, CALIB_MAX, MIN_N, TRUNC_YEARS,
    DIRECTION_MIN_MEDIAN_N, ACCEL_PP,
)


def _pts(years_ks, complete_upto, n=2000):
    # n defaults to a clearly-dense window (above DIRECTION_MIN_MEDIAN_N) so the
    # direction gate passes; thin-window behaviour is tested explicitly.
    return [{"year": y, "K": k, "n": n, "complete": y <= complete_upto}
            for y, k in years_ks]


def test_accelerating_recent_rise():
    pts = _pts([(y, 5 + (y - 2010)) for y in range(2010, 2020)], 2019)
    r = classify(pts, n_total=50_000)
    assert r["direction"] == "accelerating"
    assert r["rel_change"] > 0


def test_maturing_recent_decline():
    pts = _pts([(y, 30 - (y - 2010) * 1.2) for y in range(2010, 2020)], 2019)
    r = classify(pts, n_total=50_000)
    assert r["direction"] in ("maturing", "decelerating")
    assert r["rel_change"] < 0


def test_steady_flat():
    pts = _pts([(y, 12.0) for y in range(2010, 2020)], 2019)
    r = classify(pts, n_total=50_000)
    assert r["direction"] == "steady"


def test_insufficient_total_patents():
    pts = _pts([(y, 10) for y in range(2010, 2020)], 2019)
    r = classify(pts, n_total=DOMAIN_MIN_TOTAL - 1)
    assert r["direction"] == "insufficient_data"
    assert r["K_latest"] is None


def test_insufficient_few_complete_windows():
    # only 2 complete windows → insufficient regardless of total
    pts = _pts([(2018, 10), (2019, 11), (2020, 12), (2021, 13)], 2019)
    r = classify(pts, n_total=50_000)
    assert r["direction"] == "insufficient_data"


def test_calibration_gate_withholds_absolute():
    # median K above the calibrated ceiling → direction only, no absolute value
    pts = _pts([(y, CALIB_MAX + 30) for y in range(2010, 2020)], 2019)
    r = classify(pts, n_total=50_000)
    assert r["calibrated"] is False
    assert r["K_latest"] is None
    assert "outside" in (r["reason"] or "")


def test_calibrated_reports_absolute():
    pts = _pts([(y, 12.0) for y in range(2010, 2020)], 2019)
    r = classify(pts, n_total=50_000)
    assert r["calibrated"] is True
    assert r["K_latest"] == 12.0


def test_direction_ignores_truncated_tail():
    # a huge drop in the truncated tail must NOT flip a rising signal
    rising = [(y, 5 + (y - 2010)) for y in range(2010, 2020)]
    truncated_crash = [(2020, 2), (2021, 1), (2022, 1)]
    pts = _pts(rising + truncated_crash, complete_upto=2019)
    r = classify(pts, n_total=50_000)
    assert r["direction"] == "accelerating"


def test_direction_uncertain_when_windows_thin():
    # a strong-looking recent rise but on THIN windows → direction withheld,
    # trajectory + value still shown (the #36 density honesty gate).
    pts = _pts([(y, 5 + (y - 2010)) for y in range(2010, 2020)], 2019,
               n=DIRECTION_MIN_MEDIAN_N - 1)
    r = classify(pts, n_total=50_000)
    assert r["direction"] == "uncertain"
    assert r["rel_change"] is not None      # trajectory still computed
    assert r["K_latest"] is not None        # K value still shown
    assert r["median_recent_n"] < DIRECTION_MIN_MEDIAN_N


def test_mild_rise_on_dense_windows_is_steady_not_accelerating():
    # ~+0.18 relative rise sits on the mundane baseline (~+0.15) → steady, NOT
    # accelerating. Under the old ACCEL_PP=0.15 this was a false "accelerating".
    pts = _pts([(2010, 10.0), (2011, 10.0), (2012, 10.0), (2013, 10.0),
                (2014, 10.4), (2015, 10.8), (2016, 11.2), (2017, 11.4),
                (2018, 11.7), (2019, 12.0)], 2019)
    r = classify(pts, n_total=50_000)
    assert 0.10 < r["rel_change"] < ACCEL_PP
    assert r["direction"] == "steady"


def test_strong_rise_on_dense_windows_accelerates():
    pts = _pts([(y, 5 + (y - 2010) * 1.5) for y in range(2010, 2020)], 2019)
    r = classify(pts, n_total=50_000)
    assert r["direction"] == "accelerating"
    assert r["rel_change"] >= ACCEL_PP


def test_build_points_min_n_and_truncation():
    by_year = {y: (0.4, 500) for y in range(2000, 2027)}
    by_year[2001] = (0.4, 10)  # a thin year → its windows drop below MIN_N early
    pts = build_points(by_year, now_year=2026)
    assert pts, "should produce points"
    # every reported point clears the per-window MIN_N
    assert all(p["n"] >= MIN_N for p in pts)
    # truncation flag: last TRUNC_YEARS are incomplete
    assert all(p["complete"] is False for p in pts if p["year"] > 2026 - TRUNC_YEARS)
    assert any(p["complete"] for p in pts)
