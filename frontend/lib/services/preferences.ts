import type {
  FashionRecommendation,
  OutfitRecommendation,
  PreferenceItemSnapshot,
  TryOnFeedbackEntry,
  UserPreferenceState,
  WardrobeCategory,
} from "@/lib/types";

const PREFERENCES_KEY = "intentweave.preferences";
const PREFERENCES_CHANGE_EVENT = "intentweave-preferences-change";
const RECENT_ROUND_LIMIT = 3;

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
  return readStore()[userId] || emptyState();
}

function updateUserState(userId: string, updater: (state: UserPreferenceState) => UserPreferenceState) {
  const store = readStore();
  const nextState = updater(store[userId] || emptyState());
  writeStore({ ...store, [userId]: nextState });
  return nextState;
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

  toggleRating(userId: string, itemId: string, rating: number) {
    return updateUserState(userId, (state) => {
      const itemRatings = { ...state.itemRatings };

      if (itemRatings[itemId] === rating) {
        delete itemRatings[itemId];
      } else {
        itemRatings[itemId] = rating;
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
