/**
 * AI 生成單品：把 ENGINE 01 抽出來的意圖交給生圖服務，一次拿回六件。
 *
 * 六件來自同一張六宮格 —— 一次生圖 26–48 秒，六件逐一生成要三四分鐘，現場撐不住；
 * 擠在一張圖裡實測 43.8 秒。附帶好處是六格白底、打光、色調天然一致，可以直接互相比較。
 *
 * 這支打的是生圖服務（預設 8100），不是 ENGINE 01（8000）—— 兩個不同的服務。
 */
import type { GeneratedItem } from "@/lib/types";

const GENERATION_BASE_URL =
  process.env.NEXT_PUBLIC_GENERATION_BASE_URL ?? "http://localhost:8100";

export class ConceptImageError extends Error {}

interface BackendCell {
  index: number;
  image_url: string | null;
  varied_label: string | null;
  keywords: Record<string, string>;
}

/** 生六件單品。`intent` 原樣帶 ENGINE 01 `/intent` 回傳裡的那一包。 */
export async function generateItems(
  intent: Record<string, unknown>,
  sessionId?: string,
): Promise<GeneratedItem[]> {
  const response = await fetch(`${GENERATION_BASE_URL}/concept-image`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ intent, session_id: sessionId ?? null }),
  });

  if (!response.ok) {
    const detail = await response.text().catch(() => "");
    throw new ConceptImageError(`POST /concept-image 失敗（HTTP ${response.status}）${detail.slice(0, 200)}`);
  }

  const data = (await response.json()) as { concepts?: { cells?: BackendCell[] } };
  const cells = data.concepts?.cells ?? [];

  return cells
    .filter((cell) => Boolean(cell.image_url))
    .map((cell) => ({
      index: cell.index,
      // 回傳是 /generated/<路徑>，要補上生圖服務的位址才拿得到圖。
      imageUrl: `${GENERATION_BASE_URL}${cell.image_url}`,
      variedLabel: cell.varied_label ?? undefined,
      keywords: cell.keywords ?? {},
    }));
}
