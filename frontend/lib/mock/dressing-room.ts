import type { OutfitSlot, WardrobeCategory, WardrobeItem } from "@/lib/types";

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

export function getSavedWardrobeItems(items: WardrobeItem[]): WardrobeItem[] {
  return items;
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
