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
  slug: string;
  summary_en: string | null;
  body_en: string | null;
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
  /** Timeline date the queries order by and the free archive window (#70)
   *  filters on: the source date capped to now (aliased in TREND_COLS). */
  sort_date: string | null;
}

export interface VerticalInfo {
  id: Vertical;
  label: string;
  color: string;
  /** 4-char monospace abbreviation — replaces legacy emoji icon. */
  code: string;
  /** Legacy alias for transitional rendering; use `code` going forward. */
  icon: string;
}

export interface PestelInfo {
  id: PestelDimension;
  label: string;
  color: string;
}

export const VERTICALS: VerticalInfo[] = [
  { id: "FOOD", label: "Food & Beverage", color: "#f97316", code: "FOOD", icon: "FOOD" },
  { id: "TECH", label: "Technology & AI", color: "#a78bfa", code: "TECH", icon: "TECH" },
  { id: "HEALTH", label: "Health & Wellness", color: "#34d399", code: "HLTH", icon: "HLTH" },
  { id: "ECO", label: "Sustainability", color: "#22d3ee", code: "ECO", icon: "ECO" },
  { id: "DESIGN", label: "Design & Architecture", color: "#f472b6", code: "DSGN", icon: "DSGN" },
  { id: "FASHION", label: "Fashion & Beauty", color: "#fb7185", code: "FASH", icon: "FASH" },
  { id: "BIZ", label: "Business & Retail", color: "#60a5fa", code: "BIZ", icon: "BIZ" },
  { id: "LIFESTYLE", label: "Lifestyle & Culture", color: "#c084fc", code: "LIFE", icon: "LIFE" },
];

export const PESTEL: PestelInfo[] = [
  { id: "P", label: "Political", color: "#ef4444" },
  { id: "E", label: "Economic", color: "#60a5fa" },
  { id: "S", label: "Social", color: "#34d399" },
  { id: "T", label: "Technological", color: "#a78bfa" },
  { id: "En", label: "Environmental", color: "#22d3ee" },
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
  description_en: string;
  icon: string;
  verticals: Vertical[];
}

export function getMegaTrendInfo(key: string): MegaTrendInfo | undefined {
  return MEGA_TRENDS.find((mt) => mt.key === key);
}
