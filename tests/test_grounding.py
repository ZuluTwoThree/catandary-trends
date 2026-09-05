"""Unit tests for the fabrication detector (pipeline.grounding, #11)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.grounding import ungrounded_specifics, source_from_parts


def test_flags_invented_year_and_number():
    src = "The Ministry published a circular economy strategy to cut waste."
    body = "The strategy sets a 2027 deadline affecting 10,000 suppliers."
    flagged = set(ungrounded_specifics(body, src))
    assert "2027" in flagged and "10,000" in flagged


def test_grounded_numbers_pass():
    src = "The programme created 7,980 jobs across 36 firms in 2024."
    body = "It created 7,980 jobs across 36 firms, per the 2024 review."
    assert ungrounded_specifics(body, src) == []


def test_german_number_format_not_flagged():
    # German thousands '.' / decimal ',' must equal English formatting
    src = "Bastler baut GPU mit 8.192 Chips; DE-CIX misst 29,5 TBit/s."
    body = "A GPU with 8,192 chips; the exchange measured 29.5 Tbit/s."
    assert ungrounded_specifics(body, src) == []


def test_empty_and_missing():
    assert ungrounded_specifics("", "anything") == []
    assert ungrounded_specifics("no numbers here", "") == []


# --- source_from_parts (#11): the shared source assembly for both the content
# re-roll guard and the auto-publish gate. ---

def test_source_from_parts_joins_title_excerpt_and_lists():
    s = source_from_parts("Title 2027", "excerpt text",
                          ["a claim"], ["7,980 jobs"], ["by Q3 2025"])
    for token in ("Title 2027", "excerpt text", "a claim", "7,980 jobs", "by Q3 2025"):
        assert token in s


def test_source_from_parts_tolerates_none_and_empty():
    # None title/excerpt and empty/None lists must not raise or inject "None"
    s = source_from_parts(None, None, None, [], ["2030"])
    assert "None" not in s
    assert "2030" in s


def test_figure_in_fulltext_not_flagged_via_extraction():
    # The false-hold #11 fixes: the RSS excerpt omits a figure that the full text
    # (and the extracted key_figures) contains. Rebuilding the gate source from
    # the extracted specifics grounds the body's figure instead of flagging it.
    rss_excerpt = "The ministry announced a new circular economy strategy."
    key_figures = ["10,000 suppliers"]
    dates = ["2027"]
    body = "The 2027 strategy will affect 10,000 suppliers."
    narrow = source_from_parts("Circular strategy", rss_excerpt)          # excerpt only
    assert set(ungrounded_specifics(body, narrow)) == {"2027", "10,000"}  # falsely flagged
    wide = source_from_parts("Circular strategy", rss_excerpt, [], key_figures, dates)
    assert ungrounded_specifics(body, wide) == []                          # now grounded

def test_cjk_source_numbers_are_seen():
    """Regression 2026-08-04: a figure stated in a Japanese/Korean source was
    flagged as fabricated because \b finds no boundary between a digit and a
    CJK character, so the number stayed invisible to the check."""
    src = "140以上の通貨、180以上の国・地域をカバーし"
    body = "covering 140 currencies across 180 countries."
    assert ungrounded_specifics(body, src) == []


def test_korean_grouped_number_not_mangled():
    """'2,900만' used to be read as the garbage token '2,'."""
    src = "약 2,900만 명의 고객을 보유"
    body = "The bank serves 2,900 万 customers."
    assert "2,900" not in ungrounded_specifics(body, src)


def test_percent_still_matches_across_formats():
    src = "Registrations rose 50% to a 26% share."
    body = "BEV registrations rose by 50%, reaching 26% of the market."
    assert ungrounded_specifics(body, src) == []


# --- Quantities the source spells out in words (2026-08-04) -----------------
# Measured cause of most holds in the live queue: German and English sources
# routinely write "die Hälfte" / "one in five" where the body writes 50% / 20%.

def test_half_in_source_grounds_fifty_percent():
    src = "Around half of melanomas carry a mutation in a protein called BRAF."
    assert ungrounded_specifics("mutations in approximately 50% of melanoma cases", src) == []


def test_german_half_grounds_fifty_percent():
    src = "Erstmals ist mehr als die Hälfte neu hochgeladener Songs auf Deezer KI"
    assert ungrounded_specifics("AI accounted for over 50% of all new uploads", src) == []


def test_quarter_and_fifth_and_ratio_forms():
    assert ungrounded_specifics("cut demand by 25%", "um ein Viertel senken") == []
    assert ungrounded_specifics("20 percent of power", "ein Fünftel des Landesstroms") == []
    assert ungrounded_specifics("25% of IT ops work", "a quarter of the IT ops work") == []
    assert ungrounded_specifics("20% of the cohort", "one in five face lasting struggles") == []


def test_scaled_fraction():
    assert ungrounded_specifics("a $500 billion bill", "New York Faces Half a Trillion in Costs") == []
    assert ungrounded_specifics("committing €500 million", "Nestlé investiert halbe Milliarde") == []


def test_spelled_cardinal_grounds_digit():
    src = "Leerverkäufer erzielen Buchgewinne von etwa fünf Milliarden US-Dollar."
    assert ungrounded_specifics("extracting $5 billion in paper profits", src) == []


# --- and the limits: the gate must still catch real inventions -------------

def test_word_quantities_do_not_ground_unrelated_figures():
    """'half' implies 50 — it must NOT wave through an invented 150 or 70."""
    src = "The 2026 El Niño is on track to be the strongest on record."
    assert ungrounded_specifics("the strongest recorded in 150 years", src) == ["150"]


def test_implied_digit_never_grounds_via_substring():
    """A source cardinal 'five' implies '5'; a body '500,000' is NOT thereby
    grounded — otherwise every figure containing the digit would pass."""
    src = "The company named five priorities for the year."
    assert ungrounded_specifics("a 500,000 unit shortfall", src) == ["500,000"]


def test_vague_words_carry_no_number():
    src = "Most patients benefited, and many reported fewer symptoms."
    assert ungrounded_specifics("benefited 80% of patients", src) == ["80%"]


def test_digits_inside_a_capitalised_name_are_not_claims():
    """COVID-19 / LTG-001 / PAC-3 are names, not measurements."""
    assert ungrounded_specifics(
        "the largest exodus since the COVID-19 pandemic.",
        "Privatanleger verkaufen netto Aktien im Wert von 243 Millionen US-Dollar.") == []
    assert ungrounded_specifics(
        "its acute pain drug, LTG-001.", "Latigo reports mid-stage success") == []


def test_lowercase_hyphen_figure_is_still_a_claim():
    """'under-25' carries a real (here fabricated) measurement — the capital
    letter is exactly what separates a name from a number."""
    src = "More young adults are living with their parents."
    assert ungrounded_specifics("demand from the under-25 demographic", src) == ["25"]


# --- Abbreviations and date formats (2026-08-05) ----------------------------

def test_digits_welded_to_a_name_are_not_claims():
    """CO2 / B2B / Inspire360 — the digit is part of the name, not a figure."""
    assert ungrounded_specifics("cutting CO2 emissions across the fleet",
                                "Der Konzern senkt seinen Ausstoss deutlich") == []
    assert ungrounded_specifics("a B2B hardware and subscription hybrid",
                                "Peloton's Latest Push Into Commercial Fitness") == []
    assert ungrounded_specifics("A new report from Inspire360 indicates",
                                "More Gyms Are Integrating GLP-1s Into Their Offerings") == []
    assert ungrounded_specifics("PM2.5 concentrations near the port",
                                "Feinstaubbelastung am Hafen gemessen") == []


def test_same_date_written_two_ways():
    """'04 August 2026' and 'August 4, 2026' are one date, not a fabrication."""
    src = "Nature Human Behaviour, Published online: 04 August 2026"
    assert ungrounded_specifics("published in Nature Human Behaviour on August 4, 2026", src) == []


def test_leading_zero_does_not_ground_a_bigger_number():
    """Stripping the zero must not let '04' wave through an invented '400'."""
    assert ungrounded_specifics("some 400 delegates attended",
                                "Beginn am 04. August") == ["400"]


def test_unattached_capitalised_number_is_still_checked():
    """'Under 25' is a measurement; only WELDED digits count as a name."""
    src = "More young adults are living with their parents."
    assert ungrounded_specifics("Under 25 year olds are staying home", src) == ["25"]


def test_medical_middle_dot_decimal_separator():
    """The Lancet writes '13·4%' (U+00B7) where the body writes '13.4%'."""
    src = "the composite outcome was 7·8% versus 13·4% (risk ratio 0·58)"
    assert ungrounded_specifics(
        "lowered the outcome to 7.8%, compared to 13.4% (risk ratio 0.58).", src) == []


# --- Designators, decades, scaled words (2026-08-06) ------------------------

def test_designator_numbers_name_a_thing():
    """'Scope 1' / 'Article 6' / 'MAX 8' name something; they do not measure."""
    assert ungrounded_specifics("a reduction in Scope 1 emissions",
                                "outlining what needs to be done on heat pumps") == []
    assert ungrounded_specifics("projects entering the Article 6 market",
                                "Renewable Energy Methodology Cleared In UN Carbon Market") == []
    assert ungrounded_specifics("a different profile than the larger MAX 8",
                                "U.S. Clears Smallest Boeing 737 Max to Fly") == []


def test_abbreviated_decade():
    """Source \"the '80s\", body \"the 1980s\" — one decade."""
    assert ungrounded_specifics("a technology popularized in the 1980s",
                                "Carmakers Go Back to the '80s With Turbo Engines") == []


