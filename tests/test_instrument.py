

# ---------------------------------------------------------------------------
# Projektion: die Eichung der Feldschätzung
# ---------------------------------------------------------------------------
def test_calibration_beats_the_queue_ladder_on_level():
    """Die Warteschlangen-Leiter schätzt die HÖHE eines Felds systematisch zu
    hoch — das ist der Grund, warum estimate_relevance eine eigene Eichung hat.

    Gemessen an 157 echten Bewertungen (leave-one-out): Leiter MAE 1,06 bei
    +0,82 Verzerrung, lineare Eichung MAE 0,72 bei +0,02. Hier festgehalten als
    Eigenschaft, nicht als Zahl: bei einem Nutzer, der streng bewertet, muss
    die Eichung tiefer liegen als die Leiter.
    """
    from pipeline.instrument import hint_points
    strict_mean = 0.96          # der reale Bestand
    ladder = [hint_points(s) for s in (0.30, 0.20, 0.10, 0.02, -0.05)]
    assert sum(ladder) / len(ladder) > strict_mean, (
        "Leiter muss über einem strengen Nutzer liegen — sonst gäbe es nichts "
        "zu eichen und der Kommentar in relevance_calibration wäre falsch")


def test_estimate_relevance_uses_calibration_when_given():
    """Mit Eichung kommt die lineare Abbildung, ohne die Leiter."""
    import pipeline.instrument as inst

    class FakeConn:
        def execute(self, *a, **k):
            raise AssertionError("darf nicht angefasst werden")

    calls = {}

    def fake_ids(conn, field_key, limit=40_000):
        return [1, 2, 3]

    def fake_scores(conn, direction, ids):
        calls["ids"] = ids
        return {1: 0.30, 2: 0.10, 3: -0.10}

    old_ids, old_sc = inst.field_trend_ids, inst.score_against
    inst.field_trend_ids, inst.score_against = fake_ids, fake_scores
    try:
        # Leiter: 4, 2, 0 -> 2.0
        assert inst.estimate_relevance(FakeConn(), [0.1], "x")["relevance"] == 2.0
        # Eichung points = 0.5 + 2*cos -> 1.1, 0.7, 0.3 -> 0.7
        est = inst.estimate_relevance(FakeConn(), [0.1], "x", calib=(0.5, 2.0))
        assert est["relevance"] == 0.7
        assert est["field_n"] == 3 and est["sampled"] == 3
    finally:
        inst.field_trend_ids, inst.score_against = old_ids, old_sc


def test_estimate_relevance_clamps_to_the_zero_four_scale():
    """Eine Gerade kann aus der Skala laufen; die Punkte dürfen es nicht."""
    import pipeline.instrument as inst

    old_ids, old_sc = inst.field_trend_ids, inst.score_against
    inst.field_trend_ids = lambda conn, fk, limit=40_000: [1, 2]
    inst.score_against = lambda conn, d, ids: {1: 1.0, 2: -1.0}
    try:
        est = inst.estimate_relevance(None, [0.1], "x", calib=(2.0, 9.0))
        assert est["relevance"] == 2.0, "clamp auf [0,4]: (4+0)/2"
    finally:
        inst.field_trend_ids, inst.score_against = old_ids, old_sc


def test_stage_texts_are_english():
    """Produktsprache ist Englisch — die Texte gehen unverändert ins Frontend."""
    from pipeline.instrument import (STAGE_LABEL, STAGE_BAND, curve_position,
                                     merge_maturity)
    assert STAGE_LABEL["volatile"] == "Volatile"
    assert STAGE_BAND["maturing"] == "Consider"
    german = ("Reihe", "Gipfel", "Verlauf", "Feld", "verwertbare", "Streuung")
    for text in (curve_position([])["reason"],
                 merge_maturity({"stage": None, "reason": ""}, None)["note"],
                 merge_maturity({"stage": "maturing", "reason": "x"}, None)["note"],
                 merge_maturity({"stage": "maturing", "reason": "x"}, 3.5)["note"]):
        assert not any(w in text for w in german), text


# ---------------------------------------------------------------------------
# Bestätigung vor dem Neustart
# ---------------------------------------------------------------------------
def test_reset_preview_counts_orphaned_ratings():
    """Die Bestätigung darf NICHT die Zahl der Tafel nennen.

    Nimmt ein Nutzer ein Feld vom Tisch, bleiben dessen Bewertungen in
    signal_relevance stehen und speisen weiter das globale Interessensmodell —
    die Tafel zeigt sie nicht mehr. Real gemessen: Tafel 3, gelöscht 9. Eine
    Bestätigung, die untertreibt, ist schlimmer als gar keine, deshalb holt der
    Dialog die Zahlen vom Server statt sie aus der Tafel zu summieren.

    Hier als SQL-Formtest ohne DB: die Waisen-Zählung muss gegen
    workspace_field korrelieren, nicht gegen die angezeigten Felder.
    """
    import inspect
    from pipeline.instrument import reset_preview
    src = inspect.getsource(reset_preview)
    assert "NOT EXISTS" in src and "workspace_field" in src, (
        "orphaned muss über die Abwesenheit in workspace_field bestimmt werden")
    assert "orphaned" in src and "ratings" in src


