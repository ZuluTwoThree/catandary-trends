"""Auftrags-Intake (pipeline/dossier_brief.py, Stufe 1 des Dossier-Agent-Plans).

Ohne Modell: der Fragecheck und die Advisor-Weiche sind deterministisch, die
Modellaufrufe (`build_brief`, `must_answer_scores`) laufen gegen ein Fake-
`chat_structured`. Abnahme laut Plan: datacenter v1 wird am Intake abgewiesen;
„which stack should …" wird als Dossier + Advisor geroutet.
"""
import pytest

from pipeline import dossier_brief as b

DATACENTER_V1 = ("The purpose of the dossier is to provide a free sample for the IT Manager "
                 "of a small German technology firm providing IT Infrastructure and software "
                 "development services in their own company group and for related regional "
                 "partner companies.")
DATACENTER_V2 = ("Which virtualization stack should a small German IT service firm run for its "
                 "own company group and its regional partner companies after the VMware "
                 "licensing change, and which BSI, GDPR and EU Data Act requirements apply to "
                 "such an offering? Context: the dossier serves as a free sample for the IT "
                 "manager of a small German technology firm.")


class TestDeterministicQuestionCheck:
    def test_datacenter_v1_is_rejected_with_a_reason(self):
        ok, reason = b.deterministic_question_check(DATACENTER_V1)
        assert ok is False
        assert "does not ask" in reason and "The purpose of the dossier" in reason

    def test_empty_is_fine_default_question_applies(self):
        assert b.deterministic_question_check("") == (True, "")
        assert b.deterministic_question_check(None) == (True, "")
        assert b.deterministic_question_check("   \n ") == (True, "")

    def test_question_mark_anywhere_passes(self):
        assert b.deterministic_question_check(DATACENTER_V2)[0] is True
        assert b.deterministic_question_check("Context first. What moves in LFP cells?")[0] is True

    @pytest.mark.parametrize("q", [
        "Which stack should we run after the Broadcom change",
        "How mature is sodium-ion for stationary storage",
        "welche Regulierung gilt für Novel Food in der EU",
        "Was bewegt sich bei Perowskit-Tandemzellen",
        "\"Should a mid-sized firm adopt Proxmox\"",
        "Is the EU Data Act applicable to hosting providers",
    ])
    def test_interrogative_opening_passes_without_question_mark(self, q):
        assert b.deterministic_question_check(q) == (True, "")

    @pytest.mark.parametrize("q", [
        "The dossier is a free sample for the IT manager.",
        "Overview of virtualization stacks for SMEs.",
        "Ein Überblick über Batterietechnologien für Kunden.",
    ])
    def test_descriptions_fail(self, q):
        ok, reason = b.deterministic_question_check(q)
        assert ok is False and reason


class TestRouting:
    @pytest.mark.parametrize("q", [
        DATACENTER_V2,
        "Which battery chemistry should we pick for the 2027 platform?",
        "What should the board recommend on perovskite licensing?",
        "Welche Plattform sollten wir für das Rechenzentrum wählen?",
        "Should we adopt Proxmox or stay on VMware?",
        "Please give a recommendation on stationary storage suppliers.",
    ])
    def test_which_should_routes_to_advisor(self, q):
        assert b.route_artefact(q) == "dossier+advisor"

    @pytest.mark.parametrize("q", [
        "What is moving in lithium iron phosphate cells, and what is proven?",
        "Which regulations apply to novel foods in the EU?",
        "",
    ])
    def test_evidence_questions_stay_dossier(self, q):
        assert b.route_artefact(q) is None


def _fake_brief(**over):
    base = dict(question_type="technology",
                decision="Whether to migrate the group's virtualization to a non-VMware stack.",
                reader="IT manager of a small German IT service firm",
                constraints=["Germany", "no VS-NfD data"],
                must_answer=["Which stacks are supported for at least five years?",
                             "What does BSI SYS.1.5 require of the hypervisor?",
                             "Does the EU Data Act apply to the partner offering?"],
                artefact="dossier", is_question=True, rejection_reason="")
    base.update(over)
    return b.Brief(**base)


