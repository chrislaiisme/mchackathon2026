/**
 * Design for Me：把 ENGINE 01 抽出來的意圖交給生圖服務，換回可以直接放進輪播的單品。
 *
 * 六件來自同一張六宮格 —— 一次生圖 26–48 秒，六件逐一生成要三四分鐘，現場撐不住；
 * 擠在一張圖裡實測 43.8 秒。附帶好處是六格白底、打光、色調天然一致，可以直接互相比較。
 *
 * TOP 與 BOTTOM 是兩張圖，由 BFF 並行送出去（見 bff/images/concept.py 的
 * generate_concept_pair），所以兩組拿到的時間大約等於一張。
 *
 * 這支打的是生圖服務（預設 8100），不是 ENGINE 01（8000）—— 兩個不同的服務。
 */
import type { FashionRecommendation } from "@/lib/types";

const GENERATION_BASE_URL =
  process.env.NEXT_PUBLIC_GENERATION_BASE_URL ?? "http://localhost:8100";

export class ConceptImageError extends Error {}

interface BackendCell {
  index: number;
  image_url: string | null;
  varied_label: string | null;
  keywords: Record<string, string>;
}

interface BackendSlot {
  cells?: BackendCell[];
  error?: string;
}

export interface GeneratedSlots {
  topOrDress: FashionRecommendation[];
  bottom: FashionRecommendation[];
}

// 卡片上那句說明。六格差在同一個屬性，變化的值（"knee"、"below the knee"）就是
// 這一格跟其他格的差別，直接講出來比寫一句空泛的行銷詞有用。
function explain(cell: BackendCell, locale: string): string {
  const varied = cell.varied_label;
  if (!varied) {
    return locale === "zh-TW" ? "照你的描述生成的" : "Generated from what you described";
  }
  return locale === "zh-TW" ? `跟其他幾件的差別：${varied}` : `Differs from the others: ${varied}`;
}

function toRecommendation(
  cell: BackendCell,
  slot: "top" | "bottom",
  locale: string,
): FashionRecommendation | null {
  if (!cell.image_url) {
    return null;
  }

  const label = cell.varied_label ?? String(cell.index);

  return {
    // id 前綴要跟 ENGINE 02 的商品分得開：這些不在商品庫裡，按讚／收藏之後
    // 不能拿去查商品，getItemSlot() 也靠前綴判斷它屬於哪一欄。
    id: `${slot}-ai-${cell.index}`,
    name: label,
    imageUrl: `${GENERATION_BASE_URL}${cell.image_url}`,
    explanation: explain(cell, locale),
    attributes: [...new Set(Object.values(cell.keywords ?? {}).filter(Boolean))],
    priceBand: locale === "zh-TW" ? "尚未生產" : "Not in catalog",
    // 不是檢索出來的，沒有比對分數可言。100 會讓它看起來比真商品更「準」，
    // 這裡給 0 並在卡片上以 generated 標記改成顯示「AI 生成」而不是百分比。
    confidence: 0,
    itemType: slot,
    generated: true,
  };
}

/** TOP 與 BOTTOM 各生六件。`intent` 原樣帶 ENGINE 01 `/intent` 回傳裡的那一包。 */
export async function generateItemPair(
  intent: Record<string, unknown>,
  sessionId: string | undefined,
  locale: string,
): Promise<GeneratedSlots> {
  const response = await fetch(`${GENERATION_BASE_URL}/concept-image`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ intent, session_id: sessionId ?? null, pair: true }),
  });

  if (!response.ok) {
    const detail = await response.text().catch(() => "");
    throw new ConceptImageError(
      `POST /concept-image 失敗（HTTP ${response.status}）${detail.slice(0, 200)}`,
    );
  }

  const data = (await response.json()) as { slots?: Record<string, BackendSlot> };
  const slots = data.slots ?? {};

  // 其中一邊失敗時 BFF 回的是 { error }，另一邊照樣有六件——不要整個當失敗。
  const pick = (slot: "top" | "bottom") =>
    (slots[slot]?.cells ?? [])
      .map((cell) => toRecommendation(cell, slot, locale))
      .filter((item): item is FashionRecommendation => item !== null);

  const result = { topOrDress: pick("top"), bottom: pick("bottom") };

  if (result.topOrDress.length === 0 && result.bottom.length === 0) {
    const reason = Object.values(slots)
      .map((s) => s.error)
      .filter(Boolean)
      .join("；");
    throw new ConceptImageError(reason || "生圖服務沒有回傳任何單品");
  }

  return result;
}
