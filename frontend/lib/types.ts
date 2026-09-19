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

export type PreferenceItemSource = "recommended" | "generated";
export type PreferenceRatingDimension = "visual_impact" | "polished_formality" | "soft_energy";
export type PreferenceDimensionRatings = Partial<Record<PreferenceRatingDimension, number>>;

export interface WardrobeItem {
  id: string;
  name: string;
  imageUrl: string;
  category: WardrobeCategory;
  brand?: string;
  attributes: string[];
}

export interface PreferenceItemSnapshot extends WardrobeItem {
  source: PreferenceItemSource;
  likedBySave: boolean;
  savedAt: string;
  conversationId?: string;
  messageId?: string;
  roundKey?: string;
}

export interface TryOnFeedbackEntry {
  outfitKey: string;
  feedback: "like" | "dislike";
  itemIds: string[];
  timestamp: string;
  conversationId?: string;
  roundKey?: string;
}

export interface UserPreferenceState {
  savedItems: Record<string, PreferenceItemSnapshot>;
  dislikedItems: Record<string, PreferenceItemSnapshot>;
  itemRatings: Record<string, PreferenceDimensionRatings>;
  tryOnFeedback: Record<string, TryOnFeedbackEntry>;
  recentRecommendationRounds: string[];
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
  // 2026-09-19 新增：最近一次 /recommend 回應的 round——POST /feedback 要求 round
  // 跟後端 session 目前的 round 完全一致（不符回 409），前端這邊需要記住這個數字
  // 才能在送出下一句話之前，把這一輪收集到的收藏／不喜歡／打分／整套喜歡送出去。
  engineRound?: number;
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
