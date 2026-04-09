"""One-shot: enrich mega_trends.yaml with icon + description_de from the old
hard-coded frontend MEGA_TRENDS array. After this runs, mega_trends.yaml is the
single source of truth and frontend/src/lib/mega-trends.generated.ts is generated
from it. Safe to re-run — idempotent.
"""
from pathlib import Path
import yaml

YAML_PATH = Path(__file__).resolve().parents[1] / "mega_trends.yaml"

# icon + description_de snapshot extracted from frontend/src/lib/types.ts (2026-04-08)
ENRICH: dict[str, dict[str, str]] = {
    "artificial_intelligence_and_automation": {
        "icon": "🤖",
        "description_de": "KI/ML-Integration über alle Branchen — von generativer KI und Design-Tools bis zu industrieller Robotik und autonomen Systemen.",
    },
    "circular_economy_and_zero_waste": {
        "icon": "♻️",
        "description_de": "Geschlossene Produktionskreisläufe, Abfallvermeidung, Recycling-by-Design, reversible Architektur.",
    },
    "personalized_health_and_longevity": {
        "icon": "🧬",
        "description_de": "Präzisionsmedizin, digitale Therapeutika, individualisierte Ernährung, Langlebigkeitswissenschaft.",
    },
    "climate_resilience_and_adaptation": {
        "icon": "🌍",
        "description_de": "Systeme für den Klimawandel gestalten — hochwasserresistente Architektur, Hitzeanpassung, klimasmarte Landwirtschaft.",
    },
    "clean_energy_transition": {
        "icon": "⚡",
        "description_de": "Dekarbonisierung von Energie, Industrie und Verkehr — Erneuerbare, Energiespeicher, Netzmodernisierung.",
    },
    "bio_revolution_and_new_materials": {
        "icon": "🧫",
        "description_de": "Biotech-basierte Materialien, synthetische Biologie, Myzel/Algen-Produkte, lab-grown Alternativen, Biomimikry.",
    },
    "connected_living_and_smart_spaces": {
        "icon": "🏠",
        "description_de": "IoT-Ökosysteme, Smart Homes/Küchen/Büros, Ambient Computing, sensorgesteuerte Umgebungen.",
    },
    "experience_economy_and_immersive_design": {
        "icon": "✨",
        "description_de": "Physische Räume als Erlebnisplattformen — immersiver Retail, Erlebnis-Gastronomie, sensorische Umgebungen.",
    },
    "cultural_heritage_and_identity": {
        "icon": "🏛️",
        "description_de": "Revival von Handwerkstraditionen, kulturelle Fusion, ortsbasiertes Branding, indigenes Wissen.",
    },
    "inclusive_and_human_centric_design": {
        "icon": "♿",
        "description_de": "Universelle Barrierefreiheit, assistive Technologien, genderinklusive Produkte, Neurodiversität.",
    },
    "future_of_food_and_agriculture": {
        "icon": "🌾",
        "description_de": "Alternative Proteine, Präzisionslandwirtschaft, Vertical Farming, funktionale Lebensmittel, Food-as-Medicine.",
    },
    "creator_economy_and_platform_shift": {
        "icon": "📱",
        "description_de": "Content-Monetarisierung, Creator-Tools, dezentrale Medien, Plattformökonomie, digital-native Marken.",
    },
    "new_luxury_and_premiumization": {
        "icon": "💎",
        "description_de": "Luxus-Demokratisierung, Quiet Luxury, erlebnisorientiertes Premium, handwerkliche Positionierung.",
    },
    "modular_and_adaptive_systems": {
        "icon": "🧩",
        "description_de": "Rekonfigurierbare Architektur, modulare Möbel/Wohnungen, flexible Arbeitsbereiche, temporäre Strukturen.",
    },
    "urban_transformation_and_smart_cities": {
        "icon": "🏙️",
        "description_de": "Städte neu gestalten für Dichte, Lebensqualität und Nachhaltigkeit — öffentlicher Raum, smarte Infrastruktur.",
    },
    "financial_innovation_and_inclusion": {
        "icon": "💳",
        "description_de": "Fintech-Disruption, Embedded Finance, Digital Banking, dezentrale Finanzen, Finanzbildung.",
    },
    "mental_health_and_neuro_wellness": {
        "icon": "🧠",
        "description_de": "Mental-Health-Technologie, neurowissenschaftsbasierte Produkte, Stressmanagement, Achtsamkeitsplattformen.",
    },
    "regenerative_design_and_net_positive": {
        "icon": "🌿",
        "description_de": "Über Nachhaltigkeit hinaus — Designs die Ökosysteme aktiv wiederherstellen, regenerative Landwirtschaft.",
    },
    "electric_and_autonomous_mobility": {
        "icon": "🚗",
        "description_de": "Elektrofahrzeuge, autonomes Fahren, geteilte Mobilität, urbane Mikromobilität, Ladeinfrastruktur.",
    },
    "wearable_technology_and_augmented_living": {
        "icon": "⌚",
        "description_de": "Smart Wearables, Gesundheitsmonitoring, AR/VR, smarte Textilien, Gehirn-Computer-Schnittstellen.",
    },
    "digital_trust_and_data_sovereignty": {
        "icon": "🔒",
        "description_de": "Datenschutz, digitale Identität, KI-Governance, algorithmische Transparenz, Cybersicherheit.",
    },
    "geopolitical_disruption_and_supply_chain_resilience": {
        "icon": "🌐",
        "description_de": "Zoll-Auswirkungen, Handelskriege, Energiesicherheit, Lieferketten-Diversifizierung, Reshoring, geopolitisches Risiko, Sanktionen.",
    },
    "virtual_worlds_consolidation": {
        "icon": "🕶️",
        "description_de": "Rückzug und Konsolidierung von Social VR, Metaverse-Plattformen und Social Gaming nach dem Hype — Schließungen, Nostalgie-Revivals, Neudenken virtueller Räume.",
    },
}


def main():
    with open(YAML_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    trends = data.get("mega_trends", [])
    changed = 0
    for mt in trends:
        key = mt.get("key")
        extras = ENRICH.get(key)
        if not extras:
            print(f"WARN: no icon/description_de for {key}")
            continue
        if mt.get("icon") != extras["icon"]:
            mt["icon"] = extras["icon"]
            changed += 1
        if mt.get("description_de") != extras["description_de"]:
            mt["description_de"] = extras["description_de"]
            changed += 1

    with open(YAML_PATH, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, sort_keys=False, width=100)

    print(f"Enriched {len(trends)} mega-trends, {changed} field updates.")


if __name__ == "__main__":
    main()