class TestBuildBrief:
    def test_fake_chat_returns_brief_and_deterministic_routing_wins(self):
        seen = {}
        def chat(**kw):
            seen.update(kw)
            return _fake_brief(artefact="dossier")     # Modell sagt Dossier …
        br = b.build_brief("datacenter virtualization", DATACENTER_V2, {"mode": "technology"}, chat=chat)
        assert br.artefact == "dossier+advisor"          # … die Weiche sagt Advisor
        assert br.is_question is True and br.rejection_reason == ""
        assert br.must_answer and len(br.must_answer) == 3
        assert seen["schema"] is b.Brief and seen["temperature"] == 0.0
        assert "datacenter virtualization" in seen["prompt"] and DATACENTER_V2[:40] in seen["prompt"]
        assert seen["system"] == b.BRIEF_SYSTEM

    def test_datacenter_v1_is_rejected_even_if_the_model_liked_it(self):
        br = b.build_brief("datacenter virtualization", DATACENTER_V1, {},
                           chat=lambda **kw: _fake_brief(is_question=True))
        assert br.is_question is False and "does not ask" in br.rejection_reason

    def test_model_cannot_reject_a_real_question(self):
        br = b.build_brief("t", "What moves in LFP?", {},
                           chat=lambda **kw: _fake_brief(is_question=False, rejection_reason="nah"))
        assert br.is_question is True and br.rejection_reason == ""

    def test_landscape_mode_forces_the_type_and_context_reaches_the_prompt(self):
        seen = {}
        def chat(**kw):
            seen.update(kw)
            return _fake_brief(question_type="technology")
        br = b.build_brief("batteries", "", {"mode": "landscape", "cpc": "H01M4/5825"}, chat=chat)
        assert br.question_type == "landscape"
        assert "Landscape mode" in seen["prompt"] and "H01M4/5825" in seen["prompt"]

    def test_none_from_the_model_raises(self):
        with pytest.raises(RuntimeError):
            b.build_brief("t", "What?", {}, chat=lambda **kw: None)

    def test_must_answer_is_capped_and_deduplicated(self):
        many = [f"Point {i}?" for i in range(9)] + ["Point 1?"]
        br = b.build_brief("t", "What?", {}, chat=lambda **kw: _fake_brief(must_answer=many))
        assert len(br.must_answer) == b.MUST_ANSWER_MAX


REPORT = """# Datacenter virtualization

## Decision summary
Broadcom set VMware vSphere Foundation subscription terms on 12 March 2024 [[W12]]. Proxmox VE 8.2 was released on 24 April 2024 [[W13]].
The Data Act applies from 12 September 2025 to data holders in the EU [[W20]].

## What is moving
BSI published SYS.1.5 edition 2022 in February 2022 and it requires hypervisor hardening. This sentence has no citation.
"""

MUST = ["Which stacks are supported for at least five years?",
        "What does BSI SYS.1.5 require of the hypervisor?",
        "Does the EU Data Act apply to the partner offering?",
        "What are the licence costs per socket?"]


class TestMustAnswerScores:
    def test_quote_verified_in_text_and_cited(self):
        def chat(**kw):
            assert kw["schema"] is b.MustAnswerEval
            return b.MustAnswerEval(items=[
                b.MustAnswerItem(item=MUST[0], answered=True,
                                 quote="Proxmox VE 8.2 was released on 24 April 2024"),
                # Zitat steht im Text, der Satz traegt aber keine Quellenmarke
                b.MustAnswerItem(item=MUST[1], answered=True,
                                 quote="BSI published SYS.1.5 edition 2022 in February 2022 and it requires hypervisor hardening."),
                b.MustAnswerItem(item=MUST[2], answered=True,
                                 quote="The Data Act applies from 12 September 2025 to data holders in the EU"),
                # Zitat erfunden
                b.MustAnswerItem(item=MUST[3], answered=True,
                                 quote="Licence costs are 350 euro per socket per year"),
            ])
        items = b.must_answer_scores(REPORT, MUST, chat=chat)
        by = {i["item"]: i for i in items}
        assert by[MUST[0]]["answered"] is True and by[MUST[0]]["quote"]
        assert by[MUST[1]]["answered"] is False and "no citation" in by[MUST[1]]["reason"]
        assert by[MUST[2]]["answered"] is True
        assert by[MUST[3]]["answered"] is False and "not in the dossier" in by[MUST[3]]["reason"]
        assert b.answered_share(items) == 0.5

    def test_model_failure_yields_all_unanswered(self):
        def chat(**kw):
            raise RuntimeError("down")
        items = b.must_answer_scores(REPORT, MUST, chat=chat)
        assert len(items) == 4 and not any(i["answered"] for i in items)
        assert b.answered_share(items) == 0.0

    def test_empty_must_answer(self):
        assert b.must_answer_scores(REPORT, [], chat=lambda **kw: None) == []
        assert b.answered_share([]) is None

    def test_not_answered_verdict_is_kept(self):
        chat = lambda **kw: b.MustAnswerEval(items=[b.MustAnswerItem(item=MUST[0], answered=False, quote="")])
        items = b.must_answer_scores(REPORT, [MUST[0]], chat=chat)
        assert items[0]["answered"] is False and items[0]["reason"] == "not answered"


class TestPromptBlocks:
    def test_brief_block_lists_the_points_in_order(self):
        blk = b.brief_block(_fake_brief())
        assert "MUST ANSWER" in blk and "  1. Which stacks" in blk and "  3. Does the EU Data Act" in blk
        assert "Reader: IT manager" in blk and "Constraints: Germany; no VS-NfD data" in blk

    def test_checklist_empty_without_points(self):
        assert b.must_answer_checklist([]) == ""
        assert "MUST-ANSWER checklist" in b.must_answer_checklist(["A?"])
