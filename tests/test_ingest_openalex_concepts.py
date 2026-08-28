"""Regression guard for the CONCEPT_SHARDS fix (#81): "sustainable architecture"
and "creator economy" returned zero results against the OpenAlex /concepts
search API (verified 2026-08-28 via a live curl check) and were replaced with
concepts that do resolve. This just pins the dict content — see
scripts/ingest_openalex.py for the live-API verification notes."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.ingest_openalex import CONCEPT_SHARDS


def test_broken_concepts_removed():
    all_shards = {c for shards in CONCEPT_SHARDS.values() for c in shards}
    assert "sustainable architecture" not in all_shards
    assert "creator economy" not in all_shards


def test_replacement_concepts_present():
    assert "sustainable design" in CONCEPT_SHARDS["DESIGN"]
    assert "green building" in CONCEPT_SHARDS["DESIGN"]
    assert "influencer marketing" in CONCEPT_SHARDS["LIFESTYLE"]
    assert "user-generated content" in CONCEPT_SHARDS["LIFESTYLE"]


def test_no_duplicate_shards_within_a_vertical():
    """Guards against accidentally reintroducing "social media" twice etc."""
    for vertical, shards in CONCEPT_SHARDS.items():
        assert len(shards) == len(set(shards)), f"duplicate concept shard in {vertical}"
