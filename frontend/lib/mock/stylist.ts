import type { Locale } from "@/lib/i18n/dictionaries";
import { dictionaries } from "@/lib/i18n/dictionaries";
import type {
  ChatMessage,
  FashionRecommendation,
  GuidedChoice,
  PreferenceSignal,
  VisualChoice,
} from "@/lib/types";

export function getQuickStyleChoices(locale: Locale = "en"): GuidedChoice[] {
  const t = dictionaries[locale].choices;

  return [
    { id: "minimal", label: t.minimal, prompt: locale === "zh-TW" ? "我想要極簡乾淨的方向" : "Minimal and clean" },
    { id: "street", label: t.street, prompt: locale === "zh-TW" ? "我想要街頭休閒的方向" : "Casual streetwear" },
    { id: "romantic", label: t.romantic, prompt: locale === "zh-TW" ? "我想要柔和浪漫的單品" : "Soft romantic pieces" },
    { id: "vintage", label: t.vintage, prompt: locale === "zh-TW" ? "我想要復古靈感" : "Vintage inspired" },
    { id: "surprise", label: t.surprise, prompt: locale === "zh-TW" ? "給我一個好穿的驚喜" : "Surprise me with something wearable" },
  ];
}

export function getVisualStyleChoices(locale: Locale = "en"): VisualChoice[] {
  return [
    {
      id: "quiet-tailoring",
      title: locale === "zh-TW" ? "俐落剪裁" : "Minimal",
      subtitle: locale === "zh-TW" ? "乾淨層次，帶一點正式感" : "clean layers, quietly polished",
      imageUrl:
        "https://images.unsplash.com/photo-1485968579580-b6d095142e6e?auto=format&fit=crop&w=900&q=80",
      prompt: locale === "zh-TW" ? "我喜歡俐落剪裁這個方向" : "I like the quiet tailoring direction",
    },
    {
      id: "soft-layering",
      title: locale === "zh-TW" ? "柔和層次" : "Soft",
      subtitle: locale === "zh-TW" ? "柔軟材質，輕盈輪廓" : "romantic textures, easy volume",
      imageUrl:
        "https://images.unsplash.com/photo-1496747611176-843222e1e57c?auto=format&fit=crop&w=900&q=80",
      prompt: locale === "zh-TW" ? "我比較喜歡柔和層次" : "I prefer soft layering",
    },
    {
      id: "urban-neutral",
      title: locale === "zh-TW" ? "都會中性" : "Street",
      subtitle: locale === "zh-TW" ? "放鬆街頭感，中性色調" : "relaxed streetwear, elevated neutrals",
      imageUrl:
        "https://images.unsplash.com/photo-1529139574466-a303027c1d8b?auto=format&fit=crop&w=900&q=80",
      prompt: locale === "zh-TW" ? "都會中性比較接近我的感覺" : "Urban neutral feels right",
    },
  ];
}

export function getRecommendations(locale: Locale = "en"): FashionRecommendation[] {
  return [
    {
      id: "rec-1",
      name: locale === "zh-TW" ? "薰衣草針織長線套裝" : "Lavender Column Knit Set",
      imageUrl:
        "https://images.unsplash.com/photo-1509631179647-0177331693ae?auto=format&fit=crop&w=900&q=80",
      explanation:
        locale === "zh-TW"
          ? "乾淨的長線針織加上短版層次，輪廓俐落，薰衣草色讓整體更柔和。"
          : "A clean knit column with a cropped layer keeps the silhouette polished while lavender softens the look.",
      attributes:
        locale === "zh-TW"
          ? ["極簡", "薰衣草", "柔軟針織", "長線輪廓"]
          : ["minimal", "lavender", "soft knit", "column fit"],
      priceBand: "$$",
      confidence: 92,
    },
    {
      id: "rec-2",
      name: locale === "zh-TW" ? "寬鬆西外與緞面長褲" : "Relaxed Blazer + Satin Trouser",
      imageUrl:
        "https://images.unsplash.com/photo-1495385794356-15371f348c31?auto=format&fit=crop&w=900&q=80",
      explanation:
        locale === "zh-TW"
          ? "有結構但不拘謹，適合晚餐或工作後的場合，看起來用心但不過度正式。"
          : "This balances smart structure with fluid movement, good for dinner without feeling overly formal.",
      attributes: locale === "zh-TW" ? ["剪裁", "中性色", "流動感", "晚間"] : ["tailored", "neutral", "fluid", "evening"],
      priceBand: "$$$",
      confidence: 88,
    },
    {
      id: "rec-3",
      name: locale === "zh-TW" ? "單色 Utility 洋裝" : "Monochrome Utility Midi",
      imageUrl:
        "https://images.unsplash.com/photo-1524504388940-b1c1722653e1?auto=format&fit=crop&w=900&q=80",
      explanation:
        locale === "zh-TW"
          ? "Utility 細節讓造型更當代，單色配置則保留了日常搭配的彈性。"
          : "Utility seams make it current, while the monochrome palette keeps it easy to style.",
      attributes: locale === "zh-TW" ? ["utility", "單色", "midi", "百搭"] : ["utility", "monochrome", "midi", "versatile"],
      priceBand: "$$",
      confidence: 84,
    },
  ];
}

