"""Auftragszettel für Scouting-Dossiers (Branch Agentic-Dossiers).

Dossiers sind proprietäre Owner-Dokumente. Drei Festlegungen des Owners
(2026-09-01) sind hier Konstruktionsprinzip, nicht Konfiguration:

  * Aufträge erteilt ausschließlich der Owner (Frontend-Seite /trends/dossiers
    oder CLI) — es gibt keinen Kundenpfad zu dieser Tabelle.
  * Kein Automatikbetrieb: nichts hier läuft per Cron. Aufträge werden nur
    abgearbeitet, wenn der Owner scripts/dossier_worker.py startet.
  * Jeder abgeschlossene Lauf endet im Status 'review', nie in 'done' — die
    finale Durchsicht macht immer der Owner. Der Agent liefert vorher seine
    eigene Endkontrolle (pipeline/dossier_check.py) als check_json mit.

Statusfluss (seit Stufe 1 des Dossier-Agent-Plans, 2026-09-19, mit
Owner-Checkpoint):

    queued ──(worker)──▶ running ──▶ review ──(Owner)──▶ done
       │                    │  │
       │                    │  └──(Intake, checkpoint)──▶ awaiting_confirmation
       │                    │            (Owner: confirm [+ Korrektur]) ──▶ queued
       ▼ (Owner)            ▼ (Fehler / Intake abgewiesen)
    cancelled            failed ──(Owner: requeue)──▶ queued

Der Intake (pipeline/dossier_brief.py) legt Auftrag, Feldprofil und Plan auf
den Zettel (brief_json/profile_json/plan_json); beim Checkpoint bleibt der
Auftrag in 'awaiting_confirmation', bis der Owner bestätigt — mit oder ohne
Korrektur in einem Satz (owner_note; der Worker hängt sie als "Owner
correction: …" an die Frage und rechnet Auftrag/Profil/Plan dann neu).

Die Tabelle wird — wie dead_links (#48) — NICHT in db.init_db() verdrahtet.
Auf der Live-DB legt sie scripts/migrate_dossier_orders.py einmalig manuell an;
ensure_schema() hier ist idempotent und dient Tests (SQLite) und dem Worker als
Gürtel-und-Hosenträger.
"""
from __future__ import annotations

import json
import re
import unicodedata

from pipeline import db as db_mod
from pipeline.db import get_connection

VALID_STATUS = ("queued", "running", "awaiting_confirmation", "review", "done",
                "failed", "cancelled")

# Worker-Parameter, die ein Auftrag überschreiben darf (alles andere in
# params_json wird ignoriert, damit ein Tippfehler nicht still versandet).
ALLOWED_PARAMS = frozenset(
    ("steps", "sources", "per_query", "scope", "web_steps", "web_sources",
     "retrieval", "quant", "measure",
     # 2026-09-13: "dr" (Notizen vor dem Schreiben, Default an — false schaltet ab)
     # und "cpc" (Anker fuer die Patentmessung, z. B. H01M4/5825). Bis dahin
     # filterte diese Liste "dr" still heraus — params={"dr": true} kam nie an.
     "dr", "cpc",
     # 2026-09-13: "mode" = technology | landscape (Teilfeld-Karte fuer breite Felder)
     "mode",
     # 2026-09-19 (Stufe 1): "checkpoint" = nach Auftrag/Profil/Plan auf den Owner
     # warten (Desk: an; CLI --order-new und Newsletter-Deep-Dive: aus).
     "checkpoint"))

# Spalten der Stufe 1 (additive Migration scripts/migrate_dossier_brief.py;
# ensure_schema zieht sie idempotent nach, damit Tests und Worker sie haben).
BRIEF_COLUMNS: tuple[tuple[str, str, str], ...] = (
    # (Name, Postgres-Typ, SQLite-Typ)
    ("brief_json", "JSONB", "TEXT"),
    ("plan_json", "JSONB", "TEXT"),
    ("profile_json", "JSONB", "TEXT"),
    ("confirmed_at", "TIMESTAMP", "TEXT"),
    ("owner_note", "TEXT", "TEXT"),
)
STATUS_CHECK = "CHECK (status IN (" + ",".join(f"'{s}'" for s in VALID_STATUS) + "))"


