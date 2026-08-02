"""Referenz-Radar „Alternative Proteine" — der erste Horizont-Radar.

Bewusst handkuratiert: acht Technologiefelder mit expliziten Ein- und
Ausschlusstermen. Der Ausschluss ist nicht Kosmetik — ein naives
'%fermentation%' fängt traditionelle Lebensmittelfermentation, Silage- und
Futtermittelzusätze sowie EFSA-Gutachten zu Vitaminen mit ein und würde die
Einordnung sauber auf der falschen Menge berechnen
(docs/radar_redesign_proposal.md §6.4).

Dieses Radar ist der Prüfstein für die Methode: das Owner-Beispiel
(Precision Fermentation — technologisch H2, regulatorisch H3 in der EU,
Markt H1 in den USA/Israel) muss hier reproduzierbar herausfallen.
"""

from __future__ import annotations

import json
import logging

from .db import get_connection

log = logging.getLogger(__name__)

CONFIG = {
    "slug": "alt-protein",
    "name": "Alternative Proteine",
    "description": (
        "Acht Proteintechnologien entlang der Innovationskette, eingeordnet nach "
        "Handlungshorizont je Dimension und Jurisdiktion."
    ),
    "dimension_set": "strategic",
    # Lebensmittel sind eine regulierte Domäne: ohne Zulassung kein zulässiger
    # Markt. Koppelt die Markt-Dimension an die Regulatorik (siehe
    # radar_horizons.couple_market_to_regulation).
    "regulated": True,
    "regions": ["US", "EU", "UK", "IL", "GLOBAL"],
    "window_months": 48,
}

SCOPES: list[dict] = [
    {
        "slug": "precision-fermentation",
        "label": "Precision Fermentation",
        "include": [
            "%precision fermentation%", "%animal-free dairy%", "%animal free dairy%",
            "%recombinant whey%", "%recombinant casein%", "%animal-free whey%",
            "%fermentation-derived protein%", "%fermentation-made protein%",
            "%egg protein produced through%",
        ],
        "exclude": [
            "%silage%", "%feed additive%", "%vitamin b12%", "%cyanocobalamin%",
            "%citric acid%", "%steviol%",
        ],
    },
    {
        "slug": "cultivated-meat",
        "label": "Cultivated Meat",
        "include": [
            "%cultivated meat%", "%cultured meat%", "%lab-grown meat%",
            "%lab grown meat%", "%cell-based meat%", "%cultivated chicken%",
            "%cultivated seafood%", "%cultivated pork%", "%cellular agriculture%",
        ],
        "exclude": [],
    },
    {
        "slug": "mycoprotein",
        "label": "Mycoprotein / Pilz-Protein",
        "include": [
            "%mycoprotein%", "%mycelium protein%", "%fungal protein%",
            "%koji protein%", "%filamentous fungi%", "%mycelial%",
        ],
        "exclude": ["%mycelium leather%", "%mycelium packaging%"],
    },
    {
        "slug": "plant-based-meat",
        "label": "Plant-Based Meat",
        "include": [
            "%plant-based meat%", "%plant based meat%", "%meat alternative%",
            "%meat substitute%", "%vegan meat%", "%plant-based burger%",
            "%plant-based chicken%",
        ],
        "exclude": [],
    },
    {
        "slug": "insect-protein",
        "label": "Insekten-Protein",
        "include": [
            "%insect protein%", "%black soldier fly%", "%cricket protein%",
            "%insect farming%", "%edible insect%", "%mealworm%",
        ],
        "exclude": [],
    },
    {
        "slug": "algae-protein",
        "label": "Algen-Protein",
        "include": [
            "%microalgae%", "%algae protein%", "%algal protein%", "%spirulina%",
            "%chlorella%", "%seaweed protein%",
        ],
        "exclude": ["%algae biofuel%", "%algal bloom%"],
    },
    {
        "slug": "gas-fermentation",
        "label": "Gas-Fermentation (CO₂-zu-Protein)",
        "include": [
            "%gas fermentation%", "%co2-to-protein%", "%co2 to protein%",
            "%air protein%", "%hydrogenotrophic%", "%power-to-protein%",
            "%gas protein%",
        ],
        "exclude": [],
    },
    {
        "slug": "molecular-farming",
        "label": "Molecular Farming",
        "include": [
            "%molecular farming%", "%plant-made protein%", "%plant-made pharmaceutical%",
            "%plant molecular farming%", "%transgenic plant protein%",
        ],
        "exclude": [],
    },
]


