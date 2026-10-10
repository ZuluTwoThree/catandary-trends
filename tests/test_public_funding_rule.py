"""Öffentliche Förderung ist immer ein Trendsignal (Owner 2026-10-10)."""
from pipeline import llm_processor as lp
from pipeline.tiers import is_public_funding, tier_of


def test_public_funding_names():
    for n in ("Förderinfo Bund – Bekanntmachungen (alle)", "Förderdatenbank des Bundes",
              "NSF Awards (US Federal Research Funding)", "NIH RePORTER (US Biomedical Funding)",
              "OpenAIRE Projects (EU + National Funders)", "UKRI Gateway to Research (UK)",
              "SBIR/STTR Awards (US Startup R&D Funding)", "CORDIS EU Research Projects (SME Participations)"):
        assert is_public_funding(n), n
    for n in ("SEC Form D (Startup Private Offerings)", "Tech Funding News", "TechCrunch", None):
        assert not is_public_funding(n), n


def test_rule_relevance_and_signal_type():
    e = {"source_name": "Förderinfo Bund – Bekanntmachungen (alle)", "source_type": "press_wire",
         "source_vertical": "health"}
    r = lp.public_funding_relevance(e)
    assert r.is_relevant and r.confidence == 1.0 and r.reason == "rule:public_funding"
    assert r.primary_vertical == "HEALTH"
    assert lp._distill_signal_type(e, {"signal_type": "market_shift", "signal_type_confidence": 0.99}) == "funding"
    # Presse-Feed mit Signaltyp funding zählt überall zur Ebene Förderung
    assert tier_of(e["source_name"], e["source_type"], "funding") == "funding"
    assert lp.public_funding_relevance({"source_name": "x", "source_vertical": "CROSS"}).primary_vertical == "TECH"


def test_form_d_keeps_its_own_rules():
    e = {"source_name": "SEC Form D (Startup Private Offerings)", "source_type": "api"}
    assert lp._distill_signal_type(e) == "funding"        # über den bisherigen API-Zweig
    assert not is_public_funding(e["source_name"])        # aber kein Relevanz-Freifahrtschein
