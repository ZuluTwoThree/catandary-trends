"""pipeline/text_clean.py — boilerplate out, content in."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.text_clean import clean_text, embed_text


def test_leading_labels_go_even_stacked():
    assert clean_text("Abstract Background: Obesity rises.") == "Obesity rises."
    assert clean_text("ABSTRACT. The study shows x.") == "The study shows x."
    assert clean_text("Background Obesity is common.") == "Obesity is common."
    assert clean_text("Introduction — Food waste grows.") == "Food waste grows."


def test_a_label_word_starting_a_real_sentence_stays():
    assert clean_text("Aim of this study was to test x.") == "Aim of this study was to test x."
    assert clean_text("Summary statistics were computed.").startswith("Summary statistics")


def test_inline_section_labels_go_but_content_words_stay():
    t = clean_text("Background: A. Methods: B. RESULTS: C. Conclusions: D. Keywords: probiotics, kefir")
    assert t == "A. B. C. D. probiotics, kefir"
    assert clean_text("The results were clear.") == "The results were clear."


def test_markup_and_entities_go_but_comparisons_survive():
    assert clean_text("Effect of <i>Lactobacillus</i> on H<sub>2</sub>O") == "Effect of Lactobacillus on H 2 O"
    assert clean_text("&lt;jats:p&gt;Milk proteins&lt;/jats:p&gt;") == "Milk proteins"
    assert clean_text("&amp;lt;jats:title&amp;gt;Abstract&amp;lt;/jats:title&amp;gt;Whey.") == "Whey."
    assert clean_text("significant (p &lt; 0.05) and x&lt;0.1 &amp; y &gt; 2") == "significant (p < 0.05) and x<0.1 & y > 2"


def test_copyright_tails_go():
    assert clean_text("Whey is useful. © 2024 Elsevier Ltd. All rights reserved.") == "Whey is useful."
    assert clean_text("Whey is useful. This article is protected by copyright. All rights reserved.") == "Whey is useful."


def test_embed_text_cuts_after_cleaning():
    body = "Abstract: " + "x" * 600
    assert embed_text("<i>T</i>", body) == "T\n" + "x" * 500
    assert embed_text("T", body, max_body=None) == "T\n" + "x" * 600
    assert embed_text(None, None) == "\n"
