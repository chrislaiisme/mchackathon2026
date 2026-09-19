/**
 * 串接層 client：前端只跟 BFF 講話，由它去呼叫三個引擎。
 *
 * 每個函式失敗時回傳 null，呼叫端退回 mock —— 後端沒起來時畫面仍然能動，
 * 這也是現場網路出問題時的備援。
 */
import type { ChatMessage, FashionRecommendation, GuidedChoice } from "@/lib/types";

const BFF_URL = process.env.NEXT_PUBLIC_BFF_URL ?? "http://127.0.0.1:8100";
const ENGINE02_URL = process.env.NEXT_PUBLIC_ENGINE02_URL ?? "http://127.0.0.1:8002";
const SESSIONS_KEY = "intentweave.sessions";

type SessionState = { sessionId: string; round: number; shownItemIds: string[] };

function readSessions(): Record<string, SessionState> {
  if (typeof window === "undefined") return {};
  try {
    return JSON.parse(window.localStorage.getItem(SESSIONS_KEY) || "{}");
  } catch {
    return {};
  }
}

function writeSession(conversationId: string, state: SessionState) {
  if (typeof window === "undefined") return;
  const all = readSessions();
  all[conversationId] = state;
  window.localStorage.setItem(SESSIONS_KEY, JSON.stringify(all));
}

export function getSession(conversationId: string): SessionState | undefined {
  return readSessions()[conversationId];
}

function absoluteImage(url: string): string {
  if (!url) return "";
  return /^https?:\/\//i.test(url) ? url : `${ENGINE02_URL}${url.startsWith("/") ? "" : "/"}${url}`;
}

/** ENGINE 02 的 products → 前端的推薦卡。attributes 可能是陣列或字典，兩種都吃。 */
function toRecommendations(retrieval: any): FashionRecommendation[] {
  const products = retrieval?.products ?? [];
  // ENGINE 02 的 score 是無界的相關性分數（例如 2.954），UI 的欄位是 0–100 的百分比。
  // 以這批裡最高分為 100% 做相對換算 —— 卡片上真正的理由是分數分解那段文字，這個數字只是排序強弱。
  const top = Math.max(...products.map((p: any) => Number(p.score) || 0), 1e-9);
  return products.map((p: any) => {
    const attrs = Array.isArray(p.attributes)
      ? p.attributes.map(String)
      : Object.entries(p.attributes ?? {}).map(([k, v]) => `${k}: ${v}`);
    return {
      id: String(p.product_id ?? p.item_id ?? ""),
      name: String(p.title ?? p.product_id ?? ""),
      imageUrl: absoluteImage(String(p.image_url ?? "")),
      explanation: String(p.reason ?? ""),
      attributes: attrs,
      priceBand: String(p.price_band ?? p.price ?? "—"),
      confidence: Math.round(((Number(p.score) || 0) / top) * 100),
    };
  });
}

function toQuickChoices(questions: any[]): GuidedChoice[] | undefined {
  if (!Array.isArray(questions) || questions.length === 0) return undefined;
  return questions.slice(0, 3).map((q: any, i: number) => ({
    id: String(q.id ?? `clarify-${i}`),
    label: String(q.label ?? q.text ?? ""),
    prompt: String(q.prompt ?? q.text ?? ""),
  }));
}

function toAssistantMessage(data: any, fallbackText: string): ChatMessage {
  const recommendations = toRecommendations(data?.retrieval);
  const questions = data?.clarifying_questions ?? [];
  const firstQuestion = questions[0]?.text;
  return {
    id: `assistant-${Date.now()}`,
    role: "assistant",
    text: String(firstQuestion || fallbackText),
    recommendations: recommendations.length ? recommendations : undefined,
    quickChoices: toQuickChoices(questions),
  };
}

function authHeader(): Record<string, string> {
  if (typeof window === "undefined") return {};
  const token = window.localStorage.getItem("intentweave.token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function postJson(path: string, body: unknown): Promise<any | null> {
  try {
    const res = await fetch(`${BFF_URL}${path}`, {
      method: "POST",
      headers: { "content-type": "application/json", ...authHeader() },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      console.warn(`[intentweave] ${path} 回傳 ${res.status}`, await res.text());
      return null;
    }
    return await res.json();
  } catch (error) {
    console.warn(`[intentweave] ${path} 連不上，退回 mock`, error);
    return null;
  }
}

/** 一句話 → ENGINE 01 → ENGINE 02。回傳助理訊息，失敗回 null。 */
export async function runRound(
  conversationId: string,
  message: string,
  fallbackText: string,
): Promise<ChatMessage | null> {
  const session = getSession(conversationId);
  const data = await postJson("/round", { session_id: session?.sessionId ?? null, message });
  if (!data) return null;

  const reply = toAssistantMessage(data, fallbackText);
  writeSession(conversationId, {
    sessionId: String(data.session_id),
    round: Number(data.round ?? 1),
    shownItemIds: (reply.recommendations ?? []).map((r) => r.id),
  });
  return reply;
}

/** 對某張卡按讚／倒讚 → ENGINE 03 → 帶著回饋重跑 ENGINE 02，直接拿到下一輪。 */
export async function sendCardFeedback(
  conversationId: string,
  itemId: string,
  value: "like" | "dislike",
  fallbackText: string,
): Promise<ChatMessage | null> {
  const session = getSession(conversationId);
  if (!session) return null;

  const data = await postJson("/feedback", {
    session_id: session.sessionId,
    round: session.round,
    target: "recommended",
    shown_item_ids: session.shownItemIds,
    liked_item_ids: value === "like" ? [itemId] : [],
    disliked_item_ids: value === "dislike" ? [itemId] : [],
    selected_option_id: value === "like" ? itemId : null,
  });
  if (!data) return null;

  const reply = toAssistantMessage(data, fallbackText);
  writeSession(conversationId, {
    sessionId: session.sessionId,
    round: Number(data.round ?? session.round + 1),
    shownItemIds: (reply.recommendations ?? []).map((r) => r.id),
  });
  return reply;
}

/** 三個引擎在不在。現場排查用，畫面上可以顯示一個小指示燈。 */
export async function health(): Promise<any | null> {
  try {
    const res = await fetch(`${BFF_URL}/health`);
    return res.ok ? await res.json() : null;
  } catch {
    return null;
  }
}
