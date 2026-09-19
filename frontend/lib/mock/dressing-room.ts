import type { Locale } from "@/lib/i18n/dictionaries";
import { getRecommendations } from "@/lib/mock/stylist";
import type { Conversation, OutfitSlot, WardrobeCategory, WardrobeItem } from "@/lib/types";

export const wardrobeCategories: Array<"all" | WardrobeCategory> = [
  "all",
  "tops",
  "bottoms",
  "dresses",
  "outerwear",
  "shoes",
  "accessories",
];

export const outfitSlots: OutfitSlot[] = ["top", "bottom", "dress", "outerwear", "shoes", "accessories"];

const fallbackWardrobe: WardrobeItem[] = [
  {
    id: "saved-top-1",
    name: "Fine Rib Knit Tank",
    imageUrl: "https://images.unsplash.com/photo-1503342217505-b0a15ec3261c?auto=format&fit=crop&w=900&q=80",
    category: "tops",
    brand: "Atelier Edit",
    attributes: ["minimal", "soft knit"],
  },
  {
    id: "saved-bottom-1",
    name: "Fluid Satin Trouser",
    imageUrl: "https://images.unsplash.com/photo-1495385794356-15371f348c31?auto=format&fit=crop&w=900&q=80",
    category: "bottoms",
    brand: "Line Studio",
    attributes: ["neutral", "fluid"],
  },
  {
    id: "saved-dress-1",
    name: "Monochrome Utility Midi",
    imageUrl: "https://images.unsplash.com/photo-1524504388940-b1c1722653e1?auto=format&fit=crop&w=900&q=80",
    category: "dresses",
    brand: "Intent Archive",
    attributes: ["midi", "versatile"],
  },
  {
    id: "saved-outerwear-1",
    name: "Relaxed Long Blazer",
    imageUrl: "https://images.unsplash.com/photo-1485968579580-b6d095142e6e?auto=format&fit=crop&w=900&q=80",
    category: "outerwear",
    brand: "Northline",
    attributes: ["tailored", "layering"],
  },
  {
    id: "saved-shoes-1",
    name: "Soft Leather Mary Jane",
    imageUrl: "https://images.unsplash.com/photo-1543163521-1bf539c55dd2?auto=format&fit=crop&w=900&q=80",
    category: "shoes",
    brand: "Mira",
    attributes: ["polished", "daily"],
  },
  {
    id: "saved-accessory-1",
    name: "Slim Crescent Bag",
    imageUrl: "https://images.unsplash.com/photo-1594223274512-ad4803739b7c?auto=format&fit=crop&w=900&q=80",
    category: "accessories",
    brand: "Carry Form",
    attributes: ["structured", "black"],
  },
];

const zhNames: Record<string, Pick<WardrobeItem, "name" | "brand" | "attributes">> = {
  "saved-top-1": { name: "細羅紋針織背心", brand: "Atelier Edit", attributes: ["極簡", "柔軟針織"] },
  "saved-bottom-1": { name: "緞面垂墜長褲", brand: "Line Studio", attributes: ["中性色", "流動感"] },
  "saved-dress-1": { name: "單色 Utility 洋裝", brand: "Intent Archive", attributes: ["midi", "百搭"] },
  "saved-outerwear-1": { name: "寬鬆長版西外", brand: "Northline", attributes: ["剪裁", "層次"] },
  "saved-shoes-1": { name: "柔軟皮革瑪莉珍鞋", brand: "Mira", attributes: ["精緻", "日常"] },
  "saved-accessory-1": { name: "窄版月牙包", brand: "Carry Form", attributes: ["結構感", "黑色"] },
};

function recommendationCategory(index: number): WardrobeCategory {
  return (["dresses", "outerwear", "dresses"] as WardrobeCategory[])[index] || "tops";
}

function likedRecommendationItems(conversations: Conversation[], locale: Locale): WardrobeItem[] {
  const likedIds = new Set(
    conversations.flatMap((conversation) =>
      Object.entries(conversation.recommendationFeedback)
        .filter(([, value]) => value === "like")
        .map(([id]) => id),
    ),
  );

  return getRecommendations(locale)
    .filter((recommendation) => likedIds.has(recommendation.id))
    .map((recommendation, index) => ({
      id: recommendation.id,
      name: recommendation.name,
      imageUrl: recommendation.imageUrl,
      category: recommendationCategory(index),
      brand: locale === "zh-TW" ? "已收藏造型" : "Saved look",
      attributes: recommendation.attributes.slice(0, 2),
    }));
}

export function getSavedWardrobeItems(conversations: Conversation[], locale: Locale): WardrobeItem[] {
  const likedItems = likedRecommendationItems(conversations, locale);

  if (likedItems.length > 0) {
    return likedItems;
  }

  if (locale === "zh-TW") {
    return fallbackWardrobe.map((item) => ({
      ...item,
      ...zhNames[item.id],
    }));
  }

  return fallbackWardrobe;
}

export function getOutfitSlot(category: WardrobeCategory): OutfitSlot {
  if (category === "tops") {
    return "top";
  }

  if (category === "bottoms") {
    return "bottom";
  }

  if (category === "dresses") {
    return "dress";
  }

  return category;
}
