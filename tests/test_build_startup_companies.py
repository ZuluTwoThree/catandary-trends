from datetime import date

from scripts.build_startup_companies import (
    Group, _CORDIS_TITLE, _FORMD_GEO, _FORMD_TITLE, _PREFIX_GEO, _SBIR_TITLE,
    _corroborates_regd, _event, _geo_compatible, _us_state, merge, parse_money,
)


class TestParsers:
    def test_money(self):
        assert parse_money("raises $3.1M private round") == (3_100_000, "USD")
        assert parse_money("wins $150k SBIR") == (150_000, "USD")
        assert parse_money("secures EUR 1.2M grant") == (1_200_000, "EUR")
        assert parse_money("secures undisclosed grant") is None

    def test_formd_title(self):
        m = _FORMD_TITLE.match("Cart.com, Inc. raises $17.7M private round (Other Technology)")
        assert m.group(1) == "Cart.com, Inc." and m.group(2) == "Other Technology"

    def test_formd_geo(self):
        m = _FORMD_GEO.search("[Funding · SEC Form D] X (SEATTLE, WASHINGTON) filed a Reg-D…")
        assert m.group(1) == "SEATTLE"
        assert _us_state(m.group(2)) == "WA"

    def test_sbir_title_with_and_without_amount(self):
        m = _SBIR_TITLE.match("ISOFLUX, INC wins $100k STTR Phase I award (National Science Foundation)")
        assert (m.group(1), m.group(2), m.group(3)) == ("ISOFLUX, INC", "STTR", "I")
        m2 = _SBIR_TITLE.match("ACTA, LLC wins undisclosed STTR Phase I award (Department of Defense)")
        assert m2.group(1) == "ACTA, LLC"

    def test_prefix_geo(self):
        m = _PREFIX_GEO.search("[Funding · STTR Phase I · NSF · Rush, NY · $100k] …")
        assert (m.group(1).strip(), m.group(2)) == ("Rush", "NY")

    def test_cordis_title(self):
        m = _CORDIS_TITLE.match("LAMBDA-X SA secures EUR 149k Horizon Europe grant (uCAIR)")
        assert m.group(1) == "LAMBDA-X SA" and m.group(3) == "Horizon Europe"
        m2 = _CORDIS_TITLE.match("LAMBDA-X SA secures undisclosed Horizon 2020 grant (X)")
        assert m2 is not None


def _grp(name, country=None, region=None, sources=("formd",)):
    g = Group()
    g.names.append(name)
    g.country, g.region = country, region
    g.sources = set(sources)
    g.events.append(_event("regd_offering", date(2024, 1, 1), "t", f"u://{name}/{country}/{region}"))
    return g


class TestMerge:
    def test_geo_gate_blocks_conflicting_state(self):
        a = _grp("Acme Robotics Inc", "US", "CA")
        b = _grp("Acme Robotics Inc", "US", "TX", sources=("sbir",))
        assert not _geo_compatible(a, b)
        assert len(merge([a, b])) == 2

    def test_same_state_merges(self):
        a = _grp("Acme Robotics Inc", "US", "CA")
        b = _grp("Acme Robotics Inc", "US", "CA", sources=("sbir",))
        merged = merge([a, b])
        assert len(merged) == 1 and merged[0].sources == {"formd", "sbir"}

    def test_press_merges_only_when_unique(self):
        a = _grp("Quantum Widgets Inc", "US", "CA")
        p = _grp("Quantum Widgets", sources=("press",))
        assert len(merge([a, p])) == 1
        # zwei Geo-Kandidaten -> Presse bleibt separat
        a2 = _grp("Quantum Widgets Inc", "US", "CA")
        b2 = _grp("Quantum Widgets Ltd", "US", "TX", sources=("sbir",))
        p2 = _grp("Quantum Widgets", sources=("press",))
        assert len(merge([a2, b2, p2])) == 3

    def test_press_short_key_stays_alone(self):
        a = _grp("Flex Inc", "US", "CA")
        p = _grp("Flex", sources=("press",))  # name_norm "flex" < 5 Zeichen
        assert len(merge([a, p])) == 2


class TestCorroboration:
    def test_press_confirming_regd_not_double_counted(self):
        regd = _event("regd_offering", date(2021, 7, 20), "s", "u1", amount=45e6, currency="USD")
        press = _event("press_round", date(2021, 8, 19), "s", "u2", amount=45e6, currency="USD")
        assert _corroborates_regd(press, [regd, press])
        assert not _corroborates_regd(regd, [regd, press])

    def test_different_amount_or_window_counts(self):
        regd = _event("regd_offering", date(2021, 7, 20), "s", "u1", amount=9.1e6, currency="USD")
        press = _event("press_round", date(2021, 8, 1), "s", "u2", amount=22e6, currency="USD")
        assert not _corroborates_regd(press, [regd, press])
        far = _event("press_round", date(2022, 7, 20), "s", "u3", amount=9.1e6, currency="USD")
        assert not _corroborates_regd(far, [regd, far])
