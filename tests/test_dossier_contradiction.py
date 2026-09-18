"""Widerspruchs-Gate (Stufe 4, 2026-09-19): datacenter-virtualization v2/v4 —
Kurzfassung „Proxmox VE is the leading candidate", zwei Abschnitte spaeter
„the evidence fails to support a definitive technical recommendation …
Proxmox VE". Der Leser fand es, der Ganzdokument-Neuwurf liess es stehen."""
from pipeline import dossier_structure as ds
from scripts import corpus_research as cr

SUMMARY = ("Proxmox VE is the leading candidate for the firm's virtualization stack after the "
           "VMware licensing change [[T1]]. The vSphere 8 end of general support falls on "
           "11 October 2027 [[T2]]. The EU Data Act applies to the firm's hosting service [[T3]].")
UNSUPPORTED = ("The evidence fails to support a definitive technical recommendation for a single "
               "virtualization stack; Proxmox VE, Hyper-V and OpenStack each have documented "
               "trade-offs [[T1]].")


def _doc(unsupported=UNSUPPORTED, watch="- Watch the Broadcom licensing terms [[T2]]."):
    return (f"# Dossier\n\n## Decision summary\n\n{SUMMARY}\n\n## What is moving\n\nText.\n\n"
            f"## What the evidence does not support\n\n{unsupported}\n\n"
            f"## Decision points and watch items\n\n{watch}\n\n## Open questions and limits\n\nOpen.\n")


class TestMechanicalGate:
    def test_the_v4_pattern_is_caught(self):
        f = ds.contradiction_findings(_doc(), "en")
        assert len(f) == 1
        assert f[0]["section"] == "unsupported" and f[0]["names"] == ["Proxmox VE"]
        assert "leading candidate" in f[0]["text"] and "fails to support" in f[0]["text"]
        assert f[0]["source"] == "mechanical"

    def test_a_limitation_about_another_matter_is_no_contradiction(self):
        other = "The evidence does not date the Broadcom price list for vSphere 8 [[T2]]."
        assert ds.contradiction_findings(_doc(unsupported=other), "en") == []

    def test_a_negated_sentence_without_a_shared_content_word_is_ignored(self):
        other = "No source names Proxmox VE's headquarters [[T1]]."
        assert ds.contradiction_findings(_doc(unsupported=other), "en") == []

    def test_decision_points_are_checked_too(self):
        watch = ("- The evidence cannot support Proxmox VE as the leading candidate for the "
                 "virtualization stack until the firm tests it [[T1]].")
        f = ds.contradiction_findings(_doc(unsupported="Nothing.", watch=watch), "en")
        assert len(f) == 1 and f[0]["section"] == "watch"

    def test_no_summary_no_findings(self):
        assert ds.contradiction_findings("## What is moving\n\nx\n", "en") == []


class TestReaderMapping:
    def test_coherence_and_contradict_findings_map_to_the_gate(self):
        review = {"answers_question": False, "overall": "x", "findings": [
            {"section": "What the evidence does not support", "kind": "coherence", "severity": "major",
             "passage": "fails to support", "issue": "Summary recommends Proxmox, this section denies it.",
             "suggestion": "Align both."},
            {"section": "Decision summary", "kind": "missing", "severity": "major",
             "passage": "", "issue": "No cost structure.", "suggestion": "Add it."},
            {"section": "Decision points and watch items", "kind": "other", "severity": "minor",
             "passage": "", "issue": "This contradicts the summary.", "suggestion": "Fix."}]}
        f = ds.contradiction_from_reader(review, "en")
        assert [x["section"] for x in f] == ["unsupported", "watch"]
        assert all(x["kind"] == "contradiction" and x["source"] == "reader" for x in f)
        rest = cr.without_contradictions(review)
        assert [x["kind"] for x in rest["findings"]] == ["missing"]
        assert cr._is_contradiction_finding(review["findings"][0])
        assert not cr._is_contradiction_finding(review["findings"][1])

    def test_a_reader_section_naming_the_summary_defaults_to_unsupported(self):
        review = {"findings": [{"section": "Decision summary", "kind": "coherence",
                                "severity": "major", "passage": "", "issue": "x", "suggestion": ""}]}
        assert ds.contradiction_from_reader(review, "en")[0]["section"] == "unsupported"


class TestSectionSurgery:
    def test_span_and_replace_keep_the_rest_intact(self):
        doc = _doc()
        s, e = ds.section_span(doc, "unsupported", "en")
        assert doc[s:].startswith("## What the evidence does not support")
        assert doc[s:e].strip().endswith("[[T1]].")
        out = ds.replace_section(doc, "unsupported",
                                 "## What the evidence does not support\n\nThe evidence supports Proxmox VE only "
                                 "for unclassified workloads [[T1]].", "en")
        assert "fails to support" not in out and "## Decision points and watch items" in out
        assert out.count("## What the evidence does not support") == 1
        assert "Text.\n\n## What the evidence" in out
        assert ds.contradiction_findings(out, "en") == []
        assert ds.replace_section(doc, "options", "## Options\n\nx", "en") == doc

    def test_section_key_for(self):
        assert ds.section_key_for("What the evidence does not support") == "unsupported"
        assert ds.section_key_for("3. Decision points and watch items") == "watch"
        assert ds.section_key_for("Executive overview") is None


class TestTargetedRewrite:
    def test_only_the_named_sections_are_rewritten(self, monkeypatch):
        calls = []

        def fake_chat(*, model, system, prompt, **kw):
            calls.append(system)
            if '"## Decision summary"' in system:
                return ("## Decision summary\n\nProxmox VE is one of three documented candidates for the "
                        "virtualization stack [[T1]]. The vSphere 8 end of general support falls on "
                        "11 October 2027 [[T2]]. The EU Data Act applies to the firm's hosting service [[T3]].\n")
            return ("## What the evidence does not support\n\nThe evidence does not rank the three "
                    "candidates; each has documented trade-offs [[T1]].\n")
        monkeypatch.setattr(cr.llamacpp_client, "chat", fake_chat)
        doc = _doc()
        contra = ds.contradiction_findings(doc, "en")
        directive = "\n".join(c["text"] for c in contra)
        out = cr.rewrite_sections(doc, ["decision", "unsupported"], directive, "SYS", "PROMPT", "en",
                                  {"temperature": 0.3})
        assert len(calls) == 2 and all("CONTRADICTION" in s and "FINDINGS" in s for s in calls)
        assert "leading candidate" not in out and "fails to support" not in out
        assert "## What is moving\n\nText." in out and "## Open questions and limits" in out
        assert ds.contradiction_findings(out, "en") == []

    def test_a_failed_or_empty_call_keeps_the_section(self, monkeypatch):
        monkeypatch.setattr(cr.llamacpp_client, "chat", lambda **kw: "## Decision summary\n\n")
        doc = _doc()
        assert cr.rewrite_sections(doc, ["decision"], "x", "S", "P", "en", {}) == doc

        def boom(**kw):
            raise RuntimeError("down")
        monkeypatch.setattr(cr.llamacpp_client, "chat", boom)
        assert cr.rewrite_sections(doc, ["decision"], "x", "S", "P", "en", {}) == doc
