"""Der Lizenz-Auflöser prüft jeden Eintrag genau einmal (#97, 2026-09-09).

Ohne `licence_checked_at` fragte der nächtliche Lauf dieselben ~85 % Nicht-
Offenen jede Nacht neu ab: die Zeilen der Vorbehalts-Quellen bleiben
unverarbeitet, bis der Samstagslauf sie einzieht, und OpenAlex ist seit dem
Umbau ein Kreditdienst. Bei ~254 Einträgen/Tag und `--limit 300` wäre der
ältere Teil des Pools nie an die Reihe gekommen.
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import resolve_open_licence as rol
from pipeline.db import get_connection, init_db, upsert_source


def _seed(name="reserved-src", llm=False, source_type="research"):
    init_db()
    sid = upsert_source(name, f"https://x.example/{name}", source_type, "HEALTH",
                        llm_pipeline=llm)
    with get_connection() as conn:
        conn.execute("UPDATE sources SET llm_pipeline = ? WHERE id = ?", (llm, sid))
    return sid


def _url(tag: str) -> str:
    """Der Test-DB-Pfad ist fest (/tmp/catandary_test_fallback.db) und ueberlebt
    den Lauf — URLs muessen je Lauf eindeutig sein, sonst schlaegt UNIQUE(url)
    beim zweiten pytest-Aufruf zu."""
    return f"https://x.example/{tag}/{uuid.uuid4().hex}"


def _entry(sid, url, **cols):
    keys = ", ".join(cols)
    marks = ", ".join(["?"] * len(cols))
    with get_connection() as conn:
        conn.execute(
            f"INSERT INTO raw_entries (source_id, url, title{', ' + keys if cols else ''}) "
            f"VALUES (?, ?, ?{', ' + marks if cols else ''})",
            (sid, url, "T", *cols.values()))
        row = conn.execute("SELECT id FROM raw_entries WHERE url = ?", (url,)).fetchone()
    return row["id"] if hasattr(row, "keys") else row[0]


class TestCandidateScope:
    def test_fresh_entry_of_a_signal_only_source_is_a_candidate(self):
        sid = _seed("cand-fresh")
        url = _url("a")
        _entry(sid, url)
        assert url in {c["url"] for c in rol.candidates(50)}

    def test_already_checked_entry_is_skipped(self):
        sid = _seed("cand-checked")
        url = _url("b")
        _entry(sid, url, licence_checked_at="2026-09-09 00:00:00")
        assert url not in {c["url"] for c in rol.candidates(50)}

    def test_already_resolved_entry_is_skipped(self):
        sid = _seed("cand-open")
        url = _url("c")
        _entry(sid, url, open_licence="cc-by")
        assert url not in {c["url"] for c in rol.candidates(50)}

    def test_normal_source_is_never_a_candidate(self):
        sid = _seed("cand-normal", llm=True)
        url = _url("d")
        _entry(sid, url)
        assert url not in {c["url"] for c in rol.candidates(50)}

    def test_api_sources_are_out_of_scope(self):
        """SEC Form D & Co. sind Signale, keine Aufsätze mit DOI."""
        sid = _seed("cand-api", source_type="api")
        url = _url("e")
        _entry(sid, url)
        assert url not in {c["url"] for c in rol.candidates(50)}


class TestStamp:
    def test_stamp_marks_the_row(self):
        sid = _seed("stamp-src")
        eid = _entry(sid, _url("s"))
        rol._stamp(eid)
        with get_connection() as conn:
            row = conn.execute(
                "SELECT licence_checked_at FROM raw_entries WHERE id = ?", (eid,)).fetchone()
        assert row["licence_checked_at"] is not None

    def test_stamped_row_drops_out_of_the_candidate_set(self):
        sid = _seed("stamp-scope")
        url = _url("t")
        eid = _entry(sid, url)
        assert url in {c["url"] for c in rol.candidates(50)}
        rol._stamp(eid)
        assert url not in {c["url"] for c in rol.candidates(50)}


class TestSaturdayStepScope:
    """Der Samstagsschritt darf NICHT auf --min-id laufen.

    `MIN_ID` ist der Wasserstand vom Samstagmorgen; die Einträge der
    Vorbehalts-Quellen entstehen beim Poll von Montag bis Freitag und liegen
    darunter. Mit --min-id fände der Schritt konsequent 0 Zeilen.
    """

    def test_wrapper_calls_signal_only_without_min_id(self):
        text = (Path(__file__).parent.parent / "scripts" / "weekly_ingesters.sh").read_text()
        line = next(l for l in text.splitlines() if "--signal-only" in l)
        assert "--min-id" not in line, line
        assert "--limit" in line, "Mengenbremse fehlt"
