"""Mirror of frontend/src/lib/momentum.test.ts — same cases, same expectations.
If one side changes thresholds, both suites must move."""
from pipeline.mega_momentum import classify


def test_no_claim_below_evidence_floor():
    assert classify(4, 5, 1000, 1000) is None
    assert classify(0, 0, 1000, 1000) is None


def test_share_change_not_raw_counts():
    assert classify(200, 100, 20000, 10000) == "stable"   # corpus doubled too
    assert classify(30, 40, 1000, 2000) == "rising"       # share +50 %
    assert classify(20, 40, 1000, 1000) == "declining"


def test_threshold_boundary():
    assert classify(114, 100, 1000, 1000) == "stable"
    assert classify(116, 100, 1000, 1000) == "rising"
    assert classify(86, 100, 1000, 1000) == "stable"
    assert classify(84, 100, 1000, 1000) == "declining"


def test_emerging_and_degenerate_totals():
    assert classify(12, 0, 1000, 1000) == "emerging"
    assert classify(50, 50, 0, 1000) is None
    assert classify(50, 50, 1000, 0) is None
