"""Field Watch / Trajectory Sheet (Pivot 2026-09-20): reine Rechen- und
Renderregeln ohne Postgres — die SQL-Messung selbst läuft nur gegen die
Live-DB (scripts/field_watch.py example --week ...)."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
import yaml

from pipeline import field_watch as fw
from pipeline import field_watch_render as fr
from pipeline.tiers import tier_of

ROOT = Path(__file__).resolve().parent.parent


class TestCalendar:
    def test_week_bounds_are_iso_monday_to_sunday(self):
        assert fw.week_bounds(date(2026, 9, 20)) == (date(2026, 9, 14), date(2026, 9, 20))   # Sonntag
        assert fw.week_bounds(date(2026, 9, 16)) == (date(2026, 9, 14), date(2026, 9, 20))   # Mittwoch
        assert fw.iso_week(date(2026, 9, 14)) == "2026-W38"

    def test_quarter_labels(self):
        assert fw.quarter(date(2026, 9, 20)) == "2026-Q3"
        assert fw.quarter_start(date(2026, 9, 20)) == date(2023, 7, 1)


class TestRules:
    def test_ramp_takeoff_needs_15_percent_of_peak_and_at_least_three(self):
        years = {2005: 1, 2008: 2, 2010: 3, 2015: 20, 2020: 100}
        assert fw.ramp_takeoff(years) == 2015          # 3 < 15 (0.15*100)
        assert fw.ramp_takeoff({2019: 2, 2020: 4}) == 2020
        assert fw.ramp_takeoff({}) is None

    def test_delta_pct_against_zero_median_is_none(self):
        assert fw.delta_pct(9, 3.5) == 157
        assert fw.delta_pct(0, 0) is None

    def test_panel_keeps_only_sources_active_early_and_late(self):
        per_src = {1: {"2023-Q4": 5, "2026-Q3": 2}, 2: {"2026-Q2": 9, "2026-Q3": 4}, 3: {"2023-Q3": 1}}
        early, late = ["2023-Q3", "2023-Q4", "2024-Q1", "2024-Q2"], ["2025-Q4", "2026-Q1", "2026-Q2", "2026-Q3"]
        assert fw.panel_sources(per_src, early, late) == {1}

    def test_actor_cleaning_drops_bylines_and_quotes(self):
        assert fw.clean_actor("Ferm Labs") == "Ferm Labs"
        assert fw.clean_actor("SHAFANA FAZAL") is None
        assert fw.clean_actor('California’s "Non-Ultraprocessed" Seal') is None
        assert fw.clean_actor("ADM") == "ADM"

    def test_slugify(self):
        assert fw.slugify("Präzisionsfermentation") == "praezisionsfermentation"
        assert fw.slugify("LFP cells (2026)") == "lfp-cells-2026"


class TestTierTwin:
    """TIER_SQL ist der SQL-Zwilling von tiers.tier_of — die Regel, die die
    Python-Funktion ausspricht, muss im CASE-Ausdruck wörtlich stehen."""

    @pytest.mark.parametrize("name,stype,sig,expected", [
        ("Google Patents", "api", None, "patent"), ("EPO Weekly", "api", None, "patent"),
        ("NSF Awards", "api", None, "funding"), ("CORDIS", "api", None, "funding"),
        ("OpenAlex fresh: Fermentation", "research", None, "science"), ("bioRxiv preprints", "api", None, "science"),
        ("FoodNavigator", "trade_media", "funding", "funding"), ("FoodNavigator", "trade_media", "product_launch", "market"),
    ])
    def test_python_rule(self, name, stype, sig, expected):
        assert tier_of(name, stype, sig) == expected

    def test_sql_expression_names_the_same_markers(self):
        for marker in ("google patents", "epo ", "nih reporter", "nsf ", "openaire", "ukri", "sec form d", "sbir",
                       "cordis", "preprints", "openalex", "trade_media", "press_wire", "brand", "'funding'"):
            assert marker in fw.TIER_SQL


class TestCustomerFile:
    def test_example_file_validates(self):
        doc = fw.load_customer(str(ROOT / "fields" / "example.yaml"))
        assert doc["slug"] == "example" and len(doc["fields"]) == 3
        assert doc["fields"][0]["slug"] == "praezisionsfermentation"
        assert all(f["terms"] for f in doc["fields"])

    def test_missing_terms_is_an_error(self):
        with pytest.raises(ValueError, match="terms"):
            fw.validate_customer({"customer": "x", "fields": [{"name": "leer"}]})
        with pytest.raises(ValueError, match="doppelter"):
            fw.validate_customer({"customer": "x", "fields": [{"name": "A", "terms": ["a"]}, {"name": "a", "terms": ["b"]}]})

    def test_real_customer_files_are_gitignored(self):
        gi = (ROOT / ".gitignore").read_text()
        assert "fields/*.yaml" in gi and "!fields/example*.yaml" in gi


def _week_payload() -> dict:
    tiers = ("science", "patent", "funding", "market")
    qs = [f"{y}-Q{q}" for y in (2023, 2024, 2025, 2026) for q in (1, 2, 3, 4)][3:15]
    f = {"name": "Präzisionsfermentation", "slug": "praezisionsfermentation", "terms": ["precision fermentation"], "cpc": ["C12P21/02"],
         "week": {t: {"n": 9 if t == "market" else 0, "median4": 3.5 if t == "market" else 0, "delta_pct": 157 if t == "market" else None} for t in tiers},
         "weekly": {t: [3, 2, 4, 3, 5, 2, 4, 9] if t == "market" else [0] * 8 for t in tiers},
         "quarterly": {t: [{"q": q, "n": 5, "panel_n": 4, "per10k": 2.5} for q in qs] for t in tiers},
         "top": {t: ([{"title": "LFP <sup>x</sup> Dominates", "source": "Energy-Storage.news", "url": "https://x", "date": "2026-09-16", "status": "published"}] if t == "market" else []) for t in tiers},
         "actors": [{"name": "Ferm Labs", "n90": 2, "week": 2, "new": True}], "actors_total": 1, "actors_new_week": 1,
         "sources_90d": 12, "signals_90d": 40, "patents_window": 7, "top_source": ["vegconomist", 45],
         "nests": [{"label": "Sustainable Food Systems", "scope": "vertical:FOOD", "size": 81, "cohesion": 0.8, "first_month": "2019-01",
                    "age_months": 92, "novelty_lift": 1.7, "tier_order": ["science", "market"], "rep_titles": ["a", "b"]}]}
    return {"week": "2026-W38", "week_start": "2026-09-14", "week_end": "2026-09-20", "measured_on": "2026-09-20",
            "weeks": [f"2026-W{w}" for w in range(31, 39)], "quarters": qs,
            "panel_size": {"science": 51, "funding": 46, "market": 55}, "fields": [f]}


class TestRender:
    def test_week_sheet_carries_numbers_labels_and_no_model_text(self):
        html = fr.render_week(_week_payload(), "Kunde X", sample=True)
        assert "9 vs. 3,5 · +157 %" in html                # Delta-Badge
        assert "Beispiel zur Demonstration" in html
        assert "kein Sprachmodell" in html
        assert "<sup>" not in html and "LFP x Dominates" in html   # Tags aus Titeln entfernt
        assert "Quellenkonzentration: vegconomist liefert 45 %" in html
        assert "Wissenschaft → Markt" in html

    def test_week_sheet_without_sample_flag_has_no_demo_badge(self):
        assert "Beispiel zur Demonstration" not in fr.render_week(_week_payload(), "Kunde X")

    def test_delta_badge_classes(self):
        assert 'class="delta up"' in fr.delta_badge(9, 3.5)
        assert 'class="delta dn"' in fr.delta_badge(1, 4)
        assert 'class="delta flat"' in fr.delta_badge(4, 4)
        assert "kein Vergleich" in fr.delta_badge(0, 0)

    def test_sheet_without_anchor_says_so_and_omits_reading(self):
        years = list(range(1990, 2027))
        ser = {t: [{"y": y, "n": (y - 1989) if t == "patent" else 0, "per10k": None} for y in years] for t in fw.TIERS}
        d = {"field": {"name": "Feld", "name_en": "Field", "slug": "feld", "terms": ["x"], "cpc": [], "reading": ""},
             "measured_on": "2026-09-20", "series": ser, "takeoff": {t: None for t in fw.TIERS}, "first": {t: None for t in fw.TIERS},
             "totals": {t: 0 for t in fw.TIERS}, "science_from": 2010, "market_from": 2020, "patents_5y": 0,
             "patents_with_assignee_5y": 0, "assignees": [], "subclasses": [], "landmarks": [], "offices": [], "top_works": [], "quant": None}
        html = fr.render_sheet(d, None, "Kunde")
        assert "kein CPC-Anker" in html and "7 · Einordnung" not in html
        d["field"]["reading"] = "Ein Absatz."
        html = fr.render_sheet(d, None, "Kunde")
        assert "7 · Einordnung" in html and "vom Analysten geschrieben" in html

    def test_bars_svg_marks_partial_last_bar_and_handles_gaps(self):
        svg = fr.bars_svg([("23", 1.0), ("24", None), ("25", 3.0)], "#000", partial_last=True)
        assert 'opacity="0.45"' in svg and svg.count("<rect") == 2


class TestCron:
    def test_crontab_template_and_wrapper_agree(self):
        """Field Watch laeuft samstags NACH dem Pulse — die Uhrzeit selbst ist frei.

        Der Test pinnte bis 2026-09-26 "30 12 * * 6" und brach damit, als der Owner die
        Samstags-Mittagsjobs auf vor 9 Uhr zog (Pulse 08:30, Field Watch 08:45). Gepinnt
        gehoert die Reihenfolge, nicht die Minute: Field Watch liest, was der Lauf davor
        gerechnet hat."""
        import re
        crontab = (ROOT / "deploy" / "crontab.txt").read_text()
        times = {}
        for line in crontab.splitlines():
            m = re.match(r"^(\d+)\s+(\d+)\s+\*\s+\*\s+6\b", line)
            if not m:
                continue
            for job in ("weekly_field_watch.sh", "weekly_research_pulse.sh"):
                if job in line:
                    times[job] = int(m.group(2)) * 60 + int(m.group(1))
        assert "weekly_field_watch.sh" in times, "keine Samstags-Zeile fuer Field Watch"
        assert "weekly_research_pulse.sh" in times, "keine Samstags-Zeile fuer den Pulse"
        assert times["weekly_field_watch.sh"] > times["weekly_research_pulse.sh"], \
            "Field Watch muss nach dem Pulse laufen"
        wrapper = (ROOT / "scripts" / "weekly_field_watch.sh").read_text()
        assert "field_watch.py --all" in wrapper and "gpu_guard_wait" not in wrapper   # keine GPU, kein Wächter
        assert "weekly_field_watch" in (ROOT / "scripts" / "review_notify.py").read_text()

    def test_example_yaml_is_valid_yaml_with_cpc_anchors(self):
        doc = yaml.safe_load((ROOT / "fields" / "example.yaml").read_text())
        assert all(f.get("cpc") for f in doc["fields"])
