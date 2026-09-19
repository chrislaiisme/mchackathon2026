export type SignalDirection = "up" | "down" | "steady";

export interface FashionRecommendation {
  id: string;
  name: string;
  imageUrl: string;
  explanation: string;
  attributes: string[];
  priceBand: string;
  confidence: number;
  feedback?: "like" | "dislike";
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
