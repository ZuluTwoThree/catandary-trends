"""Der Advisor (2026-09-14): Speicher, Prompt, deterministische Pruefung und ein
Lauf mit Modell-Stub — Dossier-Katalog geschlossen, Zahlen gegen Dossier +
Profil, Freigabe nur durch einen Menschen."""
from __future__ import annotations

import json

import pytest

from pipeline import advisory as adv


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "t.db"))
    monkeypatch.delenv("OPS_EVENT_ID", raising=False)
    import importlib
    from pipeline import config, db as dbm
    importlib.reload(config)
    importlib.reload(dbm)
    from pipeline import dossier_orders as orders, advisory_store as store
    importlib.reload(orders)
    importlib.reload(store)
    dbm.init_db()
    orders.ensure_schema()
    store.ensure_schema()
    return dbm, store


SOURCES = [{"id": "W1", "kind": "web", "title": "IEA storage review", "url": "https://www.iea.org/x",
            "origin": "", "outlet": "IEA", "date": "2026-03-01", "rank": 0, "fetched": True},
           {"id": "T5", "kind": "article", "title": "Plant story", "url": "https://catandary.de/trends/p",
            "origin": "https://www.energy-storage.news/p", "outlet": "ESN", "date": "2026-05-01", "rank": 2}]
REPORT = ("## Decision summary\n\nLFP took 90% of 108 GW in 2025 [IEA storage review](https://www.iea.org/x).\n\n"
          "## What is moving\n\nA plant of 9 GWh started in 2026 [Plant story](https://www.energy-storage.news/p).\n")


def _seed_dossier(dbm, slug="lfp", version=9):
    with dbm.get_connection() as conn:
        conn.execute("INSERT INTO dossiers (slug, version, topic, question, report_md, result, model) "
                     "VALUES (?, ?, ?, ?, ?, ?, ?)",
                     (slug, version, "LFP cells", "q?", REPORT,
                      json.dumps({"sources": SOURCES, "cited": ["W1", "T5"], "lang": "en"}), "m"))


def test_store_round_trip_and_human_approval(db):
    dbm, store = db
    _seed_dossier(dbm)
    d = store.get_dossier("lfp")
    assert d["version"] == 9 and d["result"]["cited"] == ["W1", "T5"]
    nid = store.create_note("lfp", 9, {"industry": "utilities"}, "Should we build storage?")
    n = store.get_note(nid)
    assert n["status"] == "queued" and n["profile"]["industry"] == "utilities"
    assert store.approve(nid, "owner") is False                  # nicht aus queued
    assert store.mark_running(nid) and store.mark_review(nid, "note", {"ok": True}, "m", 12.0)
    assert store.approve(nid, "owner", "gelesen") is True
    n = store.get_note(nid)
    assert n["status"] == "approved" and n["approved_at"] and n["approved_by"] == "owner"
    assert store.withdraw(nid) and store.get_note(nid)["approved_at"] is None
    with pytest.raises(ValueError):
        store.create_note("lfp", 9, {}, "   ")


def test_prompt_and_checks():
    p = adv.build_prompt("DOSSIER", {"industry": "steel", "size": "2000 staff", "bogus": "x"},
                         "Decide on a 20 MWh battery", "q", "LFP")
    assert "- industry: steel" in p and "bogus" not in p and "<untrusted_dossier>\nDOSSIER" in p
    note = ("### Option 1 — Build\n- Trigger: plant start 2026 [[T5]]\n- Effort: unknown\n"
            "- Who pays: savings of $4.5 million per year\n- Kill criterion: price above $100/kWh in 2027")
    assert adv.unfilled_fields(note) == ["Effort"]
    foreign = adv.figures_not_in_sources(note, "plant start 2026 … $100/kWh", "2000 staff")
    assert "$4.5" in foreign and "2026" not in foreign and "$100" not in foreign
    linked = "price above $100/kWh [Patent term](https://x.org/2701/20110704.html)"
    assert adv.figures_not_in_sources(linked, "$100/kWh", "") == []     # URL-Ziffern zaehlen nicht


def test_run_note_with_a_model_stub(db, monkeypatch):
    dbm, store = db
    _seed_dossier(dbm)
    import scripts.advisory as sa
    import scripts.corpus_research as cr
    from pipeline import llamacpp_client
    nid = store.create_note("lfp", 9, {"industry": "utilities", "geography": "Germany"},
                            "Decide whether to procure 20 MWh of LFP storage by 2027")
    monkeypatch.setattr(sa, "thinking_server", lambda assume_model_up=False: __import__("contextlib").nullcontext())
    monkeypatch.setattr(sa, "ADVISOR_MIN_WORDS", 50)     # der Stub ist kuerzer als eine echte Notiz
    seen = {}

    def chat(model, prompt, system=None, **kw):
        seen["thinking"] = kw.get("enable_thinking")
        seen["prompt"] = prompt
        return ("<think>hmm</think>## Situation\n\nThe client operates in Germany [[client]]; LFP took 90% "
                "of 108 GW in 2025 [[W1]].\n\n### Option 0 — Do nothing\n- Trigger: no external trigger, a standing choice [[W1]]\n"
                "- Time horizon: 2027\n- Effort: no capital, staff time\n- Who pays: nobody\n- Risk: prices rise\n"
                "- Kill criterion: a 9 GWh plant contract in 2026 [[T5]]\n- Against it: exposure\n\n"
                "### Option 1 — Procure\n- Trigger: 9 GWh plant start in 2026 [[T5]]\n- Time horizon: 2027\n"
                "- Effort: comparable 9 GWh plant [[T5]]\n- Who pays: savings\n- Risk: lock-in\n"
                "- Kill criterion: none by 2027\n- Against it: price\n\n## Recommendation\n\nOption 1, medium.\n"
                "\n## Evidence used\n\nW1, T5 [[ZZ9]]\n")

    monkeypatch.setattr(llamacpp_client, "chat", chat)
    monkeypatch.setattr(cr, "reader_review", lambda *a, **k: {"answers_question": True, "overall": "fine",
                                                                 "findings": [{"severity": "minor"}]})
    assert sa.run_note(nid) is True
    n = store.get_note(nid)
    assert n["status"] == "review" and seen["thinking"] is True
    assert "CITATION CATALOG" in seen["prompt"] and "[[W1]]" in seen["prompt"]
    c = n["check"]
    assert c["stripped_citations"] == 1 and c["ok"] is False        # [[ZZ9]] ist kein Katalog-Eintrag
    assert c["reader_ok"] is True and c["unfilled"] == [] and c["foreign_figures"] == []
    assert "[IEA storage review](https://www.iea.org/x)" in n["note_md"]
    assert "<think>" not in n["note_md"]


def test_run_note_retries_without_thinking_and_fails_on_empty_answer(db, monkeypatch):
    dbm, store = db
    _seed_dossier(dbm)
    import scripts.advisory as sa
    from pipeline import llamacpp_client
    nid = store.create_note("lfp", 9, {}, "Decide something")
    monkeypatch.setattr(sa, "thinking_server", lambda assume_model_up=False: __import__("contextlib").nullcontext())
    calls = []
    monkeypatch.setattr(llamacpp_client, "chat", lambda model, prompt, system=None, **kw: calls.append(kw.get("enable_thinking")) or "<think>only thoughts</think>")
    assert sa.run_note(nid) is False
    assert calls == [True, False]                      # zweiter Versuch ohne Denken, dann Abbruch
    n = store.get_note(nid)
    assert n["status"] == "failed" and "empty note" in (n["error"] or "")
