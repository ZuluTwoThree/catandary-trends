"""OpenAlex-Sync v2 (Owner 2026-10-05): Änderungen erkennen statt verwerfen.

Die Textfälle sind die, die am 05.10. an 4.234 vorhandenen Werken gemessen wurden
(docs/openalex_sync_2026-10-05.md): Leerraum, Titel-Markup, Seiten-Müll statt Abstract,
abgeschnittener Abstract, OpenAlex liefert nur noch den ersten Absatz.
"""
from datetime import date, datetime

import pytest

from pipeline import openalex_sync as ox

ABS = ("Aims. We present a comprehensive X-ray study of the population of supernova remnants. "
       "Methods. We combined all archival observations. Results. We find 51 remnants.")


class TestText:
    def test_whitespace_and_punctuation_are_not_a_change(self):
        a = "The bit error rate (BER) is the percentage. The different modulation techniques matter here a lot."
        b = "The bit error rate (BER) is the percentage.The different  modulation techniques matter here a lot."
        assert ox.text_fp("T", a) == ox.text_fp("T", b)
        assert not ox.decide_text("T", a, "T", b).changed

    def test_markup_only_is_not_a_change(self):
        assert not ox.decide_text("Ultrathin MnO<sub>2</sub>/Graphene", ABS, "Ultrathin MnO2/Graphene", ABS).changed
        assert not ox.decide_text("Bi&lt;sub&gt;1.6&lt;/sub&gt;Pb", ABS, "Bi1.6Pb", ABS).changed
        assert ox.strip_markup("<i>Xenopus</i> &amp; MnO<sub>2</sub>") == "Xenopus & MnO2"

    def test_leading_label_and_dropped_subtitle_are_not_changes(self):
        assert not ox.decide_text("T", "Abstract " + ABS, "T", ABS).changed
        assert not ox.decide_text("T", "Background " + ABS, "T", ABS).changed
        assert not ox.decide_text("NPL Securitization in China: Some Initial Considerations", ABS,
                                  "NPL Securitization in China", ABS).changed

    def test_restored_diacritics_are_a_change(self):
        assert ox.decide_text("T", ABS + " Patrn de Distribucin", "T", ABS + " Patrón de Distribución").changed

    def test_real_title_change_is_taken(self):
        d = ox.decide_text("Preliminary results on X", ABS, "Final results on X and Y", ABS)
        assert d.changed and d.title_changed and not d.abstract_changed

    def test_shortened_prefix_keeps_ours(self):
        d = ox.decide_text("T", ABS, "T", "Aims. We present a comprehensive X-ray study of the population of supernova remnants.")
        assert not d.changed and d.shortened and d.abstract == ABS

    def test_junk_replaced_by_real_abstract_is_taken(self):
        junk = "MEPS Marine Ecology Progress Series Contact the journal Facebook Twitter RSS Mailing List Subscribe"
        real = "Anchovies and sardines hold a very important position in pelagic ecosystems and fluctuate in abundance."
        d = ox.decide_text("T", junk, "T", real)
        assert d.changed and d.abstract == real and not d.shortened

    def test_completed_abstract_is_taken(self):
        tail = "group are organized into gpPULs. Variation in gpPULs explains specialization at species level."
        full = "Firmicutes and Bacteroidetes colonize the human large intestine. " + tail
        assert ox.decide_text("T", tail, "T", full).abstract == full

    def test_empty_or_tiny_new_abstract_never_overwrites(self):
        assert ox.decide_text("T", ABS, "T", "Short.").abstract == ABS


class TestHelpers:
    def test_fp_fits_bigint(self):
        v = ox.text_fp("x", "y")
        assert -2**63 <= v < 2**63

    def test_reconstruct(self):
        assert ox.reconstruct({"world": [1], "hello": [0]}) == "hello world"
        assert ox.reconstruct('{"a": [0]}') == "a"
        assert ox.reconstruct(None) == ""

    def test_citation_counts_roll_with_the_year(self):
        cby = [{"year": 2026, "cited_by_count": 3}, {"year": 2025, "cited_by_count": 2}, {"year": 2020, "cited_by_count": 5}]
        assert ox.citation_counts(cby, date(2026, 10, 5)) == (5, 10)
        assert ox.citation_counts(cby, date(2027, 3, 1)) == (3, 10)

    def test_keep_filter_unchanged(self):
        base = {"type": "article", "is_paratext": False, "language": "en", "publication_year": 2020,
                "abstract_inverted_index": {"a": [0]}, "cited_by_count": 1}
        assert ox.keep_row(base)
        assert not ox.keep_row(base | {"cited_by_count": 0})
        assert ox.keep_row(base | {"publication_year": 2025, "cited_by_count": 0})
        assert not ox.keep_row(base | {"language": "de"})
        assert not ox.keep_row(base | {"abstract_inverted_index": None})

    def test_window_is_same_day_and_never_wraps(self):
        assert ox.window_end("09:00-17:00", datetime(2026, 10, 6, 10, 0)) == (True, datetime(2026, 10, 6, 17, 0))
        assert ox.window_end("09:00-17:00", datetime(2026, 10, 6, 17, 5))[0] is False   # nach dem Warten zu spät
        assert ox.window_end("09:00-17:00", datetime(2026, 10, 6, 8, 59))[0] is False
        assert ox.window_end(None) == (True, None)
        with pytest.raises(ValueError):
            ox.window_end("17:00-09:00")

    def test_deadline_wraps_midnight(self):
        assert ox.deadline("00:30", datetime(2026, 10, 6, 9, 0)) == datetime(2026, 10, 7, 0, 30)
        assert ox.deadline("23:00", datetime(2026, 10, 6, 9, 0)) == datetime(2026, 10, 6, 23, 0)
        assert ox.deadline(None) is None
        with pytest.raises(ValueError):
            ox.deadline("25h")


