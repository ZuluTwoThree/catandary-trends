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
