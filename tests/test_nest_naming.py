"""Naming is a grounded task: the model may only use the nest's own words."""

import pytest

from pipeline import nest_naming as N

TITLES = [
    "Retrieval-Augmented Generation with Dense Passage Retrieval for Clinical QA",
    "Improving RAG pipelines with hybrid retrieval and reranking",
    "Retrieval augmented generation reduces hallucination in legal summarisation",
]
TAGS = ["rag", "retrieval augmented generation", "llm"]


def test_clean_name_strips_what_a_chat_model_wraps_around_it():
    assert N.clean_name('  "Retrieval Augmented Generation."  ') == "Retrieval Augmented Generation"
    assert N.clean_name("Name: Solid State Batteries") == "Solid State Batteries"
    assert N.clean_name("**Vision Language Models**\nThese papers…") == "Vision Language Models"


def test_a_grounded_specific_name_passes():
    assert N.check_name("Retrieval Augmented Generation", TITLES, TAGS) is None
    assert N.check_name("Hybrid Retrieval and Reranking", TITLES, TAGS) is None


def test_an_invented_word_is_rejected():
    reason = N.check_name("Perovskite Tandem Modules", TITLES, TAGS)
    assert reason and "not in the documents" in reason


def test_invented_specifics_are_rejected_even_when_plausible():
    # "2026" and "Google" never appear in the titles — exactly the failure the
    # article pipeline's grounding gate exists for.
    assert N.check_name("Google RAG Rollout 2026", TITLES, TAGS)
    assert N.check_name("European Retrieval Augmented Generation", TITLES, TAGS)


def test_glue_words_do_not_need_to_be_in_the_source():
    assert N.check_name("Retrieval Augmented Generation for Clinical QA", TITLES, TAGS) is None


def test_plurals_count_as_the_same_word():
    titles = ["Solid state battery cathode interfaces"]
    assert N.check_name("Solid State Batteries", titles, []) is None


def test_generic_and_malformed_names_are_rejected():
    assert N.check_name("Machine Learning Research", TITLES, TAGS) == "generic name"
    assert N.check_name("Retrieval", TITLES, TAGS) == "1 words"
    assert N.check_name("NONE", TITLES, TAGS) == "model declined"
    assert N.check_name("", TITLES, TAGS) == "empty"
    assert N.check_name("a " * 40, TITLES, TAGS)


def test_name_nest_retries_then_falls_back_with_a_reason():
    calls = []

    def chat(**kw):
        calls.append(kw["seed"])
        return "Quantum Blockchain Synergy"        # nothing of it in the titles

    name, note = N.name_nest(TITLES, TAGS, chat=chat)
    assert name is None
    assert "not in the documents" in note
    assert len(calls) == 2 and calls[0] != calls[1]   # two seeds, then give up


def test_name_nest_takes_the_first_answer_that_holds_up():
    answers = iter(["Totally Invented Thing", "Hybrid Retrieval"])

    def chat(**kw):
        return next(answers)

    name, note = N.name_nest(TITLES, TAGS, chat=chat)
    assert name == "Hybrid Retrieval" and note is None


def test_a_dead_model_never_breaks_the_run():
    def chat(**kw):
        raise ConnectionError("no server")

    name, note = N.name_nest(TITLES, TAGS, chat=chat)
    assert name is None and "model error" in note


def test_name_nests_marks_every_nest_and_reports_the_tally():
    nests = [
        {"name_titles": TITLES, "top_tags": TAGS, "label": "Rag · Llm"},
        {"name_titles": ["Bread baking with sourdough starters"], "top_tags": [], "label": "X"},
    ]
    answers = iter(["Retrieval Augmented Generation", "Quantum Falconry"])
    summary = N.name_nests(nests, chat=lambda **kw: next(answers))
    assert summary == {"named": 1, "total": 2}
    assert nests[0]["llm_label"] == "Retrieval Augmented Generation"
    assert nests[1]["llm_label"] is None and nests[1]["llm_label_note"]


def test_the_prompt_carries_the_titles_and_never_the_measurements():
    prompt = N.build_prompt(TITLES, TAGS)
    assert "Retrieval-Augmented Generation with Dense" in prompt
    assert "rag" in prompt
    # the model names, it never sees what was measured
    for field in ("novelty_lift", "age_months", "established_share",
                  "n_sources", "first_month", "tagged_share"):
        assert field not in prompt


def test_house_casing_is_applied_to_an_accepted_name():
    assert N.titlecase("image processing") == "Image Processing"
    assert N.titlecase("retrieval augmented generation for ai") == "Retrieval Augmented Generation for AI"
    assert N.titlecase("RAG pipelines") == "RAG Pipelines"
    assert N.titlecase("kv cache compression") == "Kv Cache Compression"

    name, note = N.name_nest(TITLES, TAGS, chat=lambda **kw: "hybrid retrieval")
    assert name == "Hybrid Retrieval" and note is None


def test_shouting_patent_titles_do_not_shout_on_the_card():
    assert N.titlecase("COSMETIC COMPOSITION") == "Cosmetic Composition"


def test_two_pockets_never_get_the_same_name():
    nests = [
        {"name_titles": ["COSMETIC COMPOSITION for skin"], "top_tags": [], "label": "A"},
        {"name_titles": ["Another cosmetic composition patent"], "top_tags": [], "label": "B"},
    ]
    summary = N.name_nests(nests, chat=lambda **kw: "cosmetic composition")
    assert summary["named"] == 1
    assert nests[0]["llm_label"] == "Cosmetic Composition"
    assert nests[1]["llm_label"] is None
    assert nests[1]["llm_label_note"] == "duplicate of another pocket"
