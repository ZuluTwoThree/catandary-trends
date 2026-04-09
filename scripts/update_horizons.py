"""Update horizon field in mega_trends.yaml with more realistic estimates."""
from pathlib import Path
import yaml

YAML = Path(__file__).resolve().parents[1] / "mega_trends.yaml"

# Realistic structural horizon for each mega-trend (years until it is fully
# expressed / no longer a "trend" but the new normal). Shorter means faster
# moving / already mostly here; longer means deep systemic shift.
HORIZONS = {
    "artificial_intelligence_and_automation": "10-20 years",
    "personalized_health_and_longevity": "10-20 years",
    "clean_energy_transition": "20-30 years",
    "electric_and_autonomous_mobility": "10-20 years",
    "financial_innovation_and_inclusion": "5-15 years",
    "new_luxury_and_premiumization": "5-10 years",
    "regenerative_design_and_net_positive": "15-25 years",
    "inclusive_and_human_centric_design": "10-20 years",
    "future_of_food_and_agriculture": "10-20 years",
    "connected_living_and_smart_spaces": "5-15 years",
    "creator_economy_and_platform_shift": "5-10 years",
    "bio_revolution_and_new_materials": "15-25 years",
    "circular_economy_and_zero_waste": "15-25 years",
    "climate_resilience_and_adaptation": "20-30 years",
    "experience_economy_and_immersive_design": "5-10 years",
    "cultural_heritage_and_identity": "5-10 years",
    "urban_transformation_and_smart_cities": "20-30 years",
    "digital_trust_and_data_sovereignty": "10-20 years",
    "modular_and_adaptive_systems": "10-20 years",
    "mental_health_and_neuro_wellness": "5-15 years",
    "wearable_technology_and_augmented_living": "5-15 years",
    "virtual_worlds_consolidation": "3-7 years",
    "geopolitical_disruption_and_supply_chain_resilience": "5-10 years",
}

data = yaml.safe_load(YAML.read_text(encoding="utf-8"))
for mt in data["mega_trends"]:
    new = HORIZONS.get(mt["key"])
    if new:
        mt["horizon"] = new
YAML.write_text(yaml.dump(data, allow_unicode=True, sort_keys=False, width=100), encoding="utf-8")
print("Horizons updated.")
