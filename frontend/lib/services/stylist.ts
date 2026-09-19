// 2026-09-19 新增：把「我們幫你推」從 mock 換成真的打 ENGINE01（/intent、/recommend、
// /style-me）。這支檔案只做兩件事——呼叫後端、把後端的資料形狀轉成前端 stylist-experience.tsx
// 已經在用的 ChatRecommendation／ChatMessage 形狀——渲染那一側完全不用改，因為
// ChatMessage.recommendation 本來就是這些元件直接消費的資料。
import { buildPreferenceRatingFeedback } from "@/lib/services/preferences";
import type { ChatMessage, ChatRecommendation, FashionRecommendation, GuidedChoice, UserPreferenceState } from "@/lib/types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

// 後端 backend/shared/schemas.py 的形狀，只列出這裡實際會用到的欄位。
interface BackendClarifyingOption {
  id: string;
  label: string;
}

// 2026-09-19 匯出：stylist-experience.tsx 要把一輪裡「還沒顯示」的其餘題目
// 存進本地佇列狀態（見 adaptToClarifyingMessage 下面的說明），所以需要這個型別。
export interface BackendClarifyingQuestion {
  field: string;
  question: string;
  options: BackendClarifyingOption[];
  allow_free_text: boolean;
}

interface BackendIntentResponse {
  session_id: string;
  round: number;
  clarifying_questions: BackendClarifyingQuestion[];
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
  match_score: number;
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

// 2026-09-19 新增：「Design for Me」按鈕——ENGINE01 的 POST /concept-image（重用
// bff/images/concept.py 的 generate_concepts()，見 backend/engine01_intent/main.py
// 該端點上方的說明）。cells 只列出實際會用到的欄位；dry_run 模式下沒有 image_url，
// 只有 prompt_used／keywords／varied_label 可以顯示，Hermes Agent 這套外部工具還沒
// 裝好之前先靠這個驗證整條管線接不接得通（見 CLAUDE.md、跟使用者的討論記錄）。
interface BackendConceptCell {
  id?: string;
  index: number;
  keywords: Record<string, string>;
  varied_label?: string | null;
  prompt_fragment?: string | null;
  image_url?: string | null;
}

interface BackendConceptZoneResult {
  dry_run?: boolean;
  grid_image?: string | null;
  prompt_used: string;
  cells: BackendConceptCell[];
}

// 2026-09-19：後端 /concept-image 一律回兩分區形狀（連身裙／單品＋填充另一區／
// 整套請求，三種情境都統一組裝成 zones.top／zones.bottom，見
// backend/engine01_intent/main.py::post_concept_image()）＋一句 Top Pick 理由，
// 比照資料庫推薦「上衣／下身各 6 件」的展示邏輯。連身裙情境下 zones.bottom.cells
// 會是空陣列，不是欄位缺失——呼叫端（conceptCellsToRecommendations()）已經會
// 把空陣列轉成空的候選清單，不用額外判斷。
interface BackendConceptImageResult {
  session_id: string;
  round: number;
  zones: {
    top: BackendConceptZoneResult;
    bottom: BackendConceptZoneResult;
  };
  top_pick_reason?: string | null;
}

export async function fetchConceptImage(
  sessionId: string,
  token: string,
  options?: { dryRun?: boolean },
): Promise<BackendConceptImageResult> {
  const response = await fetch(`${API_BASE_URL}/concept-image`, {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify({ session_id: sessionId, dry_run: options?.dryRun ?? false }),
  });

  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    throw new StylistApiError(
      (detail && (detail.detail as string)) || `POST /concept-image 失敗（HTTP ${response.status}）`,
    );
  }

  return (await response.json()) as BackendConceptImageResult;
}

// 後端回傳的 image_url／grid_image 是相對路徑（例如 `/generated/...`），因為 ENGINE01
// 是用 StaticFiles 掛載的（見 backend/engine01_intent/main.py 的 /generated 掛載點），
// 前端渲染 <img> 要補上 API_BASE_URL 才能跨 origin 讀到圖。
function toAbsoluteMediaUrl(path: string): string {
  return path.startsWith("http") ? path : `${API_BASE_URL}${path}`;
}

