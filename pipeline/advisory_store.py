"""Speicher der Beratungsnotizen (Advisor, Owner 2026-09-14).

Eine Zeile je Notiz: welches Dossier (Slug + Version), Kundenprofil und
Auftragsumfang als Daten, Status `queued → running → review → approved`
(oder `failed`), Notiz, Pruefnachweis, Modell, Freigabe (`approved_at`,
`approved_by`, `approval_note`) — dieselbe Freigabe-Semantik wie beim
Newsletter (06.09.): ohne `approved_at` verlaesst nichts das Haus.

Additiv, idempotent (`ensure_schema`), backend-gerecht (Postgres/SQLite).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from pipeline import db as db_mod
from pipeline.db import get_connection

STATUSES = ("queued", "running", "review", "approved", "failed", "withdrawn")


def _ddl() -> str:
    if db_mod.USE_POSTGRES:
        id_col, ts, ts_default = "id SERIAL PRIMARY KEY", "TIMESTAMP", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
    else:
        id_col, ts, ts_default = "id INTEGER PRIMARY KEY AUTOINCREMENT", "TEXT", "TEXT DEFAULT (datetime('now'))"
    return (
        "CREATE TABLE IF NOT EXISTS advisory_notes ("
        f" {id_col},"
        "  dossier_slug TEXT NOT NULL,"
        "  dossier_version INTEGER NOT NULL,"
        "  profile_json TEXT NOT NULL DEFAULT '{}',"
        "  scope TEXT NOT NULL,"
        "  status TEXT NOT NULL DEFAULT 'queued'"
        "    CHECK (status IN ('queued','running','review','approved','failed','withdrawn')),"
        "  note_md TEXT,"
        "  check_json TEXT,"
        "  model TEXT,"
        "  seconds REAL,"
        "  error TEXT,"
        f" created_at {ts_default},"
        f" started_at {ts},"
        f" finished_at {ts},"
        f" approved_at {ts},"
        "  approved_by TEXT,"
        "  approval_note TEXT"
        ")")


def ensure_schema() -> None:
    with get_connection() as conn:
        conn.execute(_ddl())


def _now():
    return datetime.now(timezone.utc) if db_mod.USE_POSTGRES else datetime.now(timezone.utc).isoformat()


def _row(r) -> dict:
    d = dict(r)
    for k in ("profile_json", "check_json"):
        v = d.get(k)
        if isinstance(v, str):
            try:
                d[k[:-5]] = json.loads(v)
            except ValueError:
                d[k[:-5]] = {}
        elif isinstance(v, dict):
            d[k[:-5]] = v
        else:
            d[k[:-5]] = {}
    return d


def get_dossier(slug: str, version: int | None = None) -> dict | None:
    """Das Dossier (report_md + result) — die neueste Version, wenn keine genannt ist."""
    with get_connection() as conn:
        if version is None:
            r = conn.execute("SELECT * FROM dossiers WHERE slug = ? ORDER BY version DESC LIMIT 1",
                             (slug,)).fetchone()
        else:
            r = conn.execute("SELECT * FROM dossiers WHERE slug = ? AND version = ?",
                             (slug, int(version))).fetchone()
    if not r:
        return None
    d = dict(r)
    if isinstance(d.get("result"), str):
        try:
            d["result"] = json.loads(d["result"])
        except ValueError:
            d["result"] = {}
    return d


def create_note(dossier_slug: str, dossier_version: int, profile: dict, scope: str) -> int:
    scope = " ".join((scope or "").split())
    if not scope:
        raise ValueError("scope must not be empty")
    payload = json.dumps(profile or {}, ensure_ascii=False)
    with get_connection() as conn:
        if db_mod.USE_POSTGRES:
            cur = conn.execute(
                "INSERT INTO advisory_notes (dossier_slug, dossier_version, profile_json, scope) "
                "VALUES (?, ?, ?, ?) RETURNING id", (dossier_slug, int(dossier_version), payload, scope))
            return int(dict(cur.fetchone())["id"])
        cur = conn.execute(
            "INSERT INTO advisory_notes (dossier_slug, dossier_version, profile_json, scope) "
            "VALUES (?, ?, ?, ?)", (dossier_slug, int(dossier_version), payload, scope))
        return int(cur.lastrowid)


def get_note(note_id: int) -> dict | None:
    with get_connection() as conn:
        r = conn.execute("SELECT * FROM advisory_notes WHERE id = ?", (int(note_id),)).fetchone()
    return _row(r) if r else None


def list_notes(dossier_slug: str | None = None, limit: int = 50) -> list[dict]:
    with get_connection() as conn:
        if dossier_slug:
            rows = conn.execute("SELECT * FROM advisory_notes WHERE dossier_slug = ? "
                                "ORDER BY id DESC LIMIT ?", (dossier_slug, int(limit))).fetchall()
        else:
            rows = conn.execute("SELECT * FROM advisory_notes ORDER BY id DESC LIMIT ?",
                                (int(limit),)).fetchall()
    return [_row(r) for r in rows]


def queued_notes() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM advisory_notes WHERE status = 'queued' ORDER BY id").fetchall()
    return [_row(r) for r in rows]


def _transition(note_id: int, from_status: tuple[str, ...], to_status: str, extra_sql: str = "",
                extra_params: tuple = ()) -> bool:
    placeholders = ", ".join("?" for _ in from_status)
    with get_connection() as conn:
        cur = conn.execute(
            f"UPDATE advisory_notes SET status = ?{extra_sql} WHERE id = ? AND status IN ({placeholders})",
            (to_status, *extra_params, int(note_id), *from_status))
        return bool(cur.rowcount)


def mark_running(note_id: int) -> bool:
    return _transition(note_id, ("queued", "failed"), "running", ", started_at = ?", (_now(),))


def mark_review(note_id: int, note_md: str, check: dict, model: str, seconds: float) -> bool:
    return _transition(note_id, ("running",), "review",
                       ", note_md = ?, check_json = ?, model = ?, seconds = ?, finished_at = ?",
                       (note_md, json.dumps(check, ensure_ascii=False), model, float(seconds), _now()))


def mark_failed(note_id: int, error: str) -> bool:
    return _transition(note_id, ("queued", "running"), "failed", ", error = ?, finished_at = ?",
                       (str(error)[:2000], _now()))


def approve(note_id: int, by: str, note: str | None = None) -> bool:
    """Freigabe durch einen Menschen — nur aus `review`."""
    return _transition(note_id, ("review",), "approved",
                       ", approved_at = ?, approved_by = ?, approval_note = ?",
                       (_now(), (by or "owner")[:120], (note or "")[:2000] or None))


def withdraw(note_id: int) -> bool:
    """Freigabe zurueckziehen (oder eine Review-Notiz verwerfen)."""
    return _transition(note_id, ("approved", "review"), "withdrawn",
                       ", approved_at = NULL, approved_by = NULL", ())
