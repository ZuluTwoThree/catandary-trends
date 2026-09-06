"""Agentischer Newsletter-Entwurf (Prototyp) — Kontrakt ohne GPU/Modell.

Geprueft werden nur die reinen Teile: Kriterienkatalog und Schema, die
Abbruchbedingung, der Rundenzaehler des Loops, der Parser der Ueberarbeitung
und die maschinelle Pruefung. Der Modellzugriff wird injiziert (chat_fn /
structured_fn) — pytest startet nie einen llama-server.
"""
import json

import pytest
from pydantic import ValidationError

import scripts.newsletter_agentic_draft as ag


# ---------------------------------------------------------------------------
# Testdaten: die kleinste Struktur, die die Prompt-Builder akzeptieren
# ---------------------------------------------------------------------------

def _data():
    from collections import Counter
    trends = [
        {"id": 1, "title_en": "Vitalfluid raises EUR 17.2 million for plasma crop protection",
         "summary_en": "Dutch agritech Vitalfluid closed a EUR 17.2 million round.",
         "source_name": "AgFunder", "slug": "vitalfluid", "source_url": "https://x/1",
         "mega_trend": "future_of_food", "trend_signal_type": "funding"},
        {"id": 2, "title_en": "Data centre water use doubles in Arizona",
         "summary_en": "Water draw by data centres in Arizona doubled year on year.",
         "source_name": "Carbon Brief", "slug": "dc-water", "source_url": "https://x/2",
         "mega_trend": "climate_resilience", "trend_signal_type": "market_shift"},
    ]
    verticals = {
        "TECH": {"count": 12, "top_trends": trends,
                 "mega_trend_counts": Counter({"climate_resilience": 4}),
                 "signal_types": Counter({"market_shift": 6})},
        "ECO": {"count": 7, "top_trends": trends[1:],
                "mega_trend_counts": Counter({"climate_resilience": 3}),
                "signal_types": Counter({"market_shift": 4})},
    }
    return {
        "total_count": 19, "period": "2026-W35", "period_label": "Week 35/2026",
        "verticals": verticals,
        "mega_trend_counts": Counter({"climate_resilience": 7, "future_of_food": 3}),
        "mega_trend_map": {"climate_resilience": {"name_en": "Climate Resilience & Adaptation"},
                           "future_of_food": {"name_en": "Future of Food & Agriculture"}},
        "signal_types": Counter({"market_shift": 10, "funding": 4}),
        "top_trends": trends,
    }


@pytest.fixture(autouse=True)
def _no_momentum(monkeypatch):
    """_format_mega_trend_momentum fragt die DB — im Test abschalten."""
    import pipeline.mega_momentum as mm
    monkeypatch.setattr(mm, "measure", lambda *a, **k: {})


def _critique(overall=4.8, defects=(), **scores):
    base = {"evidence": 5, "specificity": 5, "density": 5, "tone": 5, "structure": 5}
    base.update(scores)
    return ag.Critique(overall=overall, defects=list(defects), **base)


def _defect(criterion="specificity", quote="Market shifts define the sector"):
    return ag.Defect(criterion=criterion, quote=quote, problem="zu abstrakt",
                     fix="Firma benennen")


def _draft(editorial="Alpha beta gamma. " * 12):
    return ag.Draft(editorial=editorial.strip(),
                    verticals={"TECH": "Tech sentence.", "ECO": "Eco sentence."})


# ---------------------------------------------------------------------------
# 1. Kriterienkatalog + Schema
# ---------------------------------------------------------------------------

def test_criteria_catalogue_is_complete_and_matches_the_schema():
    assert list(ag.CRITERIA) == ["evidence", "specificity", "density", "tone", "structure"]
    for key, text in ag.CRITERIA.items():
        assert len(text) > 60, f"{key}: Kriterium ohne Definition ist wertlos"
    # Jedes Kriterium ist im Schema eine eigene Note und ein zulaessiges
    # Defect-Label — sonst kann der Kritiker Maengel nicht zuordnen.
    props = ag.Critique.model_json_schema()["properties"]
    for key in ag.CRITERIA:
        assert key in props
    with pytest.raises(ValidationError):
        ag.Defect(criterion="vibes", quote="q", problem="p", fix="f")


def test_critic_schema_has_no_field_for_a_rewrite():
    """Der Kritiker darf nicht selbst umschreiben — erzwungen durchs Schema."""
    fields = set(ag.Critique.model_json_schema()["properties"])
    assert not fields & {"revision", "rewrite", "text", "editorial", "improved"}
    assert set(ag.Defect.model_fields) == {"criterion", "quote", "problem", "fix"}


def test_critic_prompt_carries_catalogue_machine_check_and_ban_list():
    data = _data()
    check = ag.machine_check(_draft(), ag.grounding_source(data))
    prompt = ag.build_critic_prompt(_draft(), data, check)
    for key in ag.CRITERIA:
        assert key in prompt
    assert "landscape" in prompt          # BANNED_PHRASES
    assert "<automatic_check>" in prompt
    assert "Do NOT rewrite" in prompt


