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


def test_dfg_and_new_call_feeds_are_public_funding():
    from pipeline.tiers import is_funding_signal_only
    for n in ("DFG", "UKRI Funding Opportunities", "Funding call: ANR Appels à projets (France)"):
        assert is_public_funding(n), n
        assert tier_of(n, "press_wire", "funding") == "funding"
    # Förderdatenbank: nur Signale (Owner 10.10., 1b); Förderinfo Bund schreibt weiter Artikel
    assert is_funding_signal_only("Förderdatenbank des Bundes")
    assert is_funding_signal_only("Förderdatenbank des Bundes (Pressemitteilungen)")
    assert not is_funding_signal_only("Förderinfo Bund – Bekanntmachungen (alle)")
    assert not is_funding_signal_only("DFG")


def test_judge_prompt_carries_funding_rule(monkeypatch):
    """Der Richter hielt 64 von 71 Förder-Entwürfen als no_signal (10.10.) — Entscheid 1a."""
    from pipeline import draft_judge, llamacpp_client
    seen = []
    monkeypatch.setattr(llamacpp_client, "chat_structured",
                        lambda **k: seen.append(k["prompt"]) or None)
    base = {"re_title": "T", "raw_content": "Quelle", "excerpt": "", "title_en": "X",
            "body_en": "Y", "extraction_json": None}
    draft_judge.judge_one({**base, "source_name": "Förderinfo Bund – Bekanntmachungen (alle)"})
    draft_judge.judge_one({**base, "source_name": "TechCrunch"})
    assert seen[0].startswith("EDITORIAL RULE") and "do NOT use no_signal" in seen[0]
    assert "EDITORIAL RULE" not in seen[1]


def test_numeric_source_dates_ground_written_out_dates():
    """Förderinfo Bund: „02.09.2026 - 14.10.2026“ ↔ „September 2, 2026“ (10.10.)."""
    from pipeline.grounding import ungrounded_specifics
    src = "PROKIWA | 02.09.2026 - 14.10.2026 Infoveranstaltung 17.09.2026"
    assert ungrounded_specifics("Released September 2, 2026; info session September 17, 2026; "
                                "deadline October 14, 2026.", src) == []
    assert ungrounded_specifics("It funds 250 projects from September 2, 2026.", src) == ["250"]
    assert ungrounded_specifics("Closes on October 14.", "Frist 2026-10-14") == []
    assert ungrounded_specifics("Closes on October 23.", "Frist 2026-10-14") == ["23."]
