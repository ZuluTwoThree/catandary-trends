#!/usr/bin/env python3
"""Prozessgrenze des Messtischs — von den API-Routen via execFile aufgerufen.

    instrument.py board   --workspace catandary
    instrument.py queue   --workspace catandary --rater owner --field cluster:63:12
    instrument.py rate    --workspace catandary --rater owner --field ... --trend 42 --points 3
    instrument.py fields  --workspace catandary --add cluster:63:12 --label "Machine Learning"

Eine JSON-Zeile auf stdout. Die Zellenlogik bleibt in Python, damit sie nicht in
zwei Sprachen driftet — dieselbe Begründung wie bei radar_query.py.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.db import get_connection
from pipeline.instrument import (SAMPLE_SIZE, STAGE_BAND, STAGE_LABEL,
                                 assess_field, ensure_rater, ensure_workspace,
                                 expertise_weight, hint_points, migrate,
                                 relevance_direction, relevance_stage,
                                 sample_for_rating, score_against, discover,
                                 field_series, field_trend_ids, reset_workspace,
                                 reset_preview,
                                 project)


def _cluster_meta(conn, field_key: str) -> tuple[list[dict], float | None, str | None]:
    """Zeitreihe, Evidenzpunkte und Vertikale eines Felds."""
    kind, _, rest = field_key.partition(":")
    if kind != "cluster":
        return [], None, None
    run_id, _, idx = rest.partition(":")
    row = conn.execute(
        "SELECT fc.monthly_series, fc.verticals, fr.scope FROM foresight_clusters fc "
        "JOIN foresight_runs fr ON fr.id = fc.run_id "
        "WHERE fc.run_id=%s AND fc.cluster_idx=%s", (int(run_id), int(idx))).fetchone()
    if not row:
        return [], None, None
    ms = row["monthly_series"]
    ms = ms if isinstance(ms, list) else json.loads(ms or "[]")
    verts = row["verticals"]
    verts = verts if isinstance(verts, list) else json.loads(verts or "[]")
    vertical = verts[0] if verts else None
    # Evidenzpunkte aus dem bestehenden, kalibrierten Reife-Modul, sofern für
    # dieses Cluster schon ein Radar gerechnet wurde.
    ev = conn.execute(
        "SELECT m.score FROM radar_maturity m JOIN radar_scopes s "
        "  ON s.slug = m.scope_slug "
        "WHERE s.cluster_run_id=%s AND s.cluster_idx=%s "
        "ORDER BY m.id DESC LIMIT 1", (int(run_id), int(idx))).fetchone()
    return ms, (float(ev["score"]) if ev and ev["score"] is not None else None), vertical


def cmd_board(args) -> dict:
    wid = ensure_workspace(args.workspace, args.workspace.title())
    out = []
    with get_connection() as conn:
        conn.execute("SET statement_timeout = 60000")
        fields = conn.execute(
            "SELECT field_key, label, vertical FROM workspace_field "
            "WHERE workspace_id=%s ORDER BY sort_order, label", (wid,)).fetchall()
        for f in fields:
            a = conn.execute(
                "SELECT * FROM field_assessment WHERE workspace_id=%s AND field_key=%s",
                (wid, f["field_key"])).fetchone()
            rated = conn.execute(
                "SELECT count(*) AS n FROM signal_relevance "
                "WHERE workspace_id=%s AND field_key=%s AND points IS NOT NULL",
                (wid, f["field_key"])).fetchone()["n"]
            stage = (a["maturity_stage"] if a else None) or "volatile"
            rel = a["relevance"] if a else None
            out.append({
                "field_key": f["field_key"], "label": f["label"],
                "vertical": f["vertical"],
                "stage": stage, "stage_label": STAGE_LABEL[stage],
                "band": STAGE_BAND[stage],
                "basis": (a["maturity_basis"] if a else "default"),
                "note": (a["maturity_note"] if a else None),
                "relevance": rel, "rel_stage": relevance_stage(rel),
                "spread": (a["relevance_spread"] if a else 0),
                "n_rated": rated, "n_raters": (a["n_raters"] if a else 0),
                "sample_size": SAMPLE_SIZE,
            })
    return {"workspace": args.workspace, "fields": out}


def cmd_queue(args) -> dict:
    wid = ensure_workspace(args.workspace, args.workspace.title())
    rid = ensure_rater(wid, args.rater)
    with get_connection() as conn:
        conn.execute("SET statement_timeout = 60000")
        rows = sample_for_rating(conn, wid, rid, args.field, n=args.n)
        total = conn.execute(
            "SELECT count(*) AS n FROM signal_relevance WHERE workspace_id=%s "
            "AND rater_id=%s AND field_key=%s", (wid, rid, args.field)).fetchone()["n"]
        _, _, vertical = _cluster_meta(conn, args.field)
        w = expertise_weight(conn, rid, wid, vertical)
        # Vorschlag aus den bisherigen Bewertungen — global gelernt, nicht je
        # Feld (siehe pipeline/instrument.py, relevance_direction).
        direction, dmeta = relevance_direction(conn, wid)
        scores = score_against(conn, direction, [r["id"] for r in rows]) \
            if direction else {}
    return {
        "field": args.field, "done": total, "sample_size": SAMPLE_SIZE,
        "weight": w, "model": dmeta,
        "signals": [{
            "id": r["id"], "title": r["title_en"],
            "summary": (r["summary_en"] or "")[:260],
            "source": r["source_name"], "url": r["source_url"],
            "type": r["trend_signal_type"], "date": str(r["event_date"]),
            "hint": (hint_points(scores[r["id"]]) if r["id"] in scores else None),
            "hint_score": (round(scores[r["id"]], 3) if r["id"] in scores else None),
        } for r in rows],
    }


def cmd_rate(args) -> dict:
    wid = ensure_workspace(args.workspace, args.workspace.title())
    rid = ensure_rater(wid, args.rater)
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO signal_relevance (workspace_id, rater_id, field_key,"
            " trend_id, points, skipped) VALUES (%s,%s,%s,%s,%s,%s) "
            "ON CONFLICT (workspace_id, rater_id, trend_id) DO UPDATE "
            "SET points=EXCLUDED.points, skipped=EXCLUDED.skipped, "
            "    rated_at=CURRENT_TIMESTAMP",
            (wid, rid, args.field, args.trend,
             None if args.skip else args.points, bool(args.skip)))
        conn.commit()
        ms, ev, vertical = _cluster_meta(conn, args.field)
        if not ms:
            ms = field_series(conn, args.field)
    return assess_field(wid, args.field, evidence_score=ev, series=ms,
                        vertical=vertical)


def cmd_search(args) -> dict:
    """Vorschau auf ein Suchfeld, bevor es auf den Tisch kommt."""
    wid = ensure_workspace(args.workspace, args.workspace.title())
    key = f"search:{args.q}"
    with get_connection() as conn:
        conn.execute("SET statement_timeout = 60000")
        ids = field_trend_ids(conn, key, limit=40_000)
        preview = []
        if ids:
            preview = [dict(r) for r in conn.execute(
                """SELECT t.id, t.title_en, t.source_name, t.trend_signal_type,
                          COALESCE(r.published_date, t.created_at)::date AS d
                     FROM trends t LEFT JOIN raw_entries r ON r.id = t.raw_entry_id
                    WHERE t.id = ANY(%s)
                    ORDER BY COALESCE(r.published_date, t.created_at) DESC
                    LIMIT 6""", (ids[:5000],)).fetchall()]
        series = field_series(conn, key)
    from pipeline.instrument import curve_position
    cp = curve_position(series)
    return {
        "query": args.q, "field_key": key, "n": len(ids),
        "months": len(series),
        "stage": cp.get("stage"), "stage_reason": cp.get("reason"),
        "preview": [{"id": p["id"], "title": p["title_en"],
                     "source": p["source_name"], "type": p["trend_signal_type"],
                     "date": str(p["d"])} for p in preview],
    }


def cmd_reset(args) -> dict:
    wid = ensure_workspace(args.workspace, args.workspace.title())
    return reset_workspace(wid, keep_fields=args.keep_fields)


def cmd_discover(args) -> dict:
    wid = ensure_workspace(args.workspace, args.workspace.title())
    with get_connection() as conn:
        conn.execute("SET statement_timeout = 60000")
        return discover(conn, wid)


def cmd_catalog(args) -> dict:
    """Was der Nutzer auf den Tisch legen kann.

    Drei Flughöhen, wie im Auftrag: Vertikale (die Branche), Mega-Trend (die
    große Bewegung), Cluster (das konkrete Feld). Ein Nutzer beobachtet in der
    Regel nicht alles — die Auswahl ist deshalb der erste Arbeitsschritt, nicht
    eine Einstellung im Hintergrund.
    """
    wid = ensure_workspace(args.workspace, args.workspace.title())
    out: dict[str, list] = {"vertical": [], "mega": [], "cluster": []}
    with get_connection() as conn:
        conn.execute("SET statement_timeout = 120000")
        chosen = {r["field_key"] for r in conn.execute(
            "SELECT field_key FROM workspace_field WHERE workspace_id=%s",
            (wid,)).fetchall()}

        for r in conn.execute(
            "SELECT primary_vertical AS v, count(*) AS n FROM trends "
            "WHERE primary_vertical IS NOT NULL GROUP BY 1 ORDER BY n DESC"
        ).fetchall():
            out["vertical"].append({
                "field_key": f"vertical:{r['v']}", "label": r["v"],
                "n": r["n"], "group": "Branche", "chosen": f"vertical:{r['v']}" in chosen,
            })

        for r in conn.execute(
            "SELECT mega_trend AS m, count(*) AS n FROM trends "
            "WHERE mega_trend IS NOT NULL AND mega_trend <> '' "
            "GROUP BY 1 HAVING count(*) >= 500 ORDER BY n DESC"
        ).fetchall():
            key = f"mega:{r['m']}"
            out["mega"].append({
                "field_key": key,
                "label": r["m"].replace("_", " ").title(),
                "n": r["n"], "group": "Mega-Trend", "chosen": key in chosen,
            })

        # Cluster nur aus dem jüngsten Lauf je Scope, und nur solche mit
        # gespeicherter Mitgliedschaft — sonst wäre die Stichprobe nicht ziehbar.
        for r in conn.execute(
            """SELECT fc.run_id, fc.cluster_idx, fc.label, fc.size, fc.momentum,
                      fc.sov_delta_pp, fc.rep_titles, fr.scope
                 FROM foresight_clusters fc
                 JOIN foresight_runs fr ON fr.id = fc.run_id
                WHERE fc.run_id IN (SELECT max(id) FROM foresight_runs GROUP BY scope)
                  AND fc.size >= 300
                  AND EXISTS (SELECT 1 FROM foresight_cluster_members m
                               WHERE m.run_id = fc.run_id)
                ORDER BY fr.scope, fc.size DESC"""
        ).fetchall():
            key = f"cluster:{r['run_id']}:{r['cluster_idx']}"
            reps = r["rep_titles"] if isinstance(r["rep_titles"], list) \
                else json.loads(r["rep_titles"] or "[]")
            scope = r["scope"]
            pretty = (scope.replace("vertical:", "")
                      .replace("mega:", "")
                      .replace("_", " ").title()
                      if scope != "global" else "Branchenübergreifend")
            out["cluster"].append({
                "field_key": key, "label": r["label"], "n": r["size"],
                "group": pretty, "momentum": r["momentum"],
                "delta": r["sov_delta_pp"], "reps": reps[:2],
                "chosen": key in chosen,
            })
    return {"catalog": out, "n_chosen": len(chosen)}


def cmd_fields(args) -> dict:
    wid = ensure_workspace(args.workspace, args.workspace.title())
    with get_connection() as conn:
        if args.add:
            _, _, vertical = _cluster_meta(conn, args.add)
            kind, _, rest = args.add.partition(":")
            if kind == "vertical":
                vertical = rest
            if not args.label:
                args.label = (rest if kind == "search" else
                              rest.replace("_", " ").title()
                              if kind in ("mega", "vertical") else args.add)
            conn.execute(
                "INSERT INTO workspace_field (workspace_id, field_key, label,"
                " vertical, sort_order) VALUES (%s,%s,%s,%s,%s) "
                "ON CONFLICT (workspace_id, field_key) DO UPDATE "
                "SET label=EXCLUDED.label, vertical=EXCLUDED.vertical",
                (wid, args.add, args.label or args.add, vertical, 0))
            conn.commit()
            ms, ev, vertical = _cluster_meta(conn, args.add)
            if not ms:
                ms = field_series(conn, args.add)
            assess_field(wid, args.add, evidence_score=ev, series=ms,
                         vertical=vertical)
        if args.remove:
            conn.execute("DELETE FROM workspace_field WHERE workspace_id=%s "
                         "AND field_key=%s", (wid, args.remove))
            conn.commit()
    return cmd_board(args)


def cmd_reset_preview(args) -> dict:
    """Was ein Neustart löschen würde — die Zahlen für die Bestätigung."""
    return reset_preview(ensure_workspace(args.workspace, args.workspace.title()))


def cmd_project(args) -> dict:
    """Den gesamten Signalraum gegen das gelernte Interesse ins Radar legen."""
    wid = ensure_workspace(args.workspace, args.workspace.title())
    with get_connection() as conn:
        conn.execute("SET statement_timeout = 60000")
        return project(conn, wid)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["board", "queue", "rate", "fields",
                                    "catalog", "discover", "search", "reset",
                                    "reset-preview", "project", "migrate"])
    ap.add_argument("--workspace", default="catandary")
    ap.add_argument("--rater", default="owner")
    ap.add_argument("--field", default=None)
    ap.add_argument("--trend", type=int, default=None)
    ap.add_argument("--points", type=int, default=None)
    ap.add_argument("--skip", action="store_true")
    ap.add_argument("--n", type=int, default=SAMPLE_SIZE)
    ap.add_argument("--add", default=None)
    ap.add_argument("--remove", default=None)
    ap.add_argument("--label", default=None)
    ap.add_argument("--q", default=None)
    ap.add_argument("--keep-fields", action="store_true")
    args = ap.parse_args()

    if args.cmd == "migrate":
        migrate()
        print(json.dumps({"ok": True}))
        return 0
    fn = {"board": cmd_board, "queue": cmd_queue, "rate": cmd_rate,
          "fields": cmd_fields, "catalog": cmd_catalog,
          "discover": cmd_discover, "search": cmd_search,
          "reset": cmd_reset, "reset-preview": cmd_reset_preview,
          "project": cmd_project}[args.cmd]
    print(json.dumps(fn(args), default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