def test_scaled_word_number():
    """Source \"2.5 thousand products\", body \"2,500 products\"."""
    assert ungrounded_specifics("audited 2,500 products labeled for infants",
                                "an audit of more than 2.5 thousand products") == []


def test_designator_list_does_not_excuse_measurements():
    """The list names things; a plain quantity must still be checked."""
    src = "More young adults are living with their parents."
    assert ungrounded_specifics("Under 25 year olds stay home", src) == ["25"]
    # 'Level' is a designator, but a bare figure elsewhere still counts
    assert ungrounded_specifics("Level 3 autonomy cut costs by 42%",
                                "carmakers discuss autonomous driving") == ["42%"]


# --- ungrounded_names (#11, owner review 2026-09-05) -------------------------
# "Henkel-Chef Knobel" became "Henkel CEO Markus Knobel" (real: Carsten). A
# person = given name (pipeline.first_names) or title + capitalised word; every
# word of the name must stand in the source.
from pipeline.grounding import ungrounded_names


def test_added_first_name_is_flagged():
    src = "Henkel-Chef Knobel: Margen verbessert, Ausblick bestätigt."
    body = "Henkel CEO Markus Knobel said margins improved."
    assert ungrounded_names(body, src) == ["Markus Knobel"]


def test_name_as_in_source_passes():
    src = "Henkel-Chef Carsten Knobel: Margen verbessert."
    assert ungrounded_names("Henkel CEO Carsten Knobel said margins improved.", src) == []
    assert ungrounded_names("Henkel CEO Knobel said margins improved.", src) == []


