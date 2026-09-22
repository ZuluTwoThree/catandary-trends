"""Review-Agent (Test 2026-09-22): die Beleg-Regeln ohne Modell und ohne DB."""
from pipeline.review_agent import (FigureVerdict, evidence_in_source, sentence_with, verify_verdict)

SRC = ("OneWeb is based on a constellation of satellites in low earth orbit, positioned approximately "
       "1 000 kilometres from earth. Le 12 juin 2026 à 23 heures, les équipes … Seventy percent said "
       "they’re using it for search.")


def test_verbatim_quote_is_found_despite_whitespace_quotes_and_case():
    assert evidence_in_source("positioned approximately 1 000 kilometres", SRC)
    assert evidence_in_source("SEVENTY PERCENT said they're using it", SRC)      # ’ vs '
    assert evidence_in_source("  positioned   approximately 1 000 kilometres.", SRC)


def test_paraphrase_or_translation_is_not_verbatim():
    assert not evidence_in_source("positioned about 1,000 km from earth", SRC)
    assert not evidence_in_source("11:00 PM on June 12, 2026", SRC)
    assert not evidence_in_source("2026", SRC)                                    # zu kurz


def test_verdict_needs_support_plus_verbatim_evidence():
    ok, why = verify_verdict(FigureVerdict(supported=True, evidence="approximately 1 000 kilometres", form="format"), SRC)
    assert ok and why == "format"
    ok, why = verify_verdict(FigureVerdict(supported=True, evidence="about 1,000 km", form="format"), SRC)
    assert not ok and "verbatim" in why
    ok, why = verify_verdict(FigureVerdict(supported=False, evidence="", form="not-found"), SRC)
    assert not ok and "not supported" in why
    ok, why = verify_verdict(FigureVerdict(supported=True, evidence="", form="same"), SRC)
    assert not ok and "without evidence" in why
    ok, _ = verify_verdict(None, SRC)
    assert not ok


def test_evidence_without_digits_counts_only_for_number_word_forms():
    ok, _ = verify_verdict(FigureVerdict(supported=True, evidence="Seventy percent said they’re using it", form="number-word"), SRC)
    assert ok
    ok, why = verify_verdict(FigureVerdict(supported=True, evidence="Seventy percent said they’re using it", form="same"), SRC)
    assert not ok and "no figure" in why


def test_sentence_with_token_picks_the_carrying_sentence():
    body = "First sentence has nothing. The plant makes 20,000 tonnes a year. Last one."
    assert sentence_with(body, "20,000") == "The plant makes 20,000 tonnes a year."
    assert sentence_with(body, "999").startswith("First sentence")
