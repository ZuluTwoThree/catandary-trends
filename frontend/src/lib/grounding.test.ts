/**
 * Parity tests for the TypeScript grounding port (issue #71).
 *
 * These use the SAME fixtures as tests/test_grounding.py — if the two
 * implementations ever drift, one of these fails.
 */
import { describe, it, expect } from "vitest";
import { ungroundedSpecifics, sourceFromParts, ungroundedNames } from "@/lib/grounding";

describe("ungroundedSpecifics — parity with pipeline/grounding.py", () => {
  it("flags an invented year and number", () => {
    const src = "The Ministry published a circular economy strategy to cut waste.";
    const body = "The strategy sets a 2027 deadline affecting 10,000 suppliers.";
    const flagged = new Set(ungroundedSpecifics(body, src));
    expect(flagged.has("2027")).toBe(true);
    expect(flagged.has("10,000")).toBe(true);
  });

  it("passes grounded numbers", () => {
    const src = "The programme created 7,980 jobs across 36 firms in 2024.";
    const body = "It created 7,980 jobs across 36 firms, per the 2024 review.";
    expect(ungroundedSpecifics(body, src)).toEqual([]);
  });

  it("treats German and English number formats as equal", () => {
    // '8.192' == '8,192' and '29,5' == '29.5' — ~half our sources are German,
    // so a format-blind check would flag correct figures.
    const src = "Bastler baut GPU mit 8.192 Chips; DE-CIX misst 29,5 TBit/s.";
    const body = "A GPU with 8,192 chips; the exchange measured 29.5 Tbit/s.";
    expect(ungroundedSpecifics(body, src)).toEqual([]);
  });

  it("handles empty input", () => {
    expect(ungroundedSpecifics("", "anything")).toEqual([]);
    expect(ungroundedSpecifics("no numbers here", "")).toEqual([]);
  });

  it("reproduces the real Intel hold from 2026-08-03", () => {
    // Held live: body claims '€5' billion, the RSS teaser never states it.
    const src = "Intel expands its Irish semiconductor operations.";
    const body = "Intel allocates €5 billion to expand Irish semiconductor capacity.";
    expect(ungroundedSpecifics(body, src).length).toBeGreaterThan(0);
  });
});

describe("sourceFromParts", () => {
  it("joins title, excerpt and token lists", () => {
    const s = sourceFromParts("Title 2027", "excerpt text", ["a claim"], ["7,980 jobs"], ["by Q3 2025"]);
    for (const token of ["Title 2027", "excerpt text", "a claim", "7,980 jobs", "by Q3 2025"]) {
      expect(s).toContain(token);
    }
  });

  it("tolerates nulls without injecting 'null'", () => {
    const s = sourceFromParts(null, null, null, [], ["2030"]);
    expect(s).not.toContain("null");
    expect(s).toContain("2030");
  });

  it("grounds a figure that only the full text contains", () => {
    // The false-hold class #11 fixed: RSS teaser omits the figure, the
    // extracted specifics carry it.
    const rss = "The ministry announced a new circular economy strategy.";
    const body = "The 2027 strategy will affect 10,000 suppliers.";
    const narrow = sourceFromParts("Circular strategy", rss);
    expect(ungroundedSpecifics(body, narrow).sort()).toEqual(["10,000", "2027"]);
    const wide = sourceFromParts("Circular strategy", rss, [], ["10,000 suppliers"], ["2027"]);
    expect(ungroundedSpecifics(body, wide)).toEqual([]);
  });
});

describe("CJK sources (regression 2026-08-04)", () => {
  it("sees a figure stated in a Japanese source", () => {
    // \b finds no boundary between a digit and a CJK character, so the number
    // was invisible and the body's correct figure was flagged as fabricated.
    expect(
      ungroundedSpecifics("covering 140 currencies across 180 countries.", "140以上の通貨、180以上の国・地域をカバーし")
    ).toEqual([]);
  });

  it("does not mangle a Korean grouped number into '2,'", () => {
    expect(ungroundedSpecifics("The bank serves 2,900 万 customers.", "약 2,900만 명의 고객을 보유")).not.toContain("2,");
  });
});