def test_scores_are_bounded():
    with pytest.raises(ValidationError):
        _critique(evidence=6)
    with pytest.raises(ValidationError):
        ag.Critique(evidence=5, specificity=5, density=5, tone=5, structure=5, overall=5.4)


# ---------------------------------------------------------------------------
# 2. Abbruchbedingung
# ---------------------------------------------------------------------------

CLEAN = {"ungrounded_specifics": 0, "ungrounded_names": 0, "banned_phrases": [],
         "editorial": {"specifics": [], "names": []}, "verticals": {}}


def test_accept_needs_score_and_clean_evidence():
    ok, why = ag.is_accepted(_critique(overall=4.5), CLEAN)
    assert ok and "4.5" in why


def test_reject_below_threshold():
    ok, why = ag.is_accepted(_critique(overall=4.4), CLEAN)
    assert not ok and "4.4" in why


def test_open_evidence_defect_blocks_even_at_a_top_score():
    ok, why = ag.is_accepted(_critique(overall=5.0, defects=[_defect("evidence")]), CLEAN)
    assert not ok and "Belegtreue" in why


def test_machine_grounding_outranks_the_models_opinion():
    """Eine gemessene erfundene Zahl blockiert, auch wenn der Kritiker sie
    uebersieht und eine 5,0 vergibt."""
    dirty = {**CLEAN, "ungrounded_specifics": 2}
    ok, why = ag.is_accepted(_critique(overall=5.0), dirty)
    assert not ok and "unbelegte Zahl" in why


def test_unsupported_person_names_do_not_block():
    warn = {**CLEAN, "ungrounded_names": 3}
    ok, _ = ag.is_accepted(_critique(overall=4.6), warn)
    assert ok


def test_threshold_is_configurable():
    assert ag.is_accepted(_critique(overall=4.0), CLEAN, threshold=4.0)[0]
    assert not ag.is_accepted(_critique(overall=4.0), CLEAN, threshold=4.5)[0]


# ---------------------------------------------------------------------------
# 3. Maschinelle Pruefung
# ---------------------------------------------------------------------------

def test_machine_check_finds_invented_figures_and_banned_phrases():
    data = _data()
    src = ag.grounding_source(data)
    draft = ag.Draft(
        editorial="Vitalfluid raised EUR 17.2 million while the market grew 43% in 2019.",
        verticals={"TECH": "The landscape shifted.", "ECO": "Water use doubled."})
    check = ag.machine_check(draft, src)
    assert "43%" in check["editorial"]["specifics"]
    assert "2019" in check["editorial"]["specifics"]
    assert check["ungrounded_specifics"] >= 2
    assert check["banned_phrases"] == ["landscape"]


def test_machine_check_accepts_figures_that_are_in_the_data():
    data = _data()
    draft = ag.Draft(editorial="Vitalfluid closed a EUR 17.2 million round.", verticals={})
    assert ag.machine_check(draft, ag.grounding_source(data))["ungrounded_specifics"] == 0


def test_grounding_source_excludes_the_instruction_numbers():
    """Die Anweisungen nennen '150-200 Woerter' — stuenden sie in der Quelle,
    waere eine erfundene 200 im Text plotzlich belegt."""
    src = ag.grounding_source(_data())
    assert "150-200 words" not in src
    assert "Vitalfluid" in src


def test_format_machine_check_states_a_clean_result_explicitly():
    assert "No fabricated figures" in ag.format_machine_check(CLEAN)
    dirty = {**CLEAN, "editorial": {"specifics": ["43%"], "names": []},
             "banned_phrases": ["robust"]}
    text = ag.format_machine_check(dirty)
    assert "43%" in text and "robust" in text


# ---------------------------------------------------------------------------
# 4. Parser der Ueberarbeitung
# ---------------------------------------------------------------------------

def _revision(editorial_words=80, verticals=("TECH", "ECO")):
    body = " ".join(["Alpha"] * editorial_words)
    parts = [f"## EDITORIAL\n{body}", "## VERTICALS"]
    for v in verticals:
        parts.append(f"{v}\n{v} sentence one. {v} sentence two.")
    return "\n\n".join(parts)


def test_parse_revision_reads_both_sections():
    draft, problems = ag.parse_revision(_revision(), _draft())
    assert problems == []
    assert set(draft.verticals) == {"TECH", "ECO"}
    assert draft.editorial.startswith("Alpha")


def test_parse_revision_keeps_previous_vertical_when_one_is_missing():
    prev = _draft()
    draft, problems = ag.parse_revision(_revision(verticals=("TECH",)), prev)
    assert draft.verticals["ECO"] == prev.verticals["ECO"]
    assert any("ECO" in p for p in problems)


def test_parse_revision_never_invents_a_vertical():
    prev = _draft()
    draft, _ = ag.parse_revision(_revision(verticals=("TECH", "ECO", "FOOD")), prev)
    assert set(draft.verticals) == set(prev.verticals)


