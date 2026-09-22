"""Review-Agent (Test 2026-09-22): die Beleg-Regeln ohne Modell und ohne DB."""
from pipeline.review_agent import (FigureVerdict, evidence_in_source, sentence_with, verify_verdict)

SRC = ("OneWeb is based on a constellation of satellites in low earth orbit, positioned approximately "
       "1 000 kilometres from earth. Le 12 juin 2026 à 23 heures, les équipes … Seventy percent said "
       "they’re using it for search.")


def test_verbatim_quote_is_found_despite_whitespace_quotes_and_case():
    assert evidence_in_source("positioned approximately 1 000 kilometres", SRC)
    assert evidence_in_source("SEVENTY PERCENT said they're using it", SRC)      # ’ vs '
    assert evidence_in_source("  positioned   approximately 1 000 kilometres.", SRC)


def test_paraphrase_or_translation_is_not_verbatim():
    assert not evidence_in_source("positioned about 1,000 km from earth", SRC)
    assert not evidence_in_source("11:00 PM on June 12, 2026", SRC)
    assert not evidence_in_source("2026", SRC)                                    # zu kurz


def test_verdict_needs_support_plus_verbatim_evidence():
    ok, why = verify_verdict(FigureVerdict(supported=True, evidence="approximately 1 000 kilometres", form="format"), SRC)
    assert ok and why == "format"
    ok, why = verify_verdict(FigureVerdict(supported=True, evidence="about 1,000 km", form="format"), SRC)
    assert not ok and "verbatim" in why
    ok, why = verify_verdict(FigureVerdict(supported=False, evidence="", form="not-found"), SRC)
    assert not ok and "not supported" in why
    ok, why = verify_verdict(FigureVerdict(supported=True, evidence="", form="same"), SRC)
    assert not ok and "without evidence" in why
    ok, _ = verify_verdict(None, SRC)
    assert not ok


def test_evidence_without_digits_counts_only_for_number_word_forms():
    ok, _ = verify_verdict(FigureVerdict(supported=True, evidence="Seventy percent said they’re using it", form="number-word"), SRC)
    assert ok
    ok, why = verify_verdict(FigureVerdict(supported=True, evidence="Seventy percent said they’re using it", form="same"), SRC)
    assert not ok and "no figure" in why


def test_sentence_with_token_picks_the_carrying_sentence():
    body = "First sentence has nothing. The plant makes 20,000 tonnes a year. Last one."
    assert sentence_with(body, "20,000") == "The plant makes 20,000 tonnes a year."
    assert sentence_with(body, "999").startswith("First sentence")


# --- Namen (Erweiterung 2026-09-22) ---------------------------------------
from pipeline.review_agent import (NameVerdict, name_tokens_in_source, romanisation_matches,  # noqa: E402
                                   titles_not_in_source, verify_name_verdict)

SRC_DE = ("Sweeneys Konzern wäre betroffen vom Kids Act, den Kommissions-Präsidentin Urlula von der "
          "Leyen und Digital-Kommissarin Henna Virkkunen vorgestellt haben.")
SRC_UK = "Der Vorschlag sei bei Gesprächen mit Chinas Vize-Ministerpräsident He Lifeng unterbreitet worden."
SRC_ROLE = "'What climate security means now' - Foreign Secretary at New York Climate Week."
SRC_SURNAME = "Badenoch has pledged that a Conservative government would bring back tax-free shopping."


class TestNameTokens:
    def test_typo_in_the_source_given_name_still_counts(self):
        assert name_tokens_in_source("Ursula von der Leyen", SRC_DE) == (True, [])

    def test_title_words_are_not_part_of_the_identity(self):
        # Artikel: "Chinese Vice Premier He Lifeng" — Quelle: "Vize-Ministerpräsident He Lifeng"
        assert name_tokens_in_source("Premier He", SRC_UK)[0]
        assert titles_not_in_source("Premier He", SRC_UK) == ["Premier"]

    def test_a_short_surname_must_match_as_a_word_not_inside_another(self):
        # "He" darf nicht in "Sicherheit" treffen
        assert not name_tokens_in_source("Premier He", "Gespräche über KI-Sicherheit in New York.")[0]

    def test_missing_given_name_is_reported(self):
        assert name_tokens_in_source("Kemi Badenoch", SRC_SURNAME) == (False, ["Kemi"])

    def test_a_misspelled_surname_is_a_defect_of_the_article(self):
        ok, missing = name_tokens_in_source("Kerstin Papfuss", "Founded by CEO Dr. Kerstin Papenfuss and CTO Mark Hammond.")
        assert not ok and missing == ["Papfuss"]


