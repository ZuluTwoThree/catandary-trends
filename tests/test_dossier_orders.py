"""Auftragszettel (dossier_orders): Statusfluss und Invarianten.

Die harte Invariante ist der Owner-Kontrakt: ein Lauf endet IMMER in 'review',
nie in 'done' — 'done' erreicht nur approve() (die Owner-Abnahme). Und ein
Auftrag kann nie doppelt laufen: mark_running gewinnt genau einmal.
"""
import pytest

from pipeline import dossier_orders as m
from pipeline.db import get_connection


@pytest.fixture(autouse=True)
def fresh_tables():
    with get_connection() as conn:
        conn.execute("DROP TABLE IF EXISTS dossier_orders")
        conn.execute("DROP TABLE IF EXISTS dossiers")
    m.ensure_schema()
    yield


class TestCreateAndList:
    def test_create_defaults_slug_from_topic(self):
        oid = m.create_order("Solid-State Batteries")
        o = m.get_order(oid)
        assert o["slug"] == "solid-state-batteries"
        assert o["status"] == "queued"
        assert o["question"] is None

    def test_explicit_slug_and_question(self):
        oid = m.create_order("topic", slug="Meine Serie!", question="  Q?  ")
        o = m.get_order(oid)
        assert o["slug"] == "meine-serie"
        assert o["question"] == "Q?"

    def test_unknown_params_are_dropped(self):
        oid = m.create_order("t", params={"steps": 9, "rm_rf": "/", "quant": False})
        o = m.get_order(oid)
        assert o["params"] == {"steps": 9, "quant": False}

    def test_empty_topic_rejected(self):
        with pytest.raises(ValueError):
            m.create_order("   ")

    def test_queued_orders_oldest_first(self):
        a = m.create_order("a")
        b = m.create_order("b")
        m.cancel(b)
        c = m.create_order("c")
        assert [o["id"] for o in m.queued_orders()] == [a, c]

    def test_list_filters_by_status(self):
        a = m.create_order("a")
        m.create_order("b")
        m.cancel(a)
        assert [o["id"] for o in m.list_orders(status="cancelled")] == [a]


class TestStatusFlow:
    def test_happy_path_ends_in_review_never_done(self):
        oid = m.create_order("t")
        assert m.mark_running(oid)
        assert m.mark_review(oid, 3, {"ok": True, "findings": []})
        o = m.get_order(oid)
        assert o["status"] == "review"          # nie automatisch 'done'
        assert o["dossier_version"] == 3
        assert o["check"] == {"ok": True, "findings": []}

    def test_owner_approval_is_the_only_path_to_done(self):
        oid = m.create_order("t")
        assert not m.approve(oid)               # queued → done: verboten
        m.mark_running(oid)
        assert not m.approve(oid)               # running → done: verboten
        m.mark_review(oid, 1, {})
        assert m.approve(oid)
        assert m.get_order(oid)["status"] == "done"

    def test_mark_running_wins_exactly_once(self):
        oid = m.create_order("t")
        assert m.mark_running(oid)
        assert not m.mark_running(oid)          # Doppel-Lauf ausgeschlossen

    def test_cancel_only_from_queued(self):
        oid = m.create_order("t")
        m.mark_running(oid)
        assert not m.cancel(oid)

    def test_failed_and_requeue(self):
        oid = m.create_order("t")
        m.mark_running(oid)
        assert m.mark_failed(oid, "boom")
        assert m.get_order(oid)["error"] == "boom"
        assert m.requeue(oid)
        assert m.get_order(oid)["status"] == "queued"
        # und der nächste Lauf räumt den alten Fehler weg
        m.mark_running(oid)
        assert m.get_order(oid)["error"] is None


class TestSlugify:
    def test_umlauts_and_specials(self):
        assert m.slugify("Präzisions-Fermentation (DACH)") == \
            "prazisions-fermentation-dach"

    def test_never_empty(self):
        assert m.slugify("???") == "dossier"


