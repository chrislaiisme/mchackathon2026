export type SignalDirection = "up" | "down" | "steady";

export interface FashionRecommendation {
  id: string;
  name: string;
  imageUrl: string;
  explanation: string;
  attributes: string[];
  priceBand: string;
  confidence: number;
  itemType?: "top" | "bottom" | "dress";
  feedback?: "like" | "dislike";
}

export interface StylistOutfitRecommendation {
  topOrDressId: string;
  bottomId: string | null;
  reason: string;
  summary?: string;
}

export type RecommendationView = "top-pick" | "explore";

export interface OutfitRecommendation {
  id: string;
  name: string;
  items: {
    topOrDress: FashionRecommendation;
    bottom: FashionRecommendation | null;
  };
  imageUrl?: string;
  matchScore: number;
  explanation: string;
  tags: string[];
}

export interface ChatRecommendation {
  view: RecommendationView;
  topPick: OutfitRecommendation;
  alternatives: {
    topOrDressCandidates: FashionRecommendation[];
    bottomCandidates: FashionRecommendation[];
    selectedTopOrDressIndex: number;
    selectedBottomIndex: number;
  };
}

export type WardrobeCategory = "tops" | "bottoms" | "dresses" | "outerwear" | "shoes" | "accessories";

export type OutfitSlot = "top" | "bottom" | "dress" | "outerwear" | "shoes" | "accessories";

export interface WardrobeItem {
  id: string;
  name: string;
  imageUrl: string;
  category: WardrobeCategory;
  brand?: string;
  attributes: string[];
}

export interface GuidedChoice {
  id: string;
  label: string;
  prompt: string;
}

export interface VisualChoice {
  id: string;
  title: string;
  subtitle: string;
  imageUrl: string;
  prompt: string;
}

export interface PreferenceSignal {
  label: string;
  value: number;
  direction: SignalDirection;
}

export interface GeneratedItem {
  /** 六宮格切出來的單格，1 起算。 */
  index: number;
  imageUrl: string;
  /** 這一格相對其他格改了什麼，中文原字，直接顯示在卡片上。 */
  variedLabel?: string;
  keywords: Record<string, string>;
}

export interface ChatMessage {
  id: string;
  conversationId?: string;
  role: "assistant" | "user";
  text: string;
  createdAt?: string;
  quickChoices?: GuidedChoice[];
  visualChoices?: VisualChoice[];
  recommendations?: FashionRecommendation[];
  recommendation?: ChatRecommendation;
  /** AI 生成的單品（不是商品庫裡的東西，卡片上要標明）。 */
  generatedItems?: GeneratedItem[];
}

export interface User {
  id: string;
  name: string;
  email: string;
  avatarUrl: string;
}

export interface Conversation {
  id: string;
  userId: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  messages: ChatMessage[];
  recommendationFeedback: Record<string, "like" | "dislike">;
  preferenceSignals: PreferenceSignal[];
  // 2026-09-19 新增：ENGINE01 的 /intent session_id，讓同一個對話的多輪訊息延續同一個
  // session（沿用 ENGINE01 的澄清問題把關與五題上限邏輯），而不是每則訊息都開新 session。
  // 選填是因為舊對話（合併 main 之前建立的、或還沒送出過第一句真訊息的）不會有這個欄位。
  engineSessionId?: string;
}

export interface VirtualYouMeasurements {
  heightCm?: string;
  weightKg?: string;
  waistCm?: string;
  hipsCm?: string;
  chestBustCm?: string;
}

export interface VirtualYouProfile {
  userId: string;
  modelImageUrl: string;
  hasCustomPhoto: boolean;
  hasExtractedPerson: boolean;
  selectedDefaultModelUrl?: string;
  isDefaultModel: boolean;
  measurements: VirtualYouMeasurements;
  processingMode: "mock" | "generated";
  personBoundingBox?: {
    x: number;
    y: number;
    width: number;
    height: number;
  };
  storageError?: string;
  updatedAt: string;
}

export interface KpiMetric {
  label: string;
  value: string;
  change: string;
  tone: "positive" | "neutral" | "warning";
}

export interface TrendPoint {
  label: string;
  value: number;
}

export interface TrendInsight {
  name: string;
  momentum: number;
  audience: string;
  signal: string;
}

export interface RankedSignal {
  label: string;
  value: number;
  note: string;
}
