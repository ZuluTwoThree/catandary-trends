export type Vertical =
  | "FOOD" | "TECH" | "HEALTH" | "ECO" | "DESIGN"
  | "FASHION" | "BIZ" | "CULTURE" | "SOCIAL" | "LUXURY";

export type PestelDimension = "P" | "E" | "S" | "T" | "En" | "L";

export type TrendSignalType =
  | "product_launch" | "research" | "market_shift"
  | "consumer_behavior" | "regulation" | "funding"
  | "partnership" | "patent";

export interface Trend {
  id: number;
  raw_entry_id: number;
  title_en: string;
  title_de: string | null;
  slug: string;
  summary_en: string | null;
  summary_de: string | null;
  body_en: string | null;
  body_de: string | null;
  verticals: Vertical[];
  primary_vertical: Vertical;
  pestel: PestelDimension[];
  tags: string[];
  trend_signal_type: TrendSignalType;
  mega_trend: string | null;
  macro_trend: string | null;
  trend_level: "mega" | "macro" | "micro" | null;
  brands: string[];
  companies: string[];
  regions: string[];
  trend_score: number | null;
  confidence: number | null;
  source_url: string;
  source_name: string | null;
  source_date: string | null;
  source_type: "trade_media" | "press_wire" | "radar" | "brand" | "api" | null;
  status: "draft" | "review" | "published" | "rejected";
  auto_published: boolean;
  published_at: string | null;
  created_at: string;
}

export interface VerticalInfo {
  id: Vertical;
  label: string;
  color: string;
  icon: string;
}

export interface PestelInfo {
  id: PestelDimension;
  label: string;
  color: string;
}

export const VERTICALS: VerticalInfo[] = [
  { id: "FOOD", label: "Food & Beverage", color: "#f97316", icon: "🍽" },
  { id: "TECH", label: "Technology & AI", color: "#8b5cf6", icon: "💻" },
  { id: "HEALTH", label: "Health & Wellness", color: "#10b981", icon: "🏥" },
  { id: "ECO", label: "Sustainability", color: "#06b6d4", icon: "🌱" },
  { id: "DESIGN", label: "Design & Architecture", color: "#ec4899", icon: "🎨" },
  { id: "FASHION", label: "Fashion & Beauty", color: "#f43f5e", icon: "👗" },
  { id: "BIZ", label: "Business & Retail", color: "#3b82f6", icon: "📊" },
  { id: "CULTURE", label: "Culture & Media", color: "#a855f7", icon: "🎭" },
  { id: "SOCIAL", label: "Social Impact", color: "#22c55e", icon: "🤝" },
  { id: "LUXURY", label: "Luxury & Premium", color: "#eab308", icon: "✨" },
];

export const PESTEL: PestelInfo[] = [
  { id: "P", label: "Political", color: "#ef4444" },
  { id: "E", label: "Economic", color: "#3b82f6" },
  { id: "S", label: "Social", color: "#22c55e" },
  { id: "T", label: "Technological", color: "#8b5cf6" },
  { id: "En", label: "Environmental", color: "#06b6d4" },
  { id: "L", label: "Legal", color: "#f97316" },
];

export function getVerticalInfo(id: Vertical): VerticalInfo {
  return VERTICALS.find((v) => v.id === id) ?? VERTICALS[0];
}

export function getPestelInfo(id: PestelDimension): PestelInfo {
  return PESTEL.find((p) => p.id === id) ?? PESTEL[0];
}

export interface MegaTrendInfo {
  key: string;
  name_en: string;
  name_de: string;
  description_en: string;
  description_de: string;
  icon: string;
  verticals: Vertical[];
}