describe("quantities the source spells out in words (2026-08-04)", () => {
  it("grounds a numeral against the word form, EN and DE", () => {
    expect(ungroundedSpecifics("50% of melanoma cases", "Around half of melanomas carry a mutation")).toEqual([]);
    expect(ungroundedSpecifics("over 50% of all new uploads", "mehr als die Hälfte neu hochgeladener Songs")).toEqual([]);
    expect(ungroundedSpecifics("cut demand by 25%", "um ein Viertel senken")).toEqual([]);
    expect(ungroundedSpecifics("20% of the cohort", "one in five face lasting struggles")).toEqual([]);
  });

  it("scales a fraction against a magnitude word", () => {
    expect(ungroundedSpecifics("a $500 billion bill", "New York Faces Half a Trillion in Costs")).toEqual([]);
    expect(ungroundedSpecifics("committing €500 million", "Nestlé investiert halbe Milliarde")).toEqual([]);
  });

  it("still catches inventions — a word quantity is not a blanket pass", () => {
    // "half" implies 50; it must not wave through an invented 150.
    expect(ungroundedSpecifics("strongest in 150 years", "on track to be the strongest on record")).toEqual(["150"]);
    // an implied digit must never ground a larger figure by substring
    expect(ungroundedSpecifics("a 500,000 unit shortfall", "named five priorities")).toEqual(["500,000"]);
    expect(ungroundedSpecifics("benefited 80% of patients", "Most patients benefited, many reported fewer symptoms")).toEqual(["80%"]);
  });
});

describe("digits inside a capitalised name", () => {
  it("are not treated as measurements", () => {
    expect(ungroundedSpecifics("the largest exodus since the COVID-19 pandemic.", "Aktien im Wert von 243 Millionen")).toEqual([]);
    expect(ungroundedSpecifics("its acute pain drug, LTG-001.", "Latigo reports mid-stage success")).toEqual([]);
  });
  it("but a lowercase hyphen figure still is one", () => {
    expect(ungroundedSpecifics("demand from the under-25 demographic", "young adults living with their parents")).toEqual(["25"]);
  });
});

describe("abbreviations and date formats (2026-08-05)", () => {
  it("treats digits welded to a name as part of the name", () => {
    expect(ungroundedSpecifics("cutting CO2 emissions", "Der Konzern senkt seinen Ausstoss")).toEqual([]);
    expect(ungroundedSpecifics("a B2B hardware hybrid", "Peloton's Push Into Commercial Fitness")).toEqual([]);
    expect(ungroundedSpecifics("a report from Inspire360", "More Gyms Are Integrating GLP-1s")).toEqual([]);
  });

  it("recognises the same date written two ways", () => {
    expect(ungroundedSpecifics("on August 4, 2026", "Published online: 04 August 2026")).toEqual([]);
  });

  it("reads the medical middle-dot decimal separator", () => {
    expect(ungroundedSpecifics("to 7.8%, compared to 13.4% (risk ratio 0.58).",
      "the outcome was 7·8% versus 13·4% (risk ratio 0·58)")).toEqual([]);
  });

  it("still catches inventions around those forms", () => {
    // stripping the leading zero must not let "04" wave through "400"
    expect(ungroundedSpecifics("some 400 delegates attended", "Beginn am 04. August")).toEqual(["400"]);
    // only WELDED digits are a name — "Under 25" is a measurement
    expect(ungroundedSpecifics("Under 25 year olds stay home", "young adults living with parents")).toEqual(["25"]);
  });
});

describe("designators, decades, scaled words (2026-08-06)", () => {
  it("treats designator numbers as names", () => {
    expect(ungroundedSpecifics("a reduction in Scope 1 emissions", "what needs to be done on heat pumps")).toEqual([]);
    expect(ungroundedSpecifics("entering the Article 6 market", "Methodology Cleared In UN Carbon Market")).toEqual([]);
    expect(ungroundedSpecifics("larger than the MAX 8", "U.S. Clears Smallest Boeing 737 Max to Fly")).toEqual([]);
  });
  it("matches an abbreviated decade and a scaled word", () => {
    expect(ungroundedSpecifics("popularized in the 1980s", "Carmakers Go Back to the '80s")).toEqual([]);
    expect(ungroundedSpecifics("audited 2,500 products", "an audit of more than 2.5 thousand products")).toEqual([]);
  });
  it("still checks plain quantities", () => {
    expect(ungroundedSpecifics("Under 25 year olds stay home", "young adults living with parents")).toEqual(["25"]);
    expect(ungroundedSpecifics("Level 3 autonomy cut costs by 42%", "carmakers discuss autonomous driving")).toEqual(["42%"]);
  });
});

