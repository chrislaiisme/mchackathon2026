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
  /**
   * 這件是 AI 生成的，不在商品庫裡。影響兩件事：卡片要標明「不是商品」，
   * 圖片要用 contain 不能用 cover——生成的是白底平拍圖，裁切會把衣服切掉。
   */
  generated?: boolean;
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

export interface GeneratedGroup {
  slot: "top" | "bottom";
  /** 已經翻好的標題，直接顯示。 */
  label: string;
  items: FashionRecommendation[];
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
  /**
   * Design for Me 生出來的單品，照上身／下身分組，自成一輪對話。
   * 刻意不併進 recommendations——那一欄是 ENGINE 02 從商品庫撈到的真商品，
   * 這些是還不存在的東西，混在一起就分不出哪些買得到。
   */
  generatedGroups?: GeneratedGroup[];
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
  // 2026-09-19 新增：ENGINE01 抽出來的最新意圖，Design for Me 生成單品要靠它。
  // 不能只放 React state——重新整理頁面後 state 會歸零，但對話是從 localStorage
  // 讀回來的，兩者不同步就會出現「畫面上明明有推薦結果，按鈕卻說先說需求」的情況。
  // 選填＋可為 null 是因為舊對話沒有這個欄位、或某輪 ENGINE01 沒回意圖。
  lastIntent?: Record<string, unknown> | null;
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
