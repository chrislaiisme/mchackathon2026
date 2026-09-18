"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Heart, RefreshCw, Send, SlidersHorizontal, ThumbsDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/components/intentweave/i18n-provider";
import { createStylistReply } from "@/lib/mock/stylist";
import { authService } from "@/lib/services/auth";
import { conversationService } from "@/lib/services/conversations";
import type { ChatMessage, Conversation, FashionRecommendation, PreferenceSignal, VisualChoice } from "@/lib/types";

function RecommendationCard({
  item,
  onFeedback,
  feedback,
}: {
  item: FashionRecommendation;
  onFeedback: (id: string, value: "like" | "dislike", itemName: string) => void;
  feedback?: "like" | "dislike";
}) {
  const { t } = useI18n();

  return (
    <article className="group overflow-hidden border border-border bg-card">
      <div
        className="fashion-image aspect-[3/4] bg-muted transition duration-700 group-hover:scale-[1.03]"
        style={{ backgroundImage: `url(${item.imageUrl})` }}
        aria-label={item.name}
      />
      <div className="space-y-4 p-4">
        <div>
          <div className="flex items-start justify-between gap-4">
            <h3 className="font-serif text-xl leading-tight text-foreground">{item.name}</h3>
            <span className="mt-1 border-b border-primary/50 pb-1 text-xs text-muted-foreground">
              {item.confidence}% {t.stylist.match}
            </span>
          </div>
          <p className="mt-3 text-sm leading-6 text-muted-foreground">{item.explanation}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          {item.attributes.map((attribute) => (
            <span key={attribute} className="border border-border px-2.5 py-1 text-xs text-muted-foreground">
              {attribute}
            </span>
          ))}
        </div>
        <div className="flex items-center justify-between gap-2">
          <span className="text-xs text-muted-foreground">
            {t.stylist.priceBand} {item.priceBand}
          </span>
          <div className="flex gap-1">
            <Button
              size="icon-sm"
              variant={feedback === "like" ? "default" : "outline"}
              aria-label={`${t.stylist.like} ${item.name}`}
              onClick={() => onFeedback(item.id, "like", item.name)}
            >
              <Heart className="size-4" />
            </Button>
            <Button
              size="icon-sm"
              variant={feedback === "dislike" ? "destructive" : "outline"}
              aria-label={`${t.stylist.dislike} ${item.name}`}
              onClick={() => onFeedback(item.id, "dislike", item.name)}
            >
              <ThumbsDown className="size-4" />
            </Button>
          </div>
        </div>
      </div>
    </article>
  );
}

function VisualChoiceCard({ choice, onSelect }: { choice: VisualChoice; onSelect: (prompt: string) => void }) {
  return (
    <button
      type="button"
      onClick={() => onSelect(choice.prompt)}
      className="group min-w-[220px] overflow-hidden border border-border bg-card text-left transition hover:border-foreground/40 md:min-w-0"
    >
      <div className="fashion-image aspect-[4/5] bg-muted" style={{ backgroundImage: `url(${choice.imageUrl})` }} />
      <div className="space-y-1 p-4">
        <div className="text-xs uppercase tracking-[0.2em] text-muted-foreground">{choice.title}</div>
        <div className="font-serif text-xl text-foreground">{choice.subtitle}</div>
      </div>
    </button>
  );
}

function MessageBlock({
  message,
  index,
  onChoice,
  onFeedback,
  feedback,
}: {
  message: ChatMessage;
  index: number;
  onChoice: (prompt: string) => void;
  onFeedback: (id: string, value: "like" | "dislike", itemName: string) => void;
  feedback: Record<string, "like" | "dislike">;
}) {
  const { t } = useI18n();
  const isUser = message.role === "user";

  if (isUser) {
    return (
      <div className="ml-auto max-w-2xl border-l border-foreground pl-5 text-right">
        <p className="text-sm uppercase tracking-[0.18em] text-muted-foreground">You</p>
        <p className="mt-2 text-xl leading-8 text-foreground">{message.text}</p>
      </div>
    );
  }

  return (
    <section className="space-y-5">
      <div className="grid gap-4 md:grid-cols-[84px_minmax(0,1fr)]">
        <div className="text-xs uppercase tracking-[0.22em] text-muted-foreground">
          {String(index + 1).padStart(2, "0")}
        </div>
        <div>
          <p className="font-serif text-2xl leading-9 text-foreground">{message.text}</p>
        </div>
      </div>

      {message.visualChoices && (
        <div className="grid auto-cols-[220px] grid-flow-col gap-3 overflow-x-auto pb-2 md:grid-flow-row md:grid-cols-3 md:overflow-visible">
          {message.visualChoices.map((choice) => (
            <VisualChoiceCard key={choice.id} choice={choice} onSelect={onChoice} />
          ))}
        </div>
      )}

      {message.quickChoices && (
        <div className="flex flex-wrap gap-2 md:pl-[100px]">
          {message.quickChoices.map((choice) => (
            <Button key={choice.id} variant="outline" size="sm" onClick={() => onChoice(choice.prompt)}>
              {choice.label}
            </Button>
          ))}
          <span className="px-2 py-1 text-sm text-muted-foreground">{t.stylist.noneOfThese}</span>
        </div>
      )}

      {message.recommendations && (
        <div className="grid gap-4 md:grid-cols-3">
          {message.recommendations.map((item) => (
            <RecommendationCard key={item.id} item={item} feedback={feedback[item.id]} onFeedback={onFeedback} />
          ))}
        </div>
      )}
    </section>
  );
}