export const MEGA_TRENDS: MegaTrendInfo[] = [
  {
    key: "artificial_intelligence_and_automation",
    name_en: "Artificial Intelligence & Automation",
    name_de: "Künstliche Intelligenz & Automatisierung",
    description_en: "AI/ML integration across industries — from generative AI and design tools to industrial robotics and autonomous systems.",
    description_de: "KI/ML-Integration über alle Branchen — von generativer KI und Design-Tools bis zu industrieller Robotik und autonomen Systemen.",
    icon: "🤖",
    verticals: ["TECH", "BIZ", "HEALTH", "FOOD", "DESIGN", "CULTURE"],
  },
  {
    key: "circular_economy_and_zero_waste",
    name_en: "Circular Economy & Zero Waste",
    name_de: "Kreislaufwirtschaft & Zero Waste",
    description_en: "Closed-loop production systems, waste elimination, recyclability-by-design, reversible architecture.",
    description_de: "Geschlossene Produktionskreisläufe, Abfallvermeidung, Recycling-by-Design, reversible Architektur.",
    icon: "♻️",
    verticals: ["ECO", "DESIGN", "FASHION", "FOOD", "BIZ"],
  },
  {
    key: "personalized_health_and_longevity",
    name_en: "Personalized Health & Longevity",
    name_de: "Personalisierte Gesundheit & Langlebigkeit",
    description_en: "Precision medicine, digital therapeutics, individualized nutrition, longevity science, biomarker-driven optimization.",
    description_de: "Präzisionsmedizin, digitale Therapeutika, individualisierte Ernährung, Langlebigkeitswissenschaft.",
    icon: "🧬",
    verticals: ["HEALTH", "TECH", "FOOD", "FASHION"],
  },
  {
    key: "climate_resilience_and_adaptation",
    name_en: "Climate Resilience & Adaptation",
    name_de: "Klimaresilienz & Anpassung",
    description_en: "Designing systems for climate change impact — flood-resistant architecture, heat adaptation, climate-smart agriculture.",
    description_de: "Systeme für den Klimawandel gestalten — hochwasserresistente Architektur, Hitzeanpassung, klimasmarte Landwirtschaft.",
    icon: "🌍",
    verticals: ["ECO", "DESIGN", "FOOD", "SOCIAL"],
  },
  {
    key: "clean_energy_transition",
    name_en: "Clean Energy Transition",
    name_de: "Saubere Energiewende",
    description_en: "Decarbonization of energy, industry and transport — renewables, energy storage, grid modernization, carbon capture.",
    description_de: "Dekarbonisierung von Energie, Industrie und Verkehr — Erneuerbare, Energiespeicher, Netzmodernisierung.",
    icon: "⚡",
    verticals: ["ECO", "TECH", "BIZ", "SOCIAL"],
  },
  {
    key: "bio_revolution_and_new_materials",
    name_en: "Bio-Revolution & New Materials",
    name_de: "Bio-Revolution & Neue Materialien",
    description_en: "Biotech-derived materials, synthetic biology, mycelium/algae-based products, lab-grown alternatives, biomimicry.",
    description_de: "Biotech-basierte Materialien, synthetische Biologie, Myzel/Algen-Produkte, lab-grown Alternativen, Biomimikry.",
    icon: "🧫",
    verticals: ["ECO", "DESIGN", "FASHION", "FOOD", "HEALTH"],
  },
  {
    key: "connected_living_and_smart_spaces",
    name_en: "Connected Living & Smart Spaces",
    name_de: "Vernetztes Wohnen & Intelligente Räume",
    description_en: "IoT ecosystems, smart homes/kitchens/offices, ambient computing, sensor-driven environments.",
    description_de: "IoT-Ökosysteme, Smart Homes/Küchen/Büros, Ambient Computing, sensorgesteuerte Umgebungen.",
    icon: "🏠",
    verticals: ["TECH", "DESIGN", "FOOD", "BIZ"],
  },
  {
    key: "experience_economy_and_immersive_design",
    name_en: "Experience Economy & Immersive Design",
    name_de: "Erlebnisökonomie & Immersives Design",
    description_en: "Physical spaces as experience platforms — immersive retail, experiential dining, sensory environments, pop-up culture.",
    description_de: "Physische Räume als Erlebnisplattformen — immersiver Retail, Erlebnis-Gastronomie, sensorische Umgebungen.",
    icon: "✨",
    verticals: ["DESIGN", "BIZ", "CULTURE", "LUXURY", "FOOD"],
  },
  {
    key: "cultural_heritage_and_identity",
    name_en: "Cultural Heritage & Identity Renaissance",
    name_de: "Kulturelles Erbe & Identitätsrenaissance",
    description_en: "Revival of craft traditions, cultural fusion, place-based branding, indigenous knowledge, regional identity.",
    description_de: "Revival von Handwerkstraditionen, kulturelle Fusion, ortsbasiertes Branding, indigenes Wissen.",
    icon: "🏛️",
    verticals: ["DESIGN", "FASHION", "CULTURE", "FOOD", "LUXURY"],
  },
  {
    key: "inclusive_and_human_centric_design",
    name_en: "Inclusive & Human-Centric Design",
    name_de: "Inklusives & Menschenzentriertes Design",
    description_en: "Universal accessibility, assistive technology, gender-inclusive products, neurodiversity, equity in design.",
    description_de: "Universelle Barrierefreiheit, assistive Technologien, genderinklusive Produkte, Neurodiversität.",
    icon: "♿",
    verticals: ["DESIGN", "SOCIAL", "HEALTH", "TECH", "FASHION"],
  },
  {
    key: "future_of_food_and_agriculture",
    name_en: "Future of Food & Agriculture",
    name_de: "Zukunft der Ernährung & Landwirtschaft",
    description_en: "Alternative proteins, precision agriculture, vertical farming, functional foods, food-as-medicine, novel ingredients.",
    description_de: "Alternative Proteine, Präzisionslandwirtschaft, Vertical Farming, funktionale Lebensmittel, Food-as-Medicine.",
    icon: "🌾",
    verticals: ["FOOD", "TECH", "HEALTH", "ECO"],
  },
  {
    key: "creator_economy_and_platform_shift",
    name_en: "Creator Economy & Platform Shift",
    name_de: "Creator Economy & Plattformwandel",
    description_en: "Content monetization, creator tools, decentralized media, platform economy, digital-native brands.",
    description_de: "Content-Monetarisierung, Creator-Tools, dezentrale Medien, Plattformökonomie, digital-native Marken.",
    icon: "📱",
    verticals: ["CULTURE", "TECH", "BIZ", "FASHION"],
  },
  {
    key: "new_luxury_and_premiumization",
    name_en: "New Luxury & Premiumization",
    name_de: "Neuer Luxus & Premiumisierung",
    description_en: "Luxury democratization, quiet luxury, experiential premium, artisanal positioning, heritage brand renewal.",
    description_de: "Luxus-Demokratisierung, Quiet Luxury, erlebnisorientiertes Premium, handwerkliche Positionierung.",
    icon: "💎",
    verticals: ["LUXURY", "FASHION", "DESIGN", "FOOD", "BIZ"],
  },
  {
    key: "modular_and_adaptive_systems",
    name_en: "Modular & Adaptive Systems",
    name_de: "Modulare & Adaptive Systeme",
    description_en: "Reconfigurable architecture, modular furniture/housing, flexible workspaces, temporary structures.",
    description_de: "Rekonfigurierbare Architektur, modulare Möbel/Wohnungen, flexible Arbeitsbereiche, temporäre Strukturen.",
    icon: "🧩",
    verticals: ["DESIGN", "BIZ", "TECH", "SOCIAL"],
  },
  {
    key: "urban_transformation_and_smart_cities",
    name_en: "Urban Transformation & Smart Cities",
    name_de: "Urbane Transformation & Smart Cities",
    description_en: "Redesigning cities for density, livability and sustainability — public space, smart infrastructure, transit.",
    description_de: "Städte neu gestalten für Dichte, Lebensqualität und Nachhaltigkeit — öffentlicher Raum, smarte Infrastruktur.",
    icon: "🏙️",
    verticals: ["DESIGN", "ECO", "SOCIAL", "TECH", "BIZ"],
  },
  {
    key: "financial_innovation_and_inclusion",
    name_en: "Financial Innovation & Inclusion",
    name_de: "Finanzinnovation & Inklusion",
    description_en: "Fintech disruption, embedded finance, digital banking, decentralized finance, financial literacy.",
    description_de: "Fintech-Disruption, Embedded Finance, Digital Banking, dezentrale Finanzen, Finanzbildung.",
    icon: "💳",
    verticals: ["BIZ", "TECH", "SOCIAL"],
  },
  {
    key: "mental_health_and_neuro_wellness",
    name_en: "Mental Health & Neuro-Wellness",
    name_de: "Mentale Gesundheit & Neuro-Wellness",
    description_en: "Mental health technology, neuroscience-based products, stress management, mindfulness platforms, biofeedback.",
    description_de: "Mental-Health-Technologie, neurowissenschaftsbasierte Produkte, Stressmanagement, Achtsamkeitsplattformen.",
    icon: "🧠",
    verticals: ["HEALTH", "TECH", "FASHION", "SOCIAL"],
  },
  {
    key: "regenerative_design_and_net_positive",
    name_en: "Regenerative Design & Net Positive",
    name_de: "Regeneratives Design & Net Positive",
    description_en: "Beyond sustainability — designs that actively restore ecosystems, regenerative agriculture, net-positive buildings.",
    description_de: "Über Nachhaltigkeit hinaus — Designs die Ökosysteme aktiv wiederherstellen, regenerative Landwirtschaft.",
    icon: "🌿",
    verticals: ["ECO", "DESIGN", "FOOD", "FASHION"],
  },
  {
    key: "electric_and_autonomous_mobility",
    name_en: "Electric & Autonomous Mobility",
    name_de: "Elektrische & Autonome Mobilität",
    description_en: "Electric vehicles, autonomous driving, shared mobility, urban micro-mobility, charging infrastructure.",
    description_de: "Elektrofahrzeuge, autonomes Fahren, geteilte Mobilität, urbane Mikromobilität, Ladeinfrastruktur.",
    icon: "🚗",
    verticals: ["TECH", "ECO", "DESIGN", "BIZ"],
  },
  {
    key: "wearable_technology_and_augmented_living",
    name_en: "Wearable Technology & Augmented Living",
    name_de: "Wearable-Technologie & Augmented Living",
    description_en: "Smart wearables, health monitoring, AR/VR, smart textiles, brain-computer interfaces.",
    description_de: "Smart Wearables, Gesundheitsmonitoring, AR/VR, smarte Textilien, Gehirn-Computer-Schnittstellen.",
    icon: "⌚",
    verticals: ["TECH", "HEALTH", "FASHION", "DESIGN"],
  },
  {
    key: "digital_trust_and_data_sovereignty",
    name_en: "Digital Trust & Data Sovereignty",
    name_de: "Digitales Vertrauen & Datensouveränität",
    description_en: "Data privacy, digital identity, AI governance, algorithmic transparency, cybersecurity, content authentication.",
    description_de: "Datenschutz, digitale Identität, KI-Governance, algorithmische Transparenz, Cybersicherheit.",
    icon: "🔒",
    verticals: ["TECH", "BIZ", "SOCIAL", "HEALTH"],
  },
];

export function getMegaTrendInfo(key: string): MegaTrendInfo | undefined {
  return MEGA_TRENDS.find((mt) => mt.key === key);
}