def test_dr_and_cpc_survive_the_param_filter():
    from pipeline import dossier_orders as o
    assert o._clean_params({"dr": False, "cpc": "H01M4/5825", "bogus": 1}) == {"dr": False, "cpc": "H01M4/5825"}


class TestCheckpointTransitions:
    """Stufe 1 (2026-09-19): Intake und Owner-Checkpoint."""

    BRIEF = {"question_type": "regulatory", "must_answer": ["A?", "B?", "C?"],
             "artefact": "dossier", "decision": "d", "reader": "r", "constraints": [],
             "is_question": True, "rejection_reason": ""}
    PLAN = {"title": "p", "steps": [{"title": "s", "query": "q"}], "landscape": []}

    def test_running_to_awaiting_stores_the_artefacts(self):
        oid = m.create_order("t", question="What moves?")
        assert not m.mark_awaiting(oid, self.BRIEF, None, self.PLAN)   # queued → nein
        m.mark_running(oid)
        assert m.mark_awaiting(oid, self.BRIEF, {"field": "f"}, self.PLAN)
        o = m.get_order(oid)
        assert o["status"] == "awaiting_confirmation"
        assert o["brief"] == self.BRIEF and o["plan"] == self.PLAN and o["profile"] == {"field": "f"}
        assert o["confirmed_at"] is None and o["owner_note"] is None

    def test_confirm_returns_to_queued_with_note(self):
        oid = m.create_order("t", question="What moves?")
        assert not m.confirm(oid)                       # nur aus awaiting_confirmation
        m.mark_running(oid)
        m.mark_awaiting(oid, self.BRIEF, None, self.PLAN)
        assert m.confirm(oid, "  the plan is about IT service firms,   not virtualization ")
        o = m.get_order(oid)
        assert o["status"] == "queued" and o["confirmed_at"] is not None
        assert o["owner_note"] == "the plan is about IT service firms, not virtualization"
        assert o["brief"] == self.BRIEF                 # Artefakte bleiben sichtbar
        # die Korrektur haengt am Lauf-Text, nicht am Fragefeld
        assert o["question"] == "What moves?"
        assert m.effective_question(o, "default") == \
            "What moves?\n\nOwner correction: the plan is about IT service firms, not virtualization"
        assert m.mark_running(oid)                      # naechster Worker-Start

    def test_confirm_without_note(self):
        oid = m.create_order("t")
        m.mark_running(oid)
        m.mark_awaiting(oid, self.BRIEF, None, self.PLAN)
        assert m.confirm(oid, "")
        o = m.get_order(oid)
        assert o["owner_note"] is None and o["confirmed_at"] is not None
        assert m.effective_question(o, "default question") == "default question"

    def test_reject_intake_is_failed_with_reason(self):
        oid = m.create_order("t", question="The purpose of the dossier is a sample.")
        m.mark_running(oid)
        assert m.reject_intake(oid, "no question")
        o = m.get_order(oid)
        assert o["status"] == "failed" and o["error"] == "intake rejected: no question"
        assert m.requeue(oid)

    def test_cancel_from_awaiting(self):
        oid = m.create_order("t")
        m.mark_running(oid)
        m.mark_awaiting(oid, self.BRIEF, None, self.PLAN)
        assert m.cancel(oid)
        assert m.get_order(oid)["status"] == "cancelled"

    def test_store_intake_keeps_status(self):
        oid = m.create_order("t")
        m.mark_running(oid)
        m.store_intake(oid, self.BRIEF, None, self.PLAN)
        o = m.get_order(oid)
        assert o["status"] == "running" and o["brief"] == self.BRIEF

    def test_checkpoint_param_survives_the_filter(self):
        assert m._clean_params({"checkpoint": False}) == {"checkpoint": False}
        assert "awaiting_confirmation" in m.VALID_STATUS