def test_generic_capitalised_bigrams_never_trigger():
    """The proxy's false alarms from the issue: 'Storage System', 'Middle
    Eastern' are not people."""
    body = ("The Storage System uses Middle Eastern suppliers; Global Voices and "
            "the Digital Markets Act shape the New Energy Outlook.")
    assert ungrounded_names(body, "unrelated source") == []


def test_title_introduces_a_person_without_known_given_name():
    src = "The company reported growth."
    assert ungrounded_names("CEO Xiaoming Wang announced the plan.", src) == ["Xiaoming Wang"]
    assert ungrounded_names("Minister Habeck welcomed it.", src) == ["Habeck"]
    assert ungrounded_names("Minister Habeck welcomed it.", "Habeck begrüßt den Plan.") == []


def test_title_does_not_capture_role_words_or_sentence_starts():
    src = "The chief executive resigned; a doctor was consulted."
    assert ungrounded_names("The Chief Executive Officer resigned.", src) == []
    assert ungrounded_names("They consulted a doctor. The clinic reopened.", src) == []
    assert ungrounded_names("Aid reached the DR Congo region.", src) == []      # 'DR' ≠ 'Dr'
    assert ungrounded_names("Dr. Oetker expanded.", "Dr. Oetker baut aus.") == []
    assert ungrounded_names("Dr. Oetker expanded.", "Ein Hersteller baut aus.") == ["Oetker"]


def test_particles_and_possessives():
    body = "Commission President Ursula von der Leyen’s plan and Donald Trump’s tariffs."
    assert ungrounded_names(body, "Ursula von der Leyen legt Plan vor; Trumps Zölle") == ["Donald Trump"]
    assert ungrounded_names(body, "von der Leyen; Donald Trump") == ["Ursula von der Leyen"]


def test_sentence_boundary_never_glues_two_words():
    src = "Mirko leitet das Projekt."
    assert ungrounded_names("The project is led by Mirko. This matters.", src) == []


def test_diacritics_and_german_transliteration_match():
    assert ungrounded_names("Analyst Thomas Mueller expects growth.", "Thomas Müller erwartet Wachstum.") == []
    assert ungrounded_names("Analyst Thomas Muller expects growth.", "Thomas Müller erwartet Wachstum.") == []
    assert ungrounded_names("Sebastian Krüger spoke.", "Sebastian Krueger sprach.") == []


def test_organisations_with_person_names_are_not_people():
    src = "HHU Düsseldorf, the foundation and Kim (POSTECH) published a study."
    body = ("Researchers at Heinrich-Heine-University Düsseldorf and the Hans-Böckler "
            "Foundation's team, with Professor Kim of POSTECH’s lab, published it.")
    assert ungrounded_names(body, src) == []


def test_institutions_brands_and_instruments_named_after_people():
    src = "The university and the telescope reported results; the drugmaker grew."
    body = ("Justus Liebig University Giessen and the James Webb Space Telescope reported "
            "results, while Eli Lilly grew; Levi Strauss & Co. and the Max Planck "
            "Institute for Chemistry followed, as did Abu Dhabi.")
    assert ungrounded_names(body, src) == []
    # the same given name IS a person when nothing institutional follows
    assert ungrounded_names("Karin Voordeckers said so.", src) == ["Karin Voordeckers"]


def test_lone_given_name_is_not_a_claim():
    assert ungrounded_names("Alexa and Emma are popular assistants.", "Assistants are popular.") == []


def test_empty():
    assert ungrounded_names("", "x") == []
    assert ungrounded_names("Markus Knobel", "") == ["Markus Knobel"]
