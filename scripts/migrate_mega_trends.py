#!/usr/bin/env python3
"""One-time migration: Map 627 fragmented mega-trend labels to 21 canonical keys.

Uses keyword matching with priority ordering. Labels that don't match
any pattern are set to NULL (to be reviewed by the monthly reviewer).

Usage:
    python scripts/migrate_mega_trends.py --dry-run   # Preview changes
    python scripts/migrate_mega_trends.py              # Apply changes
"""

import re
import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "catandary.db"

# Mapping rules: ordered list of (pattern, canonical_key).
# First match wins — order matters! More specific patterns first.
# Patterns are matched against the lowercase mega-trend label.
MAPPING_RULES = [
    # --- AI & Automation (broadest tech mega-trend) ---
    (r"ai[_\s-](?:in|driven|powered|agent|tool|assistant|platform|innovation|content|security|governance|hardware|workspace|education|democratization)", "artificial_intelligence_and_automation"),
    (r"ai[_\s-]and[_\s-]", "artificial_intelligence_and_automation"),
    (r"automated|automation|autonomous(?!.*mobil)", "artificial_intelligence_and_automation"),
    (r"^ai[_\s]", "artificial_intelligence_and_automation"),
    (r"machine.?learning|deep.?learning|generative.?ai|llm|chatbot", "artificial_intelligence_and_automation"),
    (r"robot(?:ic|s)", "artificial_intelligence_and_automation"),
    (r"smart[_\s-](?:factory|manufacturing|industrial|productivity|edge)", "artificial_intelligence_and_automation"),
    (r"enterprise[_\s-]ai", "artificial_intelligence_and_automation"),
    (r"industrial[_\s-]ai", "artificial_intelligence_and_automation"),
    (r"neuro[_\s-]verification", "artificial_intelligence_and_automation"),
    (r"cloud[_\s-]resilience|cloud[_\s-]native", "artificial_intelligence_and_automation"),

    # --- Circular Economy & Zero Waste ---
    (r"circular[_\s-](?:economy|design|architecture|construction)", "circular_economy_and_zero_waste"),
    (r"zero[_\s-]waste|waste[_\s-]reduction", "circular_economy_and_zero_waste"),
    (r"reversible[_\s-](?:architecture|design)", "circular_economy_and_zero_waste"),
    (r"recycl|upcycl|repurpos", "circular_economy_and_zero_waste"),
    (r"sustainable[_\s-]packag", "circular_economy_and_zero_waste"),

    # --- Personalized Health & Longevity ---
    (r"personalized[_\s-](?:health|medicine|healthcare|nutrition|wellness|beauty)", "personalized_health_and_longevity"),
    (r"precision[_\s-](?:medicine|nutrition|health)", "personalized_health_and_longevity"),
    (r"longevity|anti[_\s-]aging|aging[_\s-]population", "personalized_health_and_longevity"),
    (r"digital[_\s-]health|healthtech|health[_\s-]tech", "personalized_health_and_longevity"),
    (r"healthcare[_\s-](?:ai|automation|access|logistics|remodel|standardization)", "personalized_health_and_longevity"),
    (r"health[_\s-](?:and|driven|focused|conscious|aware|technology)", "personalized_health_and_longevity"),
    (r"biomimetic[_\s-]healthcare", "personalized_health_and_longevity"),
    (r"wellness[_\s-](?:tech|auto|innov|community|economy|and)", "personalized_health_and_longevity"),

    # --- Climate Resilience & Adaptation ---
    (r"climate[_\s-](?:resilien|adapt|smart|solution|intelligence|finance)", "climate_resilience_and_adaptation"),
    (r"flood|drought|heat[_\s-](?:adapt|island)", "climate_resilience_and_adaptation"),
    (r"water[_\s-]sensitive|rainwater", "climate_resilience_and_adaptation"),
    (r"post[_\s-]disaster|disaster[_\s-]resilien", "climate_resilience_and_adaptation"),

    # --- Clean Energy Transition ---
    (r"clean[_\s-]energy|green[_\s-]energy|renewable|solar|wind[_\s-](?:energy|power)", "clean_energy_transition"),
    (r"energy[_\s-]transition|decarboni", "clean_energy_transition"),
    (r"green[_\s-](?:hydrogen|tech|shipping|maritime|logistics|mobility|city|urban)", "clean_energy_transition"),
    (r"global[_\s-]energy[_\s-]transition", "clean_energy_transition"),
    (r"carbon[_\s-]captur", "clean_energy_transition"),
    (r"electric[_\s-](?:vehicle|mobility|and)", "electric_and_autonomous_mobility"),
    (r"smart[_\s-](?:mobility|sustainable[_\s-]mobil)|autonomous[_\s-]mobil", "electric_and_autonomous_mobility"),

    # --- Bio-Revolution & New Materials ---
    (r"bio[_\s-]?(?:revolution|tech|based|materials|mimicry|feedback|psycho)", "bio_revolution_and_new_materials"),
    (r"mycelium|algae|cellulose|biomaterial|synthetic[_\s-]biology", "bio_revolution_and_new_materials"),
    (r"lab[_\s-]grown|cell[_\s-]cultivat", "bio_revolution_and_new_materials"),
    (r"material[_\s-](?:driven|innov)", "bio_revolution_and_new_materials"),
    (r"sustainable[_\s-]material(?!.*packag)", "bio_revolution_and_new_materials"),

    # --- Connected Living & Smart Spaces ---
    (r"smart[_\s-](?:home|kitchen|cooking|living|house|appliance|audio|sustainable[_\s-](?:home|living))", "connected_living_and_smart_spaces"),
    (r"connected[_\s-](?:home|kitchen|wearable|content)", "connected_living_and_smart_spaces"),
    (r"home[_\s-]automation|iot|ambient", "connected_living_and_smart_spaces"),
    (r"smart[_\s-](?:grocery|food[_\s-](?:supply|safety|processing))", "connected_living_and_smart_spaces"),
    (r"electrification[_\s-]of[_\s-]home", "connected_living_and_smart_spaces"),

    # --- Experience Economy & Immersive Design ---
    (r"experience[_\s-]|experiential[_\s-]|immersive", "experience_economy_and_immersive_design"),
    (r"sensory[_\s-](?:brand|wellness|technology|enhanced|nostalgic|design)", "experience_economy_and_immersive_design"),
    (r"pop[_\s-]culture|interactive[_\s-]food", "experience_economy_and_immersive_design"),
    (r"temporary[_\s-]architect", "experience_economy_and_immersive_design"),

    # --- Cultural Heritage & Identity ---
    (r"cultural[_\s-](?:fusion|storytelling|renewal|branding|brand|heritage|curation|cuisine|crossover|archetype|sustain|luxury)", "cultural_heritage_and_identity"),
    (r"heritage|artisan|craft|place[_\s-]based|regional[_\s-]identity", "cultural_heritage_and_identity"),
    (r"nostalg|retro[_\s-]", "cultural_heritage_and_identity"),
    (r"k[_\s-]beauty|ethnic[_\s-]root", "cultural_heritage_and_identity"),

    # --- Inclusive & Human-Centric Design ---
    (r"inclusive[_\s-]|universal[_\s-]design|assistive", "inclusive_and_human_centric_design"),
    (r"human[_\s-]centric|child[_\s-]centric|gender[_\s-](?:equity|fluid|specific)", "inclusive_and_human_centric_design"),
    (r"play[_\s-]as[_\s-]|playful[_\s-](?:design|education)", "inclusive_and_human_centric_design"),
    (r"blurring[_\s-]borders|social[_\s-](?:justice|mobility)", "inclusive_and_human_centric_design"),
    (r"celebrating[_\s-]motherhood", "inclusive_and_human_centric_design"),

    # --- Future of Food & Agriculture ---
    (r"(?:alternative|clean|plant[_\s-]based)[_\s-]protein", "future_of_food_and_agriculture"),
    (r"functional[_\s-](?:food|snack)", "future_of_food_and_agriculture"),
    (r"food[_\s-](?:tech|innovation|customiz|traceab|replicat|system)", "future_of_food_and_agriculture"),
    (r"foodtech|agri[_\s-]?tech|precision[_\s-]agriculture|regenerative[_\s-]agriculture", "future_of_food_and_agriculture"),
    (r"(?:novel|healthy|affordable)[_\s-]food", "future_of_food_and_agriculture"),
    (r"sustainable[_\s-]food|sustainable[_\s-]farm|sustainable[_\s-](?:protein|beverage|distill|infra.*food)", "future_of_food_and_agriculture"),
    (r"culinary[_\s-](?:experiment|automation)", "future_of_food_and_agriculture"),
    (r"snack(?:ing|ification)", "future_of_food_and_agriculture"),
    (r"coffee[_\s-]2|home[_\s-]coffee", "future_of_food_and_agriculture"),
    (r"flavor[_\s-]sustain|sweet[_\s-](?:savory|heat)", "future_of_food_and_agriculture"),
    (r"(?:health|wellness)[_\s-](?:driven[_\s-])?(?:dairy|beverage|food)", "future_of_food_and_agriculture"),
    (r"clean[_\s-](?:eating|label|food)", "future_of_food_and_agriculture"),
    (r"food[_\s-]beauty[_\s-]crossover", "future_of_food_and_agriculture"),
    (r"portion[_\s-]control|space[_\s-]food|on[_\s-]demand[_\s-]food", "future_of_food_and_agriculture"),
    (r"metaverse[_\s-]food|digital[_\s-](?:food|culinary|dining|gamification.*food)", "future_of_food_and_agriculture"),
    (r"social[_\s-]dining|fast[_\s-]casual", "future_of_food_and_agriculture"),
    (r"convenience[_\s-]food|uber.*food|disruption.*grocery", "future_of_food_and_agriculture"),
    (r"sustainable[_\s-](?:superfoods|water[_\s-](?:tech|innov))", "future_of_food_and_agriculture"),
    (r"(?:web3|pop[_\s-]culture|entertainment)[_\s-](?:in[_\s-])?food", "future_of_food_and_agriculture"),
    (r"confectionery|sensory[_\s-].*food|carbon[_\s-]capturing[_\s-]food", "future_of_food_and_agriculture"),
    (r"regulatory[_\s-](?:shift|barrier|evolution).*food", "future_of_food_and_agriculture"),
    (r"(?:ethical|seasonal)[_\s-]food", "future_of_food_and_agriculture"),
    (r"(?:automated|instant)[_\s-](?:food[_\s-]service|culinary|commerce)", "future_of_food_and_agriculture"),

    # --- Creator Economy & Platform Shift ---
    (r"creator[_\s-]|content[_\s-](?:driven|monetiz|ecosystem|consumption)", "creator_economy_and_platform_shift"),
    (r"platform[_\s-](?:monetiz|content|economy|shift)", "creator_economy_and_platform_shift"),
    (r"streaming|social[_\s-]media[_\s-]monetiz", "creator_economy_and_platform_shift"),
    (r"financialization[_\s-]of[_\s-]content", "creator_economy_and_platform_shift"),
    (r"digital[_\s-](?:media[_\s-]transform|content[_\s-]monetiz|puzzle|native[_\s-]gaming)", "creator_economy_and_platform_shift"),
    (r"gaming[_\s-](?:industry|entertainment|convergence)", "creator_economy_and_platform_shift"),

    # --- New Luxury & Premiumization ---
    (r"luxury[_\s-](?:democrat|meets|custom|brand|material|eco|design|coastal|resort|mobility|spirits|seasonal|beauty|audio|sportswear|equestrian|revival|technology|wellness)", "new_luxury_and_premiumization"),
    (r"premiumiz|quiet[_\s-]luxury|scented[_\s-]luxury", "new_luxury_and_premiumization"),
    (r"status[_\s-]symbol", "new_luxury_and_premiumization"),
    (r"(?:sustainable|inclusive)[_\s-]luxury", "new_luxury_and_premiumization"),

    # --- Modular & Adaptive Systems ---
    (r"modular[_\s-](?:design|architect|furniture|playground)", "modular_and_adaptive_systems"),
    (r"adaptive[_\s-](?:space|reuse|design)", "modular_and_adaptive_systems"),
    (r"flexible[_\s-](?:workspace|space)", "modular_and_adaptive_systems"),
    (r"design[_\s-](?:driven[_\s-]workspace|kit)", "modular_and_adaptive_systems"),
    (r"modern[_\s-]office[_\s-]design", "modular_and_adaptive_systems"),

    # --- Urban Transformation & Smart Cities ---
    (r"urban[_\s-](?:transform|develop|design|sustain|living|luxury|redevelop|food|electric)", "urban_transformation_and_smart_cities"),
    (r"smart[_\s-]city|smart[_\s-](?:energy|deliver|logistic|retail|construction)", "urban_transformation_and_smart_cities"),
    (r"public[_\s-]space|civic[_\s-]design", "urban_transformation_and_smart_cities"),
    (r"tiny[_\s-]home|micro[_\s-]domicile|housing[_\s-](?:crisis|access)", "urban_transformation_and_smart_cities"),
    (r"last[_\s-]mile|sustainable[_\s-](?:housing|urban|living[_\s-]access)", "urban_transformation_and_smart_cities"),

    # --- Financial Innovation & Inclusion ---
    (r"fin(?:tech|ancial)[_\s-](?:innov|disrupt|inclus|transform|regul|service|technology)", "financial_innovation_and_inclusion"),
    (r"embedded[_\s-]finance|digital[_\s-](?:bank|currency|finance)", "financial_innovation_and_inclusion"),
    (r"decentralized[_\s-](?:financ|econom|global)", "financial_innovation_and_inclusion"),
    (r"shared[_\s-]profit|subscription[_\s-]economy", "financial_innovation_and_inclusion"),
    (r"(?:instant|metaverse)[_\s-]commerce", "financial_innovation_and_inclusion"),

    # --- Mental Health & Neuro-Wellness ---
    (r"mental[_\s-](?:health|wellness)", "mental_health_and_neuro_wellness"),
    (r"neuro[_\s-](?:driven|wellness)", "mental_health_and_neuro_wellness"),
    (r"self[_\s-]care|mindfulness|biofeedback[_\s-]wellness", "mental_health_and_neuro_wellness"),
    (r"sleep[_\s-]wellness", "mental_health_and_neuro_wellness"),

    # --- Regenerative Design & Net Positive ---
    (r"regenerat|restorative|net[_\s-]positive", "regenerative_design_and_net_positive"),
    (r"sustainable[_\s-](?:architect|design|build|interior|tech[_\s-]design|fashion|beauty|skin|retail|dental|lodging|travel|consumption|energy[_\s-](?:innov|access))", "regenerative_design_and_net_positive"),
    (r"eco[_\s-](?:design|luxury|education|friendly)", "regenerative_design_and_net_positive"),
    (r"green[_\s-]architect", "regenerative_design_and_net_positive"),
    (r"sustainable[_\s-](?:military|supply|distill)", "regenerative_design_and_net_positive"),
    (r"sustainable[_\s-](?:innovation$|living$|luxury[_\s-](?:spirit|fashion))", "regenerative_design_and_net_positive"),
    (r"^sustainable[_\s-](?:design|architect|fashion|beauty|energy|retail|living|baby|interior)", "regenerative_design_and_net_positive"),
    (r"scandinavian[_\s-]sustain", "regenerative_design_and_net_positive"),

    # --- Electric & Autonomous Mobility ---
    (r"electric[_\s-]|ev[_\s-]|autonomous[_\s-](?:mobil|vehic|driving)", "electric_and_autonomous_mobility"),
    (r"shared[_\s-]mobility|mobility[_\s-]as[_\s-]service", "electric_and_autonomous_mobility"),
    (r"design[_\s-]driven[_\s-]mobility", "electric_and_autonomous_mobility"),
    (r"automotive", "electric_and_autonomous_mobility"),

    # --- Wearable Technology & Augmented Living ---
    (r"wearable|smart[_\s-](?:glass|wearable|textile|fabric)", "wearable_technology_and_augmented_living"),
    (r"smart[_\s-]fashion|fashion[_\s-]tech", "wearable_technology_and_augmented_living"),
    (r"fitness[_\s-]tech", "wearable_technology_and_augmented_living"),
    (r"pet[_\s-]wellness[_\s-]tech", "wearable_technology_and_augmented_living"),
    (r"outdoor[_\s-]living[_\s-]tech", "wearable_technology_and_augmented_living"),

    # --- Digital Trust & Data Sovereignty ---
    (r"digital[_\s-](?:identity|trust)|data[_\s-](?:privacy|sovereign)", "digital_trust_and_data_sovereignty"),
    (r"privacy|cybersecur|ai[_\s-]governance", "digital_trust_and_data_sovereignty"),
    (r"legal[_\s-]tech|regulatory[_\s-](?:framework|evolution[^_])", "digital_trust_and_data_sovereignty"),

    # --- Catch patterns that span multiple ---
    (r"clean[_\s-]beauty|visible[_\s-]skincare|aesthetic[_\s-]renaissance|beauty[_\s-](?:and|evolution)", "personalized_health_and_longevity"),
    (r"(?:influencer|consumer)[_\s-]driven[_\s-](?:fashion|beauty)", "creator_economy_and_platform_shift"),
    (r"tech[_\s-](?:driven[_\s-]beauty|in[_\s-]beauty|disruption)", "artificial_intelligence_and_automation"),
    (r"(?:slow|sustainable)[_\s-]fashion", "regenerative_design_and_net_positive"),
    (r"fashion[_\s-](?:collabor|curation)", "new_luxury_and_premiumization"),
    (r"sports[_\s-](?:brand|fashion|and[_\s-]commun|wear)", "experience_economy_and_immersive_design"),
    (r"workwear|functional[_\s-]fashion|expressive[_\s-]beauty", "cultural_heritage_and_identity"),
    (r"(?:real[_\s-]time|domestic[_\s-]travel|global[_\s-](?:food|culinary|cultural|economic|cuisine|snack))", "experience_economy_and_immersive_design"),
    (r"store(?:less)?[_\s-]retail|retail[_\s-](?:auto|digital|transform)", "artificial_intelligence_and_automation"),
    (r"demographic|post[_\s-]pandemic", "experience_economy_and_immersive_design"),

    # --- Additional unmapped patterns ---
    (r"agricultural[_\s-]technology", "future_of_food_and_agriculture"),
    (r"celebrity[_\s-]driven", "new_luxury_and_premiumization"),
    (r"climate[_\s-]technology", "climate_resilience_and_adaptation"),
    (r"collaborative[_\s-]music", "creator_economy_and_platform_shift"),
    (r"consumer[_\s-]co[_\s-]creation", "creator_economy_and_platform_shift"),
    (r"decentralized[_\s-]energy", "clean_energy_transition"),
    (r"entertainment[_\s-](?:brand|industry)", "creator_economy_and_platform_shift"),
    (r"(?:food[_\s-]industry[_\s-]mergers|foodtech[_\s-]mergers)", "future_of_food_and_agriculture"),
    (r"functional[_\s-]sustain", "regenerative_design_and_net_positive"),
    (r"healthcare[_\s-]fashion", "wearable_technology_and_augmented_living"),
    (r"health(?:ier|ified)[_\s-](?:sweeten|indulg)", "future_of_food_and_agriculture"),
    (r"high[_\s-]fidelity[_\s-]audio", "connected_living_and_smart_spaces"),
    (r"luxury[_\s-]beverage", "new_luxury_and_premiumization"),
    (r"personali(?:z|s)(?:ation|ed)[_\s-](?:in[_\s-]accessor|food|olfact|value|beverage|luxury)", "personalized_health_and_longevity"),
    (r"plant[_\s-]based[_\s-](?:gourmet|food[_\s-]reg|nutrit)", "future_of_food_and_agriculture"),
    (r"regulatory[_\s-](?:fragment|evolution).*(?:health|suppl)", "digital_trust_and_data_sovereignty"),
    (r"seasonal[_\s-](?:consumer|fashion)", "experience_economy_and_immersive_design"),
    (r"self[_\s-]enhancement", "artificial_intelligence_and_automation"),
    (r"sensor(?:ial|y)[_\s-]skincare", "personalized_health_and_longevity"),
    (r"single[_\s-]serve[_\s-]coffee", "future_of_food_and_agriculture"),
    (r"skin[_\s-]enhancing", "personalized_health_and_longevity"),
    (r"soft[_\s-]texture[_\s-]interior", "bio_revolution_and_new_materials"),
    (r"sportswear[_\s-]meets", "experience_economy_and_immersive_design"),

    # --- Edge cases ---
    (r"innovation[_\s-]ecosystem", "artificial_intelligence_and_automation"),
    (r"(?:supply[_\s-]chain|smart[_\s-]sustainable[_\s-](?:logist|agric|fashion))", "regenerative_design_and_net_positive"),
    (r"(?:art|museum|design)[_\s-](?:as[_\s-]participation|galleries)", "cultural_heritage_and_identity"),
    (r"crime[_\s-]inspired|space[_\s-]pop|music[_\s-]as[_\s-]social", "creator_economy_and_platform_shift"),
    (r"next[_\s-]gen[_\s-]game|3d[_\s-]animation", "creator_economy_and_platform_shift"),
    (r"web[_\s-]design[_\s-]revolution|digital[_\s-](?:workflow|transformation[_\s-]in)", "artificial_intelligence_and_automation"),
    (r"upskilling|skill[_\s-]based|education", "inclusive_and_human_centric_design"),
    (r"workplace[_\s-]humor|brand[_\s-](?:ambiguity|personif)", "experience_economy_and_immersive_design"),
    (r"remote[_\s-]creative|future[_\s-]of[_\s-]work|tech[_\s-]layoff", "artificial_intelligence_and_automation"),
    (r"(?:blue|sustainable)[_\s-](?:economy)", "regenerative_design_and_net_positive"),
    (r"quantum|edge[_\s-](?:ai|comput)", "artificial_intelligence_and_automation"),
    (r"(?:travel|tourism)", "experience_economy_and_immersive_design"),
    (r"^wellness", "personalized_health_and_longevity"),
    (r"^sustainable", "regenerative_design_and_net_positive"),
    (r"^smart", "connected_living_and_smart_spaces"),
    (r"^digital", "artificial_intelligence_and_automation"),
    (r"^green", "clean_energy_transition"),
]


