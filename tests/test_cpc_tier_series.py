"""Tests for the cross-tier lead-time core (#9): SoV-based S-curve takeoff and
the emergence gate that keeps established fields (and thin-signal noise) from
fabricating a lead-time. Pure functions — no DB."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.build_cpc_tier_series import _sov_takeoff, EMERGENCE_MAX_START


def test_takeoff_on_clean_s_curve():
    # SoV rises from ~0 to a peak of 0.4; 50%-of-peak (0.2) first reached in 2015
    sov = {2010: 0.01, 2011: 0.02, 2012: 0.05, 2013: 0.10,
           2014: 0.18, 2015: 0.25, 2016: 0.35, 2017: 0.40}
    takeoff, genuine = _sov_takeoff(sov, 2010, 2017)
    assert takeoff == 2015
    assert genuine is True  # started near zero → real emergence


def test_established_field_not_genuine():
    # SoV already high at window start (present all along) → not an emergence,
    # so no defensible lead-time even though a "takeoff" year exists
    sov = {2010: 0.30, 2011: 0.32, 2012: 0.28, 2013: 0.31,
           2014: 0.35, 2015: 0.33, 2016: 0.34, 2017: 0.30}
    takeoff, genuine = _sov_takeoff(sov, 2010, 2017)
    assert genuine is False


def test_too_few_points_returns_none():
    assert _sov_takeoff({2015: 0.5, 2016: 0.6}, 2015, 2016) == (None, False)


def test_flat_zero_series():
    assert _sov_takeoff({y: 0.0 for y in range(2010, 2018)}, 2010, 2017) == (None, False)


def test_emergence_threshold_boundary():
    # start level exactly at the emergence ceiling → not genuine (strict <)
    peak = 1.0
    start = peak * EMERGENCE_MAX_START
    sov = {2010: start, 2011: start, 2012: start, 2013: 0.5,
           2014: 0.7, 2015: 0.9, 2016: peak}
    _, genuine = _sov_takeoff(sov, 2010, 2016)
    assert genuine is False