class TestNameVerdict:
    def test_role_only_is_a_hallucinated_name(self):
        v = NameVerdict(status="role_only", evidence="the Foreign Secretary of the United Kingdom",
                        source_form="Foreign Secretary")
        assert verify_name_verdict(v, "David Lammy", SRC_ROLE) == (False, "role_only")

    def test_surname_only_wins_over_the_models_label(self):
        v = NameVerdict(status="named", evidence="Badenoch has pledged", source_form="Badenoch")
        assert verify_name_verdict(v, "Kemi Badenoch", SRC_SURNAME) == (False, "surname_only")

    def test_all_tokens_present_publishes_even_with_a_source_typo(self):
        v = NameVerdict(status="named", evidence="Kommissions-Präsidentin Urlula von der Leyen",
                        source_form="Urlula von der Leyen")
        assert verify_name_verdict(v, "Ursula von der Leyen", SRC_DE) == (True, "named")

    def test_model_veto_holds_even_when_tokens_match(self):
        v = NameVerdict(status="absent", evidence="", source_form="")
        assert verify_name_verdict(v, "Ursula von der Leyen", SRC_DE) == (False, "absent")

    def test_evidence_must_be_verbatim(self):
        v = NameVerdict(status="named", evidence="paraphrase that is not in the source", source_form="")
        assert verify_name_verdict(v, "Kerstin Papfuss", "Founded by CEO Dr. Kerstin Papenfuss.")[1] == "misspelled"


class TestRomanisation:
    def test_blind_romanisation_confirms_a_transliteration(self):
        assert romanisation_matches("Hisaaki Kato", "Katō Hisaaki")
        assert romanisation_matches("Pan Gang", "Pan Gang")
        assert romanisation_matches("Ursula von der Leyen", "Ursula von der Leyen")

    def test_a_different_person_is_not_confirmed(self):
        assert not romanisation_matches("Mark Schneider", "Philip Navratil")
        assert not romanisation_matches("John McIntyre", "Dzhona Makintayr")

    def test_empty_romanisation_never_confirms(self):
        assert not romanisation_matches("Mark Schneider", "")


# --- Reparatur (Stufe 1, 2026-09-22) --------------------------------------
from pipeline.review_agent import name_shaped, proposals_for, repair_name, repairs_for  # noqa: E402


class TestNameShape:
    def test_a_name_looks_like_a_name(self):
        assert all(map(name_shaped, ["Badenoch", "Kerstin Papenfuss", "He Lifeng", "von der Leyen",
                                     "Le Maire", "Christophe Périllat"]))

    def test_a_handle_a_number_or_a_lowercase_blob_is_not_a_name(self):
        # gemessener Fall 22.09.: Quellform „arnegiacomo" kam aus einer Repo-URL
        assert not any(map(name_shaped, ["arnegiacomo", "Team 42", "a2 Milk", "", "der",
                                         "john@example.com", "Урсула фон дер Ляєн"]))


