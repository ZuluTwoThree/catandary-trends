"""Erfahrungsbasis je (Feld, Host) — Stufe 2 des Plans
docs/plan_dossier_agent_2026-09-18.md („Beschaffung aus dem Profil,
Primärquellen je Feld").

Tabelle `dossier_source_priors`: je Feld und Host, wie oft der Rechercheur
dort gelesen (`n_read`), zitiert (`n_cited`) und eine zitierte Aussage später
gestrichen hat (`n_dropped`), dazu der beste je gesehene Rang (`rank_seen`).
Ein Host, der im selben Feld mindestens zweimal zitiert, nie gestrichen und
mindestens einmal wirklich GELESEN wurde (Web-Abruf, nicht nur Original eines
Korpus-Artikels — sonst würde die Fachpresse, die unsere Artikel zitieren,
zur „Erfahrung"), bekommt beim nächsten Lauf Rang 1 (`primary_hosts_for`) —
verifiziert durch den Abruf wie jede andere Primärquelle.

Feld = `TopicProfile.field` normalisiert (Kleinschreibung, nur Wortzeichen),
sonst die Themenphrase des Auftrags. Alte Läufe ohne Profil (vor Stufe 1)
zählen unter ihrem Thema.

Schreibpfad NIE sperrend: `update_from_run` fängt alles und gibt 0 zurück.
Additive Migration `scripts/migrate_dossier_source_priors.py` (wie die anderen
Dossier-Tabellen nicht in `db.init_db`); `--backfill` baut die Tabelle aus
allen gespeicherten Läufen NEU (löscht vorher — der Backfill ist eine
Rechnung über `dossiers.result`, keine Fortschreibung).

Inspektion: `python -m pipeline.dossier_priors --show [--field F]`.
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from urllib.parse import urlparse

from pipeline import db as db_mod
from pipeline.db import get_connection

logger = logging.getLogger(__name__)

MIN_CITED_FOR_RANK1 = 2       # so oft zitiert, nie gestrichen, >= 1x gelesen → Rang 1 im Feld
MIN_READ_FOR_RANK1 = 1
WEB_KINDS = ("web", "legal", "market", "entity", "funding")
_NONWORD = re.compile(r"[^a-z0-9]+")
_DROP_EXEMPT_KINDS = ("weaksource", "weakclaim")   # gekennzeichnet, nicht gestrichen


def normalise_field(text: str | None) -> str:
    """'Datacenter Virtualization (x86)' → 'datacenter virtualization x86'."""
    return " ".join(_NONWORD.sub(" ", str(text or "").lower()).split())


def field_of(profile, topic: str) -> str:
    """Feld aus dem Profil (Objekt oder dict), sonst die Themenphrase."""
    name = ""
    if profile is not None:
        name = getattr(profile, "field", None) or (
            profile.get("field") if isinstance(profile, dict) else "") or ""
    return normalise_field(name) or normalise_field(topic)


def host_of(url: str) -> str:
    try:
        return urlparse(str(url or "")).netloc.lower().removeprefix("www.")
    except ValueError:
        return ""


def _ddl() -> str:
    ts = "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
    return (
        "CREATE TABLE IF NOT EXISTS dossier_source_priors ("
        "  field TEXT NOT NULL,"
        "  host TEXT NOT NULL,"
        "  n_read INTEGER NOT NULL DEFAULT 0,"
        "  n_cited INTEGER NOT NULL DEFAULT 0,"
        "  n_dropped INTEGER NOT NULL DEFAULT 0,"
        "  rank_seen INTEGER,"
        f"  updated_at {ts},"
        "  PRIMARY KEY (field, host)"
        ")")


def ensure_schema() -> None:
    """Idempotent; auf der Live-DB übernimmt das scripts/migrate_dossier_source_priors.py."""
    with get_connection() as conn:
        conn.execute(_ddl())
        conn.execute("CREATE INDEX IF NOT EXISTS idx_dossier_source_priors_field "
                     "ON dossier_source_priors (field)")


def table_exists() -> bool:
    try:
        with get_connection() as conn:
            if db_mod.USE_POSTGRES:
                row = conn.execute("SELECT to_regclass('dossier_source_priors') AS r").fetchone()
                return bool(dict(row)["r"]) if row else False
            row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' "
                               "AND name='dossier_source_priors'").fetchone()
            return row is not None
    except Exception:                                               # noqa: BLE001
        return False


# --------------------------------------------------------------------------
# Rechnung über einen Lauf (rein, ohne DB) — Live-Pfad und Backfill teilen sie
# --------------------------------------------------------------------------

def _source_url(src: dict) -> str:
    kind = str(src.get("kind") or "")
    if kind in WEB_KINDS:
        return str(src.get("url") or "")
    if kind in ("article", "signal"):
        return str(src.get("origin") or "")
    return ""


def dropped_urls_from_structure(structure: dict | None) -> list[str]:
    """URLs der Befunde, die den Streichpfad ausgelöst haben (Zahl nicht auf
    der Seite, Beleg von etwas anderem, widersprochen …). `weaksource`/
    `weakclaim` werden gekennzeichnet, nicht gestrichen — sie zählen nicht."""
    out: list[str] = []
    for e in ((structure or {}).get("cite_findings_after") or []):
        if not isinstance(e, dict) or e.get("kind") in _DROP_EXEMPT_KINDS:
            continue
        u = str(e.get("url") or "")
        if u:
            out.append(u)
    return out


def run_host_stats(sources: list[dict], cited_ids, dropped_urls,
                   rank_of=None) -> dict[str, dict]:
    """Je Host: gelesen / zitiert / gestrichen / bester Rang.

    `rank_of(src)` liefert den Rang, wenn die Quelle keinen trägt (alte Läufe
    speichern ihn nicht); ohne Funktion zählt nur, was in `src["rank"]` steht."""
    cited = {str(c) for c in (cited_ids or [])}
    stats: dict[str, dict] = {}

    def _bucket(host: str) -> dict:
        return stats.setdefault(host, {"n_read": 0, "n_cited": 0, "n_dropped": 0,
                                       "rank_seen": None})

    for src in sources or []:
        url = _source_url(src)
        host = host_of(url)
        if not host:
            continue
        b = _bucket(host)
        kind = str(src.get("kind") or "")
        if kind in WEB_KINDS and src.get("fetched"):
            b["n_read"] += 1
        if str(src.get("id")) in cited:
            b["n_cited"] += 1
        rank = src.get("rank")
        if rank is None and rank_of is not None:
            try:
                rank = rank_of(src)
            except Exception:                                       # noqa: BLE001
                rank = None
        if rank is not None:
            rank = int(rank)
            b["rank_seen"] = rank if b["rank_seen"] is None else min(b["rank_seen"], rank)
    for u in dropped_urls or []:
        host = host_of(u)
        if host:
            _bucket(host)["n_dropped"] += 1
    return {h: b for h, b in stats.items()
            if b["n_read"] or b["n_cited"] or b["n_dropped"]}


def upsert(field: str, stats: dict[str, dict]) -> int:
    """Zähler addieren, Rang als Minimum halten. Rückgabe: Hosts geschrieben."""
    field = normalise_field(field)
    if not field or not stats:
        return 0
    sql = (
        "INSERT INTO dossier_source_priors (field, host, n_read, n_cited, n_dropped,"
        " rank_seen, updated_at) VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)"
        " ON CONFLICT (field, host) DO UPDATE SET"
        "  n_read = dossier_source_priors.n_read + EXCLUDED.n_read,"
        "  n_cited = dossier_source_priors.n_cited + EXCLUDED.n_cited,"
        "  n_dropped = dossier_source_priors.n_dropped + EXCLUDED.n_dropped,"
        "  rank_seen = CASE WHEN dossier_source_priors.rank_seen IS NULL THEN EXCLUDED.rank_seen"
        "                   WHEN EXCLUDED.rank_seen IS NULL THEN dossier_source_priors.rank_seen"
        "                   WHEN EXCLUDED.rank_seen < dossier_source_priors.rank_seen THEN EXCLUDED.rank_seen"
        "                   ELSE dossier_source_priors.rank_seen END,"
        "  updated_at = CURRENT_TIMESTAMP")
    n = 0
    with get_connection() as conn:
        for host, b in sorted(stats.items()):
            conn.execute(sql, (field, host, int(b.get("n_read") or 0),
                               int(b.get("n_cited") or 0), int(b.get("n_dropped") or 0),
                               b.get("rank_seen")))
            n += 1
    return n


def update_from_run(field: str, sources: list[dict], cited_ids, structure: dict | None,
                    rank_of=None) -> int:
    """Laufende Fortschreibung am Ende eines Laufs — nie sperrend."""
    try:
        if not table_exists():
            logger.info("dossier_source_priors fehlt — Migration "
                        "scripts/migrate_dossier_source_priors.py nicht ausgeführt; "
                        "keine Fortschreibung")
            return 0
        stats = run_host_stats(sources, cited_ids,
                               dropped_urls_from_structure(structure), rank_of)
        n = upsert(field, stats)
        logger.info("source priors: field=%r, %d host(s) updated", normalise_field(field), n)
        return n
    except Exception as exc:                                        # noqa: BLE001
        logger.warning("source priors not updated (%s: %s)", type(exc).__name__, exc)
        return 0


def qualifies(row: dict, min_cited: int = MIN_CITED_FOR_RANK1) -> bool:
    return (int(row.get("n_cited") or 0) >= min_cited and int(row.get("n_dropped") or 0) == 0
            and int(row.get("n_read") or 0) >= MIN_READ_FOR_RANK1)


def primary_hosts_for(field: str, min_cited: int = MIN_CITED_FOR_RANK1) -> list[str]:
    """Hosts, die im Feld ≥ min_cited-mal zitiert, nie gestrichen und
    mindestens einmal gelesen wurden."""
    field = normalise_field(field)
    if not field:
        return []
    try:
        if not table_exists():
            return []
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT host FROM dossier_source_priors WHERE field = ? AND n_cited >= ? "
                "AND n_dropped = 0 AND n_read >= ? ORDER BY n_cited DESC, host",
                (field, int(min_cited), int(MIN_READ_FOR_RANK1))).fetchall()
        return [str(dict(r)["host"]) for r in rows]
    except Exception as exc:                                        # noqa: BLE001
        logger.warning("source priors not read (%s: %s)", type(exc).__name__, exc)
        return []


def list_priors(field: str | None = None) -> list[dict]:
    with get_connection() as conn:
        if field:
            rows = conn.execute("SELECT * FROM dossier_source_priors WHERE field = ? "
                                "ORDER BY n_cited DESC, n_read DESC, host",
                                (normalise_field(field),)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM dossier_source_priors "
                                "ORDER BY field, n_cited DESC, n_read DESC, host").fetchall()
    return [dict(r) for r in rows]


# --------------------------------------------------------------------------
# Backfill aus den gespeicherten Läufen
# --------------------------------------------------------------------------

def _as_dict(v) -> dict:
    if isinstance(v, dict):
        return v
    if isinstance(v, (str, bytes)):
        try:
            d = json.loads(v)
            return d if isinstance(d, dict) else {}
        except ValueError:
            return {}
    return {}


def load_runs() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute("SELECT id, slug, version, topic, result FROM dossiers "
                            "ORDER BY id").fetchall()
    out = []
    for r in rows:
        r = dict(r)
        r["result"] = _as_dict(r.get("result"))
        out.append(r)
    return out


def backfill(runs: list[dict] | None = None, rank_of=None, wipe: bool = True) -> dict:
    """Tabelle aus allen gespeicherten Läufen neu rechnen. Feld = Profil des
    Laufs (`result["profile"]`, seit Stufe 2) oder das Thema. Rückgabe:
    Zähler je Feld (Hosts, davon Rang-1-Kandidaten)."""
    ensure_schema()
    runs = load_runs() if runs is None else runs
    if wipe:
        with get_connection() as conn:
            conn.execute("DELETE FROM dossier_source_priors")
    per_field: dict[str, int] = {}
    n_runs = 0
    for r in runs:
        res = r.get("result") or {}
        srcs = res.get("sources") or []
        if not srcs:
            continue
        field = field_of(res.get("profile"), str(r.get("topic") or r.get("slug") or ""))
        stats = run_host_stats(srcs, res.get("cited") or [],
                               dropped_urls_from_structure(res.get("structure")), rank_of)
        if not stats:
            continue
        upsert(field, stats)
        per_field[field] = per_field.get(field, 0) + 1
        n_runs += 1
    summary: dict[str, dict] = {}
    for field in per_field:
        rows = list_priors(field)
        summary[field] = {"runs": per_field[field], "hosts": len(rows),
                          "rank1": len(primary_hosts_for(field)),
                          "rank1_hosts": primary_hosts_for(field)}
    return {"runs": n_runs, "fields": summary}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="dossier_source_priors ansehen / neu rechnen")
    ap.add_argument("--show", action="store_true", help="Zeilen ausgeben")
    ap.add_argument("--field", help="nur dieses Feld (normalisiert)")
    ap.add_argument("--backfill", action="store_true",
                    help="Tabelle aus allen gespeicherten Läufen NEU rechnen (löscht vorher)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if a.backfill:
        from scripts import corpus_research as cr
        out = backfill(rank_of=lambda s: cr.catalog_rank(s))
        if a.json:
            print(json.dumps(out, ensure_ascii=False, indent=1))
        else:
            print(f"{out['runs']} Lauf/Läufe verrechnet")
            for f, s in out["fields"].items():
                print(f"  {f}: {s['runs']} Lauf/Läufe, {s['hosts']} Host(s), "
                      f"Rang 1 aus Erfahrung: {s['rank1']} "
                      f"({', '.join(s['rank1_hosts'][:8])}{' …' if len(s['rank1_hosts']) > 8 else ''})")
        return 0
    rows = list_priors(a.field)
    if a.json:
        print(json.dumps(rows, ensure_ascii=False, indent=1, default=str))
        return 0
    if not rows:
        print("(keine Zeilen)")
        return 0
    cur = None
    for r in rows:
        if r["field"] != cur:
            cur = r["field"]
            print(f"\n== {cur}")
        flag = " *" if qualifies(r) else ""
        print(f"  {r['host']:<45} read {r['n_read']:>3}  cited {r['n_cited']:>3}  "
              f"dropped {r['n_dropped']:>3}  rank {r['rank_seen'] if r['rank_seen'] is not None else '-'}{flag}")
    print("\n* = Rang 1 im Feld beim nächsten Lauf (≥ 2× zitiert, nie gestrichen, ≥ 1× gelesen)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
