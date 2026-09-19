import type {
  FashionRecommendation,
  OutfitRecommendation,
  PreferenceDimensionRatings,
  PreferenceItemSnapshot,
  PreferenceRatingDimension,
  TryOnFeedbackEntry,
  UserPreferenceState,
  WardrobeCategory,
} from "@/lib/types";

const PREFERENCES_KEY = "intentweave.preferences";
const PREFERENCES_CHANGE_EVENT = "intentweave-preferences-change";
const RECENT_ROUND_LIMIT = 3;
const RATING_DIMENSIONS: PreferenceRatingDimension[] = ["visual_impact", "polished_formality", "soft_energy"];

type PreferenceStore = Record<string, UserPreferenceState>;

interface PreferenceContext {
  conversationId?: string;
  messageId?: string;
  roundKey?: string;
}

function isBrowser() {
  return typeof window !== "undefined";
}

function now() {
  return new Date().toISOString();
}

function emptyState(): UserPreferenceState {
  return {
    savedItems: {},
    dislikedItems: {},
    itemRatings: {},
    tryOnFeedback: {},
    recentRecommendationRounds: [],
  };
}

function readStore(): PreferenceStore {
  if (!isBrowser()) {
    return {};
  }

  const raw = window.localStorage.getItem(PREFERENCES_KEY);

  if (!raw) {
    return {};
  }

  try {
    return JSON.parse(raw) as PreferenceStore;
  } catch {
    window.localStorage.removeItem(PREFERENCES_KEY);
    return {};
  }
}

function writeStore(store: PreferenceStore) {
  window.localStorage.setItem(PREFERENCES_KEY, JSON.stringify(store));
  window.dispatchEvent(new Event(PREFERENCES_CHANGE_EVENT));
}

function readUserState(userId: string) {
  return normalizeState(readStore()[userId]);
}

function updateUserState(userId: string, updater: (state: UserPreferenceState) => UserPreferenceState) {
  const store = readStore();
  const nextState = updater(normalizeState(store[userId]));
  writeStore({ ...store, [userId]: nextState });
  return nextState;
}

function normalizeState(state?: UserPreferenceState): UserPreferenceState {
  if (!state) {
    return emptyState();
  }

  const itemRatings: UserPreferenceState["itemRatings"] = {};

  Object.entries(state.itemRatings || {}).forEach(([itemId, value]) => {
    if (typeof value === "number") {
      itemRatings[itemId] = {
        visual_impact: value,
        polished_formality: value,
        soft_energy: value,
      };
      return;
    }

    if (!value || typeof value !== "object") {
      return;
    }

    const nextRatings: PreferenceDimensionRatings = {};
    RATING_DIMENSIONS.forEach((dimension) => {
      const rating = (value as PreferenceDimensionRatings)[dimension];

      if (typeof rating === "number" && Number.isInteger(rating) && rating >= 1 && rating <= 5) {
        nextRatings[dimension] = rating;
      }
    });

    if (Object.keys(nextRatings).length > 0) {
      itemRatings[itemId] = nextRatings;
    }
  });

  return {
    ...emptyState(),
    ...state,
    itemRatings,
  };
}

function categoryForItem(item: FashionRecommendation): WardrobeCategory {
  if (item.itemType === "bottom" || item.id.startsWith("bottom-")) {
    return "bottoms";
  }

  if (item.itemType === "dress" || item.id.startsWith("dress-")) {
    return "dresses";
  }

  return "tops";
}

function snapshotItem(
  item: FashionRecommendation,
  context: PreferenceContext = {},
  category: WardrobeCategory = categoryForItem(item),
): PreferenceItemSnapshot {
  return {
    id: item.id,
    name: item.name,
    imageUrl: item.imageUrl,
    category,
    brand: "Saved",
    attributes: item.attributes.slice(0, 4),
    source: "recommended",
    likedBySave: true,
    savedAt: now(),
    conversationId: context.conversationId,
    messageId: context.messageId,
    roundKey: context.roundKey,
  };
}

function outfitItems(outfit: OutfitRecommendation) {
  return [outfit.items.topOrDress, outfit.items.bottom].filter(Boolean) as FashionRecommendation[];
}

export function outfitKeyFromItems(items: FashionRecommendation[]) {
  return items
    .map((item) => item.id)
    .sort()
    .join("+");
}