class TestRepair:
    def test_the_added_given_name_is_replaced_everywhere(self):
        body = "Kemi Badenoch stated it. Later Kemi Badenoch repeated it."
        assert repair_name(body, "Kemi Badenoch", "Badenoch") == "Badenoch stated it. Later Badenoch repeated it."

    def test_nothing_to_replace_returns_none(self):
        assert repair_name("A text without the name.", "Kemi Badenoch", "Badenoch") is None
        assert repair_name("Badenoch stated it.", "Badenoch", "Badenoch") is None

    def _item(self, kind, name, form):
        return {"names": [{"ok": False, "kind": kind, "name": name, "source_form": form}], "figures": []}

    def test_only_surname_only_is_repaired_automatically(self):
        assert repairs_for(self._item("surname_only", "Kemi Badenoch", "Badenoch"))
        # Schreibweisen bleiben beim Menschen: welche Seite stimmt, ist ohne Weltwissen offen
        assert repairs_for(self._item("misspelled", "Kerstin Papfuss", "Kerstin Papenfuss")) == []
        assert repairs_for(self._item("role_only", "David Lammy", "Foreign Secretary")) == []

    def test_a_repair_never_drops_the_surname(self):
        # gemessener Fall: Quelle nennt ihn nur „Dario" — daraus darf kein Artikelname werden
        assert repairs_for(self._item("surname_only", "Dario Amodei", "Dario")) == []

    def test_a_handle_as_source_form_is_refused(self):
        assert repairs_for(self._item("surname_only", "Arne Giacomo", "arnegiacomo")) == []

    def test_unrepairable_findings_become_proposals(self):
        item = self._item("misspelled", "Kerstin Papfuss", "Kerstin Papenfuss")
        item["figures"] = [{"ok": False, "token": "20,000"}]
        kinds = {p["kind"] for p in proposals_for(item)}
        assert kinds == {"spelling", "drop_sentence"}


# --- Nachtlauf (Stage 11, 2026-09-22) -------------------------------------
class TestNightlyStage:
    def _cycle(self) -> str:
        from pathlib import Path
        return (Path(__file__).resolve().parent.parent / "scripts" / "scheduled_cycle.sh").read_text()

    def test_stage_11_runs_after_the_judge_and_can_be_switched_off(self):
        s = self._cycle()
        assert s.index("# <<< Stage 10 <<<") < s.index("# >>> Stage 11")
        assert 'REVIEW_AGENT:-1' in s and 'REVIEW_AGENT_APPLY:-1' in s
        # eigener Kollisionswächter, damit ein fremder GPU-Job nicht überfahren wird
        assert "gpu_guard_wait scheduled_cycle-agent" in s
        # der Handover gehört dem Agenten, nicht dem Shell-Skript
        assert "--handover" in s
        assert "agent=${RCA:--}" in s      # Exit-Code steht in der end-Zeile

    def test_the_morning_mail_reports_the_agent(self):
        from pathlib import Path
        s = (Path(__file__).resolve().parent.parent / "scripts" / "review_notify.py").read_text()
        assert "def agent_stats()" in s and "_agent_line(agent)" in s
        # eine stale Datei darf nicht aussehen, als sei der Lauf von heute Nacht
        block = s[s.index("def agent_stats()"):s.index("def _agent_line")]
        assert "24 * 3600" in block


class TestAgentLine:
    def test_the_line_names_what_was_settled_and_what_is_left(self):
        import importlib.util
        from pathlib import Path
        spec = importlib.util.spec_from_file_location(
            "rn", Path(__file__).resolve().parent.parent / "scripts" / "review_notify.py")
        rn = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(rn)
        line = rn._agent_line({
            "model": "./models/gemma.gguf", "checked": 65, "equivalent": 0, "repaired": 15,
            "human": 50, "published": 15, "dry_run": False,
            "items": [{"names": [{"ok": False, "kind": "role_only"},
                                 {"ok": False, "kind": "surname_only"},
                                 {"ok": True, "kind": "named"}]}],
        })
        assert "65 held drafts checked" in line and "15 repaired" in line
        assert "15 published" in line
        assert "role_only=1" in line and "surname_only=1" in line and "named" not in line

    def test_a_dry_run_says_it_wrote_nothing(self):
        import importlib.util
        from pathlib import Path
        spec = importlib.util.spec_from_file_location(
            "rn2", Path(__file__).resolve().parent.parent / "scripts" / "review_notify.py")
        rn = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(rn)
        line = rn._agent_line({"model": "m", "checked": 3, "equivalent": 1, "repaired": 0,
                               "human": 2, "published": 0, "dry_run": True, "items": []})
        assert "no writes" in line