def test_reset_preview_runs_before_the_delete():
    """reset_workspace muss den Vorher-Stand mitliefern — sonst kann niemand
    hinterher prüfen, ob die Bestätigung die Wahrheit gesagt hat."""
    import inspect
    from pipeline.instrument import reset_workspace
    src = inspect.getsource(reset_workspace)
    before = src.index("reset_preview(")
    delete = src.index("DELETE FROM signal_relevance")
    assert before < delete, "Vorschau muss VOR dem Löschen gezogen werden"
    assert '"before": before' in src


# ---------------------------------------------------------------------------
# Automatisierung der Relevanzbewertung
# ---------------------------------------------------------------------------
def test_automation_tiers_are_discounted_against_the_measurement():
    """Die angezeigte Genauigkeit muss UNTER der Messreihe liegen.

    Gemessen (docs/instrument_learning_curve.md) auf `search:dairy`:

        Positive   Präzision@50
         3–4          50 %
         5–7          52 %
         8–11         60 %
        12–17         71 %
        18–27         72 %
        28–44         76 %

    Die Simulation ist optimistisch — lexikalische Konzepte sind konsistent,
    menschliches Interesse nicht (reale Anker: 98 Bewertungen AUC 0,700 gegen
    0,86 simuliert). AUTOMATION_TIERS verschiebt deshalb um einen Eimer nach
    unten. Bricht jemand diese Verschiebung, verspricht die Oberfläche etwas,
    das das Werkzeug nicht hält.
    """
    from pipeline.instrument import AUTOMATION_TIERS
    measured = {3: 0.50, 5: 0.52, 8: 0.60, 12: 0.71, 18: 0.72, 28: 0.76, 45: 0.82}
    thresholds = [thr for thr, _ in AUTOMATION_TIERS]
    for thr, shown in AUTOMATION_TIERS:
        assert shown < measured[thr], (
            f"bei {thr} Positiven zeigt die Oberfläche {shown}, gemessen wurde "
            f"{measured[thr]} — der Realanker-Abschlag fehlt")
    assert thresholds == sorted(thresholds)
    assert [a for _, a in AUTOMATION_TIERS] == sorted(a for _, a in AUTOMATION_TIERS)


def test_automation_unlocks_only_above_seventy_percent():
    """Angeboten wird die Automatisierung erst, wenn sie über 70 % trägt."""
    from pipeline.instrument import AUTOMATION_TIERS, AUTOMATION_MIN_POSITIVES
    acc = next(a for thr, a in AUTOMATION_TIERS if thr == AUTOMATION_MIN_POSITIVES)
    assert acc >= 0.70
    below = [a for thr, a in AUTOMATION_TIERS if thr < AUTOMATION_MIN_POSITIVES]
    assert all(a < 0.70 for a in below), "unterhalb der Schwelle darf nichts >=70% sein"


def test_model_ratings_never_train_the_model():
    """Maschinelle Zeilen dürfen nicht ins Training zurücklaufen.

    Sonst träte das Modell gegen die eigenen Ausgaben an — jede Fehleinschätzung
    verstärkte sich und sähe mit jedem Lauf sicherer aus.
    """
    import inspect
    from pipeline.instrument import (relevance_direction, relevance_calibration,
                                     decision_threshold, automation_status,
                                     automate_field)
    for fn in (relevance_direction, relevance_calibration, decision_threshold,
               automation_status):
        assert "by_model" in inspect.getsource(fn), (
            f"{fn.__name__} filtert maschinelle Bewertungen nicht heraus")
    # automate_field schreibt gar keine Bewertungen
    src = inspect.getsource(automate_field)
    assert "INSERT INTO signal_relevance" not in src


def test_decision_threshold_is_learned_not_fixed():
    """Die Relevanzgrenze darf nicht an HINT_THRESHOLD hängen.

    Der erste Bau schwellte die geeichten Punkte bei 3 ab und meldete auf einem
    Feld mit erkennbar richtiger Rangfolge NULL relevante Signale: die
    Kleinste-Quadrate-Gerade staucht bimodale Bewertungen (0/4) auf 0,5–2,7.
    Real nachgestellt: 4.144 Signale, 0 als relevant gemeldet.
    """
    import inspect
    from pipeline.instrument import automate_field, decision_threshold
    src = inspect.getsource(automate_field)
    assert "decision_threshold(" in src
    assert "v[2] >= cut" in src, "gefiltert wird am gelernten Kosinus-Schnitt"
    assert "f1" in inspect.getsource(decision_threshold)