def test_parse_revision_falls_back_on_a_truncated_editorial():
    prev = _draft()
    draft, problems = ag.parse_revision("## EDITORIAL\nToo short.\n\n## VERTICALS\nTECH\nx.",
                                        prev)
    assert draft.editorial == prev.editorial
    assert any("zu kurz" in p for p in problems)


def test_parse_revision_survives_missing_markers():
    prev = _draft()
    draft, problems = ag.parse_revision(" ".join(["Alpha"] * 80), prev)
    assert draft.verticals == prev.verticals
    assert "VERTICALS-Marker fehlt" in problems


# ---------------------------------------------------------------------------
# 5. Loop: Rundenzaehler, Abbruch, Rueckfallpfade
# ---------------------------------------------------------------------------

class FakeModel:
    """Schreiber/Ueberarbeiter als Textquelle, Kritiker als Notenfolge."""

    def __init__(self, scores, defects_per_round=None):
        self.scores = list(scores)
        self.defects_per_round = defects_per_round or {}
        self.chat_calls: list[str] = []
        self.critic_calls = 0

    def chat(self, prompt, system, temperature):
        self.chat_calls.append(prompt)
        if "Write the editorial summary" in prompt:
            return " ".join(["Alpha"] * 160)
        if "Write per-vertical summaries" in prompt:
            return "TECH\nTech sentence.\n\nECO\nEco sentence."
        return _revision()

    def structured(self, prompt, system, temperature):
        i = self.critic_calls
        self.critic_calls += 1
        if i >= len(self.scores):
            return None
        score = self.scores[i]
        if score is None:
            return None
        return _critique(overall=score, defects=self.defects_per_round.get(i + 1, ()))


def _run(model, **kw):
    return ag.run_loop(_data(), chat_fn=model.chat, structured_fn=model.structured, **kw)


def test_loop_stops_on_the_first_excellent_round():
    m = FakeModel([4.9])
    res = _run(m)
    assert res["rounds_used"] == 1 and res["accepted"]
    assert m.critic_calls == 1
    # Runde 1 = Schreiber-Entwurf, keine Ueberarbeitung.
    assert len(m.chat_calls) == 2
    assert res["final_draft"] == res["first_draft"]


def test_loop_revises_until_the_score_is_reached():
    m = FakeModel([3.0, 4.0, 4.7])
    res = _run(m)
    assert res["rounds_used"] == 3 and res["accepted"]
    assert m.critic_calls == 3
    assert len(m.chat_calls) == 2 + 2      # 2 Schreiber + 2 Ueberarbeitungen
    assert "angenommen in Runde 3" in res["stop_reason"]


def test_loop_never_exceeds_the_round_budget():
    m = FakeModel([2.0] * 10)
    res = _run(m, max_rounds=5)
    assert res["rounds_used"] == 5
    assert not res["accepted"]
    assert m.critic_calls == 5
    # Nach der letzten Kritik wird NICHT mehr blind ueberarbeitet.
    assert len(m.chat_calls) == 2 + 4
    assert "Rundenbudget" in res["stop_reason"]


def test_every_round_is_logged_with_scores_and_machine_numbers():
    m = FakeModel([2.5, 4.6])
    res = _run(m)
    assert [r["round"] for r in res["rounds"]] == [1, 2]
    for r in res["rounds"]:
        assert set(r["scores"]) == set(ag.CRITERIA)
        assert "ungrounded_specifics" in r["machine"]
        assert r["draft"]["editorial"]
        assert r["seconds"] >= 0


def test_a_broken_critic_ends_the_loop_without_losing_the_draft():
    m = FakeModel([None])
    res = _run(m)
    assert not res["accepted"]
    assert res["rounds"][-1]["error"]
    assert res["final_draft"]["editorial"]      # Rueckfall: Entwurf bleibt


def test_open_evidence_defect_forces_another_round():
    m = FakeModel([5.0, 5.0], defects_per_round={1: [_defect("evidence")]})
    res = _run(m)
    assert res["rounds_used"] == 2
    assert "Belegtreue" in res["rounds"][0]["reason"]


def test_protocol_is_json_serialisable():
    res = _run(FakeModel([4.8]))
    json.loads(json.dumps(res, default=str))


# ---------------------------------------------------------------------------
# 6. Kritiker und Ueberarbeiter sehen dieselben Daten
# ---------------------------------------------------------------------------

def test_critic_sees_the_per_vertical_signals_too():
    """Erster Lauf 2026-09-06: der Kritiker bekam nur den Editorial-Block und
    erklaerte echte Vertikal-Signale fuer erfunden. Kritiker, Ueberarbeiter
    und maschinelle Pruefung muessen dasselbe Material sehen."""
    data = _data()
    check = ag.machine_check(_draft(), ag.grounding_source(data))
    critic = ag.build_critic_prompt(_draft(), data, check)
    reviser = ag.build_reviser_prompt(_draft(), data, _critique(3.0, [_defect()]), check)
    block = ag.full_data_block(data)
    assert block in critic
    assert block in reviser
    assert ag.grounding_source(data) == block
    # ECO taucht nur im Vertikal-Block auf
    assert "ECO — Sustainability" in critic