def _ddl() -> str:
    if db_mod.USE_POSTGRES:
        id_col = "id SERIAL PRIMARY KEY"
        ts = "TIMESTAMP"
        ts_default = "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
    else:
        id_col = "id INTEGER PRIMARY KEY AUTOINCREMENT"
        ts = "TEXT"
        ts_default = "TEXT DEFAULT (datetime('now'))"
    return (
        "CREATE TABLE IF NOT EXISTS dossier_orders ("
        f" {id_col},"
        "  slug TEXT NOT NULL,"
        "  topic TEXT NOT NULL,"
        "  question TEXT,"                 # NULL → foresight_question(topic)
        "  params_json TEXT NOT NULL DEFAULT '{}',"
        "  status TEXT NOT NULL DEFAULT 'queued'"
        f"    {STATUS_CHECK},"
        "  error TEXT,"
        "  check_json TEXT,"               # Endkontrolle des Agenten
        "  dossier_version INTEGER,"       # erzeugte Version in dossiers(slug, version)
        f" created_at {ts_default},"
        f" started_at {ts},"
        f" finished_at {ts},"
        f" reviewed_at {ts},"
        + ", ".join(f"{name} {pg if db_mod.USE_POSTGRES else lite}"
                    for name, pg, lite in BRIEF_COLUMNS)
        + ")")


def _dossiers_ddl() -> str:
    """Versionierte Berichte des Rechercheurs — backend-gerecht (das frühere
    Ad-hoc-DDL in save_dossier war mit SERIAL stillschweigend Postgres-only)."""
    if db_mod.USE_POSTGRES:
        id_col, result_t = "id SERIAL PRIMARY KEY", "JSONB"
        ts_default = "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
    else:
        id_col, result_t = "id INTEGER PRIMARY KEY AUTOINCREMENT", "TEXT"
        ts_default = "TEXT DEFAULT (datetime('now'))"
    return (
        "CREATE TABLE IF NOT EXISTS dossiers ("
        f" {id_col},"
        "  slug TEXT NOT NULL,"
        "  version INTEGER NOT NULL,"
        "  topic TEXT,"
        "  question TEXT NOT NULL,"
        "  report_md TEXT NOT NULL,"
        f" result {result_t} NOT NULL,"
        "  model TEXT,"
        f" created_at {ts_default},"
        "  UNIQUE (slug, version)"
        ")")


def _existing_columns(conn) -> set[str]:
    if db_mod.USE_POSTGRES:
        rows = conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'dossier_orders'").fetchall()
        return {dict(r)["column_name"] for r in rows}
    rows = conn.execute("PRAGMA table_info(dossier_orders)").fetchall()
    return {dict(r)["name"] for r in rows}


def migrate_brief_columns(conn) -> list[str]:
    """Stufe-1-Spalten additiv nachziehen; gibt die neu angelegten zurück."""
    have = _existing_columns(conn)
    added = []
    for name, pg, lite in BRIEF_COLUMNS:
        if name in have:
            continue
        conn.execute(f"ALTER TABLE dossier_orders ADD COLUMN {name} "
                     f"{pg if db_mod.USE_POSTGRES else lite}")
        added.append(name)
    return added


def migrate_status_check(conn) -> bool:
    """Postgres: die CHECK-Constraint auf VALID_STATUS heben (drop + re-add).
    SQLite kann eine Tabellen-Constraint nicht ändern — dort gilt sie nur für
    neu angelegte Tabellen (Tests legen frisch an). True = geändert."""
    if not db_mod.USE_POSTGRES:
        return False
    rows = conn.execute(
        "SELECT conname, pg_get_constraintdef(oid) AS def FROM pg_constraint "
        "WHERE conrelid = 'dossier_orders'::regclass AND contype = 'c'").fetchall()
    for r in rows:
        r = dict(r)
        if "status" not in (r["def"] or ""):
            continue
        if all(f"'{s}'" in r["def"] for s in VALID_STATUS):
            return False
        conn.execute(f"ALTER TABLE dossier_orders DROP CONSTRAINT {r['conname']}")
    conn.execute(f"ALTER TABLE dossier_orders ADD CONSTRAINT dossier_orders_status_check "
                 f"{STATUS_CHECK}")
    return True


