// 2026-09-19 新增：把「我們幫你推」從 mock 換成真的打 ENGINE01（/intent、/recommend、
// /style-me）。這支檔案只做兩件事——呼叫後端、把後端的資料形狀轉成前端 stylist-experience.tsx
// 已經在用的 ChatRecommendation／ChatMessage 形狀——渲染那一側完全不用改，因為
// ChatMessage.recommendation 本來就是這些元件直接消費的資料。
import type { ChatMessage, ChatRecommendation, FashionRecommendation, GuidedChoice } from "@/lib/types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

// 後端 backend/shared/schemas.py 的形狀，只列出這裡實際會用到的欄位。
interface BackendClarifyingOption {
  id: string;
  label: string;
}

interface BackendClarifyingQuestion {
  field: string;
  question: string;
  options: BackendClarifyingOption[];
  allow_free_text: boolean;
}

interface BackendIntentResponse {
  session_id: string;
  round: number;
  clarifying_questions: BackendClarifyingQuestion[];
  /** ENGINE 01 抽出來的結構化意圖。生成單品要用它，所以這裡把它宣告出來。 */
  intent?: Record<string, unknown>;
}

interface BackendProductCard {
  product_id: string;
  image_url: string;
  title: string;
  attributes: Record<string, string>;
  score: number;
  reason: string;
  explanation_source?: string | null;
}

interface BackendZoneSlate {
  zone: "top" | "bottom";
  requested: boolean;
  products: BackendProductCard[];
}

interface BackendZonedRecommendationResult {
  session_id: string;
  round: number;
  outfit_requested: boolean;
  zones: BackendZoneSlate[];
}

interface BackendStyledComplement {
  session_id: string;
  round: number;
  zone: "top" | "bottom";
  complement: BackendProductCard;
}

export class StylistApiError extends Error {}

function authHeaders(token: string): HeadersInit {
  return { "Content-Type": "application/json", Authorization: `Bearer ${token}` };
}

// session_id 省略（undefined）代表這是這個對話的第一句話，後端會開一個新 session。
export async function fetchIntentTurn(
  sessionId: string | undefined,
  message: string,
  token: string,
): Promise<BackendIntentResponse> {
  const response = await fetch(`${API_BASE_URL}/intent`, {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify({ session_id: sessionId, message }),
  });

  if (!response.ok) {
    throw new StylistApiError(`POST /intent 失敗（HTTP ${response.status}）`);
  }

  return (await response.json()) as BackendIntentResponse;
}

export async function fetchRecommendation(
  sessionId: string,
  token: string,
): Promise<BackendZonedRecommendationResult> {
  const response = await fetch(`${API_BASE_URL}/recommend`, {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify({ session_id: sessionId }),
  });

  if (!response.ok) {
    throw new StylistApiError(`POST /recommend 失敗（HTTP ${response.status}）`);
  }

  return (await response.json()) as BackendZonedRecommendationResult;
}

// 幫你搭的相容配對；找不到搭配時後端回 404，這裡回傳 null 而不是 throw，
// 呼叫端要退回「下身區分數最高那件」，不能讓 Top Pick 因為這個失敗整個掛掉。
export async function fetchStyleMe(
  sessionId: string,
  anchorProductId: string,
  anchorZone: "top" | "bottom",
  token: string,
): Promise<BackendStyledComplement | null> {
  const response = await fetch(`${API_BASE_URL}/style-me`, {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify({ session_id: sessionId, anchor_product_id: anchorProductId, anchor_zone: anchorZone }),
  });

  if (response.status === 404) {
    return null;
  }

  if (!response.ok) {
    throw new StylistApiError(`POST /style-me 失敗（HTTP ${response.status}）`);
  }

  return (await response.json()) as BackendStyledComplement;
}

// ENGINE02 的 score 是逐項加總出來的排序分數（dense+bm25+design+...疊加），不是 0–100 的
// 信心百分比——但前端 confidence／matchScore 兩個欄位都是直接顯示成「{value}%」（見
// stylist-experience.tsx 的 `{item.confidence}% {t.stylist.match}`），把原始 score 直接塞進去
// 會出現「3% match」這種失真數字。這裡沒有 ENGINE02 提供的正式 0–1 校準分數可用
// （ZonedRecommendationResult 沒有 match_score 欄位，那是 RetrievalResult 專屬的），
// 用觀察到的實際分數範圍（好的配對大約 3.5–4）粗略換算成看得懂的百分比，
// 不是精確校準過的信心值。
function toMatchPercent(score: number): number {
  const CEILING = 5;
  return Math.max(0, Math.min(100, Math.round((score / CEILING) * 100)));
}