// 把「生成新單品」回傳的六格，轉成既有的 FashionRecommendation 形狀——
// ChatMessage.recommendations 本來就有一個會渲染讚／倒讚的元件在等這個資料
// （RecommendationCard，見 stylist-experience.tsx），只是目前完全沒有人填值，
// 這裡重用它，不用另外做一套生圖專屬的卡片元件。
//
// `zone` 有給的話會設 itemType——Try On 判斷要把某件單品放進上衣還是下身槽位
// 是看 `item.itemType === "bottom"` 或 id 前綴（stylist-experience.tsx 的
// getItemSlot()），兩分區（整套請求）生效後如果沒設，全部生成品會被誤判成
// 上衣，兩邊都放到同一槽位——單一品項模式（沒有 zone 概念）維持不設，
// 讓既有的「沒設就當上衣」預設值處理。
export function conceptCellsToRecommendations(
  concepts: BackendConceptZoneResult,
  zone?: "top" | "bottom",
): FashionRecommendation[] {
  const prefix = zone ? `${zone}-concept` : "concept";
  return concepts.cells
    .filter((cell) => Boolean(cell.image_url))
    .map((cell) => ({
      // 生成 id 由 ENGINE01 從 manifest 建立並保存；必須原樣回傳給 /feedback，
      // 不能只靠 index 在瀏覽器端重新組一個暫時 id。
      id: cell.id || `${prefix}-${cell.index}`,
      name: cell.varied_label || `Option ${cell.index}`,
      imageUrl: toAbsoluteMediaUrl(cell.image_url as string),
      explanation: cell.prompt_fragment || concepts.prompt_used,
      attributes: Object.values(cell.keywords),
      priceBand: "",
      confidence: 0,
      ...(zone ? { itemType: zone } : {}),
    }));
}

// 整套請求（outfit_requested）生圖的組裝：跟 adaptToChatRecommendation() 處理
// 資料庫結果同一種 ChatRecommendation 形狀，重用既有的 Top Pick／Try More UI 殼
// （CompleteOutfitCard／ConversationRecommendation），不新做 UI。Top Pick 是
// 上衣格、下身格各自第一格（位置性配對，見 backend 那邊 post_concept_image()
// 的說明，不是真相容性計算），理由用後端已經批次改寫過的 top_pick_reason。
export function adaptConceptZonesToChatRecommendation(
  result: BackendConceptImageResult,
): ChatRecommendation | null {
  if (!result.zones) {
    return null;
  }

  const topCandidates = conceptCellsToRecommendations(result.zones.top, "top");
  const bottomCandidates = conceptCellsToRecommendations(result.zones.bottom, "bottom");
  const topPickCard = topCandidates[0];

  if (!topPickCard) {
    return null;
  }

  const bottomPickCard = bottomCandidates[0] ?? null;

  return {
    view: "top-pick",
    topPick: {
      id: `concept-outfit-${topPickCard.id}-${bottomPickCard?.id ?? "none"}`,
      name: topPickCard.name,
      items: { topOrDress: topPickCard, bottom: bottomPickCard },
      matchScore: 0,
      explanation: result.top_pick_reason || topPickCard.explanation,
      tags: topPickCard.attributes,
    },
    alternatives: {
      topOrDressCandidates: topCandidates,
      bottomCandidates: bottomCandidates,
      selectedTopOrDressIndex: 0,
      selectedBottomIndex: 0,
    },
  };
}

export class StylistApiError extends Error {
  constructor(message: string, public readonly status?: number) {
    super(message);
    this.name = "StylistApiError";
  }
}

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
// 信心百分比——但前端 confidence 這個欄位是直接顯示成「{value}%」（見 stylist-experience.tsx
// 的 `{item.confidence}% {t.stylist.match}`），把原始 score 直接塞進去會出現「3% match」
// 這種失真數字。逐張卡片沒有 ENGINE02 提供的正式 0–1 校準分數可用（那是 zone 層級的
// match_score，不是每張卡片各自的），用觀察到的實際分數範圍（好的配對大約 3.5–4）
// 粗略換算成看得懂的百分比，不是精確校準過的信心值。
//
// 2026-09-19：Top Pick 整體的 matchScore 已經改用 ZoneSlate.match_score（見
// adaptToChatRecommendation()）——那是 ENGINE02 RetrievalResult.match_score 真的算出來的
// 意圖符合度，不是這支粗略換算，兩者不要搞混。
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

