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


class TestHandoverWiring:
    """Der Nachtlauf-Pfad muss importierbar sein, BEVOR er nachts läuft.

    Am 23.09. brach Stage 11 sofort ab: `NameError: _llama_unit_active is not
    defined` — eine Patch-Ersetzung hatte still nichts getroffen, und kein Test
    fasste den --handover-Zweig an (`--help` läuft ja daran vorbei). Dieser Test
    lädt das CLI-Modul und prüft, dass jeder Name, den der Zweig aufruft, auch
    existiert."""

    def _cli(self):
        import importlib.util
        from pathlib import Path
        path = Path(__file__).resolve().parent.parent / "scripts" / "review_agent.py"
        spec = importlib.util.spec_from_file_location("review_agent_cli", path)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m

    def test_every_name_the_handover_branch_calls_exists(self):
        import ast
        from pathlib import Path
        m = self._cli()
        src = (Path(__file__).resolve().parent.parent / "scripts" / "review_agent.py").read_text()
        tree = ast.parse(src)
        main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main")
        called = {n.func.id for n in ast.walk(main)
                  if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        import builtins
        for name in sorted(called):
            if hasattr(builtins, name):
                continue                      # int(), print(), … kommen nicht aus dem Modul
            assert hasattr(m, name), f"main() ruft {name}(), das Modul kennt es nicht"
        assert hasattr(m, "llama_unit_active") and hasattr(m, "restore_resting_server")

    def test_the_helpers_live_in_the_pipeline_module(self):
        from pipeline import review_agent as ra
        assert callable(ra.llama_unit_active) and callable(ra.restore_resting_server)


class TestCheckDraftFlow:
    """check_draft muss BEIDE Prüfungen fahren — Zahlen und Namen.

    Am 23.09. fiel auf: beim Einbau der Namensprüfung war die Zahlen-Schleife aus
    check_draft verschwunden. Der Agent meldete für jeden reinen Zahlen-Hold
    „no gate objection found", prüfte also nichts mehr — und kein Test merkte es,
    weil alle nur reine Funktionen abdeckten. Dieser Test fährt check_draft mit
    einem Attrappen-Modell und prüft den Ablauf."""

    # >= 60 Woerter, sonst schlaegt der Garbage-Guard („too_short") vor den Gates zu
    BODY = ("The plant makes 20,000 tonnes a year in its northern works. "
            "The site employs two hundred people and supplies customers across the region. "
            "A second line is planned for the coming season and a rail link is under review "
            "by the local authority, which has promised a decision before the winter break. "
            "Management says the expansion depends on demand from the construction sector, "
            "where order books have been thinner than in previous seasons.")
    SRC = "Die Anlage stellt 20 000 Tonnen pro Jahr in ihrem noerdlichen Werk her."

    def _draft(self, body=None):
        return {"id": 1, "raw_entry_id": 42, "title_en": "T", "source_name": "S",
                "primary_vertical": "TECH", "created_at": "2026-09-23",
                "body_en": body or self.BODY}

    def _patch(self, monkeypatch, *, fig_ok=True, name_status="named", src=None):
        from pipeline import review_agent as ra
        src = src or self.SRC
        monkeypatch.setattr(ra, "ask_model", lambda *a, **k: ra.FigureVerdict(
            supported=fig_ok,
            evidence="stellt 20 000 Tonnen pro Jahr" if fig_ok else "",
            form="format" if fig_ok else "not-found"))
        monkeypatch.setattr(ra, "ask_model_name", lambda *a, **k: ra.NameVerdict(
            status=name_status, evidence="Badenoch eroeffnete sie", source_form="Badenoch"))
        monkeypatch.setattr("pipeline.auto_publisher._source_text", lambda _id: src)

    def test_a_figure_hold_is_actually_checked(self, monkeypatch):
        from pipeline import review_agent as ra
        self._patch(monkeypatch)
        out = ra.check_draft(self._draft(), "m")
        assert out["figures"], "die Zahlen-Schleife lief nicht"
        assert out["figures"][0]["token"] == "20,000" and out["figures"][0]["ok"]
        assert out["decision"] == "equivalent"

    def test_an_unsupported_figure_keeps_the_draft(self, monkeypatch):
        from pipeline import review_agent as ra
        self._patch(monkeypatch, fig_ok=False)
        out = ra.check_draft(self._draft(), "m")
        assert out["decision"] == "human" and "not supported" in out["why"]
        # proposals setzt erst run(); check_draft liefert den Befund, aus dem sie entstehen
        from pipeline.review_agent import proposals_for
        assert any(p["kind"] == "drop_sentence" for p in proposals_for(out))

    def test_a_name_hold_is_decided_before_the_figures(self, monkeypatch):
        from pipeline import review_agent as ra
        body = self.BODY + " Kemi Badenoch opened it."
        self._patch(monkeypatch, src=self.SRC + " Badenoch eroeffnete es.")
        out = ra.check_draft(self._draft(body), "m")
        assert out["names"] and out["names"][0]["kind"] == "surname_only"
        assert out["decision"] == "repaired" or "Nachnamen" in out["why"]


class TestEvidenceSupportsToken:
    """Ein Zitat mit IRGENDEINER Zahl ist kein Beleg für DIESE Zahl — und die vom
    Modell genannte Form darf das nicht entscheiden.

    Gemessen 23.09.: das 8B belegte das Jahr „2026" (aus „Media Study 2026") mit
    „59 % der Bevölkerung ab 14 Jahren nutzen zumindest gelegentlich KI-Tools" —
    wörtlich aus der Quelle, mit Ziffern, ohne die Angabe. Kam die Ziffernprüfung
    nur für die Form „same", nannte dasselbe Modell die Fundstelle „number-word"."""

    def test_a_quote_without_the_figure_is_refused_whatever_the_form_says(self):
        from pipeline.review_agent import evidence_supports_token as f
        q = "59 % der Bevölkerung ab 14 Jahren nutzen zumindest gelegentlich KI-Tools"
        for form in ("same", "format", "number-word", "rounding", "range", "date"):
            assert not f("2026", q, form), f"Form {form} darf die Prüfung nicht aushebeln"

    def test_the_same_value_in_another_notation_passes(self):
        from pipeline.review_agent import evidence_supports_token as f
        assert f("20,000", "Die Anlage stellt 20 000 Tonnen her", "format")
        assert f("21", "gestern (21.9.2026) feierlich eröffnet", "date")

    def test_number_words_and_other_scripts_pass(self):
        from pipeline.review_agent import evidence_supports_token as f
        assert f("70%", "Seventy percent said they use it", "number-word")
        assert f("207", "税引き後純利益は5.8％減の2億750万NZD", "rounding")   # nicht nachrechenbar

    def test_rounding_and_ranges_are_computed_not_believed(self):
        from pipeline.review_agent import evidence_supports_token as f
        assert f("2000", "18 mois pour passer de 2 000 à 20 000 utilisateurs", "same")
        assert f("11200", "the number behind bars doubled to over 11,200", "same")
        assert f("60", "eine Rendite von 61,5 Prozent", "rounding")          # 2,5 % Abstand
        # abgeleitet, nicht belegt: „through 2036" aus „over the next 10 years"
        assert not f("2036", "over the next 10 years, the minister said on September 15, 2026", "range")

    def test_a_token_without_digits_is_left_to_the_other_checks(self):
        from pipeline.review_agent import evidence_supports_token as f
        assert f("", "irgendein Satz", "same")
