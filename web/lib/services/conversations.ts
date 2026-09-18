import type { Locale } from "@/lib/i18n/dictionaries";
import { basePreferenceSignals, createStylistReply, getInitialMessages, initialMessages } from "@/lib/mock/stylist";
import type { ChatMessage, Conversation, PreferenceSignal } from "@/lib/types";

const CONVERSATIONS_KEY = "intentweave.conversations";
const CURRENT_KEY = "intentweave.currentConversation";

function isBrowser() {
  return typeof window !== "undefined";
}

function now() {
  return new Date().toISOString();
}

function createId(prefix: string) {
  return `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

function withConversation(message: ChatMessage, conversationId: string): ChatMessage {
  return {
    ...message,
    id: message.id || createId("msg"),
    conversationId,
    createdAt: message.createdAt || now(),
  };
}

function cloneWelcomeMessages(conversationId: string, locale: Locale = "en"): ChatMessage[] {
  return getInitialMessages(locale).map((message) => withConversation({ ...message, id: createId("msg") }, conversationId));
}

function seedConversation(userId: string, title: string, userPrompt: string, createdAt: string): Conversation {
  const id = createId("conv");
  const userMessage: ChatMessage = {
    id: createId("msg"),
    conversationId: id,
    role: "user",
    text: userPrompt,
    createdAt,
  };
  const assistantMessage = withConversation(createStylistReply(userPrompt), id);

  return {
    id,
    userId,
    title,
    createdAt,
    updatedAt: createdAt,
    messages: [withConversation(initialMessages[0], id), userMessage, assistantMessage],
    recommendationFeedback: {},
    preferenceSignals: basePreferenceSignals,
  };
}

function readAll(): Conversation[] {
  if (!isBrowser()) {
    return [];
  }

  const raw = window.localStorage.getItem(CONVERSATIONS_KEY);

  if (!raw) {
    return [];
  }

  try {
    return JSON.parse(raw) as Conversation[];
  } catch {
    window.localStorage.removeItem(CONVERSATIONS_KEY);
    return [];
  }
}

function writeAll(conversations: Conversation[]) {
  window.localStorage.setItem(CONVERSATIONS_KEY, JSON.stringify(conversations));
  window.dispatchEvent(new Event("intentweave-conversations-change"));
}

function titleFromPrompt(prompt: string) {
  const cleaned = prompt
    .replace(/^i need\s+/i, "")
    .replace(/^i want\s+/i, "")
    .replace(/^show me\s+/i, "")
    .trim();

  if (!cleaned) {
    return "New style conversation";
  }

  return cleaned.length > 34 ? `${cleaned.slice(0, 31)}...` : cleaned;
}

export const conversationService = {
  ensureSeeded(userId: string) {
    const existing = readAll().filter((conversation) => conversation.userId === userId);

    if (existing.length > 0) {
      return existing;
    }

    const today = new Date();
    const yesterday = new Date(Date.now() - 24 * 60 * 60 * 1000);
    const previous = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000);
    const seeded = [
      seedConversation(userId, "Tokyo autumn outfits", "I am traveling to Tokyo in autumn and want layered outfits", today.toISOString()),
      seedConversation(userId, "Workwear refresh", "I need an outfit for a work event", today.toISOString()),
      seedConversation(userId, "Weekend date outfit", "I need a dinner date outfit", yesterday.toISOString()),
      seedConversation(userId, "Minimal wardrobe ideas", "Minimal and clean", previous.toISOString()),
    ];

    writeAll(seeded);
    window.localStorage.setItem(CURRENT_KEY, seeded[0].id);
    return seeded;
  },

  list(userId: string) {
    return readAll()
      .filter((conversation) => conversation.userId === userId)
      .sort((a, b) => Date.parse(b.updatedAt) - Date.parse(a.updatedAt));
  },

  getCurrentId() {
    if (!isBrowser()) {
      return null;
    }

    return window.localStorage.getItem(CURRENT_KEY);
  },

  setCurrentId(id: string) {
    window.localStorage.setItem(CURRENT_KEY, id);
    window.dispatchEvent(new Event("intentweave-conversations-change"));
  },

  create(userId: string, locale: Locale = "en") {
    const id = createId("conv");
    const timestamp = now();
    const conversation: Conversation = {
      id,
      userId,
      title: "New fashion conversation",
      createdAt: timestamp,
      updatedAt: timestamp,
      messages: cloneWelcomeMessages(id, locale),
      recommendationFeedback: {},
      preferenceSignals: basePreferenceSignals,
    };

    writeAll([conversation, ...readAll()]);
    this.setCurrentId(id);
    return conversation;
  },

  update(conversation: Conversation) {
    const conversations = readAll();
    const next = conversations.map((item) => (item.id === conversation.id ? conversation : item));
    writeAll(next);
    return conversation;
  },

  appendMessage(conversation: Conversation, message: ChatMessage) {
    const timestamp = now();
    const nextMessages = [...conversation.messages, withConversation(message, conversation.id)];
    const firstUserMessage = nextMessages.find((item) => item.role === "user")?.text;
    const next: Conversation = {
      ...conversation,
      title:
        conversation.title === "New fashion conversation" && firstUserMessage
          ? titleFromPrompt(firstUserMessage)
          : conversation.title,
      updatedAt: timestamp,
      messages: nextMessages,
    };

    return this.update(next);
  },

  appendTurn(conversation: Conversation, userText: string, assistantMessage: ChatMessage) {
    const timestamp = now();
    const userMessage: ChatMessage = {
      id: createId("msg"),
      conversationId: conversation.id,
      role: "user",
      text: userText,
      createdAt: timestamp,
    };
    const firstMeaningfulTitle =
      conversation.title === "New fashion conversation" ? titleFromPrompt(userText) : conversation.title;
    const next: Conversation = {
      ...conversation,
      title: firstMeaningfulTitle,
      updatedAt: timestamp,
      messages: [
        ...conversation.messages,
        userMessage,
        withConversation({ ...assistantMessage, id: createId("msg") }, conversation.id),
      ],
    };

    return this.update(next);
  },

  updateFeedback(conversation: Conversation, recommendationId: string, value: "like" | "dislike") {
    const likes = Object.values({ ...conversation.recommendationFeedback, [recommendationId]: value }).filter(
      (item) => item === "like",
    ).length;
    const dislikes = Object.values({ ...conversation.recommendationFeedback, [recommendationId]: value }).filter(
      (item) => item === "dislike",
    ).length;
    const nextSignals: PreferenceSignal[] = basePreferenceSignals.map((signal, index) => ({
      ...signal,
      value: Math.min(96, Math.max(18, signal.value + likes * 4 - dislikes * (index === 3 ? -3 : 2))),
    }));

    return this.update({
      ...conversation,
      updatedAt: now(),
      recommendationFeedback: {
        ...conversation.recommendationFeedback,
        [recommendationId]: value,
      },
      preferenceSignals: nextSignals,
    });
  },
};