function StylePanel({ signals, feedbackCount }: { signals: PreferenceSignal[]; feedbackCount: number }) {
  const { t } = useI18n();
  const topSignals = signals.filter((signal) => signal.direction !== "down").slice(0, 4);
  const message =
    feedbackCount > 0
      ? t.stylist.likedSignals
          .replace("{count}", String(feedbackCount))
          .replace("{plural}", feedbackCount > 1 ? "s" : "")
      : t.stylist.emptySignals;

  return (
    <aside className="space-y-6 border-t border-border pt-6 lg:border-l lg:border-t-0 lg:pl-6 lg:pt-0">
      <div>
        <p className="text-xs uppercase tracking-[0.22em] text-muted-foreground">{t.stylist.yourStyle}</p>
        <div className="mt-5 flex flex-wrap gap-2">
          {topSignals.map((signal) => (
            <span key={signal.label} className="border border-border bg-card px-3 py-2 text-sm">
              {signal.label.replace(" Colors", "").replace(" Fit", "")}
            </span>
          ))}
        </div>
      </div>
      <p className="font-serif text-2xl leading-8 text-foreground">{t.stylist.evolves}</p>
      <p className="text-sm leading-6 text-muted-foreground">{message}</p>
      <Link href="/profile" className="inline-flex border-b border-primary pb-1 text-sm font-medium text-foreground">
        {t.stylist.viewProfile}
      </Link>
    </aside>
  );
}