def _inv(text):
    inv = {}
    for n, w in enumerate(text.split()):
        inv.setdefault(w, []).append(n)
    return inv


def _work(i="W1", title="Title", abstract=ABS, cites=3, fwci=1.0, retracted=False, oa=False, total=3, idx=0):
    r = {"id": f"https://openalex.org/{i}", "title": title,
         "abstract_inverted_index": _inv(abstract),
         "publication_year": 2024, "type": "article", "cited_by_count": cites, "fwci": fwci,
         "is_retracted": retracted, "open_access": {"is_oa": oa, "oa_url": "https://x/pdf" if oa else None},
         "primary_location": {"source": {"display_name": "Journal X"}}, "funders": [{"display_name": "DFG"}],
         "counts_by_year": [{"year": 2026, "cited_by_count": total}], "updated_date": "2026-09-23"}
    return ox.Work.from_row(r, idx, date(2026, 10, 5))


def _state(w, **kw):
    s = {"oa_fp": w.fp, "cited_by_count": w.cited_by_count, "fwci": w.fwci, "cnp": w.cnp, "type": w.type,
         "is_retracted": w.is_retracted, "is_oa": w.is_oa, "shortened": False}
    s.update(kw)
    return s


class TestPlan:
    def test_new_work_is_inserted_with_side_data_and_archive(self):
        w = _work(oa=True)
        p = ox.plan_batch([w], {}, {})
        assert p.insert == [w] and p.side == [w] and p.oa == [w] and p.cites == [w] and p.archive == [0]
        assert len(p.state) == 1 and not p.update_text

    def test_first_touch_unchanged_text_writes_state_only(self):
        w = _work()
        p = ox.plan_batch([w], {}, {"W1": {"title": "Title", "abstract": ABS, "is_retracted": False}})
        assert not p.insert and not p.update_text and not p.archive
        assert len(p.state) == 1 and p.side == [w]          # Journal/Förderer einmal nachtragen

    def test_known_unchanged_work_costs_nothing(self):
        w = _work()
        p = ox.plan_batch([w], {"W1": _state(w)}, {})
        assert p.unchanged == 1 and not (p.state or p.insert or p.update_text or p.side or p.oa or p.cites)

    def test_citation_change_goes_to_state_and_recent_not_to_corpus(self):
        w = _work(cites=9)
        p = ox.plan_batch([w], {"W1": _state(w, cited_by_count=3)}, {})
        assert len(p.state) == 1 and p.cites == [w] and not p.update_text and not p.retraction

    def test_text_change_with_known_state_is_checked_against_corpus(self):
        w = _work(title="Revised title")
        st = _state(w, oa_fp=123)
        p = ox.plan_batch([w], {"W1": st}, {"W1": {"title": "Old title", "abstract": ABS, "is_retracted": False}})
        assert len(p.update_text) == 1 and p.archive == [0]

    def test_shortened_is_recorded_and_not_rechecked_next_time(self):
        w = _work(abstract="Aims. We present a comprehensive X-ray study of the population of supernova remnants.")
        p = ox.plan_batch([w], {}, {"W1": {"title": "Title", "abstract": ABS, "is_retracted": False}})
        assert not p.update_text and p.shortened == 1 and p.state[0][8] is True
        nxt = ox.plan_batch([w], {"W1": _state(w, shortened=True)}, {})
        assert nxt.unchanged == 1

    def test_retraction_flip_is_written(self):
        w = _work(retracted=True)
        p = ox.plan_batch([w], {"W1": _state(w, is_retracted=False)}, {})
        assert p.retraction == [("W1", True)] and len(p.state) == 1

    def test_float4_roundtrip_is_not_a_change(self):
        w = _work(fwci=0.1)
        p = ox.plan_batch([w], {"W1": _state(w, fwci=0.10000000149011612)}, {})
        assert p.unchanged == 1 and not p.state

    def test_newly_open_access_is_added(self):
        w = _work(oa=True)
        p = ox.plan_batch([w], {"W1": _state(w, is_oa=False)}, {})
        assert p.oa == [w]
