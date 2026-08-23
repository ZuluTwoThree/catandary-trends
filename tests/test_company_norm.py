from pipeline.company_norm import (
    cik_from_edgar_url, norm_company_name, pic_from_cordis_url,
)


class TestNormCompanyName:
    def test_strips_us_suffixes(self):
        assert norm_company_name("PlayEveryWare, Inc.") == "playeveryware"
        assert norm_company_name("Cart.com, Inc.") == "cart com"
        assert norm_company_name("ACME Corp") == "acme"

    def test_suffix_only_at_end(self):
        # "Spa"/"Co" als Namensbestandteil bleibt erhalten
        assert norm_company_name("Spa Beauty Ltd.") == "spa beauty"
        assert norm_company_name("Co-Diagnostics, Inc.") == "co diagnostics"

    def test_chained_suffixes(self):
        assert norm_company_name("Müller & Söhne GmbH & Co. KG") == "muller and sohne"
        assert norm_company_name("Beispiel Verwaltungs GmbH & Co KG") == "beispiel verwaltungs"

    def test_ampersand_and_diacritics(self):
        assert norm_company_name("Häagen & Sons") == "haagen and sons"
        assert norm_company_name("Café Ltd") == "cafe"

    def test_whitespace_and_case(self):
        assert norm_company_name("  QUANTUM   Sensing  LLC ") == "quantum sensing"

    def test_empty_and_none(self):
        assert norm_company_name(None) == ""
        assert norm_company_name("") == ""
        assert norm_company_name("GmbH") == ""

    def test_cjk_passthrough(self):
        assert norm_company_name("株式会社サンプル") == "株式会社サンプル"

    def test_uk_style(self):
        assert norm_company_name("DEEPMIND TECHNOLOGIES LIMITED") == "deepmind technologies"


class TestUrlIds:
    def test_cik(self):
        url = "https://www.sec.gov/Archives/edgar/data/0002016462/000201646224000001/x-index.htm"
        assert cik_from_edgar_url(url) == "2016462"
        assert cik_from_edgar_url("https://example.com/") is None
        assert cik_from_edgar_url(None) is None

    def test_pic(self):
        url = "https://cordis.europa.eu/project/id/101096364#org-999852104"
        assert pic_from_cordis_url(url) == ("101096364", "999852104")
        assert pic_from_cordis_url("https://cordis.europa.eu/project/id/1") is None
