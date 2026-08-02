#!/usr/bin/env python3
"""Cluster-Radare: aus einem Foresight-Lauf wird ein Horizont-Radar.

Warum dieser Weg die getippte Query ersetzt (Owner-Entscheidung 2026-08-02):

Eine Freitext-Query definiert ihr Feld über WÖRTER. Das hat zwei Mängel, die in
der Nutzerprobe beide auftraten. Erstens trennt sie schlecht — „solid state
battery" und „sodium ion battery" teilen Vokabular, ihre Punkte lagen dicht
beieinander und unterschieden zu wenig. Zweitens ist die Zusammensetzung des
Felds für den Leser nicht nachvollziehbar: welche Signale die Query eingesammelt
hat, sieht man erst, wenn man eine Zelle öffnet, und die fünf Belege dort sind
die Auslöser eines Gates, nicht eine Beschreibung des Felds.

Ein Cluster hat beide Eigenschaften umgekehrt. Es ist über die Lage im
Embedding-Raum definiert, also **disjunkt zu seinen Nachbarn** — Trennung ist
Konstruktionsprinzip, nicht Zufall. Und es bringt seine eigene Definition mit:
die fünf zentralsten Signale (`rep_titles`) SIND das Feld, ohne Umweg über eine
Gate-Begründung.

Dazu kommt, was der Cluster-Lauf ohnehin schon rechnet und das Radar bisher
nicht hatte: `momentum` und `sov_delta_pp` — steigender oder fallender Anteil am
Signalaufkommen. Die Richtungsachse war der größte Mangel der Nutzerprobe.

Bau:
    Ein Foresight-Lauf (`foresight_runs`, ein Scope) wird eine radar_configs-
    Zeile; jedes seiner Cluster ein radar_scopes-Eintrag mit
    `selector='cluster'`. Danach rechnet `radar_horizons.compute()` unverändert
    weiter — dieselben Zellen, dieselben Readouts, dieselbe Delta-Historie.
    Der Cluster-Pfad fügt der Engine nichts hinzu, er füllt sie nur anders.

    python -m pipeline.radar_clusters --scope vertical:FOOD
    python -m pipeline.radar_clusters --all
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys

from .db import get_connection
from .radar_horizons import compute, migrate

log = logging.getLogger("radar_clusters")

# Ein Radar zeigt die größten Cluster eines Laufs. Darüber wird der Bogen
# unlesbar, und die kleinen Cluster eines Laufs sind ohnehin meist Restmengen.
MAX_FIELDS = 8
# Cluster unter dieser Größe tragen keine Jurisdiktions-Aussage.
MIN_CLUSTER_SIZE = 300

# Signalgattungen statt Technologien: die Clusterung erzeugt gelegentlich einen
# Eimer für "Finanzierungsrunden" oder "Konferenzankündigungen". Das ist ein
# bekannter Defekt der Zerlegung (docs/radar_redesign_proposal.md §1.3), und ein
# Radar über "Venture Capital · Funding Round" ist keine Aussage über eine
# Technologie. Sie werden ausgeschlossen, nicht stillschweigend eingeordnet.
GENRE_LABEL = re.compile(
    r"\b(venture capital|funding round|investment|ipo|merger|acquisition|"
    r"conference|award|event|press release|earnings|quarterly|market research|"
    r"job|hiring|obituary|opinion|editorial|"
    # Disziplinen und Prozesse statt Technologien. Der erste FOOD-Cluster-Lauf
    # setzte „Food Safety · Regulatory Approval" (EFSA-Futtermittelgutachten) auf
    # TRL 8-9 — für einen Begutachtungsstrom, für den ein Reifegrad keine
    # Bedeutung hat. Gemessen trennt weder Patentanteil (0,89! höher als
    # Plant-Based Meat mit 0,19) noch Vertikalenfokus; das Label selbst ist das
    # verlässlichste Merkmal.
    r"regulatory approval|food safety|food security|water security|"
    r"health equity|health disparities|healthcare access|healthcare costs?|"
    r"health outcomes?|patient care|"
    r"public health|policy|regulation|compliance|certification|standards?|"
    r"science|research|academia|education|"
    r"sustainability|climate change|circular economy|"
    r"supply chain|logistics|operations|management|strategy|leadership|"
    r"marketing|branding|consumer behaviou?r|retail trends?|"
    r"innovation|digital transformation|business model)\b", re.I)

# KEINE Schwelle auf den Anteil angewandter Signale. Als Filter ausprobiert und
# verworfen: er warf „Offshore Wind · Renewables" (4 % angewandt) hinaus — ein
# 92-GW-Industriezweig. Genau derselbe Fehlschluss, den die Technologie-Dimension
# schon einmal machte: in forschungsnahen Feldern misst der Anteil die
# Publikationsdichte, nicht die Reife. Die Zusammensetzung wird deshalb ANGEZEIGT
# und nicht zum Ausschlusskriterium gemacht.


def field_part(label: str) -> str | None:
    """Der Teil eines Cluster-Labels, der ein FELD benennt — oder None.

    Labels sind zweiteilig („Climate Policy · Renewables"). Ein Cluster nur
    deshalb zu verwerfen, weil EIN Teil eine Disziplin ist, kostete im ersten
    Lauf „Renewables", „Cancer Treatment" und „Circular Economy" — allesamt
    Felder. Verworfen wird erst, wenn KEIN Teil ein Feld benennt; angezeigt wird
    dann der Teil, der eines ist.
    """
    parts = [x.strip() for x in re.split(r"[·|]", label or "") if x.strip()]
    fields = [x for x in parts if not GENRE_LABEL.search(x)]
    if not fields:
        return None
    return " · ".join(fields)


def _composition(conn, run_id: int, cluster_idx: int) -> dict:
    """Signalzusammensetzung eines Clusters — sein Charakter in vier Zahlen."""
    rows = conn.execute(
        "SELECT t.trend_signal_type AS ty, count(*) AS n "
        "FROM foresight_cluster_members m JOIN trends t ON t.id = m.trend_id "
        "WHERE m.run_id = %s AND m.cluster_idx = %s GROUP BY t.trend_signal_type",
        (run_id, cluster_idx)).fetchall()
    by = {r["ty"]: r["n"] for r in rows}
    n = max(sum(by.values()), 1)
    return {
        "applied": round((by.get("product_launch", 0)
                          + by.get("partnership", 0)) / n, 3),
        "research": round((by.get("research", 0) + by.get("patent", 0)) / n, 3),
        "regulation": round(by.get("regulation", 0) / n, 3),
        "n": n,
    }


def scope_title(scope: str) -> tuple[str, str]:
    """Anzeigename und Umschreibung eines Scopes.

    `mega:clean_energy_transition` ist ein Schlüssel, kein Titel — ungefiltert
    stand im Frontend „Mega:Clean_Energy_Transition · Trend clusters".
    """
    if scope.startswith("mega:"):
        key = scope.split(":", 1)[1].replace("_", " ")
        title = " ".join(w.capitalize() if w not in ("and", "of", "the") else w
                         for w in key.split())
        return title, f"{title} mega-trend"
    if scope.startswith("vertical:"):
        v = scope.split(":", 1)[1]
        return v.title(), f"{v} signal space"
    return "Cross-industry", "whole corpus"


def scope_slug(scope: str) -> str:
    return "cl-" + re.sub(r"[^a-z0-9]+", "-", scope.lower()).strip("-")


def build(scope: str, *, max_fields: int = MAX_FIELDS,
          run_compute: bool = True) -> str | None:
    """Radar-Konfiguration für den jüngsten Lauf eines Scopes anlegen/auffrischen."""
    migrate()
    with get_connection() as conn:
        run = conn.execute(
            "SELECT id, scope, tier, signals, k FROM foresight_runs "
            "WHERE scope = %s ORDER BY id DESC LIMIT 1", (scope,)).fetchone()
        if not run:
            log.warning("kein Foresight-Lauf für Scope %r", scope)
            return None

        n_members = conn.execute(
            "SELECT count(*) AS n FROM foresight_cluster_members WHERE run_id = %s",
            (run["id"],)).fetchone()["n"]
        if not n_members:
            log.warning("Lauf %d hat keine gespeicherte Mitgliedschaft — "
                        "`pipeline.foresight_snapshot` erneut laufen lassen",
                        run["id"])
            return None

        clusters = conn.execute(
            "SELECT cluster_idx, label, size, cohesion, momentum, sov_delta_pp, "
            "       rep_titles, top_tags, mega_trend "
            "FROM foresight_clusters WHERE run_id = %s ORDER BY size DESC",
            (run["id"],)).fetchall()

        picked = []
        seen_keys: list[frozenset] = []
        for c in clusters:
            if c["size"] < MIN_CLUSTER_SIZE:
                continue
            field = field_part(c["label"] or "")
            if not field:
                log.info("übersprungen (nur Disziplin/Gattung): %r", c["label"])
                continue
            # Dubletten: nach dem Abtrennen der Disziplinen fallen Labels
            # zusammen — ECO lieferte „Renewables", „Renewables · Solar Energy",
            # „Solar Energy · Renewables" und „Offshore Wind · Renewables"
            # nebeneinander. Ein Radar mit vier Mal demselben Feld unterscheidet
            # nichts. Es gewinnt das GRÖSSERE Cluster (die Liste ist nach Größe
            # sortiert), spätere Wiederholungen fallen weg.
            key = frozenset(re.findall(r"[a-z]{4,}", field.lower()))
            if any(key <= s or s <= key for s in seen_keys):
                log.info("übersprungen (Dublette zu einem größeren Cluster): %r",
                         field)
                continue
            seen_keys.append(key)
            mix = _composition(conn, run["id"], c["cluster_idx"])
            picked.append((dict(c, label=field), mix))
            if len(picked) >= max_fields:
                break
        if not picked:
            log.warning("Lauf %d: kein verwertbares Cluster", run["id"])
            return None

        slug = scope_slug(scope)
        pretty, kind_word = scope_title(scope)
        name = f"{pretty} · Trend clusters"
        desc = (
            f"The {len(picked)} largest trend clusters of the {kind_word}, found "
            f"by grouping {run['signals']:,} embedded signals — not by a search "
            "term. Each field carries its own defining signals and its "
            "share-of-voice trend."
        )
        row = conn.execute("SELECT id FROM radar_configs WHERE slug = %s",
                           (slug,)).fetchone()
        regions = ["US", "EU", "GLOBAL"]
        if row:
            cfg_id = row["id"]
            conn.execute(
                "UPDATE radar_configs SET name=%s, description=%s, regions=%s, "
                "kind=%s, regulated=%s WHERE id=%s",
                (name, desc, json.dumps(regions), "cluster", False, cfg_id))
            conn.execute("DELETE FROM radar_scopes WHERE config_id=%s", (cfg_id,))
        else:
            cfg_id = conn.execute(
                "INSERT INTO radar_configs (slug, name, description, dimension_set,"
                " regions, window_months, regulated, kind) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                (slug, name, desc, "strategic", json.dumps(regions), 48, False,
                 "cluster")).fetchone()["id"]

        for i, (c, mix) in enumerate(picked):
            reps = c["rep_titles"] if isinstance(c["rep_titles"], list) \
                else json.loads(c["rep_titles"] or "[]")
            tags = c["top_tags"] if isinstance(c["top_tags"], list) \
                else json.loads(c["top_tags"] or "[]")
            conn.execute(
                "INSERT INTO radar_scopes (config_id, slug, label, include_terms,"
                " exclude_terms, sort_order, selector, cluster_run_id, cluster_idx,"
                " meta) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (cfg_id, f"c{c['cluster_idx']}", c["label"], json.dumps([]),
                 json.dumps([]), i, "cluster", run["id"], c["cluster_idx"],
                 json.dumps({
                     # Was das Feld IST — sichtbar, ohne eine Zelle zu öffnen.
                     "rep_titles": reps[:5],
                     "top_tags": tags[:8],
                     "size": c["size"],
                     "cohesion": c["cohesion"],
                     # Die Richtungsachse, die dem Radar bisher fehlte.
                     "momentum": c["momentum"],
                     "sov_delta_pp": c["sov_delta_pp"],
                     "mega_trend": c["mega_trend"],
                     "foresight_run": run["id"],
                     "scope": scope,
                     # Woraus das Cluster besteht — sichtbar im Frontend, damit
                     # ein Leser einen Produktstrom von einem Forschungsstrom
                     # unterscheiden kann, ohne eine Zelle zu öffnen.
                     "composition": mix,
                 })))
        conn.commit()
    log.info("Radar %r: %d Cluster aus Lauf %d", slug, len(picked), run["id"])
    if run_compute:
        compute(slug)
    return slug


def main() -> int:
    ap = argparse.ArgumentParser(description="Cluster-Radare bauen")
    ap.add_argument("--scope", default=None)
    ap.add_argument("--all", action="store_true",
                    help="jeden Scope mit gespeicherter Mitgliedschaft")
    ap.add_argument("--max-fields", type=int, default=MAX_FIELDS)
    ap.add_argument("--no-compute", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    scopes: list[str]
    if args.all:
        with get_connection() as conn:
            scopes = [r["scope"] for r in conn.execute(
                "SELECT DISTINCT fr.scope FROM foresight_runs fr "
                "JOIN foresight_cluster_members m ON m.run_id = fr.id "
                "ORDER BY fr.scope").fetchall()]
    elif args.scope:
        scopes = [args.scope]
    else:
        ap.error("--scope oder --all")
        return 2

    built = 0
    for s in scopes:
        if build(s, max_fields=args.max_fields, run_compute=not args.no_compute):
            built += 1
    log.info("%d von %d Cluster-Radaren gebaut", built, len(scopes))
    return 0


if __name__ == "__main__":
    sys.exit(main())