// 把一題澄清問題轉成一則帶選項的助理訊息。
//
// 2026-09-19 修正：這支原本吃整個 questions 陣列、只轉第一題（`questions[0]`），
// 其餘題目直接被丟掉——但 ENGINE01 的 gating.py 在回傳前就已經把「這次保留的
// 每一題」都記進 session 的 asked_core_fields（不是只記第一題），代表被丟掉的
// 第二、三題那些核心欄位從此被標記成「已經問過」，永遠不會再被問到、也沒有
// 真的被使用者回答過——這正是真人測試時「明明有固定要填的欄位，問題卻感覺
// 沒問全」的根因。現在改成一次只轉一題，呼叫端（stylist-experience.tsx 的
// sendPrompt）自己維護一個本地佇列，把同一輪其餘的題目依序秀出來、答案全部
// 收集完才真的送出下一次 /intent，不然叫使用者對同一輪的每一題各等一次
// 8–17 秒的 codex exec 往返太浪費（見 CLAUDE.md「ENGINE01 執行方式」）。
export function adaptToClarifyingMessage(question: BackendClarifyingQuestion): ChatMessage {
  const quickChoices: GuidedChoice[] = question.options.map((option) => ({
    id: option.id,
    label: option.label,
    prompt: option.label,
  }));

  return {
    id: `ai-${Date.now()}`,
    role: "assistant",
    text: question.question,
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
      // 真的 ENGINE02 意圖符合度（0–1），不是逐項分數的粗略換算——這是
      // 現場秀「回饋前 62% → 回饋後 89%」量化證明要用的那個數字。
      matchScore: Math.round((topSlate?.match_score ?? 0) * 100),
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

// 2026-09-19 新增：接上 ENGINE03 真實回饋迴圈（POST /feedback）。

interface BackendItemFeedback {
  item_id: string;
  source: "catalog" | "generated";
  favorited?: boolean;
  disliked?: boolean;
  attribute_ratings?: { attribute: string; stars: number }[];
}

interface BackendOutfitItem {
  zone: "top" | "bottom";
  source: "catalog" | "generated";
  item_id: string;
}

interface BackendOutfitFeedback {
  outfit_id: string;
  favorited: true;
  items: BackendOutfitItem[];
}

interface BackendFeedbackResponse {
  session_id: string;
  round: number;
  engine02_feedback: Record<string, unknown>;
  skipped_generated_item_feedbacks: string[];
  skipped_generated_outfit_feedbacks: string[];
}

export async function submitFeedback(
  sessionId: string,
  round: number,
  itemFeedbacks: BackendItemFeedback[],
  outfitFeedbacks: BackendOutfitFeedback[],
  token: string,
): Promise<BackendFeedbackResponse> {
  const response = await fetch(`${API_BASE_URL}/feedback`, {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify({
      session_id: sessionId,
      round,
      item_feedbacks: itemFeedbacks,
      outfit_feedbacks: outfitFeedbacks,
    }),
  });

  if (!response.ok) {
    const detail = await response
      .json()
      .then((body: unknown) => (typeof body === "object" && body !== null && "detail" in body ? String(body.detail) : ""))
      .catch(() => "");
    throw new StylistApiError(
      `POST /feedback 失敗（HTTP ${response.status}）${detail ? `：${detail}` : ""}`,
      response.status,
    );
  }

  return (await response.json()) as BackendFeedbackResponse;
}

// 生成單品的 id 是 conceptCellsToRecommendations() 組出來的 "concept-<n>"／
// "top-concept-<n>"／"bottom-concept-<n>"，真正的資料庫商品 id（ENGINE02 的
// product_id）不會是這個格式——用來判斷這張卡片的回饋要不要送給 ENGINE03
// （source="generated" 的今天整批由後端跳過，見 main.py::post_feedback()）。
function isGeneratedItemId(itemId: string): boolean {
  return itemId.startsWith("generated:") || /^(top-|bottom-)?concept-\d+$/.test(itemId);
}

// 早期前端以 concept-<n> 自行組 id；現在 ENGINE01 會從本輪 manifest 回傳
// session scoped 的 generated:<session>:... id。舊瀏覽器快取的對話仍可能帶著
// 前者，送回後端既無法驗證、也不應套用到本輪，因此只略過它的回饋，不放寬
// 後端對未知 item id 的安全檢查。
function isLegacyGeneratedItemId(itemId: string): boolean {
  return /^(top-|bottom-)?concept-\d+$/.test(itemId);
}

// 這一輪實際展示過的商品 id → 屬於哪一區——整套喜歡（OutfitFeedbackRequest）
// 一定要分清楚 top_item_id／bottom_item_id，不能只知道「兩件不知道哪件是哪區」，
// 呼叫端（stylist-experience.tsx）從 ChatRecommendation.alternatives 的
// topOrDressCandidates／bottomCandidates 兩個陣列各自的 id 組出這個 lookup。
export type ZoneByItemId = Record<string, "top" | "bottom">;

// 把 preferences.ts 的 UserPreferenceState（收藏／不喜歡／三個具名維度打分／
// 整套喜歡）轉成 POST /feedback 要的形狀。`zoneByItemId` 是這一輪實際展示過
// 的商品 id（不管是資料庫商品還是生成單品都算）各自屬於哪一區，只有這些 id 上
// 的回饋才會被送出——沒被展示過的舊回饋（例如使用者很久以前收藏過的某件商品，
// 但這輪根本沒出現）不該被當成「這輪的回饋」重複送出去。
export function adaptPreferencesToFeedbackRequest(
  preferenceState: UserPreferenceState,
  zoneByItemId: ZoneByItemId,
): { itemFeedbacks: BackendItemFeedback[]; outfitFeedbacks: BackendOutfitFeedback[] } {
  const itemFeedbacks: BackendItemFeedback[] = [];

  for (const itemId of Object.keys(zoneByItemId)) {
    if (isLegacyGeneratedItemId(itemId)) {
      continue;
    }

    const favorited = Boolean(preferenceState.savedItems[itemId]);
    const disliked = Boolean(preferenceState.dislikedItems[itemId]);
    const ratings = preferenceState.itemRatings[itemId];
    const ratingFeedback = ratings ? buildPreferenceRatingFeedback(itemId, ratings) : null;
    const attributeRatings = ratingFeedback?.attribute_ratings ?? [];

    // 三種訊號都沒有就不送——沒有動作不能當成「中立」或某個預設分數（既有規則，
    // 見 docs/engine03-feedback.md「輸入」一節）。
    if (!favorited && !disliked && attributeRatings.length === 0) {
      continue;
    }

    itemFeedbacks.push({
      item_id: itemId,
      source: isGeneratedItemId(itemId) ? "generated" : "catalog",
      favorited,
      disliked,
      attribute_ratings: attributeRatings,
    });
  }

  const outfitFeedbacks: BackendOutfitFeedback[] = [];

  for (const entry of Object.values(preferenceState.tryOnFeedback)) {
    // 只有「喜歡」有對應的後端概念（ENGINE03 OutfitFeedback.favorited 寫死
    // Literal[True]，沒有「整套不喜歡」）；itemIds 一定要正好兩件、分別是
    // 上衣區跟下身區各一件，才是一套真正的整套試穿。
    if (entry.feedback !== "like" || entry.itemIds.length !== 2) {
      continue;
    }
    if (entry.itemIds.some((id) => !zoneByItemId[id])) {
      continue;
    }
    if (entry.itemIds.some(isLegacyGeneratedItemId)) {
      continue;
    }
    const topItemId = entry.itemIds.find((id) => zoneByItemId[id] === "top");
    const bottomItemId = entry.itemIds.find((id) => zoneByItemId[id] === "bottom");
    if (!topItemId || !bottomItemId) {
      continue;
    }
    // 2026-09-19：這裡不再自己過濾掉含生成單品的整套——資料庫＋生成混合的整套
    // 一樣照實送出去（source 標明是哪一種），後端會判斷要不要真的套用還是
    // 跳過並回報在 skipped_generated_outfit_feedbacks（今天還不支援生成單品的
    // design_attributes 映射，但那是後端的決定，不該在前端就默默丟掉這筆訊號）。
    outfitFeedbacks.push({
      outfit_id: entry.outfitKey,
      favorited: true,
      items: [
        { zone: "top", source: isGeneratedItemId(topItemId) ? "generated" : "catalog", item_id: topItemId },
        { zone: "bottom", source: isGeneratedItemId(bottomItemId) ? "generated" : "catalog", item_id: bottomItemId },
      ],
    });
  }

  return { itemFeedbacks, outfitFeedbacks };
}
