"""pipeline/signal_rules.py — patents and funding judged by rule, not by the press-trained head.

The cases are the true misses and true hits of the blind audit (docs/filter_audit_2026-10-02.md)."""
from pipeline import signal_rules as R


def P(title):
    return {"pub_number": "US123", "title": title, "excerpt": "x", "source_name": "Google Patents US"}


def F(title, excerpt, source="SEC Form D"):
    return {"title": title, "excerpt": excerpt, "source_name": source, "source_type": "api"}


def test_patents_keep_everything_but_plant_varieties():
    for t in ["SOYBEAN CULTIVAR 01220205", "Phalaenopsis plant named 'PHA964388'",
              "HYBRID TOMATO VARIETY 72-CH0362 RZ", "Plants and Seeds of Corn Variety CV934113"]:
        assert R.verdict(P(t)) == "plant_variety", t
    for t in ["Preparation method of cold-extracted freeze-dried coffee powder",
              "Sampling a variety of signals in a wireless receiver", "POLYMERIC MITRAL HEART VALVE"]:
        assert R.verdict(P(t)) == "", t


def test_form_d_keeps_company_finance_and_drops_vehicles():
    tech = "[Funding · SEC Form D] Adronite, Inc. (SEATTLE) filed a Reg-D private offering. Industry: Other Technology. Total offering $3.4M, sold $3.4M."
    assert R.verdict(F("Adronite, Inc. raises $3.4M private round (Other Technology)", tech)) == ""
    re_ = "[Funding · SEC Form D] filed a Reg-D private offering. Industry: Commercial. Total offering $8.8M, sold $0."
    assert R.verdict(F("CS1031 Canopy Apartments, DST raises $8.8M private round (Commercial)", re_)) == "form_d_industry"
    fund = "[Funding · SEC Form D] filed. Industry: Other Technology. Total offering $600,000, sold $0."
    assert R.verdict(F("2021 East Coast Fund LLC raises $600,000 private round", fund)) == "form_d_vehicle"
    tiny = "[Funding · SEC Form D] filed. Industry: Other Health Care. Total offering $6, sold $6."
    assert R.verdict(F("REALIST PHARMA INC. raises $6 private round (Other Health Care)", tiny)) == "form_d_amount"


def test_grants_need_a_description_and_are_not_bookings():
    sbir = ("[Funding · SBIR Phase I · Department of Defense · Columbia, SC · $50k] ADVANCE GUN BARREL "
            "TECHNOLOGY THROUGH PLASMA SURFACE ALLOYING. Plaur Corp (5 employees): THE HOSTILE ENVIRONMENT "
            "EXISTING AT THE BORE SURFACE OF GUN BARRELS")
    assert R.verdict(F("Plaur Corp wins $50k SBIR Phase I award", sbir, "SBIR/STTR Awards")) == ""
    empty = "[Funding · STTR Phase I · Department of Health and Human Services · Salt Lake City, UT · undisclosed] N/A. ECHELON BIOSCIENCES, INC. (0 employees): N/A"
    assert R.verdict(F("ECHELON BIOSCIENCES wins STTR", empty, "SBIR/STTR Awards")) == "no_description"
    sub = "[Funding · NIH/NCRR · US-CA · $33] This subproject is one of many research subprojects utilizing the resources"
    assert R.verdict(F("HIV PROTEINS AND PROTEIN INTERACTIONS", sub, "NIH RePORTER")) == "nih_subproject"
    assert R.verdict(F("Teen Court", "[Funding · NIH/SAMHSA · US-IL]", "NIH RePORTER")) == "no_description"


def test_press_and_research_stay_with_the_head():
    assert R.verdict({"title": "x", "excerpt": "y", "source_name": "TechCrunch", "source_type": "trade_media"}) is None
    assert R.verdict({"title": "x", "excerpt": "y", "source_name": "arXiv Preprints", "source_type": "research"}) is None


def test_a_grant_title_is_its_description_an_award_notice_is_not():
    hdr = "[Funding · National Science Foundation · US · €175k] "
    assert R.verdict(F("CRII: RI: A Study of Rank-based Decomposable Losses for Machine Learning", hdr,
                       "NSF Awards (US Federal Research Funding)")) == ""
    assert R.verdict(F("Strategic and digital improvements of a drain water microalgae product",
                       "[Funding · Fundação para a Ciência e a Tecnologia, I.P. · PT] ",
                       "OpenAIRE Projects (EU + National Funders)")) == ""
    sbir = "[Funding · SBIR Phase I · Department of Commerce · EDMOND, OK · $50k] N/A. MECHMATH LLC (2 employees): N/A"
    assert R.verdict(F("MECHMATH LLC wins $50k SBIR Phase I award (Department of Commerce)", sbir,
                       "SBIR/STTR Awards")) == "no_description"