function toFashionRecommendation(card: BackendProductCard, itemType: "top" | "bottom"): FashionRecommendation {
  // 欄位對欄位轉換：後端跟前端各自的命名慣例不一樣（product_id/id、image_url/imageUrl...），
  // 這是唯一需要對齊的地方——後端沒有價格資料（price 屬性覆蓋率 0%，見 data/README.md），
  // priceBand 在前端型別上是必填字串，這裡先給空字串，不是遺漏。
  return {
    id: card.product_id,
    name: card.title,
    imageUrl: card.image_url,
    explanation: card.reason,
    attributes: Object.values(card.attributes),
    priceBand: "",
    confidence: toMatchPercent(card.score),
    itemType,
  };
}

function findZone(zones: BackendZoneSlate[], zone: "top" | "bottom"): BackendZoneSlate | undefined {
  return zones.find((slate) => slate.zone === zone);
}

// 把第一個澄清問題轉成一則帶選項的助理訊息——quickChoices 被點擊時前端本來就會
// 呼叫 sendPrompt(choice.prompt)，所以這裡的 prompt 直接填 label 就會自然送出下一輪 /intent。
export function adaptToClarifyingMessage(questions: BackendClarifyingQuestion[]): ChatMessage {
  const first = questions[0];
  const quickChoices: GuidedChoice[] = first.options.map((option) => ({
    id: option.id,
    label: option.label,
    prompt: option.label,
  }));

  return {
    id: `ai-${Date.now()}`,
    role: "assistant",
    text: first.question,
    quickChoices,
  };
}

// 幫你搭的核心：Top Pick 不是「兩個分區各自分數最高的東西硬湊」，是拿上衣區分數最高的
// 那件當錨點，問 ENGINE02 真的相容排序過的下身（POST /style-me → /engine02/complete-look）。
// 連身裙（下身區被 zones.is_dress() 留空）不用配對，bottom 直接是 null。
export async function adaptToChatRecommendation(
  zoned: BackendZonedRecommendationResult,
  token: string,
): Promise<ChatRecommendation> {
  const topSlate = findZone(zoned.zones, "top");
  const bottomSlate = findZone(zoned.zones, "bottom");

  const topCandidates = topSlate?.products ?? [];
  const bottomCandidates = bottomSlate?.products ?? [];

  const topPickCard = topCandidates[0];
  if (!topPickCard) {
    throw new StylistApiError("這一輪上衣區沒有任何推薦商品，無法組出 Top Pick");
  }

  const topOrDress = toFashionRecommendation(topPickCard, "top");
  let bottom: FashionRecommendation | null = null;

  if (bottomCandidates.length > 0) {
    // 有下身候選才需要幫你搭配對；沒有（連身裙情境）就維持 bottom: null。
    const styled = await fetchStyleMe(zoned.session_id, topPickCard.product_id, "top", token).catch(
      () => null,
    );

    if (styled) {
      bottom = toFashionRecommendation(styled.complement, "bottom");
    } else {
      // /style-me 沒接上（尚未部署 ENGINE02、或這件錨點沒有相容 slate）→
      // 退回下身區分數最高的一件，Top Pick 不能直接空著。
      bottom = toFashionRecommendation(bottomCandidates[0], "bottom");
    }
  }

  return {
    view: "top-pick",
    topPick: {
      id: `outfit-${topPickCard.product_id}`,
      name: topOrDress.name,
      items: { topOrDress, bottom },
      matchScore: toMatchPercent(topPickCard.score),
      explanation: topOrDress.explanation,
      tags: Object.values(topPickCard.attributes),
    },
    alternatives: {
      topOrDressCandidates: topCandidates.map((card) => toFashionRecommendation(card, "top")),
      bottomCandidates: bottomCandidates.map((card) => toFashionRecommendation(card, "bottom")),
      selectedTopOrDressIndex: 0,
      selectedBottomIndex: 0,
    },
  };
}