export function StylistExperience() {
  const router = useRouter();
  const { locale, t } = useI18n();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string>();
  const [input, setInput] = useState("");
  const [isGenerating, setIsGenerating] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const shouldFollowRef = useRef(true);

  const activeConversation = conversations.find((conversation) => conversation.id === activeId);

  const refreshConversations = useCallback(() => {
    const user = authService.getSession();

    if (!user) {
      router.replace("/login");
      return;
    }

    const seeded = conversationService.ensureSeeded(user.id);
    const list = seeded.length ? conversationService.list(user.id) : [];
    const currentId = conversationService.getCurrentId();
    const nextActiveId =
      currentId && list.some((conversation) => conversation.id === currentId) ? currentId : list[0]?.id;

    if (nextActiveId && nextActiveId !== currentId) {
      conversationService.setCurrentId(nextActiveId);
    }

    setConversations(list);
    setActiveId(nextActiveId);
  }, [router]);

  useEffect(() => {
    queueMicrotask(refreshConversations);

    function handleChange() {
      refreshConversations();
    }

    window.addEventListener("intentweave-conversations-change", handleChange);
    window.addEventListener("intentweave-auth-change", handleChange);

    return () => {
      window.removeEventListener("intentweave-conversations-change", handleChange);
      window.removeEventListener("intentweave-auth-change", handleChange);
    };
  }, [refreshConversations]);

  useEffect(() => {
    if (shouldFollowRef.current) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
    }
  }, [activeConversation?.messages.length, isGenerating, activeId]);

  function handleScroll() {
    const element = scrollRef.current;

    if (!element) {
      return;
    }

    const distanceFromBottom = element.scrollHeight - element.scrollTop - element.clientHeight;
    shouldFollowRef.current = distanceFromBottom < 140;
  }

  function createNewSession() {
    const user = authService.getSession();

    if (!user) {
      router.replace("/login");
      return;
    }

    shouldFollowRef.current = true;
    conversationService.create(user.id, locale);
  }

  function persistConversation(next: Conversation) {
    const list = conversationService.list(next.userId);
    setConversations(list);
    setActiveId(next.id);
  }

  function sendPrompt(prompt: string) {
    const trimmed = prompt.trim();

    if (!trimmed || !activeConversation || isGenerating) {
      return;
    }

    shouldFollowRef.current = true;
    let nextConversation = conversationService.appendMessage(activeConversation, {
      id: `user-${Date.now()}`,
      role: "user",
      text: trimmed,
      createdAt: new Date().toISOString(),
    });

    persistConversation(nextConversation);
    setInput("");
    setIsGenerating(true);

    window.setTimeout(() => {
      const latest =
        conversationService.list(nextConversation.userId).find((conversation) => conversation.id === nextConversation.id) ||
        nextConversation;
      nextConversation = conversationService.appendMessage(latest, createStylistReply(trimmed, locale));
      persistConversation(nextConversation);
      setIsGenerating(false);
    }, 420);
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    sendPrompt(input);
  }

  function handleFeedback(id: string, value: "like" | "dislike", itemName: string) {
    if (!activeConversation || isGenerating) {
      return;
    }

    shouldFollowRef.current = true;
    let nextConversation = conversationService.updateFeedback(activeConversation, id, value);
    const feedbackText =
      value === "like"
        ? locale === "zh-TW"
          ? `我喜歡 ${itemName}，想看類似方向。`
          : `I like ${itemName}. Show me similar directions.`
        : locale === "zh-TW"
          ? `我不太喜歡 ${itemName}，請幫我調整。`
          : `I do not love ${itemName}. Refine it.`;

    nextConversation = conversationService.appendMessage(nextConversation, {
      id: `user-feedback-${Date.now()}`,
      role: "user",
      text: feedbackText,
    });
    nextConversation = conversationService.appendMessage(nextConversation, {
      id: `assistant-feedback-${Date.now()}`,
      role: "assistant",
      text: value === "like" ? t.assistant.feedbackLike : t.assistant.feedbackDislike,
      quickChoices: [
        { id: "similar", label: t.choices.showSimilar, prompt: locale === "zh-TW" ? "看類似款" : "Show me something similar" },
        { id: "casual", label: t.choices.makeCasual, prompt: locale === "zh-TW" ? "更休閒一點" : "I like this, but make it more casual" },
        { id: "color", label: t.choices.keepColor, prompt: locale === "zh-TW" ? "保留顏色但換輪廓" : "I like the color but not the silhouette" },
      ],
    });
    persistConversation(nextConversation);
  }

  const feedback = activeConversation?.recommendationFeedback || {};
  const signals = activeConversation?.preferenceSignals || [];

  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_280px]">
      <section className="min-h-[calc(100vh-8rem)] overflow-hidden border border-border bg-card">
        <div className="border-b border-border px-5 py-5 sm:px-8">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <p className="text-xs uppercase tracking-[0.24em] text-muted-foreground">{t.stylist.eyebrow}</p>
              <h1 className="mt-2 font-serif text-4xl leading-tight tracking-tight text-foreground">
                {activeConversation?.title || t.stylist.fallbackTitle}
              </h1>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" size="sm" onClick={createNewSession}>
                {t.stylist.newSession}
              </Button>
              <Button variant="outline" size="sm" onClick={() => sendPrompt(locale === "zh-TW" ? "看類似方向" : "Show me something similar")}>
                <RefreshCw className="size-4" />
                {t.stylist.similar}
              </Button>
              <Button variant="outline" size="sm" onClick={() => sendPrompt(locale === "zh-TW" ? "我喜歡，但想要更休閒一點" : "I like this, but make it more casual")}>
                <SlidersHorizontal className="size-4" />
                {t.stylist.refine}
              </Button>
            </div>
          </div>
        </div>

        <div
          ref={scrollRef}
          onScroll={handleScroll}
          className="h-[calc(100vh-17rem)] min-h-[560px] space-y-12 overflow-y-auto p-5 sm:p-8"
        >
          {activeConversation?.messages.map((message, index) => (
            <MessageBlock
              key={message.id}
              message={message}
              index={index}
              onChoice={sendPrompt}
              onFeedback={handleFeedback}
              feedback={feedback}
            />
          ))}

          {isGenerating && (
            <div className="border-l border-primary pl-5 font-serif text-2xl text-muted-foreground">
              {t.stylist.generating}
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        <form onSubmit={handleSubmit} className="border-t border-border bg-card p-4 sm:p-5">
          <div className="flex gap-2">
            <input
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder={t.stylist.input}
              className="h-12 min-w-0 flex-1 border border-input bg-background px-4 text-sm outline-none transition focus:border-primary"
            />
            <Button type="submit" size="lg" aria-label={t.stylist.send} disabled={isGenerating}>
              <Send className="size-4" />
              {t.stylist.send}
            </Button>
          </div>
        </form>
      </section>

      <StylePanel signals={signals} feedbackCount={Object.keys(feedback).length} />
    </div>
  );
}
