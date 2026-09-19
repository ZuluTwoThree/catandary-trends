"""Widerspruchs-Gate (Stufe 4, 2026-09-19): datacenter-virtualization v2/v4 —
Kurzfassung „Proxmox VE is the leading candidate", zwei Abschnitte spaeter
„the evidence fails to support a definitive technical recommendation …
Proxmox VE". Der Leser fand es, der Ganzdokument-Neuwurf liess es stehen.

Runde 28 (datacenter v7): „fails to support a definitive recommendation" ist
fuer sich genommen eine SCOPE-Aussage (das Dossier empfiehlt nichts — seit
Runde 19 gewollt). Der echte v4-Fehler war die Kurzfassung, die einen
Kandidaten behauptet, den der Rest dann zuruecknimmt: der Befund bleibt genau
dann, wenn die Kurzfassung selbst empfiehlt. Leser-Befunde der Art `coherence`
zaehlen nur mit benanntem Widerspruch; „does not summarize", „drifts",
„dilutes the focus" (die drei v7-Befunde) sind Fokus-/Drift-Einwaende."""
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


SUMMARY_NO_REC = ("Proxmox VE is one of three documented candidates for the firm's virtualization "
                  "stack after the VMware licensing change [[T1]]. The vSphere 8 end of general support "
                  "falls on 11 October 2027 [[T2]]. The EU Data Act applies to the firm's hosting service [[T3]].")


class TestMechanicalGate:
    def test_the_v4_pattern_is_caught_because_the_summary_recommends(self):
        """„leading candidate" ist eine Empfehlung; der Rest nimmt sie zurueck —
        der Bericht hat zwei Meinungen, das bleibt sperrend."""
        assert ds.summary_recommends(_doc(), "en")
        ex = []
        f = ds.contradiction_findings(_doc(), "en", excluded=ex)
        assert len(f) == 1 and ex == []
        assert f[0]["section"] == "unsupported" and f[0]["names"] == ["Proxmox VE"]
        assert "leading candidate" in f[0]["text"] and "fails to support" in f[0]["text"]
        assert f[0]["source"] == "mechanical"

    def test_the_same_scope_statement_is_excluded_when_the_summary_recommends_nothing(self):
        """v7: „fails to support a definitive recommendation" gegen eine
        Kurzfassung ohne Empfehlung ist eine Aussage ueber den Geltungsbereich."""
        doc = _doc().replace(SUMMARY, SUMMARY_NO_REC)
        assert not ds.summary_recommends(doc, "en")
        ex = []
        assert ds.contradiction_findings(doc, "en", excluded=ex) == []
        assert len(ex) == 1 and ex[0]["why"] == "scope" and ex[0]["source"] == "mechanical"
        assert "Scope-Aussage" in ex[0]["text"]

    def test_is_scope_statement(self):
        yes = ["the corpus does not provide a definitive recommendation on which stack the firm should run",
               "The evidence fails to support a definitive technical recommendation for a single stack",
               "the dossier cannot provide a tailored recommendation for the firm",
               "No source ranks the three candidates; the evidence does not choose between them"]
        no = ["The summary says 'do not deploy it for VS-NfD data', but the decision point says 'Restrict'",
              "The evidence cannot support Proxmox VE as the leading candidate until the firm tests it",
              "does not summarize the decision or the dossier's content",
              "The evidence does not date the Broadcom price list for vSphere 8"]
        assert all(ds.is_scope_statement(t) for t in yes)
        assert not any(ds.is_scope_statement(t) for t in no)

    def test_claim_recommends(self):
        assert ds.claim_recommends("Proxmox VE is the leading candidate for the stack")
        assert ds.claim_recommends("The firm should migrate before October 2027")
        assert not ds.claim_recommends("Proxmox VE is one of three documented candidates")
        assert not ds.claim_recommends("The vSphere 8 end of general support falls on 11 October 2027")

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


V7_READER = {"answers_question": False, "overall": "x", "findings": [
    {"section": "Scout's verdict", "kind": "coherence", "severity": "minor", "passage": "This migration",
     "issue": "The 'Scout's verdict' is a single sentence that does not summarize the decision or the "
              "dossier's content. It focuses on a single technical detail (VDDK). It fails to serve as a summary.",
     "suggestion": "Rewrite the verdict."},
    {"section": "Maturity and position in the cycle", "kind": "coherence", "severity": "minor",
     "passage": "The patent citation graph",
     "issue": "This section focuses heavily on patent statistics and funding signals, which are irrelevant to "
              "the specific question of which stack a small IT firm should run. It drifts into adjacent topics.",
     "suggestion": "Reduce the focus on patent statistics."},
    {"section": "What happens next", "kind": "coherence", "severity": "minor", "passage": "Q2 2026",
     "issue": "The decision points include the EU Data Centre Rating Scheme, which is about energy efficiency. "
              "It is not directly related to the virtualization stack choice. It dilutes the focus.",
     "suggestion": "Tie the decision points to the stack decision."}]}


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

    def test_the_three_v7_focus_findings_are_drift_not_contradictions(self):
        """datacenter v7 (2026-09-19): drei `coherence`-Befunde ohne benannten
        Widerspruch sperrten das Dossier als „Widerspruch noch offen (3)"."""
        ex = []
        assert ds.contradiction_from_reader(V7_READER, "en", excluded=ex) == []
        assert [e["why"] for e in ex] == ["drift", "drift", "drift"]
        assert all(e["source"] == "reader" for e in ex)
        # … und sie bleiben im normalen Leser-Pfad (Ganzdokument-Neuwurf).
        rest = cr.without_contradictions(V7_READER)
        assert len(rest["findings"]) == 3
        assert not any(cr._is_contradiction_finding(f) for f in V7_READER["findings"])

    def test_a_scope_finding_counts_only_when_the_summary_itself_recommends(self):
        f = {"section": "What the evidence does not support", "kind": "coherence", "severity": "major",
             "passage": "cannot provide", "issue": "The dossier admits it does not know the firm's licensing, "
             "yet the question asks for a recommendation; the dossier cannot provide a tailored "
             "recommendation, which contradicts the verdict.", "suggestion": "Say so."}
        review = {"findings": [f]}
        assert ds.reader_contradiction_class(f, False) == "scope"
        assert ds.reader_contradiction_class(f, True) == "contradiction"
        ex = []
        assert ds.contradiction_from_reader(review, "en", _doc().replace(SUMMARY, SUMMARY_NO_REC),
                                            excluded=ex) == []
        assert ex and ex[0]["why"] == "scope"
        assert len(ds.contradiction_from_reader(review, "en", _doc())) == 1
        assert not cr._is_contradiction_finding(f, _doc().replace(SUMMARY, SUMMARY_NO_REC))
        assert cr._is_contradiction_finding(f, _doc())

    def test_reader_contradiction_class(self):
        assert ds.reader_contradiction_class({"kind": "missing", "issue": "No cost structure."}) is None
        assert ds.reader_contradiction_class({"kind": "coherence", "issue": "The date is inconsistent with "
                                              "'What is moving', which says it filed in May."}) == "contradiction"
        assert ds.reader_contradiction_class({"kind": "coherence", "issue": "The section conflates hardware "
                                              "with PQC migration."}) == "drift"
        assert ds.reader_contradiction_class({"kind": "other", "issue": "This contradicts the summary."}) \
            == "contradiction"

    def test_a_reader_section_naming_the_summary_defaults_to_unsupported(self):
        review = {"findings": [{"section": "Decision summary", "kind": "coherence", "severity": "major",
                                "passage": "", "issue": "The summary contradicts the body on the date.",
                                "suggestion": ""}]}
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