export const preferenceService = {
  changeEvent: PREFERENCES_CHANGE_EVENT,

  get(userId: string): UserPreferenceState {
    return readUserState(userId);
  },

  listSavedItems(userId: string): PreferenceItemSnapshot[] {
    return Object.values(readUserState(userId).savedItems).sort((a, b) => Date.parse(b.savedAt) - Date.parse(a.savedAt));
  },

  isSaved(userId: string, itemId: string) {
    return Boolean(readUserState(userId).savedItems[itemId]);
  },

  isDisliked(userId: string, itemId: string) {
    return Boolean(readUserState(userId).dislikedItems[itemId]);
  },

  feedbackFor(userId: string, itemId: string): "like" | "dislike" | undefined {
    const state = readUserState(userId);

    if (state.savedItems[itemId]) {
      return "like";
    }

    if (state.dislikedItems[itemId]) {
      return "dislike";
    }

    return undefined;
  },

  registerRecommendationRound(userId: string, roundKey: string) {
    updateUserState(userId, (state) => {
      const recentRecommendationRounds = [
        roundKey,
        ...state.recentRecommendationRounds.filter((item) => item !== roundKey),
      ].slice(0, RECENT_ROUND_LIMIT);

      return { ...state, recentRecommendationRounds };
    });
  },

  toggleSavedItem(userId: string, item: FashionRecommendation, context: PreferenceContext = {}) {
    return updateUserState(userId, (state) => {
      const savedItems = { ...state.savedItems };
      const dislikedItems = { ...state.dislikedItems };

      if (savedItems[item.id]) {
        delete savedItems[item.id];
      } else {
        savedItems[item.id] = snapshotItem(item, context);
        delete dislikedItems[item.id];
      }

      return { ...state, savedItems, dislikedItems };
    });
  },

  removeSavedItem(userId: string, itemId: string) {
    return updateUserState(userId, (state) => {
      const savedItems = { ...state.savedItems };
      delete savedItems[itemId];

      return { ...state, savedItems };
    });
  },

  toggleSavedOutfitItems(userId: string, outfit: OutfitRecommendation, context: PreferenceContext = {}) {
    return updateUserState(userId, (state) => {
      const savedItems = { ...state.savedItems };
      const dislikedItems = { ...state.dislikedItems };
      const items = outfitItems(outfit);
      const allSaved = items.length > 0 && items.every((item) => savedItems[item.id]);

      items.forEach((item) => {
        if (allSaved) {
          delete savedItems[item.id];
          return;
        }

        savedItems[item.id] = snapshotItem(item, context);
        delete dislikedItems[item.id];
      });

      return { ...state, savedItems, dislikedItems };
    });
  },

  toggleDislikedItem(userId: string, item: FashionRecommendation, context: PreferenceContext = {}) {
    return updateUserState(userId, (state) => {
      const savedItems = { ...state.savedItems };
      const dislikedItems = { ...state.dislikedItems };

      if (dislikedItems[item.id]) {
        delete dislikedItems[item.id];
      } else {
        dislikedItems[item.id] = snapshotItem(item, context);
        delete savedItems[item.id];
      }

      return { ...state, savedItems, dislikedItems };
    });
  },

  setDimensionRating(userId: string, itemId: string, dimension: PreferenceRatingDimension, rating: number) {
    return updateUserState(userId, (state) => {
      const itemRatings = { ...state.itemRatings };
      const currentRatings = { ...(itemRatings[itemId] || {}) };

      if (currentRatings[dimension] === rating) {
        delete currentRatings[dimension];
      } else if (Number.isInteger(rating) && rating >= 1 && rating <= 5) {
        currentRatings[dimension] = rating;
      }

      if (Object.keys(currentRatings).length === 0) {
        delete itemRatings[itemId];
      } else {
        itemRatings[itemId] = currentRatings;
      }

      return { ...state, itemRatings };
    });
  },

  setTryOnFeedback(
    userId: string,
    items: FashionRecommendation[],
    feedback: "like" | "dislike",
    context: PreferenceContext = {},
  ) {
    const outfitKey = outfitKeyFromItems(items);

    if (!outfitKey) {
      return readUserState(userId);
    }

    return updateUserState(userId, (state) => {
      const entry: TryOnFeedbackEntry = {
        outfitKey,
        feedback,
        itemIds: items.map((item) => item.id),
        timestamp: now(),
        conversationId: context.conversationId,
        roundKey: context.roundKey,
      };

      return {
        ...state,
        tryOnFeedback: {
          ...state.tryOnFeedback,
          [outfitKey]: entry,
        },
      };
    });
  },
};

export function buildPreferenceRatingFeedback(itemId: string, ratings: PreferenceDimensionRatings) {
  return {
    item_id: itemId,
    attribute_ratings: RATING_DIMENSIONS.flatMap((dimension) => {
      const rating = ratings[dimension];

      if (typeof rating !== "number" || !Number.isInteger(rating) || rating < 1 || rating > 5) {
        return [];
      }

      return [{ attribute: dimension, stars: rating }];
    }),
  };
}
