"""Tests for Pydantic models (schema validation)."""

import json
import pytest
from pydantic import ValidationError

from pipeline.models import (
    ClassificationResult,
    ExtractionResult,
    GeneratedContent,
    RelevanceResult,
)


class TestRelevanceResult:
    def test_valid_relevant(self):
        r = RelevanceResult(
            is_relevant=True,
            confidence=0.85,
            primary_vertical="FOOD",
            reason="New product launch in food sector",
        )
        assert r.is_relevant is True
        assert r.confidence == 0.85
        assert r.primary_vertical == "FOOD"

    def test_valid_not_relevant(self):
        r = RelevanceResult(
            is_relevant=False,
            confidence=0.2,
            primary_vertical="TECH",
            reason="Generic earnings report",
        )
        assert r.is_relevant is False

    def test_invalid_confidence_too_high(self):
        with pytest.raises(ValidationError):
            RelevanceResult(
                is_relevant=True,
                confidence=1.5,
                primary_vertical="FOOD",
                reason="test",
            )

    def test_invalid_confidence_negative(self):
        with pytest.raises(ValidationError):
            RelevanceResult(
                is_relevant=True,
                confidence=-0.1,
                primary_vertical="FOOD",
                reason="test",
            )

    def test_invalid_vertical(self):
        with pytest.raises(ValidationError):
            RelevanceResult(
                is_relevant=True,
                confidence=0.8,
                primary_vertical="INVALID",
                reason="test",
            )

    def test_json_roundtrip(self):
        r = RelevanceResult(
            is_relevant=True,
            confidence=0.9,
            primary_vertical="TECH",
            reason="AI breakthrough",
        )
        json_str = r.model_dump_json()
        r2 = RelevanceResult.model_validate_json(json_str)
        assert r == r2


class TestExtractionResult:
    def test_full_extraction(self):
        e = ExtractionResult(
            brand_name="Beyond Meat",
            product_name="Beyond Burger 4.0",
            source_type="press_release",
            key_claims=["50% less fat", "new protein blend"],
        )
        assert e.brand_name == "Beyond Meat"
        assert len(e.key_claims) == 2

    def test_empty_extraction(self):
        e = ExtractionResult()
        assert e.brand_name is None
        assert e.product_name is None
        assert e.key_claims == []

    def test_json_roundtrip(self):
        e = ExtractionResult(brand_name="Test", key_claims=["claim1"])
        e2 = ExtractionResult.model_validate_json(e.model_dump_json())
        assert e == e2

    def test_rich_extraction_fields_default_empty(self):
        # #11: new extractive fields default to empty lists (backward-compatible
        # with rows extracted before they existed).
        e = ExtractionResult()
        assert e.key_figures == []
        assert e.quotes == []
        assert e.dates == []
        assert e.geography == []

    def test_rich_extraction_roundtrip(self):
        e = ExtractionResult(
            key_claims=["cuts emissions"],
            key_figures=["7,980 jobs", "29,5 %"],
            quotes=['"a turning point"'],
            dates=["2027", "by Q3 2025"],
            geography=["EU", "Germany"],
        )
        e2 = ExtractionResult.model_validate_json(e.model_dump_json())
        assert e == e2
        assert "7,980 jobs" in e2.key_figures and "2027" in e2.dates


class TestClassificationResult:
    def test_valid_classification(self):
        c = ClassificationResult(
            verticals=["FOOD", "HEALTH"],
            pestel=["T", "S"],
            tags=["protein", "plant-based", "sustainability"],
            trend_signal_type="product_launch",
            regions=["EU", "US"],
            mega_trend="Personalized Nutrition",
        )
        assert len(c.verticals) == 2
        assert "FOOD" in c.verticals
        assert c.trend_signal_type == "product_launch"

    def test_invalid_vertical_in_list(self):
        with pytest.raises(ValidationError):
            ClassificationResult(
                verticals=["INVALID"],
                pestel=["T"],
                tags=["test"],
                trend_signal_type="product_launch",
            )

    def test_invalid_signal_type(self):
        with pytest.raises(ValidationError):
            ClassificationResult(
                verticals=["TECH"],
                pestel=["T"],
                tags=["test"],
                trend_signal_type="invalid_type",
            )


class TestGeneratedContent:
    def test_valid_content(self):
        g = GeneratedContent(
            title="Plant-Based Revolution Reaches New Heights",
            summary="Beyond Meat launches new product line.",
            body="The plant-based industry continues to grow..." * 5,
            source_attribution="Source: FoodNavigator (https://example.com)",
        )
        assert len(g.title) > 0
        assert len(g.body) > 0