def ensure_schema() -> None:
    """Idempotent; auf der Live-DB übernimmt das die manuelle Migration."""
    with get_connection() as conn:
        conn.execute(_ddl())
        conn.execute(_dossiers_ddl())
        migrate_brief_columns(conn)


def slugify(text: str) -> str:
    """Dossier-Serien-Slug aus dem Thema — stabil, damit ein zweiter Auftrag
    zum selben Thema als nächste Version derselben Serie landet."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return text[:80] or "dossier"


def _clean_params(params: dict | None) -> dict:
    if not params:
        return {}
    return {k: v for k, v in params.items() if k in ALLOWED_PARAMS}


def create_order(topic: str, slug: str | None = None, question: str | None = None,
                 params: dict | None = None) -> int:
    """Einen Auftragszettel anlegen. Gibt die Order-ID zurück."""
    topic = (topic or "").strip()
    if not topic:
        raise ValueError("topic must not be empty")
    row_slug = slugify(slug) if slug else slugify(topic)
    payload = json.dumps(_clean_params(params), ensure_ascii=False)
    with get_connection() as conn:
        if db_mod.USE_POSTGRES:
            cur = conn.execute(
                "INSERT INTO dossier_orders (slug, topic, question, params_json) "
                "VALUES (?, ?, ?, ?) RETURNING id",
                (row_slug, topic, (question or "").strip() or None, payload))
            return int(dict(cur.fetchone())["id"])
        cur = conn.execute(
            "INSERT INTO dossier_orders (slug, topic, question, params_json) "
            "VALUES (?, ?, ?, ?)",
            (row_slug, topic, (question or "").strip() or None, payload))
        return int(cur.lastrowid)


def _json_col(v):
    """JSON-Spalte lesen: SQLite liefert den String, psycopg2 bei JSONB schon
    das Objekt."""
    if v is None or v == "":
        return None
    if isinstance(v, (dict, list)):
        return v
    try:
        return json.loads(v)
    except (TypeError, ValueError):
        return None


def _row(r) -> dict:
    d = dict(r)
    try:
        d["params"] = _clean_params(json.loads(d.get("params_json") or "{}"))
    except (TypeError, ValueError):
        d["params"] = {}
    try:
        d["check"] = json.loads(d["check_json"]) if d.get("check_json") else None
    except (TypeError, ValueError):
        d["check"] = None
    for col, key in (("brief_json", "brief"), ("profile_json", "profile"),
                     ("plan_json", "plan")):
        d[key] = _json_col(d.get(col))
    d.setdefault("confirmed_at", None)
    d.setdefault("owner_note", None)
    return d


def get_order(order_id: int) -> dict | None:
    with get_connection() as conn:
        r = conn.execute("SELECT * FROM dossier_orders WHERE id = ?",
                         (order_id,)).fetchone()
    return _row(r) if r else None


def list_orders(status: str | None = None, limit: int = 100) -> list[dict]:
    sql = "SELECT * FROM dossier_orders"
    args: tuple = ()
    if status:
        sql += " WHERE status = ?"
        args = (status,)
    sql += " ORDER BY id DESC LIMIT ?"
    with get_connection() as conn:
        rows = conn.execute(sql, args + (limit,)).fetchall()
    return [_row(r) for r in rows]


def queued_orders() -> list[dict]:
    """Alle offenen Aufträge, älteste zuerst — die Abarbeitungsreihenfolge."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM dossier_orders WHERE status = 'queued' "
            "ORDER BY id ASC").fetchall()
    return [_row(r) for r in rows]


def _transition(order_id: int, from_status: tuple[str, ...], to_status: str,
                extra_sql: str = "", extra_args: tuple = ()) -> bool:
    """Statusübergang nur aus den erlaubten Ausgangszuständen. False = der
    Auftrag war nicht (mehr) in einem davon — der Aufrufer muss das behandeln,
    still weiterlaufen wäre ein Doppel-Lauf."""
    ph = ", ".join("?" for _ in from_status)
    with get_connection() as conn:
        cur = conn.execute(
            f"UPDATE dossier_orders SET status = ?{extra_sql} "
            f"WHERE id = ? AND status IN ({ph})",
            (to_status,) + extra_args + (order_id,) + from_status)
        return cur.rowcount == 1