def map_mega_trend(old_label: str) -> str | None:
    """Map an old mega-trend label to a canonical key. Returns None if no match."""
    label = old_label.lower().strip()
    for pattern, canonical in MAPPING_RULES:
        if re.search(pattern, label):
            return canonical
    return None


def run_migration(dry_run: bool = False):
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    # Get all distinct mega-trend labels
    rows = conn.execute(
        "SELECT DISTINCT mega_trend FROM trends "
        "WHERE mega_trend IS NOT NULL AND mega_trend != ''"
    ).fetchall()

    old_labels = [r["mega_trend"] for r in rows]
    print(f"Found {len(old_labels)} distinct mega-trend labels to migrate.\n")

    mapped = 0
    unmapped = []
    mapping = {}  # old_label -> canonical_key

    for label in old_labels:
        canonical = map_mega_trend(label)
        if canonical:
            mapping[label] = canonical
            mapped += 1
        else:
            unmapped.append(label)

    print(f"Mapped: {mapped}/{len(old_labels)}")
    print(f"Unmapped: {len(unmapped)}")

    if unmapped:
        print(f"\nUnmapped labels (will be set to NULL):")
        for u in sorted(unmapped):
            print(f"  - {u}")

    # Count trends affected per canonical key
    print(f"\n{'Canonical Key':<50} {'Labels':>6}")
    print("-" * 60)
    canonical_counts = {}
    for old, new in mapping.items():
        cnt = conn.execute(
            "SELECT COUNT(*) as c FROM trends WHERE mega_trend = ?", (old,)
        ).fetchone()["c"]
        canonical_counts[new] = canonical_counts.get(new, 0) + cnt

    for key in sorted(canonical_counts, key=lambda k: -canonical_counts[k]):
        print(f"{key:<50} {canonical_counts[key]:>6}")

    null_count = 0
    for label in unmapped:
        cnt = conn.execute(
            "SELECT COUNT(*) as c FROM trends WHERE mega_trend = ?", (label,)
        ).fetchone()["c"]
        null_count += cnt
    print(f"{'-> NULL (unmapped)':<50} {null_count:>6}")

    if dry_run:
        print("\n[DRY RUN] No changes applied.")
        conn.close()
        return

    print("\nApplying migration...")

    # Update mapped labels
    for old, new in mapping.items():
        conn.execute(
            "UPDATE trends SET mega_trend = ? WHERE mega_trend = ?",
            (new, old),
        )

    # Set unmapped labels to NULL
    for label in unmapped:
        conn.execute(
            "UPDATE trends SET mega_trend = NULL WHERE mega_trend = ?",
            (label,),
        )

    conn.commit()
    conn.close()
    print("Migration complete.")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    run_migration(dry_run=dry_run)