# PESTEL-Zwilling: dieselben acht Felder, aber als PESTEL-Einordnung
# (P/E/S/T/En/L statt Technologie/Regulatorik/Markt/Adoption). Belegt die
# Mehr-Radar-Fähigkeit: gleiche Engine, anderes Dimensions-Set.
CONFIG_PESTEL = {
    **CONFIG,
    "slug": "alt-protein-pestel",
    "name": "Alternative Proteine · PESTEL",
    "description": (
        "Dieselben acht Proteintechnologien, eingeordnet entlang der sechs "
        "PESTEL-Dimensionen je Jurisdiktion."
    ),
    "dimension_set": "pestel",
    # regulated steuert seit 2026-08-02 auch, wie die L-Zelle ABWESENHEIT liest
    # (reguliert: fehlende Zulassung = blockiert). Lebensmittel sind
    # zulassungspflichtig, also True; die Markt↔L-Kopplung existiert im
    # PESTEL-Zweig ohnehin nicht.
    "regulated": True,
}


def seed() -> None:
    """Konfigurationen idempotent anlegen/aktualisieren."""
    for cfg in (CONFIG, CONFIG_PESTEL):
        _seed_one(cfg)


def _seed_one(CONFIG: dict) -> None:
    with get_connection() as conn:
        row = conn.execute("SELECT id FROM radar_configs WHERE slug = %s",
                           (CONFIG["slug"],)).fetchone()
        if row:
            cfg_id = row["id"]
            conn.execute(
                "UPDATE radar_configs SET name=%s, description=%s, dimension_set=%s, "
                "regions=%s, window_months=%s, regulated=%s WHERE id=%s",
                (CONFIG["name"], CONFIG["description"], CONFIG["dimension_set"],
                 json.dumps(CONFIG["regions"]), CONFIG["window_months"],
                 CONFIG["regulated"], cfg_id),
            )
        else:
            cfg_id = conn.execute(
                "INSERT INTO radar_configs (slug, name, description, dimension_set, "
                "regions, window_months, regulated) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                (CONFIG["slug"], CONFIG["name"], CONFIG["description"],
                 CONFIG["dimension_set"], json.dumps(CONFIG["regions"]),
                 CONFIG["window_months"], CONFIG["regulated"]),
            ).fetchone()["id"]

        for i, s in enumerate(SCOPES):
            exists = conn.execute(
                "SELECT id FROM radar_scopes WHERE config_id=%s AND slug=%s",
                (cfg_id, s["slug"]),
            ).fetchone()
            if exists:
                conn.execute(
                    "UPDATE radar_scopes SET label=%s, include_terms=%s, "
                    "exclude_terms=%s, sort_order=%s WHERE id=%s",
                    (s["label"], json.dumps(s["include"]), json.dumps(s["exclude"]),
                     i, exists["id"]),
                )
            else:
                conn.execute(
                    "INSERT INTO radar_scopes (config_id, slug, label, include_terms, "
                    "exclude_terms, sort_order) VALUES (%s,%s,%s,%s,%s,%s)",
                    (cfg_id, s["slug"], s["label"], json.dumps(s["include"]),
                     json.dumps(s["exclude"]), i),
                )
        conn.commit()
    log.info("Referenz-Radar %r mit %d Scopes angelegt", CONFIG["slug"], len(SCOPES))
