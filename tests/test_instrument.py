

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
