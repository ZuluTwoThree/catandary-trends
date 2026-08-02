#!/usr/bin/env python3
"""Signalwolke eines Radar-Felds — Prozessgrenze für die API-Route.

Anders als das Zellen-Radar aggregiert dieser Pfad NICHT. Er gibt jedes einzelne
Signal mit seiner Platzierung zurück, damit das Frontend die Verteilung zeigen
kann statt ihres Mittels.

    radar_cloud.py --radar cl-vertical-food --scope c3 [--cap 4000]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.db import get_connection
from pipeline.radar_horizons import (resolve_scope, scope_field_terms,
                                     signal_cloud)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--radar", required=True)
    ap.add_argument("--scope", required=True)
    ap.add_argument("--cap", type=int, default=4000)
    args = ap.parse_args()

    with get_connection() as conn:
        conn.execute("SET statement_timeout = 30000")
        sc = conn.execute(
            "SELECT s.slug, s.label, s.include_terms, s.exclude_terms, s.selector,"
            " s.query_text, s.phrase, s.cluster_run_id, s.cluster_idx, s.meta "
            "FROM radar_scopes s JOIN radar_configs c ON c.id = s.config_id "
            "WHERE c.slug = %s AND s.slug = %s", (args.radar, args.scope)).fetchone()
        if not sc:
            print(json.dumps({"error": "unknown_scope"}))
            return 0
        rows = resolve_scope(conn, dict(sc))
        cloud = signal_cloud(rows, today=date.today(),
                             field_terms=scope_field_terms(dict(sc)),
                             cap=max(200, min(args.cap, 8000)))
        cloud["label"] = sc["label"]
    print(json.dumps(cloud, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