describe("ungroundedNames — parity with pipeline/grounding.py (#11, 2026-09-05)", () => {
  it("flags an added first name", () => {
    expect(
      ungroundedNames("Henkel CEO Markus Knobel said margins improved.",
                      "Henkel-Chef Knobel: Margen verbessert, Ausblick bestätigt.")
    ).toEqual(["Markus Knobel"]);
  });

  it("passes names as the source gives them", () => {
    const src = "Henkel-Chef Carsten Knobel: Margen verbessert.";
    expect(ungroundedNames("Henkel CEO Carsten Knobel said margins improved.", src)).toEqual([]);
    expect(ungroundedNames("Henkel CEO Knobel said margins improved.", src)).toEqual([]);
  });

  it("never triggers on generic capitalised bigrams", () => {
    const body =
      "The Storage System uses Middle Eastern suppliers; Global Voices and " +
      "the Digital Markets Act shape the New Energy Outlook.";
    expect(ungroundedNames(body, "unrelated source")).toEqual([]);
  });

  it("lets a title introduce a person with an unknown given name", () => {
    const src = "The company reported growth.";
    expect(ungroundedNames("CEO Xiaoming Wang announced the plan.", src)).toEqual(["Xiaoming Wang"]);
    expect(ungroundedNames("Minister Habeck welcomed it.", src)).toEqual(["Habeck"]);
    expect(ungroundedNames("Minister Habeck welcomed it.", "Habeck begrüßt den Plan.")).toEqual([]);
  });

  it("does not let titles capture role words, sentence starts or 'DR Congo'", () => {
    const src = "The chief executive resigned; a doctor was consulted.";
    expect(ungroundedNames("The Chief Executive Officer resigned.", src)).toEqual([]);
    expect(ungroundedNames("They consulted a doctor. The clinic reopened.", src)).toEqual([]);
    expect(ungroundedNames("Aid reached the DR Congo region.", src)).toEqual([]);
    expect(ungroundedNames("Dr. Oetker expanded.", "Dr. Oetker baut aus.")).toEqual([]);
    expect(ungroundedNames("Dr. Oetker expanded.", "Ein Hersteller baut aus.")).toEqual(["Oetker"]);
  });

  it("handles particles and possessives", () => {
    const body = "Commission President Ursula von der Leyen’s plan and Donald Trump’s tariffs.";
    expect(ungroundedNames(body, "Ursula von der Leyen legt Plan vor; Trumps Zölle")).toEqual(["Donald Trump"]);
    expect(ungroundedNames(body, "von der Leyen; Donald Trump")).toEqual(["Ursula von der Leyen"]);
  });

  it("never glues two words across a sentence boundary", () => {
    expect(ungroundedNames("The project is led by Mirko. This matters.", "Mirko leitet das Projekt.")).toEqual([]);
  });

  it("matches diacritics and German transliteration", () => {
    expect(ungroundedNames("Analyst Thomas Mueller expects growth.", "Thomas Müller erwartet Wachstum.")).toEqual([]);
    expect(ungroundedNames("Analyst Thomas Muller expects growth.", "Thomas Müller erwartet Wachstum.")).toEqual([]);
    expect(ungroundedNames("Sebastian Krüger spoke.", "Sebastian Krueger sprach.")).toEqual([]);
  });

  it("does not treat organisations carrying person names as people", () => {
    const src = "HHU Düsseldorf, the foundation and Kim (POSTECH) published a study.";
    const body =
      "Researchers at Heinrich-Heine-University Düsseldorf and the Hans-Böckler " +
      "Foundation's team, with Professor Kim of POSTECH’s lab, published it.";
    expect(ungroundedNames(body, src)).toEqual([]);
  });

  it("ignores lone given names and empty input", () => {
    expect(ungroundedNames("Alexa and Emma are popular assistants.", "Assistants are popular.")).toEqual([]);
    expect(ungroundedNames("", "x")).toEqual([]);
    expect(ungroundedNames("Markus Knobel", "")).toEqual(["Markus Knobel"]);
  });
});