def mark_running(order_id: int) -> bool:
    return _transition(order_id, ("queued",), "running",
                       ", started_at = CURRENT_TIMESTAMP, error = NULL")


def mark_review(order_id: int, dossier_version: int, check: dict) -> bool:
    """Lauf fertig → IMMER 'review' (Owner-Festlegung: die finale Durchsicht
    macht der Owner, auch bei tadelloser Endkontrolle)."""
    return _transition(
        order_id, ("running",), "review",
        ", finished_at = CURRENT_TIMESTAMP, dossier_version = ?, check_json = ?",
        (dossier_version, json.dumps(check, ensure_ascii=False)))


def mark_failed(order_id: int, error: str) -> bool:
    return _transition(order_id, ("running", "queued"), "failed",
                       ", finished_at = CURRENT_TIMESTAMP, error = ?",
                       ((error or "unknown error")[:2000],))


# --- Stufe 1: Intake und Owner-Checkpoint ----------------------------------

def _dumps(obj) -> str | None:
    return None if obj is None else json.dumps(obj, ensure_ascii=False)


def store_intake(order_id: int, brief: dict | None, profile: dict | None,
                 plan: dict | None) -> None:
    """Auftrag/Profil/Plan auf den Zettel legen (jeder Status; der Desk zeigt
    sie auch nach dem Lauf)."""
    with get_connection() as conn:
        conn.execute("UPDATE dossier_orders SET brief_json = ?, profile_json = ?, "
                     "plan_json = ? WHERE id = ?",
                     (_dumps(brief), _dumps(profile), _dumps(plan), order_id))


def mark_awaiting(order_id: int, brief: dict | None, profile: dict | None,
                  plan: dict | None) -> bool:
    """running → awaiting_confirmation (Checkpoint): der Worker hält an, der
    Desk zeigt Auftrag, Feldprofil und Plan."""
    return _transition(order_id, ("running",), "awaiting_confirmation",
                       ", brief_json = ?, profile_json = ?, plan_json = ?",
                       (_dumps(brief), _dumps(profile), _dumps(plan)))


def confirm(order_id: int, note: str | None = None) -> bool:
    """awaiting_confirmation → queued. Die Notiz („Korrektur in einem Satz")
    wird gespeichert; der Worker hängt sie beim nächsten Lauf als
    "Owner correction: …" an die Frage und rechnet Auftrag/Profil/Plan neu.
    Leer = Bestätigung: die gespeicherten Artefakte werden weiterverwendet."""
    note = " ".join((note or "").split())[:1000] or None
    return _transition(order_id, ("awaiting_confirmation",), "queued",
                       ", confirmed_at = CURRENT_TIMESTAMP, owner_note = ?", (note,))


def reject_intake(order_id: int, reason: str) -> bool:
    """Intake abgewiesen (kein Fragesatz o. ä.) → failed mit dem Grund; der
    Owner korrigiert die Frage auf einem neuen Zettel oder reiht neu ein."""
    return _transition(order_id, ("running", "queued"), "failed",
                       ", finished_at = CURRENT_TIMESTAMP, error = ?",
                       (("intake rejected: " + (reason or "no question"))[:2000],))


def effective_question(order: dict, default: str) -> str:
    """Die Frage, mit der der Lauf arbeitet: das Fragefeld (sonst `default`)
    plus die Owner-Korrektur aus dem Checkpoint."""
    q = (order.get("question") or "").strip() or default
    note = " ".join((order.get("owner_note") or "").split())
    if note:
        q = f"{q}\n\nOwner correction: {note}"
    return q


def approve(order_id: int) -> bool:
    """Owner-Abnahme nach der finalen Durchsicht."""
    return _transition(order_id, ("review",), "done",
                       ", reviewed_at = CURRENT_TIMESTAMP")


def cancel(order_id: int) -> bool:
    return _transition(order_id, ("queued", "awaiting_confirmation"), "cancelled")


def requeue(order_id: int) -> bool:
    """Fehlgeschlagenen Auftrag erneut einreihen (Fehlertext bleibt bis zum
    nächsten mark_running stehen, damit die Ursache sichtbar ist)."""
    return _transition(order_id, ("failed",), "queued")
