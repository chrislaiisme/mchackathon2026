/**
 * 「AI 幫我搭」：從這一輪所有的上衣與下身裡挑一組最搭的。
 *
 * 候選**同時包含 AI 生成的單品與 ENGINE 02 從商品庫撈到的商品**。理由是使用者
 * 常常只是不滿意其中一件——上衣沒問題、只想換褲子——這時最好的答案往往是
 * 「商品庫那件上衣 ＋ 生成的那件褲子」。只讓生成的單品互配會把這個答案排除掉。
 *
 * 每一筆候選都帶 origin，一路送到模型：買得到與還不存在是不同的東西，模型要知道
 * 它在混什麼，使用者也要在結果上看得出哪件買得到。
 *
 * 只挑、不生圖——候選都已經在畫面上了，再生一次要 50–70 秒，這裡只花模型判斷的
 * 十幾秒。BFF 轉手給 agent/scripts/pair_outfit.py，判斷依據寫在
 * agent/skills/outfit-pairer/SKILL.md。
 *
 * 不走 /style-me：那支的錨點是商品庫的 product_id，生成的單品不在庫裡，接不上。
 *
 * 這支打的是生圖服務（預設 8100），跟 concept-image.ts 同一個服務。
 */
import type { FashionRecommendation } from "@/lib/types";

const GENERATION_BASE_URL =
  process.env.NEXT_PUBLIC_GENERATION_BASE_URL ?? "http://localhost:8100";

export class OutfitPairError extends Error {}

export interface OutfitPairing {
  /** 選中的兩件本體。呼叫端要直接畫出來——選中的可能是商品庫的商品，不在輪播裡。 */
  top: FashionRecommendation;
  bottom: FashionRecommendation;
  /** 模型給的搭配理由，直接顯示給使用者。 */
  reason: string;
  /**
   * "llm" 才是模型真的挑的；"fallback" 是後端退場給的第一件配第一件。
   * 畫面上要照實講，不要把退場結果講成 AI 的判斷。
   */
  source: "llm" | "fallback";
}

interface BackendPair {
  top_id?: string;
  bottom_id?: string;
  reason?: string;
  source?: string;
}

// 後端兩種 keywords 形狀都吃，這裡送前端本來就有的 attributes 字串陣列。
// origin 讓模型知道這件買不買得到——SKILL.md 有一條規則專門講混搭時怎麼取捨。
function toCandidate(item: FashionRecommendation) {
  return {
    id: item.id,
    label: item.name,
    keywords: item.attributes,
    origin: item.generated ? "generated" : "catalog",
  };
}

/**
 * 從 `tops` 與 `bottoms` 裡挑一組最搭的。兩份清單可以混著生成的與商品庫的。
 * `intent` 原樣帶 ENGINE 01 `/intent` 回傳裡那一包。
 *
 * 後端保證回傳的 id 來自送過去的清單，這裡再驗一次並把整件還回去——呼叫端要畫
 * 選中的那兩件，對不到的 id 會變成「按了沒反應」，不如當成錯誤講出來。
 */
export async function pairOutfit(
  intent: Record<string, unknown>,
  tops: FashionRecommendation[],
  bottoms: FashionRecommendation[],
  sessionId: string | undefined,
): Promise<OutfitPairing> {
  if (tops.length === 0 || bottoms.length === 0) {
    throw new OutfitPairError("上衣與下身都要有東西才配得起來");
  }

  const response = await fetch(`${GENERATION_BASE_URL}/outfit-pair`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id: sessionId ?? null,
      intent,
      tops: tops.map(toCandidate),
      bottoms: bottoms.map(toCandidate),
    }),
  });

  if (!response.ok) {
    const detail = await response.text().catch(() => "");
    throw new OutfitPairError(
      `POST /outfit-pair 失敗（HTTP ${response.status}）${detail.slice(0, 200)}`,
    );
  }

  const data = (await response.json()) as BackendPair;
  const top = tops.find((item) => item.id === (data.top_id ?? ""));
  const bottom = bottoms.find((item) => item.id === (data.bottom_id ?? ""));

  if (!top || !bottom) {
    throw new OutfitPairError("配對服務回傳了不在候選清單裡的單品");
  }

  const reason = (data.reason ?? "").trim();

  return {
    top,
    bottom,
    reason,
    // 只認得 "llm" 這一種「真的是模型挑的」，其餘一律當退場——寧可少邀功。
    source: data.source === "llm" && reason ? "llm" : "fallback",
  };
}