export function getInitialMessages(locale: Locale = "en"): ChatMessage[] {
  const t = dictionaries[locale];

  return [
    {
      id: "m-1",
      role: "assistant",
      text: t.assistant.welcome,
      quickChoices: [
        { id: "work", label: t.choices.work, prompt: locale === "zh-TW" ? "我需要工作場合的穿搭" : "I need an outfit for a work event" },
        { id: "date", label: t.choices.dinner, prompt: locale === "zh-TW" ? "我需要晚餐約會穿搭" : "I need a dinner date outfit" },
        { id: "weekend", label: t.choices.weekend, prompt: locale === "zh-TW" ? "我想要週末休閒穿搭" : "I want weekend casual ideas" },
        { id: "vague", label: t.choices.unsure, prompt: locale === "zh-TW" ? "我還不太確定想要什麼" : "I am not really sure what I want" },
      ],
    },
  ];
}

export const initialMessages = getInitialMessages("en");

export const basePreferenceSignals: PreferenceSignal[] = [
  { label: "Minimal", value: 76, direction: "up" },
  { label: "Neutral Colors", value: 68, direction: "up" },
  { label: "Relaxed Fit", value: 61, direction: "up" },
  { label: "Layering", value: 54, direction: "up" },
  { label: "Soft Romantic", value: 34, direction: "down" },
];

export function createStylistReply(input: string, locale: Locale = "en"): ChatMessage {
  const normalized = input.toLowerCase();
  const t = dictionaries[locale];
  const vagueTerms =
    locale === "zh-TW"
      ? ["不確定", "不知道", "隨便", "給我驚喜", "還不太確定"]
      : ["not sure", "surprise", "anything", "don't know"];

  if (vagueTerms.some((term) => normalized.includes(term))) {
    return {
      id: `ai-${Date.now()}`,
      role: "assistant",
      text: t.assistant.vague,
      quickChoices: getQuickStyleChoices(locale),
      visualChoices: getVisualStyleChoices(locale),
    };
  }

  if (
    normalized.includes("casual") ||
    normalized.includes("similar") ||
    normalized.includes("urban") ||
    normalized.includes("tailoring") ||
    normalized.includes("romantic") ||
    normalized.includes("dinner") ||
    normalized.includes("work") ||
    normalized.includes("休閒") ||
    normalized.includes("類似") ||
    normalized.includes("晚餐") ||
    normalized.includes("工作") ||
    normalized.includes("極簡")
  ) {
    return {
      id: `ai-${Date.now()}`,
      role: "assistant",
      text: t.assistant.recommendations,
      recommendations: getRecommendations(locale),
      quickChoices: [
        { id: "more-casual", label: t.choices.makeCasual, prompt: locale === "zh-TW" ? "我喜歡，但想要更休閒一點" : "I like this, but make it more casual" },
        { id: "more-color", label: t.choices.moreColor, prompt: locale === "zh-TW" ? "我喜歡版型，想看多一點顏色" : "I like the shape, show more color" },
        { id: "less-structure", label: t.choices.softer, prompt: locale === "zh-TW" ? "我喜歡顏色，但不喜歡輪廓" : "I like the color but not the silhouette" },
      ],
    };
  }

  return {
    id: `ai-${Date.now()}`,
    role: "assistant",
    text: t.assistant.clarify,
    quickChoices: getQuickStyleChoices(locale),
    visualChoices: getVisualStyleChoices(locale),
  };
}
