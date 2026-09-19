import type { Locale } from "@/lib/i18n/dictionaries";
import { dictionaries } from "@/lib/i18n/dictionaries";
import type {
  ChatMessage,
  FashionRecommendation,
  GuidedChoice,
  OutfitRecommendation,
  PreferenceSignal,
  StylistOutfitRecommendation,
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

export function getTopOrDressCandidates(locale: Locale = "en"): FashionRecommendation[] {
  return [
    {
      id: "top-01",
      name: locale === "zh-TW" ? "象牙色垂墜襯衫" : "Ivory Draped Shirt",
      imageUrl:
        "https://images.unsplash.com/photo-1496747611176-843222e1e57c?auto=format&fit=crop&w=900&q=80",
      explanation:
        locale === "zh-TW"
          ? "柔軟垂墜感讓襯衫保有正式度，但不會太硬挺。"
          : "Soft drape keeps the shirt polished without feeling rigid.",
      attributes: locale === "zh-TW" ? ["象牙白", "垂墜", "輕正式", "柔軟"] : ["ivory", "draped", "polished", "soft"],
      priceBand: "$$",
      confidence: 91,
      itemType: "top",
    },
    {
      id: "top-02",
      name: locale === "zh-TW" ? "短版建築感背心" : "Cropped Architectural Vest",
      imageUrl:
        "https://images.unsplash.com/photo-1485968579580-b6d095142e6e?auto=format&fit=crop&w=900&q=80",
      explanation:
        locale === "zh-TW" ? "俐落線條拉高比例，適合搭配高腰下身。" : "Clean structure sharpens the proportion over a high waist.",
      attributes: locale === "zh-TW" ? ["短版", "結構感", "極簡", "高腰友善"] : ["cropped", "structured", "minimal", "high-waist"],
      priceBand: "$$$",
      confidence: 87,
      itemType: "top",
    },
    {
      id: "top-03",
      name: locale === "zh-TW" ? "霧紫柔軟針織" : "Misted Violet Soft Knit",
      imageUrl:
        "https://images.unsplash.com/photo-1509631179647-0177331693ae?auto=format&fit=crop&w=900&q=80",
      explanation:
        locale === "zh-TW" ? "紫色調呼應你的柔和偏好，針織材質讓輪廓更放鬆。" : "The violet tone keeps it soft while the knit relaxes the silhouette.",
      attributes: locale === "zh-TW" ? ["霧紫", "針織", "放鬆", "晚餐"] : ["violet", "knit", "relaxed", "dinner"],
      priceBand: "$$",
      confidence: 94,
      itemType: "top",
    },
    {
      id: "top-04",
      name: locale === "zh-TW" ? "鬆弛感細羅紋上衣" : "Relaxed Rib Knit Top",
      imageUrl:
        "https://images.unsplash.com/photo-1495385794356-15371f348c31?auto=format&fit=crop&w=900&q=80",
      explanation:
        locale === "zh-TW" ? "細羅紋有質感但不搶戲，很適合拿來平衡剪裁下身。" : "A quiet rib texture balances tailored bottoms without stealing focus.",
      attributes: locale === "zh-TW" ? ["細羅紋", "中性色", "放鬆", "精緻"] : ["rib knit", "neutral", "relaxed", "refined"],
      priceBand: "$$",
      confidence: 96,
      itemType: "top",
    },
    {
      id: "dress-01",
      name: locale === "zh-TW" ? "單色 Utility 洋裝" : "Monochrome Utility Midi",
      imageUrl:
        "https://images.unsplash.com/photo-1524504388940-b1c1722653e1?auto=format&fit=crop&w=900&q=80",
      explanation:
        locale === "zh-TW" ? "完整輪廓已經成立，適合想少一點搭配步驟的日子。" : "A complete silhouette on its own for days that need fewer decisions.",
      attributes: locale === "zh-TW" ? ["洋裝", "midi", "utility", "單色"] : ["dress", "midi", "utility", "monochrome"],
      priceBand: "$$",
      confidence: 89,
      itemType: "dress",
    },
    {
      id: "dress-02",
      name: locale === "zh-TW" ? "結構感直筒洋裝" : "Structured Column Dress",
      imageUrl:
        "https://images.unsplash.com/photo-1529139574466-a303027c1d8b?auto=format&fit=crop&w=900&q=80",
      explanation:
        locale === "zh-TW" ? "直筒線條乾淨、有存在感，下身不需要再加層。" : "The column line is strong and complete, with no bottom layer needed.",
      attributes: locale === "zh-TW" ? ["洋裝", "直筒", "剪裁", "完整造型"] : ["dress", "column", "tailored", "complete"],
      priceBand: "$$$",
      confidence: 92,
      itemType: "dress",
    },
  ];
}

export function getBottomCandidates(locale: Locale = "en"): FashionRecommendation[] {
  return [
    {
      id: "bottom-01",
      name: locale === "zh-TW" ? "深炭灰直筒牛仔褲" : "Charcoal Straight Denim",
      imageUrl:
        "https://images.unsplash.com/photo-1542272604-787c3835535d?auto=format&fit=crop&w=900&q=80",
      explanation: locale === "zh-TW" ? "直筒版型保留休閒感，也能接住精緻上衣。" : "Straight denim keeps polish grounded and wearable.",
      attributes: locale === "zh-TW" ? ["直筒", "炭灰", "日常", "俐落"] : ["straight", "charcoal", "everyday", "clean"],
      priceBand: "$$",
      confidence: 86,
      itemType: "bottom",
    },
    {
      id: "bottom-02",
      name: locale === "zh-TW" ? "高腰剪裁長褲" : "High-Waist Tailored Trouser",
      imageUrl:
        "https://images.unsplash.com/photo-1506629905607-d9e297d33be7?auto=format&fit=crop&w=900&q=80",
      explanation: locale === "zh-TW" ? "高腰與俐落褲線讓放鬆上衣更有精神。" : "A high waist and crisp line make relaxed tops feel intentional.",
      attributes: locale === "zh-TW" ? ["高腰", "剪裁", "中性色", "俐落"] : ["high-waist", "tailored", "neutral", "crisp"],
      priceBand: "$$$",
      confidence: 95,
      itemType: "bottom",
    },
    {
      id: "bottom-03",
      name: locale === "zh-TW" ? "緞面垂墜長褲" : "Fluid Satin Trouser",
      imageUrl:
        "https://images.unsplash.com/photo-1515886657613-9f3515b0c78f?auto=format&fit=crop&w=900&q=80",
      explanation: locale === "zh-TW" ? "緞面帶出晚間光澤，走路時會有輕盈流動感。" : "Satin adds an evening sheen with easy movement.",
      attributes: locale === "zh-TW" ? ["緞面", "流動感", "晚間", "柔和"] : ["satin", "fluid", "evening", "soft"],
      priceBand: "$$$",
      confidence: 90,
      itemType: "bottom",
    },
    {
      id: "bottom-04",
      name: locale === "zh-TW" ? "霧米色 A 字裙" : "Misty Beige A-Line Skirt",
      imageUrl:
        "https://images.unsplash.com/photo-1503342217505-b0a15ec3261c?auto=format&fit=crop&w=900&q=80",
      explanation: locale === "zh-TW" ? "A 字線條柔化上半身結構，也保留乾淨比例。" : "The A-line softens structured tops while keeping the proportion clean.",
      attributes: locale === "zh-TW" ? ["A字", "柔和", "霧米", "比例"] : ["A-line", "soft", "misty beige", "proportion"],
      priceBand: "$$",
      confidence: 88,
      itemType: "bottom",
    },
    {
      id: "bottom-05",
      name: locale === "zh-TW" ? "黑色長版百慕達短褲" : "Longline Black Bermuda",
      imageUrl:
        "https://images.unsplash.com/photo-1516762689617-e1cffcef479d?auto=format&fit=crop&w=900&q=80",
      explanation: locale === "zh-TW" ? "長版短褲讓整體更當代，適合都會休閒方向。" : "Longline shorts make the look feel current and urban.",
      attributes: locale === "zh-TW" ? ["黑色", "長版", "都會", "休閒"] : ["black", "longline", "urban", "casual"],
      priceBand: "$$",
      confidence: 83,
      itemType: "bottom",
    },
    {
      id: "bottom-06",
      name: locale === "zh-TW" ? "柔灰垂墜半裙" : "Soft Grey Draped Skirt",
      imageUrl:
        "https://images.unsplash.com/photo-1487412720507-e7ab37603c6f?auto=format&fit=crop&w=900&q=80",
      explanation: locale === "zh-TW" ? "垂墜半裙延伸柔和感，很適合搭配短版或細羅紋上衣。" : "Draping extends the softness and pairs well with cropped or ribbed tops.",
      attributes: locale === "zh-TW" ? ["柔灰", "垂墜", "半裙", "輕盈"] : ["soft grey", "draped", "skirt", "light"],
      priceBand: "$$",
      confidence: 87,
      itemType: "bottom",
    },
  ];
}

export const stylistLooks: StylistOutfitRecommendation[] = [
  {
    topOrDressId: "top-04",
    bottomId: "bottom-02",
    summary: "Relaxed knit + tailored trousers",
    reason: "The relaxed knit balances the tailored trousers for a polished but effortless silhouette.",
  },
  {
    topOrDressId: "top-03",
    bottomId: "bottom-03",
    summary: "Soft knit + fluid satin",
    reason: "The soft knit and satin trouser keep the look fluid while the tonal contrast feels quietly intentional.",
  },
  {
    topOrDressId: "top-02",
    bottomId: "bottom-04",
    summary: "Structured vest + A-line skirt",
    reason: "A structured top balances the softer A-line skirt for an editorial shape that still feels wearable.",
  },
  {
    topOrDressId: "dress-02",
    bottomId: null,
    summary: "Structured column dress",
    reason: "The structured column dress creates a complete silhouette on its own.",
  },
];

export function getStylistRecommendation(lookIndex = 0): StylistOutfitRecommendation {
  return stylistLooks[lookIndex % stylistLooks.length];
}

function buildTopPickOutfit(locale: Locale = "en", lookIndex = 0): OutfitRecommendation {
  const topOrDressCandidates = getTopOrDressCandidates(locale);
  const bottomCandidates = getBottomCandidates(locale);
  const recommendation = getStylistRecommendation(lookIndex);
  const topOrDress = topOrDressCandidates.find((item) => item.id === recommendation.topOrDressId) || topOrDressCandidates[3];
  const bottom = recommendation.bottomId ? bottomCandidates.find((item) => item.id === recommendation.bottomId) || null : null;
  const resolvedBottom = topOrDress.itemType === "dress" ? null : bottom;

  return {
    id: `outfit-${topOrDress.id}-${resolvedBottom?.id || "solo"}`,
    name: locale === "zh-TW" ? "放鬆晚餐造型" : "Relaxed Dinner Edit",
    items: {
      topOrDress,
      bottom: resolvedBottom,
    },
    imageUrl: topOrDress.imageUrl,
    matchScore: 94,
    explanation:
      locale === "zh-TW"
        ? "柔和剪裁保留精緻感，但不會顯得太正式。"
        : "Soft tailoring keeps the look polished without feeling formal.",
    tags: locale === "zh-TW" ? ["柔和", "精緻", "晚餐"] : ["soft", "polished", "dinner"],
  };
}

export function createChatRecommendation(locale: Locale = "en") {
  return {
    view: "top-pick" as const,
    topPick: buildTopPickOutfit(locale),
    alternatives: {
      topOrDressCandidates: getTopOrDressCandidates(locale),
      bottomCandidates: getBottomCandidates(locale),
      selectedTopOrDressIndex: 0,
      selectedBottomIndex: 0,
    },
  };
}

function getMoodQuestion(locale: Locale): ChatMessage {
  return {
    id: `ai-${Date.now()}`,
    role: "assistant",
    text: locale === "zh-TW" ? "聽起來不錯。你想要哪一種氛圍？" : "Sounds good. What kind of mood are you going for?",
    quickChoices: [
      { id: "mood-polished", label: locale === "zh-TW" ? "精緻" : "Polished", prompt: locale === "zh-TW" ? "精緻" : "Polished" },
      { id: "mood-relaxed", label: locale === "zh-TW" ? "放鬆" : "Relaxed", prompt: locale === "zh-TW" ? "放鬆" : "Relaxed" },
      { id: "mood-romantic", label: locale === "zh-TW" ? "浪漫" : "Romantic", prompt: locale === "zh-TW" ? "浪漫" : "Romantic" },
      { id: "mood-minimal", label: locale === "zh-TW" ? "極簡" : "Minimal", prompt: locale === "zh-TW" ? "極簡" : "Minimal" },
    ],
  };
}

function getFormalityQuestion(locale: Locale): ChatMessage {
  return {
    id: `ai-${Date.now()}`,
    role: "assistant",
    text: locale === "zh-TW" ? "收到。你想要看起來多正式？" : "Got it. How dressed-up do you want to feel?",
    quickChoices: [
      { id: "formality-casual", label: locale === "zh-TW" ? "休閒" : "Casual", prompt: locale === "zh-TW" ? "休閒" : "Casual" },
      { id: "formality-smart-casual", label: locale === "zh-TW" ? "聰明休閒" : "Smart casual", prompt: locale === "zh-TW" ? "聰明休閒" : "Smart casual" },
      { id: "formality-dressy", label: locale === "zh-TW" ? "正式一點" : "Dressy", prompt: locale === "zh-TW" ? "正式一點" : "Dressy" },
    ],
  };
}

function getOutfitReply(locale: Locale): ChatMessage {
  return {
    id: `ai-${Date.now()}`,
    role: "assistant",
    text: locale === "zh-TW" ? "我有一套很適合你的方向。" : "I have something in mind. This is the look I'd start with.",
    recommendation: createChatRecommendation(locale),
  };
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
  const isMoodAnswer =
    normalized.startsWith("mood:") || ["polished", "relaxed", "romantic", "minimal", "精緻", "放鬆", "浪漫", "極簡"].includes(normalized);
  const isFormalityAnswer =
    normalized.startsWith("formality:") || ["casual", "smart casual", "dressy", "休閒", "聰明休閒", "正式一點"].includes(normalized);
  const vagueTerms =
    locale === "zh-TW"
      ? ["不確定", "不知道", "隨便", "給我驚喜", "還不太確定"]
      : ["not sure", "surprise", "anything", "don't know"];

  if (isMoodAnswer) {
    return getFormalityQuestion(locale);
  }

  if (isFormalityAnswer) {
    return getOutfitReply(locale);
  }

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
    return getMoodQuestion(locale);
  }

  return {
    id: `ai-${Date.now()}`,
    role: "assistant",
    text: t.assistant.clarify,
    quickChoices: getQuickStyleChoices(locale),
    visualChoices: getVisualStyleChoices(locale),
  };
}
