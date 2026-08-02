"""Newsletter citation de-duplication.

Regression for the 2026-W31 FOOD collision: two write-ups of the same
Campylobacter/poultry study (Food Safety News + Guardian Environment) were both
cited in the same three-signal list, which reads as unchecked output.

The pair scores only ~0.67 on fuzz.ratio — below the 0.90 title threshold — so
the title check alone can never catch this class; the embedding similarity
(measured 0.845 vs 0.31-0.34 for genuinely distinct signals) is what separates
them. These tests cover the pure selection logic; the embedding lookup itself
needs Postgres and is exercised in the live run.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.newsletter_generator import _pick_distinct, TOP_CANDIDATE_POOL


# The real titles from the 2026-W31 collision.
DUP_A = {"id": 1128603, "title_en": "Intensive Poultry Farming Accelerates Campylobacter Strain Exchange"}
DUP_B = {"id": 1129992, "title_en": "Poultry Farming Environments Drive Campylobacter Strain Evolution"}
OTHER = {"id": 1129978, "title_en": "Stingless Bee Honey Emerges as a Targeted Functional Food Ingredient"}
THIRD = {"id": 1130001, "title_en": "Pladis Reformulates Product Lines to Target High-Protein Segments"}

PAIRS = {(1128603, 1129992)}  # what the embedding lookup reports


def test_drops_the_near_duplicate():
    picked = _pick_distinct([DUP_A, DUP_B, OTHER], PAIRS, 3)
    ids = [p["id"] for p in picked]
    assert ids == [1128603, 1129978], "second write-up of the same story must go"


def test_keeps_the_higher_ranked_of_a_pair():
    # Candidates arrive score-ordered, so whichever comes first is the stronger
    # signal and must be the survivor — regardless of pair-tuple ordering.
    picked = _pick_distinct([DUP_B, DUP_A, OTHER], PAIRS, 3)
    assert [p["id"] for p in picked] == [1129992, 1129978]


def test_duplicate_is_backfilled_not_just_removed():
    """Dropping a duplicate must not shorten the citation list."""
    picked = _pick_distinct([DUP_A, DUP_B, OTHER, THIRD], PAIRS, 3)
    assert len(picked) == 3
    assert [p["id"] for p in picked] == [1128603, 1129978, 1130001]


def test_distinct_signals_are_untouched():
    picked = _pick_distinct([DUP_A, OTHER, THIRD], PAIRS, 3)
    assert len(picked) == 3


def test_no_pairs_means_no_embedding_filtering():
    """SQLite / missing vectors: the lookup returns an empty set and these two
    titles are far enough apart that the fallback keeps both."""
    picked = _pick_distinct([DUP_A, DUP_B, OTHER], set(), 3)
    assert len(picked) == 3


def test_title_fallback_catches_verbatim_repeats():
    """Same story republished under a near-identical headline is caught even
    without embeddings."""
    a = {"id": 1, "title_en": "EU Commission Launches Tender for AI Gigafactories"}
    b = {"id": 2, "title_en": "EU Commission Launches Tenders for AI Gigafactories"}
    picked = _pick_distinct([a, b], set(), 3)
    assert len(picked) == 1


def test_limit_is_respected():
    # Genuinely different stories — headlines that differ only by a number would
    # (correctly) trip the title check, which is itself covered above.
    headlines = [
        "Antora Energy Secures $550 Million for Thermal Storage",
        "EU Commission Tenders Seven AI Gigafactories",
        "xAI Challenges Minnesota Law on Image Editing",
        "Stingless Bee Honey Emerges as Functional Ingredient",
        "US Bans Foreign-Made Inverters From Federal Projects",
        "Moonshot Releases Kimi K3 Model Weights Free",
        "Ethiopian Coffee Smallholders Face Deforestation Rules",
    ]
    cands = [{"id": i, "title_en": h} for i, h in enumerate(headlines)]
    assert len(_pick_distinct(cands, set(), 5)) == 5


def test_candidate_pool_exceeds_pick_count():
    """Backfilling only works if we collect more candidates than we cite."""
    assert TOP_CANDIDATE_POOL > 10
