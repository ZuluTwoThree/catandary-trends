import { MEGA_TRENDS } from "./mega-trends.generated";
export { MEGA_TRENDS };

export type Vertical =
  | "FOOD" | "TECH" | "HEALTH" | "ECO" | "DESIGN"
  | "FASHION" | "BIZ" | "LIFESTYLE";

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
  { id: "LIFESTYLE", label: "Lifestyle & Culture", color: "#a855f7", icon: "🎭" },
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

export function getMegaTrendInfo(key: string): MegaTrendInfo | undefined {
  return MEGA_TRENDS.find((mt) => mt.key === key);
}
